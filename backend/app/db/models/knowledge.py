"""Base de conhecimento: documentos e blocos indexados."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    Base,
    OrgScopedMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_type,
)
from app.db.models.enums import DocumentStatus


class KnowledgeDocument(UUIDPrimaryKeyMixin, OrgScopedMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Documento enviado para a base de conhecimento."""

    __tablename__ = "knowledge_documents"

    title: Mapped[str] = mapped_column(String(240), index=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), default=None)
    mime_type: Mapped[str] = mapped_column(String(120), default="text/plain")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[DocumentStatus] = mapped_column(
        enum_type(DocumentStatus, length=16), default=DocumentStatus.PROCESSING
    )
    tags: Mapped[list[str]] = mapped_column(default=list)
    source_label: Mapped[str] = mapped_column(String(160), default="upload")
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )

    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="raise",
        order_by="DocumentChunk.chunk_index",
    )


class DocumentChunk(UUIDPrimaryKeyMixin, OrgScopedMixin, TimestampMixin, Base):
    """Bloco de texto pesquisável.

    ``content_normalized`` guarda o texto sem acentos e em minúsculas; é usado
    pelo fallback de busca portátil (SQLite). No PostgreSQL a busca usa
    ``to_tsvector('portuguese', content)`` com índice GIN de expressão criado na
    migration.
    """

    __tablename__ = "document_chunks"
    __table_args__ = (Index("ix_document_chunks_doc_index", "document_id", "chunk_index"),)

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    content_normalized: Mapped[str] = mapped_column(Text, default="")
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    token_estimate: Mapped[int] = mapped_column(Integer, default=0)
    page_hint: Mapped[str | None] = mapped_column(String(60), default=None)
    meta: Mapped[dict[str, Any]] = mapped_column(default=dict)

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks", lazy="joined")
