# 高校分级智能排课系统（多级通用版）V1.0

面向高等院校的纯 Web（B/S）智能排课与协同工作平台：支持**单个院系独立轻量化运行**与**全校多级统筹协同**，基于 `org_node` 多级自由调整组织树与 `Google OR-Tools (CP-SAT)` 确定性求解引擎。

---

## 一、Linux 服务器一条命令一键拉取安装（最简单）

把 `<你的GitHub用户名>` 替换为你的用户名，在 Linux 服务器直接运行：
```bash
curl -fsSL https://raw.githubusercontent.com/<你的GitHub用户名>/school/main/install.sh | sudo REPO_OWNER=<你的GitHub用户名> bash
```
- 自动检测安装 Docker、自动避让 80 端口（被占自动切 `8088`）、自动生成随机强密码、优先拉取云端预构建镜像极速启动。

## 二、NAS（群晖 / 飞牛 OS / 极空间 / 绿联 / Portainer）一键部署

1. 先在 GitHub 仓库的 **Actions → Build & Publish Production Images** 点一次 **Run workflow**，自动产出 `:latest` 镜像（首次在 GitHub Packages 中将两个镜像设为 Public 即可免密拉取）。
2. 在 NAS 的 Docker Compose 界面新建项目，直接复制粘贴仓库中的 [`docker-compose.nas.yml`](docker-compose.nas.yml)（把 `YOUR_GITHUB_USER` 改为你的小写用户名），点击启动即可。
3. 浏览器打开 `http://<NAS的IP>:8088` 直接使用；排课归档文件自动落入同级 `./cloud_archive` 目录，SMB 共享随时查看。

---

详细内网离线部署、备份与运维手册请见 [docs/DEPLOY_AND_OPS.md](docs/DEPLOY_AND_OPS.md)。
