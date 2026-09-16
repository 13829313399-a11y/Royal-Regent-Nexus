# UV 后端与前端集成交接

日期：2026-09-14。范围：DSH 合并、C0 业务审查、C1 核心闭环、C2 财务/导入导出/核数基础、B1 采集协议参考实现。生产开关保持关闭。本文件区分代码验证、现场验证和生产交付。

## 当前交付位置

以下位置和未提交状态记录集成验证时的快照。后续 Git 交付使用分支 `feat/uv-printing-delivery-20260914`；提交、远程同步与 PR 合并结果以 Git 历史和 PR 状态为准，不将本地集成记录当作当前发布状态。

- DSH 实际工作树为 `D:\RR\dsh-worktree`，分支 `feat/uv-ui`；`c2d7c2b` 与 `e66b0ff` 已通过 fast-forward 合入 `D:\RR\royal-regent-nexus` 的本地 `main`，主线 HEAD 为 `e66b0ff`。原 `PROJECT_MEMORY.md` 改动与四个未跟踪输出目录仍保留，备份在 `D:\RR\maintenance-backups\uv-merge-20260913-234225`。未推送或同步远端其他提交。
- 新实现经 `D:\RR\uv-backend-worktree`（`feat/uv-backend`）完成集成和验证，随后按用户指令合入 `D:\RR\royal-regent-nexus` 的 main 工作区。85 个文件已整合，PROJECT_MEMORY.md 三方合并保留主项目已有内容；仍为未提交改动，尚未形成 Git 合并提交。未部署、未迁移任何真实业务库。合入前备份与文件摘要位于 `D:\RR\maintenance-backups\uv-integrate-main-20260914-142137`。
- 阅读顺序为接手提示词、AGENTS、相关 PROJECT_MEMORY、DESIGN、共同规格、来源审计、DSH 交接及实际 diff。原始来源审计未修改，DSH 历史交接保留；当前接口差异已同步 `DECISIONS.md`、共同规格第 21 节、前端 contracts/mock/测试。

## 已实现行为

禁用 UV 时启动不要求 UV 迁移，也不自动创建 UV 表；已有业务模块可以继续启动。启用时才检查 UV schema 完整性。独立新库登录测试验证了禁用状态下无 UV 表产生。

核心模块使用现有 FastAPI、SQLAlchemy、Alembic 和宿主会话。13 个 UV 权限码注册在现有权限目录，权限裁剪不依赖 UI，也不受 legacy/shadow 模式的宽松兜底影响。所有员工入口要求华康 A 生产部；采集凭据独立绑定机台。`UV_PRINTING_ENABLED=false` 与 `VITE_UV_ENABLED` 未开启时模块不可用。

产品、机台、工艺版本、员工、班次模板、排班、商业价和工价支持正式维护。报工先存草稿，确认才成为有效产量并占用来源。操作幂等、版本冲突、来源守恒和事务锁均在后端执行。质量守恒、修订、纠正、作废和追溯保留历史证据。工资按合格数与独立工价快照计算，按最小币种单位分配余数；确认批次冻结来源，后续调整计入开放日期且不被再次建批计量。

墨水按供应商/材质/颜色/包装等 SKU 身份独立记账；领用使用移动平均成本，退回沿用原领用成本，反向流水保留原记录。库存不足、跨币种反向和不允许的历史改写明确拒绝。月费用分摊保留版本且尾差守恒，缺项或多币种无汇率时不伪造完整结余，关闭期间明确拒绝未核齐或回写操作。核数记录独立保存接收量与差异，来源修订使其待核，不写 PMC 库存。

CSV 导入先保留原文/行号/摘要，显式映射后在 savepoint 内执行实际业务校验并回滚，应用时重查并整批提交；同批并发应用不重复入账。导出从同范围服务端事实生成，重新检查权限，UTF-8 BOM、前导零和公式字符得到保护。

B1 包括不可变事件凭据、稳定事件与作业身份、逐项落盘 ACK、老事件不回滚新状态，以及只读 JSONL 参考采集器的 SQLite 持久待发队列。未知单位、不确定完成、窗口消失均不能生成合格产量；遥测不扣库存。协议和断网重放在合成环境验证，任何机型都没有被标为实机可用。

## 审查与修复证据

