"""Testes de clientes, planos, renovações e leads."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.base import utcnow
from app.db.models import Customer, Organization, Renewal
from app.db.models.enums import CustomerStatus, RenewalStatus
from tests.conftest import auth_headers

API = settings.api_v1_prefix


# ------------------------------------------------------------- clientes -------


async def test_list_customers_is_paginated(client: AsyncClient, viewer_token: str) -> None:
    response = await client.get(
        f"{API}/customers", headers=auth_headers(viewer_token), params={"page_size": 10}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 100
    assert len(body["items"]) == 10
    assert body["pages"] == 10


async def test_list_customers_search_by_name(client: AsyncClient, viewer_token: str) -> None:
    response = await client.get(
        f"{API}/customers", headers=auth_headers(viewer_token), params={"search": "Padaria"}
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert items
    assert all("padaria" in item["name"].lower() for item in items)


async def test_list_customers_filter_by_status(client: AsyncClient, viewer_token: str) -> None:
    response = await client.get(
        f"{API}/customers",
        headers=auth_headers(viewer_token),
        params={"status": ["PAST_DUE"]},
    )
    items = response.json()["items"]
    assert items
    assert all(item["status"] == "PAST_DUE" for item in items)


async def test_list_customers_filter_renewal_window(client: AsyncClient, viewer_token: str) -> None:
    response = await client.get(
        f"{API}/customers",
        headers=auth_headers(viewer_token),
        params={"renewal_within_days": 30},
    )
    items = response.json()["items"]
    assert items
    assert all(0 <= item["days_to_renewal"] <= 30 for item in items)


async def test_list_customers_sorting(client: AsyncClient, viewer_token: str) -> None:
    response = await client.get(
        f"{API}/customers",
        headers=auth_headers(viewer_token),
        params={"sort": "monthly_value", "direction": "desc", "page_size": 5},
    )
    values = [Decimal(item["monthly_value"]) for item in response.json()["items"]]
    assert values == sorted(values, reverse=True)


async def test_list_customers_rejects_invalid_sort(client: AsyncClient, viewer_token: str) -> None:
    response = await client.get(
        f"{API}/customers", headers=auth_headers(viewer_token), params={"sort": "senha"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_customer_crud_flow(client: AsyncClient, analyst_token: str) -> None:
    headers = auth_headers(analyst_token)
    created = await client.post(
        f"{API}/customers",
        headers=headers,
        json={
            "name": "Empresa Teste Ltda",
            "email": "contato@empresateste.com.br",
            "phone": "(11) 98765-4321",
            "document": "12345678000190",
            "monthly_value": "750.00",
            "renewal_date": (utcnow().date() + timedelta(days=15)).isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["phone"] == "+5511987654321"
    assert body["phone_formatted"] == "+55 (11) 98765-4321"
    assert body["document"] == "12.345.678/0001-90"
    assert body["days_to_renewal"] == 15
    customer_id = body["id"]

    duplicated = await client.post(
        f"{API}/customers",
        headers=headers,
        json={"name": "Outro Nome", "email": "contato@empresateste.com.br"},
    )
    assert duplicated.status_code == 409

    updated = await client.patch(
        f"{API}/customers/{customer_id}",
        headers=headers,
        json={"status": "PAST_DUE", "monthly_value": "900.00"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "PAST_DUE"

    history = await client.get(f"{API}/customers/{customer_id}/history", headers=headers)
    assert history.status_code == 200
    actions = [item["action"] for item in history.json()]
    assert "customer.updated" in actions
    diff = next(
        item["meta"]["changes"] for item in history.json() if item["action"] == "customer.updated"
    )
    assert diff["status"]["before"] == "ACTIVE"
    assert diff["status"]["after"] == "PAST_DUE"

    deleted = await client.delete(f"{API}/customers/{customer_id}", headers=headers)
    assert deleted.status_code == 204
    missing = await client.get(f"{API}/customers/{customer_id}", headers=headers)
    assert missing.status_code == 404


async def test_customer_rejects_invalid_phone(client: AsyncClient, analyst_token: str) -> None:
    response = await client.post(
        f"{API}/customers",
        headers=auth_headers(analyst_token),
        json={"name": "Empresa Sem DDD", "phone": "98765432"},
    )
    assert response.status_code == 422


async def test_viewer_cannot_create_customer(client: AsyncClient, viewer_token: str) -> None:
    response = await client.post(
        f"{API}/customers", headers=auth_headers(viewer_token), json={"name": "Bloqueado"}
    )
    assert response.status_code == 403


async def test_register_contact_updates_last_contact(
    client: AsyncClient, analyst_token: str, session: AsyncSession, seeded: Organization
) -> None:
    customer = (
        (
            await session.execute(
                select(Customer).where(Customer.organization_id == seeded.id).limit(1)
            )
        )
        .scalars()
        .first()
    )
    assert customer is not None
    response = await client.post(
        f"{API}/customers/{customer.id}/contact",
        headers=auth_headers(analyst_token),
        params={"note": "Ligação de acompanhamento"},
    )
    assert response.status_code == 200
    assert response.json()["days_since_contact"] == 0


async def test_export_customers_csv(client: AsyncClient, viewer_token: str) -> None:
    response = await client.get(f"{API}/customers/export", headers=auth_headers(viewer_token))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    text = response.content.decode("utf-8-sig")
    lines = text.strip().splitlines()
    assert lines[0].startswith("Nome;E-mail;Telefone")
    assert len(lines) == 101  # cabeçalho + 100 clientes


# --------------------------------------------------------------- planos -------


async def test_list_plans_with_metrics(client: AsyncClient, viewer_token: str) -> None:
    response = await client.get(f"{API}/plans", headers=auth_headers(viewer_token))
    assert response.status_code == 200
    plans = response.json()
    assert len(plans) == 5
    assert sum(plan["customers_count"] for plan in plans) == 100
    assert all(0.0 <= plan["churn_rate"] <= 1.0 for plan in plans)
    assert any(Decimal(plan["monthly_revenue"]) > 0 for plan in plans)


async def test_plan_crud_and_delete_guard(client: AsyncClient, analyst_token: str) -> None:
    headers = auth_headers(analyst_token)
    created = await client.post(
        f"{API}/plans",
        headers=headers,
        json={"name": "Plano Piloto", "monthly_value": "99.90"},
    )
    assert created.status_code == 201
    plan_id = created.json()["id"]

    duplicated = await client.post(f"{API}/plans", headers=headers, json={"name": "plano piloto"})
    assert duplicated.status_code == 409

    updated = await client.patch(
        f"{API}/plans/{plan_id}", headers=headers, json={"monthly_value": "129.90"}
    )
    assert updated.status_code == 200
    assert updated.json()["monthly_value"] == "129.90"

    customer = await client.post(
        f"{API}/customers",
        headers=headers,
        json={"name": "Cliente do Piloto", "plan_id": plan_id},
    )
    assert customer.status_code == 201
    blocked = await client.delete(f"{API}/plans/{plan_id}", headers=headers)
    assert blocked.status_code == 409

    await client.delete(f"{API}/customers/{customer.json()['id']}", headers=headers)
    removed = await client.delete(f"{API}/plans/{plan_id}", headers=headers)
    assert removed.status_code == 204


# ----------------------------------------------------------- renovações -------


async def test_renewal_indicators_come_from_database(
    client: AsyncClient, viewer_token: str, session: AsyncSession, seeded: Organization
) -> None:
    response = await client.get(f"{API}/renewals/indicators", headers=auth_headers(viewer_token))
    assert response.status_code == 200
    body = response.json()

    today = utcnow().date()
    renewals = (
        (await session.execute(select(Renewal).where(Renewal.organization_id == seeded.id)))
        .scalars()
        .unique()
        .all()
    )
    expected_7 = sum(
        1
        for item in renewals
        if item.status in (RenewalStatus.SCHEDULED, RenewalStatus.AT_RISK)
        and today <= item.due_date <= today + timedelta(days=7)
    )
    assert body["due_next_7_days"] == expected_7
    assert body["reference_date"] == today.isoformat()
    assert Decimal(body["amount_at_risk"]) >= 0
    assert body["contact_threshold_days"] == 45


async def test_critical_renewals_have_reason(client: AsyncClient, viewer_token: str) -> None:
    response = await client.get(f"{API}/renewals/critical", headers=auth_headers(viewer_token))
    assert response.status_code == 200
    items = response.json()
    assert items
    assert all(item["reason"] for item in items)
    assert all("customer_name" in item for item in items)


async def test_confirming_renewal_moves_customer_date(
    client: AsyncClient, analyst_token: str, session: AsyncSession, seeded: Organization
) -> None:
    renewal = (
        (
            await session.execute(
                select(Renewal).where(
                    Renewal.organization_id == seeded.id,
                    Renewal.status == RenewalStatus.SCHEDULED,
                )
            )
        )
        .scalars()
        .unique()
        .first()
    )
    assert renewal is not None
    previous_due = renewal.due_date

    response = await client.patch(
        f"{API}/renewals/{renewal.id}",
        headers=auth_headers(analyst_token),
        json={"status": "CONFIRMED"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CONFIRMED"
    assert response.json()["confirmed_at"]

    customer = await session.get(Customer, renewal.customer_id)
    assert customer is not None
    await session.refresh(customer)
    assert customer.renewal_date == previous_due + timedelta(days=365)
    assert customer.status is CustomerStatus.ACTIVE


async def test_renewals_filter_overdue(client: AsyncClient, viewer_token: str) -> None:
    response = await client.get(
        f"{API}/renewals", headers=auth_headers(viewer_token), params={"overdue_only": True}
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert all(item["days_until_due"] < 0 for item in items)


async def test_export_renewals_csv(client: AsyncClient, viewer_token: str) -> None:
    response = await client.get(f"{API}/renewals/export", headers=auth_headers(viewer_token))
    assert response.status_code == 200
    text = response.content.decode("utf-8-sig")
    assert text.splitlines()[0].startswith("Cliente;Plano;Vencimento")


# ---------------------------------------------------------------- leads -------


async def test_list_leads_sorted_by_score(client: AsyncClient, viewer_token: str) -> None:
    response = await client.get(
        f"{API}/leads", headers=auth_headers(viewer_token), params={"page_size": 20}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 60
    scores = [item["score"] for item in body["items"]]
    assert scores == sorted(scores, reverse=True)


async def test_filter_leads_by_category_and_open(client: AsyncClient, viewer_token: str) -> None:
    response = await client.get(
        f"{API}/leads",
        headers=auth_headers(viewer_token),
        params={"category": ["HOT"], "only_open": True},
    )
    items = response.json()["items"]
    assert all(item["score_category"] == "HOT" for item in items)
    assert all(item["status"] not in {"WON", "LOST"} for item in items)


async def test_lead_indicators_include_funnel_and_sources(
    client: AsyncClient, viewer_token: str
) -> None:
    response = await client.get(f"{API}/leads/indicators", headers=auth_headers(viewer_token))
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 60
    assert sum(stage["total"] for stage in body["funnel"]) == 60
    assert body["by_source"]
    assert all(item["total"] > 0 for item in body["by_source"])


async def test_lead_lifecycle_with_events(client: AsyncClient, analyst_token: str) -> None:
    headers = auth_headers(analyst_token)
    created = await client.post(
        f"{API}/leads",
        headers=headers,
        json={
            "name": "Joana Prospect",
            "company": "Clínica Nova",
            "email": "joana@clinicanova.com.br",
            "phone": "11987651234",
            "source": "indicacao",
            "segment": "saúde",
            "company_size": "SMALL",
            "interest": "controlar renovações",
            "estimated_value": "2500.00",
            "last_interaction_at": utcnow().isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    lead = created.json()
    assert lead["score"] == 100
    assert lead["score_category"] == "HOT"
    assert lead["next_step"]
    lead_id = lead["id"]

    events = await client.get(f"{API}/leads/{lead_id}/events", headers=headers)
    types = {event["event_type"] for event in events.json()}
    assert {"CREATED", "SCORED"} <= types

    note = await client.post(
        f"{API}/leads/{lead_id}/notes",
        headers=headers,
        json={"note": "Reunião marcada para quinta.", "mark_as_contacted": True},
    )
    assert note.status_code == 200
    assert note.json()["status"] == "CONTACTED"

    status_change = await client.patch(
        f"{API}/leads/{lead_id}", headers=headers, json={"status": "PROPOSAL"}
    )
    assert status_change.status_code == 200
    events = await client.get(f"{API}/leads/{lead_id}/events", headers=headers)
    assert any(event["event_type"] == "STATUS_CHANGED" for event in events.json())


async def test_lead_score_endpoint_is_transparent(
    client: AsyncClient, analyst_token: str, session: AsyncSession, seeded: Organization
) -> None:
    from app.db.models import Lead

    lead = (
        (await session.execute(select(Lead).where(Lead.organization_id == seeded.id).limit(1)))
        .scalars()
        .first()
    )
    assert lead is not None
    response = await client.post(
        f"{API}/leads/{lead.id}/score", headers=auth_headers(analyst_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["method"] == "RULES"
    assert body["version"] == "rules-v1"
    assert len(body["reasons"]) == 7
    assert sum(reason["max_points"] for reason in body["reasons"]) == 100
    assert body["sources"]


async def test_export_leads_csv(client: AsyncClient, viewer_token: str) -> None:
    response = await client.get(f"{API}/leads/export", headers=auth_headers(viewer_token))
    assert response.status_code == 200
    text = response.content.decode("utf-8-sig")
    assert text.splitlines()[0].startswith("Nome;Empresa;E-mail")


# ------------------------------------------------------------ dashboard -------


async def test_dashboard_overview_matches_database(client: AsyncClient, viewer_token: str) -> None:
    response = await client.get(f"{API}/dashboard/overview", headers=auth_headers(viewer_token))
    assert response.status_code == 200
    body = response.json()
    assert body["customers"]["total_customers"] == 100
    assert Decimal(body["customers"]["monthly_revenue"]) > 0
    assert body["leads"]["total_leads"] == 60
    assert body["renewals"]["reference_date"]
    assert len(body["plans"]) == 5
    assert body["imports"]["total_imports"] == 0
    assert body["ai_usage"]["calls"] == 0
    assert len(body["timeline"]) >= 6


async def test_dashboard_requires_authentication(client: AsyncClient) -> None:
    response = await client.get(f"{API}/dashboard/overview")
    assert response.status_code == 401


async def test_viewer_can_read_dashboard(client: AsyncClient, viewer_token: str) -> None:
    response = await client.get(f"{API}/dashboard/customers", headers=auth_headers(viewer_token))
    assert response.status_code == 200
    assert response.json()["total_customers"] == 100
