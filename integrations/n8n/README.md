# Integração OpsPilot ↔ n8n

Automação opcional. O OpsPilot funciona sem n8n; esta pasta contém o workflow de
exemplo, os payloads e o contrato dos webhooks.

> Todos os exemplos usam **dados sintéticos** e o segredo de demonstração
> `opspilot_webhook_demo_secret`. Em qualquer ambiente real, gere um segredo
> próprio e guarde-o apenas em variável de ambiente.

---

## 1. Subir o n8n (profile opcional do Docker Compose)

```bash
docker compose --profile automation up -d
```

- n8n: <http://localhost:5678> (usuário `opspilot`, senha definida em `.env`)
- Backend visto de dentro da rede do compose: `http://backend:8000`
- O diretório `integrations/n8n` é montado em `/workflows` (somente leitura)

Sem Docker, aponte `OPSPILOT_API_BASE_URL` para `http://localhost:8000`.

## 2. Importar o workflow

1. Abra o n8n → menu **⋯** → **Import from file**.
2. Selecione `opspilot-workflow.json` (ou `/workflows/opspilot-workflow.json`
   quando estiver dentro do container).
3. Confira as variáveis de ambiente usadas pelos nós:

| Variável | Para que serve |
| --- | --- |
| `OPSPILOT_API_BASE_URL` | Base da API (`http://backend:8000` no compose) |
| `OPSPILOT_WEBHOOK_SECRET` | Segredo do HMAC, igual ao do backend |
| `OPSPILOT_DEMO_PASSWORD` | Senha do usuário de demonstração usado no login |

4. Ative o workflow. Ele traz três fluxos independentes:

| Fluxo | Gatilho | O que faz |
| --- | --- | --- |
| Novo lead | `POST /webhook/opspilot-novo-lead` | assina o payload e chama `POST /api/v1/integrations/webhooks/leads` |
| Eventos do OpsPilot | `POST /webhook/opspilot-eventos` | recebe `import.completed` e `lead.classified` e roteia por tipo |
| Alerta de renovações | cron 9h em dias úteis | faz login, lê `/renewals/indicators` e alerta se houver vencimento em 7 dias |

## 3. Contrato dos webhooks de entrada (n8n → OpsPilot)

| Cabeçalho | Obrigatório | Descrição |
| --- | --- | --- |
| `X-OpsPilot-Signature` | sim | `sha256=<HMAC-SHA256 do corpo bruto>` |
| `X-OpsPilot-Idempotency-Key` | recomendado | identificador único do evento |
| `X-OpsPilot-Organization` | opcional | slug da organização (`acme-servicos`) |
| `X-OpsPilot-Event` | opcional | nome do evento, apenas informativo |

Endpoints:

| Evento | Método e rota |
| --- | --- |
| `lead.created` | `POST /api/v1/integrations/webhooks/leads` |
| `renewal.updated` | `POST /api/v1/integrations/webhooks/renewals` |

Regras aplicadas pelo backend:

- assinatura inválida ou ausente → **401** com `error.code = unauthenticated`;
- mesma chave de idempotência → **200** com `status = DUPLICATE` e `duplicate = true`,
  sem criar registro novo;
- todo evento recebido fica em `webhook_events` e aparece em
  **Integrações** e na **Auditoria**.

### Exemplo de envio (bash)

```bash
BODY='{"name":"Marcos Webhook","company":"Clínica Integrada","email":"marcos@clinicaintegrada.com.br","phone":"11987654321","source":"site","segment":"saúde","company_size":"SMALL","interest":"controlar renovações","estimated_value":"1800.00"}'
SECRET="opspilot_webhook_demo_secret"
SIG="sha256=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')"

curl -sS -X POST http://localhost:8000/api/v1/integrations/webhooks/leads \
  -H "Content-Type: application/json" \
  -H "X-OpsPilot-Signature: $SIG" \
  -H "X-OpsPilot-Idempotency-Key: lead-demo-001" \
  -H "X-OpsPilot-Organization: acme-servicos" \
  -d "$BODY"
```

### Exemplo de envio (PowerShell)

```powershell
$body   = '{"name":"Marcos Webhook","source":"site","email":"marcos@exemplo.com.br"}'
$secret = 'opspilot_webhook_demo_secret'
$hmac   = [System.Security.Cryptography.HMACSHA256]::new([Text.Encoding]::UTF8.GetBytes($secret))
$hash   = $hmac.ComputeHash([Text.Encoding]::UTF8.GetBytes($body))
$sig    = 'sha256=' + (($hash | ForEach-Object { $_.ToString('x2') }) -join '')

Invoke-RestMethod -Method Post -Uri 'http://localhost:8000/api/v1/integrations/webhooks/leads' `
  -ContentType 'application/json' `
  -Headers @{ 'X-OpsPilot-Signature' = $sig; 'X-OpsPilot-Idempotency-Key' = 'lead-demo-002' } `
  -Body $body
```

## 4. Webhooks de saída (OpsPilot → n8n)

Configure a URL do webhook do n8n no backend:

```env
OPSPILOT_WEBHOOK_OUTBOUND_URL=http://n8n:5678/webhook/opspilot-eventos
```

| Evento | Quando é disparado |
| --- | --- |
| `import.completed` | ao confirmar uma importação |
| `lead.classified` | ao classificar um lead com IA |
| `renewal.alert` | manualmente, em `POST /api/v1/integrations/webhooks/test` |

Envelope padrão:

```json
{
  "event": "import.completed",
  "organization_id": "0f3f...",
  "idempotency_key": "import-9c1e...",
  "correlation_id": "4f2b...",
  "sent_at": "2026-10-09T12:34:56.789012+00:00",
  "data": {
    "import_id": "9c1e...",
    "filename": "customers.csv",
    "created_customers": 97,
    "updated_customers": 3,
    "created_renewals": 88,
    "invalid_rows": 14,
    "duplicate_rows": 13
  }
}
```

O corpo é assinado com o mesmo cabeçalho `X-OpsPilot-Signature`, então o n8n pode
validar a origem. Sem URL configurada o evento é registrado com
`status = SKIPPED` — o histórico fica completo de qualquer forma.

## 5. Respostas da API

Sucesso:

```json
{
  "received": true,
  "event_id": "7a1c...",
  "status": "PROCESSED",
  "idempotency_key": "lead-demo-001",
  "message": "Lead criado com score 84 (HOT).",
  "entity_id": "3d9f...",
  "duplicate": false
}
```

Erro (formato padrão de toda a API):

```json
{
  "error": {
    "code": "unauthenticated",
    "message": "Assinatura do webhook inválida ou ausente.",
    "details": { "header": "X-OpsPilot-Signature" },
    "correlation_id": "4f2b..."
  }
}
```

## 6. Arquivos desta pasta

| Arquivo | Conteúdo |
| --- | --- |
| `opspilot-workflow.json` | workflow de exemplo com os três fluxos |
| `payload-lead.json` | payload de entrada de lead |
| `payload-renewal.json` | payload de entrada de renovação |
| `response-examples.json` | respostas de sucesso, duplicidade e erro |

## 7. Limitações

- O workflow usa nós `NoOp` nos pontos de notificação: troque por Slack, e-mail
  ou Telegram conforme a necessidade.
- O fluxo de alerta faz login com usuário de demonstração. Em produção, crie um
  usuário de serviço com perfil `ANALYST` e use as credenciais do n8n.
- O backend não expõe endpoint de registro automático de workflow no n8n: a
  importação é manual (uma vez).
