# T05c 工序物料期与业务自审基础

后续采购准备、负责人内部审核和取消／改量申请已接续实现，见 [T06a 实施说明](huakang-c-material-purchase-foundation.md)。正式下发仍未开放。

## 实施计划与业务边界

1. 复用 0191 草稿指针和不可变事件，新增提交、采购填期、业务自审、退回编辑动作，不另建订单或库存账。
2. 原业务提交已关联订单的已保存需求；采购按该固定版本的工序填写日期，支持部分保存，全部完成后原业务自审。
3. 提交和自审重查有效 BOM 与订单 revision。改需求须退回草稿，清空本轮日期和审核结论，重新提交；原事件不修改。
4. 采购日期只描述该工序物料期，不代表供应商承诺、到货、按期可抵扣在途或生产排产。未使用提供表格以外的假库存。
5. 自审结果为“业务已自审，待供给资料”，不是正式放单、采购申请或采购订单。净采购数量仍为空，放单门槛始终关闭。
6. 同码自制与委外始终分别汇总，日期保存及自审不得重新按编码合并。

状态：草稿 → 待采购填期 → 待业务自审 → 业务已自审待资料；业务可从后三种状态退回草稿重新编辑。采购可修改待填期／待自审状态的日期，基于 expected_version 防止审核与改期互相覆盖。已自审必须先由业务退回。日期接口整表替换当前日期集合，未传或为 null 的工序清空；页面始终发送全部工序键，允许保存未填齐的日期。

权限：沿用华康 C Sales 的 read/draft_write，新增 submit/self_review；采购新增 pmc-warehouse 的 dates_read/dates_write，独立显式授权，不给仓库原有权限自动扩权。采购只获得已提交需求的必要用料及工序投影，不获得订单客户数据或私人草稿。历史仍由原业务查看。

## UI 简报

- 业务沿用需求试算页，列表显示实际状态；保存完成且无未保存改动时可提交，待自审时可自审，其余已提交状态支持退回编辑。编辑区显示采购已填日期，提交后锁定用料输入。
- 采购新增“工序物料期”入口，左侧／上方为已提交需求列表，详情为逐工序日期表及用料明细（含本次属性），主操作为保存物料期。没有审核订单、采购下发或库存按钮。
- 复用 PageHeader、SectionPanel、Button 及 DESIGN.md 的颜色、圆角、字体；窄屏纵向堆叠、表格局部横向滚动，日期用原生带标签控件，状态不用纯颜色表达。
- 明确加载、空列表、无权限、未启用、只读、版本冲突、保存未知和成功状态。未知写入固定原请求重试，阻止竞争编辑；身份变化清除私有数据；有未保存输入离开需提示。
- 浏览器应覆盖桌面、窄屏、键盘及受限状态。当前 Chrome DevTools 不可用，不以单元测试代替视觉验收。

## 验证计划

隔离 SQLite 验证状态顺序、只允许原业务自审、厂区／部门／动作权限、部分／完整／未知工序日期、日期清除、已审锁定、退回重审、源订单／BOM 变化、请求重放与并发冲突、同码不同属性、采购投影隔离。前端验证对应操作及未知写入／撤权；运行相关 unit tests、typecheck:test、build，独立审查状态与权限。

真实库迁移和授权均不在本批执行；无需新增迁移。PostgreSQL、真实岗位及生产排产联动仍待验收。物料、库存、在途和采购表格后补，不阻塞本批流程基础。

## 实现与验证

- 业务入口沿用 `/modules/sales-business/material-planning?factory=huakang-c`，采购入口为 `/modules/pmc-warehouse/process-material-dates?factory=huakang-c`。
- 原业务指需求草稿创建人；新增 `material_plan:submit` 和 `material_plan:self_review` 仍需显式配置。采购位于现有 PMC／仓管组织目录，但原有仓库权限不会自动取得 `dates_read` 或 `dates_write`。
- 日期、提交、自审及退回均追加不可变事件，记录操作者和说明。采购保存重试仅返回必要投影；成功后重新读取当前队列，避免旧成功回执使已自审界面恢复可编辑。若已退回业务，采购不能继续操作旧需求。
- 提交和自审重查来源；采购填写的是固定提交版本的日期。来源订单／BOM 改变后须业务退回、核对并重新提交，不能凭已有日期越过自审检查。
- 本期查询仍未做大数据分页，当前工序按固定 BOM 的工序名称区分；后续如拆分同名不同执行段，须引入稳定工序身份和迁移设计，不能自动合并日期或需求。

| 验证 | 结果 |
| --- | --- |
| 后端 `.venv/Scripts/python.exe -m pytest tests/test_material_plan_workflow.py tests/test_material_plan_orders.py tests/test_material_plan.py tests/test_engineering_bom.py -q --tb=short`（backend 目录） | 74 项通过；隔离 SQLite，无真实业务写入 |
| 前端 `npm run test:unit -- src/features/material-planning src/features/engineering-bom/EngineeringBomView.spec.ts src/stores/__tests__/authScopedPermissions.spec.ts src/router/__tests__/authorizationRefresh.spec.ts` | 98 项通过 |
| `npm run typecheck:test`、`npm run build` | 均通过；build 包含主应用与图片翻译子项目，既有依赖注释及插件耗时告警保留 |
| `git diff --check` | 通过 |
| 独立审查 | 已修复采购旧回执显示陈旧状态，复核无剩余阻断 |
| 浏览器、PostgreSQL、真实员工 | 未验证；当前无 Chrome DevTools 工具，未生成浏览器截图 |

### 本批文件

| 范围 | 文件 |
| --- | --- |
| 流程服务及接口 | `backend/app/services/material_plan_workflow.py`、`material_plan.py`；`backend/app/api/material_plan.py`；`backend/app/schemas/material_plan.py` |
| 权限 | `backend/app/services/permission_codes.py`、`src/stores/auth.ts`；现有动态敏感权限及岗位排除集合沿用，不增加自动授权 |
| 业务／采购 UI | `src/features/material-planning/MaterialPlanningView.vue`、`ProcessDatesView.vue`、`TrialResults.vue`、`api.ts` |
| 导航 | `src/router/index.ts`、`src/data/enterpriseMock.ts`、`src/composables/useVisibleModules.ts` |
| 测试 | `backend/tests/test_material_plan_workflow.py`；`src/features/material-planning/MaterialPlanningView.spec.ts`、`ProcessDatesView.spec.ts`、`navigation.spec.ts` |
| 说明与索引 | 本文、试算说明、一期计划、任务清单、`PROJECT_MEMORY.md`、门户说明与相关帮助来源摘要 |
