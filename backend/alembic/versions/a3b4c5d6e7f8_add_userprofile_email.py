"""add public email to user_profiles（主页公开联系邮箱）

只处理「改动已存在旧表」：给 user_profiles 增加 email 列。
新增表靠 create_all 自动建。

Revision ID: a3b4c5d6e7f8
Revises: a2b3c4d5e6f7
Create Date: 2026-07-15
"""
from alembic import op
import sqlalchemy as sa

revision = "a3b4c5d6e7f8"
down_revision = "a2b3c4d5e6f7"
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
    # user_profiles 是 create_all 建的表；库全新时它此刻可能还不存在，
    # 交给 create_all 建齐（模型已含 email 列），这里跳过即可。
    if _has_table("user_profiles") and not _has_column("user_profiles", "email"):
        op.add_column("user_profiles", sa.Column("email", sa.String(length=200), nullable=True))


def downgrade():
    if _has_column("user_profiles", "email"):
        op.drop_column("user_profiles", "email")
