"""Cálculo dos indicadores do dashboard.

Regras:

* **nenhum número é inventado** — tudo vem de consultas agregadas ao banco;
* cada bloco informa a data de referência e a janela usada;
* o mesmo serviço alimenta o dashboard, o assistente de IA e as ferramentas dos
  agentes, garantindo que todos vejam os mesmos valores.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.db.models import (
    Customer,
    CustomerStatus,
    ImportJob,
    ImportStatus,
    Lead,
    LeadStatus,
    LLMUsage,
    Plan,
    Renewal,
    RenewalStatus,
)
from app.domains.leads.service import HIGH_PRIORITY_SCORE
from app.domains.leads.service import OPEN_STATUSES as OPEN_LEAD_STATUSES
from app.domains.renewals.service import CONTACT_THRESHOLD_DAYS
from app.domains.renewals.service import OPEN_STATUSES as OPEN_RENEWALS

ACTIVE_STATUSES = (CustomerStatus.ACTIVE, CustomerStatus.PAST_DUE)


async def _scalar(session: AsyncSession, stmt: Any) -> Any:
    return (await session.execute(stmt)).scalar_one()


async def customer_overview(session: AsyncSession, *, organization_id: uuid.UUID) -> dict[str, Any]:
    """Totais de clientes, receita mensal estimada e distribuição por situação."""
    rows = (
        await session.execute(
            select(
                Customer.status, func.count(), func.coalesce(func.sum(Customer.monthly_value), 0)
            )
            .where(Customer.organization_id == organization_id, Customer.deleted_at.is_(None))
            .group_by(Customer.status)
        )
    ).all()
    by_status = {
        row[0].value: {"total": int(row[1]), "monthly_value": str(Decimal(row[2] or 0))}
        for row in rows
    }
    total = sum(int(row[1]) for row in rows)
    billable_total = sum(int(row[1]) for row in rows if row[0] in ACTIVE_STATUSES)
    active_revenue = sum(Decimal(row[2] or 0) for row in rows if row[0] in ACTIVE_STATUSES)
    return {
        "total_customers": total,
        "active_customers": by_status.get(CustomerStatus.ACTIVE.value, {}).get("total", 0),
        "past_due_customers": by_status.get(CustomerStatus.PAST_DUE.value, {}).get("total", 0),
        "churned_customers": by_status.get(CustomerStatus.CHURNED.value, {}).get("total", 0),
        "prospect_customers": by_status.get(CustomerStatus.PROSPECT.value, {}).get("total", 0),
        "monthly_revenue": str(Decimal(active_revenue).quantize(Decimal("0.01"))),
        "average_ticket": str(
            (Decimal(active_revenue) / billable_total).quantize(Decimal("0.01"))
            if billable_total
            else Decimal("0.00")
        ),
        "by_status": by_status,
    }


async def renewal_overview(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    contact_threshold_days: int = CONTACT_THRESHOLD_DAYS,
) -> dict[str, Any]:
    """Renovações próximas, atrasos, valor em risco e falta de contato."""
    today = utcnow().date()

    def renewal_base() -> Any:
        return (
            select(func.count(), func.coalesce(func.sum(Renewal.amount), 0))
            .select_from(Renewal)
            .join(Customer, Renewal.customer_id == Customer.id)
            .where(
                Renewal.organization_id == organization_id,
                Customer.deleted_at.is_(None),
            )
        )

    async def window(days: int) -> tuple[int, Decimal]:
        row = (
            await session.execute(
                renewal_base().where(
                    Renewal.status.in_(OPEN_RENEWALS),
                    Renewal.due_date >= today,
                    Renewal.due_date <= today + timedelta(days=days),
                )
            )
        ).one()
        return int(row[0]), Decimal(row[1] or 0).quantize(Decimal("0.01"))

    next_7, amount_7 = await window(7)
    next_30, amount_30 = await window(30)

    overdue_row = (
        await session.execute(
            renewal_base().where(Renewal.status.in_(OPEN_RENEWALS), Renewal.due_date < today)
        )
    ).one()
    at_risk_row = (
        await session.execute(
            renewal_base().where(Renewal.status == RenewalStatus.AT_RISK, Renewal.due_date >= today)
        )
    ).one()

    cutoff = utcnow() - timedelta(days=contact_threshold_days)
    without_contact = int(
        await _scalar(
            session,
            select(func.count())
            .select_from(Customer)
            .where(
                Customer.organization_id == organization_id,
                Customer.deleted_at.is_(None),
                Customer.status != CustomerStatus.CHURNED,
                or_(Customer.last_contact_at.is_(None), Customer.last_contact_at < cutoff),
            ),
        )
    )
    amount_at_risk = (Decimal(overdue_row[1] or 0) + Decimal(at_risk_row[1] or 0)).quantize(
        Decimal("0.01")
    )

    return {
        "reference_date": today.isoformat(),
        "due_next_7_days": next_7,
        "amount_next_7_days": str(amount_7),
        "due_next_30_days": next_30,
        "amount_next_30_days": str(amount_30),
        "overdue": int(overdue_row[0]),
        "amount_overdue": str(Decimal(overdue_row[1] or 0).quantize(Decimal("0.01"))),
        "at_risk": int(at_risk_row[0]),
        "amount_at_risk": str(amount_at_risk),
        "customers_without_recent_contact": without_contact,
        "contact_threshold_days": contact_threshold_days,
    }


async def lead_overview(session: AsyncSession, *, organization_id: uuid.UUID) -> dict[str, Any]:
    """Totais de leads, pipeline e prioridade."""
    row = (
        await session.execute(
            select(
                func.count(),
                func.coalesce(func.sum(case((Lead.status.in_(OPEN_LEAD_STATUSES), 1), else_=0)), 0),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                Lead.status.in_(OPEN_LEAD_STATUSES)
                                & (Lead.score >= HIGH_PRIORITY_SCORE),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (Lead.status.in_(OPEN_LEAD_STATUSES), Lead.estimated_value),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(func.avg(Lead.score), 0),
            ).where(Lead.organization_id == organization_id, Lead.deleted_at.is_(None))
        )
    ).one()
    won = int(
        await _scalar(
            session,
            select(func.count())
            .select_from(Lead)
            .where(
                Lead.organization_id == organization_id,
                Lead.deleted_at.is_(None),
                Lead.status == LeadStatus.WON,
            ),
        )
    )
    return {
        "total_leads": int(row[0]),
        "open_leads": int(row[1]),
        "high_priority_leads": int(row[2]),
        "estimated_pipeline": str(Decimal(row[3] or 0).quantize(Decimal("0.01"))),
        "average_score": round(float(row[4] or 0), 1),
        "won_leads": won,
    }


async def plan_ranking(
    session: AsyncSession, *, organization_id: uuid.UUID, limit: int = 10
) -> list[dict[str, Any]]:
    """Ranking de planos por receita, com taxa de cancelamento."""
    rows = (
        await session.execute(
            select(
                Plan.name,
                func.count(Customer.id),
                func.coalesce(
                    func.sum(
                        case(
                            (Customer.status.in_(ACTIVE_STATUSES), Customer.monthly_value), else_=0
                        )
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(case((Customer.status == CustomerStatus.CHURNED, 1), else_=0)), 0
                ),
            )
            .outerjoin(Customer, (Customer.plan_id == Plan.id) & (Customer.deleted_at.is_(None)))
            .where(Plan.organization_id == organization_id, Plan.deleted_at.is_(None))
            .group_by(Plan.id, Plan.name)
            .order_by(func.count(Customer.id).desc())
            .limit(limit)
        )
    ).all()
    ranking: list[dict[str, Any]] = []
    for name, total, revenue, churned in rows:
        total_int = int(total)
        ranking.append(
            {
                "plan_name": name,
                "customers": total_int,
                "monthly_revenue": str(Decimal(revenue or 0).quantize(Decimal("0.01"))),
                "churned_customers": int(churned),
                "churn_rate": round(int(churned) / total_int, 4) if total_int else 0.0,
            }
        )
    return ranking


async def lead_source_ranking(
    session: AsyncSession, *, organization_id: uuid.UUID, limit: int = 10
) -> list[dict[str, Any]]:
    """Ranking de origens de leads por volume e qualidade."""
    rows = (
        await session.execute(
            select(
                Lead.source,
                func.count(),
                func.coalesce(func.avg(Lead.score), 0),
                func.coalesce(func.sum(Lead.estimated_value), 0),
                func.coalesce(func.sum(case((Lead.status == LeadStatus.WON, 1), else_=0)), 0),
            )
            .where(Lead.organization_id == organization_id, Lead.deleted_at.is_(None))
            .group_by(Lead.source)
            .order_by(func.count().desc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "source": row[0],
            "total": int(row[1]),
            "average_score": round(float(row[2] or 0), 1),
            "estimated_value": str(Decimal(row[3] or 0).quantize(Decimal("0.01"))),
            "won": int(row[4]),
        }
        for row in rows
    ]


async def import_overview(
    session: AsyncSession, *, organization_id: uuid.UUID, limit: int = 5
) -> dict[str, Any]:
    """Importações recentes e total de erros acumulados."""
    rows = (
        (
            await session.execute(
                select(ImportJob)
                .where(ImportJob.organization_id == organization_id)
                .order_by(ImportJob.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .unique()
        .all()
    )
    totals = (
        await session.execute(
            select(
                func.count(),
                func.coalesce(func.sum(ImportJob.invalid_rows), 0),
                func.coalesce(func.sum(ImportJob.duplicate_rows), 0),
                func.coalesce(func.sum(ImportJob.imported_rows), 0),
            ).where(ImportJob.organization_id == organization_id)
        )
    ).one()
    return {
        "total_imports": int(totals[0]),
        "total_invalid_rows": int(totals[1]),
        "total_duplicate_rows": int(totals[2]),
        "total_imported_rows": int(totals[3]),
        "recent": [
            {
                "id": str(job.id),
                "filename": job.original_filename,
                "status": job.status.value,
                "total_rows": job.total_rows,
                "valid_rows": job.valid_rows,
                "invalid_rows": job.invalid_rows,
                "duplicate_rows": job.duplicate_rows,
                "imported_rows": job.imported_rows,
                "created_at": job.created_at.isoformat(),
            }
            for job in rows
        ],
        "pending_commit": int(
            await _scalar(
                session,
                select(func.count())
                .select_from(ImportJob)
                .where(
                    ImportJob.organization_id == organization_id,
                    ImportJob.status.in_(
                        [ImportStatus.UPLOADED, ImportStatus.MAPPED, ImportStatus.VALIDATED]
                    ),
                ),
            )
        ),
    }


async def ai_usage_overview(
    session: AsyncSession, *, organization_id: uuid.UUID, days: int = 30
) -> dict[str, Any]:
    """Uso estimado de IA no período."""
    since = utcnow() - timedelta(days=days)
    row = (
        await session.execute(
            select(
                func.count(),
                func.coalesce(func.sum(LLMUsage.input_tokens), 0),
                func.coalesce(func.sum(LLMUsage.output_tokens), 0),
                func.coalesce(func.sum(LLMUsage.estimated_cost_usd), 0),
                func.coalesce(func.avg(LLMUsage.duration_ms), 0),
            ).where(LLMUsage.organization_id == organization_id, LLMUsage.created_at >= since)
        )
    ).one()
    by_feature = (
        await session.execute(
            select(LLMUsage.feature, func.count())
            .where(LLMUsage.organization_id == organization_id, LLMUsage.created_at >= since)
            .group_by(LLMUsage.feature)
            .order_by(func.count().desc())
        )
    ).all()
    return {
        "window_days": days,
        "calls": int(row[0]),
        "input_tokens": int(row[1]),
        "output_tokens": int(row[2]),
        "estimated_cost_usd": str(Decimal(row[3] or 0).quantize(Decimal("0.000001"))),
        "average_duration_ms": int(row[4] or 0),
        "by_feature": [{"feature": item[0], "calls": int(item[1])} for item in by_feature],
    }


async def revenue_timeline(
    session: AsyncSession, *, organization_id: uuid.UUID, months: int = 6
) -> list[dict[str, Any]]:
    """Evolução mensal de novos clientes e receita adicionada.

    Agrupamento feito em Python a partir de ``start_date`` para manter o SQL
    portável entre PostgreSQL e SQLite.
    """
    today = utcnow().date()
    month_index = today.year * 12 + today.month - months
    first_month = date(month_index // 12, month_index % 12 + 1, 1)
    rows = (
        await session.execute(
            select(Customer.start_date, Customer.monthly_value, Customer.status).where(
                Customer.organization_id == organization_id,
                Customer.deleted_at.is_(None),
                Customer.start_date.is_not(None),
                Customer.start_date >= first_month,
            )
        )
    ).all()

    buckets: dict[str, dict[str, Any]] = {}
    cursor = date(first_month.year, first_month.month, 1)
    while cursor <= today:
        key = cursor.strftime("%Y-%m")
        buckets[key] = {
            "month": key,
            "new_customers": 0,
            "added_monthly_value": Decimal("0.00"),
            "churned_customers": 0,
        }
        cursor = date(cursor.year + (cursor.month // 12), (cursor.month % 12) + 1, 1)

    for start_date, monthly_value, status in rows:
        key = start_date.strftime("%Y-%m")
        bucket = buckets.get(key)
        if bucket is None:
            continue
        bucket["new_customers"] += 1
        bucket["added_monthly_value"] += Decimal(monthly_value or 0)
        if status is CustomerStatus.CHURNED:
            bucket["churned_customers"] += 1

    return [
        {
            "month": item["month"],
            "new_customers": item["new_customers"],
            "added_monthly_value": str(
                Decimal(item["added_monthly_value"]).quantize(Decimal("0.01"))
            ),
            "churned_customers": item["churned_customers"],
        }
        for item in buckets.values()
    ]


async def dashboard_overview(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    contact_threshold_days: int = CONTACT_THRESHOLD_DAYS,
    timeline_months: int = 6,
) -> dict[str, Any]:
    """Consolida todos os blocos exibidos na visão geral."""
    return {
        "generated_at": utcnow().isoformat(),
        "reference_date": utcnow().date().isoformat(),
        "customers": await customer_overview(session, organization_id=organization_id),
        "renewals": await renewal_overview(
            session,
            organization_id=organization_id,
            contact_threshold_days=contact_threshold_days,
        ),
        "leads": await lead_overview(session, organization_id=organization_id),
        "plans": await plan_ranking(session, organization_id=organization_id),
        "lead_sources": await lead_source_ranking(session, organization_id=organization_id),
        "imports": await import_overview(session, organization_id=organization_id),
        "ai_usage": await ai_usage_overview(session, organization_id=organization_id),
        "timeline": await revenue_timeline(
            session, organization_id=organization_id, months=timeline_months
        ),
    }


async def metrics_for_ai(session: AsyncSession, *, organization_id: uuid.UUID) -> dict[str, Any]:
    """Subconjunto de métricas usado pelo assistente e pelos agentes."""
    return {
        "customers": await customer_overview(session, organization_id=organization_id),
        "renewals": await renewal_overview(session, organization_id=organization_id),
        "leads": await lead_overview(session, organization_id=organization_id),
        "plans": await plan_ranking(session, organization_id=organization_id, limit=5),
        "lead_sources": await lead_source_ranking(
            session, organization_id=organization_id, limit=5
        ),
    }
