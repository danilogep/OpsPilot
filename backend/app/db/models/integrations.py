"""Eventos de webhook (entrada e saída)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    Base,
    OrgScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_type,
)
from app.db.models.enums import WebhookDirection, WebhookStatus


class WebhookEvent(UUIDPrimaryKeyMixin, OrgScopedMixin, TimestampMixin, Base):
    """Evento trocado com automações externas (n8n).

    A chave de idempotência é única por organização e direção, garantindo que o
    mesmo evento reenviado não seja processado duas vezes.
    """

    __tablename__ = "webhook_events"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "direction", "idempotency_key", name="org_direction_idem"
        ),
        Index("ix_webhook_events_org_created", "organization_id", "created_at"),
    )

    direction: Mapped[WebhookDirection] = mapped_column(enum_type(WebhookDirection, length=10))
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(120))
    signature_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[WebhookStatus] = mapped_column(
        enum_type(WebhookStatus, length=16), default=WebhookStatus.RECEIVED
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    target_url: Mapped[str | None] = mapped_column(String(500), default=None)
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    response: Mapped[dict[str, Any]] = mapped_column(default=dict)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    processed_at: Mapped[datetime | None] = mapped_column(default=None)
