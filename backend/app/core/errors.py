"""Erros de domínio e handlers HTTP padronizados.

Formato de resposta de erro (sem detalhes internos, sem stack trace):

    {"error": {"code": "not_found", "message": "...", "details": {...}}}
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_correlation_id, get_logger

logger = get_logger(__name__)


class AppError(Exception):
    """Erro de aplicação com código estável e status HTTP."""

    code = "internal_error"
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    message = "Erro interno inesperado."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
        code: str | None = None,
    ) -> None:
        self.message = message or self.message
        self.details = details or {}
        if code:
            self.code = code
        super().__init__(self.message)


class NotFoundError(AppError):
    code = "not_found"
    status_code = status.HTTP_404_NOT_FOUND
    message = "Recurso não encontrado."


class ValidationError(AppError):
    code = "validation_error"
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    message = "Dados inválidos."


class ConflictError(AppError):
    code = "conflict"
    status_code = status.HTTP_409_CONFLICT
    message = "Conflito com o estado atual do recurso."


class AuthenticationError(AppError):
    code = "unauthenticated"
    status_code = status.HTTP_401_UNAUTHORIZED
    message = "Credenciais inválidas ou ausentes."


class PermissionDeniedError(AppError):
    code = "forbidden"
    status_code = status.HTTP_403_FORBIDDEN
    message = "Você não tem permissão para esta ação."


class UnprocessableFileError(AppError):
    code = "unprocessable_file"
    status_code = status.HTTP_400_BAD_REQUEST
    message = "Arquivo inválido ou não suportado."


class PayloadTooLargeError(AppError):
    code = "payload_too_large"
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    message = "Arquivo acima do tamanho máximo permitido."


class ProviderError(AppError):
    code = "provider_error"
    status_code = status.HTTP_502_BAD_GATEWAY
    message = "Falha ao consultar o provedor externo."


def error_payload(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    """Monta o corpo padronizado de erro."""
    payload: dict[str, Any] = {"code": code, "message": message, "details": details or {}}
    cid = get_correlation_id()
    if cid:
        payload["correlation_id"] = cid
    return {"error": payload}


def register_exception_handlers(app: FastAPI) -> None:
    """Registra handlers que nunca expõem detalhes internos ao cliente."""

    @app.exception_handler(AppError)
    async def _app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {
                "field": ".".join(str(part) for part in err.get("loc", ())[1:]),
                "message": err.get("msg", "inválido"),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_payload("validation_error", "Dados inválidos.", {"fields": fields}),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code_map = {
            401: "unauthenticated",
            403: "forbidden",
            404: "not_found",
            405: "method_not_allowed",
            413: "payload_too_large",
            429: "rate_limited",
        }
        detail = exc.detail if isinstance(exc.detail, str) else "Erro na requisição."
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(code_map.get(exc.status_code, "http_error"), detail),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            exc_type=type(exc).__name__,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_payload("internal_error", "Erro interno inesperado."),
        )
