"""Serviço do assistente de IA.

Fluxo de uma pergunta:

1. detectar a intenção (determinístico, por palavras-chave);
2. consultar os fatos no banco (números verificáveis com fonte);
3. buscar trechos relevantes na base de conhecimento;
4. **se não houver fato nem trecho**, devolver a mensagem padrão de ausência de
   evidência — sem chamar o provider de IA;
5. com evidência, pedir ao provider que redija a resposta usando apenas esse
   contexto, registrar o uso e devolver fatos, fontes e rastreamento.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequestContext
from app.core.config import settings
from app.core.errors import ProviderError, ValidationError
from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.models import Customer, Lead, LeadEventType, ScoringMethod, User
from app.domains.assistant import intents as intent_module
from app.domains.assistant.schemas import (
    AssistantAnswer,
    AssistantConfig,
    FactRead,
    LeadClassification,
    LeadClassificationResponse,
    MessageDraftRequest,
    MessageDraftResponse,
    ProviderInfo,
    RenewalSummaryResponse,
    SourceRead,
)
from app.domains.audit import service as audit_service
from app.domains.knowledge import service as knowledge_service
from app.domains.knowledge.search import SearchHit
from app.domains.leads import service as leads_service
from app.domains.leads.scoring import score_lead
from app.domains.organizations import metrics
from app.domains.renewals import service as renewals_service
from app.integrations.llm import prompts
from app.integrations.llm.base import LLMFeature, LLMMessage, LLMRequest
from app.integrations.llm.factory import available_providers, get_provider
from app.integrations.llm.mock import NO_EVIDENCE_MESSAGE
from app.integrations.llm.runner import parse_json_response, run_llm
from app.integrations.webhooks import dispatcher

logger = get_logger(__name__)

#: Trechos de documento considerados por pergunta.
KNOWLEDGE_LIMIT = 4


def _fact_sources(facts: list[intent_module.Fact]) -> list[SourceRead]:
    """Fontes derivadas dos fatos consultados no banco."""
    seen: dict[str, SourceRead] = {}
    for fact in facts:
        if fact.source in seen:
            continue
        seen[fact.source] = SourceRead(
            type="database", title=fact.source, locator="consulta agregada"
        )
    return list(seen.values())


async def ask(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    question: str,
    actor: User,
    context: RequestContext | None = None,
) -> AssistantAnswer:
    """Responde uma pergunta sobre os dados da organização."""
    intent = intent_module.detect_intent(question)
    resolved = await intent_module.resolve(
        session, organization_id=organization_id, question=question, intent=intent
    )

    hits: list[SearchHit] = []
    if resolved.needs_knowledge or not resolved.has_facts:
        hits = await knowledge_service.search(
            session, organization_id=organization_id, query=question, limit=KNOWLEDGE_LIMIT
        )
    engine = knowledge_service.search_engine_name(session)

    if not resolved.has_facts and not hits:
        await audit_service.record_audit(
            session,
            organization_id=organization_id,
            action=audit_service.ACTION_AI_ASSISTANT,
            entity_type="assistant",
            actor=actor,
            summary="Pergunta sem evidência suficiente nos dados.",
            meta={"question": question[:300], "intent": intent.value},
            context=context,
        )
        await session.commit()
        logger.info("assistant_no_evidence", intent=intent.value)
        return AssistantAnswer(
            question=question,
            intent=intent,
            intent_label=intent_module.INTENT_LABELS[intent],
            answer=(
                f"{NO_EVIDENCE_MESSAGE}\n\n"
                "Nenhum indicador do OpsPilot responde a esta pergunta e não há documento "
                "indexado que trate do assunto. Importe dados ou envie um documento para "
                "a base de conhecimento e pergunte novamente."
            ),
            has_evidence=False,
            suggestions=list(intent_module.SUGGESTED_QUESTIONS[:5]),
            trace={"intent": intent.value, "facts": 0, "knowledge_hits": 0, "llm_called": False},
            generated_at=utcnow(),
        )

    request = LLMRequest(
        feature=LLMFeature.ASSISTANT,
        system=prompts.ASSISTANT_SYSTEM,
        prompt_version=prompts.ASSISTANT_VERSION,
        messages=[LLMMessage(role="user", content=question)],
        max_output_tokens=settings.llm_max_output_tokens,
        context={
            "question": question,
            "intent": intent.value,
            "headline": resolved.headline,
            "facts": [fact.as_dict() for fact in resolved.facts],
            "knowledge": [
                {
                    "document_title": hit.document_title,
                    "excerpt": hit.excerpt,
                    "locator": hit.page_hint or f"bloco {hit.chunk_index + 1}",
                    "score": hit.score,
                }
                for hit in hits
            ],
            "reasoning": resolved.reasoning,
            "recommendation": resolved.recommendation,
            "tables": resolved.tables,
        },
    )
    execution = await run_llm(
        session,
        organization_id=organization_id,
        request=request,
        actor=actor,
        provider=get_provider(),
    )

    sources = _fact_sources(resolved.facts) + [
        SourceRead.model_validate(hit.as_source()) for hit in hits
    ]
    await audit_service.record_audit(
        session,
        organization_id=organization_id,
        action=audit_service.ACTION_AI_ASSISTANT,
        entity_type="assistant",
        actor=actor,
        summary=f"Pergunta respondida ({intent_module.INTENT_LABELS[intent]}).",
        meta={
            "question": question[:300],
            "intent": intent.value,
            "facts": len(resolved.facts),
            "knowledge_hits": len(hits),
            "provider": execution.response.provider,
        },
        context=context,
    )
    await session.commit()

    return AssistantAnswer(
        question=question,
        intent=intent,
        intent_label=intent_module.INTENT_LABELS[intent],
        answer=execution.text,
        has_evidence=True,
        facts=[FactRead.model_validate(fact.as_dict()) for fact in resolved.facts],
        sources=sources,
        tables=resolved.tables,
        reasoning=resolved.reasoning,
        recommendation=resolved.recommendation,
        suggestions=list(intent_module.SUGGESTED_QUESTIONS[:5]),
        trace={
            **execution.trace(),
            "intent": intent.value,
            "facts": len(resolved.facts),
            "knowledge_hits": len(hits),
            "search_engine": engine,
            "llm_called": True,
        },
        generated_at=utcnow(),
    )


async def classify_lead(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    lead_id: uuid.UUID,
    actor: User,
    context: RequestContext | None = None,
) -> LeadClassificationResponse:
    """Classifica um lead com IA, ancorada no score determinístico."""
    lead = await leads_service.get_lead(session, organization_id=organization_id, lead_id=lead_id)
    rules = score_lead(leads_service.score_input(lead))

    request = LLMRequest(
        feature=LLMFeature.LEAD_CLASSIFIER,
        system=prompts.LEAD_CLASSIFIER_SYSTEM,
        prompt_version=prompts.LEAD_CLASSIFIER_VERSION,
        messages=[
            LLMMessage(
                role="user",
                content=f"Classifique o lead {lead.name} e sugira o próximo passo.",
            )
        ],
        expects_json=True,
        max_output_tokens=settings.llm_max_output_tokens,
        context={
            "lead": {
                "name": lead.name,
                "company": lead.company,
                "email": lead.email,
                "phone": lead.phone,
                "source": lead.source,
                "segment": lead.segment,
                "company_size": lead.company_size.value,
                "interest": lead.interest,
                "status": lead.status.value,
                "estimated_value": str(lead.estimated_value),
                "last_interaction_at": (
                    lead.last_interaction_at.isoformat() if lead.last_interaction_at else None
                ),
            },
            "rules_score": {
                "score": rules.score,
                "category": rules.category.value,
                "version": rules.version,
                "reasons": [reason.detail for reason in rules.reasons],
                "risks": rules.risks,
                "next_step": rules.next_step,
            },
        },
    )
    execution = await run_llm(
        session,
        organization_id=organization_id,
        request=request,
        actor=actor,
        provider=get_provider(),
    )

    try:
        payload = parse_json_response(execution.text)
        classification = LeadClassification.model_validate(payload)
    except (ProviderError, PydanticValidationError) as exc:
        logger.warning("lead_classification_invalid", lead_id=str(lead.id))
        raise ProviderError(
            "A resposta da IA não seguiu o formato esperado. O score por regras "
            "continua disponível.",
            details={"rules_score": rules.score},
        ) from exc

    leads_service.apply_score(lead, rules, method=ScoringMethod.LLM)
    lead.score = classification.score
    lead.score_category = classification.category
    lead.risks = classification.risks or rules.risks
    lead.next_step = classification.next_action
    lead.suggested_message = classification.suggested_message
    lead.score_version = f"{rules.version}+{prompts.LEAD_CLASSIFIER_VERSION}"

    agreement = (
        "igual"
        if classification.score == rules.score
        else ("acima" if classification.score > rules.score else "abaixo")
    )
    await leads_service.add_event(
        session,
        lead=lead,
        event_type=LeadEventType.SCORED,
        description=(
            f"Classificação por IA: {classification.score} ({classification.category.value}); "
            f"score por regras: {rules.score} ({agreement})."
        ),
        payload={
            "llm_score": classification.score,
            "rules_score": rules.score,
            "provider": execution.response.provider,
            "model": execution.response.model,
        },
        actor=actor,
    )
    await audit_service.record_audit(
        session,
        organization_id=organization_id,
        action=audit_service.ACTION_AI_LEAD_CLASSIFY,
        entity_type="lead",
        entity_id=str(lead.id),
        actor=actor,
        summary=f"Lead {lead.name} classificado por IA ({classification.category.value}).",
        meta={
            "provider": execution.response.provider,
            "model": execution.response.model,
            "prompt_version": prompts.LEAD_CLASSIFIER_VERSION,
            "llm_score": classification.score,
            "rules_score": rules.score,
        },
        context=context,
    )
    await dispatcher.dispatch_event(
        session,
        organization_id=organization_id,
        event_type=dispatcher.EVENT_LEAD_CLASSIFIED,
        idempotency_key=f"lead-classified-{lead.id}-{classification.score}",
        payload={
            "lead_id": str(lead.id),
            "name": lead.name,
            "company": lead.company,
            "score": classification.score,
            "category": classification.category.value,
            "next_action": classification.next_action,
        },
    )
    await session.commit()
    await session.refresh(lead)

    return LeadClassificationResponse(
        lead_id=lead.id,
        classification=classification,
        rules_score=rules.score,
        rules_version=rules.version,
        agreement=agreement,
        sources=[
            SourceRead(type="database", title="tabela leads", locator=f"lead {lead.id}"),
            SourceRead(
                type="rules",
                title=f"Score determinístico ({rules.version})",
                locator="7 critérios, 100 pontos",
            ),
        ],
        trace=execution.trace(),
        generated_at=utcnow(),
    )


async def renewal_summary(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    actor: User,
    context: RequestContext | None = None,
) -> RenewalSummaryResponse:
    """Resumo executivo de renovações, com clientes críticos e ações."""
    indicators = await metrics.renewal_overview(session, organization_id=organization_id)
    critical = await renewals_service.critical_renewals(
        session, organization_id=organization_id, limit=8
    )
    critical_payload = [
        {
            "customer_name": item.customer_name,
            "plan_name": item.plan_name,
            "due_date": item.due_date.isoformat(),
            "days_until_due": item.days_until_due,
            "amount": str(item.amount),
            "status": item.status.value,
            "reason": item.reason,
        }
        for item in critical
    ]

    has_evidence = bool(critical_payload) or indicators["due_next_30_days"] > 0
    if not has_evidence:
        await session.commit()
        return RenewalSummaryResponse(
            summary=(
                f"{NO_EVIDENCE_MESSAGE}\n\n"
                "Não há renovações cadastradas nos próximos 30 dias nem contratos vencidos "
                "em aberto."
            ),
            has_evidence=False,
            indicators=indicators,
            critical_customers=[],
            recommended_actions=[],
            sources=[],
            trace={"llm_called": False},
            generated_at=utcnow(),
        )

    request = LLMRequest(
        feature=LLMFeature.RENEWAL_SUMMARY,
        system=prompts.RENEWAL_SUMMARY_SYSTEM,
        prompt_version=prompts.RENEWAL_SUMMARY_VERSION,
        messages=[LLMMessage(role="user", content="Monte o resumo executivo das renovações.")],
        max_output_tokens=settings.llm_max_output_tokens,
        context={"indicators": indicators, "critical": critical_payload},
    )
    execution = await run_llm(
        session,
        organization_id=organization_id,
        request=request,
        actor=actor,
        provider=get_provider(),
    )
    actions = [
        "Priorizar contato com renovações vencidas e com vencimento em até 7 dias.",
        "Registrar cada tentativa de contato no cliente.",
        f"Revisar os {indicators['customers_without_recent_contact']} cliente(s) sem contato "
        f"há mais de {indicators['contact_threshold_days']} dias.",
    ]
    await audit_service.record_audit(
        session,
        organization_id=organization_id,
        action=audit_service.ACTION_AI_RENEWAL_SUMMARY,
        entity_type="renewal",
        actor=actor,
        summary="Resumo de renovações gerado por IA.",
        meta={"provider": execution.response.provider, "critical": len(critical_payload)},
        context=context,
    )
    await session.commit()

    return RenewalSummaryResponse(
        summary=execution.text,
        has_evidence=True,
        indicators=indicators,
        critical_customers=critical_payload,
        recommended_actions=actions,
        sources=[
            SourceRead(type="database", title="tabela renewals", locator="indicadores agregados"),
            SourceRead(type="database", title="tabela customers", locator="clientes críticos"),
        ],
        trace=execution.trace(),
        generated_at=utcnow(),
    )


async def draft_message(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    payload: MessageDraftRequest,
    actor: User,
    context: RequestContext | None = None,
) -> MessageDraftResponse:
    """Gera um rascunho curto de mensagem comercial (sem envio)."""
    target: dict[str, Any] = {}
    sources: list[SourceRead] = []

    if payload.purpose == "lead":
        if payload.lead_id is None:
            raise ValidationError("Informe o lead para gerar a mensagem.")
        lead: Lead = await leads_service.get_lead(
            session, organization_id=organization_id, lead_id=payload.lead_id
        )
        target = {
            "kind": "lead",
            "id": str(lead.id),
            "name": lead.name,
            "company": lead.company,
            "interest": lead.interest,
            "score": lead.score,
        }
        sources.append(SourceRead(type="database", title="tabela leads", locator=f"lead {lead.id}"))
    elif payload.purpose == "renewal":
        if payload.customer_id is None:
            raise ValidationError("Informe o cliente para gerar a mensagem de renovação.")
        customer: Customer = await session.get(Customer, payload.customer_id)  # type: ignore[assignment]
        if customer is None or customer.organization_id != organization_id:
            raise ValidationError("Cliente não encontrado nesta organização.")
        target = {
            "kind": "customer",
            "id": str(customer.id),
            "name": customer.name,
            "due_date": customer.renewal_date.isoformat() if customer.renewal_date else None,
            "amount": str(customer.monthly_value),
            "plan": customer.plan.name if customer.plan else None,
        }
        sources.append(
            SourceRead(type="database", title="tabela customers", locator=f"cliente {customer.id}")
        )
    else:
        target = {"kind": "generic", "name": "cliente"}

    request = LLMRequest(
        feature=LLMFeature.MESSAGE_DRAFT,
        system=prompts.MESSAGE_DRAFT_SYSTEM,
        prompt_version=prompts.MESSAGE_DRAFT_VERSION,
        messages=[LLMMessage(role="user", content="Escreva a mensagem sugerida.")],
        max_output_tokens=400,
        context={
            "purpose": payload.purpose,
            "target": target,
            "detail": payload.detail,
            "tone": payload.tone,
        },
    )
    execution = await run_llm(
        session,
        organization_id=organization_id,
        request=request,
        actor=actor,
        provider=get_provider(),
    )
    await audit_service.record_audit(
        session,
        organization_id=organization_id,
        action=audit_service.ACTION_AI_MESSAGE_DRAFT,
        entity_type=target.get("kind", "generic"),
        entity_id=target.get("id"),
        actor=actor,
        summary="Rascunho de mensagem comercial gerado por IA.",
        meta={"purpose": payload.purpose, "provider": execution.response.provider},
        context=context,
    )
    await session.commit()

    return MessageDraftResponse(
        draft=execution.text,
        purpose=payload.purpose,
        target=target,
        sources=sources,
        trace=execution.trace(),
        generated_at=utcnow(),
    )


def config(session: AsyncSession) -> AssistantConfig:
    """Configuração atual do assistente, exibida na interface."""
    provider = get_provider()
    return AssistantConfig(
        active_provider=provider.name,
        active_model=provider.model or provider.default_model,
        is_mock=provider.is_mock,
        providers=[ProviderInfo.model_validate(item) for item in available_providers()],
        search_engine=knowledge_service.search_engine_name(session),
        suggestions=list(intent_module.SUGGESTED_QUESTIONS),
        no_evidence_message=NO_EVIDENCE_MESSAGE,
    )
