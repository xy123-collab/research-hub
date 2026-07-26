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
                            ProjectTimelineEntry, ProjectFile, ProjectResourceLink)
from ..models.dataset import Dataset, DatasetMember, JoinRequest
from ..models.version import DataVersion, DownloadLog
from ..models.correction import Bug, CorrectionFinal
from ..models.code import CodeScript
from ..models.community import Post, PostComment, PostReaction
from ..models.governance import AuditLog, ContributionEvent
from ..models.governance import FeedbackTicket
from ..models.access import DownloadRequest
from ..models.notify import DownloadHistory
from ..models.curation import CodeVersion
from ..models.skill import Skill
from ..models.extras import CollabSection, SkillComment, PasswordResetToken
from ..models.authx import InviteCode, InviteCodeUse
from ..core.config import settings
from ..core.time import china_iso
from ..schemas.auth import InviteCodeIn, RegistrationSettingIn
from ..services import registration as reg
from ..services.scoring import leaderboard, by_dataset
from ..services.uploads import attachment_headers

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
        "downloaded_at": china_iso(row.downloaded_at),
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
                   row["location"], row["detail"],
                   row["downloaded_at"].replace("T", " ") if row["downloaded_at"] else ""])
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
                       "at": str(v.release_date) if v.release_date else "", "sort": v.id})
    for b in db.query(Bug).filter_by(dataset_id=d.id).order_by(Bug.id.desc()).limit(5).all():
        recent.append({"type": "bug", "text": f"勘误 #{b.id}（{b.status}）",
                       "at": str(b.reviewed_at) if b.reviewed_at else "", "sort": b.id})
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
                       "at": str(v.release_date) if v.release_date else "", "sort": v.id})
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

    def exact_action_count(actions, cutoff):
        return db.query(AuditLog).filter(
            AuditLog.created_at >= cutoff, AuditLog.action.in_(actions)).count()

    def from_query(name, query, time_col):
        return {"name": name,
                "week": query.filter(time_col >= week).count(),
                "month": query.filter(time_col >= month).count(),
                "source": "业务记录"}

    def from_audit(name, actions):
        return {"name": name, "week": exact_action_count(actions, week),
                "month": exact_action_count(actions, month), "source": "审计日志"}

    def combined(name, parts):
        return {"name": name, "week": sum(x["week"] for x in parts),
                "month": sum(x["month"] for x in parts),
                "source": "业务记录/审计日志" if any(
                    x["source"] == "审计日志" for x in parts) else "业务记录"}

    public_posts = db.query(Post).filter(Post.group_id.is_(None))
    public_post_ids = [x.id for x in public_posts.all()]
    internal_posts = db.query(Post).filter(Post.group_id.isnot(None))
    internal_post_ids = [x.id for x in internal_posts.all()]
    skill_parts = [
        from_query("", db.query(Skill), Skill.created_at),
        from_query("", db.query(SkillComment), SkillComment.created_at),
        from_query("", db.query(DownloadHistory).filter(
            DownloadHistory.source == "skill"), DownloadHistory.downloaded_at),
        from_audit("", ("skill.visibility", "skill.delete")),
    ]
    collab_parts = [
        from_query("", db.query(CollabSection).filter(
            CollabSection.kind == "generic"), CollabSection.created_at),
        from_audit("", ("collab_section.delete",)),
    ]
    modules_data = [
        ("account", "账号与安全", [
            from_audit("登录", ("login",)),
            from_query("注册", db.query(User), User.created_at),
            from_query("注销账号", db.query(User).filter(User.status == "left"), User.updated_at),
            from_query("修改密码", db.query(PasswordResetToken).filter(
                PasswordResetToken.used == True), PasswordResetToken.updated_at),
        ]),
        ("datasets", "数据集", [
            from_query("创建数据集", db.query(Dataset).filter(Dataset.group_id.is_(None)),
                       Dataset.created_at),
            from_query("版本库 · 发布数据版本", db.query(DataVersion), DataVersion.release_date),
            from_query("版本库 · 下载数据", db.query(DownloadHistory).filter(
                DownloadHistory.source == "dataset_version"), DownloadHistory.downloaded_at),
            from_query("原始数据勘误 · 提交勘误", db.query(Bug), Bug.created_at),
            from_query("原始数据勘误 · 终审勘误", db.query(CorrectionFinal),
                       CorrectionFinal.decided_at),
            from_query("处理代码库 · 提交代码", db.query(CodeScript), CodeScript.created_at),
            from_query("处理代码库 · 发布代码版本", db.query(CodeVersion), CodeVersion.created_at),
            from_query("处理代码库 · 下载代码", db.query(DownloadHistory).filter(
                DownloadHistory.source == "code"), DownloadHistory.downloaded_at),
            from_audit("成员与权限 · 权限管理", ("dataset.grant", "dataset.revoke",
                       "dataset.admin.add", "dataset.admin.remove")),
        ]),
        ("projects", "研究项目", [
            from_query("创建研究项目", db.query(ResearchGroup), ResearchGroup.created_at),
            from_audit("成员 · 邀请与管理", ("project.member.invite", "group.member.remove",
                       "group.admin.add", "group.admin.remove")),
            from_query("数据集 · 新建内部数据集", db.query(Dataset).filter(
                Dataset.group_id.isnot(None)), Dataset.created_at),
            from_query("Overleaf / 链接 · 上传链接", db.query(ProjectResourceLink),
                       ProjectResourceLink.created_at),
            from_query("时间线 · 上传时间线", db.query(ProjectTimelineEntry),
                       ProjectTimelineEntry.created_at),
            from_query("文件 · 上传文件", db.query(ProjectFile), ProjectFile.created_at),
            combined("内部讨论", [
                from_query("", internal_posts, Post.created_at),
                from_query("", db.query(PostComment).filter(
                    PostComment.post_id.in_(internal_post_ids or [-1])), PostComment.created_at),
            ]),
        ]),
        ("discussion", "研究讨论区", [
            from_query("发布讨论", public_posts, Post.created_at),
            from_audit("编辑或删除讨论", ("discussion.post.edit", "discussion.post.delete")),
            combined("评论与点赞", [
                from_query("", db.query(PostComment).filter(
                    PostComment.post_id.in_(public_post_ids or [-1])), PostComment.created_at),
                from_query("", db.query(PostReaction).filter(
                    PostReaction.post_id.in_(public_post_ids or [-1])), PostReaction.created_at),
            ]),
        ]),
        ("collab", "其他协作", [
            combined("Skill 共享 · 所有操作", skill_parts),
            combined("自建协作分区 · 所有操作", collab_parts),
        ]),
        ("feedback", "帮助与反馈", [
            from_query("提交反馈", db.query(FeedbackTicket), FeedbackTicket.created_at),
            from_query("处理工单", db.query(FeedbackTicket).filter(
                FeedbackTicket.handled_at.isnot(None)), FeedbackTicket.handled_at),
        ]),
    ]
    modules = []
    for key, name, children in modules_data:
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


