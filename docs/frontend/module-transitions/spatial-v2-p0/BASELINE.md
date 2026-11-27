# Nexus Spatial Motion V2.0 · P0 基线

2026-11-24。基线为 `fe7cdb2df74a72acfca39d28a6b9fb5c6e37b3fe`，从 `codex/molding-trial-report-after-completion` 建立本地分支 `codex/nexus-spatial-motion-v2-p0`。本轮交付 V1 的源码、行为和性能基线，供 P1/P2 做同条件比较。

## 范围与工作区

P0 的提交范围为本目录内的报告、浏览器观测脚本和数值样本。浏览器脚本只用于本地验收，由 DevTools 在已登录的页面执行。产品代码、测试断言、业务数据、权限、配置及 V2 开关均不在本轮变更范围。开始时暂存区为空，已有 8 项修改、5 项删除、1,043 条未跟踪路径。对现存的 8 个文件保留工作树字节 SHA-256，对删除项核对路径缺失，对原未跟踪路径清单计算摘要。其中 `DESIGN.md` 实际为 V3.0，SHA-256 为 `115b dedc 73db 1420 762b ab6d 68b4 925b dc4f f7c9 df18 988b 3feb 82aa 78b5 5b5f`（分组显示）。两个项目技能、AGENTS、裁床计划、UI 简报、前端流程、例外索引及五个已删除文档均纳入保护核对。

## 真实实现与试点边界

| 源码 | V1 事实 | 下一阶段应保护或验证的行为 |
| --- | --- | --- |
| `src/router/index.ts`、`navigation.ts`、`classifyNavigation.ts` | 视觉钩子先安装，记录意图、序号和最终路由。成功的当前导航才产生过场。相同 workspace、认证、forbidden、实际厂区变更都参与排除判定 | 现有 RouterLink、一次 push、重定向、守卫拒绝、查询参数、历史栈及草稿继续由原路由管理 |
| `useModuleEntryMotion.ts`、`ModuleCard.vue`、`HomeModulePreview.vue`、`DepartmentTabs.vue`、`SidebarNav.vue` | 来源从触发容器找图标，部分类别只有入口 ID。修饰键、下载、新窗口和已有按钮保留原语义。来自模块页的侧栏导航会使旧意图失效 | 记录实际触点，保留预览、原生链接、键盘和异步挂载期间的首次入场所有权 |
| `AppShell.vue`、`RouteMotionHost.vue`、`route-motion.css` | 标准壳、认证壳、fullPage 分支各有原 RouterView。全页外层为 `display: contents`。body 上单个 Teleport 装饰层设置 inert、aria-hidden、pointer-events:none | 保持单份业务实例。禁止给业务根、表格、iframe、fixed/sticky 父级添加缩放或滤镜 |
| `useRouteMotionHost.ts`、`createRouteMotionCoordinator.ts` | 入口按压 120ms。主体仅 opacity 0.55→1，普通 180ms、返回 260ms、简约 140ms。40px 徽记最多 280ms，光晕 180ms。距离超过 280px 时在目标附近移动 6px。视觉预算从确认起算 340ms，计时器清理可能受调度影响。WAAPI 使用 fill:none | 候选形变仅用于经过确认的装饰面。几何失效、取消、超时或缺目标时，内容仍可操作 |
| `useHomeAppearance.ts`、`src/style.css` | 按账号保存丰富、简约、关闭。系统减少动态或页面隐藏时有效偏好为 off。总开关为 `VITE_ROUTE_MOTION_ENABLED`。样式已有时长和弹簧曲线，路由主机当前使用自己的 cubic-bezier | 复用偏好及既有原语。关闭时的 focus、scroll 与首次入场归属也属于回归范围 |

源码目录为 `src/features/route-motion/`，门户入口在 `src/components/{modules,portal,layout}/`。普通试点的目标锚点是 `ModuleDetailView.vue` 的 H1，设备试点是 `UvWorkspaceShell.vue` 顶栏 H1。两者均为当前图标目标，V2 装饰面和独立图标目标尚待设计。前端为 Vue 3、Vue Router、Pinia、Vite、Tailwind 4 和 Reka UI。

