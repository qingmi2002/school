# 高校分级智能排课系统（多级通用版）V1.0

面向高等院校的纯 Web（B/S）智能排课与协同工作平台：支持**单个院系独立轻量化运行**与**全校多级统筹协同**，基于 `org_node` 多级自由调整组织树与 `Google OR-Tools (CP-SAT)` 确定性求解引擎。

---

## 一、Linux 服务器一条命令一键安装（零参数）

```bash
curl -fsSL https://raw.githubusercontent.com/qingmi2002/school/main/install.sh | sudo bash
```

- 自动检测安装 Docker、自动避让被占用的 80 端口（自动切 `8088`）、自动生成随机强密码、优先直拉 GHCR 预构建镜像（拉不到自动回退本地构建）。

## 二、NAS（群晖 / 飞牛 OS / 极空间 / 绿联 / 1Panel / Portainer）一键部署

1. 打开 [Actions → Build & Publish Production Images](https://github.com/qingmi2002/school/actions) 点击一次 **Run workflow** 生成 `:latest` 镜像（首次在 GitHub Packages 中将两个镜像设为 Public 即可免登录拉取）。
2. 在 NAS 的 Docker Compose 界面新建项目，直接复制粘贴 [`docker-compose.nas.yml`](docker-compose.nas.yml) 全文，点击启动即可。
3. 浏览器打开 `http://<NAS的IP>:8088` 直接使用；排课归档文件自动落入同级 `./cloud_archive` 目录。

---

详细内网离线部署、备份与运维手册请见 [docs/DEPLOY_AND_OPS.md](docs/DEPLOY_AND_OPS.md)。
