import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..core.security import (hash_password, verify_password, create_access_token,
                             create_refresh_token, decode_token)
from ..core.permissions import get_current_user
from ..core.audit import write_audit
from ..core.config import settings
from ..core.email_service import send_email
from ..models.user import User, Role
from ..models.extras import PasswordResetToken
from ..schemas.auth import (LoginIn, RegisterIn, TokenOut, RefreshIn, MeOut,
                            ForgotPasswordIn, ResetPasswordIn)

router = APIRouter(tags=["auth"])


@router.post("/auth/register", response_model=TokenOut)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter_by(username=body.username).first():
        raise HTTPException(400, "账号名已存在")
    if db.query(User).filter_by(email=body.email).first():
        raise HTTPException(400, "该邮箱已被注册")
    member = db.query(Role).filter_by(code="member").first()
    u = User(username=body.username, password_hash=hash_password(body.password),
             display_name=body.display_name or body.username, email=body.email,
             role_id=member.id if member else None, status="active")
    db.add(u); db.commit(); db.refresh(u)
    return TokenOut(access_token=create_access_token(u.id),
                    refresh_token=create_refresh_token(u.id))


@router.post("/auth/forgot-password")
def forgot_password(body: ForgotPasswordIn, db: Session = Depends(get_db)):
    """请求找回密码：生成一次性重置令牌，通过邮件抽象层发送重置链接。

    出于安全，无论邮箱是否存在都返回相同结果（避免探测注册邮箱）。
    """
    email = (body.email or "").strip()
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
                   meta={"token": token})
    return {"ok": True, "detail": "若该邮箱存在，我们已发送重置链接"}


@router.post("/auth/forgot-username")
def forgot_username(body: ForgotPasswordIn, db: Session = Depends(get_db)):
    """找回账号名：把该注册邮箱对应的账号名通过邮件告知本人。

    与找回密码一样，无论邮箱是否存在都返回相同结果（避免探测注册邮箱）。
    """
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
    db.commit()
    return {"ok": True, "detail": "密码已重置，请用新密码登录"}


@router.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.query(User).filter_by(username=body.username).first()
    if not u or not verify_password(body.password, u.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "账号名或密码错误")
    if u.status == "left":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "账号已注销，无法再次登录")
    write_audit(db, u.id, "login"); db.commit()
    return TokenOut(access_token=create_access_token(u.id),
                    refresh_token=create_refresh_token(u.id))


@router.post("/auth/refresh", response_model=TokenOut)
def refresh(body: RefreshIn, db: Session = Depends(get_db)):
    payload = decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(401, "refresh 令牌无效")
    uid = int(payload["sub"])
    u = db.get(User, uid)
    if not u or u.status == "left":
        raise HTTPException(401, "账号已注销或不存在，请重新登录")
    return TokenOut(access_token=create_access_token(uid),
                    refresh_token=create_refresh_token(uid))


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)):
    return user
