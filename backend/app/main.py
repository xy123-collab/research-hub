from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .core.config import settings
from .core.permissions import require_super_admin
from .api import api_router

# A6：生产环境不暴露 /docs、/redoc（等于把全部接口清单和参数结构公开）。
# 需要临时打开时把环境变量 ENABLE_API_DOCS 设为 true。
_docs = "/docs" if settings.docs_enabled else None
app = FastAPI(title="科研数据共享平台 API", version="1.0",
              docs_url=_docs, redoc_url=("/redoc" if settings.docs_enabled else None),
              openapi_url=("/openapi.json" if settings.docs_enabled else None))

# A6：启动即校验生产配置（JWT_SECRET 仍是默认值就直接拒绝启动），
# 避免"忘了配密钥 → 任何人可自行签发总管理员令牌"这种静默的致命错误。
settings.assert_production_ready()

# A6/B5：allow_origins=["*"] 与 allow_credentials=True 同时出现时，
# Starlette 会回显任意来源域。平台用 Bearer 令牌、不依赖 Cookie，
# 因此未配白名单时关掉 credentials；配了白名单才允许带凭证。
_origins = settings.origins_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=(_origins != ["*"]),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok",
            "platform_zh": settings.PLATFORM_NAME_ZH,
            "platform_en": settings.PLATFORM_NAME_EN,
            "storage": settings.STORAGE_BACKEND,
            "ai_provider": settings.AI_PROVIDER}


@app.get("/api/config")
def public_config():
    return {"name_zh": settings.PLATFORM_NAME_ZH, "name_en": settings.PLATFORM_NAME_EN,
            "slogan_zh": settings.PLATFORM_SLOGAN_ZH, "slogan_en": settings.PLATFORM_SLOGAN_EN,
            "footer": "北京大学国家发展研究院 · 智慧科研团队"}


app.include_router(api_router)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# 定时任务（APScheduler）：每日消息摘要邮件（默认 8:00 / 18:00，本地时区可配）
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    _sched = BackgroundScheduler()

    @app.on_event("startup")
    def _start_scheduler():
        if _sched.running:
            return
        if settings.DIGEST_ENABLED:
            try:
                from .services.digest import run_digest_once
                from .services.notify import flush_due_deliveries
                from .core.db import SessionLocal

                def _flush_job():
                    _db = SessionLocal()
                    try:
                        flush_due_deliveries(_db)
                    finally:
                        _db.close()

                hours = [h.strip() for h in str(settings.DIGEST_HOURS).split(",") if h.strip()]
                for h in hours:
                    # 每日 8:00/18:00：消息摘要 + 到点的版本/代码更新汇总投递
                    _sched.add_job(
                        run_digest_once, CronTrigger(hour=int(h), minute=0,
                                                     timezone=settings.DIGEST_TZ),
                        id=f"digest_{h}", replace_existing=True)
                    _sched.add_job(
                        _flush_job, CronTrigger(hour=int(h), minute=5,
                                                timezone=settings.DIGEST_TZ),
                        id=f"flush_{h}", replace_existing=True)
                # 每周一 8:00：成员帖子周报（可用 WEEKLY_DIGEST_HOUR/DOW 环境变量微调）
                if settings.WEEKLY_DIGEST_ENABLED:
                    from .services.weekly_digest import run_weekly_digest_once
                    _sched.add_job(
                        run_weekly_digest_once,
                        CronTrigger(day_of_week=settings.WEEKLY_DIGEST_DOW,
                                    hour=settings.WEEKLY_DIGEST_HOUR, minute=0,
                                    timezone=settings.DIGEST_TZ),
                        id="weekly_digest", replace_existing=True)
            except Exception as e:  # 调度失败不影响主服务
                import logging
                logging.getLogger("scheduler").warning("注册摘要任务失败: %s", e)
        _sched.start()
except Exception:
    pass


# A2：下面三个「立刻给全平台群发邮件」的运维接口原来任何人都能 POST，
# 攻击者写个循环就能打爆企业邮日配额并轰炸全体用户邮箱。一律限平台总管理员。
@app.post("/api/admin/run-digest")
def _run_digest_now(_admin=Depends(require_super_admin)):
    """手动触发一次消息摘要巡检（便于测试/运维）。仅平台总管理员。"""
    from .services.digest import run_digest_once
    return run_digest_once()


@app.post("/api/admin/run-weekly-digest")
def _run_weekly_now(_admin=Depends(require_super_admin)):
    """手动触发一次每周帖子周报（便于测试/运维）。仅平台总管理员。"""
    from .services.weekly_digest import run_weekly_digest_once
    return run_weekly_digest_once()


@app.post("/api/admin/flush-deliveries")
def _flush_now(_admin=Depends(require_super_admin)):
    """手动把到点的版本/代码更新汇总投递发出（便于测试/运维）。仅平台总管理员。"""
    from .services.notify import flush_due_deliveries
    from .core.db import SessionLocal
    db = SessionLocal()
    try:
        return flush_due_deliveries(db)
    finally:
        db.close()


# 单服务模式（如 Render）：若存在前端构建产物 static/，由后端一并托管，
# 前后端同源、无需 CORS/额外反代。多容器部署（腾讯云/Oracle）用 nginx，此目录不存在则跳过。
import os
from fastapi.staticfiles import StaticFiles

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_STATIC_DIR):
    # 挂在最后：/api 与 /files 已在上面注册，静态托管只兜底其余路径（含前端 hash 路由的 /）
    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="frontend")
