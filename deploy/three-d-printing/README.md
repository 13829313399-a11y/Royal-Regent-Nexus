# 3D 打印离线交付与后续现场执行

本目录的脚本已用于隔离演练。当前不部署、不安装现场 VPN、不升级业务库、不停止旧系统。所有 `--execute`、Compose 启动和现场命令留到后续批准的维护窗口。

## 工具和默认行为

| 工具 | 默认行为 | 写操作门槛 |
|---|---|---|
| `recovery.py backup` | 生成新批次，校验数据库和所有资产 | 停止写入声明；目标必须不存在 |
| `recovery.py verify` | 只读校验哈希、资产清单和 SQLite 完整性 | 无 |
| `recovery.py restore` | 恢复到全新目录并校验 | 拒绝覆盖已有目录；不切换应用 |
| `cutover.py` | 生成单台打印机归属计划 | `--execute`、停写声明、操作者、原因、30分钟内校验通过的备份 |
| `retention.py` | 统计90天以前的原始遥测体 | `--execute`；每批最多500条；最短保留30天 |
| `network/windows-tailscale-plan.ps1` | 生成11条主机路由的审核计划 | 不包含执行网络修改的入口 |

原始遥测保留策略只清空过期 `raw_payload_json`。标准化状态、温度、错误、任务、命令、库存、文件和审计证据保留。执行前备份，按容量监控决定后续批次；本次未清理实际数据。

## 同批次备份与恢复

先停止所有业务写入端、连接器和图片/附件上传，记录操作者及冻结时间。SQLite 工具还持有写锁、使用在线备份 API，并对资产复制前后分别计算哈希。遇到文件变化或损坏，不生成可用 manifest。

```powershell
backend/.venv/Scripts/python.exe deploy/three-d-printing/recovery.py backup `
  --database D:/private/frozen/app.sqlite --assets D:/private/frozen/assets `
  --output D:/private/backups/batch-001 --writers-stopped
backend/.venv/Scripts/python.exe deploy/three-d-printing/recovery.py verify `
  --bundle D:/private/backups/batch-001
backend/.venv/Scripts/python.exe deploy/three-d-printing/recovery.py restore `
  --bundle D:/private/backups/batch-001 --output D:/private/rehearsal/restore-001
```

PostgreSQL 在同一个停写窗口使用 `pg_dump -Fc --no-owner --no-acl`；连接信息从受限 `PGSERVICEFILE`/`PGPASSFILE` 读取，不能把密码写在命令行或 Git。然后将归档和资产封装为同批次：

```sh
pg_dump --format=custom --no-owner --no-acl --file=/private/frozen/database.dump
python3 deploy/three-d-printing/recovery.py backup \
  --database /private/frozen/database.dump --assets /private/frozen/assets \
  --postgres --revision 20260904_0099 --pg-restore /usr/bin/pg_restore \
  --writers-stopped --output /private/backups/batch-001
python3 deploy/three-d-printing/recovery.py restore \
  --bundle /private/backups/batch-001 --output /private/rehearsal/restore-001
```

`restore` 对 PostgreSQL 只恢复并校验归档文件；还须在**新建隔离数据库**执行 `pg_restore --exit-on-error --no-owner --no-acl`，检查 Alembic 版本、表数量、业务汇总及资产后，才算数据库恢复成功。自动测试已实际完成这一步。不能把“归档哈希通过”当作数据库恢复通过。

数据库备份不包含现场 VPN 私钥和设备访问码。另用公司受控的加密凭据备份保存 VPN 配置、tailnet 路由/ACL、Connector token、Secret 引用映射、证书指纹及恢复授权记录；清单只登记引用和保管人。禁止将旧敏感 ZIP 或旧 PAT 放到服务器。

## Connector 容器与网络模式

现有 `docker-compose.prod.yml` 的 API 已挂载 `three-d-assets` 持久卷；版本附件也在同一资产根下的 `operations/`。备份应覆盖整个资产根。

