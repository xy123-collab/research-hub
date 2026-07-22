import io
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..core.storage import storage
from ..core.permissions import get_current_user, is_dataset_member, is_dataset_admin
from ..core.audit import write_audit, record_contribution
from ..core.ai_client import ai_client
from ..models.user import User
from ..models.dataset import Dataset
from ..models.code import CodeScript, CodeBug, CodeWriteup
from ..models.curation import CodeVersion, CodeGrant, CodeComment
from ..models.correction import CorrectionReview, CorrectionFinal
from ..schemas.models import CodeIn, CodeBugIn, ReviewIn, FinalizeIn

router = APIRouter(tags=["code"])


def _code_perm(db, c: CodeScript, user, kind: str) -> bool:
    """kind: edit|publish。作者、被授权者、或数据集管理员。"""
    if c.author_id == user.id or is_dataset_admin(db, c.dataset_id, user):
        return True
    g = db.query(CodeGrant).filter_by(script_id=c.id, user_id=user.id).first()
    if not g:
        return False
    return g.can_edit if kind == "edit" else g.can_publish


def _ds(db, slug):
    d = db.query(Dataset).filter_by(slug=slug, is_deleted=False).first()
    if not d:
        raise HTTPException(404, "数据集不存在")
    return d


@router.get("/datasets/{slug}/code")
def list_code(slug: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    d = _ds(db, slug)
    cs = db.query(CodeScript).filter_by(dataset_id=d.id).all()
    return [{"id": c.id, "filename": c.filename, "lang": c.lang, "title_zh": c.title_zh,
             "author_id": c.author_id, "reuse_count": c.reuse_count} for c in cs]


@router.post("/datasets/{slug}/code")
def add_code(slug: str, body: CodeIn, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    d = _ds(db, slug)
    if not is_dataset_member(db, d.id, user):
        raise HTTPException(403, "需为数据集成员")
    c = CodeScript(dataset_id=d.id, author_id=user.id, **body.model_dump())
    db.add(c); db.flush()
    record_contribution(db, user.id, "code_add", "code", c.id, d.id, weight=20)
    write_audit(db, user.id, "code.add", "code", c.id)
    db.commit()
    return {"id": c.id}


@router.get("/code/{cid}")
def get_code(cid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    c = db.get(CodeScript, cid)
    if not c:
        raise HTTPException(404, "代码不存在")
    author = db.get(User, c.author_id)
    versions = db.query(CodeVersion).filter_by(script_id=cid).order_by(
        CodeVersion.id.desc()).all()
    grants = db.query(CodeGrant).filter_by(script_id=cid).all()
    is_member = is_dataset_member(db, c.dataset_id, user)
    return {"id": c.id, "dataset_id": c.dataset_id, "filename": c.filename, "lang": c.lang,
            "title_zh": c.title_zh, "desc_zh": c.desc_zh, "source_code": c.source_code,
            "author_id": c.author_id, "author_name": author.display_name if author else "",
            "is_member": is_member,
            "can_edit": _code_perm(db, c, user, "edit"),
            "can_publish": _code_perm(db, c, user, "publish"),
            "can_grant": (c.author_id == user.id or is_dataset_admin(db, c.dataset_id, user)),
            "versions": [{"id": v.id, "version_label": v.version_label, "filename": v.filename,
                          "changelog": v.changelog, "is_current": v.is_current,
                          "created_at": str(v.created_at)[:10] if v.created_at else ""}
                         for v in versions],
            "grants": [{"user_id": g.user_id, "can_edit": g.can_edit,
                        "can_publish": g.can_publish} for g in grants]}


@router.patch("/code/{cid}")
def edit_code(cid: int, body: dict, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    c = db.get(CodeScript, cid)
    if not c:
        raise HTTPException(404, "代码不存在")
    if not _code_perm(db, c, user, "edit"):
        raise HTTPException(403, "无修改权限（需作者授予或为数据集管理员）")
    for k in ("title_zh", "desc_zh", "source_code", "lang"):
        if k in body:
            setattr(c, k, body[k])
    write_audit(db, user.id, "code.edit", "code", c.id)
    db.commit()
    return {"ok": True}


# -------- 代码版本迭代（发布新版本需写修改内容）--------
@router.post("/code/{cid}/versions")
def publish_code_version(cid: int, version_label: str = Form(...), changelog: str = Form(...),
                         file: UploadFile | None = File(None), source_code: str = Form(""),
                         db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    c = db.get(CodeScript, cid)
    if not c:
        raise HTTPException(404, "代码不存在")
    if not _code_perm(db, c, user, "publish"):
        raise HTTPException(403, "无重新发布权限（需作者授予或为数据集管理员）")
    if not changelog.strip():
        raise HTTPException(400, "请写清本次修改内容")
    if db.query(CodeVersion).filter_by(script_id=cid, version_label=version_label).first():
        raise HTTPException(400, f"版本 {version_label} 已存在")
    filename = c.filename; key = None; src = source_code
    if file is not None:
        raw = file.file.read()
        try:
            src = raw.decode("utf-8")
        except UnicodeDecodeError:
            src = raw.decode("latin-1", errors="replace")
        filename = file.filename
        key = f"code/{cid}/{version_label}/{filename}"
        from ..services.uploads import save_stored_file
        save_stored_file(key, io.BytesIO(raw))
    db.query(CodeVersion).filter_by(script_id=cid, is_current=True).update({"is_current": False})
    v = CodeVersion(script_id=cid, version_label=version_label, filename=filename,
                    file_path=key, source_code=src, changelog=changelog,
                    created_by=user.id, created_at=datetime.utcnow(), is_current=True)
    db.add(v)
    # 同步主记录的当前源码/文件名
    if src:
        c.source_code = src
    c.filename = filename
    write_audit(db, user.id, "code.version.publish", "code", cid, {"v": version_label})
    db.commit()
    try:
        from ..services.notify import notify_code_published
        notify_code_published(db, c, v, user)
        db.commit()
    except Exception as _e:
        db.rollback()
        import logging; logging.getLogger("notify").warning("代码通知创建失败: %s", _e)
    return {"id": v.id, "version_label": version_label}


@router.get("/code/{cid}/download")
def download_code(cid: int, vid: int | None = None, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """数据集成员默认可下载代码文件（当前版本或指定版本）。"""
    c = db.get(CodeScript, cid)
    if not c:
        raise HTTPException(404, "代码不存在")
    if not is_dataset_member(db, c.dataset_id, user):
        raise HTTPException(403, "需为数据集成员")
    filename = c.filename or f"code_{cid}.txt"
    data = (c.source_code or "").encode("utf-8")
    from ..services.downloads import log_download
    from ..models.dataset import Dataset as _DS
    _d = db.get(_DS, c.dataset_id)
    _label = _d.name_zh if _d else "处理代码"
    _link = f"/#/datasets/{_d.slug}?tab=code" if _d else ""
    if vid:
        v = db.get(CodeVersion, vid)
        if v and v.script_id == cid:
            filename = v.filename or filename
            data = (v.source_code or "").encode("utf-8")
            if v.file_path:
                from ..services.uploads import open_stored_file
                stream = open_stored_file(v.file_path)
                log_download(db, user_id=user.id, source="code", dataset_id=c.dataset_id,
                             location_label=_label, detail=f"处理代码·{v.version_label or ''}",
                             file_name=filename, link=_link)
                write_audit(db, user.id, "code.download", "code", cid)
                db.commit()
                return StreamingResponse(stream,
                                         media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="code_{vid}"'})
    safe = f"code_{cid}.txt"
    log_download(db, user_id=user.id, source="code", dataset_id=c.dataset_id,
                 location_label=_label, detail="处理代码", file_name=safe, link=_link)
    write_audit(db, user.id, "code.download", "code", cid)
    db.commit()
    return StreamingResponse(io.BytesIO(data), media_type="text/plain; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{safe}"'})


# -------- 作者授予修改/重发权限 --------
@router.post("/code/{cid}/grants")
def grant_code(cid: int, user_id: int = Form(...), can_edit: bool = Form(False),
               can_publish: bool = Form(False), db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    c = db.get(CodeScript, cid)
    if not c:
        raise HTTPException(404, "代码不存在")
    if not (c.author_id == user.id or is_dataset_admin(db, c.dataset_id, user)):
        raise HTTPException(403, "仅代码作者或数据集管理员可授权")
    if not is_dataset_member(db, c.dataset_id, db.get(User, user_id)):
        raise HTTPException(400, "对方需为数据集成员")
    g = db.query(CodeGrant).filter_by(script_id=cid, user_id=user_id).first()
    if not g:
        g = CodeGrant(script_id=cid, user_id=user_id, granted_by=user.id)
        db.add(g)
    g.can_edit = bool(can_edit); g.can_publish = bool(can_publish)
    write_audit(db, user.id, "code.grant", "code", cid, {"user": user_id})
    db.commit()
    return {"ok": True}


# -------- 评论（可标记为勘误类）--------
@router.get("/code/{cid}/comments")
def list_code_comments(cid: int, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    rows = db.query(CodeComment).filter_by(script_id=cid).order_by(CodeComment.id.desc()).all()
    out = []
    for cm in rows:
        u = db.get(User, cm.user_id)
        out.append({"id": cm.id, "user_id": cm.user_id, "name": u.display_name if u else "",
                    "content": cm.content, "is_correction": cm.is_correction,
                    "created_at": str(cm.created_at)[:16] if cm.created_at else ""})
    return out


@router.post("/code/{cid}/comments")
def add_code_comment(cid: int, content: str = Form(...), is_correction: bool = Form(False),
                     mentions: str = Form(""),
                     db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    c = db.get(CodeScript, cid)
    if not c:
        raise HTTPException(404, "代码不存在")
    if not is_dataset_member(db, c.dataset_id, user):
        raise HTTPException(403, "需为数据集成员")
    cm = CodeComment(script_id=cid, user_id=user.id, content=content,
                     is_correction=bool(is_correction), created_at=datetime.utcnow())
    db.add(cm); db.flush()
    import json as _json
    try:
        raw = _json.loads(mentions) if mentions else []
    except Exception:
        raw = []
    from ..models.dataset import Dataset as _DS
    _d = db.get(_DS, c.dataset_id)
    from ..services.mentions import record_mentions
    record_mentions(db, source_type="code_comment", source_id=cm.id,
                    post_ref=(f"dataset={_d.slug}&tab=code" if _d else "code"),
                    snippet=content, by_user=user, raw_mentions=raw)
    db.commit()
    return {"id": cm.id}


@router.post("/code/{cid}/writeup")
def writeup(cid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """一键生成数据处理说明（论文数据附录写法草稿）。"""
    c = db.get(CodeScript, cid)
    if not c:
        raise HTTPException(404, "代码不存在")
    sys = "你是学术写作助手，把数据处理代码转写为论文'数据来源与处理'段落草稿。"
    body = ai_client.complete(f"代码({c.lang}):\n{c.source_code}\n\n生成数据处理说明：", sys)
    w = CodeWriteup(script_id=cid, body_zh=body, ai_model=ai_client.provider,
                    generated_by=user.id)
    db.add(w); db.commit()
    return {"id": w.id, "body_zh": body}


@router.get("/code/{cid}/bugs")
def list_code_bugs(cid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    bs = db.query(CodeBug).filter_by(script_id=cid).all()
    return [{"id": b.id, "line_ref": b.line_ref, "description_zh": b.description_zh,
             "status": b.status, "reporter_id": b.reporter_id} for b in bs]


@router.post("/code/{cid}/bugs")
def add_code_bug(cid: int, body: CodeBugIn, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    c = db.get(CodeScript, cid)
    if not c:
        raise HTTPException(404, "代码不存在")
    if not is_dataset_member(db, c.dataset_id, user):
        raise HTTPException(403, "需为数据集成员")
    b = CodeBug(script_id=cid, reporter_id=user.id, status="pending", **body.model_dump())
    db.add(b); db.commit()
    return {"id": b.id}


@router.post("/codebugs/{bid}/reviews")
def review_code_bug(bid: int, body: ReviewIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    b = db.get(CodeBug, bid)
    if not b:
        raise HTTPException(404, "代码勘误不存在")
    db.add(CorrectionReview(target_type="code_bug", target_id=bid, reviewer_type="member",
                            reviewer_id=user.id, acceptability_score=body.acceptability_score,
                            comment=body.comment))
    db.commit()
    return {"ok": True}


@router.post("/codebugs/{bid}/finalize")
def finalize_code_bug(bid: int, body: FinalizeIn, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    b = db.get(CodeBug, bid)
    if not b:
        raise HTTPException(404, "代码勘误不存在")
    c = db.get(CodeScript, b.script_id)
    if not is_dataset_admin(db, c.dataset_id, user):
        raise HTTPException(403, "仅数据集管理员可终审")
    db.add(CorrectionFinal(target_type="code_bug", target_id=bid, decided_by=user.id,
                           adopt_level=body.adopt_level, final_score=body.final_score,
                           comment=body.comment, decided_at=datetime.utcnow()))
    b.status = "accepted" if body.adopt_level != "reject" else "rejected"
    b.reviewed_by = user.id; b.reviewed_at = datetime.utcnow()
    if body.adopt_level != "reject":
        record_contribution(db, b.reporter_id, "code_bug_accepted", "code_bug", bid,
                            c.dataset_id, weight=body.final_score)
    db.commit()
    return {"ok": True, "status": b.status}


# ================= 处理代码文件上传（读入文本存 source_code）=================
from fastapi import UploadFile, File, Form  # noqa: E402


@router.post("/datasets/{slug}/code/upload")
def upload_code(slug: str, title_zh: str = Form(...), lang: str = Form("Python"),
                desc_zh: str = Form(""), file: UploadFile = File(...),
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..services.uploads import save_upload, CODE_EXT
    d = _ds(db, slug)
    if not is_dataset_member(db, d.id, user):
        raise HTTPException(403, "需为数据集成员")
    raw = file.file.read()
    try:
        source = raw.decode("utf-8")
    except UnicodeDecodeError:
        source = raw.decode("latin-1", errors="replace")
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(400, "代码文件过大（>5MB）")
    c = CodeScript(dataset_id=d.id, author_id=user.id, filename=file.filename,
                   lang=lang, title_zh=title_zh, desc_zh=desc_zh, source_code=source)
    db.add(c); db.flush()
    record_contribution(db, user.id, "code_add", "code", c.id, d.id, weight=20)
    write_audit(db, user.id, "code.upload", "code", c.id)
    db.commit()
    return {"id": c.id, "filename": c.filename}
