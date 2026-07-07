#!/usr/bin/env bash
# 腾讯云一键部署脚本。在 Lighthouse/CVM (Ubuntu 22.04) 上执行。
set -e
cd "$(dirname "$0")/.."   # 项目根

echo "=================================================="
echo " 科研数据共享平台 · 腾讯云一键部署"
echo "=================================================="

# 1. 检查 .env
if [ ! -f .env ]; then
  echo "[1/4] 未发现 .env，从模板复制。请编辑后重跑本脚本。"
  cp deploy/.env.example .env
  echo ">>> 已生成 .env，请填入 DATABASE_URL / COS_* / JWT_SECRET 等，然后重新执行 bash deploy/deploy.sh"
  exit 0
fi
echo "[1/4] .env 已存在 ✓"

# 2. 安装 Docker（若缺）
if ! command -v docker >/dev/null 2>&1; then
  echo "[2/4] 安装 Docker..."
  curl -fsSL https://get.docker.com | bash
  systemctl enable --now docker
else
  echo "[2/4] Docker 已安装 ✓"
fi

# 3. 选择 compose 命令
if docker compose version >/dev/null 2>&1; then COMPOSE="docker compose"; else COMPOSE="docker-compose"; fi

# 4. 构建并启动
PROFILE_ARG=""
if grep -q "LOCAL_DB=true" .env 2>/dev/null; then
  echo "[3/4] 检测到 LOCAL_DB=true，将同机启动 PostgreSQL"
  PROFILE_ARG="--profile local-db"
fi
echo "[3/4] 构建镜像并启动容器..."
$COMPOSE -f deploy/docker-compose.yml $PROFILE_ARG up -d --build

echo "[4/4] 部署完成 ✓"
echo "--------------------------------------------------"
echo " 访问: http://<你的服务器公网IP>/"
echo " 默认账号: admin/admin123  lixiaoyu/pass123  chenmo/pass123"
echo " 健康检查: curl http://localhost/api/health"
echo " 查看日志: $COMPOSE -f deploy/docker-compose.yml logs -f web"
echo "--------------------------------------------------"
echo " ⚠ 生产务必：修改默认密码、设置强 JWT_SECRET、配置 HTTPS 证书、确认腾讯云仅放合成/脱敏数据。"
