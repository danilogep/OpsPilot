"""Seed idempotente de dados sintéticos de demonstração.

Executar várias vezes não duplica registros: cada entidade é localizada por uma
chave natural (slug da organização, e-mail do usuário, nome do plano, chave de
deduplicação do cliente, e-mail do lead, título do documento).

**Todos os dados são fictícios.** A senha dos usuários de demonstração vem de
``OPSPILOT_DEMO_PASSWORD`` e existe apenas para o ambiente local.
"""

from __future__ import annotations

import random
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import hash_password
from app.db.base import utcnow
from app.db.demo_content import DEMO_DOCUMENTS
from app.db.models import (
    AgentDefinition,
    AuditEvent,
    Customer,
    CustomerStatus,
    DocumentChunk,
    DocumentStatus,
    KnowledgeDocument,
    Lead,
    LeadEvent,
    LeadEventType,
    Organization,
    Plan,
    Renewal,
    RenewalStatus,
    Role,
    ScoringMethod,
    User,
    UserRole,
)
from app.db.models.enums import CompanySize, LeadStatus
from app.domains.auth.service import ROLE_DESCRIPTIONS, ROLE_NAMES, ROLE_PERMISSIONS
from app.domains.imports.dedupe import build_dedupe_key
from app.domains.knowledge.chunking import chunk_text
from app.domains.leads.scoring import LeadScoreInput, score_lead

logger = get_logger(__name__)

RANDOM_SEED = 20260101
CUSTOMER_TARGET = 100
LEAD_TARGET = 60
RENEWAL_TARGET = 30

DEMO_ORG_SLUG = "acme-servicos"

DEMO_USERS: tuple[tuple[str, str, UserRole], ...] = (
    ("admin@opspilot.local", "Ana Administradora", UserRole.ADMIN),
    ("analyst@opspilot.local", "Bruno Analista", UserRole.ANALYST),
    ("viewer@opspilot.local", "Carla Visualizadora", UserRole.VIEWER),
)

PLAN_CATALOG: tuple[tuple[str, str, str, str], ...] = (
    ("Essencial", "ESS", "199.00", "Até 3 usuários, relatórios básicos."),
    ("Profissional", "PRO", "499.00", "Até 10 usuários, relatórios mensais."),
    ("Avançado", "ADV", "899.00", "Integrações e atendimento prioritário."),
    ("Enterprise", "ENT", "1890.00", "Escopo negociado, SLA dedicado."),
    ("Suporte Pontual", "SUP", "150.00", "Atendimento por demanda, sem fidelidade."),
)

PLAN_VALUES: dict[str, Decimal] = {
    name: Decimal(value) for name, _code, value, _desc in PLAN_CATALOG
}

