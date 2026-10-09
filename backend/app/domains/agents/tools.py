"""Registro de ferramentas disponíveis para os agentes.

Princípios:

* **allowlist explícita**: um agente só executa ferramentas declaradas na sua
  definição; qualquer outra chamada é recusada e registrada;
* **escopo de organização obrigatório**: toda ferramenta recebe o
  ``organization_id`` do usuário autenticado e nunca aceita esse valor como
  parâmetro de entrada;
* **parâmetros validados** por Pydantic antes da execução;
* **somente leitura por padrão**: a única ferramenta de escrita
  (``create_lead_note``) exige perfil ANALYST ou ADMIN.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import UnaryExpression

from app.core.errors import PermissionDeniedError
from app.core.errors import ValidationError as AppValidationError
from app.db.base import utcnow
from app.db.models import (
    Customer,
    CustomerStatus,
    Lead,
    LeadStatus,
    Renewal,
    RenewalStatus,
    User,
    UserRole,
)
from app.domains.knowledge import service as knowledge_service
from app.domains.leads import service as leads_service
from app.domains.organizations import metrics

MAX_TOOL_ROWS = 25


# ----------------------------------------------------------- parâmetros -------


class ListCustomersParams(BaseModel):
    """Parâmetros de ``list_customers``."""

    status: CustomerStatus | None = None
    limit: int = Field(default=10, ge=1, le=MAX_TOOL_ROWS)
    order_by: str = Field(default="monthly_value", pattern="^(monthly_value|name|renewal_date)$")


class SearchCustomersParams(BaseModel):
    """Parâmetros de ``search_customers``."""

    query: str = Field(min_length=2, max_length=120)
    limit: int = Field(default=10, ge=1, le=MAX_TOOL_ROWS)


class GetCustomerParams(BaseModel):
    """Parâmetros de ``get_customer``."""

    customer_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=2, max_length=120)


class ListRenewalsParams(BaseModel):
    """Parâmetros de ``list_renewals``."""

    within_days: int = Field(default=30, ge=1, le=365)
    include_overdue: bool = True
    limit: int = Field(default=10, ge=1, le=MAX_TOOL_ROWS)


class ListLeadsParams(BaseModel):
    """Parâmetros de ``list_leads``."""

    min_score: int = Field(default=0, ge=0, le=100)
    only_open: bool = True
    limit: int = Field(default=10, ge=1, le=MAX_TOOL_ROWS)


class CalculateMetricsParams(BaseModel):
    """Parâmetros de ``calculate_metrics``."""

    scope: str = Field(default="all", pattern="^(all|customers|renewals|leads|plans|imports)$")


class SearchKnowledgeParams(BaseModel):
    """Parâmetros de ``search_knowledge``."""

    query: str = Field(min_length=3, max_length=200)
    limit: int = Field(default=3, ge=1, le=10)


class CreateLeadNoteParams(BaseModel):
    """Parâmetros de ``create_lead_note``."""

    lead_id: uuid.UUID
    note: str = Field(min_length=3, max_length=500)
    mark_as_contacted: bool = False


# ------------------------------------------------------------- execução -------


@dataclass(slots=True)
class ToolContext:
    """Contexto de execução de uma ferramenta."""

    session: AsyncSession
    organization_id: uuid.UUID
    actor: User


ToolHandler = Callable[[ToolContext, BaseModel], Awaitable[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Metadados e implementação de uma ferramenta."""

    name: str
    description: str
    params_model: type[BaseModel]
    handler: ToolHandler
    read_only: bool = True
    allowed_roles: tuple[UserRole, ...] = (UserRole.ADMIN, UserRole.ANALYST, UserRole.VIEWER)

    def schema(self) -> dict[str, Any]:
        """Esquema JSON dos parâmetros, para documentação e interface."""
        return {
            "name": self.name,
            "description": self.description,
            "read_only": self.read_only,
            "allowed_roles": [role.value for role in self.allowed_roles],
            "parameters": self.params_model.model_json_schema(),
        }


