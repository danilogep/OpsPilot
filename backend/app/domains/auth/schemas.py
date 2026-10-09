"""Schemas de autenticação e usuários."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.types import Email
from app.db.models.enums import UserRole


class LoginRequest(BaseModel):
    """Credenciais de login."""

    email: Email
    password: str = Field(min_length=6, max_length=128)


class OrganizationSummary(BaseModel):
    """Organização resumida, para o contexto da sessão."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str


class UserRead(BaseModel):
    """Usuário exposto pela API (sem hash de senha)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    email: Email
    full_name: str
    role: UserRole
    is_active: bool
    last_login_at: datetime | None = None
    created_at: datetime


class TokenResponse(BaseModel):
    """Resposta do login."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserRead
    organization: OrganizationSummary


class UserCreate(BaseModel):
    """Criação de usuário (apenas ADMIN)."""

    email: Email
    full_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.VIEWER


class UserUpdate(BaseModel):
    """Atualização parcial de usuário (apenas ADMIN)."""

    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class RoleRead(BaseModel):
    """Papel do catálogo exibido em Configurações."""

    model_config = ConfigDict(from_attributes=True)

    key: UserRole
    name: str
    description: str
    permissions: list[str]
