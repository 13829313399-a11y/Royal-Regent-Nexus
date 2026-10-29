# 3D 打印离线交付与后续现场执行

## 16 台生产切换与重编号边界

已确认目标清单为 16 台：旧 1～5 号保持编号，旧 6～11 号依次成为新 9～14 号；新设备使用 6、7、8、15、16 号。2 号的地址也有变化。实际地址、现场报告和凭据保留在仓库外的受控目录。

采集 API、Connector Worker、Bambu Adapter、分析与汇总、资源验证、现场 Windows 脚本和连接准备工具支持 1～16 号；完整站点拓扑与报告兼容旧 11 台及新 16 台。报告必须覆盖数据库设置与已初始化设备的完整机台清单。扩容后，旧 11 台报告不能继续显示全站健康，也不能通过幂等重试绕过检查。默认种子仍是原 11 台，避免应用重启自行改变现有业务设备。

**生产 16 台切换已验收。** 当前 16 台均保持 cloud-observer，记录开关开启，硬件控制关闭。当前屏幕码、证书、MQTT 登录及完整状态均已核对；两次持久采集快照间隔约 90 秒，16 台观察时间全部推进，第二次最大延迟 2.58 秒。生产登录、每日记录、机器状态及 16 号机详情已用真实浏览器验证，刷新后无控制台 warning/error；网页出现新 6、7、15 号自动记录。未发送暂停、恢复或打印命令，也未为本次恢复更改打印机模式、固件或重启现场网关。当前结果不等于长期无人值守验收。

业务以 **2026-10-29** 为新编号起点。此前日期记录保留原样；当天 7 条自动记录与 75,657 条遥测按稳定设备身份改号，业务 ID、金额与库存核对保持。`THREE_D_RECORD_NUMBERING_SINCE=2026-10-29` 限制同机号自动匹配、回填与结单，旧设备任务键不会变成新设备重复记录。当前机台运行统计与保养累计同样排除边界前的旧编号记录和遥测，可用率按实际有效统计窗口计算。前端“机台适配与保养”文案为 1～16。切换前有完整 PostgreSQL、资产及私有配置备份；隔离 PostgreSQL 恢复了全部业务表和当天遥测并成功演练，历史原始遥测包含在完整归档中，但未在演练库恢复。

当前 API 镜像为 `royal-regent-api:three-d-fleet16-20261029`，Connector 镜像为 `rr-three-d-connector:fleet16-20261029`。API 发布需沿用原 `.env.production`、`docker-compose.prod.yml`、`.deployment-prod-release.yml` 与 `.deployment-three-d-fleet16.yml`；Connector 使用原 `compose.yml` 与 `compose.fleet16.yml`。后续发布必须包含本次 16 台源码能力及日期边界，不能漏掉覆盖文件而退回旧限制。网络清单、健康脚本已同步到 16 台，定时器正常。证据见 `D:/RR/deliverables/three-d-fleet-16-readiness-20261028/fleet16-acceptance-20261029`，服务器受限备份在 `/opt/royal-regent/three-d/private/fleet16-20261029`。本地开发连接保持关闭，未迁移本地业务库。下方旧 11 台部署资料仅为历史基线。

本次停写切换曾造成约三分钟登录 HTTP 502，API 恢复后已实际登录成功。切换后已有新记录，回退必须先对账新增业务，不能直接用旧备份覆盖活跃库。

重编号必须保持物理设备的 `printer_id`、任务标识及 `credential_ref` 关联。凭据引用不是机台号：例如新 9 号继续使用原 6 号的引用。16 台现场 CSV 必须提供明确、唯一的 `credential_ref`；Windows 报告与 `tailscale_doctor.py` 保留该值，`prepare_connections.py` 拒绝覆盖既有设备的不同凭据引用。不要将新 CSV 直接套到旧机号数据库，也不要先按编号复制或改名密钥文件。

`network/collect-studio-devices.ps1` 可在现场当前 Windows 用户下定向读取 Bambu Studio 正式版/Beta 的已保存配置。默认只匹配新 6、7、8、15、16 号的 IP，兼容明文与 FNV-1a/MT19937 混淆的 `user_access_dev_ip`，按设备 SN 优先取 `user_access_code`，再取 `access_code`。缺失映射、凭据或存在冲突时报告未知，不按列表顺序猜设备，不提取账号 token、完整配置、日志或其他用户资料。非标准路径可显式传 `-ConfigPath`，不会递归扫描磁盘。

采集器兼容 Windows 版配置 JSON 后的标准 `# MD5 checksum` 行，仅去除格式匹配的末尾校验行，不忽略其他尾部内容，也不宣称验证过校验和。报告通过 `collector_version`、`read_stage`、`issue_code` 和映射计数区分文件不可读、解析失败、没有 IP 映射及目标未匹配；不包含可能泄露原始配置的异常文本。配置未成功解析时，不能把结果解释成“软件没有保存新机资料”。

