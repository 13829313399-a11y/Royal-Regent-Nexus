# UV模块交接记录｜DSH前端 → Codex

> 本文件按真实执行结果填写。“未执行”是有效状态，不用预期结果代替验证。
> 事实源：`docs/uv-printing/UV_PRINT_SHARED_SPEC.md`（v1.0）、`docs/uv-printing/UV_PRINT_SOURCE_AUDIT.md`。
> 差异与决策另见同目录 `DECISIONS.md`。

## 1. 基线与归属

- 执行工具/阶段：DeepSeek Harness（DSH），UV 前端 F0 + F1 + F2。
- 当前工作树绝对路径、分支、HEAD：`D:\RR\dsh-worktree`｜分支 `dsh-worktree`｜HEAD `35105c6162e13fa84f02c645916a407b97cf6c9f`（尚未提交，全部改动留在工作区）。
- 基础commit、当前共同规格/契约版本：基线 `main @ 35105c6162e13fa84f02c645916a407b97cf6c9f`；契约 `UV_CONTRACT_VERSION = 'uv-printing/1.0.0'`（`src/features/uv-printing/contracts.ts`）；定价公式版本 `uv-pricing-v1`；经营结余口径版本 `uv-operating-v1`。
- 已读取的规范和实际入口：`AGENTS.md`、`PROJECT_MEMORY.md`（按关键词分节读取）、`DESIGN.md`（2/3/4/5/6/7/8/9/10/11/12/15/16/17 节）、`docs/uv-printing/UV_PRINT_SHARED_SPEC.md`、`docs/uv-printing/UV_PRINT_SOURCE_AUDIT.md`、`src/router/index.ts`、`src/config/pageAccessPolicy.ts`、`src/data/enterpriseMock.ts`、`src/views/ModuleCenterView.vue`、`src/stores/app.ts`、`src/stores/auth.ts`、`src/lib/http.ts`、`src/lib/bodyScrollLock.ts`、`src/components/common/*`、`src/components/ui/button/index.ts`、`src/style.css`、`vite.config.ts`、`vitest.config.ts`、`tsconfig.app.json`、`tsconfig.test.json`、`package.json`。
- 用户已确认的页面/视觉与对应截图：**尚未由用户确认**。已生成的目标视口截图在 `.tmp/uv-shots/`（见第 5 节），等待用户验收。
- 是否已明确授权commit/merge/push：**没有**。本次未执行任何 `git commit`、`git push`、`git merge`、`git worktree remove` 或部署。

## 2. 改动范围

| 文件/目录 | 新增/修改 | 行为变化 | 下一阶段负责人 |
|---|---|---|---|
| `src/features/uv-printing/**` | 新增 | UV 模块全部契约、域计算、组件、七个工作区页面、DEV 样例 transport、测试 | Codex 复核 |
| `src/api/uvPrinting.ts` | 新增 | 正式 UV API 客户端，复用 `@/lib/http`，baseURL `'/uv-printing'` | Codex 按真实路由校准 |
| `src/env.d.ts` | 新增 | 声明 `VITE_UV_PREVIEW`、`VITE_UV_ENABLED`、`VITE_API_BASE_URL` | Codex |
| `src/router/index.ts` | 修改（+6） | 在通用动态模块路由之前注册 `...uvPrintingRoutes` 与 DEV 条件预览路由 | 双方共同文件，已并入 |
| `src/data/enterpriseMock.ts` | 修改（+26） | 生产部模块目录新增 `uv-printing` 卡片：`factoryIds: ['huakang-a']`、`permissions: ['uv_printing:read']`、`strictAccess: true`、`permissionDepartment: 'production'`；未写任何动态经营值 | 双方共同文件，已并入 |
| `src/views/ModuleCenterView.vue` | 修改（+3） | UV 卡片额外核验真正的 `activeFactoryId === 'huakang-a'`；未改动其他卡片的兜底行为 | 双方共同文件，已并入 |
| `tsconfig.test.json` | 修改（+2/-1） | include 增加 `src/env.d.ts` 与 `src/features/uv-printing/__tests__/*.spec.ts`，使 `npm run typecheck:test` 真正覆盖 UV 测试 | Codex |
| `package.json` | 修改（+2） | 仅新增脚本 `dev:uv`（5181 端口）与 `typecheck:app`；未新增/升级任何依赖 | Codex |
| `docs/uv-printing/*` | 新增 | 共同规格、来源审计、DSH 提示词、DECISIONS、本交接文件 | Codex |
| `backend/**` | **未改动** | — | Codex |
| 全局权限 / `authStore` / 全局主题 / 旧业务模块 / `.codex` / `.agents` | **未改动** | — | Codex |

