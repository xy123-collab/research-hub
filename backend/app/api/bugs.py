import io
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..core.storage import storage
from ..core.permissions import (get_current_user, is_dataset_member, is_dataset_admin,
                                count_dataset_admins, get_settings)
from ..core.audit import write_audit, record_contribution
from ..models.user import User
from ..models.dataset import Dataset, Variable
from ..models.version import DataVersion
from ..models.correction import Bug, CorrectionReview, CorrectionFinal
from ..models.curation import BugItem, VersionExtra, DatasetDataConfig
from ..schemas.models import BugIn, ReviewIn, FinalizeIn

router = APIRouter(tags=["bugs"])


def _uid_var(db, dataset_id) -> str | None:
    c = db.get(DatasetDataConfig, dataset_id)
    return c.unique_id_var if c else None


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
    # 单条勘误也建一个子项，统一按子项打分/终审/应用
    uidv = body.officer_id or body.term_id or ""
    db.add(BugItem(bug_id=b.id, dataset_id=d.id, seq=1, uid_value=uidv,
                   var_name=(_var_name(db, body.variable_id) if body.variable_id else ""),
                   current_value=body.current_value, suggested_value=body.suggested_value,
                   reason=body.description_zh, status="pending"))
    write_audit(db, user.id, "bug.submit", "bug", b.id)
    db.commit()
    return {"id": b.id}


def _var_name(db, variable_id):
    v = db.get(Variable, variable_id)
    return v.var_name if v else ""


# ============ 批量勘误：模板下载 + Excel/CSV 导入 ============
BATCH_COLS = ["唯一ID值", "变量名", "当前值", "建议值", "说明与证据"]


@router.get("/datasets/{slug}/bug-template")
def bug_template(slug: str, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """下载批量勘误 Excel 模板：含列头、规则注释与变量清单。"""
    from openpyxl import Workbook
    from openpyxl.comments import Comment
    d = _ds(db, slug)
    uidv = _uid_var(db, d.id)
    wb = Workbook()
    ws = wb.active; ws.title = "勘误"
    ws.append(BATCH_COLS)
    notes = {
        "唯一ID值": f"该数据集的唯一标识变量是「{uidv or '未设置，请管理员先在数据设置中指定'}」。"
                   "填该行记录对应的唯一ID取值（唯一ID本身不可被修改）。",
        "变量名": "要修改的变量名（须与数据集变量一致）。",
        "当前值": "该单元格现在的值。",
        "建议值": "建议改成的值。",
        "说明与证据": "修改理由与证据来源。",
    }
    for i, col in enumerate(BATCH_COLS, start=1):
        ws.cell(row=1, column=i).comment = Comment(notes[col], "系统")
    # 变量清单页，方便对照
    ws2 = wb.create_sheet("变量清单")
    ws2.append(["变量名", "标签"])
    for v in db.query(Variable).filter_by(dataset_id=d.id, enabled=True).all():
        ws2.append([v.var_name, v.label_zh or ""])
    ws3 = wb.create_sheet("填写说明")
    for line in [
        "批量勘误填写说明：",
        "1. 每一行是一个实际修改项；提交后会集成为一条勘误，便于统一查看。",
        "2. 但打分与终审仍会按行逐条进行（无论 AI 还是人工），确保每处修改单独确认。",
        f"3. 唯一ID变量：{uidv or '（管理员尚未设置，请先在数据集设置里指定唯一ID）'}，用于定位要改的记录。",
        "4. 唯一ID本身不允许被修改；变量名须与「变量清单」页一致。",
        "5. 支持 .xlsx / .csv，列顺序：" + "、".join(BATCH_COLS) + "。",
    ]:
        ws3.append([line])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f'attachment; filename="{d.slug}_bug_template.xlsx"'})


