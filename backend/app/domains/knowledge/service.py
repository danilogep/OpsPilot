"""Serviço da base de conhecimento: ingestão, consulta e busca fundamentada."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequestContext
from app.core.errors import NotFoundError
from app.core.files import KNOWLEDGE_EXTENSIONS, validate_upload
from app.core.logging import get_logger
from app.core.pagination import PageParams
from app.db.base import utcnow
from app.db.models import DocumentChunk, DocumentStatus, KnowledgeDocument, User
from app.domains.audit import service as audit_service
from app.domains.knowledge.chunking import chunk_text
from app.domains.knowledge.extraction import extract_text
from app.domains.knowledge.search import SearchHit, search_chunks
from app.integrations.llm.base import LLMFeature, LLMMessage, LLMRequest
from app.integrations.llm.factory import get_provider
from app.integrations.llm.mock import NO_EVIDENCE_MESSAGE
from app.integrations.llm.prompts import ASSISTANT_SYSTEM, ASSISTANT_VERSION
from app.integrations.llm.runner import run_llm

logger = get_logger(__name__)

#: Quantidade de blocos devolvidos no detalhe do documento.
DETAIL_CHUNKS = 5


def search_engine_name(session: AsyncSession) -> str:
    """Nome do mecanismo de busca em uso, para exibir na interface."""
    dialect = session.bind.dialect.name if session.bind is not None else "sqlite"
    if dialect == "postgresql":
        return "postgresql-fts"
    return "portable-like"


async def ingest_text(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    title: str,
    content: str,
    actor: User | None = None,
    tags: list[str] | None = None,
    filename: str | None = None,
    mime_type: str = "text/plain",
    size_bytes: int | None = None,
    source_label: str = "upload",
    context: RequestContext | None = None,
) -> KnowledgeDocument:
    """Cria o documento e seus blocos pesquisáveis."""
    chunks = chunk_text(content)
    document = KnowledgeDocument(
        organization_id=organization_id,
        title=title.strip()[:240],
        original_filename=filename,
        mime_type=mime_type,
        size_bytes=size_bytes if size_bytes is not None else len(content.encode("utf-8")),
        char_count=len(content),
        chunk_count=len(chunks),
        status=DocumentStatus.READY if chunks else DocumentStatus.FAILED,
        tags=tags or [],
        source_label=source_label,
        error_message=None if chunks else "Não foi possível extrair blocos de texto.",
        uploaded_by_id=actor.id if actor else None,
    )
    session.add(document)
    await session.flush()

    for chunk in chunks:
        session.add(
            DocumentChunk(
                organization_id=organization_id,
                document_id=document.id,
                chunk_index=chunk.index,
                content=chunk.content,
                content_normalized=chunk.normalized,
                char_count=chunk.char_count,
                token_estimate=chunk.token_estimate,
                page_hint=chunk.heading,
                meta={"heading": chunk.heading, "filename": filename},
            )
        )

    await audit_service.record_audit(
        session,
        organization_id=organization_id,
        action=audit_service.ACTION_KNOWLEDGE_UPLOAD,
        entity_type="knowledge_document",
        entity_id=str(document.id),
        actor=actor,
        summary=f"Documento “{document.title}” adicionado com {len(chunks)} bloco(s).",
        meta={"chunks": len(chunks), "chars": len(content), "filename": filename},
        context=context,
    )
    await session.commit()
    await session.refresh(document)
    logger.info("knowledge_ingested", document_id=str(document.id), chunks=len(chunks))
    return document


async def ingest_upload(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    filename: str | None,
    content_type: str | None,
    content: bytes,
    title: str | None,
    tags: list[str] | None,
    actor: User,
    context: RequestContext | None = None,
) -> KnowledgeDocument:
    """Valida o arquivo, extrai o texto e indexa."""
    safe_name, extension, effective_type = validate_upload(
        filename=filename,
        content_type=content_type,
        content=content,
        allowed=KNOWLEDGE_EXTENSIONS,
    )
    extracted = extract_text(content, extension=extension)
    return await ingest_text(
        session,
        organization_id=organization_id,
        title=title or safe_name,
        content=extracted.text,
        actor=actor,
        tags=tags,
        filename=safe_name,
        mime_type=effective_type,
        size_bytes=len(content),
        source_label="upload",
        context=context,
    )


async def list_documents(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    params: PageParams,
    search: str | None = None,
) -> tuple[list[KnowledgeDocument], int]:
    """Lista documentos da organização."""
    base = select(KnowledgeDocument).where(
        KnowledgeDocument.organization_id == organization_id,
        KnowledgeDocument.deleted_at.is_(None),
    )
    if search:
        base = base.where(KnowledgeDocument.title.ilike(f"%{search.strip()}%"))
    total = int(
        (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    )
    rows = (
        (
            await session.execute(
                base.order_by(KnowledgeDocument.created_at.desc())
                .offset(params.offset)
                .limit(params.page_size)
            )
        )
        .scalars()
        .unique()
        .all()
    )
    return list(rows), total


async def get_document(
    session: AsyncSession, *, organization_id: uuid.UUID, document_id: uuid.UUID
) -> KnowledgeDocument:
    """Busca um documento da organização ou falha com 404."""
    result = await session.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.organization_id == organization_id,
            KnowledgeDocument.deleted_at.is_(None),
        )
    )
    document: KnowledgeDocument | None = result.scalar_one_or_none()
    if document is None:
        raise NotFoundError("Documento não encontrado.")
    return document


async def list_chunks(
    session: AsyncSession, *, document_id: uuid.UUID, limit: int = DETAIL_CHUNKS
) -> list[DocumentChunk]:
    """Primeiros blocos de um documento."""
    rows = (
        (
            await session.execute(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.chunk_index)
                .limit(limit)
            )
        )
        .scalars()
        .unique()
        .all()
    )
    return list(rows)


async def delete_document(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    actor: User,
    context: RequestContext | None = None,
) -> None:
    """Exclusão lógica do documento (os blocos deixam de ser pesquisáveis)."""
    document = await get_document(session, organization_id=organization_id, document_id=document_id)
    document.deleted_at = utcnow()
    await audit_service.record_audit(
        session,
        organization_id=organization_id,
        action=audit_service.ACTION_KNOWLEDGE_DELETE,
        entity_type="knowledge_document",
        entity_id=str(document.id),
        actor=actor,
        summary=f"Documento “{document.title}” removido.",
        context=context,
    )
    await session.commit()


async def search(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    query: str,
    limit: int = 5,
) -> list[SearchHit]:
    """Busca trechos relevantes na base de conhecimento."""
    return await search_chunks(session, organization_id=organization_id, query=query, limit=limit)


async def answer_from_documents(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    question: str,
    actor: User,
    limit: int = 4,
    context: RequestContext | None = None,
) -> dict[str, Any]:
    """Responde usando **apenas** os documentos, com citações.

    Sem trecho relevante, devolve a mensagem padrão de ausência de evidência e
    não chama o provider de IA.
    """
    hits = await search(session, organization_id=organization_id, query=question, limit=limit)
    engine = search_engine_name(session)

    if not hits:
        await audit_service.record_audit(
            session,
            organization_id=organization_id,
            action=audit_service.ACTION_AI_ASSISTANT,
            entity_type="knowledge",
            actor=actor,
            summary="Pergunta à base de conhecimento sem evidência encontrada.",
            meta={"question": question[:300], "engine": engine},
            context=context,
        )
        await session.commit()
        return {
            "question": question,
            "answer": NO_EVIDENCE_MESSAGE,
            "has_evidence": False,
            "sources": [],
            "engine": engine,
            "trace": {"hits": 0},
        }

    request = LLMRequest(
        feature=LLMFeature.ASSISTANT,
        system=ASSISTANT_SYSTEM,
        prompt_version=ASSISTANT_VERSION,
        messages=[LLMMessage(role="user", content=question)],
        context={
            "headline": "Encontrei estes trechos na base de conhecimento.",
            "facts": [],
            "knowledge": [
                {
                    "document_title": hit.document_title,
                    "excerpt": hit.excerpt,
                    "locator": hit.page_hint or f"bloco {hit.chunk_index + 1}",
                    "score": hit.score,
                }
                for hit in hits
            ],
            "reasoning": [
                f"Busquei “{question}” na base de conhecimento usando {engine}.",
                f"Selecionei {len(hits)} trecho(s) com maior relevância.",
            ],
        },
    )
    execution = await run_llm(
        session,
        organization_id=organization_id,
        request=request,
        actor=actor,
        provider=get_provider(),
    )
    await audit_service.record_audit(
        session,
        organization_id=organization_id,
        action=audit_service.ACTION_AI_ASSISTANT,
        entity_type="knowledge",
        actor=actor,
        summary="Pergunta respondida com base nos documentos.",
        meta={"question": question[:300], "hits": len(hits), "engine": engine},
        context=context,
    )
    await session.commit()
    return {
        "question": question,
        "answer": execution.text,
        "has_evidence": True,
        "sources": [hit.as_source() for hit in hits],
        "engine": engine,
        "trace": execution.trace(),
    }
