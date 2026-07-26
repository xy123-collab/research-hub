"""令牌有效性与撤销（对应整改清单 A1）。

原来的问题：access token 一小时到期、前端不刷新 → 用户被动掉线；
同时改密码/注销后旧令牌仍然有效 → 账号被盗后赶不走攻击者。

这里提供两种撤销粒度：
- revoke_all(db, uid)：整户作废（改密码、重置密码、注销账号、退出全部设备）。
  实现是记一个"分水岭时间"，此前签发的令牌全部失效，不用逐条登记。
- revoke_jti(db, ...)：单条作废（refresh 轮换时把旧的那条收掉）。
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models.authx import TokenEpoch, RevokedToken


def _as_naive_utc(ts) -> datetime | None:
    """JWT 里的 iat/exp 是 unix 秒；数据库里存的是 naive UTC，统一成后者好比较。"""
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts.astimezone(timezone.utc).replace(tzinfo=None) if ts.tzinfo else ts
    try:
        return datetime.utcfromtimestamp(float(ts))
    except (TypeError, ValueError, OSError):
        return None


def revoke_all(db: Session, user_id: int, reason: str = "security") -> None:
    """作废该用户当前已签发的所有令牌（不立即 commit，交给调用方一起提交）。"""
    now = datetime.utcnow()
    row = db.get(TokenEpoch, user_id)
    if not row:
        row = TokenEpoch(user_id=user_id)
        db.add(row)
    row.not_before = now
    row.reason = reason
    row.updated_at = now


def revoke_jti(db: Session, payload: dict, reason: str = "rotated") -> None:
    """作废单条令牌（按 jti）。用于 refresh 轮换。"""
    jti = payload.get("jti")
    if not jti:
        return
    if db.get(RevokedToken, jti):
        return
    db.add(RevokedToken(jti=jti, user_id=int(payload.get("sub") or 0),
                        expires_at=_as_naive_utc(payload.get("exp")), reason=reason))


def token_is_revoked(db: Session, payload: dict) -> bool:
    """令牌是否已失效：命中 jti 黑名单，或签发时间早于该用户的分水岭。"""
    jti = payload.get("jti")
    if jti and db.get(RevokedToken, jti):
        return True
    try:
        uid = int(payload.get("sub"))
    except (TypeError, ValueError):
        return True
    row = db.get(TokenEpoch, uid)
    if not row or not row.not_before:
        return False
    issued_ms = payload.get("issued_ms")
    if issued_ms is not None:
        try:
            issued = datetime.utcfromtimestamp(float(issued_ms) / 1000)
            return issued < row.not_before
        except (TypeError, ValueError, OSError):
            return True
    iat = _as_naive_utc(payload.get("iat"))
    if iat is None:      # 老格式令牌没有 iat：一律按已失效处理，让用户重登一次
        return True
    return iat < row.not_before


def purge_expired(db: Session, keep_days: int = 1) -> int:
    """清理已过期的 jti 黑名单（令牌本身都过期了，没必要再留）。登录时顺带调用。"""
    cutoff = datetime.utcnow() - timedelta(days=keep_days)
    n = (db.query(RevokedToken)
         .filter(RevokedToken.expires_at.isnot(None), RevokedToken.expires_at < cutoff)
         .delete(synchronize_session=False))
    return n or 0
