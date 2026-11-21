# 账号、门户与工作台

[项目记忆](../../PROJECT_MEMORY.md) · [全部主题与验证入口](../agent-routing/context-index.md)

<a id="iam"></a>
## 账号与 IAM

账号凭证建立服务端会话。注册、同浏览器重置、岗位申报分别持久化。固定职位由后端目录维护，任职来源、生效时间、employment epoch 与显式拒绝共同决定实际权限。身份交接只转移允许接手的业务对象，历史作者和审计来源保留。集团总经理跨厂业务授权与系统管理员通配权分开。

默认入口在 `/system`。开发与兼容预览按构建开关选择界面。生产 Web 使用 Studio，构建时须同时开启 `VITE_IAM_IDENTITY_UI_ENABLED`、`VITE_POSITION_WORKBENCH_ENABLED`、`VITE_IAM_CONSOLIDATED_UI_ENABLED` 和 `VITE_IAM_STUDIO_ENABLED`。发布及回退按实际路由和组件验收静态包，运行与站点回执应与获准候选一致。[Web 成品验收](../aliyun-docker-deploy.md#iam-前端包验收与回退) 查看权限、身份写入和 Studio 写入各受后端控制。Studio 写入还须核对 `IAM_ACCESS_STUDIO_WRITES_ENABLED`、身份写入及授权模式等[服务端条件](../../backend/app/services/access_studio.py)。兼容深链、授权对账、回退及旧截图见[版本资料](../archive/README.md)。

[iam-navigation.ts](../../src/components/iam/workspace/iam-navigation.ts) · [identity.py](../../backend/app/api/identity.py) · [test_iam_api.py](../../backend/tests/test_iam_api.py)

旧版字段和例外可追溯至[身份、授权与历史环境](../archive/memory/iam.md)、[架构入口、全局约束与鉴权](../archive/memory/platform-contracts.md)。

<a id="dashboard"></a>
## 集团首页

首页的指标、厂区热图和跨厂待办来自展示数据。本周筛选、导出按钮的可用性由真实接入决定。示例指标不得作为业务产量或现场在线率。

变更正式统计前须确认来源、口径、厂区和权限。

[DashboardView.vue](../../src/views/DashboardView.vue) · [enterpriseMock.ts](../../src/data/enterpriseMock.ts) · [dashboardVisual.spec.ts](../../src/components/dashboard/__tests__/dashboardVisual.spec.ts)

旧版字段和例外可追溯至[首页指标与展示](../archive/memory/dashboard.md)。

<a id="portal"></a>
## 部门门户

各部门首页复用同一门户组件。路由参数改变时重新计算展示与厂区范围。模块可见性、页面准入和服务端业务权限分别执行。

展示数据、空状态、响应式和可用操作按目标厂区及真实路由核对。

[WORKFLOWS.md](../frontend/WORKFLOWS.md) · [ModuleCenterView.vue](../../src/views/ModuleCenterView.vue) · [moduleCenterFactoryScope.spec.ts](../../src/views/__tests__/moduleCenterFactoryScope.spec.ts)

旧版字段和例外可追溯至[部门门户与导航](../archive/memory/portal.md)。

<a id="work-center"></a>
## 通知与事项工作台

通知页与顶部铃铛共用工作台。是否已读属于个人，完成业务待办必须由原模块处理并产生事实。列表、数量、退回链接及处理动作按当前操作者权限取数。

新来源须明确责任人、可见范围、结束条件和回到原单的入口。

[IMPLEMENTATION.md](../work-center/IMPLEMENTATION.md) · [work_center.py](../../backend/app/api/work_center.py) · [test_work_center_api.py](../../backend/tests/test_work_center_api.py)

旧版字段和例外可追溯至[工作台事项与阅读](../archive/memory/work-center.md)。

<a id="catalog"></a>
## 模块目录与占位页

模块目录同时承载业务入口和演示卡片。判断能力需找到已注册路由、客户端、服务端与测试。船务管理等入口另按明确厂区范围展示。

未接通的卡片由业务决定接入、保留占位或移除。

[pageAccessPolicy.ts](../../src/config/pageAccessPolicy.ts) · [enterpriseMock.ts](../../src/data/enterpriseMock.ts) · [productionModuleEntry.spec.ts](../../src/views/__tests__/productionModuleEntry.spec.ts)

旧版字段和例外可追溯至[目录与规划中卡片](../archive/memory/catalog.md)。

<a id="assistant"></a>
## 曜灵助手

曜灵使用独立 `/api/assistant`。会话、运行、重试及 SSE 恢复保留身份与请求绑定，业务事实只能在当前身份和数据范围内查询。搜索、附件解析及持久运行依各自配置和服务端能力响应。

`0188/0189` 是助手迁移身份。旧库冲突处理与功能版本见[迁移说明](../assistant/MIGRATION_IDENTITY.md)，全库终点从部署版本的迁移图读取。

[RUNBOOK.md](../assistant/RUNBOOK.md) · [assistant.py](../../backend/app/api/assistant.py) · [test_assistant_api.py](../../backend/tests/test_assistant_api.py)

旧版字段和例外可追溯至[曜灵运行与数据边界](../archive/memory/assistant.md)。

## 跨域背景

[金蝶工作流及样本的适用范围](../archive/memory/platform-history.md) · [发布与迁移的历次记录](../archive/memory/release.md) · [当轮待决事项与测试基线](../archive/memory/open-issues.md)
