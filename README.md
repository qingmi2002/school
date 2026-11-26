# 高校分级智能排课系统（多级通用版）V1.0

面向高等院校的纯 Web（B/S）智能排课与协同工作平台：支持**单个院系独立轻量化运行**与**全校多级统筹协同**，基于 `org_node` 多级自由调整组织树与 `Google OR-Tools (CP-SAT)` 确定性求解引擎。

---

## 一、Linux 服务器一条命令一键安装（零参数）

```bash
curl -fsSL https://raw.githubusercontent.com/qingmi2002/school/main/install.sh | sudo bash
```

- 自动检测安装 Docker、自动避让被占用的 80 端口（自动切 `8088`）、自动生成随机强密码、优先直拉 GHCR 预构建镜像（拉不到自动回退本地构建）。

## 二、NAS（群晖 / 飞牛 OS / 极空间 / 绿联 / 1Panel / Portainer）一键部署

提供两份零修改直接粘贴的模板，按你的网络环境任选其一：
- **国内宽带直连推荐（防断流）**：复制粘贴 [`docker-compose.nas.cn.yml`](docker-compose.nas.cn.yml)（内置南京大学 GHCR 与 DaoCloud 国内镜像加速源）
- **海外 / 代理环境官方源**：复制粘贴 [`docker-compose.nas.yml`](docker-compose.nas.yml)（直连 `ghcr.io` 与 Docker Hub 官方源）

启动后浏览器打开 `http://<NAS的IP>:8088` 直接使用；排课归档文件自动落入同级 `./cloud_archive` 目录。

---

## 三、版本检测与手动确认升级

页面右上角会自动检测 `qingmi2002/school` 最新 Release 并亮起提醒（绝不静默自动重启）。确认升级时：
- **Linux 服务器**：执行 `cd /opt/smart-schedule && git pull && sudo bash deploy.sh --upgrade`（升级前自动热备 PostgreSQL 数据库）。
- **NAS**：在 Docker 界面重新拉取 `:latest` 镜像并重启容器即可。

详细内网离线部署、备份与运维手册请见 [docs/DEPLOY_AND_OPS.md](docs/DEPLOY_AND_OPS.md)。
