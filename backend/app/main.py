from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .core.config import settings
from .api import api_router

app = FastAPI(title="科研数据共享平台 API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=True,
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


# 定时质量巡检（APScheduler；一期示意）
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    _sched = BackgroundScheduler()

    @app.on_event("startup")
    def _start_scheduler():
        if not _sched.running:
            _sched.start()
except Exception:
    pass


# 单服务模式（如 Render）：若存在前端构建产物 static/，由后端一并托管，
# 前后端同源、无需 CORS/额外反代。多容器部署（腾讯云/Oracle）用 nginx，此目录不存在则跳过。
import os
from fastapi.staticfiles import StaticFiles

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_STATIC_DIR):
    # 挂在最后：/api 与 /files 已在上面注册，静态托管只兜底其余路径（含前端 hash 路由的 /）
    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="frontend")
