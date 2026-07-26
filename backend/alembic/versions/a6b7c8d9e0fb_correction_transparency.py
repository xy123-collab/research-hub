"""勘误增加上传时间、证据与新增官员标记

只处理旧表加列；全新库交给 create_all。

Revision ID: a6b7c8d9e0fb
Revises: a5b6c7d8e9fa
Create Date: 2026-07-26
"""
from alembic import op
import sqlalchemy as sa

revision = "a6b7c8d9e0fb"
down_revision = "a5b6c7d8e9fa"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    return table in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table: str, column: str) -> bool:
    if not _has_table(table):
        return False
    try:
        return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
    except Exception:
        return False


def upgrade():
    # created_at 故意不回填，避免把旧勘误伪装成本次部署时上传。
    if _has_table("bugs") and not _has_column("bugs", "created_at"):
        op.add_column("bugs", sa.Column("created_at", sa.DateTime(), nullable=True))
    if _has_table("bug_items") and not _has_column("bug_items", "evidence"):
        op.add_column("bug_items", sa.Column("evidence", sa.Text(), nullable=True))
    if _has_table("bug_items") and not _has_column("bug_items", "is_new_officer"):
        op.add_column(
            "bug_items",
            sa.Column("is_new_officer", sa.Boolean(), nullable=True, server_default=sa.false()),
        )


def downgrade():
    for column in ("is_new_officer", "evidence"):
        if _has_column("bug_items", column):
            op.drop_column("bug_items", column)
    if _has_column("bugs", "created_at"):
        op.drop_column("bugs", "created_at")
