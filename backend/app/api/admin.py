from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..core.db import get_db
from ..core.permissions import (get_current_user, require_super_admin, is_group_admin,
                                is_group_lead, group_lead_id, is_dataset_admin,
                                is_dataset_lead, dataset_lead_id, is_super_admin,
                                GROUP_ADMIN_ROLES, DS_ADMIN_ROLES)
from ..models.user import User, Role
from ..models.group import ResearchGroup, GroupMember, GroupJoinRequest
from ..models.dataset import Dataset, DatasetMember, JoinRequest
from ..models.version import DataVersion, DownloadLog
from ..models.correction import Bug
from ..models.code import CodeScript
from ..models.community import Post, PostComment
from ..models.governance import AuditLog, ContributionEvent
from ..models.access import DownloadRequest
from ..services.scoring import leaderboard, by_dataset

router = APIRouter(tags=["admin"])


def _uname(db, uid):
    u = db.get(User, uid)
    return u.display_name if u else f"用户#{uid}"


# ============ 管理控制台（按我管理的组/数据集切换）============
@router.get("/admin/my-scopes")
def my_scopes(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """当前用户可管理的课题组与数据集，供管理后台选择查看对象。"""
    groups = []
    for m in db.query(GroupMember).filter(
            GroupMember.user_id == user.id, GroupMember.status == "active",
            GroupMember.group_role.in_(GROUP_ADMIN_ROLES)).all():
        g = db.get(ResearchGroup, m.group_id)
        if g and not g.is_deleted:
            groups.append({"slug": g.slug, "name_zh": g.name_zh,
                           "role": "lead" if group_lead_id(db, g.id) == user.id else "admin"})
    datasets = []
    for m in db.query(DatasetMember).filter(
            DatasetMember.user_id == user.id,
            DatasetMember.ds_role.in_(DS_ADMIN_ROLES)).all():
        d = db.get(Dataset, m.dataset_id)
        if d and not d.is_deleted:
            datasets.append({"slug": d.slug, "name_zh": d.name_zh,
                             "role": "lead" if dataset_lead_id(db, d.id) == user.id else "admin"})
    return {"groups": groups, "datasets": datasets, "is_super": is_super_admin(user)}


@router.get("/admin/datasets/{slug}/console")
def dataset_console(slug: str, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    d = db.query(Dataset).filter_by(slug=slug, is_deleted=False).first()
    if not d:
        raise HTTPException(404, "数据集不存在")
    if not is_dataset_admin(db, d.id, user):
        raise HTTPException(403, "需要数据集管理员")
    cutoff = datetime.utcnow() - timedelta(days=30)
    # 贡献度（分成员）
    rows = (db.query(ContributionEvent.user_id, func.sum(ContributionEvent.weight))
            .filter(ContributionEvent.dataset_id == d.id)
            .group_by(ContributionEvent.user_id)
            .order_by(func.sum(ContributionEvent.weight).desc()).all())
    contributions = [{"user_id": uid, "name": _uname(db, uid), "score": round(s or 0, 2)}
                     for uid, s in rows]
    # 活跃度（有时间戳的按近30天，其余给总量）
    post_ids = [p.id for p in db.query(Post).filter_by(dataset_id=d.id).all()]
    comments_total = (db.query(PostComment)
                      .filter(PostComment.post_id.in_(post_ids or [-1])).count())
    versions_30d = db.query(DataVersion).filter(
        DataVersion.dataset_id == d.id, DataVersion.release_date >= cutoff).count()
    downloads_30d = db.query(DownloadLog).filter(
        DownloadLog.dataset_id == d.id, DownloadLog.downloaded_at >= cutoff).count()
    activity = {
        "comments_total": comments_total,
        "corrections_total": db.query(Bug).filter_by(dataset_id=d.id).count(),
        "corrections_pending": db.query(Bug).filter_by(dataset_id=d.id, status="pending").count(),
        "code_total": db.query(CodeScript).filter_by(dataset_id=d.id).count(),
        "versions_total": db.query(DataVersion).filter_by(dataset_id=d.id).count(),
        "versions_30d": versions_30d, "downloads_30d": downloads_30d,
    }
    # 最新消息（版本/勘误/代码）
    recent = []
    for v in db.query(DataVersion).filter_by(dataset_id=d.id).order_by(
            DataVersion.id.desc()).limit(5).all():
        recent.append({"type": "version", "text": f"发布版本 {v.version_id}",
                       "at": str(v.release_date)[:10] if v.release_date else "", "sort": v.id})
    for b in db.query(Bug).filter_by(dataset_id=d.id).order_by(Bug.id.desc()).limit(5).all():
        recent.append({"type": "bug", "text": f"勘误 #{b.id}（{b.status}）",
                       "at": str(b.reviewed_at)[:10] if b.reviewed_at else "", "sort": b.id})
    recent.sort(key=lambda x: x["sort"], reverse=True)
    pending = {
        "join_requests": db.query(JoinRequest).filter_by(dataset_id=d.id, status="pending").count(),
        "download_requests": db.query(DownloadRequest).filter_by(dataset_id=d.id, status="pending").count(),
        "corrections": activity["corrections_pending"],
    }
    return {"dataset": {"slug": d.slug, "name_zh": d.name_zh},
            "is_lead": is_dataset_lead(db, d.id, user),
            "contributions": contributions, "activity": activity,
            "recent": recent[:8], "pending": pending}


@router.get("/admin/groups/{slug}/console")
def group_console(slug: str, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    g = db.query(ResearchGroup).filter_by(slug=slug, is_deleted=False).first()
    if not g:
        raise HTTPException(404, "课题组不存在")
    if not is_group_admin(db, g.id, user):
        raise HTTPException(403, "需要课题组管理员")
    cutoff = datetime.utcnow() - timedelta(days=30)
    ds = db.query(Dataset).filter_by(group_id=g.id, is_deleted=False).all()
    ds_ids = [x.id for x in ds]
    member_ids = [m.user_id for m in db.query(GroupMember).filter_by(
        group_id=g.id, status="active").all()]
    # 贡献度（组内各数据集汇总，分成员）
    rows = (db.query(ContributionEvent.user_id, func.sum(ContributionEvent.weight))
            .filter(ContributionEvent.dataset_id.in_(ds_ids or [-1]))
            .group_by(ContributionEvent.user_id)
            .order_by(func.sum(ContributionEvent.weight).desc()).all())
    contributions = [{"user_id": uid, "name": _uname(db, uid), "score": round(s or 0, 2)}
                     for uid, s in rows]
    post_ids = [p.id for p in db.query(Post).filter(
        Post.author_id.in_(member_ids or [-1])).all()]
    activity = {
        "datasets": len(ds_ids),
        "members": len(member_ids),
        "posts_total": db.query(Post).filter(Post.author_id.in_(member_ids or [-1])).count(),
        "comments_total": db.query(PostComment).filter(PostComment.post_id.in_(post_ids or [-1])).count(),
        "corrections_total": db.query(Bug).filter(Bug.dataset_id.in_(ds_ids or [-1])).count(),
        "code_total": db.query(CodeScript).filter(CodeScript.dataset_id.in_(ds_ids or [-1])).count(),
        "versions_30d": db.query(DataVersion).filter(
            DataVersion.dataset_id.in_(ds_ids or [-1]), DataVersion.release_date >= cutoff).count(),
    }
    recent = []
    for v in db.query(DataVersion).filter(DataVersion.dataset_id.in_(ds_ids or [-1])).order_by(
            DataVersion.id.desc()).limit(8).all():
        dd = db.get(Dataset, v.dataset_id)
        recent.append({"type": "version", "text": f"{dd.name_zh if dd else ''} 发布 {v.version_id}",
                       "at": str(v.release_date)[:10] if v.release_date else "", "sort": v.id})
    pending = {"join_requests": db.query(GroupJoinRequest).filter_by(
        group_id=g.id, status="pending").count()}
    return {"group": {"slug": g.slug, "name_zh": g.name_zh},
            "is_lead": is_group_lead(db, g.id, user),
            "contributions": contributions, "activity": activity,
            "recent": recent, "pending": pending}


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


PRIMARY_KEY = "primary_super_admin_uid"


def _primary_uid(db) -> int | None:
    from ..models.extras import PlatformSetting
    row = db.get(PlatformSetting, PRIMARY_KEY)
    try:
        return int(row.value) if row and row.value else None
    except (TypeError, ValueError):
        return None


def _set_primary(db, uid: int):
    from ..models.extras import PlatformSetting
    row = db.get(PlatformSetting, PRIMARY_KEY)
    if not row:
        row = PlatformSetting(key=PRIMARY_KEY); db.add(row)
    row.value = str(uid)


@router.get("/admin/super-admins")
def super_admins(db: Session = Depends(get_db), user: User = Depends(require_super_admin)):
    role = db.query(Role).filter_by(code="super_admin").first()
    if not role:
        return {"admins": [], "primary_uid": None, "i_am_primary": False}
    us = db.query(User).filter_by(role_id=role.id).all()
    primary = _primary_uid(db)
    # 若尚未指定总管理员，默认取最早的一位，避免无人可交接
    if primary is None and us:
        primary = min(u.id for u in us); _set_primary(db, primary); db.commit()
    return {"admins": [{"id": u.id, "username": u.username, "display_name": u.display_name,
                        "is_primary": u.id == primary} for u in us],
            "primary_uid": primary, "i_am_primary": user.id == primary}


@router.post("/admin/super-admins")
def grant_super(uid: int, db: Session = Depends(get_db),
                user: User = Depends(require_super_admin)):
    """新增一名（其他）总管理员。任一总管理员可添加。"""
    role = db.query(Role).filter_by(code="super_admin").first()
    target = db.get(User, uid)
    if not target:
        raise HTTPException(404, "用户不存在")
    target.role_id = role.id
    db.add(AuditLog(user_id=user.id, action="super_admin.grant", object_type="user",
                    object_id=str(uid), detail_json={}))
    db.commit()
    return {"ok": True}


@router.post("/admin/super-admins/transfer")
def transfer_primary(uid: int, db: Session = Depends(get_db),
                     user: User = Depends(require_super_admin)):
    """交接「平台总管理员」头衔给某用户（仅现任总管理员可操作）。

    目标若还不是总管理员，会一并授予总管理员身份；原总管理员降为「其他管理员」。
    """
    if _primary_uid(db) != user.id:
        raise HTTPException(403, "只有平台总管理员才能交接")
    target = db.get(User, uid)
    if not target:
        raise HTTPException(404, "用户不存在")
    role = db.query(Role).filter_by(code="super_admin").first()
    target.role_id = role.id           # 确保是总管理员
    _set_primary(db, uid)              # 头衔转给对方（原总管理员保留其他管理员身份）
    db.add(AuditLog(user_id=user.id, action="super_admin.transfer_primary",
                    object_type="user", object_id=str(uid), detail_json={}))
    db.commit()
    return {"ok": True}


@router.delete("/admin/super-admins/{uid}")
def revoke_super(uid: int, db: Session = Depends(get_db),
                 user: User = Depends(require_super_admin)):
    """撤销某人的总管理员身份（仅总管理员可操作，且不能撤销现任总管理员本人）。"""
    if _primary_uid(db) != user.id:
        raise HTTPException(403, "只有平台总管理员才能移除其他管理员")
    if uid == _primary_uid(db):
        raise HTTPException(400, "不能移除现任总管理员，请先交接")
    target = db.get(User, uid)
    if not target:
        raise HTTPException(404, "用户不存在")
    member = db.query(Role).filter_by(code="member").first()
    target.role_id = member.id if member else None
    db.add(AuditLog(user_id=user.id, action="super_admin.revoke", object_type="user",
                    object_id=str(uid), detail_json={}))
    db.commit()
    return {"ok": True}