## 3. 页面和操作完成情况

| 工作区 | 已完成操作 | 数据源sample/live | 未完成/限制 | 证据 |
|---|---|---|---|---|
| 驾驶舱 `overview` | 四个紧凑摘要（合格件/在线机台/待处理/今日产值含口径标注）、机台矩阵主视图、需要处理五类清单页内切换、最近有效报工表、快速报工入口；点数字/条目进入已筛选真实清单 | sample（DEV 预览） | 正式路由无后端时按失败/未授权表现，不回落样例 | `.tmp/uv-shots/overview-{390,1024,1366,1440,1920}.png` |
| 生产与核对 `production` | 三个视角（待核作业/有效报工/入库核数）、来源核对抽屉三段式、快速报工抽屉（质量四桶守恒、来源分配余量、幂等重试、IME 安全快捷键、保存并继续、本地草稿）、确认/补质量/更正/作废（原因必填、前后差异可见、原记录保留）、入库核数保存 | sample | 离线草稿只存报工草稿；库存出库/工资确认/关账必须在线 | `.tmp/uv-shots/production-*.png` |
| 机台 `machines` | 卡片/列表可切换、行政/遥测/新鲜度三维度分开、心跳到期与「维修不等于失联」、机台详情（档案与行政状态维护、采集能力清单、真实刻度运行时序与缺口、当天任务与报工、维修费用与当班人员） | sample | 遥测不可由普通 PATCH 伪造；远程控制不在本期 | `.tmp/uv-shots/machines-*.png` |
| 墨水 `ink` | 库存/流水切换（切换保留筛选）、供应商×软硬材质×颜色组合筛选、可用ml/折合瓶数/阈值直出＋阈值刻度条、低库筛选、领用/采购入库/冲销（原单链接、原因必填）、双单位换算（500ml 包装 2 瓶 = 1000ml）、缺单价成本待核、库存不足字段级错误与重试、导出范围提示 | sample | 组合筛选目前在已加载页内完成；正式接口需把同一条件下推到 `UvScope` | `.tmp/uv-shots/ink-*.png`；`__tests__/inkPage.spec.ts` 20 用例 |
| 人员班次 `workforce` | 机台×白夜班矩阵（点击/键盘等价、跨机兼岗冲突提示不阻断、「复制前一班」只复制计划）、人员工资抽屉（工资构成、分摊依据、待核项、0.34/0.33/0.33 余数说明与「合计完全一致」）、未定价/未排班/待核分别呈现、离职历史保留 | sample | 工资预览只读；份额由排班记录表达，前端不编辑份额；无 `payroll_read` 时完全不请求金额 | `.tmp/uv-shots/workforce-*.png`；`__tests__/workforcePage.spec.ts` 5 用例 |
| 产品定价 `catalog` | 产品列表（有价/零价执行/未定价三态、同名不同货号、前导零货号）、工艺版本（每板件数 null 显示未确认）、三种价规分组与优先级/回退口径、基础设置按需展开内联维护、定价测算台可解释计算链、滑杆只做敏感性且不改价、保存测算、采用为执行价独立授权动作（显式生效日＋影响确认） | sample | 「采用为执行价」只针对已保存测算；未定价与无权限分开显示 | `.tmp/uv-shots/catalog-*.png`；`__tests__/pricing.spec.ts` 17 用例 |
| 经营报表 `reports` | 结论性标题、日/月切换、按日期趋势（缺失日期留空不补 0）＋同口径数据表、月比率（月分子合计÷月分母合计）、机台开机率与时间利用率分开且均不叫 OEE、经营结余分项/瀑布与「排除设备投资的经营贡献」、费用构成排序条形＋同口径表、可核对总表与七类下钻抽屉、费用录入、分摊配置（工作日集合＋合计守恒校验＋已结算月修订说明）、导出/打印 | sample | 关账状态接口未下发，页面不假设已关账；导出在样例不生成真实文件 | `.tmp/uv-shots/reports-*.png`；`__tests__/reporting.spec.ts` 11 用例 |

## 4. 契约交接

共同类型文件：`src/features/uv-printing/contracts.ts`（`UV_CONTRACT_VERSION = 'uv-printing/1.0.0'`）。

