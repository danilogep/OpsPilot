"""Contrato dos providers de IA.

Qualquer provider implementa :class:`LLMProvider`. O restante da aplicação só
conhece esta interface, o que permite trocar de fornecedor por variável de
ambiente (``OPSPILOT_LLM_PROVIDER``) sem alterar regra de negócio.

Nenhuma chave de API trafega por aqui além da leitura da configuração, e nada
do conteúdo é registrado em log pelo provider.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any


class LLMFeature(StrEnum):
    """Funcionalidades que consomem IA (usado em rastreamento e no mock)."""

    ASSISTANT = "assistant"
    LEAD_CLASSIFIER = "lead_classifier"
    RENEWAL_SUMMARY = "renewal_summary"
    MESSAGE_DRAFT = "message_draft"
    AGENT = "agent"


@dataclass(frozen=True, slots=True)
class LLMMessage:
    """Mensagem de conversa enviada ao provider."""

    role: str
    content: str


@dataclass(slots=True)
class LLMRequest:
    """Entrada padronizada de uma chamada de IA.

    ``context`` carrega os dados já consultados no banco (fatos verificáveis).
    Os providers reais recebem esse contexto serializado no prompt; o provider
    mock o usa diretamente para montar uma resposta coerente e offline.
    """

    feature: LLMFeature
    system: str
    messages: list[LLMMessage]
    prompt_version: str = "v1"
    max_output_tokens: int = 1200
    temperature: float = 0.2
    expects_json: bool = False
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def user_text(self) -> str:
        """Concatena as mensagens do usuário (útil para resumo e para o mock)."""
        return "\n".join(message.content for message in self.messages if message.role == "user")


@dataclass(slots=True)
class LLMResponse:
    """Saída padronizada de uma chamada de IA."""

    text: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str = "stop"
    is_mock: bool = False

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


#: Preço por 1 milhão de tokens (USD). Valores de referência para **estimativa**;
#: o mock custa zero. Mantidos em um único lugar para facilitar atualização.
PRICE_TABLE: dict[str, tuple[Decimal, Decimal]] = {
    "mock": (Decimal("0"), Decimal("0")),
    "claude-sonnet-5-5": (Decimal("3.00"), Decimal("15.00")),
    "claude-haiku-5-5": (Decimal("1.00"), Decimal("5.00")),
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
    "gpt-4o": (Decimal("2.50"), Decimal("10.00")),
    "gemini-1.5-flash": (Decimal("0.075"), Decimal("0.30")),
    "gemini-1.5-pro": (Decimal("1.25"), Decimal("5.00")),
}
DEFAULT_PRICE = (Decimal("1.00"), Decimal("3.00"))


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    """Estimativa de custo em dólares a partir da tabela de preços."""
    price_in, price_out = PRICE_TABLE.get(model, DEFAULT_PRICE)
    total = (Decimal(input_tokens) * price_in + Decimal(output_tokens) * price_out) / Decimal(
        1_000_000
    )
    return total.quantize(Decimal("0.000001"))


def estimate_tokens(text: str) -> int:
    """Aproximação de tokens (4 caracteres por token), usada pelo mock."""
    return max(1, len(text) // 4)


class LLMProvider(abc.ABC):
    """Interface de um provider de IA."""

    #: Identificador curto usado em configuração e rastreamento.
    name: str = "base"
    #: Modelo usado quando ``OPSPILOT_LLM_MODEL`` não é informado.
    default_model: str = ""
    #: Indica se o provider garante saída JSON válida.
    supports_json: bool = False
    #: ``True`` apenas para o provider local de demonstração.
    is_mock: bool = False

    def __init__(self, *, model: str | None = None) -> None:
        self.model = model or self.default_model

    @abc.abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Executa a chamada e devolve a resposta normalizada."""

    def describe(self) -> dict[str, Any]:
        """Metadados do provider para exibição na interface."""
        return {
            "provider": self.name,
            "model": self.model,
            "supports_json": self.supports_json,
            "is_mock": self.is_mock,
        }
