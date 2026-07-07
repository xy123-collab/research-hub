from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from ..core.db import get_db
from ..core.permissions import get_current_user
from ..models.user import User
from ..models.resume import Resume, ResumeBlock
from ..models.community import Post, Project
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


@router.get("/users/{uid}")
def get_user(uid: int, db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "用户不存在")
    posts = db.query(Post).filter_by(author_id=uid, visibility="platform").count()
    projects = db.query(Project).filter_by(author_id=uid).count()
    return {"id": u.id, "username": u.username, "display_name": u.display_name,
            "bio_zh": u.bio_zh, "bio_en": u.bio_en, "avatar": u.avatar,
            "contact": u.contact, "contribution": user_total(db, uid),
            "post_count": posts, "project_count": projects}


@router.patch("/me")
def patch_me(body: ProfilePatch, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(user, k, v)
    db.commit()
    return {"ok": True}


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
