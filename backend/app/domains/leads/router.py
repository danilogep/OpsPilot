"""Rotas de leads."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import ContextDep, RequireAnalyst, RequireViewer, SessionDep
from app.core.exporting import csv_response
from app.core.pagination import Page, PageParams, page_params
from app.db.base import utcnow
from app.db.models.enums import LeadCategory, LeadStatus, ScoringMethod
from app.domains.leads import service
from app.domains.leads.schemas import (
    LeadCreate,
    LeadEventRead,
    LeadIndicators,
    LeadNoteCreate,
    LeadRead,
    LeadScoreResponse,
    LeadUpdate,
    ScoreReasonRead,
)

router = APIRouter(prefix="/leads", tags=["Leads"])


def _filters(
    search: Annotated[str | None, Query(description="Busca por nome, empresa ou e-mail")] = None,
    status_filter: Annotated[
        list[LeadStatus] | None, Query(alias="status", description="Estágios do funil")
    ] = None,
    category: Annotated[list[LeadCategory] | None, Query(description="Categorias de score")] = None,
    source: Annotated[str | None, Query(description="Origem do lead")] = None,
    segment: Annotated[str | None, Query(description="Segmento")] = None,
    min_score: Annotated[int | None, Query(ge=0, le=100, description="Score mínimo")] = None,
    only_open: Annotated[bool, Query(description="Somente leads em aberto")] = False,
    stale_days: Annotated[
        int | None, Query(ge=1, le=365, description="Sem interação há N dias")
    ] = None,
) -> service.LeadFilters:
    """Dependência que agrupa os filtros de leads."""
    return service.LeadFilters(
        search=search,
        statuses=status_filter,
        categories=category,
        source=source,
        segment=segment,
        min_score=min_score,
        only_open=only_open,
        stale_days=stale_days,
    )


FiltersDep = Annotated[service.LeadFilters, Depends(_filters)]


@router.get("", response_model=Page[LeadRead], summary="Listar leads")
async def list_leads(
    session: SessionDep,
    user: RequireViewer,
    params: Annotated[PageParams, Depends(page_params)],
    filters: FiltersDep,
    sort: Annotated[str, Query(description="Campo de ordenação")] = "score",
    direction: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
) -> Page[LeadRead]:
    """Lista leads ordenados por prioridade (score) por padrão."""
    leads, total = await service.list_leads(
        session,
        organization_id=user.organization_id,
        params=params,
        filters=filters,
        sort=sort,
        direction=direction,
    )
    return Page.build([service.to_read(lead) for lead in leads], total, params)


@router.get("/indicators", response_model=LeadIndicators, summary="Indicadores de leads")
async def lead_indicators(session: SessionDep, user: RequireViewer) -> LeadIndicators:
    """Funil, pipeline estimado e ranking de origens."""
    return await service.indicators(session, organization_id=user.organization_id)


@router.get("/export", summary="Exportar leads em CSV")
async def export_leads(session: SessionDep, user: RequireViewer, filters: FiltersDep) -> Response:
    """Exporta a listagem filtrada de leads em CSV."""
    leads, _ = await service.list_leads(
        session,
        organization_id=user.organization_id,
        params=PageParams(page=1, page_size=200),
        filters=filters,
    )
    return csv_response(
        filename=f"leads-{utcnow().date().isoformat()}.csv",
        headers=service.CSV_HEADERS,
        rows=[service.to_csv_row(lead) for lead in leads],
    )


@router.post("", response_model=LeadRead, status_code=status.HTTP_201_CREATED, summary="Criar lead")
async def create_lead(
    payload: LeadCreate, session: SessionDep, user: RequireAnalyst, context: ContextDep
) -> LeadRead:
    """Cria um lead e calcula o score determinístico."""
    lead = await service.create_lead(
        session,
        organization_id=user.organization_id,
        payload=payload,
        actor=user,
        context=context,
    )
    return service.to_read(lead)


@router.get("/{lead_id}", response_model=LeadRead, summary="Detalhe do lead")
async def get_lead(lead_id: uuid.UUID, session: SessionDep, user: RequireViewer) -> LeadRead:
    """Retorna um lead da organização."""
    lead = await service.get_lead(session, organization_id=user.organization_id, lead_id=lead_id)
    return service.to_read(lead)


@router.patch("/{lead_id}", response_model=LeadRead, summary="Atualizar lead")
async def update_lead(
    lead_id: uuid.UUID,
    payload: LeadUpdate,
    session: SessionDep,
    user: RequireAnalyst,
    context: ContextDep,
) -> LeadRead:
    """Atualiza o lead e recalcula o score."""
    lead = await service.update_lead(
        session,
        organization_id=user.organization_id,
        lead_id=lead_id,
        payload=payload,
        actor=user,
        context=context,
    )
    return service.to_read(lead)


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Excluir lead")
async def delete_lead(
    lead_id: uuid.UUID, session: SessionDep, user: RequireAnalyst, context: ContextDep
) -> None:
    """Exclusão lógica do lead."""
    await service.delete_lead(
        session,
        organization_id=user.organization_id,
        lead_id=lead_id,
        actor=user,
        context=context,
    )


@router.post(
    "/{lead_id}/score",
    response_model=LeadScoreResponse,
    summary="Recalcular score por regras",
)
async def rescore_lead(
    lead_id: uuid.UUID, session: SessionDep, user: RequireAnalyst, context: ContextDep
) -> LeadScoreResponse:
    """Recalcula o score determinístico, retornando a justificativa completa."""
    lead, result = await service.rescore_lead(
        session,
        organization_id=user.organization_id,
        lead_id=lead_id,
        actor=user,
        context=context,
    )
    return LeadScoreResponse(
        lead_id=lead.id,
        score=result.score,
        category=result.category,
        method=ScoringMethod.RULES,
        version=result.version,
        reasons=[ScoreReasonRead.model_validate(reason) for reason in result.reasons],
        risks=result.risks,
        next_step=result.next_step,
        sources=["Regras determinísticas de score (rules-v1)", "Dados do lead no OpsPilot"],
    )


@router.get("/{lead_id}/events", response_model=list[LeadEventRead], summary="Histórico do lead")
async def lead_events(
    lead_id: uuid.UUID,
    session: SessionDep,
    user: RequireViewer,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[LeadEventRead]:
    """Lista os eventos do lead, mais recentes primeiro."""
    await service.get_lead(session, organization_id=user.organization_id, lead_id=lead_id)
    events = await service.list_events(
        session, organization_id=user.organization_id, lead_id=lead_id, limit=limit
    )
    return [LeadEventRead.model_validate(event) for event in events]


@router.post("/{lead_id}/notes", response_model=LeadRead, summary="Adicionar nota")
async def add_note(
    lead_id: uuid.UUID,
    payload: LeadNoteCreate,
    session: SessionDep,
    user: RequireAnalyst,
    context: ContextDep,
) -> LeadRead:
    """Registra uma nota no histórico e, opcionalmente, marca contato."""
    lead = await service.add_note(
        session,
        organization_id=user.organization_id,
        lead_id=lead_id,
        note=payload.note,
        mark_as_contacted=payload.mark_as_contacted,
        actor=user,
        context=context,
    )
    return service.to_read(lead)
