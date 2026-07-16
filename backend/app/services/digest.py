"""每日消息摘要邮件：默认每天 8:00 与 18:00 巡检。

规则（按需求）：平台自动检索每个用户「有无新消息」，有则发邮件、没有则不发。
去重：以当前消息集合的内容哈希与上一封 digest 邮件记录比对，只有在集合发生变化
（出现新消息）时才发信，避免同样内容反复打扰。

邮件通过 core.email_service 抽象层投递（默认 mock，不强绑第三方）。
"""
from __future__ import annotations
import hashlib
import logging

from ..core.db import SessionLocal
from ..core.config import settings
from ..core.email_service import send_email
from ..models.user import User
from ..models.extras import EmailEvent
from ..api.notifications import build_notifications, CATEGORY_META

log = logging.getLogger("digest")


def _content_hash(groups: list[dict]) -> str:
    parts = []
    for g in groups:
        for it in g["items"]:
            parts.append(f'{it.get("type")}|{it.get("sort")}|{it.get("title")}')
    return hashlib.sha256("\n".join(sorted(parts)).encode("utf-8")).hexdigest()


def _render_body(user: User, groups: list[dict]) -> str:
    lines = [f"你好 {user.display_name or user.username}：", "",
             "以下是你在科研数据共享平台的新消息汇总：", ""]
    for g in groups:
        lines.append(f"【{g['name']}】（{g['count']}）")
        for it in g["items"][:10]:
            lines.append(f"  · {it['title']}：{it.get('subtitle', '')}")
        lines.append("")
    lines.append(f"查看详情：{settings.SITE_URL}")
    lines.append("")
    lines.append("（本邮件由平台自动发送；如需关闭每日提醒，请联系管理员。）")
    return "\n".join(lines)


def run_digest_once() -> dict:
    """执行一次巡检：给有新消息的用户发摘要邮件。返回统计。"""
    db = SessionLocal()
    sent = 0; skipped = 0; scanned = 0
    try:
        users = db.query(User).filter(User.status != "left").all()
        from ..models.extras import UserProfile
        for u in users:
            scanned += 1
            if not u.email:
                skipped += 1
                continue
            # 尊重通知偏好：总开关 + “消息通知”细分开关（被回复/被@/权限申请/权限通过等）
            from .notify import get_pref
            pref = get_pref(db, u.id)
            if not (pref.email_enabled and pref.message_email_enabled):
                skipped += 1
                continue
            data = build_notifications(db, u)
            groups = data.get("groups") or []
            if not groups:
                skipped += 1
                continue
            h = _content_hash(groups)
            last = db.query(EmailEvent).filter_by(user_id=u.id, kind="digest").order_by(
                EmailEvent.id.desc()).first()
            if last and (last.meta or {}).get("hash") == h:
                skipped += 1     # 内容没变 = 没有新消息
                continue
            subject = f"【科研数据共享平台】你有 {sum(g['count'] for g in groups)} 条新消息"
            send_email(db, user_id=u.id, to_email=u.email, kind="digest",
                       subject=subject, body=_render_body(u, groups),
                       meta={"hash": h})
            sent += 1
        log.info("digest 巡检完成：扫描 %d，发送 %d，跳过 %d", scanned, sent, skipped)
    finally:
        db.close()
    return {"scanned": scanned, "sent": sent, "skipped": skipped}
