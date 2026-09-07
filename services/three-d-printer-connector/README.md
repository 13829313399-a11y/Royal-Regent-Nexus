# 云端打印机连接器：PR-06

PR-06 的代码与本地集成链路已实现：独立常驻服务、按打印机分配所有权、MQTT/TLS 协议适配、状态事件、任务对账、租约命令及 PostgreSQL NOTIFY → SSE → 页面更新。旧 Windows Agent 保留；只有配置明确移交给 `cloud-connector` 的设备进入新链路。导入模块不会连接设备，显式启动服务后才发现并连接已授权机台。

现场 Windows 无需运行本服务。云端 Connector 通过站点 VPN 主动访问打印机，现场候选 Windows 网关负责网络转发。真实 VPN、设备身份/证书、固件控制能力和独占灰度仍属于现场验收，当前没有修改现场网络或生产数据。

## 启动

使用 Node.js 22+，服务没有生产 npm 依赖。设置 `connector.env.example` 中三个环境变量后，在仓库根目录执行：

```sh
node services/three-d-printer-connector/src/main.mjs
```

也可在本目录执行 `npm start`。提供独立 Dockerfile，构建上下文为本目录；镜像使用非 root 用户，设备秘密和服务令牌通过只读挂载提供，不复制进镜像。Docker 构建及正式 Compose/网关部署留待 PR-08 环境演练；本地已执行真实 Node 进程集成测试。

- `THREE_D_API_URL`：API 根地址。远程必须 HTTPS，只有 loopback 允许 HTTP。禁止凭据 URL 与重定向。
- `THREE_D_CONNECTOR_TOKEN_FILE`：独立服务令牌文件，32～512 个可打印 ASCII 字符，不能复用用户/Edge/网络采集令牌。
- `THREE_D_SECRET_DIR`：按 `printer-01.json` 至 `printer-11.json` 引用读取的秘密目录；文件仅含 `serial`、`access_code`。只在证书指纹核验成功之后读取并发送设备凭据。Linux 文件不得向组或其他用户开放，Windows ACL 需部署时单独核验。

API 进程配置：`THREE_D_CONNECTOR_ENABLED=true`、`THREE_D_CONNECTOR_TOKEN` 与令牌文件一致。`THREE_D_CONNECTOR_CONTROL_ENABLED` 默认 false；`THREE_D_CONNECTOR_VERIFIED_MACHINES` 默认 `[]`，只填写已完成固件控制验收的机号 JSON 数组。缺任一条件都不允许控制。站点网络报告必须 healthy，连接表必须显式启用并设置 `connection_owner=cloud-connector`、私网 IP、8883、凭据引用及已核对的证书 SHA256 指纹。服务不会自动移交设备。

每次启动自动生成新的实例 ID。SIGINT/SIGTERM 先停止 MQTT、停止重连，再释放租约。日志仅含固定诊断码与机台 ID，API 响应正文、网络地址、设备凭据不输出到日志。

## 所有权与有序事件

每台打印机只有一个数据库 leader lease，期限30秒；worker 以单调时钟和请求开始时间计算本地截止时间，至少提前3秒停止操作。API 失联、租约过期或连接配置版本变化会关闭对应会话；单台连接错误不会停止其余机台。全局 API 失联会关闭全部本地连接。设备协议有独立连接/鉴权超时、指数退避及抖动。

每次 MQTT 重连生成新 session，先登记递增代数，再依序提交状态。每机最多排队256个事件；队列溢出停止该连接，避免无限内存增长。状态事件同 ID/同内容重试幂等，旧租约、旧 session、倒退序号/时间被拒绝。设备时间不会因快照读取而变新。retained 消息不能作为在线或命令成功证据，未知固件状态使控制降级。新 job ID 不继承上一任务的 FINISH/进度。

SQLite 提前获取写锁；PostgreSQL 使用打印机行锁。涉及任务/库存的事务先按工厂设置行串行，保持与人工库存操作一致的锁顺序。状态、运行记录、库存流水和审计在同一事务提交。复用0098表；修正 ORM 自引用库存外键的 PostgreSQL 建表顺序，不改变现有数据库数据结构，不需新迁移。

租约防止应用侧重复下发，但无法凭软件定时器证明操作系统长期暂停时旧 TCP 会话已在打印机端关闭。生产接管必须验证设备固件会话行为，并先结束旧 Edge 会话；不能未经验证允许旧系统与云端同时订阅。

## 任务转换与对账

稳定任务键以内部打印机 ID 和设备真实 subtask ID 做 SHA256，避免不同打印机的同名 ID 冲突。同一键只创建一条记录；首次 RUNNING 才创建记录、冻结成本并按既有库存规则扣料，事件重试和重连不重复扣料。

