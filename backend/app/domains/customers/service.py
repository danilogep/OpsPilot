"""Serviço de clientes: consulta com filtros, CRUD, histórico e exportação."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.api.deps import RequestContext
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.pagination import PageParams
from app.db.base import ensure_utc, utcnow
from app.db.models import Customer, CustomerStatus, Plan, User
from app.domains.audit import service as audit_service
from app.domains.customers.schemas import CustomerCreate, CustomerRead, CustomerUpdate
from app.domains.imports.dedupe import build_dedupe_key
from app.domains.imports.normalizers import format_phone_br

#: Colunas liberadas para ordenação (evita injeção via query string).
SORTABLE_COLUMNS: dict[str, Any] = {
    "name": Customer.name,
    "status": Customer.status,
    "monthly_value": Customer.monthly_value,
    "renewal_date": Customer.renewal_date,
    "start_date": Customer.start_date,
    "last_contact_at": Customer.last_contact_at,
    "created_at": Customer.created_at,
}
DEFAULT_SORT = "name"


@dataclass(slots=True)
class CustomerFilters:
    """Filtros aceitos na listagem de clientes."""

    search: str | None = None
    statuses: list[CustomerStatus] | None = None
    plan_id: uuid.UUID | None = None
    source: str | None = None
    renewal_from: date | None = None
    renewal_to: date | None = None
    renewal_within_days: int | None = None
    overdue_only: bool = False
    without_contact_days: int | None = None
    has_email: bool | None = None


def _base_query(organization_id: uuid.UUID) -> Select[Any]:
    return select(Customer).where(
        Customer.organization_id == organization_id, Customer.deleted_at.is_(None)
    )


def apply_filters(stmt: Select[Any], filters: CustomerFilters, *, today: date) -> Select[Any]:
    """Aplica os filtros de listagem à query."""
    if filters.search:
        term = f"%{filters.search.strip()}%"
        stmt = stmt.where(
            or_(
                Customer.name.ilike(term),
                Customer.email.ilike(term),
                Customer.document.ilike(term),
                Customer.phone.ilike(term),
            )
        )
    if filters.statuses:
        stmt = stmt.where(Customer.status.in_(filters.statuses))
    if filters.plan_id:
        stmt = stmt.where(Customer.plan_id == filters.plan_id)
    if filters.source:
        stmt = stmt.where(Customer.source == filters.source)
    if filters.renewal_from:
        stmt = stmt.where(Customer.renewal_date >= filters.renewal_from)
    if filters.renewal_to:
        stmt = stmt.where(Customer.renewal_date <= filters.renewal_to)
    if filters.renewal_within_days is not None:
        stmt = stmt.where(
            Customer.renewal_date.is_not(None),
            Customer.renewal_date >= today,
            Customer.renewal_date <= today + timedelta(days=filters.renewal_within_days),
        )
    if filters.overdue_only:
        stmt = stmt.where(
            or_(
                Customer.status == CustomerStatus.PAST_DUE,
                (Customer.renewal_date.is_not(None)) & (Customer.renewal_date < today),
            )
        )
    if filters.without_contact_days is not None:
        cutoff = utcnow() - timedelta(days=filters.without_contact_days)
        stmt = stmt.where(
            or_(Customer.last_contact_at.is_(None), Customer.last_contact_at < cutoff)
        )
    if filters.has_email is True:
        stmt = stmt.where(Customer.email.is_not(None), Customer.email != "")
    elif filters.has_email is False:
        stmt = stmt.where(or_(Customer.email.is_(None), Customer.email == ""))
    return stmt


def apply_sorting(stmt: Select[Any], *, sort: str, direction: str) -> Select[Any]:
    """Ordena pela coluna informada, validando contra a allowlist."""
    column = SORTABLE_COLUMNS.get(sort)
    if column is None:
        raise ValidationError(
            "Campo de ordenação inválido.", details={"allowed": sorted(SORTABLE_COLUMNS)}
        )
    order = column.desc() if direction.lower() == "desc" else column.asc()
    return stmt.order_by(order, Customer.id)


async def list_customers(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    params: PageParams,
    filters: CustomerFilters,
    sort: str = DEFAULT_SORT,
    direction: str = "asc",
) -> tuple[list[Customer], int]:
    """Lista clientes com filtros, busca, ordenação e paginação."""
    today = utcnow().date()
    base = apply_filters(_base_query(organization_id), filters, today=today)
    total = int(
        (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    )
    stmt = apply_sorting(base, sort=sort, direction=direction)
    rows = (
        (
            await session.execute(
                stmt.options(joinedload(Customer.plan))
                .offset(params.offset)
                .limit(params.page_size)
            )
        )
        .scalars()
        .unique()
        .all()
    )
    return list(rows), total


async def iter_all_customers(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    filters: CustomerFilters,
    sort: str = DEFAULT_SORT,
    direction: str = "asc",
    limit: int = 10_000,
) -> list[Customer]:
    """Carrega todos os clientes filtrados (usado na exportação CSV)."""
    today = utcnow().date()
    base = apply_filters(_base_query(organization_id), filters, today=today)
    stmt = apply_sorting(base, sort=sort, direction=direction)
    rows = (
        (await session.execute(stmt.options(joinedload(Customer.plan)).limit(limit)))
        .scalars()
        .unique()
        .all()
    )
    return list(rows)


async def get_customer(
    session: AsyncSession, *, organization_id: uuid.UUID, customer_id: uuid.UUID
) -> Customer:
    """Busca um cliente da organização ou falha com 404."""
    result = await session.execute(
        _base_query(organization_id)
        .where(Customer.id == customer_id)
        .options(joinedload(Customer.plan))
    )
    customer: Customer | None = result.unique().scalar_one_or_none()
    if customer is None:
        raise NotFoundError("Cliente não encontrado.")
    return customer


async def _validate_plan(
    session: AsyncSession, *, organization_id: uuid.UUID, plan_id: uuid.UUID | None
) -> Plan | None:
    if plan_id is None:
        return None
    plan = (
        await session.execute(
            select(Plan).where(
                Plan.id == plan_id,
                Plan.organization_id == organization_id,
                Plan.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if plan is None:
        raise ValidationError("Plano informado não existe nesta organização.")
    return plan


async def create_customer(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    payload: CustomerCreate,
    actor: User,
    context: RequestContext | None = None,
) -> Customer:
    """Cria um cliente, rejeitando duplicidade pela chave de deduplicação."""
    plan = await _validate_plan(session, organization_id=organization_id, plan_id=payload.plan_id)
    key = build_dedupe_key(
        name=payload.name, email=payload.email, document=payload.document, phone=payload.phone
    )
    duplicate = (
        await session.execute(
            select(Customer.id, Customer.name).where(
                Customer.organization_id == organization_id,
                Customer.dedupe_key == key.value,
                Customer.deleted_at.is_(None),
            )
        )
    ).first()
    if duplicate:
        raise ConflictError(
            "Já existe um cliente com estes dados.",
            details={"criterion": key.human_criterion, "customer_id": str(duplicate[0])},
        )

    customer = Customer(
        organization_id=organization_id,
        name=payload.name.strip(),
        email=payload.email,
        phone=payload.phone,
        document=payload.document,
        status=payload.status,
        plan_id=plan.id if plan else None,
        monthly_value=payload.monthly_value or (plan.monthly_value if plan else Decimal("0.00")),
        start_date=payload.start_date,
        renewal_date=payload.renewal_date,
        source=payload.source or "cadastro manual",
        notes=payload.notes,
        dedupe_key=key.value,
    )
    session.add(customer)
    await session.flush()
    await audit_service.record_audit(
        session,
        organization_id=organization_id,
        action=audit_service.ACTION_CUSTOMER_CREATE,
        entity_type="customer",
        entity_id=str(customer.id),
        actor=actor,
        summary=f"Cliente {customer.name} cadastrado manualmente.",
        meta={"dedupe_criterion": key.criterion},
        context=context,
    )
    await session.commit()
    return await get_customer(session, organization_id=organization_id, customer_id=customer.id)


def snapshot(customer: Customer) -> dict[str, Any]:
    """Estado auditável do cliente."""
    return {
        "name": customer.name,
        "email": customer.email,
        "phone": customer.phone,
        "document": customer.document,
        "status": customer.status.value,
        "plan_id": str(customer.plan_id) if customer.plan_id else None,
        "monthly_value": str(customer.monthly_value),
        "start_date": customer.start_date.isoformat() if customer.start_date else None,
        "renewal_date": customer.renewal_date.isoformat() if customer.renewal_date else None,
        "source": customer.source,
        "notes": customer.notes,
        "last_contact_at": (
            customer.last_contact_at.isoformat() if customer.last_contact_at else None
        ),
    }


async def update_customer(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    payload: CustomerUpdate,
    actor: User,
    context: RequestContext | None = None,
) -> Customer:
    """Atualiza um cliente e registra o diff na auditoria."""
    customer = await get_customer(session, organization_id=organization_id, customer_id=customer_id)
    before = snapshot(customer)
    data = payload.model_dump(exclude_unset=True)

    if "plan_id" in data:
        plan = await _validate_plan(
            session, organization_id=organization_id, plan_id=data["plan_id"]
        )
        customer.plan_id = plan.id if plan else None
        data.pop("plan_id")

    for attribute, value in data.items():
        setattr(customer, attribute, value)

    if any(key in data for key in ("name", "email", "document", "phone")):
        customer.dedupe_key = build_dedupe_key(
            name=customer.name,
            email=customer.email,
            document=customer.document,
            phone=customer.phone,
        ).value

    diff = audit_service.build_diff(before, snapshot(customer))
    if diff:
        await audit_service.record_audit(
            session,
            organization_id=organization_id,
            action=audit_service.ACTION_CUSTOMER_UPDATE,
            entity_type="customer",
            entity_id=str(customer.id),
            actor=actor,
            summary=f"Cliente {customer.name} atualizado.",
            meta={"changes": diff},
            context=context,
        )
    await session.commit()
    return await get_customer(session, organization_id=organization_id, customer_id=customer.id)


async def delete_customer(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    actor: User,
    context: RequestContext | None = None,
) -> None:
    """Exclusão lógica do cliente (``deleted_at``)."""
    customer = await get_customer(session, organization_id=organization_id, customer_id=customer_id)
    customer.deleted_at = utcnow()
    await audit_service.record_audit(
        session,
        organization_id=organization_id,
        action=audit_service.ACTION_CUSTOMER_DELETE,
        entity_type="customer",
        entity_id=str(customer.id),
        actor=actor,
        summary=f"Cliente {customer.name} excluído (exclusão lógica).",
        context=context,
    )
    await session.commit()


async def register_contact(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    actor: User,
    note: str | None = None,
    context: RequestContext | None = None,
) -> Customer:
    """Marca que houve contato com o cliente agora."""
    customer = await get_customer(session, organization_id=organization_id, customer_id=customer_id)
    customer.last_contact_at = utcnow()
    await audit_service.record_audit(
        session,
        organization_id=organization_id,
        action="customer.contacted",
        entity_type="customer",
        entity_id=str(customer.id),
        actor=actor,
        summary=f"Contato registrado com {customer.name}.",
        meta={"note": note} if note else {},
        context=context,
    )
    await session.commit()
    return customer


def to_read(customer: Customer, *, today: date | None = None) -> CustomerRead:
    """Converte o modelo em schema, calculando os campos derivados."""
    reference = today or utcnow().date()
    data = CustomerRead.model_validate(customer)
    data.phone_formatted = format_phone_br(customer.phone)
    if customer.renewal_date:
        data.days_to_renewal = (customer.renewal_date - reference).days
    contact = ensure_utc(customer.last_contact_at)
    if contact:
        data.days_since_contact = (utcnow() - contact).days
    return data


CSV_HEADERS = (
    "Nome",
    "E-mail",
    "Telefone",
    "CPF/CNPJ",
    "Situação",
    "Plano",
    "Valor mensal",
    "Início",
    "Renovação",
    "Dias para renovar",
    "Origem",
    "Último contato",
    "Observações",
)

STATUS_LABELS: dict[CustomerStatus, str] = {
    CustomerStatus.ACTIVE: "Ativo",
    CustomerStatus.PAST_DUE: "Atrasado",
    CustomerStatus.CHURNED: "Cancelado",
    CustomerStatus.PROSPECT: "Prospect",
}


def to_csv_row(customer: Customer, *, today: date) -> list[Any]:
    """Linha de exportação CSV de um cliente."""
    days = (customer.renewal_date - today).days if customer.renewal_date else None
    return [
        customer.name,
        customer.email,
        format_phone_br(customer.phone),
        customer.document,
        STATUS_LABELS.get(customer.status, customer.status.value),
        customer.plan.name if customer.plan else None,
        customer.monthly_value,
        customer.start_date,
        customer.renewal_date,
        days,
        customer.source,
        customer.last_contact_at,
        customer.notes,
    ]
