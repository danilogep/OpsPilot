# Validação da entrega

Este arquivo deve ser atualizado sempre que o projeto for validado em um ambiente limpo.

## Última validação local — 09/10/2026

- Backend SQLite: 228 testes passaram.
- Backend PostgreSQL dedicado: 228 testes passaram com a migration `0002_delivery_fixes` aplicada.
- Ruff: passou.
- MyPy: passou.
- Frontend ESLint: passou.
- Frontend TypeScript: passou.
- Frontend build de produção: passou.
- Frontend Vitest: 10 testes passaram.
- `npm audit --omit=dev --audit-level=high`: nenhuma vulnerabilidade encontrada.
- Docker Compose: banco, backend e frontend subiram saudáveis; as duas imagens foram construídas.
- Smoke test: 9 verificações passaram, incluindo dashboard, CRUDs, busca, integrações, auditoria e assistente com fontes.
- Playwright: 5 testes E2E passaram no Chromium.

## Comandos finais

```powershell
docker compose up --build -d --wait --wait-timeout 240
docker compose ps
.\backend\.venv\Scripts\python scripts\smoke_test.py
cd frontend
npm run test:e2e
```

O ambiente validado permanece disponível em `http://localhost:5173` e a API em `http://localhost:8000` enquanto os containers estiverem ativos.

## Revalidação — 09/10/2026 (sessão de publicação)

- Backend SQLite: 228 testes passaram.
- Ruff (`check` e `format --check`): passou em 113 arquivos.
- MyPy strict: passou em 101 arquivos.
- Frontend ESLint, TypeScript, Vitest (10 testes) e build de produção: passaram.
- Docker Compose: `db`, `backend` e `frontend` em `healthy`.
- Smoke test: 9 verificações passaram.
- Playwright: 5 testes E2E passaram no Chromium.
- `/health` retornou `status: ok`, `database: ok`, `llm_provider: mock`; `/docs`, `/redoc` e o frontend responderam 200.
- Projeto publicado em <https://github.com/danilogep/OpsPilot> (branch `main`), sem segredos nem artefatos no histórico.
