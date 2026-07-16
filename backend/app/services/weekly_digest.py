"""每周成员帖子周报：每周一 8:00 汇总上一自然周（周一~周日）的帖子。

严格按需求文档：先由后端按收件人权限筛出可见帖子，再交 AI 摘要（失败降级规则式）。
禁止把全站帖子交给 AI 再让它按权限过滤。
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta

from ..core.db import SessionLocal
from ..core.config import settings
from ..core.ai_client import ai_client
from ..core.email_service import send_email
from ..core.scopes import get_scopes, scope_visible
from ..models.user import User
from ..models.community import Post, PostComment, PostReaction
from ..models.notify import NotificationPreference, NotificationEvent, EmailDelivery
from .notify import get_pref, make_unsub_token

log = logging.getLogger("weekly_digest")


def _last_week_range(now: datetime) -> tuple[datetime, datetime, str]:
    """返回上一自然周的 [周一0点, 本周一0点) 及周期标识（UTC 存储，展示用北京时间）。"""
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    this_monday = today - timedelta(days=today.weekday())
    last_monday = this_monday - timedelta(days=7)
    period = last_monday.strftime("%Y%m%d")
    return last_monday, this_monday, period


def _post_category(db, p: Post) -> str:
    rows = get_scopes(db, "post", p.id)
    scopes = {r.scope for r in rows} if rows else {"public"}
    if "public" in scopes:
        return "public"
    if "group" in scopes:
        return "groups"
    if "dataset" in scopes:
        return "datasets"
    return "public"


def _visible_posts_for(db, u: User, posts: list[Post], scope_sel: list[str]) -> list[dict]:
    out = []
    for p in posts:
        if p.author_id == u.id:
            pass  # 作者本人也纳入其可见范围
        if not scope_visible(db, "post", p.id, p.author_id, u):
            continue
        cat = _post_category(db, p)
        if cat not in scope_sel:
            continue
        n_c = db.query(PostComment).filter_by(post_id=p.id).count()
        n_l = db.query(PostReaction).filter_by(post_id=p.id, type="like").count()
        author = db.get(User, p.author_id)
        out.append({"id": p.id, "title": p.title or (p.content_zh or "")[:24],
                    "author": author.display_name if author else "",
                    "summary": (p.content_zh or "")[:120],
                    "comments": n_c, "likes": n_l,
                    "type": p.post_type or "discussion"})
    return out


def _rule_based_body(u: User, items: list[dict], period_label: str, lang: str) -> str:
    items_sorted = sorted(items, key=lambda x: (x["comments"] + x["likes"]), reverse=True)
    site = settings.SITE_URL
    link = f"{site}/#/feed"
    lines = [f"{u.display_name or u.username} 你好：", "",
             f"统计周期：{period_label}", f"本周你可见的新帖子共 {len(items)} 条。", "",
             "值得关注："]
    for it in items_sorted[:6]:
        lines.append(f"• 《{it['title']}》— {it['author']}，{it['comments']} 评论 / {it['likes']} 赞")
    lines += ["", f"进入研究广场：{link}",
              f"周报设置 / 退订：{site}/api/unsubscribe?token={make_unsub_token(u.id)}"]
    return "\n".join(lines)


def _ai_body(u: User, items: list[dict], period_label: str) -> str | None:
    if not ai_client.enabled or not items:
        return None
    # 只送标题/作者/互动数/摘要等元数据，不送敏感附件
    payload_lines = [f"- 《{it['title']}》 作者:{it['author']} 评论:{it['comments']} 赞:{it['likes']} 摘要:{it['summary']}"
                     for it in items[:40]]
    sys = ("你是科研数据平台的周报助手。根据下面已按权限筛选好的帖子列表，"
           "生成简洁中文周报正文：先给出本周主要主题3-5个各一句话，再列出最受关注的帖子，"
           "最后列出未解决的问题或待跟进事项。不要编造未提供的信息。")
    try:
        text = ai_client.complete("帖子列表：\n" + "\n".join(payload_lines), sys)
        if not text or text.startswith("[AI 未启用]"):
            return None
        site = settings.SITE_URL
        return (f"{u.display_name or u.username} 你好：\n\n统计周期：{period_label}\n"
                f"本周你可见的新帖子共 {len(items)} 条。\n\n{text}\n\n"
                f"进入研究广场：{site}/#/feed\n"
                f"周报设置 / 退订：{site}/api/unsubscribe?token={make_unsub_token(u.id)}")
    except Exception as e:
        log.warning("周报 AI 摘要失败，降级规则式：%s", e)
        return None


def run_weekly_digest_once(now: datetime | None = None) -> dict:
    now = now or datetime.utcnow()
    db = SessionLocal()
    sent = 0; skipped = 0
    try:
        start, end, period = _last_week_range(now)
        period_label = f"{(start + timedelta(hours=8)).strftime('%m月%d日')}—" \
                       f"{(end + timedelta(hours=8) - timedelta(days=1)).strftime('%m月%d日')}"
        # 本周期内、未被删除的帖子（删除即从库中移除，无需额外过滤）
        posts = db.query(Post).filter(Post.created_at >= start,
                                      Post.created_at < end).all()
        event = NotificationEvent(event_type="weekly_digest", object_type="digest_period",
                                  object_id=period, payload={"period": period_label,
                                                             "n_posts": len(posts)})
        db.add(event); db.flush()
        users = db.query(User).filter(User.status != "left").all()
        for u in users:
            if not (u.email or "").strip():
                skipped += 1; continue
            pref = get_pref(db, u.id)
            if not (pref.email_enabled and pref.weekly_digest_enabled):
                skipped += 1; continue
            scope_sel = pref.weekly_digest_scope or ["public", "groups", "datasets"]
            items = _visible_posts_for(db, u, posts, scope_sel)
            if not items:
                skipped += 1; continue
            dedupe = f"digest:{period}:u{u.id}"
            if db.query(EmailDelivery).filter_by(dedupe_key=dedupe).first():
                skipped += 1; continue
            lang = pref.email_language or "zh-CN"
            body = _ai_body(u, items, period_label) or \
                _rule_based_body(u, items, period_label, lang)
            subject = f"【科研数据共享平台】每周研究动态｜{period_label}"
            dl = EmailDelivery(event_id=event.id, recipient_user_id=u.id,
                               recipient_email=u.email, template_key="weekly_digest",
                               status="pending", scheduled_at=now, dedupe_key=dedupe,
                               subject=subject, body=body)
            db.add(dl); db.flush()
            ev = send_email(db, user_id=u.id, to_email=u.email, subject=subject,
                            body=body, kind="weekly_digest", meta={"period": period})
            if ev.status in ("sent", "mock"):
                dl.status = "sent"; dl.sent_at = datetime.utcnow(); sent += 1
            else:
                dl.status = "failed"; dl.error_message = ev.error
                dl.retry_count = 1
        db.commit()
        log.info("周报完成：发送 %d，跳过 %d", sent, skipped)
    finally:
        db.close()
    return {"sent": sent, "skipped": skipped}
