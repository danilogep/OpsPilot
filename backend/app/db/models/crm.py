"""Planos, clientes e renovações."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Date, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    Base,
    OrgScopedMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_type,
)
from app.db.models.enums import CustomerStatus, RenewalStatus

MONEY = Numeric(12, 2)


class Plan(UUIDPrimaryKeyMixin, OrgScopedMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Plano/serviço vendido pela organização."""

    __tablename__ = "plans"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="org_plan_name"),)

    name: Mapped[str] = mapped_column(String(120), index=True)
    code: Mapped[str | None] = mapped_column(String(40), default=None)
    description: Mapped[str | None] = mapped_column(String(300), default=None)
    monthly_value: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.00"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    customers: Mapped[list[Customer]] = relationship(back_populates="plan", lazy="raise")


class Customer(UUIDPrimaryKeyMixin, OrgScopedMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Cliente da organização, originado de importação ou cadastro manual."""

    __tablename__ = "customers"
    __table_args__ = (
        Index("ix_customers_org_email", "organization_id", "email"),
        Index("ix_customers_org_status", "organization_id", "status"),
        Index("ix_customers_org_renewal", "organization_id", "renewal_date"),
        UniqueConstraint("organization_id", "dedupe_key", name="org_dedupe_key"),
    )

    name: Mapped[str] = mapped_column(String(200), index=True)
    email: Mapped[str | None] = mapped_column(String(254), default=None)
    phone: Mapped[str | None] = mapped_column(String(32), default=None)
    document: Mapped[str | None] = mapped_column(String(32), default=None)
    status: Mapped[CustomerStatus] = mapped_column(
        enum_type(CustomerStatus, length=16), default=CustomerStatus.ACTIVE
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("plans.id", ondelete="SET NULL"), default=None, index=True
    )
    monthly_value: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.00"))
    start_date: Mapped[date | None] = mapped_column(Date, default=None)
    renewal_date: Mapped[date | None] = mapped_column(Date, default=None)
    source: Mapped[str | None] = mapped_column(String(60), default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    last_contact_at: Mapped[datetime | None] = mapped_column(default=None)
    dedupe_key: Mapped[str] = mapped_column(String(255), index=True)
    import_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("import_jobs.id", ondelete="SET NULL"), default=None
    )
    extra: Mapped[dict[str, Any]] = mapped_column(default=dict)

    plan: Mapped[Plan | None] = relationship(back_populates="customers", lazy="joined")
    renewals: Mapped[list[Renewal]] = relationship(
        back_populates="customer", cascade="all, delete-orphan", lazy="raise"
    )


class Renewal(UUIDPrimaryKeyMixin, OrgScopedMixin, TimestampMixin, Base):
    """Renovação prevista de um cliente."""

    __tablename__ = "renewals"
    __table_args__ = (
        Index("ix_renewals_org_due", "organization_id", "due_date"),
        Index("ix_renewals_org_status", "organization_id", "status"),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("plans.id", ondelete="SET NULL"), default=None
    )
    due_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.00"))
    status: Mapped[RenewalStatus] = mapped_column(
        enum_type(RenewalStatus, length=16), default=RenewalStatus.SCHEDULED
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)

    customer: Mapped[Customer] = relationship(back_populates="renewals", lazy="joined")
