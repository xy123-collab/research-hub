"""勘误部分采纳时保留原始投稿与管理员修改记录

Revision ID: a7c8d9e0f1ab
Revises: a6b7c8d9e0fb
Create Date: 2026-07-26
"""
from alembic import op
import sqlalchemy as sa


revision = "a7c8d9e0f1ab"
down_revision = "a6b7c8d9e0fb"
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
    columns = [
        ("original_uid_value", sa.String(length=200)),
        ("original_var_name", sa.String(length=80)),
        ("original_current_value", sa.String(length=300)),
        ("original_suggested_value", sa.String(length=300)),
        ("original_reason", sa.Text()),
        ("admin_edited_by", sa.Integer()),
        ("admin_edited_at", sa.DateTime()),
    ]
    for name, column_type in columns:
        if _has_table("bug_items") and not _has_column("bug_items", name):
            op.add_column("bug_items", sa.Column(name, column_type, nullable=True))
    # 与模型保持一致；SQLite/PostgreSQL 都允许在已有表上后补外键。
    if _has_table("bug_items"):
        bind = op.get_bind()
        if bind.dialect.name != "sqlite":
            inspector = sa.inspect(bind)
            names = {fk.get("name") for fk in inspector.get_foreign_keys("bug_items")}
            if "fk_bug_items_admin_edited_by_users" not in names:
                op.create_foreign_key(
                    "fk_bug_items_admin_edited_by_users",
                    "bug_items", "users", ["admin_edited_by"], ["id"],
                )


def downgrade():
    if _has_table("bug_items") and op.get_bind().dialect.name != "sqlite":
        inspector = sa.inspect(op.get_bind())
        names = {fk.get("name") for fk in inspector.get_foreign_keys("bug_items")}
        if "fk_bug_items_admin_edited_by_users" in names:
            op.drop_constraint(
                "fk_bug_items_admin_edited_by_users", "bug_items", type_="foreignkey",
            )
    for column in (
        "admin_edited_at", "admin_edited_by", "original_reason",
        "original_suggested_value", "original_current_value",
        "original_var_name", "original_uid_value",
    ):
        if _has_column("bug_items", column):
            op.drop_column("bug_items", column)
