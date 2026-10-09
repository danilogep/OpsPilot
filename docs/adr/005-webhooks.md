# ADR 005 — Webhooks
Assinatura HMAC-SHA256 sobre corpo bruto e chave de idempotência. Eventos registram status/tentativas. Destino de saída é configurado no servidor; sem destino o evento é marcado como não enviado. O n8n é opcional ao funcionamento do produto.
