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

脚本内部执行的是：

```bash
git fetch --prune
git pull --ff-only
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
docker compose -f docker-compose.prod.yml ps
docker image prune -f
```

## 11. 数据备份

按你的 `.env.production` 里的用户名和库名执行，例如：

```bash
docker compose -f docker-compose.prod.yml exec db pg_dump -U rrnexus royal_regent_nexus > royal_regent_nexus_backup.sql
```

备份文件需要定期下载到服务器外部保存。

## 12. HTTPS

当前 compose 只配置 HTTP 80 端口。生产正式使用时建议再接 HTTPS，可以选择：

- 在 ECS 上用 Certbot 给 Nginx 配证书。
- 在前面加一层阿里云负载均衡或 CDN，由它终止 HTTPS。

未配置 HTTPS 前，不要把真实企业账号密码用于公网生产环境。