| 风险 | 修复与验证位置 |
|---|---|
| 厂区兜底、正式开关、失败回落、旧请求覆盖新上下文 | `src/views/ModuleCenterView.vue`、UV routes/provider/workspace/useUvRequest；workspace 与 API 契约测试 |
| 价格/工资敏感字段只在界面隐藏 | `backend/app/api/uv_printing.py`、`uv_finance.py`；列表、幂等响应、追溯与导出裁剪测试 |
| 草稿抢占来源、更正释放原来源、确认并发超量 | 核心 service 的 report/confirm/correction；PG 来源与幂等测试，sample transport 同步生命周期 |
| 无 quality 权限清零既有质量或作废 | 核心 API 在事务内检查原质量及新质量，清零/void 拒绝测试 |
| 工价与商业价混用、零值丢失、错币种相加、跨夜班日期 | 核心快照/Decimal/上海班次、PricingStudio 与 businessTime 测试 |
| 库存并发负数、冲销重复、成本未知被当零 | 财务 service、双 600ml 请求竞争 1000ml 的 PG 测试、反向与退回测试 |
| 费用缺项仍关账、工资调整漏计或重计 | daily/monthly coverage、payroll freeze/adjustment、关闭期间测试 |
| CSV 只检格式、预演写正式表、同批并发重复应用 | uv_imports 的回滚业务预演、拿锁后刷新 ORM、整批原子应用；PG 测试 |
| 只读首 200 条、正式数据时间显示样例时钟 | 统一 readAllPages、服务端全量汇总、workspaceFreshness；前端定向测试 |
| 首次挂载的快速报工抽屉 Esc 不关闭/不回焦 | UvDrawer 初始监听、卸载清理、最上层键盘处理；组件测试与 Chromium 实际 Enter/Esc/回焦 |

按仓库要求进行了独立静态复核。已报告的 P1/P2 问题均有修复；独立复核未发现遗留阻断。该结论不是实机或生产验收。

## 验证环境与命令

主项目合入后复测：在 `D:\RR\royal-regent-nexus` 运行上述范围的前端测试 **150 passed**、构建与测试类型检查通过；在主项目 backend 目录使用原独立 PostgreSQL 测试库复测 **76 passed in 58.21s**。代码文件摘要与最终集成版本一致，主项目已有 PROJECT_MEMORY 内容经三方合并保留。此次复测日志在 `D:\RR\maintenance-backups\uv-integrate-main-20260914-142137`。

所有运行证据位于 `D:\RR\outputs\uv-backend-qa-20260914`，不使用真实业务数据库。

- PostgreSQL 16.15，独立数据目录 `D:\RR\uv-backend-worktree\.tmp\postgres\data`，仅监听 `127.0.0.1:55432`。开发库 `rr_uv_dev`，测试库 `rr_uv_core` / `rr_uv_finance` / `rr_uv_ingest`，迁移演练库 `rr_uv_migration`。后端 API 端口 8011，前端开发端口 5182，生产构建预览 5183。
- Python 使用主项目现有 `.venv`，没有新增第三方后端依赖；前端使用 node_modules junction，没有改锁文件。
- UV：`python -m pytest tests/test_uv_printing.py tests/test_uv_finance.py tests/test_uv_ingest.py -q --disable-warnings -p no:cacheprovider`，通过显式 `UV_TEST_DATABASE_URL`、`UV_FINANCE_TEST_DATABASE_URL`、`UV_INGEST_TEST_DATABASE_URL` 选择上述 PG 测试库。最终 **76 passed in 71.02s**，无跳过。
- 现有回归：`python -m pytest tests/test_auth_api.py tests/test_iam_api.py tests/test_system_position_catalog.py -q --disable-warnings -p no:cacheprovider`。初次 81 通过、3 个权限目录/版本陈旧断言失败；更新目录版本、权限数量及读权限集合后定向复测 3 通过。未修改其他模块业务行为以迎合断言。
- 前端：`npm run test:unit -- src/features/uv-printing src/api/uvPrinting.spec.ts src/router/__tests__ src/views/__tests__/productionModuleEntry.spec.ts src/views/__tests__/moduleCenterFactoryScope.spec.ts`；`npm run build`；`npm run typecheck:test`。最终 150 项前端及路由测试通过，构建和测试类型检查通过。
- 迁移：新演练库先 `alembic upgrade 20260912_0111`，加入合成非 UV 证据，再 `alembic upgrade head` 到唯一 head `20260914_0115`。167 张非 UV 表前后行数与内容摘要一致，新增 30 张 UV 表。空库全链升级与开发库增量升级也通过；0115 upgrade/downgrade 及模型字段约束有独立测试。未演练装有真实数据的生产恢复。

浏览器使用本机 Chromium、真实宿主登录与真实 transport，库内全部是合成验收数据。先通过界面创建并确认 `100=90+5+3+2`，商业价 HKD1、工价 HKD0.2，得到 HKD90 产值与 HKD18 暂算工资；再经界面质量修订为 `95+5+0+0`，有效报工只有一个修订，产值 HKD95、工资 HKD19。七个正式页面无 UV HTTP 失败和脚本异常。390/1024/1366/1440/1920 驾驶舱均无页面水平溢出；抽屉 Enter 打开、Esc 关闭、回焦通过；经营日报实际下载 `uv-daily.csv`。

## T01–T45 状态

“通过”只表示列出的开发环境证据；“部分”明确未覆盖规格的全部规模或现场情境，不能计为完整验收。

