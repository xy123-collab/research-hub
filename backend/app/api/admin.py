from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..core.permissions import get_current_user, require_super_admin, is_group_admin
from ..models.user import User, Role
from ..models.group import ResearchGroup, GroupJoinRequest
from ..models.governance import AuditLog
from ..services.scoring import leaderboard, by_dataset

router = APIRouter(tags=["admin"])


# ---- 课题组管理员：全员总贡献度 + 分数据集贡献度（仅管理后台可见）----
@router.get("/admin/contributions")
def contributions(scope: str = "total", db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    # 课题组管理员或超管可见（贡献视图归课题组管理员）
    is_ga = any(is_group_admin(db, g.id, user)
                for g in db.query(ResearchGroup).all())
    from ..core.permissions import is_super_admin
    if not (is_ga or is_super_admin(user)):
        raise HTTPException(403, "需课题组管理员或总管理员")
    if scope == "by_dataset":
        return by_dataset(db)
    return leaderboard(db)


@router.get("/admin/group-join-requests")
def group_join_reqs(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    out = []
    for r in db.query(GroupJoinRequest).filter_by(status="pending").all():
        if is_group_admin(db, r.group_id, user):
            out.append({"id": r.id, "group_id": r.group_id, "user_id": r.user_id,
                        "message": r.message})
    return out


# ---- 总管理员：只见元信息，动作元数据级审计 ----
@router.get("/admin/groups")
def all_groups(db: Session = Depends(get_db), user: User = Depends(require_super_admin)):
    gs = db.query(ResearchGroup).all()
    return [{"id": g.id, "slug": g.slug, "name_zh": g.name_zh,
             "created_by": g.created_by, "is_deleted": g.is_deleted,
             "discoverable": g.discoverable} for g in gs]


@router.get("/admin/audit-log")
def audit_log(limit: int = 200, db: Session = Depends(get_db),
              user: User = Depends(require_super_admin)):
    # 总管理员只暴露动作元数据（谁/何时/做了什么类型），不含内容与被改的具体值
    logs = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(limit).all()
    return [{"id": l.id, "user_id": l.user_id, "action": l.action,
             "object_type": l.object_type, "object_id": l.object_id,
             "created_at": str(l.created_at)} for l in logs]


@router.get("/admin/super-admins")
def super_admins(db: Session = Depends(get_db), user: User = Depends(require_super_admin)):
    role = db.query(Role).filter_by(code="super_admin").first()
    if not role:
        return []
    us = db.query(User).filter_by(role_id=role.id).all()
    return [{"id": u.id, "username": u.username, "display_name": u.display_name} for u in us]


@router.post("/admin/super-admins")
def grant_super(uid: int, db: Session = Depends(get_db),
                user: User = Depends(require_super_admin)):
    """交接/新增总管理员。"""
    role = db.query(Role).filter_by(code="super_admin").first()
    target = db.get(User, uid)
    if not target:
        raise HTTPException(404, "用户不存在")
    target.role_id = role.id
    db.add(AuditLog(user_id=user.id, action="super_admin.grant", object_type="user",
                    object_id=str(uid), detail_json={}))
    db.commit()
    return {"ok": True}
