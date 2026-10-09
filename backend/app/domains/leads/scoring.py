"""Score determinístico de leads.

Regras explícitas, reproduzíveis e auditáveis: a mesma entrada sempre produz o
mesmo score, com a justificativa de cada critério. Soma máxima: 100 pontos.

Critérios e pesos:

| Critério                  | Peso |
| ------------------------- | ---- |
| Dados de contato          | 20   |
| Orçamento estimado        | 18   |
| Segmento compatível       | 15   |
| Recência da interação     | 15   |
| Porte da empresa          | 12   |
| Interesse declarado       | 10   |
| Origem do lead            | 10   |
"""

from __future__ import annotations

import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal

from app.db.base import ensure_utc, utcnow
from app.db.models.enums import CompanySize, LeadCategory

SCORE_VERSION = "rules-v1"

HOT_THRESHOLD = 70
WARM_THRESHOLD = 45

WEIGHTS: dict[str, int] = {
    "contact": 20,
    "budget": 18,
    "segment": 15,
    "recency": 15,
    "company_size": 12,
    "interest": 10,
    "source": 10,
}

#: Segmentos prioritários do playbook comercial (ver base de conhecimento).
PRIORITY_SEGMENTS = frozenset(
    {
        "servicos profissionais",
        "servicos",
        "saude",
        "educacao",
        "varejo",
        "varejo local",
        "tecnologia",
        "contabilidade",
    }
)
NEUTRAL_SEGMENTS = frozenset({"industria", "logistica", "construcao", "alimentacao"})

#: Origens inbound valem mais que listas frias.
INBOUND_SOURCES = frozenset({"indicacao", "site", "organico", "evento", "webinar"})
MARKETING_SOURCES = frozenset({"google ads", "meta ads", "redes sociais", "email marketing"})
OUTBOUND_SOURCES = frozenset({"prospeccao", "lista", "outbound", "cold call"})

COMPANY_SIZE_POINTS: dict[CompanySize, int] = {
    CompanySize.SMALL: 12,
    CompanySize.MEDIUM: 12,
    CompanySize.LARGE: 9,
    CompanySize.MICRO: 8,
    CompanySize.MEI: 4,
    CompanySize.UNKNOWN: 2,
}


@dataclass(frozen=True, slots=True)
class ScoreReason:
    """Justificativa de um critério do score."""

    criterion: str
    label: str
    points: int
    max_points: int
    detail: str


@dataclass(frozen=True, slots=True)
class LeadScoreInput:
    """Entrada normalizada do cálculo de score."""

    email: str | None = None
    phone: str | None = None
    segment: str | None = None
    company_size: CompanySize = CompanySize.UNKNOWN
    interest: str | None = None
    estimated_value: Decimal = Decimal("0")
    source: str = "indefinido"
    last_interaction_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ScoreResult:
    """Resultado completo e auditável do score."""

    score: int
    category: LeadCategory
    version: str
    reasons: list[ScoreReason] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    next_step: str = ""

    def reasons_as_dicts(self) -> list[dict[str, object]]:
        """Serializa as justificativas para persistência em JSON."""
        return [asdict(reason) for reason in self.reasons]


def _strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.strip().lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _score_contact(data: LeadScoreInput) -> ScoreReason:
    has_email = bool(data.email and "@" in data.email)
    has_phone = bool(data.phone and len(_digits(data.phone)) >= 10)
    if has_email and has_phone:
        return ScoreReason(
            "contact", "Dados de contato", 20, 20, "E-mail e telefone válidos informados."
        )
    if has_email or has_phone:
        canal = "E-mail" if has_email else "Telefone"
        return ScoreReason(
            "contact", "Dados de contato", 12, 20, f"Apenas {canal.lower()} disponível."
        )
    return ScoreReason("contact", "Dados de contato", 0, 20, "Nenhum contato válido informado.")


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def _score_budget(data: LeadScoreInput) -> ScoreReason:
    value = Decimal(data.estimated_value or 0)
    label = "Orçamento estimado"
    if value >= Decimal("2000"):
        return ScoreReason("budget", label, 18, 18, "Orçamento acima de R$ 2.000,00.")
    if value >= Decimal("1000"):
        return ScoreReason("budget", label, 14, 18, "Orçamento entre R$ 1.000,00 e R$ 2.000,00.")
    if value >= Decimal("500"):
        return ScoreReason("budget", label, 10, 18, "Orçamento entre R$ 500,00 e R$ 1.000,00.")
    if value > 0:
        return ScoreReason("budget", label, 6, 18, "Orçamento informado abaixo de R$ 500,00.")
    return ScoreReason("budget", label, 0, 18, "Orçamento não informado.")


def _score_segment(data: LeadScoreInput) -> ScoreReason:
    label = "Segmento compatível"
    if not data.segment:
        return ScoreReason("segment", label, 4, 15, "Segmento não informado.")
    normalized = _strip_accents(data.segment)
    if normalized in PRIORITY_SEGMENTS:
        return ScoreReason("segment", label, 15, 15, f"Segmento prioritário: {data.segment}.")
    if normalized in NEUTRAL_SEGMENTS:
        return ScoreReason("segment", label, 8, 15, f"Segmento atendido: {data.segment}.")
    return ScoreReason("segment", label, 2, 15, f"Segmento fora do foco: {data.segment}.")


