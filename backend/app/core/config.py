"""Configuração da aplicação carregada de variáveis de ambiente.

Todas as variáveis usam o prefixo ``OPSPILOT_``. Nenhum segredo possui valor real
embutido: os defaults servem apenas para o ambiente local de demonstração.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

LLMProviderName = Literal["mock", "anthropic", "openai", "gemini"]
EmbeddingsProviderName = Literal["none", "mock", "openai"]
Environment = Literal["local", "test", "staging", "production"]


class Settings(BaseSettings):
    """Configuração tipada da aplicação."""

    model_config = SettingsConfigDict(
        env_prefix="OPSPILOT_",
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Aplicação ---
    app_name: str = "OpsPilot"
    api_v1_prefix: str = "/api/v1"
    environment: Environment = "local"
    debug: bool = True
    log_level: str = "INFO"
    log_json: bool = False

    # --- Banco ---
    database_url: str = "sqlite+aiosqlite:///./opspilot.db"
    db_echo: bool = False

    # --- Segurança ---
    jwt_secret: str = "insecure-local-demo-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://localhost:4173",
            "http://localhost:8080",
        ]
    )

    # --- Uploads ---
    upload_dir: Path = Path("./var/uploads")
    max_upload_mb: int = 20

    # --- Seed de demonstração ---
    demo_org_name: str = "Acme Serviços Ltda"
    demo_password: str = "OpsPilot!2026"

    # --- IA ---
    llm_provider: LLMProviderName = "mock"
    llm_model: str = ""
    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 2
    llm_max_output_tokens: int = 1200
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""

    # --- Embeddings (opcional) ---
    embeddings_provider: EmbeddingsProviderName = "none"

    # --- Webhooks ---
    webhook_secret: str = "opspilot_webhook_demo_secret"
    webhook_outbound_url: str = ""
    webhook_timeout_seconds: float = 10.0

    # --- Agentes ---
    agent_max_steps: int = 6

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Aceita lista JSON ou string separada por vírgulas."""
        if isinstance(value, str):
            raw = value.strip()
            if raw.startswith("["):
                return json.loads(raw)
            return [item.strip() for item in raw.split(",") if item.strip()]
        return value

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retorna a configuração em cache (uma instância por processo)."""
    return Settings()


settings = get_settings()
