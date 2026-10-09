"""Paginação e ordenação reutilizáveis."""

from __future__ import annotations

from fastapi import Query
from pydantic import BaseModel, Field

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 200


class PageParams(BaseModel):
    """Parâmetros de página vindos da query string."""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def page_params(
    page: int = Query(1, ge=1, description="Página (começa em 1)"),
    page_size: int = Query(
        DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Itens por página"
    ),
) -> PageParams:
    """Dependência FastAPI para paginação."""
    return PageParams(page=page, page_size=page_size)


class Page[T](BaseModel):
    """Envelope padrão de listagem paginada."""

    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def build(cls, items: list[T], total: int, params: PageParams) -> Page[T]:
        pages = (total + params.page_size - 1) // params.page_size if total else 0
        return cls(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size,
            pages=pages,
        )
