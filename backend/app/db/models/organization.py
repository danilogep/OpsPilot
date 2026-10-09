"""Organização, catálogo de papéis e usuários."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    Base,
    OrgScopedMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_type,
)
from app.db.models.enums import UserRole


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Empresa cliente do OpsPilot (tenant)."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    document: Mapped[str | None] = mapped_column(String(32), default=None)
    settings: Mapped[dict[str, Any]] = mapped_column(default=dict)

    users: Mapped[list[User]] = relationship(back_populates="organization", lazy="raise")


class Role(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Catálogo de papéis exibido na interface.

    A autorização em runtime usa ``User.role`` (enum :class:`UserRole`);
    esta tabela documenta nome, descrição e permissões de cada papel.
    """

    __tablename__ = "roles"

    key: Mapped[UserRole] = mapped_column(enum_type(UserRole, length=16), unique=True)
    name: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(String(300))
    permissions: Mapped[list[str]] = mapped_column(default=list)


class User(UUIDPrimaryKeyMixin, OrgScopedMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Usuário autenticável, sempre vinculado a uma organização."""

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("organization_id", "email", name="org_email"),)

    email: Mapped[str] = mapped_column(String(254), index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(enum_type(UserRole, length=16), default=UserRole.VIEWER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(default=None)

    organization: Mapped[Organization] = relationship(back_populates="users", lazy="joined")

    @property
    def is_admin(self) -> bool:
        return self.role is UserRole.ADMIN


class ApiCredential(UUIDPrimaryKeyMixin, OrgScopedMixin, TimestampMixin, Base):
    """Metadados de credenciais externas.

    Guarda apenas rótulo, provedor e os últimos caracteres do identificador para
    exibição. **Nenhum segredo é persistido** — chaves reais vivem em variáveis
    de ambiente.
    """

    __tablename__ = "api_credentials"

    provider: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(80))
    masked_hint: Mapped[str] = mapped_column(String(16), default="")
    is_configured: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
