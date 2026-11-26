#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# 高校分级智能排课系统（多级通用版）Linux 一键生产部署脚本
# 支持模式：
#   bash deploy.sh                         -> 在线构建/拉取并一键部署
#   bash deploy.sh --offline images.tar.gz -> 内网离线导入镜像并一键部署
#   bash deploy.sh --upgrade               -> 平滑升级镜像并执行数据库迁移
# ==============================================================================

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

MODE="install"
OFFLINE_TAR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --offline)
      MODE="offline"
      OFFLINE_TAR="${2:-}"
      shift 2
      ;;
    --upgrade)
      MODE="upgrade"
      shift
      ;;
    *)
      echo "[ERROR] 未知参数: $1"
      exit 1
      ;;
  esac
done

echo "==> [1/5] 检查 Docker 与 Docker Compose 环境..."
if ! command -v docker >/dev/null 2>&1; then
  echo "[ERROR] 未检测到 docker，请先安装 Docker Engine（Ubuntu 可执行: curl -fsSL https://get.docker.com | sh）"
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "[ERROR] 未检测到 docker compose 插件，请升级 Docker 至 Compose V2"
  exit 1
fi

echo "==> [2/5] 初始化生产环境配置 (.env) 与数据持久化目录..."
DATA_ROOT="${DATA_ROOT:-/opt/smart-schedule/data}"
mkdir -p "${DATA_ROOT}/postgres" "${DATA_ROOT}/archive_staging" "${DATA_ROOT}/cloud_archive"

if [[ ! -f ".env" ]]; then
  RAND_PW="$(openssl rand -hex 16 2>/dev/null || tr -dc 'A-Za-z0-9' </dev/urandom | head -c 24)"
  cat > .env <<EOF
APP_PORT=80
DATA_ROOT=${DATA_ROOT}
POSTGRES_DB=smart_schedule
POSTGRES_USER=schedule_admin
POSTGRES_PASSWORD=${RAND_PW}
DATABASE_URL=postgresql+psycopg2://schedule_admin:${RAND_PW}@postgres:5432/smart_schedule
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2
ARCHIVE_LOCAL_ROOT=/mnt/cloud_drive/SmartSchedule_Archive
ARCHIVE_STAGING_DIR=/app/archive_staging
WEBDAV_URL=
WEBDAV_USERNAME=
WEBDAV_PASSWORD=
EOF
  chmod 600 .env
  echo "    已自动生成带随机强密码的生产配置 .env"
fi

if [[ "$MODE" == "offline" ]]; then
  echo "==> [3/5] 离线导入镜像包: ${OFFLINE_TAR}..."
  if [[ -z "$OFFLINE_TAR" || ! -f "$OFFLINE_TAR" ]]; then
    echo "[ERROR] 离线镜像包不存在: ${OFFLINE_TAR}"
    exit 1
  fi
  docker load -i "$OFFLINE_TAR"
  echo "==> [4/5] 启动生产服务容器（离线模式）..."
  docker compose -f docker-compose.prod.yml up -d --no-build
elif [[ "$MODE" == "upgrade" ]]; then
  echo "==> [3/5] 拉取/重建最新生产镜像..."
  docker compose -f docker-compose.prod.yml build
  echo "==> [4/5] 平滑重启并自动执行数据库迁移..."
  docker compose -f docker-compose.prod.yml up -d
else
  echo "==> [3/5] 构建并准备生产镜像..."
  docker compose -f docker-compose.prod.yml build
  echo "==> [4/5] 启动全栈服务并自动初始化 16 张核心表..."
  docker compose -f docker-compose.prod.yml up -d
fi

echo "==> [5/5] 等待服务就绪并执行健康检查..."
APP_PORT="$(grep -E '^APP_PORT=' .env | cut -d'=' -f2 || echo 80)"
for i in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${APP_PORT}/health" >/dev/null 2>&1; then
    HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || echo '服务器IP')"
    echo ""
    echo "================================================================"
    echo " 高校分级智能排课系统（多级通用版）V1.0 部署成功！"
    echo " 访问地址：http://${HOST_IP}:${APP_PORT}"
    echo " 接口文档：http://${HOST_IP}:${APP_PORT}/docs"
    echo " 数据目录：${DATA_ROOT}（备份/迁移打包此目录即可）"
    echo "================================================================"
    exit 0
  fi
  sleep 2
done

echo "[WARN] 健康检查超时，请执行 docker compose -f docker-compose.prod.yml logs -f 查看日志"
exit 1
