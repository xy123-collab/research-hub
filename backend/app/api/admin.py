from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
import io
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from ..core.db import get_db
from ..core.permissions import (get_current_user, require_super_admin, is_group_admin,
                                is_group_lead, group_lead_id, is_dataset_admin,
                                is_dataset_lead, dataset_lead_id, is_super_admin,
                                GROUP_ADMIN_ROLES, DS_ADMIN_ROLES)
from ..models.user import User, Role
from ..models.group import (ResearchGroup, GroupMember, GroupJoinRequest,
                            ProjectTimelineEntry, ProjectFile)
from ..models.dataset import Dataset, DatasetMember, JoinRequest
from ..models.version import DataVersion, DownloadLog
from ..models.correction import Bug
from ..models.code import CodeScript
from ..models.community import Post, PostComment
from ..models.governance import AuditLog, ContributionEvent
from ..models.governance import FeedbackTicket
from ..models.access import DownloadRequest
from ..models.notify import DownloadHistory
from ..services.scoring import leaderboard, by_dataset

router = APIRouter(tags=["admin"])


def _uname(db, uid):
    u = db.get(User, uid)
    return u.display_name if u else f"用户#{uid}"


def _period_counts(query, time_col, now):
    return {
        "week": query.filter(time_col >= now - timedelta(days=7)).count(),
        "month": query.filter(time_col >= now - timedelta(days=30)).count(),
    }


def _download_rows(db, query, limit=200):
    labels = {
        "dataset_version": "数据版本", "code": "处理代码",
        "bug_attachment": "勘误附件", "post_attachment": "讨论附件",
        "project_file": "项目文件", "project_timeline": "时间线附件",
        "skill": "Skill",
    }
    return [{
        "id": row.id, "category": labels.get(row.source, row.source),
        "source": row.source, "user_id": row.user_id,
        "user_name": _uname(db, row.user_id), "file_name": row.file_name,
        "location": row.location_label, "detail": row.detail,
        "downloaded_at": str(row.downloaded_at),
    } for row in query.order_by(DownloadHistory.downloaded_at.desc()).limit(limit).all()]


def _scope_download_query(db, kind, slug, user):
    if kind == "dataset":
        d = db.query(Dataset).filter_by(slug=slug, is_deleted=False).first()
        if not d or not is_dataset_admin(db, d.id, user):
            raise HTTPException(403, "需要数据集管理员")
        return d.name_zh, db.query(DownloadHistory).filter(DownloadHistory.dataset_id == d.id)
    if kind == "group":
        g = db.query(ResearchGroup).filter_by(slug=slug, is_deleted=False).first()
        if not g or not is_group_admin(db, g.id, user):
            raise HTTPException(403, "需要研究项目管理员")
        ds_ids = [x.id for x in db.query(Dataset).filter_by(group_id=g.id, is_deleted=False).all()]
        return g.name_zh, db.query(DownloadHistory).filter(or_(
            DownloadHistory.dataset_id.in_(ds_ids or [-1]),
            DownloadHistory.link.like(f"/groups/{g.slug}%")))
    raise HTTPException(400, "不支持的管理范围")


@router.get("/admin/{kind}/{slug}/downloads.xlsx")
def export_scope_downloads(kind: str, slug: str, db: Session = Depends(get_db),
                           user: User = Depends(get_current_user)):
    """导出当前管理范围的全部下载留痕，不受前端当前筛选限制。"""
    name, query = _scope_download_query(db, kind, slug, user)
    rows = _download_rows(db, query, limit=1000000)
    from openpyxl import Workbook
    from ..services.uploads import attachment_headers
    wb = Workbook()
    ws = wb.active
    ws.title = "下载历史"
    ws.append(["类别", "用户ID", "用户名", "下载内容", "所在位置", "补充信息", "下载时间"])
    for row in rows:
        ws.append([row["category"], row["user_id"], row["user_name"], row["file_name"],
                   row["location"], row["detail"], row["downloaded_at"][:19]])
    ws.freeze_panes = "A2"
    widths = [16, 12, 18, 36, 28, 28, 22]
    for i, width in enumerate(widths, 1):
        ws.column_dimensions[chr(64 + i)].width = width
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"{slug}_download_history.xlsx"
    return StreamingResponse(buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=attachment_headers(filename))


