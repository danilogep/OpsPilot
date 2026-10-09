# OpsPilot — Backend

API FastAPI do OpsPilot. A documentação completa do projeto está na
[raiz do repositório](../README.md).

## Comandos rápidos

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"        # Windows
# source .venv/bin/activate && pip install -e ".[dev]"   # Linux/macOS

alembic upgrade head          # migrations
python scripts_seed.py        # seed idempotente de demonstração
uvicorn app.main:app --reload # servidor em http://localhost:8000

pytest -q                     # testes
ruff check . && ruff format --check .
mypy
```

A URL do banco vem de `OPSPILOT_DATABASE_URL`. Sem PostgreSQL disponível, use
`sqlite+aiosqlite:///./var/dev.db`.
