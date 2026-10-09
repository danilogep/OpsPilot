"""Aumenta a coluna da versão do score de leads.

Revision ID: 0002_delivery_fixes
Revises: 0001_initial
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_delivery_fixes"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "leads",
        "score_version",
        existing_type=sa.String(length=20),
        type_=sa.String(length=64),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "leads",
        "score_version",
        existing_type=sa.String(length=64),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