默认只读当前配置和已存在的目标 TCP 连接。若现场配置没有 IP 映射，可显式加 `-DiscoverCertificates`：只向所选机台 IP 做有超时的 TLS 握手，先用 8883，失败时回退到 990，从证书 CN 取得候选 SN，再精确匹配本用户配置中的访问码。`-ProbeTimeoutMs` 默认为每阶段 3000 毫秒；`-CertificatePorts` 可显式指定最多两个端口。探测不发送应用数据、MQTT 登录、FTP 命令或访问码，不更改防火墙、LAN 模式或 Studio。CSV 可带 `observed_cert_sha256`，与此前现场观察不一致时拒绝导出该机；没有历史指纹的首次观察保留待核对状态。SN 大小写、缓存身份/密码冲突及同一 SN 对应多个目标 IP 都须严格检查。

报告不含 SN/访问码，仅包含处理阶段、各配置访问码条目数量、探测状态和证书指纹；匹配资料使用随包收件公钥加密落盘，解密私钥必须留在维护端仓库外的受限目录。返回 `collection-report.json` 和存在时的 `device-secrets.encrypted.json`，不需要原始 Studio 配置。证书名称、历史指纹匹配或缓存资料都不证明物理身份、密码有效性或 MQTT 登录成功。缺少可读证书或保存的访问码时仍需现场补齐，不会从网络获取密码。源码支持用隔离 Windows PowerShell 配置、混淆 IP 固定向量、真实本地 TLS 端点、冲突与解密回读验证；不能替代现场设备验证。