COMPANY_PREFIXES = (
    "Padaria Aurora",
    "Clínica Vida",
    "Studio Lumen",
    "Mercado Bom Preço",
    "Oficina Trilho",
    "Escola Horizonte",
    "Pet Shop Amigo",
    "Casa das Tintas",
    "Transportes Rota",
    "Farmácia Saúde",
    "Contabilidade Prisma",
    "Advocacia Mendes",
    "Restaurante Sabor",
    "Academia Força",
    "Gráfica Impacto",
    "Lavanderia Clara",
    "Marcenaria Cedro",
    "Floricultura Jardim",
    "Ótica Visão",
    "Doceria Mel",
    "Barbearia Nobre",
    "Pousada Mar Azul",
    "Agência Vértice",
    "Imobiliária Lar",
    "Serralheria Ferro",
    "Papelaria Nota",
    "Distribuidora Norte",
    "Auto Center Giro",
    "Clínica Odonto Sorriso",
    "Creche Pequeno Mundo",
    "Buffet Festa Boa",
    "Chaveiro Rápido",
    "Pizzaria Forno",
    "Salão Beleza Pura",
    "Bicicletaria Pedal",
    "Loja Natural Folha",
    "Hortifruti Colheita",
    "Dedetizadora Escudo",
    "Construtora Base",
    "Informática Byte",
)
COMPANY_SUFFIXES = ("Ltda", "ME", "EIRELI", "& Cia", "Comércio", "Serviços")
CITIES = (
    "São Paulo",
    "Campinas",
    "Belo Horizonte",
    "Curitiba",
    "Porto Alegre",
    "Recife",
    "Salvador",
    "Fortaleza",
    "Goiânia",
    "Florianópolis",
)
SEGMENTS = (
    "serviços profissionais",
    "saúde",
    "educação",
    "varejo local",
    "tecnologia",
    "alimentação",
    "logística",
    "construção",
    "contabilidade",
    "indústria",
)
SOURCES = (
    "indicacao",
    "site",
    "organico",
    "google ads",
    "meta ads",
    "evento",
    "prospeccao",
    "lista",
    "redes sociais",
    "webinar",
)
FIRST_NAMES = (
    "Mariana",
    "Rafael",
    "Juliana",
    "Thiago",
    "Patrícia",
    "Eduardo",
    "Camila",
    "Vinícius",
    "Fernanda",
    "Lucas",
    "Bianca",
    "Gustavo",
    "Larissa",
    "Felipe",
    "Natália",
    "Rodrigo",
    "Aline",
    "Marcelo",
    "Beatriz",
    "Henrique",
)
LAST_NAMES = (
    "Silva",
    "Souza",
    "Oliveira",
    "Costa",
    "Pereira",
    "Almeida",
    "Nunes",
    "Carvalho",
    "Ribeiro",
    "Barbosa",
    "Rocha",
    "Martins",
    "Freitas",
    "Gomes",
)
INTERESTS = (
    "organizar a base de clientes",
    "controlar renovações",
    "reduzir inadimplência",
    "painel de indicadores",
    "importar planilhas antigas",
    "automatizar cobrança",
    None,
)
AGENT_DEFINITIONS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "DataAnalystAgent",
        "Analista de dados",
        "Responde perguntas sobre clientes, renovações e indicadores "
        "usando apenas os dados da organização.",
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
    (
        "SalesAgent",
        "Agente comercial",
        "Prioriza leads, explica o score e sugere próximos passos e mensagens.",
        ("list_leads", "calculate_metrics", "search_knowledge", "create_lead_note"),
    ),
    (
        "RenewalAgent",
        "Agente de renovações",
        "Monta o panorama de renovações, identifica clientes críticos e valor em risco.",
        (
            "list_renewals",
            "list_customers",
            "get_customer",
            "calculate_metrics",
            "search_knowledge",
        ),
    ),
)


@dataclass
class SeedReport:
    """Resumo do que o seed criou nesta execução."""

    organization_id: uuid.UUID | None = None
    created: dict[str, int] = field(default_factory=dict)
    existing: dict[str, int] = field(default_factory=dict)

    def add(self, entity: str, created: int, existing: int) -> None:
        self.created[entity] = created
        self.existing[entity] = existing

    def as_dict(self) -> dict[str, object]:
        return {
            "organization_id": str(self.organization_id) if self.organization_id else None,
            "created": self.created,
            "existing": self.existing,
        }


def _slugify(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.lower())
    ascii_only = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return "-".join(
        part for part in "".join(ch if ch.isalnum() else " " for ch in ascii_only).split()
    )


def _email_slug(value: str) -> str:
    return _slugify(value).replace("-", ".")[:40].strip(".")


def _fake_phone(rng: random.Random) -> str:
    """Telefone celular sintético em formato E.164."""
    ddd = rng.choice([11, 19, 21, 31, 41, 51, 62, 71, 81, 85])
    return f"+55{ddd}9{rng.randint(10000000, 99999999)}"


def _fake_cnpj(rng: random.Random) -> str:
    digits = "".join(str(rng.randint(0, 9)) for _ in range(14))
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


async def run_seed(session: AsyncSession) -> SeedReport:
    """Executa todas as etapas do seed de forma idempotente."""
    rng = random.Random(RANDOM_SEED)
    report = SeedReport()

    organization = await _ensure_organization(session)
    await session.flush()
    report.organization_id = organization.id

    report.add("roles", *await _ensure_roles(session))
    report.add("users", *await _ensure_users(session, organization))
    plans, plan_counts = await _ensure_plans(session, organization)
    report.add("plans", *plan_counts)
    report.add("customers", *await _ensure_customers(session, organization, plans, rng))
    report.add("renewals", *await _ensure_renewals(session, organization, rng))
    report.add("leads", *await _ensure_leads(session, organization, rng))
    report.add("knowledge_documents", *await _ensure_knowledge(session, organization))
    report.add("agents", *await _ensure_agents(session, organization))

    session.add(
        AuditEvent(
            organization_id=organization.id,
            action="seed.completed",
            entity_type="organization",
            entity_id=str(organization.id),
            actor_email="system",
            actor_role="SYSTEM",
            summary="Seed de demonstração executado.",
            meta=report.as_dict(),
        )
    )
    await session.commit()
    logger.info("seed_completed", **dict(report.created))
    return report


