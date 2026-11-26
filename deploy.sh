#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# 高校分级智能排课系统（多级通用版）Linux 生产部署与手动确认升级脚本
#   bash deploy.sh                         -> 首次部署
#   bash deploy.sh --offline images.tar.gz -> 内网离线部署
#   bash deploy.sh --upgrade               -> 手动确认升级（先自动备份数据库再升级）
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

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  echo "[ERROR] 请先安装 Docker Engine 与 Docker Compose V2"
  exit 1
fi

DATA_ROOT="${DATA_ROOT:-/opt/smart-schedule/data}"
mkdir -p "${DATA_ROOT}/postgres" "${DATA_ROOT}/archive_staging" "${DATA_ROOT}/cloud_archive" "${DATA_ROOT}/backups"

if [[ ! -f ".env" ]]; then
  RAND_PW="$(openssl rand -hex 16 2>/dev/null || tr -dc 'A-Za-z0-9' </dev/urandom | head -c 24)"
  cat > .env <<EOF
APP_PORT=80
DATA_ROOT=${DATA_ROOT}
BACKEND_IMAGE=ghcr.io/qingmi2002/smart-schedule-backend:latest
FRONTEND_IMAGE=ghcr.io/qingmi2002/smart-schedule-web:latest
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
fi

if [[ "$MODE" == "upgrade" ]]; then
  echo "==> [升级前保护] 正在自动热备 PostgreSQL 数据库至 ${DATA_ROOT}/backups/ ..."
  BACKUP_FILE="${DATA_ROOT}/backups/pre_upgrade_$(date +%Y%m%d_%H%M%S).sql.gz"
  if docker ps --format '{{.Names}}' | grep -q '^smart_schedule_pg$'; then
    PG_USER="$(grep -E '^POSTGRES_USER=' .env | cut -d'=' -f2 || echo schedule_admin)"
    PG_DB="$(grep -E '^POSTGRES_DB=' .env | cut -d'=' -f2 || echo smart_schedule)"
    docker exec smart_schedule_pg pg_dump -U "$PG_USER" "$PG_DB" | gzip > "$BACKUP_FILE"
    echo "    数据库备份完成：${BACKUP_FILE}"
  fi

  echo "==> [升级] 拉取最新云端镜像（若不可达则自动本地构建）..."
  if docker compose -f docker-compose.prod.yml pull backend celery-worker web >/dev/null 2>&1; then
    docker compose -f docker-compose.prod.yml up -d --no-build
  else
    docker compose -f docker-compose.prod.yml up -d --build
  fi
elif [[ "$MODE" == "offline" ]]; then
  if [[ -z "$OFFLINE_TAR" || ! -f "$OFFLINE_TAR" ]]; then
    echo "[ERROR] 离线镜像包不存在: ${OFFLINE_TAR}"
    exit 1
  fi
  docker load -i "$OFFLINE_TAR"
  docker compose -f docker-compose.prod.yml up -d --no-build
else
  docker compose -f docker-compose.prod.yml up -d --build
fi

APP_PORT="$(grep -E '^APP_PORT=' .env | cut -d'=' -f2 || echo 80)"
for i in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${APP_PORT}/health" >/dev/null 2>&1; then
    HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || echo '服务器IP')"
    echo "================================================================"
    echo " 操作完成！访问地址：http://${HOST_IP}:${APP_PORT}"
    echo "================================================================"
    exit 0
  fi
  sleep 2
done
echo "[WARN] 健康检查超时，请查看 docker compose -f docker-compose.prod.yml logs -f"
exit 1
