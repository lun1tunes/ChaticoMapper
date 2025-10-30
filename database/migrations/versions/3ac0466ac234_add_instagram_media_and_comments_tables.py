"""Add instagram_comments table.

Revision ID: 3ac0466ac234
Revises: 0001
Create Date: 2025-10-29 11:56:40.202938

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '3ac0466ac234'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create instagram_comments table."""
    # Create instagram_comments table
    op.create_table(
        "instagram_comments",
        sa.Column("comment_id", sa.String(length=100), nullable=False, comment="Instagram comment ID"),
        sa.Column("media_id", sa.String(length=100), nullable=True, comment="Instagram media ID"),
        sa.Column("owner_id", sa.String(length=255), nullable=False, comment="Instagram business account ID"),
        sa.Column("user_id", sa.String(length=255), nullable=False, comment="Comment author's Instagram user ID"),
        sa.Column("username", sa.String(length=100), nullable=False, comment="Comment author's Instagram username"),
        sa.Column("text", sa.Text(), nullable=False, comment="Comment text content"),
        sa.Column("parent_id", sa.String(length=100), nullable=True, comment="Parent comment ID for replies"),
        sa.Column("timestamp", sa.Integer(), nullable=False, comment="Unix timestamp from webhook entry"),
        sa.Column("raw_webhook_data", sa.JSON(), nullable=False, comment="Raw webhook payload for audit"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("comment_id"),
    )

    # Create indexes for instagram_comments
    op.create_index("ix_instagram_comments_comment_id", "instagram_comments", ["comment_id"], unique=False)
    op.create_index("ix_instagram_comments_media_id", "instagram_comments", ["media_id"], unique=False)
    op.create_index("ix_instagram_comments_owner_id", "instagram_comments", ["owner_id"], unique=False)
    op.create_index("ix_instagram_comments_user_id", "instagram_comments", ["user_id"], unique=False)
    op.create_index("ix_instagram_comments_parent_id", "instagram_comments", ["parent_id"], unique=False)


def downgrade() -> None:
    """Drop instagram_comments table."""
    op.drop_index("ix_instagram_comments_parent_id", table_name="instagram_comments")
    op.drop_index("ix_instagram_comments_user_id", table_name="instagram_comments")
    op.drop_index("ix_instagram_comments_owner_id", table_name="instagram_comments")
    op.drop_index("ix_instagram_comments_media_id", table_name="instagram_comments")
    op.drop_index("ix_instagram_comments_comment_id", table_name="instagram_comments")
    op.drop_table("instagram_comments")
