"""Consulta ao histórico de uso de IA."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams
from app.db.models import LLMCallStatus, LLMUsage


class LLMUsageRead(BaseModel):
    """Registro de uma chamada de IA."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    feature: str
    provider: str
    model: str
    prompt_version: str
    status: LLMCallStatus
    input_summary: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: Decimal
    duration_ms: int
    attempts: int
    error: str | None
    agent_run_id: uuid.UUID | None
    created_at: datetime


async def list_usage(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    params: PageParams,
    feature: str | None = None,
) -> tuple[list[LLMUsage], int]:
    """Lista o uso de IA da organização, mais recente primeiro."""
    base = select(LLMUsage).where(LLMUsage.organization_id == organization_id)
    if feature:
        base = base.where(LLMUsage.feature == feature)
    total = int(
        (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    )
    rows = (
        (
            await session.execute(
                base.order_by(LLMUsage.created_at.desc())
                .offset(params.offset)
                .limit(params.page_size)
            )
        )
        .scalars()
        .unique()
        .all()
    )
    return list(rows), total
