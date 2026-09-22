# 本地实现与验收证据

核验日期：2026-09-22。当前交付为核心重建实现；**整份开发资料尚未全部验收，未生产启用**。原始资料只读，实际业务数据库、5173/8000服务、历史喷油迁移和表均未因本轮开发更改。

## 实现位置

- `src/features/spray-production/`：独立壳、七工作区、订单追踪、排期、报工/工时、材料、月结、人工导入及上下文隔离。
- `backend/app/api/spray_operations.py`、`backend/app/services/spray_ops/`：类型化命令、权限、生产/排期/交收/材料/工资/月结、来源解析和冻结导出。
- `backend/app/models/spray_ops.py`、`backend/alembic/versions/20260922_0119_spray_ops.py`：52张规范化新表、组合工厂外键、数量约束、迁移及启用检查。
- 现有文件仅接入路由、入口卡片、功能开关、ORM/迁移注册和权限目录；固定岗位不自动扩大授权。

## 自动验证

环境：本机 Windows / PowerShell，仓库 Python `.venv`、SQLite临时数据库、现有Node/Vite/Vitest依赖。所有后端测试均显式设置 `DATABASE_URL=sqlite://`，fixture另建隔离库。

```powershell
# backend 目录
$env:DATABASE_URL='sqlite://'
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_spray_ops.py tests/test_spray_ops_guards.py tests/test_spray_ops_imports.py tests/test_spray_ops_exports.py tests/test_spray_ops_migration.py tests/test_system_position_catalog.py -q --disable-warnings
```

最终结果：**55 passed，95.07秒**。覆盖：四厂12个方向的跨厂引用、所有授权模式、非法数量、SQLite竞争发布与部分结算、原请求幂等、准备/日历/DAG、条件计划、多列分摊、报工更正、跨月部分验收、原成本材料、未知成本补确认、实名工时历史保留、工资/费用/期间关闭、源证据、逐单导入去重及下载撤权。不能据此宣称开发文档所有验收ID均已覆盖。

此前导出断言曾失败：openpyxl回读不换行属性为None，而非False；已按实际语义改为falsey断言，同时修复数量/金额格式，最终全量通过。

```powershell
# 项目根目录
npm run build
npm run typecheck:test
npm run test:unit -- src/features/spray-production/__tests__/contextFence.spec.ts src/features/spray-production/__tests__/workspace.spec.ts
npm run test:unit -- src/views/__tests__/productionModuleEntry.spec.ts src/views/__tests__/moduleCenterFactoryScope.spec.ts
```

- 构建通过，最新Vite构建5.74秒；测试TypeScript检查通过。已有大包、依赖PURE注释及插件耗时警告，不作为零警告构建。
- 喷油上下文测试4条通过；工厂入口测试12条通过；生产入口测试4条通过、1条失败。
- 失败为既有销售报价文案断言，期望 `优先从上方 P4 v2 交接池直接转换`。`productionModuleEntry.spec.ts` 和 `QuoteCenterPanel.vue` 均经 `git diff --exit-code HEAD -- ...` 验证未改变；本轮未修改无关销售模块以迎合该断言。

迁移测试从前一head升级完整Alembic图，插入并保留旧喷油探针，核对旧表DDL/行数、52张新表、四厂协调行、重复升级、SQLite integrity/foreign_key结果。此测试不等于真实库迁移。

### 合并主线后的补充验证

合并客户报价主线后，喷油迁移调整为 `20260922_0119`，依赖保持原样的客户报价迁移 `20260922_0118`。迁移演练同时核对前一head全部既有表的DDL/行数，并确认客户报价探针仍保留；Alembic仅有一个head。权限目录为140个应用权限、133个业务权限，新喷油14权限仍不自动授予固定岗位。

上述后端命令额外加入 `tests/test_auth_api.py tests/test_customer_price_settings.py tests/test_internal_quote_buzzbee_handoff.py`：**142 passed / 756.48秒**。另运行 `tests/test_iam_api.py -k system_position_get_contract_is_code_locked`：**1 passed / 21 deselected**。

合并后构建通过（6.17秒），测试类型检查通过。前端另加入客户报价设置、来源面板、BuzzBee价格和其他报价转换器/客户范围测试：**65 passed / 1 skipped / 1 failed**；唯一失败仍为上文已有销售文案断言，相关测试和报价面板源码与主线一致。该既有失败没有作为喷油功能通过证据。

## 合成规模测试

```powershell
$env:DATABASE_URL='sqlite://'
$env:SPRAY_OPS_RUN_PERFORMANCE='1'
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_spray_ops_performance.py -q -s --disable-warnings
```

