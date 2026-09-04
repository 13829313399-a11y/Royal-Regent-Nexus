# 华康A（河源）3D 打印迁移与云端直连

## 当前边界与目标

本模块固定归属 `huakang-a`，物理站点为 `heyuan`。现有页面、API、业务表及 Edge Agent 保留；目标是云端独立 Connector 经站点 VPN 访问打印机私网 MQTT/TLS，现场网关仅负责三层路由，浏览器只访问 RR-Nexus HTTPS。

**PR-00～PR-03 提供本地快照捕获、分析、增量表结构、可续跑导入和管理员对账查询。** Alembic 升级、导入与部署都是独立操作；代码完成和隔离演练不代表现有业务库或生产库已迁移。现有 JSON 导入函数仅为显式兼容保留，禁止用于本次最终切换。旧运行期的历史改名级联、库存截断/冲销、历史成本重算问题留待 PR-04 修复，当前不能据此开放切换。

## 文件与调用链

- 现有页面：`src/views/ThreeDPrintingManagementView.vue`，API 客户端 `src/api/threeDPrinting.ts`。
- 路由：`/modules/production/three-d-printing?factory=huakang-a`；后端 `backend/app/api/three_d_printing.py` 注册 `/api/three-d-printing`。
- 业务服务/表/契约：`backend/app/services/three_d_printing.py`、`backend/app/models/three_d_printing.py`、`backend/app/schemas/three_d_printing.py`。
- 既有协议资产：`edge/three-d-printing-agent/agent.js`，后续抽取 BambuAdapter，不从零重写。
- 只读入口：`backend/scripts/capture_legacy_three_d_snapshot.py`、`legacy_sqlite_reader.py`、`legacy_three_d_analysis.py`。
- 迁移 CLI：`backend/scripts/migrate_legacy_three_d_printing.py --mode analyze`。
- checkpoint 导入与对账：`backend/scripts/legacy_three_d_importer.py`；管理员只读投影：`backend/app/services/three_d_migration_queries.py`。
- 清单契约：`backend/scripts/legacy_snapshot_manifest.schema.json`。
- 凭据检查：`backend/scripts/scan_three_d_secrets.py` 和 `.github/workflows/three-d-secret-scan.yml`。

## 数据源与只读捕获

权威业务为 SQLite `app_state.id=1`，图片为 `product_images` 的原始 BLOB。`storage_type=base64` 不表示 BLOB 还需要 Base64 解码。工具校验图片实际格式、Pillow 解码、尺寸/字节限制，保存 `legacy_sha256` 和重新计算的 `content_sha256`；旧哈希可能对应 data URI。

禁止单独复制有活动 WAL 的主库。离线输入只能是已冻结目录或原始归档，工具对白名单文件做哈希、复制前后核验，再在临时副本中通过 `sqlite3.Connection.backup()` 捕获；不会 checkpoint 或修改源 SQLite/WAL，不提取 `.git`、配置或旧源码。运行中的目录请使用 `capture --live` 在线 backup，不能假装目录复制是在线一致性快照。在线只读 SQLite 连接可能维护 SHM 读锁，不改业务主库/WAL；最终切换仍需停止旧系统写入。

