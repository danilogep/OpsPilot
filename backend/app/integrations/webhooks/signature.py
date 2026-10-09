"""Assinatura HMAC-SHA256 dos webhooks.

O cabeçalho ``X-OpsPilot-Signature`` carrega ``sha256=<hex>`` calculado sobre o
corpo bruto da requisição com o segredo compartilhado
(``OPSPILOT_WEBHOOK_SECRET``). A comparação usa ``hmac.compare_digest`` para
evitar vazamento por tempo de resposta.
"""

from __future__ import annotations

import hashlib
import hmac

SIGNATURE_HEADER = "X-OpsPilot-Signature"
IDEMPOTENCY_HEADER = "X-OpsPilot-Idempotency-Key"
EVENT_HEADER = "X-OpsPilot-Event"
SIGNATURE_PREFIX = "sha256="


def sign_payload(payload: bytes, secret: str) -> str:
    """Gera o valor do cabeçalho de assinatura para um corpo bruto."""
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"{SIGNATURE_PREFIX}{digest}"


def verify_signature(payload: bytes, secret: str, provided: str | None) -> bool:
    """Confere a assinatura recebida contra o corpo bruto."""
    if not provided or not secret:
        return False
    candidate = provided.strip()
    if not candidate.startswith(SIGNATURE_PREFIX):
        candidate = f"{SIGNATURE_PREFIX}{candidate}"
    expected = sign_payload(payload, secret)
    return hmac.compare_digest(expected, candidate)
