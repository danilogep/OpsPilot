"""Busca na base de conhecimento, sem dependência de serviço externo.

Dois caminhos, escolhidos pelo dialeto do banco:

* **PostgreSQL** (obrigatório em produção): ``to_tsvector('portuguese', content)``
  com ``plainto_tsquery`` e ordenação por ``ts_rank``. O índice GIN de expressão
  é criado na migration inicial.
* **Fallback portátil** (SQLite dos testes e execução local): filtro ``LIKE``
  sobre ``content_normalized`` e ranqueamento em Python por cobertura de termos.

Ambos devolvem a mesma estrutura, então o resto da aplicação não muda. Ver
``docs/adr/003-rag-fallback.md``.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocumentChunk, KnowledgeDocument
from app.domains.knowledge.chunking import normalize_for_search, tokenize

#: Termos muito curtos ou genéricos não ajudam no ranqueamento.
STOPWORDS = frozenset(
    {
        "a",
        "ao",
        "aos",
        "as",
        "da",
        "das",
        "de",
        "do",
        "dos",
        "e",
        "em",
        "na",
        "nas",
        "no",
        "nos",
        "o",
        "os",
        "ou",
        "para",
        "por",
        "que",
        "qual",
        "quais",
        "um",
        "uma",
        "com",
        "sem",
        "sobre",
        "como",
        "quanto",
        "quantos",
        "quantas",
        "qualquer",
        "ser",
        "sao",
        "eh",
        "esta",
        "estao",
        "me",
        "meu",
        "minha",
        "nosso",
        "nossa",
        "se",
        "ja",
        "mais",
        "menos",
        "muito",
    }
)
MIN_TERM_LENGTH = 3
#: Pontuação mínima (0–1) para considerar o trecho como evidência.
MIN_RELEVANCE = 0.08
#: Fração mínima dos termos da pergunta que o trecho precisa cobrir.
#: Evita que uma única palavra genérica transforme qualquer documento em "fonte".
MIN_COVERAGE = 0.34
#: Tamanho do trecho devolvido como citação.
EXCERPT_LENGTH = 320


@dataclass(slots=True)
class SearchHit:
    """Trecho recuperado com a fonte e a pontuação."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    chunk_index: int
    excerpt: str
    score: float
    page_hint: str | None = None
    matched_terms: list[str] = field(default_factory=list)

    def as_source(self) -> dict[str, Any]:
        """Representação usada no campo ``sources`` das respostas de IA."""
        return {
            "type": "document",
            "document_id": str(self.document_id),
            "title": self.document_title,
            "locator": self.page_hint or f"bloco {self.chunk_index + 1}",
            "score": round(self.score, 4),
            "excerpt": self.excerpt,
        }


def extract_terms(query: str) -> list[str]:
    """Tokens relevantes da pergunta, sem acento e sem stopwords."""
    return [
        token
        for token in tokenize(query)
        if len(token) >= MIN_TERM_LENGTH and token not in STOPWORDS
    ]


