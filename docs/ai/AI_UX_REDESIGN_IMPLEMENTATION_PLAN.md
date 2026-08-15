# Nexus Copilot Adaptive Workspace 实施计划

> 状态：已完成（开发文档 4.10 P2 按用户要求排除）
> 基线日期：2026-08-14
> 代码基线：本地 `main` / `e6c0e8816bca01097dae50df7ab8c4306f3e2e91`
> 测试仓库：`rrceshi3/main` / `c7850780034a1be0c155707ffc8d6593cf353328`

## 1. 范围与保护声明

本计划在现有 Nexus Intelligence Fabric 上增量完善 AI 表现层、会话上下文、工作台和交互外壳。不会重写 Orchestrator、Provider、Skill、Tool Registry、业务 Service、IAM、厂区隔离或 Action Gateway。

用户明确排除开发文档 4.10 所列的现场生产完成度门禁。本轮不声称闭环 TLS/HSTS、Secure Cookie、Provider Secret Rotation、OSS/KMS/ClamAV 现场证据、生产多实例/故障演练、成本告警现场确认或正式生产 `GO`。浏览器中的 UI 功能与安全验收仍在本轮范围内。

以下正式业务行为保持不变：报价公式与审批、注塑排产算法与发布状态、啤办状态流转、订单导入/确认/导出、库存与采购状态机、权限和厂区过滤、Preview 语义，以及唯一的 DRAFT Controlled Apply 路径。

## 2. 实施前审计基线

本节保留启动本批工作时的审计快照；完成后的现状与验证结果见第 12 节。

- 本地 `main` 跟踪 `rrceshi3/main`；两端提交图存在 27 个合并提交差异，但当前文件树无内容差异。
- 工作树没有已跟踪文件修改；存在用户已有的未跟踪 QA、artifact、data、截图和输出目录，本轮不读取为产品证据、不清理、不覆盖。
- 前端：Vue 3、TypeScript、Vite、Pinia、Tailwind CSS 4、Lucide、TanStack Table/Virtual。
- 后端：FastAPI、SQLAlchemy、Alembic；当前仓库迁移头为 `20260813_0075`。
- 当前有 158 个前端 spec 文件，其中 AI 相关 22 个；后端有 64 个 `test_ai_*.py` 文件。
- 基线验证：`npm run typecheck:test` 通过；`aiAssistantDrawer.spec.ts` 与 `aiWorkbench.spec.ts` 共 30 个测试通过。

## 3. 审计判断与复现

下表是实施前判断，用于说明本批工作的来源，不代表完成后的当前缺陷状态。

| 编号 | 文档判断 | 当前结论 | 代码证据 |
| --- | --- | --- | --- |
| 1 | Assistant 纯文本插值 | 仍成立 | `AiMessage.vue` 使用 `{{ message.text }}` |
| 2 | 每次流式 Delta 自动到底 | 仍成立 | `AiMessageList.vue` 监听消息长度并调用 `scrollTo(scrollHeight)` |
| 3 | Drawer 阻塞业务页面 | 仍成立 | 全屏遮罩、`aria-modal=true`、Body Scroll Lock |
| 4 | Workbench 发送 null Context | 仍成立 | `assistantStore.sendMessage(prompt, null)` |
| 5 | null Context 仅开放身份 Tool | 仍成立 | `ToolRegistry.is_in_request_scope()` 仅允许无权限 `identity` Tool |
| 6 | 会话缺少模块上下文绑定 | 仍成立 | `ai_conversations` 只保存 `factory_scope`，无可重新授权的模块绑定 |
| 7 | 结果/Evidence/活动为全局数组 | 仍成立 | Store 每次发送前清空三组数组 |
| 8 | 领域结果组件过度耦合 | 仍成立 | `AiBusinessResultCard.vue` 约 29 KB，聚合多个领域分支 |
| 9 | NIF-18 仍为 NO-GO | 仍成立但本轮排除现场闭环 | `PROJECT_MEMORY.md` 与 NIF-18 文档均保留现场门禁 |
| 10 | Flag/测试/迁移可能变化 | 已按本地代码更新 | AI Runtime 各能力默认关闭；迁移头 `0075` |