RUNNING/PAUSE 分别映射运行/暂停；同一任务明确 FINISH 或 FAILED/ERROR 才结束。断线、网络失效、空闲但缺完成证据，都保留开放记录并进入待对账。心跳扫描还会标记超时设备及其开放任务，恢复后由新鲜同一 job 证据继续对账。删除和已结束任务不会被重放事件复活。

产品仅在规范化文件名精确匹配且候选唯一时自动绑定，保存匹配方式、置信度和候选 ID；重复名/无匹配进入待匹配记录，不猜测重量或扣料。设备没有可靠任务 ID 时只保留诊断审计，不凭文件名新建财务记录。无法证明身份的历史开放任务保留人工待确认；不盲目与新设备任务绑定。库存不足保留待对账标记，不截断扣料或默认透支。

## 命令与回执

命令通过既有用户权限保护的 REST 接口创建。它绑定创建时的 session、job key 和 control epoch；设备状态循环回原值也不能使旧意图复活。PostgreSQL 实际执行 `FOR UPDATE SKIP LOCKED`，命令领取期限8秒，未发送最多领取3次。

worker 必须先取得持久化的唯一发送许可，再调用适配器。许可响应丢失时不猜测、不重新发送。状态事件先入库，再用 dispatch 之后、同一会话/任务的目标状态作为成功回执。已可能发送但没有结果证据的命令变成 unknown，不自动重发；旧租约回执和覆盖既有结果被拒绝。

## 内部接口

前缀 `/api/internal/three-d-connector`，均为 POST，固定华康 A / 河源，独立令牌头 `X-Three-D-Connector-Token`。浏览器不持有此令牌。

| 路径 | 用途 |
| --- | --- |
| `/heartbeat`、`/printers` | 注册进程、扫描过期设备、发现已移交机台 |
| `/leases/acquire`、`renew`、`release` | 申请、续租、释放设备所有权 |
| `/sessions/start`、`/events` | 登记会话与提交有序状态 |
| `/reconcile` | 用当前最新持久化证据幂等对账；过期证据不能结算 |
| `/commands/claim`、`dispatch`、`ack` | 领取、一次发送许可、结果确认 |

## 实时页面

`GET /api/three-d-printing/live/events?factory_id=huakang-a` 使用用户会话 Cookie 和现有模块读取权限。每次推送重新核验权限，退出登录/撤销权限后终止流。快照只含公开机台状态、网络摘要、近期命令及任务版本，不含设备连接配置与凭据。

每个 API 进程独立 LISTEN PostgreSQL 的 `three_d_printing_events`，事务提交后唤醒本进程 SSE；断开后自动重连。订阅者使用容量1的合并队列，慢客户端不会无限积压。每5秒从数据库校验一次，通知丢失或 SQLite 环境都能恢复。`Last-Event-ID` 标识完整快照版本；重连发送完整 reset/snapshot，而不是把易丢失的通知当成审计历史。状态历史与审计仍在数据库。

页面直接更新机台卡片，并按任务版本刷新台账；SSE 错误或超过15秒无心跳显示定时刷新状态，保留8秒轮询回退。正常用户只连接云端网页，无需安装 VPN。

## 本地验收

```sh
node --test services/three-d-printer-connector/test/*.test.mjs
node node_modules/typescript/bin/tsc -p services/three-d-printer-connector/tsconfig.json
python -m pytest backend/tests/test_three_d_connector.py backend/tests/test_three_d_run_reconciliation.py backend/tests/test_three_d_connector_runtime.py -q
```

真实 PostgreSQL 测试使用 `THREE_D_TEST_POSTGRES_URL=postgresql+psycopg://127.0.0.1:PORT/pr06_test`，本机测试账号通过 PostgreSQL 环境变量提供；仅允许 loopback 和专用 `pr06_test` 数据库，每次创建/清理随机测试 schema：

```sh
python -m pytest backend/tests/test_three_d_connector_postgres.py -q
```

集成测试在本机隔离 API、SQLite 与11台真实 TLS/MQTT 模拟器上运行两个 Node worker，覆盖单会话竞争、唯一暂停指令、SSE、退出接管、逻辑时钟推进30分钟断网及恢复、完成/失败和无重复任务。30分钟是逻辑时间模拟，不声称完成真实 VPN 30分钟断网实验。PostgreSQL 覆盖实际行锁/SKIP LOCKED、唯一发送许可、通知提交/回滚和订阅 fan-out。前端另有实时连接/静默中断/回退/卸载测试。

现场 VPN、11台身份/证书、Windows 转发/ACL、设备真实会话交接、完整班次灰度与生产部署尚未验收。它们不再阻塞 PR-06 代码开发，但仍是正式切换的前置条件。
