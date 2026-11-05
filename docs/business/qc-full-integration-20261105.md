# QC 完整系统集成：审查与发布约束

核验日期：2026-11-05。基线为实际 fetch 后的 `origin/main`：`8330f7d2ed018498800bc8f00c5db25216cd95cc`。

## 集成范围

完整核对 QC 前端、网关、服务、数据模型、排期解析/导入、照片与附件、审核/反审核、历史导入、工作簿和报表。133 项源码/关联文件清单中，112 项在日常版本与 main 已相同；原有完整 QC 系统已在 main 中，本次融合尚未发布的差异，不重新实现已有业务。

保留 main 的共享路由、权限网关、其他部门代码、依赖、数据库模型及迁移。日常目录只读；独立 worktree 基于最新 main。没有整项目覆盖，也没有合并冲突。

### 原 16 文件的处理

| 文件 | 最终处理 |
| --- | --- |
| `backend/app/services/qc_inspection_sheet.py` | 日期组：开放普通验货台 actualDate 最小补丁、确认快照、冻结读取；增加异常快照校验调用 |
| `backend/app/services/qc_inspection_summary.py` | 日期组：确认时决定日期、兼容历史读取；增加异常/降级保护 |
| `backend/app/services/qc_workflow.py` | main 原样保留；日常差异仅空白 |
| `backend/tests/test_qc_actual_date.py` | 日期组：新增日常版 33 项参数化验收 |
| `backend/tests/test_qc_round5.py` | 日期组：仅更新新确认记录的业务日期预期 |
| `services/qc-department/app-safety.test.js` | main 原样保留，未削弱安全/DOM 检查 |
| `services/qc-department/app.js` | 导航文案组：“统计中心” |
| `services/qc-department/index.html` | 导航文案组：“工作台”分组、统计中心位置 |
| `services/qc-department/mobile.css` | main 原样保留，保留 16px 移动输入修复 |
| `services/qc-department/qc-inspection-sheet.css` | 日期组：日期单元格样式同时覆盖验货台 |
| `services/qc-department/qc-inspection-sheet.js` | 日期组：实际日期输入、最小保存补丁和提示 |
| `services/qc-department/qc-inspection-sheet.test.js` | 日期组：原日期测试及新增“日期+照片队列立即提交” |
| `services/qc-department/qc-inspection-summary.js` | 日期组：最终验货日期与来源展示/筛选 |
| `services/qc-department/qc-inspection-summary.test.js` | 日期组：来源四态与导出筛选契约 |
| `services/qc-department/qc-schedule.js` | main 原样保留；日常差异仅空白 |
| `src/router/index.ts` | main 原样保留；QC 路径无需改动 |

上述 9 个日期文件作为一个依赖组交付。另新增 `backend/tests/test_qc_date_compatibility.py`，覆盖异常快照、合法清空、历史混合、跨进程恢复、双 HTTP 客户端冲突及部分审核重试。

清单外手工融合：`shared/assistant-help/modules/qc-inspection.json` 的日期帮助与源码 SHA-256，`PROJECT_MEMORY.md`、`DESIGN.md` 的 QC 契约，以及 `docs/business/qc-department-integration.md` 的开发/发布目录边界。保留 main 帮助中的退回、照片、通知时序说明及其他部门内容。

## 日期数据流与兼容性

1. 验货台通过现有 `/inspection-sheet/entries/{id}/save` 保存 `inspectionExecution.actualDate`，只开放此执行字段；沿用 revision、身份和厂区校验。省略字段不清空已有值。
2. `sheet.save` 合并执行补丁到现有 JSON 存储，来源计划、报告号、照片和任务 ID 保持原义。
3. 只有显式 `review_batch(..., 'confirm', ...)` 调用 `summary.resolve_inspection_date`：有效人工日期 → 任务捕获的计划开始日 → 空。来源分别为 `qc_manual` / `schedule` / `null`。不会把补位值写入人工输入。
4. 同次确认事务写入 confirm 事件、`approved_snapshot`、汇总 payload 及 SQL `inspection_date`。反审核保留历史，重新确认重新决定日期。
5. `summary.confirmed_date` / `review_item` 按冻结快照读取。无来源标记的历史记录沿用原 actualDate 规则；不会按今天或新计划补造历史日期。
6. 有标记但无有效日期/来源组合时返回 409，保留原证据；已有新汇总被无标记旧审核快照替换时同样拒绝。显式清空后重新审核仍可合法产生计划补位或空值，不能把它误判为损坏。

