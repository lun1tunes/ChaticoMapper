"""Initial migration for Chatico Mapper App."""

"""Initial migration

Revision ID: 0001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Create worker_apps table
    op.create_table(
        "worker_apps",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "owner_id",
            sa.String(length=255),
            nullable=False,
            comment="Instagram account ID",
        ),
        sa.Column(
            "owner_instagram_username",
            sa.String(length=255),
            nullable=False,
            comment="Instagram username of the owner",
        ),
        sa.Column(
            "base_url",
            sa.String(length=500),
            nullable=False,
            comment="Base URL for forwarding Instagram webhooks",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Created timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Updated timestamp",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for worker_apps
    op.create_index("ix_worker_apps_id", "worker_apps", ["id"], unique=False)
    op.create_index("ix_worker_apps_owner_id", "worker_apps", ["owner_id"], unique=True)

    # Create webhook_logs table
    op.create_table(
        "webhook_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "webhook_id",
            sa.String(length=255),
            nullable=False,
            comment="Unique webhook ID",
        ),
        sa.Column(
            "owner_id",
            sa.String(length=255),
            nullable=False,
            comment="Instagram account ID",
        ),
        sa.Column(
            "worker_app_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Target worker app ID",
        ),
        sa.Column(
            "target_owner_username",
            sa.String(length=255),
            nullable=True,
            comment="Target Instagram username",
        ),
        sa.Column(
            "target_base_url",
            sa.String(length=500),
            nullable=True,
            comment="Target base URL",
        ),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            comment="Processing status (success/failed/routed)",
        ),
        sa.Column("error_message", sa.Text(), nullable=True, comment="Error messages"),
        sa.Column(
            "processing_time_ms",
            sa.Integer(),
            nullable=True,
            comment="Processing time in milliseconds",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Created timestamp",
        ),
        sa.ForeignKeyConstraint(
            ["worker_app_id"],
            ["worker_apps.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for webhook_logs
    op.create_index("ix_webhook_logs_id", "webhook_logs", ["id"], unique=False)
    op.create_index(
        "ix_webhook_logs_webhook_id", "webhook_logs", ["webhook_id"], unique=True
    )
    op.create_index(
        "ix_webhook_logs_owner_id", "webhook_logs", ["owner_id"], unique=False
    )
    op.create_index(
        "ix_webhook_logs_worker_app_id", "webhook_logs", ["worker_app_id"], unique=False
    )
    op.create_index(
        "ix_webhook_logs_status", "webhook_logs", ["status"], unique=False
    )
    op.create_index(
        "ix_webhook_logs_created_at", "webhook_logs", ["created_at"], unique=False
    )
    op.create_index(
        "idx_webhook_logs_owner_status",
        "webhook_logs",
        ["owner_id", "status"],
        unique=False,
    )
    op.create_index(
        "idx_webhook_logs_worker_app_status",
        "webhook_logs",
        ["worker_app_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade database schema."""
    # Drop webhook_logs table
    op.drop_index("idx_webhook_logs_worker_app_status", table_name="webhook_logs")
    op.drop_index("idx_webhook_logs_owner_status", table_name="webhook_logs")
    op.drop_index("ix_webhook_logs_created_at", table_name="webhook_logs")
    op.drop_index("ix_webhook_logs_status", table_name="webhook_logs")
    op.drop_index("ix_webhook_logs_worker_app_id", table_name="webhook_logs")
    op.drop_index("ix_webhook_logs_owner_id", table_name="webhook_logs")
    op.drop_index("ix_webhook_logs_webhook_id", table_name="webhook_logs")
    op.drop_index("ix_webhook_logs_id", table_name="webhook_logs")
    op.drop_table("webhook_logs")

    # Drop worker_apps table
    op.drop_index("ix_worker_apps_owner_id", table_name="worker_apps")
    op.drop_index("ix_worker_apps_id", table_name="worker_apps")
    op.drop_table("worker_apps")