async def _ensure_organization(session: AsyncSession) -> Organization:
    organization = (
        await session.execute(select(Organization).where(Organization.slug == DEMO_ORG_SLUG))
    ).scalar_one_or_none()
    if organization is not None:
        return organization
    organization = Organization(
        name=settings.demo_org_name,
        slug=DEMO_ORG_SLUG,
        document="12.345.678/0001-90",
        settings={"demo": True, "currency": "BRL", "locale": "pt-BR"},
    )
    session.add(organization)
    return organization


async def _ensure_roles(session: AsyncSession) -> tuple[int, int]:
    existing = set((await session.execute(select(Role.key))).scalars().all())
    created = 0
    for key in (UserRole.ADMIN, UserRole.ANALYST, UserRole.VIEWER):
        if key in existing:
            continue
        session.add(
            Role(
                key=key,
                name=ROLE_NAMES[key],
                description=ROLE_DESCRIPTIONS[key],
                permissions=ROLE_PERMISSIONS[key],
            )
        )
        created += 1
    await session.flush()
    return created, len(existing)


async def _ensure_users(session: AsyncSession, organization: Organization) -> tuple[int, int]:
    existing_emails = set(
        (await session.execute(select(User.email).where(User.organization_id == organization.id)))
        .scalars()
        .all()
    )
    created = 0
    password_hash = hash_password(settings.demo_password)
    for email, full_name, role in DEMO_USERS:
        if email in existing_emails:
            continue
        session.add(
            User(
                organization_id=organization.id,
                email=email,
                full_name=full_name,
                password_hash=password_hash,
                role=role,
                is_active=True,
            )
        )
        created += 1
    await session.flush()
    return created, len(existing_emails)


async def _ensure_plans(
    session: AsyncSession, organization: Organization
) -> tuple[dict[str, Plan], tuple[int, int]]:
    rows = (
        (await session.execute(select(Plan).where(Plan.organization_id == organization.id)))
        .scalars()
        .all()
    )
    plans = {plan.name: plan for plan in rows}
    created = 0
    for name, code, value, description in PLAN_CATALOG:
        if name in plans:
            continue
        plan = Plan(
            organization_id=organization.id,
            name=name,
            code=code,
            description=description,
            monthly_value=Decimal(value),
            is_active=True,
        )
        session.add(plan)
        plans[name] = plan
        created += 1
    await session.flush()
    return plans, (created, len(rows))


def _customer_renewal_date(index: int, today: date, rng: random.Random) -> date:
    """Distribui datas de renovação para alimentar os indicadores do dashboard."""
    if index % 16 == 0:
        return today + timedelta(days=rng.randint(1, 7))
    if index % 7 == 0:
        return today + timedelta(days=rng.randint(8, 30))
    if index % 11 == 0:
        return today - timedelta(days=rng.randint(1, 25))
    return today + timedelta(days=rng.randint(31, 300))


async def _ensure_customers(
    session: AsyncSession,
    organization: Organization,
    plans: dict[str, Plan],
    rng: random.Random,
) -> tuple[int, int]:
    existing_count = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Customer)
                .where(Customer.organization_id == organization.id)
            )
        ).scalar_one()
    )
    existing_keys = set(
        (
            await session.execute(
                select(Customer.dedupe_key).where(Customer.organization_id == organization.id)
            )
        )
        .scalars()
        .all()
    )
    today = utcnow().date()
    plan_names = [name for name, *_ in PLAN_CATALOG]
    created = 0

    for index in range(CUSTOMER_TARGET):
        prefix = COMPANY_PREFIXES[index % len(COMPANY_PREFIXES)]
        suffix = COMPANY_SUFFIXES[index % len(COMPANY_SUFFIXES)]
        city = CITIES[index % len(CITIES)]
        name = f"{prefix} {suffix}" if index < len(COMPANY_PREFIXES) else f"{prefix} {city}"
        email = f"contato@{_slugify(prefix)}{index}.com.br"
        key = build_dedupe_key(name=name, email=email)
        if key.value in existing_keys:
            continue

        plan_name = plan_names[index % len(plan_names)]
        plan = plans[plan_name]
        base_value = PLAN_VALUES[plan_name]
        variation = Decimal(rng.choice(["0", "0", "-20.00", "50.00", "100.00"]))
        status = (
            CustomerStatus.PAST_DUE
            if index % 9 == 0
            else CustomerStatus.CHURNED
            if index % 17 == 0
            else CustomerStatus.PROSPECT
            if index % 23 == 0
            else CustomerStatus.ACTIVE
        )
        last_contact_days = rng.choice([2, 5, 9, 14, 21, 40, 65, 95, 120])
        session.add(
            Customer(
                organization_id=organization.id,
                name=name,
                email=email,
                phone=_fake_phone(rng),
                document=_fake_cnpj(rng),
                status=status,
                plan_id=plan.id,
                monthly_value=max(Decimal("0.00"), base_value + variation),
                # Inclui contratos recentes para que a evolução da carteira
                # tenha movimento também no mês corrente.
                start_date=today - timedelta(days=rng.randint(3, 1100)),
                renewal_date=_customer_renewal_date(index, today, rng),
                source=SOURCES[index % len(SOURCES)],
                notes=f"Cliente sintético de demonstração em {city}.",
                last_contact_at=utcnow() - timedelta(days=last_contact_days),
                dedupe_key=key.value,
                extra={"city": city, "segment": SEGMENTS[index % len(SEGMENTS)]},
            )
        )
        existing_keys.add(key.value)
        created += 1

    await session.flush()
    return created, existing_count


