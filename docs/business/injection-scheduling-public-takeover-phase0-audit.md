# 注塑排产公共接管：阶段 0 审计与阶段边界

日期：2026-08-05
范围：阶段 0 历史现状审计，以及阶段 1 Profile/Canonical 数据合同输入。本文中的缺口和阶段划分保留为设计基线；当前实现状态以代码、迁移和 `PROJECT_MEMORY.md` 为准。

## 1. 样本完整性

华康 B 只读样本：`华康B啤机日排表新6.2(1).xlsx`

- 大小：7,209,842 bytes
- SHA-256：`7622eb28d230bc0e4a6f5501c3b6f1910ce3fda2685cf6f49093b24867023eab`
- 审计前 UTC mtime：`2026-06-04T02:32:02.7060824Z`
- 审计方式：只读 ZIP/XML 解析；不使用 Excel 重算，不保存或改写源文件。

## 2. Sheet role 对照

| Canonical role | 华兴 Profile | 华康 B Profile | 首期写入当前计划 |
| --- | --- | --- | --- |
| CURRENT_PLAN | 计划表 | 排期表 | 是 |
| COMPLETED_HISTORY | 已啤记录年度表 | 已啤完 | 否，仅识别/统计 |
| MACHINE_COMPLETION | 机台完成时间 | 机台完成时间 | 否 |
| OUTSOURCED_PLAN | 可选 | 外发2 | 否，仅识别/统计 |
| CANCELLED_ORDER_HISTORY | 可选 | 取消订单 | 否，仅识别/统计 |
| SHIFT_HISTORY | 每班啤数记录 | 每班啤数记录 | 否 |
| MACHINE_MASTER | 华兴机器设备 | 厂区现有啤机 | 仅差异预览，不由普通导入写权威主数据 |
| MOLD_MASTER | 机安 | 无，读取系统厂区模具主数据 | 仅差异预览 |

华康 B 实测 Sheet：`排期表`、`已啤完`、`机台完成时间`、`外发2`、`厂区现有啤机`、`取消订单`、`转模、转色统计表`、`每班啤数记录`。标题文字出现“华康 D”不能覆盖用户选择的厂区作用域，只能产生显式警告。

## 3. 核心字段矩阵

| Canonical field | 华兴 | 华康 B | 权威类型 | 当前旧模型持久化 | 阶段 2 建议持久化 |
| --- | --- | --- | --- | --- | --- |
| machine_code | B | B（A/B 重名，精确取 B） | BASELINE_DECISION | Task.machine_id | Task + lineage |
| item_no | J | E | SOURCE_FACT | Order.item_no | PlanOrderState + source snapshot |
| mold_no | G | G | SOURCE_FACT | Order.mold_id | Order/overlay + lineage |
| product_name | H | H | SOURCE_FACT | Order.product_name | PlanOrderState |
| order_no | I | I | SOURCE_FACT | Order.order_no | stable order identity |
| warehouse_text | AR | J | SOURCE_FACT | 未完整持久化 | overlay/source snapshot |
| order_quantity | L | L | SOURCE_FACT | Order.order_quantity | PlanOrderState |
| completed_quantity | M | M | SOURCE_FACT | Order source/completed | immutable takeover watermark |
| shift_target_quantity | O | AN | SOURCE_FACT | Order/Task target | overlay + calculation input |
| daily_target_quantity | 无 | O | SOURCE_FACT | 无 | source snapshot/structured field |
| material_name | S | P | SOURCE_FACT | Mold 部分字段 | overlay/source snapshot |
| sprue_ratio | P | Q | SOURCE_FACT | 无 | source snapshot |
| color_name | Q | R | SOURCE_FACT | Mold 部分字段 | transition input/snapshot |
| color_powder_code | R | S | SOURCE_FACT | 无 | source snapshot |
| planned_start | AG | AE | BASELINE_DECISION | Task.planned_start | locked baseline + lineage |
| planned_finish | AH | AF | BASELINE_DECISION | Task.planned_finish | locked baseline + lineage |
| requires_spray_paint | AL | AK | SOURCE_FACT | 未完整持久化 | structured source fact |
| remark | AS | AT | SOURCE_FACT | 部分 | overlay/source snapshot |
| required_arm_type | AU | AU | SOURCE_FACT | Mold 部分字段 | eligibility snapshot |
| required_fixture_type | AV | AV | SOURCE_FACT | Mold 部分字段 | eligibility snapshot |
| AW:DF/动态班次 | Profile 定义范围 | AW:DF | 来源诊断 | 无 | 只保留参与映射的 lineage；不逐格永久复制整表 |

完整字段、类型、单位、转换器和权威类型由 `CANONICAL_FIELD_CATALOG` 控制；Profile 只能引用声明式转换器。

## 4. 华康 B 实测盘点