@router.post("/datasets/{slug}/bugs/batch")
def submit_bug_batch(slug: str, file: UploadFile = File(...), title: str = Form(""),
                     db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """批量导入：解析 Excel/CSV，集成为一条含多子项的勘误。"""
    d = _ds(db, slug)
    if not is_dataset_member(db, d.id, user):
        raise HTTPException(403, "非成员不能提交勘误")
    if get_settings(db, d.id).is_closed:
        raise HTTPException(400, "数据集已关闭，不再接受新勘误")
    raw = file.file.read()
    rows = _parse_batch(raw, file.filename)
    if not rows:
        raise HTTPException(400, "未解析到有效数据行，请用模板填写")
    b = Bug(dataset_id=d.id, reporter_id=user.id, status="pending",
            bug_type="batch", description_zh=title or f"批量勘误（{len(rows)} 条）")
    db.add(b); db.flush()
    for i, r in enumerate(rows, start=1):
        db.add(BugItem(bug_id=b.id, dataset_id=d.id, seq=i,
                       uid_value=str(r.get("唯一ID值", "")).strip(),
                       var_name=str(r.get("变量名", "")).strip(),
                       current_value=str(r.get("当前值", "")).strip(),
                       suggested_value=str(r.get("建议值", "")).strip(),
                       reason=str(r.get("说明与证据", "")).strip(), status="pending"))
    write_audit(db, user.id, "bug.submit.batch", "bug", b.id, {"items": len(rows)})
    db.commit()
    return {"id": b.id, "items": len(rows)}


def _parse_batch(raw: bytes, filename: str) -> list[dict]:
    name = (filename or "").lower()
    rows = []
    if name.endswith(".csv") or (not name.endswith(".xlsx") and b"," in raw[:200]):
        import csv
        text = raw.decode("utf-8-sig", errors="replace")
        for r in csv.DictReader(io.StringIO(text)):
            if any((v or "").strip() for v in r.values()):
                rows.append(r)
    else:
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        ws = wb["勘误"] if "勘误" in wb.sheetnames else wb.worksheets[0]
        header = None
        for row in ws.iter_rows(values_only=True):
            if header is None:
                header = [str(c).strip() if c is not None else "" for c in row]
                continue
            if row is None or all(c is None for c in row):
                continue
            rows.append({header[i]: row[i] for i in range(min(len(header), len(row)))})
    return rows


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
            "items": [{"id": it.id, "seq": it.seq, "uid_value": it.uid_value,
                       "var_name": it.var_name, "current_value": it.current_value,
                       "suggested_value": it.suggested_value, "reason": it.reason,
                       "status": it.status, "ai_score": it.ai_score,
                       "final_score": it.final_score, "adopt_level": it.adopt_level}
                      for it in db.query(BugItem).filter_by(bug_id=bid).order_by(BugItem.seq).all()],
            "attachments": [{"id": a.id, "file_name": a.file_name, "size": a.size} for a in atts]}


