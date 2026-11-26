# 高校分级智能排课系统（多级通用版）

面向高等院校的纯 Web（B/S）智能排课与协同工作平台：支持**单个院系独立轻量化运行**与**全校多级统筹协同**，基于 `org_node` 动态组织树与 `Google OR-Tools (CP-SAT)` 确定性求解器。

## 技术栈
- **前端**：Vue 3 + TypeScript + Vite + Element Plus
- **后端**：Python 3.11 + FastAPI + SQLAlchemy + Alembic
- **求解与异步**：Google OR-Tools (CP-SAT) + Celery + Redis
- **数据库**：PostgreSQL 15
- **归档**：Storage Adapter（NAS 本地挂载 / WebDAV 双通道）

## 快速启动
```bash
cp .env.example .env
docker compose up -d --build
```
- 后端健康检查：`http://localhost:8000/health`
- API 文档：`http://localhost:8000/docs`
- 前端工作台：`http://localhost:5173`
