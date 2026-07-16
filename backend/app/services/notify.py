"""邮件通知核心服务：偏好、收件人筛选、投递去重/重试/发送、退订令牌。

设计要点（对齐需求文档）：
- 权限优先：收件人与可发送内容全部由后端按当前权限计算，AI 只做文本摘要。
- 去重幂等：EmailDelivery.dedupe_key 唯一，重复触发不重发。
- 频率：immediate 立即发；daily/weekly 落 pending，由 flush_due_deliveries 到点汇总发送。
- 发送经 core.email_service 抽象层（默认 mock，不强绑第三方）。
"""
from __future__ import annotations
import hashlib
import hmac
import base64
import json
import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from ..core.config import settings
from ..core.email_service import send_email
from ..models.user import User
from ..models.dataset import Dataset, DatasetMember
from ..models.access import DatasetGrant
from ..models.version import DataVersion
from ..models.notify import (NotificationPreference, NotificationEvent, EmailDelivery,
                             DatasetFollow)

log = logging.getLogger("notify")

# 下载类授权码：拥有其一即视为“可下载”
_DOWNLOAD_PERMS = {"download.current", "download.masked", "download.history"}


# ---------------- 偏好 ----------------
def get_pref(db: Session, uid: int) -> NotificationPreference:
    p = db.get(NotificationPreference, uid)
    if not p:
        p = NotificationPreference(user_id=uid)
        db.add(p); db.flush()
        # 迁移旧的 UserProfile.email_opt_in 作为总开关初值
        from ..models.extras import UserProfile
        up = db.get(UserProfile, uid)
        if up is not None and up.email_opt_in is False:
            p.email_enabled = False
    return p


def pref_dict(p: NotificationPreference) -> dict:
    return {
        "email_enabled": bool(p.email_enabled),
        "version_email_enabled": bool(p.version_email_enabled),
        "version_email_frequency": p.version_email_frequency or "immediate",
        "code_email_enabled": bool(p.code_email_enabled),
        "code_email_frequency": p.code_email_frequency or "immediate",
        "message_email_enabled": bool(p.message_email_enabled),
        "weekly_digest_enabled": bool(p.weekly_digest_enabled),
        "weekly_digest_scope": p.weekly_digest_scope or ["public", "groups", "datasets"],
        "email_language": p.email_language or "zh-CN",
        "timezone": p.timezone or "Asia/Shanghai",
    }


