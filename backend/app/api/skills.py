from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..core.permissions import get_current_user, is_super_admin
from ..core.audit import record_contribution
from ..models.user import User
from ..models.skill import Skill, SkillMember, GithubSkillReco
from ..schemas.models import SkillIn

router = APIRouter(tags=["skills"])


@router.get("/skills")
def list_skills(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ss = db.query(Skill).filter_by(is_deleted=False).all()
    return [{"id": s.id, "name_zh": s.name_zh, "desc_zh": s.desc_zh,
             "founder_id": s.founder_id, "github_url": s.github_url,
             "group_id": s.group_id} for s in ss]


@router.post("/skills")
def create_skill(body: SkillIn, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    s = Skill(founder_id=user.id, **body.model_dump())
    db.add(s); db.flush()
    db.add(SkillMember(skill_id=s.id, user_id=user.id, ds_role="founder"))
    record_contribution(db, user.id, "skill_create", "skill", s.id, weight=15)
    db.commit()
    return {"id": s.id}


@router.get("/skills/{sid}")
def get_skill(sid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    s = db.get(Skill, sid)
    if not s or s.is_deleted:
        raise HTTPException(404, "Skill 不存在")
    members = db.query(SkillMember).filter_by(skill_id=sid).all()
    return {"id": s.id, "name_zh": s.name_zh, "desc_zh": s.desc_zh,
            "github_url": s.github_url, "founder_id": s.founder_id,
            "members": [{"user_id": m.user_id, "ds_role": m.ds_role} for m in members]}


@router.patch("/skills/{sid}")
def edit_skill(sid: int, body: SkillIn, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    s = db.get(Skill, sid)
    if not s:
        raise HTTPException(404, "Skill 不存在")
    if s.founder_id != user.id and not is_super_admin(user):
        raise HTTPException(403, "无权编辑")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(s, k, v)
    db.commit()
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
