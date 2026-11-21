# 阿里云 ECS 发布与恢复

## 更新已有生产环境

在服务器上找到**正在运行的 Compose 项目及最近一次有效发布回执**。从该项目的部署目录读取完整 Compose 文件顺序、环境文件、项目名、服务清单、固定镜像和挂载。基础文件是 `docker-compose.prod.yml`，服务器维护 `.deployment-prod-release.yml` 及后续按版本叠加的文件。检查时只记录文件名、镜像标识和校验结果，私有配置留在发布环境。仓库的通用更新脚本默认只传一个 Compose 文件，不能据此重建已有现网。 [基础服务定义](../docker-compose.prod.yml) · [通用脚本的默认参数](../deploy/update-from-github.sh)

1. **确认目标。** 核对现网 Git SHA、实际镜像、数据库 revision、服务健康与空间，锁定获准发布的目标 SHA。读取最近的服务器发布目录 `/opt/royal-regent/builds/<release>`、受限备份目录 `/opt/royal-regent/backups/<release>` 及当前生效清单。检查是否涉及迁移、IAM 开关、QC 私有库、文档作业、OnlyOffice 或 3D 连接器，根据实际变更确定停写范围。
2. **准备候选和回退。** 使用原部署组合生成固定镜像，保留旧镜像和组合。校验数据库和私有资产恢复材料，对目标迁移在隔离恢复副本上演练。`alembic -c alembic.ini heads` 在 `backend/` 中查看所选源码的迁移图末端。旧库身份处理见[助手迁移说明](assistant/MIGRATION_IDENTITY.md)和[纸箱迁移说明](business/carton-migration-identity.md)。
3. **公告、停写、冻结。** 构建和预检完成后进入既有公告流程。保存在线编辑，检查后台任务，进入维护并停下相关写入服务。对同一冻结点的 PostgreSQL、QC 私有库、文档及其他已挂载资产、私有运行配置创建可恢复备份并校验。保留原有卷、网络和连接器身份。
4. **安装并核验。** 按该版本发布方案实施迁移和切换。API 镜像调用 `qc_dossier_release.py start`。开启 QC dossier 时须已有对应准备标记、版本和结构，关闭时启动分支会执行 Alembic 升级。按当前现网组合保持单个正式 API，确认文档 worker 心跳、QC 服务及卷、Web 到 API 的 `/health`、实际 JS/CSS 资源、相应业务读接口和本次数据/权限对账后开放。 [容器入口](../Dockerfile.backend) · [QC 启动与准备](../backend/scripts/qc_dossier_release.py)
5. **开流或恢复。** 将 SHA、镜像、数据库 revision、配置清单、备份位置和复核结果写入发布回执。维护窗内失败时保留维护状态，按同一发布的回退清单恢复兼容镜像与原配置。开流后已有新业务写入时，先核对增量及兼容性，再决定回退或前向修复。数据恢复须有单独的恢复范围和核对依据。

`f504fb52` 的 IAM 发布可作为回执示例。2026-11-19 UTC 的记录使用 23 份 Compose 文件和两份环境文件，追加版本覆盖以固定 API、文档 worker、QC 和 Web 镜像，当次生产数据库为 `20261116_0195`。服务器批次为 `main-iam-f504fb521972`。下一次发布以届时实际运行组合为准。打印机和办公服务另有自己的网络、卷和运行身份。 [3D 交接与回退](../deploy/three-d-printing/README.md) · [在线文档](document-tools/online-documents.md)

### IAM 前端包验收与回退

生产前端构建须将 `VITE_IAM_IDENTITY_UI_ENABLED`、`VITE_POSITION_WORKBENCH_ENABLED`、`VITE_IAM_CONSOLIDATED_UI_ENABLED` 和 `VITE_IAM_STUDIO_ENABLED` 全部设为 `true`。在实际生效的 Compose 文件、环境文件和 CI 构建参数中核对这四项。Vite 在编译时选择界面，给已构建容器设置环境变量不能修复错误的包。后端开关按本次业务授权维护。

生产 Dockerfile 使用 BuildKit 只读检查最终静态目录，并把回执与启动检查装入 Nginx 镜像。标准镜像从第一次启动起就会复验成品。服务器若接收独立构建的压缩包，在切换前用宿主 Python 3.9+ 验证待发文件。脚本从 index.html 找到实际入口，核对四个管理菜单、人员和审计的路由导入、权限方案库的展示与查询分支、员工自助的全页模式，再核对相关组件文件。HTTP 模式只访问公开页面和脚本。 [验收工具](../deploy/check_iam_frontend.py)