async def _ensure_renewals(
    session: AsyncSession, organization: Organization, rng: random.Random
) -> tuple[int, int]:
    existing_count = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Renewal)
                .where(Renewal.organization_id == organization.id)
            )
        ).scalar_one()
    )
    if existing_count >= RENEWAL_TARGET:
        return 0, existing_count

    customers = (
        (
            await session.execute(
                select(Customer)
                .where(
                    Customer.organization_id == organization.id,
                    Customer.status != CustomerStatus.CHURNED,
                )
                .order_by(Customer.renewal_date)
                .limit(RENEWAL_TARGET)
            )
        )
        .scalars()
        .all()
    )

    created = 0
    for position, customer in enumerate(customers):
        if customer.renewal_date is None:
            continue
        status = (
            RenewalStatus.AT_RISK
            if position % 5 == 0
            else RenewalStatus.CONFIRMED
            if position % 7 == 0
            else RenewalStatus.LOST
            if position % 13 == 0
            else RenewalStatus.SCHEDULED
        )
        session.add(
            Renewal(
                organization_id=organization.id,
                customer_id=customer.id,
                plan_id=customer.plan_id,
                due_date=customer.renewal_date,
                amount=customer.monthly_value,
                status=status,
                confirmed_at=utcnow() if status is RenewalStatus.CONFIRMED else None,
                notes=rng.choice(
                    [
                        "Contato inicial realizado.",
                        "Aguardando retorno do responsável.",
                        "Cliente pediu revisão de escopo.",
                        None,
                    ]
                ),
            )
        )
        created += 1

    await session.flush()
    return created, existing_count