**已有的返回风险。** `returnOrigin()` 先按首页身份及上下文筛候选，再按历史位置找记录，找不到就取最后一条。未核对正在离开的模块是否为记录中的最终模块。即使命中，反向徽记仍从目标卡片附近 6px 处开始。下方两个成功往返覆盖了准确回到原卡片的正例。P1 要补来源不匹配、历史断开、重复入口及离屏时的降级测试，在 P2 再录制实际的反向形变。

**参考体验。** 依据用户提供的方案和独立 HTML，以 1440×900 实际打开丰富模式，从 UV 卡片进入、返回，另从注塑卡片打开详情并用 Escape 关闭。开启慢速观察可看到材质落到工作区头部，标题同时可获焦，图标保持自己的比例。关闭模式返回后直接聚焦原卡。生产界面应延续触点、材质、方向和可操作性。演示中的业务数字、布局和教学倍率只用于观察。实现视觉阶段需要独立评审真实首返录像中的起势、中段、落位与中断。

**后续阶段的候选文件。** P1 优先限于 `src/features/route-motion/` 的策略、几何、来源匹配、资源释放和对应专测。P2 可在上述两个试点的实际卡片及标题组件声明装饰锚点，继续使用同一 AppShell。P3 的真实角色覆盖及 P4 的局部弹层分别评审。每个视觉实施阶段需由未参与实现的评审者对照参考和同路由录制，空间连续性或操作体验不合格时在该阶段返工复评。

## 浏览器与回归

Chrome DevTools MCP。现用本地 Vite 5173 的受保护深链正常转到登录。本次另外启动同一检出的 Vite 开发服务器（18524）和真实 FastAPI（18525），仅绑定回环地址。一个新的 TEMP SQLite 运行项目既有迁移和初始化，使用一次性合成管理员经正常登录页登录，厂区为华康 A。独立 Chrome 上下文保存本次偏好及 cookie。UV 页面为无机台空态。试点路径均经真实入口，浏览器后退使用原历史项。

| 视口 / 路径 | 实际观察 |
| --- | --- |
| 1440×900 · `/modules/production?factory=huakang-a` → `/modules/production/production-plan?factory=huakang-a` → 后退 | 普通壳进入“生产计划管理”，H1 获焦。后退时焦点回到 `production-plan`，代表录像这一趟的窗口滚动为 331px |
| 1440×900 · 同门户 → `/modules/production/uv-printing/live?factory=huakang-a` → 后退 | 独立全页工作区显示“从第一台机台开始”，H1 获焦。后退时焦点回到 `uv-printing`，该趟滚动为 1004px |
| 两个落位状态 | 在真实 RouterView 子根读取到 transform/filter 均为 none，首返落位时装饰节点归零。持续效果与滚动容器是否变换另以主机源码和壳集成测试核对 |

**既有回归。** 本次扩大至 23 个 Vitest 文件、225 项，221 通过、4 失败。首次 22 文件的 219 项中同四项失败，补入喷油草稿测试后再次复现。源代码和测试在当前检出与基线 HEAD 一致。

| 类别 | 结果及差异 |
| --- | --- |
| 既有三个路由动效套件 | `navigation.spec.ts` 23/23，`shell.spec.ts` 10/10，`catalog.spec.ts` 6/7。合成目录遍历统计出现位置时预期 30、实际 36。该断言之后的覆盖导出没有执行 |
| 部门 / 厂区目录 | `moduleCenterFactoryScope.spec.ts` 18/21。工程 BOM 的标题和子项已与预期不同，PMC/仓管期望 7 项实得 5 项，业务部期望 6 项实得 5 项。需要按目录业务定义处理差异 |
| 权限、导航和草稿 | 运行的路由 `.spec.ts`、会话并发、普通壳、UI 原语、生产部入口、助手离开守卫、印尼物料草稿持久化及喷油表单取消/丢弃均通过 |
| 未被 Vitest 收集的两个独立脚本 | 用仓库 TypeScript 转译后用 Node 单独执行。浏览器后退退出保护退出 0。`authGuard.test.ts` 退出 1，首个失败点是对 `/system/users` 单项静态权限数组的正则断言。当前源码按合并版 IAM 开关选择权限组合 |
| 类型检查 | `npm run typecheck:app`、`npm run typecheck:test` 均退出 0 |

