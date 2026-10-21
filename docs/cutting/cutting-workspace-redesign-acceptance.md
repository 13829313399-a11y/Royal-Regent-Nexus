# 裁床工作区界面改版与验收

## 范围与状态

按已确认的界面方案落地到 Vue 裁床模块。原六个业务区保留，并新增生产看板、操作日志；默认进入生产看板。使用布料仓式顶部导航，页头提供“华康 C”和“使用说明”。本轮已完成代码实现及隔离环境验证，尚不代表真实员工、真实业务资料或目标部署环境已验收。

原型中的示例数字已替换为后端只读查询。新增查询复用现有业务记录与权限；没有数据库迁移、权限自动扩张或原库接管操作。

## 页面与数据口径

| 页面 | 本轮实现 |
| --- | --- |
| 生产看板 | 按日期查询当日任务、已填报、未填报和异常任务；支持定位原订单、任务及历史业务日期 |
| 生产排期 | 按相同订单号／货号、办理状态、排期状态筛选的总订单笔数、已排期笔数、未排期笔数；分页不影响统计。有效发布且有正数日计划才计已排期，部分排期仍计一笔；未发布草稿不能替代已有有效发布 |
| 每日填数 | 每日任务、日报记录、裁片配套、外发收回与验收、交接与抽查；保留原表单、任务固定报数方式和权限分工 |
| 物料库存 | 库存台账、订单领用汇总、收发记录、领料申请、耗用与余料、采购交期；领料申请集中于此，排期保留跳转 |
| 月结 | 核对总览、内部月结、外发结算、付款核销、冻结报表、期初核对；按原权限显示，当前冻结与历史冻结版本分开 |
| 基础资料 | BOM、物料、生产资源、生产日历；显示当前实体统计、状态及版本记录。日历仍属于资源版本，不另造资料体系 |
| 物料费用 | 订单费用、实发批次、完工归属、待核对、历史记录；按原批次价格和币种展示，未归属的完工／在制费用不伪记为零 |
| 操作日志 | 服务端分页汇总原操作时间、业务日期、版本、操作人、依据与关联；按来源权限过滤，支持订单号／货号、业务月份及单据／操作人／原因组合查询，可定位原记录。外发结算与付款通过原结算快照关联订单；未登记业务日期的记录不推断月份。翻页期间数据变化要求刷新 |

库存余额采用已签收减已生效退仓、正常耗用和损耗；未签收单列，不同单位不合并数量。订单汇总保留任务、BOM、执行方与物料版本边界。

外厂自报、实际收回、验收合格、交接分别统计。零产量的有效提交属于已填报，草稿不属于已填报。日志只展示已存证内容，不推断历史岗位、未记录字段差异或失败操作。

## 主要变更文件

- `src/features/cutting-operations/`：工作区壳、路由、导航、六页及原业务组件；新增看板、日志、任务／库存／费用／月结总览、统计卡、页内导航和使用说明。
- `backend/app/services/cutting_workspace.py`：只读投影、来源权限过滤、跨来源时间排序及分页一致性。
- `backend/app/api/cutting_operations.py`：只读工作区接口。
- `backend/app/services/cutting_usage.py`：允许只读汇总复用已核验的批次快照，减少重复扫描；原写入校验保留。
- `backend/tests/test_cutting_workspace.py`、裁床前端测试目录：统计、权限、追溯、异步切换和旧业务回归。
- `shared/assistant-help/modules/customer-orders.json`：同步变更源文件的校验哈希，既有业务说明未改变。
- `PROJECT_MEMORY.md`、业务方案第 3 节：更新当前界面与查询事实。

## 自动化验证

| 命令 | 结果 |
| --- | --- |
| `npm run build` | 通过；包含应用类型检查、帮助源指纹验证及构建。仍有依赖注解、包体积及构建插件耗时提示 |
| `npm run typecheck:test` | 通过 |
| `npm run test:unit -- src/features/cutting-operations/__tests__ --maxWorkers=2` | 21 个文件、260 项通过 |
| `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_cutting_workspace.py backend/tests/test_cutting_usage.py backend/tests/test_cutting_cost_allocation.py --basetemp=.tmp/workspace-tests-20261020-c` | 当时版本 56 项通过；随后补充投影边界测试 |
| `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_cutting_workspace.py --basetemp=.tmp/workspace-tests-20261020-d` | 原投影测试 10 项通过；当前补充结果见下表，不重复计数 |
| `git diff --check` | 通过 |

Vitest 在受限 Windows 临时目录初次重跑时遇到 EPERM，未执行任何测试；随后在获准的非沙箱测试进程重新执行，当时 254 项通过。本轮构建与测试同时运行时，一项导航测试超过 5 秒；构建完成后单独重跑，260 项全部通过。测试使用模拟接口／独立数据库，不以原库造测试状态。