已运行，1 passed / 22.78秒。规模100资源、14天、2,000任务、10,000历史报工：分页报工p95 220.23ms，调度窗口p95 55.04ms，排期建议p95 725.02ms。仅限本机SQLite合成测试，不包含浏览器DOM性能、PostgreSQL或现场吞吐保证。

## 浏览器实际路径

独立后端8014、前端5184、临时QA库。使用合成账号与订单，不把样例参数写成正式工价。

1. 基础资源/工艺→登记 `QA-UI-00017`（货号00017、左件、灰色、1,000件）→接收来料1,000件。
2. 排期建议→比较预案→发布→自动喷线01开工→报工1,000件：合格950、待判30、报废20；正班800、加班200。
3. 登记实名工时8小时/加班2小时→明确0.82合成计件规则→试算→正式工资820 CNY。真实生产数量没有因人数重复。
4. 交付并验收900件→选择600件结算→冻结1,242 CNY（2.07/件）→待结300件。库存保留合格50、待判30。月结详情显示原送货单和订单，点击可追踪实绩。
5. 采购100KG，原价9.2 CNY/KG→收货100→领用20→耗用8（73.60）→退回原领用12；仓库92、车间0、累计耗用8。保存后刷新版本再开放下一笔操作。
6. 下载日报和请款文件；刷新页面后业务保留；订单关联入口按关系筛选。未保存交收和排期内容在取消离开/切厂时保留。

1920/1440/1366/1024/768/390宽度已检查，页面宽度无横向溢出；宽表内部滚动。≥1680订单追踪为392px停靠侧栏，较窄视口为模态；<1024排期切任务列表。最近浏览器错误/警告日志为空。截图只证明被截取状态，不能代替完整交互矩阵。

本地截图在 `%TEMP%/rr-spray-artifact-20260922/browser/`：`planning-docked-1920.png`、`passport-overlay-1440.png`、`reports-mobile-390.png`、`labor-editor-1440.png`、`settlement-1440.png`。保存到工作树内的临时文件会触发开发刷新，截图改存临时目录，工作树中的临时副本已清理。

## 导入与导出

12份原文件SHA-256一致；10个工作簿70张表和2个PDF共7页已读取/查看。解析保留14,338公式和385个缓存错误，不执行公式/外部链接。12个Profile的实现边界见IMPORT_PROFILES；未把真实历史业务导入QA或正式库。

9类XLSX均从隔离QA数据生成并逐张渲染查看：计划、日报、库存、采购、材料、交货、月结、请款、经营。日报另拆员工工时、当日工资。修复了超宽日报、数量换行、日期时区、单号/月份缺失及金额显示问题。文件保存中文表头、单位/币种、生成时点/修订、签名栏、重复表头、A4横向设置及公式注入防护。导出回归验证65行全量结果、7人560件守恒、冻结字节一致及撤权禁下载。

渲染预览工具对纯数字文本存在前导零显示差异；原XLSX用openpyxl回读验证`00017`仍是文本且格式为`@`。因此不能拿该工具渲染的`17`作为原文件值。渲染图位于 `%TEMP%/rr-spray-artifact-20260922/`，属于应用输出的版面检查，不是S02/S08原样模板金样。未运行Excel真实打印或PDF分页验收。

## 分开进行的代码检查与修复

由主代理在功能实现后重新检查守恒、权限、期间及交互失败路径；没有子代理或外部审计。修复并回归：跨月验收倒计前月、旧工资试算引用被工时修改破坏、暂停任务错误释放能力、未知原批成本无补确认路径、外币关账误按CNY缺项、订单关联过滤缺失、相同授权快照刷新销毁草稿、材料保存后下一笔读取旧版本，以及日报重复产量/过宽布局。当前已知未完成项列在下方。

## 未通过或未执行的项目

- 未配置独立PostgreSQL环境，未执行其迁移/行锁/并发压力测试。
- S04/S06复杂矩阵及其他来源跨行/跨表自动业务映射未完成；目前人工逐单映射，不能宣称历史全量自动接管。
- 原纸表/华B请款逐文件精确还原、全套打印金样和长文案跨页效果未完成。
- 多容量资源并发任务没有独立时间轴子泳道；全部错误/角色状态、200%真实浏览器缩放、屏幕阅读器、触屏及完整键盘等价流程未验收。
- 工资、工序价、交收价、汇率、SKU换算、班次产能、费用、期初和权限仍需业务确认；跨币种统一利润未实现，覆盖度不证明现场无漏报。
- 一项无关销售报价旧文案测试仍失败，详见上述命令结果。
- 未执行真实业务库迁移、生产授权、生产启用或部署。Git交付不等于生产启用。

启用和停用步骤见RUNBOOK；默认双开关关闭。上述限制解除前，不能把当前实现称为整包开发完成或正式财务验收通过。
