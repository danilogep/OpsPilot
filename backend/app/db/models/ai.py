"""Agentes, execuções e uso de IA."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    Base,
    OrgScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_type,
)
from app.db.models.enums import AgentRunStatus, LLMCallStatus


class AgentDefinition(UUIDPrimaryKeyMixin, OrgScopedMixin, TimestampMixin, Base):
    """Configuração declarativa de um agente e suas ferramentas permitidas."""

    __tablename__ = "agent_definitions"

    key: Mapped[str] = mapped_column(String(60), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(400), default="")
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    allowed_tools: Mapped[list[str]] = mapped_column(default=list)
    max_steps: Mapped[int] = mapped_column(Integer, default=6)
    prompt_version: Mapped[str] = mapped_column(String(20), default="v1")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AgentRun(UUIDPrimaryKeyMixin, OrgScopedMixin, TimestampMixin, Base):
    """Rastro completo de uma execução de agente."""

    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_org_created", "organization_id", "created_at"),)

    agent_name: Mapped[str] = mapped_column(String(60), index=True)
    status: Mapped[AgentRunStatus] = mapped_column(
        enum_type(AgentRunStatus, length=16), default=AgentRunStatus.RUNNING
    )
    input_payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    tools_used: Mapped[list[str]] = mapped_column(default=list)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(default=list)
    result: Mapped[dict[str, Any]] = mapped_column(default=dict)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    correlation_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )


class LLMUsage(UUIDPrimaryKeyMixin, OrgScopedMixin, TimestampMixin, Base):
    """Registro de cada chamada ao provider de IA (inclui o mock).

    ``input_summary`` guarda apenas um resumo truncado; nunca o prompt completo
    nem dados sensíveis.
    """

    __tablename__ = "llm_usage"
    __table_args__ = (Index("ix_llm_usage_org_created", "organization_id", "created_at"),)

    feature: Mapped[str] = mapped_column(String(60), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(80))
    prompt_version: Mapped[str] = mapped_column(String(20), default="v1")
    status: Mapped[LLMCallStatus] = mapped_column(
        enum_type(LLMCallStatus, length=16), default=LLMCallStatus.SUCCESS
    )
    input_summary: Mapped[str] = mapped_column(String(500), default="")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    error: Mapped[str | None] = mapped_column(String(300), default=None)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), default=None
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
