"""Exportação de listagens em CSV.

O CSV é gerado com BOM e ponto e vírgula como separador, que é o padrão aberto
pelo Excel em português do Brasil sem passo extra de importação.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from fastapi.responses import StreamingResponse

CSV_DELIMITER = ";"
CSV_MEDIA_TYPE = "text/csv; charset=utf-8"


def format_cell(value: Any) -> str:
    """Converte um valor em texto adequado para planilha brasileira."""
    if value is None:
        return ""
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, bool):
        return "sim" if value else "não"
    if isinstance(value, Decimal):
        return f"{value:.2f}".replace(".", ",")
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    return str(value)


def rows_to_csv(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    """Serializa cabeçalho e linhas em uma string CSV."""
    buffer = io.StringIO()
    writer = csv.writer(
        buffer, delimiter=CSV_DELIMITER, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n"
    )
    writer.writerow(list(headers))
    for row in rows:
        writer.writerow([format_cell(cell) for cell in row])
    return buffer.getvalue()


def csv_response(
    *, filename: str, headers: Sequence[str], rows: Iterable[Sequence[Any]]
) -> StreamingResponse:
    """Monta a resposta HTTP de download do CSV."""
    content = "﻿" + rows_to_csv(headers, rows)
    return StreamingResponse(
        io.BytesIO(content.encode("utf-8")),
        media_type=CSV_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
