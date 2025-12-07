"""Add user_id to oauth_tokens and scope uniqueness per user.

Revision ID: c2b0c6c5e7c1
Revises: 9d9a5ac4613c
Create Date: 2025-02-05 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "c2b0c6c5e7c1"
down_revision = "9d9a5ac4613c"
branch_labels = None
depends_on = None


def _unique_exists(table: str, name: str) -> bool:
    inspector = inspect(op.get_bind())
    uniques = inspector.get_unique_constraints(table)
    return any(u.get("name") == name for u in uniques)


def _index_exists(table: str, name: str) -> bool:
    inspector = inspect(op.get_bind())
    indexes = inspector.get_indexes(table)
    return any(idx.get("name") == name for idx in indexes)


def _fk_exists(table: str, name: str) -> bool:
    inspector = inspect(op.get_bind())
    fks = inspector.get_foreign_keys(table)
    return any(fk.get("name") == name for fk in fks)


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    tables = inspector.get_table_names()
    if "oauth_tokens" not in tables:
        op.create_table(
            "oauth_tokens",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("provider", sa.String(length=50), nullable=False),
            sa.Column("account_id", sa.String(length=255), nullable=False),
            sa.Column("encrypted_access_token", sa.String(length=2048), nullable=False),
            sa.Column("encrypted_refresh_token", sa.String(length=2048), nullable=True),
            sa.Column("scope", sa.String(length=1024), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.ForeignKeyConstraint(
                ["user_id"],
                ["users.id"],
                ondelete="CASCADE",
                name="fk_oauth_tokens_user_id_users",
            ),
            sa.UniqueConstraint(
                "provider",
                "account_id",
                "user_id",
                name="uq_oauth_provider_account_user",
            ),
        )
        op.create_index("ix_oauth_tokens_provider", "oauth_tokens", ["provider"])
        op.create_index("ix_oauth_tokens_account_id", "oauth_tokens", ["account_id"])
        op.create_index("ix_oauth_tokens_user_id", "oauth_tokens", ["user_id"])
        return

    columns = {col["name"] for col in inspector.get_columns("oauth_tokens")}
    if "user_id" not in columns:
        op.add_column(
            "oauth_tokens",
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
    if not _index_exists("oauth_tokens", "ix_oauth_tokens_user_id"):
        op.create_index("ix_oauth_tokens_user_id", "oauth_tokens", ["user_id"])
    if not _fk_exists("oauth_tokens", "fk_oauth_tokens_user_id_users"):
        op.create_foreign_key(
            "fk_oauth_tokens_user_id_users",
            "oauth_tokens",
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )

    if not _index_exists("oauth_tokens", "ix_oauth_tokens_provider"):
        op.create_index("ix_oauth_tokens_provider", "oauth_tokens", ["provider"])
    if not _index_exists("oauth_tokens", "ix_oauth_tokens_account_id"):
        op.create_index("ix_oauth_tokens_account_id", "oauth_tokens", ["account_id"])

    if _unique_exists("oauth_tokens", "uq_oauth_provider_account"):
        op.drop_constraint("uq_oauth_provider_account", "oauth_tokens", type_="unique")
    if not _unique_exists("oauth_tokens", "uq_oauth_provider_account_user"):
        op.create_unique_constraint(
            "uq_oauth_provider_account_user",
            "oauth_tokens",
            ["provider", "account_id", "user_id"],
        )


def downgrade() -> None:
    if _unique_exists("oauth_tokens", "uq_oauth_provider_account_user"):
        op.drop_constraint(
            "uq_oauth_provider_account_user", "oauth_tokens", type_="unique"
        )
    op.create_unique_constraint(
        "uq_oauth_provider_account",
        "oauth_tokens",
        ["provider", "account_id"],
    )

    op.drop_constraint("fk_oauth_tokens_user_id_users", "oauth_tokens", type_="foreignkey")
    op.drop_index("ix_oauth_tokens_user_id", table_name="oauth_tokens")
    op.drop_column("oauth_tokens", "user_id")
