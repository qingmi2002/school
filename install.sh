#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# 高校分级智能排课系统（多级通用版）Linux 全自动一键拉取安装脚本
# 开箱即用命令：
#   curl -fsSL https://raw.githubusercontent.com/qingmi2002/school/main/install.sh | sudo bash
# 可选环境变量：
#   INSTALL_DIR=/opt/smart-schedule   安装目录
#   APP_PORT=80                       对外端口（若80被占自动切换为8088）
#   USE_PREBUILT=auto                 auto(优先拉GHCR镜像，失败自动本地构建) / true / false
# ==============================================================================

REPO_OWNER="${REPO_OWNER:-qingmi2002}"
REPO_NAME="${REPO_NAME:-school}"
BRANCH="${BRANCH:-main}"
INSTALL_DIR="${INSTALL_DIR:-/opt/smart-schedule}"
APP_PORT="${APP_PORT:-}"
USE_PREBUILT="${USE_PREBUILT:-auto}"

OWNER_LOWER="$(echo "$REPO_OWNER" | tr '[:upper:]' '[:lower:]')"
REPO_URL="https://github.com/${REPO_OWNER}/${REPO_NAME}.git"
BACKEND_IMG="ghcr.io/${OWNER_LOWER}/smart-schedule-backend:latest"
WEB_IMG="ghcr.io/${OWNER_LOWER}/smart-schedule-web:latest"

echo "==> [1/5] 检查并准备基础依赖 (git / docker / docker compose)..."
if ! command -v docker >/dev/null 2>&1; then
  echo "    未检测到 Docker，正在自动安装 Docker Engine..."
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker >/dev/null 2>&1 || true
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "[ERROR] 当前 Docker 版本不支持 docker compose v2，请升级 Docker 后重试。"
  exit 1
fi

echo "==> [2/5] 拉取最新项目代码至 ${INSTALL_DIR}..."
mkdir -p "$(dirname "$INSTALL_DIR")"
if [[ -d "${INSTALL_DIR}/.git" ]]; then
  git -C "$INSTALL_DIR" fetch origin "$BRANCH"
  git -C "$INSTALL_DIR" reset --hard "origin/${BRANCH}"
else
  if ! command -v git >/dev/null 2>&1; then
    if command -v apt-get >/dev/null 2>&1; then
      apt-get update -qq && apt-get install -y -qq git >/dev/null
    elif command -v yum >/dev/null 2>&1; then
      yum install -y -q git >/dev/null
    fi
  fi
  git clone --depth 1 -b "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

echo "==> [3/5] 智能检测端口并生成生产环境配置 (.env)..."
if [[ -z "$APP_PORT" ]]; then
  if ss -tln 2>/dev/null | grep -qE '(:80\s|:80$)'; then
    APP_PORT="8088"
    echo "    检测到 80 端口已被占用，自动切换对外端口为 ${APP_PORT}"
  else
    APP_PORT="80"
  fi
fi

DATA_ROOT="${INSTALL_DIR}/data"
mkdir -p "${DATA_ROOT}/postgres" "${DATA_ROOT}/archive_staging" "${DATA_ROOT}/cloud_archive"

if [[ ! -f ".env" ]]; then
  RAND_PW="$(openssl rand -hex 16 2>/dev/null || tr -dc 'A-Za-z0-9' </dev/urandom | head -c 24)"
  cat > .env <<EOF
APP_PORT=${APP_PORT}
DATA_ROOT=${DATA_ROOT}
BACKEND_IMAGE=${BACKEND_IMG}
FRONTEND_IMAGE=${WEB_IMG}
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

echo "==> [4/5] 拉取云端预构建镜像并一键启动服务..."
PULLED=false
if [[ "$USE_PREBUILT" != "false" ]]; then
  if docker pull "$BACKEND_IMG" >/dev/null 2>&1 && docker pull "$WEB_IMG" >/dev/null 2>&1; then
    PULLED=true
    echo "    成功拉取 GHCR 云端预构建镜像，免编译极速启动！"
  fi
fi

if [[ "$PULLED" == "true" ]]; then
  docker compose -f docker-compose.prod.yml up -d --no-build
else
  echo "    未找到公开预构建镜像，自动回退为本地构建启动（首次约需 2-4 分钟）..."
  docker compose -f docker-compose.prod.yml up -d --build
fi

echo "==> [5/5] 等待数据库迁移与健康检查..."
FINAL_PORT="$(grep -E '^APP_PORT=' .env | cut -d'=' -f2 || echo 80)"
for i in $(seq 1 35); do
  if curl -fsS "http://127.0.0.1:${FINAL_PORT}/health" >/dev/null 2>&1; then
    HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || echo '服务器IP')"
    echo ""
    echo "================================================================"
    echo " 高校分级智能排课系统（多级通用版）V1.0 一键安装成功！"
    echo " 网页访问：http://${HOST_IP}:${FINAL_PORT}"
    echo " 接口文档：http://${HOST_IP}:${FINAL_PORT}/docs"
    echo " 归档目录：${DATA_ROOT}/cloud_archive"
    echo " 日常更新：cd ${INSTALL_DIR} && sudo bash deploy.sh --upgrade"
    echo "================================================================"
    exit 0
  fi
  sleep 2
done

echo "[WARN] 启动耗时较长，请运行以下命令查看实时日志："
echo "  cd ${INSTALL_DIR} && docker compose -f docker-compose.prod.yml logs -f"
exit 1
