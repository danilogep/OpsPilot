"""Pipeline de validação, normalização e deduplicação das linhas importadas.

Para cada linha do arquivo:

1. aplica o mapeamento coluna → campo canônico;
2. normaliza cada campo (sem interromper no primeiro erro);
3. valida obrigatoriedade e coerência entre campos;
4. calcula a chave de deduplicação e detecta repetições dentro do arquivo;
5. produz estatísticas agregadas do processo.

A linha original e o número da linha são sempre preservados.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from app.db.models.enums import CustomerStatus, RowStatus
from app.domains.imports.dedupe import DedupeTracker, build_dedupe_key
from app.domains.imports.mapping import (
    FIELD_LABELS,
    REQUIRED_FIELDS,
    CanonicalField,
)
from app.domains.imports.normalizers import (
    FieldError,
    normalize_document,
    normalize_email,
    normalize_free_text,
    normalize_name,
    normalize_phone,
    normalize_source,
    parse_customer_status,
    parse_date,
    parse_money,
    to_text,
)

#: Normalizador por campo canônico.
NORMALIZERS: dict[CanonicalField, Any] = {
    CanonicalField.CUSTOMER_NAME: normalize_name,
    CanonicalField.EMAIL: normalize_email,
    CanonicalField.PHONE: normalize_phone,
    CanonicalField.DOCUMENT: normalize_document,
    CanonicalField.PLAN_NAME: lambda value: to_text(value) or None,
    CanonicalField.CUSTOMER_STATUS: parse_customer_status,
    CanonicalField.START_DATE: parse_date,
    CanonicalField.RENEWAL_DATE: parse_date,
    CanonicalField.MONTHLY_VALUE: parse_money,
    CanonicalField.SOURCE: normalize_source,
    CanonicalField.NOTES: normalize_free_text,
}


@dataclass(slots=True)
class RowIssue:
    """Erro ou aviso associado a um campo de uma linha."""

    field: str
    label: str
    message: str
    value: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "label": self.label,
            "message": self.message,
            "value": self.value,
        }


@dataclass(slots=True)
class RowResult:
    """Resultado da validação de uma linha."""

    row_number: int
    raw: dict[str, Any]
    normalized: dict[str, Any]
    status: RowStatus
    errors: list[RowIssue] = field(default_factory=list)
    warnings: list[RowIssue] = field(default_factory=list)
    dedupe_key: str = ""
    dedupe_criterion: str = "none"
    duplicate_of_row: int | None = None

    @property
    def is_importable(self) -> bool:
        return self.status is RowStatus.VALID


@dataclass(slots=True)
class ValidationReport:
    """Estatísticas agregadas da validação de um arquivo."""

    total_rows: int = 0
    valid_rows: int = 0
    invalid_rows: int = 0
    duplicate_rows: int = 0
    warning_rows: int = 0
    unique_keys: int = 0
    errors_by_field: dict[str, int] = field(default_factory=dict)
    top_errors: list[dict[str, Any]] = field(default_factory=list)
    fill_rate: dict[str, float] = field(default_factory=dict)
    dedupe_criteria: dict[str, int] = field(default_factory=dict)
    monthly_value_sum: str = "0.00"
    mapped_fields: list[str] = field(default_factory=list)
    unmapped_columns: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_rows": self.total_rows,
            "valid_rows": self.valid_rows,
            "invalid_rows": self.invalid_rows,
            "duplicate_rows": self.duplicate_rows,
            "warning_rows": self.warning_rows,
            "unique_keys": self.unique_keys,
            "errors_by_field": self.errors_by_field,
            "top_errors": self.top_errors,
            "fill_rate": self.fill_rate,
            "dedupe_criteria": self.dedupe_criteria,
            "monthly_value_sum": self.monthly_value_sum,
            "mapped_fields": self.mapped_fields,
            "unmapped_columns": self.unmapped_columns,
        }


def _jsonable(value: Any) -> Any:
    """Converte valores normalizados para tipos serializáveis em JSON."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, CustomerStatus):
        return value.value
    return value


def _raw_as_text(row: dict[str, Any]) -> dict[str, Any]:
    """Guarda a linha original como texto (JSON-safe), sem perder o conteúdo."""
    return {str(key): (None if value is None else str(value)) for key, value in row.items()}


def normalize_row(
    row: dict[str, Any],
    *,
    row_number: int,
    mapping: dict[str, str],
) -> RowResult:
    """Normaliza e valida uma linha segundo o mapeamento informado."""
    normalized: dict[str, Any] = {}
    errors: list[RowIssue] = []
    warnings: list[RowIssue] = []

    for source_column, target in mapping.items():
        if not target:
            continue
        try:
            canonical = CanonicalField(target)
        except ValueError:
            continue
        label = FIELD_LABELS[canonical]
        raw_value = row.get(source_column)
        normalizer = NORMALIZERS[canonical]
        try:
            normalized[canonical.value] = normalizer(raw_value)
        except FieldError as exc:
            normalized[canonical.value] = None
            errors.append(
                RowIssue(
                    field=canonical.value,
                    label=label,
                    message=str(exc),
                    value=to_text(raw_value),
                )
            )

    for required in REQUIRED_FIELDS:
        if not normalized.get(required.value) and all(
            error.field != required.value for error in errors
        ):
            errors.append(
                RowIssue(
                    field=required.value,
                    label=FIELD_LABELS[required],
                    message="Campo obrigatório não informado.",
                )
            )

    warnings.extend(_coherence_warnings(normalized))

    status = RowStatus.INVALID if errors else RowStatus.VALID
    key = build_dedupe_key(
        name=normalized.get(CanonicalField.CUSTOMER_NAME.value),
        email=normalized.get(CanonicalField.EMAIL.value),
        document=normalized.get(CanonicalField.DOCUMENT.value),
        phone=normalized.get(CanonicalField.PHONE.value),
    )
    return RowResult(
        row_number=row_number,
        raw=_raw_as_text(row),
        normalized={name: _jsonable(value) for name, value in normalized.items()},
        status=status,
        errors=errors,
        warnings=warnings,
        dedupe_key=key.value,
        dedupe_criterion=key.criterion,
    )


