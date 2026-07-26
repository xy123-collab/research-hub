import uuid
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from .config import settings

_ph = PasswordHasher()


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, pw)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def _token(sub: str, ttl: int, kind: str) -> str:
    # jti：令牌唯一编号，用于「单条令牌作废」（refresh 轮换时把旧的收进 revoked_tokens）。
    now = datetime.now(timezone.utc)
    payload = {"sub": str(sub), "type": kind, "jti": uuid.uuid4().hex,
               "issued_ms": int(now.timestamp() * 1000),
               "iat": now, "exp": now + timedelta(seconds=ttl)}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)


def create_access_token(user_id) -> str:
    return _token(user_id, settings.JWT_ACCESS_TTL, "access")


def create_refresh_token(user_id) -> str:
    return _token(user_id, settings.JWT_REFRESH_TTL, "refresh")


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
    except JWTError:
        return None


# ---------- 密码强度（注册 / 重置共用一套口径）----------
_WEAK_PASSWORDS = {
    "password", "12345678", "123456789", "1234567890", "qwertyuiop",
    "adminadmin", "admin12345", "passw0rd123", "iloveyou123", "abc123456",
}


def password_problem(pw: str) -> str | None:
    """返回不合规的原因；合规返回 None。

    口径（见《平台规则/08-账号与安全规则》）：长度 ≥ MIN_PASSWORD_LEN，
    且至少包含「字母 / 数字 / 符号」中的两类，且不在常见弱口令表里。
    """
    pw = pw or ""
    n = settings.MIN_PASSWORD_LEN
    if len(pw) < n:
        return f"密码至少 {n} 位"
    if pw.strip() != pw:
        return "密码首尾不能有空格"
    kinds = sum([any(c.isalpha() for c in pw),
                 any(c.isdigit() for c in pw),
                 any(not c.isalnum() for c in pw)])
    if kinds < 2:
        return "密码需包含字母、数字、符号中的至少两类"
    if pw.lower() in _WEAK_PASSWORDS:
        return "该密码过于常见，请更换"
    return None
