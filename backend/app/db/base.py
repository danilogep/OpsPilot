"""Base declarativa, mixins e utilitários de tipo portáveis.

Decisões:

* Identificador público é ``UUID`` (``sqlalchemy.Uuid``): nativo no PostgreSQL,
  ``CHAR(32)`` nos dialetos sem suporte (SQLite dos testes).
* ``JSONB`` no PostgreSQL com variante ``JSON`` genérica nos demais dialetos.
* Datas/horas sempre em UTC (``timezone=True``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, MetaData, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

#: JSON portátil: JSONB no PostgreSQL, JSON genérico no restante.
JSONType = JSON().with_variant(JSONB(), "postgresql")


def enum_type(enum_cls: type, *, length: int = 32) -> Enum:
    """Coluna de enumeração portátil (VARCHAR + CHECK, sem tipo nativo)."""
    return Enum(
        enum_cls,
        native_enum=False,
        length=length,
        validate_strings=True,
        values_callable=lambda cls: [member.value for member in cls],
    )


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    """Horário atual em UTC, com timezone explícito."""
    return datetime.now(UTC)


def ensure_utc(value: datetime | None) -> datetime | None:
    """Normaliza um datetime para UTC consciente de timezone.

    Necessário porque o SQLite devolve valores ingênuos (sem timezone).
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class Base(DeclarativeBase):
    """Base declarativa de todos os modelos."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    type_annotation_map = {  # noqa: RUF012
        uuid.UUID: Uuid(as_uuid=True),
        datetime: DateTime(timezone=True),
        dict[str, Any]: JSONType,
        list[str]: JSONType,
        list[dict[str, Any]]: JSONType,
    }

    def __repr__(self) -> str:  # pragma: no cover - conveniência de debug
        pk = getattr(self, "id", None)
        return f"<{type(self).__name__} id={pk}>"


class UUIDPrimaryKeyMixin:
    """Chave primária UUID gerada na aplicação."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    """Marcas de criação e atualização."""

    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class SoftDeleteMixin:
    """Exclusão lógica: registros com ``deleted_at`` preenchido são ignorados."""

    deleted_at: Mapped[datetime | None] = mapped_column(default=None, index=True)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class OrgScopedMixin:
    """Isolamento multi-tenant obrigatório por ``organization_id``."""

    @declared_attr
    @classmethod
    def organization_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(
            ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