`compose.connector.yml` 是独立 Compose 项目，使用 host 网络访问已建立的 VPN。设置私网 HTTPS API 地址、仓库外 token 文件和设备 Secret 目录；Secret 挂载只读，非 root 用户运行，移除全部 capabilities，日志轮转。默认 profile 不启动。

后续现场窗口的命令模板（本次未执行）：

```sh
docker compose -p rr-three-d -f deploy/three-d-printing/compose.connector.yml \
  --profile three-d-connector up -d --build --scale printer-connector=2
```

如使用 VPN sidecar，同一命令追加 `-f deploy/three-d-printing/compose.vpn-sidecar.yml`。镜像必须由运维审核并固定 digest；sidecar 配置按选用 VPN 镜像的入口要求提供，不能把示例当成现场已配置。不要将这两个文件直接并入另一目录的主 Compose 文件，避免相对路径按首个配置文件目录解析。

本机无 Docker CLI/daemon，未宣称镜像构建或容器上线通过。Node 真实进程、MQTT/TLS 模拟、API、PostgreSQL 并发及备份恢复已单独验证。

## Windows 现场网关

无需现场安装 Linux。先由维护人员安装官方 Tailscale 并登录公司管理的网络，再检查固定地址和设备身份。使用 `windows-tailscale-plan.ps1 -PrinterIPs <11个确认地址> -OutputPath <新文件>` 生成审核 JSON，不改变电脑设置。

计划仅发布11个 `/32` 打印机地址，不暴露整个办公网段。审核现有路由后，按 [Tailscale Windows 官方配置步骤](https://tailscale.com/docs/features/subnet-routers/how-to/setup?tab=windows) 发布路由，并在控制台批准路由。保留 Windows 防火墙；tailnet 访问规则只放行 Connector 身份到明确设备的 TCP 8883。无人值守运行、重启恢复、未授权身份拒绝和公网端口关闭都必须实际验证。不得对 Windows 套用 Linux 的 nftables/XFRM/SNAT 命令。

## 单机灰度及回退

1. 完成源快照、最终增量导入和对账；先在隔离副本升级至0099并验证。再次备份实际库和资产后才升级维护窗口内的目标库。
2. 核对11台固定地址、证书指纹、Secret 引用、VPN访问和新鲜网络健康报告。先选择一台没有开放任务或未完成命令的设备。
3. 现场关闭该设备旧写入端，核对物理 MQTT 会话确实断开，留存证据。租约不等同于物理隔离；不能仅凭“旧进程暂停”转移控制权。
4. 生成计划：`cutover.py --database-url-file <私有URL文件> --printer-id <ID> --owner cloud-connector --plan <新JSON>`。检查厂区、站点、连接版本、业务记录水位和备份批次。
5. 使用相同参数及 `--execute --writers-stopped --backup <批次目录> --actor <操作者> --reason <原因>` 应用单机归属。计划过期、记录水位变化、开放任务、未完成命令或健康证据不足都会阻断。脚本不启动服务、不发打印命令、不修改库存。
6. 再按现场授权逐项开启后端 Connector/控制开关和已验证机号，验证状态、暂停/恢复证据、双副本故障接管。通过后逐台重复；不得一次性跳过11台验证。
7. 需回退时停止云端该设备会话，确认没有未决命令/任务；保留并备份新产生的业务数据。生成 `--owner edge-legacy` 的新计划，重新审核并应用，再启动旧写入端。回退只改变所有者并使状态失效，不恢复旧数据库覆盖新增业务。
8. 若需恢复数据库，恢复到全新目录/数据库并先做数据差异与新增记录对账；完成业务确认后另行切换应用连接。禁止直接覆写活跃库，禁止删除迁移报告、源快照和切换审计。

完成现场验收后，记录设备/固件版本、操作者、时间、网络与主备故障证据、手机热点浏览器延迟、回退结果和旧 PAT 撤销凭证，再由负责人确认上线。