`network/extend-printer-routes.ps1` 用于在已登录的正确现场网关上补路由，默认 `Plan`；`Apply` 只合并所给 CSV 的私网 IPv4 `/32`，保留原有 IPv4/IPv6 路由，不更改登录、无人值守或防火墙设置。`-ExpectedGatewayIP` 必须与当前 Tailscale 身份一致，写入前再次检查原路由未变化，先保存 `route-change.json` 再执行并回读核对。显式 `Rollback -RestoreFile <该次报告>` 只移除该次新增且属于当前 CSV 的路由，保留后续新增的其他路由。发布路由不等于云端可达；按 [Tailscale Windows 配置说明](https://tailscale.com/docs/features/subnet-routers/how-to/setup?tab=windows) 核对管理台是否启用新增路由及访问规则，再从实际 Connector 网络验证。

执行顺序：

1. 现场按完整 CSV 运行 `windows-site.ps1 -Action Inspect`，逐台核对物理身份，取得新证书并补齐新机凭据。Inspect 只检测 TCP/TLS，不登录 MQTT。
2. 对目标库和受限配置备份，在恢复副本中生成重编号预览。生产记录、排期、维修、遥测、汇总及操作资源都可能按 `machine_no` 关联；必须核对历史编号展示口径、开放任务、旧 Edge 写入端以及按机号配置的控制白名单，不能只改设备表。本次按用户决定保留 2026-10-29 之前的编号，只修正当天自动记录及设备遥测，后续迁移须显式决定自己的业务边界。新设备不得继承旧编号的控制许可。
3. 在独立切换窗口对账后再应用编号、设备行和机台数量，更新地址、证书、网络清单及必要主机路由。控制权限保持关闭；新设备仅在身份、凭据和网络验证成功后启用观察。自动记账仍受每台独立开关约束。
4. 验收 16 台完整探测、新鲜遥测、机台卡片与历史归属，确认金额、库存、历史记录 ID 和业务总量保持。失败时停止本次新增采集并按同批备份恢复配置/数据；已有新记录时先对账，不能直接覆盖回旧库。

## 此前 11 台部署基线

云端应用和独立 Connector 已部署，Windows 现场网关已加入同一 Tailscale 网络，11 条打印机主机路由已生效。现场执行包位于本机 `D:/RR/3D现场配置包`。云端服务目录为 `/opt/royal-regent/three-d`；云端实测 11 台 TCP/TLS 均通过，证书与现场报告一致。1～11 号机均已启用 `cloud-observer` 只读接入，持续接收真实 MQTT 状态；本地开发连接仍禁用。旧程序及 Bambu Studio 可以继续运行，打印控制权未移交。

当前 Windows 接入使用 `network/windows-site.ps1`：Install 安装、Login 登录并启用无人值守、Routes 合并发布打印机主机路由、Inspect 读取网卡与 TCP/TLS 结果。Inspect 不登录 MQTT、不发送打印命令。`network/tailscale_doctor.py` 在云端检测真实 Tailscale 路由和设备 TLS，不要求 Windows 提供 Linux nftables 文件；缺少公网暴露证据保持 unknown，不冒充检查通过，也不再当作网络不通。明确 unsafe、实际探测失败或报告过期仍产生异常状态。

当现场 Studio 可访问设备但云端 TCP 超时时，Inspect 可加 `-IncludeGatewayDiagnostics`，在同一个报告中补充 Tailscale 非敏感偏好字段、逐台选路、目标邻居状态、IPv4 接口及防火墙概要。读取失败保留为 unavailable，不按 false 推断；接口 forwarding 状态只是证据，不能单独判定 Windows 用户态子网转发故障。报告使用明确字段白名单，不导出完整 prefs/netmap、私钥、账号凭据、MAC 地址或其他应用规则，也不修改网络设置。

当屏幕确认 IP 已变化时，可用 `network/rediscover-printer-addresses.ps1` 重新定位已知设备。它要求正确的现场 Tailscale 身份、唯一连接中的私网 `/24` 网卡及直接连接路由；绑定该源地址和网卡，最多四个并发，只对该网段的可用主机地址探测 TCP 8883/TLS。完整 SHA-256 证书指纹与仓库外清单精确匹配后才报告当前 IP，并保持原 `machine_no`/`credential_ref`；未知证书只计数，同一指纹出现在多个地址时标记 ambiguous，不按顺序、证书名称或旧 IP 猜身份。工具不读取访问码、不发送 MQTT 或打印命令、不修改路由/防火墙/设备设置。结果仍须审核后才能更新网络清单、批准路由及验证 MQTT；报告匹配完成不等于生产切换完成。

`prepare_connections.py --printers <CSV>` 幂等补齐禁用的设备连接，保留已有配置；`--network-config <JSON>` 用现场报告配置更新禁用设备的地址与证书，不转移设备所有权。`rr-three-d-network.timer` 每 30 秒进行不登录 MQTT 的网络检测并回传 API。Tailscale 探测超时为 10 秒以适应 DERP 中继，systemd 服务总超时为 75 秒；主机 Python 3.10 使用 `timezone.utc`。

`enable_observer.py --machine 2` 使用后端环境将单台已有连接启用为只读模式，重复执行不会重置会话。该模式保存状态与温度，不写生产记录也不处理库存，并把该连接的记录开关置为关闭；显式对账、控制命令创建/领取/下发也不会在该模式执行。旧 Edge 上报不会覆盖云端观测值。断线只使状态过期，不改变已有生产任务。只读接入不要求停止旧程序或修改现场防火墙；旧版单机断开工具不用于此流程。下方单机切换步骤用于真正移交生产控制权。

## 记录开关与设备控制相互独立

自动生产记录不再要求 `cloud-connector` 归属。连接上的 `record_reconcile_enabled` 单独决定该机台能否建记录与结算完成状态，而暂停/恢复等硬件控制仍然只允许 `cloud-connector`。迁移 `20260917_0117` 把已有连接置为开启，因此旧写入端已停止的现场无需再做一次移交就能恢复自动记录；`enable_observer.py` 切换观察模式时会把该开关显式关闭，需要记录时再单独开启。

```powershell
# 计划（默认只读，不改动任何数据）
backend/.venv/Scripts/python.exe deploy/three-d-printing/record_switch.py on
# 只开某一台
backend/.venv/Scripts/python.exe deploy/three-d-printing/record_switch.py on --machine 3 --execute
# 单台回退为不记录
backend/.venv/Scripts/python.exe deploy/three-d-printing/record_switch.py off --machine 3 --execute
```

`THREE_D_RECONCILE_SINCE` 是可选的上线护栏：设置后，只有该时刻之后观测到的运行才会建记录，避免开启开关时把此前只观测、未记录的历史一次性补进台账。默认不设（即不限制），应由开启方显式给出取值。记录结算需要的扫描间隔与静默窗口由 `THREE_D_RECONCILIATION_SWEEP_SECONDS`、`THREE_D_RECONCILIATION_TERMINAL_GRACE_SECONDS`、`THREE_D_RECONCILIATION_STALE_OPEN_SECONDS` 控制。

## 工具和默认行为

| 工具 | 默认行为 | 写操作门槛 |
|---|---|---|
| `recovery.py backup` | 生成新批次，校验数据库和所有资产 | 停止写入声明；目标必须不存在 |
| `recovery.py verify` | 只读校验哈希、资产清单和 SQLite 完整性 | 无 |
| `recovery.py restore` | 恢复到全新目录并校验 | 拒绝覆盖已有目录；不切换应用 |
| `cutover.py` | 生成单台打印机归属计划 | `--execute`、停写声明、操作者、原因、30分钟内校验通过的备份 |
| `retention.py` | 统计90天以前的原始遥测体 | `--execute`；每批最多500条；最短保留30天 |
| `network/windows-tailscale-plan.ps1` | 为完整 11/16 台清单生成逐机主机路由审核计划 | 不包含执行网络修改的入口 |

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
