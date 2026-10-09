"""Agregação dos routers da API v1."""

from __future__ import annotations

from fastapi import APIRouter

from app.domains.audit.router import router as audit_router
from app.domains.auth.router import router as auth_router
from app.domains.imports.router import router as imports_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(imports_router)
api_router.include_router(audit_router)
