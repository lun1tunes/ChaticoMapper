"""Rename users.email column to username

Revision ID: 5c9f79b953a1
Revises: d3f6b1dcb38c
Create Date: 2025-11-04 08:50:00

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5c9f79b953a1"
down_revision = "d3f6b1dcb38c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "email",
            new_column_name="username",
            existing_type=sa.String(length=255),
            existing_nullable=False,
        )
        batch_op.drop_index("ix_users_email")
        batch_op.create_index("ix_users_username", ["username"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "username",
            new_column_name="email",
            existing_type=sa.String(length=255),
            existing_nullable=False,
        )
        batch_op.drop_index("ix_users_username")
        batch_op.create_index("ix_users_email", ["email"], unique=True)
