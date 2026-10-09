"""Schemas de leads, score e eventos."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.types import Email
from app.db.models.enums import (
    CompanySize,
    LeadCategory,
    LeadEventType,
    LeadStatus,
    ScoringMethod,
)

Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]


class ScoreReasonRead(BaseModel):
    """Justificativa de um critério do score."""

    model_config = ConfigDict(from_attributes=True)

    criterion: str
    label: str
    points: int
    max_points: int
    detail: str


class LeadBase(BaseModel):
    """Campos editáveis de um lead."""

    name: str = Field(min_length=2, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    email: Email | None = None
    phone: str | None = Field(default=None, max_length=32)
    source: str = Field(default="indefinido", max_length=60)
    segment: str | None = Field(default=None, max_length=80)
    company_size: CompanySize = CompanySize.UNKNOWN
    interest: str | None = Field(default=None, max_length=200)
    status: LeadStatus = LeadStatus.NEW
    estimated_value: Money = Decimal("0.00")
    probability: int = Field(default=0, ge=0, le=100)
    notes: str | None = Field(default=None, max_length=2000)
    last_interaction_at: datetime | None = None

    @field_validator("phone")
    @classmethod
    def _normalize_phone(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        from app.domains.imports.normalizers import FieldError, normalize_phone

        try:
            return normalize_phone(value)
        except FieldError as exc:
            raise ValueError(str(exc)) from exc


class LeadCreate(LeadBase):
    """Criação de lead."""


class LeadUpdate(BaseModel):
    """Atualização parcial de lead."""

    name: str | None = Field(default=None, min_length=2, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    email: Email | None = None
    phone: str | None = Field(default=None, max_length=32)
    source: str | None = Field(default=None, max_length=60)
    segment: str | None = Field(default=None, max_length=80)
    company_size: CompanySize | None = None
    interest: str | None = Field(default=None, max_length=200)
    status: LeadStatus | None = None
    estimated_value: Money | None = None
    probability: int | None = Field(default=None, ge=0, le=100)
    notes: str | None = Field(default=None, max_length=2000)
    next_step: str | None = Field(default=None, max_length=300)
    last_interaction_at: datetime | None = None


class LeadRead(BaseModel):
    """Lead exposto pela API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    company: str | None
    email: str | None
    phone: str | None
    phone_formatted: str | None = None
    source: str
    segment: str | None
    company_size: CompanySize
    interest: str | None
    status: LeadStatus
    estimated_value: Decimal
    probability: int
    score: int
    score_category: LeadCategory
    score_reasons: list[dict[str, Any]]
    score_method: ScoringMethod
    score_version: str
    scored_at: datetime | None
    next_step: str | None
    risks: list[str]
    suggested_message: str | None
    last_interaction_at: datetime | None
    days_since_interaction: int | None = None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class LeadEventRead(BaseModel):
    """Evento do histórico do lead."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: LeadEventType
    description: str
    payload: dict[str, Any]
    created_at: datetime


class LeadNoteCreate(BaseModel):
    """Nota manual adicionada ao histórico do lead."""

    note: str = Field(min_length=2, max_length=1000)
    mark_as_contacted: bool = False


class LeadScoreResponse(BaseModel):
    """Resultado do cálculo de score."""

    lead_id: uuid.UUID
    score: int
    category: LeadCategory
    method: ScoringMethod
    version: str
    reasons: list[ScoreReasonRead]
    risks: list[str]
    next_step: str
    suggested_message: str | None = None
    sources: list[str] = Field(default_factory=list)
    notice: str | None = None


class LeadFunnelStage(BaseModel):
    """Quantidade e valor por estágio do funil."""

    status: LeadStatus
    label: str
    total: int
    estimated_value: Decimal


class LeadSourceSummary(BaseModel):
    """Ranking de origens de leads."""

    source: str
    total: int
    high_priority: int
    estimated_value: Decimal
    average_score: float


class LeadIndicators(BaseModel):
    """Indicadores de leads para o dashboard."""

    total: int
    open_leads: int
    high_priority: int
    won_last_30_days: int
    lost_last_30_days: int
    estimated_pipeline: Decimal
    average_score: float
    funnel: list[LeadFunnelStage]
    by_source: list[LeadSourceSummary]
