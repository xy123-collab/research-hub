from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..core.permissions import get_current_user, is_dataset_member, is_dataset_admin
from ..core.audit import write_audit, record_contribution
from ..core.ai_client import ai_client
from ..models.user import User
from ..models.dataset import Dataset
from ..models.code import CodeScript, CodeBug, CodeWriteup
from ..models.correction import CorrectionReview, CorrectionFinal
from ..schemas.models import CodeIn, CodeBugIn, ReviewIn, FinalizeIn

router = APIRouter(tags=["code"])


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
    return {"id": c.id, "filename": c.filename, "lang": c.lang, "title_zh": c.title_zh,
            "desc_zh": c.desc_zh, "source_code": c.source_code, "author_id": c.author_id}


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
