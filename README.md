# OpsPilot — operações, dados e IA

Uma aplicação demonstrável para transformar planilhas em uma carteira organizada de clientes, oportunidades comerciais e renovações. O assistente consulta indicadores e documentos, mostrando as fontes usadas na resposta.

**Projeto de portfólio de Danilo Evangelista. Dados sintéticos; nenhuma operação de cliente real.**

## Executar com Docker

Requisitos: Docker Desktop em execução com containers Linux. Na raiz:

```powershell
docker compose up --build -d
docker compose ps
```

- Aplicação: http://localhost:5173
- API / documentação interativa: http://localhost:8000/docs
- Saúde do serviço: http://localhost:8000/health

O primeiro início aplica migrations e cria a organização de demonstração. Os volumes preservam banco e uploads. Não precisa de chave de IA.

| Conta local | Papel |
| --- | --- |
| admin@opspilot.local | Administrador |
| analyst@opspilot.local | Analista |
| viewer@opspilot.local | Visualizador |

Senha local padrão: **OpsPilot!2026**. Alterável em `OPSPILOT_DEMO_PASSWORD` antes do primeiro seed; o seed idempotente não redefine senhas existentes.

Se a porta estiver ocupada, personalize `BACKEND_PORT`, `FRONTEND_PORT`, `POSTGRES_PORT` e os respectivos `VITE_API_BASE_URL` e `OPSPILOT_CORS_ORIGINS` em um arquivo `.env`, usando `.env.example` como referência. Mudanças em VITE_API_BASE_URL exigem novo build.

## O que demonstrar

1. Faça login e confira os indicadores calculados pelo banco.
2. Em Importações, envie `data/samples/customers.csv` ou `customers.xlsx`.
3. Revise o mapeamento, valide, veja as linhas rejeitadas e confirme.
4. Consulte clientes e registre um contato.
5. Cadastre um lead, confira os critérios do score e solicite uma classificação.
6. Gere um rascunho de mensagem — o sistema não envia mensagens externas.
7. Consulte renovações e gere um resumo executivo.
8. Envie um documento e pesquise seus trechos na Base de conhecimento.
9. Pergunte ao assistente: “Quantos clientes temos?” ou “Qual é o valor em risco?”.
10. Consulte o histórico de agentes, uso de IA, integrações e auditoria.

## Funcionalidades

- Login JWT e papéis ADMIN, ANALYST e VIEWER; dados filtrados por organização.
- CSV/XLSX/XLS com detecção de colunas, revisão, normalização, deduplicação e relatório.
- Cadastro/edição de clientes, leads e planos; registro de contatos e notas.
- Renovações, exportações CSV e indicadores financeiros estimados.
- Dashboard responsivo, listagens paginadas, filtros e estados de erro/vazio.
- Assistente com fatos e fontes; busca textual PostgreSQL em documentos.
- Agentes com ferramentas permitidas, limite de etapas e rastreamento.
- Webhooks assinados com HMAC e chaves de idempotência; exemplo n8n.
- Gestão de usuários e auditoria pela interface.
- Tests unitários/API, testes de componentes e fluxos completos no navegador.

## Stack e organização

Backend: Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, Pandas, Pydantic.
Frontend: React 18, TypeScript, Vite, Tailwind, TanStack Query, Recharts.
Qualidade: Pytest, Ruff, MyPy, Vitest, Playwright e GitHub Actions.

```text
backend/           API, regras de negócio, migrations e testes
frontend/          aplicação React, componentes e testes de navegador
data/samples/      arquivos sintéticos para demonstrar importações
integrations/n8n/  workflow e contratos de eventos
scripts/           comandos PowerShell/Bash e smoke test
docs/              arquitetura, decisões e roteiro de demonstração
```

## Desenvolvimento local sem Docker

Windows PowerShell, dois terminais. Primeiro:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
$env:OPSPILOT_DATABASE_URL = 'sqlite+aiosqlite:///./opspilot.db'
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python scripts_seed.py
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

Segundo:

```powershell
cd frontend
npm ci
npm run dev
```

No Linux use `python3.12`, `.venv/bin/python` e `export OPSPILOT_DATABASE_URL=sqlite+aiosqlite:///./opspilot.db`.
SQLite é uma opção local; a implantação Docker usa PostgreSQL.

## Qualidade

```powershell
cd backend
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m mypy app
cd ../frontend
npm run lint
npm run typecheck
npm run test:run
npm run build
npx playwright install chromium
npm run test:e2e
```

E2E requer aplicação + API com seed e provider mock; cria registros sintéticos no banco local. Não executar contra produção. Pode apontar outro ambiente com `E2E_BASE_URL`, `E2E_API_URL`, `E2E_PASSWORD`.
Os testes de backend usam SQLite temporário por padrão. `OPSPILOT_TEST_DATABASE_URL` permite PostgreSQL **dedicado e descartável** (os testes limpam todas as tabelas).

Na raiz: `backend/.venv/Scripts/python scripts/smoke_test.py` valida login, dashboard e busca no ambiente em execução.

## IA real e automações

Padrão: `OPSPILOT_LLM_PROVIDER=mock`. O mock é determinístico e não equivale a um LLM externo.
Para um provider real, configure `OPSPILOT_LLM_PROVIDER` (anthropic, openai ou gemini), `OPSPILOT_LLM_MODEL` e a respectiva chave em `.env`, depois recrie o backend.
Os adapters existem; uso real exige credenciais, modelo disponível e validação com o provider. Custos exibidos são estimativas, não faturamento oficial.

n8n é opcional: `docker compose --profile automation up -d`. Consulte [integrações](integrations/n8n/README.md). Sem destino configurado, eventos de saída aparecem como “Não enviado”.

## Documentação e limites

- [Arquitetura](docs/architecture.md)
- [API](docs/api.md)
- [Dicionário](docs/data-dictionary.md)
- [Segurança e limites](docs/security.md)
- [Demonstração e apresentação comercial](docs/demo.md)
- [Validação desta entrega](docs/validation.md)

Processamento síncrono de arquivos pequenos; sem fila distribuída, OCR, WhatsApp, cobrança ou disparo comercial. O gráfico mostra novos contratos por mês de início, não histórico contábil. Multi-organização exige revisão adicional antes de um SaaS público.
Próximas evoluções: fila de processamento, limites de consumo por organização, PostgreSQL RLS, embeddings opcionais, integrações CRM/Sheets e deploy com TLS.
