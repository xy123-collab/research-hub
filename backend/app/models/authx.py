"""账号安全与准入相关的新表（全部是新表，靠 create_all 自动建，无需 Alembic 迁移）。

覆盖三件事：
1. 邀请制注册：invite_codes（管理员批量生成的邀请码）+ invite_code_uses（核销记录）。
2. 注册邮箱验证：email_verifications（一次性验证码，10 分钟有效）。
3. 令牌撤销（修"改密码后旧 token 仍然有效"）：
   - token_epochs：每用户一行的"分水岭时间"，此前签发的所有令牌一律作废（改密码/注销/登出全部设备）；
   - revoked_tokens：单条 refresh 令牌作废（refresh 轮换时把旧的收进来，防止被长期复用）。
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, DateTime
from ..core.db import Base


# ---------- 邀请制注册 ----------
class InviteCode(Base):
    """邀请码。一批生成的码共享同一个 batch_id，便于在后台按批查看/停用。

    有效性 = is_active 且 未过期 且 used_count < max_uses。
    """
    __tablename__ = "invite_codes"
    id = Column(Integer, primary_key=True)
    code = Column(String(40), unique=True, index=True, nullable=False)
    batch_id = Column(String(40), index=True)          # 同一次生成的批次号
    note = Column(String(200))                          # 备注：发给谁/用途
    max_uses = Column(Integer, default=1)               # 可用次数（默认一码一人）
    used_count = Column(Integer, default=0)
    expires_at = Column(DateTime)                       # 到期时间（None=长期有效）
    is_active = Column(Boolean, default=True)           # 管理员可随时停用
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)


class InviteCodeUse(Base):
    """邀请码核销记录：谁在什么时候用哪个码注册的。"""
    __tablename__ = "invite_code_uses"
    id = Column(Integer, primary_key=True)
    code_id = Column(Integer, ForeignKey("invite_codes.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    username = Column(String(80))
    email = Column(String(200))
    used_at = Column(DateTime, default=datetime.utcnow)


# ---------- 注册邮箱验证 ----------
class EmailVerification(Base):
    """注册邮箱验证码（6 位数字，默认 10 分钟有效、最多试 5 次）。

    同一邮箱重复申请时旧码直接作废，只认最新一条。
    """
    __tablename__ = "email_verifications"
    id = Column(Integer, primary_key=True)
    email = Column(String(200), index=True, nullable=False)
    code = Column(String(10), nullable=False)
    purpose = Column(String(20), default="register")
    expires_at = Column(DateTime)
    attempts = Column(Integer, default=0)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------- 令牌撤销 ----------
class TokenEpoch(Base):
    """每用户一行的令牌分水岭：iat < not_before 的令牌一律视为失效。

    改密码、注销账号、"退出全部设备"时把 not_before 置为当前时间，
    等于一次性赶走所有已签发的 access / refresh 令牌。
    """
    __tablename__ = "token_epochs"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    not_before = Column(DateTime, default=datetime.utcnow)
    reason = Column(String(60))
    updated_at = Column(DateTime, default=datetime.utcnow)


class RevokedToken(Base):
    """被单独作废的令牌（按 jti）。目前用于 refresh 轮换：换新的同时旧的立即失效。

    expires_at 到期后可安全清理，避免表无限增长（登录时顺带清一次）。
    """
    __tablename__ = "revoked_tokens"
    jti = Column(String(40), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    expires_at = Column(DateTime)
    reason = Column(String(60))
    created_at = Column(DateTime, default=datetime.utcnow)
