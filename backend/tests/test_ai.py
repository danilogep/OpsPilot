"""Testes do provider mock, do assistente e da base de conhecimento."""

from __future__ import annotations

import io
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ProviderError
from app.db.models import Lead, Organization
from app.domains.assistant.intents import Intent, detect_intent
from app.domains.knowledge.chunking import chunk_text, normalize_for_search, tokenize
from app.domains.knowledge.search import extract_terms, search_chunks
from app.integrations.llm.base import (
    LLMFeature,
    LLMMessage,
    LLMRequest,
    estimate_cost_usd,
)
from app.integrations.llm.factory import available_providers, get_provider
from app.integrations.llm.mock import NO_EVIDENCE_MESSAGE, MockProvider
from app.integrations.llm.runner import parse_json_response
from tests.conftest import auth_headers

API = settings.api_v1_prefix


# ------------------------------------------------------- provider mock --------


def test_default_provider_is_mock() -> None:
    provider = get_provider()
    assert provider.name == "mock"
    assert provider.is_mock is True


def test_available_providers_lists_all_four() -> None:
    providers = {item["name"]: item for item in available_providers()}
    assert set(providers) == {"mock", "anthropic", "openai", "gemini"}
    assert providers["mock"]["configured"] is True
    assert providers["mock"]["active"] is True
    assert providers["anthropic"]["configured"] is False


async def test_mock_provider_is_deterministic() -> None:
    provider = MockProvider()
    request = LLMRequest(
        feature=LLMFeature.ASSISTANT,
        system="teste",
        messages=[LLMMessage(role="user", content="Quantos clientes renovam?")],
        context={
            "headline": "Resumo",
            "facts": [{"label": "Renovações", "value": 4, "kind": "count", "source": "renewals"}],
            "reasoning": ["Filtrei por data."],
        },
    )
    first = await provider.complete(request)
    second = await provider.complete(request)
    assert first.text == second.text
    assert "Renovações" in first.text
    assert first.is_mock is True
    assert first.output_tokens > 0


async def test_mock_provider_without_context_says_no_evidence() -> None:
    provider = MockProvider()
    response = await provider.complete(
        LLMRequest(
            feature=LLMFeature.ASSISTANT,
            system="teste",
            messages=[LLMMessage(role="user", content="Qual a cor do céu?")],
        )
    )
    assert NO_EVIDENCE_MESSAGE in response.text


async def test_mock_provider_formats_money_in_brl() -> None:
    provider = MockProvider()
    response = await provider.complete(
        LLMRequest(
            feature=LLMFeature.ASSISTANT,
            system="teste",
            messages=[LLMMessage(role="user", content="Valor em risco?")],
            context={
                "facts": [
                    {
                        "label": "Valor em risco",
                        "value": "1890.50",
                        "kind": "money",
                        "source": "renewals",
                    }
                ]
            },
        )
    )
    assert "R$ 1.890,50" in response.text


async def test_mock_provider_returns_valid_json_for_lead_classifier() -> None:
    provider = MockProvider()
    response = await provider.complete(
        LLMRequest(
            feature=LLMFeature.LEAD_CLASSIFIER,
            system="teste",
            messages=[LLMMessage(role="user", content="Classifique")],
            expects_json=True,
            context={
                "lead": {"name": "Ana", "company": "Acme", "interest": "controlar renovações"},
                "rules_score": {
                    "score": 82,
                    "category": "HOT",
                    "reasons": ["Contato completo"],
                    "risks": [],
                    "next_step": "Agendar reunião",
                },
            },
        )
    )
    payload = parse_json_response(response.text)
    assert payload["score"] == 82
    assert payload["category"] == "HOT"
    assert payload["suggested_message"]


def test_cost_estimation_is_zero_for_mock() -> None:
    assert estimate_cost_usd("mock", 1000, 1000) == Decimal("0")
    assert estimate_cost_usd("gpt-4o-mini", 1_000_000, 0) == Decimal("0.150000")


