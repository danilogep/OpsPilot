"""Serviço de auditoria: registro e consulta de ações relevantes."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequestContext
from app.core.pagination import Page, PageParams
from app.db.models import AuditEvent, User

#: Ações padronizadas (usar constantes evita divergência de nomes).
ACTION_LOGIN = "auth.login"
ACTION_LOGIN_FAILED = "auth.login_failed"
ACTION_IMPORT_UPLOAD = "import.upload"
ACTION_IMPORT_MAPPING = "import.mapping_updated"
ACTION_IMPORT_VALIDATE = "import.validated"
ACTION_IMPORT_COMMIT = "import.committed"
ACTION_CUSTOMER_CREATE = "customer.created"
ACTION_CUSTOMER_UPDATE = "customer.updated"
ACTION_CUSTOMER_DELETE = "customer.deleted"
ACTION_PLAN_CREATE = "plan.created"
ACTION_PLAN_UPDATE = "plan.updated"
ACTION_LEAD_CREATE = "lead.created"
ACTION_LEAD_UPDATE = "lead.updated"
ACTION_LEAD_SCORE = "lead.scored"
ACTION_RENEWAL_UPDATE = "renewal.updated"
ACTION_KNOWLEDGE_UPLOAD = "knowledge.uploaded"
ACTION_KNOWLEDGE_DELETE = "knowledge.deleted"
ACTION_AI_ASSISTANT = "ai.assistant_query"
ACTION_AI_AGENT_RUN = "ai.agent_run"
ACTION_AI_LEAD_CLASSIFY = "ai.lead_classified"
ACTION_AI_RENEWAL_SUMMARY = "ai.renewal_summary"
ACTION_AI_MESSAGE_DRAFT = "ai.message_drafted"
ACTION_WEBHOOK_INBOUND = "webhook.received"
ACTION_WEBHOOK_OUTBOUND = "webhook.sent"


async def record_audit(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    action: str,
    entity_type: str = "",
    entity_id: str | None = None,
    actor: User | None = None,
    actor_email: str | None = None,
    summary: str = "",
    meta: dict[str, Any] | None = None,
    context: RequestContext | None = None,
) -> AuditEvent:
    """Cria um evento de auditoria (sem commit — quem chama controla a transação)."""
    event = AuditEvent(
        organization_id=organization_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else None,
        actor_id=actor.id if actor else None,
        actor_email=(actor.email if actor else actor_email) or "system",
        actor_role=(actor.role.value if actor else "SYSTEM"),
        ip_address=context.ip_address if context else None,
        user_agent=context.user_agent if context else None,
        correlation_id=context.correlation_id if context else "",
        summary=summary[:300],
        meta=meta or {},
    )
    session.add(event)
    return event


def build_diff(
    before: dict[str, Any], after: dict[str, Any], *, fields: list[str] | None = None
) -> dict[str, Any]:
    """Monta o diff auditável entre dois estados, ignorando campos iguais."""
    keys = fields or sorted(set(before) | set(after))
    diff: dict[str, Any] = {}
    for key in keys:
        old, new = before.get(key), after.get(key)
        if old == new:
            continue
        diff[key] = {"before": _jsonable(old), "after": _jsonable(new)}
    return diff


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


def _apply_filters(
    stmt: Select[Any],
    *,
    action: str | None,
    entity_type: str | None,
    entity_id: str | None,
    actor_email: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> Select[Any]:
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if entity_type:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditEvent.entity_id == entity_id)
    if actor_email:
        stmt = stmt.where(AuditEvent.actor_email.ilike(f"%{actor_email}%"))
    if date_from:
        stmt = stmt.where(AuditEvent.created_at >= date_from)
    if date_to:
        stmt = stmt.where(AuditEvent.created_at <= date_to)
    return stmt


async def list_audit_events(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    params: PageParams,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    actor_email: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> tuple[list[AuditEvent], int]:
    """Lista eventos de auditoria da organização, mais recentes primeiro."""
    base = select(AuditEvent).where(AuditEvent.organization_id == organization_id)
    base = _apply_filters(
        base,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_email=actor_email,
        date_from=date_from,
        date_to=date_to,
    )
    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        (
            await session.execute(
                base.order_by(AuditEvent.created_at.desc())
                .offset(params.offset)
                .limit(params.page_size)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), int(total)


async def list_entity_history(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    limit: int = 50,
) -> list[AuditEvent]:
    """Histórico de alterações de uma entidade específica."""
    rows = (
        (
            await session.execute(
                select(AuditEvent)
                .where(
                    AuditEvent.organization_id == organization_id,
                    AuditEvent.entity_type == entity_type,
                    AuditEvent.entity_id == str(entity_id),
                )
                .order_by(AuditEvent.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


def to_page(events: list[AuditEvent], total: int, params: PageParams) -> Page[Any]:
    """Atalho para montar a página (schemas convertem via from_attributes)."""
    return Page.build(list(events), total, params)
