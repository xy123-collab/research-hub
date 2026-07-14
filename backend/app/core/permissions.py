"""权限判定内核。严格对齐《科研数据协作平台权限规则》。

四条核心原则在代码层的落地：
- 原则一 平台总管理员 ≠ 数据管理员：is_super_admin 只用于「平台系统」路由，
  绝不短路数据集/课题组的内容权限（本文件下方的内容判定函数都不看 super_admin）。
- 原则二 加入课题组 ≠ 加入数据集：group 与 dataset 成员分别判定。
- 原则三 加入数据集 ≠ 下载权：成员默认无下载/在线分析等权限，需单独授权(DatasetGrant)。
- 原则四~六 由各接口配合本文件的 helper 执行。

角色（六类）：
  普通用户 = 已登录但不属于任何组/集
  课题组成员 / 课题组管理员      -> GroupMember.group_role in (member, group_admin)
  数据集成员 / 数据集管理员      -> DatasetMember.ds_role in (member, founder|admin)
  平台总管理员                  -> User.role.code == super_admin
一个用户可同时拥有多个角色；权限一律按「具体课题组 / 具体数据集」判定。
"""
from datetime import datetime
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .db import get_db
from .security import decode_token
from ..models.user import User
from ..models.group import GroupMember
from ..models.dataset import DatasetMember
from ..models.access import DatasetGrant, DatasetSettings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

# 两级管理员：
#   数据集「总管理员/主管理员」= lead（ds_role in DS_LEAD_ROLES，全集内唯一）
#   数据集「管理员」          = ds_role "admin"
# 仅 lead 可增/删管理员与转让；lead 不能直接自撤，须先把 lead 转让出去。
DS_LEAD_ROLES = ("founder", "owner")           # founder 为历史命名，等同 owner
DS_ADMIN_ROLES = ("founder", "owner", "admin")  # 视为「数据集管理员」的取值
# 课题组「总管理员」= group_owner；「管理员」= group_admin
GROUP_LEAD_ROLES = ("group_owner",)
GROUP_ADMIN_ROLES = ("group_owner", "group_admin")


def get_current_user(token: str | None = Depends(oauth2_scheme),
                     db: Session = Depends(get_db)) -> User:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未登录")
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "令牌无效")
    user = db.get(User, int(payload["sub"]))
    if not user or user.status == "left":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在或已离开")
    return user


# ---------- 平台级（只管系统，不碰内容）----------
def is_super_admin(user: User) -> bool:
    return bool(user.role and user.role.code == "super_admin")


def require_super_admin(user: User = Depends(get_current_user)) -> User:
    if not is_super_admin(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要总管理员权限")
    return user


# ---------- 课题组级 ----------
def group_role(db: Session, group_id, user_id) -> str | None:
    m = db.query(GroupMember).filter_by(group_id=group_id, user_id=user_id).first()
    return m.group_role if m and m.status == "active" else None


def is_group_member(db: Session, group_id, user: User) -> bool:
    # 原则一：super_admin 不因平台身份自动成为课题组成员
    return group_role(db, group_id, user.id) is not None


def is_group_admin(db: Session, group_id, user: User) -> bool:
    # 原则一：super_admin 不自动是课题组管理员
    return group_role(db, group_id, user.id) in GROUP_ADMIN_ROLES


def count_group_admins(db: Session, group_id) -> int:
    return db.query(GroupMember).filter(
        GroupMember.group_id == group_id, GroupMember.status == "active",
        GroupMember.group_role.in_(GROUP_ADMIN_ROLES)).count()


def group_lead_id(db: Session, group_id):
    """课题组总管理员的 user_id。优先 group_owner，其次回退到 created_by（兼容历史数据）。"""
    from ..models.group import ResearchGroup
    m = db.query(GroupMember).filter_by(
        group_id=group_id, group_role="group_owner", status="active").first()
    if m:
        return m.user_id
    g = db.get(ResearchGroup, group_id)
    return g.created_by if g else None


def is_group_lead(db: Session, group_id, user: User) -> bool:
    return group_lead_id(db, group_id) == user.id


# ---------- 数据集级 ----------
def dataset_membership(db: Session, dataset_id, user_id) -> DatasetMember | None:
    return db.query(DatasetMember).filter_by(dataset_id=dataset_id, user_id=user_id).first()


def dataset_role(db: Session, dataset_id, user_id) -> str | None:
    m = dataset_membership(db, dataset_id, user_id)
    return m.ds_role if m else None


def is_dataset_member(db: Session, dataset_id, user: User) -> bool:
    # 原则一 + 二：super_admin / 课题组身份都不自动成为数据集成员
    return dataset_membership(db, dataset_id, user.id) is not None


def is_dataset_admin(db: Session, dataset_id, user: User) -> bool:
    return dataset_role(db, dataset_id, user.id) in DS_ADMIN_ROLES


def count_dataset_admins(db: Session, dataset_id) -> int:
    return db.query(DatasetMember).filter(
        DatasetMember.dataset_id == dataset_id,
        DatasetMember.ds_role.in_(DS_ADMIN_ROLES)).count()


def dataset_lead_id(db: Session, dataset_id):
    """数据集总管理员的 user_id。优先 owner/founder 角色，其次回退到 founder_id。"""
    from ..models.dataset import Dataset
    m = db.query(DatasetMember).filter(
        DatasetMember.dataset_id == dataset_id,
        DatasetMember.ds_role.in_(DS_LEAD_ROLES)).first()
    if m:
        return m.user_id
    d = db.get(Dataset, dataset_id)
    return d.founder_id if d else None


def is_dataset_lead(db: Session, dataset_id, user: User) -> bool:
    return dataset_lead_id(db, dataset_id) == user.id


def active_grants(db: Session, dataset_id, user_id):
    now = datetime.utcnow()
    rows = db.query(DatasetGrant).filter_by(
        dataset_id=dataset_id, user_id=user_id, revoked=False).all()
    return [g for g in rows if g.is_active(now)]


def has_dataset_perm(db: Session, dataset_id, user: User, perm: str,
                     version: str | None = None) -> bool:
    """成员是否拥有某单独授权。管理员天然拥有全部；否则查有效授权(含到期/版本范围)。"""
    if is_dataset_admin(db, dataset_id, user):
        return True
    m = dataset_membership(db, dataset_id, user.id)
    if not m:
        return False
    for g in active_grants(db, dataset_id, user.id):
        if g.perm != perm:
            continue
        # 仅对指定版本有效
        if g.scope_type == "version" and g.scope_version and version and \
                g.scope_version != version:
            continue
        return True
    # 兼容历史：granted_perms_json 里的永久授权
    return perm in (m.granted_perms_json or [])


# ---------- 数据集设置（懒创建）----------
def get_settings(db: Session, dataset_id) -> DatasetSettings:
    s = db.get(DatasetSettings, dataset_id)
    if not s:
        s = DatasetSettings(dataset_id=dataset_id)
        db.add(s); db.flush()
    return s
