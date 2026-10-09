"""Testes unitários dos normalizadores, mapeamento e deduplicação."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from app.db.models.enums import CustomerStatus
from app.domains.imports.dedupe import DedupeTracker, build_dedupe_key
from app.domains.imports.mapping import (
    CanonicalField,
    missing_required_fields,
    normalize_header,
    suggest_mapping,
)
from app.domains.imports.normalizers import (
    FieldError,
    format_phone_br,
    normalize_document,
    normalize_email,
    normalize_name,
    normalize_phone,
    normalize_source,
    parse_customer_status,
    parse_date,
    parse_money,
    to_text,
)

# ----------------------------------------------------------------- texto ------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Padaria   Aurora  ", "Padaria Aurora"),
        ("", None),
        ("   ", None),
        ("-", None),
        ("N/A", None),
        ("não informado", None),
        (None, None),
        (float("nan"), None),
        (1250.0, "1250"),
        (datetime(2026, 3, 1, 10, 30), "2026-03-01"),
        (date(2026, 3, 1), "2026-03-01"),
    ],
)
def test_to_text_handles_empty_and_typed_values(raw: object, expected: str | None) -> None:
    assert to_text(raw) == expected


def test_normalize_name_collapses_spaces_and_fixes_caps() -> None:
    assert normalize_name("  PADARIA AURORA LTDA ") == "Padaria Aurora Ltda"
    assert normalize_name("Clínica  Vida ME") == "Clínica Vida ME"


def test_normalize_name_rejects_too_short() -> None:
    with pytest.raises(FieldError):
        normalize_name("A")


# ---------------------------------------------------------------- e-mail ------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("CONTATO@Empresa.com.BR", "contato@empresa.com.br"),
        (" contato@empresa.com ", "contato@empresa.com"),
        ("contato@empresa.com;outro@empresa.com", "contato@empresa.com"),
    ],
)
def test_normalize_email_lowercases_and_cleans(raw: str, expected: str) -> None:
    assert normalize_email(raw) == expected


@pytest.mark.parametrize("raw", ["contato@empresa", "sem-arroba.com", "@empresa.com"])
def test_normalize_email_rejects_invalid(raw: str) -> None:
    with pytest.raises(FieldError):
        normalize_email(raw)


def test_normalize_email_accepts_empty() -> None:
    assert normalize_email("") is None


# -------------------------------------------------------------- telefone ------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("(11) 98765-4321", "+5511987654321"),
        ("11987654321", "+5511987654321"),
        ("+55 11 98765-4321", "+5511987654321"),
        ("5511987654321", "+5511987654321"),
        ("1132654321", "+551132654321"),
    ],
)
def test_normalize_phone_produces_e164(raw: str, expected: str) -> None:
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["987654321", "123", "telefone"])
def test_normalize_phone_rejects_invalid(raw: str) -> None:
    with pytest.raises(FieldError):
        normalize_phone(raw)


def test_format_phone_br_is_readable() -> None:
    assert format_phone_br("+5511987654321") == "+55 (11) 98765-4321"
    assert format_phone_br("+551132654321") == "+55 (11) 3265-4321"


# ------------------------------------------------------------- documento ------


def test_normalize_document_formats_cpf_and_cnpj() -> None:
    assert normalize_document("12345678901") == "123.456.789-01"
    assert normalize_document("12.345.678/0001-90") == "12.345.678/0001-90"


def test_normalize_document_rejects_wrong_length() -> None:
    with pytest.raises(FieldError):
        normalize_document("12345")


# ------------------------------------------------------------------ data ------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("05/02/2026", date(2026, 2, 5)),
        ("2026-02-05", date(2026, 2, 5)),
        ("05-02-2026", date(2026, 2, 5)),
        ("05.02.2026", date(2026, 2, 5)),
        ("20260205", date(2026, 2, 5)),
        (datetime(2026, 2, 5, 12, 0), date(2026, 2, 5)),
        (date(2026, 2, 5), date(2026, 2, 5)),
        (46058, date(2026, 2, 5)),
        ("", None),
    ],
)
def test_parse_date_accepts_common_formats(raw: object, expected: date | None) -> None:
    assert parse_date(raw) == expected


@pytest.mark.parametrize(
    "raw", ["31/02/2026", "0000-00-00", "2026-13-05", "amanhã", "data a definir"]
)
def test_parse_date_rejects_invalid(raw: str) -> None:
    with pytest.raises(FieldError):
        parse_date(raw)


# ----------------------------------------------------------------- valor ------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("R$ 1.250,00", Decimal("1250.00")),
        ("1250,00", Decimal("1250.00")),
        ("1250.00", Decimal("1250.00")),
        ("1,250.00", Decimal("1250.00")),
        ("R$ 980", Decimal("980.00")),
        ("1.890,50", Decimal("1890.50")),
        (499, Decimal("499.00")),
        (499.9, Decimal("499.90")),
        ("", None),
    ],
)
def test_parse_money_handles_br_and_us_formats(raw: object, expected: Decimal | None) -> None:
    assert parse_money(raw) == expected


@pytest.mark.parametrize("raw", ["mil reais", "abc", "R$ -100,00"])
def test_parse_money_rejects_invalid(raw: str) -> None:
    with pytest.raises(FieldError):
        parse_money(raw)


# --------------------------------------------------------------- situação -----


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Ativo", CustomerStatus.ACTIVE),
        ("ATIVO", CustomerStatus.ACTIVE),
        ("em dia", CustomerStatus.ACTIVE),
        ("Inadimplente", CustomerStatus.PAST_DUE),
        ("atrasado", CustomerStatus.PAST_DUE),
        ("Cancelado", CustomerStatus.CHURNED),
        ("inativo", CustomerStatus.CHURNED),
        ("Prospect", CustomerStatus.PROSPECT),
        ("", None),
    ],
)
def test_parse_customer_status_maps_synonyms(raw: str, expected: CustomerStatus | None) -> None:
    assert parse_customer_status(raw) == expected


def test_parse_customer_status_rejects_unknown() -> None:
    with pytest.raises(FieldError):
        parse_customer_status("talvez")


def test_normalize_source_is_accent_free_lowercase() -> None:
    assert normalize_source("Indicação") == "indicacao"
    assert normalize_source("Redes Sociais") == "redes sociais"


# ------------------------------------------------------------ mapeamento ------


def test_normalize_header_removes_punctuation_and_accents() -> None:
    assert normalize_header("Mensalidade (R$)") == "mensalidade r$"
    assert normalize_header("E-mail") == "e mail"
    assert normalize_header("CPF/CNPJ") == "cpf cnpj"


def test_suggest_mapping_recognizes_portuguese_headers() -> None:
    headers = [
        "Razão Social",
        "E-mail",
        "Celular / WhatsApp",
        "CNPJ",
        "Plano Contratado",
        "Situação",
        "Data de Adesão",
        "Vencimento",
        "Mensalidade (R$)",
        "Como nos conheceu",
        "Observações",
    ]
    mapping = {item.source_column: item.target_field for item in suggest_mapping(headers)}
    assert mapping["Razão Social"] is CanonicalField.CUSTOMER_NAME
    assert mapping["E-mail"] is CanonicalField.EMAIL
    assert mapping["Celular / WhatsApp"] is CanonicalField.PHONE
    assert mapping["CNPJ"] is CanonicalField.DOCUMENT
    assert mapping["Plano Contratado"] is CanonicalField.PLAN_NAME
    assert mapping["Situação"] is CanonicalField.CUSTOMER_STATUS
    assert mapping["Data de Adesão"] is CanonicalField.START_DATE
    assert mapping["Vencimento"] is CanonicalField.RENEWAL_DATE
    assert mapping["Mensalidade (R$)"] is CanonicalField.MONTHLY_VALUE
    assert mapping["Como nos conheceu"] is CanonicalField.SOURCE
    assert mapping["Observações"] is CanonicalField.NOTES


def test_suggest_mapping_handles_english_and_snake_case() -> None:
    mapping = {
        item.source_column: item.target_field
        for item in suggest_mapping(["customer_name", "email", "renewal_date", "monthly_value"])
    }
    assert mapping["customer_name"] is CanonicalField.CUSTOMER_NAME
    assert mapping["renewal_date"] is CanonicalField.RENEWAL_DATE
    assert mapping["monthly_value"] is CanonicalField.MONTHLY_VALUE


def test_suggest_mapping_does_not_assign_same_field_twice() -> None:
    suggestions = suggest_mapping(["E-mail", "Email secundário"])
    targets = [item.target_field for item in suggestions if item.target_field]
    assert targets.count(CanonicalField.EMAIL) == 1


def test_suggest_mapping_leaves_unknown_columns_unmapped() -> None:
    suggestions = {item.source_column: item for item in suggest_mapping(["Cor favorita"])}
    assert suggestions["Cor favorita"].target_field is None
    assert suggestions["Cor favorita"].needs_review is True


def test_missing_required_fields_detects_absent_name() -> None:
    assert missing_required_fields({"email"}) == [CanonicalField.CUSTOMER_NAME]
    assert missing_required_fields({"customer_name"}) == []


# ------------------------------------------------------------ deduplicação ----


def test_dedupe_key_precedence() -> None:
    assert build_dedupe_key(name="Acme", email="a@b.com").criterion == "email"
    assert build_dedupe_key(name="Acme", document="12.345.678/0001-90").criterion == "document"
    assert build_dedupe_key(name="Acme", phone="+5511987654321").criterion == "phone_name"
    assert build_dedupe_key(name="Acme").criterion == "name"
    assert build_dedupe_key(name=None).value == ""


def test_dedupe_key_is_stable_for_equivalent_inputs() -> None:
    first = build_dedupe_key(name="Padaria Aurora", email="CONTATO@A.com")
    second = build_dedupe_key(name="padaria aurora", email="contato@a.com")
    assert first.value == second.value


def test_dedupe_key_normalizes_document_mask() -> None:
    masked = build_dedupe_key(name="Acme", document="12.345.678/0001-90")
    plain = build_dedupe_key(name="Acme", document="12345678000190")
    assert masked.value == plain.value


def test_dedupe_tracker_reports_first_occurrence() -> None:
    tracker = DedupeTracker()
    key = build_dedupe_key(name="Acme", email="a@b.com")
    assert tracker.check(key, 2).is_duplicate is False
    duplicate = tracker.check(key, 7)
    assert duplicate.is_duplicate is True
    assert duplicate.first_row_number == 2
    assert tracker.unique_count == 1