源码入口：`backend/app/services/qc_inspection_sheet.py` 的 `save`、`unpack`、`review_batch`，`backend/app/services/qc_inspection_summary.py` 的 `resolve_inspection_date`、`confirmed_date`、`review_item`、`upsert`、`reconcile`。测试直接核对真实 SQLite JSON、事件、SQL 日期列及 Excel 字节，不只检查字段存在。

**不需要新增数据库结构迁移。** 两个服务的 SCHEMA、`migrate_review` AST 与 main 相同；模型、schemas、Alembic 目录无差异。变化是既有 JSON 快照的语义契约。

## 验收矩阵

测试数据均位于独立测试目录/数据库；浏览器访问生产构建的本机预览和隔离后端，未访问生产业务数据。以下通过项指隔离验收，不代表线上验收。

| 组 | 结果与证据 |
| --- | --- |
| T01 新增实际日期 | 通过：`test_date_decided_only_on_confirmation_and_recovered_verbatim`；浏览器 A 录入 11-06，刷新/API/SQLite 均保存 |
| T02 修改、快速输入、冲突 | 通过：Node 日期队列测试、双 HTTP 客户端旧 revision 409；浏览器 C 从 11-06 改 11-08；照片队列立即提交测试 |
| T03 清空人工日期 | 通过：`test_clear_override_preserves_other_execution_source_and_audit`，其他执行字段及来源保留 |
| T04 立即提交与审核补录 | 通过：新增 Node 日期/照片队列提交测试；HTTP 持久化确认；浏览器审核补录、退回、重提 |
| T05 计划补位 | 通过：人工空保持为空，最终日期 11-05/schedule；SQL、详情及实际下载一致 |
| T06 等值、闰日、全缺失 | 通过：人工等于计划仍 qc_manual；2028-02-29；不使用走货/结束/当前日 |
| T07 批准锁定和反审核 | 通过：已批准写入被拒；同 ID，旧快照/事件保留、汇总撤下 |
| T08 重审和请求重试 | 通过：11-05/schedule → 11-09/qc_manual；浏览器和回滚候选均执行；重复请求不重复事件 |
| T09 清空后重审 | 通过：有计划转 schedule，无计划转空/null；新增两项持久化测试 |
| T10 冻结与重启 | 通过：原计划冻结测试、独立进程恢复；浏览器刷新/重新登录/深层路由保持数据 |
| T11 筛选、详情与导出 | 通过：混合来源筛选/排序/分页测试；浏览器下载 Excel 实物 26 列、4 行，日期 11-05、11-06、11-06、11-09 |
| T12 schedule 查询契约 | 通过：`test_summary_schedule_date_is_read_only_filter_sort_detail_and_export`；原查询能力保留 |
| T13 真实旧历史 | 通过：原 main 进程创建空/非空历史，切新版本反复读取；无标记与原空值保留 |
| T14 新旧/导入混合 | 通过：旧提交/工作簿原回归，加新增混合历史导入、人工、补位、旧空/非空持久化用例 |
| T15 缺失投影恢复 | 通过：仅删除隔离投影，跨进程且禁止 resolver，仍从批准快照恢复；重复读取幂等 |
| T16 原始旧后端读取 | **已复现不兼容，不能作为通过项**：旧 main 把新补位日期写空，但原批准快照仍完整；切新读取器恢复 |
| T17 兼容回滚交接 | 通过数据契约演练：保留两后端日期文件及新汇总 JS 的候选；7 个进程阶段验证新→旧→恢复→兼容回滚→重审→新，回滚汇总 UI 13 项测试通过。尚非生产部署包验收 |
| T18 失败原子性与部分重试 | 通过：注入 upsert 失败无半确认；双 HTTP 客户端批次一项冲突、一项成功；同 requestKey 不重复确认 |
| T19 非法输入、身份、厂区 | 通过：非法日期/额外字段被拒；真实网关角色/厂区测试；浏览器 QC 账号无报价读取权限，管理员可正常打开 |
| T20 前后端版本配对 | **混用原始旧后端不兼容**：新日期补丁 422；兼容后端接受无执行补丁的旧请求且保留已有日期。前后端须成套交接 |
| T21 异常快照 | 通过隔离异常用例：7 类畸形标记返回 409、旧投影不变；丢标记降级被拒；缺 approved_snapshot 可只读定位，不猜测日期。线上是否存在异常未调查 |
| T22 完整 QC 回归 | 通过 QC 自动化：PASS/FAIL/PENDING/LG、照片/报告/历史/导入/撤销/导出/退回重提；浏览器华兴 1 条待验、华登 0 条、集团不加载；桌面 64px 行与冻结列、移动日期输入 16px |
| T23 其他部门 | 页面基本回归通过；自动化存在下述 main 可复现失败，不能标为全绿 |

