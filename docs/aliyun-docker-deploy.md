# 阿里云 ECS Docker 部署说明

这套部署适用于 `royal-regent-nexus` 当前结构：Vue 3/Vite 前端、FastAPI 后端、PostgreSQL 数据库。

## 1. 阿里云侧准备

在 ECS 安全组入方向放行：

- `22/tcp`：SSH 登录。
- `80/tcp`：HTTP 访问。
- `443/tcp`：后续配置 HTTPS 时使用。

服务器建议使用 Ubuntu 22.04/24.04 或 Alibaba Cloud Linux 3。下面命令以 Ubuntu 为例。

## 2. 安装 Docker

```bash
sudo apt update
sudo apt install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
docker --version
docker compose version
```

如果执行了 `usermod`，重新登录 SSH 后再继续。

## 3. 从 GitHub 拉取代码

你的发布流程建议固定为：本地开发完成后提交并推送到 GitHub，服务器只从 GitHub 拉取最新代码并重建容器。

首次部署时，在服务器上执行：

```bash
sudo mkdir -p /opt/royal-regent
sudo chown "$USER":"$USER" /opt/royal-regent
cd /opt/royal-regent
git clone https://github.com/13829313399-a11y/Royal-Regent-Nexus.git royal-regent-nexus
cd royal-regent-nexus
```

如果仓库是私有仓库，先在服务器生成 SSH key，把公钥加到 GitHub，再把上面的 clone 地址换成 SSH 地址：

```bash
ssh-keygen -t ed25519 -C "aliyun-royal-regent"
cat ~/.ssh/id_ed25519.pub
git clone git@github.com:13829313399-a11y/Royal-Regent-Nexus.git royal-regent-nexus
```

服务器部署目录不要手动改源码，否则后续 `git pull --ff-only` 会因为本地脏文件而停止。

## 4. 配置生产环境变量

```bash
cp .env.production.example .env.production
nano .env.production
```

必须修改 `POSTGRES_PASSWORD`，并同步修改 `DATABASE_URL` 里的密码。密码里如果包含 `@`、`:`、`/` 等 URL 特殊字符，需要做 URL 编码；最简单的做法是使用只包含字母、数字、下划线和短横线的长随机密码。

## 5. 启动服务

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
docker compose -f docker-compose.prod.yml ps
```

`api` 容器启动时会自动执行：

```bash
alembic -c alembic.ini upgrade head
```

新 PostgreSQL 数据库会自动建立当前迁移里的表结构。

## 6. 验证

在服务器上执行：

```bash
curl http://127.0.0.1/health
curl -I http://127.0.0.1/
```

在浏览器访问：

```text
http://你的服务器公网IP/
```

如果已经绑定域名，把域名 A 记录指向 ECS 公网 IP，然后访问域名。

## 7. 清空旧部署并重新部署

如果之前已经部署过，但容器、数据库卷、旧代码目录或 Nginx 配置混乱，建议直接做一次干净重置。

重要：下面的重置会删除旧 Docker Compose 数据卷，也就是删除旧 PostgreSQL 数据。如果旧数据还要保留，先备份：

```bash
cd /opt/royal-regent/royal-regent-nexus
docker compose -f docker-compose.prod.yml exec db pg_dump -U rrnexus royal_regent_nexus > royal_regent_nexus_backup.sql
```

如果确定不要旧环境和旧数据库数据，在服务器上先拉一份最新脚本到临时目录：

```bash
rm -rf /tmp/rr-reset
git clone --depth 1 --branch main https://github.com/13829313399-a11y/Royal-Regent-Nexus.git /tmp/rr-reset
```

执行清理和重新 clone：

```bash
CONFIRM_RESET=DELETE_OLD_ROYAL_REGENT_DEPLOY \
BRANCH=main \
sh /tmp/rr-reset/deploy/reset-server-deploy.sh
```

如果生产部署拉的不是 `main`，把 `BRANCH=main` 改成你的部署分支。

重置脚本会做这些事：

- 停止旧 Compose 服务。
- 删除旧 Compose 数据卷。
- 删除旧部署目录 `/opt/royal-regent/royal-regent-nexus`。
- 从 GitHub 重新 clone 指定分支。
- 生成新的 `.env.production` 模板。
- 清理无用 Docker 镜像。

然后编辑生产环境变量：

```bash
cd /opt/royal-regent/royal-regent-nexus
nano .env.production
```

必须替换 `POSTGRES_PASSWORD`，并同步替换 `DATABASE_URL` 里的密码。确认没有保留 `change-this-long-random-password` 后启动：

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
docker compose -f docker-compose.prod.yml ps
curl http://127.0.0.1/health
```