# ==================== 注册准入：邀请码 + 邮箱验证 ====================
@router.get("/admin/registration")
def registration_settings(db: Session = Depends(get_db),
                          user: User = Depends(require_super_admin)):
    """注册策略现状 + 邀请码统计。只有平台总管理员/管理员能看。"""
    now = datetime.utcnow()
    rows = db.query(InviteCode).all()
    stat = {"total": len(rows), "available": 0, "used_up": 0, "expired": 0, "disabled": 0}
    for r in rows:
        stat[reg.code_state(r)] = stat.get(reg.code_state(r), 0) + 1
    return {"invite_only": reg.invite_only(db),
            "email_verify": reg.email_verify_mode(db),
            "email_verify_effective": reg.email_verify_required(db),
            "email_backend": settings.EMAIL_BACKEND,
            "email_backend_can_send": reg.email_backend_can_send(),
            "min_password_len": settings.MIN_PASSWORD_LEN,
            "invite_stat": stat, "now": now.isoformat(timespec="seconds")}


@router.patch("/admin/registration")
def update_registration(body: RegistrationSettingIn, db: Session = Depends(get_db),
                        user: User = Depends(require_super_admin)):
    reg.set_policy(db, invite_only_flag=body.invite_only, email_verify=body.email_verify)
    db.add(AuditLog(user_id=user.id, action="platform.registration.update",
                    object_type="platform", object_id="registration",
                    detail_json={"invite_only": body.invite_only,
                                 "email_verify": body.email_verify}))
    db.commit()
    return registration_settings(db=db, user=user)


