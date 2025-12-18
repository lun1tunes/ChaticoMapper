"""Split OAuth token expiry fields into access/refresh.

Revision ID: 6d1c4b0a2f3e
Revises: f1a7f0b1c9d7
Create Date: 2025-12-16 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "6d1c4b0a2f3e"
down_revision = "f1a7f0b1c9d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("oauth_tokens") as batch_op:
        batch_op.alter_column(
            "expires_at",
            new_column_name="access_token_expires_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=True,
        )
        batch_op.add_column(
            sa.Column(
                "refresh_token_expires_at",
                sa.DateTime(timezone=True),
                nullable=True,
                comment="Refresh token expiry time (if provided by Google)",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("oauth_tokens") as batch_op:
        batch_op.drop_column("refresh_token_expires_at")
        batch_op.alter_column(
            "access_token_expires_at",
            new_column_name="expires_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=True,
        )

