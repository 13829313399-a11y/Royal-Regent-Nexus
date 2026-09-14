# UV打印管理 · 前端开发交接说明与决策记录

> Codex 集成补充（2026-09-14）：下方 DSH 内容保留为历史交接证据，其中“后端不存在/权限未注册”等结论已被本次实现取代。当前事实与验证边界以 `CODEX_BACKEND_HANDOFF.md` 和共同规格末尾的集成契约补充为准。实测 DSH 分支为 `feat/uv-ui`，`c2d7c2b`、`e66b0ff` 已快进合入本地主线；新后端经独立工作树验证后，已按后续指令合入 main 工作区，仍未提交。

## Codex 当前决策

- 保留 DSH 版式，只调整接口接线、范围、日期、敏感字段、生命周期和必要币种选择。
- 正式接口返回 `meta.data_mode=live`；样例仅在 DEV 显式开关下加载，生产构建不包含样例业务夹具。错误不回落样例。
- 列表每页最多 200；前端需要全范围时通过统一分页读取。服务端经营汇总独立于列表分页。
- 新报工为 draft，确认才占来源和计量；质量与更正保留来源。已冻结工资不能重写原报工，只能进入后续开放日的明确调整。
- 明确支持 CNY/HKD/USD/JPY/EUR/GBP，金额使用 Decimal。正式录入要求选择币种；无汇率不合并。测算只能采用为商业价。
- 采购、期初和盘点不直接计领用成本；领用/退回及其反向流水计入经营。缺失成本不是 0。月工作日未配置时不把默认天数当制度；已配置休息日有生产仍保留事实并标计划外。
- 导入目前为 UTF-8 CSV；预览使用实际业务校验并回滚，最终整批应用；保留原文、行号和摘要。旧原生 Excel、历史快照及复杂核数模板的专门映射未实施。产品/机台/报工导入批次不提供伪冲销成功；费用/墨水批次可反向。
- B1 为协议与只读 JSONL 参考适配器，含 SQLite 持久队列、ACK 和幂等重放；真实打印机适配仍需现场证据。核数仅交接差异，不写仓库。

> 执行工具/阶段：DeepSeek Harness（DSH），F0 + F1 + F2 前端阶段
> 事实源：`docs/uv-printing/UV_PRINT_SHARED_SPEC.md`（v1.0）、`docs/uv-printing/UV_PRINT_SOURCE_AUDIT.md`
> 本文件只记录**本次实际实现与规格之间的差异、消解的歧义和仍需后端确认的项**。
> 交接结果按 `docs/uv-printing/HANDOFF_DSH_TO_CODEX.md` 填写。

---

## 1. 工作树与运行方式

| 项目 | 值 |
|---|---|
| 工作树绝对路径 | `D:\RR\dsh-worktree` |
| 分支 | `dsh-worktree`（自 `main @ 35105c6162e13fa84f02c645916a407b97cf6c9f` 创建） |
| 依赖 | `node_modules` 以目录联接（junction）指向主检出 `D:\RR\royal-regent-nexus\node_modules`，未在本树安装第二份依赖 |
| 前端端口 | `5181`（`npm run dev:uv`，`--strictPort`），与主工作树 5173 隔离 |
| 样例开关 | `.env.local`：`VITE_UV_PREVIEW=true`、`VITE_UV_ENABLED=false`（该文件被 `.gitignore` 忽略） |
| 后端 | 本阶段不实现后端。宿主登录态需要真实会话，可用只读验收替身 `npm run uv:mock-backend`；UV 业务接口刻意返回 503，用于证明前端不回落样例 |

## 2. 契约与规格的差异（DECISIONS）

按规格 17.1 的约定记录「原约定 → 新约定 → 原因 → 受影响范围」。

