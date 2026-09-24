# 验证记录 · 2026-09-23

新域数据均为合成，范围限隔离 SQLite、PostgreSQL 和临时代理队列。没有向真实业务库播种订单、产量、工资或权限。

## 自动化命令和结果

| 检查 | 实测 |
|---|---|
| `npm run build` | 通过；既有第三方 PURE 标注/大 chunk 提示，非 UV 类型错误 |
| `npm run typecheck:test` | 通过 |
| `npm run test:unit -- src/features/uv-operations/__tests__ src/stores/__tests__/authScopedPermissions.spec.ts src/router/__tests__/authenticatedFactoryContext.spec.ts` | 5 文件、71 项通过 |
| 上述前端范围及 `moduleCenterFactoryScope`、`productionModuleEntry`、`customerPriceCustomerScope`、`CustomerPricingSettingsPanel` | 合入主线后9文件、110项通过、1项既有跳过；覆盖UV卡片授权、跨厂隐藏及撤权；构建和测试类型检查再次通过 |
| `pytest tests/test_uv_ops.py tests/test_uv_ops_edges.py tests/test_uv_ops_acceptance.py tests/test_uv_ops_workflows.py -q` | 74 项通过，112.15 秒，包含 SQLite 与 PostgreSQL |
| `pytest tests/test_system_position_catalog.py tests/test_retired_workspace_permissions.py tests/test_auth_api.py tests/test_iam_api.py -q` | 首轮87通过/2旧期望失败；修正新增18权限的计数、read分类及固定岗位排除后，失败两项定向重跑通过；最终89项均有通过证据 |
| `edge/uv-printing-agent/.venv/Scripts/python.exe -m pytest edge/uv-printing-agent/tests -q` | 12 项通过，0.34秒 |

后端命令在 backend 执行，DATABASE_URL=sqlite://，UV_OPS_TEST_POSTGRES_URL 显式指向 loopback:55439/uv_ops_test。每个测试建立自己的随机 schema。未配置 PG 时会明确 skip，本次实际配置并运行，没有把 skip 计作通过。

独立只读复核覆盖权限、事务、迁移、计算及关联前端，发现问题后补回归并修复。74项包含幂等、数量守恒、多遍返工、交接日期、库存/工资/封账竞争、持久导入、完整导出和迟到证据。

## 迁移与历史数据

- SQLite 空库完整 Alembic 链通过；PostgreSQL 16.15 最终空库完整链到0121通过。
- 最终 PG 有42张新域表、131个索引，compare_metadata 新域 **0差异**，含历史查询索引。
- 本机业务库只读备份副本含30张旧UV表，现有旧UV行数0。直接应用0121后旧表内容摘要一致；旧权限0，新权限无岗位授权。不能据此声称大量历史UV行迁移已验证。
- 副本整条升级在0118遇到预先存在 customer_price_settings；真实业务库仍0117，未 stamp 或升级。该历史漂移是正式升级前置问题。
- 私有副本只用于验证，交付保留聚合结果；业务数据库副本及内容不入Git。

## 代理可执行文件

`edge/uv-printing-agent/dist/rr-uv-agent.exe` SHA256：`6371c7e53a0d376fa8ee8879fed5dd1a4e8321ce40bf6f0710a094e6aa76b93a`。APSW SQLite3.53.4、pywin32 311，构建产物不入Git。

DPAPI配对库→隔离API→实际exe：运行8秒强停，再启动5秒；4个独立Run，待发0、隔离0，人工报产始终2笔。CLI diagnostics正常。交互式getpass配对未自动化，使用当前源码配对库写入相同DPAPI状态；没有测试系统服务安装或锁屏/注销/RDP。

## 多 worker 与重连

隔离 Uvicorn 双 worker（PID31352、34280）共用同一测试库；60次health确实命中两个进程。20次workspace均revision97，batches3/runs7/schedule2/shifts3/tasks3一致；3次独立SSE重连均返回完整reset。采用数据库轮询，无NOTIFY依赖。临时双worker服务测试后停止，用户既有服务未动。Nginx/生产网络故障仍待发布验收。

## 容量和性能

Windows11 10.0.26200、AMD64 Family25 Model80、Python3.14.6，PostgreSQL16.15 loopback独立集群；不是生产性能保证。

| 实验 | 数据/窗口 | p50 / p95 | 结果 |
|---|---|---|---|
| workspace服务查询 | 20机、100000Run、50线程、150请求、预热连接池50、3.046秒 | 879.86 / 1259.10ms | 0失败；**未达建议500ms**；未含HTTP/浏览器，未装载30天排程 |
| outbox写入 | 259200事件（20机×72h×每分钟1任务×3事件），1000条/批，37.386秒 | 168.224 / 211.966ms每批 | 0失败，243666944字节，重启后完整 |
| 本地ACK清空 | 同批持久数据，纯本地磁盘 | 6794.49事件/秒 | 最终0；不是网络补传速率 |

脚本：`backend/scripts/uv_ops_benchmark.py`、`edge/uv-printing-agent/scripts/benchmark_capacity.py`。72小时为加速负载模型，未连续运行72小时。尚未测设备→采集器延迟、识别→浏览器p95、完整30天排程负载和真实恢复速率。如果这一级别负载为上线要求，需继续优化压测，不能以单人预览替代。

## 浏览器与证据文件

使用真实开发代理/API，数据来自隔离库。覆盖1920、1440、1280、390、320以及844×390横屏；核数守恒禁提交、修正保存10件、任务档案与Escape焦点恢复、固定计划冲突、库存、缺项核算、代理诊断、2条完整异步导出、撤权清缓存、API断连与恢复。截图及边界见 [VISUAL_QA](VISUAL_QA.md)。

机器可读聚合结果在 evidence/；本机过程日志在 `D:/RR/.tmp/uv-ops-20260923/`，不作为运行时依赖。
