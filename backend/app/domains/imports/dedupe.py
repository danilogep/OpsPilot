"""Deduplicação de clientes.

A chave de deduplicação é determinística e prefixada pelo critério usado, o que
deixa explícito *por que* dois registros foram considerados o mesmo cliente:

1. ``email:`` — e-mail normalizado (critério mais forte);
2. ``doc:`` — CPF/CNPJ (apenas dígitos);
3. ``phone+name:`` — telefone e nome normalizados;
4. ``name:`` — nome normalizado (critério mais fraco, último recurso).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domains.imports.normalizers import only_digits, strip_accents


@dataclass(frozen=True, slots=True)
class DedupeKey:
    """Chave de deduplicação e o critério que a originou."""

    value: str
    criterion: str

    @property
    def human_criterion(self) -> str:
        return {
            "email": "e-mail",
            "document": "documento",
            "phone_name": "telefone + nome",
            "name": "nome",
        }.get(self.criterion, self.criterion)


def normalize_key_text(value: str) -> str:
    """Normaliza texto para compor chaves: sem acento, minúsculo, sem espaço duplo."""
    return " ".join(strip_accents(value).lower().split())


def build_dedupe_key(
    *,
    name: str | None,
    email: str | None = None,
    document: str | None = None,
    phone: str | None = None,
) -> DedupeKey:
    """Monta a chave de deduplicação segundo a precedência dos critérios."""
    if email:
        return DedupeKey(f"email:{email.strip().lower()}", "email")
    if document:
        digits = only_digits(document)
        if digits:
            return DedupeKey(f"doc:{digits}", "document")
    if phone and name:
        digits = only_digits(phone)
        if digits:
            return DedupeKey(f"phone+name:{digits}|{normalize_key_text(name)}", "phone_name")
    if name:
        return DedupeKey(f"name:{normalize_key_text(name)}", "name")
    return DedupeKey("", "none")


@dataclass(frozen=True, slots=True)
class DuplicateInfo:
    """Resultado da verificação de duplicidade dentro do arquivo."""

    is_duplicate: bool
    first_row_number: int | None
    criterion: str


class DedupeTracker:
    """Acumula chaves vistas durante a validação de um arquivo."""

    def __init__(self) -> None:
        self._seen: dict[str, int] = {}

    def check(self, key: DedupeKey, row_number: int) -> DuplicateInfo:
        """Registra a chave e informa se ela já apareceu antes."""
        if not key.value:
            return DuplicateInfo(False, None, key.criterion)
        first = self._seen.get(key.value)
        if first is None:
            self._seen[key.value] = row_number
            return DuplicateInfo(False, None, key.criterion)
        return DuplicateInfo(True, first, key.criterion)

    @property
    def unique_count(self) -> int:
        return len(self._seen)
