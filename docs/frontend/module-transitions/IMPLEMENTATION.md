# 模块导航过场实施交付

已完成交付包 P0–P5 的本地实现、可独立执行的验证和证据归档。部分真实设备、身份和性能严格口径仍有缺口，详见 [验收报告](./ACCEPTANCE.md)。本次交付不等同于生产发布或全部业务验收。

## 基线与边界

- 输入：`C:/Users/匡树杰/Desktop/chatgpt-tsc/RR-Nexus-Module-Transition-Codex-20261022/rr-module-transitions-20261022`。
- 源码：`D:/RR/royal-regent-nexus`；实施起始分支 `codex/uv-motion-acceptance-20261022`；开始 HEAD `629012a572b33f7101851ea5e597b9c9436ffd43`。本地验收完成后，按用户追加授权从工作区创建 `codex/module-transitions-delivery-20261022` 进行独立提交及 PR 交付。
- 交付包七个源码 SHA-256 与开始时一致；原有 `.playwright-cli/`、`output/`、`test-artifacts/` 保留。
- 沿用 Vue 3.5.39、Vue Router 5.1.0、CSS、WAAPI、Lucide，无新依赖、后端或迁移修改。本地实施阶段未执行 Git 发布；后续提交、推送和 PR 合并按用户追加授权执行，仍不包含生产部署。
- 浏览器仅用 Chrome DevTools MCP，复用本地 5173/8000 服务。未重启业务服务。使用现有本地管理员；喷油离开保护只填入未保存的合成文字后丢弃，未提交业务记录。

## 阶段结果

| 阶段 | 交付 |
| --- | --- |
| P0 | 核对包内规范、七文件基线、RouterView/fullPage、守卫、目录、原动效、偏好与测试起点 |
| P1 | 单实例路由树、独立装饰层、最终路由确认驱动、导航 token、取消和错误清理 |
| P2 | 真实图标/颜色、身份/厂区隔离的来源记录、返回滚动/焦点、失效入口回退 |
| P3 | 首页、UV、3D、注塑首屏所有权；局部导航不重播；真实目录与原生链接语义 |
| P4 | 30 个实际目录入口、断点、移动预览、慢网、离开保护、降级、成对性能；修复 320px 溢出和返回滚动竞争 |
| P5 | 相关回归、最终专项、类型检查、完整构建通过；实施、52 项验收、覆盖矩阵、证据和回退说明 |

包内结束条件允许外部条件阻止部分验证时，完成所有不受阻工作并交付缺口。本次按此条件结束本地实施，受阻项未计作通过。

## 实现行为

新增 `src/features/route-motion/`，拆分分类、意图、效果清理和 Vue 接入。守卫仍决定导航是否允许；过场只消费最终确认路由。旧导航的失败、延迟完成或取消不能覆盖新导航。普通壳和 fullPage 使用原 RouterView，未加全局 route key、KeepAlive 或第二套业务 DOM；移除旧 `out-in` 串行退出。

主体仅 opacity 进入，不做整页 transform/filter；40px 图标 ghost 独立 Teleport，aria-hidden、inert、pointer-events:none。没有旧页面截图、表格克隆、每帧布局读写或全页模糊。普通进入180ms、简约140ms、返回260ms、徽记280ms、光晕180ms，并行运行。清理预算从路由确认起340ms，为360ms契约留调度余量；业务渲染耗尽预算便跳过装饰，不延迟挂载或输入。

来源记录只在内存，最多12项，按身份、授权、厂区、首页和 history position 隔离。返回首页在 DOM 提交的下一帧恢复滚动，避开原生 popstate 自动恢复；该帧也由 token 取消。过滤导致原卡片屏外时，回到可见 H1 和顶部。用户已聚焦连接中的控件或弹窗时不抢焦点。

偏好传感器常驻 AppShell，fullPage 也响应减少动态效果及页面可见性。关闭动效仍拥有首屏，防止模块自身 reveal 再次出现；局部导航保留原动效和草稿保护。缺少 WAAPI、取消 rejection、错误和卸载均有清理。修饰键、新窗口、外链、下载和无目标占位保留原生语义。

Router loading 增加自身代次所有权，旧异步守卫/清理不能结束新导航。预览卸载后的延迟焦点恢复加 disposed 防护。body 最小宽改为 `min(320px, 100%)`，修复 Windows 经典滚动条下320px视口15px横向溢出。

## 修改文件

