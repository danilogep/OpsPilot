"""Rotas de autenticação e usuários."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import ContextDep, CurrentUser, RequireAdmin, SessionDep
from app.domains.auth import service
from app.domains.auth.schemas import (
    LoginRequest,
    OrganizationSummary,
    RoleRead,
    TokenResponse,
    UserCreate,
    UserRead,
    UserUpdate,
)

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post("/login", response_model=TokenResponse, summary="Autenticar e obter token")
async def login(payload: LoginRequest, session: SessionDep, context: ContextDep) -> TokenResponse:
    """Valida credenciais e devolve um JWT de acesso."""
    return await service.login(
        session, email=payload.email, password=payload.password, context=context
    )


@router.get("/me", response_model=UserRead, summary="Dados do usuário autenticado")
async def me(user: CurrentUser) -> UserRead:
    """Retorna o perfil do usuário do token."""
    return UserRead.model_validate(user)


@router.get(
    "/me/organization",
    response_model=OrganizationSummary,
    summary="Organização do usuário autenticado",
)
async def my_organization(user: CurrentUser) -> OrganizationSummary:
    """Retorna a organização (tenant) do usuário."""
    return OrganizationSummary.model_validate(user.organization)


@router.get("/roles", response_model=list[RoleRead], summary="Catálogo de papéis")
async def roles(session: SessionDep, _user: CurrentUser) -> list[RoleRead]:
    """Lista papéis e suas permissões para exibição na interface."""
    return [RoleRead.model_validate(role) for role in await service.list_roles(session)]


@router.get("/users", response_model=list[UserRead], summary="Listar usuários")
async def list_users(session: SessionDep, admin: RequireAdmin) -> list[UserRead]:
    """Lista os usuários da organização (somente ADMIN)."""
    users = await service.list_users(session, organization_id=admin.organization_id)
    return [UserRead.model_validate(item) for item in users]


@router.post(
    "/users",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Criar usuário",
)
async def create_user(
    payload: UserCreate, session: SessionDep, admin: RequireAdmin, context: ContextDep
) -> UserRead:
    """Cria um usuário na organização do administrador (somente ADMIN)."""
    user = await service.create_user(
        session,
        organization_id=admin.organization_id,
        payload=payload,
        actor=admin,
        context=context,
    )
    return UserRead.model_validate(user)


@router.patch("/users/{user_id}", response_model=UserRead, summary="Atualizar usuário")
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    session: SessionDep,
    admin: RequireAdmin,
    context: ContextDep,
) -> UserRead:
    """Atualiza dados de um usuário da organização (somente ADMIN)."""
    user = await service.update_user(
        session,
        organization_id=admin.organization_id,
        user_id=user_id,
        payload=payload,
        actor=admin,
        context=context,
    )
    return UserRead.model_validate(user)
