"""Testes dos agentes, do ToolRegistry e dos webhooks."""

from __future__ import annotations

import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import PermissionDeniedError
from app.core.errors import ValidationError as AppValidationError
from app.db.models import Customer, Lead, Organization, User, UserRole
from app.domains.agents.runtime import DEFAULT_AGENTS, plan_calls
from app.domains.agents.tools import TOOL_REGISTRY, ToolContext, execute_tool
from app.integrations.webhooks.signature import (
    IDEMPOTENCY_HEADER,
    SIGNATURE_HEADER,
    sign_payload,
    verify_signature,
)
from tests.conftest import auth_headers

API = settings.api_v1_prefix
ORG_HEADER = "X-OpsPilot-Organization"


# --------------------------------------------------------- ToolRegistry -------


def test_tool_registry_has_required_tools() -> None:
    expected = {
        "list_customers",
        "search_customers",
        "get_customer",
        "list_renewals",
        "list_leads",
        "calculate_metrics",
        "search_knowledge",
        "create_lead_note",
    }
    assert expected == set(TOOL_REGISTRY)


def test_only_lead_note_is_writable() -> None:
    writable = {name for name, tool in TOOL_REGISTRY.items() if not tool.read_only}
    assert writable == {"create_lead_note"}
    assert UserRole.VIEWER not in TOOL_REGISTRY["create_lead_note"].allowed_roles


async def test_execute_tool_rejects_unlisted_tool(
    session: AsyncSession, demo_users: dict[UserRole, User], seeded: Organization
) -> None:
    context = ToolContext(
        session=session, organization_id=seeded.id, actor=demo_users[UserRole.ANALYST]
    )
    with pytest.raises(PermissionDeniedError):
        await execute_tool("list_customers", {}, context=context, allowed_tools={"list_leads"})


async def test_execute_tool_rejects_unknown_tool(
    session: AsyncSession, demo_users: dict[UserRole, User], seeded: Organization
) -> None:
    context = ToolContext(
        session=session, organization_id=seeded.id, actor=demo_users[UserRole.ANALYST]
    )
    with pytest.raises(AppValidationError):
        await execute_tool("drop_database", {}, context=context, allowed_tools={"drop_database"})


async def test_execute_tool_validates_parameters(
    session: AsyncSession, demo_users: dict[UserRole, User], seeded: Organization
) -> None:
    context = ToolContext(
        session=session, organization_id=seeded.id, actor=demo_users[UserRole.ANALYST]
    )
    with pytest.raises(AppValidationError):
        await execute_tool(
            "list_customers",
            {"limit": 9999},
            context=context,
            allowed_tools={"list_customers"},
        )


async def test_write_tool_denied_for_viewer(
    session: AsyncSession,
    demo_users: dict[UserRole, User],
    seeded: Organization,
) -> None:
    lead = (
        (await session.execute(select(Lead).where(Lead.organization_id == seeded.id)))
        .scalars()
        .first()
    )
    assert lead is not None
    context = ToolContext(
        session=session, organization_id=seeded.id, actor=demo_users[UserRole.VIEWER]
    )
    with pytest.raises(PermissionDeniedError):
        await execute_tool(
            "create_lead_note",
            {"lead_id": str(lead.id), "note": "teste"},
            context=context,
            allowed_tools={"create_lead_note"},
        )


async def test_tools_are_scoped_to_organization(
    session: AsyncSession, demo_users: dict[UserRole, User], seeded: Organization
) -> None:
    other_org = uuid.uuid4()
    context = ToolContext(
        session=session, organization_id=other_org, actor=demo_users[UserRole.ANALYST]
    )
    result = await execute_tool(
        "list_customers", {}, context=context, allowed_tools={"list_customers"}
    )
    assert result["count"] == 0


async def test_calculate_metrics_tool_returns_sources(
    session: AsyncSession, demo_users: dict[UserRole, User], seeded: Organization
) -> None:
    context = ToolContext(
        session=session, organization_id=seeded.id, actor=demo_users[UserRole.ANALYST]
    )
    result = await execute_tool(
        "calculate_metrics",
        {"scope": "renewals"},
        context=context,
        allowed_tools={"calculate_metrics"},
    )
    assert result["scope"] == "renewals"
    assert result["renewals"]["reference_date"]
    assert result["source"]


