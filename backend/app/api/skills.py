"""其他协作：分区（第一分区=Skill 协作，可自建其他类型协作分区）+ Skill 发起/评论/下载。

Skill 发起支持：上传文件或文字、选择可见范围（公开/课题组成员/数据集成员/仅自己）。
已发布 Skill 提供评论（含评论的评论）与下载。
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from ..core.db import get_db
from ..core.permissions import (get_current_user, is_super_admin, is_group_member,
                                is_dataset_member)
from ..core.audit import record_contribution
from ..models.user import User
from ..models.skill import Skill, SkillMember, GithubSkillReco
from ..models.extras import CollabSection, SkillMeta, SkillComment, SKILL_SCOPES

router = APIRouter(tags=["skills"])


# ======================= 协作分区 =======================
def _ensure_skill_section(db: Session) -> CollabSection:
    """确保内置的「Skill 协作」分区存在。"""
    s = db.query(CollabSection).filter_by(key="skill").first()
    if not s:
        s = CollabSection(key="skill", name_zh="Skill 协作", name_en="Skill Collaboration",
                          desc_zh="共享与复用科研 Skill（脚本/流程/提示词等）。",
                          kind="skill", seq=0)
        db.add(s); db.commit(); db.refresh(s)
    return s


@router.get("/collab/sections")
def list_sections(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _ensure_skill_section(db)
    rows = db.query(CollabSection).order_by(CollabSection.seq, CollabSection.id).all()
    out = []
    for s in rows:
        n = db.query(SkillMeta).filter_by(section_id=s.id).count()
        out.append({"id": s.id, "key": s.key, "name_zh": s.name_zh, "name_en": s.name_en,
                    "desc_zh": s.desc_zh, "kind": s.kind, "item_count": n,
                    "created_by": s.created_by})
    return out


class SectionIn(BaseModel):
    name_zh: str
    name_en: str | None = None
    desc_zh: str | None = None


@router.post("/collab/sections")
def create_section(body: SectionIn, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """发起其他类型协作 = 新建一个协作分区。"""
    if not (body.name_zh or "").strip():
        raise HTTPException(400, "分区名称必填")
    import re
    base = re.sub(r"[^a-z0-9]+", "-", (body.name_en or body.name_zh).lower()).strip("-") or "collab"
    key = base
    i = 1
    while db.query(CollabSection).filter_by(key=key).first():
        i += 1; key = f"{base}-{i}"
    seq = (db.query(CollabSection).count()) + 1
    s = CollabSection(key=key, name_zh=body.name_zh.strip(), name_en=body.name_en,
                      desc_zh=body.desc_zh, kind="generic", created_by=user.id, seq=seq)
    db.add(s); db.commit(); db.refresh(s)
    return {"id": s.id, "key": s.key}


# ======================= Skill 可见性 =======================
def _can_see_skill(db: Session, s: Skill, meta: SkillMeta | None, user: User) -> bool:
    from ..core.scopes import get_scopes, scope_visible
    if s.founder_id == user.id or is_super_admin(user):
        return True
    scope = (meta.scope if meta else None) or "public"
    if scope == "public":
        return True
    if scope == "self":
        return False
    # group / dataset：多选走 ContentScope；老数据无 ContentScope 时回退单个 ref
    if get_scopes(db, "skill", s.id):
        return scope_visible(db, "skill", s.id, s.founder_id, user)
    if scope == "group" and meta and meta.scope_ref_id:
        return is_group_member(db, meta.scope_ref_id, user)
    if scope == "dataset" and meta and meta.scope_ref_id:
        return is_dataset_member(db, meta.scope_ref_id, user)
    return False


# ======================= Skill 列表 / 发起 =======================
@router.get("/skills")
def list_skills(section_id: int | None = None, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    sec = _ensure_skill_section(db)
    ss = db.query(Skill).filter_by(is_deleted=False).order_by(Skill.id.desc()).all()
    out = []
    for s in ss:
        m = db.get(SkillMeta, s.id)
        sid = (m.section_id if m and m.section_id else sec.id)
        if section_id and sid != section_id:
            continue
        if not _can_see_skill(db, s, m, user):
            continue
        fu = db.get(User, s.founder_id)
        out.append({"id": s.id, "name_zh": s.name_zh, "desc_zh": s.desc_zh,
                    "founder_id": s.founder_id,
                    "founder_name": fu.display_name if fu else "",
                    "github_url": s.github_url, "section_id": sid,
                    "scope": (m.scope if m else "public"),
                    "has_file": bool(m and m.file_path),
                    "file_name": (m.file_name if m else None),
                    "body_text": (m.body_text if m else None),
                    "comment_count": db.query(SkillComment).filter_by(skill_id=s.id).count()})
    return out


@router.post("/skills")
def create_skill(name_zh: str = Form(...), desc_zh: str = Form(""),
                 body_text: str = Form(""), scope: str = Form("public"),
                 scope_ref_ids: str = Form(""), section_id: int | None = Form(None),
                 github_url: str = Form(""), file: UploadFile | None = File(None),
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """发起 Skill：可上传文件或填写文字，选择可见范围（课题组/数据集可多选）。"""
    from ..core.scopes import set_scope, _norm_ids
    if not (name_zh or "").strip():
        raise HTTPException(400, "名称必填")
    if scope not in SKILL_SCOPES:
        scope = "public"
    if github_url and not (github_url.startswith("http://") or github_url.startswith("https://")):
        raise HTTPException(400, "GitHub 链接需以 http(s):// 开头")
    sec = _ensure_skill_section(db)
    s = Skill(founder_id=user.id, name_zh=name_zh.strip(), desc_zh=desc_zh or None,
              github_url=github_url or None, is_public=(scope == "public"))
    db.add(s); db.flush()
    db.add(SkillMember(skill_id=s.id, user_id=user.id, ds_role="founder"))
    try:
        set_scope(db, "skill", s.id, scope, scope_ref_ids, user)
    except ValueError as e:
        raise HTTPException(400, str(e))
    ids = _norm_ids(scope_ref_ids)
    meta = SkillMeta(skill_id=s.id, section_id=section_id or sec.id, scope=scope,
                     scope_ref_id=(ids[0] if ids else None),
                     body_text=(body_text or "").strip() or None)
    if file is not None and getattr(file, "filename", ""):
        from ..services.uploads import save_upload
        fm = save_upload(file, f"skill/{s.id}")
        meta.file_path = fm["file_path"]; meta.file_name = fm["file_name"]; meta.mime = fm["mime"]
    db.add(meta)
    record_contribution(db, user.id, "skill_create", "skill", s.id, weight=15)
    db.commit()
    return {"id": s.id}


@router.get("/skills/{sid}")
def get_skill(sid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    s = db.get(Skill, sid)
    if not s or s.is_deleted:
        raise HTTPException(404, "Skill 不存在")
    m = db.get(SkillMeta, sid)
    if not _can_see_skill(db, s, m, user):
        raise HTTPException(403, "无权查看该 Skill")
    fu = db.get(User, s.founder_id)
    return {"id": s.id, "name_zh": s.name_zh, "desc_zh": s.desc_zh,
            "github_url": s.github_url, "founder_id": s.founder_id,
            "founder_name": fu.display_name if fu else "",
            "scope": (m.scope if m else "public"),
            "body_text": (m.body_text if m else None),
            "has_file": bool(m and m.file_path), "file_name": (m.file_name if m else None),
            "can_edit": (s.founder_id == user.id or is_super_admin(user))}


@router.get("/skills/{sid}/download")
def download_skill(sid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..core.storage import storage
    s = db.get(Skill, sid)
    if not s or s.is_deleted:
        raise HTTPException(404, "Skill 不存在")
    m = db.get(SkillMeta, sid)
    if not _can_see_skill(db, s, m, user):
        raise HTTPException(403, "无权下载")
    if not m or not m.file_path:
        raise HTTPException(404, "该 Skill 没有可下载文件")
    from ..services.downloads import log_download
    log_download(db, user_id=user.id, source="skill", dataset_id=None,
                 location_label="Skill 协作", detail=(s.name_zh or s.name_en or "Skill"),
                 file_name=m.file_name, link="/#/collab")
    db.commit()
    from ..services.uploads import attachment_headers
    return StreamingResponse(storage.open(m.file_path),
                             media_type=m.mime or "application/octet-stream",
                             headers=attachment_headers(m.file_name))


# ======================= Skill 评论（含评论的评论）=======================
class SkillCommentIn(BaseModel):
    content: str
    parent_id: int | None = None
    mentions: list[dict] = []


@router.get("/skills/{sid}/comments")
def skill_comments(sid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cs = db.query(SkillComment).filter_by(skill_id=sid).order_by(SkillComment.id).all()
    out = []
    for c in cs:
        u = db.get(User, c.user_id)
        out.append({"id": c.id, "user_id": c.user_id,
                    "user_name": u.display_name if u else f"用户#{c.user_id}",
                    "content": c.content, "parent_id": c.parent_id,
                    "created_at": str(c.created_at) if c.created_at else None})
    return out


@router.post("/skills/{sid}/comments")
def add_skill_comment(sid: int, body: SkillCommentIn, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    s = db.get(Skill, sid)
    if not s or s.is_deleted:
        raise HTTPException(404, "Skill 不存在")
    if body.parent_id:
        p = db.get(SkillComment, body.parent_id)
        if not p or p.skill_id != sid:
            raise HTTPException(400, "父评论不存在")
    c = SkillComment(skill_id=sid, user_id=user.id, content=body.content,
                     parent_id=body.parent_id)
    db.add(c); db.flush()
    from ..services.mentions import record_mentions
    record_mentions(db, source_type="skill_comment", source_id=c.id, post_ref="collab",
                    snippet=body.content, by_user=user, raw_mentions=(body.mentions or []))
    db.commit()
    return {"id": c.id}


@router.delete("/skills/comments/{cid}")
def del_skill_comment(cid: int, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    c = db.get(SkillComment, cid)
    if not c:
        raise HTTPException(404, "评论不存在")
    if c.user_id != user.id and not is_super_admin(user):
        raise HTTPException(403, "无权删除")
    db.delete(c); db.commit()
    return {"ok": True}


# -------- GitHub 推荐 skill --------
@router.get("/github-skill-recos")
def list_recos(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rs = db.query(GithubSkillReco).all()
    return [{"id": r.id, "name": r.name, "note": r.note, "github_url": r.github_url}
            for r in rs]


@router.post("/github-skill-recos")
def add_reco(name: str, github_url: str, note: str = "", group_id: int | None = None,
             db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not (github_url.startswith("http://") or github_url.startswith("https://")):
        raise HTTPException(400, "URL 必须以 http(s):// 开头")
    r = GithubSkillReco(name=name, github_url=github_url, note=note, group_id=group_id,
                        added_by=user.id)
    db.add(r); db.commit()
    return {"id": r.id}
