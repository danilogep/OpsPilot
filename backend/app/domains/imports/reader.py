"""Leitura de planilhas CSV, XLSX e XLS.

Decisões:

* **CSV** é lido como texto puro (``dtype=str``) para preservar o valor original
  ("1.234,56", "05/02/2026") e deixar a interpretação para os normalizadores.
* **Excel** é lido com os tipos nativos (datas e números já convertidos pelo
  openpyxl/xlrd), que os normalizadores também aceitam.
* O número da linha informado ao usuário é o da planilha (cabeçalho = linha 1).
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from app.core.errors import UnprocessableFileError

#: Codificações tentadas em ordem para arquivos CSV.
CSV_ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
#: Delimitadores candidatos quando o sniffer não decide.
CSV_DELIMITERS = (";", ",", "\t", "|")
#: Primeira linha de dados em uma planilha com cabeçalho.
FIRST_DATA_ROW = 2
#: Limite de linhas lidas de um arquivo (proteção contra planilhas gigantes).
MAX_ROWS = 50_000


@dataclass(slots=True)
class SheetData:
    """Conteúdo tabular normalizado estruturalmente (sem normalização de valores)."""

    headers: list[str]
    rows: list[dict[str, Any]]
    sheet_names: list[str] = field(default_factory=list)
    active_sheet: str | None = None
    delimiter: str | None = None
    encoding: str | None = None
    truncated: bool = False

    @property
    def total_rows(self) -> int:
        return len(self.rows)

    def row_numbers(self) -> list[int]:
        return [index + FIRST_DATA_ROW for index in range(len(self.rows))]


def _decode_csv(content: bytes) -> tuple[str, str]:
    """Decodifica o CSV testando as codificações mais comuns no Brasil."""
    for encoding in CSV_ENCODINGS:
        try:
            return content.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise UnprocessableFileError(
        "Não foi possível ler o arquivo: codificação de caracteres não suportada.",
        details={"tried": list(CSV_ENCODINGS)},
    )


def _detect_delimiter(sample: str) -> str:
    """Descobre o delimitador do CSV."""
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters="".join(CSV_DELIMITERS))
        return str(dialect.delimiter)
    except csv.Error:
        first_line = sample.splitlines()[0] if sample.splitlines() else ""
        counts = {delim: first_line.count(delim) for delim in CSV_DELIMITERS}
        best = max(counts, key=lambda key: counts[key])
        return best if counts[best] > 0 else ","


def _clean_headers(columns: list[Any]) -> list[str]:
    """Garante cabeçalhos não vazios e únicos."""
    headers: list[str] = []
    seen: dict[str, int] = {}
    for index, column in enumerate(columns):
        name = str(column).strip() if column is not None else ""
        if not name or name.lower().startswith("unnamed:"):
            name = f"coluna_{index + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name} ({seen[name]})"
        else:
            seen[name] = 1
        headers.append(name)
    return headers


def _frame_to_rows(frame: pd.DataFrame, headers: list[str]) -> list[dict[str, Any]]:
    """Converte o DataFrame em dicionários preservando os valores originais."""
    frame.columns = headers
    records: list[dict[str, Any]] = []
    for values in frame.itertuples(index=False, name=None):
        records.append(dict(zip(headers, values, strict=True)))
    return records


def read_csv_bytes(content: bytes) -> SheetData:
    """Lê um CSV em memória."""
    text, encoding = _decode_csv(content)
    if not text.strip():
        raise UnprocessableFileError("O arquivo CSV está vazio.")
    delimiter = _detect_delimiter(text[:8192])
    try:
        frame = pd.read_csv(
            io.StringIO(text),
            sep=delimiter,
            dtype=str,
            keep_default_na=False,
            na_values=[],
            skip_blank_lines=True,
            nrows=MAX_ROWS,
            engine="python",
        )
    except (pd.errors.ParserError, ValueError) as exc:
        raise UnprocessableFileError(
            "Não foi possível interpretar o CSV. Verifique o separador e as colunas.",
            details={"delimiter": delimiter},
        ) from exc

    headers = _clean_headers(list(frame.columns))
    rows = _frame_to_rows(frame, headers)
    rows = [row for row in rows if any(str(value).strip() for value in row.values())]
    return SheetData(
        headers=headers,
        rows=rows,
        sheet_names=[],
        active_sheet=None,
        delimiter=delimiter,
        encoding=encoding,
        truncated=len(rows) >= MAX_ROWS,
    )


def _has_content(row: dict[str, Any]) -> bool:
    """Indica se a linha tem algum valor aproveitável."""
    return any(
        value is not None and str(value).strip() not in {"", "nan", "NaT"} for value in row.values()
    )


def read_excel_bytes(content: bytes, *, extension: str, sheet_name: str | None = None) -> SheetData:
    """Lê um XLSX (openpyxl) ou XLS (xlrd) em memória."""
    engine: Literal["openpyxl", "xlrd"] = "openpyxl" if extension == ".xlsx" else "xlrd"
    try:
        with pd.ExcelFile(io.BytesIO(content), engine=engine) as workbook:
            sheet_names = [str(name) for name in workbook.sheet_names]
            if not sheet_names:
                raise UnprocessableFileError("A planilha não possui abas.")
            target = sheet_name if sheet_name in sheet_names else sheet_names[0]
            frame = workbook.parse(sheet_name=target, dtype=object, nrows=MAX_ROWS)
    except UnprocessableFileError:
        raise
    except Exception as exc:  # pandas/openpyxl levantam tipos variados
        raise UnprocessableFileError(
            "Não foi possível abrir a planilha. O arquivo pode estar corrompido "
            "ou protegido por senha.",
            details={"engine": engine},
        ) from exc

    headers = _clean_headers(list(frame.columns))
    rows = _frame_to_rows(frame, headers)
    rows = [row for row in rows if _has_content(row)]
    return SheetData(
        headers=headers,
        rows=rows,
        sheet_names=sheet_names,
        active_sheet=target,
        truncated=len(rows) >= MAX_ROWS,
    )


def read_spreadsheet(content: bytes, *, extension: str, sheet_name: str | None = None) -> SheetData:
    """Despacha a leitura conforme a extensão do arquivo."""
    if extension == ".csv":
        return read_csv_bytes(content)
    if extension in {".xlsx", ".xls"}:
        return read_excel_bytes(content, extension=extension, sheet_name=sheet_name)
    raise UnprocessableFileError(
        "Formato não suportado para importação.", details={"extension": extension}
    )


def read_spreadsheet_file(path: Path, *, sheet_name: str | None = None) -> SheetData:
    """Lê uma planilha a partir do disco."""
    if not path.exists():
        raise UnprocessableFileError("Arquivo da importação não encontrado no servidor.")
    return read_spreadsheet(path.read_bytes(), extension=path.suffix.lower(), sheet_name=sheet_name)
