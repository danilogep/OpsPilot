"""Agregação dos routers da API v1."""

from __future__ import annotations

from fastapi import APIRouter

from app.domains.audit.router import router as audit_router
from app.domains.auth.router import router as auth_router
from app.domains.customers.router import router as customers_router
from app.domains.imports.router import router as imports_router
from app.domains.leads.router import router as leads_router
from app.domains.organizations.router import router as dashboard_router
from app.domains.plans.router import router as plans_router
from app.domains.renewals.router import router as renewals_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(dashboard_router)
api_router.include_router(imports_router)
api_router.include_router(customers_router)
api_router.include_router(plans_router)
api_router.include_router(renewals_router)
api_router.include_router(leads_router)
api_router.include_router(audit_router)