async def _ensure_leads(
    session: AsyncSession, organization: Organization, rng: random.Random
) -> tuple[int, int]:
    rows = (
        await session.execute(
            select(Lead.email, Lead.name, Lead.company).where(
                Lead.organization_id == organization.id
            )
        )
    ).all()
    # Chave natural: e-mail quando existe, senão nome + empresa.
    existing_keys = {(row[0] or f"{row[1]}|{row[2]}").lower() for row in rows}
    existing_count = len(rows)
    created = 0
    now = utcnow()

    for index in range(LEAD_TARGET):
        first = FIRST_NAMES[index % len(FIRST_NAMES)]
        last = LAST_NAMES[(index * 3) % len(LAST_NAMES)]
        person = f"{first} {last}"
        company = (
            f"{COMPANY_PREFIXES[(index * 7) % len(COMPANY_PREFIXES)]} {CITIES[index % len(CITIES)]}"
        )
        email = None if index % 13 == 0 else f"{_email_slug(person)}{index}@exemplo.com.br"
        natural_key = (email or f"{person}|{company}").lower()
        if natural_key in existing_keys:
            continue

        phone = None if index % 11 == 0 else f"+55119{rng.randint(10000000, 99999999)}"
        segment = SEGMENTS[index % len(SEGMENTS)]
        size = list(CompanySize)[index % len(CompanySize)]
        interest = INTERESTS[index % len(INTERESTS)]
        estimated = Decimal(
            rng.choice(["0", "0", "350.00", "600.00", "1200.00", "1800.00", "2500.00"])
        )
        source = SOURCES[(index * 3) % len(SOURCES)]
        last_interaction = (
            None if index % 17 == 0 else now - timedelta(days=rng.choice([1, 2, 5, 9, 20, 45, 70]))
        )
        status = (
            LeadStatus.WON
            if index % 19 == 0
            else LeadStatus.LOST
            if index % 23 == 0
            else LeadStatus.PROPOSAL
            if index % 7 == 0
            else LeadStatus.CONTACTED
            if index % 3 == 0
            else LeadStatus.NEW
        )

        result = score_lead(
            LeadScoreInput(
                email=email,
                phone=phone,
                segment=segment,
                company_size=size,
                interest=interest,
                estimated_value=estimated,
                source=source,
                last_interaction_at=last_interaction,
            ),
            now=now,
        )
        lead = Lead(
            organization_id=organization.id,
            name=person,
            company=company,
            email=email,
            phone=phone,
            source=source,
            segment=segment,
            company_size=size,
            interest=interest,
            status=status,
            estimated_value=estimated,
            probability=min(95, result.score),
            score=result.score,
            score_category=result.category,
            score_reasons=result.reasons_as_dicts(),
            score_method=ScoringMethod.RULES,
            score_version=result.version,
            scored_at=now,
            next_step=result.next_step,
            risks=result.risks,
            last_interaction_at=last_interaction,
            notes="Lead sintético de demonstração.",
        )
        session.add(lead)
        await session.flush()

        session.add(
            LeadEvent(
                organization_id=organization.id,
                lead_id=lead.id,
                event_type=LeadEventType.CREATED,
                description=f"Lead criado com origem {source}.",
                payload={"source": source, "segment": segment},
            )
        )
        session.add(
            LeadEvent(
                organization_id=organization.id,
                lead_id=lead.id,
                event_type=LeadEventType.SCORED,
                description=(
                    f"Score {result.score} ({result.category.value}) por regras {result.version}."
                ),
                payload={"score": result.score, "category": result.category.value},
            )
        )
        if status is not LeadStatus.NEW:
            session.add(
                LeadEvent(
                    organization_id=organization.id,
                    lead_id=lead.id,
                    event_type=LeadEventType.STATUS_CHANGED,
                    description=f"Status alterado para {status.value}.",
                    payload={"status": status.value},
                )
            )
        existing_keys.add(natural_key)
        created += 1

    await session.flush()
    return created, existing_count


async def _ensure_knowledge(session: AsyncSession, organization: Organization) -> tuple[int, int]:
    existing_titles = set(
        (
            await session.execute(
                select(KnowledgeDocument.title).where(
                    KnowledgeDocument.organization_id == organization.id
                )
            )
        )
        .scalars()
        .all()
    )
    created = 0
    for demo in DEMO_DOCUMENTS:
        if demo.title in existing_titles:
            continue
        chunks = chunk_text(demo.body)
        document = KnowledgeDocument(
            organization_id=organization.id,
            title=demo.title,
            original_filename=demo.filename,
            mime_type="text/markdown",
            size_bytes=len(demo.body.encode("utf-8")),
            char_count=len(demo.body),
            chunk_count=len(chunks),
            status=DocumentStatus.READY,
            tags=demo.tags,
            source_label="seed de demonstração",
        )
        session.add(document)
        await session.flush()
        for chunk in chunks:
            session.add(
                DocumentChunk(
                    organization_id=organization.id,
                    document_id=document.id,
                    chunk_index=chunk.index,
                    content=chunk.content,
                    content_normalized=chunk.normalized,
                    char_count=chunk.char_count,
                    token_estimate=chunk.token_estimate,
                    page_hint=chunk.heading,
                    meta={"heading": chunk.heading, "filename": demo.filename},
                )
            )
        created += 1
    await session.flush()
    return created, len(existing_titles)


async def _ensure_agents(session: AsyncSession, organization: Organization) -> tuple[int, int]:
    existing_keys = set(
        (
            await session.execute(
                select(AgentDefinition.key).where(
                    AgentDefinition.organization_id == organization.id
                )
            )
        )
        .scalars()
        .all()
    )
    created = 0
    for key, name, description, tools in AGENT_DEFINITIONS:
        if key in existing_keys:
            continue
        session.add(
            AgentDefinition(
                organization_id=organization.id,
                key=key,
                name=name,
                description=description,
                system_prompt=(
                    "Você é um agente do OpsPilot. Responda em português do Brasil, "
                    "use apenas dados retornados pelas ferramentas e cite as fontes. "
                    "Se não houver evidência suficiente, diga isso explicitamente."
                ),
                allowed_tools=list(tools),
                max_steps=settings.agent_max_steps,
                prompt_version="v1",
                is_active=True,
            )
        )
        created += 1
    await session.flush()
    return created, len(existing_keys)