不要在还有其它业务运行的服务器上执行 `docker system prune -a --volumes`。它会删除全服务器范围内不用的镜像和数据卷，容易误删其它项目。

## 8. 查看日志

```bash
docker compose -f docker-compose.prod.yml logs -f api
docker compose -f docker-compose.prod.yml logs -f web
docker compose -f docker-compose.prod.yml logs -f db
```

## 9. 本地发布到 GitHub

在本机项目目录完成修改后：

```powershell
cd D:\RR\royal-regent-nexus
git status --short
git add Dockerfile.backend Dockerfile.frontend docker-compose.prod.yml nginx.prod.conf .dockerignore .env.production.example backend\requirements.prod.txt docs\aliyun-docker-deploy.md deploy\update-from-github.sh deploy\reset-server-deploy.sh PROJECT_MEMORY.md
git commit -m "添加阿里云 Docker 部署配置"
git push origin 你的部署分支
```

服务器要拉取哪个分支，就在服务器部署目录 checkout 到哪个分支。正式生产一般建议固定拉 `main` 或一个专门的 `deploy/production` 分支。

## 10. 服务器拉取 GitHub 并更新容器

只有仓库管理员给服务器配置了 GitHub 读取权限后，才能使用这一节。私有仓库下，服务器本身也需要读取权限；只给你的个人账号 `Write` 权限，并不会自动让服务器能 `git pull`。

```bash
cd /opt/royal-regent/royal-regent-nexus
sh deploy/update-from-github.sh
```

如果部署目录不是 `/opt/royal-regent/royal-regent-nexus`，可以指定：

```bash
APP_DIR=/你的实际目录 sh deploy/update-from-github.sh
```

脚本采用数据保护和健康检查流程：

1. 确认生产工作区干净，并检查 DB、API、Web 都处于健康状态。
2. 仅接受到 `origin/main` 的快进更新；更新前创建 PostgreSQL custom-format 备份、校验和、恢复清单，以及不含环境变量值的容器元数据和配置键名清单。脚本不会再复制 `.env.production` 或归档完整 `docker inspect`。
3. 保持旧服务在线完成 API、Web 镜像构建，并保留带时间戳的 API/Web 回滚镜像。
4. 没有 Alembic 变更时，先启动继承正式 API 持久 volume 的健康候选容器，再依次替换 Web 和正式 API；Nginx 会动态解析 API 容器地址。
5. 检测到 Alembic 变更时自动改用维护窗口路径，避免新旧代码同时访问可能不兼容的数据库结构。
6. 默认在切换前发布 5 分钟全站倒计时，进入维护后暂停业务访问；每个服务替换后等待健康状态，验证 `/health`、静态首页、维护页和备份校验和后撤销维护。数据库容器和数据卷不会被重建。

可通过 `BACKUP_ROOT` 和 `HEALTH_TIMEOUT_SECONDS` 调整备份目录及健康检查等待时间。部署中途失败且 API 候选容器仍能服务时，脚本会保留该候选容器并输出清理命令，避免自动清理导致二次中断。

API 会输出不包含查询字符串的请求耗时记录，Nginx 访问日志包含 `request_time` 与 `upstream_time`。Compose 将单个容器日志限制为 `10 MB × 5`，防止诊断日志持续占用磁盘。

