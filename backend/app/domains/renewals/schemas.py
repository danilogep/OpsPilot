"""Schemas de renovações e indicadores de renovação."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import CustomerStatus, RenewalStatus


class RenewalCustomer(BaseModel):
    """Cliente resumido dentro da renovação."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str | None = None
    phone: str | None = None
    status: CustomerStatus


class RenewalRead(BaseModel):
    """Renovação exposta pela API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer: RenewalCustomer
    plan_id: uuid.UUID | None
    plan_name: str | None = None
    due_date: date
    days_until_due: int | None = None
    amount: Decimal
    status: RenewalStatus
    confirmed_at: datetime | None
    notes: str | None
    created_at: datetime


class RenewalCreate(BaseModel):
    """Criação manual de renovação."""

    customer_id: uuid.UUID
    due_date: date
    amount: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2)
    status: RenewalStatus = RenewalStatus.SCHEDULED
    notes: str | None = Field(default=None, max_length=1000)


class RenewalUpdate(BaseModel):
    """Atualização de renovação."""

    due_date: date | None = None
    amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    status: RenewalStatus | None = None
    notes: str | None = Field(default=None, max_length=1000)


class RenewalIndicators(BaseModel):
    """Indicadores de renovação usados no dashboard."""

    due_next_7_days: int
    due_next_30_days: int
    overdue: int
    amount_at_risk: Decimal
    amount_next_30_days: Decimal
    customers_without_recent_contact: int
    contact_threshold_days: int
    confirmed_last_30_days: int
    lost_last_30_days: int
    reference_date: date


class CriticalRenewal(BaseModel):
    """Renovação crítica destacada no dashboard."""

    customer_id: uuid.UUID
    customer_name: str
    plan_name: str | None
    due_date: date
    days_until_due: int
    amount: Decimal
    status: RenewalStatus
    customer_status: CustomerStatus
    reason: str
