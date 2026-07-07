from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..core.security import (hash_password, verify_password, create_access_token,
                             create_refresh_token, decode_token)
from ..core.permissions import get_current_user
from ..core.audit import write_audit
from ..models.user import User, Role
from ..schemas.auth import LoginIn, RegisterIn, TokenOut, RefreshIn, MeOut

router = APIRouter(tags=["auth"])


@router.post("/auth/register", response_model=TokenOut)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter_by(username=body.username).first():
        raise HTTPException(400, "用户名已存在")
    member = db.query(Role).filter_by(code="member").first()
    u = User(username=body.username, password_hash=hash_password(body.password),
             display_name=body.display_name or body.username, email=body.email,
             role_id=member.id if member else None, status="active")
    db.add(u); db.commit(); db.refresh(u)
    return TokenOut(access_token=create_access_token(u.id),
                    refresh_token=create_refresh_token(u.id))


@router.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.query(User).filter_by(username=body.username).first()
    if not u or not verify_password(body.password, u.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")
    write_audit(db, u.id, "login"); db.commit()
    return TokenOut(access_token=create_access_token(u.id),
                    refresh_token=create_refresh_token(u.id))


@router.post("/auth/refresh", response_model=TokenOut)
def refresh(body: RefreshIn, db: Session = Depends(get_db)):
    payload = decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(401, "refresh 令牌无效")
    uid = int(payload["sub"])
    return TokenOut(access_token=create_access_token(uid),
                    refresh_token=create_refresh_token(uid))


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)):
    return user
