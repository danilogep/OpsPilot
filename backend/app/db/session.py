"""Engine assíncrona, factory de sessões e dependência FastAPI."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _engine_kwargs(url: str) -> dict[str, Any]:
    """Opções específicas por dialeto."""
    kwargs: dict[str, Any] = {"echo": settings.db_echo, "future": True}
    if url.startswith("postgresql"):
        kwargs |= {"pool_size": 10, "max_overflow": 20, "pool_pre_ping": True}
    else:
        # SQLite (testes/desenvolvimento): sem pool dimensionável.
        kwargs |= {"connect_args": {"check_same_thread": False}}
    return kwargs


def get_engine() -> AsyncEngine:
    """Engine singleton do processo."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url, **_engine_kwargs(settings.database_url)
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Factory singleton de sessões."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            autoflush=False,
        )
    return _sessionmaker


async def dispose_engine() -> None:
    """Fecha o pool (shutdown da aplicação e testes)."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def get_session() -> AsyncIterator[AsyncSession]:
    """Dependência FastAPI: uma sessão por requisição, com rollback em erro."""
    factory = get_sessionmaker()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
