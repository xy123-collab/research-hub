"""三级权限判定：super_admin -> 课题组 group -> 数据集 dataset。
业务代码只判断权限码；加角色/授权/交接=改数据行，不改代码。"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .db import get_db
from .security import decode_token
from ..models.user import User
from ..models.group import GroupMember
from ..models.dataset import DatasetMember

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


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


def is_group_admin(db: Session, group_id, user: User) -> bool:
    return is_super_admin(user) or group_role(db, group_id, user.id) == "group_admin"


# ---------- 数据集级 ----------
def dataset_membership(db: Session, dataset_id, user_id) -> DatasetMember | None:
    return db.query(DatasetMember).filter_by(dataset_id=dataset_id, user_id=user_id).first()


def dataset_role(db: Session, dataset_id, user_id) -> str | None:
    m = dataset_membership(db, dataset_id, user_id)
    return m.ds_role if m else None


def is_dataset_member(db: Session, dataset_id, user: User) -> bool:
    return is_super_admin(user) or dataset_membership(db, dataset_id, user.id) is not None


def is_dataset_admin(db: Session, dataset_id, user: User) -> bool:
    """founder 或 super_admin。"""
    if is_super_admin(user):
        return True
    return dataset_role(db, dataset_id, user.id) == "founder"


def has_dataset_perm(db: Session, dataset_id, user: User, perm: str) -> bool:
    if is_super_admin(user):
        return True
    m = dataset_membership(db, dataset_id, user.id)
    if not m:
        return False
    if m.ds_role in ("founder", "maintainer"):
        return True
    perms = m.granted_perms_json or []
    return perm in perms
