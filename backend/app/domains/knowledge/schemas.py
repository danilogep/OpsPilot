"""Schemas da base de conhecimento."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import DocumentStatus


class DocumentRead(BaseModel):
    """Documento exposto pela API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    original_filename: str | None
    mime_type: str
    size_bytes: int
    char_count: int
    chunk_count: int
    status: DocumentStatus
    tags: list[str]
    source_label: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class DocumentChunkRead(BaseModel):
    """Bloco de um documento."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chunk_index: int
    content: str
    char_count: int
    token_estimate: int
    page_hint: str | None


class DocumentDetail(DocumentRead):
    """Documento com os primeiros blocos, para inspeção."""

    chunks: list[DocumentChunkRead] = Field(default_factory=list)


class TextDocumentCreate(BaseModel):
    """Criação de documento a partir de texto colado na interface."""

    title: str = Field(min_length=2, max_length=240)
    content: str = Field(min_length=20)
    tags: list[str] = Field(default_factory=list, max_length=10)


class SearchHitRead(BaseModel):
    """Trecho recuperado na busca."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    chunk_index: int
    excerpt: str
    score: float
    page_hint: str | None = None
    matched_terms: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    """Resultado da busca textual."""

    query: str
    engine: str
    total: int
    hits: list[SearchHitRead]
    notice: str | None = None


class GroundedAnswer(BaseModel):
    """Resposta fundamentada apenas em documentos."""

    question: str
    answer: str
    has_evidence: bool
    sources: list[dict[str, Any]] = Field(default_factory=list)
    engine: str
    trace: dict[str, Any] = Field(default_factory=dict)
