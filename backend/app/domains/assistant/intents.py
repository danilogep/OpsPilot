"""Detecção de intenção e coleta de fatos para o assistente de dados.

O assistente **não** deixa o modelo escolher números: a intenção é detectada por
palavras-chave (determinístico e auditável), os fatos são consultados no banco e
só então o provider de IA é usado para redigir a resposta em cima desses fatos.

Cada fato carrega a fonte (indicador/consulta) que o originou, para o campo
``sources`` da resposta.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.db.models import (
    Customer,
    CustomerStatus,
    ImportJob,
    Lead,
    Renewal,
    RenewalStatus,
)
from app.domains.imports.normalizers import strip_accents
from app.domains.leads.service import HIGH_PRIORITY_SCORE
from app.domains.leads.service import OPEN_STATUSES as OPEN_LEAD_STATUSES
from app.domains.organizations import metrics
from app.domains.renewals.service import CONTACT_THRESHOLD_DAYS
from app.domains.renewals.service import OPEN_STATUSES as OPEN_RENEWALS


class Intent(StrEnum):
    """Intenções reconhecidas pelo assistente."""

    RENEWALS = "renewals"
    AMOUNT_AT_RISK = "amount_at_risk"
    TOP_LEADS = "top_leads"
    PLAN_CHURN = "plan_churn"
    STALE_CUSTOMERS = "stale_customers"
    CUSTOMER_OVERVIEW = "customer_overview"
    LEAD_FUNNEL = "lead_funnel"
    IMPORT_STATUS = "import_status"
    POLICY = "policy"
    UNKNOWN = "unknown"


INTENT_LABELS: dict[Intent, str] = {
    Intent.RENEWALS: "Renovações por período",
    Intent.AMOUNT_AT_RISK: "Valor mensal em risco",
    Intent.TOP_LEADS: "Leads prioritários",
    Intent.PLAN_CHURN: "Cancelamento por plano",
    Intent.STALE_CUSTOMERS: "Clientes sem contato recente",
    Intent.CUSTOMER_OVERVIEW: "Panorama de clientes e receita",
    Intent.LEAD_FUNNEL: "Funil de leads",
    Intent.IMPORT_STATUS: "Situação das importações",
    Intent.POLICY: "Consulta à base de conhecimento",
    Intent.UNKNOWN: "Intenção não identificada",
}

#: Palavras-chave por intenção, **na ordem de especificidade**: a primeira
#: intenção com qualquer palavra-chave presente na pergunta vence. A ordem
#: importa porque perguntas reais combinam termos: "prazo de aviso prévio para
#: cancelamento" é política (documento), enquanto "quais planos apresentam maior
#: cancelamento" é indicador (banco).
INTENT_KEYWORDS: tuple[tuple[Intent, tuple[str, ...]], ...] = (
    (
        Intent.AMOUNT_AT_RISK,
        ("valor em risco", "receita em risco", "valor mensal em risco", "quanto posso perder"),
    ),
    (
        Intent.POLICY,
        (
            "politica",
            "prazo",
            "regra",
            "como funciona",
            "procedimento",
            "sla",
            "desconto",
            "multa",
            "aviso previo",
            "cobranca",
            "onboarding",
            "manual",
            "documento",
            "playbook",
        ),
    ),
    (
        Intent.RENEWALS,
        (
            "renova",
            "renovacao",
            "renovacoes",
            "vencimento",
            "vence",
            "vencendo",
            "a vencer",
        ),
    ),
    (
        Intent.STALE_CUSTOMERS,
        (
            "sem contato",
            "nao tiveram contato",
            "contato recente",
            "ultimo contato",
            "abandonado",
            "esquecido",
        ),
    ),
    (
        Intent.PLAN_CHURN,
        ("cancelamento", "cancelaram", "churn", "cancelado", "cancelados", "cancelou"),
    ),
    (
        Intent.TOP_LEADS,
        ("lead", "leads", "prioridade", "prioritario", "prioritarios", "score", "quente"),
    ),
    (Intent.LEAD_FUNNEL, ("funil", "pipeline", "estagio", "conversao")),
    (
        Intent.IMPORT_STATUS,
        ("importacao", "importacoes", "planilha", "upload", "linhas invalidas", "linhas com erro"),
    ),
    (
        Intent.CUSTOMER_OVERVIEW,
        (
            "quantos clientes",
            "total de clientes",
            "receita",
            "faturamento",
            "mrr",
            "ticket medio",
            "base de clientes",
            "clientes ativos",
            "clientes atrasados",
        ),
    ),
)


@dataclass(slots=True)
class Fact:
    """Número ou texto verificável usado na resposta."""

    label: str
    value: Any
    kind: str = "text"  # text | count | money | date | percent
    source: str = "banco de dados"

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "value": str(self.value) if isinstance(self.value, Decimal) else self.value,
            "kind": self.kind,
            "source": self.source,
        }


@dataclass(slots=True)
class ResolvedContext:
    """Resultado da coleta de fatos para uma intenção."""

    intent: Intent
    headline: str
    facts: list[Fact] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)
    recommendation: str | None = None
    tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    needs_knowledge: bool = False

    @property
    def has_facts(self) -> bool:
        return bool(self.facts) or any(self.tables.values())


def detect_intent(question: str) -> Intent:
    """Classifica a pergunta por palavras-chave, de forma determinística.

    Percorre as intenções na ordem de especificidade e devolve a primeira cujo
    vocabulário aparece na pergunta. Sem correspondência, devolve
    :attr:`Intent.UNKNOWN`, que recai na base de conhecimento.
    """
    normalized = strip_accents(question.lower())
    for intent, keywords in INTENT_KEYWORDS:
        if any(keyword in normalized for keyword in keywords):
            return intent
    return Intent.UNKNOWN


def _window_from_question(question: str) -> tuple[int, str]:
    """Extrai a janela de dias mencionada na pergunta (padrão: 30 dias)."""
    normalized = strip_accents(question.lower())
    if "7 dias" in normalized or "sete dias" in normalized or "semana" in normalized:
        return 7, "próximos 7 dias"
    if "60 dias" in normalized:
        return 60, "próximos 60 dias"
    if "90 dias" in normalized or "trimestre" in normalized:
        return 90, "próximos 90 dias"
    if "15 dias" in normalized or "quinze dias" in normalized:
        return 15, "próximos 15 dias"
    return 30, "próximos 30 dias"


async def _resolve_renewals(
    session: AsyncSession, *, organization_id: uuid.UUID, question: str
) -> ResolvedContext:
    """Renovações em uma janela de dias, com a lista dos clientes."""
    days, label = _window_from_question(question)
    today = utcnow().date()
    limit_date = today + timedelta(days=days)

    rows = (
        (
            await session.execute(
                select(Renewal, Customer.name)
                .join(Customer, Renewal.customer_id == Customer.id)
                .where(
                    Renewal.organization_id == organization_id,
                    Customer.deleted_at.is_(None),
                    Renewal.status.in_(OPEN_RENEWALS),
                    Renewal.due_date >= today,
                    Renewal.due_date <= limit_date,
                )
                .order_by(Renewal.due_date)
                .limit(25)
            )
        )
        .unique()
        .all()
    )
    total = len(rows)
    amount = sum((row[0].amount for row in rows), Decimal("0.00"))
    indicators = await metrics.renewal_overview(session, organization_id=organization_id)

    context = ResolvedContext(
        intent=Intent.RENEWALS,
        headline=f"Renovações previstas para os {label}.",
        facts=[
            Fact(f"Renovações nos {label}", total, "count", "tabela renewals"),
            Fact(f"Valor total nos {label}", amount, "money", "tabela renewals"),
            Fact(
                "Renovações vencidas em aberto", indicators["overdue"], "count", "tabela renewals"
            ),
            Fact("Data de referência", today.isoformat(), "date", "data do servidor"),
        ],
        reasoning=[
            f"Filtrei renovações com situação agendada ou em risco e vencimento entre "
            f"{today:%d/%m/%Y} e {limit_date:%d/%m/%Y}.",
            f"Contei {total} registro(s) e somei o valor de cada renovação.",
        ],
        tables={
            "renewals": [
                {
                    "customer_name": name,
                    "due_date": renewal.due_date.isoformat(),
                    "amount": str(renewal.amount),
                    "status": renewal.status.value,
                    "days_until_due": (renewal.due_date - today).days,
                }
                for renewal, name in rows
            ]
        },
    )
    if total:
        context.recommendation = (
            "Priorize o contato com as renovações mais próximas e registre cada tentativa."
        )
    return context


async def _resolve_amount_at_risk(
    session: AsyncSession, *, organization_id: uuid.UUID, question: str
) -> ResolvedContext:
    """Valor mensal em risco: vencidas em aberto + marcadas como em risco."""
    del question
    indicators = await metrics.renewal_overview(session, organization_id=organization_id)
    critical = (
        (
            await session.execute(
                select(Renewal, Customer.name)
                .join(Customer, Renewal.customer_id == Customer.id)
                .where(
                    Renewal.organization_id == organization_id,
                    Customer.deleted_at.is_(None),
                    or_(
                        Renewal.status == RenewalStatus.AT_RISK,
                        Renewal.due_date < utcnow().date(),
                    ),
                    Renewal.status.in_(OPEN_RENEWALS),
                )
                .order_by(Renewal.amount.desc())
                .limit(10)
            )
        )
        .unique()
        .all()
    )
    return ResolvedContext(
        intent=Intent.AMOUNT_AT_RISK,
        headline="Valor mensal em risco calculado a partir das renovações em aberto.",
        facts=[
            Fact("Valor mensal em risco", indicators["amount_at_risk"], "money", "tabela renewals"),
            Fact(
                "Renovações vencidas em aberto", indicators["overdue"], "count", "tabela renewals"
            ),
            Fact(
                "Renovações marcadas como em risco",
                indicators["at_risk"],
                "count",
                "tabela renewals",
            ),
            Fact(
                "Clientes sem contato recente",
                indicators["customers_without_recent_contact"],
                "count",
                "tabela customers",
            ),
        ],
        reasoning=[
            "Somei o valor das renovações vencidas que continuam em aberto.",
            "Acrescentei as renovações futuras marcadas como “em risco” pela equipe.",
            "Não incluí renovações confirmadas nem perdidas.",
        ],
        recommendation="Comece pelos contratos de maior valor com vencimento já ultrapassado.",
        tables={
            "at_risk": [
                {
                    "customer_name": name,
                    "amount": str(renewal.amount),
                    "due_date": renewal.due_date.isoformat(),
                    "status": renewal.status.value,
                }
                for renewal, name in critical
            ]
        },
    )


async def _resolve_top_leads(
    session: AsyncSession, *, organization_id: uuid.UUID, question: str
) -> ResolvedContext:
    """Leads abertos com maior score."""
    del question
    rows = (
        (
            await session.execute(
                select(Lead)
                .where(
                    Lead.organization_id == organization_id,
                    Lead.deleted_at.is_(None),
                    Lead.status.in_(OPEN_LEAD_STATUSES),
                )
                .order_by(Lead.score.desc(), Lead.estimated_value.desc())
                .limit(10)
            )
        )
        .scalars()
        .all()
    )
    overview = await metrics.lead_overview(session, organization_id=organization_id)
    return ResolvedContext(
        intent=Intent.TOP_LEADS,
        headline="Leads em aberto ordenados pelo score determinístico.",
        facts=[
            Fact("Leads em aberto", overview["open_leads"], "count", "tabela leads"),
            Fact(
                f"Leads com score ≥ {HIGH_PRIORITY_SCORE}",
                overview["high_priority_leads"],
                "count",
                "tabela leads",
            ),
            Fact("Pipeline estimado", overview["estimated_pipeline"], "money", "tabela leads"),
            Fact("Score médio da base", overview["average_score"], "text", "tabela leads"),
        ],
        reasoning=[
            "Filtrei leads que não estão ganhos nem perdidos.",
            "Ordenei pelo score calculado pelas regras determinísticas (rules-v1).",
            "O score usa contato, orçamento, segmento, recência, porte, interesse e origem.",
        ],
        recommendation="Trate primeiro os leads de alta prioridade com interação recente.",
        tables={
            "leads": [
                {
                    "name": lead.name,
                    "company": lead.company,
                    "score": lead.score,
                    "category": lead.score_category.value,
                    "status": lead.status.value,
                    "estimated_value": str(lead.estimated_value),
                    "next_step": lead.next_step,
                }
                for lead in rows
            ]
        },
    )


async def _resolve_plan_churn(
    session: AsyncSession, *, organization_id: uuid.UUID, question: str
) -> ResolvedContext:
    """Planos ordenados por cancelamento."""
    del question
    ranking = await metrics.plan_ranking(session, organization_id=organization_id, limit=10)
    ordered = sorted(ranking, key=lambda item: (-item["churn_rate"], -item["churned_customers"]))
    churned_total = sum(item["churned_customers"] for item in ranking)
    facts = [Fact("Clientes cancelados na base", churned_total, "count", "tabela customers")]
    if ordered and ordered[0]["churned_customers"]:
        top = ordered[0]
        facts.extend(
            [
                Fact("Plano com maior cancelamento", top["plan_name"], "text", "tabela plans"),
                Fact(
                    f"Taxa de cancelamento de {top['plan_name']}",
                    top["churn_rate"],
                    "percent",
                    "tabela customers",
                ),
            ]
        )
    return ResolvedContext(
        intent=Intent.PLAN_CHURN,
        headline="Cancelamento por plano, calculado sobre a base atual de clientes.",
        facts=facts,
        reasoning=[
            "Agrupei os clientes por plano.",
            "Dividi a quantidade de clientes com situação “cancelado” pelo total do plano.",
            "Planos sem clientes aparecem com taxa zero.",
        ],
        recommendation=(
            "Compare o plano com maior taxa com os motivos de cancelamento registrados "
            "na base de conhecimento."
        ),
        tables={"plans": ordered},
        needs_knowledge=True,
    )


async def _resolve_stale_customers(
    session: AsyncSession, *, organization_id: uuid.UUID, question: str
) -> ResolvedContext:
    """Clientes sem contato recente."""
    del question
    threshold = CONTACT_THRESHOLD_DAYS
    cutoff = utcnow() - timedelta(days=threshold)
    rows = (
        (
            await session.execute(
                select(Customer)
                .where(
                    Customer.organization_id == organization_id,
                    Customer.deleted_at.is_(None),
                    Customer.status != CustomerStatus.CHURNED,
                    or_(
                        Customer.last_contact_at.is_(None),
                        Customer.last_contact_at < cutoff,
                    ),
                )
                .order_by(Customer.monthly_value.desc())
                .limit(15)
            )
        )
        .scalars()
        .unique()
        .all()
    )
    total = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Customer)
                .where(
                    Customer.organization_id == organization_id,
                    Customer.deleted_at.is_(None),
                    Customer.status != CustomerStatus.CHURNED,
                    or_(
                        Customer.last_contact_at.is_(None),
                        Customer.last_contact_at < cutoff,
                    ),
                )
            )
        ).scalar_one()
    )
    exposure = sum((customer.monthly_value for customer in rows), Decimal("0.00"))
    return ResolvedContext(
        intent=Intent.STALE_CUSTOMERS,
        headline=f"Clientes ativos sem contato registrado nos últimos {threshold} dias.",
        facts=[
            Fact(
                f"Clientes sem contato há mais de {threshold} dias",
                total,
                "count",
                "tabela customers",
            ),
            Fact("Receita mensal dos 15 maiores da lista", exposure, "money", "tabela customers"),
            Fact("Janela considerada", f"{threshold} dias", "text", "parâmetro do sistema"),
        ],
        reasoning=[
            f"Considerei clientes não cancelados com último contato anterior a {cutoff:%d/%m/%Y} "
            "ou sem nenhum contato registrado.",
            "Ordenei pela receita mensal para priorizar o maior impacto.",
        ],
        recommendation=(
            "Registre o contato no cliente após cada tentativa para manter o indicador útil."
        ),
        tables={
            "customers": [
                {
                    "name": customer.name,
                    "monthly_value": str(customer.monthly_value),
                    "status": customer.status.value,
                    "last_contact_at": (
                        customer.last_contact_at.isoformat() if customer.last_contact_at else None
                    ),
                    "renewal_date": (
                        customer.renewal_date.isoformat() if customer.renewal_date else None
                    ),
                }
                for customer in rows
            ]
        },
    )


async def _resolve_customer_overview(
    session: AsyncSession, *, organization_id: uuid.UUID, question: str
) -> ResolvedContext:
    """Panorama de clientes e receita."""
    del question
    overview = await metrics.customer_overview(session, organization_id=organization_id)
    ranking = await metrics.plan_ranking(session, organization_id=organization_id, limit=5)
    return ResolvedContext(
        intent=Intent.CUSTOMER_OVERVIEW,
        headline="Panorama atual da base de clientes.",
        facts=[
            Fact("Total de clientes", overview["total_customers"], "count", "tabela customers"),
            Fact("Clientes ativos", overview["active_customers"], "count", "tabela customers"),
            Fact("Clientes atrasados", overview["past_due_customers"], "count", "tabela customers"),
            Fact("Clientes cancelados", overview["churned_customers"], "count", "tabela customers"),
            Fact(
                "Receita mensal estimada", overview["monthly_revenue"], "money", "tabela customers"
            ),
            Fact("Ticket médio", overview["average_ticket"], "money", "tabela customers"),
        ],
        reasoning=[
            "Agrupei os clientes não excluídos por situação.",
            "A receita mensal soma o valor dos clientes ativos e atrasados.",
            "O ticket médio divide a receita pelo total de clientes.",
        ],
        tables={"plans": ranking},
    )


async def _resolve_lead_funnel(
    session: AsyncSession, *, organization_id: uuid.UUID, question: str
) -> ResolvedContext:
    """Distribuição do funil de leads."""
    del question
    overview = await metrics.lead_overview(session, organization_id=organization_id)
    rows = (
        await session.execute(
            select(Lead.status, func.count(), func.coalesce(func.sum(Lead.estimated_value), 0))
            .where(Lead.organization_id == organization_id, Lead.deleted_at.is_(None))
            .group_by(Lead.status)
        )
    ).all()
    sources = await metrics.lead_source_ranking(session, organization_id=organization_id, limit=5)
    return ResolvedContext(
        intent=Intent.LEAD_FUNNEL,
        headline="Distribuição dos leads por estágio do funil.",
        facts=[
            Fact("Total de leads", overview["total_leads"], "count", "tabela leads"),
            Fact("Leads em aberto", overview["open_leads"], "count", "tabela leads"),
            Fact("Leads ganhos", overview["won_leads"], "count", "tabela leads"),
            Fact("Pipeline estimado", overview["estimated_pipeline"], "money", "tabela leads"),
        ],
        reasoning=[
            "Agrupei os leads por status e somei o valor estimado de cada grupo.",
            "Estágios ganhos e perdidos ficam fora do pipeline em aberto.",
        ],
        tables={
            "funnel": [
                {
                    "status": row[0].value,
                    "total": int(row[1]),
                    "estimated_value": str(Decimal(row[2] or 0)),
                }
                for row in rows
            ],
            "sources": sources,
        },
    )


async def _resolve_import_status(
    session: AsyncSession, *, organization_id: uuid.UUID, question: str
) -> ResolvedContext:
    """Situação das importações."""
    del question
    overview = await metrics.import_overview(session, organization_id=organization_id)
    last = (
        (
            await session.execute(
                select(ImportJob)
                .where(ImportJob.organization_id == organization_id)
                .order_by(ImportJob.created_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .unique()
        .first()
    )
    facts = [
        Fact("Importações realizadas", overview["total_imports"], "count", "tabela import_jobs"),
        Fact("Linhas importadas", overview["total_imported_rows"], "count", "tabela import_jobs"),
        Fact("Linhas com erro", overview["total_invalid_rows"], "count", "tabela import_jobs"),
        Fact("Linhas duplicadas", overview["total_duplicate_rows"], "count", "tabela import_jobs"),
        Fact(
            "Importações pendentes de confirmação",
            overview["pending_commit"],
            "count",
            "tabela import_jobs",
        ),
    ]
    if last is not None:
        facts.append(
            Fact(
                "Última importação",
                f"{last.original_filename} ({last.status.value})",
                "text",
                "tabela import_jobs",
            )
        )
    return ResolvedContext(
        intent=Intent.IMPORT_STATUS,
        headline="Situação das importações de planilhas.",
        facts=facts,
        reasoning=[
            "Somei os contadores de cada importação registrada.",
            "Considerei pendentes as importações enviadas, mapeadas ou validadas sem confirmação.",
        ],
        tables={"imports": overview["recent"]},
    )


async def _resolve_policy(
    session: AsyncSession, *, organization_id: uuid.UUID, question: str
) -> ResolvedContext:
    """Perguntas de política/processo: respondidas pela base de conhecimento."""
    del session, organization_id, question
    return ResolvedContext(
        intent=Intent.POLICY,
        headline="Resposta baseada nos documentos da base de conhecimento.",
        reasoning=["Busquei trechos relevantes nos documentos indexados da organização."],
        needs_knowledge=True,
    )


async def _resolve_unknown(
    session: AsyncSession, *, organization_id: uuid.UUID, question: str
) -> ResolvedContext:
    """Sem intenção clara: tenta a base de conhecimento."""
    del session, organization_id, question
    return ResolvedContext(
        intent=Intent.UNKNOWN,
        headline="Não identifiquei um indicador específico para esta pergunta.",
        reasoning=[
            "Não encontrei correspondência com os indicadores disponíveis.",
            "Busquei a resposta nos documentos da base de conhecimento.",
        ],
        needs_knowledge=True,
    )


Resolver = Callable[..., Awaitable[ResolvedContext]]

RESOLVERS: dict[Intent, Resolver] = {
    Intent.RENEWALS: _resolve_renewals,
    Intent.AMOUNT_AT_RISK: _resolve_amount_at_risk,
    Intent.TOP_LEADS: _resolve_top_leads,
    Intent.PLAN_CHURN: _resolve_plan_churn,
    Intent.STALE_CUSTOMERS: _resolve_stale_customers,
    Intent.CUSTOMER_OVERVIEW: _resolve_customer_overview,
    Intent.LEAD_FUNNEL: _resolve_lead_funnel,
    Intent.IMPORT_STATUS: _resolve_import_status,
    Intent.POLICY: _resolve_policy,
    Intent.UNKNOWN: _resolve_unknown,
}


async def resolve(
    session: AsyncSession, *, organization_id: uuid.UUID, question: str, intent: Intent
) -> ResolvedContext:
    """Executa o resolver da intenção detectada."""
    resolver = RESOLVERS.get(intent, _resolve_unknown)
    return await resolver(session, organization_id=organization_id, question=question)


#: Perguntas sugeridas na interface do assistente.
SUGGESTED_QUESTIONS: tuple[str, ...] = (
    "Quantos clientes renovam nos próximos 30 dias?",
    "Qual é o valor mensal em risco?",
    "Quais leads têm maior prioridade?",
    "Quais planos apresentam maior cancelamento?",
    "Quais clientes não tiveram contato recente?",
    "Qual é a receita mensal estimada da base?",
    "Como está o funil de leads?",
    "Qual é o prazo de aviso prévio para cancelamento?",
    "Qual o desconto máximo que um consultor pode dar?",
    "Quantas linhas foram rejeitadas nas importações?",
)