实际HTTP方法/路径/请求/响应与规格差异：客户端按规格第 12 节实现（`src/api/uvPrinting.ts`），未做任何路径改写；差异集中在**新增具名方法与命令请求体**，逐项列在 `DECISIONS.md` 第 2 节 D-01…D-10。

| 变更项 | 旧约定→新约定 | 原因 | 前端/样例/后端/测试是否同步 |
|---|---|---|---|
| 传输接口 | 仅 `UvTransport`（5 方法）→ `UvWorkspaceTransport extends UvTransport`（约 40 具名方法） | 规格 628 行允许按同样模式扩展具名方法 | 前端✅ 样例✅ 测试✅ 后端待做 |
| `shift` 语义 | 单类型 → 查询只用 `day`/`night`，`ShiftScope='all'` 仅用于响应与 UI | 规格 628 行「请求全天时省略 shift」 | 前端✅ 样例✅ 后端待做 |
| 报工/命令请求体 | 规格仅给 `CreateUvReport` → 其余命令统一 `extends UvCommandMeta` | 规格 11.2 要求 `operation_id` + `expected_version` | 前端✅ 样例✅ 后端待做 |
| 墨水领用/入库 | — → 不带 `expected_version`（只带 `operation_id`），冲销带版本 | 出入库不修改既有对象 | 前端✅ 样例✅ 后端待做 |
| 报工只读冗余字段 | — → `product_no`/`product_name`/`worker_names`/`allocation_total`/`correction_reason` | 列表需要可读名称而不额外请求 | 前端✅ 样例✅ 后端待做 |
| `decimalDivide` 舍入 | 截断到目标位数 → 多算 4 位后 half-away-from-zero 舍入 | 规格 5.5 示例 0.7÷0.6 = 1.166667 | 前端✅ 测试✅ |
| 缺成本表示 | 样例把无记录写成 `'0'` → 改为 `null`（0 是有效数据） | 规格 FIX-03 与 5.8 | 前端✅ 样例✅ **后端务必一致** |
| 导航徽标 / 关注数 | — → 由同一份 summary 驱动，不写死 | 规格 723 行不得冒充动态经营值 | 前端✅ |

需要业务确认的币种、价规、工价、单位、班次、费用/入库口径：见 `DECISIONS.md` 第 4 节（10 项）。缺失时 UI/后端采用的暂行行为也已逐项写明。

## 5. 实际验证

| 检查 | 实际命令或操作 | 环境/视口 | 结果与数量 | 失败/未执行原因 |
|---|---|---|---|---|
| 前端构建 | `npm run build`（`vue-tsc -b && vite build`） | Node v24.14.0，worktree | **通过**：`✓ built in 16.63s`，exit 0 | — |
| 应用类型检查 | `npm run typecheck:app`（`vue-tsc --noEmit -p tsconfig.app.json`） | 同上 | **通过**：0 错误 | — |
| UV前端测试 | `npm run test:unit -- src/features/uv-printing` | vitest / jsdom | **通过**：6 文件 / **79 用例全通过**（含路由与模块卡片契约 19、工作区上下文 7） | — |
| 测试类型检查 | `npm run typecheck:test` | 同上 | **通过**：0 错误（已把 UV 测试纳入 include） | — |
| 全仓回归测试 | `npm run test:unit` | 同上 | 157 passed / 4 failed / 7 skipped（168 文件）；1269 passed / 17 failed / 13 skipped（1299 用例） | 4 个失败文件在**本次改动前就是失败状态**：`document-tools/TaskActions.spec.ts`、`lib/__tests__/yinhuiCustomerPriceConverter.spec.ts`、`views/__tests__/cartonProcurementFrontend.spec.ts`、`views/__tests__/customerOrderCenterLayout.spec.ts`；改动前基线为 14 个失败用例，未发现 UV 相关失败 |
| 浏览器页面操作 | Chrome `--headless=new` + CDP 脚本 `.tmp/uv-browser-check.mjs`；7 页面 × 5 视口 = **35 次真实渲染**，记录 DOM 文本、H1、导航项、console 错误、页面异常、HTTP ≥400、横向溢出 | 390×844 / 1024×768 / 1366×768 / 1440×900 / 1920×1080 | **35/35 通过**：H1 与页面一致、样例横幅存在、7 个二级导航项、**0 console 错误、0 页面异常、0 横向溢出**（`.tmp/uv-shots/report.json`） | — |
| 390/1024/1366/1440/1920布局 | 同上，逐页截图 | 同上 | 截图 35 张（`.tmp/uv-shots/*.png`）；窄屏二级导航折行、表格只在自身容器横向滚动 | 未做屏幕阅读器实机走查 |
| 生产包样例隔离 | `npm run build` 后检查 `dist/assets` | — | 生产入口**未注册**预览路由；样例数据只存在于一个**动态 chunk**（`memoryStore-*.js`，仅当 `isUvPreviewEnabled()` 为真时 `import()`），入口与 `UvWorkspaceShell` 均不静态引用 | 该 chunk 仍作为不可达死代码存在于 `dist`；产物级彻底剔除需要发布流程裁剪 |
| 后端UV测试 | 未执行 | — | 未执行 | 后端由 Codex 在 B0/B1 实现，本阶段不写后端 |
| PostgreSQL迁移/并发 | 未执行 | — | 未执行 | 无后端与迁移 |
| 权限与敏感数据 | 样例中逐角色验证（现场操作员/生产主管/仓管/成本人员/部门主管/只读）；无 `cost_read`/`payroll_read` 时金额不下发也不渲染 | 浏览器 + jsdom | 通过（样例层） | 真实服务端字段裁剪必须由 Codex 实现；前端隐藏列不是权限控制 |
| 事件重放/断网恢复 | 样例幂等重放（同 `operation_id` 同 body 返回原结果、异 body 409）在 store 与用例中验证 | jsdom | 通过（样例层） | 真实采集器断网重放未验证（B1） |
| 已有模块回归 | 全仓 `npm run test:unit` + `npm run build` | 同上 | 无新增失败 | 见上表 4 个既有失败文件 |