def test_parse_json_response_handles_code_fence() -> None:
    assert parse_json_response('```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(ProviderError):
        parse_json_response("sem json aqui")


# ------------------------------------------------------------- chunking -------


def test_chunk_text_splits_and_normalizes() -> None:
    text = "# Título\n\n" + ("Parágrafo de exemplo com conteúdo. " * 60)
    chunks = chunk_text(text, chunk_size=300, overlap=50)
    assert len(chunks) > 2
    assert all(chunk.char_count <= 320 for chunk in chunks)
    assert chunks[0].normalized == normalize_for_search(chunks[0].content)
    assert all(chunk.token_estimate > 0 for chunk in chunks)


def test_chunk_text_handles_empty_input() -> None:
    assert chunk_text("") == []
    assert chunk_text("   \n  ") == []


def test_normalize_for_search_removes_accents() -> None:
    assert normalize_for_search("Renovação ANUAL") == "renovacao anual"
    assert "renovacao" in tokenize("Renovação de contratos")


def test_extract_terms_drops_stopwords() -> None:
    terms = extract_terms("Qual é o prazo de aviso prévio para cancelamento?")
    assert "cancelamento" in terms
    assert "prazo" in terms
    assert "de" not in terms
    assert "o" not in terms


# -------------------------------------------------------------- busca ---------


async def test_search_finds_seeded_knowledge(session: AsyncSession, seeded: Organization) -> None:
    hits = await search_chunks(
        session, organization_id=seeded.id, query="aviso prévio de cancelamento", limit=5
    )
    assert hits
    assert any("cancelamento" in hit.document_title.lower() for hit in hits)
    assert all(0 < hit.score <= 1 for hit in hits)
    assert hits[0].excerpt


async def test_search_returns_nothing_for_unrelated_query(
    session: AsyncSession, seeded: Organization
) -> None:
    hits = await search_chunks(
        session, organization_id=seeded.id, query="receita de bolo de chocolate", limit=5
    )
    assert hits == []


async def test_search_is_isolated_by_organization(
    session: AsyncSession, seeded: Organization
) -> None:
    import uuid

    hits = await search_chunks(session, organization_id=uuid.uuid4(), query="cancelamento", limit=5)
    assert hits == []


async def test_knowledge_search_endpoint(client: AsyncClient, viewer_token: str) -> None:
    response = await client.get(
        f"{API}/knowledge/search",
        headers=auth_headers(viewer_token),
        params={"q": "desconto consultor"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["engine"] in {"portable-like", "postgresql-fts"}
    assert body["total"] >= 1
    assert body["hits"][0]["document_title"]


async def test_knowledge_documents_are_listed(client: AsyncClient, viewer_token: str) -> None:
    response = await client.get(f"{API}/knowledge/documents", headers=auth_headers(viewer_token))
    assert response.status_code == 200
    assert response.json()["total"] == 10


async def test_upload_markdown_document(client: AsyncClient, analyst_token: str) -> None:
    content = (
        "# Política de férias coletivas\n\n"
        "A empresa concede férias coletivas entre 24 de dezembro e 2 de janeiro.\n\n"
        "Durante o período, o atendimento fica restrito a incidentes críticos."
    ).encode()
    response = await client.post(
        f"{API}/knowledge/documents",
        headers=auth_headers(analyst_token),
        files={"file": ("ferias.md", io.BytesIO(content), "text/markdown")},
        data={"title": "Política de férias coletivas", "tags": "rh,operação"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["chunk_count"] >= 1
    assert body["status"] == "READY"
    assert body["tags"] == ["rh", "operação"]

    search = await client.get(
        f"{API}/knowledge/search",
        headers=auth_headers(analyst_token),
        params={"q": "férias coletivas"},
    )
    assert search.json()["total"] >= 1


async def test_upload_rejects_executable(client: AsyncClient, analyst_token: str) -> None:
    response = await client.post(
        f"{API}/knowledge/documents",
        headers=auth_headers(analyst_token),
        files={"file": ("virus.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
    )
    assert response.status_code == 400


async def test_text_document_and_ask_with_citation(client: AsyncClient, analyst_token: str) -> None:
    created = await client.post(
        f"{API}/knowledge/documents/text",
        headers=auth_headers(analyst_token),
        json={
            "title": "Regra de reembolso",
            "content": (
                "O reembolso de despesas é feito até o quinto dia útil do mês seguinte, "
                "mediante nota fiscal e aprovação da coordenação."
            ),
            "tags": ["financeiro"],
        },
    )
    assert created.status_code == 201

    answer = await client.post(
        f"{API}/knowledge/ask",
        headers=auth_headers(analyst_token),
        json={"question": "Como funciona o reembolso de despesas?"},
    )
    assert answer.status_code == 200
    body = answer.json()
    assert body["has_evidence"] is True
    assert body["sources"]
    assert body["sources"][0]["title"]
    assert "reembolso" in body["answer"].lower()


async def test_ask_documents_without_evidence(client: AsyncClient, analyst_token: str) -> None:
    response = await client.post(
        f"{API}/knowledge/ask",
        headers=auth_headers(analyst_token),
        json={"question": "Qual é a cotação do dólar hoje?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["has_evidence"] is False
    assert body["answer"] == NO_EVIDENCE_MESSAGE
    assert body["sources"] == []


async def test_delete_document_removes_from_search(client: AsyncClient, analyst_token: str) -> None:
    headers = auth_headers(analyst_token)
    created = await client.post(
        f"{API}/knowledge/documents/text",
        headers=headers,
        json={
            "title": "Procedimento temporário",
            "content": "O procedimento temporário de inventário usa a palavra-chave xilofone.",
        },
    )
    document_id = created.json()["id"]
    before = await client.get(f"{API}/knowledge/search", headers=headers, params={"q": "xilofone"})
    assert before.json()["total"] >= 1

    removed = await client.delete(f"{API}/knowledge/documents/{document_id}", headers=headers)
    assert removed.status_code == 204

    after = await client.get(f"{API}/knowledge/search", headers=headers, params={"q": "xilofone"})
    assert after.json()["total"] == 0


# ---------------------------------------------------------- intenções ---------


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Quantos clientes renovam este mês?", Intent.RENEWALS),
        ("Qual é o valor mensal em risco?", Intent.AMOUNT_AT_RISK),
        ("Quais leads têm maior prioridade?", Intent.TOP_LEADS),
        ("Quais planos apresentam maior cancelamento?", Intent.PLAN_CHURN),
        ("Quais clientes não tiveram contato recente?", Intent.STALE_CUSTOMERS),
        ("Qual a receita mensal estimada?", Intent.CUSTOMER_OVERVIEW),
        ("Como está o funil de vendas?", Intent.LEAD_FUNNEL),
        ("Quantas linhas deram erro na importação?", Intent.IMPORT_STATUS),
        ("Qual é o prazo de aviso prévio?", Intent.POLICY),
    ],
)
def test_detect_intent(question: str, expected: Intent) -> None:
    assert detect_intent(question) is expected


# --------------------------------------------------------- assistente ---------


async def test_assistant_config_exposes_mock_provider(
    client: AsyncClient, viewer_token: str
) -> None:
    response = await client.get(f"{API}/assistant/config", headers=auth_headers(viewer_token))
    assert response.status_code == 200
    body = response.json()
    assert body["active_provider"] == "mock"
    assert body["is_mock"] is True
    assert body["no_evidence_message"] == NO_EVIDENCE_MESSAGE
    assert len(body["suggestions"]) >= 5


async def test_assistant_answers_renewal_question_with_numbers(
    client: AsyncClient, viewer_token: str
) -> None:
    response = await client.post(
        f"{API}/assistant/ask",
        headers=auth_headers(viewer_token),
        json={"question": "Quantos clientes renovam nos próximos 30 dias?"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["intent"] == "renewals"
    assert body["has_evidence"] is True
    assert body["facts"]
    assert all(fact["source"] for fact in body["facts"])
    assert body["sources"]
    assert body["reasoning"]
    assert body["trace"]["llm_called"] is True
    assert body["trace"]["provider"] == "mock"
    assert "renewals" in body["tables"]


async def test_assistant_answers_amount_at_risk(client: AsyncClient, viewer_token: str) -> None:
    response = await client.post(
        f"{API}/assistant/ask",
        headers=auth_headers(viewer_token),
        json={"question": "Qual é o valor mensal em risco?"},
    )
    body = response.json()
    assert body["intent"] == "amount_at_risk"
    labels = {fact["label"] for fact in body["facts"]}
    assert "Valor mensal em risco" in labels
    assert "R$" in body["answer"]


async def test_assistant_answers_top_leads(client: AsyncClient, viewer_token: str) -> None:
    response = await client.post(
        f"{API}/assistant/ask",
        headers=auth_headers(viewer_token),
        json={"question": "Quais leads têm maior prioridade?"},
    )
    body = response.json()
    assert body["intent"] == "top_leads"
    assert body["tables"]["leads"]
    scores = [item["score"] for item in body["tables"]["leads"]]
    assert scores == sorted(scores, reverse=True)


async def test_assistant_answers_plan_churn(client: AsyncClient, viewer_token: str) -> None:
    response = await client.post(
        f"{API}/assistant/ask",
        headers=auth_headers(viewer_token),
        json={"question": "Quais planos apresentam maior cancelamento?"},
    )
    body = response.json()
    assert body["intent"] == "plan_churn"
    assert body["tables"]["plans"]
    assert body["has_evidence"] is True


async def test_assistant_answers_stale_customers(client: AsyncClient, viewer_token: str) -> None:
    response = await client.post(
        f"{API}/assistant/ask",
        headers=auth_headers(viewer_token),
        json={"question": "Quais clientes não tiveram contato recente?"},
    )
    body = response.json()
    assert body["intent"] == "stale_customers"
    assert body["tables"]["customers"]


async def test_assistant_uses_knowledge_for_policy_question(
    client: AsyncClient, viewer_token: str
) -> None:
    response = await client.post(
        f"{API}/assistant/ask",
        headers=auth_headers(viewer_token),
        json={"question": "Qual é o prazo de aviso prévio para cancelamento?"},
    )
    body = response.json()
    assert body["intent"] == "policy"
    assert body["has_evidence"] is True
    assert any(source["type"] == "document" for source in body["sources"])
    assert "30 dias" in body["answer"] or "30" in body["answer"]


async def test_assistant_refuses_without_evidence(client: AsyncClient, viewer_token: str) -> None:
    response = await client.post(
        f"{API}/assistant/ask",
        headers=auth_headers(viewer_token),
        json={"question": "Quem ganhou o campeonato mundial de xadrez em 1998?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["has_evidence"] is False
    assert NO_EVIDENCE_MESSAGE in body["answer"]
    assert body["sources"] == []
    assert body["trace"]["llm_called"] is False


async def test_assistant_records_usage_and_audit(client: AsyncClient, admin_token: str) -> None:
    headers = auth_headers(admin_token)
    await client.post(
        f"{API}/assistant/ask",
        headers=headers,
        json={"question": "Qual é a receita mensal estimada?"},
    )
    usage = await client.get(f"{API}/assistant/usage", headers=headers)
    assert usage.status_code == 200
    body = usage.json()
    assert body["total"] >= 1
    record = body["items"][0]
    assert record["provider"] == "mock"
    assert record["prompt_version"] == "assistant-v1"
    assert record["status"] == "SUCCESS"
    assert record["duration_ms"] >= 0

    audit = await client.get(
        f"{API}/audit/events", headers=headers, params={"action": "ai.assistant_query"}
    )
    assert audit.json()["total"] >= 1


async def test_assistant_usage_summary_in_dashboard(client: AsyncClient, viewer_token: str) -> None:
    headers = auth_headers(viewer_token)
    await client.post(
        f"{API}/assistant/ask", headers=headers, json={"question": "Como está o funil de leads?"}
    )
    response = await client.get(f"{API}/dashboard/ai-usage", headers=headers)
    body = response.json()
    assert body["calls"] >= 1
    assert body["by_feature"]


# ------------------------------------------------- classificação de lead ------


async def test_classify_lead_returns_validated_json(
    client: AsyncClient, analyst_token: str, session: AsyncSession, seeded: Organization
) -> None:
    lead = (
        (
            await session.execute(
                select(Lead).where(Lead.organization_id == seeded.id).order_by(Lead.score.desc())
            )
        )
        .scalars()
        .first()
    )
    assert lead is not None
    response = await client.post(
        f"{API}/assistant/leads/{lead.id}/classify", headers=auth_headers(analyst_token)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    classification = body["classification"]
    assert 0 <= classification["score"] <= 100
    assert classification["category"] in {"HOT", "WARM", "COLD"}
    assert classification["reasons"]
    assert classification["next_action"]
    assert classification["suggested_message"]
    assert body["rules_score"] == lead.score or body["agreement"] in {"igual", "acima", "abaixo"}
    assert body["trace"]["provider"] == "mock"
    assert any(source["type"] == "rules" for source in body["sources"])


async def test_classify_lead_registers_event_and_audit(
    client: AsyncClient, admin_token: str, session: AsyncSession, seeded: Organization
) -> None:
    lead = (
        (await session.execute(select(Lead).where(Lead.organization_id == seeded.id)))
        .scalars()
        .first()
    )
    assert lead is not None
    headers = auth_headers(admin_token)
    await client.post(f"{API}/assistant/leads/{lead.id}/classify", headers=headers)

    events = await client.get(f"{API}/leads/{lead.id}/events", headers=headers)
    assert any("IA" in event["description"] for event in events.json())

    audit = await client.get(
        f"{API}/audit/events", headers=headers, params={"action": "ai.lead_classified"}
    )
    assert audit.json()["total"] == 1


async def test_viewer_cannot_classify_lead(
    client: AsyncClient, viewer_token: str, session: AsyncSession, seeded: Organization
) -> None:
    lead = (
        (await session.execute(select(Lead).where(Lead.organization_id == seeded.id)))
        .scalars()
        .first()
    )
    assert lead is not None
    response = await client.post(
        f"{API}/assistant/leads/{lead.id}/classify", headers=auth_headers(viewer_token)
    )
    assert response.status_code == 403


# ------------------------------------------------ resumo e mensagem -----------


async def test_renewal_summary_has_evidence_and_actions(
    client: AsyncClient, viewer_token: str
) -> None:
    response = await client.post(
        f"{API}/assistant/renewals/summary", headers=auth_headers(viewer_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["has_evidence"] is True
    assert body["critical_customers"]
    assert body["recommended_actions"]
    assert body["indicators"]["reference_date"]
    assert body["sources"]


async def test_message_draft_for_lead(
    client: AsyncClient, analyst_token: str, session: AsyncSession, seeded: Organization
) -> None:
    lead = (
        (await session.execute(select(Lead).where(Lead.organization_id == seeded.id)))
        .scalars()
        .first()
    )
    assert lead is not None
    response = await client.post(
        f"{API}/assistant/messages/draft",
        headers=auth_headers(analyst_token),
        json={"purpose": "lead", "lead_id": str(lead.id)},
    )
    assert response.status_code == 200
    body = response.json()
    assert lead.name.split()[0] in body["draft"]
    assert "não envia mensagens" in body["disclaimer"]
    assert body["trace"]["provider"] == "mock"


async def test_message_draft_requires_target(client: AsyncClient, analyst_token: str) -> None:
    response = await client.post(
        f"{API}/assistant/messages/draft",
        headers=auth_headers(analyst_token),
        json={"purpose": "lead"},
    )
    assert response.status_code == 422