# ============ 逐条子项：AI 评分 / 管理员终审 ============
@router.post("/bug-items/{iid}/ai-review")
def ai_review_item(iid: int, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    from ..core.ai_client import ai_client
    it = db.get(BugItem, iid)
    if not it:
        raise HTTPException(404, "勘误项不存在")
    if not is_dataset_member(db, it.dataset_id, user):
        raise HTTPException(403, "需为数据集成员")
    prompt = (f"勘误：变量 {it.var_name} 记录 {it.uid_value} 当前值={it.current_value} "
              f"建议值={it.suggested_value} 理由={it.reason}。给 0-10 可采纳度，仅回数字。")
    resp = ai_client.complete(prompt, "你是数据质量评审助手，只输出 0-10 的数字。")
    try:
        it.ai_score = max(0, min(10, float("".join(c for c in resp if c.isdigit() or c == ".").split(".")[0] or 5)))
    except Exception:
        it.ai_score = 5.0
    db.commit()
    return {"ai_score": it.ai_score}


@router.post("/bug-items/{iid}/finalize")
def finalize_item(iid: int, body: FinalizeIn, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    it = db.get(BugItem, iid)
    if not it:
        raise HTTPException(404, "勘误项不存在")
    if not is_dataset_admin(db, it.dataset_id, user):
        raise HTTPException(403, "仅数据集管理员可审核")
    b = db.get(Bug, it.bug_id)
    # 自审校验：本人提交且存在其他管理员时须由他人审
    if b and b.reporter_id == user.id and count_dataset_admins(db, it.dataset_id) > 1:
        raise HTTPException(403, "这是你本人提交的勘误，请由另一名管理员审核")
    it.adopt_level = body.adopt_level
    it.final_score = body.final_score
    it.status = "accepted" if body.adopt_level != "reject" else "rejected"
    it.reviewed_by = user.id; it.reviewed_at = datetime.utcnow()
    if body.adopt_level != "reject" and b:
        record_contribution(db, b.reporter_id, "bug_accepted", "bug_item", iid,
                            it.dataset_id, weight=body.final_score)
    # 聚合更新父勘误状态
    if b:
        items = db.query(BugItem).filter_by(bug_id=b.id).all()
        if all(x.status in ("accepted", "rejected", "fixed") for x in items):
            b.status = "accepted" if any(x.status == "accepted" for x in items) else "rejected"
            b.reviewed_by = user.id; b.reviewed_at = datetime.utcnow()
    write_audit(db, user.id, "bug.item.finalize", "bug_item", iid,
                {"adopt": body.adopt_level, "score": body.final_score})
    db.commit()
    return {"ok": True, "status": it.status}


# ============ 一键把已采纳勘误应用到上一版数据，生成新版本 ============
@router.post("/datasets/{slug}/apply-corrections")
def apply_corrections_endpoint(slug: str, base_version_id: int = Form(...),
                               new_version_id: str = Form(...), changelog_zh: str = Form(""),
                               db: Session = Depends(get_db),
                               user: User = Depends(get_current_user)):
    from ..services.data_ops import apply_corrections
    d = _ds(db, slug)
    if not is_dataset_admin(db, d.id, user):
        raise HTTPException(403, "仅数据集管理员可应用勘误发版")
    if get_settings(db, d.id).is_closed:
        raise HTTPException(400, "数据集已关闭")
    base = db.get(DataVersion, base_version_id)
    if not base or base.dataset_id != d.id or not base.data_file_path:
        raise HTTPException(404, "基准版本不存在或无数据文件")
    if db.query(DataVersion).filter_by(dataset_id=d.id, version_id=new_version_id).first():
        raise HTTPException(400, f"版本 {new_version_id} 已存在")
    cfg = db.get(DatasetDataConfig, d.id)
    uidv = cfg.unique_id_var if cfg else None
    if not uidv:
        raise HTTPException(400, "请先在数据设置里指定唯一ID变量，才能按ID定位修改")
    items = db.query(BugItem).filter_by(dataset_id=d.id, status="accepted").filter(
        BugItem.applied_in_version.is_(None)).all()
    if not items:
        raise HTTPException(400, "没有待应用的已采纳勘误项")
    payload = [{"seq": it.id, "uid_value": it.uid_value, "var_name": it.var_name,
                "suggested_value": it.suggested_value} for it in items]
    new_bytes, source, script, applied_ids = apply_corrections(
        base.data_file_path, payload, uidv, cfg.script_only if cfg else False)
    if new_bytes is None:
        write_audit(db, user.id, "dataset.apply_corrections.script", "dataset", d.id)
        return {"generated": "script", "script": script,
                "note": "数据过大或设为仅脚本模式：请在本地运行脚本改好数据后，用「发布新版本·原始」上传。"}
    key = f"versions/{d.slug}/{new_version_id}/data.dta"
    storage.save(key, io.BytesIO(new_bytes))
    db.query(DataVersion).filter_by(dataset_id=d.id, is_current=True).update(
        {"is_current": False, "valid_to": datetime.utcnow()})
    v = DataVersion(dataset_id=d.id, version_id=new_version_id, based_on_version=base.version_id,
                    release_date=datetime.utcnow(), data_file_path=key,
                    changelog_zh=changelog_zh or f"应用 {len(applied_ids)} 条已采纳勘误",
                    created_by=user.id, is_current=True, valid_from=datetime.utcnow())
    db.add(v); db.flush()
    db.add(VersionExtra(version_id=v.id, data_kind="raw", generated=source))
    d.current_version_id = v.id
    applied_set = set(applied_ids)
    for it in items:
        if it.id in applied_set:
            it.status = "fixed"; it.applied_in_version = v.id
    write_audit(db, user.id, "dataset.apply_corrections.server", "dataset", d.id,
                {"version": new_version_id, "applied": len(applied_ids)})
    db.commit()
    return {"generated": "server", "id": v.id, "version_id": new_version_id,
            "applied": len(applied_ids)}