### T01–T45 逐项标记

| 编号 | 标记 | 说明 |
|---|---|---|
| T01 | **通过（前端）** | UV 卡片额外核验 `activeFactoryId === 'huakang-a'`；集团/其他厂区不显示该卡片；`__tests__/workspaceContract.spec.ts` 断言卡片作用域与不存在 group/huaxing 兜底项。服务端侧待 Codex |
| T02 | **通过（前端）** | 正式路由 `beforeEnter` 与工作区 composable 双重校验：query 厂区不是华康A、或已登录后有效厂区不是华康A 时立即改道生产部并停止读取，不静默切厂（`workspaceContract.spec.ts` + `workspaceContext.spec.ts` 覆盖 query/数组/有效厂区三类输入） |
| T03 | 前端通过 / 服务端未执行 | 无写权限时按钮禁用并显示原因；真实 403 由后端保证 |
| T04 | **通过（前端）** | 每次请求持 `AbortController` + 请求代次，过时响应不覆盖新页；离开上下文时清空并取消 |
| T05 | 前端通过 / 服务端未执行 | 无 `cost_read`/`payroll_read` 时页面不渲染金额、也不请求工资预览；真实字段裁剪待后端 |
| T06 | 未执行（服务端） | — |
| T07 | 未执行（服务端） | 样例以 `source_event_id` 保留原始事件，未做 10 次重放测试 |
| T08 | **通过（样例）** | `DEMO-J-1001/J-1002` 同机同名 60 秒内两条合法完成并存，界面提示「疑似相似（不自动删除）」 |
| T09 | **通过（样例）** | 同 `operation_id` 同 body → `replayed: true` 且不重复记账 |
| T10 | **通过（样例）** | 同 `operation_id` 异 body → 409，无覆盖 |
| T11 | 未执行（B1 采集器） | — |
| T12 | **通过（样例）** | `DEMO-J-1010` 状态 `uncertain`、`time_evidence: unknown`，界面标注「完工不确定 / 时间待确认」，不自动产生合格报工 |
| T13 | **通过（样例）** | `DEMO-J-1005` `raw_count=10`、`raw_unit=unknown` → `suggested_piece_qty`/`available_piece_qty` 均为 null，分配请求 422 |
| T14 | **通过（样例）** | `DEMO-J-1006` 建议量 47（2 完整板 × 20 + 尾板 7）；分配上限由 `available_piece_qty` 约束 |
| T15 | **通过（样例）** | 超量分配返回 `uv_allocation_overflow` 422 并带剩余量 |
| T16 | **通过（前端）** | 报工只允许关联既有采集作业，不新增第二份有效产量 |
| T17 | **通过** | `reported=100, 90/5/3/2` 守恒；良率按 95 已判件口径 ≈ 94.7368%（用例断言） |
| T18 | **通过** | 分桶合计不符时给出具体差额、拒绝提交、不自动抹平 |
| T19 | **通过（样例）** | `DEMO-P-0005` 显式零价判为 `priced` 且产值 0；缺价判 `unpriced`/`null`，UI 文案不同 |
| T20 | **通过（逻辑）** | `shiftMembership` 严格按 5.3 归属（07:39:59 前一日夜班 / 07:40 白班 / 21:00 夜班 / 跨月夜班归开始日）；不使用客户端时区 |
| T21 | **通过（展示层）** | `splitByShift` 按班次区间拆分运行时长，不在两天重复计同一份产量 |
| T22 | **通过（样例）** | 周日真实报工保留并标注「计划外生产」，不清零 |
| T23 | 前端通过 / 服务端未执行 | 报工保存商业价版本快照字段；历史金额随查询重算由后端保证 |
| T24 | **通过** | 同一报工上商业价与计件工价分开：产值 = 合格件 × 商业执行价，班组工资 = 合格件 × 计件工价，不混算 |
| T25 | **通过** | `splitRemainder('1.00', 3, 'HKD')` = 0.34 + 0.33 + 0.33，合计完全一致（用例断言） |
| T26 | **通过（样例）** | 无工价 → 未定价（金额 null）；无人员 → 未排班；质量未判清 → 待核；都不假定 0 工资 |
| T27 | **通过** | 10h / 0.5h / 20 件 / 人工 200 / 油墨 80 → 20 板、400 件、成本 0.7、加成价 0.98、加成对应毛利率 28.5714%、目标毛利价 1.166667 |
| T28 | **通过** | 500ml 包装领 2 瓶 → 出库 1000ml（用例断言，并断言不出现 2000ml） |
| T29 | **通过（样例）** | 同色不同供应商各自独立；B 库存不足时不能用 A 抵扣（用例断言两侧余额不变） |
| T30 | 未执行（需 PostgreSQL） | 样例层串行校验会拒绝负库存；并发竞争由后端事务保证 |
| T31 | **通过（样例）** | 冲销保留原流水并生成关联反向记录，余额恢复（用例断言） |
| T32 | **通过（设计）** | 遥测耗墨只作参考/差异分析字段展示，不参与库存扣减与计费 |
| T33 | **通过** | 100.00 分摊 3 个日期，合计恰好 100.00，`prorationTotals().matches === true`；不一致时拒绝保存 |
| T34 | **通过** | 90/100 + 1/10 → 91/110 ≈ 0.827273（明确断言 ≠ 0.5） |
| T35 | **通过（样例）** | 混合币种不合并为一个金额；`addMoney` 异币返回 null；费用构成按币种分行 |
| T36 | 部分通过 | 样例对全量过滤后分页；2000 行虚拟滚动**未做**（见第 7 节） |
| T37 | **通过（前端）** | 403/422/409/503/超时归一为结构化错误；读取失败显示失败块与重试，**不回落样例、不显示今日 0 产量** |
| T38 | 未执行（B0 导入） | 导入预览/应用属于后端阶段 |
| T39 | **通过（设计）** | 历史归档快照与实时事实分开建模，报表只聚合实时事实 |
| T40 | 部分通过 | 界面不假设关账；已结算月修改分摊参数要求修订说明；关账字段待后端下发 |
| T41 | **通过** | 生产入口未注册预览路由；样例数据只在 DEV 条件动态 chunk 中（见第 5 节） |
| T42 | **通过** | 5 视口 × 7 页面全部无横向溢出、无 console 错误；抽屉有焦点管理与 Esc、关闭后回焦；主要操作 44px；表格在自身容器滚动 |
| T43 | 未执行（服务端） | — |
| T44 | 前端通过 / 服务端未执行 | 更正创建新修订、原记录保留并标注、差异可见；工资与报表只计有效修订由后端保证 |
| T45 | **通过（构建/测试层）** | 全仓 `npm run test:unit` 与 `npm run build` 通过，未发现因 UV 引起的既有模块回归 |

