"""注册准入：邀请码 + 注册邮箱验证。

两个开关都存在已有的 platform_settings 键值表里，由平台总管理员在管理后台改：
- reg.invite_only  : "true" / "false"。打开后注册必须填有效邀请码。
- reg.email_verify : "auto" / "on" / "off"。
    auto（默认）= 邮件后端真能发信（EMAIL_BACKEND=smtp 且配了 SMTP_HOST）时才要求验证。
    这样在 Render 免费档（出站 SMTP 端口被封、EMAIL_BACKEND=mock）不会把所有人挡在门外，
    迁到阿里云配好 465 端口后自动生效，不用改代码。
    on / off = 管理员强制开启或关闭。
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.email_service import send_email
from ..models.authx import EmailVerification, InviteCode, InviteCodeUse
from ..models.extras import PlatformSetting

K_INVITE_ONLY = "reg.invite_only"
K_EMAIL_VERIFY = "reg.email_verify"

CODE_TTL_MINUTES = 10          # 邮箱验证码有效期
CODE_MAX_ATTEMPTS = 5          # 同一条验证码最多试几次
# 去掉容易看错的 0/O/1/I/L，管理员要把码抄给别人
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


# ---------- 开关读写 ----------
def _get(db: Session, key: str, default: str) -> str:
    row = db.get(PlatformSetting, key)
    return row.value if row and row.value is not None else default


def _set(db: Session, key: str, value: str) -> None:
    row = db.get(PlatformSetting, key)
    if row:
        row.value = value
    else:
        db.add(PlatformSetting(key=key, value=value))


def email_backend_can_send() -> bool:
    return (settings.EMAIL_BACKEND or "mock").lower() == "smtp" and bool(settings.SMTP_HOST)


def invite_only(db: Session) -> bool:
    return _get(db, K_INVITE_ONLY, "false").lower() == "true"


def email_verify_mode(db: Session) -> str:
    mode = (_get(db, K_EMAIL_VERIFY, "auto") or "auto").lower()
    return mode if mode in ("auto", "on", "off") else "auto"


def email_verify_required(db: Session) -> bool:
    mode = email_verify_mode(db)
    if mode == "off":
        return False
    # 邮件服务未正式接通时，哪怕数据库里残留了 on，也不能把所有新用户挡住。
    # 配好 SMTP 后，auto/on 才会实际要求验证码。
    return email_backend_can_send()


def registration_policy(db: Session) -> dict:
    """给登录页用的公开策略（不含任何敏感信息）。"""
    return {"invite_required": invite_only(db),
            "email_verify_required": email_verify_required(db),
            "min_password_len": settings.MIN_PASSWORD_LEN,
            "code_ttl_minutes": CODE_TTL_MINUTES}


def set_policy(db: Session, *, invite_only_flag: bool | None = None,
               email_verify: str | None = None) -> None:
    if invite_only_flag is not None:
        _set(db, K_INVITE_ONLY, "true" if invite_only_flag else "false")
    if email_verify is not None:
        mode = email_verify.lower()
        if mode not in ("auto", "on", "off"):
            raise ValueError("邮箱验证开关只能是 auto / on / off")
        _set(db, K_EMAIL_VERIFY, mode)


# ---------- 邀请码 ----------
def _gen_code(n: int = 10) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(n))


def generate_codes(db: Session, *, count: int, valid_days: int | None,
                   max_uses: int = 1, note: str = "", created_by: int | None = None) -> list[InviteCode]:
    """批量生成邀请码。count 个、每个可用 max_uses 次、valid_days 天后过期。"""
    if count < 1 or count > 200:
        raise ValueError("单次生成数量需在 1–200 之间")
    if max_uses < 1 or max_uses > 500:
        raise ValueError("每个邀请码的可用次数需在 1–500 之间")
    if valid_days is not None and (valid_days < 1 or valid_days > 3650):
        raise ValueError("有效期需在 1–3650 天之间（留空表示长期有效）")
    batch = datetime.utcnow().strftime("%Y%m%d%H%M%S") + secrets.token_hex(2)
    expires = datetime.utcnow() + timedelta(days=valid_days) if valid_days else None
    out: list[InviteCode] = []
    for _ in range(count):
        for _try in range(8):                       # 极小概率撞码，重试即可
            code = _gen_code()
            if not db.query(InviteCode).filter_by(code=code).first():
                break
        else:
            raise ValueError("生成邀请码失败，请重试")
        row = InviteCode(code=code, batch_id=batch, note=(note or "").strip()[:200],
                         max_uses=max_uses, used_count=0, expires_at=expires,
                         is_active=True, created_by=created_by)
        db.add(row)
        out.append(row)
    db.flush()
    return out


def code_state(row: InviteCode) -> str:
    if not row.is_active:
        return "disabled"
    if row.expires_at and row.expires_at < datetime.utcnow():
        return "expired"
    if (row.used_count or 0) >= (row.max_uses or 1):
        return "used_up"
    return "available"


def take_invite_code(db: Session, raw: str) -> InviteCode:
    """校验并占用一次邀请码。失败抛 ValueError（接口层会转成 400）。"""
    code = (raw or "").strip().upper().replace(" ", "").replace("-", "")
    if not code:
        raise ValueError("当前为邀请制注册，请填写邀请码")
    # PostgreSQL 上锁住这一行，避免两个并发注册把一次性码同时核销成功。
    # SQLite 测试环境会把 with_for_update() 安全地降级为普通查询。
    row = (db.query(InviteCode).filter_by(code=code)
           .with_for_update().first())
    if not row:
        raise ValueError("邀请码不存在，请向平台管理员确认后重新输入")
    state = code_state(row)
    if state == "disabled":
        raise ValueError("该邀请码已被管理员停用")
    if state == "expired":
        raise ValueError("该邀请码已过期，请向平台管理员索取新的邀请码")
    if state == "used_up":
        raise ValueError("该邀请码的可用次数已用完")
    row.used_count = (row.used_count or 0) + 1
    return row


def record_invite_use(db: Session, row: InviteCode, user) -> None:
    db.add(InviteCodeUse(code_id=row.id, user_id=user.id, username=user.username,
                         email=user.email))


# ---------- 邮箱验证码 ----------
def send_email_code(db: Session, email: str) -> dict:
    """给注册邮箱发一次性验证码。旧码立即作废，只认最新一条。"""
    email = (email or "").strip()
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        raise ValueError("请填写有效邮箱")
    if not email_backend_can_send():
        raise ValueError("注册邮箱验证尚未启用；当前注册无需验证码")
    (db.query(EmailVerification)
       .filter_by(email=email, purpose="register", used=False)
       .update({"used": True}, synchronize_session=False))
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(EmailVerification(email=email, code=code, purpose="register",
                             expires_at=datetime.utcnow() + timedelta(minutes=CODE_TTL_MINUTES)))
    db.commit()
    ev = send_email(db, user_id=None, to_email=email, kind="email_verify",
                    subject="【科研数据共享平台】注册邮箱验证码",
                    body=(f"你的注册验证码是：{code}\n\n"
                          f"有效期 {CODE_TTL_MINUTES} 分钟，请勿转发给他人。\n"
                          f"若非本人操作，忽略本邮件即可。"),
                    meta={"purpose": "register"})
    if ev.status != "sent":
        raise ValueError("验证码邮件发送失败，请稍后重试")
    return {"ok": True,
            "detail": f"验证码已发送到 {email}，{CODE_TTL_MINUTES} 分钟内有效"}


def verify_email_code(db: Session, email: str, code: str) -> None:
    """核验注册邮箱验证码；失败抛 ValueError。成功后该码立即作废。"""
    email = (email or "").strip()
    code = (code or "").strip()
    if not code:
        raise ValueError("请填写邮箱验证码")
    row = (db.query(EmailVerification)
           .filter_by(email=email, purpose="register", used=False)
           .order_by(EmailVerification.id.desc()).first())
    if not row:
        raise ValueError("请先点击「发送验证码」获取邮箱验证码")
    if row.expires_at and row.expires_at < datetime.utcnow():
        raise ValueError("验证码已过期，请重新发送")
    if (row.attempts or 0) >= CODE_MAX_ATTEMPTS:
        row.used = True
        db.commit()
        raise ValueError("验证码错误次数过多，请重新发送")
    if not secrets.compare_digest(row.code, code):
        row.attempts = (row.attempts or 0) + 1
        db.commit()
        raise ValueError(f"验证码不正确（还可重试 {CODE_MAX_ATTEMPTS - row.attempts} 次）")
    row.used = True
    # 不在这里提交：注册用户、邀请码核销、验证码消费必须在同一事务里原子完成。
