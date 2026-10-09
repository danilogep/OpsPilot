"""Modelo canônico de importação e sugestão automática de mapeamento.

A sugestão é determinística e explicável: para cada coluna do arquivo calculamos
a melhor correspondência entre os sinônimos conhecidos e devolvemos a confiança
usada pela interface para destacar o que precisa de revisão humana.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import StrEnum

from app.domains.imports.normalizers import strip_accents


class CanonicalField(StrEnum):
    """Campos do modelo canônico de cliente."""

    CUSTOMER_NAME = "customer_name"
    EMAIL = "email"
    PHONE = "phone"
    DOCUMENT = "document"
    PLAN_NAME = "plan_name"
    CUSTOMER_STATUS = "customer_status"
    START_DATE = "start_date"
    RENEWAL_DATE = "renewal_date"
    MONTHLY_VALUE = "monthly_value"
    SOURCE = "source"
    NOTES = "notes"


#: Rótulos em português exibidos na interface.
FIELD_LABELS: dict[CanonicalField, str] = {
    CanonicalField.CUSTOMER_NAME: "Nome do cliente",
    CanonicalField.EMAIL: "E-mail",
    CanonicalField.PHONE: "Telefone",
    CanonicalField.DOCUMENT: "CPF/CNPJ",
    CanonicalField.PLAN_NAME: "Plano",
    CanonicalField.CUSTOMER_STATUS: "Situação",
    CanonicalField.START_DATE: "Início do contrato",
    CanonicalField.RENEWAL_DATE: "Data de renovação",
    CanonicalField.MONTHLY_VALUE: "Valor mensal",
    CanonicalField.SOURCE: "Origem",
    CanonicalField.NOTES: "Observações",
}

#: Campos obrigatórios no mapeamento para que a importação possa ser validada.
REQUIRED_FIELDS: frozenset[CanonicalField] = frozenset({CanonicalField.CUSTOMER_NAME})

#: Sinônimos aceitos por campo (sem acento, minúsculos).
FIELD_SYNONYMS: dict[CanonicalField, tuple[str, ...]] = {
    CanonicalField.CUSTOMER_NAME: (
        "customer_name",
        "cliente",
        "nome",
        "nome do cliente",
        "nome cliente",
        "razao social",
        "razao",
        "empresa",
        "nome fantasia",
        "cliente/empresa",
        "customer",
        "name",
        "contratante",
        "sacado",
    ),
    CanonicalField.EMAIL: (
        "email",
        "e-mail",
        "e mail",
        "endereco de email",
        "email do cliente",
        "mail",
        "email principal",
        "contato email",
        "e-mail de contato",
    ),
    CanonicalField.PHONE: (
        "phone",
        "telefone",
        "fone",
        "celular",
        "whatsapp",
        "whats",
        "tel",
        "telefone de contato",
        "numero",
        "contato telefone",
        "ddd + telefone",
    ),
    CanonicalField.DOCUMENT: (
        "document",
        "documento",
        "cpf",
        "cnpj",
        "cpf/cnpj",
        "cpf_cnpj",
        "doc",
        "inscricao",
        "cnpj/cpf",
        "registro",
    ),
    CanonicalField.PLAN_NAME: (
        "plan_name",
        "plano",
        "produto",
        "servico",
        "pacote",
        "plano contratado",
        "plan",
        "assinatura",
        "modalidade",
        "produto/servico",
    ),
    CanonicalField.CUSTOMER_STATUS: (
        "customer_status",
        "status",
        "situacao",
        "situacao do cliente",
        "estado",
        "condicao",
        "status do cliente",
        "ativo/inativo",
    ),
    CanonicalField.START_DATE: (
        "start_date",
        "inicio",
        "data de inicio",
        "inicio do contrato",
        "data inicio",
        "adesao",
        "data de adesao",
        "cliente desde",
        "data contrato",
        "inicio contrato",
    ),
    CanonicalField.RENEWAL_DATE: (
        "renewal_date",
        "renovacao",
        "data de renovacao",
        "renovar em",
        "vencimento",
        "data de vencimento",
        "vence em",
        "proxima renovacao",
        "data renovacao",
        "validade",
        "fim do contrato",
    ),
    CanonicalField.MONTHLY_VALUE: (
        "monthly_value",
        "valor",
        "mensalidade",
        "preco",
        "valor mensal",
        "valor do plano",
        "ticket",
        "receita",
        "valor contrato",
        "mensal",
        "valor (r$)",
        "preco mensal",
    ),
    CanonicalField.SOURCE: (
        "source",
        "origem",
        "canal",
        "como nos conheceu",
        "fonte",
        "origem do cliente",
        "canal de aquisicao",
    ),
    CanonicalField.NOTES: (
        "notes",
        "observacao",
        "observacoes",
        "obs",
        "comentarios",
        "anotacoes",
        "detalhes",
        "descricao",
    ),
}

#: Confiança mínima para sugerir automaticamente um campo.
MIN_CONFIDENCE = 0.62
#: Acima deste valor a sugestão é considerada segura (não exige revisão).
STRONG_CONFIDENCE = 0.9


@dataclass(frozen=True, slots=True)
class MappingSuggestion:
    """Sugestão de mapeamento para uma coluna do arquivo."""

    source_column: str
    target_field: CanonicalField | None
    confidence: float
    reason: str

    @property
    def needs_review(self) -> bool:
        return self.target_field is None or self.confidence < STRONG_CONFIDENCE


def normalize_header(value: str) -> str:
    """Normaliza um cabeçalho para comparação."""
    text = strip_accents(str(value)).lower().strip()
    for char in ("_", "-", ".", ":", ";", "/", "\\", "(", ")", "[", "]", "*", "#"):
        text = text.replace(char, " ")
    return " ".join(text.split())


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right).ratio()


def _best_match(header: str) -> tuple[CanonicalField | None, float, str]:
    """Encontra o melhor campo canônico para um cabeçalho."""
    normalized = normalize_header(header)
    if not normalized:
        return None, 0.0, "Cabeçalho vazio."

    best_field: CanonicalField | None = None
    best_score = 0.0
    best_reason = "Nenhum sinônimo compatível."

    for field, synonyms in FIELD_SYNONYMS.items():
        for synonym in synonyms:
            candidate = normalize_header(synonym)
            if normalized == candidate:
                return field, 1.0, f"Correspondência exata com “{synonym}”."
            score = 0.0
            reason = ""
            if normalized.startswith(candidate) or candidate.startswith(normalized):
                score = 0.86
                reason = f"Prefixo compatível com “{synonym}”."
            elif candidate in normalized.split() or candidate in normalized:
                score = 0.8
                reason = f"Contém o termo “{synonym}”."
            else:
                ratio = _similarity(normalized, candidate)
                if ratio >= 0.78:
                    score = round(ratio * 0.85, 3)
                    reason = f"Semelhante a “{synonym}” ({ratio:.0%})."
            if score > best_score:
                best_field, best_score, best_reason = field, score, reason

    if best_score < MIN_CONFIDENCE:
        return None, round(best_score, 3), "Confiança baixa: revise manualmente."
    return best_field, round(best_score, 3), best_reason


def suggest_mapping(headers: list[str]) -> list[MappingSuggestion]:
    """Sugere o mapeamento de cada coluna, sem repetir campos canônicos.

    Quando duas colunas apontam para o mesmo campo, a de maior confiança vence e
    a outra fica sem mapeamento para decisão humana.
    """
    scored: list[tuple[str, CanonicalField | None, float, str]] = []
    for header in headers:
        field, score, reason = _best_match(header)
        scored.append((header, field, score, reason))

    taken: dict[CanonicalField, float] = {}
    for _header, field, score, _reason in scored:
        if field is None:
            continue
        if field not in taken or score > taken[field]:
            taken[field] = score

    used: set[CanonicalField] = set()
    suggestions: list[MappingSuggestion] = []
    for header, field, score, reason in scored:
        if field is not None and (score < taken[field] or field in used):
            suggestions.append(
                MappingSuggestion(
                    source_column=header,
                    target_field=None,
                    confidence=0.0,
                    reason=(
                        f"Outra coluna tem correspondência melhor para “{FIELD_LABELS[field]}”."
                    ),
                )
            )
            continue
        if field is not None:
            used.add(field)
        suggestions.append(
            MappingSuggestion(
                source_column=header, target_field=field, confidence=score, reason=reason
            )
        )
    return suggestions


def missing_required_fields(mapped_fields: set[str]) -> list[CanonicalField]:
    """Lista campos obrigatórios ausentes no mapeamento."""
    return [field for field in REQUIRED_FIELDS if field.value not in mapped_fields]
