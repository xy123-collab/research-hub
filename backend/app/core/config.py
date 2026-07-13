from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ---- DB ----
    DATABASE_URL: str = "sqlite:///./dev.db"  # 生产: postgresql+psycopg2://user:pwd@host:5432/db

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def _normalize_db_url(cls, v: str) -> str:
        # 兼容 Render/Heroku 提供的 postgres:// 与无驱动的 postgresql://
        if v.startswith("postgres://"):
            v = "postgresql+psycopg2://" + v[len("postgres://"):]
        elif v.startswith("postgresql://"):
            v = "postgresql+psycopg2://" + v[len("postgresql://"):]
        return v

    # ---- Auth ----
    JWT_SECRET: str = "change-me-in-prod"
    JWT_ALG: str = "HS256"
    JWT_ACCESS_TTL: int = 3600           # 秒
    JWT_REFRESH_TTL: int = 60 * 60 * 24 * 14

    # ---- Storage ----
    STORAGE_BACKEND: str = "local"       # local | cos
    LOCAL_STORAGE_DIR: str = "./data"
    COS_BUCKET: str = ""
    COS_REGION: str = ""
    COS_SECRET_ID: str = ""
    COS_SECRET_KEY: str = ""
    COS_SIGNED_URL_TTL: int = 600

    # ---- AI 网关（OpenAI 兼容；默认腾讯云 TokenHub）----
    AI_PROVIDER: str = "none"            # none | tokenhub | openai | local（none=关闭）
    AI_BASE_URL: str = "https://tokenhub.tencentmaas.com/v1"
    AI_MODEL: str = "deepseek-v4-flash"          # 常规任务（评分/标签/总结）用快模型
    AI_MODEL_STRONG: str = "deepseek-v4-pro"     # 代码/写作等强任务
    AI_API_KEY: str = ""                          # ★ 只在环境变量里配，切勿写进代码/提交
    AI_GATEWAY_URL: str = ""                       # 兼容旧字段（留空即用 AI_BASE_URL）

    # ---- 其它 ----
    ALLOWED_ORIGINS: str = "*"
    MAX_UPLOAD_MB: int = 50
    PLATFORM_NAME_ZH: str = "科研数据共享平台"
    PLATFORM_NAME_EN: str = "Research Hub"
    PLATFORM_SLOGAN_ZH: str = "让每一份自建数据都可信、可迭代、可复用"
    PLATFORM_SLOGAN_EN: str = "Make every self-built dataset trustworthy, iterable and reusable"

    @property
    def origins_list(self):
        if self.ALLOWED_ORIGINS.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


settings = Settings()