主要自动化入口：`node --test *.test.js server/*.test.js`、`pytest tests/test_qc*.py -q`、`npm run typecheck:test`、`npm run build`。完整生产构建包含 Vue 类型、Vite 与 Node 24 图片翻译子项目；帮助指纹校验通过。依赖锁与 main 一致，复用已安装依赖；没有声称本轮重新 npm ci。

QC Node 最终 278 通过；QC 后端最终 283 通过。Vue 选定 19 文件共 502 项：500 通过、2 失败；同两失败在干净 main 副本复现。其他部门后端选定 66 项：43 通过、23 失败；23 项纸箱文件处理失败在干净 main 的同一测试文件完整复现（另 1 项通过）。没有删除测试或降低断言。

已有失败：`src/router/__tests__/systemPermission.spec.ts` 与 `src/views/__tests__/internalQuoteDeskLayout.spec.ts` 的源码字符串断言；`backend/tests/test_carton_schedule_batch.py` 的 23 项在文件导入阶段得到 422“纸箱文件超出处理资源限制”。相关业务源码/测试未被本次修改。不能由此承诺完整 main 测试全绿；需要负责人确认现有问题处理安排。

## 发布与回滚门槛

本 PR 仅供人工审查。未合并 main，未触发生产部署或完成线上验收。现有 main 回归失败及生产数据/部署拓扑未验收，因此不宣称可直接上线。

- 前后端同批切换，避免新前端连接旧后端；所有进程/后台任务/导出任务须核对实际版本。
- 上线前在一致备份副本只读预检。批准记录缺快照可用 `entry_details` 中 `flow_version=2 AND review_state='approved' AND coalesce(approved_snapshot,'')=''` 定位；带标记快照逐条核对日期和来源组合。任何异常应记录 entry_id 与原因，人工核对，不批量回填。
- 尚未产生新快照时可以撤回功能代码。已经产生新快照后，禁止将数据交给未改的旧 main，即使仅 GET/导出也会触发汇总重建。
- 兼容回滚必须保留两个后端日期文件的完整保存/确认/重审/读取逻辑，以及新汇总 JS；仅回退输入 UI 可行，但需使用实际部署产物重跑相应验收。本次候选仅完成隔离数据交接与汇总 UI 测试，未在生产环境执行回滚。
- SQLite 一致备份须覆盖验货、汇总、workflow/cumulative、主库和附件的关联恢复集合，并考虑 WAL/journal；本次未更改 journal 策略，未用单次事务测试宣称断电原子性。
- 缺失批准快照且无可核实历史凭据的资料不能安全自动恢复日期；保持证据，单独人工处置。
- 私有客户工作簿、累计模板、排期样例、业务库、照片和凭据均不提交；生产环境仍须按已有机制配置私有资源。
