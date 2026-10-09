"""Providers reais de IA (Anthropic, OpenAI, Gemini).

As implementações são funcionais e usam apenas ``httpx``: basta configurar
``OPSPILOT_LLM_PROVIDER`` e a chave correspondente. **Nenhuma chave aparece em
log ou em mensagem de erro** — a ausência de chave é reportada como erro de
configuração, sem revelar valores.

O contexto consultado no banco é serializado como um bloco de dados no prompt,
com instrução explícita de responder apenas com base nele.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import settings
from app.core.errors import ProviderError
from app.integrations.llm.base import LLMProvider, LLMRequest, LLMResponse

#: Instrução comum a todos os providers reais.
GROUNDING_INSTRUCTION = (
    "Use exclusivamente os dados do bloco DADOS para responder. "
    "Não invente números, nomes ou datas. Se o bloco não contiver evidência "
    'suficiente, responda exatamente: "Não encontrei evidências suficientes nos '
    'dados disponíveis." Responda em português do Brasil.'
)


def _build_user_content(request: LLMRequest) -> str:
    """Monta o conteúdo do usuário com a pergunta e o bloco de dados."""
    context_block = json.dumps(request.context, ensure_ascii=False, default=str, indent=2)
    parts = [request.user_text.strip(), "", "DADOS:", "```json", context_block, "```"]
    if request.expects_json:
        parts.append("Responda apenas com JSON válido, sem texto antes ou depois.")
    return "\n".join(parts)


def _system_prompt(request: LLMRequest) -> str:
    return f"{request.system.strip()}\n\n{GROUNDING_INSTRUCTION}"


class AnthropicProvider(LLMProvider):
    """Claude via API de mensagens da Anthropic."""

    name = "anthropic"
    default_model = "claude-sonnet-5-5"
    supports_json = False
    api_url = "https://api.anthropic.com/v1/messages"
    api_version = "2023-06-01"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if not settings.anthropic_api_key:
            raise ProviderError(
                "Provider Anthropic selecionado, mas a chave não está configurada.",
                details={"variable": "OPSPILOT_ANTHROPIC_API_KEY"},
            )
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
            "system": _system_prompt(request),
            "messages": [{"role": "user", "content": _build_user_content(request)}],
        }
        headers = {
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": self.api_version,
            "content-type": "application/json",
        }
        data = await _post_json(self.api_url, payload, headers, provider=self.name)
        blocks = data.get("content") or []
        text = "".join(block.get("text", "") for block in blocks if block.get("type") == "text")
        usage = data.get("usage") or {}
        return LLMResponse(
            text=text.strip(),
            provider=self.name,
            model=str(data.get("model", self.model)),
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            finish_reason=str(data.get("stop_reason", "stop")),
        )


class OpenAIProvider(LLMProvider):
    """GPT via API de chat completions da OpenAI."""

    name = "openai"
    default_model = "gpt-4o-mini"
    supports_json = True
    api_url = "https://api.openai.com/v1/chat/completions"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if not settings.openai_api_key:
            raise ProviderError(
                "Provider OpenAI selecionado, mas a chave não está configurada.",
                details={"variable": "OPSPILOT_OPENAI_API_KEY"},
            )
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
            "messages": [
                {"role": "system", "content": _system_prompt(request)},
                {"role": "user", "content": _build_user_content(request)},
            ],
        }
        if request.expects_json:
            payload["response_format"] = {"type": "json_object"}
        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        data = await _post_json(self.api_url, payload, headers, provider=self.name)
        choices = data.get("choices") or [{}]
        message = choices[0].get("message") or {}
        usage = data.get("usage") or {}
        return LLMResponse(
            text=str(message.get("content", "")).strip(),
            provider=self.name,
            model=str(data.get("model", self.model)),
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            finish_reason=str(choices[0].get("finish_reason", "stop")),
        )


class GeminiProvider(LLMProvider):
    """Gemini via API generativeLanguage do Google."""

    name = "gemini"
    default_model = "gemini-1.5-flash"
    supports_json = True
    base_url = "https://generativelanguage.googleapis.com/v1beta/models"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if not settings.gemini_api_key:
            raise ProviderError(
                "Provider Gemini selecionado, mas a chave não está configurada.",
                details={"variable": "OPSPILOT_GEMINI_API_KEY"},
            )
        generation: dict[str, Any] = {
            "temperature": request.temperature,
            "maxOutputTokens": request.max_output_tokens,
        }
        if request.expects_json:
            generation["responseMimeType"] = "application/json"
        payload = {
            "systemInstruction": {"parts": [{"text": _system_prompt(request)}]},
            "contents": [{"role": "user", "parts": [{"text": _build_user_content(request)}]}],
            "generationConfig": generation,
        }
        url = f"{self.base_url}/{self.model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": settings.gemini_api_key,
        }
        data = await _post_json(url, payload, headers, provider=self.name)
        candidates = data.get("candidates") or [{}]
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(part.get("text", "") for part in parts)
        usage = data.get("usageMetadata") or {}
        return LLMResponse(
            text=text.strip(),
            provider=self.name,
            model=self.model,
            input_tokens=int(usage.get("promptTokenCount", 0)),
            output_tokens=int(usage.get("candidatesTokenCount", 0)),
            finish_reason=str(candidates[0].get("finishReason", "stop")),
        )


async def _post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    *,
    provider: str,
) -> dict[str, Any]:
    """POST JSON com timeout, sem expor cabeçalhos em caso de erro."""
    try:
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            response = await client.post(url, json=payload, headers=headers)
    except httpx.TimeoutException as exc:
        raise ProviderError(
            f"Tempo esgotado ao consultar o provider {provider}.", code="provider_timeout"
        ) from exc
    except httpx.HTTPError as exc:
        raise ProviderError(f"Falha de rede ao consultar o provider {provider}.") from exc

    if response.status_code >= 400:
        raise ProviderError(
            f"O provider {provider} recusou a requisição.",
            details={"status_code": response.status_code},
        )
    try:
        data: dict[str, Any] = response.json()
    except ValueError as exc:
        raise ProviderError(f"Resposta inválida do provider {provider}.") from exc
    return data
