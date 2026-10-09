"""Normalização de valores vindos de planilhas heterogêneas.

Cada função é pura e lança :class:`FieldError` com mensagem em português quando o
valor não pode ser aproveitado. Vazios são tratados como ``None`` (ausência) e
não como erro — a obrigatoriedade é decidida pelo validador do domínio.
"""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from app.db.models.enums import CustomerStatus

#: Valores textuais tratados como ausência de dado.
EMPTY_TOKENS = frozenset(
    {
        "",
        "-",
        "--",
        "n/a",
        "na",
        "nao informado",
        "não informado",
        "nao informada",
        "sem informacao",
        "sem informação",
        "null",
        "none",
        "nulo",
        "indefinido",
        "#n/d",
        "#n/a",
        "nd",
    }
)

_WS_RE = re.compile(r"\s+")
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
_DIGITS_RE = re.compile(r"\d+")

#: Epoch do serial de datas do Excel (sistema 1900, já descontando o bug do ano 1900).
_EXCEL_EPOCH = date(1899, 12, 30)

DATE_FORMATS = (
    "%d/%m/%Y",
    "%d/%m/%y",
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%Y/%m/%d",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%m/%d/%Y",
)

STATUS_SYNONYMS: dict[str, CustomerStatus] = {
    "ativo": CustomerStatus.ACTIVE,
    "ativa": CustomerStatus.ACTIVE,
    "active": CustomerStatus.ACTIVE,
    "em dia": CustomerStatus.ACTIVE,
    "adimplente": CustomerStatus.ACTIVE,
    "cliente": CustomerStatus.ACTIVE,
    "atrasado": CustomerStatus.PAST_DUE,
    "atrasada": CustomerStatus.PAST_DUE,
    "inadimplente": CustomerStatus.PAST_DUE,
    "em atraso": CustomerStatus.PAST_DUE,
    "past due": CustomerStatus.PAST_DUE,
    "vencido": CustomerStatus.PAST_DUE,
    "cancelado": CustomerStatus.CHURNED,
    "cancelada": CustomerStatus.CHURNED,
    "churn": CustomerStatus.CHURNED,
    "churned": CustomerStatus.CHURNED,
    "inativo": CustomerStatus.CHURNED,
    "inativa": CustomerStatus.CHURNED,
    "encerrado": CustomerStatus.CHURNED,
    "prospect": CustomerStatus.PROSPECT,
    "prospeccao": CustomerStatus.PROSPECT,
    "potencial": CustomerStatus.PROSPECT,
    "lead": CustomerStatus.PROSPECT,
    "em negociacao": CustomerStatus.PROSPECT,
}


class FieldError(ValueError):
    """Valor presente mas inaproveitável para o campo."""


