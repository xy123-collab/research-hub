"""集中消息入口：按当前用户在各课题组/数据集的角色，实时聚合待办与状态变更。

不落 Notification 表，直接按当前数据状态计算，保证始终与真实待办一致。
- action 级（需要我处理，计入红点数）：
    成员加入审批（数据集/课题组）、下载申请审批、勘误终审、数据集归属审批
- info 级（与我相关的状态变更，不计红点）：
    我的加入/下载申请被通过或拒绝、我提交的勘误被采纳/拒绝/已修复
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..core.permissions import get_current_user, DS_ADMIN_ROLES
from ..models.user import User
from ..models.group import ResearchGroup, GroupMember, GroupJoinRequest
from ..models.dataset import Dataset, DatasetMember, JoinRequest, DatasetGroupRequest
from ..models.access import DownloadRequest
from ..models.correction import Bug

router = APIRouter(tags=["notifications"])


@router.get("/notifications")
def notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    items: list[dict] = []

    # 我管理的数据集 / 课题组
    ds_admin_ids = [m.dataset_id for m in db.query(DatasetMember).filter(
        DatasetMember.user_id == user.id,
        DatasetMember.ds_role.in_(DS_ADMIN_ROLES)).all()]
    grp_admin_ids = [m.group_id for m in db.query(GroupMember).filter_by(
        user_id=user.id, group_role="group_admin", status="active").all()]

    ds_map = {d.id: d for d in db.query(Dataset).filter(
        Dataset.id.in_(ds_admin_ids or [-1])).all()}
    grp_map = {g.id: g for g in db.query(ResearchGroup).filter(
        ResearchGroup.id.in_(grp_admin_ids or [-1])).all()}

    def uname(uid):
        u = db.get(User, uid)
        return u.display_name if u else f"用户#{uid}"

    # —— 数据集管理员的待办 ——
    if ds_admin_ids:
        for r in db.query(JoinRequest).filter(
                JoinRequest.dataset_id.in_(ds_admin_ids),
                JoinRequest.status == "pending").all():
            d = ds_map.get(r.dataset_id)
            items.append({"type": "dataset_join", "level": "action",
                          "title": "数据集加入申请",
                          "subtitle": f"{uname(r.user_id)} 申请加入「{d.name_zh if d else ''}」",
                          "link": f"/datasets/{d.slug}?tab=members" if d else "/",
                          "at": None, "sort": r.id})
        for r in db.query(DownloadRequest).filter(
                DownloadRequest.dataset_id.in_(ds_admin_ids),
                DownloadRequest.status == "pending").all():
            d = ds_map.get(r.dataset_id)
            items.append({"type": "download_request", "level": "action",
                          "title": "数据下载申请",
                          "subtitle": f"{uname(r.user_id)} 申请下载「{d.name_zh if d else ''}」",
                          "link": f"/datasets/{d.slug}?tab=members" if d else "/",
                          "at": str(r.created_at) if r.created_at else None, "sort": r.id})
        for b in db.query(Bug).filter(
                Bug.dataset_id.in_(ds_admin_ids), Bug.status == "pending").all():
            d = ds_map.get(b.dataset_id)
            items.append({"type": "correction_review", "level": "action",
                          "title": "勘误待终审",
                          "subtitle": f"「{d.name_zh if d else ''}」勘误 #{b.id} 等待审核",
                          "link": f"/datasets/{d.slug}?tab=bugs&bug={b.id}" if d else "/",
                          "at": None, "sort": b.id})

    # —— 课题组管理员的待办 ——
    if grp_admin_ids:
        for r in db.query(GroupJoinRequest).filter(
                GroupJoinRequest.group_id.in_(grp_admin_ids),
                GroupJoinRequest.status == "pending").all():
            g = grp_map.get(r.group_id)
            items.append({"type": "group_join", "level": "action",
                          "title": "课题组加入申请",
                          "subtitle": f"{uname(r.user_id)} 申请加入「{g.name_zh if g else ''}」",
                          "link": f"/groups/{g.slug}" if g else "/",
                          "at": None, "sort": r.id})
        for r in db.query(DatasetGroupRequest).filter(
                DatasetGroupRequest.group_id.in_(grp_admin_ids),
                DatasetGroupRequest.status == "pending").all():
            g = grp_map.get(r.group_id)
            d = db.get(Dataset, r.dataset_id)
            kind = "并入" if r.kind == "attach" else "移出"
            items.append({"type": "dataset_group_request", "level": "action",
                          "title": "数据集归属申请",
                          "subtitle": f"「{d.name_zh if d else ''}」申请{kind}课题组",
                          "link": f"/groups/{g.slug}" if g else "/",
                          "at": None, "sort": r.id})

    # —— 与我相关的状态变更（info，不计红点）——
    for r in db.query(JoinRequest).filter(
            JoinRequest.user_id == user.id,
            JoinRequest.status.in_(["approved", "rejected"])).order_by(
            JoinRequest.id.desc()).limit(8).all():
        d = db.get(Dataset, r.dataset_id)
        ok = r.status == "approved"
        items.append({"type": "my_dataset_join", "level": "info",
                      "title": "我的数据集加入申请" + ("已通过" if ok else "被拒绝"),
                      "subtitle": f"「{d.name_zh if d else ''}」",
                      "link": f"/datasets/{d.slug}" if d else "/",
                      "at": str(r.decided_at) if r.decided_at else None, "sort": r.id})
    for r in db.query(DownloadRequest).filter(
            DownloadRequest.user_id == user.id,
            DownloadRequest.status.in_(["approved", "rejected"])).order_by(
            DownloadRequest.id.desc()).limit(8).all():
        d = db.get(Dataset, r.dataset_id)
        ok = r.status == "approved"
        items.append({"type": "my_download", "level": "info",
                      "title": "我的下载申请" + ("已批准" if ok else "被拒绝"),
                      "subtitle": f"「{d.name_zh if d else ''}」",
                      "link": f"/datasets/{d.slug}?tab=versions" if d else "/",
                      "at": str(r.decided_at) if r.decided_at else None, "sort": r.id})
    for b in db.query(Bug).filter(
            Bug.reporter_id == user.id,
            Bug.status.in_(["accepted", "rejected", "fixed"])).order_by(
            Bug.id.desc()).limit(8).all():
        d = db.get(Dataset, b.dataset_id)
        label = {"accepted": "已采纳", "rejected": "被拒绝", "fixed": "已修复"}[b.status]
        items.append({"type": "my_correction", "level": "info",
                      "title": f"我的勘误{label}",
                      "subtitle": f"「{d.name_zh if d else ''}」勘误 #{b.id}",
                      "link": f"/datasets/{d.slug}?tab=bugs&bug={b.id}" if d else "/",
                      "at": str(b.reviewed_at) if b.reviewed_at else None, "sort": b.id})

    actions = [i for i in items if i["level"] == "action"]
    infos = [i for i in items if i["level"] == "info"]
    actions.sort(key=lambda x: (x["at"] or "", x["sort"]), reverse=True)
    infos.sort(key=lambda x: (x["at"] or "", x["sort"]), reverse=True)
    return {"action_count": len(actions), "items": actions + infos}