| # | 原约定 | 新约定 | 原因 | 受影响范围 |
|---|---|---|---|---|
| D-01 | 规格 11.1 只给出 `UvTransport`（summary/machines/jobs/reports/createReport） | 新增 `UvWorkspaceTransport extends UvTransport`，补齐产品、价规、命令、墨水、排班、工资预览、费用、定价、报表与导出方法 | 页面需要具名方法；规格 628 行允许「其他操作按同样模式扩展具名方法」 | `contracts.ts`、`src/api/uvPrinting.ts`、样例 transport、后端 Pydantic schema |
| D-02 | `UvScope.shift` 仅 `ShiftCode` | 查询仍只发送 `day`/`night`；`ShiftScope = ShiftCode \| 'all'` 只用于**响应**与 UI 状态 | 规格 628 行明确「请求全天时省略 shift，不发送类型外的 all」 | `contracts.ts` 类型、各页面筛选 |
| D-03 | 规格未定义 `UvReport` 上的展示字段 | 增加 `product_no`、`product_name`、`worker_names`、`allocation_total`、`correction_reason` 等只读冗余字段 | 列表需要在不额外请求产品/人员目录的情况下显示可读名称；服务端可下发的投影 | 后端 schema（只读字段），前端列表 |
| D-04 | 规格未定义报工命令的请求体细节 | `UvReportCommandInput` / `UvQualityCommandInput` / `UvCorrectionInput` / `UvVoidInput` / `UvHandoverInput` / `UvAssignmentInput` / `UvExpenseInput` / `UvMonthlyPolicyInput` / `UvPricingQuoteInput` / `UvPricingAdoptInput` / `UvExportInput` 均 `extends UvCommandMeta` | 规格 11.2 要求所有命令携带 `operation_id` 与 `expected_version` | 后端路由、前端命令 |
| D-05 | `UvInkIssueInput` / `UvInkPurchaseInput` 是否带版本 | **不带** `expected_version`，只带 `operation_id`；冲销 `UvReverseInput` 带 `expected_version` | 墨水出入库不修改既有对象，只有冲销引用原流水 | 后端路由、`InkIssueDrawer` |
| D-06 | 规格未定义前端如何在不额外请求的情况下知道「当前用户的 UV 权限」 | 页面通过 `useUvWorkspace().can(code)` 调用宿主 `authStore.can(code, 'huakang-a', 'production')`；**不给 authStore 塞任何 UV 权限字符串** | 规格 10 节要求不得伪造授权；权限码注册属于 Codex | 所有页面的按钮门控 |
| D-07 | 规格未规定样例预览如何携带登录态 | 预览沿用 `requiresAuth: true`，但 `enforcePermissions: false`（内存样例不访问真实 UV 接口） | 规格 11.3 要求沿用登录状态、不要求尚未注册的 UV 业务权限 | `routes.ts`、DEV 预览 |
| D-08 | 规格未规定 stale 的展示方式 | `stale`（刷新失败但已有旧数据）显示可重试横幅；列表页在 stale 时隐藏数字而不是继续显示旧值 | 规格 391 行要求过期状态有明确表现，且失败不是空账 | 各页面 `UvStateBlock` 使用 |
| D-09 | 规格 5.7 只说明领用成本口径 | 页面把 `cost_pending`（缺单价）与 `amount: null` 分开渲染为「待核」，绝不显示 0 | 规格 FIX-03 要求 null 表示缺失、0 是有效数据 | 墨水页面、费用、报表 |
| D-10 | 规格示例金额样例币种 HKD | 样例统一 `HKD`，并在 `DECISIONS` 与本文件标注为样例币种，旧历史不猜 | 规格 5.4【待确认】 | 全部样例数据 |

## 3. 代码消解的实现歧义（需要 Codex 复核）

1. **价规解析优先级**：样例 transport 的 `priceOn()` 实现「精确机台覆盖(3) > 价组覆盖(2) > 标准价(1)」，同优先级内按读取顺序取第一条，并在 `saveRateVersion` 中拒绝同优先级/同币种/同作用域的生效区间重叠（422）。回退**只发生在同一种价规内**，缺工价不会回退到商业价。
2. **产值口径**：`output_value = 已确认合格件 × 商业执行价快照`；`area_value = 合格件 × 单件计价面积(cm²) × 面积费率` 作为**独立备选视角**，两者不相加。显式零价（`unit_price = 0`）判为 `priced` 且金额为 0，与「缺价 → `unpriced`/`null`」严格区分。
3. **工资口径**：`班组计件金额 = 可计薪合格数量 × 计件工价快照`；同工作批次按稳定员工顺序（工号升序）等分，余数按最小币种单位补足（HKD 1.00 / 3 人 = 0.34 + 0.33 + 0.33）。未定价 → `amount: null`，不是 0；质量未判清 → `provisional` + 原因。
4. **更正语义**：`correctReport` 把原记录置为 `voided` 并保留全部原值、冲销其来源分配，再创建 `status: 'corrected'`、`replaces_report_id` 指向原单的新修订；数量差异在 UI 上并排显示。
5. **质量补录**：已确认报工的质量补录也创建递增 `version` 的修订（不原地覆盖），并要求填写原因。
6. **来源分配守恒**：`available_piece_qty = suggested_piece_qty − 未被冲销的分配量`；`raw_unit === 'unknown'` 时 `available_piece_qty` 一律为 `null`，分配请求直接 422。
7. **幂等**：样例 transport 以 `operation_id` 为键保存 payload 指纹；同键同体返回 `replayed: true` 的原结果，同键异体返回 409。
8. **班次归属**：用 `Intl.DateTimeFormat(Asia/Shanghai)` 计算，白班 07:40–21:00、夜班 21:00–次日 07:40，业务日期取班次开始日；运行时序按班次区间拆分，不在两天重复计同一份产量。
9. **分摊**：`prorateMonthly` 用 BigInt 定点数把整月固定费用摊到工作日集合，余数从当月第一天起逐日补一个最小币种单位；`prorationTotals().matches` 为 false 时拒绝保存月参数。
10. **月比率**：`ratioOfSums` 一律用「月分子合计 ÷ 月分母合计」，不平均每天百分比（T34：90/100 + 1/10 → 91/110 ≈ 82.7273%）。
11. **样例时钟**：样例 transport 有独立 `asOf`，「时间 +12 分钟」按钮推进它并重算心跳新鲜度，用于演示 `fresh → stale`、`printing → offline`；不代表真实遥测。

