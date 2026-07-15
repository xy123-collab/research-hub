"""user_profiles 增加 email_opt_in（邮件提醒开关）

只处理旧表加列；库全新时该表可能还不存在，交给 create_all。

Revision ID: a5b6c7d8e9fa
Revises: a4b5c6d7e8f9
Create Date: 2026-07-15
"""
from alembic import op
import sqlalchemy as sa

revision = "a5b6c7d8e9fa"
down_revision = "a4b5c6d7e8f9"
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
    if _has_table("user_profiles") and not _has_column("user_profiles", "email_opt_in"):
        op.add_column("user_profiles",
                      sa.Column("email_opt_in", sa.Boolean(), nullable=True,
                                server_default=sa.true()))


def downgrade():
    if _has_column("user_profiles", "email_opt_in"):
        op.drop_column("user_profiles", "email_opt_in")
