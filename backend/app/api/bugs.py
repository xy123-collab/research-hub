import io
import hashlib
import json
from collections import Counter
from decimal import Decimal, InvalidOperation
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
from ..core.time import china_iso

router = APIRouter(tags=["bugs"])


def _uid_var(db, dataset_id) -> str | None:
    c = db.get(DatasetDataConfig, dataset_id)
    return c.unique_id_var if c else None


def _ds(db, slug):
    d = db.query(Dataset).filter_by(slug=slug, is_deleted=False).first()
    if not d:
        raise HTTPException(404, "数据集不存在")
    return d


def _latest_raw_version(db: Session, dataset_id: int) -> DataVersion | None:
    rows = db.query(DataVersion).filter_by(dataset_id=dataset_id).order_by(
        DataVersion.id.desc()).all()
    for version in rows:
        if not version.data_file_path:
            continue
        extra = db.get(VersionExtra, version.id)
        if (extra.data_kind if extra else "raw") == "raw":
            return version
    return None


def _canonical_uid(value, numeric: bool) -> str:
    if value is None:
        return ""
    try:
        import pandas as pd
        if pd.isna(value):
            return ""
    except Exception:
        pass
    text = str(value).strip()
    if not numeric:
        return text
    try:
        return format(Decimal(text).normalize(), "f")
    except (InvalidOperation, ValueError):
        return text


def _uid_context(db: Session, dataset_id: int) -> dict:
    """读取最新原始版本唯一 ID 列，并建立规范化计数索引。"""
    cfg = db.get(DatasetDataConfig, dataset_id)
    uid_var = cfg.unique_id_var if cfg else None
    if not uid_var:
        raise HTTPException(400, "管理员尚未设置唯一 ID 变量，请先到版本库的「数据处理设置」配置")
    version = _latest_raw_version(db, dataset_id)
    if not version:
        raise HTTPException(400, "还没有可用于核对唯一 ID 的原始数据版本，请管理员先发布原始数据")
    try:
        from ..services.introspect import read_table_column
        import pandas as pd
        series = read_table_column(version.data_file_path, uid_var)
        numeric = bool(pd.api.types.is_numeric_dtype(series))
        counts = Counter(_canonical_uid(value, numeric) for value in series)
    except Exception as exc:
        raise HTTPException(
            400, f"无法读取最新原始版本「{version.version_id}」的唯一 ID：{exc}。"
                 "请检查文件是否仍在 COS、格式是否正确及唯一 ID 配置") from exc
    return {"unique_id_var": uid_var, "version": version,
            "numeric": numeric, "counts": counts}


def _check_uid(context: dict, value) -> dict:
    raw = str(value or "").strip()
    if not raw:
        raise HTTPException(400, f"请填写{context['unique_id_var']}（唯一 ID）")
    normalized = _canonical_uid(raw, context["numeric"])
    count = int(context["counts"].get(normalized, 0))
    if count > 1:
        raise HTTPException(
            400, f"{context['unique_id_var']}={raw} 在最新原始版本中匹配到 {count} 条；"
                 "唯一 ID 不唯一，请管理员先修正数据或配置")
    return {"value": raw, "normalized": normalized, "count": count, "exists": count == 1}


def _effective_bug_status(items: list[BugItem], fallback: str) -> str:
    if not items:
        return fallback
    states = {item.status for item in items}
    if "pending" in states:
        return "pending"
    if "accepted" in states:
        return "accepted"
    if "fixed" in states:
        return "fixed"
    return "rejected"


def _sync_bug_status(db: Session, bug: Bug, fixed_version_id: int | None = None) -> str:
    items = db.query(BugItem).filter_by(bug_id=bug.id).all()
    bug.status = _effective_bug_status(items, bug.status)
    if bug.status == "fixed" and fixed_version_id:
        bug.fixed_in_version_id = fixed_version_id
    return bug.status


