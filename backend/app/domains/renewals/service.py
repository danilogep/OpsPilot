"""Serviço de renovações e indicadores de risco.

Os indicadores são calculados **sempre a partir do banco**: nenhum número é
estimado ou fixado no código. ``reference_date`` deixa explícita a data usada.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.api.deps import RequestContext
from app.core.errors import NotFoundError, ValidationError
from app.core.pagination import PageParams
from app.db.base import utcnow
from app.db.models import Customer, CustomerStatus, Plan, Renewal, RenewalStatus, User
from app.domains.audit import service as audit_service
from app.domains.renewals.schemas import (
    CriticalRenewal,
    RenewalCreate,
    RenewalIndicators,
    RenewalRead,
    RenewalUpdate,
)

#: Dias sem contato a partir dos quais o cliente entra no indicador de risco.
CONTACT_THRESHOLD_DAYS = 45
#: Status considerados "em aberto" para risco de receita.
OPEN_STATUSES = (RenewalStatus.SCHEDULED, RenewalStatus.AT_RISK)

SORTABLE_COLUMNS: dict[str, Any] = {
    "due_date": Renewal.due_date,
    "amount": Renewal.amount,
    "status": Renewal.status,
    "created_at": Renewal.created_at,
}


@dataclass(slots=True)
class RenewalFilters:
    """Filtros da listagem de renovações."""

    statuses: list[RenewalStatus] | None = None
    due_from: date | None = None
    due_to: date | None = None
    within_days: int | None = None
    overdue_only: bool = False
    customer_id: uuid.UUID | None = None
    search: str | None = None


def _base_query(organization_id: uuid.UUID) -> Select[Any]:
    return (
        select(Renewal)
        .join(Customer, Renewal.customer_id == Customer.id)
        .where(Renewal.organization_id == organization_id, Customer.deleted_at.is_(None))
    )


def apply_filters(stmt: Select[Any], filters: RenewalFilters, *, today: date) -> Select[Any]:
    """Aplica os filtros à query de renovações."""
    if filters.statuses:
        stmt = stmt.where(Renewal.status.in_(filters.statuses))
    if filters.due_from:
        stmt = stmt.where(Renewal.due_date >= filters.due_from)
    if filters.due_to:
        stmt = stmt.where(Renewal.due_date <= filters.due_to)
    if filters.within_days is not None:
        stmt = stmt.where(
            Renewal.due_date >= today,
            Renewal.due_date <= today + timedelta(days=filters.within_days),
        )
    if filters.overdue_only:
        stmt = stmt.where(Renewal.due_date < today, Renewal.status.in_(OPEN_STATUSES))
    if filters.customer_id:
        stmt = stmt.where(Renewal.customer_id == filters.customer_id)
    if filters.search:
        stmt = stmt.where(Customer.name.ilike(f"%{filters.search.strip()}%"))
    return stmt


async def list_renewals(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    params: PageParams,
    filters: RenewalFilters,
    sort: str = "due_date",
    direction: str = "asc",
) -> tuple[list[Renewal], int]:
    """Lista renovações com filtros e paginação."""
    today = utcnow().date()
    base = apply_filters(_base_query(organization_id), filters, today=today)
    total = int(
        (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    )
    column = SORTABLE_COLUMNS.get(sort)
    if column is None:
        raise ValidationError(
            "Campo de ordenação inválido.", details={"allowed": sorted(SORTABLE_COLUMNS)}
        )
    order = column.desc() if direction.lower() == "desc" else column.asc()
    rows = (
        (
            await session.execute(
                base.order_by(order, Renewal.id)
                .options(joinedload(Renewal.customer))
                .offset(params.offset)
                .limit(params.page_size)
            )
        )
        .scalars()
        .unique()
        .all()
    )
    return list(rows), total


async def plan_names(session: AsyncSession, *, organization_id: uuid.UUID) -> dict[uuid.UUID, str]:
    """Mapa id → nome dos planos, para evitar N+1 na serialização."""
    rows = (
        await session.execute(
            select(Plan.id, Plan.name).where(Plan.organization_id == organization_id)
        )
    ).all()
    return {row[0]: row[1] for row in rows}


def to_read(
    renewal: Renewal, *, today: date, plans: dict[uuid.UUID, str] | None = None
) -> RenewalRead:
    """Converte a renovação em schema, calculando dias até o vencimento."""
    data = RenewalRead.model_validate(renewal)
    data.days_until_due = (renewal.due_date - today).days
    if plans and renewal.plan_id:
        data.plan_name = plans.get(renewal.plan_id)
    return data


async def get_renewal(
    session: AsyncSession, *, organization_id: uuid.UUID, renewal_id: uuid.UUID
) -> Renewal:
    """Busca uma renovação da organização ou falha com 404."""
    result = await session.execute(
        _base_query(organization_id)
        .where(Renewal.id == renewal_id)
        .options(joinedload(Renewal.customer))
    )
    renewal: Renewal | None = result.unique().scalar_one_or_none()
    if renewal is None:
        raise NotFoundError("Renovação não encontrada.")
    return renewal


async def create_renewal(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    payload: RenewalCreate,
    actor: User,
    context: RequestContext | None = None,
) -> Renewal:
    """Cria uma renovação para um cliente da organização."""
    customer = (
        await session.execute(
            select(Customer).where(
                Customer.id == payload.customer_id,
                Customer.organization_id == organization_id,
                Customer.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if customer is None:
        raise ValidationError("Cliente informado não existe nesta organização.")

    renewal = Renewal(
        organization_id=organization_id,
        customer_id=customer.id,
        plan_id=customer.plan_id,
        due_date=payload.due_date,
        amount=payload.amount or customer.monthly_value,
        status=payload.status,
        notes=payload.notes,
    )
    session.add(renewal)
    await session.flush()
    await audit_service.record_audit(
        session,
        organization_id=organization_id,
        action="renewal.created",
        entity_type="renewal",
        entity_id=str(renewal.id),
        actor=actor,
        summary=f"Renovação de {customer.name} criada para {payload.due_date:%d/%m/%Y}.",
        context=context,
    )
    await session.commit()
    return await get_renewal(session, organization_id=organization_id, renewal_id=renewal.id)


async def update_renewal(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    renewal_id: uuid.UUID,
    payload: RenewalUpdate,
    actor: User,
    context: RequestContext | None = None,
) -> Renewal:
    """Atualiza data, valor, situação ou observações da renovação."""
    renewal = await get_renewal(session, organization_id=organization_id, renewal_id=renewal_id)
    before = {
        "due_date": renewal.due_date.isoformat(),
        "amount": str(renewal.amount),
        "status": renewal.status.value,
        "notes": renewal.notes,
    }
    data = payload.model_dump(exclude_unset=True)
    for attribute, value in data.items():
        setattr(renewal, attribute, value)
    if data.get("status") is RenewalStatus.CONFIRMED and renewal.confirmed_at is None:
        renewal.confirmed_at = utcnow()
        # Confirmar a renovação também desloca a data de renovação do cliente.
        customer = renewal.customer
        customer.renewal_date = renewal.due_date + timedelta(days=365)
        customer.status = CustomerStatus.ACTIVE

    after = {
        "due_date": renewal.due_date.isoformat(),
        "amount": str(renewal.amount),
        "status": renewal.status.value,
        "notes": renewal.notes,
    }
    diff = audit_service.build_diff(before, after)
    if diff:
        await audit_service.record_audit(
            session,
            organization_id=organization_id,
            action=audit_service.ACTION_RENEWAL_UPDATE,
            entity_type="renewal",
            entity_id=str(renewal.id),
            actor=actor,
            summary=f"Renovação de {renewal.customer.name} atualizada.",
            meta={"changes": diff},
            context=context,
        )
    await session.commit()
    return await get_renewal(session, organization_id=organization_id, renewal_id=renewal.id)


async def indicators(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    contact_threshold_days: int = CONTACT_THRESHOLD_DAYS,
) -> RenewalIndicators:
    """Calcula os indicadores de renovação a partir do banco."""
    today = utcnow().date()
    open_filter = Renewal.status.in_(OPEN_STATUSES)

    async def count_renewals(*conditions: Any) -> int:
        stmt = (
            select(func.count())
            .select_from(Renewal)
            .join(Customer, Renewal.customer_id == Customer.id)
            .where(
                Renewal.organization_id == organization_id,
                Customer.deleted_at.is_(None),
                *conditions,
            )
        )
        return int((await session.execute(stmt)).scalar_one())

    async def sum_renewals(*conditions: Any) -> Decimal:
        stmt = (
            select(func.coalesce(func.sum(Renewal.amount), 0))
            .select_from(Renewal)
            .join(Customer, Renewal.customer_id == Customer.id)
            .where(
                Renewal.organization_id == organization_id,
                Customer.deleted_at.is_(None),
                *conditions,
            )
        )
        return Decimal((await session.execute(stmt)).scalar_one() or 0).quantize(Decimal("0.01"))

    due_7 = await count_renewals(
        open_filter, Renewal.due_date >= today, Renewal.due_date <= today + timedelta(days=7)
    )
    due_30 = await count_renewals(
        open_filter, Renewal.due_date >= today, Renewal.due_date <= today + timedelta(days=30)
    )
    overdue = await count_renewals(open_filter, Renewal.due_date < today)
    amount_at_risk = await sum_renewals(
        or_(
            and_(Renewal.status == RenewalStatus.AT_RISK, Renewal.due_date >= today),
            and_(open_filter, Renewal.due_date < today),
        )
    )
    amount_30 = await sum_renewals(
        open_filter, Renewal.due_date >= today, Renewal.due_date <= today + timedelta(days=30)
    )
    confirmed_30 = await count_renewals(
        Renewal.status == RenewalStatus.CONFIRMED,
        Renewal.confirmed_at.is_not(None),
        Renewal.confirmed_at >= utcnow() - timedelta(days=30),
    )
    lost_30 = await count_renewals(
        Renewal.status == RenewalStatus.LOST,
        Renewal.updated_at >= utcnow() - timedelta(days=30),
    )

    cutoff = utcnow() - timedelta(days=contact_threshold_days)
    without_contact = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Customer)
                .where(
                    Customer.organization_id == organization_id,
                    Customer.deleted_at.is_(None),
                    Customer.status != CustomerStatus.CHURNED,
                    or_(
                        Customer.last_contact_at.is_(None),
                        Customer.last_contact_at < cutoff,
                    ),
                )
            )
        ).scalar_one()
    )

    return RenewalIndicators(
        due_next_7_days=due_7,
        due_next_30_days=due_30,
        overdue=overdue,
        amount_at_risk=amount_at_risk,
        amount_next_30_days=amount_30,
        customers_without_recent_contact=without_contact,
        contact_threshold_days=contact_threshold_days,
        confirmed_last_30_days=confirmed_30,
        lost_last_30_days=lost_30,
        reference_date=today,
    )


async def critical_renewals(
    session: AsyncSession, *, organization_id: uuid.UUID, limit: int = 10
) -> list[CriticalRenewal]:
    """Renovações que exigem ação imediata, com o motivo de cada destaque."""
    today = utcnow().date()
    horizon = today + timedelta(days=30)
    rows = (
        (
            await session.execute(
                _base_query(organization_id)
                .where(
                    Renewal.status.in_(OPEN_STATUSES),
                    Renewal.due_date <= horizon,
                )
                .options(joinedload(Renewal.customer))
                .order_by(Renewal.due_date, Renewal.amount.desc())
                .limit(limit)
            )
        )
        .scalars()
        .unique()
        .all()
    )
    plans = await plan_names(session, organization_id=organization_id)

    results: list[CriticalRenewal] = []
    for renewal in rows:
        days = (renewal.due_date - today).days
        if days < 0:
            reason = f"Vencida há {abs(days)} dia(s)."
        elif renewal.status is RenewalStatus.AT_RISK:
            reason = "Marcada como em risco pela equipe."
        elif renewal.customer.status is CustomerStatus.PAST_DUE:
            reason = "Cliente com pagamento atrasado."
        elif days <= 7:
            reason = f"Vence em {days} dia(s)."
        else:
            reason = f"Vence em {days} dias."
        results.append(
            CriticalRenewal(
                customer_id=renewal.customer_id,
                customer_name=renewal.customer.name,
                plan_name=plans.get(renewal.plan_id) if renewal.plan_id else None,
                due_date=renewal.due_date,
                days_until_due=days,
                amount=renewal.amount,
                status=renewal.status,
                customer_status=renewal.customer.status,
                reason=reason,
            )
        )
    return results


CSV_HEADERS = (
    "Cliente",
    "Plano",
    "Vencimento",
    "Dias até vencer",
    "Valor",
    "Situação",
    "Confirmada em",
    "Observações",
)

STATUS_LABELS: dict[RenewalStatus, str] = {
    RenewalStatus.SCHEDULED: "Agendada",
    RenewalStatus.AT_RISK: "Em risco",
    RenewalStatus.CONFIRMED: "Confirmada",
    RenewalStatus.LOST: "Perdida",
}


def to_csv_row(renewal: Renewal, *, today: date, plans: dict[uuid.UUID, str]) -> list[Any]:
    """Linha de exportação CSV de uma renovação."""
    return [
        renewal.customer.name,
        plans.get(renewal.plan_id) if renewal.plan_id else None,
        renewal.due_date,
        (renewal.due_date - today).days,
        renewal.amount,
        STATUS_LABELS.get(renewal.status, renewal.status.value),
        renewal.confirmed_at,
        renewal.notes,
    ]
