"""Rotas de integrações (webhooks de entrada e saída)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request

from app.api.deps import RequireAdmin, RequireViewer, SessionDep
from app.core.errors import ValidationError
from app.core.pagination import Page, PageParams, page_params
from app.db.models.enums import WebhookDirection
from app.domains.integrations import service
from app.domains.integrations.schemas import (
    InboundLeadPayload,
    InboundRenewalPayload,
    IntegrationStatus,
    OutboundTestRequest,
    WebhookAck,
    WebhookEventRead,
)
from app.integrations.webhooks.signature import IDEMPOTENCY_HEADER, SIGNATURE_HEADER

router = APIRouter(prefix="/integrations", tags=["Integrações"])

SignatureHeader = Annotated[
    str | None,
    Header(alias=SIGNATURE_HEADER, description="HMAC-SHA256 do corpo bruto (sha256=...)"),
]
IdempotencyHeader = Annotated[
    str | None, Header(alias=IDEMPOTENCY_HEADER, description="Chave de idempotência do evento")
]
OrganizationHeader = Annotated[
    str | None,
    Header(alias=service.ORGANIZATION_HEADER, description="Slug da organização de destino"),
]


async def _raw_body(request: Request) -> bytes:
    """Corpo bruto da requisição, necessário para validar a assinatura."""
    return await request.body()


@router.get("/status", response_model=IntegrationStatus, summary="Situação das integrações")
async def integration_status(session: SessionDep, user: RequireViewer) -> IntegrationStatus:
    """Mostra cabeçalhos exigidos, endpoints e contadores de eventos."""
    return await service.status(session, organization_id=user.organization_id)


@router.get("/webhooks/events", response_model=Page[WebhookEventRead], summary="Eventos de webhook")
async def list_webhook_events(
    session: SessionDep,
    user: RequireViewer,
    params: Annotated[PageParams, Depends(page_params)],
    direction: Annotated[WebhookDirection | None, Query(description="INBOUND ou OUTBOUND")] = None,
    event_type: Annotated[str | None, Query(description="Filtra por tipo de evento")] = None,
) -> Page[WebhookEventRead]:
    """Lista os eventos recebidos e enviados, com situação e tentativas."""
    events, total = await service.list_events(
        session,
        organization_id=user.organization_id,
        params=params,
        direction=direction,
        event_type=event_type,
    )
    return Page.build([WebhookEventRead.model_validate(item) for item in events], total, params)


@router.post(
    "/webhooks/leads",
    response_model=WebhookAck,
    summary="Receber novo lead (n8n → OpsPilot)",
)
async def receive_lead(
    session: SessionDep,
    request: Request,
    signature: SignatureHeader = None,
    idempotency_key: IdempotencyHeader = None,
    organization_slug: OrganizationHeader = None,
) -> WebhookAck:
    """Cria um lead a partir de um evento externo assinado por HMAC."""
    raw = await _raw_body(request)
    organization = await service.resolve_organization(session, slug=organization_slug)
    try:
        payload = InboundLeadPayload.model_validate_json(raw)
    except ValueError as exc:
        service.ensure_signature(raw, signature)
        raise ValidationError("Corpo do evento inválido para lead.") from exc
    return await service.receive_lead(
        session,
        organization=organization,
        payload=payload,
        raw_body=raw,
        signature=signature,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/webhooks/renewals",
    response_model=WebhookAck,
    summary="Receber evento de renovação (n8n → OpsPilot)",
)
async def receive_renewal(
    session: SessionDep,
    request: Request,
    signature: SignatureHeader = None,
    idempotency_key: IdempotencyHeader = None,
    organization_slug: OrganizationHeader = None,
) -> WebhookAck:
    """Cria ou atualiza a renovação de um cliente existente."""
    raw = await _raw_body(request)
    organization = await service.resolve_organization(session, slug=organization_slug)
    try:
        payload = InboundRenewalPayload.model_validate_json(raw)
    except ValueError as exc:
        service.ensure_signature(raw, signature)
        raise ValidationError("Corpo do evento inválido para renovação.") from exc
    return await service.receive_renewal(
        session,
        organization=organization,
        payload=payload,
        raw_body=raw,
        signature=signature,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/webhooks/test",
    response_model=WebhookEventRead,
    summary="Enviar evento de teste (OpsPilot → n8n)",
)
async def send_test_event(
    payload: OutboundTestRequest, session: SessionDep, admin: RequireAdmin
) -> WebhookEventRead:
    """Publica um evento de saída assinado para validar a automação."""
    event = await service.send_test_event(
        session,
        organization_id=admin.organization_id,
        event_type=payload.event_type,
        payload=payload.payload,
        target_url=payload.target_url,
        actor=admin,
    )
    return WebhookEventRead.model_validate(event)