async def _list_customers(context: ToolContext, params: BaseModel) -> dict[str, Any]:
    """Clientes da organização, ordenados pelo campo escolhido."""
    assert isinstance(params, ListCustomersParams)
    columns: dict[str, UnaryExpression[Any]] = {
        "monthly_value": Customer.monthly_value.desc(),
        "name": Customer.name.asc(),
        "renewal_date": Customer.renewal_date.asc(),
    }
    stmt = select(Customer).where(
        Customer.organization_id == context.organization_id, Customer.deleted_at.is_(None)
    )
    if params.status is not None:
        stmt = stmt.where(Customer.status == params.status)
    rows = (
        (await context.session.execute(stmt.order_by(columns[params.order_by]).limit(params.limit)))
        .scalars()
        .unique()
        .all()
    )
    return {
        "count": len(rows),
        "customers": [
            {
                "id": str(customer.id),
                "name": customer.name,
                "status": customer.status.value,
                "monthly_value": str(customer.monthly_value),
                "renewal_date": (
                    customer.renewal_date.isoformat() if customer.renewal_date else None
                ),
                "plan": customer.plan.name if customer.plan else None,
            }
            for customer in rows
        ],
        "source": "tabela customers",
    }


async def _search_customers(context: ToolContext, params: BaseModel) -> dict[str, Any]:
    """Busca clientes por nome, e-mail ou documento."""
    assert isinstance(params, SearchCustomersParams)
    term = f"%{params.query.strip()}%"
    rows = (
        (
            await context.session.execute(
                select(Customer)
                .where(
                    Customer.organization_id == context.organization_id,
                    Customer.deleted_at.is_(None),
                    or_(
                        Customer.name.ilike(term),
                        Customer.email.ilike(term),
                        Customer.document.ilike(term),
                    ),
                )
                .order_by(Customer.name)
                .limit(params.limit)
            )
        )
        .scalars()
        .unique()
        .all()
    )
    return {
        "query": params.query,
        "count": len(rows),
        "customers": [
            {
                "id": str(customer.id),
                "name": customer.name,
                "email": customer.email,
                "status": customer.status.value,
                "monthly_value": str(customer.monthly_value),
            }
            for customer in rows
        ],
        "source": "tabela customers",
    }


async def _get_customer(context: ToolContext, params: BaseModel) -> dict[str, Any]:
    """Detalha um cliente por id ou nome."""
    assert isinstance(params, GetCustomerParams)
    if params.customer_id is None and not params.name:
        raise AppValidationError("Informe o id ou o nome do cliente.")
    stmt = select(Customer).where(
        Customer.organization_id == context.organization_id, Customer.deleted_at.is_(None)
    )
    if params.customer_id is not None:
        stmt = stmt.where(Customer.id == params.customer_id)
    else:
        stmt = stmt.where(Customer.name.ilike(f"%{params.name}%"))
    customer = (await context.session.execute(stmt.limit(1))).scalars().unique().first()
    if customer is None:
        return {"found": False, "source": "tabela customers"}
    return {
        "found": True,
        "customer": {
            "id": str(customer.id),
            "name": customer.name,
            "email": customer.email,
            "phone": customer.phone,
            "status": customer.status.value,
            "plan": customer.plan.name if customer.plan else None,
            "monthly_value": str(customer.monthly_value),
            "start_date": customer.start_date.isoformat() if customer.start_date else None,
            "renewal_date": (customer.renewal_date.isoformat() if customer.renewal_date else None),
            "last_contact_at": (
                customer.last_contact_at.isoformat() if customer.last_contact_at else None
            ),
        },
        "source": "tabela customers",
    }


