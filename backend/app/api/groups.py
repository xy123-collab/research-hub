from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..core.permissions import (get_current_user, is_super_admin, is_group_admin,
                                group_role, is_group_member, count_group_admins,
                                group_lead_id, is_group_lead, GROUP_ADMIN_ROLES,
                                GROUP_LEAD_ROLES)
from ..core.audit import write_audit
from ..core.naming import ensure_unique, normalize_name, gen_slug
from ..models.user import User
from ..models.group import (ResearchGroup, GroupMember, GroupJoinRequest, Charter,
                            ProjectResourceLink, ProjectTimelineEntry, ProjectFile)
from ..models.dataset import Dataset, DatasetMember, DatasetGroupRequest
from ..models.version import DataVersion
from ..models.community import Post
from ..schemas.models import GroupIn, DatasetIn

router = APIRouter(tags=["groups"])


@router.get("/groups")
def list_groups(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    mine_ids = {m.group_id for m in db.query(GroupMember)
                .filter_by(user_id=user.id, status="active").all()}
    # Project 是私密空间：列表只返回当前用户已参与的项目，不再提供“发现/申请加入”。
    all_groups = db.query(ResearchGroup).filter_by(is_deleted=False).all()

    def card(g):
        n_members = db.query(GroupMember).filter_by(group_id=g.id, status="active").count()
        n_datasets = db.query(Dataset).filter_by(group_id=g.id, is_deleted=False).count()
        return {"id": g.id, "slug": g.slug, "name_zh": g.name_zh, "name_en": g.name_en,
                "icon": g.icon, "desc_zh": g.desc_zh, "member_count": n_members,
                "dataset_count": n_datasets, "my_role": group_role(db, g.id, user.id)}

    mine = [card(g) for g in all_groups if g.id in mine_ids]
    return {"mine": mine, "discover": []}


@router.post("/groups")
def create_group(body: GroupIn, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    slug = (body.slug or "").strip() or gen_slug(db, ResearchGroup, "grp")
    if db.query(ResearchGroup).filter_by(slug=slug).first():
        raise HTTPException(400, "slug 已存在")
    ensure_unique(db, ResearchGroup, "name_zh", body.name_zh, "课题组名称",
                  extra_filter={"is_deleted": False})
    data = body.model_dump(); data["slug"] = slug
    data["discoverable"] = False
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
    if not is_member:
        raise HTTPException(403, "该研究项目为私密空间，仅受邀成员可访问")
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
    # 平台管理员也不绕过 Project 私密边界。
    n_members = db.query(GroupMember).filter_by(group_id=g.id, status="active").count()
    result["member_count"] = n_members
    members = db.query(GroupMember).filter_by(group_id=g.id, status="active").all()
    result["members"] = [{"user_id": m.user_id, "group_role": m.group_role,
                          "is_lead": m.user_id == lead_id,
                          "is_admin": m.group_role in GROUP_ADMIN_ROLES,
                          "name": (db.get(User, m.user_id).display_name
                                   if db.get(User, m.user_id) else "")}
                         for m in members]
    result["links"] = [{
        "id": x.id, "title": x.title, "url": x.url, "created_by": x.created_by
    } for x in db.query(ProjectResourceLink).filter_by(group_id=g.id)
        .order_by(ProjectResourceLink.id.desc()).all()]
    result["timeline"] = [{
        "id": x.id, "category": x.category, "title": x.title, "body": x.body,
        "file_name": x.file_name, "has_file": bool(x.file_path),
        "created_by": x.created_by,
        "author_name": (db.get(User, x.created_by).display_name
                        if db.get(User, x.created_by) else ""),
        "created_at": str(x.created_at) if x.created_at else None
    } for x in db.query(ProjectTimelineEntry).filter_by(group_id=g.id)
        .order_by(ProjectTimelineEntry.created_at.desc(),
                  ProjectTimelineEntry.id.desc()).all()]
    result["files"] = [{
        "id": x.id, "file_name": x.file_name, "size": x.size,
        "created_by": x.created_by,
        "author_name": (db.get(User, x.created_by).display_name
                        if db.get(User, x.created_by) else ""),
        "created_at": str(x.created_at) if x.created_at else None
    } for x in db.query(ProjectFile).filter_by(group_id=g.id)
        .order_by(ProjectFile.id.desc()).all()]
    return result


@router.post("/groups/{slug}/join-requests")
def join_group(slug: str, message: str = "", user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    raise HTTPException(410, "研究项目不开放申请加入，请联系研究项目总管理员/管理员邀请")


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
    g.discoverable = False
    write_audit(db, user.id, "group.edit", "group", g.id)
    db.commit()
    return {"ok": True}


@router.delete("/groups/{slug}")
def delete_group(slug: str, body: dict, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """课题组总管理员可永久下架空课题组；关联数据集必须先处理。"""
    g = _get_group(db, slug)
    if not is_group_lead(db, g.id, user):
        raise HTTPException(403, "仅课题组总管理员可删除课题组")
    if (body.get("confirmation") or "").strip() != (g.name_zh or "").strip():
        raise HTTPException(400, "二次确认失败：请完整输入课题组名称")
    linked = db.query(Dataset).filter_by(group_id=g.id, is_deleted=False).count()
    if linked:
        raise HTTPException(409, f"该课题组仍有 {linked} 个有效数据集；请先在各数据集申请移出或单独删除")
    g.discoverable = False
    g.is_deleted = True
    write_audit(db, user.id, "group.delete", "group", g.id,
                {"confirmation": "name_matched"})
    db.commit()
    return {"ok": True, "detail": "课题组已永久下架，审计记录保留"}


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


@router.post("/groups/{slug}/invite/{uid}")
def invite_project_member(slug: str, uid: int, user: User = Depends(get_current_user),
                          db: Session = Depends(get_db)):
    """Project Owner/Admin 从全平台检索后直接邀请；不再存在公开申请加入。"""
    g = _get_group(db, slug)
    if not is_group_admin(db, g.id, user):
        raise HTTPException(403, "仅研究项目总管理员/管理员可邀请成员")
    target = db.get(User, uid)
    if not target or target.status == "left":
        raise HTTPException(404, "用户不存在或账号已停用")
    m = db.query(GroupMember).filter_by(group_id=g.id, user_id=uid).first()
    if m:
        m.status = "active"
        m.group_role = m.group_role or "member"
        m.joined_at = m.joined_at or datetime.utcnow()
        m.approved_by = user.id
    else:
        db.add(GroupMember(group_id=g.id, user_id=uid, group_role="member",
                           status="active", joined_at=datetime.utcnow(),
                           approved_by=user.id))
    write_audit(db, user.id, "project.member.invite", "group", g.id, {"user": uid})
    db.commit()
    return {"ok": True}


def _project_member_guard(db: Session, slug: str, user: User) -> ResearchGroup:
    g = _get_group(db, slug)
    if not is_group_member(db, g.id, user):
        raise HTTPException(403, "仅研究项目成员可访问")
    return g


@router.post("/groups/{slug}/links")
def add_project_link(slug: str, title: str = Form(...), url: str = Form(...),
                     user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    g = _project_member_guard(db, slug, user)
    title, url = title.strip(), url.strip()
    if not title or not (url.startswith("https://") or url.startswith("http://")):
        raise HTTPException(400, "请填写标题及有效的 http(s) 链接")
    row = ProjectResourceLink(group_id=g.id, title=title, url=url, created_by=user.id)
    db.add(row); db.commit()
    return {"id": row.id}


@router.patch("/groups/{slug}/links/{lid}")
def edit_project_link(slug: str, lid: int, body: dict,
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    g = _project_member_guard(db, slug, user)
    row = db.get(ProjectResourceLink, lid)
    if not row or row.group_id != g.id:
        raise HTTPException(404, "链接不存在")
    title = (body.get("title") or "").strip()
    url = (body.get("url") or "").strip()
    if not title or not (url.startswith("https://") or url.startswith("http://")):
        raise HTTPException(400, "请填写标题及有效的 http(s) 链接")
    row.title, row.url = title, url
    db.commit()
    return {"ok": True}


@router.delete("/groups/{slug}/links/{lid}")
def delete_project_link(slug: str, lid: int, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    g = _project_member_guard(db, slug, user)
    row = db.get(ProjectResourceLink, lid)
    if row and row.group_id == g.id:
        db.delete(row); db.commit()
    return {"ok": True}


@router.post("/groups/{slug}/timeline")
def add_project_timeline(slug: str, category: str = Form("progress"),
                         title: str = Form(""), body: str = Form(""),
                         file: UploadFile | None = File(None),
                         user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    g = _project_member_guard(db, slug, user)
    if category not in {"progress", "discussion", "chart", "todo", "other"}:
        category = "other"
    if not title.strip() and not body.strip() and not getattr(file, "filename", ""):
        raise HTTPException(400, "请至少填写标题、内容或上传附件")
    meta = {}
    if file and file.filename:
        from ..services.uploads import save_upload
        meta = save_upload(file, f"project/{g.id}/timeline")
    row = ProjectTimelineEntry(group_id=g.id, category=category,
                               title=title.strip() or None, body=body.strip() or None,
                               created_by=user.id, **meta)
    db.add(row); db.commit()
    return {"id": row.id}


@router.get("/groups/{slug}/timeline/{eid}/file")
def project_timeline_file(slug: str, eid: int, user: User = Depends(get_current_user),
                          db: Session = Depends(get_db)):
    g = _project_member_guard(db, slug, user)
    row = db.get(ProjectTimelineEntry, eid)
    if not row or row.group_id != g.id or not row.file_path:
        raise HTTPException(404, "附件不存在")
    from ..services.uploads import open_stored_file, attachment_headers
    from ..services.downloads import log_download
    log_download(db, user_id=user.id, source="project_timeline",
                 file_name=row.file_name or "时间线附件", location_label=g.name_zh,
                 detail=row.title or "时间线", link=f"/groups/{g.slug}?tab=timeline")
    db.commit()
    return StreamingResponse(open_stored_file(row.file_path),
                             media_type=row.mime or "application/octet-stream",
                             headers=attachment_headers(row.file_name))


@router.post("/groups/{slug}/files")
def upload_project_file(slug: str, file: UploadFile = File(...),
                        user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    g = _project_member_guard(db, slug, user)
    from ..services.uploads import save_upload
    row = ProjectFile(group_id=g.id, created_by=user.id,
                      **save_upload(file, f"project/{g.id}/files"))
    db.add(row); db.commit()
    return {"id": row.id, "file_name": row.file_name}


@router.get("/groups/{slug}/files/{fid}/download")
def download_project_file(slug: str, fid: int, user: User = Depends(get_current_user),
                          db: Session = Depends(get_db)):
    g = _project_member_guard(db, slug, user)
    row = db.get(ProjectFile, fid)
    if not row or row.group_id != g.id:
        raise HTTPException(404, "文件不存在")
    from ..services.uploads import open_stored_file, attachment_headers
    from ..services.downloads import log_download
    log_download(db, user_id=user.id, source="project_file",
                 file_name=row.file_name, location_label=g.name_zh,
                 detail="项目文件", link=f"/groups/{g.slug}?tab=files")
    db.commit()
    return StreamingResponse(open_stored_file(row.file_path),
                             media_type=row.mime or "application/octet-stream",
                             headers=attachment_headers(row.file_name))


@router.delete("/groups/{slug}/files/{fid}")
def delete_project_file(slug: str, fid: int, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    g = _project_member_guard(db, slug, user)
    row = db.get(ProjectFile, fid)
    if row and row.group_id == g.id:
        from ..core.storage import storage
        try:
            storage.delete(row.file_path)
        except Exception:
            pass
        db.delete(row); db.commit()
    return {"ok": True}


@router.post("/groups/{slug}/datasets")
def create_dataset(slug: str, body: DatasetIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    g = db.query(ResearchGroup).filter_by(slug=slug, is_deleted=False).first()
    if not g:
        raise HTTPException(404, "课题组不存在")
    role = group_role(db, g.id, user.id)
    # 原则一 + 二：仅本组成员/管理员可在组内发起数据集；总管理员不因平台身份获得此权
    if role not in ("group_owner", "group_admin", "member"):
        raise HTTPException(403, "需先加入研究项目")
    ds_slug = (body.slug or "").strip() or gen_slug(db, Dataset, "ds")
    if db.query(Dataset).filter_by(slug=ds_slug).first():
        raise HTTPException(400, "数据集 slug 已存在")
    ensure_unique(db, Dataset, "name_zh", body.name_zh, "数据集名称",
                  extra_filter={"is_deleted": False})
    data = body.model_dump()
    data["slug"] = ds_slug
    data["founder_contact"] = data.get("founder_contact") or ""  # 列非空；联系方式已改为自动取总管理员邮箱
    d = Dataset(group_id=g.id, founder_id=user.id, is_public=False, **data)
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
    if not is_group_member(db, g.id, user):
        raise HTTPException(403, "该研究项目为私密空间，仅受邀成员可访问")
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
