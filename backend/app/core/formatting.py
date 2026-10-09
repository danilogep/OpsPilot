"""Formatação de números, valores e datas em português do Brasil."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


def format_brl(value: Any) -> str:
    """Formata um valor monetário como ``R$ 1.234,56``."""
    try:
        amount = Decimal(str(value or 0))
    except (InvalidOperation, ValueError):
        return "R$ 0,00"
    quantized = amount.quantize(Decimal("0.01"))
    integer, _, decimals = f"{quantized:.2f}".partition(".")
    negative = integer.startswith("-")
    digits = integer.lstrip("-")
    groups: list[str] = []
    while len(digits) > 3:
        groups.insert(0, digits[-3:])
        digits = digits[:-3]
    groups.insert(0, digits)
    formatted = ".".join(groups)
    return f"{'-' if negative else ''}R$ {formatted},{decimals}"


def format_int(value: Any) -> str:
    """Formata inteiros com separador de milhar (``1.234``)."""
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        return "0"
    return f"{number:,}".replace(",", ".")


def format_date_br(value: Any) -> str:
    """Formata datas e datas ISO como ``dd/mm/aaaa``."""
    if value in (None, ""):
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    text = str(value)
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(text[: len(fmt) + 6], fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return text


def format_percent(value: Any, *, decimals: int = 1) -> str:
    """Formata uma fração (0–1) como percentual."""
    try:
        number = float(value or 0) * 100
    except (TypeError, ValueError):
        return "0%"
    return f"{number:.{decimals}f}".replace(".", ",") + "%"


def pluralize(count: int, singular: str, plural: str) -> str:
    """Escolhe singular ou plural segundo a contagem."""
    return singular if abs(count) == 1 else plural
