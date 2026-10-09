"""Serviço de integrações: recepção e publicação de eventos.

Contrato de entrada (n8n → OpsPilot):

* ``X-OpsPilot-Signature``: ``sha256=<hmac-sha256 do corpo bruto>``;
* ``X-OpsPilot-Idempotency-Key``: identificador único do evento;
* ``X-OpsPilot-Organization``: slug da organização (opcional quando existe uma só).

Regras: assinatura inválida é rejeitada com 401 e registrada; chave repetida
devolve 200 com ``duplicate: true`` sem reprocessar; qualquer falha de
processamento é registrada no evento sem vazar detalhes internos.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AuthenticationError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.pagination import PageParams
from app.db.base import utcnow
from app.db.models import (
    Customer,
    Organization,
    Renewal,
    User,
    UserRole,
    WebhookDirection,
    WebhookEvent,
    WebhookStatus,
)
from app.domains.audit import service as audit_service
from app.domains.integrations.schemas import (
    InboundLeadPayload,
    InboundRenewalPayload,
    IntegrationStatus,
    WebhookAck,
)
from app.domains.leads import service as leads_service
from app.domains.leads.schemas import LeadCreate
from app.integrations.webhooks import dispatcher
from app.integrations.webhooks.signature import (
    EVENT_HEADER,
    IDEMPOTENCY_HEADER,
    SIGNATURE_HEADER,
    verify_signature,
)

logger = get_logger(__name__)

ORGANIZATION_HEADER = "X-OpsPilot-Organization"

EVENT_LEAD_CREATED = "lead.created"
EVENT_RENEWAL_UPDATED = "renewal.updated"


async def resolve_organization(session: AsyncSession, *, slug: str | None) -> Organization:
    """Resolve a organização do evento pelo slug ou pela única existente."""
    if slug:
        result = await session.execute(
            select(Organization).where(Organization.slug == slug.strip().lower())
        )
        organization: Organization | None = result.scalars().unique().first()
        if organization is None:
            raise NotFoundError(
                "Organização não encontrada para o slug informado.",
                details={"header": ORGANIZATION_HEADER},
            )
        return organization

    rows = (await session.execute(select(Organization).limit(2))).scalars().unique().all()
    if not rows:
        raise NotFoundError("Nenhuma organização cadastrada.")
    if len(rows) > 1:
        raise ValidationError(
            "Informe a organização no cabeçalho para ambientes com mais de um tenant.",
            details={"header": ORGANIZATION_HEADER},
        )
    return rows[0]


async def _webhook_actor(session: AsyncSession, *, organization_id: uuid.UUID) -> User | None:
    """Usuário técnico usado para atribuir as ações do webhook."""
    result = await session.execute(
        select(User)
        .where(
            User.organization_id == organization_id,
            User.role.in_([UserRole.ADMIN, UserRole.ANALYST]),
            User.deleted_at.is_(None),
        )
        .order_by(User.role)
    )
    actor: User | None = result.scalars().unique().first()
    return actor


def ensure_signature(raw_body: bytes, signature: str | None) -> None:
    """Valida a assinatura HMAC do corpo bruto."""
    if not verify_signature(raw_body, settings.webhook_secret, signature):
        raise AuthenticationError(
            "Assinatura do webhook inválida ou ausente.",
            details={"header": SIGNATURE_HEADER},
        )


async def _find_duplicate(
    session: AsyncSession, *, organization_id: uuid.UUID, idempotency_key: str
) -> WebhookEvent | None:
    result = await session.execute(
        select(WebhookEvent).where(
            WebhookEvent.organization_id == organization_id,
            WebhookEvent.direction == WebhookDirection.INBOUND,
            WebhookEvent.idempotency_key == idempotency_key,
        )
    )
    event: WebhookEvent | None = result.scalars().unique().first()
    return event


async def receive_lead(
    session: AsyncSession,
    *,
    organization: Organization,
    payload: InboundLeadPayload,
    raw_body: bytes,
    signature: str | None,
    idempotency_key: str | None,
) -> WebhookAck:
    """Processa um lead recebido por webhook."""
    ensure_signature(raw_body, signature)
    key = (idempotency_key or "").strip() or f"lead-{uuid.uuid4().hex}"

    duplicate = await _find_duplicate(session, organization_id=organization.id, idempotency_key=key)
    if duplicate is not None:
        logger.info("webhook_duplicate", event_type=EVENT_LEAD_CREATED, key=key)
        return WebhookAck(
            received=True,
            event_id=duplicate.id,
            status=WebhookStatus.DUPLICATE,
            idempotency_key=key,
            message="Evento já processado anteriormente.",
            entity_id=(
                uuid.UUID(duplicate.response["lead_id"])
                if duplicate.response.get("lead_id")
                else None
            ),
            duplicate=True,
        )

    event = WebhookEvent(
        organization_id=organization.id,
        direction=WebhookDirection.INBOUND,
        event_type=EVENT_LEAD_CREATED,
        idempotency_key=key,
        signature_valid=True,
        status=WebhookStatus.RECEIVED,
        attempts=1,
        payload=payload.model_dump(mode="json"),
    )
    session.add(event)
    await session.flush()

    actor = await _webhook_actor(session, organization_id=organization.id)
    try:
        lead = await leads_service.create_lead(
            session,
            organization_id=organization.id,
            payload=LeadCreate(
                name=payload.name,
                company=payload.company,
                email=payload.email,
                phone=payload.phone,
                source=payload.source,
                segment=payload.segment,
                company_size=payload.company_size,
                interest=payload.interest,
                estimated_value=payload.estimated_value,
                notes=payload.notes,
                last_interaction_at=utcnow(),
            ),
            actor=actor,
            source_label="webhook n8n",
        )
    except Exception as exc:  # falha de negócio não deve derrubar a integração
        event.status = WebhookStatus.FAILED
        event.error = type(exc).__name__
        await session.commit()
        logger.warning("webhook_lead_failed", error=type(exc).__name__)
        raise

    event.status = WebhookStatus.PROCESSED
    event.processed_at = utcnow()
    event.response = {
        "lead_id": str(lead.id),
        "score": lead.score,
        "category": lead.score_category.value,
    }
    await audit_service.record_audit(
        session,
        organization_id=organization.id,
        action=audit_service.ACTION_WEBHOOK_INBOUND,
        entity_type="lead",
        entity_id=str(lead.id),
        actor=actor,
        actor_email="webhook@n8n",
        summary=f"Lead {lead.name} criado por webhook (score {lead.score}).",
        meta={"event_type": EVENT_LEAD_CREATED, "idempotency_key": key},
    )
    await session.commit()
    logger.info("webhook_lead_processed", lead_id=str(lead.id), score=lead.score)

    return WebhookAck(
        received=True,
        event_id=event.id,
        status=WebhookStatus.PROCESSED,
        idempotency_key=key,
        message=f"Lead criado com score {lead.score} ({lead.score_category.value}).",
        entity_id=lead.id,
    )


async def receive_renewal(
    session: AsyncSession,
    *,
    organization: Organization,
    payload: InboundRenewalPayload,
    raw_body: bytes,
    signature: str | None,
    idempotency_key: str | None,
) -> WebhookAck:
    """Processa um evento de renovação recebido por webhook."""
    ensure_signature(raw_body, signature)
    key = (idempotency_key or "").strip() or f"renewal-{uuid.uuid4().hex}"

    duplicate = await _find_duplicate(session, organization_id=organization.id, idempotency_key=key)
    if duplicate is not None:
        return WebhookAck(
            received=True,
            event_id=duplicate.id,
            status=WebhookStatus.DUPLICATE,
            idempotency_key=key,
            message="Evento já processado anteriormente.",
            duplicate=True,
        )

    event = WebhookEvent(
        organization_id=organization.id,
        direction=WebhookDirection.INBOUND,
        event_type=EVENT_RENEWAL_UPDATED,
        idempotency_key=key,
        signature_valid=True,
        status=WebhookStatus.RECEIVED,
        attempts=1,
        payload=payload.model_dump(mode="json"),
    )
    session.add(event)
    await session.flush()

    stmt = select(Customer).where(
        Customer.organization_id == organization.id, Customer.deleted_at.is_(None)
    )
    if payload.customer_email:
        stmt = stmt.where(func.lower(Customer.email) == payload.customer_email)
    elif payload.customer_name:
        stmt = stmt.where(Customer.name.ilike(f"%{payload.customer_name}%"))
    else:
        event.status = WebhookStatus.FAILED
        event.error = "Payload sem identificação do cliente."
        await session.commit()
        raise ValidationError("Informe customer_email ou customer_name.")

    customer: Customer | None = (await session.execute(stmt.limit(1))).scalars().unique().first()
    if customer is None:
        event.status = WebhookStatus.FAILED
        event.error = "Cliente não encontrado."
        await session.commit()
        raise NotFoundError("Cliente não encontrado para o evento de renovação.")

    existing = (
        (
            await session.execute(
                select(Renewal).where(
                    Renewal.organization_id == organization.id,
                    Renewal.customer_id == customer.id,
                    Renewal.due_date == payload.due_date,
                )
            )
        )
        .scalars()
        .unique()
        .first()
    )

    created = existing is None
    renewal = existing or Renewal(
        organization_id=organization.id,
        customer_id=customer.id,
        plan_id=customer.plan_id,
        due_date=payload.due_date,
    )
    renewal.amount = payload.amount or customer.monthly_value or Decimal("0.00")
    renewal.status = payload.status
    renewal.notes = payload.notes or renewal.notes
    if created:
        session.add(renewal)
    customer.renewal_date = payload.due_date
    await session.flush()

    actor = await _webhook_actor(session, organization_id=organization.id)
    event.status = WebhookStatus.PROCESSED
    event.processed_at = utcnow()
    event.response = {
        "renewal_id": str(renewal.id),
        "customer_id": str(customer.id),
        "created": created,
    }
    await audit_service.record_audit(
        session,
        organization_id=organization.id,
        action=audit_service.ACTION_WEBHOOK_INBOUND,
        entity_type="renewal",
        entity_id=str(renewal.id),
        actor=actor,
        actor_email="webhook@n8n",
        summary=(
            f"Renovação de {customer.name} {'criada' if created else 'atualizada'} por webhook."
        ),
        meta={"event_type": EVENT_RENEWAL_UPDATED, "idempotency_key": key},
    )
    await session.commit()

    return WebhookAck(
        received=True,
        event_id=event.id,
        status=WebhookStatus.PROCESSED,
        idempotency_key=key,
        message=(
            f"Renovação {'criada' if created else 'atualizada'} para {customer.name} "
            f"em {payload.due_date:%d/%m/%Y}."
        ),
        entity_id=renewal.id,
    )


async def list_events(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    params: PageParams,
    direction: WebhookDirection | None = None,
    event_type: str | None = None,
) -> tuple[list[WebhookEvent], int]:
    """Lista os eventos de webhook da organização."""
    base = select(WebhookEvent).where(WebhookEvent.organization_id == organization_id)
    if direction is not None:
        base = base.where(WebhookEvent.direction == direction)
    if event_type:
        base = base.where(WebhookEvent.event_type == event_type)
    total = int(
        (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    )
    rows = (
        (
            await session.execute(
                base.order_by(WebhookEvent.created_at.desc())
                .offset(params.offset)
                .limit(params.page_size)
            )
        )
        .scalars()
        .unique()
        .all()
    )
    return list(rows), total


async def status(session: AsyncSession, *, organization_id: uuid.UUID) -> IntegrationStatus:
    """Situação das integrações e contadores por direção."""
    rows = (
        await session.execute(
            select(WebhookEvent.direction, WebhookEvent.status, func.count())
            .where(WebhookEvent.organization_id == organization_id)
            .group_by(WebhookEvent.direction, WebhookEvent.status)
        )
    ).all()
    totals: dict[str, int] = {}
    for direction, event_status, count in rows:
        totals[f"{direction.value.lower()}_{event_status.value.lower()}"] = int(count)
    totals["total"] = sum(int(row[2]) for row in rows)

    return IntegrationStatus(
        inbound_signature_required=True,
        signature_header=SIGNATURE_HEADER,
        idempotency_header=IDEMPOTENCY_HEADER,
        event_header=EVENT_HEADER,
        organization_header=ORGANIZATION_HEADER,
        outbound_url_configured=bool(settings.webhook_outbound_url),
        outbound_url=settings.webhook_outbound_url or None,
        inbound_endpoints=[
            {
                "event": EVENT_LEAD_CREATED,
                "method": "POST",
                "path": f"{settings.api_v1_prefix}/integrations/webhooks/leads",
                "description": "Cria um lead e calcula o score determinístico.",
            },
            {
                "event": EVENT_RENEWAL_UPDATED,
                "method": "POST",
                "path": f"{settings.api_v1_prefix}/integrations/webhooks/renewals",
                "description": "Cria ou atualiza a renovação de um cliente existente.",
            },
        ],
        outbound_events=[
            {
                "event": dispatcher.EVENT_IMPORT_COMPLETED,
                "description": "Disparado após confirmar uma importação.",
            },
            {
                "event": dispatcher.EVENT_LEAD_CLASSIFIED,
                "description": "Disparado após classificar um lead com IA.",
            },
            {
                "event": dispatcher.EVENT_RENEWAL_ALERT,
                "description": "Disparado manualmente para testar a automação de renovações.",
            },
        ],
        totals=totals,
    )


async def send_test_event(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_type: str,
    payload: dict[str, Any],
    target_url: str | None,
    actor: User,
) -> WebhookEvent:
    """Publica um evento de saída para validar a automação."""
    event = await dispatcher.dispatch_event(
        session,
        organization_id=organization_id,
        event_type=event_type,
        payload=payload or {"message": "Evento de teste do OpsPilot", "demo": True},
        target_url=target_url,
    )
    await audit_service.record_audit(
        session,
        organization_id=organization_id,
        action=audit_service.ACTION_WEBHOOK_OUTBOUND,
        entity_type="webhook_event",
        entity_id=str(event.id),
        actor=actor,
        summary=f"Evento de saída {event_type} ({event.status.value}).",
        meta={"target_url": event.target_url, "status": event.status.value},
    )
    await session.commit()
    return event


def upcoming_renewal_alert_payload(
    session: AsyncSession, *, organization_id: uuid.UUID
) -> dict[str, Any]:
    """Payload de exemplo do alerta de renovação (documentação e testes)."""
    del session, organization_id
    return {
        "window_days": 7,
        "generated_at": utcnow().isoformat(),
        "example": True,
        "renewals": [
            {
                "customer_name": "Padaria Aurora Ltda",
                "due_date": (utcnow().date() + timedelta(days=3)).isoformat(),
                "amount": "199.00",
            }
        ],
    }