## 4. 仍需业务/后端确认的项

| 项 | 前端现行暂行行为 | 需要谁确认 |
|---|---|---|
| 本模块默认币种 | 样例统一 HKD 并标注为样例；字段本身是 `currency + Decimal` | 业务（规格 5.4 / 19 节） |
| 计价基准 | 默认「已确认合格件 × 商业执行价」，`basis` 字段已显式建模 | 业务 |
| 计件工价与商业价的关系 | 严格分开；缺工价显示「未定价」，不回退商业价 | 业务 |
| 多人/换人/跨机分摊 | 同工作批次等分；份额由排班记录表达，前端不编辑份额 | 业务 + Codex |
| 「无产值工资」「可回收工资/油漆」的来源 | 建模为独立费用类别/调整项，不与个人工资互相抵扣 | 业务 |
| 入库核数是否对接 PMC 仓 | 只做核数/交接，不写仓库库存 | PMC |
| 分摊工作日集合 | 由月参数显式选择，不使用 26/26/21 默认值 | 业务 |
| 关账状态 | 接口未下发时页面**不假设**已关账，也不把未关账当已定稿 | Codex（补字段） |
| 导出文件 | 样例不生成真实文件，只报告与网页完全一致的筛选范围 | Codex（B0 实现 `/exports/{kind}`） |
| 采集能力清单 | 由机台档案的 `capabilities` 逐台声明，不支持即显示「设备未提供」 | Codex（B1） |

## 5. 已知限制

0. **路由与卡片契约有自动化测试**：`__tests__/workspaceContract.spec.ts`（19 用例）锁定正式路由元信息、七个子路由、预览路由仅在开关为真时注册且不继承正式权限、卡片作用域与「卡片不写死动态经营值」；`__tests__/workspaceContext.spec.ts`（7 用例）锁定预览仅按 `/__preview/uv-printing` 前缀判定、正式环境权限落到宿主 `authStore`（不被预览分支短路）、有效厂区不符时返回违规状态。
1. **UV 业务后端不存在**：`/api/uv-printing/*` 全部未实现；正式路由在任何后端就绪前只应表现为失败/未授权，不会回落样例。`VITE_UV_ENABLED` 默认 false。
2. **权限码未注册**：`uv_printing:*` 未在 `backend/app/services/permission_codes.py` 注册，正式卡片的 `strictAccess` 会让模块中心隐藏该卡片，直接访问 URL 会被路由守卫拒绝。这是预期行为，不是缺陷。
3. **样例 transport 的分页与聚合在内存中完成**：正式接口必须由服务端做过滤、分页与全量聚合（规格 11.2）；样例只保证前端契约一致。
4. **未接入 TanStack Virtual**：本次列表使用语义化表格 + 容器横向滚动，尚未做 2000 行虚拟滚动验证；规格 6.8 建议长表复用既有虚拟化。
5. **未做屏幕阅读器实机走查**：只做了静态语义审查（role/aria/焦点管理）与键盘路径实现。
6. **未在真实打印机/采集器上验证任何能力**：机台能力、心跳与遥测全部为合成样例。
