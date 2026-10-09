"""Rotas de clientes."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import ContextDep, RequireAnalyst, RequireViewer, SessionDep
from app.core.exporting import csv_response
from app.core.pagination import Page, PageParams, page_params
from app.db.base import utcnow
from app.db.models.enums import CustomerStatus
from app.domains.audit import service as audit_service
from app.domains.customers import service
from app.domains.customers.schemas import (
    CustomerCreate,
    CustomerHistoryEntry,
    CustomerRead,
    CustomerUpdate,
)

router = APIRouter(prefix="/customers", tags=["Clientes"])


def _filters(
    search: Annotated[
        str | None, Query(description="Busca por nome, e-mail, documento ou telefone")
    ] = None,
    status_filter: Annotated[
        list[CustomerStatus] | None, Query(alias="status", description="Situações")
    ] = None,
    plan_id: Annotated[uuid.UUID | None, Query(description="Filtra por plano")] = None,
    source: Annotated[str | None, Query(description="Filtra por origem")] = None,
    renewal_from: Annotated[date | None, Query(description="Renovação a partir de")] = None,
    renewal_to: Annotated[date | None, Query(description="Renovação até")] = None,
    renewal_within_days: Annotated[
        int | None, Query(ge=1, le=365, description="Renovações nos próximos N dias")
    ] = None,
    overdue_only: Annotated[bool, Query(description="Somente atrasados")] = False,
    without_contact_days: Annotated[
        int | None, Query(ge=1, le=3650, description="Sem contato há N dias")
    ] = None,
    has_email: Annotated[bool | None, Query(description="Com ou sem e-mail")] = None,
) -> service.CustomerFilters:
    """Dependência que agrupa os filtros da listagem."""
    return service.CustomerFilters(
        search=search,
        statuses=status_filter,
        plan_id=plan_id,
        source=source,
        renewal_from=renewal_from,
        renewal_to=renewal_to,
        renewal_within_days=renewal_within_days,
        overdue_only=overdue_only,
        without_contact_days=without_contact_days,
        has_email=has_email,
    )


FiltersDep = Annotated[service.CustomerFilters, Depends(_filters)]


@router.get("", response_model=Page[CustomerRead], summary="Listar clientes")
async def list_customers(
    session: SessionDep,
    user: RequireViewer,
    params: Annotated[PageParams, Depends(page_params)],
    filters: FiltersDep,
    sort: Annotated[str, Query(description="Campo de ordenação")] = service.DEFAULT_SORT,
    direction: Annotated[str, Query(pattern="^(asc|desc)$")] = "asc",
) -> Page[CustomerRead]:
    """Lista clientes com busca, filtros, ordenação e paginação."""
    customers, total = await service.list_customers(
        session,
        organization_id=user.organization_id,
        params=params,
        filters=filters,
        sort=sort,
        direction=direction,
    )
    today = utcnow().date()
    return Page.build(
        [service.to_read(customer, today=today) for customer in customers], total, params
    )


@router.get("/export", summary="Exportar clientes em CSV")
async def export_customers(
    session: SessionDep, user: RequireViewer, filters: FiltersDep
) -> Response:
    """Exporta a listagem filtrada em CSV (separador ';', compatível com Excel)."""
    customers = await service.iter_all_customers(
        session, organization_id=user.organization_id, filters=filters
    )
    today = utcnow().date()
    return csv_response(
        filename=f"clientes-{today.isoformat()}.csv",
        headers=service.CSV_HEADERS,
        rows=[service.to_csv_row(customer, today=today) for customer in customers],
    )


@router.post(
    "",
    response_model=CustomerRead,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar cliente",
)
async def create_customer(
    payload: CustomerCreate, session: SessionDep, user: RequireAnalyst, context: ContextDep
) -> CustomerRead:
    """Cadastra um cliente manualmente."""
    customer = await service.create_customer(
        session,
        organization_id=user.organization_id,
        payload=payload,
        actor=user,
        context=context,
    )
    return service.to_read(customer)


@router.get("/{customer_id}", response_model=CustomerRead, summary="Detalhe do cliente")
async def get_customer(
    customer_id: uuid.UUID, session: SessionDep, user: RequireViewer
) -> CustomerRead:
    """Retorna um cliente da organização."""
    customer = await service.get_customer(
        session, organization_id=user.organization_id, customer_id=customer_id
    )
    return service.to_read(customer)


@router.patch("/{customer_id}", response_model=CustomerRead, summary="Atualizar cliente")
async def update_customer(
    customer_id: uuid.UUID,
    payload: CustomerUpdate,
    session: SessionDep,
    user: RequireAnalyst,
    context: ContextDep,
) -> CustomerRead:
    """Atualiza os dados de um cliente."""
    customer = await service.update_customer(
        session,
        organization_id=user.organization_id,
        customer_id=customer_id,
        payload=payload,
        actor=user,
        context=context,
    )
    return service.to_read(customer)


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Excluir cliente")
async def delete_customer(
    customer_id: uuid.UUID, session: SessionDep, user: RequireAnalyst, context: ContextDep
) -> None:
    """Exclusão lógica do cliente."""
    await service.delete_customer(
        session,
        organization_id=user.organization_id,
        customer_id=customer_id,
        actor=user,
        context=context,
    )


@router.post(
    "/{customer_id}/contact",
    response_model=CustomerRead,
    summary="Registrar contato com o cliente",
)
async def register_contact(
    customer_id: uuid.UUID,
    session: SessionDep,
    user: RequireAnalyst,
    context: ContextDep,
    note: Annotated[str | None, Query(max_length=300)] = None,
) -> CustomerRead:
    """Atualiza a data do último contato."""
    customer = await service.register_contact(
        session,
        organization_id=user.organization_id,
        customer_id=customer_id,
        actor=user,
        note=note,
        context=context,
    )
    return service.to_read(customer)


@router.get(
    "/{customer_id}/history",
    response_model=list[CustomerHistoryEntry],
    summary="Histórico de alterações",
)
async def customer_history(
    customer_id: uuid.UUID, session: SessionDep, user: RequireViewer
) -> list[CustomerHistoryEntry]:
    """Lista as alterações auditadas do cliente, mais recentes primeiro."""
    await service.get_customer(
        session, organization_id=user.organization_id, customer_id=customer_id
    )
    events = await audit_service.list_entity_history(
        session,
        organization_id=user.organization_id,
        entity_type="customer",
        entity_id=customer_id,
    )
    return [CustomerHistoryEntry.model_validate(event) for event in events]
