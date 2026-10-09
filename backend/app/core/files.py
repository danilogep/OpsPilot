"""Validação e armazenamento seguro de arquivos enviados.

Regras aplicadas:

* extensão e MIME type dentro de uma allowlist;
* tamanho máximo configurável (``OPSPILOT_MAX_UPLOAD_MB``);
* nome de arquivo saneado (sem caminho, sem caractere de controle);
* gravação com nome gerado pela aplicação, preservando o nome original apenas
  como metadado.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.core.errors import PayloadTooLargeError, UnprocessableFileError

#: Extensões aceitas no módulo de importação de planilhas.
SPREADSHEET_EXTENSIONS: dict[str, tuple[str, ...]] = {
    ".csv": ("text/csv", "application/csv", "text/plain", "application/vnd.ms-excel"),
    ".xlsx": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/octet-stream",
        "application/zip",
    ),
    ".xls": ("application/vnd.ms-excel", "application/octet-stream"),
}

#: Extensões aceitas na base de conhecimento.
KNOWLEDGE_EXTENSIONS: dict[str, tuple[str, ...]] = {
    ".txt": ("text/plain",),
    ".md": ("text/markdown", "text/plain", "text/x-markdown"),
    ".pdf": ("application/pdf", "application/octet-stream"),
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
        "application/zip",
    ),
    ".csv": ("text/csv", "application/csv", "text/plain", "application/vnd.ms-excel"),
    ".xlsx": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/octet-stream",
        "application/zip",
    ),
}

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_MAGIC_SIGNATURES: dict[str, bytes] = {
    ".xlsx": b"PK\x03\x04",
    ".docx": b"PK\x03\x04",
    ".pdf": b"%PDF",
    ".xls": b"\xd0\xcf\x11\xe0",
}


@dataclass(frozen=True, slots=True)
class StoredFile:
    """Arquivo aceito e persistido em disco."""

    path: Path
    stored_name: str
    original_name: str
    extension: str
    content_type: str
    size_bytes: int


def sanitize_filename(filename: str | None, *, fallback: str = "arquivo") -> str:
    """Remove diretórios e caracteres perigosos do nome informado."""
    raw = (filename or "").strip()
    raw = raw.replace("\\", "/").split("/")[-1]
    raw = unicodedata.normalize("NFKD", raw)
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    raw = "".join(ch for ch in raw if ch.isprintable() and ch not in {"\r", "\n", "\t"})
    raw = _UNSAFE_CHARS.sub("_", raw).strip("._")
    if not raw or raw in {".", ".."}:
        raw = fallback
    return raw[:120]


def validate_upload(
    *,
    filename: str | None,
    content_type: str | None,
    content: bytes,
    allowed: dict[str, tuple[str, ...]],
) -> tuple[str, str, str]:
    """Valida nome, extensão, MIME, assinatura e tamanho.

    Retorna ``(nome_saneado, extensao, content_type_efetivo)``.
    """
    safe_name = sanitize_filename(filename)
    extension = Path(safe_name).suffix.lower()
    if extension not in allowed:
        raise UnprocessableFileError(
            "Formato de arquivo não suportado.",
            details={
                "extension": extension or "(sem extensão)",
                "allowed": sorted(allowed),
            },
        )
    if not content:
        raise UnprocessableFileError("Arquivo vazio.")
    if len(content) > settings.max_upload_bytes:
        raise PayloadTooLargeError(
            f"Arquivo acima do limite de {settings.max_upload_mb} MB.",
            details={"size_bytes": len(content), "max_bytes": settings.max_upload_bytes},
        )

    effective_type = (content_type or "").split(";")[0].strip().lower()
    accepted = allowed[extension]
    if effective_type and effective_type not in accepted:
        raise UnprocessableFileError(
            "O tipo de conteúdo informado não corresponde à extensão do arquivo.",
            details={"content_type": effective_type, "expected": list(accepted)},
        )

    signature = _MAGIC_SIGNATURES.get(extension)
    if signature and not content.startswith(signature):
        raise UnprocessableFileError(
            "O conteúdo do arquivo não corresponde à extensão informada.",
            details={"extension": extension},
        )
    return safe_name, extension, effective_type or accepted[0]


def store_upload(
    *,
    content: bytes,
    safe_name: str,
    extension: str,
    content_type: str,
    subdirectory: str,
) -> StoredFile:
    """Grava o arquivo com nome gerado pela aplicação."""
    directory = settings.upload_dir / subdirectory
    directory.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{extension}"
    path = directory / stored_name
    path.write_bytes(content)
    return StoredFile(
        path=path,
        stored_name=stored_name,
        original_name=safe_name,
        extension=extension,
        content_type=content_type,
        size_bytes=len(content),
    )
