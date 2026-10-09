# API
Contrato completo e exemplos de entrada/saída em http://localhost:8000/docs. Prefixo: /api/v1.

Autenticação: POST /auth/login com email/password. Envie o access_token no cabeçalho Authorization: Bearer TOKEN.
GET /auth/me e /auth/me/organization retornam a sessão. ADMIN gerencia /auth/users.

| Recurso | Rotas principais |
| --- | --- |
| Dashboard | GET /dashboard/overview, /dashboard/timeline, /dashboard/ai-usage |
| Clientes | GET/POST /customers; GET/PATCH/DELETE /customers/{id}; POST /customers/{id}/contact |
| Leads | GET/POST /leads; GET/PATCH/DELETE /leads/{id}; POST /leads/{id}/notes e /score |
| Planos | GET/POST /plans; GET/PATCH/DELETE /plans/{id} |
| Renovações | GET/POST /renewals; GET/PATCH /renewals/{id}; GET /renewals/critical |
| Importações | POST /imports (multipart file); PUT /imports/{id}/mapping; POST /validate e /commit |
| Relatórios | GET /imports/{id}/preview, /errors e /report |
| Conhecimento | GET/POST /knowledge/documents; GET /knowledge/search?q=... |
| Assistente | GET /assistant/config; POST /assistant/ask; GET /assistant/usage |
| Agentes | GET /agents; POST /agents/{key}/run; GET /agents/runs |
| Integrações | GET /integrations/status e /webhooks/events; POST /webhooks/leads e /webhooks/renewals |
| Auditoria | GET /audit/events e /audit/actions |

Listagens paginadas usam page/page_size e retornam items, total, page, page_size, pages.
Erros retornam error.code, error.message, error.details e correlation_id quando disponível.
Exportação CSV: /customers/export, /leads/export, /renewals/export.
Webhooks possuem autenticação própria HMAC; consultar integrations/n8n/README.md.
