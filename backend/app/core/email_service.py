"""邮件服务抽象层。

设计目标（按需求）：
- 不强绑任何第三方邮件服务；部署环境未来可能是高校内部服务器。
- 现阶段默认 mock：只记录 EmailEvent、打日志，不真正发信。
- 未来把 EMAIL_BACKEND 设为 "smtp" 并在环境变量填 SMTP_* 即可真实发送，
  代码无需改动。也可在此文件新增 backend（如企业邮/内部网关）而不影响调用方。

调用方只用 send_email(...) / notify(...)，与后端如何投递解耦。
"""
from __future__ import annotations
import logging
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr
from datetime import datetime

from sqlalchemy.orm import Session
from .config import settings
from ..models.extras import EmailEvent
from ..models.user import User

log = logging.getLogger("email_service")


def _deliver_smtp(to_email: str, subject: str, body: str) -> None:
    """真实 SMTP 投递。仅当 EMAIL_BACKEND=smtp 且配置齐全时调用。

    三种连接方式（按端口/开关自动选择）：
    - 隐式 SSL（465）：SMTP_SSL 直连，或 SMTP_PORT==465 时自动启用。
    - STARTTLS（587）：先明文连接再升级 TLS（SMTP_TLS=True）。
    - 明文：不加密（仅内网自建时用）。
    """
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr((str(Header(settings.EMAIL_FROM_NAME, "utf-8")), settings.EMAIL_FROM))
    msg["To"] = to_email

    use_ssl = getattr(settings, "SMTP_SSL", False) or settings.SMTP_PORT == 465
    if use_ssl:
        import ssl
        server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT,
                                  timeout=20, context=ssl.create_default_context())
    else:
        server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20)
        if settings.SMTP_TLS:
            server.starttls()
    try:
        if settings.SMTP_USER:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(settings.EMAIL_FROM, [to_email], msg.as_string())
    finally:
        try: server.quit()
        except Exception: pass


def send_email(db: Session, *, user_id: int | None, to_email: str | None,
               subject: str, body: str, kind: str = "system",
               meta: dict | None = None) -> EmailEvent:
    """统一发信入口：先落 EmailEvent，再按后端投递。

    - 无收件地址 → status=skipped（不报错，方便"没有邮箱就跳过"）。
    - mock/none 后端 → 记录但不真正发信（status=mock/skipped）。
    - smtp 后端 → 真发；失败落 status=failed 但不抛异常打断业务。
    """
    ev = EmailEvent(user_id=user_id, to_email=to_email or "", subject=subject,
                    body=body, kind=kind, meta=meta or {}, created_at=datetime.utcnow())
    backend = (settings.EMAIL_BACKEND or "mock").lower()

    if not to_email:
        ev.status = "skipped"; ev.error = "无收件邮箱"
        db.add(ev); db.commit(); db.refresh(ev)
        return ev

    if backend == "smtp" and settings.SMTP_HOST:
        try:
            _deliver_smtp(to_email, subject, body)
            ev.status = "sent"
        except Exception as e:   # 投递失败不打断业务
            ev.status = "failed"; ev.error = str(e)[:500]
            log.warning("SMTP 发送失败 → %s: %s", to_email, e)
    elif backend == "none":
        ev.status = "skipped"
    else:  # mock（默认）
        ev.status = "mock"
        log.info("[MOCK EMAIL] → %s | %s\n%s", to_email, subject, body)

    db.add(ev); db.commit(); db.refresh(ev)
    return ev


def notify_user(db: Session, user_id: int, subject: str, body: str,
                kind: str = "system", meta: dict | None = None) -> EmailEvent | None:
    """给某个用户发信（自动取其邮箱）。"""
    u = db.get(User, user_id)
    if not u:
        return None
    return send_email(db, user_id=user_id, to_email=u.email, subject=subject,
                      body=body, kind=kind, meta=meta)