@router.get("/datasets/{slug}/bugs")
def list_bugs(slug: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    d = _ds(db, slug)
    bugs = db.query(Bug).filter_by(dataset_id=d.id).order_by(Bug.id.desc()).all()
    out = []
    for b in bugs:
        items = db.query(BugItem).filter_by(bug_id=b.id).order_by(BugItem.seq).all()
        reporter = db.get(User, b.reporter_id)
        reviewer_count = db.query(CorrectionReview.reviewer_id).filter_by(
            target_type="bug", target_id=b.id, reviewer_type="member").filter(
            CorrectionReview.reviewer_id.is_not(None)).distinct().count()
        out.append({
            "id": b.id, "officer_id": b.officer_id, "term_id": b.term_id,
            "current_value": b.current_value, "suggested_value": b.suggested_value,
            "description_zh": b.description_zh,
            "status": _effective_bug_status(items, b.status),
            "reporter_id": b.reporter_id,
            "reporter_name": reporter.display_name if reporter else "已注销用户",
            "created_at": china_iso(b.created_at),
            "reviewer_count": reviewer_count,
            "has_new_officer": any(bool(it.is_new_officer) for it in items),
        })
    return out


@router.get("/datasets/{slug}/bugs/id-check")
def check_bug_uid(slug: str, value: str, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    d = _ds(db, slug)
    if not is_dataset_member(db, d.id, user):
        raise HTTPException(403, "需为数据集成员")
    context = _uid_context(db, d.id)
    result = _check_uid(context, value)
    return {"unique_id_var": context["unique_id_var"],
            "source_version": context["version"].version_id, **result}


@router.post("/datasets/{slug}/bugs")
def submit_bug(slug: str, body: dict, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    d = _ds(db, slug)
    if not is_dataset_member(db, d.id, user):
        raise HTTPException(403, "非成员不能提交勘误，请先申请加入处理")
    if get_settings(db, d.id).is_closed:
        raise HTTPException(400, "数据集已关闭，不再接受新勘误")
    try:
        body = BugIn.model_validate(body)
    except Exception as exc:
        raise HTTPException(422, "请完整填写勘误说明和证据") from exc
    context = _uid_context(db, d.id)
    uid_value = body.officer_id or body.term_id or ""
    check = _check_uid(context, uid_value)
    if not check["exists"] and not body.confirm_new_officer:
        raise HTTPException(
            409, f"最新原始版本中没有 {context['unique_id_var']}={check['value']}。"
                 "请确认 ID 是否填错；若确为新增官员，请勾选确认后再提交")
    var = db.get(Variable, body.variable_id) if body.variable_id else None
    if not var or var.dataset_id != d.id or not var.enabled:
        raise HTTPException(400, "请选择本数据集当前有效的勘误变量")
    if var.var_name == context["unique_id_var"]:
        raise HTTPException(400, "唯一 ID 变量本身不能作为勘误修改对象")
    data = body.model_dump(exclude={"confirm_new_officer"})
    b = Bug(dataset_id=d.id, reporter_id=user.id, status="pending",
            created_at=datetime.utcnow(), **data)
    db.add(b); db.flush()
    # 单条勘误也建一个子项，统一按子项打分/终审/应用
    db.add(BugItem(bug_id=b.id, dataset_id=d.id, seq=1, uid_value=check["value"],
                   var_name=var.var_name,
                   current_value=body.current_value, suggested_value=body.suggested_value,
                   reason=body.description_zh, evidence=body.evidence,
                   is_new_officer=not check["exists"], status="pending"))
    write_audit(db, user.id, "bug.submit", "bug", b.id,
                {"is_new_officer": not check["exists"],
                 "checked_version": context["version"].version_id})
    db.commit()
    return {"id": b.id}


def _var_name(db, variable_id):
    v = db.get(Variable, variable_id)
    return v.var_name if v else ""


# ============ 批量勘误：模板下载 + Excel/CSV 导入 ============
BATCH_COLS = ["唯一ID值", "变量名", "当前值", "建议值", "说明", "证据"]
BATCH_REQUIRED = ["唯一ID值", "变量名", "说明", "证据"]


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
        "说明": "为什么需要修改（必填）。",
        "证据": "证据来源、链接或出处（必填；附件可在单条勘误中另行上传）。",
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
        "5. 「说明」和「证据」是两个独立必填列，旧版合并列模板不再接受。",
        "6. 支持 .xlsx / .csv，列顺序：" + "、".join(BATCH_COLS) + "。",
    ]:
        ws3.append([line])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f'attachment; filename="{d.slug}_bug_template.xlsx"'})


