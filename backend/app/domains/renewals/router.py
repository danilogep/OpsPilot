"""Rotas de renovações."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import ContextDep, RequireAnalyst, RequireViewer, SessionDep
from app.core.exporting import csv_response
from app.core.pagination import Page, PageParams, page_params
from app.db.base import utcnow
from app.db.models.enums import RenewalStatus
from app.domains.renewals import service
from app.domains.renewals.schemas import (
    CriticalRenewal,
    RenewalCreate,
    RenewalIndicators,
    RenewalRead,
    RenewalUpdate,
)

router = APIRouter(prefix="/renewals", tags=["Renovações"])


def _filters(
    status_filter: Annotated[
        list[RenewalStatus] | None, Query(alias="status", description="Situações")
    ] = None,
    due_from: Annotated[date | None, Query(description="Vencimento a partir de")] = None,
    due_to: Annotated[date | None, Query(description="Vencimento até")] = None,
    within_days: Annotated[
        int | None, Query(ge=1, le=365, description="Vencendo nos próximos N dias")
    ] = None,
    overdue_only: Annotated[bool, Query(description="Somente vencidas em aberto")] = False,
    customer_id: Annotated[uuid.UUID | None, Query(description="Filtra por cliente")] = None,
    search: Annotated[str | None, Query(description="Busca pelo nome do cliente")] = None,
) -> service.RenewalFilters:
    """Dependência que agrupa os filtros de renovação."""
    return service.RenewalFilters(
        statuses=status_filter,
        due_from=due_from,
        due_to=due_to,
        within_days=within_days,
        overdue_only=overdue_only,
        customer_id=customer_id,
        search=search,
    )


FiltersDep = Annotated[service.RenewalFilters, Depends(_filters)]


@router.get("", response_model=Page[RenewalRead], summary="Listar renovações")
async def list_renewals(
    session: SessionDep,
    user: RequireViewer,
    params: Annotated[PageParams, Depends(page_params)],
    filters: FiltersDep,
    sort: Annotated[str, Query(description="Campo de ordenação")] = "due_date",
    direction: Annotated[str, Query(pattern="^(asc|desc)$")] = "asc",
) -> Page[RenewalRead]:
    """Lista renovações com filtros, ordenação e paginação."""
    renewals, total = await service.list_renewals(
        session,
        organization_id=user.organization_id,
        params=params,
        filters=filters,
        sort=sort,
        direction=direction,
    )
    plans = await service.plan_names(session, organization_id=user.organization_id)
    today = utcnow().date()
    return Page.build(
        [service.to_read(item, today=today, plans=plans) for item in renewals], total, params
    )


@router.get("/indicators", response_model=RenewalIndicators, summary="Indicadores de renovação")
async def renewal_indicators(
    session: SessionDep,
    user: RequireViewer,
    contact_threshold_days: Annotated[
        int, Query(ge=1, le=365, description="Dias sem contato considerados risco")
    ] = service.CONTACT_THRESHOLD_DAYS,
) -> RenewalIndicators:
    """Calcula renovações próximas, atrasos, valor em risco e falta de contato."""
    return await service.indicators(
        session,
        organization_id=user.organization_id,
        contact_threshold_days=contact_threshold_days,
    )


@router.get("/critical", response_model=list[CriticalRenewal], summary="Renovações críticas")
async def critical(
    session: SessionDep,
    user: RequireViewer,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> list[CriticalRenewal]:
    """Lista as renovações que exigem ação imediata, com o motivo."""
    return await service.critical_renewals(
        session, organization_id=user.organization_id, limit=limit
    )


@router.get("/export", summary="Exportar renovações em CSV")
async def export_renewals(
    session: SessionDep, user: RequireViewer, filters: FiltersDep
) -> Response:
    """Exporta a listagem filtrada de renovações em CSV."""
    renewals, total = await service.list_renewals(
        session,
        organization_id=user.organization_id,
        params=PageParams(page=1, page_size=200),
        filters=filters,
    )
    for page in range(2, (total + 199) // 200 + 1):
        batch, _ = await service.list_renewals(
            session,
            organization_id=user.organization_id,
            params=PageParams(page=page, page_size=200),
            filters=filters,
        )
        renewals.extend(batch)
    plans = await service.plan_names(session, organization_id=user.organization_id)
    today = utcnow().date()
    return csv_response(
        filename=f"renovacoes-{today.isoformat()}.csv",
        headers=service.CSV_HEADERS,
        rows=[service.to_csv_row(item, today=today, plans=plans) for item in renewals],
    )


@router.post(
    "",
    response_model=RenewalRead,
    status_code=status.HTTP_201_CREATED,
    summary="Criar renovação",
)
async def create_renewal(
    payload: RenewalCreate, session: SessionDep, user: RequireAnalyst, context: ContextDep
) -> RenewalRead:
    """Cria uma renovação manualmente."""
    renewal = await service.create_renewal(
        session,
        organization_id=user.organization_id,
        payload=payload,
        actor=user,
        context=context,
    )
    plans = await service.plan_names(session, organization_id=user.organization_id)
    return service.to_read(renewal, today=utcnow().date(), plans=plans)


@router.get("/{renewal_id}", response_model=RenewalRead, summary="Detalhe da renovação")
async def get_renewal(
    renewal_id: uuid.UUID, session: SessionDep, user: RequireViewer
) -> RenewalRead:
    """Retorna uma renovação da organização."""
    renewal = await service.get_renewal(
        session, organization_id=user.organization_id, renewal_id=renewal_id
    )
    plans = await service.plan_names(session, organization_id=user.organization_id)
    return service.to_read(renewal, today=utcnow().date(), plans=plans)


@router.patch("/{renewal_id}", response_model=RenewalRead, summary="Atualizar renovação")
async def update_renewal(
    renewal_id: uuid.UUID,
    payload: RenewalUpdate,
    session: SessionDep,
    user: RequireAnalyst,
    context: ContextDep,
) -> RenewalRead:
    """Atualiza a renovação; confirmar move a data do cliente para o próximo ciclo."""
    renewal = await service.update_renewal(
        session,
        organization_id=user.organization_id,
        renewal_id=renewal_id,
        payload=payload,
        actor=user,
        context=context,
    )
    plans = await service.plan_names(session, organization_id=user.organization_id)
    return service.to_read(renewal, today=utcnow().date(), plans=plans)
