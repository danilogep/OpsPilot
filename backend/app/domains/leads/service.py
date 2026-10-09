"""Serviço de leads: CRUD, score determinístico, eventos e indicadores."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequestContext
from app.core.errors import NotFoundError, ValidationError
from app.core.pagination import PageParams
from app.db.base import ensure_utc, utcnow
from app.db.models import (
    Lead,
    LeadCategory,
    LeadEvent,
    LeadEventType,
    LeadStatus,
    ScoringMethod,
    User,
)
from app.domains.audit import service as audit_service
from app.domains.imports.normalizers import format_phone_br
from app.domains.leads.schemas import (
    LeadCreate,
    LeadFunnelStage,
    LeadIndicators,
    LeadRead,
    LeadSourceSummary,
    LeadUpdate,
)
from app.domains.leads.scoring import LeadScoreInput, ScoreResult, score_lead

#: Score mínimo para considerar o lead de alta prioridade.
HIGH_PRIORITY_SCORE = 70

STATUS_LABELS: dict[LeadStatus, str] = {
    LeadStatus.NEW: "Novo",
    LeadStatus.CONTACTED: "Contatado",
    LeadStatus.QUALIFIED: "Qualificado",
    LeadStatus.PROPOSAL: "Proposta",
    LeadStatus.WON: "Ganho",
    LeadStatus.LOST: "Perdido",
}
OPEN_STATUSES = (
    LeadStatus.NEW,
    LeadStatus.CONTACTED,
    LeadStatus.QUALIFIED,
    LeadStatus.PROPOSAL,
)

SORTABLE_COLUMNS: dict[str, Any] = {
    "score": Lead.score,
    "name": Lead.name,
    "estimated_value": Lead.estimated_value,
    "status": Lead.status,
    "created_at": Lead.created_at,
    "last_interaction_at": Lead.last_interaction_at,
}


@dataclass(slots=True)
class LeadFilters:
    """Filtros da listagem de leads."""

    search: str | None = None
    statuses: list[LeadStatus] | None = None
    categories: list[LeadCategory] | None = None
    source: str | None = None
    segment: str | None = None
    min_score: int | None = None
    only_open: bool = False
    stale_days: int | None = None


def _base_query(organization_id: uuid.UUID) -> Select[Any]:
    return select(Lead).where(Lead.organization_id == organization_id, Lead.deleted_at.is_(None))


def apply_filters(stmt: Select[Any], filters: LeadFilters) -> Select[Any]:
    """Aplica os filtros à query de leads."""
    if filters.search:
        term = f"%{filters.search.strip()}%"
        stmt = stmt.where(
            or_(Lead.name.ilike(term), Lead.company.ilike(term), Lead.email.ilike(term))
        )
    if filters.statuses:
        stmt = stmt.where(Lead.status.in_(filters.statuses))
    if filters.categories:
        stmt = stmt.where(Lead.score_category.in_(filters.categories))
    if filters.source:
        stmt = stmt.where(Lead.source == filters.source)
    if filters.segment:
        stmt = stmt.where(Lead.segment == filters.segment)
    if filters.min_score is not None:
        stmt = stmt.where(Lead.score >= filters.min_score)
    if filters.only_open:
        stmt = stmt.where(Lead.status.in_(OPEN_STATUSES))
    if filters.stale_days is not None:
        cutoff = utcnow() - timedelta(days=filters.stale_days)
        stmt = stmt.where(
            or_(Lead.last_interaction_at.is_(None), Lead.last_interaction_at < cutoff)
        )
    return stmt


async def list_leads(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    params: PageParams,
    filters: LeadFilters,
    sort: str = "score",
    direction: str = "desc",
) -> tuple[list[Lead], int]:
    """Lista leads com filtros, ordenação e paginação."""
    base = apply_filters(_base_query(organization_id), filters)
    total = int(
        (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    )
    column = SORTABLE_COLUMNS.get(sort)
    if column is None:
        raise ValidationError(
            "Campo de ordenação inválido.", details={"allowed": sorted(SORTABLE_COLUMNS)}
        )
    order = column.desc() if direction.lower() == "desc" else column.asc()
    rows = (
        (
            await session.execute(
                base.order_by(order, Lead.id).offset(params.offset).limit(params.page_size)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), total


async def get_lead(
    session: AsyncSession, *, organization_id: uuid.UUID, lead_id: uuid.UUID
) -> Lead:
    """Busca um lead da organização ou falha com 404."""
    result = await session.execute(_base_query(organization_id).where(Lead.id == lead_id))
    lead: Lead | None = result.scalar_one_or_none()
    if lead is None:
        raise NotFoundError("Lead não encontrado.")
    return lead


def score_input(lead: Lead) -> LeadScoreInput:
    """Monta a entrada do score a partir do modelo."""
    return LeadScoreInput(
        email=lead.email,
        phone=lead.phone,
        segment=lead.segment,
        company_size=lead.company_size,
        interest=lead.interest,
        estimated_value=lead.estimated_value,
        source=lead.source,
        last_interaction_at=lead.last_interaction_at,
    )


def apply_score(lead: Lead, result: ScoreResult, *, method: ScoringMethod) -> None:
    """Grava o resultado do score no lead."""
    lead.score = result.score
    lead.score_category = result.category
    lead.score_reasons = result.reasons_as_dicts()
    lead.score_method = method
    lead.score_version = result.version
    lead.scored_at = utcnow()
    lead.next_step = result.next_step
    lead.risks = result.risks


async def add_event(
    session: AsyncSession,
    *,
    lead: Lead,
    event_type: LeadEventType,
    description: str,
    payload: dict[str, Any] | None = None,
    actor: User | None = None,
) -> LeadEvent:
    """Registra um evento no histórico do lead."""
    event = LeadEvent(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        event_type=event_type,
        description=description[:400],
        payload=payload or {},
        created_by_id=actor.id if actor else None,
    )
    session.add(event)
    return event


async def create_lead(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    payload: LeadCreate,
    actor: User | None = None,
    context: RequestContext | None = None,
    source_label: str = "cadastro manual",
) -> Lead:
    """Cria um lead e calcula o score determinístico imediatamente."""
    lead = Lead(
        organization_id=organization_id,
        name=payload.name.strip(),
        company=payload.company,
        email=payload.email,
        phone=payload.phone,
        source=payload.source or "indefinido",
        segment=payload.segment,
        company_size=payload.company_size,
        interest=payload.interest,
        status=payload.status,
        estimated_value=payload.estimated_value,
        probability=payload.probability,
        notes=payload.notes,
        last_interaction_at=payload.last_interaction_at,
    )
    result = score_lead(
        LeadScoreInput(
            email=lead.email,
            phone=lead.phone,
            segment=lead.segment,
            company_size=lead.company_size,
            interest=lead.interest,
            estimated_value=lead.estimated_value,
            source=lead.source,
            last_interaction_at=lead.last_interaction_at,
        )
    )
    apply_score(lead, result, method=ScoringMethod.RULES)
    session.add(lead)
    await session.flush()

    await add_event(
        session,
        lead=lead,
        event_type=LeadEventType.CREATED,
        description=f"Lead criado ({source_label}) com origem {lead.source}.",
        payload={"source": lead.source, "segment": lead.segment},
        actor=actor,
    )
    await add_event(
        session,
        lead=lead,
        event_type=LeadEventType.SCORED,
        description=f"Score {result.score} ({result.category.value}) por regras {result.version}.",
        payload={"score": result.score, "category": result.category.value},
        actor=actor,
    )
    await audit_service.record_audit(
        session,
        organization_id=organization_id,
        action=audit_service.ACTION_LEAD_CREATE,
        entity_type="lead",
        entity_id=str(lead.id),
        actor=actor,
        actor_email=None if actor else "webhook",
        summary=f"Lead {lead.name} criado ({source_label}).",
        meta={"score": result.score, "category": result.category.value},
        context=context,
    )
    await session.commit()
    await session.refresh(lead)
    return lead


def snapshot(lead: Lead) -> dict[str, Any]:
    """Estado auditável do lead."""
    return {
        "name": lead.name,
        "company": lead.company,
        "email": lead.email,
        "phone": lead.phone,
        "source": lead.source,
        "segment": lead.segment,
        "company_size": lead.company_size.value,
        "interest": lead.interest,
        "status": lead.status.value,
        "estimated_value": str(lead.estimated_value),
        "probability": lead.probability,
        "notes": lead.notes,
    }


async def update_lead(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    lead_id: uuid.UUID,
    payload: LeadUpdate,
    actor: User,
    context: RequestContext | None = None,
) -> Lead:
    """Atualiza o lead, recalcula o score e registra os eventos."""
    lead = await get_lead(session, organization_id=organization_id, lead_id=lead_id)
    before = snapshot(lead)
    previous_status = lead.status
    data = payload.model_dump(exclude_unset=True)
    for attribute, value in data.items():
        setattr(lead, attribute, value)

    result = score_lead(score_input(lead))
    apply_score(lead, result, method=ScoringMethod.RULES)

    diff = audit_service.build_diff(before, snapshot(lead))
    if previous_status is not lead.status:
        await add_event(
            session,
            lead=lead,
            event_type=LeadEventType.STATUS_CHANGED,
            description=(
                f"Status alterado de {STATUS_LABELS[previous_status]} "
                f"para {STATUS_LABELS[lead.status]}."
            ),
            payload={"from": previous_status.value, "to": lead.status.value},
            actor=actor,
        )
    if diff:
        await add_event(
            session,
            lead=lead,
            event_type=LeadEventType.UPDATED,
            description="Dados do lead atualizados.",
            payload={"changes": diff},
            actor=actor,
        )
        await audit_service.record_audit(
            session,
            organization_id=organization_id,
            action=audit_service.ACTION_LEAD_UPDATE,
            entity_type="lead",
            entity_id=str(lead.id),
            actor=actor,
            summary=f"Lead {lead.name} atualizado.",
            meta={"changes": diff},
            context=context,
        )
    await session.commit()
    await session.refresh(lead)
    return lead


async def rescore_lead(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    lead_id: uuid.UUID,
    actor: User,
    context: RequestContext | None = None,
) -> tuple[Lead, ScoreResult]:
    """Recalcula o score determinístico e registra a execução."""
    lead = await get_lead(session, organization_id=organization_id, lead_id=lead_id)
    result = score_lead(score_input(lead))
    apply_score(lead, result, method=ScoringMethod.RULES)
    await add_event(
        session,
        lead=lead,
        event_type=LeadEventType.SCORED,
        description=f"Score recalculado: {result.score} ({result.category.value}).",
        payload={
            "score": result.score,
            "category": result.category.value,
            "version": result.version,
        },
        actor=actor,
    )
    await audit_service.record_audit(
        session,
        organization_id=organization_id,
        action=audit_service.ACTION_LEAD_SCORE,
        entity_type="lead",
        entity_id=str(lead.id),
        actor=actor,
        summary=f"Score do lead {lead.name}: {result.score} ({result.category.value}).",
        meta={"method": "rules", "version": result.version},
        context=context,
    )
    await session.commit()
    await session.refresh(lead)
    return lead, result


async def add_note(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    lead_id: uuid.UUID,
    note: str,
    mark_as_contacted: bool,
    actor: User | None = None,
    context: RequestContext | None = None,
) -> Lead:
    """Adiciona uma nota ao histórico do lead."""
    lead = await get_lead(session, organization_id=organization_id, lead_id=lead_id)
    await add_event(
        session,
        lead=lead,
        event_type=LeadEventType.CONTACTED if mark_as_contacted else LeadEventType.NOTE,
        description=note[:400],
        payload={"note": note},
        actor=actor,
    )
    if mark_as_contacted:
        lead.last_interaction_at = utcnow()
        if lead.status is LeadStatus.NEW:
            lead.status = LeadStatus.CONTACTED
        result = score_lead(score_input(lead))
        apply_score(lead, result, method=ScoringMethod.RULES)
    await audit_service.record_audit(
        session,
        organization_id=organization_id,
        action="lead.note_added",
        entity_type="lead",
        entity_id=str(lead.id),
        actor=actor,
        actor_email=None if actor else "agent",
        summary=f"Nota registrada no lead {lead.name}.",
        context=context,
    )
    await session.commit()
    await session.refresh(lead)
    return lead


async def list_events(
    session: AsyncSession, *, organization_id: uuid.UUID, lead_id: uuid.UUID, limit: int = 50
) -> list[LeadEvent]:
    """Histórico de eventos do lead, mais recentes primeiro."""
    rows = (
        (
            await session.execute(
                select(LeadEvent)
                .where(
                    LeadEvent.organization_id == organization_id,
                    LeadEvent.lead_id == lead_id,
                )
                .order_by(LeadEvent.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def delete_lead(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    lead_id: uuid.UUID,
    actor: User,
    context: RequestContext | None = None,
) -> None:
    """Exclusão lógica do lead."""
    lead = await get_lead(session, organization_id=organization_id, lead_id=lead_id)
    lead.deleted_at = utcnow()
    await audit_service.record_audit(
        session,
        organization_id=organization_id,
        action="lead.deleted",
        entity_type="lead",
        entity_id=str(lead.id),
        actor=actor,
        summary=f"Lead {lead.name} excluído.",
        context=context,
    )
    await session.commit()


async def indicators(session: AsyncSession, *, organization_id: uuid.UUID) -> LeadIndicators:
    """Indicadores agregados de leads, calculados no banco."""
    base = _base_query(organization_id).subquery()
    thirty_days_ago = utcnow() - timedelta(days=30)

    total = int((await session.execute(select(func.count()).select_from(base))).scalar_one())
    open_leads = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Lead)
                .where(
                    Lead.organization_id == organization_id,
                    Lead.deleted_at.is_(None),
                    Lead.status.in_(OPEN_STATUSES),
                )
            )
        ).scalar_one()
    )
    high_priority = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Lead)
                .where(
                    Lead.organization_id == organization_id,
                    Lead.deleted_at.is_(None),
                    Lead.status.in_(OPEN_STATUSES),
                    Lead.score >= HIGH_PRIORITY_SCORE,
                )
            )
        ).scalar_one()
    )
    won = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Lead)
                .where(
                    Lead.organization_id == organization_id,
                    Lead.deleted_at.is_(None),
                    Lead.status == LeadStatus.WON,
                    Lead.updated_at >= thirty_days_ago,
                )
            )
        ).scalar_one()
    )
    lost = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Lead)
                .where(
                    Lead.organization_id == organization_id,
                    Lead.deleted_at.is_(None),
                    Lead.status == LeadStatus.LOST,
                    Lead.updated_at >= thirty_days_ago,
                )
            )
        ).scalar_one()
    )
    pipeline = Decimal(
        (
            await session.execute(
                select(func.coalesce(func.sum(Lead.estimated_value), 0)).where(
                    Lead.organization_id == organization_id,
                    Lead.deleted_at.is_(None),
                    Lead.status.in_(OPEN_STATUSES),
                )
            )
        ).scalar_one()
        or 0
    ).quantize(Decimal("0.01"))
    average = float(
        (
            await session.execute(
                select(func.coalesce(func.avg(Lead.score), 0)).where(
                    Lead.organization_id == organization_id, Lead.deleted_at.is_(None)
                )
            )
        ).scalar_one()
        or 0
    )

    funnel_rows = (
        await session.execute(
            select(
                Lead.status,
                func.count(),
                func.coalesce(func.sum(Lead.estimated_value), 0),
            )
            .where(Lead.organization_id == organization_id, Lead.deleted_at.is_(None))
            .group_by(Lead.status)
        )
    ).all()
    by_status = {row[0]: (int(row[1]), Decimal(row[2] or 0)) for row in funnel_rows}
    funnel = [
        LeadFunnelStage(
            status=status,
            label=STATUS_LABELS[status],
            total=by_status.get(status, (0, Decimal("0")))[0],
            estimated_value=by_status.get(status, (0, Decimal("0")))[1].quantize(Decimal("0.01")),
        )
        for status in LeadStatus
    ]

    source_rows = (
        await session.execute(
            select(
                Lead.source,
                func.count(),
                func.coalesce(func.sum(Lead.estimated_value), 0),
                func.coalesce(func.avg(Lead.score), 0),
                func.coalesce(func.sum(case((Lead.score >= HIGH_PRIORITY_SCORE, 1), else_=0)), 0),
            )
            .where(Lead.organization_id == organization_id, Lead.deleted_at.is_(None))
            .group_by(Lead.source)
            .order_by(func.count().desc())
        )
    ).all()
    by_source = [
        LeadSourceSummary(
            source=row[0],
            total=int(row[1]),
            high_priority=int(row[4] or 0),
            estimated_value=Decimal(row[2] or 0).quantize(Decimal("0.01")),
            average_score=round(float(row[3] or 0), 1),
        )
        for row in source_rows
    ]

    return LeadIndicators(
        total=total,
        open_leads=open_leads,
        high_priority=high_priority,
        won_last_30_days=won,
        lost_last_30_days=lost,
        estimated_pipeline=pipeline,
        average_score=round(average, 1),
        funnel=funnel,
        by_source=by_source,
    )


def to_read(lead: Lead) -> LeadRead:
    """Converte o lead em schema com campos derivados."""
    data = LeadRead.model_validate(lead)
    data.phone_formatted = format_phone_br(lead.phone)
    interaction = ensure_utc(lead.last_interaction_at)
    if interaction:
        data.days_since_interaction = (utcnow() - interaction).days
    return data


CSV_HEADERS = (
    "Nome",
    "Empresa",
    "E-mail",
    "Telefone",
    "Origem",
    "Segmento",
    "Porte",
    "Interesse",
    "Status",
    "Valor estimado",
    "Score",
    "Categoria",
    "Próximo passo",
    "Última interação",
)

CATEGORY_LABELS: dict[LeadCategory, str] = {
    LeadCategory.HOT: "Alta prioridade",
    LeadCategory.WARM: "Média prioridade",
    LeadCategory.COLD: "Baixa prioridade",
}


def to_csv_row(lead: Lead, *, today: date | None = None) -> list[Any]:
    """Linha de exportação CSV de um lead."""
    return [
        lead.name,
        lead.company,
        lead.email,
        format_phone_br(lead.phone),
        lead.source,
        lead.segment,
        lead.company_size.value,
        lead.interest,
        STATUS_LABELS.get(lead.status, lead.status.value),
        lead.estimated_value,
        lead.score,
        CATEGORY_LABELS.get(lead.score_category, lead.score_category.value),
        lead.next_step,
        lead.last_interaction_at,
    ]
