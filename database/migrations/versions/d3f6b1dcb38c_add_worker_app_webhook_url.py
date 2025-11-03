"""Add webhook_url column to worker_apps."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "d3f6b1dcb38c"
down_revision = "9d9a5ac4613c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "worker_apps",
        sa.Column(
            "webhook_url",
            sa.String(length=500),
            nullable=True,
            comment="Webhook endpoint URL for forwarding",
        ),
    )

    # Backfill existing records to preserve behaviour
    op.execute("UPDATE worker_apps SET webhook_url = base_url WHERE webhook_url IS NULL")

    op.alter_column(
        "worker_apps",
        "webhook_url",
        existing_type=sa.String(length=500),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column("worker_apps", "webhook_url")
