"""Schemas de clientes e planos."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.types import Email
from app.db.models.enums import CustomerStatus

Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]


class PlanSummary(BaseModel):
    """Plano em forma reduzida, para exibir junto do cliente."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    monthly_value: Decimal


class PlanRead(PlanSummary):
    """Plano completo."""

    code: str | None = None
    description: str | None = None
    is_active: bool
    created_at: datetime


class PlanWithMetrics(PlanRead):
    """Plano com indicadores agregados."""

    customers_count: int = 0
    active_customers: int = 0
    churned_customers: int = 0
    monthly_revenue: Decimal = Decimal("0.00")
    churn_rate: float = 0.0


class PlanCreate(BaseModel):
    """Criação de plano."""

    name: str = Field(min_length=2, max_length=120)
    code: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=300)
    monthly_value: Money = Decimal("0.00")
    is_active: bool = True


class PlanUpdate(BaseModel):
    """Atualização parcial de plano."""

    name: str | None = Field(default=None, min_length=2, max_length=120)
    code: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=300)
    monthly_value: Money | None = None
    is_active: bool | None = None


class CustomerBase(BaseModel):
    """Campos editáveis de um cliente."""

    name: str = Field(min_length=2, max_length=200)
    email: Email | None = None
    phone: str | None = Field(default=None, max_length=32)
    document: str | None = Field(default=None, max_length=32)
    status: CustomerStatus = CustomerStatus.ACTIVE
    plan_id: uuid.UUID | None = None
    monthly_value: Money = Decimal("0.00")
    start_date: date | None = None
    renewal_date: date | None = None
    source: str | None = Field(default=None, max_length=60)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("phone")
    @classmethod
    def _normalize_phone(cls, value: str | None) -> str | None:
        """Aplica a mesma normalização da importação."""
        if value is None or not value.strip():
            return None
        from app.domains.imports.normalizers import FieldError, normalize_phone

        try:
            return normalize_phone(value)
        except FieldError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("document")
    @classmethod
    def _normalize_document(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        from app.domains.imports.normalizers import FieldError, normalize_document

        try:
            return normalize_document(value)
        except FieldError as exc:
            raise ValueError(str(exc)) from exc


class CustomerCreate(CustomerBase):
    """Criação de cliente."""


class CustomerUpdate(BaseModel):
    """Atualização parcial de cliente."""

    name: str | None = Field(default=None, min_length=2, max_length=200)
    email: Email | None = None
    phone: str | None = Field(default=None, max_length=32)
    document: str | None = Field(default=None, max_length=32)
    status: CustomerStatus | None = None
    plan_id: uuid.UUID | None = None
    monthly_value: Money | None = None
    start_date: date | None = None
    renewal_date: date | None = None
    source: str | None = Field(default=None, max_length=60)
    notes: str | None = Field(default=None, max_length=2000)
    last_contact_at: datetime | None = None


class CustomerRead(BaseModel):
    """Cliente exposto pela API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str | None
    phone: str | None
    phone_formatted: str | None = None
    document: str | None
    status: CustomerStatus
    plan: PlanSummary | None = None
    monthly_value: Decimal
    start_date: date | None
    renewal_date: date | None
    days_to_renewal: int | None = None
    source: str | None
    notes: str | None
    last_contact_at: datetime | None
    days_since_contact: int | None = None
    import_job_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class CustomerHistoryEntry(BaseModel):
    """Entrada do histórico de alterações do cliente."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action: str
    summary: str
    actor_email: str
    meta: dict[str, Any]
    created_at: datetime
