"""Tipos anotados reutilizáveis nos schemas Pydantic.

``Email`` substitui ``pydantic.EmailStr`` porque o validador padrão rejeita
domínios de uso especial (como ``.local``), usados pelos usuários de
demonstração (``admin@opspilot.local``). A validação aqui é de formato,
suficiente para a aplicação e previsível em ambiente offline.
"""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import AfterValidator, StringConstraints

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)+$")


def _validate_email(value: str) -> str:
    """Valida o formato e normaliza para minúsculas."""
    candidate = value.strip().lower()
    if not _EMAIL_RE.match(candidate):
        raise ValueError("E-mail inválido.")
    if len(candidate) > 254:
        raise ValueError("E-mail excede 254 caracteres.")
    return candidate


Email = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=5, max_length=254),
    AfterValidator(_validate_email),
]

#: Texto curto obrigatório (nomes, títulos).
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