def _validate_batch_rows(db: Session, dataset: Dataset, rows: list[dict]) -> tuple[dict, list[dict]]:
    if not rows:
        raise HTTPException(400, "未解析到有效数据行，请用最新模板填写")
    header = set(rows[0].keys())
    if "说明与证据" in header:
        raise HTTPException(400, "这是旧版批量模板。请重新下载模板，将「说明」和「证据」分列填写")
    missing_cols = [col for col in BATCH_COLS if col not in header]
    if missing_cols:
        raise HTTPException(400, "批量模板缺少列：" + "、".join(missing_cols))
    errors = []
    context = _uid_context(db, dataset.id)
    variables = {v.var_name for v in db.query(Variable).filter_by(
        dataset_id=dataset.id, enabled=True).all()}
    checked = []
    for row_no, row in enumerate(rows, start=2):
        cleaned = {key: str(row.get(key, "") if row.get(key) is not None else "").strip()
                   for key in BATCH_COLS}
        missing = [col for col in BATCH_REQUIRED if not cleaned[col]]
        if missing:
            errors.append(f"第 {row_no} 行缺少：" + "、".join(missing))
            continue
        if cleaned["变量名"] not in variables:
            errors.append(f"第 {row_no} 行变量「{cleaned['变量名']}」不在当前变量清单")
            continue
        if cleaned["变量名"] == context["unique_id_var"]:
            errors.append(f"第 {row_no} 行试图修改唯一 ID 变量本身")
            continue
        try:
            uid_check = _check_uid(context, cleaned["唯一ID值"])
        except HTTPException as exc:
            errors.append(f"第 {row_no} 行：{exc.detail}")
            continue
        checked.append({"row_no": row_no, "row": cleaned, "uid": uid_check})
    if errors:
        raise HTTPException(400, "；".join(errors[:20]))
    return context, checked


