#!/usr/bin/env bash
set -e
echo "[entrypoint] 等待数据库就绪..."
python - <<'PY'
import time, sys
from sqlalchemy import create_engine, text
from app.core.config import settings
for i in range(30):
    try:
        e = create_engine(settings.DATABASE_URL)
        with e.connect() as c:
            c.execute(text("SELECT 1"))
        print("[entrypoint] 数据库连接成功"); break
    except Exception as ex:
        print(f"[entrypoint] 重试 {i+1}/30: {ex}"); time.sleep(2)
else:
    print("[entrypoint] 数据库连接失败"); sys.exit(1)
PY

echo "[entrypoint] 执行数据库迁移 (alembic upgrade head)..."
alembic upgrade head || echo "[entrypoint] 迁移跳过/已最新"

if [ "${SEED_ON_START:-true}" = "true" ]; then
  echo "[entrypoint] 初始化 seed 数据（仅首次，库非空则跳过）..."
  python -m app.seed || true
fi

echo "[entrypoint] 执行数据修正（幂等/一次性）..."
python -m app.data_fixes || true

echo "[entrypoint] 启动 Gunicorn..."
# 免费档 512MB：默认单 worker；--max-requests 让 worker 处理一定请求数后回收，
# 释放偶发的 pandas 沙箱内存，避免缓慢增长触发 OOM 重启。
exec gunicorn app.main:app \
  -k uvicorn.workers.UvicornWorker \
  -w "${WEB_CONCURRENCY:-1}" -b 0.0.0.0:8000 --timeout 120 \
  --max-requests 400 --max-requests-jitter 50