### 用户可见问题复现

1. Markdown 加粗、标题、列表和表格按普通文字显示。
2. 用户上滚阅读时，流式增量会把视图再次拉到底部。
3. 页面内助手打开后遮罩页面并锁定滚动，无法边看业务页面边提问。
4. 从业务页进入工作台后，后续请求只带会话 ID，不带原业务上下文。
5. 连续问两轮时，结构化结果、来源和 Tool 活动只保留最新一轮。
6. Workbench 在 `xl` 宽度永久保留 360px 右栏，即使任务和 Evidence 为空。
7. 会话栏缺少搜索、时间分组、重命名、固定和归档。

## 4. 目标架构与兼容策略

### 4.1 表现层

- 新增安全 Markdown Renderer，模型 HTML 默认禁用，输出再按严格白名单净化。
- Assistant 使用文档式 Turn；User 继续使用紧凑气泡。
- 领域结构化结果通过闭合 Registry 选择组件；未知合同只进入安全只读回退，不执行动态组件名或 HTML。
- Source Chip 与对应 Turn 绑定；原始 Tool/Evidence 标识只在技术详情显示。

### 4.2 轮次模型

- 新增 `AITurnPresentation`，绑定 request、user/assistant message、结果、活动、来源和 Evidence。
- 旧 `messages`、`activities`、`sources`、`businessResults` Store API 暂时保留为兼容视图。
- SSE 事件写入当前 Turn；持久历史按消息对重建只读 Turn，旧记录标注需要重新查询。

### 4.3 自适应 Surface

- `AiAssistantDrawer.vue` 保留为兼容入口，内部改用 Edge/Floating/Docked/Mobile Surface。
- Desktop 无遮罩、不锁 Body Scroll；Mobile Fullscreen 才使用模态语义和焦点限制。
- 仅把版本、模式、停靠侧、位置、尺寸和边缘高度写入 localStorage。
- Pointer Move 通过 `requestAnimationFrame` 合并；只在交互结束时持久化。

### 4.4 Workbench

- 左 Rail 可折叠并支持搜索、时间分组和状态。
- 中央 Conversation Canvas 使用文档式 Turn 和受控自动滚动。
- 右 Inspector 只在有内容或用户固定时打开，提供 Task/Evidence/Artifact/Action Tab 与宽度调整。
- 移动端把 Rail 和 Inspector 降级为按需抽屉/折叠区域。

### 4.5 上下文连续性

- 新增 AI 专用 Conversation Context 字段和 API，不修改业务表。
- Context Options 由服务端根据当前用户、厂区、模块白名单和 IAM 计算。
- Context Picker 的选择通过服务端验证后保存；每次发送仍调用 `build_server_page_context()` 重新授权。
- Workbench 不因全屏路由获得额外 Tool；跨厂区、未知模块、权限撤销和陈旧实体均失败关闭。

## 5. 数据库影响

计划新增两个仅影响 `ai_conversations` 的可回滚迁移：

1. Conversation Context：模块、路由、路径、上下文版本、可选实体类型/ID/Revision。
2. Conversation Management：`pinned_at`、`archived_at`。

约束：

- 不保存权限结果、Prompt、Tool 参数/正文、业务正文副本或业务表外键。
- 不修改任何报价、排产、订单、库存、采购或审批表。
- 升级为加列；降级只删除本批新增的 AI 列，不删除会话或消息。

## 6. API 兼容

- 现有 `/api/ai/responses`、SSE v1、Tool 合同和 Action Gateway 保持不变。
- `AIConversationListItem/Detail` 只增加有默认值的上下文和管理字段。
- 新增 `GET /api/ai/context-options`。
- 新增 `PATCH /api/ai/conversations/{id}/context`。
- 新增 `PATCH /api/ai/conversations/{id}` 用于重命名/固定/归档。
- 旧客户端未发送上下文时继续得到身份级能力；不会隐式扩大权限。

