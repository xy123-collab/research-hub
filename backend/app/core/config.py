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

    # ---- 邮件（抽象层；默认 mock，不强绑第三方；未来接 SMTP / 邮件 API）----
    EMAIL_BACKEND: str = "mock"          # mock | smtp | none
    EMAIL_FROM: str = "no-reply@research-hub.local"
    EMAIL_FROM_NAME: str = "科研数据共享平台"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_TLS: bool = True                # 587 STARTTLS 时为 True
    SMTP_SSL: bool = False               # 465 隐式 SSL 时设 True（端口=465 时也会自动启用）
    # 站点地址，用于邮件里的找回密码/跳转链接（部署后按实际域名/校内地址改）
    SITE_URL: str = "https://research-hub-pmow.onrender.com"
    # 每日消息摘要
    DIGEST_ENABLED: bool = True
    DIGEST_TZ: str = "Asia/Shanghai"
    DIGEST_HOURS: str = "8,18"           # 逗号分隔的小时（本地时区）
    # 每周帖子周报（默认周一 8:00，本地时区）
    WEEKLY_DIGEST_ENABLED: bool = True
    WEEKLY_DIGEST_DOW: str = "mon"       # APScheduler day_of_week
    WEEKLY_DIGEST_HOUR: int = 8

    # ---- 其它 ----
    # 留空时：本地开发允许任意来源；生产只允许 SITE_URL 同源。
    # 迁移到新域名时可用逗号分隔显式配置多个可信来源。
    ALLOWED_ORIGINS: str = ""
    MAX_UPLOAD_MB: int = 50
    MIN_PASSWORD_LEN: int = 10           # 注册/重置密码的最短长度（A6 生产配置基线）
    ENABLE_API_DOCS: bool = False        # 生产默认关闭 /docs、/redoc；本地开发自动打开
    # A4：只有 isolated_queue 才允许启用。Web 只投递任务，用户代码由独立的
    # --network none / --read-only / 无业务密钥 sandbox 容器执行。
    ENABLE_ONLINE_ANALYSIS: bool = False
    SANDBOX_BACKEND: str = "disabled"     # disabled | isolated_queue
    SANDBOX_JOB_DIR: str = "/sandbox-jobs"
    SANDBOX_TIMEOUT: int = 10
    RATE_LIMIT_ENABLED: bool = True      # 登录/注册/找回密码的频率限制（测试里关掉）
    PLATFORM_NAME_ZH: str = "科研数据共享平台"
    PLATFORM_NAME_EN: str = "Research Hub"
    PLATFORM_SLOGAN_ZH: str = "让每一份自建数据都可信、可迭代、可复用"
    PLATFORM_SLOGAN_EN: str = "Make every self-built dataset trustworthy, iterable and reusable"

    @property
    def origins_list(self):
        configured = self.ALLOWED_ORIGINS.strip()
        if configured == "*":
            return ["*"]
        if configured:
            return [o.strip() for o in configured.split(",") if o.strip()]
        if not self.is_production:
            return ["*"]
        from urllib.parse import urlsplit
        site = urlsplit(self.SITE_URL)
        return [f"{site.scheme}://{site.netloc}"] if site.scheme and site.netloc else []

    # ---- 生产环境判定与启动自检（A6）----
    @property
    def is_production(self) -> bool:
        """用 sqlite 即视为本地/测试；用 Postgres 即视为真实部署。

        这样不需要再引入一个容易忘记设置的 APP_ENV 变量：线上 Render/阿里云
        注入的都是 Postgres 的 DATABASE_URL，本地开发与 pytest 用的都是 sqlite。
        """
        return not self.DATABASE_URL.startswith("sqlite")

    @property
    def docs_enabled(self) -> bool:
        return self.ENABLE_API_DOCS or not self.is_production

    def assert_production_ready(self) -> None:
        """生产环境缺少关键密钥时直接拒绝启动，而不是带着默认值裸奔。

        触发时请在部署面板（Render Environment / 服务器 .env）补齐后重启。
        生成强密钥：python -c "import secrets;print(secrets.token_urlsafe(48))"
        """
        if not self.is_production:
            return
        if self.JWT_SECRET.strip() in ("", "change-me-in-prod"):
            raise RuntimeError(
                "启动被拒绝：生产环境的 JWT_SECRET 仍是默认值。任何人都能用它伪造"
                "包括总管理员在内的任意用户令牌。请在部署环境变量里设置一个强随机值："
                'python -c "import secrets;print(secrets.token_urlsafe(48))"')
        storage_backend = self.STORAGE_BACKEND.strip().lower()
        if storage_backend != "cos":
            raise RuntimeError(
                "启动被拒绝：生产文件存储必须使用腾讯云 COS（STORAGE_BACKEND=cos）。"
                "本地容器磁盘会在重部署后清空，并让数据库中已有的 COS 文件全部不可见。")
        missing_cos = [
            name for name in ("COS_BUCKET", "COS_REGION", "COS_SECRET_ID", "COS_SECRET_KEY")
            if not getattr(self, name).strip()
        ]
        if missing_cos:
            raise RuntimeError(
                "启动被拒绝：COS 配置不完整，缺少 " + "、".join(missing_cos))
        if self.ENABLE_ONLINE_ANALYSIS and self.SANDBOX_BACKEND != "isolated_queue":
            raise RuntimeError(
                "启动被拒绝：ENABLE_ONLINE_ANALYSIS=true 时必须设置 "
                "SANDBOX_BACKEND=isolated_queue，并启动独立 sandbox 容器。")


settings = Settings()
