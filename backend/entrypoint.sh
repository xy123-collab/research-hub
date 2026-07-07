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

echo "[entrypoint] 启动 Gunicorn..."
exec gunicorn app.main:app \
  -k uvicorn.workers.UvicornWorker \
  -w "${WEB_CONCURRENCY:-3}" -b 0.0.0.0:8000 --timeout 120