def build_excerpt(content: str, terms: list[str]) -> str:
    """Recorta a janela do texto que cobre o maior número de termos buscados.

    Procurar apenas a primeira ocorrência do primeiro termo costuma devolver um
    trecho que não contém a resposta; aqui a janela escolhida é a que cobre mais
    termos distintos.
    """
    normalized = normalize_for_search(content)
    positions: list[tuple[int, str]] = []
    for term in terms:
        start = 0
        while True:
            found = normalized.find(term, start)
            if found == -1:
                break
            positions.append((found, term))
            start = found + len(term)
    if not positions:
        return content[:EXCERPT_LENGTH].strip()

    positions.sort()
    best_position, best_coverage = positions[0][0], 0
    for index, (position, _term) in enumerate(positions):
        covered = {
            other_term
            for other_position, other_term in positions[index:]
            if other_position - position <= EXCERPT_LENGTH
        }
        if len(covered) > best_coverage:
            best_position, best_coverage = position, len(covered)

    position = best_position
    start = max(0, position - EXCERPT_LENGTH // 4)
    end = min(len(content), start + EXCERPT_LENGTH)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(content) else ""
    return f"{prefix}{content[start:end].strip()}{suffix}"


def _score_fallback(normalized_content: str, terms: list[str]) -> tuple[float, list[str]]:
    """Pontua por cobertura de termos e frequência relativa."""
    matched: list[str] = []
    occurrences = 0
    for term in terms:
        count = len(re.findall(re.escape(term), normalized_content))
        if count:
            matched.append(term)
            occurrences += count
    if not matched:
        return 0.0, []
    coverage = len(matched) / len(terms)
    if coverage < MIN_COVERAGE:
        return 0.0, []
    density = min(1.0, occurrences / 12)
    return round(0.7 * coverage + 0.3 * density, 4), matched


async def search_chunks(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    query: str,
    limit: int = 5,
    document_ids: list[uuid.UUID] | None = None,
) -> list[SearchHit]:
    """Recupera os trechos mais relevantes para a pergunta."""
    terms = extract_terms(query)
    if not terms:
        return []

    dialect = session.bind.dialect.name if session.bind is not None else "sqlite"
    if dialect == "postgresql":
        return await _search_postgres(
            session,
            organization_id=organization_id,
            query=query,
            terms=terms,
            limit=limit,
            document_ids=document_ids,
        )
    return await _search_fallback(
        session,
        organization_id=organization_id,
        terms=terms,
        limit=limit,
        document_ids=document_ids,
    )


async def _search_postgres(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    query: str,
    terms: list[str],
    limit: int,
    document_ids: list[uuid.UUID] | None,
) -> list[SearchHit]:
    """Busca com Full Text Search nativo do PostgreSQL."""
    vector = func.to_tsvector("portuguese", DocumentChunk.content)
    ts_query = func.plainto_tsquery("portuguese", query)
    rank = func.ts_rank(vector, ts_query)

    stmt = (
        select(DocumentChunk, KnowledgeDocument.title, rank.label("rank"))
        .join(KnowledgeDocument, DocumentChunk.document_id == KnowledgeDocument.id)
        .where(
            DocumentChunk.organization_id == organization_id,
            KnowledgeDocument.deleted_at.is_(None),
            vector.op("@@")(ts_query),
        )
        .order_by(rank.desc())
        .limit(limit)
    )
    if document_ids:
        stmt = stmt.where(DocumentChunk.document_id.in_(document_ids))

    rows = (await session.execute(stmt)).all()
    hits: list[SearchHit] = []
    max_rank = max((float(row[2] or 0) for row in rows), default=0.0)
    for chunk, title, raw_rank in rows:
        normalized = float(raw_rank or 0) / max_rank if max_rank else 0.0
        score = round(max(MIN_RELEVANCE, normalized), 4)
        hits.append(
            SearchHit(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_title=title,
                chunk_index=chunk.chunk_index,
                excerpt=build_excerpt(chunk.content, terms),
                score=score,
                page_hint=chunk.page_hint,
                matched_terms=terms,
            )
        )
    return hits


async def _search_fallback(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    terms: list[str],
    limit: int,
    document_ids: list[uuid.UUID] | None,
) -> list[SearchHit]:
    """Busca portátil por ``LIKE`` + ranqueamento em Python."""
    conditions = [DocumentChunk.content_normalized.like(f"%{term}%") for term in terms]
    stmt = (
        select(DocumentChunk, KnowledgeDocument.title)
        .join(KnowledgeDocument, DocumentChunk.document_id == KnowledgeDocument.id)
        .where(
            DocumentChunk.organization_id == organization_id,
            KnowledgeDocument.deleted_at.is_(None),
            or_(*conditions),
        )
        .limit(200)
    )
    if document_ids:
        stmt = stmt.where(DocumentChunk.document_id.in_(document_ids))

    rows = (await session.execute(stmt)).all()
    scored: list[SearchHit] = []
    for chunk, title in rows:
        score, matched = _score_fallback(chunk.content_normalized, terms)
        if score < MIN_RELEVANCE:
            continue
        scored.append(
            SearchHit(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_title=title,
                chunk_index=chunk.chunk_index,
                excerpt=build_excerpt(chunk.content, matched),
                score=score,
                page_hint=chunk.page_hint,
                matched_terms=matched,
            )
        )
    scored.sort(key=lambda hit: (-hit.score, hit.document_title, hit.chunk_index))
    return scored[:limit]
