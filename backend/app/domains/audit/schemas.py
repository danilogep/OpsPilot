"""Schemas da trilha de auditoria."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditEventRead(BaseModel):
    """Evento de auditoria exposto pela API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action: str
    entity_type: str
    entity_id: str | None
    actor_email: str
    actor_role: str
    summary: str
    meta: dict[str, Any]
    correlation_id: str
    ip_address: str | None
    created_at: datetime


class AuditActionSummary(BaseModel):
    """Contagem por ação, usada nos filtros da interface."""

    action: str
    total: int
