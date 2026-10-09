"""Regressões encontradas ao executar o produto completo."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models import Customer, CustomerStatus, Lead, Organization, Renewal
from app.domains.organizations import metrics
from tests.conftest import auth_headers


@pytest.mark.parametrize(
    "value",
    [
        "http://localhost:5173,http://localhost:8080",
        '["http://localhost:5173","http://localhost:8080"]',
    ],
)
def test_cors_from_environment(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("OPSPILOT_CORS_ORIGINS", value)
    assert Settings().cors_origins == ["http://localhost:5173", "http://localhost:8080"]


async def test_exact_calendar_month_window(
    session: AsyncSession, seeded: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(metrics, "utcnow", lambda: datetime(2026, 3, 31, tzinfo=UTC))
    points = await metrics.revenue_timeline(session, organization_id=seeded.id, months=3)
    assert [p["month"] for p in points] == ["2026-01", "2026-02", "2026-03"]


async def test_average_ticket_uses_only_billable_customers(session: AsyncSession) -> None:
    org = Organization(name="Test", slug="metric-test")
    session.add(org)
    await session.flush()
    session.add_all(
        [
            Customer(
                organization_id=org.id,
                name="Ativo",
                dedupe_key="active-test",
                status=CustomerStatus.ACTIVE,
                monthly_value=Decimal("100"),
            ),
            Customer(
                organization_id=org.id,
                name="Cancelado",
                dedupe_key="churn-test",
                status=CustomerStatus.CHURNED,
                monthly_value=Decimal("50"),
            ),
        ]
    )
    await session.flush()
    data = await metrics.customer_overview(session, organization_id=org.id)
    assert data["average_ticket"] == "100.00"


@pytest.mark.parametrize("resource", ["leads", "renewals"])
async def test_export_does_not_truncate_after_200_rows(
    client: AsyncClient,
    session: AsyncSession,
    seeded: Organization,
    admin_token: str,
    resource: str,
) -> None:
    customer = Customer(
        organization_id=seeded.id,
        name="Export test",
        status=CustomerStatus.ACTIVE,
        dedupe_key="export-test",
    )
    session.add(customer)
    await session.flush()
    rows: list[Any] = []
    for index in range(205):
        if resource == "leads":
            rows.append(
                Lead(organization_id=seeded.id, name=f"Export {index}", source="export-test")
            )
        else:
            rows.append(
                Renewal(
                    organization_id=seeded.id,
                    customer_id=customer.id,
                    due_date=datetime.now(UTC).date(),
                    amount=Decimal("100"),
                )
            )
    session.add_all(rows)
    await session.commit()
    query = {"source": "export-test"} if resource == "leads" else {"customer_id": str(customer.id)}
    response = await client.get(
        f"/api/v1/{resource}/export", params=query, headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    assert len(list(csv.reader(io.StringIO(response.text)))) == 206
