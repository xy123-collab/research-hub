"""一次性/幂等数据修正。entrypoint 在 seed 之后调用：`python -m app.data_fixes`。

- 账号修正（只跑一次，靠 applied_fixes 标记）：
    · 「卢欣一」设为平台总管理员，密码改为 lxy.2001
    · 删除「陈默」账号及其帖子 / 数据集 / 相关数据
- 课题组总管理员修正（每次幂等）：确保 NSD 课题组的「李小雨」是 group_owner
  且 created_by 已设置——修复"总管理员看不到转让入口"的历史数据问题。

所有操作都包在 try/except 里，失败不影响服务启动。
"""
import logging

from .core.db import Base, SessionLocal
from .core.security import hash_password
from . import models  # noqa: 注册全部表
from .models.user import User, Role
from .models.group import ResearchGroup, GroupMember
from .models.dataset import Dataset
from .models.community import Post, Project
from .models.skill import Skill
from .models.workspace import Workspace
from .models.extras import ContentScope, AppliedFix

log = logging.getLogger("data_fixes")

# 识别目标账号用的候选（用户名或显示名）
LUXINYI_KEYS = ("卢欣一", "luxinyi", "xylu", "xylu2024")
CHENMO_KEYS = ("陈默", "chenmo")


def _find_user(db, keys):
    for k in keys:
        u = db.query(User).filter((User.username == k) | (User.display_name == k)).first()
        if u:
            return u
    return None


def _del_children(db, id_col_name: str, id_val: int):
    """删除所有含指定外键列(如 dataset_id/post_id)的子表记录，child-first 顺序避免 FK 冲突。"""
    for table in reversed(Base.metadata.sorted_tables):
        if id_col_name in table.c:
            db.execute(table.delete().where(table.c[id_col_name] == id_val))


def _delete_dataset(db, ds_id: int):
    _del_children(db, "dataset_id", ds_id)
    db.execute(Dataset.__table__.delete().where(Dataset.__table__.c.id == ds_id))


def _delete_content_scope(db, ctype: str, cid: int):
    db.execute(ContentScope.__table__.delete().where(
        (ContentScope.__table__.c.content_type == ctype) &
        (ContentScope.__table__.c.content_id == cid)))


def _delete_user(db, uid: int):
    # 1) 其发起的数据集连同全部依赖
    for ds in db.query(Dataset).filter_by(founder_id=uid).all():
        _delete_dataset(db, ds.id)
    # 2) 帖子 + 子记录
    for p in db.query(Post).filter_by(author_id=uid).all():
        _del_children(db, "post_id", p.id)
        _delete_content_scope(db, "post", p.id)
        db.execute(Post.__table__.delete().where(Post.__table__.c.id == p.id))
    # 3) 项目 + 子记录
    for pr in db.query(Project).filter_by(author_id=uid).all():
        _del_children(db, "project_id", pr.id)
        _delete_content_scope(db, "project", pr.id)
        db.execute(Project.__table__.delete().where(Project.__table__.c.id == pr.id))
    # 4) 其发起的 skill + 子记录
    for s in db.query(Skill).filter_by(founder_id=uid).all():
        _del_children(db, "skill_id", s.id)
        _delete_content_scope(db, "skill", s.id)
        db.execute(Skill.__table__.delete().where(Skill.__table__.c.id == s.id))
    # 5) 其拥有的工作台 + 子记录
    for w in db.query(Workspace).filter_by(owner_id=uid).all():
        _del_children(db, "workspace_id", w.id)
        db.execute(Workspace.__table__.delete().where(Workspace.__table__.c.id == w.id))
    # 6) 其余引用该用户的记录（成员/贡献/评论/申请/简历等），child-first
    user_cols = {"user_id", "author_id", "reporter_id", "added_by", "created_by",
                 "owner_id", "assignee_id", "reviewed_by", "decided_by", "updated_by",
                 "generated_by", "edited_by", "granted_by", "approved_by", "reviewer_id",
                 "founder_id", "reviewed_by_id"}
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in ("users", "roles", "permissions", "role_permissions"):
            continue
        for col in table.columns:
            if col.name in user_cols:
                try:
                    db.execute(table.delete().where(col == uid))
                except Exception as e:
                    log.warning("清理 %s.%s 失败: %s", table.name, col.name, e)
    # 7) 用户本身
    db.execute(User.__table__.delete().where(User.__table__.c.id == uid))


def _fix_accounts(db):
    super_role = db.query(Role).filter_by(code="super_admin").first()
    lu = _find_user(db, LUXINYI_KEYS)
    if lu and super_role:
        lu.role_id = super_role.id
        lu.password_hash = hash_password("lxy.2001")
        log.info("已将 %s(id=%s) 设为总管理员并重置密码", lu.display_name, lu.id)
    else:
        log.info("未找到「卢欣一」账号，跳过总管理员设置（可注册后再跑）")
    cm = _find_user(db, CHENMO_KEYS)
    if cm:
        cid = cm.id
        _delete_user(db, cid)
        log.info("已删除「陈默」(id=%s) 及其相关数据", cid)
    db.commit()


def _fix_group_owner(db):
    """确保 NSD 课题组的李小雨是 group_owner，且 created_by 已设置。幂等。"""
    lx = _find_user(db, ("李小雨", "lixiaoyu"))
    nsd = (db.query(ResearchGroup).filter_by(slug="nsd-dpe").first()
           or db.query(ResearchGroup).filter(ResearchGroup.name_zh.like("%NSD%")).first())
    if not (lx and nsd):
        return
    changed = False
    if not nsd.created_by:
        nsd.created_by = lx.id; changed = True
    m = db.query(GroupMember).filter_by(group_id=nsd.id, user_id=lx.id).first()
    if not m:
        from datetime import datetime
        m = GroupMember(group_id=nsd.id, user_id=lx.id, group_role="group_owner",
                        status="active", joined_at=datetime.utcnow(), approved_by=lx.id)
        db.add(m); changed = True
    elif m.group_role != "group_owner" or m.status != "active":
        m.group_role = "group_owner"; m.status = "active"; changed = True
    if changed:
        db.commit()
        log.info("已修正 NSD 课题组总管理员为 %s(id=%s)", lx.display_name, lx.id)


def run():
    Base.metadata.create_all(bind=SessionLocal().bind)
    db = SessionLocal()
    try:
        # 账号修正只跑一次
        if not db.get(AppliedFix, "fix_2026_accounts"):
            try:
                _fix_accounts(db)
                db.add(AppliedFix(key="fix_2026_accounts", note="卢欣一设总管理员+删除陈默"))
                db.commit()
            except Exception as e:
                db.rollback()
                log.warning("账号修正失败（本次跳过，不阻断启动）: %s", e)
        # 课题组总管理员修正每次幂等执行
        try:
            _fix_group_owner(db)
        except Exception as e:
            db.rollback()
            log.warning("课题组总管理员修正失败: %s", e)
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
