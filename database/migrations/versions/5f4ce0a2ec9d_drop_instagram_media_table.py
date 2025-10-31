"""Drop instagram_media table and align instagram_comments schema."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision = "5f4ce0a2ec9d"
down_revision = "4b27f4d0b8e0"
branch_labels = None
depends_on = None


def _drop_comment_fk_to_media(inspector: Inspector) -> None:
    foreign_keys = inspector.get_foreign_keys("instagram_comments")
    for fk in foreign_keys:
        referred_table = fk.get("referred_table")
        fk_name = fk.get("name")
        if referred_table == "instagram_media" and fk_name:
            op.drop_constraint(fk_name, "instagram_comments", type_="foreignkey")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    existing_tables = inspector.get_table_names()
    if "instagram_comments" in existing_tables:
        _drop_comment_fk_to_media(inspector)
        op.alter_column(
            "instagram_comments",
            "media_id",
            existing_type=sa.String(length=100),
            nullable=True,
        )

        columns = {col["name"] for col in inspector.get_columns("instagram_comments")}
        if "owner_id" not in columns:
            op.add_column(
                "instagram_comments",
                sa.Column("owner_id", sa.String(length=255), nullable=True),
            )
            op.execute(
                sa.text(
                    "UPDATE instagram_comments "
                    "SET owner_id = COALESCE(owner_id, 'legacy_owner')"
                )
            )
            op.alter_column(
                "instagram_comments",
                "owner_id",
                existing_type=sa.String(length=255),
                nullable=False,
            )

        existing_indexes = {
            idx["name"] for idx in inspector.get_indexes("instagram_comments")
        }
        if "ix_instagram_comments_owner_id" not in existing_indexes:
            op.create_index(
                "ix_instagram_comments_owner_id",
                "instagram_comments",
                ["owner_id"],
            )

    if "instagram_media" in existing_tables:
        op.drop_table("instagram_media")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    existing_tables = inspector.get_table_names()

    if "instagram_media" not in existing_tables:
        op.create_table(
            "instagram_media",
            sa.Column(
                "media_id",
                sa.String(length=100),
                nullable=False,
                comment="Instagram media ID",
            ),
            sa.Column(
                "owner_id",
                sa.String(length=255),
                nullable=False,
                comment="Instagram account ID of media owner",
            ),
            sa.Column(
                "owner_username",
                sa.String(length=100),
                nullable=True,
                comment="Instagram username of media owner",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("media_id"),
        )
        op.create_index(
            "ix_instagram_media_media_id",
            "instagram_media",
            ["media_id"],
            unique=False,
        )
        op.create_index(
            "ix_instagram_media_owner_id",
            "instagram_media",
            ["owner_id"],
            unique=False,
        )

    if "instagram_comments" in inspector.get_table_names():
        indexes = {idx["name"] for idx in inspector.get_indexes("instagram_comments")}
        if "ix_instagram_comments_owner_id" in indexes:
            op.drop_index("ix_instagram_comments_owner_id", table_name="instagram_comments")

        columns = {col["name"] for col in inspector.get_columns("instagram_comments")}

        if "owner_id" in columns:
            op.drop_column("instagram_comments", "owner_id")

        op.alter_column(
            "instagram_comments",
            "media_id",
            existing_type=sa.String(length=100),
            nullable=False,
        )

        op.create_foreign_key(
            "instagram_comments_media_id_fkey",
            "instagram_comments",
            "instagram_media",
            ["media_id"],
            ["media_id"],
            ondelete="CASCADE",
        )
