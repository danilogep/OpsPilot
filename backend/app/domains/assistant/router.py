"""Rotas do assistente de IA."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import ContextDep, RequireAnalyst, RequireViewer, SessionDep
from app.core.pagination import Page, PageParams, page_params
from app.domains.assistant import service
from app.domains.assistant.schemas import (
    AskRequest,
    AssistantAnswer,
    AssistantConfig,
    LeadClassificationResponse,
    MessageDraftRequest,
    MessageDraftResponse,
    RenewalSummaryResponse,
)
from app.domains.assistant.usage import LLMUsageRead, list_usage

router = APIRouter(prefix="/assistant", tags=["Assistente de IA"])


@router.get("/config", response_model=AssistantConfig, summary="Configuração do assistente")
async def assistant_config(session: SessionDep, _user: RequireViewer) -> AssistantConfig:
    """Mostra provider ativo, mecanismo de busca e perguntas sugeridas."""
    return service.config(session)


@router.post("/ask", response_model=AssistantAnswer, summary="Perguntar sobre os dados")
async def ask(
    payload: AskRequest, session: SessionDep, user: RequireViewer, context: ContextDep
) -> AssistantAnswer:
    """Responde com números do banco e trechos dos documentos, citando as fontes."""
    return await service.ask(
        session,
        organization_id=user.organization_id,
        question=payload.question,
        actor=user,
        context=context,
    )


@router.post(
    "/leads/{lead_id}/classify",
    response_model=LeadClassificationResponse,
    summary="Classificar lead com IA",
)
async def classify_lead(
    lead_id: uuid.UUID, session: SessionDep, user: RequireAnalyst, context: ContextDep
) -> LeadClassificationResponse:
    """Classifica o lead em JSON validado, ancorado no score determinístico."""
    return await service.classify_lead(
        session,
        organization_id=user.organization_id,
        lead_id=lead_id,
        actor=user,
        context=context,
    )


@router.post(
    "/renewals/summary",
    response_model=RenewalSummaryResponse,
    summary="Resumo executivo de renovações",
)
async def renewal_summary(
    session: SessionDep, user: RequireViewer, context: ContextDep
) -> RenewalSummaryResponse:
    """Gera resumo, clientes críticos, valor em risco e ações recomendadas."""
    return await service.renewal_summary(
        session, organization_id=user.organization_id, actor=user, context=context
    )


@router.post(
    "/messages/draft",
    response_model=MessageDraftResponse,
    summary="Rascunho de mensagem comercial",
)
async def draft_message(
    payload: MessageDraftRequest,
    session: SessionDep,
    user: RequireAnalyst,
    context: ContextDep,
) -> MessageDraftResponse:
    """Gera uma sugestão curta de mensagem. Nada é enviado automaticamente."""
    return await service.draft_message(
        session,
        organization_id=user.organization_id,
        payload=payload,
        actor=user,
        context=context,
    )


@router.get("/usage", response_model=Page[LLMUsageRead], summary="Histórico de uso de IA")
async def usage(
    session: SessionDep,
    user: RequireViewer,
    params: Annotated[PageParams, Depends(page_params)],
    feature: Annotated[str | None, Query(description="Filtra por funcionalidade")] = None,
) -> Page[LLMUsageRead]:
    """Lista as execuções de IA registradas, mais recentes primeiro."""
    records, total = await list_usage(
        session, organization_id=user.organization_id, params=params, feature=feature
    )
    return Page.build([LLMUsageRead.model_validate(item) for item in records], total, params)