def _feature(name, group, query, time_col, now):
    return {"name": name, "group": group, **_period_counts(query, time_col, now)}


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
    now = datetime.utcnow()
    cutoff = now - timedelta(days=30)
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
    ds_posts = db.query(Post).filter(Post.dataset_id == d.id)
    ds_post_ids = [x.id for x in ds_posts.all()]
    dh = db.query(DownloadHistory).filter(DownloadHistory.dataset_id == d.id)
    feature_activity = [
        _feature("版本库 · 发布数据版本", "内容上传", db.query(DataVersion).filter(
            DataVersion.dataset_id == d.id), DataVersion.release_date, now),
        _feature("处理代码库 · 提交代码", "内容上传", db.query(CodeScript).filter(
            CodeScript.dataset_id == d.id), CodeScript.created_at, now),
        _feature("原始数据勘误 · 提交勘误", "内容上传", db.query(Bug).filter(
            Bug.dataset_id == d.id), Bug.created_at, now),
        _feature("研究讨论区 · 发布讨论", "讨论互动", ds_posts, Post.created_at, now),
        _feature("研究讨论区 · 发表评论", "讨论互动", db.query(PostComment).filter(
            PostComment.post_id.in_(ds_post_ids or [-1])), PostComment.created_at, now),
    ]
    for source, label in [("dataset_version", "版本库 · 下载数据"),
                          ("code", "处理代码库 · 下载代码"),
                          ("bug_attachment", "原始数据勘误 · 下载附件"),
                          ("post_attachment", "研究讨论区 · 下载附件")]:
        feature_activity.append(_feature(label, "内容下载", dh.filter(
            DownloadHistory.source == source), DownloadHistory.downloaded_at, now))
    return {"dataset": {"slug": d.slug, "name_zh": d.name_zh},
            "is_lead": is_dataset_lead(db, d.id, user),
            "contributions": contributions, "activity": activity,
            "feature_activity": feature_activity,
            "download_history": _download_rows(db, dh, limit=100000),
            "recent": recent[:8], "pending": pending}


