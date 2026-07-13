from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..core.permissions import (get_current_user, is_dataset_member, is_dataset_admin,
                                count_dataset_admins, get_settings)
from ..core.audit import write_audit, record_contribution
from ..models.user import User
from ..models.dataset import Dataset
from ..models.correction import Bug, CorrectionReview, CorrectionFinal
from ..schemas.models import BugIn, ReviewIn, FinalizeIn

router = APIRouter(tags=["bugs"])


def _ds(db, slug):
    d = db.query(Dataset).filter_by(slug=slug, is_deleted=False).first()
    if not d:
        raise HTTPException(404, "数据集不存在")
    return d


@router.get("/datasets/{slug}/bugs")
def list_bugs(slug: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    d = _ds(db, slug)
    bugs = db.query(Bug).filter_by(dataset_id=d.id).order_by(Bug.id.desc()).all()
    return [{"id": b.id, "officer_id": b.officer_id, "term_id": b.term_id,
             "current_value": b.current_value, "suggested_value": b.suggested_value,
             "description_zh": b.description_zh, "status": b.status,
             "reporter_id": b.reporter_id} for b in bugs]


@router.post("/datasets/{slug}/bugs")
def submit_bug(slug: str, body: BugIn, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    d = _ds(db, slug)
    if not is_dataset_member(db, d.id, user):
        raise HTTPException(403, "非成员不能提交勘误，请先申请加入处理")
    if get_settings(db, d.id).is_closed:
        raise HTTPException(400, "数据集已关闭，不再接受新勘误")
    b = Bug(dataset_id=d.id, reporter_id=user.id, status="pending", **body.model_dump())
    db.add(b); db.flush()
    write_audit(db, user.id, "bug.submit", "bug", b.id)
    db.commit()
    return {"id": b.id}


@router.patch("/bugs/{bid}")
def edit_bug(bid: int, body: BugIn, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    b = db.get(Bug, bid)
    if not b:
        raise HTTPException(404, "勘误不存在")
    if b.reporter_id != user.id or b.status != "pending":
        raise HTTPException(403, "仅本人且未审核前可改")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(b, k, v)
    db.commit()
    return {"ok": True}


@router.delete("/bugs/{bid}")
def del_bug(bid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    b = db.get(Bug, bid)
    if not b:
        raise HTTPException(404, "勘误不存在")
    if b.reporter_id != user.id or b.status != "pending":
        raise HTTPException(403, "仅本人且未审核前可删")
    db.delete(b); db.commit()
    return {"ok": True}


@router.get("/bugs/{bid}/reviews")
def get_reviews(bid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rs = db.query(CorrectionReview).filter_by(target_type="bug", target_id=bid).all()
    fin = db.query(CorrectionFinal).filter_by(target_type="bug", target_id=bid).first()
    return {"reviews": [{"reviewer_type": r.reviewer_type, "reviewer_id": r.reviewer_id,
                         "score": r.acceptability_score, "comment": r.comment} for r in rs],
            "final": ({"adopt_level": fin.adopt_level, "final_score": fin.final_score,
                       "comment": fin.comment} if fin else None)}


@router.post("/bugs/{bid}/reviews")
def review_bug(bid: int, body: ReviewIn, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    b = db.get(Bug, bid)
    if not b:
        raise HTTPException(404, "勘误不存在")
    if not is_dataset_member(db, b.dataset_id, user):
        raise HTTPException(403, "需为数据集成员")
    db.add(CorrectionReview(target_type="bug", target_id=bid, reviewer_type="member",
                            reviewer_id=user.id, acceptability_score=body.acceptability_score,
                            comment=body.comment))
    db.commit()
    return {"ok": True}


@router.post("/bugs/{bid}/ai-review")
def ai_review_bug(bid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..core.ai_client import ai_client
    b = db.get(Bug, bid)
    if not b:
        raise HTTPException(404, "勘误不存在")
    prompt = (f"勘误：变量当前值={b.current_value} 建议值={b.suggested_value} "
              f"说明={b.description_zh}。给 0-10 可采纳度分，仅回数字。")
    resp = ai_client.complete(prompt, "你是数据质量评审助手，只输出 0-10 的数字。")
    try:
        score = float("".join(c for c in resp if (c.isdigit() or c == ".")).split(".")[0] or 5)
        score = max(0, min(10, score))
    except Exception:
        score = 5.0
    db.add(CorrectionReview(target_type="bug", target_id=bid, reviewer_type="ai",
                            reviewer_id=None, acceptability_score=score, comment=resp[:500]))
    db.commit()
    return {"ai_score": score}


@router.post("/bugs/{bid}/finalize")
def finalize_bug(bid: int, body: FinalizeIn, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    b = db.get(Bug, bid)
    if not b:
        raise HTTPException(404, "勘误不存在")
    if not is_dataset_admin(db, b.dataset_id, user):
        raise HTTPException(403, "仅数据集管理员可审核勘误")
    if b.status != "pending":
        raise HTTPException(400, "该勘误已处理")
    # 八节 4：管理员本人提交的勘误，若还有其他管理员，应由另一名管理员审核
    self_review = (b.reporter_id == user.id)
    if self_review and count_dataset_admins(db, b.dataset_id) > 1:
        raise HTTPException(403, "这是你本人提交的勘误，请由另一名数据集管理员审核")
    db.add(CorrectionFinal(target_type="bug", target_id=bid, decided_by=user.id,
                           adopt_level=body.adopt_level, final_score=body.final_score,
                           comment=body.comment, decided_at=datetime.utcnow()))
    b.status = "accepted" if body.adopt_level != "reject" else "rejected"
    b.reviewed_by = user.id; b.reviewed_at = datetime.utcnow()
    if body.adopt_level != "reject":
        # 报告人贡献按终审分加权
        record_contribution(db, b.reporter_id, "bug_accepted", "bug", bid,
                            b.dataset_id, weight=body.final_score)
        # 参与评审且方向与终审一致者 +k
        member_reviews = db.query(CorrectionReview).filter_by(
            target_type="bug", target_id=bid, reviewer_type="member").all()
        for r in member_reviews:
            aligned = (r.acceptability_score >= 5) == (body.final_score >= 5)
            if aligned and r.reviewer_id:
                record_contribution(db, r.reviewer_id, "review_adopted", "bug", bid,
                                    b.dataset_id, weight=3)
    write_audit(db, user.id, "bug.finalize", "bug", bid,
                {"adopt": body.adopt_level, "score": body.final_score,
                 "self_review": self_review})
    db.commit()
    return {"ok": True, "status": b.status}


# ================= bug 证据附件（真实文件上传）=================
from fastapi import UploadFile, File  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402


@router.post("/bugs/{bid}/attachments")
def upload_bug_attachment(bid: int, file: UploadFile = File(...),
                          db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)):
    from ..models.correction import BugAttachment
    from ..services.uploads import save_upload
    from datetime import datetime
    b = db.get(Bug, bid)
    if not b:
        raise HTTPException(404, "勘误不存在")
    if not is_dataset_member(db, b.dataset_id, user):
        raise HTTPException(403, "需为数据集成员")
    meta = save_upload(file, f"bug/{bid}")
    a = BugAttachment(bug_id=bid, uploaded_by=user.id, uploaded_at=datetime.utcnow(), **meta)
    db.add(a); db.commit(); db.refresh(a)
    return {"id": a.id, "file_name": a.file_name, "size": a.size}


@router.get("/bugs/{bid}/attachments")
def list_bug_attachments(bid: int, db: Session = Depends(get_db),
                         user: User = Depends(get_current_user)):
    from ..models.correction import BugAttachment
    rows = db.query(BugAttachment).filter_by(bug_id=bid).all()
    return [{"id": a.id, "file_name": a.file_name, "size": a.size, "mime": a.mime}
            for a in rows]


@router.get("/bug-attachments/{aid}/download")
def download_bug_attachment(aid: int, db: Session = Depends(get_db),
                            user: User = Depends(get_current_user)):
    from ..models.correction import BugAttachment
    from ..core.storage import storage
    a = db.get(BugAttachment, aid)
    if not a:
        raise HTTPException(404, "附件不存在")
    b = db.get(Bug, a.bug_id)
    if not is_dataset_member(db, b.dataset_id, user):
        raise HTTPException(403, "需为数据集成员")
    return StreamingResponse(storage.open(a.file_path), media_type=a.mime or "application/octet-stream",
                             headers={"Content-Disposition": f'attachment; filename="{a.file_name}"'})


@router.get("/bugs/{bid}")
def bug_detail(bid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..models.correction import BugAttachment
    from ..models.version import DataVersion
    b = db.get(Bug, bid)
    if not b:
        raise HTTPException(404, "勘误不存在")
    reporter = db.get(User, b.reporter_id)
    reviews = db.query(CorrectionReview).filter_by(target_type="bug", target_id=bid).all()
    fin = db.query(CorrectionFinal).filter_by(target_type="bug", target_id=bid).first()
    atts = db.query(BugAttachment).filter_by(bug_id=bid).all()
    fixed_v = db.get(DataVersion, b.fixed_in_version_id) if b.fixed_in_version_id else None
    return {"id": b.id, "dataset_id": b.dataset_id, "officer_id": b.officer_id,
            "term_id": b.term_id, "current_value": b.current_value,
            "suggested_value": b.suggested_value, "description_zh": b.description_zh,
            "evidence": b.evidence, "status": b.status,
            "reporter": {"id": b.reporter_id, "name": reporter.display_name if reporter else ""},
            "fixed_in_version": fixed_v.version_id if fixed_v else None,
            "reviews": [{"reviewer_type": r.reviewer_type, "reviewer_id": r.reviewer_id,
                         "score": r.acceptability_score, "comment": r.comment} for r in reviews],
            "final": ({"adopt_level": fin.adopt_level, "final_score": fin.final_score,
                       "comment": fin.comment} if fin else None),
            "attachments": [{"id": a.id, "file_name": a.file_name, "size": a.size} for a in atts]}
