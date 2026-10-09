# Handoff — continuar o OpsPilot no Claude Code

Cole a mensagem abaixo na aba Code do Claude, dentro da pasta deste repositório.

---

Você está continuando um projeto existente. Leia primeiro `CLAUDE.md`, `README.md`, `docs/validation.md` se existir, `docker-compose.yml` e o estado do Git. Não reescreva funcionalidades que já estão implementadas. Inspecione o código atual antes de editar.

## Objetivo

Concluir, validar e preparar para publicação o OpsPilot — Hub de Operações, Dados e IA. O projeto usa somente dados sintéticos e deve funcionar sem chave de IA usando `LLM_PROVIDER=mock`.

## O que já foi implementado

### Backend

- FastAPI modular por domínio.
- PostgreSQL 16 com SQLAlchemy assíncrono e Alembic.
- SQLite temporário para testes.
- JWT, Argon2, papéis ADMIN/ANALYST/VIEWER e isolamento por organização.
- Clientes, planos, leads, renovações e histórico.
- Importação CSV/XLSX/XLS com mapeamento, normalização, validação, duplicidades, preview, commit e relatório.
- Dashboard com métricas calculadas no banco.
- Assistente de IA com provider mock, Anthropic, OpenAI e Gemini.
- Respostas fundamentadas com fontes.
- Base de conhecimento para TXT, Markdown, PDF, DOCX, CSV e XLSX.
- Busca PostgreSQL Full Text Search em português e fallback lexical para SQLite.
- Score determinístico de leads e classificação opcional por IA.
- Agentes com ferramentas allowlisted, limite de passos e rastreamento.
- Webhooks HMAC com idempotência e fluxo n8n de exemplo.
- Auditoria e histórico de uso da IA.
- Healthcheck completo e liveness.
- Exportação CSV.

### Frontend

- React 18, TypeScript, Vite, Tailwind, TanStack Query e Recharts.
- Login e sessão persistente.
- Layout responsivo com menu lateral e controle por papel.
- Visão geral com cards, gráfico de evolução, ranking de origens e tabelas críticas.
- Importações com upload, mapeamento, validação, commit e relatório.
- Clientes, detalhe do cliente, edição, contato, histórico e exportação.
- Leads, score, classificação por IA, sugestão de mensagem, notas e histórico.
- Renovações, filtros, resumo executivo e atualização de status.
- Planos.
- Base de conhecimento e busca.
- Assistente com fontes, fatos e histórico de uso.
- Agentes com execução e rastro de ferramentas.
- Integrações com histórico de webhooks.
- Auditoria.
- Configurações, papéis e usuários.
- Estados de loading, erro, vazio, acessibilidade básica e navegação mobile.

### Qualidade e operação

- 228 testes backend passaram em SQLite após as correções de entrega.
- 3 regressões encontradas ao executar PostgreSQL foram corrigidas:
  1. busca FTS usava AND literal e não encontrava perguntas naturais;
  2. `score_version` tinha VARCHAR(20), insuficiente para `rules-v1+lead-classifier-v1`;
  3. migrations não refletiam a largura nova.
- Foi criada a migration `backend/alembic/versions/0002_delivery_fixes.py`.
- Foram adicionados testes de regressão em `backend/tests/test_delivery.py`.
- Foram adicionados testes de componentes/HTTP em `frontend/tests/ui.test.tsx`.
- Foi criado fluxo E2E em `frontend/tests/e2e/operations.spec.ts`.
- Foi criado `scripts/smoke_test.py`.
- Foi criado `.github/workflows/ci.yml`.
- Foi criada documentação em `README.md` e `docs/`.
- Dockerfile do backend e healthchecks foram ajustados.
- O indicador visual de campo obrigatório foi marcado como decorativo para preservar o nome acessível do campo.

## Validações já realizadas

- `backend`: Ruff passou.
- `backend`: MyPy passou.
- `backend`: 228 testes passaram em SQLite.
- PostgreSQL dedicado: 228 testes passaram com a migration `0002_delivery_fixes` aplicada.
- `frontend`: ESLint passou.
- `frontend`: TypeScript passou.
- `frontend`: build de produção passou.
- `frontend`: 10 testes de interface/HTTP passaram.
- `docker compose up --build -d --wait --wait-timeout 240` passou; banco, backend e frontend ficaram saudáveis.
- Smoke test passou com 9 verificações.
- Playwright passou com 5 testes E2E no Chromium.
- O healthcheck do frontend usa `127.0.0.1` para funcionar corretamente no container Nginx.
- O E2E de upload localiza o input de arquivo diretamente e tolera documentos duplicados no banco de demonstração.
- `react-router-dom` foi atualizado para `7.18.4`; `npm audit --omit=dev --audit-level=high` retorna zero vulnerabilidades.

## Próximos passos opcionais

1. Para repetir a validação completa do backend em PostgreSQL dedicado, execute:

```powershell
$env:OPSPILOT_TEST_DATABASE_URL = 'postgresql+asyncpg://opspilot:opspilot_local_dev_only@localhost:5432/opspilot_test'
cd backend
.\.venv\Scripts\python -m pytest
```

2. Para subir o ambiente completo em outra sessão:

```powershell
cd ..
docker compose up --build -d --wait --wait-timeout 240
docker compose ps
```

3. Rodar o smoke test:

```powershell
.\backend\.venv\Scripts\python scripts\smoke_test.py
```

4. Rodar o E2E:

```powershell
cd frontend
npm run test:e2e
```

5. Se aparecer alguma falha futura, corrigir sem apagar os testes nem reduzir cobertura.
6. Antes de publicar, conferir `git diff`, `git status` e se não há `.env`, tokens, bancos locais, screenshots ou arquivos gerados no commit.
7. Ao publicar, preparar uma mensagem final curta com:
   - arquivos principais alterados;
   - comandos executados;
   - resultados dos testes;
   - limitações conhecidas;
   - instrução de execução para o GitHub.

## Cuidados

- Não usar dados reais.
- Não adicionar chaves de API.
- Não trocar o provider padrão `mock`.
- Não usar `docker compose down -v` sem necessidade, pois isso apaga o banco local de demonstração.
- O usuário quer um produto de portfólio demonstrável; mantenha a interface polida e o README comercialmente claro.
- Não afirmar que o mock é uma IA real nem que o sistema está em produção.

---

Depois de ler este handoff, comece verificando `git status`, os processos ativos e o resultado dos testes. Continue do estado atual.
