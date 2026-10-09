"""Logging estruturado com structlog e correlation id por requisição."""

from __future__ import annotations

import logging
import sys
import uuid
from collections.abc import MutableMapping
from contextvars import ContextVar
from typing import Any

import structlog

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)

#: Chaves que nunca devem aparecer em log, mesmo que cheguem por acidente.
SENSITIVE_KEYS = frozenset(
    {
        "password",
        "senha",
        "token",
        "access_token",
        "authorization",
        "api_key",
        "anthropic_api_key",
        "openai_api_key",
        "gemini_api_key",
        "jwt_secret",
        "webhook_secret",
        "secret",
    }
)


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def set_correlation_id(value: str | None) -> str:
    cid = value or new_correlation_id()
    _correlation_id.set(cid)
    return cid


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def _add_correlation_id(
    _logger: Any, _name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    cid = get_correlation_id()
    if cid:
        event_dict.setdefault("correlation_id", cid)
    return event_dict


def _redact(
    _logger: Any, _name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Remove valores sensíveis antes de qualquer renderização."""
    for key in list(event_dict):
        if key.lower() in SENSITIVE_KEYS:
            event_dict[key] = "***"
    return event_dict


def configure_logging(level: str = "INFO", json_output: bool = False) -> None:
    """Configura structlog + stdlib logging uma única vez."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
        force=True,
    )
    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _add_correlation_id,
            _redact,
            structlog.processors.StackInfoRenderer(),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
