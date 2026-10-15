# 华康 C 裁床 P4a：月结前核对验收

## 当前范围

月结工作区按订单、上海时间自然月提供实时核对。未锁月补录及更正按最新有效业务日期重算，原单、替代关系和取数时间保留。当前月只核对到当天，不接受未来月。完整方案见 [P4a 实施边界](huakang-c-cutting-module-plan.md#p4a-首批月结前核对)。

| 视图 | 已实现口径 |
| --- | --- |
| 生产与外发数量 | 期初累计、本期计划／合格完成／交接、期末累计与未交接；散片、不良、报废另列；外发自报、收回、验收独立，合格完成取验收 |
| 领退料及耗用 | 按原实发及原单位核对期初现场余料、实发、签收、退仓、正常耗用、损耗、期末余料和已发未签 |
| 材料费用试算 | 独立成本读取权限；原批次当前价、累计舍入额差分、币种分列、缺价待核对；当前归集状态与历史月末在制区分 |
| 来源及更正追溯 | 期初形成依据、本期发生与更正筛选；原生产／耗用单、草稿、生效／作废、替代关联、任务／执行方／物料／单位、操作者与日期；仓库关联全期间流水不混入本期数量 |

计划采用当前发布版本，明确填零不计漏报；该版本并非历史月末冻结计划。计划失效沿用排期区判断，明确提示重新核对、计划及漏报仅供参考，实际产量仍按生效记录。外发自报未收回和收回待验收分别按任务提示数量。当前有效签收与退仓核对现场保管量，不等于重新计算整个布料仓库存。普通读取不返回批次价格、费用或成本确认凭据；费用读取沿用 `cutting_ops:read` 与 `cost_read`（生产或 PMC／仓库）边界，不新增权限或自动授权员工。

待办和原单链接直接读取有权限的订单，保留核对月份并定位任务、实发、生产／耗用原单或仓库关联流水；定位仅展开和突出显示记录，仍需用户主动选择业务操作。查询参数切换保留未保存内容和结果未知保护，迟到响应不得覆盖新订单；403／404 清除旧订单，返回入口恢复原核对月份，手动查询不受链接限制。原单已移除或不可见时保留明确定位提示。

## 验证重点

1. 前月裁片、当月配套及外发跨月收回／验收，不把自报或交接重复计为合格完成。
2. 补录、更正草稿、生效更正、撤销及关联退仓；核对旧单可见、有效数量不重复、期初＋本期收支＝期末。
3. 原实发金额跨月的半分舍入、明确零价、缺价、不同币种及调价；本期金额等于同一当前价下期末累计舍入金额减期初累计舍入金额。
4. 普通读取不含费用；真实 Cookie 会话中跨厂／部门拒绝、显式禁止、成本权限撤销，以及前端 401／403 后缓存清理。
5. 切换月份、订单、工作区时迟到响应不能覆盖新选择；取数与批次调价并发时返回同一版本的费用及依据。
6. 期初完成／余料非零时提供形成依据，跨月生产日期更正、耗用替代及后续作废保持原单关联，数量不重复计算；作废／抽查记录不渲染空白耗用或盘余。
7. 定位不依赖订单列表第一页；同页参数切换、手动查询、无权限／不存在目标、成本独立授权及未保存内容拒绝离开均有回归。

## 尚未交付与部署边界

本批没有数据库迁移、业务写入或员工授权。已启用 P3b 的本地服务需加载新版 API 和前端；缺少 0155／0156 证据保护时明确拒绝查询。自动测试使用隔离合成数据，不能代替真实岗位、订单或盘点验收。

正式月末在制结转、公共耗料／损耗分摊、冻结快照、锁月／反结、外发加工单价与应付、税费、付款核销及全厂批量月结尚未实施。后续需要确认复核岗位、锁月顺序、调整规则和外发计价口径。当前全厂历史回放及成本读取重复回放存在大历史量性能限制；专用 PostgreSQL 并发与真实数据验收仍需开展。

## 当前验证结果

- `backend/.venv/Scripts/python.exe -m pytest tests/test_cutting_closing.py tests/test_cutting_session_auth.py tests/test_cutting_usage_concurrency.py -k "closing or monthly_preview" -q -p no:cacheprovider --basetemp <新的工作区临时目录>`：21 项通过，1 项专用 PostgreSQL 月结并发用例因未配置环境跳过；不计为 PostgreSQL 已验收。涵盖计划失效、外发未收回／待验收、期初依据及跨月更正、金额与实物口径、真实会话权限和价格并发。
- `npm run test:unit -- src/features/cutting-operations/__tests__ --maxWorkers=1 --testTimeout=30000 --hookTimeout=30000`：12 个文件、158 项通过。
- `npm run typecheck:test`、`npm run build`、帮助资料一致性及 `git diff --check` 通过。
- 本地前端与 `/health` 返回 HTTP 200，OpenAPI 已包含 `closing-preview`；浏览器现有登录会话显示 P4a 月结前核对、自然月选择和真实空订单列表。当前无已下发裁床订单，未向业务库注入样例，不替代真实业务验收。

## 主要改动文件

- 后端：`backend/app/services/cutting_closing.py`、`backend/app/api/cutting_operations.py`。
- 界面与接口：`src/features/cutting-operations/CuttingClosingPage.vue`、`CuttingClosingReport.vue`、`CuttingClosingTrace.vue`、`closingApi.ts`；`CuttingLocationNotice.vue`、`location.ts`、排期／物料／填数／费用页面和关联明细定位标识；`routes.ts`、`navigation.ts`、`workspace.css`。
- 回归：`backend/tests/test_cutting_closing.py`、`test_cutting_usage_concurrency.py`、`test_cutting_session_auth.py`；`src/features/cutting-operations/__tests__/closing.spec.ts`、`navigation.spec.ts`。
- 方案与帮助：`docs/business/huakang-c-cutting-module-plan.md`、本清单、`PROJECT_MEMORY.md`、`shared/assistant-help/modules/customer-orders.json`。