| 文件/目录 | 用途 |
| --- | --- |
| `src/features/route-motion/{classifyNavigation,navigation,createRouteMotionCoordinator,useRouteMotionHost,useModuleEntryMotion}.ts` | 身份分类、最终意图、取消清理、来源、焦点/滚动、模块接入 |
| `src/features/route-motion/RouteMotionHost.vue`、`route-motion.css` | 非交互装饰层 |
| `src/features/route-motion/__tests__/{navigation,shell,catalog}.spec.ts` | 竞争/错误、真实壳单实例、偏好/清理、目录契约 |
| `src/components/layout/{AppShell,SidebarNav}.vue`、`src/router/index.ts` | 双分支宿主、入口、早期观察与 loading 所有权 |
| `src/components/modules/{ModuleCard,DepartmentTabs}.vue` | 来源记录、图标锚点、单次激活 |
| `src/components/portal/{HomeAppearanceControl,HomeModulePreview,HomePreviewRegion}.vue`、`styles/home-prism-motion.css` | 偏好文案、预览/焦点、即时按压 |
| `src/components/common/PageHeader.vue`、`src/views/ModuleDetailView.vue` | 标题锚点 |
| `src/views/{DashboardView,ModuleCenterView,InjectionSchedulingView}.vue` | 首屏所有权、锚点 |
| `src/features/uv-operations/{UvWorkspaceShell.vue,components/UvPageFrame.vue}` | UV 首屏消重，保留局部七页 |
| `src/features/three-d-printing/WorkspaceView.vue` | 3D 首屏消重 |
| `src/features/injection-scheduling/{components/DemandPool.vue,styles/motion.css}` | 注塑头部/需求池消重 |
| `src/style.css` | 删除旧 route-page；320px修复 |
| `src/router/__tests__/authorizationRefresh.spec.ts` | 补既有测试 active Pinia |
| `src/components/layout/__tests__/enterpriseUiShell.spec.ts`、`src/views/__tests__/productionModuleEntry.spec.ts` | 更新过时结构/样式/提取后目录实现断言 |
| `tsconfig.test.json` | 新测试类型检查 |
| `shared/assistant-help/modules/{portal,injection-scheduling,carton-procurement}.json` | 仅四处源码哈希同步，复核帮助内容无须改写 |
| `DESIGN.md`、`PROJECT_MEMORY.md` | 更新现有规范对应段落 |
| `.gitignore`、`docs/frontend/module-transitions/*.md` | 本目录 Markdown 窄例外和交付文档 |

## 验证与复现

原始日志：`D:/RR/outputs/module-transitions-20261022`。后期证据在仓库外，避免触发 Vite 刷新。

| 检查 | 结果 | 日志 |
| --- | --- | --- |
| 相关业务回归 | 29文件237测试通过；其后补返回帧/过滤焦点局部修复及目录测试有效授权夹具 | `final-regression-tests.log` |
| 最终导航专项 | 3文件40测试通过，覆盖最终源码 | `closure-motion-tests.log` |
| 测试类型检查 | 通过 | `closure-typecheck-test.log` |
| 完整构建 | assistant-help、vue-tsc、主 Vite、图片翻译类型/构建/发布边界全部通过；有既有大 chunk 提示 | `closure-build.log` |
| 独立浏览器后退脚本 | 现有 TypeScript 转译至临时目录后 Node 执行，退出0 | `browser-back-guard.log`（成功无输出） |
| 浏览器控制台 | 最终同一页面 warn/error 为0 | MCP末轮读取 |
| 补丁格式 | `git diff --check` 通过 | 最终交付检查 |

237与40有重叠，不能相加成277；也未宣称最终一次全业务测试运行239项。初始68项有3个既有失败，已修复测试初始化和旧断言；随后发现的生产入口旧断言按当前真实目录修正，不改变权限策略。

```powershell
npm run test:unit -- src/features/route-motion/__tests__
npm run typecheck:test
npm run build
node .tmp/module-transitions-back-guard/src/router/__tests__/browserBackExitGuard.test.js
git diff --check
```

29文件回归完整参数在日志首行。设置 `ROUTE_MOTION_COVERAGE_OUTPUT` 后运行 `catalog.spec.ts` 可重建目录矩阵。该测试使用显式合成读权限及UV/供应商专用有效授权快照，不登录、不授予真实权限、不替代真实账号验证。

## 回退

1. 即时关闭：现有首页外观 → 动效 → 关闭。偏好按账号保存，普通/fullPage共享。
2. 全局关闭新宿主：运行环境设置 `VITE_ROUTE_MOTION_ENABLED=false`，按现有流程重启开发进程或重新构建发布。Vite 在构建时读取该值，改环境文件不会即时更改已发布 bundle。模块既有局部首屏行为恢复；开关已自动化验证。
3. 移除实现：根据交付提交和实际后续改动，按本次 diff 逐项反向补丁并复核；不要对混合工作区整体 restore/reset，不删除原有输出或业务数据。仅在没有需要保留的后续交叉修改时，才对对应功能提交使用 git revert。

无需修改后端或数据库。剩余验证条件见 [ACCEPTANCE.md](./ACCEPTANCE.md)，全部目录结论见 [COVERAGE.md](./COVERAGE.md)。
