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
    now = datetime.now(timezone.utc)
    payload = {"sub": str(sub), "type": kind, "iat": now, "exp": now + timedelta(seconds=ttl)}
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
