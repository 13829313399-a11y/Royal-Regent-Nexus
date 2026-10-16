# 华康 C 裁床部 P4b 首批：内部月结与锁月

对应方案：[第 16.2 节 P4b 首批](huakang-c-cutting-module-plan.md#p4b-首批内部月结与锁月)。

## 交付范围

- 按裁床部整月编制，包含本厂及外发的我方物料、实绩和材料费用。已结束自然月才可编制；P4a 实时核对继续保留。
- 首期回放更早有效事实并确认期初；后续连续承接上期冻结期末。月末按原实发确认累计完工正常耗用，余数为在制，不能引用今天的归集代替月末确认。
- 主管编制并提交，会计独立复核锁月。退回、反结、更正后重结均留历史；从最近已锁月份逐月反结，必须填写原因。
- 缺价、未核清物料／公共耗料／期初、待处理日报更正草稿阻止正式提交和锁月。跨月未收回、未签收及计划差异须明确核对，不凭计划增加实绩。
- 分币种、原单位、原实发核算费用，损耗单列，分位余差保留在制。冻结数量、金额、来源及操作人，历史快照不随改价或更正改变。
- 已锁期间及其期初事实不能补改，原批次成本被已锁月引用时须先反结。正常未锁月份业务继续办理。
- 历史最早已锁月份固定连续起点；即使全部反结，也只能从最早待重结月份顺序办理。若旧版本已形成较后月份锁定、前月缺口，先从最近锁月逐月反结，再重结，不修改旧事件。
- 月结依据只核对本月、期初、相关计划和原单更正及引用价格；无关工厂流水、下月正常入库／退料／填数／耗用不再误拦截。原始流水版本与后续追溯仍保存在快照，不能据此认为历史快照被实时更新。旧草稿需保留数量刷新依据并重新保存一次；旧待复核版本须先退回，再重新编制提交。
- 客户／订单号／货号／货名筛选仅控制明细显示，不缩减保存范围和整月金额。逐实发核对完工、在制、损耗、余料金额及原批次凭据；与上一编制版本比较，提交／锁月操作不成为重复的比较基准，缺价和换币种不冒充零费用差额。
- 冻结及历史快照使用保存时价格、计划和依据，不再混入 P4a 的尚未冻结警告或当前归集待办；旧快照通过展示兼容处理，原始内容不改写。

## 岗位权限

以下均限定华康 C，并要求 `cutting_ops:read` 与 `cutting_ops:cost_read`。

| 岗位 | 独立操作权限 | 范围 |
| --- | --- | --- |
| 裁床主管／生产部 | `cutting_ops:period_prepare` | 编制和提交 |
| 会计部复核人 | `cutting_ops:period_lock` | 复核锁月或退回；不得是该版本编制／提交人 |
| 会计部反结授权人 | `cutting_ops:period_reopen` | 按顺序反结，必须有原因 |

不自动授予员工权限。仅 `development` 环境的现有 `user-admin`，在明确设置 `CUTTING_PERIOD_ADMIN_ACCEPTANCE=true` 时可验收两个岗位，快照记录该例外；不能作为正式双人复核验收。

## 部署及本地验收

- 新增 `20261015_0163`，父版本 `20261015_0162`。增加 `cutting_ops_period_events` 和不可改删保护；启动不自动创建，迁移缺失时页面提示未启用。
- 迁移汇合版本 `20261016_0164` 的父版本为裁床 `20261015_0163` 和远程纸箱 `20261016_0163`；合并节点不执行 DDL，不改写已应用历史。标准迁移链从任一分支升级到 head 时，只补另一分支尚未应用的迁移；纸箱分支会增加可空的 `quantity_rule_json` 列。此代码汇合不代表本地或生产数据库已升级到该合并节点。
- 旧环境无月结表时继续原有业务；存在月结表但保护不完整时失败关闭。
- 标准已版本化数据库按实际迁移链升级。当前本地数据库历史 Alembic 标记不完整，不能盲目 stamp 或全链升级；应先备份，在副本验证仅增加 0163 对象且原表不变，再独立应用该迁移，保留原版本标记。
- 不在本地业务库造订单、领料、费用或正式锁月。完整流程与并发使用隔离测试库。
- 本地已按上述流程独立应用 0163：备份位于 `D:/RR/.tmp/p4b-migration/before-0163-20261015-191016.sqlite`，演练及实际迁移均保留原 203 张表结构与 2042 行原数据，完整性检查为 `ok`。没有修改原 Alembic 标记，不能据此声称已完成全链升级。
- 本地前后端现已运行，admin 真实会话 `/access` 返回 `periods_schema_ready=true` 及三项月结权限；2026-09 月结读取及编制依据均返回 200、空台账、未编制。本次验证未保存或锁定任何业务月份。开发启动脚本显式开启 admin 双岗位验收开关，正式环境不得沿用该例外。

## 自动化验证

- 合并远程 main 并加入 `20261016_0164` 后：迁移、月结、并发及真实会话权限回归 75 项通过，2 项 PostgreSQL 用例跳过；三个迁移起点均汇合到单一 head。构建和测试类型检查通过。裁床及公共 HTTP 前端回归先有 184 项通过、2 项首次加载超时；构建结束后独立重跑 `masterProtection.spec.ts`、`orders.spec.ts`，47 项全部通过（命令临时设置 `--testTimeout=30000 --hookTimeout=30000`，未修改测试断言或项目超时配置）。
- `npm run build`：通过，包含帮助资料证据检查、应用类型检查、主应用及图片翻译构建。
- `npm run typecheck:test`：通过。
- `npm run test:unit -- src/features/cutting-operations/__tests__ --maxWorkers=2`：14 个文件、171 项通过。首次全量并发有 4 项旧用例超时，限制工作进程后全部通过，未放宽用例时限。
- 最后统一历史追溯为“取数时生效记录”后，`period-review.spec.ts`、`periods.spec.ts`、`closing.spec.ts` 23 项再次通过，并重新完成构建。
- `python -m pytest tests/test_cutting_periods.py tests/test_cutting_period_concurrency.py tests/test_cutting_session_auth.py tests/test_cutting_closing.py tests/test_cutting_reporting.py tests/test_cutting_materials.py tests/test_cutting_usage.py tests/test_cutting_migration.py -q -p no:cacheprovider`：173 项通过，2 项专用 PostgreSQL 用例因环境未配置跳过，不能视为 PostgreSQL 验收。
- 随后追加 `python -m pytest tests/test_cutting_periods.py -k future_only_plan -q -p no:cacheprovider`：1 项通过，验证只改下月计划不误拦截、改变本月计划仍要求重新核对。
- 实现完成后单独复查连续重结、月度依据投影、成本读取边界、原操作重试／封存、旧快照不变、舍入和分币种差额。回归覆盖全部反结后重结顺序、旧缺口修复、相同数量原单更正、期初变更、未来正常业务、锁月与改价／实绩并发、草稿刷新与实际撤权恢复、筛选不漏保存、历史冻结提示及版本差异。

## 核心人工验收

1. 主管选择已结束月份，逐原实发核对期初及月末正常耗用、合格套数、完工归属；声明物料和期初完整，保存草稿后提交。
2. 会计使用独立账号核对分币种费用、生产／外发、领退耗存及原单历史后锁月；主管或同一编制人不得代锁。
3. 尝试旧月补报、移动旧单日期、耗用更正、撤签、旧月退料冲销与原批次改价，均应被阻止；当前开放月份的正常退料应允许。
4. 下一月份承接冻结期末；跳月应拒绝。已有后续锁月时，须从最近月份逐月反结；全部反结后仍只能先重结历史起点月份，后月不能抢先。
5. 反结后更正并重新编制／提交／锁月，旧快照仍能独立查看；断网、重复点击和超时核对不重复写入。上一编制版差异需显示数量、同币种金额、凭据和原编制人。
6. 编制时查询其他订单或翻页不丢月结草稿；刷新依据保留数量并重置声明。实际撤销成本权限后隐藏费用和草稿数据，重新授权可恢复填写并读取新依据；仍可核对自己的未知操作结果，迟到响应不能恢复旧数据。
7. 草稿后新增无关入库及同订单下月退料、填数、耗用，仍可按原本月依据提交锁月；本月补录、移动旧单日期、同量更正和所引用批次改价必须拦截并要求重新编制。
8. 筛选客户、订单或货名后，检查整月汇总不变、保存仍包含全部实发；清空筛选可恢复所有填写。旧锁月版本不显示尚未冻结或当前价格，定位链接明确打开当前业务记录。

## 当前边界

- 系统外未录入的期初库存／在制仍需专门录入依据，本批仅识别并阻止带缺口锁月。
- 尚不包含外发加工费对账、应付／付款、公共耗料或损耗分摊、跨期调整单、报表导出。
- 真实员工双岗位、生产环境迁移、大历史量性能及专用 PostgreSQL 并发需要单独验收；工厂全量回放保留既有性能限制。
- 通过隔离用例与本地空台账检查不等于真实岗位及现场正式验收。

## 代码与文档入口

- 月结顺序与命令：[cutting_periods.py](../../backend/app/services/cutting_periods.py)；月份依据投影：[cutting_period_evidence.py](../../backend/app/services/cutting_period_evidence.py)；精确版本差异：[cutting_period_review.py](../../backend/app/services/cutting_period_review.py)。
- 月结表单与草稿保护：[CuttingPeriodClosing.vue](../../src/features/cutting-operations/CuttingPeriodClosing.vue)；复核明细：[CuttingPeriodReview.vue](../../src/features/cutting-operations/CuttingPeriodReview.vue)；查询加载与历史快照展示：`CuttingClosingPage.vue`、`CuttingClosingReport.vue`、`CuttingClosingTrace.vue`。
- 类型及筛选展示：`periodApi.ts`、`periodDisplay.ts`、`closingApi.ts`；回归：`backend/tests/test_cutting_periods.py`、`periods.spec.ts`、`period-review.spec.ts`。
- 当前业务规则同步维护在 `PROJECT_MEMORY.md`、本模块方案第 16.2 节和 `shared/assistant-help/modules/customer-orders.json`。