在仓库根目录用 PowerShell 执行以下回归命令。

```powershell
npm run test:unit -- src/features/route-motion/__tests__ src/components/layout/__tests__/enterpriseUiShell.spec.ts src/router/__tests__ src/components/ui/__tests__ src/features/assistant/__tests__/navigationGuard.spec.ts src/views/__tests__/moduleCenterFactoryScope.spec.ts src/views/__tests__/productionModuleEntry.spec.ts src/stores/__tests__/authSessionConcurrency.spec.ts src/features/indonesia-materials/__tests__/draftPersistence.spec.ts src/features/spray-production/__tests__/demandForms.spec.ts
npm run typecheck:app
npm run typecheck:test
```

2026-10-22 的记录包含 52 项、按当时证据层级通过 43 项、9 项有缺口，目录矩阵当时为 30 个出现位置、7 个厂区、217 条控制或过滤记录。本轮覆盖以上实测路径。非管理员真实撤权与跨厂拒绝、有数据的拖排/冻结列/iframe、慢守卫期间操作、进入中过早弹层、NVDA、200% 真实缩放、真机与全站性能仍有待专门验收。[历史实现](../../../archive/completed/frontend/module-transitions/IMPLEMENTATION.md) · [历史验收](../../../archive/completed/frontend/module-transitions/ACCEPTANCE.md) · [历史矩阵](../COVERAGE.md)

## 性能基线

Windows，Ryzen 7 5800H，16 个逻辑处理器。Chrome UA 主版本 158。系统报告桌面显示输出为 1920×1080、165Hz，浏览器内容视口为 1440×900，DPR 约 1。CPU 1×，回环网络无降速，同一账号、厂区、空业务库与已预热的 Vite 模块。正式采样固定启用 MCP 焦点模拟，每次成功导航的观测点均记录到页面 visible、有焦点。下表单位为 ms。

| 模式 | 导航 | 次数 | 输入到下一 rAF 回调 p95 | 输入到确认 p95 | Event Timing p95 | rAF 间隔 p95 | 徽记最晚移除 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 丰富 | 门户 → 生产计划 | 10 | 51.8 | 19.3 | 72 | 6.2 | 341.6 |
| 丰富 | 生产计划 → 后退 | 10 | — | — | — | 12.1 | 344.0 |
| 丰富 | 门户 → UV | 10 | 34.1 | 7.4 | 48 | 6.2 | 342.1 |
| 丰富 | UV → 后退 | 10 | — | — | — | 12.1 | 342.1 |
| 关闭 | 门户 → 生产计划 | 10 | 52.8 | 14.6 | 72 | 6.2 | — |
| 关闭 | 生产计划 → 后退 | 10 | — | — | — | 6.2 | — |
| 关闭 | 门户 → UV | 10 | 24.7 | 5.1 | 32 | 6.2 | — |
| 关闭 | UV → 后退 | 10 | — | — | — | 6.3 | — |

