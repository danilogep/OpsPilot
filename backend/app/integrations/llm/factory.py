"""Seleção do provider de IA por configuração."""

from __future__ import annotations

from app.core.config import LLMProviderName, settings
from app.integrations.llm.base import LLMProvider
from app.integrations.llm.mock import MockProvider
from app.integrations.llm.providers import (
    AnthropicProvider,
    GeminiProvider,
    OpenAIProvider,
)

PROVIDERS: dict[str, type[LLMProvider]] = {
    MockProvider.name: MockProvider,
    AnthropicProvider.name: AnthropicProvider,
    OpenAIProvider.name: OpenAIProvider,
    GeminiProvider.name: GeminiProvider,
}


def get_provider(
    name: LLMProviderName | str | None = None, *, model: str | None = None
) -> LLMProvider:
    """Instancia o provider configurado (padrão: ``mock``).

    Nomes desconhecidos caem no mock em vez de quebrar a aplicação — o projeto
    precisa funcionar sem nenhuma chave de API.
    """
    key = str(name or settings.llm_provider).strip().lower()
    provider_cls = PROVIDERS.get(key, MockProvider)
    return provider_cls(model=model or settings.llm_model or None)


def available_providers() -> list[dict[str, object]]:
    """Lista os providers suportados e se estão prontos para uso."""
    configured = {
        "mock": True,
        "anthropic": bool(settings.anthropic_api_key),
        "openai": bool(settings.openai_api_key),
        "gemini": bool(settings.gemini_api_key),
    }
    return [
        {
            "name": name,
            "default_model": provider_cls.default_model,
            "supports_json": provider_cls.supports_json,
            "is_mock": provider_cls.is_mock,
            "configured": configured.get(name, False),
            "active": name == settings.llm_provider,
        }
        for name, provider_cls in PROVIDERS.items()
    ]
