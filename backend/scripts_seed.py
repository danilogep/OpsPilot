"""CLI do seed de demonstração.

Uso:

    python scripts_seed.py            # cria o que falta (idempotente)
    python scripts_seed.py --reset    # apaga os dados da organização demo antes

Requer ``OPSPILOT_DATABASE_URL`` apontando para um banco já migrado.
"""

from __future__ import annotations

import argparse
import asyncio
import json

from sqlalchemy import delete, select

from app.db.models import (
    AgentDefinition,
    AgentRun,
    AuditEvent,
    Customer,
    DocumentChunk,
    ImportJob,
    KnowledgeDocument,
    Lead,
    LeadEvent,
    LLMUsage,
    Organization,
    Plan,
    RawImportRow,
    Renewal,
    WebhookEvent,
)
from app.db.seed import DEMO_ORG_SLUG, run_seed
from app.db.session import dispose_engine, get_sessionmaker


async def _reset(organization_slug: str) -> None:
    """Remove os dados transacionais da organização de demonstração."""
    factory = get_sessionmaker()
    async with factory() as session:
        org_id = (
            await session.execute(
                select(Organization.id).where(Organization.slug == organization_slug)
            )
        ).scalar_one_or_none()
        if org_id is None:
            return
        for model in (
            LeadEvent,
            Lead,
            Renewal,
            Customer,
            Plan,
            DocumentChunk,
            KnowledgeDocument,
            RawImportRow,
            ImportJob,
            LLMUsage,
            AgentRun,
            AgentDefinition,
            WebhookEvent,
            AuditEvent,
        ):
            await session.execute(delete(model).where(model.organization_id == org_id))
        await session.commit()


async def _main(reset: bool) -> None:
    if reset:
        await _reset(DEMO_ORG_SLUG)
    factory = get_sessionmaker()
    async with factory() as session:
        report = await run_seed(session)
    print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
    await dispose_engine()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed de demonstração do OpsPilot")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="apaga os dados da organização de demonstração antes de semear",
    )
    args = parser.parse_args()
    asyncio.run(_main(args.reset))
