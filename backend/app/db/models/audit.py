"""Trilha de auditoria."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AuditEvent(UUIDPrimaryKeyMixin, OrgScopedMixin, TimestampMixin, Base):
    """Registro imutável de uma ação relevante.

    Usado também como histórico de alterações de clientes e leads: o campo
    ``meta`` carrega o diff (``{"campo": {"before": ..., "after": ...}}``).
    """

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_org_created", "organization_id", "created_at"),
        Index("ix_audit_events_entity", "entity_type", "entity_id"),
    )

    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str] = mapped_column(String(60), default="")
    entity_id: Mapped[str | None] = mapped_column(String(64), default=None)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    actor_email: Mapped[str] = mapped_column(String(254), default="system")
    actor_role: Mapped[str] = mapped_column(String(16), default="SYSTEM")
    ip_address: Mapped[str | None] = mapped_column(String(64), default=None)
    user_agent: Mapped[str | None] = mapped_column(String(300), default=None)
    correlation_id: Mapped[str] = mapped_column(String(64), default="")
    summary: Mapped[str] = mapped_column(String(300), default="")
    meta: Mapped[dict[str, Any]] = mapped_column(default=dict)