独立代码复核发现的时间排序、历史日期丢失、费用事件定位、异步切换覆盖及月结重复加载问题已修复并复核；复核未发现新的阻断项。复核结论与浏览器、自动化结果分别记录，不互相替代。

## 浏览器验收

环境：隔离前端 `http://127.0.0.2:15173`，隔离 API `http://127.0.0.1:18001`，合成 P5b 流程数据及测试主管账号。未对原库执行业务写入。

- 八个顶部导航可进入相应真实页面；页头厂区标签、使用说明、帮助关闭后焦点返回已检查。
- 排期显示合成订单总数 1、已排期 1、未排期 0，订单数量与工程核定套数分别保留。
- 库存展示 2 笔原实发及 3.5 米余额，订单汇总保留两个任务；BOM 可展开现行版本、裁片和必需物料。
- 历史日期 2026-10-15 展示 2 个任务、2 个已填报；从任务进入详情后仍按 2026-10-15 统计。
- 月结核对可查看当前及历史冻结，定位已锁月版本；无付款读取权限的测试主管显示无查询权限。
- 费用显示正常材料费用 8 HKD、完工 4.80、在制 3.20、损耗 2；日志可定位到原价格历史，外发价格原凭据可以展开。
- 320、640、1024、1280、1536、1920 像素宽度检查页面无整体横向溢出；宽表和导航在自身容器滚动。另检查 1440×900 页面层级与间距。
- 请求失败、403 清空、迟到响应不覆盖、日志翻页失效、草稿保护由自动化覆盖；没有把全部错误状态、全部角色、所有写入流程都声明为本轮浏览器逐项验收。

本地截图证据位于 `.tmp/cutting-redesign-qa/`，不纳入源码提交：

- `materials-1440.png`、`closing-1440.png`、`costs-1440.png`
- `master-320.png`、`reporting-320.png`、`reporting-1440.png`
- `report-detail-640.png`、`report-detail-1024.png`、`report-detail-1280.png`、`report-detail-1536.png`、`report-detail-1920.png`
- `activity-final.png`

隔离服务未挂载工作中心／通讯录等无关接口，这些全局背景请求返回 404，不属于裁床业务接口失败。真实目标环境需另行核验全站集成。

## 分阶段完善复验

- **运行环境**：旧 8000 进程缺少新工作区接口，已停止身份核对一致的旧进程，并从当前 `D:/RR/backend` 启动新 API。8000 明确使用 `.tmp/service-start/redesign-20261020-171435/runtime.db`，该库由此前已隔离的运行库通过 SQLite backup 生成，完整性检查为 `ok`。本次没有执行原库迁移或修改 `.env`；前端 5173 保持当前项目 Vite。重新启动应显式复用该独立副本，不能以默认 `.env` 数据库路径代替。进程配置和日志在同目录 `launch.json`、`backend-final*.log`。
- **月份联动**：月结总览与订单核对共用月份；切月立即清除旧预览。跨月深链在发起请求前同步期间，避免被监听器取消。内部月结、结算、付款视图遇到未保存填写或未决操作时保留原月份并提示；内部月结未提交原因也纳入保护。
- **保存后刷新**：当前会话中成功的裁床写入、确认已提交的恢复结果通知只读投影刷新。查询、失败、已放弃恢复及旧登录代次响应不当作成功写入；原编辑器和填写不重建。
- **筛选与异常定位**：排期状态同时作用于卡片与台账；无匹配订单区别于未下发订单并提供清除筛选。每类异常有独立入口：缺报进入日报，收回待验进入外发验收，计划及就绪问题进入排期，均保留查询日期和任务。
- **日志查询**：支持订单、业务月份、来源及原因组合筛选、清除筛选和带范围的翻页一致性检查；缺少订单表时基础资料日志仍可使用。

本轮最终检查：

| 检查 | 结果 |
| --- | --- |
| `npm run test:unit -- src/features/cutting-operations/__tests__ --maxWorkers=2` | 21 文件、260 项通过；含跨月深链、原因保留、保存通知、筛选与定位 |
| `npm run typecheck:test` | 通过 |
| `npm run build` | 通过；帮助指纹、应用及图片翻译构建通过，既有包体积提示保留 |
| `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_cutting_workspace.py -q -p no:cacheprovider --basetemp=.tmp/workspace-review-fix-c` | 11 项通过；含付款按原结算关联订单、来源权限及部分迁移兼容 |

本轮浏览器在新的隔离合成服务 15173／18001 验证：未排筛选卡片与台账同步为 0；九月总览、核对框和预览期间一致；订单 `000123`＋十月＋外发结算返回 7 条；收回待验入口保留 `2026-10-15` 并高亮外发任务。变更筛选区在 320、640 和 1440 像素宽度复查，320 像素页面无整体横向溢出。真实 5173 新建验收页需重新登录，未代用合成账号登录运行副本；运行接口版本另行只读核验。保存成功通知、迟到响应、草稿保护和财务权限主要由自动化验证，未声称所有写入都已做浏览器逐项验收。