async def _list_renewals(context: ToolContext, params: BaseModel) -> dict[str, Any]:
    """Renovações em aberto na janela informada."""
    assert isinstance(params, ListRenewalsParams)
    today = utcnow().date()
    stmt = (
        select(Renewal, Customer.name)
        .join(Customer, Renewal.customer_id == Customer.id)
        .where(
            Renewal.organization_id == context.organization_id,
            Customer.deleted_at.is_(None),
            Renewal.status.in_([RenewalStatus.SCHEDULED, RenewalStatus.AT_RISK]),
            Renewal.due_date <= today + timedelta(days=params.within_days),
        )
    )
    if not params.include_overdue:
        stmt = stmt.where(Renewal.due_date >= today)
    rows = (
        (await context.session.execute(stmt.order_by(Renewal.due_date).limit(params.limit)))
        .unique()
        .all()
    )
    total_amount = sum((renewal.amount for renewal, _ in rows), Decimal("0.00"))
    return {
        "window_days": params.within_days,
        "reference_date": today.isoformat(),
        "count": len(rows),
        "total_amount": str(total_amount),
        "renewals": [
            {
                "customer_name": name,
                "due_date": renewal.due_date.isoformat(),
                "days_until_due": (renewal.due_date - today).days,
                "amount": str(renewal.amount),
                "status": renewal.status.value,
            }
            for renewal, name in rows
        ],
        "source": "tabela renewals",
    }


async def _list_leads(context: ToolContext, params: BaseModel) -> dict[str, Any]:
    """Leads ordenados por score."""
    assert isinstance(params, ListLeadsParams)
    stmt = select(Lead).where(
        Lead.organization_id == context.organization_id,
        Lead.deleted_at.is_(None),
        Lead.score >= params.min_score,
    )
    if params.only_open:
        stmt = stmt.where(
            Lead.status.in_(
                [LeadStatus.NEW, LeadStatus.CONTACTED, LeadStatus.QUALIFIED, LeadStatus.PROPOSAL]
            )
        )
    rows = (
        (
            await context.session.execute(
                stmt.order_by(Lead.score.desc(), Lead.estimated_value.desc()).limit(params.limit)
            )
        )
        .scalars()
        .all()
    )
    return {
        "count": len(rows),
        "leads": [
            {
                "id": str(lead.id),
                "name": lead.name,
                "company": lead.company,
                "score": lead.score,
                "category": lead.score_category.value,
                "status": lead.status.value,
                "estimated_value": str(lead.estimated_value),
                "next_step": lead.next_step,
            }
            for lead in rows
        ],
        "source": "tabela leads",
    }


async def _calculate_metrics(context: ToolContext, params: BaseModel) -> dict[str, Any]:
    """Indicadores agregados do escopo pedido."""
    assert isinstance(params, CalculateMetricsParams)
    scope = params.scope
    data: dict[str, Any]
    if scope == "customers":
        data = {
            "customers": await metrics.customer_overview(
                context.session, organization_id=context.organization_id
            )
        }
    elif scope == "renewals":
        data = {
            "renewals": await metrics.renewal_overview(
                context.session, organization_id=context.organization_id
            )
        }
    elif scope == "leads":
        data = {
            "leads": await metrics.lead_overview(
                context.session, organization_id=context.organization_id
            )
        }
    elif scope == "plans":
        data = {
            "plans": await metrics.plan_ranking(
                context.session, organization_id=context.organization_id
            )
        }
    elif scope == "imports":
        data = {
            "imports": await metrics.import_overview(
                context.session, organization_id=context.organization_id
            )
        }
    else:
        data = await metrics.metrics_for_ai(
            context.session, organization_id=context.organization_id
        )
    return {"scope": scope, **data, "source": "consultas agregadas do banco"}


async def _search_knowledge(context: ToolContext, params: BaseModel) -> dict[str, Any]:
    """Busca trechos na base de conhecimento."""
    assert isinstance(params, SearchKnowledgeParams)
    hits = await knowledge_service.search(
        context.session,
        organization_id=context.organization_id,
        query=params.query,
        limit=params.limit,
    )
    return {
        "query": params.query,
        "count": len(hits),
        "passages": [hit.as_source() for hit in hits],
        "engine": knowledge_service.search_engine_name(context.session),
        "source": "base de conhecimento",
    }


