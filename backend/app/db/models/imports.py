"""Modelos do pipeline de importação de planilhas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    Base,
    OrgScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_type,
)
from app.db.models.enums import ImportStatus, RowStatus


class ImportJob(UUIDPrimaryKeyMixin, OrgScopedMixin, TimestampMixin, Base):
    """Um upload de arquivo e todo o seu ciclo de vida."""

    __tablename__ = "import_jobs"

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sheet_name: Mapped[str | None] = mapped_column(String(120), default=None)
    status: Mapped[ImportStatus] = mapped_column(
        enum_type(ImportStatus, length=16), default=ImportStatus.UPLOADED, index=True
    )
    detected_columns: Mapped[list[str]] = mapped_column(default=list)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, default=0)
    invalid_rows: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_rows: Mapped[int] = mapped_column(Integer, default=0)
    imported_rows: Mapped[int] = mapped_column(Integer, default=0)
    updated_rows: Mapped[int] = mapped_column(Integer, default=0)
    stats: Mapped[dict[str, Any]] = mapped_column(default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    validated_at: Mapped[datetime | None] = mapped_column(default=None)
    committed_at: Mapped[datetime | None] = mapped_column(default=None)

    mappings: Mapped[list[ImportColumnMapping]] = relationship(
        back_populates="import_job",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ImportColumnMapping.source_column",
    )
    rows: Mapped[list[RawImportRow]] = relationship(
        back_populates="import_job", cascade="all, delete-orphan", lazy="raise"
    )


class ImportColumnMapping(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Associação entre uma coluna do arquivo e um campo canônico."""

    __tablename__ = "import_column_mappings"

    import_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("import_jobs.id", ondelete="CASCADE"), index=True
    )
    source_column: Mapped[str] = mapped_column(String(200))
    target_field: Mapped[str | None] = mapped_column(String(60), default=None)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    sample_values: Mapped[list[str]] = mapped_column(default=list)

    import_job: Mapped[ImportJob] = relationship(back_populates="mappings", lazy="raise")


class RawImportRow(UUIDPrimaryKeyMixin, OrgScopedMixin, TimestampMixin, Base):
    """Linha original preservada, com resultado da normalização e erros."""

    __tablename__ = "raw_import_rows"
    __table_args__ = (
        Index("ix_raw_import_rows_job_status", "import_job_id", "status"),
        Index("ix_raw_import_rows_job_row", "import_job_id", "row_number"),
    )

    import_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("import_jobs.id", ondelete="CASCADE"), index=True
    )
    row_number: Mapped[int] = mapped_column(Integer)
    raw_data: Mapped[dict[str, Any]] = mapped_column(default=dict)
    normalized_data: Mapped[dict[str, Any]] = mapped_column(default=dict)
    status: Mapped[RowStatus] = mapped_column(
        enum_type(RowStatus, length=16), default=RowStatus.PENDING
    )
    errors: Mapped[list[dict[str, Any]]] = mapped_column(default=list)
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(default=list)
    dedupe_key: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    duplicate_of_row: Mapped[int | None] = mapped_column(Integer, default=None)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"), default=None
    )

    import_job: Mapped[ImportJob] = relationship(back_populates="rows", lazy="raise")
