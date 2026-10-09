# ADR 002 — Providers intercambiáveis
Interface comum para mock, Anthropic, OpenAI e Gemini. Mock obrigatório para execução sem credenciais e testes determinísticos. Providers reais dependem de disponibilidade, modelo configurado e teste externo; nenhum segredo é versionado.
