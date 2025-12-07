"""Merge oauth_tokens and worker_app branches.

Revision ID: e8e8e8merge
Revises: c2b0c6c5e7c1, 5c9f79b953a1
Create Date: 2025-02-05 00:00:00.000000
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "e8e8e8merge"
down_revision = ("c2b0c6c5e7c1", "5c9f79b953a1")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No-op merge migration to combine branches.
    pass


def downgrade() -> None:
    # No-op merge migration.
    pass