async def _create_lead_note(context: ToolContext, params: BaseModel) -> dict[str, Any]:
    """Registra uma nota no histórico de um lead (única ferramenta de escrita)."""
    assert isinstance(params, CreateLeadNoteParams)
    lead = await leads_service.add_note(
        context.session,
        organization_id=context.organization_id,
        lead_id=params.lead_id,
        note=params.note,
        mark_as_contacted=params.mark_as_contacted,
        actor=context.actor,
    )
    return {
        "lead_id": str(lead.id),
        "lead_name": lead.name,
        "note_registered": True,
        "marked_as_contacted": params.mark_as_contacted,
        "source": "tabela lead_events",
    }


TOOL_REGISTRY: dict[str, ToolDefinition] = {
    "list_customers": ToolDefinition(
        name="list_customers",
        description=(
            "Lista clientes da organização por situação, ordenados por valor, "
            "nome ou data de renovação."
        ),
        params_model=ListCustomersParams,
        handler=_list_customers,
    ),
    "search_customers": ToolDefinition(
        name="search_customers",
        description="Busca clientes por nome, e-mail ou documento.",
        params_model=SearchCustomersParams,
        handler=_search_customers,
    ),
    "get_customer": ToolDefinition(
        name="get_customer",
        description="Detalha um cliente específico por id ou nome.",
        params_model=GetCustomerParams,
        handler=_get_customer,
    ),
    "list_renewals": ToolDefinition(
        name="list_renewals",
        description="Lista renovações em aberto dentro de uma janela de dias, incluindo vencidas.",
        params_model=ListRenewalsParams,
        handler=_list_renewals,
    ),
    "list_leads": ToolDefinition(
        name="list_leads",
        description="Lista leads por score mínimo, priorizando os de maior pontuação.",
        params_model=ListLeadsParams,
        handler=_list_leads,
    ),
    "calculate_metrics": ToolDefinition(
        name="calculate_metrics",
        description=(
            "Calcula indicadores agregados de clientes, renovações, leads, planos ou importações."
        ),
        params_model=CalculateMetricsParams,
        handler=_calculate_metrics,
    ),
    "search_knowledge": ToolDefinition(
        name="search_knowledge",
        description="Busca trechos relevantes nos documentos da base de conhecimento.",
        params_model=SearchKnowledgeParams,
        handler=_search_knowledge,
    ),
    "create_lead_note": ToolDefinition(
        name="create_lead_note",
        description="Registra uma nota no histórico de um lead. Única ferramenta de escrita.",
        params_model=CreateLeadNoteParams,
        handler=_create_lead_note,
        read_only=False,
        allowed_roles=(UserRole.ADMIN, UserRole.ANALYST),
    ),
}


def get_tool(name: str) -> ToolDefinition:
    """Busca a ferramenta pelo nome, recusando nomes desconhecidos."""
    tool = TOOL_REGISTRY.get(name)
    if tool is None:
        raise AppValidationError(
            f"Ferramenta “{name}” não existe.", details={"available": sorted(TOOL_REGISTRY)}
        )
    return tool


async def execute_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    context: ToolContext,
    allowed_tools: set[str],
) -> dict[str, Any]:
    """Valida permissão e parâmetros e executa a ferramenta."""
    if name not in allowed_tools:
        raise PermissionDeniedError(
            f"A ferramenta “{name}” não está autorizada para este agente.",
            details={"allowed": sorted(allowed_tools)},
        )
    tool = get_tool(name)
    if context.actor.role not in tool.allowed_roles:
        raise PermissionDeniedError(
            f"Seu perfil não permite usar a ferramenta “{name}”.",
            details={"required_roles": [role.value for role in tool.allowed_roles]},
        )
    try:
        params = tool.params_model.model_validate(arguments)
    except ValidationError as exc:
        raise AppValidationError(
            f"Parâmetros inválidos para “{name}”.",
            details={"errors": [error["msg"] for error in exc.errors()][:5]},
        ) from exc
    return await tool.handler(context, params)


def describe_tools(names: list[str] | None = None) -> list[dict[str, Any]]:
    """Catálogo das ferramentas (todas ou um subconjunto)."""
    selected = names or sorted(TOOL_REGISTRY)
    return [TOOL_REGISTRY[name].schema() for name in selected if name in TOOL_REGISTRY]
