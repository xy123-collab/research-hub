#!/usr/bin/env bash
set -e
echo "[entrypoint] 等待数据库就绪..."
python - <<'PY'
import os, time, sys
from sqlalchemy import create_engine, text
from app.core.config import settings
raw_storage = os.environ.get("STORAGE_BACKEND")
cos_presence = {
    name: bool(os.environ.get(name, "").strip())
    for name in ("COS_BUCKET", "COS_REGION", "COS_SECRET_ID", "COS_SECRET_KEY")
}
print(
    "[entrypoint] 存储配置诊断："
    f"STORAGE_BACKEND 原始值={raw_storage!r}，解析值={settings.STORAGE_BACKEND!r}；"
    f"COS 变量是否存在={cos_presence}"
)
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

# A6：生产环境默认**不**灌 seed。seed 会建 admin/admin123 等弱口令账号，
# 新库上线的瞬间就存在一个弱口令总管理员。需要初始化演示数据时，
# 临时把环境变量 SEED_ON_START 设为 true，跑完一次立刻改回 false。
if [ "${SEED_ON_START:-false}" = "true" ]; then
  echo "[entrypoint] 初始化 seed 数据（仅首次，库非空则跳过）..."
  python -m app.seed || true
else
  echo "[entrypoint] 跳过 seed（SEED_ON_START 未开启）。首次部署请手工创建管理员账号。"
  python -m app.bootstrap_admin || true
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
