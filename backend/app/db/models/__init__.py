"""Modelos SQLAlchemy do OpsPilot.

Importar este pacote registra todas as tabelas no ``Base.metadata`` — é o que o
Alembic e os testes usam para criar o schema.
"""

from __future__ import annotations

from app.db.base import Base
from app.db.models.ai import AgentDefinition, AgentRun, LLMUsage
from app.db.models.audit import AuditEvent
from app.db.models.crm import Customer, Plan, Renewal
from app.db.models.enums import (
    AgentRunStatus,
    CompanySize,
    CustomerStatus,
    DocumentStatus,
    ImportStatus,
    LeadCategory,
    LeadEventType,
    LeadStatus,
    LLMCallStatus,
    RenewalStatus,
    RowStatus,
    ScoringMethod,
    UserRole,
    WebhookDirection,
    WebhookStatus,
)
from app.db.models.imports import ImportColumnMapping, ImportJob, RawImportRow
from app.db.models.integrations import WebhookEvent
from app.db.models.knowledge import DocumentChunk, KnowledgeDocument
from app.db.models.leads import Lead, LeadEvent
from app.db.models.organization import ApiCredential, Organization, Role, User

__all__ = [
    "AgentDefinition",
    "AgentRun",
    "AgentRunStatus",
    "ApiCredential",
    "AuditEvent",
    "Base",
    "CompanySize",
    "Customer",
    "CustomerStatus",
    "DocumentChunk",
    "DocumentStatus",
    "ImportColumnMapping",
    "ImportJob",
    "ImportStatus",
    "KnowledgeDocument",
    "LLMCallStatus",
    "LLMUsage",
    "Lead",
    "LeadCategory",
    "LeadEvent",
    "LeadEventType",
    "LeadStatus",
    "Organization",
    "Plan",
    "RawImportRow",
    "Renewal",
    "RenewalStatus",
    "Role",
    "RowStatus",
    "ScoringMethod",
    "User",
    "UserRole",
    "WebhookDirection",
    "WebhookEvent",
    "WebhookStatus",
]
