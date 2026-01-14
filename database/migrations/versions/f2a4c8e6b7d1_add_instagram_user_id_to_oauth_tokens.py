"""Add instagram_user_id to oauth_tokens.

Revision ID: f2a4c8e6b7d1
Revises: f1a7f0b1c9d7
Create Date: 2025-02-07 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "f2a4c8e6b7d1"
down_revision = "f1a7f0b1c9d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "oauth_tokens",
        sa.Column(
            "instagram_user_id",
            sa.String(length=255),
            nullable=True,
            comment="Instagram user id from OAuth (app-scoped)",
        ),
    )


def downgrade() -> None:
    op.drop_column("oauth_tokens", "instagram_user_id")