1. 从门户正常登录后，在 Chrome DevTools MCP 的 `evaluate_script` 中执行 `probe.js` 的函数。它订阅现有 router.afterEach、可信 pointerdown/click、PerformanceObserver、body 直接子节点变更与短期 rAF。用门户外观控件切换偏好。每组开始在页中调用 `window.__rrSpatialP0.start(组名)`，结束读取 `read()`，整个实验后调用 `dispose()` 或关闭该页。[采样脚本](./probe.js)
2. 一轮为生产计划和 UV 各进、退一次。卡片内“查看模块”链接先即时滚动到视口中部，等待 250ms 检查中心命中原链接，再由 `qa_click_sequence` 向该 UID 派发一次真实鼠标点击，返回使用浏览器后退。每次操作后至少留 650ms 检查 URL、焦点和清理，再进行下一次。丰富和关闭各预热一轮。正式顺序 A 丰富、B 关闭、C 关闭、D 丰富，每段五轮，每种模式每条有向路径各 10 笔，共 80 笔。另存 8 笔预热，录像、trace、移动端和页面重载均独立于这 80 笔。[逐次数据](./samples.json)
3. 输入计时从 pointerdown 的事件时间戳起，确认取成功的 afterEach 观测点。Event Timing 汇总同次可信 pointerdown/click 中浏览器上报的最大 `duration`，观察阈值 16ms，数值受浏览器取整影响。正式四组入口每组均匹配 10/10。历史后退没有页面 pointerdown，表中留空。rAF 间隔取该组各导航在确认后约 450ms 内的相邻回调时间戳。首帧延迟另存 `firstFrameMs`。分位数取 nearest rank，对 10 次输入该 p95 即最大值。rAF 与实际显示帧、单次 Event Timing 与整页 INP 分别记录。
4. 丰富模式 40 笔各观察到一次徽记挂载和一次移除，关闭模式 40 笔未挂载。尾部实际采样时间为确认后 450.3–456.6ms，80 笔的尾部徽记均为 0。徽记移除以 DOM 变更为准，主体 WAAPI 完成时刻和全部计时器数量另须专项测量。正式窗口内，关闭模式的普通入口有一次浏览器 Long Tasks API 上报为 50ms，其余各组为 0。
5. 探索采样曾遇到工具回执超时但已抵达 UV、目标检查发现误入啤办，以及 rAF 间隔接近 1 秒。一次前置诊断甚至在尾部观察时仍有装饰。原因未定位。这些受干扰的整批结果按操作条件单列，正式数据包含固定流程下全部 80 笔，未按耗时或外观表现筛样。原始试采保存了 72 笔先期样本、一组 8 笔诊断和独立的空闲 rAF 读数。[试采数据](<D:/RR/outputs/nexus-spatial-motion-v2-p0-20261124/exploratory-samples.json>)

**独立 trace。** 丰富和关闭各额外录一轮，同一页、同一对真实首返，在标记 `rr-p0-begin` 至 `rr-p0-end` 之间统计目标渲染器主线程。浏览器在两个软导航分段（NAVIGATION_1 和 3）给出的 INP 为普通/UV 丰富 92/51ms、关闭 81/45ms，每段来自单独一次录制。录制开销及两次导航、两次后退、门户滚动和业务渲染都包含在窗口内。

| 整轮 trace | 录制标记间隔 | Layout 次数 / 总毫秒 | Paint 次数 / 总毫秒 | RunTask 超 50ms |
| --- | ---: | ---: | ---: | ---: |
| 丰富 | 5265.5ms | 535 / 76.3 | 2124 / 363.3 | 2 |
| 关闭 | 5247.6ms | 341 / 49.7 | 1072 / 150.4 | 2 |

这台机器上，丰富模式的整轮 Paint 工作量较高。P2 应使用同一对路由、模式和采集方法复测，再从 trace 的具体事件归因。现场设备、GPU/堆内存、持续满帧及全站输入目标仍待验证。[丰富 trace](<C:/Users/匡树杰/AppData/Local/Temp/chrome-devtools-mcp-ORV3yz/v1-expressive-trace.json.gz>) · [关闭 trace](<C:/Users/匡树杰/AppData/Local/Temp/chrome-devtools-mcp-ORV3yz/v1-off-trace.json.gz>) · [统计明细](<D:/RR/outputs/nexus-spatial-motion-v2-p0-20261124/trace-summary.json>)

