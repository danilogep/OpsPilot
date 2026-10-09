# Handoff — continuar o OpsPilot

Cole a mensagem abaixo na aba Code do Claude (ou no Codex), dentro da pasta deste repositório.

---

Você está continuando um projeto existente e **publicado**. Leia primeiro `CLAUDE.md`, `README.md`, `docs/validation.md`, `docker-compose.yml` e o estado do Git. Não reescreva funcionalidades já implementadas. Inspecione o código atual antes de editar.

## Estado atual (atualizado em 09/10/2026)

- Repositório publicado em <https://github.com/danilogep/OpsPilot>, branch `main`, remote `origin` configurado.
- 7 commits, 197 arquivos versionados, árvore de trabalho limpa no momento do push.
- Nenhum `.env`, token, banco local, `node_modules`, `.venv` ou artefato gerado foi publicado.
- Ambiente Docker validado e saudável: `db`, `backend` e `frontend`.

### Objetivo do produto

OpsPilot — Hub de Operações, Dados e IA para pequenas empresas. Somente dados sintéticos. Funciona sem chave de IA com `OPSPILOT_LLM_PROVIDER=mock` (padrão).

## O que está implementado

### Backend (FastAPI, Python 3.12)

- Modular por domínio, PostgreSQL 16 com SQLAlchemy assíncrono e Alembic (migrations `0001_initial_schema` e `0002_delivery_fixes`).
- SQLite temporário nos testes; `OPSPILOT_TEST_DATABASE_URL` permite PostgreSQL dedicado.
- JWT, Argon2, papéis ADMIN/ANALYST/VIEWER e isolamento por `organization_id`.
- Clientes, planos, leads, renovações, histórico e exportação CSV.
- Importação CSV/XLSX/XLS: mapeamento sugerido, normalização, validação linha a linha, duplicidades, preview, commit transacional e relatório.
- Dashboard com métricas calculadas no banco (nenhum número fixo no código).
- Assistente de IA: provider mock padrão + adapters Anthropic, OpenAI e Gemini.
- Respostas sempre com fontes; sem evidência responde "Não encontrei evidências suficientes nos dados disponíveis."
- Base de conhecimento TXT/Markdown/PDF/DOCX/CSV/XLSX com PostgreSQL Full Text Search em português e fallback lexical portátil.
- Score determinístico de leads (7 critérios, 100 pontos) e classificação opcional por IA.
- Agentes com ferramentas allowlisted, limite de passos e rastreamento completo.
- Webhooks HMAC com idempotência e workflow n8n de exemplo.
- Auditoria e histórico de uso de IA. `/health`, `/health/live`, `/docs`, `/redoc`.

### Frontend (React 18, TypeScript, Vite, Tailwind, TanStack Query, Recharts)

- Login, sessão persistente, layout responsivo com menu lateral e controle por papel.
- Visão geral, importações, clientes, leads, renovações, planos, base de conhecimento, assistente, agentes, integrações, auditoria e configurações.
- Estados de carregamento, erro e vazio padronizados; acessibilidade básica e navegação mobile.

## Validação executada nesta sessão (09/10/2026)

| Verificação | Resultado |
| --- | --- |
| `pytest` (SQLite) | 228 testes passaram |
| `ruff check` + `ruff format --check` | passou (113 arquivos) |
| `mypy` (strict) | passou (101 arquivos) |
| `npm run lint` | passou |
| `npm run typecheck` | passou |
| `npm run test:run` | 10 testes passaram |
| `npm run build` | passou (764 kB JS, 22 kB CSS) |
| `docker compose ps` | 3 serviços `healthy` |
| `scripts/smoke_test.py` | 9 verificações passaram |
| `npx playwright test` | 5 testes E2E passaram no Chromium |
| `/health`, `/docs`, `/redoc`, frontend | HTTP 200; `llm_provider: mock` |
| `git push origin main` | publicado com sucesso |

Validação anterior em PostgreSQL dedicado: 228 testes passaram com a migration `0002_delivery_fixes` aplicada.

## Próximos passos opcionais

1. Revalidar o backend em PostgreSQL dedicado:

```powershell
$env:OPSPILOT_TEST_DATABASE_URL = 'postgresql+asyncpg://opspilot:opspilot_local_dev_only@localhost:5432/opspilot_test'
cd backend
.\.venv\Scripts\python -m pytest
```

2. Subir o ambiente completo:

```powershell
docker compose up --build -d --wait --wait-timeout 240
docker compose ps
```

3. Smoke test: `.\backend\.venv\Scripts\python scripts\smoke_test.py`
4. E2E: `cd frontend; npm run test:e2e`
5. Capturas de tela para o portfólio: o E2E gera `frontend/test-results/dashboard-desktop.png` e `imports-mobile.png`. Decidir se entram no repositório (hoje estão ignoradas pelo `.gitignore`).
6. Itens do roadmap do README (fila Redis, alertas por e-mail, Google Sheets, WhatsApp/Telegram, CRM, pagamentos, Power BI, embeddings/pgvector, OCR, RLS multi-tenant, deploy em nuvem) — nenhum iniciado, todos documentados como evolução.
7. Se aparecer falha futura, corrigir sem apagar testes nem reduzir cobertura.

## Cuidados

- Não usar dados reais; não adicionar chaves de API; não trocar o provider padrão `mock`.
- Não usar `docker compose down -v` sem necessidade: apaga o banco local de demonstração.
- Manter a interface polida e o README comercialmente claro — é um produto de portfólio.
- Não afirmar que o mock é uma IA real nem que o sistema está em produção.
- Antes de qualquer novo push, conferir `git status` e `git diff` e garantir que não há `.env`, tokens, bancos locais ou artefatos gerados.

---

Depois de ler este handoff, comece por `git status`, confira se os containers estão ativos e rode os testes. Continue do estado atual.