| 编号 | 状态 | 证据与边界 |
|---|---|---|
| T01 | 通过 | 模块中心厂区测试：B/group 无 A 卡片 |
| T02 | 通过 | URL/权限契约及 API 显式厂区，拒绝 B/group |
| T03 | 通过 | PG 只读账号直接写拒绝；legacy/shadow/enforce 均验证 |
| T04 | 通过 | workspace 异步代次/取消测试，不恢复旧上下文 |
| T05 | 通过 | 列表、响应重放、追溯、导出敏感字段裁剪；未新增实时通道 |
| T06 | 通过 | 跨厂对象引用拒绝，原数据不变 |
| T07 | 通过 | 同事件十次重放一条有效事件/投影 |
| T08 | 通过 | 同机同名不同作业 ID 保留 |
| T09 | 通过 | 相同 operation/payload 重放及并发，单次计量 |
| T10 | 通过 | 同键异体 409，旧事实不覆盖 |
| T11 | 通过 | SQLite 队列重启、网络失败、丢 ACK 和局部 ACK 重放；合成环境 |
| T12 | 部分 | uncertain 协议不自动报工；真实软件窗口消失未现场执行 |
| T13 | 通过 | 未知 raw_unit 保留待核，不能猜件数 |
| T14 | 部分 | 界面实现完整板/尾板建议，服务端确认幂等已测；47 件尾板场景未做端到端回放 |
| T15 | 通过 | 来源 100 先分 60 后分 50 拒绝，余额 40 |
| T16 | 部分 | 自动证据不新增报工，人工关联保持产量；现场迟到同一实体作业未验收 |
| T17 | 通过 | UI/API 100=90+5+3+2，良率按 90/95 |
| T18 | 通过 | 不守恒的质量保存拒绝，无半条记录 |
| T19 | 通过 | 显式 0 与缺值分离，工价及换算测试 |
| T20 | 通过 | 07:39:59/07:40/21:00/跨月夜班，上海时区测试 |
| T21 | 通过 | 跨月运行区间分段，产量仍归有效报工一次 |
| T22 | 通过 | 周日产量保留；明确日历为休息日时标计划外，未配置不猜制度 |
| T23 | 通过 | 价格变更不改已确认快照 |
| T24 | 通过 | 商业价 1 与工价 0.2 分开；PG 与真实 UI 链 |
| T25 | 通过 | 1.00 分三人 0.34/0.33/0.33，PG + 前端 |
| T26 | 通过 | 无工价、无人员、待质量各自待核，非假零 |
| T27 | 通过 | 400件、0.70、0.98、1.166667；工价不可由报价采用 |
| T28 | 通过 | 500ml × 2 = 1000ml |
| T29 | 通过 | 供应商 B 不借供应商 A 库存 |
| T30 | 通过 | PG 并发各出 600ml，库存 1000ml，仅一笔成功 |
| T31 | 通过 | 反向保留原流水、余额/成本恢复、跨币种拒绝 |
| T32 | 通过 | 遥测与实际领用共存，不重复库存/成本 |
| T33 | 通过 | 100.00 分三天 33.34/33.33/33.33，版本历史不变 |
| T34 | 通过 | 月度 91/110，全量汇总而非日比率平均 |
| T35 | 通过 | HKD/CNY 无汇率不合并，缺成本为 null |
| T36 | 部分 | 跨 200 条分页前端测试 + 服务端 page_size=1 全量汇总；2000 条性能/虚拟滚动未验收 |
| T37 | 部分 | 失败状态、FastAPI 错误形状、无 mock 回落测试；未做真实断网压力实验 |
| T38 | 通过 | CSV 预演不落正式表、错误整批回滚、重复与两个 actor 并发应用 |
| T39 | 未实施 | 未提供历史汇总快照导入入口；不会导入后叠加，但不能声称快照迁移验收 |
| T40 | 通过 | 关闭期间拒绝回写；工资冻结后的调整进入后续日期 |
| T41 | 通过 | 生产构建不注册样例路由，直接访问无 UV 工作区；产物无样例夹具标识 |
| T42 | 部分 | 五宽度驾驶舱、真实关键链、抽屉键盘/回焦；所有页面极端长名大数与屏幕阅读器未全量验收 |
| T43 | 通过 | 完整迁移至唯一 0115，167 非 UV 表摘要不变；合成旧库 |
| T44 | 通过 | 质量/更正只计有效修订，旧记录/原因/trace 可查；工资冻结不回写 |
| T45 | 部分 | 登录、IAM、职位与路由/模块中心回归；喷油/3D/注塑真实业务数据端到端流程未重跑 |

## 尚未作为完成交付的内容

1. 原生旧 Excel 和历史汇总快照的专用映射/迁移；目前只提供 CSV 业务导入，未宣称所有旧模板可用。
2. 2000 条规模的全部页面性能、极端内容与辅助技术验收。
3. 真实打印机适配、现场断网/软件版本/单位及完工信号验证；当前 B1 参考适配器不等于五种机型可用。
4. 正式费率、币种、人员/班次与工作日制度的业务确认，以及真实数据迁移、备份恢复、生产开关和部署。

新后端已按后续指令合入 main 工作区，Git 交付状态以仓库提交与 PR 为准；生产部署和真实业务库迁移未执行。运行证据可复核，但不能把开发测试转换为业务验收结论。
