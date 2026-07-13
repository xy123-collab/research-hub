from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..core.permissions import get_current_user, is_super_admin, is_group_admin, group_role
from ..core.audit import write_audit
from ..models.user import User
from ..models.group import ResearchGroup, GroupMember, GroupJoinRequest, Charter
from ..models.dataset import Dataset, DatasetMember, DatasetGroupRequest
from ..models.version import DataVersion
from ..models.community import Post
from ..schemas.models import GroupIn, DatasetIn

router = APIRouter(tags=["groups"])


@router.get("/groups")
def list_groups(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    mine_ids = {m.group_id for m in db.query(GroupMember)
                .filter_by(user_id=user.id, status="active").all()}
    all_groups = db.query(ResearchGroup).filter_by(is_deleted=False).all()

    def card(g):
        n_members = db.query(GroupMember).filter_by(group_id=g.id, status="active").count()
        n_datasets = db.query(Dataset).filter_by(group_id=g.id, is_deleted=False).count()
        return {"id": g.id, "slug": g.slug, "name_zh": g.name_zh, "name_en": g.name_en,
                "icon": g.icon, "desc_zh": g.desc_zh, "member_count": n_members,
                "dataset_count": n_datasets, "my_role": group_role(db, g.id, user.id)}

    mine = [card(g) for g in all_groups if g.id in mine_ids]
    discover = [card(g) for g in all_groups if g.id not in mine_ids and g.discoverable]
    return {"mine": mine, "discover": discover}


@router.post("/groups")
def create_group(body: GroupIn, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    if db.query(ResearchGroup).filter_by(slug=body.slug).first():
        raise HTTPException(400, "slug 已存在")
    g = ResearchGroup(**body.model_dump(), created_by=user.id)
    db.add(g); db.flush()
    # 创建者成为 group_admin（角色创建时产生）
    db.add(GroupMember(group_id=g.id, user_id=user.id, group_role="group_admin",
                       status="active", joined_at=datetime.utcnow(), approved_by=user.id))
    db.add(Charter(scope="group", ref_id=g.id, body_zh="（请课题组管理员编辑本组公约）",
                   version=1, updated_by=user.id))
    write_audit(db, user.id, "group.create", "group", g.id)
    db.commit()
    return {"id": g.id, "slug": g.slug}


@router.get("/groups/{slug}")
def group_detail(slug: str, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    g = db.query(ResearchGroup).filter_by(slug=slug, is_deleted=False).first()
    if not g:
        raise HTTPException(404, "课题组不存在")
    is_member = db.query(GroupMember).filter_by(
        group_id=g.id, user_id=user.id, status="active").first() is not None
    datasets = db.query(Dataset).filter_by(group_id=g.id, is_deleted=False).all()
    charter = db.query(Charter).filter_by(scope="group", ref_id=g.id).order_by(
        Charter.version.desc()).first()
    result = {"id": g.id, "slug": g.slug, "name_zh": g.name_zh, "name_en": g.name_en,
              "desc_zh": g.desc_zh, "icon": g.icon, "discoverable": g.discoverable,
              "is_member": is_member, "is_admin": is_group_admin(db, g.id, user),
              "charter": ({"id": charter.id, "body_zh": charter.body_zh,
                           "version": charter.version} if charter else None),
              "datasets": [{"id": d.id, "slug": d.slug, "name_zh": d.name_zh,
                            "icon": d.icon} for d in datasets]}
    # 非成员只见公开信息 + 成员数，不见成员名单明细
    n_members = db.query(GroupMember).filter_by(group_id=g.id, status="active").count()
    result["member_count"] = n_members
    if is_member or is_super_admin(user):
        members = db.query(GroupMember).filter_by(group_id=g.id, status="active").all()
        result["members"] = [{"user_id": m.user_id, "group_role": m.group_role}
                             for m in members]
    return result


@router.post("/groups/{slug}/join-requests")
def join_group(slug: str, message: str = "", user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    g = db.query(ResearchGroup).filter_by(slug=slug, is_deleted=False).first()
    if not g:
        raise HTTPException(404, "课题组不存在")
    if db.query(GroupMember).filter_by(group_id=g.id, user_id=user.id).first():
        raise HTTPException(400, "已是成员")
    req = GroupJoinRequest(group_id=g.id, user_id=user.id, message=message, status="pending")
    db.add(req); db.commit()
    return {"id": req.id, "status": "pending"}


@router.post("/group-join/{rid}/decide")
def decide_group_join(rid: int, approve: bool, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    req = db.get(GroupJoinRequest, rid)
    if not req:
        raise HTTPException(404, "申请不存在")
    if not is_group_admin(db, req.group_id, user):
        raise HTTPException(403, "需要课题组管理员")
    req.status = "approved" if approve else "rejected"
    req.decided_by = user.id; req.decided_at = datetime.utcnow()
    if approve:
        db.add(GroupMember(group_id=req.group_id, user_id=req.user_id, group_role="member",
                           status="active", joined_at=datetime.utcnow(), approved_by=user.id))
    write_audit(db, user.id, "group.join.decide", "group", req.group_id,
                {"approve": approve, "applicant": req.user_id})
    db.commit()
    return {"ok": True, "status": req.status}


@router.patch("/groups/{slug}")
def update_group(slug: str, body: GroupIn, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    g = db.query(ResearchGroup).filter_by(slug=slug).first()
    if not g:
        raise HTTPException(404, "课题组不存在")
    if not is_group_admin(db, g.id, user):
        raise HTTPException(403, "需要课题组管理员")
    for k, v in body.model_dump(exclude={"slug"}).items():
        setattr(g, k, v)
    db.commit()
    return {"ok": True}


@router.post("/groups/{slug}/datasets")
def create_dataset(slug: str, body: DatasetIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    g = db.query(ResearchGroup).filter_by(slug=slug, is_deleted=False).first()
    if not g:
        raise HTTPException(404, "课题组不存在")
    role = group_role(db, g.id, user.id)
    if not (is_super_admin(user) or role in ("group_admin", "member")):
        raise HTTPException(403, "需先加入课题组")
    if db.query(Dataset).filter_by(slug=body.slug).first():
        raise HTTPException(400, "数据集 slug 已存在")
    d = Dataset(group_id=g.id, founder_id=user.id, **body.model_dump())
    db.add(d); db.flush()
    # 发起人成为 founder
    db.add(DatasetMember(dataset_id=d.id, user_id=user.id, ds_role="founder",
                         joined_at=datetime.utcnow(), approved_by=user.id))
    db.add(Charter(scope="dataset", ref_id=d.id, body_zh="（请数据集发起人编辑本数据集公约）",
                   version=1, updated_by=user.id))
    from ..core.audit import record_contribution
    record_contribution(db, user.id, "dataset_founder", "dataset", d.id, d.id, weight=30)
    write_audit(db, user.id, "dataset.create", "dataset", d.id)
    db.commit()
    return {"id": d.id, "slug": d.slug}


# ---------- 组内动态（成员发帖 + 数据更新）----------
@router.get("/groups/{slug}/activity")
def group_activity(slug: str, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    g = db.query(ResearchGroup).filter_by(slug=slug, is_deleted=False).first()
    if not g:
        raise HTTPException(404, "课题组不存在")
    member_ids = [m.user_id for m in db.query(GroupMember)
                  .filter_by(group_id=g.id, status="active").all()]
    ds = db.query(Dataset).filter_by(group_id=g.id, is_deleted=False).all()
    ds_ids = [d.id for d in ds]
    ds_name = {d.id: d.name_zh for d in ds}
    ds_slug = {d.id: d.slug for d in ds}
    items = []
    for p in (db.query(Post).filter(Post.author_id.in_(member_ids or [-1]))
              .order_by(Post.id.desc()).limit(20).all()):
        if p.visibility == "private":
            continue
        u = db.get(User, p.author_id)
        items.append({"type": "post", "who": u.display_name if u else "",
                      "title": (p.content_zh or "")[:80], "ref": p.id,
                      "at": None, "sort": p.id})
    for v in (db.query(DataVersion).filter(DataVersion.dataset_id.in_(ds_ids or [-1]))
              .order_by(DataVersion.id.desc()).limit(20).all()):
        u = db.get(User, v.created_by)
        items.append({"type": "version", "who": u.display_name if u else "",
                      "title": f"{ds_name.get(v.dataset_id,'')} 发布 {v.version_id}",
                      "ref": ds_slug.get(v.dataset_id), "sort": v.id,
                      "at": str(v.release_date) if v.release_date else None})
    items.sort(key=lambda x: (x["at"] is not None, x["at"] or "", x["sort"]), reverse=True)
    return items[:25]


# ---------- 数据集归属申请（课题组管理员审批）----------
@router.get("/groups/{slug}/dataset-requests")
def list_dataset_requests(slug: str, user: User = Depends(get_current_user),
                          db: Session = Depends(get_db)):
    g = db.query(ResearchGroup).filter_by(slug=slug, is_deleted=False).first()
    if not g:
        raise HTTPException(404, "课题组不存在")
    if not is_group_admin(db, g.id, user):
        raise HTTPException(403, "需要课题组管理员")
    out = []
    for r in db.query(DatasetGroupRequest).filter_by(group_id=g.id, status="pending").all():
        d = db.get(Dataset, r.dataset_id)
        u = db.get(User, r.requested_by)
        out.append({"id": r.id, "kind": r.kind,
                    "dataset_name": d.name_zh if d else "", "dataset_slug": d.slug if d else "",
                    "requested_by": u.display_name if u else ""})
    return out


@router.post("/dataset-group-requests/{rid}/decide")
def decide_dataset_request(rid: int, approve: bool, user: User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    r = db.get(DatasetGroupRequest, rid)
    if not r or r.status != "pending":
        raise HTTPException(404, "申请不存在或已处理")
    if not is_group_admin(db, r.group_id, user):
        raise HTTPException(403, "需要课题组管理员")
    r.status = "approved" if approve else "rejected"
    r.decided_by = user.id; r.decided_at = datetime.utcnow()
    if approve:
        d = db.get(Dataset, r.dataset_id)
        if d:
            d.group_id = r.group_id if r.kind == "attach" else None
    write_audit(db, user.id, f"dataset.{r.kind}.decide", "dataset", r.dataset_id,
                {"approve": approve})
    db.commit()
    return {"ok": True, "status": r.status}
