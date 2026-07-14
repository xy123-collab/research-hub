"""add doi to lit_refs（文献 DOI 字段）

只处理「改动已存在旧表」的部分：给 lit_refs 增加 doi 列。
新增表（content_scopes / applied_fixes 等）靠 create_all 自动建。

Revision ID: a2b3c4d5e6f7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-14
"""
from alembic import op
import sqlalchemy as sa

revision = "a2b3c4d5e6f7"
down_revision = "a1b2c3d4e5f6"
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
    if not _has_column("lit_refs", "doi"):
        op.add_column("lit_refs", sa.Column("doi", sa.String(length=200), nullable=True))


def downgrade():
    if _has_column("lit_refs", "doi"):
        op.drop_column("lit_refs", "doi")
