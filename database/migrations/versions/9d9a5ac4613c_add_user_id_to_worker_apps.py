"""Add user_id foreign key to worker_apps and backfill data."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "9d9a5ac4613c"
down_revision = "8f0d1a7c5b6e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "worker_apps",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Associated application user",
        ),
    )
    op.create_index("ix_worker_apps_user_id", "worker_apps", ["user_id"], unique=False)
    op.create_foreign_key(
        "fk_worker_apps_user_id",
        "worker_apps",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    worker_apps = sa.table(
        "worker_apps",
        sa.column("account_id", sa.String(length=255)),
        sa.column("user_id", postgresql.UUID(as_uuid=True)),
    )
    users = sa.table(
        "users",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("email", sa.String(length=255)),
    )

    update_stmt = (
        worker_apps.update()
        .values(
            user_id=sa.select(users.c.id)
            .where(users.c.email == worker_apps.c.account_id)
            .scalar_subquery()
        )
        .where(sa.exists(sa.select(1).where(users.c.email == worker_apps.c.account_id)))
    )

    op.execute(update_stmt)


def downgrade() -> None:
    op.drop_constraint("fk_worker_apps_user_id", "worker_apps", type_="foreignkey")
    op.drop_index("ix_worker_apps_user_id", table_name="worker_apps")
    op.drop_column("worker_apps", "user_id")
