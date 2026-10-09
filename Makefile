# OpsPilot — atalhos de operação (Linux/macOS/WSL/Git Bash).
# No Windows PowerShell use ./scripts/ops.ps1 <comando> (mesmos nomes).

SHELL := /bin/bash
COMPOSE := docker compose
BACKEND := cd backend &&
FRONTEND := cd frontend &&
PY := python

.DEFAULT_GOAL := help
.PHONY: help up up-automation down stop logs logs-backend ps migrate seed seed-reset \
        samples test test-backend test-frontend e2e lint lint-backend lint-frontend \
        format typecheck build build-frontend db-reset install install-backend \
        install-frontend dev-backend dev-frontend health smoke

help: ## Lista os comandos disponíveis
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- ambiente ----

up: ## Sobe postgres + backend + frontend (build incluído)
	$(COMPOSE) up --build -d
	@echo "Backend:  http://localhost:8000/docs"
	@echo "Frontend: http://localhost:5173"

up-automation: ## Sobe o ambiente incluindo o n8n (profile opcional)
	$(COMPOSE) --profile automation up --build -d
	@echo "n8n: http://localhost:5678"

down: ## Derruba os serviços e remove os volumes anônimos
	$(COMPOSE) down --remove-orphans

stop: ## Para os serviços sem remover containers
	$(COMPOSE) stop

ps: ## Mostra o estado dos serviços
	$(COMPOSE) ps

logs: ## Acompanha os logs de todos os serviços
	$(COMPOSE) logs -f --tail=100

logs-backend: ## Acompanha os logs do backend
	$(COMPOSE) logs -f --tail=200 backend

health: ## Consulta o healthcheck do backend
	curl -fsS http://localhost:8000/health && echo ""

# ------------------------------------------------------------------- dados ----

migrate: ## Aplica as migrations no banco do compose
	$(COMPOSE) exec backend alembic upgrade head

seed: ## Executa o seed idempotente de demonstração
	$(COMPOSE) exec backend python scripts_seed.py

seed-reset: ## Limpa os dados da organização demo e semeia novamente
	$(COMPOSE) exec backend python scripts_seed.py --reset

samples: ## Gera as planilhas sintéticas em data/samples
	$(PY) scripts/generate_sample_data.py

db-reset: ## Destrói e recria o banco local (apaga o volume do postgres)
	$(COMPOSE) down -v
	$(COMPOSE) up -d db
	@echo "Aguardando o postgres..."
	@until $(COMPOSE) exec -T db pg_isready -U opspilot -d opspilot >/dev/null 2>&1; do sleep 1; done
	$(COMPOSE) up -d --build backend
	@echo "Banco recriado, migrations e seed executados pelo entrypoint do backend."

# ----------------------------------------------------------------- qualidade --

install: install-backend install-frontend ## Instala as dependências locais

install-backend: ## Cria o venv e instala o backend com extras de desenvolvimento
	$(BACKEND) $(PY) -m venv .venv && .venv/bin/pip install -e ".[dev]" 2>/dev/null \
		|| ( $(BACKEND) .venv/Scripts/pip install -e ".[dev]" )

install-frontend: ## Instala as dependências do frontend
	$(FRONTEND) npm install

test: test-backend test-frontend ## Executa todos os testes automatizados

test-backend: ## Testes do backend (pytest)
	$(BACKEND) .venv/bin/python -m pytest -q 2>/dev/null || ( $(BACKEND) .venv/Scripts/python -m pytest -q )

test-frontend: ## Testes do frontend (vitest)
	$(FRONTEND) npm run test -- --run

e2e: ## Teste end-to-end (Playwright) contra o ambiente em execução
	$(FRONTEND) npm run test:e2e

lint: lint-backend lint-frontend ## Lint de backend e frontend

lint-backend: ## Ruff + MyPy
	$(BACKEND) .venv/bin/python -m ruff check . 2>/dev/null || ( $(BACKEND) .venv/Scripts/python -m ruff check . )
	$(BACKEND) .venv/bin/python -m ruff format --check . 2>/dev/null || ( $(BACKEND) .venv/Scripts/python -m ruff format --check . )
	$(BACKEND) .venv/bin/python -m mypy 2>/dev/null || ( $(BACKEND) .venv/Scripts/python -m mypy )

lint-frontend: ## ESLint + TypeScript
	$(FRONTEND) npm run lint
	$(FRONTEND) npm run typecheck

format: ## Formata o backend com ruff
	$(BACKEND) .venv/bin/python -m ruff format . 2>/dev/null || ( $(BACKEND) .venv/Scripts/python -m ruff format . )

typecheck: ## Type checking do backend
	$(BACKEND) .venv/bin/python -m mypy 2>/dev/null || ( $(BACKEND) .venv/Scripts/python -m mypy )

build: ## Constrói as imagens Docker
	$(COMPOSE) build

build-frontend: ## Build de produção do frontend
	$(FRONTEND) npm run build

# ------------------------------------------------------- desenvolvimento ------

dev-backend: ## Backend local com reload (SQLite, sem Docker)
	$(BACKEND) OPSPILOT_DATABASE_URL=sqlite+aiosqlite:///./var/dev.db \
		.venv/Scripts/python -m uvicorn app.main:app --reload

dev-frontend: ## Frontend local com Vite
	$(FRONTEND) npm run dev

smoke: ## Checagem rápida pós-subida (health + login + dashboard)
	$(PY) scripts/smoke_test.py
