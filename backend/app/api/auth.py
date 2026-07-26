import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..core.security import (hash_password, verify_password, create_access_token,
                             create_refresh_token, decode_token)
from ..core.permissions import get_current_user
from ..core.ratelimit import rate_limit
from ..core.audit import write_audit
from ..core.config import settings
from ..core.email_service import send_email
from ..models.user import User, Role
from ..models.extras import PasswordResetToken
from ..schemas.auth import (LoginIn, RegisterIn, TokenOut, RefreshIn, MeOut, EmailCodeIn,
                            ForgotPasswordIn, ResetPasswordIn)
from ..services import registration as reg
from ..services.tokens import purge_expired, revoke_all, revoke_jti, token_is_revoked

router = APIRouter(tags=["auth"])


@router.get("/auth/register-policy")
def register_policy(db: Session = Depends(get_db)):
    """登录页据此决定是否显示「邀请码」「邮箱验证码」输入框。公开接口，不含敏感信息。"""
    return reg.registration_policy(db)


@router.post("/auth/send-email-code")
def send_email_code(body: EmailCodeIn, request: Request, db: Session = Depends(get_db)):
    """注册前给邮箱发一次性验证码。限流：同一 IP 5 分钟 5 次、同一邮箱 10 分钟 3 次。"""
    email = body.email.strip()
    rate_limit("send-email-code", request, limit=5, window=300,
               message="验证码发送过于频繁")
    rate_limit(f"send-email-code:{email.lower()}", limit=3, window=600, by_ip=False,
               message="该邮箱验证码发送过于频繁")
    if db.query(User).filter_by(email=email).first():
        # 与找回密码一致，不向匿名调用者确认某邮箱是否已经注册。
        return {"ok": True, "detail": "若该邮箱可用于注册，我们已发送验证码"}
    return reg.send_email_code(db, email)


@router.post("/auth/register", response_model=TokenOut)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    rate_limit("register", request, limit=5, window=600, message="注册过于频繁")
    if db.query(User).filter_by(username=body.username).first():
        raise HTTPException(400, "账号名已存在")
    if db.query(User).filter_by(email=body.email).first():
        raise HTTPException(400, "该邮箱已被注册")

    # 邮箱验证：开关打开时必须先通过验证码校验
    if reg.email_verify_required(db):
        reg.verify_email_code(db, body.email, body.email_code or "")
    # 邀请制：开关打开时必须提供有效邀请码（占用次数在同一事务里，失败会整体回滚）
    invite = reg.take_invite_code(db, body.invite_code) if reg.invite_only(db) else None

    member = db.query(Role).filter_by(code="member").first()
    u = User(username=body.username, password_hash=hash_password(body.password),
             display_name=body.display_name or body.username, email=body.email,
             role_id=member.id if member else None, status="active")
    db.add(u); db.flush()
    if invite is not None:
        reg.record_invite_use(db, invite, u)
    write_audit(db, u.id, "account.register", "user", u.id)
    db.commit(); db.refresh(u)
    return TokenOut(access_token=create_access_token(u.id),
                    refresh_token=create_refresh_token(u.id))


@router.post("/auth/forgot-password")
def forgot_password(body: ForgotPasswordIn, request: Request, db: Session = Depends(get_db)):
    """请求找回密码：生成一次性重置令牌，通过邮件抽象层发送重置链接。

    出于安全，无论邮箱是否存在都返回相同结果（避免探测注册邮箱）。
    """
    rate_limit("forgot-password", request, limit=5, window=600,
               message="找回密码请求过于频繁")
    email = (body.email or "").strip()
    if email:
        rate_limit(f"forgot-password:{email.lower()}", limit=3, window=900, by_ip=False,
                   message="该邮箱的找回请求过于频繁")
    u = db.query(User).filter_by(email=email).first() if email else None
    if u:
        token = secrets.token_urlsafe(24)
        db.add(PasswordResetToken(user_id=u.id, token=token,
                                  expires_at=datetime.utcnow() + timedelta(hours=2)))
        db.commit()
        link = f"{settings.SITE_URL}/#/reset-password?token={token}"
        send_email(db, user_id=u.id, to_email=u.email, kind="password_reset",
                   subject="【科研数据共享平台】找回密码",
                   body=(f"你好 {u.display_name or u.username}：\n\n"
                         f"我们收到你的找回密码请求。请点击下方链接在 2 小时内重置密码：\n{link}\n\n"
                         f"若非本人操作，请忽略本邮件。"),
                   # 不把重置令牌写进 meta：管理后台能看到邮件记录，
                   # 令牌落库等于给有后台权限的人一把接管任意账号的钥匙。
                   meta={"expires_in_hours": 2})
    return {"ok": True, "detail": "若该邮箱存在，我们已发送重置链接"}