## 7. Feature Flag 与回滚

新增默认关闭的后端能力 Flag，并由 capabilities 暴露：

- `AI_RICH_MESSAGE_RENDERER_ENABLED`
- `AI_ADAPTIVE_SURFACE_ENABLED`
- `AI_WORKBENCH_V2_ENABLED`
- `AI_CONVERSATION_CONTEXT_ENABLED`
- `AI_PRESENTATION_BLOCKS_ENABLED`

前端在能力不存在或关闭时保留安全兼容行为；实现完成后本地测试可显式启用。回滚顺序：Presentation → Context → Workbench → Surface → Rich Text。旧 Store API、旧会话消息和 `AiAssistantDrawer.vue` 入口暂不删除。

## 8. 分批实施与验收

### Batch 1：安全 Rich Text

范围：Markdown、标题、列表、引用、代码、表格、安全链接、XSS、Streaming、复制。
验收：有效 Markdown 正常显示；HTML/Script/Event/JavaScript URL/Image/Iframe/Style 不执行；长表格只在自身区域滚动；旧纯文本仍可读。

### Batch 2：Adaptive Surface

范围：Edge、Floating、Drag、Resize、Dock Left/Right、Minimize、Viewport Clamp、Mobile Fullscreen、键盘和偏好。
验收：Desktop 页面仍可点击和滚动；Edge 不超过 42px；Resize 后不出视口；移动端无自由拖动；localStorage 无正文和业务数据。

### Batch 3：Workbench Shell

范围：可折叠 Rail、Conversation Canvas、Inspector Tabs、自动关闭、Splitter、Responsive、空状态。
验收：无内容不浪费右栏；用户可固定/调整 Inspector；长回答宽度合理；移动端可访问；业务示例按当前可用上下文展示。

### Batch 4：Turn Presentation

范围：Request/Message/Tool/Result/Source/Evidence/Feedback 绑定与旧 Store 兼容。
验收：连续两轮内容不串位；SSE 与持久恢复绑定正确；未知 Renderer 失败关闭；Feedback 仍指向持久消息或响应 ID。

### Batch 5：Context Continuity

范围：Context Options、Picker、Binding、请求重新授权、迁移与安全测试。
验收：业务页进入 Workbench 后仍可在同模块继续；跨厂区、未知模块、权限撤销、篡改 Payload 被拒绝；无 Context 时仍只有身份 Tool。

### Batch 6：Renderer Refactor

范围：组件 Registry、领域组件、统一表格/分页/来源、业务标签与技术详情。
验收：现有所有闭合结果合同继续渲染；原始 Tool 名不占主视觉；未知字段不展示；大型结果自身滚动。

### Batch 7：Prompt / Output Presentation

范围：Presentation Policy、简洁首答、不重复结构化表格、不暴露 Tool 名、截断下一步、Golden Eval。
验收：Prompt Compiler hash/版本测试更新；Tool 结构化结果存在时自然语言不逐行复述；Preview/Action 语义不变。

### Batch 8：Conversation Management

范围：Search、Rename、Pin、Archive、时间分组、Context/Factory/Task/Action 状态。
验收：搜索与分组可键盘使用；固定排序稳定；归档可恢复；删除仍保留原有审计边界。

### Batch 9：浏览器验收

范围：Desktop/Tablet/Mobile、Drag/Edge/Route/Persistence、Markdown/XSS、Context、Inspector、长表格、Task/Evidence/Artifact/Action。
验收：保存当前运行截图并逐张检查；控制台无新增错误；功能、布局、键盘、Reduced Motion 和业务页底层交互均有证据。4.10 的生产现场门禁不在本批结论内。

## 9. 测试计划

前端新增：