@router.post("/datasets/{slug}/bugs/batch/validate")
def validate_bug_batch(slug: str, file: UploadFile = File(...),
                       db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    d = _ds(db, slug)
    if not is_dataset_member(db, d.id, user):
        raise HTTPException(403, "非成员不能提交勘误")
    rows = _parse_batch(file.file.read(), file.filename)
    context, checked = _validate_batch_rows(db, d, rows)
    missing = []
    seen = set()
    for item in checked:
        if not item["uid"]["exists"] and item["uid"]["value"] not in seen:
            seen.add(item["uid"]["value"])
            missing.append(item["uid"]["value"])
    return {"rows": len(checked), "unique_id_var": context["unique_id_var"],
            "source_version": context["version"].version_id,
            "missing_uid_values": missing}


@router.post("/datasets/{slug}/bugs/batch")
def submit_bug_batch(slug: str, file: UploadFile = File(...), title: str = Form(""),
                     confirmed_new_officer_ids: str = Form("[]"),
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
    context, checked = _validate_batch_rows(db, d, rows)
    try:
        confirmed = {str(x).strip() for x in json.loads(confirmed_new_officer_ids or "[]")}
    except Exception:
        raise HTTPException(400, "新增官员确认参数格式错误，请重新校验批量文件")
    unconfirmed = sorted({item["uid"]["value"] for item in checked
                          if not item["uid"]["exists"] and item["uid"]["value"] not in confirmed})
    if unconfirmed:
        raise HTTPException(
            409, "以下 ID 在最新原始版本中不存在，请确认它们是新增官员后再提交："
                 + "、".join(unconfirmed[:20]))
    b = Bug(dataset_id=d.id, reporter_id=user.id, status="pending",
            bug_type="batch", description_zh=title or f"批量勘误（{len(checked)} 条）",
            evidence=f"逐条证据见批量勘误子项", created_at=datetime.utcnow())
    db.add(b); db.flush()
    for i, item in enumerate(checked, start=1):
        r = item["row"]
        db.add(BugItem(bug_id=b.id, dataset_id=d.id, seq=i,
                       uid_value=r["唯一ID值"], var_name=r["变量名"],
                       current_value=r["当前值"], suggested_value=r["建议值"],
                       reason=r["说明"], evidence=r["证据"],
                       is_new_officer=not item["uid"]["exists"], status="pending"))
    write_audit(db, user.id, "bug.submit.batch", "bug", b.id,
                {"items": len(checked),
                 "new_officer_ids": sorted(confirmed),
                 "checked_version": context["version"].version_id})
    db.commit()
    return {"id": b.id, "items": len(checked)}


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
    context = _uid_context(db, b.dataset_id)
    check = _check_uid(context, body.officer_id or body.term_id)
    if not check["exists"] and not body.confirm_new_officer:
        raise HTTPException(409, "该唯一 ID 不存在；若确为新增官员，请勾选确认后再保存")
    var = db.get(Variable, body.variable_id) if body.variable_id else None
    if not var or var.dataset_id != b.dataset_id or not var.enabled:
        raise HTTPException(400, "请选择本数据集当前有效的勘误变量")
    for k, v in body.model_dump(
            exclude={"confirm_new_officer"}, exclude_none=True).items():
        setattr(b, k, v)
    item = db.query(BugItem).filter_by(bug_id=b.id).order_by(BugItem.seq).first()
    if item:
        item.uid_value = check["value"]
        item.var_name = var.var_name
        item.current_value = body.current_value
        item.suggested_value = body.suggested_value
        item.reason = body.description_zh
        item.evidence = body.evidence
        item.is_new_officer = not check["exists"]
    db.commit()
    return {"ok": True}


@router.delete("/bugs/{bid}")
def del_bug(bid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    b = db.get(Bug, bid)
    if not b:
        raise HTTPException(404, "勘误不存在")
    if b.reporter_id != user.id or b.status != "pending":
        raise HTTPException(403, "仅本人且未审核前可删")
    from ..models.correction import BugAttachment
    db.query(CorrectionReview).filter_by(target_type="bug", target_id=bid).delete(
        synchronize_session=False)
    db.query(CorrectionReview).filter_by(target_type="bug_item").filter(
        CorrectionReview.target_id.in_(
            db.query(BugItem.id).filter_by(bug_id=bid))).delete(
                synchronize_session=False)
    db.query(CorrectionFinal).filter_by(target_type="bug", target_id=bid).delete(
        synchronize_session=False)
    db.query(BugAttachment).filter_by(bug_id=bid).delete(synchronize_session=False)
    db.query(BugItem).filter_by(bug_id=bid).delete(synchronize_session=False)
    db.query(Bug).filter_by(id=bid).delete(synchronize_session=False)
    db.commit()
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
    if _effective_bug_status(
            db.query(BugItem).filter_by(bug_id=bid).all(), b.status) != "pending":
        raise HTTPException(400, "该勘误已终审，不能继续评分")
    review = db.query(CorrectionReview).filter_by(
        target_type="bug", target_id=bid, reviewer_type="member",
        reviewer_id=user.id).first()
    if not review:
        review = CorrectionReview(target_type="bug", target_id=bid,
                                  reviewer_type="member", reviewer_id=user.id)
        db.add(review)
    review.acceptability_score = body.acceptability_score
    review.comment = body.comment
    db.commit()
    return {"ok": True}


def _parse_ai_review(response: str) -> tuple[float, str]:
    try:
        start, end = response.find("{"), response.rfind("}")
        payload = json.loads(response[start:end + 1])
        score = float(payload["score"])
        reason = str(payload["reason"]).strip()
        if not 0 <= score <= 10 or not reason:
            raise ValueError
        return score, reason[:1000]
    except Exception as exc:
        raise HTTPException(502, "AI 评分返回格式异常，未保存任何分数，请稍后重试") from exc


def _run_ai_review(prompt: str) -> tuple[float, str]:
    from ..core.ai_client import ai_client
    if not ai_client.enabled():
        raise HTTPException(400, "AI 勘误评分尚未启用，请联系平台管理员配置 AI")
    response = ai_client.complete(
        prompt,
        '你是数据质量评审助手。只输出 JSON：{"score":0到10的数字,"reason":"具体评分理由"}。'
        "必须同时比较当前值和建议值，并结合修改说明与证据；不得只给分不解释。",
    )
    return _parse_ai_review(response)


@router.post("/bugs/{bid}/ai-review")
def ai_review_bug(bid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    b = db.get(Bug, bid)
    if not b:
        raise HTTPException(404, "勘误不存在")
    if not is_dataset_member(db, b.dataset_id, user):
        raise HTTPException(403, "需为数据集成员")
    if not (b.description_zh or "").strip() or not (b.evidence or "").strip():
        raise HTTPException(400, "该历史勘误缺少独立的说明或证据，补充完整后才能进行 AI 评分")
    prompt = (f"当前值：{b.current_value or ''}\n建议值：{b.suggested_value or ''}\n"
              f"修改说明：{b.description_zh}\n证据：{b.evidence}")
    score, reason = _run_ai_review(prompt)
    review = db.query(CorrectionReview).filter_by(
        target_type="bug", target_id=bid, reviewer_type="ai").first()
    if not review:
        review = CorrectionReview(target_type="bug", target_id=bid, reviewer_type="ai")
        db.add(review)
    review.acceptability_score = score
    review.comment = reason
    db.commit()
    return {"ai_score": score, "reason": reason}


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
    child_status = "accepted" if body.adopt_level != "reject" else "rejected"
    for item in db.query(BugItem).filter_by(bug_id=bid, status="pending").all():
        item.status = child_status
        item.adopt_level = body.adopt_level
        item.final_score = body.final_score
        item.reviewed_by = user.id
        item.reviewed_at = datetime.utcnow()
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
    from ..services.uploads import open_stored_file
    stream = open_stored_file(a.file_path)
    from ..services.downloads import log_download
    from ..models.dataset import Dataset as _DS
    _d = db.get(_DS, b.dataset_id)
    log_download(db, user_id=user.id, source="bug_attachment", dataset_id=b.dataset_id,
                 location_label=(_d.name_zh if _d else "勘误附件"),
                 detail=f"勘误#{b.id} 附件", file_name=a.file_name,
                 link=(f"/#/datasets/{_d.slug}?tab=bugs&bug={b.id}" if _d else ""))
    db.commit()
    from ..services.uploads import attachment_headers
    return StreamingResponse(stream, media_type=a.mime or "application/octet-stream",
                             headers=attachment_headers(a.file_name))


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
    items = db.query(BugItem).filter_by(bug_id=bid).order_by(BugItem.seq).all()
    item_ai = {}
    for review in db.query(CorrectionReview).filter_by(
            target_type="bug_item", reviewer_type="ai").filter(
            CorrectionReview.target_id.in_([it.id for it in items] or [-1])).all():
        item_ai[review.target_id] = review.comment
    reviewer_count = db.query(CorrectionReview.reviewer_id).filter_by(
        target_type="bug", target_id=bid, reviewer_type="member").filter(
        CorrectionReview.reviewer_id.is_not(None)).distinct().count()
    return {"id": b.id, "dataset_id": b.dataset_id, "officer_id": b.officer_id,
            "term_id": b.term_id, "current_value": b.current_value,
            "suggested_value": b.suggested_value, "description_zh": b.description_zh,
            "evidence": b.evidence, "status": _effective_bug_status(items, b.status),
            "created_at": china_iso(b.created_at), "reviewer_count": reviewer_count,
            "reporter": {"id": b.reporter_id, "name": reporter.display_name if reporter else ""},
            "fixed_in_version": fixed_v.version_id if fixed_v else None,
            "reviews": [{"reviewer_type": r.reviewer_type, "reviewer_id": r.reviewer_id,
                         "score": r.acceptability_score, "comment": r.comment} for r in reviews],
            "final": ({"adopt_level": fin.adopt_level, "final_score": fin.final_score,
                       "comment": fin.comment} if fin else None),
            "items": [{"id": it.id, "seq": it.seq, "uid_value": it.uid_value,
                       "var_name": it.var_name, "current_value": it.current_value,
                       "suggested_value": it.suggested_value, "reason": it.reason,
                       "evidence": it.evidence,
                       "is_new_officer": bool(it.is_new_officer),
                       "status": it.status, "ai_score": it.ai_score,
                       "ai_reason": item_ai.get(it.id),
                       "final_score": it.final_score, "adopt_level": it.adopt_level}
                      for it in items],
            "attachments": [{"id": a.id, "file_name": a.file_name, "size": a.size} for a in atts]}


# ============ 逐条子项：AI 评分 / 管理员终审 ============
@router.post("/bug-items/{iid}/ai-review")
def ai_review_item(iid: int, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    it = db.get(BugItem, iid)
    if not it:
        raise HTTPException(404, "勘误项不存在")
    if not is_dataset_member(db, it.dataset_id, user):
        raise HTTPException(403, "需为数据集成员")
    if not (it.reason or "").strip() or not (it.evidence or "").strip():
        raise HTTPException(400, "该勘误项缺少独立的说明或证据，补充完整后才能进行 AI 评分")
    prompt = (f"变量：{it.var_name}\n唯一 ID：{it.uid_value}\n"
              f"当前值：{it.current_value or ''}\n建议值：{it.suggested_value or ''}\n"
              f"修改说明：{it.reason}\n证据：{it.evidence}")
    score, reason = _run_ai_review(prompt)
    it.ai_score = score
    review = db.query(CorrectionReview).filter_by(
        target_type="bug_item", target_id=iid, reviewer_type="ai").first()
    if not review:
        review = CorrectionReview(target_type="bug_item", target_id=iid,
                                  reviewer_type="ai")
        db.add(review)
    review.acceptability_score = score
    review.comment = reason
    db.commit()
    return {"ai_score": it.ai_score, "reason": reason}


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
    if b:
        _sync_bug_status(db, b)
        b.reviewed_by = user.id
        b.reviewed_at = datetime.utcnow()
    write_audit(db, user.id, "bug.item.finalize", "bug_item", iid,
                {"adopt": body.adopt_level, "score": body.final_score})
    db.commit()
    return {"ok": True, "status": it.status}


# ============ 一键把已采纳勘误应用到上一版数据，生成新版本 ============
def _accepted_release_material(db: Session, dataset_id: int, unique_id_var: str,
                               base_version_id: int):
    """生成勘误发版所需的结构化修改项、文字说明和实际修改代码。"""
    from ..services.data_ops import apply_corrections_script
    items = db.query(BugItem).filter_by(dataset_id=dataset_id, status="accepted").filter(
        BugItem.applied_in_version.is_(None)).order_by(BugItem.bug_id, BugItem.seq).all()
    payload = [{"seq": it.id, "bug_id": it.bug_id, "item_seq": it.seq,
                "uid_value": it.uid_value, "var_name": it.var_name,
                "current_value": it.current_value, "suggested_value": it.suggested_value,
                "reason": it.reason, "evidence": it.evidence,
                "is_new_officer": bool(it.is_new_officer)} for it in items]
    auto_payload = [it for it in payload if not it["is_new_officer"]]
    manual_payload = [it for it in payload if it["is_new_officer"]]
    script = apply_corrections_script(payload, unique_id_var) if payload else ""
    lines = [f"本版本自动应用 {len(auto_payload)} 条已采纳勘误；"
             f"{len(manual_payload)} 条新增官员勘误保留为人工处理："]
    for it in payload:
        mode = "人工处理·新增官员" if it["is_new_officer"] else "自动应用"
        reason = f"；说明：{it['reason']}" if it.get("reason") else ""
        lines.append(
            f"- [{mode}] 勘误 #{it['bug_id']}·第 {it['item_seq']} 项："
            f"{unique_id_var}={it['uid_value']}，"
            f"{it['var_name']} 由「{it.get('current_value') or ''}」改为「{it.get('suggested_value') or ''}」{reason}")
    fingerprint = hashlib.sha256(json.dumps(
        {"dataset_id": dataset_id, "base_version_id": base_version_id,
         "unique_id_var": unique_id_var, "items": payload},
        ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return items, auto_payload, manual_payload, script, "\n".join(lines), fingerprint


@router.get("/datasets/{slug}/corrections-release-preview")
def corrections_release_preview(slug: str, base_version_id: int | None = None,
                                db: Session = Depends(get_db),
                                user: User = Depends(get_current_user)):
    """一键发版弹窗默认说明：同时给出人可读摘要与可复核修改代码。"""
    d = _ds(db, slug)
    if not is_dataset_admin(db, d.id, user):
        raise HTTPException(403, "仅数据集管理员可查看已采纳勘误的发版说明")
    cfg = db.get(DatasetDataConfig, d.id)
    uidv = cfg.unique_id_var if cfg else None
    if not uidv:
        raise HTTPException(400, "请先在「数据处理设置」指定唯一ID变量，再生成勘误发版说明")
    base = db.get(DataVersion, base_version_id) if base_version_id else _latest_raw_version(
        db, d.id)
    extra = db.get(VersionExtra, base.id) if base else None
    if (not base or base.dataset_id != d.id or not base.data_file_path or
            (extra.data_kind if extra else "raw") != "raw"):
        raise HTTPException(400, "请选择本数据集带数据文件的原始版本作为基准版本")
    _, auto, manual, script, changelog, preview_hash = _accepted_release_material(
        db, d.id, uidv, base.id)
    if not auto and not manual:
        raise HTTPException(400, "没有待应用的已采纳勘误项；请先完成勘误终审")
    return {"count": len(auto) + len(manual), "auto_count": len(auto),
            "manual_count": len(manual), "manual_items": manual,
            "base_version_id": base.id, "changelog_zh": changelog,
            "script": script, "preview_hash": preview_hash}


@router.post("/datasets/{slug}/apply-corrections")
def apply_corrections_endpoint(slug: str, base_version_id: int = Form(...),
                               new_version_id: str = Form(...), changelog_zh: str = Form(""),
                               preview_hash: str = Form(...),
                               db: Session = Depends(get_db),
                               user: User = Depends(get_current_user)):
    from ..services.data_ops import apply_corrections, CorrectionPreconditionError
    d = _ds(db, slug)
    if not is_dataset_admin(db, d.id, user):
        raise HTTPException(403, "仅数据集管理员可应用勘误发版")
    if get_settings(db, d.id).is_closed:
        raise HTTPException(400, "数据集已关闭")
    base = db.get(DataVersion, base_version_id)
    if not base or base.dataset_id != d.id or not base.data_file_path:
        raise HTTPException(404, "基准版本不存在或无数据文件")
    base_extra = db.get(VersionExtra, base.id)
    if (base_extra.data_kind if base_extra else "raw") != "raw":
        raise HTTPException(400, "勘误只能应用到原始数据版本")
    if not (new_version_id or "").strip():
        raise HTTPException(400, "请填写新版本号")
    if db.query(DataVersion).filter_by(dataset_id=d.id, version_id=new_version_id).first():
        raise HTTPException(400, f"版本 {new_version_id} 已存在")
    cfg = db.get(DatasetDataConfig, d.id)
    uidv = cfg.unique_id_var if cfg else None
    if not uidv:
        raise HTTPException(400, "请先在数据设置里指定唯一ID变量，才能按ID定位修改")
    items, payload, manual, script, default_changelog, current_hash = (
        _accepted_release_material(db, d.id, uidv, base.id))
    if current_hash != preview_hash:
        raise HTTPException(409, "已采纳勘误或基准版本在预览后发生变化，请重新打开并审阅代码")
    if not payload and manual:
        return {"generated": "script", "script": script, "manual_remaining": len(manual),
                "note": "待处理项全部是新增官员，系统不会自动追加不完整记录。请复制代码提示并人工补全后再发布原始版本。"}
    if not payload:
        raise HTTPException(400, "没有待应用的已采纳勘误项")
    try:
        new_bytes, source, generated_script, applied_ids = apply_corrections(
            base.data_file_path, payload, uidv, cfg.script_only if cfg else False)
    except CorrectionPreconditionError as exc:
        raise HTTPException(409, f"数据与勘误预期不一致，已中止整批应用：{exc}") from exc
    if new_bytes is None:
        write_audit(db, user.id, "dataset.apply_corrections.script", "dataset", d.id)
        return {"generated": "script", "script": script,
                "manual_remaining": len(manual),
                "note": "数据过大或设为仅脚本模式：请在本地运行脚本改好数据后，用「发布新版本·原始」上传。"}
    key = f"versions/{d.slug}/{new_version_id}/data.dta"
    from ..services.uploads import save_stored_file
    save_stored_file(key, io.BytesIO(new_bytes))
    db.query(DataVersion).filter_by(dataset_id=d.id, is_current=True).update(
        {"is_current": False, "valid_to": datetime.utcnow()})
    audit_changelog = ((changelog_zh or "").strip() or default_changelog)
    audit_changelog += "\n\n管理员审阅的实际修改代码：\n" + script.rstrip()
    v = DataVersion(dataset_id=d.id, version_id=new_version_id, based_on_version=base.version_id,
                    release_date=datetime.utcnow(), data_file_path=key,
                    changelog_zh=audit_changelog,
                    created_by=user.id, is_current=True, valid_from=datetime.utcnow())
    db.add(v); db.flush()
    db.add(VersionExtra(version_id=v.id, data_kind="raw", generated=source))
    d.current_version_id = v.id
    applied_set = set(applied_ids)
    for it in items:
        if it.id in applied_set:
            it.status = "fixed"; it.applied_in_version = v.id
    affected_bug_ids = {it.bug_id for it in items if it.id in applied_set}
    for bug_id in affected_bug_ids:
        bug = db.get(Bug, bug_id)
        if bug:
            _sync_bug_status(db, bug, v.id)
    write_audit(db, user.id, "dataset.apply_corrections.server", "dataset", d.id,
                {"version": new_version_id, "applied": len(applied_ids)})
    db.commit()
    return {"generated": "server", "id": v.id, "version_id": new_version_id,
            "applied": len(applied_ids), "manual_remaining": len(manual)}
