"""Regras de autenticação e gestão de usuários."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequestContext
from app.core.config import settings
from app.core.errors import AuthenticationError, ConflictError, NotFoundError
from app.core.logging import get_logger
from app.core.security import create_access_token, hash_password, verify_password
from app.db.base import utcnow
from app.db.models import Organization, Role, User, UserRole
from app.domains.audit import service as audit_service
from app.domains.auth.schemas import (
    OrganizationSummary,
    TokenResponse,
    UserCreate,
    UserRead,
    UserUpdate,
)

logger = get_logger(__name__)


async def login(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    context: RequestContext | None = None,
) -> TokenResponse:
    """Autentica o usuário, registra auditoria e devolve o token."""
    normalized = email.strip().lower()
    user = (
        await session.execute(
            select(User).where(func.lower(User.email) == normalized, User.deleted_at.is_(None))
        )
    ).scalar_one_or_none()

    if user is None or not verify_password(password, user.password_hash) or not user.is_active:
        if user is not None:
            await audit_service.record_audit(
                session,
                organization_id=user.organization_id,
                action=audit_service.ACTION_LOGIN_FAILED,
                entity_type="user",
                entity_id=str(user.id),
                actor_email=normalized,
                summary="Tentativa de login malsucedida.",
                context=context,
            )
            await session.commit()
        logger.info("login_failed", email_domain=normalized.split("@")[-1])
        raise AuthenticationError("E-mail ou senha inválidos.")

    organization = (
        await session.execute(select(Organization).where(Organization.id == user.organization_id))
    ).scalar_one()

    user.last_login_at = utcnow()
    await audit_service.record_audit(
        session,
        organization_id=user.organization_id,
        action=audit_service.ACTION_LOGIN,
        entity_type="user",
        entity_id=str(user.id),
        actor=user,
        summary=f"Login realizado por {user.email}.",
        context=context,
    )
    await session.commit()
    await session.refresh(user)

    token = create_access_token(
        user_id=user.id,
        organization_id=user.organization_id,
        role=user.role.value,
        email=user.email,
    )
    logger.info("login_success", user_id=str(user.id), role=user.role.value)
    return TokenResponse(
        access_token=token,
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserRead.model_validate(user),
        organization=OrganizationSummary.model_validate(organization),
    )


async def list_users(session: AsyncSession, *, organization_id: uuid.UUID) -> list[User]:
    """Usuários ativos e inativos da organização."""
    rows = (
        (
            await session.execute(
                select(User)
                .where(User.organization_id == organization_id, User.deleted_at.is_(None))
                .order_by(User.full_name)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def create_user(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    payload: UserCreate,
    actor: User,
    context: RequestContext | None = None,
) -> User:
    """Cria um usuário na organização do ator."""
    email = payload.email.strip().lower()
    exists = (
        await session.execute(
            select(User.id).where(
                User.organization_id == organization_id,
                func.lower(User.email) == email,
                User.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if exists:
        raise ConflictError("Já existe um usuário com este e-mail nesta organização.")

    user = User(
        organization_id=organization_id,
        email=email,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    session.add(user)
    await session.flush()
    await audit_service.record_audit(
        session,
        organization_id=organization_id,
        action="user.created",
        entity_type="user",
        entity_id=str(user.id),
        actor=actor,
        summary=f"Usuário {user.email} criado com perfil {user.role.value}.",
        context=context,
    )
    await session.commit()
    await session.refresh(user)
    return user


async def update_user(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: UserUpdate,
    actor: User,
    context: RequestContext | None = None,
) -> User:
    """Atualiza nome, papel, status ou senha de um usuário."""
    user = (
        await session.execute(
            select(User).where(
                User.id == user_id,
                User.organization_id == organization_id,
                User.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if user is None:
        raise NotFoundError("Usuário não encontrado.")

    changes: dict[str, object] = {}
    if payload.full_name is not None and payload.full_name != user.full_name:
        changes["full_name"] = payload.full_name
        user.full_name = payload.full_name.strip()
    if payload.role is not None and payload.role != user.role:
        changes["role"] = payload.role.value
        user.role = payload.role
    if payload.is_active is not None and payload.is_active != user.is_active:
        changes["is_active"] = payload.is_active
        user.is_active = payload.is_active
    if payload.password:
        changes["password"] = "***"
        user.password_hash = hash_password(payload.password)

    if changes:
        await audit_service.record_audit(
            session,
            organization_id=organization_id,
            action="user.updated",
            entity_type="user",
            entity_id=str(user.id),
            actor=actor,
            summary=f"Usuário {user.email} atualizado.",
            meta={"changes": changes},
            context=context,
        )
    await session.commit()
    await session.refresh(user)
    return user


async def list_roles(session: AsyncSession) -> list[Role]:
    """Catálogo de papéis (seedado); usado na tela de Configurações."""
    rows = (await session.execute(select(Role).order_by(Role.key))).scalars().all()
    if rows:
        return list(rows)
    # Catálogo mínimo em memória caso o seed ainda não tenha rodado.
    return [
        Role(
            key=key,
            name=ROLE_NAMES[key],
            description=ROLE_DESCRIPTIONS[key],
            permissions=ROLE_PERMISSIONS[key],
        )
        for key in (UserRole.ADMIN, UserRole.ANALYST, UserRole.VIEWER)
    ]


ROLE_NAMES: dict[UserRole, str] = {
    UserRole.ADMIN: "Administrador",
    UserRole.ANALYST: "Analista",
    UserRole.VIEWER: "Visualizador",
}

ROLE_DESCRIPTIONS: dict[UserRole, str] = {
    UserRole.ADMIN: "Acesso total, incluindo usuários, integrações e configurações.",
    UserRole.ANALYST: "Acesso a dados, importações, dashboard e recursos de IA.",
    UserRole.VIEWER: "Acesso somente leitura a dashboard, clientes, leads e renovações.",
}

ROLE_PERMISSIONS: dict[UserRole, list[str]] = {
    UserRole.ADMIN: [
        "dashboard:read",
        "customers:write",
        "leads:write",
        "renewals:write",
        "imports:write",
        "knowledge:write",
        "assistant:use",
        "integrations:manage",
        "audit:read",
        "users:manage",
    ],
    UserRole.ANALYST: [
        "dashboard:read",
        "customers:write",
        "leads:write",
        "renewals:write",
        "imports:write",
        "knowledge:write",
        "assistant:use",
        "audit:read",
    ],
    UserRole.VIEWER: [
        "dashboard:read",
        "customers:read",
        "leads:read",
        "renewals:read",
        "imports:read",
        "knowledge:read",
    ],
}
