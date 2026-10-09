"""Dependências HTTP compartilhadas: sessão, usuário autenticado e autorização."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthenticationError, PermissionDeniedError
from app.core.security import decode_access_token
from app.db.models import User, UserRole
from app.db.session import get_session

bearer_scheme = HTTPBearer(auto_error=False, description="Token JWT obtido em /auth/login")

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    """Resolve o usuário a partir do token Bearer."""
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Autenticação obrigatória.")
    claims = decode_access_token(credentials.credentials)
    try:
        user_id = uuid.UUID(str(claims.get("sub")))
    except (TypeError, ValueError) as exc:
        raise AuthenticationError("Token inválido.") from exc

    user = (
        await session.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise AuthenticationError("Usuário inativo ou inexistente.")
    if str(user.organization_id) != str(claims.get("org")):
        raise AuthenticationError("Token não corresponde à organização do usuário.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(
    *roles: UserRole,
) -> Callable[[User], Coroutine[Any, Any, User]]:
    """Fábrica de dependência que exige um dos papéis informados."""
    allowed = set(roles)

    async def _dependency(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise PermissionDeniedError(
                "Seu perfil não permite esta ação.",
                details={"required_roles": sorted(role.value for role in allowed)},
            )
        return user

    return _dependency


#: Leitura: todos os papéis autenticados.
RequireViewer = Annotated[
    User, Depends(require_roles(UserRole.ADMIN, UserRole.ANALYST, UserRole.VIEWER))
]
#: Escrita de dados operacionais.
RequireAnalyst = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.ANALYST))]
#: Administração (usuários, integrações, configurações).
RequireAdmin = Annotated[User, Depends(require_roles(UserRole.ADMIN))]


class RequestContext:
    """Metadados da requisição usados na auditoria."""

    __slots__ = ("correlation_id", "ip_address", "user_agent")

    def __init__(self, ip_address: str | None, user_agent: str | None, correlation_id: str) -> None:
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.correlation_id = correlation_id


def get_request_context(request: Request) -> RequestContext:
    """Extrai IP, user-agent e correlation id da requisição."""
    client_host = request.client.host if request.client else None
    return RequestContext(
        ip_address=client_host,
        user_agent=(request.headers.get("user-agent") or "")[:300] or None,
        correlation_id=str(getattr(request.state, "correlation_id", "")),
    )


ContextDep = Annotated[RequestContext, Depends(get_request_context)]
