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
4. 没有 Alembic 变更且 AI Pilot 未启用时，先启动继承正式 API 持久 volume 的健康候选容器，再依次替换 Web 和正式 API；Nginx 会动态解析 API 容器地址。
5. 检测到 Alembic 变更时自动改用维护窗口路径，避免新旧代码同时访问可能不兼容的数据库结构。
6. 每个服务替换后都等待健康状态，最后验证 `/health`、首页和备份校验和。数据库容器和数据卷不会被重建。

当 `AI_PILOT_ENABLED=true` 时，脚本会在 API 切换前通过共享 control volume 创建关闭标记。若 `AI_SHARED_GUARD_ENABLED=false`，仍使用单 API 维护窗口，禁止并行副本绕过进程内并发、分钟速率或日预算。若已经完成 ADR-007/NIF-09 配置并设置 `AI_SHARED_GUARD_ENABLED=true`，无迁移的发布可在关闭标记持续生效时启动健康候选 API；候选与正式 API 通过 PostgreSQL Guard 共用并发、RPM、日预算和禁用状态。存在 Alembic 变更时始终使用维护窗口。健康检查通过后仍保留标记，必须由运维完成 13.2/NIF-18 两阶段检查后再单独决定是否移除；部署失败或原本已经存在的标记同样保持 AI 关闭。

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

对 Nexus AI Pilot，HTTPS 不是建议项而是硬门：必须验证浏览器到公网入口全程使用 HTTPS、HTTP 永久跳转到同一 HTTPS Origin，并返回至少一年 `max-age` 的 HSTS。只把 Provider 请求发往 HTTPS，不能弥补浏览器到 Nexus 仍走 HTTP 的问题。

## 13. Nexus AI Pilot 安全启用与紧急关闭

### 13.1 启用前配置

首次部署包含 B8 的代码和 Compose 时，先保持 `AI_ENABLED=false`、`AI_PILOT_ENABLED=false`，按第 10 节完成一次正常更新，让新的只读 control volume 先就位。然后完成外层 ALB/CDN TLS 或 Nginx 443，并按 13.3 的命令先创建关闭标记。只有标记已确认存在，才在真实、未跟踪的 `.env.production` 中填写 Pilot 控制项并重建 API。这样配置切换和就绪检查期间不会提前开放 Provider 或 Tool。未启用 Shared Guard 的 Pilot 使用单 API 维护窗口；启用并现场验证 Shared Guard 后，可使用第 10 节描述的关闭标记保护候选路径。不要把 API Key、Workspace Host、用户清单或真实环境文件提交到仓库：

```dotenv
AI_ENABLED=true
AI_PILOT_ENABLED=true
AI_PILOT_USER_IDS=明确批准的用户ID，多个用英文逗号分隔，去重后最多128个
AI_PILOT_FACTORY_IDS=明确批准的厂区ID，多个用英文逗号分隔
AI_PILOT_PUBLIC_TLS_VERIFIED=true
AI_RUNTIME_DISABLE_PATH=/app/backend/control/ai.disabled
AI_PILOT_MAX_CONCURRENT_PER_USER=1
AI_PILOT_REQUESTS_PER_MINUTE=10
AI_PILOT_DAILY_TOKEN_BUDGET=20000000
AI_PILOT_MAX_OUTPUT_TOKENS=4096
AI_LOG_RAW_PROMPTS=false
AI_LOG_RAW_TOOL_RESULTS=false
```

确认关闭标记存在后，再切换配置并执行：

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production \
  up -d --no-deps api
docker compose -f docker-compose.prod.yml --env-file .env.production \
  ps api
```

`AI_PILOT_PUBLIC_TLS_VERIFIED=true` 是完成外部 TLS/HSTS 实测后的运维声明，不能用它代替实测。Pilot Provider 固定为 Qwen、`cn-beijing`、`qwen3.7-plus` 和 Workspace 推导的官方 HTTPS Host；生产禁止自定义 `AI_BASE_URL`。应使用新轮换且只存在于服务器 Secret 边界中的 Key。

`AI_PILOT_DAILY_TOKEN_BUDGET` 同时承担并发请求的保守 admission reservation：文字 Tool 请求会按最大轮次、每轮最多 8 个 Tool 结果及重复回放上限预留，Vision 会按原始图片字节上限预留。成功且 Provider 返回 usage 后只按真实累计 Token 对账；usage 缺失、取消或异常中断则按保守预留计费。因此不能把日预算随意改成低于单次最大预留的小数值；就绪脚本会根据同一组限制计算并拒绝不可用配置。

第一次 Pilot 建议保持 `AI_CLOUD_VISION_ENABLED=false`，先验收纯文字和只读 Tool。只有图片流程也已完成外部 TLS、逐次同意和故障演练后才单独开启 Vision。

### 13.2 自动就绪检查

API/Web 部署完成且关闭标记仍存在时，从生产目录执行第一阶段检查：

```bash
cd /opt/royal-regent/royal-regent-nexus
AI_PUBLIC_ORIGIN=https://你的正式域名 \
  sh deploy/verify-ai-pilot-readiness.sh