def _coherence_warnings(normalized: dict[str, Any]) -> list[RowIssue]:
    """Avisos que não impedem a importação, mas merecem atenção."""
    warnings: list[RowIssue] = []
    start = normalized.get(CanonicalField.START_DATE.value)
    renewal = normalized.get(CanonicalField.RENEWAL_DATE.value)
    value = normalized.get(CanonicalField.MONTHLY_VALUE.value)

    if isinstance(start, date) and isinstance(renewal, date) and renewal < start:
        warnings.append(
            RowIssue(
                field=CanonicalField.RENEWAL_DATE.value,
                label=FIELD_LABELS[CanonicalField.RENEWAL_DATE],
                message="Data de renovação anterior ao início do contrato.",
                value=renewal.isoformat(),
            )
        )
    if value is not None and Decimal(value) == 0:
        warnings.append(
            RowIssue(
                field=CanonicalField.MONTHLY_VALUE.value,
                label=FIELD_LABELS[CanonicalField.MONTHLY_VALUE],
                message="Valor mensal igual a zero.",
                value="0",
            )
        )
    if not normalized.get(CanonicalField.EMAIL.value) and not normalized.get(
        CanonicalField.PHONE.value
    ):
        warnings.append(
            RowIssue(
                field=CanonicalField.EMAIL.value,
                label="Contato",
                message="Cliente sem e-mail e sem telefone.",
            )
        )
    if not normalized.get(CanonicalField.RENEWAL_DATE.value):
        warnings.append(
            RowIssue(
                field=CanonicalField.RENEWAL_DATE.value,
                label=FIELD_LABELS[CanonicalField.RENEWAL_DATE],
                message="Sem data de renovação: o cliente não entra nos indicadores de renovação.",
            )
        )
    return warnings


def validate_rows(
    rows: list[dict[str, Any]],
    *,
    mapping: dict[str, str],
    all_columns: list[str] | None = None,
    first_row_number: int = 2,
) -> tuple[list[RowResult], ValidationReport]:
    """Valida todas as linhas e devolve os resultados com as estatísticas."""
    tracker = DedupeTracker()
    results: list[RowResult] = []
    error_counter: Counter[str] = Counter()
    message_counter: Counter[tuple[str, str]] = Counter()
    filled_counter: Counter[str] = Counter()
    criteria_counter: Counter[str] = Counter()
    total_value = Decimal("0.00")

    for offset, row in enumerate(rows):
        result = normalize_row(row, row_number=first_row_number + offset, mapping=mapping)
        if result.status is RowStatus.VALID:
            duplicate = tracker.check(
                build_dedupe_key(
                    name=result.normalized.get(CanonicalField.CUSTOMER_NAME.value),
                    email=result.normalized.get(CanonicalField.EMAIL.value),
                    document=result.normalized.get(CanonicalField.DOCUMENT.value),
                    phone=result.normalized.get(CanonicalField.PHONE.value),
                ),
                result.row_number,
            )
            if duplicate.is_duplicate:
                result.status = RowStatus.DUPLICATE
                result.duplicate_of_row = duplicate.first_row_number
                result.warnings.append(
                    RowIssue(
                        field="dedupe",
                        label="Duplicidade",
                        message=(
                            f"Registro duplicado da linha {duplicate.first_row_number} "
                            f"(critério: {result.dedupe_criterion})."
                        ),
                    )
                )
            else:
                criteria_counter[result.dedupe_criterion] += 1

        for error in result.errors:
            error_counter[error.field] += 1
            message_counter[(error.field, error.message)] += 1
        for name, value in result.normalized.items():
            if value not in (None, ""):
                filled_counter[name] += 1
        monthly = result.normalized.get(CanonicalField.MONTHLY_VALUE.value)
        if monthly and result.status in {RowStatus.VALID, RowStatus.DUPLICATE}:
            total_value += Decimal(str(monthly))
        results.append(result)

    total = len(results)
    report = ValidationReport(
        total_rows=total,
        valid_rows=sum(1 for item in results if item.status is RowStatus.VALID),
        invalid_rows=sum(1 for item in results if item.status is RowStatus.INVALID),
        duplicate_rows=sum(1 for item in results if item.status is RowStatus.DUPLICATE),
        warning_rows=sum(1 for item in results if item.warnings),
        unique_keys=tracker.unique_count,
        errors_by_field=dict(error_counter),
        top_errors=[
            {"field": field_name, "message": message, "count": count}
            for (field_name, message), count in message_counter.most_common(10)
        ],
        fill_rate={
            name: round(filled_counter.get(name, 0) / total, 4) if total else 0.0
            for name in sorted(set(mapping.values()) - {""})
        },
        dedupe_criteria=dict(criteria_counter),
        monthly_value_sum=str(total_value),
        mapped_fields=sorted({value for value in mapping.values() if value}),
        unmapped_columns=[
            column for column in (all_columns or list(mapping)) if not mapping.get(column)
        ],
    )
    return results, report