- 主表表头行：第 3 行；A/B 都显示“机位”，Profile 必须用列坐标和重复序号消歧。
- 计划相关关键列：E 货号、G 工模、I 单号、J 仓库、O 计划日目标、AN 每班计划啤数、P/Q/R/S 材料与颜色、X/Y/Z 日期、AE/AF 计划窗口、AK 喷油、AT 备注、AU/AV 手臂/夹具。
- `排期表` 解析到 4,022 个公式单元格；当前安全 XML reader 口径下 197 个公式错误缓存、65 个缺失缓存。该口径与 Excel UI 的“可见错误值”统计不同，不混为同一个指标。
- 原始结构审计识别约 493 个订单候选行和 79 个机台标题候选。Canonical 分类必须在 Profile 映射及厂区主数据校验后重新计算。
- 旧硬编码解析器对该文件得到 0 机台、0 模具、0 任务、5 个阻断问题，证明固定“计划表/华兴机器设备/机安”不是公共契约。
- 公式错误影响 SOURCE_FACT/BASELINE_DECISION 必填字段时阻断该行；系统派生/兼容展示字段只给诊断 warning。存在已排证据但 AE/AF 不可信时进入 INVALID，不能降级为 BACKLOG 或伪造时间。
- `completed_quantity > order_quantity` 固定为超产 warning，允许导入并按完成处理；欠数下限为 0，真实完成率允许超过 100%。旧确认合同仍阻断超产，必须在阶段 2 一并改造并加回归。

## 5. 阶段 0 审计时的实现缺口

- 导入确认按文件 hash + source row 建身份，并会隐式创建机台/模具；不满足稳定业务键和普通 import 权限边界。
- 导入任务为 `locked=False`，基线可被后续自动排产移动。
- 全局 Order 同时被 DRAFT/PUBLISHED 共享；草案导入可能污染执行计划的订单状态和进度。
- current-plan 读取优先 DRAFT，可能遮蔽仍在报工的 PUBLISHED。
- heuristic/CP-SAT/projection 中存在 `order_id -> task` 单值映射，多 split 会被覆盖。
- rollback/successor 没有完整复制 import/Profile/stable split 来源链。
- duration/projection/手工调整/自动排产未共享同一 calculation version、日历搜索和 continuation anchor。
- 前端单一 `plan` slice 未显式区分 executionPublishedPlan 与 planningDraftPlan。
- 没有 Profile 感知导出、ExportAudit、签名 manifest 或安全往返。

## 6. 已确定的职责边界

- 普通 `import`：只能使用当前厂区 ACTIVE Profile 预览；阶段 2 只允许向 planning DRAFT 执行安全动作，不能创建权威主数据或修改 PUBLISHED。
- `manage_import_profiles`：Profile 新建、修订、审核、激活、停用、厂区绑定。ACTIVE revision 被引用后不可原地修改或删除。
- `manage_master`：独立审批/补录主数据；审批后原批次在安全保留期内重新识别，普通文员不得绕过。
- `publish`：改变锁定基线、解锁、插入基线之前、发布/回滚及 successor rebase；必须带原因和审计。
- 总经理不因职位名自动获得 `manage_import_profiles`；需要明确授权。文员获得 `export`，主管/经理继承并获得 Profile 管理。

## 7. 阶段 2 持久化与锁顺序方案

建议新增：

1. `PlanOrderState`：`plan_id + order_id` 唯一，保存订单量、交期、takeover progress baseline、状态、calculation version、revision。
2. Task/split：稳定 `stable_row_key/split_key`、`allocated_quantity`、`quantity_scope`、Profile/source lineage、`origin=excel_baseline` 和导入基线锁。
3. `ProgressAdjustment`：只追加、不覆写；与 ShiftReport 增量及 takeover watermark 分开累计。
4. successor：保存 based_on PUBLISHED snapshot、report/event watermark；clone/rollback 复制完整 lineage 和 inherited counter。
5. `UploadArtifact`：随机存储键、factory/uploader scope、hash、大小、格式、TTL、清理状态；不提供通用下载/执行。

确认/发布锁顺序固定为：factory scope → target plan（`SELECT ... FOR UPDATE`）→ referenced published snapshot/event watermark → plan-order overlays（稳定键排序）→ tasks/splits（稳定键排序）→ reports/adjustments watermark → import batch revision。锁内重算 mapping/action/calculation fingerprint；任一 revision 或水位变化返回 409，不覆盖。

## 8. API 与测试阶段划分基线

- 阶段 1：Profile registry、ACTIVE 厂区绑定、mapping preview、Canonical Model、未知/漂移模板状态及 Huaxing/Huakang B parser contract。
- 阶段 2：可恢复批次、主数据审批、action preview/confirm、stable reconciliation、PlanOrderState、锁定基线、双计划读取、successor/rebase/rollback。
- 阶段 3：统一计算、task/split freeze、continuation anchor、manual append preview/confirm、heuristic/CP-SAT 对齐。
- 阶段 4：前端导入向导、双 plan slice、动态详情与权限/fallback UX。
- 阶段 5：source-compatible/system-standard 导出、ExportAudit、签名 manifest、篡改/跨厂/stale/round-trip 测试。

每阶段先通过迁移、后端契约与回归，再进入下一阶段。真实样本始终只读；confirm 使用独立脱敏小 fixture 和隔离数据库。
