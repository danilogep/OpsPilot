"""Verifica o ambiente local com dados sintéticos, sem exibir tokens."""
from __future__ import annotations

import os

import httpx


def main() -> None:
    base = os.getenv("E2E_API_URL", "http://localhost:8000")
    with httpx.Client(base_url=base, timeout=30) as client:
        health = client.get("/health")
        health.raise_for_status()
        assert health.json()["database"] == "ok", health.text
        response = client.post("/api/v1/auth/login", json={"email": "admin@opspilot.local", "password": os.getenv("E2E_PASSWORD", "OpsPilot!2026")})
        response.raise_for_status()
        client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
        for path in ["/dashboard/overview", "/customers", "/leads", "/renewals", "/plans", "/knowledge/search?q=renovacao", "/integrations/status", "/audit/events"]:
            result = client.get(f"/api/v1{path}")
            result.raise_for_status()
            print(f"OK {path}")
        answer = client.post("/api/v1/assistant/ask", json={"question": "Quantos clientes temos?"})
        answer.raise_for_status()
        assert answer.json()["sources"], "Resposta sem fontes"
        print("OK assistente com fontes")


if __name__ == "__main__":
    main()
