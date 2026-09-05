# PR-06 本地代码验收

范围：常驻 Connector、事件与命令、运行任务对账、PostgreSQL 通知和 SSE。代码留在工作区；本次没有提交、推送、合并 Git PR，也没有生产部署或现场网络变更。

## 交付对应

| 蓝图交付 | 实现 |
| --- | --- |
| BambuAdapter / Secret Store | 独立协议、固定证书 pin、按引用延迟读取设备凭据、固件控制 allowlist |
| 独立服务 | Node 启动入口、进程心跳、机台发现、信号退出、Dockerfile/环境变量模板 |
| per-printer leader | 数据库所有权与本地保守截止时间，失效关闭连接 |
| 事件与对账 | 会话代数、序号/时间校验、事务内投影、首次运行扣料、恢复不重复任务 |
| 命令 | SKIP LOCKED、有限领取、一次发送许可、事件证据回执、未知发送不重放 |
| 实时推送 | PostgreSQL LISTEN/NOTIFY、SSE 有界快照、重连 reset、权限撤销、轮询回退 |

## 已执行验证

- 36 项相关后端测试通过：连接器11项、任务对账/SSE4项、独立进程集成1项、实际 PostgreSQL 2项、既有接口/网络/台账18项。
- 20 项 Node 协议与 worker 测试通过。
- 7 项前端实时连接及原台账组件测试通过。
- Vue 类型检查、Connector checkJs、Vite 构建、作用范围内 Ruff 和差异空白检查通过。
- 生产源码、运行配置模板与说明文件的定向凭据检查通过；不等同于全仓库安全审计。

独立进程验收使用两个不同 PID 的 Node worker、同一个隔离 FastAPI/SQLite 和11台本机 TLS/MQTT 模拟器：竞争期间各机单会话、只执行一次暂停、HTTP SSE可读、退出后接管、逻辑30分钟断网及恢复、同一任务只留一条记录，最后10台完成、1台失败。测试不访问现场 IP；逻辑30分钟不代表真实 VPN 断网30分钟。

实际 PostgreSQL 验收使用仓库外临时 PostgreSQL 16 实例，仅监听 loopback。按测试随机 schema 验证真实锁竞争、被锁命令跳过、只授予一次发送许可、回滚不发通知、提交后多订阅者收到通知。测试完成后停止专用实例；未连接或迁移业务数据库。

主要命令见 [连接器说明](../services/three-d-printer-connector/README.md)。后端测试文件为 `test_three_d_connector.py`、`test_three_d_run_reconciliation.py`、`test_three_d_connector_runtime.py`、`test_three_d_connector_postgres.py`、`test_three_d_network_health.py`、`test_three_d_printing_api.py`、`test_three_d_ledger_snapshots.py`。

## 正式切换前

PR-06 代码链路已完成；真实 VPN、Windows 转发/ACL、逐台设备身份/证书/固件验证、旧 Edge 独占移交和完整班次灰度仍需现场条件。Docker 镜像构建及正式部署演练留在 PR-08。不能以本地测试代替现场验收，也不能保证操作系统冻结时仅靠租约定时器关闭远端旧 TCP 会话。

身份不明确的历史开放任务继续人工待确认；缺少可靠设备 job ID 不按文件名强行创建财务记录。现有用户接口与本地 Edge 保留，只有显式移交的打印机走云端主链路，所有控制开关默认关闭。