# ---------------- 退订令牌（签名 + 可过期，不暴露 user_id/邮箱明文）----------------
def make_unsub_token(uid: int, kind: str = "all", days: int = 30) -> str:
    exp = int((datetime.utcnow() + timedelta(days=days)).timestamp())
    payload = json.dumps({"u": uid, "k": kind, "e": exp}, separators=(",", ":"))
    raw = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    sig = hmac.new(settings.JWT_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()[:24]
    return f"{raw}.{sig}"


def verify_unsub_token(token: str) -> dict | None:
    try:
        raw, sig = token.split(".", 1)
    except ValueError:
        return None
    good = hmac.new(settings.JWT_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()[:24]
    if not hmac.compare_digest(sig, good):
        return None
    pad = "=" * (-len(raw) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(raw + pad).decode())
    except Exception:
        return None
    if int(data.get("e", 0)) < int(datetime.utcnow().timestamp()):
        return None
    return data


# ---------------- 时间：下一次 8:00 / 周一 8:00（本地时区，落库为 UTC）----------------
def _next_daily_utc(now: datetime) -> datetime:
    # Asia/Shanghai 8:00 == 00:00 UTC
    t = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if now >= t:
        t += timedelta(days=1)
    return t


def _next_weekly_utc(now: datetime) -> datetime:
    t = now.replace(hour=0, minute=0, second=0, microsecond=0)
    # 周一：Monday.weekday()==0
    days_ahead = (7 - t.weekday()) % 7
    cand = t + timedelta(days=days_ahead)
    if cand <= now:
        cand += timedelta(days=7)
    return cand


def _scheduled_for(freq: str, now: datetime) -> datetime:
    if freq == "daily":
        return _next_daily_utc(now)
    if freq == "weekly":
        return _next_weekly_utc(now)
    return now  # immediate


# ---------------- 收件人筛选（数据版本）----------------
def recipients_for_version(db: Session, d: Dataset, v: DataVersion) -> list[tuple[User, bool]]:
    """返回 [(user, can_download)]，已去重且排除不该收信的人。"""
    from ..api.datasets import check_download, get_settings  # 延迟导入避免环路

    ids: set[int] = set()
    # 数据集成员（含管理员）
    for m in db.query(DatasetMember).filter_by(dataset_id=d.id).all():
        ids.add(m.user_id)
    # 有效的单独下载授权
    for g in db.query(DatasetGrant).filter_by(dataset_id=d.id, revoked=False).all():
        if g.perm in _DOWNLOAD_PERMS and g.is_active():
            ids.add(g.user_id)
    # 关注该数据集并允许接收版本通知的用户
    for f in db.query(DatasetFollow).filter_by(dataset_id=d.id).all():
        if f.version_notification_enabled:
            ids.add(f.user_id)

    out: list[tuple[User, bool]] = []
    for uid in ids:
        u = db.get(User, uid)
        if not u or u.status == "left":
            continue
        if not (u.email or "").strip():
            continue  # 邮箱缺失/未验证 → 跳过
        pref = get_pref(db, uid)
        if not (pref.email_enabled and pref.version_email_enabled):
            continue
        try:
            can_dl, _ = check_download(db, d, v, u)
        except Exception:
            can_dl = False
        out.append((u, bool(can_dl)))
    return out


# ---------------- 渲染 ----------------
def _unsub_line(uid: int, lang: str) -> str:
    url = f"{settings.SITE_URL}/api/unsubscribe?token={make_unsub_token(uid)}"
    if lang == "en":
        return f"Manage or unsubscribe: {url}"
    return f"通知设置 / 退订：{url}"


def render_version_email(d: Dataset, v: DataVersion, publisher, u: User,
                         can_download: bool, lang: str) -> tuple[str, str]:
    site = settings.SITE_URL
    link = f"{site}/#/datasets/{d.slug}?tab=versions"
    date = (v.release_date or datetime.utcnow()).strftime("%Y-%m-%d")
    if lang == "en":
        subject = f"[{d.name_en or d.name_zh}] published {v.version_id}"
        perm = ("You can download this version." if can_download
                else "You can view the release notes, but have no download permission yet.")
        body = "\n".join([
            f"Hi {u.display_name or u.username},", "",
            f"{d.name_en or d.name_zh} released {v.version_id} on {date}.",
            f"Publisher: {publisher.display_name if publisher else '-'}",
            f"Current recommended version: {'Yes' if v.is_current else 'No'}", "",
            "Change summary:", (v.changelog_en or v.changelog_zh or "-"), "",
            f"Your permission: {perm}",
            "Older versions remain available for reference.", "",
            f"Open dataset: {link}", _unsub_line(u.id, lang)])
        return subject, body
    subject = f"【{d.name_zh}】已发布 {v.version_id}"
    perm = ("你可以下载该版本。" if can_download
            else "你可以查看版本说明，但当前没有下载权限。")
    body = "\n".join([
        f"{u.display_name or u.username} 你好：", "",
        f"「{d.name_zh}」已于 {date} 发布 {v.version_id}。",
        f"发布者：{publisher.display_name if publisher else '-'}",
        f"是否当前推荐版本：{'是' if v.is_current else '否'}", "",
        "版本更新摘要：", (v.changelog_zh or v.changelog_en or "-"), "",
        f"你当前的权限：{perm}",
        "旧版本仍可查看/使用。", "",
        f"进入数据集：{link}", _unsub_line(u.id, lang)])
    return subject, body


# ---------------- 投递 ----------------
def _create_delivery(db: Session, *, event: NotificationEvent, u: User, template_key: str,
                     subject: str, body: str, dedupe_key: str, scheduled_at: datetime) -> EmailDelivery | None:
    exists = db.query(EmailDelivery).filter_by(dedupe_key=dedupe_key).first()
    if exists:
        return None  # 去重：已存在则不重复创建
    dl = EmailDelivery(event_id=event.id, recipient_user_id=u.id, recipient_email=u.email,
                       template_key=template_key, status="pending", scheduled_at=scheduled_at,
                       dedupe_key=dedupe_key, subject=subject, body=body)
    db.add(dl); db.flush()
    if scheduled_at <= datetime.utcnow():
        _send_delivery(db, dl)   # immediate
    return dl


def _send_delivery(db: Session, dl: EmailDelivery) -> None:
    dl.status = "sending"
    ev = send_email(db, user_id=dl.recipient_user_id, to_email=dl.recipient_email,
                    subject=dl.subject or "", body=dl.body or "",
                    kind=dl.template_key or "notify",
                    meta={"delivery_id": dl.id, "dedupe": dl.dedupe_key})
    if ev.status in ("sent", "mock"):
        dl.status = "sent"; dl.sent_at = datetime.utcnow(); dl.error_message = None
    elif ev.status == "skipped":
        dl.status = "skipped"; dl.error_message = ev.error
    else:
        dl.status = "failed"; dl.error_message = ev.error
        dl.retry_count = (dl.retry_count or 0) + 1
    db.flush()


def notify_version_published(db: Session, d: Dataset, v: DataVersion, publisher) -> NotificationEvent:
    """发布版本事务成功后调用：创建事件并按订阅频率生成投递。"""
    event = NotificationEvent(
        event_type="dataset_version_published", object_type="dataset_version",
        object_id=f"{d.id}:{v.id}", created_by=getattr(publisher, "id", None),
        payload={"dataset": d.name_zh, "version": v.version_id})
    db.add(event); db.flush()
    now = datetime.utcnow()
    for u, can_dl in recipients_for_version(db, d, v):
        pref = get_pref(db, u.id)
        lang = pref.email_language or "zh-CN"
        subject, body = render_version_email(d, v, publisher, u, can_dl,
                                              "en" if lang == "en" else "zh")
        sched = _scheduled_for(pref.version_email_frequency or "immediate", now)
        _create_delivery(db, event=event, u=u, template_key="dataset_version",
                         subject=subject, body=body,
                         dedupe_key=f"ver:{v.id}:u{u.id}", scheduled_at=sched)
    return event


def notify_code_published(db: Session, script, code_version, publisher) -> NotificationEvent | None:
    """处理代码新版本发布：通知该数据集成员中开启了代码更新通知的用户。"""
    d = db.get(Dataset, script.dataset_id)
    if not d:
        return None
    event = NotificationEvent(
        event_type="dataset_code_published", object_type="code_version",
        object_id=f"{script.id}:{getattr(code_version,'id',0)}",
        created_by=getattr(publisher, "id", None),
        payload={"dataset": d.name_zh, "script": getattr(script, "title", "") or script.filename})
    db.add(event); db.flush()
    now = datetime.utcnow()
    label = getattr(code_version, "version_label", "") or ""
    site = settings.SITE_URL
    link = f"{site}/#/datasets/{d.slug}?tab=code"
    for m in db.query(DatasetMember).filter_by(dataset_id=d.id).all():
        if m.user_id == getattr(publisher, "id", None):
            continue
        u = db.get(User, m.user_id)
        if not u or u.status == "left" or not (u.email or "").strip():
            continue
        pref = get_pref(db, u.id)
        if not (pref.email_enabled and pref.code_email_enabled):
            continue
        lang = pref.email_language or "zh-CN"
        if lang == "en":
            subject = f"[{d.name_en or d.name_zh}] processing code updated {label}".strip()
            body = (f"Hi {u.display_name or u.username},\n\n"
                    f"Processing code in {d.name_en or d.name_zh} has a new version {label}.\n\n"
                    f"Open: {link}\n{_unsub_line(u.id, 'en')}")
        else:
            subject = f"【{d.name_zh}】处理代码有新版本 {label}".strip()
            body = (f"{u.display_name or u.username} 你好：\n\n"
                    f"「{d.name_zh}」的处理代码发布了新版本 {label}。\n\n"
                    f"查看：{link}\n{_unsub_line(u.id, 'zh')}")
        sched = _scheduled_for(pref.code_email_frequency or "immediate", now)
        _create_delivery(db, event=event, u=u, template_key="dataset_code",
                         subject=subject, body=body,
                         dedupe_key=f"code:{event.object_id}:u{u.id}", scheduled_at=sched)
    return event


# ---------------- 到点汇总发送（daily/weekly pending）----------------
def flush_due_deliveries(db: Session, now: datetime | None = None) -> dict:
    """把到期的 pending 投递按用户合并成一封“更新汇总”发送。"""
    now = now or datetime.utcnow()
    due = db.query(EmailDelivery).filter(
        EmailDelivery.status == "pending",
        EmailDelivery.scheduled_at <= now).all()
    by_user: dict[int, list[EmailDelivery]] = {}
    for dl in due:
        by_user.setdefault(dl.recipient_user_id, []).append(dl)
    sent = 0
    for uid, lst in by_user.items():
        u = db.get(User, uid)
        if not u or not (u.email or "").strip():
            for dl in lst:
                dl.status = "skipped"; dl.error_message = "无收件邮箱"
            continue
        if len(lst) == 1:
            _send_delivery(db, lst[0]); sent += 1
            continue
        # 合并多条为一封汇总
        parts = [f"{u.display_name or u.username} 你好：", "",
                 f"以下是你的数据更新汇总（共 {len(lst)} 条）：", ""]
        for dl in lst:
            parts.append("— " + (dl.subject or ""))
        parts += ["", f"查看详情：{settings.SITE_URL}", _unsub_line(uid, "zh")]
        combined = "\n".join(parts)
        ev = send_email(db, user_id=uid, to_email=u.email,
                        subject=f"【科研数据共享平台】你有 {len(lst)} 条数据更新",
                        body=combined, kind="update_digest",
                        meta={"delivery_ids": [dl.id for dl in lst]})
        ok = ev.status in ("sent", "mock")
        for dl in lst:
            dl.status = "sent" if ok else "failed"
            dl.sent_at = datetime.utcnow() if ok else None
            if not ok:
                dl.error_message = ev.error; dl.retry_count = (dl.retry_count or 0) + 1
        sent += 1
    db.commit()
    return {"due": len(due), "emails_sent": sent}


def retry_delivery(db: Session, delivery_id: int) -> EmailDelivery | None:
    dl = db.get(EmailDelivery, delivery_id)
    if not dl or dl.status not in ("failed", "pending"):
        return dl
    _send_delivery(db, dl)
    db.commit()
    return dl