@router.post("/auth/forgot-username")
def forgot_username(body: ForgotPasswordIn, request: Request, db: Session = Depends(get_db)):
    """找回账号名：把该注册邮箱对应的账号名通过邮件告知本人。

    与找回密码一样，无论邮箱是否存在都返回相同结果（避免探测注册邮箱）。
    """
    rate_limit("forgot-username", request, limit=5, window=600,
               message="找回账号名请求过于频繁")
    email = (body.email or "").strip()
    u = db.query(User).filter_by(email=email).first() if email else None
    if u:
        send_email(db, user_id=u.id, to_email=u.email, kind="username_reminder",
                   subject="【科研数据共享平台】找回账号名",
                   body=(f"你好 {u.display_name or u.username}：\n\n"
                         f"我们收到你的找回账号名请求。你的账号名是：\n\n    {u.username}\n\n"
                         f"请使用该账号名配合密码登录。若你也忘记了密码，可在登录页选择「找回密码」。\n"
                         f"若非本人操作，请忽略本邮件。"),
                   meta={"username": u.username})
    return {"ok": True, "detail": "若该邮箱存在，我们已发送你的账号名"}


@router.post("/auth/reset-password")
def reset_password(body: ResetPasswordIn, db: Session = Depends(get_db)):
    row = db.query(PasswordResetToken).filter_by(token=body.token, used=False).first()
    if not row:
        raise HTTPException(400, "重置链接无效或已使用")
    if row.expires_at and row.expires_at < datetime.utcnow():
        raise HTTPException(400, "重置链接已过期，请重新申请")
    u = db.get(User, row.user_id)
    if not u:
        raise HTTPException(400, "用户不存在")
    u.password_hash = hash_password(body.new_password)
    row.used = True
    # 改完密码把旧令牌全部作废：账号被盗时改密码才真的能把攻击者赶下线
    revoke_all(db, u.id, reason="password_reset")
    write_audit(db, u.id, "account.password.reset", "user", u.id)
    db.commit()
    return {"ok": True, "detail": "密码已重置，请用新密码登录（其他设备上的登录状态已失效）"}


@router.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    rate_limit("login", request, limit=20, window=300, message="登录尝试过于频繁")
    rate_limit(f"login:{(body.username or '').lower()}", limit=5, window=900, by_ip=False,
               message="该账号连续登录失败次数过多，已临时锁定")
    u = db.query(User).filter_by(username=body.username).first()
    if not u or not verify_password(body.password, u.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "账号名或密码错误")
    if u.status == "left":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "账号已注销，无法再次登录")
    # 登录成功不该占用「失败次数」额度，把该账号的计数清掉
    from ..core.ratelimit import reset as _rl_reset
    _rl_reset(f"login:{(body.username or '').lower()}")
    purge_expired(db)
    write_audit(db, u.id, "login"); db.commit()
    return TokenOut(access_token=create_access_token(u.id),
                    refresh_token=create_refresh_token(u.id))


@router.post("/auth/refresh", response_model=TokenOut)
def refresh(body: RefreshIn, db: Session = Depends(get_db)):
    """用 refresh 令牌换新的 access 令牌，并**轮换** refresh 令牌本身。

    轮换 = 旧 refresh 立即作废。这样即使某次 refresh 被截获，也只能用一次，
    而且真正的用户下一次刷新会失败并被要求重新登录，异常可被发现。
    """
    payload = decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(401, "refresh 令牌无效")
    if token_is_revoked(db, payload):
        raise HTTPException(401, "登录状态已失效，请重新登录")
    uid = int(payload["sub"])
    u = db.get(User, uid)
    if not u or u.status == "left":
        raise HTTPException(401, "账号已注销或不存在，请重新登录")
    revoke_jti(db, payload, reason="rotated")
    try:
        db.commit()
    except Exception as exc:
        # 并发 refresh 都试图写入同一个 jti 时，唯一键只允许一个成功；
        # 其余请求视为旧令牌已被轮换，不能返回 500。
        from sqlalchemy.exc import IntegrityError
        db.rollback()
        if isinstance(exc, IntegrityError):
            raise HTTPException(401, "refresh 令牌已被使用，请重新登录")
        raise
    return TokenOut(access_token=create_access_token(uid),
                    refresh_token=create_refresh_token(uid))


@router.post("/auth/logout")
def logout(body: RefreshIn | None = None, db: Session = Depends(get_db)):
    """退出登录：凭 refresh 本身作废本次会话，不依赖可能已经过期的 access。

    任何持有该 refresh 的人最多只能把它自己作废，不能影响其他会话。
    """
    if body and body.refresh_token:
        payload = decode_token(body.refresh_token)
        if payload and payload.get("type") == "refresh":
            revoke_jti(db, payload, reason="logout")
    db.commit()
    return {"ok": True}


@router.post("/auth/logout-all")
def logout_all(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """退出全部设备：作废该账号当前已签发的所有令牌（含本机，需重新登录）。"""
    revoke_all(db, user.id, reason="logout_all")
    write_audit(db, user.id, "account.logout_all", "user", user.id)
    db.commit()
    return {"ok": True, "detail": "已退出全部设备，请重新登录"}


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)):
    return user
