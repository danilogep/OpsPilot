"""Infraestrutura de testes.

Estratégia: um banco SQLite por sessão de testes, schema criado uma vez e cada
teste isolado em uma transação revertida no final (``join_transaction_mode``
com savepoints). A dependência ``get_session`` da aplicação é sobrescrita para
usar a mesma sessão do teste, de modo que rotas e serviços compartilhem estado.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

# A configuração é lida no import de app.core.config: definir antes de importar app.
_TEST_DB_DIR = Path(tempfile.gettempdir()) / "opspilot-tests"
_TEST_DB_DIR.mkdir(parents=True, exist_ok=True)
_TEST_DB_PATH = _TEST_DB_DIR / f"test-{uuid.uuid4().hex}.db"

os.environ.setdefault("OPSPILOT_ENVIRONMENT", "test")
os.environ["OPSPILOT_DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB_PATH.as_posix()}"
os.environ["OPSPILOT_JWT_SECRET"] = "test-secret-not-used-in-production"
os.environ["OPSPILOT_LLM_PROVIDER"] = "mock"
os.environ["OPSPILOT_DEMO_PASSWORD"] = "DemoTest!2026"
os.environ["OPSPILOT_UPLOAD_DIR"] = str(_TEST_DB_DIR / "uploads")
os.environ["OPSPILOT_LOG_LEVEL"] = "WARNING"

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.models import Organization, User, UserRole  # noqa: E402
from app.db.session import dispose_engine, get_engine, get_session  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402

DEMO_PASSWORD = os.environ["OPSPILOT_DEMO_PASSWORD"]


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session", autouse=True)
async def _create_schema() -> AsyncIterator[None]:
    """Cria o schema uma única vez por sessão de testes."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await dispose_engine()
    _TEST_DB_PATH.unlink(missing_ok=True)


async def _truncate_all() -> None:
    """Esvazia todas as tabelas, respeitando a ordem das chaves estrangeiras.

    O driver do SQLite não suporta o padrão "transação externa + savepoint" de
    forma confiável, então o isolamento entre testes é feito limpando o banco
    antes de cada teste. É rápido o suficiente e não depende do dialeto.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Sessão de teste em banco limpo."""
    await _truncate_all()
    factory = async_sessionmaker(bind=get_engine(), expire_on_commit=False, autoflush=False)
    async with factory() as test_session:
        yield test_session


@pytest.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """Cliente HTTP ligado à sessão do teste."""

    async def _override() -> AsyncIterator[AsyncSession]:
        yield session

    fastapi_app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
async def seeded(session: AsyncSession) -> Organization:
    """Executa o seed de demonstração completo dentro da transação do teste."""
    from app.db.seed import run_seed

    report = await run_seed(session)
    assert report.organization_id is not None
    organization = await session.get(Organization, report.organization_id)
    assert organization is not None
    return organization


@pytest.fixture
async def demo_users(seeded: Organization, session: AsyncSession) -> dict[UserRole, User]:
    """Mapa papel -> usuário de demonstração."""
    from sqlalchemy import select

    users = (
        (await session.execute(select(User).where(User.organization_id == seeded.id)))
        .scalars()
        .all()
    )
    return {user.role: user for user in users}


async def login(client: AsyncClient, email: str, password: str = DEMO_PASSWORD) -> str:
    """Faz login e devolve o token de acesso."""
    response = await client.post(
        f"{settings.api_v1_prefix}/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    token: str = response.json()["access_token"]
    return token


def auth_headers(token: str) -> dict[str, str]:
    """Cabeçalho Authorization para as requisições autenticadas."""
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def admin_token(client: AsyncClient, seeded: Organization) -> str:
    return await login(client, "admin@opspilot.local")


@pytest.fixture
async def analyst_token(client: AsyncClient, seeded: Organization) -> str:
    return await login(client, "analyst@opspilot.local")


@pytest.fixture
async def viewer_token(client: AsyncClient, seeded: Organization) -> str:
    return await login(client, "viewer@opspilot.local")
