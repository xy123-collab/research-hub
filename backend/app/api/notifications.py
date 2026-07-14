"""集中消息中心：按当前用户在各课题组/数据集的角色，实时聚合待办与状态变更。

不落 Notification 表，直接按当前数据状态计算，保证始终与真实待办一致。
消息分门别类（category）：
  todo     待我处理（计红点）：加入审批、下载审批、勘误终审、归属审批
  access   权限与身份：我的加入/下载申请结果、被设为管理员、加入的课题组
  interact 互动：我的帖子/代码被评论
  collab   协作：被拉入新的工作台
  publish  发布：我参与数据集的新版本/新代码、我课题组的新数据集

同一套 build_notifications 供「站内消息中心」与「每日邮件摘要」共用。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..core.permissions import get_current_user, DS_ADMIN_ROLES, GROUP_ADMIN_ROLES
from ..models.user import User
from ..models.group import ResearchGroup, GroupMember, GroupJoinRequest
from ..models.dataset import Dataset, DatasetMember, JoinRequest, DatasetGroupRequest
from ..models.access import DownloadRequest
from ..models.correction import Bug
from ..models.community import Post, PostComment
from ..models.code import CodeScript
from ..models.curation import CodeComment, CodeVersion
from ..models.version import DataVersion
from ..models.workspace import Workspace, WorkspaceMember

router = APIRouter(tags=["notifications"])

# 分类元信息：key -> (中文名, 圆点色)
CATEGORY_META = {
    "todo":     {"name": "待我处理", "color": "#c0392b"},
    "access":   {"name": "权限与身份", "color": "#2d4a7c"},
    "interact": {"name": "互动·评论", "color": "#a15c2b"},
    "collab":   {"name": "协作·工作台", "color": "#3f6f4f"},
    "publish":  {"name": "发布·数据与代码", "color": "#5b4b8a"},
}


def build_notifications(db: Session, user: User) -> dict:
    items: list[dict] = []

    def uname(uid):
        u = db.get(User, uid)
        return u.display_name if u else f"用户#{uid}"

    def add(**kw):
        kw.setdefault("at", None)
        items.append(kw)

    # 我管理的数据集 / 课题组
    ds_admin_ids = [m.dataset_id for m in db.query(DatasetMember).filter(
        DatasetMember.user_id == user.id,
        DatasetMember.ds_role.in_(DS_ADMIN_ROLES)).all()]
    grp_admin_ids = [m.group_id for m in db.query(GroupMember).filter(
        GroupMember.user_id == user.id, GroupMember.status == "active",
        GroupMember.group_role.in_(GROUP_ADMIN_ROLES)).all()]
    ds_map = {d.id: d for d in db.query(Dataset).filter(
        Dataset.id.in_(ds_admin_ids or [-1])).all()}
    grp_map = {g.id: g for g in db.query(ResearchGroup).filter(
        ResearchGroup.id.in_(grp_admin_ids or [-1])).all()}

    # ===== todo：待我处理（action，计红点）=====
    if ds_admin_ids:
        for r in db.query(JoinRequest).filter(
                JoinRequest.dataset_id.in_(ds_admin_ids),
                JoinRequest.status == "pending").all():
            d = ds_map.get(r.dataset_id)
            add(type="dataset_join", level="action", category="todo",
                title="数据集加入申请",
                subtitle=f"{uname(r.user_id)} 申请加入「{d.name_zh if d else ''}」",
                link=f"/datasets/{d.slug}?tab=access" if d else "/", sort=r.id)
        for r in db.query(DownloadRequest).filter(
                DownloadRequest.dataset_id.in_(ds_admin_ids),
                DownloadRequest.status == "pending").all():
            d = ds_map.get(r.dataset_id)
            add(type="download_request", level="action", category="todo",
                title="数据下载申请",
                subtitle=f"{uname(r.user_id)} 申请下载「{d.name_zh if d else ''}」",
                link=f"/datasets/{d.slug}?tab=access" if d else "/",
                at=str(r.created_at) if r.created_at else None, sort=r.id)
        for b in db.query(Bug).filter(
                Bug.dataset_id.in_(ds_admin_ids), Bug.status == "pending").all():
            d = ds_map.get(b.dataset_id)
            add(type="correction_review", level="action", category="todo",
                title="勘误待终审",
                subtitle=f"「{d.name_zh if d else ''}」勘误 #{b.id} 等待审核",
                link=f"/datasets/{d.slug}?tab=bugs&bug={b.id}" if d else "/", sort=b.id)
        from ..models.mapping import FileCorrection
        _fc_label = {"codebook": "codebook", "mapping": "对照表"}
        for r in db.query(FileCorrection).filter(
                FileCorrection.dataset_id.in_(ds_admin_ids),
                FileCorrection.status == "pending").all():
            d = ds_map.get(r.dataset_id)
            add(type="file_correction", level="action", category="todo",
                title=f"{_fc_label.get(r.target, r.target)}勘误待确认",
                subtitle=f"「{d.name_zh if d else ''}」有一条{_fc_label.get(r.target, r.target)}勘误待采纳",
                link=f"/datasets/{d.slug}?tab=versions" if d else "/",
                at=str(r.created_at) if r.created_at else None, sort=r.id)
        from ..models.extras import PermRequest
        from ..models.access import PERM_LABELS_ZH
        for r in db.query(PermRequest).filter(
                PermRequest.dataset_id.in_(ds_admin_ids),
                PermRequest.status == "pending").all():
            d = ds_map.get(r.dataset_id)
            add(type="perm_request", level="action", category="todo",
                title="权限申请待审批",
                subtitle=f"{uname(r.user_id)} 申请「{PERM_LABELS_ZH.get(r.perm, r.perm)}」",
                link=f"/datasets/{d.slug}?tab=access" if d else "/",
                at=str(r.created_at) if r.created_at else None, sort=r.id)
    if grp_admin_ids:
        for r in db.query(GroupJoinRequest).filter(
                GroupJoinRequest.group_id.in_(grp_admin_ids),
                GroupJoinRequest.status == "pending").all():
            g = grp_map.get(r.group_id)
            add(type="group_join", level="action", category="todo",
                title="课题组加入申请",
                subtitle=f"{uname(r.user_id)} 申请加入「{g.name_zh if g else ''}」",
                link=f"/groups/{g.slug}" if g else "/", sort=r.id)
        for r in db.query(DatasetGroupRequest).filter(
                DatasetGroupRequest.group_id.in_(grp_admin_ids),
                DatasetGroupRequest.status == "pending").all():
            g = grp_map.get(r.group_id)
            d = db.get(Dataset, r.dataset_id)
            kind = "并入" if r.kind == "attach" else "移出"
            add(type="dataset_group_request", level="action", category="todo",
                title="数据集归属申请",
                subtitle=f"「{d.name_zh if d else ''}」申请{kind}课题组",
                link=f"/groups/{g.slug}" if g else "/", sort=r.id)

    # ===== access：权限与身份（info）=====
    for r in db.query(JoinRequest).filter(
            JoinRequest.user_id == user.id,
            JoinRequest.status.in_(["approved", "rejected"])).order_by(
            JoinRequest.id.desc()).limit(8).all():
        d = db.get(Dataset, r.dataset_id); ok = r.status == "approved"
        add(type="my_dataset_join", level="info", category="access",
            title="数据集加入申请" + ("已通过" if ok else "被拒绝"),
            subtitle=f"「{d.name_zh if d else ''}」",
            link=f"/datasets/{d.slug}" if d else "/",
            at=str(r.decided_at) if r.decided_at else None, sort=r.id)
    for r in db.query(GroupJoinRequest).filter(
            GroupJoinRequest.user_id == user.id,
            GroupJoinRequest.status.in_(["approved", "rejected"])).order_by(
            GroupJoinRequest.id.desc()).limit(8).all():
        g = db.get(ResearchGroup, r.group_id); ok = r.status == "approved"
        add(type="my_group_join", level="info", category="access",
            title="课题组加入申请" + ("已通过" if ok else "被拒绝"),
            subtitle=f"「{g.name_zh if g else ''}」",
            link=f"/groups/{g.slug}" if g else "/",
            at=str(r.decided_at) if r.decided_at else None, sort=r.id)
    for r in db.query(DownloadRequest).filter(
            DownloadRequest.user_id == user.id,
            DownloadRequest.status.in_(["approved", "rejected"])).order_by(
            DownloadRequest.id.desc()).limit(8).all():
        d = db.get(Dataset, r.dataset_id); ok = r.status == "approved"
        add(type="my_download", level="info", category="access",
            title="下载申请" + ("已批准" if ok else "被拒绝"),
            subtitle=f"「{d.name_zh if d else ''}」",
            link=f"/datasets/{d.slug}?tab=versions" if d else "/",
            at=str(r.decided_at) if r.decided_at else None, sort=r.id)
    # 被设为管理员（当前身份提示）
    for m in db.query(DatasetMember).filter(
            DatasetMember.user_id == user.id,
            DatasetMember.ds_role.in_(DS_ADMIN_ROLES)).all():
        d = db.get(Dataset, m.dataset_id)
        add(type="ds_admin_role", level="info", category="access",
            title="你是数据集管理员",
            subtitle=f"「{d.name_zh if d else ''}」",
            link=f"/datasets/{d.slug}?tab=access" if d else "/", sort=m.dataset_id)
    for m in db.query(GroupMember).filter(
            GroupMember.user_id == user.id, GroupMember.status == "active",
            GroupMember.group_role.in_(GROUP_ADMIN_ROLES)).all():
        g = db.get(ResearchGroup, m.group_id)
        add(type="grp_admin_role", level="info", category="access",
            title="你是课题组管理员",
            subtitle=f"「{g.name_zh if g else ''}」",
            link=f"/groups/{g.slug}" if g else "/", sort=m.group_id)

    # ===== interact：我的帖子/代码被评论 =====
    my_post_ids = [p.id for p in db.query(Post).filter_by(author_id=user.id).all()]
    if my_post_ids:
        for c in db.query(PostComment).filter(
                PostComment.post_id.in_(my_post_ids),
                PostComment.user_id != user.id).order_by(
                PostComment.id.desc()).limit(10).all():
            add(type="post_comment", level="info", category="interact",
                title="你的帖子有新评论",
                subtitle=f"{uname(c.user_id)}：{(c.content or '')[:30]}",
                link="/feed",
                at=str(c.created_at) if c.created_at else None, sort=c.id)
    my_script_ids = [s.id for s in db.query(CodeScript).filter_by(author_id=user.id).all()]
    if my_script_ids:
        for c in db.query(CodeComment).filter(
                CodeComment.script_id.in_(my_script_ids),
                CodeComment.user_id != user.id).order_by(
                CodeComment.id.desc()).limit(10).all():
            sc = db.get(CodeScript, c.script_id)
            d = db.get(Dataset, sc.dataset_id) if sc else None
            add(type="code_comment", level="info", category="interact",
                title="你的代码有新评论",
                subtitle=f"{uname(c.user_id)}：{(c.content or '')[:30]}",
                link=f"/datasets/{d.slug}?tab=code" if d else "/",
                at=str(c.created_at) if c.created_at else None, sort=c.id)

    # ===== collab：被拉入新的工作台 =====
    for m in db.query(WorkspaceMember).filter_by(user_id=user.id).all():
        w = db.get(Workspace, m.workspace_id)
        if w and w.owner_id != user.id:
            add(type="ws_added", level="info", category="collab",
                title="你被加入了工作台",
                subtitle=f"「{w.title}」",
                link="/me?tab=ws", sort=w.id)

    # ===== publish：我参与数据集的新版本/新代码、我课题组的新数据集 =====
    my_ds_ids = [m.dataset_id for m in db.query(DatasetMember).filter_by(
        user_id=user.id).all()]
    my_grp_ids = [m.group_id for m in db.query(GroupMember).filter_by(
        user_id=user.id, status="active").all()]
    if my_ds_ids:
        for v in db.query(DataVersion).filter(
                DataVersion.dataset_id.in_(my_ds_ids),
                DataVersion.created_by != user.id).order_by(
                DataVersion.id.desc()).limit(10).all():
            d = db.get(Dataset, v.dataset_id)
            add(type="new_version", level="info", category="publish",
                title="数据集发布了新版本",
                subtitle=f"「{d.name_zh if d else ''}」{v.version_id}",
                link=f"/datasets/{d.slug}?tab=versions" if d else "/",
                at=str(v.release_date) if v.release_date else None, sort=v.id)
        for cv in db.query(CodeVersion).join(
                CodeScript, CodeScript.id == CodeVersion.script_id).filter(
                CodeScript.dataset_id.in_(my_ds_ids),
                CodeVersion.created_by != user.id).order_by(
                CodeVersion.id.desc()).limit(10).all():
            sc = db.get(CodeScript, cv.script_id)
            d = db.get(Dataset, sc.dataset_id) if sc else None
            add(type="new_code", level="info", category="publish",
                title="处理代码有新版本",
                subtitle=f"「{d.name_zh if d else ''}」{cv.version_label or ''}",
                link=f"/datasets/{d.slug}?tab=code" if d else "/",
                at=str(cv.created_at) if cv.created_at else None, sort=cv.id)
    if my_grp_ids:
        for d in db.query(Dataset).filter(
                Dataset.group_id.in_(my_grp_ids),
                Dataset.founder_id != user.id).order_by(
                Dataset.id.desc()).limit(10).all():
            add(type="new_group_dataset", level="info", category="publish",
                title="课题组发布了新数据集",
                subtitle=f"「{d.name_zh}」",
                link=f"/datasets/{d.slug}", sort=d.id)

    actions = [i for i in items if i["level"] == "action"]
    infos = [i for i in items if i["level"] == "info"]
    actions.sort(key=lambda x: (x.get("at") or "", x["sort"]), reverse=True)
    infos.sort(key=lambda x: (x.get("at") or "", x["sort"]), reverse=True)
    ordered = actions + infos

    # 按分类分组（保持 CATEGORY_META 顺序）
    groups = []
    for key, meta in CATEGORY_META.items():
        g_items = [i for i in ordered if i.get("category") == key]
        if g_items:
            groups.append({"key": key, "name": meta["name"], "color": meta["color"],
                           "count": len(g_items), "items": g_items})
    return {"action_count": len(actions), "items": ordered, "groups": groups,
            "category_meta": CATEGORY_META}


@router.get("/notifications")
def notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return build_notifications(db, user)
