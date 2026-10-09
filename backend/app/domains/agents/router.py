"""Rotas de agentes e ferramentas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.api.deps import ContextDep, RequireViewer, SessionDep
from app.core.errors import NotFoundError
from app.core.pagination import Page, PageParams, page_params
from app.db.models import AgentRun, AgentRunStatus
from app.domains.agents import runtime
from app.domains.agents.tools import describe_tools

router = APIRouter(prefix="/agents", tags=["Agentes"])


class AgentInfo(BaseModel):
    """Agente disponível."""

    key: str
    name: str
    description: str
    allowed_tools: list[str]
    max_steps: int


class AgentRunRequest(BaseModel):
    """Pedido de execução de agente."""

    question: str = Field(min_length=5, max_length=500)


class AgentStepRead(BaseModel):
    """Passo executado pelo agente."""

    index: int
    tool: str
    arguments: dict[str, Any]
    rationale: str
    status: str
    duration_ms: int
    observation: dict[str, Any] | None = None
    error: str | None = None


class AgentRunResponse(BaseModel):
    """Resultado de uma execução de agente."""

    run_id: uuid.UUID
    agent_name: str
    status: AgentRunStatus
    answer: str
    has_evidence: bool
    tools_used: list[str]
    steps: list[AgentStepRead]
    sources: list[dict[str, Any]]
    duration_ms: int
    correlation_id: str
    error: str | None = None
    trace: dict[str, Any]


class AgentRunRead(BaseModel):
    """Execução registrada."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_name: str
    status: AgentRunStatus
    input_payload: dict[str, Any]
    tools_used: list[str]
    steps: list[dict[str, Any]]
    result: dict[str, Any]
    duration_ms: int
    error: str | None
    correlation_id: str
    created_at: datetime


@router.get("", response_model=list[AgentInfo], summary="Agentes disponíveis")
async def list_agents(_user: RequireViewer) -> list[AgentInfo]:
    """Lista os agentes e as ferramentas que cada um pode usar."""
    return [AgentInfo.model_validate(item) for item in runtime.agent_catalog()]


@router.get("/tools", response_model=list[dict[str, Any]], summary="Ferramentas registradas")
async def list_tools(_user: RequireViewer) -> list[dict[str, Any]]:
    """Catálogo do ToolRegistry, com parâmetros e permissões."""
    return describe_tools()


@router.get("/runs", response_model=Page[AgentRunRead], summary="Execuções registradas")
async def list_runs(
    session: SessionDep,
    user: RequireViewer,
    params: Annotated[PageParams, Depends(page_params)],
    agent_name: Annotated[str | None, Query(description="Filtra por agente")] = None,
) -> Page[AgentRunRead]:
    """Lista as execuções de agentes, mais recentes primeiro."""
    base = select(AgentRun).where(AgentRun.organization_id == user.organization_id)
    if agent_name:
        base = base.where(AgentRun.agent_name == agent_name)
    total = int(
        (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    )
    rows = (
        (
            await session.execute(
                base.order_by(AgentRun.created_at.desc())
                .offset(params.offset)
                .limit(params.page_size)
            )
        )
        .scalars()
        .unique()
        .all()
    )
    return Page.build([AgentRunRead.model_validate(row) for row in rows], total, params)


@router.get("/runs/{run_id}", response_model=AgentRunRead, summary="Detalhe da execução")
async def get_run(run_id: uuid.UUID, session: SessionDep, user: RequireViewer) -> AgentRunRead:
    """Retorna o rastro completo de uma execução."""
    result = await session.execute(
        select(AgentRun).where(
            AgentRun.id == run_id, AgentRun.organization_id == user.organization_id
        )
    )
    run: AgentRun | None = result.scalars().unique().first()
    if run is None:
        raise NotFoundError("Execução não encontrada.")
    return AgentRunRead.model_validate(run)


@router.post("/{agent_name}/run", response_model=AgentRunResponse, summary="Executar um agente")
async def run_agent(
    agent_name: str,
    payload: AgentRunRequest,
    session: SessionDep,
    user: RequireViewer,
    context: ContextDep,
) -> AgentRunResponse:
    """Executa o agente com limite de passos e devolve o rastro das ferramentas."""
    result = await runtime.run_agent(
        session,
        organization_id=user.organization_id,
        agent_name=agent_name,
        question=payload.question,
        actor=user,
        context=context,
    )
    return AgentRunResponse(
        run_id=result.run_id,
        agent_name=result.agent_name,
        status=result.status,
        answer=result.answer,
        has_evidence=result.has_evidence,
        tools_used=result.tools_used,
        steps=[AgentStepRead.model_validate(step.as_dict()) for step in result.steps],
        sources=result.sources,
        duration_ms=result.duration_ms,
        correlation_id=result.correlation_id,
        error=result.error,
        trace=result.trace,
    )
