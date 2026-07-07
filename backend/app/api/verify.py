from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..core.permissions import get_current_user, is_dataset_member, is_dataset_admin
from ..models.user import User
from ..models.dataset import Dataset
from ..models.version import DataVersion
from ..models.governance import VerifyFlag, QualityRule
from ..models.correction import Bug
from ..services.quality import run_rules

router = APIRouter(tags=["verify"])


def _ds(db, slug):
    d = db.query(Dataset).filter_by(slug=slug, is_deleted=False).first()
    if not d:
        raise HTTPException(404, "数据集不存在")
    return d


@router.get("/datasets/{slug}/verify-flags")
def flags(slug: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    d = _ds(db, slug)
    fs = db.query(VerifyFlag).filter_by(dataset_id=d.id).order_by(VerifyFlag.id.desc()).all()
    return [{"id": f.id, "source": f.source, "officer_id": f.officer_id,
             "term_id": f.term_id, "variable_name": f.variable_name,
             "issue_desc": f.issue_desc, "confidence": f.confidence,
             "status": f.status, "drafted_bug_id": f.drafted_bug_id} for f in fs]


@router.post("/datasets/{slug}/verify/run")
def run_verify(slug: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """规则通道：定时/手动跑 quality_rules，失败写 verify_flags(source=rule)。不改数据。"""
    d = _ds(db, slug)
    if not is_dataset_member(db, d.id, user):
        raise HTTPException(403, "需为数据集成员")
    cur = db.query(DataVersion).filter_by(dataset_id=d.id, is_current=True).first()
    n = run_rules(db, d.id, cur.id if cur else None)
    db.commit()
    return {"new_flags": n}


@router.post("/verify-flags/{fid}/draft-bug")
def draft_bug(fid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """一键把 flag 生成勘误草稿 → 进评分制审核。绝不静默改原始数据。"""
    f = db.get(VerifyFlag, fid)
    if not f:
        raise HTTPException(404, "flag 不存在")
    if not is_dataset_member(db, f.dataset_id, user):
        raise HTTPException(403, "需为数据集成员")
    b = Bug(dataset_id=f.dataset_id, reporter_id=user.id, officer_id=f.officer_id,
            term_id=f.term_id, description_zh=f"[核验草稿] {f.issue_desc}",
            evidence=f"来源: {f.source} (confidence={f.confidence})", status="pending")
    db.add(b); db.flush()
    f.status = "drafted"; f.drafted_bug_id = b.id
    db.commit()
    return {"bug_id": b.id, "flag_status": "drafted"}


@router.post("/verify-flags/{fid}/dismiss")
def dismiss(fid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    f = db.get(VerifyFlag, fid)
    if not f:
        raise HTTPException(404, "flag 不存在")
    if not is_dataset_admin(db, f.dataset_id, user):
        raise HTTPException(403, "仅管理员可忽略")
    f.status = "dismissed"; db.commit()
    return {"ok": True}
