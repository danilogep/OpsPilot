# ADR 006 — Testes em banco descartável
SQLite temporário dá feedback local rápido. PostgreSQL dedicado é usado em CI para validar migrations, JSON e recuperação textual. O E2E valida o fluxo completo contra o ambiente Docker. Testes apagam suas tabelas: nunca indicar banco real na variável de teste.
