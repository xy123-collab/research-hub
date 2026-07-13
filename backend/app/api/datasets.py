from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..core.storage import storage
from ..core.ai_client import ai_client
from ..core.permissions import (get_current_user, is_super_admin, is_dataset_member,
                                is_dataset_admin, dataset_membership, has_dataset_perm)
from ..core.audit import write_audit, record_contribution
from ..models.user import User
from ..models.dataset import (Dataset, DatasetMember, JoinRequest, Variable,
                              DatasetGroupRequest)
from ..models.version import DataVersion, DownloadLog
from ..models.literature import (LitTopic, LitRef, Publication, DatasetSummary)
from ..models.group import ResearchGroup, Charter
from ..models.correction import Bug
from ..models.code import CodeScript
from ..models.governance import VerifyFlag
from ..schemas.models import VersionIn, LitRefIn, DatasetIn

router = APIRouter(tags=["datasets"])


def _get_ds(db, slug) -> Dataset:
    d = db.query(Dataset).filter_by(slug=slug, is_deleted=False).first()
    if not d:
        raise HTTPException(404, "数据集不存在")
    return d


def _ds_card(db, d, user):
    """首页/发现页用的数据集卡片：带课题组、当前版本、协作活跃度信号（只读）。"""
    n = db.query(DatasetMember).filter_by(dataset_id=d.id).count()
    g = db.get(ResearchGroup, d.group_id) if d.group_id else None
    cur = db.query(DataVersion).filter_by(dataset_id=d.id, is_current=True).first()
    pending = db.query(Bug).filter_by(dataset_id=d.id, status="pending").count()
    open_flags = db.query(VerifyFlag).filter_by(dataset_id=d.id, status="open").count()
    m = dataset_membership(db, d.id, user.id)
    return {"id": d.id, "slug": d.slug, "name_zh": d.name_zh, "name_en": d.name_en,
            "icon": d.icon, "desc_zh": d.desc_zh, "group_id": d.group_id,
            "group_name": g.name_zh if g else "", "group_slug": g.slug if g else "",
            "member_count": n, "is_sensitive": d.is_sensitive,
            "current_version": cur.version_id if cur else None,
            "pending_bugs": pending, "open_flags": open_flags,
            "is_member": m is not None, "my_role": m.ds_role if m else None}


