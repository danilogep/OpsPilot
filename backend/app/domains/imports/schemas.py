"""Schemas do módulo de importação."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import ImportStatus, RowStatus
from app.domains.imports.mapping import FIELD_LABELS, CanonicalField


class CanonicalFieldInfo(BaseModel):
    """Campo do modelo canônico, para montar o seletor da interface."""

    field: CanonicalField
    label: str
    required: bool
    synonyms: list[str]


class ColumnMappingRead(BaseModel):
    """Mapeamento persistido de uma coluna."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_column: str
    target_field: str | None
    confidence: float
    is_manual: bool
    sample_values: list[str]


class ColumnMappingInput(BaseModel):
    """Mapeamento informado pelo usuário na revisão."""

    source_column: str = Field(min_length=1, max_length=200)
    target_field: CanonicalField | None = None


class MappingUpdate(BaseModel):
    """Revisão completa do mapeamento de uma importação."""

    mappings: list[ColumnMappingInput]
    sheet_name: str | None = None


class ImportJobRead(BaseModel):
    """Importação exposta pela API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    content_type: str
    size_bytes: int
    sheet_name: str | None
    status: ImportStatus
    detected_columns: list[str]
    total_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_rows: int
    imported_rows: int
    updated_rows: int
    stats: dict[str, Any]
    error_message: str | None
    validated_at: datetime | None
    committed_at: datetime | None
    created_at: datetime
    created_by_id: uuid.UUID | None


class ImportJobDetail(ImportJobRead):
    """Importação com o mapeamento atual."""

    mappings: list[ColumnMappingRead] = Field(default_factory=list)
    available_sheets: list[str] = Field(default_factory=list)


class RowIssueRead(BaseModel):
    """Erro ou aviso de uma linha."""

    field: str
    label: str
    message: str
    value: str | None = None


class PreviewRow(BaseModel):
    """Linha da prévia, com original, normalizado e problemas."""

    row_number: int
    raw: dict[str, Any]
    normalized: dict[str, Any]
    status: RowStatus
    errors: list[RowIssueRead] = Field(default_factory=list)
    warnings: list[RowIssueRead] = Field(default_factory=list)


class ImportPreview(BaseModel):
    """Prévia da importação antes da validação completa."""

    import_id: uuid.UUID
    status: ImportStatus
    headers: list[str]
    available_sheets: list[str]
    active_sheet: str | None
    delimiter: str | None
    encoding: str | None
    total_rows_in_file: int
    mapping: dict[str, str | None]
    suggestions: list[MappingSuggestionRead]
    unmapped_columns: list[str]
    missing_required_fields: list[str]
    rows: list[PreviewRow]
    canonical_fields: list[CanonicalFieldInfo]


class MappingSuggestionRead(BaseModel):
    """Sugestão automática de mapeamento com a justificativa."""

    source_column: str
    target_field: CanonicalField | None
    confidence: float
    reason: str
    needs_review: bool


class ValidationSummary(BaseModel):
    """Resumo da validação completa."""

    import_id: uuid.UUID
    status: ImportStatus
    total_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_rows: int
    warning_rows: int
    unique_keys: int
    errors_by_field: dict[str, int]
    top_errors: list[dict[str, Any]]
    fill_rate: dict[str, float]
    dedupe_criteria: dict[str, int]
    monthly_value_sum: str
    mapped_fields: list[str]
    unmapped_columns: list[str]


class RowErrorRead(BaseModel):
    """Linha rejeitada ou duplicada, para o relatório de erros."""

    model_config = ConfigDict(from_attributes=True)

    row_number: int
    status: RowStatus
    raw_data: dict[str, Any]
    normalized_data: dict[str, Any]
    errors: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    duplicate_of_row: int | None


class CommitResult(BaseModel):
    """Resultado do commit da importação."""

    import_id: uuid.UUID
    status: ImportStatus
    created_customers: int
    updated_customers: int
    created_plans: int
    created_renewals: int
    skipped_invalid: int
    skipped_duplicates: int
    committed_at: datetime | None
    message: str


class ImportReport(BaseModel):
    """Relatório final consolidado da importação."""

    job: ImportJobDetail
    validation: ValidationSummary | None
    sample_errors: list[RowErrorRead]
    recommendations: list[str]


def canonical_field_catalog() -> list[CanonicalFieldInfo]:
    """Catálogo de campos canônicos com rótulos e sinônimos."""
    from app.domains.imports.mapping import FIELD_SYNONYMS, REQUIRED_FIELDS

    return [
        CanonicalFieldInfo(
            field=field,
            label=FIELD_LABELS[field],
            required=field in REQUIRED_FIELDS,
            synonyms=list(FIELD_SYNONYMS[field][:8]),
        )
        for field in CanonicalField
    ]


ImportPreview.model_rebuild()