## 6. 运行与发布状态

- 前端端口：**5181**（`npm run dev:uv`，`--strictPort`），与主工作树 5173 隔离。API 端口：未起真实后端；本地验收用替身 `node .tmp/uv-mock-backend.mjs 8000`（仅实现 `/api/auth/*`，`/api/uv-printing/*` 一律 503）。
- 数据库/数据卷：**未连接任何数据库**。文件输出目录：`.tmp/`（截图、报告、脚本），均被 `.gitignore` 忽略。
- 样例开关与正式开关状态：`.env.local`（被忽略，不入库）`VITE_UV_PREVIEW=true`、`VITE_UV_ENABLED=false`。
- 生产包是否可达预览路由：**不可达**。是否包含合成业务数据：合成记录只存在于未注册路由引用的动态 chunk；入口与壳层不静态引用它们（详见第 5 节）。
- 未写入任何密钥、token 或真实用户私密数据。样例全部为 `DEMO-` 合成行。

## 7. 下一位代理接手事项

**保留的视觉/交互基线**
- 顶栏：返回华康A生产部、模块名、业务日/班次、数据新鲜度、当前角色、刷新；二级导航固定七项（驾驶舱/生产记录/机台/墨水/人员班次/产品定价/经营报表），窄屏折行不隐藏入口。
- 命名空间：全部样式限定在 `.uv-workspace`（`src/features/uv-printing/styles/workspace.css`），复用宿主语义 token 与 `src/components/common`、`src/components/ui/button`；未改全局主题、未写全局选择器。
- 状态语义：`UvStateBlock` 统一 loading / empty / no-result / forbidden / readonly / error / stale；`UvStatusPill` 输出业务语言而非枚举；金额未定价显示「未定价」、缺失显示「—」、显式 0 显示 0。
- 三段式来源核对抽屉（我看到了什么 / 我确认什么 / 会影响什么）与现场快速报工的键盘路径（Enter 选品、Tab 连输、Ctrl/Cmd+Enter 提交、IME 组合期不触发）是验收重点，请勿在联调时退回普通 CRUD 表格。

