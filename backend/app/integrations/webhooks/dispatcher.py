"""Envio de webhooks de saída (OpsPilot → n8n).

Características:

* registra **todo** evento em ``webhook_events``, mesmo quando não há URL
  configurada (status ``SKIPPED``) — o histórico fica completo na auditoria;
* assina o corpo com HMAC-SHA256 e envia a chave de idempotência;
* tenta novamente em falhas de rede, com espera progressiva;
* nunca propaga exceção para o fluxo de negócio: a falha de integração não
  invalida a importação ou a classificação que a originou.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_correlation_id, get_logger
from app.db.base import utcnow
from app.db.models import WebhookDirection, WebhookEvent, WebhookStatus
from app.integrations.webhooks.signature import (
    EVENT_HEADER,
    IDEMPOTENCY_HEADER,
    SIGNATURE_HEADER,
    sign_payload,
)

logger = get_logger(__name__)

#: Eventos de saída publicados pelo OpsPilot.
EVENT_IMPORT_COMPLETED = "import.completed"
EVENT_LEAD_CLASSIFIED = "lead.classified"
EVENT_RENEWAL_ALERT = "renewal.alert"

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (0.5, 1.5)


async def dispatch_event(
    session: Any,
    *,
    organization_id: uuid.UUID,
    event_type: str,
    payload: dict[str, Any],
    idempotency_key: str | None = None,
    target_url: str | None = None,
) -> WebhookEvent:
    """Publica um evento de saída e devolve o registro persistido.

    A sessão não é commitada aqui: quem chama controla a transação.
    """
    url = (target_url or settings.webhook_outbound_url).strip()
    key = idempotency_key or uuid.uuid4().hex
    body = {
        "event": event_type,
        "organization_id": str(organization_id),
        "idempotency_key": key,
        "correlation_id": get_correlation_id() or "",
        "sent_at": utcnow().isoformat(),
        "data": payload,
    }
    event = WebhookEvent(
        organization_id=organization_id,
        direction=WebhookDirection.OUTBOUND,
        event_type=event_type,
        idempotency_key=key,
        signature_valid=True,
        status=WebhookStatus.SKIPPED,
        attempts=0,
        target_url=url or None,
        payload=body,
    )
    session.add(event)

    if not url:
        event.error = "OPSPILOT_WEBHOOK_OUTBOUND_URL não configurada."
        logger.info("webhook_outbound_skipped", event_type=event_type)
        return event

    raw = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        EVENT_HEADER: event_type,
        IDEMPOTENCY_HEADER: key,
        SIGNATURE_HEADER: sign_payload(raw, settings.webhook_secret),
    }

    last_error: str | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        event.attempts = attempt
        try:
            async with httpx.AsyncClient(timeout=settings.webhook_timeout_seconds) as client:
                response = await client.post(url, content=raw, headers=headers)
            event.response = {
                "status_code": response.status_code,
                "body": response.text[:1000],
            }
            if response.is_success:
                event.status = WebhookStatus.SENT
                event.processed_at = utcnow()
                event.error = None
                logger.info(
                    "webhook_outbound_sent",
                    event_type=event_type,
                    status_code=response.status_code,
                    attempts=attempt,
                )
                return event
            last_error = f"HTTP {response.status_code}"
        except httpx.HTTPError as exc:
            last_error = type(exc).__name__
        if attempt < MAX_ATTEMPTS:
            await asyncio.sleep(BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)])

    event.status = WebhookStatus.FAILED
    event.error = last_error
    logger.warning("webhook_outbound_failed", event_type=event_type, error=last_error)
    return event
