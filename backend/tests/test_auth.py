"""Testes de autenticação, autorização e usuários."""

from __future__ import annotations

from httpx import AsyncClient

from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import Organization, User, UserRole
from tests.conftest import DEMO_PASSWORD, auth_headers

API = settings.api_v1_prefix


async def test_health_endpoint(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert body["llm_provider"] == "mock"


async def test_password_hash_roundtrip() -> None:
    hashed = hash_password("SenhaForte!2026")
    assert hashed != "SenhaForte!2026"
    assert verify_password("SenhaForte!2026", hashed)
    assert not verify_password("outra-senha", hashed)


async def test_login_success_returns_token_and_user(
    client: AsyncClient, seeded: Organization
) -> None:
    response = await client.post(
        f"{API}/auth/login",
        json={"email": "admin@opspilot.local", "password": DEMO_PASSWORD},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["role"] == "ADMIN"
    assert body["organization"]["slug"] == "acme-servicos"
    assert body["expires_in"] > 0


async def test_login_is_case_insensitive_for_email(
    client: AsyncClient, seeded: Organization
) -> None:
    response = await client.post(
        f"{API}/auth/login",
        json={"email": "ADMIN@OpsPilot.local", "password": DEMO_PASSWORD},
    )
    assert response.status_code == 200


async def test_login_with_wrong_password_is_rejected(
    client: AsyncClient, seeded: Organization
) -> None:
    response = await client.post(
        f"{API}/auth/login",
        json={"email": "admin@opspilot.local", "password": "senha-errada"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


async def test_protected_route_requires_token(client: AsyncClient) -> None:
    response = await client.get(f"{API}/auth/me")
    assert response.status_code == 401


async def test_me_returns_authenticated_user(client: AsyncClient, admin_token: str) -> None:
    response = await client.get(f"{API}/auth/me", headers=auth_headers(admin_token))
    assert response.status_code == 200
    assert response.json()["email"] == "admin@opspilot.local"


async def test_invalid_token_is_rejected(client: AsyncClient) -> None:
    response = await client.get(f"{API}/auth/me", headers=auth_headers("token-invalido"))
    assert response.status_code == 401


async def test_expired_token_is_rejected(
    client: AsyncClient, demo_users: dict[UserRole, User]
) -> None:
    admin = demo_users[UserRole.ADMIN]
    token = create_access_token(
        user_id=admin.id,
        organization_id=admin.organization_id,
        role=admin.role.value,
        email=admin.email,
        expires_minutes=-1,
    )
    response = await client.get(f"{API}/auth/me", headers=auth_headers(token))
    assert response.status_code == 401


async def test_viewer_cannot_list_users(client: AsyncClient, viewer_token: str) -> None:
    response = await client.get(f"{API}/auth/users", headers=auth_headers(viewer_token))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_analyst_cannot_create_users(client: AsyncClient, analyst_token: str) -> None:
    response = await client.post(
        f"{API}/auth/users",
        headers=auth_headers(analyst_token),
        json={
            "email": "novo@opspilot.local",
            "full_name": "Novo Usuário",
            "password": "SenhaForte!2026",
            "role": "VIEWER",
        },
    )
    assert response.status_code == 403


async def test_admin_creates_and_updates_user(client: AsyncClient, admin_token: str) -> None:
    headers = auth_headers(admin_token)
    created = await client.post(
        f"{API}/auth/users",
        headers=headers,
        json={
            "email": "novo@opspilot.local",
            "full_name": "Novo Usuário",
            "password": "SenhaForte!2026",
            "role": "ANALYST",
        },
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]

    duplicated = await client.post(
        f"{API}/auth/users",
        headers=headers,
        json={
            "email": "novo@opspilot.local",
            "full_name": "Duplicado",
            "password": "SenhaForte!2026",
            "role": "VIEWER",
        },
    )
    assert duplicated.status_code == 409

    updated = await client.patch(
        f"{API}/auth/users/{user_id}",
        headers=headers,
        json={"role": "VIEWER", "is_active": False},
    )
    assert updated.status_code == 200
    assert updated.json()["role"] == "VIEWER"
    assert updated.json()["is_active"] is False


async def test_inactive_user_cannot_login(client: AsyncClient, admin_token: str) -> None:
    headers = auth_headers(admin_token)
    created = await client.post(
        f"{API}/auth/users",
        headers=headers,
        json={
            "email": "inativo@opspilot.local",
            "full_name": "Usuário Inativo",
            "password": "SenhaForte!2026",
            "role": "VIEWER",
        },
    )
    user_id = created.json()["id"]
    await client.patch(f"{API}/auth/users/{user_id}", headers=headers, json={"is_active": False})
    response = await client.post(
        f"{API}/auth/login",
        json={"email": "inativo@opspilot.local", "password": "SenhaForte!2026"},
    )
    assert response.status_code == 401


async def test_roles_catalog_is_available(client: AsyncClient, viewer_token: str) -> None:
    response = await client.get(f"{API}/auth/roles", headers=auth_headers(viewer_token))
    assert response.status_code == 200
    keys = {item["key"] for item in response.json()}
    assert keys == {"ADMIN", "ANALYST", "VIEWER"}


async def test_login_is_audited(client: AsyncClient, admin_token: str) -> None:
    response = await client.get(
        f"{API}/audit/events",
        headers=auth_headers(admin_token),
        params={"action": "auth.login"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert body["items"][0]["actor_email"] == "admin@opspilot.local"