WAL 校验覆盖 header、页大小、帧长度、有效帧 salt 与滚动校验和。SQLite 在 checkpoint 后可以复用 WAL 并保留旧尾部：工具记录有效/已提交帧数及旧 checkpoint 尾部帧数，不将正常旧尾部当坏文件；有效帧损坏会阻断。格式依据 [SQLite WAL 文件格式](https://www.sqlite.org/fileformat.html#wal_reset)。缺 WAL 且主库标记为 WAL 模式时拒绝捕获；只有确已停写并完成 checkpoint 才可使用 `--wal-checkpoint-confirmed`。不能靠当前数量相同证明 WAL 可丢弃。

输出为新目录中的 `snapshot.sqlite` 与 `manifest.json`，不覆盖现有目录。独立 snapshot 使用 DELETE journal，无需携带 WAL。manifest 只含哈希、时间、数量与检查结果，不包含配置或原始业务行。源业务字段及最终报告还会进行凭据模式检查，命中时以固定错误码阻断，不输出原值。业务快照和图片本身仍是内部数据，放在仓库外的受限目录。

仓库根目录执行（将示例路径替换成受控路径）：

```powershell
backend/.venv/Scripts/python.exe backend/scripts/capture_legacy_three_d_snapshot.py `
  --source-zip 'D:/private/legacy.zip' --output-dir 'D:/private/capture-001'

backend/.venv/Scripts/python.exe backend/scripts/capture_legacy_three_d_snapshot.py `
  --source-dir 'D:/legacy/3d-server' --live --output-dir 'D:/private/live-capture-001'

backend/.venv/Scripts/python.exe backend/scripts/migrate_legacy_three_d_printing.py `
  --source-zip 'D:/private/legacy.zip' --factory-id huakang-a --site-code heyuan `
  --mode analyze --snapshot-dir 'D:/private/capture-002' `
  --expected-audit 'D:/private/three_d_legacy_audit.json' --report 'D:/private/analyze-001.json'

backend/.venv/Scripts/python.exe backend/scripts/migrate_legacy_three_d_printing.py `
  --source 'D:/private/capture-001/snapshot.sqlite' --mode analyze `
  --report 'D:/private/analyze-002.json'
```

分析入口不加载 `app.db`、不读取 Nexus 连接设置，不连接业务数据库或写图片资产。不指定 `--snapshot-dir` 时使用临时副本并自动清理。报告输出路径必须未存在；不能指向源目录内。JSON 与 SQLite 并存时即使显式给了 `data.json` 也优先 SQLite。只有 JSON 时须 `--allow-json-fallback`，输出醒目过期警告；JSON 不允许通过 SQLite 的 `--expected-audit` 验收。`--dry-run` 作为只读兼容参数保留，默认模式也是 analyze。

## 首份上传包验收基线

以下是用户提供的 2026-09-04 快照，非生产硬编码常量。正式切换需重新捕获最新快照并生成期望值。

| 项目 | 本次验收 |
| --- | ---: |
| ZIP SHA-256 | `336d891130e1810c9f35d77c4fdb51eec081a2af01b304877d02cb7ba50f080f` |
| SQLite 更新时间（UTC） | 2026-09-04T04:46:46.084+00:00 |
| 材料 / 产品 / 图片 | 8 / 1,316 / 1,006 |
| 日期范围 / 日期键 | 2026-05-26～2026-09-04 / 89 |
| 全部 / 有效 / 墓碑记录 | 3,020 / 2,871 / 149 |
| 缺结束时间、待设备核对 | 4 |
| 库存键 / 入库凭证 / 库存余额 | 10 / 3 / 10,500g |
| 图片字节 / 孤儿 / 无法解码 | 54,967,958 / 0 / 0 |
| 计划材料 / 数量合计 | 374,028.5g / 4,560 |
| 设计费 / 单价×数量 | 7,820 / 38,427.51 |

库存只统计期初余额，115,000g 历史入库不再叠加。保留重复产品 ID 和材料原名/别名；不补造缺客户、价格、重量。历史快照对当前主数据仅比较，不修改。

业务 state 的 `settings.machines=11` 与实际配置机数是两类证据。分析器不读取含 secrets 的配置，只报告 configured_machine_count；现场审计另核实 11 台 Bambu，不从设置值伪造配置核对。

`legacy_status=running` 不能证明设备正在运行。分析报告使用蓝图 §8.1 的派生标签，区分有结束时间、缺开始时间和待设备核对。数据库使用稳定 `run_status` 加独立 `reconciliation_status` / 质量标志；蓝图 §7.1 的枚举与 §8.1 标签不完全一致，不直接塞入同一数据库枚举。

## v2 升级、分批导入与对账

Alembic `20260904_0098` 紧接 `20260904_0097`，增量升级既有 `three_d_printing_*` 表，保留旧 Edge Agent。新增站点、网关、连接器、受限连接配置、状态事件、材料别名和迁移批次/行结果。记录保存历史快照、来源与质量信息，库存流水区分期初余额和不影响余额的历史凭证；命令具有租约字段，但现有 Edge 运行协议尚未使用新租约。

升级前备份目标数据库与资产，检查当前 revision 和待执行迁移。`upgrade` 不会由导入脚本或应用自动执行。尤其已有目标若早于 `0095`，需单独审查该版本删除退役排程数据的要求，不能因本次 3D 开发而跳过备份门槛。有业务数据时禁止通过 downgrade 丢弃 v2 信息。

下面示例的 `DATABASE_URL` **只指向仓库外的隔离演练库**；正式环境使用其受控配置，不在命令输出中打印连接凭据。先完成目标 schema 升级，再导入独立快照：

```powershell
$env:DATABASE_URL = 'sqlite:///D:/private/rehearsal/nexus.db'
$env:THREE_D_ASSET_DIR = 'D:/private/rehearsal/assets'
Push-Location backend
.venv/Scripts/python.exe -m alembic upgrade head
Pop-Location

backend/.venv/Scripts/python.exe backend/scripts/migrate_legacy_three_d_printing.py `
  --source 'D:/private/capture-001/snapshot.sqlite' --mode import --chunk-size 200 `
  --expected-audit 'D:/private/three_d_legacy_audit.json' --report 'D:/private/import-001.json'

backend/.venv/Scripts/python.exe backend/scripts/migrate_legacy_three_d_printing.py `
  --source 'D:/private/capture-001/snapshot.sqlite' --mode reconcile `
  --migration-batch '<批次ID>' --report 'D:/private/reconcile-001.json'

backend/.venv/Scripts/python.exe backend/scripts/migrate_legacy_three_d_printing.py `
  --source 'D:/private/capture-001/snapshot.sqlite' --mode import --resume `
  --migration-batch '<失败批次ID>' --report 'D:/private/resume-001.json'
```

每 100～500 行提交一次业务变更和 checkpoint，图片逐张验证、保存并记录失败。失败批次保留已提交进度；续跑须绑定同一快照及批次。新快照只更新来源明确且未被 RR-Nexus 人工修改的迁移行；来源冲突必须解决，不能用迁移覆盖手工业务数据。首次导入只接管经精确检查的未修改默认设置/打印机占位行。

同一快照再次导入会重新核验目标，全部一致才返回 `already_reconciled`。业务行、库存流水与资产零增量，核验审计允许新增。对账检查业务字段和实际图片资产哈希，不能只相信成功行数。`--expected-audit` 不匹配时在写目标前停止；`analyze`、`dry-run` 和 `--dry-run` 不初始化应用数据库。退出码 0 表示本次模式成功，2 表示失败或对账差异，不能忽略后继续切换。报告文件必须使用新路径，且不能落在捕获目录、图片资产目录或目标数据库文件上。

受控异常会在失败报告中保留 `batch_id`，可据此续跑；强制终止进程或机器断电时可能来不及生成报告，需从管理员迁移列表查找批次，待租约到期后续跑。已提交 checkpoint 不回退，未提交整批事务由数据库回滚。

历史成本保存 `legacy-v1` 公式、输入和快照费率，并明确标注这些费率来自源快照，不等于已核实的历史实际成本。仅主数据/费率改变，或记录仅改备注、结束时间等非成本字段时，保留已有成本快照。权威新源修正重量、时长、数量、报价或设计费且材料未变时，沿用首次导入的费率计算修正值；若更换材料且缺少历史单价，相关成本保持空值并标记 `cost_snapshot_requires_review`，不能使用当前主数据倒推历史价格。进一步的财务重算/审批策略属于 PR-04。图片按产品与内容哈希幂等存储，旧 data URI 哈希单独保留。

管理员只读接口（均位于 `/api/three-d-printing`）：

- `GET /migration-batches?page=1&page_size=50`：批次列表。
- `GET /migration-batches/{id}`：来源哈希、版本、预期计数和摘要。
- `GET /migration-batches/{id}/rows?status=failed`：行结果与分页；`/row-errors` 为失败行入口。
- `GET /migration-batches/{id}/reconciliation`：安全投影后的对账结果。

仅有效管理员且具备华康 A 审计权限可访问；显式拒绝、过期授权仍生效。跨厂批次不返回数据，普通 3D 岗位不得查看或执行迁移；没有浏览器导入 POST 接口。不返回原始 JSON、连接凭据或不受约束的错误文本。

## 凭据基线与上线前待办

```powershell
backend/.venv/Scripts/python.exe backend/scripts/scan_three_d_secrets.py --source-zip 'D:/private/legacy.zip'
backend/.venv/Scripts/python.exe backend/scripts/scan_three_d_secrets.py --staged
backend/.venv/Scripts/python.exe backend/scripts/scan_three_d_secrets.py --paths 'D:/private/analyze-001.json'
```

ZIP 检查只在内存读取固定配置/源码白名单；结果仅计数，不输出 token、LAN code、BasicAuth 密码或匹配片段。退出 0=无发现、1=发现、2=未完成。它是定向规则检查，不能证明未知格式的秘密绝不存在。CI 检查被跟踪的 3D 文件和子目录，工作流只具有 contents:read。

旧包已确认有嵌入 Git URL 凭据、PAT、11 个设备 code 和 BasicAuth。PAT 撤销须由该旧凭据的账户所有者完成并提供无密钥的核验记录；不把本机当前 Git 登录误认为旧凭据所有者。第一轮没有轮换、撤销或部署任何凭据。设备 code 待独占灰度通过后逐台轮换，Secret Store 使用只读服务挂载，库里只存 credential_ref。VPN 私钥、服务令牌和打印机凭据分别管理。禁止整个旧 ZIP 上服务器或进入 Git。

## 后续批次、依赖与数据库设计

以下是拟定交付分支名，不表示这些分支/PR已创建。本轮只留工作区代码。

| 批次 / 拟定分支 | 依赖 | 内容与完成门槛 |
| --- | --- | --- |
| PR-00 `agent/3d-pr00-baseline` | 基线审计 | 清单、秘密检查、忽略规则、备份边界 |
| PR-01 `agent/3d-pr01-sqlite-reader` | PR-00 | SQLite/WAL、黄金样本、只读 analyze |
| PR-02 `agent/3d-pr02-domain-v2` | PR-01 | 增量 Alembic、站点、来源、质量、批次、租约 |
| PR-03 `agent/3d-pr03-reconciled-import` | PR-02 | 分批事务、图片资产、checkpoint、幂等/续跑/对账 |
| PR-04 `agent/3d-pr04-ledger-snapshots` | PR-02 | 取消历史级联、消费/冲销/恢复、成本版本 |
| PR-05 `agent/3d-pr05-site-vpn` | PR-00，可与03/04并行 | 网关、路由、最小ACL与doctor |
| PR-06 `agent/3d-pr06-cloud-connector` | PR-03/04/05 | BambuAdapter、单机leader、事件、租约命令、SSE |
| PR-07 `agent/3d-pr07-modular-ui` | PR-06契约 | 拆分页面、分页/虚拟化、实时和迁移中心 |
| PR-08 `agent/3d-pr08-cutover` | PR-03～07 | 两次迁移演练、备份恢复、VPN/设备独占切换 |

PR-02/PR-03 的模型和导入器复用现有 `three_d_printing_*` 表名，没有另造平行业务模块。PR-04 的历史/库存运行逻辑修复及后续 VPN/Connector/UI/切换工作仍需独立验收。

## 测试与恢复

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_legacy_three_d_snapshot.py backend/tests/test_legacy_three_d_analysis.py backend/tests/test_three_d_secret_scan.py -q
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_three_d_printing_api.py -q
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_three_d_schema_v2.py backend/tests/test_legacy_three_d_importer.py backend/tests/test_legacy_three_d_cli.py backend/tests/test_three_d_migration_api.py -q
```

自动测试数据库与源素材均由合成 fixture 创建；真实完整包仅在仓库外演练，不提交客户数据、数据库、图片或凭据。除快照安全测试外，需覆盖旧 schema 升级保留数据、导入幂等、失败续跑、增量更新、人工修改冲突、图片损坏对账及管理员访问边界。

已应用 v2 schema 或导入业务后，不能把撤回代码等同于数据回滚。恢复应依据同批数据库/资产备份及切换后新业务情况决定；已产生新业务时不可直接覆盖为旧备份。源文件保持不变，生成快照可另目录重建；不要覆盖或删除用户原包。

## 正式切换前保留的运维门槛

1. PostgreSQL 与图片资产同批备份，校验哈希并在隔离环境恢复。若已有新业务，不得直接恢复旧备份覆盖。
2. 定义并确认真实打印机 VLAN、11 台地址、云端 VPN 身份及回程路由。只允许 Connector 到指定打印机 TCP 8883；禁止公网NAT映射。其它设备端口须逐项验证后放行。
3. 用模拟器测试11台、双实例leader、重复/乱序事件、租约过期、30分钟VPN中断和恢复。断网只产生 STALE/UNKNOWN，不误结算任务。
4. 停止旧界面写入，取得新鲜一致性快照，运行 analyze/import/reconcile；任一硬性差异阻断切换。
5. 逐台独占移交：先释放旧Agent该机连接，再启云端Connector，回滚时反向；未经固件验证不双订阅。
6. 一台灰度机完成开始/暂停/恢复/结束、库存/成本闭环，外网或手机热点验证无需用户VPN即可实时查看；之后2～3台一批放开。
7. 24～72小时保留旧系统只读与审计材料，确认稳定后轮换设备code并停用旧Edge写入。VPN或Connector停机不能影响设备本地继续打印。
