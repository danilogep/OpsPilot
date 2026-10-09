"""Execução de agentes.

Arquitetura **explícita e auditável**, em vez de um laço livre de chamadas de
ferramenta decidido pelo modelo:

1. o agente planeja as chamadas a partir da pergunta (determinístico, por
   intenção) e respeitando a allowlist da sua definição;
2. cada chamada é executada e observada, com limite máximo de passos;
3. o provider de IA recebe **apenas** as observações coletadas e redige a
   resposta final;
4. tudo fica registrado em ``agent_runs`` (entrada, ferramentas, passos,
   resultado, duração, status, erro e ``correlation_id``).

Esse desenho impede loop infinito, mantém o custo previsível e deixa claro de
onde veio cada número.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequestContext
from app.core.config import settings
from app.core.errors import NotFoundError, PermissionDeniedError
from app.core.errors import ValidationError as AppValidationError
from app.core.logging import get_correlation_id, get_logger
from app.db.base import utcnow
from app.db.models import AgentDefinition, AgentRun, AgentRunStatus, User
from app.domains.agents.tools import ToolContext, execute_tool
from app.domains.assistant.intents import Intent, detect_intent
from app.domains.audit import service as audit_service
from app.integrations.llm import prompts
from app.integrations.llm.base import LLMFeature, LLMMessage, LLMRequest
from app.integrations.llm.factory import get_provider
from app.integrations.llm.mock import NO_EVIDENCE_MESSAGE
from app.integrations.llm.runner import run_llm

logger = get_logger(__name__)

#: Agentes conhecidos e suas ferramentas padrão (espelha o seed).
DEFAULT_AGENTS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "DataAnalystAgent": (
        "Analista de dados",
        "Responde perguntas sobre clientes, renovações e indicadores da organização.",
        (
            "calculate_metrics",
            "list_customers",
            "search_customers",
            "get_customer",
            "list_renewals",
            "list_leads",
            "search_knowledge",
        ),
    ),
    "SalesAgent": (
        "Agente comercial",
        "Prioriza leads, explica o score e sugere próximos passos.",
        ("list_leads", "calculate_metrics", "search_knowledge", "create_lead_note"),
    ),
    "RenewalAgent": (
        "Agente de renovações",
        "Monta o panorama de renovações, clientes críticos e valor em risco.",
        (
            "list_renewals",
            "list_customers",
            "get_customer",
            "calculate_metrics",
            "search_knowledge",
        ),
    ),
}


@dataclass(slots=True)
class PlannedCall:
    """Chamada de ferramenta planejada pelo agente."""

    tool: str
    arguments: dict[str, Any]
    rationale: str


@dataclass(slots=True)
class ExecutedStep:
    """Passo executado, com entrada, saída e duração."""

    index: int
    tool: str
    arguments: dict[str, Any]
    rationale: str
    status: str
    duration_ms: int
    observation: dict[str, Any] | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "tool": self.tool,
            "arguments": self.arguments,
            "rationale": self.rationale,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "observation": self.observation,
            "error": self.error,
        }

    def summary(self) -> str:
        """Resumo curto da observação, usado no prompt final."""
        if self.error:
            return f"falhou: {self.error}"
        observation = self.observation or {}
        if "count" in observation:
            return f"{observation['count']} registro(s) de {observation.get('source', 'banco')}"
        if "scope" in observation:
            return f"indicadores do escopo “{observation['scope']}”"
        if observation.get("note_registered"):
            return f"nota registrada no lead {observation.get('lead_name')}"
        return "dados coletados"


@dataclass(slots=True)
class AgentResult:
    """Resultado completo de uma execução."""

    run_id: uuid.UUID
    agent_name: str
    status: AgentRunStatus
    answer: str
    has_evidence: bool
    steps: list[ExecutedStep] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: int = 0
    correlation_id: str = ""
    error: str | None = None
    trace: dict[str, Any] = field(default_factory=dict)


def plan_calls(agent_name: str, question: str, *, allowed: set[str]) -> list[PlannedCall]:
    """Planeja as chamadas de ferramenta conforme o agente e a pergunta."""
    intent = detect_intent(question)
    planned: list[PlannedCall] = []

    def add(tool: str, arguments: dict[str, Any], rationale: str) -> None:
        if tool in allowed and all(call.tool != tool for call in planned):
            planned.append(PlannedCall(tool=tool, arguments=arguments, rationale=rationale))

    if agent_name == "RenewalAgent":
        add("calculate_metrics", {"scope": "renewals"}, "Obter os indicadores de renovação.")
        add("list_renewals", {"within_days": 30, "limit": 10}, "Listar as renovações próximas.")
        add(
            "list_customers",
            {"status": "PAST_DUE", "limit": 10},
            "Identificar clientes com pagamento atrasado.",
        )
        add(
            "search_knowledge",
            {"query": "política de renovação e retenção", "limit": 2},
            "Checar a política interna de renovação.",
        )
    elif agent_name == "SalesAgent":
        add("calculate_metrics", {"scope": "leads"}, "Obter os indicadores de leads.")
        add(
            "list_leads",
            {"min_score": 0, "only_open": True, "limit": 10},
            "Listar os leads em aberto por prioridade.",
        )
        add(
            "search_knowledge",
            {"query": "playbook comercial de qualificação", "limit": 2},
            "Checar os critérios de qualificação do playbook.",
        )
    else:  # DataAnalystAgent
        scope_by_intent = {
            Intent.RENEWALS: "renewals",
            Intent.AMOUNT_AT_RISK: "renewals",
            Intent.TOP_LEADS: "leads",
            Intent.LEAD_FUNNEL: "leads",
            Intent.PLAN_CHURN: "plans",
            Intent.CUSTOMER_OVERVIEW: "customers",
            Intent.STALE_CUSTOMERS: "customers",
            Intent.IMPORT_STATUS: "imports",
        }
        scope = scope_by_intent.get(intent, "all")
        add("calculate_metrics", {"scope": scope}, f"Calcular indicadores ({scope}).")
        if intent in {Intent.RENEWALS, Intent.AMOUNT_AT_RISK}:
            add(
                "list_renewals",
                {"within_days": 30, "limit": 10},
                "Detalhar as renovações do período.",
            )
        if intent in {Intent.TOP_LEADS, Intent.LEAD_FUNNEL}:
            add("list_leads", {"only_open": True, "limit": 10}, "Detalhar os leads prioritários.")
        if intent in {Intent.CUSTOMER_OVERVIEW, Intent.STALE_CUSTOMERS}:
            add(
                "list_customers",
                {"limit": 10, "order_by": "monthly_value"},
                "Listar os clientes de maior receita.",
            )
        add(
            "search_knowledge",
            {"query": question, "limit": 3},
            "Procurar contexto nos documentos indexados.",
        )
    return planned


async def get_definition(
    session: AsyncSession, *, organization_id: uuid.UUID, agent_name: str
) -> AgentDefinition:
    """Carrega a definição do agente ou monta a padrão em memória."""
    result = await session.execute(
        select(AgentDefinition).where(
            AgentDefinition.organization_id == organization_id,
            AgentDefinition.key == agent_name,
            AgentDefinition.is_active.is_(True),
        )
    )
    definition: AgentDefinition | None = result.scalars().unique().first()
    if definition is not None:
        return definition
    if agent_name not in DEFAULT_AGENTS:
        raise NotFoundError("Agente não encontrado.", details={"available": sorted(DEFAULT_AGENTS)})
    name, description, tools = DEFAULT_AGENTS[agent_name]
    return AgentDefinition(
        organization_id=organization_id,
        key=agent_name,
        name=name,
        description=description,
        allowed_tools=list(tools),
        max_steps=settings.agent_max_steps,
        prompt_version="v1",
    )


async def run_agent(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    agent_name: str,
    question: str,
    actor: User,
    context: RequestContext | None = None,
) -> AgentResult:
    """Executa o agente com limite de passos e rastreamento completo."""
    definition = await get_definition(
        session, organization_id=organization_id, agent_name=agent_name
    )
    allowed = set(definition.allowed_tools)
    max_steps = max(1, min(definition.max_steps or settings.agent_max_steps, 12))
    correlation_id = (context.correlation_id if context else "") or get_correlation_id() or ""

    run = AgentRun(
        organization_id=organization_id,
        agent_name=agent_name,
        status=AgentRunStatus.RUNNING,
        input_payload={"question": question, "max_steps": max_steps},
        correlation_id=correlation_id,
        created_by_id=actor.id,
    )
    session.add(run)
    await session.flush()

    planned = plan_calls(agent_name, question, allowed=allowed)
    tool_context = ToolContext(session=session, organization_id=organization_id, actor=actor)
    steps: list[ExecutedStep] = []
    started = time.perf_counter()
    hit_limit = False

    for index, call in enumerate(planned, start=1):
        if index > max_steps:
            hit_limit = True
            logger.warning("agent_max_steps_reached", agent=agent_name, max_steps=max_steps)
            break
        step_started = time.perf_counter()
        try:
            observation = await execute_tool(
                call.tool, call.arguments, context=tool_context, allowed_tools=allowed
            )
            steps.append(
                ExecutedStep(
                    index=index,
                    tool=call.tool,
                    arguments=call.arguments,
                    rationale=call.rationale,
                    status="ok",
                    duration_ms=int((time.perf_counter() - step_started) * 1000),
                    observation=observation,
                )
            )
        except (PermissionDeniedError, AppValidationError) as exc:
            steps.append(
                ExecutedStep(
                    index=index,
                    tool=call.tool,
                    arguments=call.arguments,
                    rationale=call.rationale,
                    status="error",
                    duration_ms=int((time.perf_counter() - step_started) * 1000),
                    error=exc.message,
                )
            )

    successful = [step for step in steps if step.status == "ok"]
    sources = _collect_sources(successful)

    if not successful:
        duration_ms = int((time.perf_counter() - started) * 1000)
        run.status = AgentRunStatus.ERROR if steps else AgentRunStatus.PARTIAL
        run.steps = [step.as_dict() for step in steps]
        run.tools_used = [step.tool for step in steps]
        run.duration_ms = duration_ms
        run.error = "Nenhuma ferramenta retornou dados."
        run.result = {"answer": NO_EVIDENCE_MESSAGE, "has_evidence": False}
        await session.commit()
        return AgentResult(
            run_id=run.id,
            agent_name=agent_name,
            status=run.status,
            answer=NO_EVIDENCE_MESSAGE,
            has_evidence=False,
            steps=steps,
            tools_used=run.tools_used,
            duration_ms=duration_ms,
            correlation_id=correlation_id,
            error=run.error,
            trace={"planned": len(planned), "executed": len(steps), "llm_called": False},
        )

    request = LLMRequest(
        feature=LLMFeature.AGENT,
        system=definition.system_prompt or prompts.AGENT_SYSTEM,
        prompt_version=f"{prompts.AGENT_VERSION}+{definition.prompt_version}",
        messages=[LLMMessage(role="user", content=question)],
        max_output_tokens=settings.llm_max_output_tokens,
        context={
            "agent": agent_name,
            "question": question,
            "observations": [
                {
                    "tool": step.tool,
                    "summary": step.summary(),
                    "data": step.observation,
                }
                for step in successful
            ],
            "conclusion": (
                "Use apenas os números das observações acima e cite a ferramenta de origem."
            ),
        },
    )
    execution = await run_llm(
        session,
        organization_id=organization_id,
        request=request,
        actor=actor,
        agent_run_id=run.id,
        provider=get_provider(),
    )

    duration_ms = int((time.perf_counter() - started) * 1000)
    status = (
        AgentRunStatus.MAX_STEPS
        if hit_limit
        else (AgentRunStatus.PARTIAL if len(successful) < len(steps) else AgentRunStatus.SUCCESS)
    )
    run.status = status
    run.steps = [step.as_dict() for step in steps]
    run.tools_used = [step.tool for step in steps]
    run.duration_ms = duration_ms
    run.result = {
        "answer": execution.text,
        "has_evidence": True,
        "sources": sources,
        "trace": execution.trace(),
    }

    await audit_service.record_audit(
        session,
        organization_id=organization_id,
        action=audit_service.ACTION_AI_AGENT_RUN,
        entity_type="agent_run",
        entity_id=str(run.id),
        actor=actor,
        summary=f"Agente {agent_name} executado com {len(successful)} ferramenta(s).",
        meta={
            "agent": agent_name,
            "tools_used": run.tools_used,
            "status": status.value,
            "duration_ms": duration_ms,
        },
        context=context,
    )
    await session.commit()
    logger.info(
        "agent_run",
        agent=agent_name,
        status=status.value,
        steps=len(steps),
        duration_ms=duration_ms,
    )

    return AgentResult(
        run_id=run.id,
        agent_name=agent_name,
        status=status,
        answer=execution.text,
        has_evidence=True,
        steps=steps,
        tools_used=run.tools_used,
        sources=sources,
        duration_ms=duration_ms,
        correlation_id=correlation_id,
        trace={
            **execution.trace(),
            "planned": len(planned),
            "executed": len(steps),
            "max_steps": max_steps,
            "llm_called": True,
        },
    )


def _collect_sources(steps: list[ExecutedStep]) -> list[dict[str, Any]]:
    """Fontes citáveis a partir das observações das ferramentas."""
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for step in steps:
        observation = step.observation or {}
        label = str(observation.get("source") or step.tool)
        key = f"{step.tool}:{label}"
        if key not in seen:
            seen.add(key)
            sources.append({"type": "tool", "title": label, "locator": step.tool})
        for passage in observation.get("passages", []) or []:
            identifier = str(passage.get("document_id"))
            if identifier not in seen:
                seen.add(identifier)
                sources.append(passage)
    return sources


def agent_catalog() -> list[dict[str, Any]]:
    """Catálogo dos agentes padrão, para a interface."""
    return [
        {
            "key": key,
            "name": name,
            "description": description,
            "allowed_tools": list(tools),
            "max_steps": settings.agent_max_steps,
        }
        for key, (name, description, tools) in DEFAULT_AGENTS.items()
    ]


def utc_now_iso() -> str:
    """Horário atual em ISO (usado nas respostas)."""
    return utcnow().isoformat()