@router.get("/admin/invite-codes")
def list_invite_codes(state: str = "", limit: int = 300, db: Session = Depends(get_db),
                      user: User = Depends(require_super_admin)):
    """邀请码列表（新的在前）。state 可选 available/used_up/expired/disabled。"""
    rows = (db.query(InviteCode).order_by(InviteCode.id.desc()).limit(max(1, min(limit, 1000))).all())
    uses = {}
    for u in db.query(InviteCodeUse).all():
        uses.setdefault(u.code_id, []).append({"user_id": u.user_id, "username": u.username,
                                               "used_at": u.used_at})
    out = []
    for r in rows:
        st = reg.code_state(r)
        if state and st != state:
            continue
        out.append({"id": r.id, "code": r.code, "batch_id": r.batch_id, "note": r.note,
                    "max_uses": r.max_uses, "used_count": r.used_count or 0,
                    "expires_at": r.expires_at, "is_active": r.is_active,
                    "state": st, "created_at": r.created_at,
                    "created_by": _uname(db, r.created_by) if r.created_by else "—",
                    "used_by": uses.get(r.id, [])})
    return out


@router.post("/admin/invite-codes")
def create_invite_codes(body: InviteCodeIn, db: Session = Depends(get_db),
                        user: User = Depends(require_super_admin)):
    """批量生成邀请码：指定数量、有效期（天）、每码可用次数、备注。"""
    rows = reg.generate_codes(db, count=body.count, valid_days=body.valid_days,
                              max_uses=body.max_uses, note=body.note or "",
                              created_by=user.id)
    codes = [r.code for r in rows]
    batch = rows[0].batch_id if rows else ""
    db.add(AuditLog(user_id=user.id, action="platform.invite_code.create",
                    object_type="invite_code", object_id=batch,
                    detail_json={"count": len(codes), "valid_days": body.valid_days,
                                 "max_uses": body.max_uses}))
    db.commit()
    return {"ok": True, "batch_id": batch, "codes": codes,
            "expires_at": rows[0].expires_at if rows else None}


@router.patch("/admin/invite-codes/{cid}")
def toggle_invite_code(cid: int, active: bool, db: Session = Depends(get_db),
                       user: User = Depends(require_super_admin)):
    """停用 / 恢复某个邀请码（不删除，保留核销记录便于追溯）。"""
    r = db.get(InviteCode, cid)
    if not r:
        raise HTTPException(404, "邀请码不存在")
    r.is_active = bool(active)
    db.add(AuditLog(user_id=user.id, action="platform.invite_code.toggle",
                    object_type="invite_code", object_id=r.code,
                    detail_json={"active": bool(active)}))
    db.commit()
    return {"ok": True, "state": reg.code_state(r)}


@router.post("/admin/invite-codes/disable-batch")
def disable_batch(batch_id: str, db: Session = Depends(get_db),
                  user: User = Depends(require_super_admin)):
    """整批停用（比如一批码发错了对象）。已经用掉的核销记录仍保留。"""
    n = (db.query(InviteCode).filter_by(batch_id=batch_id)
         .update({"is_active": False}, synchronize_session=False))
    db.add(AuditLog(user_id=user.id, action="platform.invite_code.disable_batch",
                    object_type="invite_code", object_id=batch_id,
                    detail_json={"count": n}))
    db.commit()
    return {"ok": True, "disabled": n}


@router.get("/admin/invite-codes.csv")
def export_invite_codes(batch_id: str = "", db: Session = Depends(get_db),
                        user: User = Depends(require_super_admin)):
    """导出邀请码 CSV（可按批次），方便逐个发给受邀人。"""
    q = db.query(InviteCode).order_by(InviteCode.id.desc())
    if batch_id:
        q = q.filter_by(batch_id=batch_id)
    lines = ["邀请码,状态,可用次数,已用次数,到期时间,备注,批次"]
    for r in q.all():
        lines.append(",".join([
            r.code, reg.code_state(r), str(r.max_uses or 1), str(r.used_count or 0),
            (china_iso(r.expires_at) or "").replace("T", " ") if r.expires_at else "长期有效",
            (r.note or "").replace(",", "，"), r.batch_id or ""]))
    buf = io.BytesIO(("﻿" + "\n".join(lines)).encode("utf-8"))   # BOM：Excel 打开不乱码
    return StreamingResponse(buf, media_type="text/csv",
                             headers=attachment_headers("invite_codes.csv"))
