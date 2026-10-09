"""Leads e histórico de eventos."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    Base,
    OrgScopedMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_type,
)
from app.db.models.enums import (
    CompanySize,
    LeadCategory,
    LeadEventType,
    LeadStatus,
    ScoringMethod,
)

MONEY = Numeric(12, 2)


class Lead(UUIDPrimaryKeyMixin, OrgScopedMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Oportunidade comercial em avaliação."""

    __tablename__ = "leads"
    __table_args__ = (
        Index("ix_leads_org_status", "organization_id", "status"),
        Index("ix_leads_org_score", "organization_id", "score"),
        Index("ix_leads_org_source", "organization_id", "source"),
    )

    name: Mapped[str] = mapped_column(String(200), index=True)
    company: Mapped[str | None] = mapped_column(String(200), default=None)
    email: Mapped[str | None] = mapped_column(String(254), default=None)
    phone: Mapped[str | None] = mapped_column(String(32), default=None)
    source: Mapped[str] = mapped_column(String(60), default="indefinido")
    segment: Mapped[str | None] = mapped_column(String(80), default=None)
    company_size: Mapped[CompanySize] = mapped_column(
        enum_type(CompanySize, length=16), default=CompanySize.UNKNOWN
    )
    interest: Mapped[str | None] = mapped_column(String(200), default=None)
    status: Mapped[LeadStatus] = mapped_column(
        enum_type(LeadStatus, length=16), default=LeadStatus.NEW
    )
    estimated_value: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.00"))
    probability: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    score_category: Mapped[LeadCategory] = mapped_column(
        enum_type(LeadCategory, length=8), default=LeadCategory.COLD
    )
    score_reasons: Mapped[list[dict[str, Any]]] = mapped_column(default=list)
    score_method: Mapped[ScoringMethod] = mapped_column(
        enum_type(ScoringMethod, length=8), default=ScoringMethod.RULES
    )
    score_version: Mapped[str] = mapped_column(String(64), default="rules-v1")
    scored_at: Mapped[datetime | None] = mapped_column(default=None)
    next_step: Mapped[str | None] = mapped_column(String(300), default=None)
    risks: Mapped[list[str]] = mapped_column(default=list)
    suggested_message: Mapped[str | None] = mapped_column(Text, default=None)
    last_interaction_at: Mapped[datetime | None] = mapped_column(default=None)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    notes: Mapped[str | None] = mapped_column(Text, default=None)

    events: Mapped[list[LeadEvent]] = relationship(
        back_populates="lead",
        cascade="all, delete-orphan",
        lazy="raise",
        order_by="LeadEvent.created_at.desc()",
    )


class LeadEvent(UUIDPrimaryKeyMixin, OrgScopedMixin, TimestampMixin, Base):
    """Evento imutável no histórico de um lead."""

    __tablename__ = "lead_events"
    __table_args__ = (Index("ix_lead_events_lead_created", "lead_id", "created_at"),)

    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[LeadEventType] = mapped_column(enum_type(LeadEventType, length=20))
    description: Mapped[str] = mapped_column(String(400))
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )

    lead: Mapped[Lead] = relationship(back_populates="events", lazy="raise")
