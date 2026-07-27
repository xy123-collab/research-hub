"""勘误记录非唯一定位匹配数及管理员多行应用确认

Revision ID: a9e0f1a2b3cd
Revises: a8d9e0f1a2bc
Create Date: 2026-07-27
"""
from alembic import op
import sqlalchemy as sa


revision = "a9e0f1a2b3cd"
down_revision = "a8d9e0f1a2bc"
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
    if not _has_table("bug_items"):
        return
    if not _has_column("bug_items", "uid_match_count"):
        op.add_column(
            "bug_items",
            sa.Column("uid_match_count", sa.Integer(), nullable=True),
        )
    if not _has_column("bug_items", "allow_multi_row_apply"):
        op.add_column(
            "bug_items",
            sa.Column(
                "allow_multi_row_apply", sa.Boolean(), nullable=True,
                server_default=sa.false(),
            ),
        )


def downgrade():
    if _has_column("bug_items", "allow_multi_row_apply"):
        op.drop_column("bug_items", "allow_multi_row_apply")
    if _has_column("bug_items", "uid_match_count"):
        op.drop_column("bug_items", "uid_match_count")