def strip_accents(value: str) -> str:
    """Remove acentos preservando o restante dos caracteres."""
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def to_text(value: Any) -> str | None:
    """Converte qualquer célula em texto limpo, devolvendo ``None`` se vazia."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
    text = _WS_RE.sub(" ", text.replace(" ", " ")).strip()
    if strip_accents(text).lower() in EMPTY_TOKENS:
        return None
    return text or None


def normalize_name(value: Any) -> str | None:
    """Nome/razão social: espaços colapsados e capitalização preservada."""
    text = to_text(value)
    if text is None:
        return None
    text = text.strip(" ,;.-")
    if len(text) < 2:
        raise FieldError("Nome muito curto.")
    if len(text) > 200:
        text = text[:200]
    if text.isupper() or text.islower():
        text = " ".join(
            part
            if len(part) <= 2 and part.lower() in {"de", "da", "do", "e"}
            else part.capitalize()
            for part in text.split(" ")
        )
    return text


def normalize_email(value: Any) -> str | None:
    """E-mail em minúsculas e validado por formato."""
    text = to_text(value)
    if text is None:
        return None
    candidate = text.replace(" ", "").replace(",", ".").lower()
    candidate = candidate.split(";")[0].split("/")[0]
    if not _EMAIL_RE.match(candidate):
        raise FieldError(f"E-mail inválido: {text!r}.")
    if len(candidate) > 254:
        raise FieldError("E-mail excede o tamanho máximo.")
    return candidate


def only_digits(value: str) -> str:
    """Mantém apenas dígitos."""
    return "".join(_DIGITS_RE.findall(value))


def normalize_phone(value: Any, *, default_country: str = "55") -> str | None:
    """Telefone brasileiro em formato E.164 (``+5511987654321``)."""
    text = to_text(value)
    if text is None:
        return None
    digits = only_digits(text)
    if not digits:
        raise FieldError(f"Telefone sem dígitos: {text!r}.")
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) > 11 and digits.startswith(default_country):
        digits = digits[len(default_country) :]
    if len(digits) == 9 or len(digits) == 8:
        raise FieldError("Telefone sem DDD.")
    if len(digits) not in {10, 11}:
        raise FieldError(f"Telefone com quantidade de dígitos inválida: {text!r}.")
    return f"+{default_country}{digits}"


def format_phone_br(value: str | None) -> str | None:
    """Formata para exibição: ``+55 (11) 98765-4321``."""
    if not value:
        return None
    digits = only_digits(value)
    if digits.startswith("55") and len(digits) in {12, 13}:
        digits = digits[2:]
    if len(digits) == 11:
        return f"+55 ({digits[:2]}) {digits[2:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"+55 ({digits[:2]}) {digits[2:6]}-{digits[6:]}"
    return value


def normalize_document(value: Any) -> str | None:
    """CPF (11) ou CNPJ (14) formatado; rejeita tamanhos diferentes."""
    text = to_text(value)
    if text is None:
        return None
    digits = only_digits(text)
    if not digits:
        raise FieldError(f"Documento sem dígitos: {text!r}.")
    if len(digits) == 11:
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
    if len(digits) == 14:
        return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"
    raise FieldError(f"Documento deve ter 11 (CPF) ou 14 (CNPJ) dígitos, recebido {len(digits)}.")


def parse_date(value: Any) -> date | None:
    """Converte para ``date`` aceitando formatos BR/ISO e serial do Excel."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, int | float) and not isinstance(value, bool):
        if isinstance(value, float) and math.isnan(value):
            return None
        serial = int(value)
        if 1 <= serial <= 60000:
            return _EXCEL_EPOCH + timedelta(days=serial)
        raise FieldError(f"Data numérica fora do intervalo aceito: {value!r}.")

    text = to_text(value)
    if text is None:
        return None
    cleaned = text.replace("Z", "").strip()
    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(cleaned, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
        return parsed.date()
    if cleaned.isdigit() and len(cleaned) == 8:  # 20260131
        try:
            return datetime.strptime(cleaned, "%Y%m%d").replace(tzinfo=UTC).date()
        except ValueError as exc:
            raise FieldError(f"Data inválida: {text!r}.") from exc
    raise FieldError(f"Data inválida: {text!r}.")


def parse_money(value: Any) -> Decimal | None:
    """Converte valores monetários BR/US em ``Decimal`` com 2 casas."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"))
    if isinstance(value, bool):
        raise FieldError("Valor monetário inválido.")
    if isinstance(value, int | float):
        if isinstance(value, float) and math.isnan(value):
            return None
        return Decimal(str(round(float(value), 2))).quantize(Decimal("0.01"))

    text = to_text(value)
    if text is None:
        return None
    cleaned = (
        strip_accents(text)
        .lower()
        .replace("r$", "")
        .replace("brl", "")
        .replace("reais", "")
        .replace(" ", "")
        .replace(" ", "")
    )
    negative = cleaned.startswith("-") or (cleaned.startswith("(") and cleaned.endswith(")"))
    cleaned = cleaned.strip("()-+")
    if not cleaned:
        return None

    has_comma, has_dot = "," in cleaned, "." in cleaned
    if has_comma and has_dot:
        # O separador decimal é o que aparece por último.
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif has_comma:
        decimals = len(cleaned.split(",")[-1])
        cleaned = cleaned.replace(",", "." if decimals <= 2 else "")
    elif has_dot:
        decimals = len(cleaned.split(".")[-1])
        if decimals == 3 and cleaned.count(".") >= 1 and len(cleaned.split(".")[0]) <= 3:
            # Padrão 1.234 (milhar) sem casas decimais.
            cleaned = cleaned.replace(".", "")

    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise FieldError(f"Valor monetário inválido: {text!r}.") from exc
    if negative:
        amount = -amount
    if amount < 0:
        raise FieldError(f"Valor monetário negativo não é aceito: {text!r}.")
    if amount > Decimal("9999999999"):
        raise FieldError("Valor monetário acima do limite suportado.")
    return amount.quantize(Decimal("0.01"))


def parse_customer_status(value: Any) -> CustomerStatus | None:
    """Mapeia sinônimos em português para :class:`CustomerStatus`."""
    text = to_text(value)
    if text is None:
        return None
    key = strip_accents(text).lower().strip()
    if key in STATUS_SYNONYMS:
        return STATUS_SYNONYMS[key]
    try:
        return CustomerStatus(key.upper())
    except ValueError as exc:
        raise FieldError(
            f"Situação não reconhecida: {text!r}. Use ativo, atrasado, cancelado ou prospect."
        ) from exc


def normalize_free_text(value: Any, *, max_length: int = 2000) -> str | None:
    """Texto livre (observações) com limite de tamanho."""
    text = to_text(value)
    if text is None:
        return None
    return text[:max_length]


def normalize_source(value: Any) -> str | None:
    """Origem em minúsculas, sem acento, para agrupamento consistente."""
    text = to_text(value)
    if text is None:
        return None
    return strip_accents(text).lower()[:60]
