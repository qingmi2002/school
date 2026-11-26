# 高校分级智能排课系统（多级通用版）V1.0 部署与运维手册

## 1. 服务器配置建议
- **推荐配置**：Linux（Ubuntu 22.04/24.04、Debian 12、Rocky/CentOS 8+ 或国产麒麟/统信），8 核 CPU / 16 GB 内存 / 100 GB 磁盘，已安装 Docker Engine 与 Docker Compose V2。
- **对外端口**：仅需开放 `80` 端口（或 `.env` 中自定义的 `APP_PORT`），前端静态页面与后端 `/api` 均通过 Nginx 单端口统一对外提供服务。

## 2. Linux 一键部署（在线模式）
```bash
git clone <你的GitHub仓库地址> smart-schedule
cd smart-schedule
chmod +x deploy.sh
sudo bash deploy.sh
```
脚本将自动完成：随机强密码 `.env` 生成、持久化目录 `/opt/smart-schedule/data` 创建、容器镜像构建、PostgreSQL 15 自动执行 `alembic upgrade head` 建好 16 张核心表、全栈启动与 `/health` 健康检查。

## 3. 无外网校园内网离线部署
1. 在有外网环境拉取或构建镜像并导出：
   ```bash
   docker save postgres:15-alpine redis:7-alpine smart-schedule-backend:v1.0.0 smart-schedule-web:v1.0.0 | gzip > smart-schedule-images.tar.gz
   ```
2. 将代码目录与 `smart-schedule-images.tar.gz` 拷贝至内网 Linux 服务器后执行：
   ```bash
   sudo bash deploy.sh --offline smart-schedule-images.tar.gz
   ```

## 4. 首次上线初始化（支持单院系独立 / 全校多级）
打开 `http://服务器IP/docs` 或调用接口一键初始化高校组织树（7 套预设任选其一）：
- **单个院系独立使用**：`POST /api/v1/org/presets/single_dept_standalone/apply`
- **全校多级统筹**：支持 `school_college_dept`（校-院-系）、`school_college_flat`（校-院）、`school_dept_vocational`（校-系）、`multi_campus_four_tier`（多校区四级）、`academy_college_dual`（学部/书院制）、`public_dept_and_training_center`（独立公共部+实训中心）。

## 5. 日常备份、迁移与升级
- **一键冷备/迁移**：所有数据库文件与云盘归档产物均集中存放在 `/opt/smart-schedule/data/`，定时 `tar -czf` 打包该目录即可。
- **平滑升级**：`git pull && sudo bash deploy.sh --upgrade`。
