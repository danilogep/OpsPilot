"""Rotas de auditoria."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.deps import RequireViewer, SessionDep
from app.core.pagination import Page, PageParams, page_params
from app.db.models import AuditEvent
from app.domains.audit import service
from app.domains.audit.schemas import AuditActionSummary, AuditEventRead

router = APIRouter(prefix="/audit", tags=["Auditoria"])


@router.get("/events", response_model=Page[AuditEventRead], summary="Listar eventos")
async def list_events(
    session: SessionDep,
    user: RequireViewer,
    params: Annotated[PageParams, Depends(page_params)],
    action: Annotated[str | None, Query(description="Filtra por ação exata")] = None,
    entity_type: Annotated[str | None, Query(description="Filtra por tipo de entidade")] = None,
    entity_id: Annotated[str | None, Query(description="Filtra por id da entidade")] = None,
    actor_email: Annotated[str | None, Query(description="Busca parcial pelo ator")] = None,
    date_from: Annotated[datetime | None, Query(description="Início do período")] = None,
    date_to: Annotated[datetime | None, Query(description="Fim do período")] = None,
) -> Page[AuditEventRead]:
    """Lista eventos de auditoria da organização, mais recentes primeiro."""
    events, total = await service.list_audit_events(
        session,
        organization_id=user.organization_id,
        params=params,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_email=actor_email,
        date_from=date_from,
        date_to=date_to,
    )
    return Page.build([AuditEventRead.model_validate(event) for event in events], total, params)


@router.get(
    "/actions",
    response_model=list[AuditActionSummary],
    summary="Ações registradas e contagem",
)
async def list_actions(session: SessionDep, user: RequireViewer) -> list[AuditActionSummary]:
    """Lista as ações existentes com a contagem de eventos."""
    rows = (
        await session.execute(
            select(AuditEvent.action, func.count())
            .where(AuditEvent.organization_id == user.organization_id)
            .group_by(AuditEvent.action)
            .order_by(func.count().desc())
        )
    ).all()
    return [AuditActionSummary(action=row[0], total=int(row[1])) for row in rows]
