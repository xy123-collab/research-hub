from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pydantic import BaseModel
from ..core.db import get_db
from ..core.permissions import get_current_user
from ..models.user import User
from ..models.resume import Resume, ResumeBlock
from ..models.community import Post, Project
from ..models.extras import UserProfile
from ..schemas.models import ResumeBlockIn
from ..services.scoring import user_total

router = APIRouter(tags=["users"])


class ProfilePatch(BaseModel):
    display_name: str | None = None
    bio_zh: str | None = None
    bio_en: str | None = None
    avatar: str | None = None
    preferred_language: str | None = None
    contact: str | None = None
    research_direction: str | None = None   # 研究方向（存 UserProfile）
    keywords: str | None = None             # 关键词（存 UserProfile）


def _profile_extra(db: Session, uid: int) -> UserProfile:
    p = db.get(UserProfile, uid)
    if not p:
        p = UserProfile(user_id=uid); db.add(p); db.flush()
    return p


@router.get("/users/search")
def search_users(q: str = "", limit: int = 20, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """按姓名 / 用户名 / ID 检索平台全体成员（用于邀请/授权）。"""
    q = (q or "").strip()
    query = db.query(User).filter(User.status != "left")
    if q:
        conds = [User.display_name.ilike(f"%{q}%"), User.username.ilike(f"%{q}%")]
        if q.isdigit():
            conds.append(User.id == int(q))
        query = query.filter(or_(*conds))
    rows = query.order_by(User.id).limit(min(limit, 50)).all()
    return [{"id": u.id, "display_name": u.display_name, "username": u.username,
             "avatar": u.avatar} for u in rows]


@router.get("/users/{uid}")
def get_user(uid: int, db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "用户不存在")
    posts = db.query(Post).filter_by(author_id=uid, visibility="platform").count()
    projects = db.query(Project).filter_by(author_id=uid).count()
    ex = db.get(UserProfile, uid)
    return {"id": u.id, "username": u.username, "display_name": u.display_name,
            "bio_zh": u.bio_zh, "bio_en": u.bio_en, "avatar": u.avatar,
            "contact": u.contact, "contribution": user_total(db, uid),
            "research_direction": ex.research_direction if ex else None,
            "keywords": ex.keywords if ex else None,
            "post_count": posts, "project_count": projects}


@router.patch("/me")
def patch_me(body: ProfilePatch, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    data = body.model_dump(exclude_none=True)
    extra_keys = {"research_direction", "keywords"}
    if data.keys() & extra_keys:
        p = _profile_extra(db, user.id)
        for k in list(extra_keys):
            if k in data:
                setattr(p, k, data.pop(k))
    for k, v in data.items():
        setattr(user, k, v)
    db.commit()
    return {"ok": True}


@router.post("/me/avatar")
def upload_avatar(file: UploadFile = File(...), user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """上传头像图片，返回可访问 URL 并写入 user.avatar。"""
    from ..services.uploads import save_upload, IMG_EXT
    meta = save_upload(file, f"avatar/{user.id}", whitelist=IMG_EXT)
    user.avatar = f"/api/me/avatar/file?k={meta['file_path']}"
    db.commit()
    return {"avatar": user.avatar}


@router.get("/me/avatar/file")
def get_avatar_file(k: str, db: Session = Depends(get_db)):
    from ..core.storage import storage
    if not k.startswith("avatar/"):
        raise HTTPException(400, "非法路径")
    try:
        return StreamingResponse(storage.open(k), media_type="image/*")
    except Exception:
        raise HTTPException(404, "头像不存在")


# -------- resume --------
@router.get("/users/{uid}/resume")
def get_resume(uid: int, db: Session = Depends(get_db)):
    r = db.query(Resume).filter_by(user_id=uid).first()
    if not r:
        return {"resume": None, "blocks": []}
    blocks = (db.query(ResumeBlock).filter_by(resume_id=r.id)
              .order_by(ResumeBlock.seq).all())
    return {"resume": {"id": r.id, "from_template": r.from_template},
            "blocks": [{"id": b.id, "seq": b.seq, "type": b.type,
                        "text_zh": b.text_zh, "text_en": b.text_en} for b in blocks]}


@router.put("/me/resume")
def upsert_resume(from_template: bool = False, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    r = db.query(Resume).filter_by(user_id=user.id).first()
    if not r:
        r = Resume(user_id=user.id, from_template=from_template)
        db.add(r); db.commit(); db.refresh(r)
    return {"id": r.id}


class ResumeBulkIn(BaseModel):
    blocks: list[ResumeBlockIn]


@router.put("/me/resume/blocks")
def replace_blocks(body: ResumeBulkIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """整块替换本人简历：一次保存所有块（支持排序/增删/编辑）。

    前端把整份简历当一个文本/表单编辑，保存时一次提交，避免一行一行操作。
    """
    r = db.query(Resume).filter_by(user_id=user.id).first()
    if not r:
        r = Resume(user_id=user.id); db.add(r); db.commit(); db.refresh(r)
    db.query(ResumeBlock).filter_by(resume_id=r.id).delete()
    for i, b in enumerate(body.blocks):
        db.add(ResumeBlock(resume_id=r.id, type=b.type, text_zh=b.text_zh,
                           text_en=b.text_en, seq=i))
    db.commit()
    return {"ok": True, "count": len(body.blocks)}


@router.post("/me/resume/blocks")
def add_block(body: ResumeBlockIn, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    r = db.query(Resume).filter_by(user_id=user.id).first()
    if not r:
        r = Resume(user_id=user.id); db.add(r); db.commit(); db.refresh(r)
    b = ResumeBlock(resume_id=r.id, type=body.type, text_zh=body.text_zh,
                    text_en=body.text_en, seq=body.seq)
    db.add(b); db.commit(); db.refresh(b)
    return {"id": b.id}


@router.patch("/me/resume/blocks/{bid}")
def edit_block(bid: int, body: ResumeBlockIn, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    b = db.get(ResumeBlock, bid)
    if not b:
        raise HTTPException(404, "块不存在")
    r = db.get(Resume, b.resume_id)
    if r.user_id != user.id:
        raise HTTPException(403, "只能编辑本人简历")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(b, k, v)
    db.commit()
    return {"ok": True}


@router.delete("/me/resume/blocks/{bid}")
def del_block(bid: int, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    b = db.get(ResumeBlock, bid)
    if not b:
        raise HTTPException(404, "块不存在")
    r = db.get(Resume, b.resume_id)
    if r.user_id != user.id:
        raise HTTPException(403, "只能编辑本人简历")
    db.delete(b); db.commit()
    return {"ok": True}


@router.get("/me/contributions")
def my_contributions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from ..models.governance import ContributionEvent
    rows = db.query(ContributionEvent).filter_by(user_id=user.id).all()
    return {"total": user_total(db, user.id),
            "events": [{"type": e.event_type, "ref_type": e.ref_type,
                        "ref_id": e.ref_id, "dataset_id": e.dataset_id,
                        "weight": e.weight} for e in rows]}
