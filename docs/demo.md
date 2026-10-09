# Roteiro de demonstração
Duração sugerida: 3 a 5 minutos.

1. Contexto: “A empresa recebe planilhas diferentes, perde tempo conciliando dados e não sabe quais clientes priorizar.”
2. Mostre o painel e explique que os números são calculados no banco.
3. Importe customers.csv, revise mapeamento, mostre erros/duplicidades e confirme.
4. Abra um lead, explique o score por critérios e gere uma sugestão de contato.
5. Pergunte pelo valor em risco e mostre as fontes da resposta.
6. Mostre um documento pesquisável e o registro da execução de um agente.
7. Termine pela auditoria e pelo código/testes no repositório.

## Texto de portfólio
OpsPilot — sistema web demonstrativo com FastAPI, PostgreSQL, React e TypeScript para organizar dados comerciais, automatizar importações de planilhas e apoiar decisões com IA. Inclui validação por linha, dashboard, clientes, leads, renovações, busca documental com fontes, agentes com ferramentas limitadas e webhooks para n8n. Ambiente reproduzível via Docker, testes automatizados e dados sintéticos.

Não apresentar o mock como um modelo de IA real nem afirmar uso em produção por empresas.
Para capturas, rode o E2E: test-results/dashboard-desktop.png e imports-mobile.png. As capturas refletem o banco de demonstração do momento.

## Textos prontos para publicação

### Descrição curta do repositório no GitHub (até 350 caracteres)

> Hub de operações, dados e IA para pequenas empresas: importa planilhas CSV/XLSX com mapeamento e validação linha a linha, organiza clientes, leads e renovações, e responde perguntas sobre os próprios dados citando as fontes. FastAPI + PostgreSQL + React, Docker, testes automatizados e dados sintéticos.

Tópicos sugeridos: `fastapi`, `python`, `react`, `typescript`, `postgresql`, `sqlalchemy`, `docker`, `tailwindcss`, `data-pipeline`, `rag`, `n8n`, `portfolio`.

### Perfil de freelancer (99Freelas e Workana)

> **Automação de dados e aplicações com IA para pequenas empresas**
>
> Desenvolvo sistemas que tiram a operação da planilha: ingestão de arquivos com validação linha a linha, painel de indicadores calculados no banco e consultas em linguagem natural sobre os próprios dados, sempre com as fontes à vista.
>
> Exemplo público: o OpsPilot (<https://github.com/danilogep/OpsPilot>) sobe com um comando (`docker compose up --build`) e demonstra o fluxo completo — upload de CSV/XLSX, mapeamento automático de colunas, relatório de erros e duplicidades, confirmação transacional, dashboard, score de leads explicável, base de conhecimento pesquisável e integração por webhook com n8n.
>
> Stack: Python 3.12, FastAPI, SQLAlchemy assíncrono, PostgreSQL 16, Alembic, React, TypeScript, Vite, Tailwind, Docker e GitHub Actions. Cobertura por testes automatizados de backend, frontend e ponta a ponta.

### Proposta para um projeto específico (modelo)

> Pelo que entendi, hoje a informação está dividida entre planilhas e cada fechamento exige conciliação manual. Proponho começar pelo que dá resultado mais rápido:
>
> 1. **Semana 1** — ingestão: envio dos seus arquivos atuais, mapeamento das colunas e relatório de inconsistências (campos vazios, datas inválidas, duplicidades). Você passa a saber o tamanho real do problema.
> 2. **Semana 2** — base organizada: clientes, planos e renovações com histórico de alterações e exportação.
> 3. **Semana 3** — indicadores: receita mensal, vencimentos de 7 e 30 dias, valor em risco e clientes sem contato recente.
> 4. **Semana 4** — consulta assistida: perguntas sobre os seus dados com as fontes de cada número, e automações opcionais por webhook.
>
> Tenho um sistema de referência público que já faz esse fluxo de ponta a ponta (OpsPilot, link acima), então a conversa começa com algo funcionando na sua frente, não com slides.

### Observações de honestidade (manter em qualquer publicação)

- O provider de IA padrão é um mock determinístico e local; não é um modelo de linguagem externo.
- Os dados de demonstração são sintéticos; nenhuma operação de cliente real.
- O projeto é demonstrativo: não foi auditado para uso público multiempresa.
