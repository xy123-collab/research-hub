"""通知偏好 / 数据集关注 / 退订 / 管理后台通知状态。"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from ..core.db import get_db
from ..core.permissions import get_current_user, is_super_admin
from ..models.user import User
from ..models.dataset import Dataset
from ..models.notify import (NotificationPreference, NotificationEvent, EmailDelivery,
                             DatasetFollow, NOTIFY_FREQUENCIES, DIGEST_SCOPES)
from ..services.notify import (get_pref, pref_dict, verify_unsub_token, retry_delivery)

router = APIRouter(tags=["notify"])


class PrefIn(BaseModel):
    email_enabled: bool | None = None
    version_email_enabled: bool | None = None
    version_email_frequency: str | None = None
    code_email_enabled: bool | None = None
    code_email_frequency: str | None = None
    message_email_enabled: bool | None = None
    weekly_digest_enabled: bool | None = None
    weekly_digest_scope: list[str] | None = None
    email_language: str | None = None
    timezone: str | None = None


@router.get("/notification-preferences")
def get_prefs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = get_pref(db, user.id)
    db.commit()
    return {**pref_dict(p), "email": user.email or "",
            "frequencies": NOTIFY_FREQUENCIES, "digest_scopes": DIGEST_SCOPES}


@router.put("/notification-preferences")
def put_prefs(body: PrefIn, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    p = get_pref(db, user.id)
    data = body.model_dump(exclude_none=True)
    for f in ("version_email_frequency", "code_email_frequency"):
        if f in data and data[f] not in NOTIFY_FREQUENCIES:
            raise HTTPException(400, "频率取值不合法")
    if "weekly_digest_scope" in data:
        data["weekly_digest_scope"] = [s for s in data["weekly_digest_scope"]
                                       if s in DIGEST_SCOPES] or ["public"]
    if data.get("email_language") not in (None, "zh-CN", "en"):
        raise HTTPException(400, "语言取值不合法")
    for k, v in data.items():
        setattr(p, k, v)
    p.updated_at = datetime.utcnow()
    # 兼容旧的 UserProfile.email_opt_in（总开关同步）
    if "email_enabled" in data:
        from ..models.extras import UserProfile
        up = db.get(UserProfile, user.id) or UserProfile(user_id=user.id)
        up.email_opt_in = bool(data["email_enabled"]); db.add(up)
    db.commit()
    return {"ok": True, **pref_dict(p)}


# -------- 数据集关注（关注即可接收版本通知）--------
def _get_ds(db, slug):
    d = db.query(Dataset).filter_by(slug=slug).first()
    if not d:
        raise HTTPException(404, "数据集不存在")
    return d


@router.get("/datasets/{slug}/follow")
def follow_state(slug: str, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    d = _get_ds(db, slug)
    f = db.query(DatasetFollow).filter_by(dataset_id=d.id, user_id=user.id).first()
    return {"following": bool(f),
            "version_notification_enabled": bool(f.version_notification_enabled) if f else True}


@router.post("/datasets/{slug}/follow")
def follow_dataset(slug: str, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    d = _get_ds(db, slug)
    f = db.query(DatasetFollow).filter_by(dataset_id=d.id, user_id=user.id).first()
    if not f:
        f = DatasetFollow(dataset_id=d.id, user_id=user.id,
                          version_notification_enabled=True)
        db.add(f)
    db.commit()
    return {"following": True}


@router.delete("/datasets/{slug}/follow")
def unfollow_dataset(slug: str, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    d = _get_ds(db, slug)
    db.query(DatasetFollow).filter_by(dataset_id=d.id, user_id=user.id).delete()
    db.commit()
    return {"following": False}


# -------- 退订（邮件里的签名链接，无需登录）--------
@router.get("/unsubscribe", response_class=HTMLResponse)
def unsubscribe(token: str = "", db: Session = Depends(get_db)):
    data = verify_unsub_token(token)
    if not data:
        return HTMLResponse("<h3>链接无效或已过期</h3><p>请登录平台在「通知设置」中调整。</p>",
                            status_code=400)
    uid = int(data["u"])
    p = get_pref(db, uid)
    p.email_enabled = False; p.updated_at = datetime.utcnow()
    from ..models.extras import UserProfile
    up = db.get(UserProfile, uid) or UserProfile(user_id=uid)
    up.email_opt_in = False; db.add(up)
    db.commit()
    return HTMLResponse(
        "<div style='font-family:sans-serif;max-width:520px;margin:60px auto;text-align:center'>"
        "<h2>已退订</h2><p>你已关闭本平台的邮件提醒。找回密码等必要邮件不受影响。</p>"
        "<p>如需重新开启，请登录平台在「通知设置」里切换。</p></div>")


# -------- 管理后台：通知任务与发送状态 --------
@router.get("/admin/notifications")
def admin_notifications(limit: int = 50, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    if not is_super_admin(user):
        raise HTTPException(403, "仅平台总管理员可查看")
    events = db.query(NotificationEvent).order_by(
        NotificationEvent.id.desc()).limit(min(limit, 200)).all()
    out = []
    for ev in events:
        dls = db.query(EmailDelivery).filter_by(event_id=ev.id).all()
        stat = {"total": len(dls), "sent": 0, "failed": 0, "pending": 0, "skipped": 0}
        for dl in dls:
            stat[dl.status] = stat.get(dl.status, 0) + 1
        out.append({"id": ev.id, "event_type": ev.event_type,
                    "object_type": ev.object_type, "object_id": ev.object_id,
                    "created_at": str(ev.created_at), "payload": ev.payload,
                    "stats": stat})
    return {"events": out}


@router.post("/admin/notifications/deliveries/{did}/retry")
def admin_retry(did: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    if not is_super_admin(user):
        raise HTTPException(403, "仅平台总管理员可重试")
    dl = retry_delivery(db, did)
    if not dl:
        raise HTTPException(404, "投递记录不存在")
    return {"id": dl.id, "status": dl.status, "error": dl.error_message}


@router.get("/admin/notifications/{eid}/deliveries")
def admin_event_deliveries(eid: int, user: User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    if not is_super_admin(user):
        raise HTTPException(403, "仅平台总管理员可查看")
    dls = db.query(EmailDelivery).filter_by(event_id=eid).order_by(EmailDelivery.id).all()
    return [{"id": dl.id, "recipient_user_id": dl.recipient_user_id,
             "recipient_email": dl.recipient_email, "status": dl.status,
             "retry_count": dl.retry_count, "error": dl.error_message,
             "sent_at": str(dl.sent_at) if dl.sent_at else None,
             "scheduled_at": str(dl.scheduled_at) if dl.scheduled_at else None}
            for dl in dls]
