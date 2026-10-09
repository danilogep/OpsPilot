#!/usr/bin/env bash
# Entrypoint do backend: aguarda o banco, aplica migrations, opcionalmente roda o seed.
set -euo pipefail

COMMAND="${1:-serve}"

wait_for_database() {
  python - <<'PY'
import asyncio
import sys
import time

from sqlalchemy import text

from app.core.config import settings
from app.db.session import get_engine


async def ping() -> None:
    engine = get_engine()
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    await engine.dispose()


deadline = time.time() + 60
while True:
    try:
        asyncio.run(ping())
        print(f"banco disponivel ({'postgres' if settings.is_postgres else 'sqlite'})")
        break
    except Exception as exc:  # noqa: BLE001
        if time.time() > deadline:
            print(f"banco indisponivel: {type(exc).__name__}", file=sys.stderr)
            raise SystemExit(1) from exc
        print("aguardando banco...")
        time.sleep(2)
PY
}

case "$COMMAND" in
  serve)
    wait_for_database
    echo "aplicando migrations..."
    alembic upgrade head
    if [ "${OPSPILOT_RUN_SEED:-true}" = "true" ]; then
      echo "executando seed idempotente..."
      python scripts_seed.py
    fi
    echo "iniciando uvicorn..."
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
    ;;
  migrate)
    wait_for_database
    exec alembic upgrade head
    ;;
  seed)
    wait_for_database
    exec python scripts_seed.py "${@:2}"
    ;;
  shell)
    exec python
    ;;
  *)
    exec "$@"
    ;;
esac
