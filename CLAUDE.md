# CLAUDE.md — OpsPilot

Guia operacional do repositório para agentes de IA e novos desenvolvedores.
Este arquivo descreve **arquitetura, comandos, padrões e decisões**. Leia antes de alterar código.

> **Projeto demonstrativo de portfólio.** Todos os dados são **sintéticos**. Nenhuma credencial real,
> nenhum dado pessoal real. O provider de IA padrão é `mock` e o sistema funciona **sem nenhuma chave de API**.

---

## 1. O que é

OpsPilot é um hub de operações, dados e IA para pequenas empresas. Permite:

1. Ingerir planilhas (CSV/XLSX/XLS) com colunas heterogêneas.
2. Mapear colunas para um modelo canônico (sugestão automática + revisão humana).
3. Validar, normalizar e deduplicar os dados linha a linha.
4. Persistir clientes, planos, leads e renovações isolados por organização.
5. Acompanhar indicadores em um dashboard.
6. Perguntar sobre os próprios dados com respostas **fundamentadas e com fontes**.
7. Classificar leads (score determinístico + opcionalmente IA).
8. Integrar com n8n por webhooks (entrada e saída, HMAC + idempotência).
9. Auditar ações e uso de IA.

## 2. Arquitetura (visão rápida)

```
frontend (React/Vite/TS)  ──HTTP/JSON──>  backend (FastAPI)  ──asyncpg──>  PostgreSQL 16
                                             │
                                             ├─ integrations/llm (mock | anthropic | openai | gemini)
                                             ├─ integrations/embeddings (opcional, não obrigatório)
                                             └─ integrations/webhooks (n8n, HMAC-SHA256)
```

- **Camadas**: `api` (routers HTTP) → `domains/*/service.py` (regra de negócio) → `db/models` (persistência).
- **Schemas** Pydantic v2 em `domains/*/schemas.py`. Nunca expor modelo ORM direto.
- **Multi-tenant** por `organization_id` em todas as tabelas de negócio. Toda query de negócio
  passa por `organization_id` nos serviços de domínio e pelas dependências em `app/api/deps.py`.
- **RAG** obrigatório sem API externa: busca textual no PostgreSQL (`to_tsvector`/`plainto_tsquery`)
  com fallback portátil para SQLite (usado nos testes). Ver `docs/adr/003-rag-fallback.md`.
- **Agentes** explícitos e limitados: `ToolRegistry` com ferramentas allowlisted e limite de passos.

Detalhes e diagramas Mermaid: [`docs/architecture.md`](docs/architecture.md).

## 3. Layout do repositório

```
backend/app/
  api/v1/            agregação de routers + dependências HTTP
  core/              config, segurança, logging, erros, paginação, tenancy
  db/                engine/session, Base, models/ (SQLAlchemy 2.x tipado)
  domains/<x>/       router.py + service.py + schemas.py (+ helpers do domínio)
  integrations/      llm/, embeddings/, webhooks/
  main.py            app factory, middlewares, /health
backend/tests/       pytest (unit + API, SQLite async)
frontend/src/
  app/               bootstrap, providers, layout
  components/        UI reutilizável (sem regra de negócio)
  features/<x>/      hooks de dados + componentes do domínio
  lib/               api client, auth, formatadores
  routes/            páginas (uma por rota)
  types/             tipos compartilhados
data/samples/        planilhas sintéticas de demonstração
integrations/n8n/    workflow de exemplo + README
scripts/             geração de dados, seed, helpers PowerShell/Bash
docs/                architecture, api, demo, data-dictionary, security, adr/
```

## 4. Comandos

Make (Linux/macOS/WSL/Git Bash) e PowerShell (`scripts/ops.ps1`) são equivalentes.

| Objetivo | Make | PowerShell |
| --- | --- | --- |
| Subir tudo (Docker) | `make up` | `./scripts/ops.ps1 up` |
| Derrubar | `make down` | `./scripts/ops.ps1 down` |
| Logs | `make logs` | `./scripts/ops.ps1 logs` |
| Migrations | `make migrate` | `./scripts/ops.ps1 migrate` |
| Seed idempotente | `make seed` | `./scripts/ops.ps1 seed` |
| Gerar amostras | `make samples` | `./scripts/ops.ps1 samples` |
| Testes backend | `make test-backend` | `./scripts/ops.ps1 test-backend` |
| Testes frontend | `make test-frontend` | `./scripts/ops.ps1 test-frontend` |
| Lint + types | `make lint` | `./scripts/ops.ps1 lint` |
| Reset do banco local | `make db-reset` | `./scripts/ops.ps1 db-reset` |

Comando principal: `docker compose up --build`.
Backend expõe `/health`, `/docs`, `/redoc` em `http://localhost:8000`. Frontend em `http://localhost:5173`.

### Desenvolvimento sem Docker

```bash
cd backend && python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"   # Windows
cd backend && OPSPILOT_DATABASE_URL=sqlite+aiosqlite:///./opspilot.db .venv/Scripts/python -m uvicorn app.main:app --reload
cd frontend && npm install && npm run dev
```

## 5. Padrões de código

- **Python 3.12**, tipagem completa (`mypy --strict` no pacote `app`), `ruff` para lint/format.
- SQLAlchemy 2.x: `Mapped[...]` / `mapped_column`, sessão **assíncrona**, sem lazy-load implícito em rota.
- Pydantic v2: `model_config = ConfigDict(from_attributes=True)` nos schemas de saída.
- Nomes de código em **inglês**; textos de interface e documentação em **português brasileiro**.
- Erros de API padronizados: `{"error": {"code": ..., "message": ..., "details": ...}}` sem stack trace.
- Logs estruturados (structlog) com `correlation_id`; **nunca** logar chaves, tokens ou payload sensível completo.
- IA: toda resposta carrega `sources`; sem evidência, retorna
  `"Não encontrei evidências suficientes nos dados disponíveis."`
- Nada de números inventados no frontend: todo indicador vem da API.

## 6. Decisões registradas (ADR)

- [001 — Arquitetura modular por domínio](docs/adr/001-architecture.md)
- [002 — Abstração de providers de LLM com mock padrão](docs/adr/002-llm-provider.md)
- [003 — RAG sem dependência externa (Postgres FTS + fallback)](docs/adr/003-rag-fallback.md)
- [004 — Score de leads determinístico e auditável](docs/adr/004-lead-scoring.md)
- [005 — Contrato de webhooks (HMAC + idempotência)](docs/adr/005-webhooks.md)
- [006 — Compatibilidade SQLite nos testes](docs/adr/006-sqlite-test-compat.md)

## 7. Regras invioláveis

1. Nenhum segredo no código ou no histórico. `.env.example` sem valores reais.
2. Dados de demonstração sempre sintéticos e marcados como tal.
3. `LLM_PROVIDER=mock` é o padrão e precisa continuar funcional e testado.
4. Não quebrar o build: cada fase termina com lint, types e testes verdes.
5. Toda alteração de schema passa por migration Alembic.