**重载样本单列。** 浏览器 HTTP 缓存绕过，Vite 服务端已有缓存，已有登录会话。在 1440×900 丰富模式重载生产部门户，一次 Navigation Timing 为响应开始 10.5ms、DOMContentLoaded 699.7ms、load 729.0ms。该次浏览器未提供 paint 或 LCP 条目。服务进程首次启动和首次登录冷链路尚未计量。

## 证据与复核

- 桌面代表截图覆盖生产部门户、普通壳和独立 UV 空态。录制文件包含两条完整首返。Chrome 的截图工作区拒绝直接写入项目证据路径，媒体均由 MCP 写入其允许的临时证据目录。该目录可能被系统清理。[门户](<C:/Users/匡树杰/AppData/Local/Temp/chrome-devtools-mcp-ORV3yz/v1-portal-1440.png>) · [生产计划](<C:/Users/匡树杰/AppData/Local/Temp/chrome-devtools-mcp-ORV3yz/v1-standard-1440.png>) · [UV 设备页](<C:/Users/匡树杰/AppData/Local/Temp/chrome-devtools-mcp-ORV3yz/v1-uv-1440.png>) · [V1 首返录像](<C:/Users/匡树杰/AppData/Local/Temp/chrome-devtools-mcp-ORV3yz/v1-portal-standard-uv.mp4>) · [演示首返慢放](<C:/Users/匡树杰/AppData/Local/Temp/chrome-devtools-mcp-ORV3yz/demo-surface-return.mp4>)
- 390×844 触控仿真下，已保存的丰富偏好在系统减少动态时实际生效为 off。打开 UV 底部预览后，Tab 从关闭键移到“查看模块”，Enter 进入全页。弹层关闭，正文恢复可滚动，H1 获焦。浏览器后退重新聚焦 UV 原卡。首返挂载装饰数均为 0，两次尾部检查均为 0，门户和 UV 文档宽度均为 390px。[移动门户](<C:/Users/匡树杰/AppData/Local/Temp/chrome-devtools-mcp-ORV3yz/v1-portal-mobile-reduce.png>) · [预览弹层](<C:/Users/匡树杰/AppData/Local/Temp/chrome-devtools-mcp-ORV3yz/v1-mobile-uv-preview.png>) · [移动 UV](<C:/Users/匡树杰/AppData/Local/Temp/chrome-devtools-mcp-ORV3yz/v1-uv-mobile-reduce.png>)
- 在完成正式桌面样本和 trace 后检查当前文档，控制台 warn/error 为 0。DevTools 列出的 175 个 fetch/XHR 没有 HTTP 4xx/5xx，POST 仅为既有成员在线心跳。网络核查以本地空数据试点为限。[浏览器观测](<D:/RR/outputs/nexus-spatial-motion-v2-p0-20261124/browser-observations.json>) · [Vitest 逐项结果](<D:/RR/outputs/nexus-spatial-motion-v2-p0-20261124/vitest-results.json>) · [独立守卫脚本记录](<D:/RR/outputs/nexus-spatial-motion-v2-p0-20261124/authGuard.test.log>)
- 独立 reviewer `p0_review` 未参与采集和编写。其逐帧观察中，V1 普通壳约在录像 0.57–0.72s 切入，UV 约在 3.42–3.67s 切入，标题和内容落位稳定。参考演示中能连续追踪卡面与独立图标在首返的位移，V1 的上述切换缺少这段卡面轨迹。P2 需在同一实际路由证明材质与图标的连续运动，及输入中断后的可操作性。

**独立复评结论为 PASS（P0 技术基线）。** Reviewer 复算 80 笔正式样本与 8 笔热身，核验两个完整 trace、首返录像、移动端截图、测试日志和证据链接。复评前已在探针补记确认到首个 rAF 及尾部的实际观测时刻，正式采集核对真实点击目标，受干扰试采单列。四项 Vitest 失败和单独鉴权脚本的一个失败保留为既有差异。V2 视觉实现与独立动效设计评审从后续阶段开始。
