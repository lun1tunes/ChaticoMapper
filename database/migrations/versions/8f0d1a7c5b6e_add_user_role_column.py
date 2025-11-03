"""Add user role column.

Revision ID: 8f0d1a7c5b6e
Revises: 74f3d9f8d975
Create Date: 2025-02-03 14:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "8f0d1a7c5b6e"
down_revision = "74f3d9f8d975"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(length=50),
            nullable=True,
            server_default="basic",
        ),
    )
    op.execute("UPDATE users SET role = 'basic' WHERE role IS NULL")
    op.alter_column("users", "role", nullable=False, server_default="basic")


def downgrade() -> None:
    op.drop_column("users", "role")