本轮截图位于 `.tmp/cutting-redesign-fixes/`：`planning-filter.png`、`closing-month.png`、`logs-320.png`、`logs-640.png`、`logs-1440.png`、`exception-location.png`。测试日志在 `.tmp/redesign-*`。独立复核发现的跨月深链取消和原因跨月沿用问题均已修复并有回归覆盖。

## 月结切换、筛选分页与历史定位复验

本批修复范围：

- 月结直接定位、手动切月、读取历史和路由离开均检查未保存草稿及操作原因；取消保留，确认成功切换后清空旧输入。路由被其他守卫取消时不提前清空，未知结果继续阻止离开。
- 生产任务、库存、费用、操作日志以及六区订单／基础资料列表区分编辑中的筛选与已查询条件。翻页及成功写入后的刷新使用已查询条件，显式查询回到第一页；日志翻页令牌继续绑定原筛选。
- 日志携带基础资料原版本号，后端 `focus_version` 在同一版本上界中定位历史页，前端展开指定版本；列表修订仍依据当前资料。用户开始编辑时取消旧定位，迟到响应不关闭新表单。
- 库存、费用、月结、填数及基础资料区分筛选无匹配与无业务资料，提供清除筛选；待计价视图在全部记录已有价格时显示明确提示。

本批验证（模拟接口／独立临时 SQLite）：

| 命令／检查 | 结果 |
| --- | --- |
| `npm run test:unit -- src/features/cutting-operations/__tests__ --maxWorkers=2` | 21 文件、272 项通过 |
| `npm run typecheck:test` | 通过 |
| `npm run build` | 通过，含帮助指纹及图片翻译构建；既有包体积提示保留 |
| `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_cutting_ops.py -q -p no:cacheprovider --basetemp=.tmp/cutting-ui-fixes-pytest-3` | 27 项通过，含指定版本、读取间新增版本、厂区与读取权限 |
| 独立代码复核 | 慢定位响应和版本分页上界问题已修复，复核未发现新的阻断项 |
| 运行服务只读检查 | 5173 返回 200，8000 健康且 OpenAPI 已含 `focus_version`；后端继续使用既有 `.tmp/service-start/redesign-20261020-171435/runtime.db` 副本 |

测试日志位于 `.tmp/cutting-ui-fixes-*`。首次沙箱测试遇到 Windows 临时文件／测试运行限制，最终以上结果来自获准的非沙箱测试进程，临时数据库路径独立。构建发现帮助资料的源文件指纹失效；核对订单业务说明未受本次只读版本查询变化影响后，仅同步了对应源文件指纹。

**本批浏览器视觉与手动交互尚未验收**：当前没有 Chrome DevTools MCP 工具，按项目规则没有切换其他浏览器工具，也没有将上文历史截图作为本批修复证据。待工具可用后，需复查直接跨月／历史定位、取消确认、筛选输入后翻页、日志跨历史页定位及各类空状态，包含窄屏布局。

改动文件：

- 前端：`src/features/cutting-operations/` 下 `CuttingPeriodClosing.vue`、`CuttingOrdersPage.vue`、`CuttingReportingPage.vue`、`CuttingClosingPage.vue`、`CuttingCostsPage.vue`、`CuttingMasterPage.vue`、`CuttingTaskBoard.vue`、`CuttingInventory.vue`、`CuttingCostOverview.vue`、`CuttingActivityPage.vue`、`CuttingMaterialUsage.vue`、`api.ts`。
- 回归：同目录 `__tests__/periods.spec.ts`、`orders.spec.ts`、`closing.spec.ts`、`master.spec.ts`、`usage.spec.ts`、`workspace.spec.ts`。
- 后端与帮助：`backend/app/api/cutting_operations.py`、`backend/tests/test_cutting_ops.py`、`shared/assistant-help/modules/customer-orders.json`。
- 约定与证据：`PROJECT_MEMORY.md`、本文档。

## 原数据与待办

原数据库 `backend/data/royal_regent_nexus.db` 修改前后 SHA256 一致：

`0E6912AEB263F9C309D399CA694671A338D2EB69708797DFA5FE91F9F40F5F1A`

剩余验收包括：真实员工授权及岗位操作、真实订单和月结资料逐项核对、实际业务容量下的查询耗时、目标部署环境与物理打印机。没有以此次界面改版代替这些上线验收。

月结只读总览单月超过 200 条时明确提示改从操作日志分段查询，不静默截断。数据库权限、冻结流程、付款复核与冲销约束继续沿用现有规则。当前工作保留为未提交修改。