- `aiRichText.spec.ts`
- `aiSurface.spec.ts`
- `aiTurnPresentation.spec.ts`
- `aiWorkbenchLayout.spec.ts`
- 会话管理和 Context Picker 目标测试

后端新增：

- `test_ai_conversation_context.py`
- `test_ai_workbench_context.py`
- `test_ai_context_options.py`
- Conversation Management 与迁移测试

最终至少运行：

```text
npm run typecheck:test
npm run test:unit -- --run
npm run build
python -m pytest backend/tests/test_ai_*.py
python -m ruff check backend/app backend/tests
python -m alembic heads
git diff --check
```

若全量命令受本机依赖或运行时间限制，必须报告精确边界，并至少完成全部新增测试、既有 AI 目标回归、迁移头、类型检查和构建。

## 10. 主要风险与缓解

- Streaming Markdown 频繁解析：按时间片批量刷新，并限制单条消息长度。
- Surface Pointer 事件影响表单：只允许专用 Drag/Resize Handle 捕获 Pointer。
- 持久会话旧记录无 Context：显示“无业务上下文”，不根据正文猜权限。
- Context 绑定被误当权限快照：每次请求重新调用服务端 Context Builder 和 IAM。
- 迁移与旧数据库兼容：只增加可空/默认列，验证 SQLite/PostgreSQL DDL 路径和单一迁移头。
- 领域组件拆分引入合同漂移：继续复用现有闭合 Parser，组件只接受解析后的 Type。
- 大范围 UI 回归：保留兼容 Wrapper、分批目标测试、同视口浏览器截图和可回滚 Flag。

## 11. 完成边界

“实现完成”表示代码和自动化测试已落地；“已在本机验证”只覆盖实际执行并通过的命令和浏览器路径。任何未实际运行的生产部署、真实域名、TLS、外部告警、OSS/KMS、ClamAV、多实例或灾备演练不得称为已验证。

## 12. 完成结果（2026-08-14）

- Batch 1–5、7 已完成既定安全 Rich Text、自适应 Surface、Workbench、Turn Presentation、Context Continuity 与 Presentation Policy。
- Batch 6 已完成闭合 Renderer Registry、领域独立适配器、统一分页/来源/证据框架、业务化厂区与状态标签，以及默认折叠的技术详情；旧 `AiBusinessResultCard.vue` 仅保留轻量兼容入口。
- Batch 8 已完成搜索、时间分组、重命名、固定、归档、Context/Factory 展示，并在会话列表补齐 Task 与 Action 运行状态。
- Batch 9 已在本机生产构建预览中完成 Desktop `1440×900`、Tablet `1024×768`、Mobile `390×844`，以及浮动/左右停靠/最小化、跨路由模式恢复、键盘移动和缩放、底层业务页交互、会话上下文持久化、Inspector 四页签、真实只读 Tool 结果、Markdown/XSS、Reduced Motion、无横向溢出和控制台检查。
- 本地正式数据中内部报价为 0 条，因此现场验收覆盖真实空态、数据时间与来源链；7 条结构化结果的分页、翻页和服务端“仍有更多”提示由前端自动化测试覆盖，没有为了截图写入测试业务数据。

本机验证结果：

```text
npm run test:unit
  158 passed / 5 skipped spec files
  932 passed / 6 skipped tests

npm run typecheck:test
  passed

npm run build
  passed

backend test_ai_*.py（4 个隔离分组）
  457 passed / 2 skipped

python -m ruff check <本批 24 个新增或修改 Python 文件>
  passed

python -m alembic heads
  20260814_0077 (head)

git diff --check
  passed
```

仓库级 `ruff check backend/app backend/tests` 仍会命中本批范围外的历史规则债务；本批没有批量改写这些无关文件。开发文档 4.10 P2 的 TLS/HSTS、Secure Cookie、Secret Rotation、ClamAV/OSS/KMS 现场证据、生产告警/成本、多实例/故障演练及正式生产 `GO` 仍按用户要求不纳入本次完成结论。
