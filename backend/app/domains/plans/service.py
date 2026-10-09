"""Serviço de planos, incluindo indicadores agregados por plano."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequestContext
from app.core.errors import ConflictError, NotFoundError
from app.db.base import utcnow
from app.db.models import Customer, CustomerStatus, Plan, User
from app.domains.audit import service as audit_service
from app.domains.customers.schemas import PlanCreate, PlanUpdate, PlanWithMetrics


async def list_plans(
    session: AsyncSession, *, organization_id: uuid.UUID, include_inactive: bool = True
) -> list[PlanWithMetrics]:
    """Lista planos com contagem de clientes, receita e taxa de cancelamento."""
    active_case = case((Customer.status == CustomerStatus.ACTIVE, 1), else_=0)
    churn_case = case((Customer.status == CustomerStatus.CHURNED, 1), else_=0)
    revenue_case = case(
        (
            Customer.status.in_([CustomerStatus.ACTIVE, CustomerStatus.PAST_DUE]),
            Customer.monthly_value,
        ),
        else_=0,
    )

    stmt = (
        select(
            Plan,
            func.count(Customer.id),
            func.coalesce(func.sum(active_case), 0),
            func.coalesce(func.sum(churn_case), 0),
            func.coalesce(func.sum(revenue_case), 0),
        )
        .outerjoin(
            Customer,
            (Customer.plan_id == Plan.id) & (Customer.deleted_at.is_(None)),
        )
        .where(Plan.organization_id == organization_id, Plan.deleted_at.is_(None))
        .group_by(Plan.id)
        .order_by(Plan.monthly_value.desc(), Plan.name)
    )
    if not include_inactive:
        stmt = stmt.where(Plan.is_active.is_(True))

    rows = (await session.execute(stmt)).all()
    results: list[PlanWithMetrics] = []
    for plan, total, active, churned, revenue in rows:
        item = PlanWithMetrics.model_validate(plan)
        item.customers_count = int(total)
        item.active_customers = int(active)
        item.churned_customers = int(churned)
        item.monthly_revenue = Decimal(revenue or 0).quantize(Decimal("0.01"))
        item.churn_rate = round(int(churned) / int(total), 4) if total else 0.0
        results.append(item)
    return results


async def get_plan(
    session: AsyncSession, *, organization_id: uuid.UUID, plan_id: uuid.UUID
) -> Plan:
    """Busca um plano da organização ou falha com 404."""
    plan = (
        await session.execute(
            select(Plan).where(
                Plan.id == plan_id,
                Plan.organization_id == organization_id,
                Plan.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if plan is None:
        raise NotFoundError("Plano não encontrado.")
    return plan


async def create_plan(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    payload: PlanCreate,
    actor: User,
    context: RequestContext | None = None,
) -> Plan:
    """Cria um plano, impedindo nomes repetidos na organização."""
    exists = (
        await session.execute(
            select(Plan.id).where(
                Plan.organization_id == organization_id,
                func.lower(Plan.name) == payload.name.strip().lower(),
                Plan.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if exists:
        raise ConflictError("Já existe um plano com este nome.")

    plan = Plan(
        organization_id=organization_id,
        name=payload.name.strip(),
        code=payload.code,
        description=payload.description,
        monthly_value=payload.monthly_value,
        is_active=payload.is_active,
    )
    session.add(plan)
    await session.flush()
    await audit_service.record_audit(
        session,
        organization_id=organization_id,
        action=audit_service.ACTION_PLAN_CREATE,
        entity_type="plan",
        entity_id=str(plan.id),
        actor=actor,
        summary=f"Plano {plan.name} criado.",
        context=context,
    )
    await session.commit()
    await session.refresh(plan)
    return plan


async def update_plan(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    plan_id: uuid.UUID,
    payload: PlanUpdate,
    actor: User,
    context: RequestContext | None = None,
) -> Plan:
    """Atualiza um plano e registra o diff."""
    plan = await get_plan(session, organization_id=organization_id, plan_id=plan_id)
    before = {
        "name": plan.name,
        "code": plan.code,
        "description": plan.description,
        "monthly_value": str(plan.monthly_value),
        "is_active": plan.is_active,
    }
    for attribute, value in payload.model_dump(exclude_unset=True).items():
        setattr(plan, attribute, value)
    after = {
        "name": plan.name,
        "code": plan.code,
        "description": plan.description,
        "monthly_value": str(plan.monthly_value),
        "is_active": plan.is_active,
    }
    diff = audit_service.build_diff(before, after)
    if diff:
        await audit_service.record_audit(
            session,
            organization_id=organization_id,
            action=audit_service.ACTION_PLAN_UPDATE,
            entity_type="plan",
            entity_id=str(plan.id),
            actor=actor,
            summary=f"Plano {plan.name} atualizado.",
            meta={"changes": diff},
            context=context,
        )
    await session.commit()
    await session.refresh(plan)
    return plan


async def delete_plan(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    plan_id: uuid.UUID,
    actor: User,
    context: RequestContext | None = None,
) -> None:
    """Exclusão lógica do plano, se não houver cliente vinculado."""
    plan = await get_plan(session, organization_id=organization_id, plan_id=plan_id)
    linked = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Customer)
                .where(Customer.plan_id == plan.id, Customer.deleted_at.is_(None))
            )
        ).scalar_one()
    )
    if linked:
        raise ConflictError(
            "Não é possível excluir um plano com clientes vinculados.",
            details={"customers": linked},
        )
    plan.deleted_at = utcnow()
    await audit_service.record_audit(
        session,
        organization_id=organization_id,
        action="plan.deleted",
        entity_type="plan",
        entity_id=str(plan.id),
        actor=actor,
        summary=f"Plano {plan.name} excluído.",
        context=context,
    )
    await session.commit()
