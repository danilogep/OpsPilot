"""Rotas de planos."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import ContextDep, RequireAnalyst, RequireViewer, SessionDep
from app.domains.customers.schemas import PlanCreate, PlanRead, PlanUpdate, PlanWithMetrics
from app.domains.plans import service

router = APIRouter(prefix="/plans", tags=["Planos"])


@router.get("", response_model=list[PlanWithMetrics], summary="Listar planos")
async def list_plans(
    session: SessionDep,
    user: RequireViewer,
    include_inactive: Annotated[bool, Query(description="Inclui planos inativos")] = True,
) -> list[PlanWithMetrics]:
    """Lista planos com clientes, receita mensal e taxa de cancelamento."""
    return await service.list_plans(
        session, organization_id=user.organization_id, include_inactive=include_inactive
    )


@router.post(
    "", response_model=PlanRead, status_code=status.HTTP_201_CREATED, summary="Criar plano"
)
async def create_plan(
    payload: PlanCreate, session: SessionDep, user: RequireAnalyst, context: ContextDep
) -> PlanRead:
    """Cria um plano na organização."""
    plan = await service.create_plan(
        session,
        organization_id=user.organization_id,
        payload=payload,
        actor=user,
        context=context,
    )
    return PlanRead.model_validate(plan)


@router.get("/{plan_id}", response_model=PlanRead, summary="Detalhe do plano")
async def get_plan(plan_id: uuid.UUID, session: SessionDep, user: RequireViewer) -> PlanRead:
    """Retorna um plano da organização."""
    plan = await service.get_plan(session, organization_id=user.organization_id, plan_id=plan_id)
    return PlanRead.model_validate(plan)


@router.patch("/{plan_id}", response_model=PlanRead, summary="Atualizar plano")
async def update_plan(
    plan_id: uuid.UUID,
    payload: PlanUpdate,
    session: SessionDep,
    user: RequireAnalyst,
    context: ContextDep,
) -> PlanRead:
    """Atualiza um plano."""
    plan = await service.update_plan(
        session,
        organization_id=user.organization_id,
        plan_id=plan_id,
        payload=payload,
        actor=user,
        context=context,
    )
    return PlanRead.model_validate(plan)


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Excluir plano")
async def delete_plan(
    plan_id: uuid.UUID, session: SessionDep, user: RequireAnalyst, context: ContextDep
) -> None:
    """Exclusão lógica do plano (bloqueada se houver clientes vinculados)."""
    await service.delete_plan(
        session,
        organization_id=user.organization_id,
        plan_id=plan_id,
        actor=user,
        context=context,
    )
