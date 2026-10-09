"""Execução rastreada de chamadas de IA.

Responsabilidades:

* aplicar **timeout** e **retry** com espera progressiva;
* registrar cada chamada em ``llm_usage`` (provider, modelo, versão do prompt,
  tokens, custo estimado, duração, status) — inclusive para o provider mock;
* nunca persistir o prompt completo: apenas um resumo truncado;
* nunca registrar chaves de API em log.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ProviderError
from app.core.logging import get_logger
from app.db.models import LLMCallStatus, LLMUsage, User
from app.integrations.llm.base import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    estimate_cost_usd,
)
from app.integrations.llm.factory import get_provider

logger = get_logger(__name__)

#: Tamanho máximo do resumo da entrada guardado em banco.
INPUT_SUMMARY_LIMIT = 400
#: Espera entre tentativas (segundos).
RETRY_BACKOFF = (0.4, 1.2, 2.0)


@dataclass(slots=True)
class LLMExecution:
    """Resultado de uma execução com rastreamento."""

    response: LLMResponse
    duration_ms: int
    attempts: int
    estimated_cost_usd: Decimal
    usage: LLMUsage

    @property
    def text(self) -> str:
        return self.response.text

    def trace(self) -> dict[str, object]:
        """Metadados de rastreamento expostos na API."""
        return {
            "provider": self.response.provider,
            "model": self.response.model,
            "prompt_version": self.usage.prompt_version,
            "input_tokens": self.response.input_tokens,
            "output_tokens": self.response.output_tokens,
            "estimated_cost_usd": str(self.estimated_cost_usd),
            "duration_ms": self.duration_ms,
            "attempts": self.attempts,
            "is_mock": self.response.is_mock,
        }


def summarize_input(request: LLMRequest) -> str:
    """Resumo curto e seguro da entrada, para auditoria."""
    question = request.user_text.strip().replace("\n", " ")
    return question[:INPUT_SUMMARY_LIMIT] or f"[{request.feature.value}]"


async def run_llm(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    request: LLMRequest,
    actor: User | None = None,
    agent_run_id: uuid.UUID | None = None,
    provider: LLMProvider | None = None,
) -> LLMExecution:
    """Executa a chamada e registra o uso. A transação é do chamador."""
    engine = provider or get_provider()
    attempts = 0
    started = time.perf_counter()
    last_error: Exception | None = None
    response: LLMResponse | None = None

    while attempts <= settings.llm_max_retries:
        attempts += 1
        try:
            response = await asyncio.wait_for(
                engine.complete(request), timeout=settings.llm_timeout_seconds
            )
            break
        except TimeoutError as exc:
            last_error = ProviderError(
                "Tempo esgotado ao consultar o provider de IA.", code="provider_timeout"
            )
            logger.warning(
                "llm_timeout", provider=engine.name, feature=request.feature.value, attempt=attempts
            )
            del exc
        except ProviderError as exc:
            last_error = exc
            logger.warning(
                "llm_provider_error",
                provider=engine.name,
                feature=request.feature.value,
                attempt=attempts,
                code=exc.code,
            )
        if attempts <= settings.llm_max_retries:
            await asyncio.sleep(RETRY_BACKOFF[min(attempts - 1, len(RETRY_BACKOFF) - 1)])

    duration_ms = int((time.perf_counter() - started) * 1000)

    if response is None:
        usage = LLMUsage(
            organization_id=organization_id,
            feature=request.feature.value,
            provider=engine.name,
            model=engine.model or engine.default_model,
            prompt_version=request.prompt_version,
            status=(
                LLMCallStatus.TIMEOUT
                if isinstance(last_error, ProviderError) and last_error.code == "provider_timeout"
                else LLMCallStatus.ERROR
            ),
            input_summary=summarize_input(request),
            duration_ms=duration_ms,
            attempts=attempts,
            error=str(last_error)[:300] if last_error else "falha desconhecida",
            agent_run_id=agent_run_id,
            created_by_id=actor.id if actor else None,
        )
        session.add(usage)
        raise last_error or ProviderError("Falha ao consultar o provider de IA.")

    cost = estimate_cost_usd(response.model, response.input_tokens, response.output_tokens)
    usage = LLMUsage(
        organization_id=organization_id,
        feature=request.feature.value,
        provider=response.provider,
        model=response.model,
        prompt_version=request.prompt_version,
        status=LLMCallStatus.SUCCESS,
        input_summary=summarize_input(request),
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        estimated_cost_usd=cost,
        duration_ms=duration_ms,
        attempts=attempts,
        agent_run_id=agent_run_id,
        created_by_id=actor.id if actor else None,
    )
    session.add(usage)
    logger.info(
        "llm_call",
        provider=response.provider,
        model=response.model,
        feature=request.feature.value,
        duration_ms=duration_ms,
        output_tokens=response.output_tokens,
    )
    return LLMExecution(
        response=response,
        duration_ms=duration_ms,
        attempts=attempts,
        estimated_cost_usd=cost,
        usage=usage,
    )


def parse_json_response(text: str) -> dict[str, object]:
    """Extrai JSON da resposta do modelo, tolerando cercas de código."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1] if cleaned.count("```") >= 2 else cleaned
        cleaned = cleaned.removeprefix("json").strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ProviderError("O provider não devolveu JSON válido.", code="invalid_json")
    try:
        parsed = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ProviderError("O provider não devolveu JSON válido.", code="invalid_json") from exc
    if not isinstance(parsed, dict):
        raise ProviderError("O provider não devolveu um objeto JSON.", code="invalid_json")
    return parsed
