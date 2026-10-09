"""Enumerações de domínio.

Todas são persistidas como ``VARCHAR`` com CHECK constraint (``native_enum=False``),
o que mantém as migrations portáveis entre PostgreSQL e SQLite.
"""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    """Papéis de acesso. Fonte da verdade para autorização."""

    ADMIN = "ADMIN"
    ANALYST = "ANALYST"
    VIEWER = "VIEWER"


class ImportStatus(StrEnum):
    """Ciclo de vida de uma importação."""

    UPLOADED = "UPLOADED"
    MAPPED = "MAPPED"
    VALIDATED = "VALIDATED"
    COMMITTED = "COMMITTED"
    FAILED = "FAILED"


class RowStatus(StrEnum):
    """Resultado da validação de uma linha."""

    PENDING = "PENDING"
    VALID = "VALID"
    INVALID = "INVALID"
    DUPLICATE = "DUPLICATE"
    IMPORTED = "IMPORTED"


class CustomerStatus(StrEnum):
    """Situação comercial do cliente."""

    ACTIVE = "ACTIVE"
    PAST_DUE = "PAST_DUE"
    CHURNED = "CHURNED"
    PROSPECT = "PROSPECT"


class RenewalStatus(StrEnum):
    """Situação de uma renovação."""

    SCHEDULED = "SCHEDULED"
    AT_RISK = "AT_RISK"
    CONFIRMED = "CONFIRMED"
    LOST = "LOST"


class LeadStatus(StrEnum):
    """Estágio do lead no funil."""

    NEW = "NEW"
    CONTACTED = "CONTACTED"
    QUALIFIED = "QUALIFIED"
    PROPOSAL = "PROPOSAL"
    WON = "WON"
    LOST = "LOST"


class LeadCategory(StrEnum):
    """Categoria derivada do score."""

    HOT = "HOT"
    WARM = "WARM"
    COLD = "COLD"


class CompanySize(StrEnum):
    """Porte declarado da empresa do lead."""

    MEI = "MEI"
    MICRO = "MICRO"
    SMALL = "SMALL"
    MEDIUM = "MEDIUM"
    LARGE = "LARGE"
    UNKNOWN = "UNKNOWN"


class LeadEventType(StrEnum):
    """Tipos de evento no histórico do lead."""

    CREATED = "CREATED"
    UPDATED = "UPDATED"
    NOTE = "NOTE"
    STATUS_CHANGED = "STATUS_CHANGED"
    SCORED = "SCORED"
    CONTACTED = "CONTACTED"
    WEBHOOK = "WEBHOOK"


class ScoringMethod(StrEnum):
    """Origem do score do lead."""

    RULES = "RULES"
    LLM = "LLM"


class DocumentStatus(StrEnum):
    """Situação do documento na base de conhecimento."""

    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class AgentRunStatus(StrEnum):
    """Resultado da execução de um agente."""

    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    ERROR = "ERROR"
    MAX_STEPS = "MAX_STEPS"


class LLMCallStatus(StrEnum):
    """Resultado de uma chamada ao provider de IA."""

    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"


class WebhookDirection(StrEnum):
    """Direção do evento de webhook."""

    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"


class WebhookStatus(StrEnum):
    """Situação de processamento do evento de webhook."""

    RECEIVED = "RECEIVED"
    PROCESSED = "PROCESSED"
    DUPLICATE = "DUPLICATE"
    FAILED = "FAILED"
    SENT = "SENT"
    SKIPPED = "SKIPPED"
