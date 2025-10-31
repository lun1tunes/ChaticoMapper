"""Rename owner_id columns to account_id in worker_apps and webhook_logs."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "74f3d9f8d975"
down_revision = "5f4ce0a2ec9d"
branch_labels = None
depends_on = None


def _rename_index(old_name: str, new_name: str, table: str) -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_indexes = {idx["name"] for idx in inspector.get_indexes(table)}
    if old_name in existing_indexes:
        op.execute(sa.text(f'ALTER INDEX "{old_name}" RENAME TO "{new_name}"'))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "worker_apps" in tables:
        columns = {col["name"] for col in inspector.get_columns("worker_apps")}
        if "owner_id" in columns:
            op.alter_column("worker_apps", "owner_id", new_column_name="account_id")
        _rename_index("ix_worker_apps_owner_id", "ix_worker_apps_account_id", "worker_apps")

    if "webhook_logs" in tables:
        columns = {col["name"] for col in inspector.get_columns("webhook_logs")}
        if "owner_id" in columns:
            op.alter_column("webhook_logs", "owner_id", new_column_name="account_id")
        _rename_index("ix_webhook_logs_owner_id", "ix_webhook_logs_account_id", "webhook_logs")
        _rename_index("idx_webhook_logs_owner_status", "idx_webhook_logs_account_status", "webhook_logs")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "worker_apps" in tables:
        columns = {col["name"] for col in inspector.get_columns("worker_apps")}
        if "account_id" in columns:
            op.alter_column("worker_apps", "account_id", new_column_name="owner_id")
        _rename_index("ix_worker_apps_account_id", "ix_worker_apps_owner_id", "worker_apps")

    if "webhook_logs" in tables:
        columns = {col["name"] for col in inspector.get_columns("webhook_logs")}
        if "account_id" in columns:
            op.alter_column("webhook_logs", "account_id", new_column_name="owner_id")
        _rename_index("ix_webhook_logs_account_id", "ix_webhook_logs_owner_id", "webhook_logs")
        _rename_index("idx_webhook_logs_account_status", "idx_webhook_logs_owner_status", "webhook_logs")