@router.get("/admin/groups/{slug}/console")
def group_console(slug: str, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    g = db.query(ResearchGroup).filter_by(slug=slug, is_deleted=False).first()
    if not g:
        raise HTTPException(404, "课题组不存在")
    if not is_group_admin(db, g.id, user):
        raise HTTPException(403, "需要课题组管理员")
    now = datetime.utcnow()
    cutoff = now - timedelta(days=30)
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
    group_posts = db.query(Post).filter(Post.group_id == g.id)
    group_post_ids = [x.id for x in group_posts.all()]
    dh = db.query(DownloadHistory).filter(or_(
        DownloadHistory.dataset_id.in_(ds_ids or [-1]),
        DownloadHistory.link.like(f"/groups/{g.slug}%")))
    feature_activity = [
        _feature("文件 · 上传项目文件", "内容上传", db.query(ProjectFile).filter(
            ProjectFile.group_id == g.id), ProjectFile.created_at, now),
        _feature("时间线 · 发布进展", "内容上传", db.query(ProjectTimelineEntry).filter(
            ProjectTimelineEntry.group_id == g.id), ProjectTimelineEntry.created_at, now),
        _feature("数据集 · 发布数据版本", "内容上传", db.query(DataVersion).filter(
            DataVersion.dataset_id.in_(ds_ids or [-1])), DataVersion.release_date, now),
        _feature("数据集 · 提交处理代码", "内容上传", db.query(CodeScript).filter(
            CodeScript.dataset_id.in_(ds_ids or [-1])), CodeScript.created_at, now),
        _feature("内部讨论 · 发布讨论", "讨论互动", group_posts, Post.created_at, now),
        _feature("内部讨论 · 发表评论", "讨论互动", db.query(PostComment).filter(
            PostComment.post_id.in_(group_post_ids or [-1])), PostComment.created_at, now),
    ]
    for source, label in [("dataset_version", "数据集 · 下载数据"),
                          ("code", "数据集 · 下载处理代码"),
                          ("post_attachment", "内部讨论 · 下载附件"),
                          ("project_file", "文件 · 下载项目文件"),
                          ("project_timeline", "时间线 · 下载附件")]:
        feature_activity.append(_feature(label, "内容下载", dh.filter(
            DownloadHistory.source == source), DownloadHistory.downloaded_at, now))
    return {"group": {"slug": g.slug, "name_zh": g.name_zh},
            "is_lead": is_group_lead(db, g.id, user),
            "contributions": contributions, "activity": activity,
            "feature_activity": feature_activity,
            "download_history": _download_rows(db, dh, limit=100000),
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


@router.get("/admin/platform-analytics")
def platform_analytics(db: Session = Depends(get_db),
                       user: User = Depends(require_super_admin)):
    """平台运营元数据汇总，不返回私有 Project/Dataset 内容。"""
    now = datetime.utcnow()
    week = now - timedelta(days=7)
    month = now - timedelta(days=30)

    def active_since(cutoff):
        return (db.query(func.count(func.distinct(AuditLog.user_id)))
                .filter(AuditLog.created_at >= cutoff, AuditLog.user_id.isnot(None)).scalar() or 0)

    # 标题与前台现有功能保持一致；数值直接来自 audit_log，不生成模拟数据。
    module_specs = [
        ("account", "账号与安全", [
            ("登录", ("login",)),
            ("注册", ("account.register",)),
            ("注销账号", ("account.deactivate",)),
            ("修改密码", ("account.password.reset",)),
        ]),
        ("datasets", "数据集", [
            ("创建数据集", ("dataset.create", "dataset.create_standalone")),
            ("版本库 · 发布数据版本", ("version.publish",)),
            ("版本库 · 下载数据", ("download",)),
            ("原始数据勘误 · 提交勘误", ("bug.submit", "bug.submit.batch")),
            ("原始数据勘误 · 终审勘误", ("bug.finalize", "bug.item.finalize")),
            ("处理代码库 · 提交代码", ("code.add", "code.upload")),
            ("处理代码库 · 发布代码版本", ("code.version.publish",)),
            ("处理代码库 · 下载代码", ("code.download",)),
            ("成员与权限 · 权限管理", ("dataset.grant", "dataset.revoke",
                                  "dataset.admin.add", "dataset.admin.remove")),
        ]),
        ("projects", "研究项目", [
            ("创建研究项目", ("group.create",)),
            ("成员 · 邀请与管理", ("project.member.invite", "group.member.remove",
                              "group.admin.add", "group.admin.remove")),
            ("数据集 · 新建内部数据集", ("project.dataset.create",)),
            ("Overleaf / 链接 · 上传链接", ("project.link.add",)),
            ("时间线 · 上传时间线", ("project.timeline.add",)),
            ("文件 · 上传文件", ("project.file.upload",)),
            ("内部讨论", ("project.discussion.post.create",
                      "project.discussion.comment.create")),
        ]),
        ("discussion", "研究讨论区", [
            ("发布讨论", ("discussion.post.create",)),
            ("编辑或删除讨论", ("discussion.post.edit", "discussion.post.delete")),
            ("评论与点赞", ("discussion.comment.create", "discussion.reaction")),
        ]),
        ("collab", "其他协作", [
            ("Skill 共享 · 所有操作", ("skill.create", "skill.download", "skill.comment",
                                  "skill.visibility", "skill.delete")),
            ("自建协作分区 · 所有操作", ("collab_section.create",
                                  "collab_section.delete")),
        ]),
        ("feedback", "帮助与反馈", [
            ("提交反馈", ("feedback.submit",)),
            ("处理工单", ("feedback.update",)),
        ]),
    ]

    def exact_action_count(actions, cutoff):
        return db.query(AuditLog).filter(
            AuditLog.created_at >= cutoff, AuditLog.action.in_(actions)).count()

    modules = []
    for key, name, specs in module_specs:
        children = [{"name": child_name,
                     "week": exact_action_count(actions, week),
                     "month": exact_action_count(actions, month)}
                    for child_name, actions in specs]
        modules.append({"key": key, "name": name, "features": children,
                        "week": sum(x["week"] for x in children),
                        "month": sum(x["month"] for x in children)})

    daily = []
    for offset in range(29, -1, -1):
        start = (now - timedelta(days=offset)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        count = (db.query(func.count(func.distinct(AuditLog.user_id)))
                 .filter(AuditLog.created_at >= start, AuditLog.created_at < end,
                         AuditLog.user_id.isnot(None)).scalar() or 0)
        daily.append({"date": start.strftime("%m-%d"), "active_users": count})

    return {
        "overview": {
            "users": db.query(User).count(),
            "projects": db.query(ResearchGroup).filter_by(is_deleted=False).count(),
            "datasets": db.query(Dataset).filter_by(is_deleted=False).count(),
            "wau": active_since(week), "mau": active_since(month),
            "open_feedback": db.query(FeedbackTicket).filter(
                FeedbackTicket.status.in_(["pending", "processing", "waiting_user"])).count(),
        },
        "modules": modules,
        "daily_active": daily,
        "audit_actions_7d": db.query(AuditLog).filter(AuditLog.created_at >= week).count(),
        "audit_actions_30d": db.query(AuditLog).filter(AuditLog.created_at >= month).count(),
    }


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