@router.get("/datasets")
def wall(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """全平台公开数据集墙（发现用）。字段向后兼容，仅新增协作信号。"""
    return [_ds_card(db, d, user) for d in
            db.query(Dataset).filter_by(is_deleted=False, is_public=True).all()]


def _recent_events(db, d):
    """数据集近期消息：最新版本 + 最新勘误，供首页直观展示。"""
    ev = []
    v = db.query(DataVersion).filter_by(dataset_id=d.id).order_by(DataVersion.id.desc()).first()
    if v:
        ev.append({"type": "version", "text": f"发布 {v.version_id}",
                   "at": str(v.release_date)[:10] if v.release_date else ""})
    b = db.query(Bug).filter_by(dataset_id=d.id).order_by(Bug.id.desc()).first()
    if b:
        ev.append({"type": "bug", "text": f"勘误 #{b.id}（{b.status}）",
                   "at": str(b.reviewed_at)[:10] if b.reviewed_at else ""})
    return ev


@router.get("/datasets/mine")
def my_datasets(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """我参与（成员/维护者/发起人）的数据集，按待办协作量排序，供首页直达协作。"""
    ds_ids = [m.dataset_id for m in
              db.query(DatasetMember).filter_by(user_id=user.id).all()]
    cards = []
    for d in db.query(Dataset).filter(Dataset.id.in_(ds_ids or [-1]),
                                       Dataset.is_deleted == False).all():
        card = _ds_card(db, d, user)
        card["recent"] = _recent_events(db, d)
        cards.append(card)
    cards.sort(key=lambda c: (c["pending_bugs"] + c["open_flags"]), reverse=True)
    return cards


@router.post("/datasets")
def create_standalone_dataset(body: DatasetIn, db: Session = Depends(get_db),
                              user: User = Depends(get_current_user)):
    """独立创建数据集（不归属任何课题组）。创建者即发起人/数据集管理员。"""
    if db.query(Dataset).filter_by(slug=body.slug).first():
        raise HTTPException(400, "数据集 slug 已存在")
    d = Dataset(group_id=None, founder_id=user.id, **body.model_dump())
    db.add(d); db.flush()
    db.add(DatasetMember(dataset_id=d.id, user_id=user.id, ds_role="founder",
                         joined_at=datetime.utcnow(), approved_by=user.id))
    db.add(Charter(scope="dataset", ref_id=d.id,
                   body_zh="（请数据集发起人编辑本数据集公约）", version=1, updated_by=user.id))
    record_contribution(db, user.id, "dataset_founder", "dataset", d.id, d.id, weight=30)
    write_audit(db, user.id, "dataset.create_standalone", "dataset", d.id)
    db.commit()
    return {"id": d.id, "slug": d.slug}


@router.get("/datasets/{slug}/activity")
def dataset_activity(slug: str, kind: str = "all", db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """更新记录时间线：版本发布 / 勘误 / 处理代码，可用 kind 过滤（all|version|bug|code）。"""
    d = _get_ds(db, slug)
    items = []
    if kind in ("all", "version"):
        for v in db.query(DataVersion).filter_by(dataset_id=d.id).all():
            items.append({"type": "version", "title": f"发布版本 {v.version_id}",
                          "detail": v.changelog_zh or "", "ref": v.version_id,
                          "at": str(v.release_date) if v.release_date else None, "sort": v.id})
    if kind in ("all", "bug"):
        for b in db.query(Bug).filter_by(dataset_id=d.id).all():
            items.append({"type": "bug", "title": f"勘误 #{b.id}（{b.status}）",
                          "detail": b.description_zh or "", "ref": b.id,
                          "at": str(b.reviewed_at) if b.reviewed_at else None, "sort": b.id})
    if kind in ("all", "code"):
        for c in db.query(CodeScript).filter_by(dataset_id=d.id).all():
            items.append({"type": "code", "title": f"处理代码 {c.filename}",
                          "detail": c.title_zh or "", "ref": c.id, "at": None, "sort": c.id})
    items.sort(key=lambda x: (x["at"] is not None, x["at"] or "", x["sort"]), reverse=True)
    return items


@router.post("/datasets/{slug}/attach-request")
def attach_request(slug: str, group_slug: str, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """数据集管理员申请把（独立）数据集并入某课题组，待该组管理员审批。"""
    d = _get_ds(db, slug)
    if not is_dataset_admin(db, d.id, user):
        raise HTTPException(403, "仅数据集发起人/管理员可申请归属")
    if d.group_id:
        raise HTTPException(400, "数据集已归属某课题组，请先申请移出")
    g = db.query(ResearchGroup).filter_by(slug=group_slug, is_deleted=False).first()
    if not g:
        raise HTTPException(404, "课题组不存在")
    if db.query(DatasetGroupRequest).filter_by(dataset_id=d.id, status="pending").first():
        raise HTTPException(400, "已有待处理的归属申请")
    r = DatasetGroupRequest(dataset_id=d.id, group_id=g.id, kind="attach",
                            requested_by=user.id, status="pending", created_at=datetime.utcnow())
    db.add(r); db.commit()
    return {"id": r.id, "status": "pending"}


@router.post("/datasets/{slug}/detach-request")
def detach_request(slug: str, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """数据集管理员申请把数据集移出当前课题组（变为独立），需该组管理员同意。"""
    d = _get_ds(db, slug)
    if not is_dataset_admin(db, d.id, user):
        raise HTTPException(403, "仅数据集发起人/管理员可申请移出")
    if not d.group_id:
        raise HTTPException(400, "数据集当前不属于任何课题组")
    if db.query(DatasetGroupRequest).filter_by(dataset_id=d.id, status="pending").first():
        raise HTTPException(400, "已有待处理的归属申请")
    r = DatasetGroupRequest(dataset_id=d.id, group_id=d.group_id, kind="detach",
                            requested_by=user.id, status="pending", created_at=datetime.utcnow())
    db.add(r); db.commit()
    return {"id": r.id, "status": "pending"}


@router.get("/datasets/{slug}")
def detail(slug: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    d = _get_ds(db, slug)
    member = is_dataset_member(db, d.id, user)
    founder = db.get(User, d.founder_id)
    cur = db.query(DataVersion).filter_by(dataset_id=d.id, is_current=True).first()
    members = db.query(DatasetMember).filter_by(dataset_id=d.id).all()
    approvals = []
    for m in members:
        u = db.get(User, m.user_id)
        approvals.append({"user_id": m.user_id, "name": u.display_name if u else "",
                          "ds_role": m.ds_role, "joined_at": str(m.joined_at),
                          "approved_by": m.approved_by})
    pubs = db.query(Publication).filter_by(dataset_id=d.id).all()
    grp = db.get(ResearchGroup, d.group_id) if d.group_id else None
    pend = db.query(DatasetGroupRequest).filter_by(
        dataset_id=d.id, status="pending").first()
    pend_group = db.get(ResearchGroup, pend.group_id) if pend else None
    return {
        "id": d.id, "slug": d.slug, "name_zh": d.name_zh, "name_en": d.name_en,
        "desc_zh": d.desc_zh, "icon": d.icon, "is_sensitive": d.is_sensitive,
        "group": ({"slug": grp.slug, "name_zh": grp.name_zh} if grp else None),
        "pending_group_request": ({"kind": pend.kind, "group_name": pend_group.name_zh
                                   if pend_group else "", "status": pend.status}
                                  if pend else None),
        "founder": {"id": d.founder_id, "name": founder.display_name if founder else "",
                    "contact": d.founder_contact},
        "is_member": member, "is_admin": is_dataset_admin(db, d.id, user),
        "current_version": ({"id": cur.id, "version_id": cur.version_id,
                             "changelog_zh": cur.changelog_zh} if cur else None),
        "members": approvals,
        "publications": [{"title": p.title, "venue": p.venue, "year": p.year,
                          "url": p.url} for p in pubs],
    }


# -------- variables / codebook（非成员亦可看）--------
@router.get("/datasets/{slug}/variables")
def variables(slug: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    d = _get_ds(db, slug)
    vs = db.query(Variable).filter_by(dataset_id=d.id, enabled=True).all()
    return [{"id": v.id, "var_name": v.var_name, "group_code": v.group_code,
             "label_zh": v.label_zh, "label_en": v.label_en} for v in vs]


# -------- versions --------
@router.get("/datasets/{slug}/versions")
def list_versions(slug: str, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    d = _get_ds(db, slug)
    vs = db.query(DataVersion).filter_by(dataset_id=d.id).order_by(
        DataVersion.id.desc()).all()
    return [{"id": v.id, "version_id": v.version_id, "based_on": v.based_on_version,
             "release_date": str(v.release_date), "changelog_zh": v.changelog_zh,
             "is_current": v.is_current} for v in vs]


@router.post("/datasets/{slug}/versions")
async def publish_version(slug: str, version_id: str = Form(...),
                          based_on_version: str = Form(""),
                          changelog_zh: str = Form(""), changelog_en: str = Form(""),
                          fixed_bug_ids: str = Form(""),  # 逗号分隔：本次修复的已采纳勘误
                          data_file: UploadFile | None = File(None),
                          codebook_file: UploadFile | None = File(None),
                          db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)):
    d = _get_ds(db, slug)
    if not is_dataset_admin(db, d.id, user):
        raise HTTPException(403, "仅发起人/管理员可发版")
    # 版本不可覆盖：同 (dataset, version_id) 不允许重复
    if db.query(DataVersion).filter_by(dataset_id=d.id, version_id=version_id).first():
        raise HTTPException(400, f"版本 {version_id} 已存在，版本不可覆盖")
    data_key = codebook_key = None
    if data_file:
        if not data_file.filename.endswith(".dta"):
            raise HTTPException(400, "数据文件仅支持 .dta")
        data_key = f"versions/{d.slug}/{version_id}/{data_file.filename}"
        storage.save(data_key, data_file.file)
    if codebook_file:
        codebook_key = f"versions/{d.slug}/{version_id}/{codebook_file.filename}"
        storage.save(codebook_key, codebook_file.file)
    # 取消旧 current（旧版本文件保留、不覆盖，只是不再是推荐版）
    db.query(DataVersion).filter_by(dataset_id=d.id, is_current=True).update(
        {"is_current": False, "valid_to": datetime.utcnow()})
    v = DataVersion(dataset_id=d.id, version_id=version_id, based_on_version=based_on_version,
                    release_date=datetime.utcnow(), data_file_path=data_key,
                    codebook_file_path=codebook_key, changelog_zh=changelog_zh,
                    changelog_en=changelog_en, created_by=user.id, is_current=True,
                    valid_from=datetime.utcnow())
    db.add(v); db.flush()
    d.current_version_id = v.id
    # 核心闭环最后一环：本次修复的已采纳勘误标 fixed + fixed_in_version_id
    from ..models.correction import Bug
    fixed = []
    for raw in [x.strip() for x in fixed_bug_ids.split(",") if x.strip()]:
        bug = db.get(Bug, int(raw))
        if bug and bug.dataset_id == d.id and bug.status == "accepted":
            bug.status = "fixed"; bug.fixed_in_version_id = v.id
            fixed.append(bug.id)
    write_audit(db, user.id, "version.publish", "dataset", d.id,
                {"version": version_id, "fixed_bugs": fixed})
    db.commit()
    return {"id": v.id, "version_id": version_id, "fixed_bugs": fixed}


@router.patch("/datasets/{slug}")
def edit_dataset(slug: str, body: dict, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """编辑数据集元信息（名称/简介/图标/联系方式/敏感标记）。"""
    d = _get_ds(db, slug)
    if not is_dataset_admin(db, d.id, user):
        raise HTTPException(403, "仅发起人/管理员可编辑")
    allowed = {"name_zh", "name_en", "desc_zh", "desc_en", "icon",
               "founder_contact", "is_sensitive"}
    for k, val in body.items():
        if k in allowed:
            setattr(d, k, val)
    write_audit(db, user.id, "dataset.edit", "dataset", d.id)
    db.commit()
    return {"ok": True}


@router.patch("/datasets/{slug}/versions/{vid}")
def edit_version(slug: str, vid: int, body: dict, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """仅可改元数据 changelog（版本文件不可覆盖）。"""
    d = _get_ds(db, slug)
    if not is_dataset_admin(db, d.id, user):
        raise HTTPException(403, "仅发起人/管理员可编辑")
    v = db.get(DataVersion, vid)
    if not v or v.dataset_id != d.id:
        raise HTTPException(404, "版本不存在")
    for k in ("changelog_zh", "changelog_en"):
        if k in body:
            setattr(v, k, body[k])
    db.commit()
    return {"ok": True}


@router.delete("/datasets/{slug}/members/{uid}")
def remove_member(slug: str, uid: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    d = _get_ds(db, slug)
    if not is_dataset_admin(db, d.id, user):
        raise HTTPException(403, "仅发起人/管理员可移除成员")
    m = dataset_membership(db, d.id, uid)
    if not m:
        raise HTTPException(404, "该用户不是成员")
    if m.ds_role == "founder":
        raise HTTPException(400, "不能移除发起人")
    db.delete(m)
    write_audit(db, user.id, "dataset.member.remove", "dataset", d.id, {"user": uid})
    db.commit()
    return {"ok": True}


@router.get("/datasets/{slug}/versions/{vid}/download")
def download(slug: str, vid: int, file: str = "data", db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    d = _get_ds(db, slug)
    v = db.get(DataVersion, vid)
    if not v or v.dataset_id != d.id:
        raise HTTPException(404, "版本不存在")
    if file == "codebook":
        key = v.codebook_file_path  # 任意登录用户可下
    else:
        # 下载分级：成员下当前版；管理员下全部历史；非成员不可下原始数据
        if not is_dataset_member(db, d.id, user):
            raise HTTPException(403, "非成员不能下载原始数据，请先申请加入处理")
        if not is_dataset_admin(db, d.id, user) and not v.is_current:
            raise HTTPException(403, "成员仅可下载当前推荐版本；历史版本需管理员权限")
        key = v.data_file_path
    if not key:
        raise HTTPException(404, "文件不存在")
    db.add(DownloadLog(user_id=user.id, dataset_id=d.id, version_id=v.id, file_type=file,
                       file_name=key.split("/")[-1], downloaded_at=datetime.utcnow()))
    write_audit(db, user.id, "download", "dataset", d.id, {"version": v.version_id, "file": file})
    db.commit()
    return StreamingResponse(storage.open(key), media_type="application/octet-stream",
                             headers={"Content-Disposition":
                                      f'attachment; filename="{key.split("/")[-1]}"'})


# -------- members / join --------
@router.get("/datasets/{slug}/members")
def members(slug: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    d = _get_ds(db, slug)
    ms = db.query(DatasetMember).filter_by(dataset_id=d.id).all()
    reqs = db.query(JoinRequest).filter_by(dataset_id=d.id).all()
    return {"members": [{"user_id": m.user_id, "ds_role": m.ds_role,
                         "perms": m.granted_perms_json} for m in ms],
            "requests": [{"id": r.id, "user_id": r.user_id, "status": r.status,
                          "message": r.message} for r in reqs]}


@router.post("/datasets/{slug}/join-requests")
def join_dataset(slug: str, message: str = "", db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    d = _get_ds(db, slug)
    if dataset_membership(db, d.id, user.id):
        raise HTTPException(400, "已是成员")
    r = JoinRequest(dataset_id=d.id, user_id=user.id, message=message, status="pending")
    db.add(r); db.commit()
    return {"id": r.id}


@router.post("/join-requests/{rid}/decide")
def decide_join(rid: int, approve: bool, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    r = db.get(JoinRequest, rid)
    if not r:
        raise HTTPException(404, "申请不存在")
    if not is_dataset_admin(db, r.dataset_id, user):
        raise HTTPException(403, "仅发起人/管理员可审批")
    r.status = "approved" if approve else "rejected"
    r.decided_by = user.id; r.decided_at = datetime.utcnow()
    if approve:
        db.add(DatasetMember(dataset_id=r.dataset_id, user_id=r.user_id, ds_role="member",
                             granted_perms_json=["bug.review", "download"],
                             joined_at=datetime.utcnow(), approved_by=user.id))
    write_audit(db, user.id, "dataset.join.decide", "dataset", r.dataset_id,
                {"approve": approve, "applicant": r.user_id})
    db.commit()
    return {"ok": True, "status": r.status}


@router.post("/datasets/{slug}/members/{uid}/grant")
def grant(slug: str, uid: int, perms: list[str], db: Session = Depends(get_db),
          user: User = Depends(get_current_user)):
    d = _get_ds(db, slug)
    if not is_dataset_admin(db, d.id, user):
        raise HTTPException(403, "仅发起人可授权")
    m = dataset_membership(db, d.id, uid)
    if not m:
        raise HTTPException(404, "该用户不是成员")
    m.granted_perms_json = perms
    write_audit(db, user.id, "dataset.grant", "dataset", d.id, {"user": uid, "perms": perms})
    db.commit()
    return {"ok": True}


# -------- 数据看板（从派生汇总表出图，只读）--------
@router.get("/datasets/{slug}/dashboard")
def dashboard(slug: str, var: str, group: str = "", db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    d = _get_ds(db, slug)  # 非成员也可看
    q = db.query(DatasetSummary).filter_by(dataset_id=d.id, var_name=var)
    if group:
        q = q.filter_by(group_key=group)
    rows = q.all()
    return [{"bucket": r.bucket, "value": r.value, "group_key": r.group_key} for r in rows]


@router.post("/datasets/{slug}/analysis/generate")
def gen_analysis(slug: str, prompt: str, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """AI 只接收变量名/codebook/需求，返回分析代码；不接收原始数据行。"""
    d = _get_ds(db, slug)
    vs = db.query(Variable).filter_by(dataset_id=d.id).all()
    schema = ", ".join(v.var_name for v in vs)
    sys = ("你是数据分析助手。只可基于给定变量名生成 pandas 只读描述性分析代码，"
           "结果赋值给变量 result。禁止任何文件/网络/写操作。")
    code = ai_client.complete(f"变量: {schema}\n需求: {prompt}\n生成 pandas 代码：", sys)
    return {"code": code, "lang": "Python"}


@router.post("/datasets/{slug}/analysis/run")
def run_analysis(slug: str, code: str, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """只读沙箱执行；使用派生汇总，不加载敏感原始行。"""
    from ..services.sandbox import run_readonly, SandboxViolation
    d = _get_ds(db, slug)
    rows = db.query(DatasetSummary).filter_by(dataset_id=d.id).all()
    records = [{"var_name": r.var_name, "group_key": r.group_key,
                "bucket": r.bucket, "value": r.value} for r in rows]
    try:
        return run_readonly(code, records)
    except SandboxViolation as e:
        raise HTTPException(400, str(e))


# -------- literature / publications --------
@router.get("/datasets/{slug}/literature")
def literature(slug: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    d = _get_ds(db, slug)
    topics = db.query(LitTopic).filter_by(dataset_id=d.id).all()
    refs = db.query(LitRef).filter_by(dataset_id=d.id).all()
    return {"topics": [{"id": t.id, "parent_id": t.parent_id, "title_zh": t.title_zh,
                        "ai_generated": t.ai_generated} for t in topics],
            "refs": [{"id": r.id, "title": r.title, "authors": r.authors,
                      "venue": r.venue, "year": r.year, "url": r.url,
                      "note_zh": r.note_zh} for r in refs]}


@router.post("/datasets/{slug}/literature/refs")
def add_ref(slug: str, body: LitRefIn, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    d = _get_ds(db, slug)
    if not is_dataset_member(db, d.id, user):
        raise HTTPException(403, "需为数据集成员")
    r = LitRef(dataset_id=d.id, added_by=user.id, **body.model_dump())
    db.add(r); db.commit()
    return {"id": r.id}


# ================= AI 文献/用途总结（元数据-only，安全）=================
@router.post("/datasets/{slug}/literature/ai-summarize")
def ai_summarize_literature(slug: str, db: Session = Depends(get_db),
                            user: User = Depends(get_current_user)):
    d = _get_ds(db, slug)
    if not is_dataset_member(db, d.id, user):
        raise HTTPException(403, "需为数据集成员")
    refs = db.query(LitRef).filter_by(dataset_id=d.id).all()
    vs = db.query(Variable).filter_by(dataset_id=d.id).all()
    ctx = (f"数据集：{d.name_zh}。简介：{d.desc_zh}。变量："
           + ", ".join(v.var_name for v in vs) + "。已有文献："
           + "; ".join(f"{r.title}({r.year})" for r in refs))
    sys = "你是研究助理。基于数据集元信息与文献，用中文总结该数据集的研究用途与3-5个研究话题，简洁分点。"
    out = ai_client.complete(ctx, sys)
    return {"summary": out, "ai_model": ai_client.provider}
