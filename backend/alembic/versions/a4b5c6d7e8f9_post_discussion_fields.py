"""posts 增加 title/post_type/status/created_at（统一讨论系统）

只处理旧表 posts 加列；新表 post_follows / notification_state 靠 create_all 建。

Revision ID: a4b5c6d7e8f9
Revises: a3b4c5d6e7f8
Create Date: 2026-07-15
"""
from alembic import op
import sqlalchemy as sa

revision = "a4b5c6d7e8f9"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    return table in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        cols = [c["name"] for c in insp.get_columns(table)]
    except Exception:
        return False
    return column in cols


def upgrade():
    # posts/post_reactions 为原始表，正常存在；库全新时若还未建，交给 create_all。
    if not _has_table("posts") or not _has_table("post_reactions"):
        return
    if not _has_column("posts", "title"):
        op.add_column("posts", sa.Column("title", sa.String(length=300), nullable=True))
    if not _has_column("posts", "post_type"):
        op.add_column("posts", sa.Column("post_type", sa.String(length=30),
                                         nullable=True, server_default="discussion"))
    if not _has_column("posts", "status"):
        op.add_column("posts", sa.Column("status", sa.String(length=20),
                                         nullable=True, server_default="open"))
    if not _has_column("posts", "created_at"):
        op.add_column("posts", sa.Column("created_at", sa.DateTime(), nullable=True))
    if not _has_column("post_reactions", "created_at"):
        op.add_column("post_reactions", sa.Column("created_at", sa.DateTime(), nullable=True))


def downgrade():
    if _has_column("post_reactions", "created_at"):
        op.drop_column("post_reactions", "created_at")
    for c in ("created_at", "status", "post_type", "title"):
        if _has_column("posts", c):
            op.drop_column("posts", c)