## 11. 数据备份

按你的 `.env.production` 里的用户名和库名执行，例如：

```bash
docker compose -f docker-compose.prod.yml exec db pg_dump -U rrnexus royal_regent_nexus > royal_regent_nexus_backup.sql
```

备份文件需要定期下载到服务器外部保存。

## 12. HTTPS

当前 compose 只配置 HTTP 80 端口。生产正式使用时应在公网入口接入 HTTPS，可以选择：

- 在 ECS 上用 Certbot 给 Nginx 配证书。
- 在前面加一层阿里云负载均衡或 CDN，由它终止 HTTPS。

未配置 HTTPS 前，不要把真实企业账号密码用于公网生产环境。

## 13. 全站停机倒计时与恢复公告

新版网站在所有应用页面显示维护公告，包含登录页。默认停机前 5 分钟弹窗提醒保存；收起后仍显示倒计时横幅。倒计时到零只显示等待更新，真正暂停业务由发布流程显式进入维护。页面在维护期间保留原有输入，恢复后由用户确认刷新，避免直接丢失未保存内容。公告每 10 秒检查一次，切回页面或恢复联网时立即检查。

公告不依赖业务 API 或数据库。Web 需要保留 `docker-compose.prod.yml` 中的只读挂载：主机 `.deployment-notice` 目录到 `/var/run/rrn-notice`。`DEPLOYMENT_NOTICE_DIR` 可指定主机目录，Compose 与公告命令必须指向同一目录。服务器只需 Python 3 标准库。Nginx 在维护期间对业务页面和 API 返回 503，状态公告、独立维护页面及健康检查继续提供；不要直接停止 Web，否则新访问者无法获取维护页。

`deploy/update-from-github.sh` 在完成构建后才发布公告，默认等待 `NOTICE_SECONDS=300` 秒；检查公告确实由当前 Web 提供，再开启维护并切换容器。开始前失败会撤销公告，切换后失败会保留维护状态，健康与备份检查通过后才公布恢复。生产使用服务器自有发布配置 `.deployment-prod-release.yml` 的流程，仍必须遵循其备份、迁移、worker 与单 API 约束，把以下步骤接入实际切换位置；不要用通用脚本替代已验证的发布方案。

手动发布流程的控制命令（在服务器项目目录执行）：

```bash
# 先完成备份、构建和发布前检查，再通知用户。
notice_id=$(python3 deploy/maintenance_notice.py start --seconds 300)
sleep 300
python3 deploy/maintenance_notice.py maintenance --id "$notice_id"

# 按原有发布方案切换，并验证 API、Web、worker 和静态资源。
# 确认已恢复后才撤销业务暂停，并给在线用户恢复提示。
python3 deploy/maintenance_notice.py complete --id "$notice_id"
```

开始切换前取消部署，可执行 `python3 deploy/maintenance_notice.py cancel --id "$notice_id"`；进入维护后不能用取消绕过恢复验证。故障时执行 `fail --id "$notice_id"` 会保留维护和暂停状态，完成原有恢复／回滚检查后再执行 `complete`。旧公告 ID 无权改动下一次发布，重复部署也不能覆盖正在进行的公告。公告只填写对用户公开的说明，不放凭据、服务器地址或诊断详情。

首次安装时旧 Web 和旧页面没有这项能力，需要先安装新版 Web 与公告目录挂载。通用脚本仅首次引导可显式使用 `MAINTENANCE_NOTICE_ENABLED=0`；它不会声称旧用户已收到提醒。此后恢复默认开启，用户加载过新版页面后才会收到未来的倒计时。外层代理／CDN 必须禁用 `/deployment-status.json` 缓存并透传 503，不应把维护页改写成业务请求成功。首次生产接入要验收两个不同账号、不同页面的同步提醒及失败恢复；本地测试不代表已在服务器启用。
