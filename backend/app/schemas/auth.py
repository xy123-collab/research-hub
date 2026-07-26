from pydantic import BaseModel, field_validator
from ..core.security import password_problem
from .common import ORMModel


def _check_email(v: str) -> str:
    v = (v or "").strip().lower()
    if not v or "@" not in v or "." not in v.split("@")[-1]:
        raise ValueError("请填写有效邮箱，用于找回密码与消息通知")
    return v


class LoginIn(BaseModel):
    username: str
    password: str


class RegisterIn(BaseModel):
    username: str
    password: str
    display_name: str | None = None
    email: str   # 注册必填邮箱，用于找回密码与消息通知
    email_code: str | None = None    # 邮箱验证码（开启邮箱验证时必填）
    invite_code: str | None = None   # 邀请码（开启邀请制注册时必填）

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        return _check_email(v)

    @field_validator("password")
    @classmethod
    def _pw(cls, v):
        problem = password_problem(v)
        if problem:
            raise ValueError(problem)
        return v


class EmailCodeIn(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        return _check_email(v)


class ForgotPasswordIn(BaseModel):
    email: str


class ResetPasswordIn(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _pw(cls, v):
        problem = password_problem(v)
        if problem:
            raise ValueError(problem)
        return v


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshIn(BaseModel):
    refresh_token: str


class InviteCodeIn(BaseModel):
    """管理后台批量生成邀请码。valid_days 留空 = 长期有效。"""
    count: int = 10
    valid_days: int | None = 30
    max_uses: int = 1
    note: str | None = None


class RegistrationSettingIn(BaseModel):
    invite_only: bool | None = None
    email_verify: str | None = None      # auto | on | off


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
