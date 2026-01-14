"""Add oauth_tokens.username and drop worker_apps account fields.

Revision ID: b7c8d9e0f1a2
Revises: a4b1c2d3e4f5
Create Date: 2025-02-07 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "b7c8d9e0f1a2"
down_revision = "a4b1c2d3e4f5"
branch_labels = None
depends_on = None


def _index_exists(table: str, name: str) -> bool:
    inspector = inspect(op.get_bind())
    indexes = inspector.get_indexes(table)
    return any(idx.get("name") == name for idx in indexes)


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    tables = inspector.get_table_names()

    if "oauth_tokens" in tables:
        columns = {col["name"] for col in inspector.get_columns("oauth_tokens")}
        if "username" not in columns:
            op.add_column(
                "oauth_tokens",
                sa.Column(
                    "username",
                    sa.String(length=255),
                    nullable=True,
                    comment="External account username (e.g., Instagram username)",
                ),
            )

    if "worker_apps" in tables:
        columns = {col["name"] for col in inspector.get_columns("worker_apps")}
        if "account_id" in columns:
            if _index_exists("worker_apps", "ix_worker_apps_account_id"):
                op.drop_index("ix_worker_apps_account_id", table_name="worker_apps")
            op.drop_column("worker_apps", "account_id")
        if "owner_instagram_username" in columns:
            op.drop_column("worker_apps", "owner_instagram_username")


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    tables = inspector.get_table_names()

    if "worker_apps" in tables:
        columns = {col["name"] for col in inspector.get_columns("worker_apps")}
        if "account_id" not in columns:
            op.add_column(
                "worker_apps",
                sa.Column(
                    "account_id",
                    sa.String(length=255),
                    nullable=True,
                    comment="Instagram account ID of the business owner",
                ),
            )
            op.create_index(
                "ix_worker_apps_account_id", "worker_apps", ["account_id"], unique=True
            )
        if "owner_instagram_username" not in columns:
            op.add_column(
                "worker_apps",
                sa.Column(
                    "owner_instagram_username",
                    sa.String(length=255),
                    nullable=True,
                    comment="Instagram username of the account owner",
                ),
            )

    if "oauth_tokens" in tables:
        columns = {col["name"] for col in inspector.get_columns("oauth_tokens")}
        if "username" in columns:
            op.drop_column("oauth_tokens", "username")
