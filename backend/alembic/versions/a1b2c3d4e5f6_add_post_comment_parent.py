"""add parent_id/created_at to post_comments (评论的评论)

新增表一律靠 create_all 自动建；此迁移只处理「改动已存在旧表」的部分：
给 post_comments 增加 parent_id（评论的评论）与 created_at。

Revision ID: a1b2c3d4e5f6
Revises: 98c32ba37beb
Create Date: 2026-07-14
"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "98c32ba37beb"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        cols = [c["name"] for c in insp.get_columns(table)]
    except Exception:
        return False
    return column in cols


def upgrade():
    # 幂等：若列已存在（例如 create_all 先建过）则跳过
    if not _has_column("post_comments", "parent_id"):
        op.add_column("post_comments", sa.Column("parent_id", sa.Integer(), nullable=True))
    if not _has_column("post_comments", "created_at"):
        op.add_column("post_comments", sa.Column("created_at", sa.DateTime(), nullable=True))


def downgrade():
    if _has_column("post_comments", "created_at"):
        op.drop_column("post_comments", "created_at")
    if _has_column("post_comments", "parent_id"):
        op.drop_column("post_comments", "parent_id")
