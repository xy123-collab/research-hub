from pydantic import BaseModel, field_validator
from .common import ORMModel


class LoginIn(BaseModel):
    username: str
    password: str


class RegisterIn(BaseModel):
    username: str
    password: str
    display_name: str | None = None
    email: str   # 注册必填邮箱，用于找回密码与消息通知

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        v = (v or "").strip()
        if not v or "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("请填写有效邮箱，用于找回密码与消息通知")
        return v


class ForgotPasswordIn(BaseModel):
    email: str


class ResetPasswordIn(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _pw(cls, v):
        if len(v or "") < 6:
            raise ValueError("新密码至少 6 位")
        return v


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
