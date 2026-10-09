"""Schemas das integrações por webhook."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.types import Email
from app.db.models.enums import (
    CompanySize,
    RenewalStatus,
    WebhookDirection,
    WebhookStatus,
)


class InboundLeadPayload(BaseModel):
    """Lead recebido de uma automação externa (n8n)."""

    name: str = Field(min_length=2, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    email: Email | None = None
    phone: str | None = Field(default=None, max_length=32)
    source: str = Field(default="n8n", max_length=60)
    segment: str | None = Field(default=None, max_length=80)
    company_size: CompanySize = CompanySize.UNKNOWN
    interest: str | None = Field(default=None, max_length=200)
    estimated_value: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2)
    notes: str | None = Field(default=None, max_length=1000)
    external_id: str | None = Field(default=None, max_length=120)


class InboundRenewalPayload(BaseModel):
    """Evento de renovação recebido de uma automação externa."""

    customer_email: Email | None = None
    customer_name: str | None = Field(default=None, max_length=200)
    due_date: date
    amount: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2)
    status: RenewalStatus = RenewalStatus.SCHEDULED
    notes: str | None = Field(default=None, max_length=1000)
    external_id: str | None = Field(default=None, max_length=120)


class WebhookAck(BaseModel):
    """Resposta padronizada de um webhook de entrada."""

    received: bool
    event_id: uuid.UUID
    status: WebhookStatus
    idempotency_key: str
    message: str
    entity_id: uuid.UUID | None = None
    duplicate: bool = False


class WebhookEventRead(BaseModel):
    """Evento de webhook registrado."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    direction: WebhookDirection
    event_type: str
    idempotency_key: str
    signature_valid: bool
    status: WebhookStatus
    attempts: int
    target_url: str | None
    payload: dict[str, Any]
    response: dict[str, Any]
    error: str | None
    processed_at: datetime | None
    created_at: datetime


class IntegrationStatus(BaseModel):
    """Situação atual das integrações."""

    inbound_signature_required: bool
    signature_header: str
    idempotency_header: str
    event_header: str
    organization_header: str
    outbound_url_configured: bool
    outbound_url: str | None
    inbound_endpoints: list[dict[str, str]]
    outbound_events: list[dict[str, str]]
    totals: dict[str, int]


class OutboundTestRequest(BaseModel):
    """Pedido de envio de um evento de teste."""

    event_type: str = Field(default="renewal.alert", max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)
    target_url: str | None = Field(default=None, max_length=500)
