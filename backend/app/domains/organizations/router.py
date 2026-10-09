"""Rotas do dashboard e da organização."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query

from app.api.deps import RequireViewer, SessionDep
from app.domains.organizations import metrics
from app.domains.renewals.service import CONTACT_THRESHOLD_DAYS

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/overview", summary="Visão geral consolidada")
async def overview(
    session: SessionDep,
    user: RequireViewer,
    contact_threshold_days: Annotated[
        int, Query(ge=1, le=365, description="Dias sem contato considerados risco")
    ] = CONTACT_THRESHOLD_DAYS,
    timeline_months: Annotated[
        int, Query(ge=3, le=24, description="Meses no gráfico de evolução")
    ] = 6,
) -> dict[str, Any]:
    """Todos os indicadores da visão geral, calculados a partir do banco."""
    return await metrics.dashboard_overview(
        session,
        organization_id=user.organization_id,
        contact_threshold_days=contact_threshold_days,
        timeline_months=timeline_months,
    )


@router.get("/customers", summary="Indicadores de clientes")
async def customers(session: SessionDep, user: RequireViewer) -> dict[str, Any]:
    """Totais por situação, receita mensal e ticket médio."""
    return await metrics.customer_overview(session, organization_id=user.organization_id)


@router.get("/timeline", summary="Evolução mensal")
async def timeline(
    session: SessionDep,
    user: RequireViewer,
    months: Annotated[int, Query(ge=3, le=24)] = 6,
) -> list[dict[str, Any]]:
    """Série mensal de novos clientes e receita adicionada."""
    return await metrics.revenue_timeline(
        session, organization_id=user.organization_id, months=months
    )


@router.get("/ai-usage", summary="Uso estimado de IA")
async def ai_usage(
    session: SessionDep,
    user: RequireViewer,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> dict[str, Any]:
    """Chamadas, tokens e custo estimado no período."""
    return await metrics.ai_usage_overview(session, organization_id=user.organization_id, days=days)