async def test_create_lead_note_tool_registers_event(
    session: AsyncSession, demo_users: dict[UserRole, User], seeded: Organization
) -> None:
    lead = (
        (await session.execute(select(Lead).where(Lead.organization_id == seeded.id)))
        .scalars()
        .first()
    )
    assert lead is not None
    context = ToolContext(
        session=session, organization_id=seeded.id, actor=demo_users[UserRole.ANALYST]
    )
    result = await execute_tool(
        "create_lead_note",
        {"lead_id": str(lead.id), "note": "Nota criada pelo agente.", "mark_as_contacted": True},
        context=context,
        allowed_tools={"create_lead_note"},
    )
    assert result["note_registered"] is True
    assert result["marked_as_contacted"] is True


# ------------------------------------------------------------- agentes --------


def test_planner_respects_allowlist() -> None:
    planned = plan_calls("RenewalAgent", "Quais renovações vencem?", allowed={"list_renewals"})
    assert [call.tool for call in planned] == ["list_renewals"]


def test_planner_varies_by_agent() -> None:
    allowed_sales = set(DEFAULT_AGENTS["SalesAgent"][2])
    sales = plan_calls("SalesAgent", "Quais leads priorizar?", allowed=allowed_sales)
    assert "list_leads" in [call.tool for call in sales]

    allowed_renewal = set(DEFAULT_AGENTS["RenewalAgent"][2])
    renewal = plan_calls("RenewalAgent", "Panorama de renovações", allowed=allowed_renewal)
    assert "list_renewals" in [call.tool for call in renewal]


def test_planner_never_repeats_a_tool() -> None:
    allowed = set(DEFAULT_AGENTS["DataAnalystAgent"][2])
    planned = plan_calls(
        "DataAnalystAgent", "Quantos clientes renovam e qual a receita?", allowed=allowed
    )
    tools = [call.tool for call in planned]
    assert len(tools) == len(set(tools))


async def test_list_agents_endpoint(client: AsyncClient, viewer_token: str) -> None:
    response = await client.get(f"{API}/agents", headers=auth_headers(viewer_token))
    assert response.status_code == 200
    keys = {item["key"] for item in response.json()}
    assert keys == {"DataAnalystAgent", "SalesAgent", "RenewalAgent"}


async def test_list_tools_endpoint(client: AsyncClient, viewer_token: str) -> None:
    response = await client.get(f"{API}/agents/tools", headers=auth_headers(viewer_token))
    assert response.status_code == 200
    names = {item["name"] for item in response.json()}
    assert "calculate_metrics" in names
    assert all("parameters" in item for item in response.json())


