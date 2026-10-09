"""Rotas da base de conhecimento."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Body, Depends, File, Form, Query, UploadFile, status

from app.api.deps import ContextDep, RequireAnalyst, RequireViewer, SessionDep
from app.core.config import settings
from app.core.errors import PayloadTooLargeError
from app.core.pagination import Page, PageParams, page_params
from app.domains.knowledge import service
from app.domains.knowledge.schemas import (
    DocumentChunkRead,
    DocumentDetail,
    DocumentRead,
    GroundedAnswer,
    SearchHitRead,
    SearchResponse,
    TextDocumentCreate,
)

router = APIRouter(prefix="/knowledge", tags=["Base de conhecimento"])


@router.get("/documents", response_model=Page[DocumentRead], summary="Listar documentos")
async def list_documents(
    session: SessionDep,
    user: RequireViewer,
    params: Annotated[PageParams, Depends(page_params)],
    search: Annotated[str | None, Query(description="Busca pelo título")] = None,
) -> Page[DocumentRead]:
    """Lista os documentos indexados da organização."""
    documents, total = await service.list_documents(
        session, organization_id=user.organization_id, params=params, search=search
    )
    return Page.build(
        [DocumentRead.model_validate(document) for document in documents], total, params
    )


@router.post(
    "/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Enviar documento (TXT, MD, PDF, DOCX, CSV, XLSX)",
)
async def upload_document(
    session: SessionDep,
    user: RequireAnalyst,
    context: ContextDep,
    file: Annotated[UploadFile, File(description="Documento a indexar")],
    title: Annotated[str | None, Form(description="Título opcional")] = None,
    tags: Annotated[str | None, Form(description="Etiquetas separadas por vírgula")] = None,
) -> DocumentRead:
    """Extrai o texto, divide em blocos e indexa o documento."""
    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise PayloadTooLargeError(f"Arquivo acima do limite de {settings.max_upload_mb} MB.")
    tag_list = [item.strip() for item in (tags or "").split(",") if item.strip()]
    document = await service.ingest_upload(
        session,
        organization_id=user.organization_id,
        filename=file.filename,
        content_type=file.content_type,
        content=content,
        title=title,
        tags=tag_list,
        actor=user,
        context=context,
    )
    return DocumentRead.model_validate(document)


@router.post(
    "/documents/text",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Criar documento a partir de texto",
)
async def create_text_document(
    payload: TextDocumentCreate,
    session: SessionDep,
    user: RequireAnalyst,
    context: ContextDep,
) -> DocumentRead:
    """Indexa um texto colado diretamente na interface."""
    document = await service.ingest_text(
        session,
        organization_id=user.organization_id,
        title=payload.title,
        content=payload.content,
        actor=user,
        tags=payload.tags,
        mime_type="text/markdown",
        source_label="texto colado",
        context=context,
    )
    return DocumentRead.model_validate(document)


@router.get("/search", response_model=SearchResponse, summary="Buscar trechos")
async def search_documents(
    session: SessionDep,
    user: RequireViewer,
    q: Annotated[str, Query(min_length=2, description="Termos de busca")],
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
) -> SearchResponse:
    """Busca textual nos blocos indexados."""
    hits = await service.search(session, organization_id=user.organization_id, query=q, limit=limit)
    engine = service.search_engine_name(session)
    return SearchResponse(
        query=q,
        engine=engine,
        total=len(hits),
        hits=[SearchHitRead(**asdict(hit)) for hit in hits],
        notice=None if hits else "Nenhum trecho relevante encontrado para esta busca.",
    )


@router.post("/ask", response_model=GroundedAnswer, summary="Perguntar aos documentos")
async def ask_documents(
    session: SessionDep,
    user: RequireViewer,
    context: ContextDep,
    question: Annotated[str, Body(embed=True, min_length=5, max_length=500)],
) -> GroundedAnswer:
    """Responde usando apenas os documentos, com citação das fontes."""
    payload = await service.answer_from_documents(
        session,
        organization_id=user.organization_id,
        question=question,
        actor=user,
        context=context,
    )
    return GroundedAnswer.model_validate(payload)


@router.get(
    "/documents/{document_id}", response_model=DocumentDetail, summary="Detalhe do documento"
)
async def get_document(
    document_id: uuid.UUID, session: SessionDep, user: RequireViewer
) -> DocumentDetail:
    """Retorna o documento com os primeiros blocos indexados."""
    document = await service.get_document(
        session, organization_id=user.organization_id, document_id=document_id
    )
    chunks = await service.list_chunks(session, document_id=document.id)
    detail = DocumentDetail.model_validate(document)
    detail.chunks = [DocumentChunkRead.model_validate(chunk) for chunk in chunks]
    return detail


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remover documento",
)
async def delete_document(
    document_id: uuid.UUID, session: SessionDep, user: RequireAnalyst, context: ContextDep
) -> None:
    """Exclusão lógica do documento."""
    await service.delete_document(
        session,
        organization_id=user.organization_id,
        document_id=document_id,
        actor=user,
        context=context,
    )
