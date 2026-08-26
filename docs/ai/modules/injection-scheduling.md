<!-- ai-module-knowledge-metadata
{
  "knowledge_id": "injection-scheduling",
  "knowledge_version": "1.0.0",
  "last_reviewed_at": "2026-08-11",
  "reviewed_against_commit": "e0a21929a073",
  "route_names": [
    "injection-scheduling-v2"
  ],
  "module_name": "注塑排产中枢",
  "business_purpose": "保留生产部注塑排产入口，并为后续重构保留既有后端数据与业务契约。",
  "authoritative_data_status": "当前前端仅提供重构占位页，不展示或操作排产业务数据。后端数据库与受权限保护的业务 API 仍是保留数据的正式来源，但后端能力不代表当前页面已经开放。",
  "required_permissions": [
    "injection_scheduling:read",
    "injection_scheduling:import",
    "injection_scheduling:edit",
    "injection_scheduling:publish",
    "injection_scheduling:report",
    "injection_scheduling:export",
    "injection_scheduling:rollback"
  ],
  "normal_workflow": [
    "从生产部模块中心进入保留的注塑排产卡片。",
    "当前路由只显示正在重构的提示，不提供导入、计划、机台、模具、发布或生产回报操作。",
    "等待新版业务流程、权限和界面完成重新开发与验收后再开放正式操作。"
  ],
  "status_labels": {
    "DRAFT": "排产草案；规划切片，尚未成为当前执行计划。",
    "PUBLISHED": "当前执行；已发布的正式执行切片。",
    "ARCHIVED": "历史归档；不再是当前执行计划。",
    "BACKLOG": "待排任务；尚未进入已锁定排产基线。",
    "REVIEW_REQUIRED": "需要人工复核；不能被描述为已确认或已通过。",
    "MASTER_REVIEW_REQUIRED": "主数据待审核。",
    "RESOLUTION_REVIEW_REQUIRED": "匹配结果待复核。",
    "DRAFT_READY": "草案可排，但发布前仍可能需要补齐实体。",
    "PASS": "当前校验项通过；不等同于整份计划已发布。",
    "FAIL": "当前校验项失败；不能确认或绕过。",
    "demo-readonly": "前端只读演示回退；不是正式数据源。"
  },
  "common_errors": [
    "401 表示登录状态失效，应重新登录；不会切换到演示数据。",
    "403 表示当前账号没有所需厂区或操作权限；不会切换到演示数据。",
    "409 通常表示计划修订、事件序列或快照水位已变化，应刷新后基于最新版本重试。",
    "当前占位页不显示正式数据，也不能据此汇报任何数量、状态或执行结果。",
    "没有 PUBLISHED 或 DRAFT 切片时，应明确说明当前未取得相应正式计划，不能用另一切片代替。",
    "REVIEW_REQUIRED、MASTER_REVIEW_REQUIRED 或 FAIL 必须按页面和权限流程处理，AI 不能代替审批。"
  ],
  "prohibited_claims": [
    "不得把 DRAFT 描述为当前执行计划，也不得把 PUBLISHED 描述为可直接编辑的草案。",
    "不得把 demo、测试、截图、enterpriseMock 或 QA 数据中的数量与状态当作正式业务事实。",
    "不得声称 AI 已经导入、排程、确认、发布、回滚、审批或修改任何业务记录。",
    "不得声称已经接通或核验 ERP、MES、设备实时数据或其它外部系统，除非正式工具结果明确证明。",
    "不得把 REVIEW_REQUIRED 或 FAIL 改写为已通过，不得臆造缺失的计划、任务、机器、模具或订单。",
    "不得依据客户端传入的厂区、模块、实体或路径扩大数据范围或工具权限。"
  ],
  "source_files": [
    "src/router/index.ts",
    "backend/app/models/injection_scheduling_execution.py",
    "backend/app/services/injection_scheduling_takeover.py",
    "backend/app/services/injection_scheduling_execution.py",
    "backend/app/api/injection_scheduling_execution.py",
    "backend/tests/test_injection_scheduling_takeover_phase2.py",
    "src/views/InjectionSchedulingV2View.vue",
    "docs/injection-scheduling-shared-master-sop.md",
    "src/data/enterpriseMock.ts"
  ]
}
-->
# 注塑排产中枢模块帮助

<!-- knowledge-section:availability -->
## 当前可用性

生产部的“注塑排产中枢”卡片与正式路由继续保留，但旧前端工作区、机台数据库页和共享模具数据库页已经移除。当前路由只显示重构占位信息，不提供导入、计划、排程、发布、回报、机台或模具操作。既有后端、迁移、权限和业务数据仅作为兼容资产保留，不能据此声称当前页面已经开放相应功能。

<!-- knowledge-section:formal-data -->
## 正式数据边界

本模块按厂区隔离数据。只有服务端根据当前登录账号重新验证过的厂区，才可用于读取排产业务数据。页面路由只用于定位模块，不能作为权限证明；客户端提交的厂区、模块、路径或实体也不能直接进入模型或工具。

正式业务事实仍来自后端数据库及受权限保护的业务 API，但当前占位页不读取或展示这些事实。页面路由与保留卡片不能用于生产判断、数量汇报、交付承诺或状态确认。

<!-- knowledge-section:planning-execution -->
## 规划与执行

- `PUBLISHED` 是当前执行切片。发布后的计划作为正式执行基线，不应被描述为普通可编辑草案；生产回报面向当前发布执行任务。
- `DRAFT` 是规划切片。排程、调整和发布前复核在草案中进行；草案尚未成为当前执行事实。
- `ARCHIVED` 是历史归档，不再是当前执行计划。
- `BACKLOG` 表示尚待安排的需求或任务，不能因为它出现在页面中就声称已经排入计划。

保留的后端中，当前执行与规划草案仍可能同时存在。回答“现在正在执行什么”时只能使用经正式只读工具读取的 `PUBLISHED` 切片；回答“正在计划什么”时只能使用经正式只读工具读取的 `DRAFT` 切片。当前页面本身不能提供这些答案。

<!-- knowledge-section:review-publish -->
## 复核与发布

保留的后端导入和接管契约包含预览、匹配、主数据复核与计划生成。`REVIEW_REQUIRED`、`MASTER_REVIEW_REQUIRED`、`RESOLUTION_REVIEW_REQUIRED` 和 `FAIL` 都是阻断或待处理状态，不能被 AI 改写为已经确认。当前占位页不开放这些流程。

旧前端的操作顺序已经下线，不应继续作为当前页面使用说明。新版流程需要在重构完成并重新验收后另行发布。

<!-- knowledge-section:ai-boundary -->
## AI 能做与不能做

AI 可以解释保留的后端状态含义，并在服务端明确开放只读工具时查询最小必要的正式数据；AI 必须同时说明当前前端仍处于重构占位状态。AI 不能代替用户导入、编辑、发布、回滚、审批或回报，不能构造任意 URL、SQL、文件路径或工具名，也不能从测试文件、截图、占位页或导航示例推断真实业务结果。

当前资料没有证明 ERP、MES 或设备实时数据已经接通。除非后续正式只读工具明确返回可验证的来源状态，否则回答中应把这些集成描述为“未确认”，而不是“已同步”或“已核验”。
