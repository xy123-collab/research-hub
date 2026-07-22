from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..core.permissions import (get_current_user, is_super_admin, is_group_admin,
                                group_role, is_group_member, count_group_admins,
                                group_lead_id, is_group_lead, GROUP_ADMIN_ROLES,
                                GROUP_LEAD_ROLES)
from ..core.audit import write_audit
from ..core.naming import ensure_unique, normalize_name, gen_slug
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
    slug = (body.slug or "").strip() or gen_slug(db, ResearchGroup, "grp")
    if db.query(ResearchGroup).filter_by(slug=slug).first():
        raise HTTPException(400, "slug 已存在")
    ensure_unique(db, ResearchGroup, "name_zh", body.name_zh, "课题组名称",
                  extra_filter={"is_deleted": False})
    data = body.model_dump(); data["slug"] = slug
    g = ResearchGroup(**data, created_by=user.id)
    db.add(g); db.flush()
    # 创建者成为课题组总管理员（group_owner）
    db.add(GroupMember(group_id=g.id, user_id=user.id, group_role="group_owner",
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
    lead_id = group_lead_id(db, g.id)
    # 「负责人」永远指向当前总管理员：转让后自动更换；联系方式默认取其注册邮箱
    lead_user = db.get(User, lead_id) if lead_id else None
    result = {"id": g.id, "slug": g.slug, "name_zh": g.name_zh, "name_en": g.name_en,
              "desc_zh": g.desc_zh, "icon": g.icon, "discoverable": g.discoverable,
              "is_member": is_member, "is_admin": is_group_admin(db, g.id, user),
              "is_lead": lead_id == user.id, "lead_id": lead_id,
              "founder": {"id": lead_id, "name": lead_user.display_name if lead_user else "",
                          "contact": (lead_user.email if lead_user else "") or ""},
              "charter": ({"id": charter.id, "body_zh": charter.body_zh,
                           "version": charter.version} if charter else None),
              "datasets": [{"id": d.id, "slug": d.slug, "name_zh": d.name_zh,
                            "icon": d.icon} for d in datasets]}
    # 非成员只见公开信息 + 成员数，不见成员名单明细
    # 原则一：总管理员不因平台身份自动查看课题组内部（此处不给 super_admin 开口子）
    n_members = db.query(GroupMember).filter_by(group_id=g.id, status="active").count()
    result["member_count"] = n_members
    if is_member:
        members = db.query(GroupMember).filter_by(group_id=g.id, status="active").all()
        result["members"] = [{"user_id": m.user_id, "group_role": m.group_role,
                              "is_lead": m.user_id == lead_id,
                              "is_admin": m.group_role in GROUP_ADMIN_ROLES,
                              "name": (db.get(User, m.user_id).display_name
                                       if db.get(User, m.user_id) else "")}
                             for m in members]
    if result["is_admin"]:
        pend = db.query(GroupJoinRequest).filter_by(group_id=g.id, status="pending").all()
        result["join_requests"] = [
            {"id": r.id, "user_id": r.user_id, "message": r.message,
             "name": (db.get(User, r.user_id).display_name
                      if db.get(User, r.user_id) else "")} for r in pend]
    return result


@router.post("/groups/{slug}/join-requests")
def join_group(slug: str, message: str = "", user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    g = db.query(ResearchGroup).filter_by(slug=slug, is_deleted=False).first()
    if not g:
        raise HTTPException(404, "课题组不存在")
    if db.query(GroupMember).filter_by(group_id=g.id, user_id=user.id).first():
        raise HTTPException(400, "已是成员")
    if db.query(GroupJoinRequest).filter_by(group_id=g.id, user_id=user.id,
                                            status="pending").first():
        raise HTTPException(400, "已提交申请，等待审批")
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
    if body.name_zh and normalize_name(body.name_zh) != normalize_name(g.name_zh):
        ensure_unique(db, ResearchGroup, "name_zh", body.name_zh, "课题组名称",
                      exclude_id=g.id, extra_filter={"is_deleted": False})
    for k, v in body.model_dump(exclude={"slug"}).items():
        setattr(g, k, v)
    write_audit(db, user.id, "group.edit", "group", g.id)
    db.commit()
    return {"ok": True}


def _get_group(db, slug):
    g = db.query(ResearchGroup).filter_by(slug=slug, is_deleted=False).first()
    if not g:
        raise HTTPException(404, "课题组不存在")
    return g


# ---------- 课题组成员/管理员管理（三节 2、五节 3）----------
@router.get("/groups/{slug}/join-requests")
def group_join_requests(slug: str, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    g = _get_group(db, slug)
    if not is_group_admin(db, g.id, user):
        raise HTTPException(403, "需要课题组管理员")
    out = []
    for r in db.query(GroupJoinRequest).filter_by(group_id=g.id, status="pending").all():
        u = db.get(User, r.user_id)
        out.append({"id": r.id, "user_id": r.user_id, "message": r.message,
                    "name": u.display_name if u else ""})
    return out


@router.post("/groups/{slug}/admins/{uid}")
def add_group_admin(slug: str, uid: int, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    g = _get_group(db, slug)
    if not is_group_lead(db, g.id, user):
        raise HTTPException(403, "仅课题组总管理员可设置管理员")
    m = db.query(GroupMember).filter_by(group_id=g.id, user_id=uid, status="active").first()
    if not m:
        raise HTTPException(404, "该用户不是本组成员")
    if m.group_role in GROUP_LEAD_ROLES:
        raise HTTPException(400, "该用户已是总管理员")
    m.group_role = "group_admin"
    write_audit(db, user.id, "group.admin.add", "group", g.id, {"user": uid})
    db.commit()
    return {"ok": True}


@router.delete("/groups/{slug}/admins/{uid}")
def remove_group_admin(slug: str, uid: int, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    g = _get_group(db, slug)
    if not is_group_lead(db, g.id, user):
        raise HTTPException(403, "仅课题组总管理员可取消管理员")
    m = db.query(GroupMember).filter_by(group_id=g.id, user_id=uid, status="active").first()
    if not m or m.group_role not in GROUP_ADMIN_ROLES:
        raise HTTPException(404, "该用户不是课题组管理员")
    if m.group_role in GROUP_LEAD_ROLES:
        raise HTTPException(400, "不能取消总管理员本人；请先把总管理员转让给他人")
    m.group_role = "member"
    write_audit(db, user.id, "group.admin.remove", "group", g.id, {"user": uid})
    db.commit()
    return {"ok": True}


@router.post("/groups/{slug}/transfer-lead/{uid}")
def transfer_group_lead(slug: str, uid: int, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """把「课题组总管理员」转让给另一名成员；原总管理员降为普通管理员。"""
    g = _get_group(db, slug)
    if not is_group_lead(db, g.id, user):
        raise HTTPException(403, "仅课题组总管理员可转让")
    if uid == user.id:
        raise HTTPException(400, "不能转让给自己")
    target = db.query(GroupMember).filter_by(group_id=g.id, user_id=uid, status="active").first()
    if not target:
        raise HTTPException(404, "该用户不是本组成员")
    me = db.query(GroupMember).filter_by(group_id=g.id, user_id=user.id, status="active").first()
    target.group_role = "group_owner"
    if me:
        me.group_role = "group_admin"
    write_audit(db, user.id, "group.lead.transfer", "group", g.id, {"to": uid})
    db.commit()
    return {"ok": True}


@router.delete("/groups/{slug}/members/{uid}")
def remove_group_member(slug: str, uid: int, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    g = _get_group(db, slug)
    if not is_group_admin(db, g.id, user):
        raise HTTPException(403, "需要课题组管理员")
    m = db.query(GroupMember).filter_by(group_id=g.id, user_id=uid, status="active").first()
    if not m:
        raise HTTPException(404, "该用户不是本组成员")
    if m.group_role in GROUP_LEAD_ROLES:
        raise HTTPException(400, "不能移除总管理员；请先转让总管理员身份")
    db.delete(m)
    write_audit(db, user.id, "group.member.remove", "group", g.id, {"user": uid})
    db.commit()
    return {"ok": True}


@router.post("/groups/{slug}/datasets")
def create_dataset(slug: str, body: DatasetIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    g = db.query(ResearchGroup).filter_by(slug=slug, is_deleted=False).first()
    if not g:
        raise HTTPException(404, "课题组不存在")
    role = group_role(db, g.id, user.id)
    # 原则一 + 二：仅本组成员/管理员可在组内发起数据集；总管理员不因平台身份获得此权
    if role not in ("group_admin", "member"):
        raise HTTPException(403, "需先加入课题组")
    ds_slug = (body.slug or "").strip() or gen_slug(db, Dataset, "ds")
    if db.query(Dataset).filter_by(slug=ds_slug).first():
        raise HTTPException(400, "数据集 slug 已存在")
    ensure_unique(db, Dataset, "name_zh", body.name_zh, "数据集名称",
                  extra_filter={"is_deleted": False})
    data = body.model_dump()
    data["slug"] = ds_slug
    data["founder_contact"] = data.get("founder_contact") or ""  # 列非空；联系方式已改为自动取总管理员邮箱
    d = Dataset(group_id=g.id, founder_id=user.id, **data)
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
        _ptitle = (p.title or p.content_zh or "")[:80]
        items.append({"type": "post", "who": u.display_name if u else "",
                      "title": _ptitle, "ref": p.id,
                      "at": str(p.created_at) if getattr(p, "created_at", None) else None,
                      "sort": p.id})
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
