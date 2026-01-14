"""Merge oauth_tokens heads.

Revision ID: a4b1c2d3e4f5
Revises: 6d1c4b0a2f3e, f2a4c8e6b7d1
Create Date: 2025-02-07 00:00:00.000000
"""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "a4b1c2d3e4f5"
down_revision = ("6d1c4b0a2f3e", "f2a4c8e6b7d1")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No-op merge migration to join heads.
    pass


def downgrade() -> None:
    # No-op merge migration.
    pass