```sh
# 按实际批次提供 ARCHIVE、WEB_ID 和最终站点 ORIGIN（含 http 或 https）。
guard=/opt/royal-regent/iam-web-release
python3 "$guard/check_iam_frontend.py" --archive "$ARCHIVE" --approve-dir "$guard/approved" > iam-candidate.txt
# 已构建的镜像也可用 --image "$IMAGE" 验收；检查过程中不会启动候选容器。
# Web 切换后、维护解除前，检查实际安装的六个文件。
python3 "$guard/check_iam_frontend.py" --container "$WEB_ID" > iam-installed.txt
cmp iam-candidate.txt iam-installed.txt
# 恢复访问后，从实际站点检查人员、办理大厅、方案库、审计和员工自助入口。
python3 "$guard/check_iam_frontend.py" --url "$ORIGIN" > iam-served.txt
cmp iam-candidate.txt iam-served.txt
```

将这些命令纳入遇错即停的发布脚本。宿主可用 `install -m 0755 deploy/99-verify-iam-web.sh "$guard/99-verify-iam-web.sh"` 和 `install -m 0644 deploy/check_iam_frontend.py "$guard/check_iam_frontend.py"` 安装门禁。创建该目录并限制为部署账号写入。在实际生效的 Web 服务中保留下列只读挂载及官方 Nginx entrypoint。候选通过审核后，工具按 index.html 的 SHA-256 原子生成一份六文件回执。同一入口摘要重复批准须与先前已签发的全部文件摘要一致。每次容器启动都会按回执校验。 [Nginx 启动检查](../deploy/99-verify-iam-web.sh)

```yaml
services:
  web:
    volumes:
      - /opt/royal-regent/iam-web-release/99-verify-iam-web.sh:/docker-entrypoint.d/99-verify-iam-web.sh:ro
      - /opt/royal-regent/iam-web-release/approved:/run/rrn-iam-approved:ro
```

回退前保存本次已批准镜像、完整 Compose 组合及对应回执。在维护期复验拟回退的既有 Studio 镜像，核对指定镜像与回执后只切换 Web，再执行容器与站点检查。需要恢复历史兼容界面时，先取得该界面变更的明确授权，另行评审对应发布合同。不要通过删除挂载或手填摘要放行旧包。此流程不涉及数据库、授权来源或服务端写开关。

## 首次安装独立的新实例

以下基础配置用于没有既有数据卷和服务器覆盖配置的新实例。

### ECS 和网络

在 ECS 安全组入方向放行：

- `22/tcp`：SSH 登录。
- `80/tcp`：HTTP 访问。
- `443/tcp`：后续配置 HTTPS 时使用。

服务器建议使用 Ubuntu 22.04/24.04 或 Alibaba Cloud Linux 3。下面命令以 Ubuntu 为例。

### Docker

```bash
sudo apt update
sudo apt install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
docker --version
docker compose version
```

如果执行了 `usermod`，重新登录 SSH 后再继续。

### 获取代码

为新实例选择已批准的源码版本。服务器通过授权的只读凭据获取私有仓库。

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

### 配置新环境

```bash
cp .env.production.example .env.production
nano .env.production
```

必须修改 `POSTGRES_PASSWORD`，并同步修改 `DATABASE_URL` 里的密码。密码里如果包含 `@`、`:`、`/` 等 URL 特殊字符，需要做 URL 编码。环境文件仅限部署账号读取。

### 首次启动与检查

在部署目录准备好 `.env.production`、对应数据库、持久卷及确实需要的子服务后运行。镜像初始化可能执行迁移。需要 QC dossier 的新实例先按该功能的准备流程处理。 [QC 包装说明](business/qc-complete-records.md)

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
docker compose --env-file .env.production -f docker-compose.prod.yml ps
curl -f http://127.0.0.1/health
```

首个受管域名在公网入口配置 HTTPS。检查页面、静态脚本、API 代理和 worker 心跳。按实例启用的功能，用自建文档完成提交、处理、下载和重新打开。容器日志按 `10 MB × 5` 轮转。API 和 Nginx 耗时字段可帮助区分服务处理和下游传输。

## 单一基础 Compose 的维护

只使用基础 Compose 的独立环境可以参考 `deploy/update-from-github.sh`。脚本校验工作区和健康状态，只接受快进，保存数据库备份与校验和，按迁移变更选择切换路径。`APP_DIR`、`BACKUP_ROOT`、`HEALTH_TIMEOUT_SECONDS` 和 `NOTICE_SECONDS` 由该实例维护。保留异地备份与恢复验证记录。 [脚本及参数](../deploy/update-from-github.sh)

## 退役后重建空环境

仅当目标容器、卷和旧部署目录已明确获准弃置，且所需备份已可恢复时，才使用重置工具。此脚本会删除目标 Compose 数据卷（含 PostgreSQL）、旧部署目录并重新克隆。先核实目标目录、Compose 项目和保留的数据，按脚本的确认参数单独执行。 [重置工具](../deploy/reset-server-deploy.sh)

## 维护公告和恢复

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
