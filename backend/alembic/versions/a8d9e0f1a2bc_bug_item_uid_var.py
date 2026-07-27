"""勘误项记录本次实际使用的 ID 变量

Revision ID: a8d9e0f1a2bc
Revises: a7c8d9e0f1ab
Create Date: 2026-07-27
"""
from alembic import op
import sqlalchemy as sa


revision = "a8d9e0f1a2bc"
down_revision = "a7c8d9e0f1ab"
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
    if _has_table("bug_items") and not _has_column("bug_items", "uid_var"):
        op.add_column(
            "bug_items",
            sa.Column("uid_var", sa.String(length=80), nullable=True),
        )


def downgrade():
    if _has_column("bug_items", "uid_var"):
        op.drop_column("bug_items", "uid_var")
