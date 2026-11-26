# 高校分级智能排课系统（多级通用版）V1.0

面向高等院校的纯 Web（B/S）智能排课与协同工作平台：支持**单个院系独立轻量化运行**与**全校多级统筹协同**，基于 `org_node` 多级自由调整组织树与 `Google OR-Tools (CP-SAT)` 确定性求解引擎。

## Linux 生产一键部署
```bash
chmod +x deploy.sh
sudo bash deploy.sh
```
- 单端口统一访问：`http://<服务器IP>`
- 接口文档控制台：`http://<服务器IP>/docs`
- 离线部署与运维说明详见 [docs/DEPLOY_AND_OPS.md](docs/DEPLOY_AND_OPS.md)