async def test_run_renewal_agent_records_trace(client: AsyncClient, analyst_token: str) -> None:
    response = await client.post(
        f"{API}/agents/RenewalAgent/run",
        headers=auth_headers(analyst_token),
        json={"question": "Como estão as renovações do mês?"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] in {"SUCCESS", "PARTIAL", "MAX_STEPS"}
    assert body["has_evidence"] is True
    assert body["tools_used"]
    assert body["steps"]
    assert all(step["rationale"] for step in body["steps"])
    assert all(step["duration_ms"] >= 0 for step in body["steps"])
    assert body["sources"]
    assert body["correlation_id"]
    assert body["trace"]["executed"] <= body["trace"]["max_steps"]


async def test_run_sales_agent_uses_lead_tools(client: AsyncClient, analyst_token: str) -> None:
    response = await client.post(
        f"{API}/agents/SalesAgent/run",
        headers=auth_headers(analyst_token),
        json={"question": "Quais leads devo priorizar hoje?"},
    )
    body = response.json()
    assert "list_leads" in body["tools_used"]
    assert body["answer"]


async def test_run_data_analyst_agent(client: AsyncClient, viewer_token: str) -> None:
    response = await client.post(
        f"{API}/agents/DataAnalystAgent/run",
        headers=auth_headers(viewer_token),
        json={"question": "Qual a receita mensal estimada da base?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "calculate_metrics" in body["tools_used"]
    assert body["trace"]["llm_called"] is True


async def test_unknown_agent_returns_404(client: AsyncClient, analyst_token: str) -> None:
    response = await client.post(
        f"{API}/agents/HackerAgent/run",
        headers=auth_headers(analyst_token),
        json={"question": "Apague os dados"},
    )
    assert response.status_code == 404


async def test_agent_run_is_persisted(client: AsyncClient, analyst_token: str) -> None:
    headers = auth_headers(analyst_token)
    run = await client.post(
        f"{API}/agents/RenewalAgent/run",
        headers=headers,
        json={"question": "Resumo das renovações"},
    )
    run_id = run.json()["run_id"]

    listing = await client.get(f"{API}/agents/runs", headers=headers)
    assert listing.json()["total"] >= 1

    detail = await client.get(f"{API}/agents/runs/{run_id}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["agent_name"] == "RenewalAgent"
    assert body["steps"]
    assert body["result"]["answer"]
    assert body["duration_ms"] >= 0


async def test_agent_run_is_audited(client: AsyncClient, admin_token: str) -> None:
    headers = auth_headers(admin_token)
    await client.post(
        f"{API}/agents/DataAnalystAgent/run",
        headers=headers,
        json={"question": "Panorama da base de clientes"},
    )
    audit = await client.get(
        f"{API}/audit/events", headers=headers, params={"action": "ai.agent_run"}
    )
    assert audit.json()["total"] >= 1


async def test_viewer_agent_cannot_write(client: AsyncClient, viewer_token: str) -> None:
    """O SalesAgent inclui create_lead_note, mas o VIEWER não pode escrever."""
    response = await client.post(
        f"{API}/agents/SalesAgent/run",
        headers=auth_headers(viewer_token),
        json={"question": "Quais leads priorizar?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"SUCCESS", "PARTIAL"}
    write_steps = [step for step in body["steps"] if step["tool"] == "create_lead_note"]
    assert all(step["status"] == "error" for step in write_steps)


# ------------------------------------------------------------ webhooks --------


def test_signature_roundtrip() -> None:
    body = b'{"name":"Teste"}'
    signature = sign_payload(body, "segredo")
    assert signature.startswith("sha256=")
    assert verify_signature(body, "segredo", signature)
    assert not verify_signature(body, "outro", signature)
    assert not verify_signature(b'{"name":"Outro"}', "segredo", signature)
    assert not verify_signature(body, "segredo", None)


def _signed(body: dict, key: str) -> tuple[bytes, dict[str, str]]:
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        SIGNATURE_HEADER: sign_payload(raw, settings.webhook_secret),
        IDEMPOTENCY_HEADER: key,
        ORG_HEADER: "acme-servicos",
    }
    return raw, headers


async def test_inbound_lead_webhook_creates_lead(client: AsyncClient, seeded: Organization) -> None:
    raw, headers = _signed(
        {
            "name": "Marcos Webhook",
            "company": "Clínica Integrada",
            "email": "marcos@clinicaintegrada.com.br",
            "phone": "11987654321",
            "source": "site",
            "segment": "saúde",
            "company_size": "SMALL",
            "interest": "controlar renovações",
            "estimated_value": "1800.00",
        },
        "lead-001",
    )
    response = await client.post(f"{API}/integrations/webhooks/leads", content=raw, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["received"] is True
    assert body["status"] == "PROCESSED"
    assert body["entity_id"]
    assert "score" in body["message"]


async def test_inbound_lead_webhook_is_idempotent(
    client: AsyncClient, seeded: Organization
) -> None:
    raw, headers = _signed({"name": "Lead Repetido", "source": "n8n"}, "lead-dup")
    first = await client.post(f"{API}/integrations/webhooks/leads", content=raw, headers=headers)
    second = await client.post(f"{API}/integrations/webhooks/leads", content=raw, headers=headers)
    assert first.json()["status"] == "PROCESSED"
    assert second.json()["status"] == "DUPLICATE"
    assert second.json()["duplicate"] is True


async def test_inbound_webhook_rejects_invalid_signature(
    client: AsyncClient, seeded: Organization
) -> None:
    raw, headers = _signed({"name": "Lead Falso"}, "lead-bad")
    headers[SIGNATURE_HEADER] = "sha256=0000"
    response = await client.post(f"{API}/integrations/webhooks/leads", content=raw, headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


async def test_inbound_webhook_requires_signature(
    client: AsyncClient, seeded: Organization
) -> None:
    raw, headers = _signed({"name": "Lead Sem Assinatura"}, "lead-nosig")
    headers.pop(SIGNATURE_HEADER)
    response = await client.post(f"{API}/integrations/webhooks/leads", content=raw, headers=headers)
    assert response.status_code == 401


async def test_inbound_webhook_unknown_organization(
    client: AsyncClient, seeded: Organization
) -> None:
    raw, headers = _signed({"name": "Lead Org"}, "lead-org")
    headers[ORG_HEADER] = "organizacao-inexistente"
    response = await client.post(f"{API}/integrations/webhooks/leads", content=raw, headers=headers)
    assert response.status_code == 404


async def test_inbound_renewal_webhook_updates_customer(
    client: AsyncClient, session: AsyncSession, seeded: Organization
) -> None:
    customer = (
        (
            await session.execute(
                select(Customer)
                .where(Customer.organization_id == seeded.id, Customer.email.is_not(None))
                .limit(1)
            )
        )
        .scalars()
        .unique()
        .first()
    )
    assert customer is not None
    raw, headers = _signed(
        {
            "customer_email": customer.email,
            "due_date": "2027-03-10",
            "amount": "499.00",
            "status": "AT_RISK",
            "notes": "Cliente pediu revisão de escopo.",
        },
        "renewal-001",
    )
    response = await client.post(
        f"{API}/integrations/webhooks/renewals", content=raw, headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "PROCESSED"

    await session.refresh(customer)
    assert customer.renewal_date.isoformat() == "2027-03-10"


async def test_inbound_renewal_webhook_unknown_customer(
    client: AsyncClient, seeded: Organization
) -> None:
    raw, headers = _signed(
        {"customer_email": "inexistente@exemplo.com", "due_date": "2027-01-01"},
        "renewal-404",
    )
    response = await client.post(
        f"{API}/integrations/webhooks/renewals", content=raw, headers=headers
    )
    assert response.status_code == 404


async def test_integration_status_lists_contract(client: AsyncClient, viewer_token: str) -> None:
    response = await client.get(f"{API}/integrations/status", headers=auth_headers(viewer_token))
    assert response.status_code == 200
    body = response.json()
    assert body["inbound_signature_required"] is True
    assert body["signature_header"] == SIGNATURE_HEADER
    assert len(body["inbound_endpoints"]) == 2
    assert len(body["outbound_events"]) == 3


async def test_outbound_test_event_is_skipped_without_url(
    client: AsyncClient, admin_token: str
) -> None:
    response = await client.post(
        f"{API}/integrations/webhooks/test",
        headers=auth_headers(admin_token),
        json={"event_type": "renewal.alert", "payload": {"demo": True}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["direction"] == "OUTBOUND"
    assert body["status"] == "SKIPPED"
    assert "OPSPILOT_WEBHOOK_OUTBOUND_URL" in (body["error"] or "")


async def test_webhook_events_are_listed(client: AsyncClient, admin_token: str) -> None:
    headers = auth_headers(admin_token)
    raw, signed_headers = _signed({"name": "Lead Listagem"}, "lead-list")
    await client.post(f"{API}/integrations/webhooks/leads", content=raw, headers=signed_headers)

    response = await client.get(
        f"{API}/integrations/webhooks/events", headers=headers, params={"direction": "INBOUND"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    event = body["items"][0]
    assert event["signature_valid"] is True
    assert event["event_type"] == "lead.created"


async def test_import_commit_publishes_outbound_event(
    client: AsyncClient, analyst_token: str
) -> None:
    """A confirmação de importação registra o evento de saída mesmo sem URL."""
    import io

    csv = (
        "Razão Social;E-mail;Vencimento;Mensalidade (R$)\n"
        "Empresa Webhook Ltda;webhook@empresa.com.br;01/12/2027;499,00\n"
    ).encode()
    headers = auth_headers(analyst_token)
    upload = await client.post(
        f"{API}/imports",
        headers=headers,
        files={"file": ("webhook.csv", io.BytesIO(csv), "text/csv")},
    )
    import_id = upload.json()["id"]
    await client.post(f"{API}/imports/{import_id}/validate", headers=headers)
    await client.post(f"{API}/imports/{import_id}/commit", headers=headers)

    events = await client.get(
        f"{API}/integrations/webhooks/events",
        headers=headers,
        params={"direction": "OUTBOUND", "event_type": "import.completed"},
    )
    assert events.json()["total"] == 1
    assert events.json()["items"][0]["idempotency_key"] == f"import-{import_id}"
