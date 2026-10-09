"""Schemas do assistente de IA."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import LeadCategory
from app.domains.assistant.intents import Intent


class AskRequest(BaseModel):
    """Pergunta enviada ao assistente."""

    question: str = Field(min_length=5, max_length=500)


class FactRead(BaseModel):
    """Número ou texto verificável usado na resposta."""

    label: str
    value: Any
    kind: str
    source: str


class SourceRead(BaseModel):
    """Fonte citada pela resposta."""

    type: str
    title: str
    locator: str | None = None
    document_id: uuid.UUID | None = None
    score: float | None = None
    excerpt: str | None = None


class AssistantAnswer(BaseModel):
    """Resposta do assistente, sempre com fatos e fontes."""

    question: str
    intent: Intent
    intent_label: str
    answer: str
    has_evidence: bool
    facts: list[FactRead] = Field(default_factory=list)
    sources: list[SourceRead] = Field(default_factory=list)
    tables: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    reasoning: list[str] = Field(default_factory=list)
    recommendation: str | None = None
    suggestions: list[str] = Field(default_factory=list)
    trace: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime


class LeadClassification(BaseModel):
    """Saída estruturada e validada da classificação de lead."""

    model_config = ConfigDict(extra="ignore")

    score: int = Field(ge=0, le=100)
    category: LeadCategory
    reasons: list[str] = Field(default_factory=list, max_length=10)
    risks: list[str] = Field(default_factory=list, max_length=10)
    next_action: str = Field(min_length=3, max_length=300)
    suggested_message: str = Field(min_length=3, max_length=1200)
    summary: str = Field(default="", max_length=500)


class LeadClassificationResponse(BaseModel):
    """Resposta da classificação, com rastreamento e fontes."""

    lead_id: uuid.UUID
    classification: LeadClassification
    rules_score: int
    rules_version: str
    agreement: str
    sources: list[SourceRead] = Field(default_factory=list)
    trace: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime


class RenewalSummaryResponse(BaseModel):
    """Resumo executivo de renovações."""

    summary: str
    has_evidence: bool
    indicators: dict[str, Any]
    critical_customers: list[dict[str, Any]]
    recommended_actions: list[str]
    sources: list[SourceRead] = Field(default_factory=list)
    trace: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime


class MessageDraftRequest(BaseModel):
    """Pedido de rascunho de mensagem comercial."""

    purpose: str = Field(default="lead", pattern="^(lead|renewal|generic)$")
    lead_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    detail: str | None = Field(default=None, max_length=300)
    tone: str = Field(default="cordial e direto", max_length=60)


class MessageDraftResponse(BaseModel):
    """Rascunho gerado — nunca enviado automaticamente."""

    draft: str
    purpose: str
    target: dict[str, Any]
    sources: list[SourceRead] = Field(default_factory=list)
    trace: dict[str, Any] = Field(default_factory=dict)
    disclaimer: str = (
        "Rascunho gerado por IA. Revise antes de enviar — o OpsPilot não envia mensagens."
    )
    generated_at: datetime


class ProviderInfo(BaseModel):
    """Provider de IA disponível."""

    name: str
    default_model: str
    supports_json: bool
    is_mock: bool
    configured: bool
    active: bool


class AssistantConfig(BaseModel):
    """Configuração visível do assistente."""

    active_provider: str
    active_model: str
    is_mock: bool
    providers: list[ProviderInfo]
    search_engine: str
    suggestions: list[str]
    no_evidence_message: str
