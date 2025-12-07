"""Make oauth_tokens.user_id non-nullable and enforce uniqueness.

Revision ID: f1a7f0b1c9d7
Revises: e8e8e8merge
Create Date: 2025-02-05 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "f1a7f0b1c9d7"
down_revision = "e8e8e8merge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop existing unique constraint to update column
    with op.batch_alter_table("oauth_tokens") as batch_op:
        batch_op.drop_constraint("uq_oauth_provider_account_user", type_="unique")

    # Clean up any null user_id rows (legacy)
    op.execute("DELETE FROM oauth_tokens WHERE user_id IS NULL")

    # Alter column to be non-nullable
    with op.batch_alter_table("oauth_tokens") as batch_op:
        batch_op.alter_column(
            "user_id",
            existing_type=postgresql.UUID(as_uuid=True),
            nullable=False,
        )
        batch_op.create_unique_constraint(
            "uq_oauth_provider_account_user",
            ["provider", "account_id", "user_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("oauth_tokens") as batch_op:
        batch_op.drop_constraint("uq_oauth_provider_account_user", type_="unique")
        batch_op.alter_column(
            "user_id",
            existing_type=postgresql.UUID(as_uuid=True),
            nullable=True,
        )
        batch_op.create_unique_constraint(
            "uq_oauth_provider_account_user",
            ["provider", "account_id", "user_id"],
        )
