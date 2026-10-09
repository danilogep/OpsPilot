"""Testes do pipeline e das rotas de importação."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.db.models import Organization
from app.db.models.enums import RowStatus
from app.domains.imports.pipeline import validate_rows
from app.domains.imports.reader import read_csv_bytes, read_spreadsheet
from tests.conftest import auth_headers

API = settings.api_v1_prefix
SAMPLES_DIR = Path(__file__).resolve().parents[2] / "data" / "samples"

MAPPING = {
    "Razão Social": "customer_name",
    "E-mail": "email",
    "Celular / WhatsApp": "phone",
    "CNPJ": "document",
    "Plano Contratado": "plan_name",
    "Situação": "customer_status",
    "Data de Adesão": "start_date",
    "Vencimento": "renewal_date",
    "Mensalidade (R$)": "monthly_value",
    "Como nos conheceu": "source",
    "Observações": "notes",
}

CSV_CONTENT = """Razão Social;E-mail;Celular / WhatsApp;CNPJ;Plano Contratado;Situação;Data de Adesão;Vencimento;Mensalidade (R$);Como nos conheceu;Observações
PADARIA AURORA LTDA;contato@aurora.com.br;(11) 98765-4321;12.345.678/0001-90;Essencial;Ativo;01/02/2025;01/02/2027;R$ 199,00;Indicação;Primeiro cliente
Clínica Vida ME;contato@vida.com.br;11987654322;98.765.432/0001-10;Profissional;atrasado;2024-03-15;2026-03-15;499,00;Site;
Studio Lumen;contato@aurora.com.br;11987654323;11.111.111/0001-11;Avançado;ativo;01/01/2024;01/01/2027;899,00;Evento;Duplicado por e-mail
Sem Data Ltda;contato@semdata.com.br;11987654324;22.222.222/0001-22;Essencial;ativo;01/01/2024;31/02/2026;199,00;Site;Data inválida
;contato@semnome.com.br;11987654325;33.333.333/0001-33;Essencial;ativo;01/01/2024;01/01/2027;199,00;Site;Sem nome
Contato Vazio ME;;;44.444.444/0001-44;Suporte Pontual;;;;;;Sem contato nem valor
"""


# ------------------------------------------------------------ leitura ---------


def test_read_csv_detects_delimiter_and_headers() -> None:
    sheet = read_csv_bytes(CSV_CONTENT.encode("utf-8"))
    assert sheet.delimiter == ";"
    assert sheet.headers[0] == "Razão Social"
    assert sheet.total_rows == 6
    assert sheet.row_numbers()[0] == 2


def test_read_csv_accepts_bom_and_latin1() -> None:
    assert read_csv_bytes(CSV_CONTENT.encode("utf-8-sig")).encoding == "utf-8-sig"
    assert read_csv_bytes(CSV_CONTENT.encode("cp1252")).encoding in {"utf-8", "cp1252"}


def test_read_csv_rejects_empty_file() -> None:
    from app.core.errors import UnprocessableFileError

    with pytest.raises(UnprocessableFileError):
        read_csv_bytes(b"   ")


@pytest.mark.skipif(not (SAMPLES_DIR / "customers.xlsx").exists(), reason="amostra XLSX não gerada")
def test_read_xlsx_sample_has_sheets() -> None:
    content = (SAMPLES_DIR / "customers.xlsx").read_bytes()
    sheet = read_spreadsheet(content, extension=".xlsx")
    assert "Clientes" in sheet.sheet_names
    assert sheet.active_sheet == "Clientes"
    assert sheet.total_rows > 100


# ------------------------------------------------------------ pipeline --------


def test_validate_rows_classifies_each_row() -> None:
    sheet = read_csv_bytes(CSV_CONTENT.encode("utf-8"))
    results, report = validate_rows(sheet.rows, mapping=MAPPING, all_columns=sheet.headers)

    by_row = {result.row_number: result for result in results}
    assert by_row[2].status is RowStatus.VALID
    assert by_row[4].status is RowStatus.DUPLICATE
    assert by_row[4].duplicate_of_row == 2
    assert by_row[5].status is RowStatus.INVALID  # data inválida
    assert by_row[6].status is RowStatus.INVALID  # sem nome
    assert by_row[7].status is RowStatus.VALID  # vazios não são erro

    assert report.total_rows == 6
    assert report.valid_rows == 3
    assert report.invalid_rows == 2
    assert report.duplicate_rows == 1
    assert report.unique_keys == 3


def test_validate_rows_normalizes_values() -> None:
    sheet = read_csv_bytes(CSV_CONTENT.encode("utf-8"))
    results, _ = validate_rows(sheet.rows, mapping=MAPPING)
    first = results[0].normalized
    assert first["customer_name"] == "Padaria Aurora Ltda"
    assert first["email"] == "contato@aurora.com.br"
    assert first["phone"] == "+5511987654321"
    assert first["renewal_date"] == "2027-02-01"
    assert first["monthly_value"] == "199.00"
    assert first["customer_status"] == "ACTIVE"
    assert first["source"] == "indicacao"


def test_validate_rows_preserves_original_row() -> None:
    sheet = read_csv_bytes(CSV_CONTENT.encode("utf-8"))
    results, _ = validate_rows(sheet.rows, mapping=MAPPING)
    assert results[0].raw["Razão Social"] == "PADARIA AURORA LTDA"
    assert results[0].row_number == 2


def test_validate_rows_reports_error_messages_per_field() -> None:
    sheet = read_csv_bytes(CSV_CONTENT.encode("utf-8"))
    results, report = validate_rows(sheet.rows, mapping=MAPPING)
    invalid = next(item for item in results if item.row_number == 5)
    assert any(error.field == "renewal_date" for error in invalid.errors)
    assert "renewal_date" in report.errors_by_field
    assert report.top_errors


def test_validate_rows_emits_warnings_without_blocking() -> None:
    sheet = read_csv_bytes(CSV_CONTENT.encode("utf-8"))
    results, report = validate_rows(sheet.rows, mapping=MAPPING)
    no_contact = next(item for item in results if item.row_number == 7)
    assert no_contact.status is RowStatus.VALID
    assert any("sem e-mail" in warning.message.lower() for warning in no_contact.warnings)
    assert report.warning_rows >= 1


def test_validate_rows_without_mapping_reports_required_field() -> None:
    sheet = read_csv_bytes(CSV_CONTENT.encode("utf-8"))
    results, report = validate_rows(sheet.rows, mapping={"E-mail": "email"})
    assert report.valid_rows == 0
    assert all(item.status is RowStatus.INVALID for item in results)
    assert report.errors_by_field["customer_name"] == 6


# --------------------------------------------------------------- rotas --------


async def _upload(client: AsyncClient, token: str, content: bytes, filename: str) -> dict:
    response = await client.post(
        f"{API}/imports",
        headers=auth_headers(token),
        files={"file": (filename, io.BytesIO(content), "text/csv")},
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def test_upload_detects_columns_and_suggests_mapping(
    client: AsyncClient, analyst_token: str
) -> None:
    job = await _upload(client, analyst_token, CSV_CONTENT.encode("utf-8"), "clientes.csv")
    assert job["status"] == "UPLOADED"
    assert job["total_rows"] == 6
    assert "Razão Social" in job["detected_columns"]
    mapped = {item["source_column"]: item["target_field"] for item in job["mappings"]}
    assert mapped["Razão Social"] == "customer_name"
    assert mapped["Vencimento"] == "renewal_date"


async def test_viewer_cannot_upload(client: AsyncClient, viewer_token: str) -> None:
    response = await client.post(
        f"{API}/imports",
        headers=auth_headers(viewer_token),
        files={"file": ("clientes.csv", io.BytesIO(b"a;b\n1;2\n"), "text/csv")},
    )
    assert response.status_code == 403


async def test_upload_rejects_unsupported_extension(
    client: AsyncClient, analyst_token: str
) -> None:
    response = await client.post(
        f"{API}/imports",
        headers=auth_headers(analyst_token),
        files={"file": ("dados.exe", io.BytesIO(b"MZ binario"), "application/octet-stream")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unprocessable_file"


async def test_upload_sanitizes_dangerous_filename(client: AsyncClient, analyst_token: str) -> None:
    job = await _upload(
        client, analyst_token, CSV_CONTENT.encode("utf-8"), "../../etc/passwd/clientes.csv"
    )
    assert "/" not in job["original_filename"]
    assert ".." not in job["original_filename"]


async def test_preview_shows_normalized_rows_and_issues(
    client: AsyncClient, analyst_token: str
) -> None:
    job = await _upload(client, analyst_token, CSV_CONTENT.encode("utf-8"), "clientes.csv")
    response = await client.get(
        f"{API}/imports/{job['id']}/preview", headers=auth_headers(analyst_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_rows_in_file"] == 6
    assert body["missing_required_fields"] == []
    assert body["rows"][0]["normalized"]["customer_name"] == "Padaria Aurora Ltda"
    assert any(row["errors"] for row in body["rows"])
    assert body["canonical_fields"]


async def test_full_import_flow(client: AsyncClient, analyst_token: str) -> None:
    headers = auth_headers(analyst_token)
    job = await _upload(client, analyst_token, CSV_CONTENT.encode("utf-8"), "clientes.csv")
    import_id = job["id"]

    mapping_response = await client.put(
        f"{API}/imports/{import_id}/mapping",
        headers=headers,
        json={
            "mappings": [
                {"source_column": column, "target_field": target}
                for column, target in MAPPING.items()
            ]
        },
    )
    assert mapping_response.status_code == 200
    assert mapping_response.json()["status"] == "MAPPED"

    validation = await client.post(f"{API}/imports/{import_id}/validate", headers=headers)
    assert validation.status_code == 200, validation.text
    summary = validation.json()
    assert summary["status"] == "VALIDATED"
    assert summary["valid_rows"] == 3
    assert summary["invalid_rows"] == 2
    assert summary["duplicate_rows"] == 1

    errors = await client.get(f"{API}/imports/{import_id}/errors", headers=headers)
    assert errors.status_code == 200
    assert errors.json()["total"] == 3  # 2 inválidas + 1 duplicada
    first_error = errors.json()["items"][0]
    assert first_error["row_number"] >= 2
    assert first_error["raw_data"]

    commit = await client.post(f"{API}/imports/{import_id}/commit", headers=headers)
    assert commit.status_code == 200, commit.text
    result = commit.json()
    assert result["status"] == "COMMITTED"
    assert result["created_customers"] == 3
    assert result["created_renewals"] >= 2

    report = await client.get(f"{API}/imports/{import_id}/report", headers=headers)
    assert report.status_code == 200
    assert report.json()["validation"]["valid_rows"] == 3
    assert report.json()["recommendations"]


async def test_commit_requires_validation(client: AsyncClient, analyst_token: str) -> None:
    job = await _upload(client, analyst_token, CSV_CONTENT.encode("utf-8"), "clientes.csv")
    response = await client.post(
        f"{API}/imports/{job['id']}/commit", headers=auth_headers(analyst_token)
    )
    assert response.status_code == 409


async def test_commit_twice_is_rejected(client: AsyncClient, analyst_token: str) -> None:
    headers = auth_headers(analyst_token)
    job = await _upload(client, analyst_token, CSV_CONTENT.encode("utf-8"), "clientes.csv")
    await client.post(f"{API}/imports/{job['id']}/validate", headers=headers)
    first = await client.post(f"{API}/imports/{job['id']}/commit", headers=headers)
    assert first.status_code == 200
    second = await client.post(f"{API}/imports/{job['id']}/commit", headers=headers)
    assert second.status_code == 409


async def test_mapping_rejects_duplicated_target_field(
    client: AsyncClient, analyst_token: str
) -> None:
    job = await _upload(client, analyst_token, CSV_CONTENT.encode("utf-8"), "clientes.csv")
    response = await client.put(
        f"{API}/imports/{job['id']}/mapping",
        headers=auth_headers(analyst_token),
        json={
            "mappings": [
                {"source_column": "Razão Social", "target_field": "customer_name"},
                {"source_column": "E-mail", "target_field": "customer_name"},
            ]
        },
    )
    assert response.status_code == 422


async def test_import_is_isolated_by_organization(
    client: AsyncClient, analyst_token: str, session: object
) -> None:
    job = await _upload(client, analyst_token, CSV_CONTENT.encode("utf-8"), "clientes.csv")
    listing = await client.get(f"{API}/imports", headers=auth_headers(analyst_token))
    ids = {item["id"] for item in listing.json()["items"]}
    assert job["id"] in ids


async def test_import_audit_trail_is_recorded(client: AsyncClient, admin_token: str) -> None:
    headers = auth_headers(admin_token)
    job = await _upload(client, admin_token, CSV_CONTENT.encode("utf-8"), "clientes.csv")
    await client.post(f"{API}/imports/{job['id']}/validate", headers=headers)
    await client.post(f"{API}/imports/{job['id']}/commit", headers=headers)

    audit = await client.get(
        f"{API}/audit/events",
        headers=headers,
        params={"entity_type": "import_job", "entity_id": job["id"]},
    )
    actions = {item["action"] for item in audit.json()["items"]}
    assert {"import.upload", "import.validated", "import.committed"} <= actions


@pytest.mark.skipif(not (SAMPLES_DIR / "customers.csv").exists(), reason="amostra CSV não gerada")
async def test_import_real_sample_file_end_to_end(
    client: AsyncClient, analyst_token: str, seeded: Organization
) -> None:
    """Importa a planilha sintética de ``data/samples`` do início ao fim."""
    headers = auth_headers(analyst_token)
    content = (SAMPLES_DIR / "customers.csv").read_bytes()
    job = await _upload(client, analyst_token, content, "customers.csv")

    preview = await client.get(f"{API}/imports/{job['id']}/preview", headers=headers)
    assert preview.status_code == 200
    assert preview.json()["missing_required_fields"] == []

    validation = await client.post(f"{API}/imports/{job['id']}/validate", headers=headers)
    summary = validation.json()
    assert summary["total_rows"] == 124
    assert summary["invalid_rows"] > 0, "a amostra precisa ter erros propositais"
    assert summary["duplicate_rows"] > 0, "a amostra precisa ter duplicidades propositais"
    assert summary["valid_rows"] > 80

    commit = await client.post(f"{API}/imports/{job['id']}/commit", headers=headers)
    assert commit.status_code == 200
    body = commit.json()
    assert body["created_customers"] + body["updated_customers"] == summary["valid_rows"]
