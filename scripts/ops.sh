#!/usr/bin/env bash
# Atalhos de operação do OpsPilot para Linux/macOS/WSL/Git Bash.
# Uso: ./scripts/ops.sh <comando>   (os mesmos nomes do Makefile)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if command -v make >/dev/null 2>&1; then
  exec make "$@"
fi

echo "make não encontrado; executando o comando equivalente diretamente." >&2
case "${1:-help}" in
  up)            docker compose up --build -d ;;
  up-automation) docker compose --profile automation up --build -d ;;
  down)          docker compose down --remove-orphans ;;
  logs)          docker compose logs -f --tail=100 ;;
  migrate)       docker compose exec backend alembic upgrade head ;;
  seed)          docker compose exec backend python scripts_seed.py ;;
  samples)       python scripts/generate_sample_data.py ;;
  test-backend)  (cd backend && python -m pytest -q) ;;
  test-frontend) (cd frontend && npm run test -- --run) ;;
  health)        curl -fsS http://localhost:8000/health && echo "" ;;
  smoke)         python scripts/smoke_test.py ;;
  *)             echo "Comandos: up, up-automation, down, logs, migrate, seed, samples, test-backend, test-frontend, health, smoke" ;;
esac