def _score_recency(data: LeadScoreInput, *, now: datetime) -> ScoreReason:
    label = "Recência da interação"
    moment = ensure_utc(data.last_interaction_at)
    if moment is None:
        return ScoreReason("recency", label, 0, 15, "Nenhuma interação registrada.")
    days = max(0, (now - moment).days)
    if days <= 3:
        return ScoreReason("recency", label, 15, 15, f"Interação há {days} dia(s).")
    if days <= 7:
        return ScoreReason("recency", label, 12, 15, f"Interação há {days} dias.")
    if days <= 15:
        return ScoreReason("recency", label, 8, 15, f"Interação há {days} dias.")
    if days <= 30:
        return ScoreReason("recency", label, 4, 15, f"Interação há {days} dias.")
    return ScoreReason("recency", label, 0, 15, f"Sem interação há {days} dias.")


def _score_company_size(data: LeadScoreInput) -> ScoreReason:
    points = COMPANY_SIZE_POINTS.get(data.company_size, 2)
    descriptions = {
        CompanySize.MEI: "MEI",
        CompanySize.MICRO: "microempresa",
        CompanySize.SMALL: "pequena empresa",
        CompanySize.MEDIUM: "média empresa",
        CompanySize.LARGE: "grande empresa",
        CompanySize.UNKNOWN: "porte não informado",
    }
    return ScoreReason(
        "company_size",
        "Porte da empresa",
        points,
        12,
        f"Porte: {descriptions.get(data.company_size, 'não informado')}.",
    )


def _score_interest(data: LeadScoreInput) -> ScoreReason:
    label = "Interesse declarado"
    if data.interest and data.interest.strip():
        return ScoreReason("interest", label, 10, 10, f"Interesse: {data.interest.strip()}.")
    return ScoreReason("interest", label, 0, 10, "Interesse não declarado.")


def _score_source(data: LeadScoreInput) -> ScoreReason:
    label = "Origem do lead"
    normalized = _strip_accents(data.source or "")
    if normalized in INBOUND_SOURCES:
        return ScoreReason("source", label, 10, 10, f"Origem inbound: {data.source}.")
    if normalized in MARKETING_SOURCES:
        return ScoreReason("source", label, 6, 10, f"Origem paga: {data.source}.")
    if normalized in OUTBOUND_SOURCES:
        return ScoreReason("source", label, 3, 10, f"Origem outbound: {data.source}.")
    return ScoreReason("source", label, 1, 10, "Origem não classificada.")


def _risks(data: LeadScoreInput, reasons: list[ScoreReason]) -> list[str]:
    risks: list[str] = []
    by_criterion = {reason.criterion: reason for reason in reasons}
    if by_criterion["contact"].points == 0:
        risks.append("Lead sem canal de contato válido.")
    if by_criterion["budget"].points == 0:
        risks.append("Orçamento não informado — proposta pode não ter aderência.")
    if by_criterion["recency"].points <= 4:
        risks.append("Interação antiga: risco de o lead já ter resolvido com outro fornecedor.")
    if by_criterion["segment"].points <= 2:
        risks.append("Segmento fora dos prioritários do playbook.")
    if data.company_size is CompanySize.UNKNOWN:
        risks.append("Porte da empresa desconhecido.")
    return risks


def _next_step(category: LeadCategory, reasons: list[ScoreReason]) -> str:
    by_criterion = {reason.criterion: reason for reason in reasons}
    if by_criterion["contact"].points == 0:
        return "Enriquecer o cadastro com e-mail ou telefone antes de qualquer abordagem."
    if category is LeadCategory.HOT:
        return "Agendar reunião de diagnóstico em até 1 dia útil e preparar proposta."
    if category is LeadCategory.WARM:
        if by_criterion["budget"].points == 0:
            return "Fazer ligação de qualificação para levantar orçamento e urgência."
        return "Enviar mensagem de retomada e propor conversa de 15 minutos."
    return "Incluir em fluxo de nutrição e revisar em 30 dias."


def categorize(score: int) -> LeadCategory:
    """Converte o score numérico em categoria."""
    if score >= HOT_THRESHOLD:
        return LeadCategory.HOT
    if score >= WARM_THRESHOLD:
        return LeadCategory.WARM
    return LeadCategory.COLD


def score_lead(data: LeadScoreInput, *, now: datetime | None = None) -> ScoreResult:
    """Calcula o score determinístico do lead."""
    moment = ensure_utc(now) or utcnow()
    reasons = [
        _score_contact(data),
        _score_budget(data),
        _score_segment(data),
        _score_recency(data, now=moment),
        _score_company_size(data),
        _score_interest(data),
        _score_source(data),
    ]
    total = min(100, sum(reason.points for reason in reasons))
    category = categorize(total)
    return ScoreResult(
        score=total,
        category=category,
        version=SCORE_VERSION,
        reasons=reasons,
        risks=_risks(data, reasons),
        next_step=_next_step(category, reasons),
    )
