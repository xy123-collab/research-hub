from pydantic import BaseModel
from .common import ORMModel


class LoginIn(BaseModel):
    username: str
    password: str


class RegisterIn(BaseModel):
    username: str
    password: str
    display_name: str | None = None
    email: str | None = None


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshIn(BaseModel):
    refresh_token: str


class MeOut(ORMModel):
    id: int
    username: str
    display_name: str | None = None
    email: str | None = None
    avatar: str | None = None
    bio_zh: str | None = None
    bio_en: str | None = None
    preferred_language: str = "zh"
    status: str = "active"
