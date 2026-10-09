"""Divisão de texto em blocos e normalização para busca portátil.

Função pura, sem dependência de banco ou rede — usada pela ingestão de
documentos, pelo seed e pelos testes.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

#: Tamanho alvo de cada bloco em caracteres.
DEFAULT_CHUNK_SIZE = 900
#: Sobreposição entre blocos consecutivos, para não perder contexto na fronteira.
DEFAULT_OVERLAP = 120
#: Aproximação simples de tokens (4 caracteres por token).
CHARS_PER_TOKEN = 4

_WHITESPACE_RE = re.compile(r"[ \t ]+")
_MULTILINE_RE = re.compile(r"\n{3,}")
_PARAGRAPH_RE = re.compile(r"\n\s*\n")
_WORD_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, slots=True)
class TextChunk:
    """Bloco de texto pronto para persistência."""

    index: int
    content: str
    normalized: str
    char_count: int
    token_estimate: int
    heading: str | None = None


def clean_text(raw: str) -> str:
    """Remove ruído de espaçamento preservando parágrafos."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = _WHITESPACE_RE.sub(" ", text)
    text = _MULTILINE_RE.sub("\n\n", text)
    return "\n".join(line.strip() for line in text.split("\n")).strip()


def normalize_for_search(text: str) -> str:
    """Minúsculas sem acentos, para o fallback de busca em SQLite."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _WHITESPACE_RE.sub(" ", without_accents)


def tokenize(text: str) -> list[str]:
    """Tokens alfanuméricos sem acento, usados no ranking do fallback."""
    return _WORD_RE.findall(normalize_for_search(text))


def estimate_tokens(text: str) -> int:
    """Estimativa conservadora de tokens de um texto."""
    return max(1, (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN)


def _detect_heading(block: str) -> str | None:
    for line in block.split("\n"):
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()[:120] or None
    return None


def chunk_text(
    raw: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[TextChunk]:
    """Divide o texto em blocos com sobreposição, respeitando parágrafos.

    Parágrafos são agrupados até o tamanho alvo. Um parágrafo maior que o alvo é
    quebrado por tamanho, mantendo ``overlap`` caracteres de contexto.
    """
    text = clean_text(raw)
    if not text:
        return []
    if overlap >= chunk_size:
        overlap = chunk_size // 4

    paragraphs = [p.strip() for p in _PARAGRAPH_RE.split(text) if p.strip()]
    blocks: list[str] = []
    buffer = ""

    for paragraph in paragraphs:
        if len(paragraph) > chunk_size:
            if buffer:
                blocks.append(buffer)
                buffer = ""
            blocks.extend(_split_by_size(paragraph, chunk_size, overlap))
            continue
        candidate = f"{buffer}\n\n{paragraph}" if buffer else paragraph
        if len(candidate) <= chunk_size:
            buffer = candidate
        else:
            blocks.append(buffer)
            buffer = paragraph
    if buffer:
        blocks.append(buffer)

    return [
        TextChunk(
            index=index,
            content=block,
            normalized=normalize_for_search(block),
            char_count=len(block),
            token_estimate=estimate_tokens(block),
            heading=_detect_heading(block),
        )
        for index, block in enumerate(blocks)
    ]


def _split_by_size(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Quebra um parágrafo longo em janelas com sobreposição."""
    step = max(1, chunk_size - overlap)
    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        if end < len(text):
            cut = text.rfind(" ", start + step // 2, end)
            if cut > start:
                end = cut
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return pieces