```

默认 `AI_PILOT_EXPECT_DISABLED_MARKER=true`，因此第一阶段会要求关闭标记保持存在。检查通过后才移除标记，并立即执行第二阶段检查：

```bash
API_ID="$(docker compose -f docker-compose.prod.yml \
  --env-file .env.production ps -q api)"
AI_CONTROL_VOLUME="$(docker inspect --format \
  '{{range .Mounts}}{{if eq .Destination "/app/backend/control"}}{{.Name}}{{end}}{{end}}' \
  "$API_ID")"
test -n "$AI_CONTROL_VOLUME"
docker run --rm --network none -v "$AI_CONTROL_VOLUME:/control" \
  postgres:16-alpine rm -f /control/ai.disabled
AI_PILOT_EXPECT_DISABLED_MARKER=false \
AI_PUBLIC_ORIGIN=https://你的正式域名 \
  sh deploy/verify-ai-pilot-readiness.sh
```

该脚本不会调用模型或上传业务数据。它只验证：

- HTTPS 健康检查、同 Origin 的 HTTP→HTTPS 永久跳转和 HSTS；
- 匿名访问 AI capabilities 必须返回 `401`；
- Pilot 用户/厂区、并发、速率、预算、只读日志和 Provider 控制项已安全设置；
- runtime control volume 在 API 中只读挂载，且关闭标记符合本阶段预期状态。

脚本通过后，还必须由一个批准的 Pilot 账号在浏览器完成现场验收：登录响应的 `rr_session` Cookie 具有 `Secure`、`HttpOnly` 和 `SameSite=Lax`；非 Pilot 账号看不到入口并得到 `403`；Pilot 账号只能读取已授权厂区；停止生成、429、Provider 故障和 Tool 故障都不影响正式业务页面。不要把 Cookie 或凭据粘贴进命令、日志或验收文档。

### 13.3 不重启 API 的紧急关闭

`ai-control` 是独立持久化 volume，并以只读方式挂载到 API。创建空标记文件即可阻止后续 Provider/Tool 调用；正在进行的流会在下一个模型事件或工具执行边界安全终止。

先从当前 API 容器取得它实际挂载的 control volume 名：

```bash
API_ID="$(docker compose -f docker-compose.prod.yml \
  --env-file .env.production ps -q api)"
AI_CONTROL_VOLUME="$(docker inspect --format \
  '{{range .Mounts}}{{if eq .Destination "/app/backend/control"}}{{.Name}}{{end}}{{end}}' \
  "$API_ID")"
test -n "$AI_CONTROL_VOLUME"
```

紧急关闭：

```bash
docker run --rm --network none -v "$AI_CONTROL_VOLUME:/control" \
  postgres:16-alpine touch /control/ai.disabled
```

确认标记存在且刷新浏览器后 AI 入口消失：

```bash
docker run --rm --network none -v "$AI_CONTROL_VOLUME:/control:ro" \
  postgres:16-alpine test -f /control/ai.disabled
```

重新启用前必须先排除故障，并在标记保持存在时重新完成第一阶段就绪检查。通过后移除标记，再执行第二阶段检查：

```bash
AI_PUBLIC_ORIGIN=https://你的正式域名 \
  sh deploy/verify-ai-pilot-readiness.sh
docker run --rm --network none -v "$AI_CONTROL_VOLUME:/control" \
  postgres:16-alpine rm -f /control/ai.disabled
AI_PILOT_EXPECT_DISABLED_MARKER=false \
AI_PUBLIC_ORIGIN=https://你的正式域名 \
  sh deploy/verify-ai-pilot-readiness.sh
```

### 13.4 旧备份 Secret 审计

旧版部署脚本曾把 `.env.production` 和完整容器 inspect 复制到备份目录。新版只保存变量键名、环境文件校验摘要和 allowlisted 容器元数据。升级后应在服务器上审计历史备份中是否存在 `environment.snapshot` 或 `container-inspect*.json`，限制备份目录访问，并轮换可能出现过的数据库密码、签名 Key、边缘 Token 和 Provider Key。未经明确确认不要自动删除数据库备份或回滚镜像。