**最优先的三个问题及证据**
1. **没有后端，正式路由不可用**：`/api/uv-printing/*` 全部未实现；权限码 `uv_printing:*` 未注册，模块中心的 `strictAccess` 会让卡片隐藏。证据：`src/api/uvPrinting.ts`、`src/features/uv-printing/routes.ts`、`.env.local` 状态。
2. **契约需要后端逐条对齐**：`DECISIONS.md` 第 2 节 D-01…D-10 是为页面需要新增的具名方法与命令请求体。请以 `contracts.ts` 为前端事实源生成 Pydantic schema 并做契约测试，不要静默改名（例如把 `good_qty` 改成 `quantity`）。
3. **缺成本必须用 `null` 表示**，不能写成 `'0'`。证据：规格 FIX-03 / 5.8；样例 store 的 `categoryTotal` 与 `inkIssueCost` 已按此修正；若后端写成 0，「结余暂算/缺成本」口径说明会失效。

**仍未接通的接口和真实设备能力**
- 全部 UV HTTP 接口（规格第 12 节清单）。
- 采集入口 `/ingest/events` 与连接器认证、五种打印软件适配器、可靠完工信号、分色耗墨、稳定作业 ID —— 目前全是合成能力声明（`capabilities`），没有任何实机验证。
- 导出文件本体、导入预览/应用、日结月结、审计与 `UvOperation` 查询。

**下一阶段可写/不可写范围**
- Codex 可写：`backend/**`（路由、schema、模型、服务、迁移、测试）、`connectors/uv-printing/**`、正式权限码注册、真实 transport 接线修复、UV 前端接线/计算/错误行为。
- Codex 应保持：已实现的中文信息架构、七个工作区结构、三段式抽屉、状态语义与色彩；必须更改时给出具体原因与前后证据。
- 同一时刻只有一个写入者：`contracts.ts`、`src/router/index.ts`、`src/data/enterpriseMock.ts`、`src/views/ModuleCenterView.vue`、`docs/uv-printing/*`。

**已知未完成项（明确记录，不冒充已交付）**
- 未做 2000 行级虚拟滚动验证（规格 6.8 建议复用宿主 TanStack Virtual）。
- 未做屏幕阅读器实机走查（仅静态语义审查与键盘路径实现）。
- 未在真实后端/真实打印设备上验证任何行为。
- 墨水页的组合筛选目前在已加载页内完成，正式接口需把同一条件下推到 `UvScope`。
- 生产 `dist` 中仍会生成一个不可达的样例动态 chunk；如需产物级彻底剔除，需要发布流程配合裁剪。
