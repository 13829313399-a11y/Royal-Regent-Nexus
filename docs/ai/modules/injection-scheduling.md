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
  "business_purpose": "按厂区隔离注塑排产数据，区分规划草案与当前执行计划，支持主数据复核、草案排程、发布以及发布后的生产回报。",
  "authoritative_data_status": "后端数据库与受权限保护的业务 API 返回值是正式数据来源。PUBLISHED 表示当前执行计划，DRAFT 表示尚未发布的规划草案；前端只读演示回退、测试夹具和页面示例均不是正式业务事实。",
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
    "选择当前账号有读取权限的厂区，并先确认页面数据源状态。",
    "查看 PUBLISHED 当前执行切片；需要调整时进入或创建 DRAFT 规划草案。",
    "导入前先预览、匹配并处理需要人工复核的主数据或业务标识。",
    "只在 DRAFT 中安排或调整任务，复核冲突、机器、模具、人员及物料约束。",
    "具备发布权限的用户发布通过校验的草案，使其成为新的 PUBLISHED 当前执行计划。",
    "只对 PUBLISHED 当前执行任务进行正式生产回报；导出与回滚仍分别受权限控制。"
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
    "页面显示只读演示数据时，只能用于界面浏览，不能据此汇报真实数量、状态或执行结果。",
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
    "src/features/injection-scheduling-v2/api/injectionSchedulingV2Api.ts",
    "src/features/injection-scheduling-v2/stores/useInjectionSchedulingV2Store.ts",
    "src/features/injection-scheduling-v2/presentation/schedulingLabels.ts",
    "PROJECT_MEMORY.md",
    "docs/injection-scheduling-shared-master-sop.md",
    "src/data/enterpriseMock.ts"
  ]
}
-->
# 注塑排产中枢模块帮助

## 正式数据边界

本模块按厂区隔离数据。只有服务端根据当前登录账号重新验证过的厂区，才可用于读取排产业务数据。页面路由只用于定位模块，不能作为权限证明；客户端提交的厂区、模块、路径或实体也不能直接进入模型或工具。

正式业务事实来自后端数据库及受权限保护的业务 API。页面若标记为“只读演示数据”或 `demo-readonly`，说明当前展示的是前端回退数据，只能帮助理解界面，不能用于生产判断、数量汇报、交付承诺或状态确认。401、403 与其他业务类 4xx 不会触发演示回退；仅初始加载时符合条件的网络错误或 5xx 才可能进入只读回退。

## 规划与执行

- `PUBLISHED` 是当前执行切片。发布后的计划作为正式执行基线，不应被描述为普通可编辑草案；生产回报面向当前发布执行任务。
- `DRAFT` 是规划切片。排程、调整和发布前复核在草案中进行；草案尚未成为当前执行事实。
- `ARCHIVED` 是历史归档，不再是当前执行计划。
- `BACKLOG` 表示尚待安排的需求或任务，不能因为它出现在页面中就声称已经排入计划。

当前执行与规划草案可以同时存在。回答“现在正在执行什么”时应使用经工具读取的 `PUBLISHED` 切片；回答“正在计划什么”时应使用经工具读取的 `DRAFT` 切片。缺少某个切片时必须说明缺失，不能用另一个切片冒充。

## 复核与发布

导入和接管流程包含预览、匹配、主数据复核与计划生成。`REVIEW_REQUIRED`、`MASTER_REVIEW_REQUIRED`、`RESOLUTION_REVIEW_REQUIRED` 和 `FAIL` 都是阻断或待处理状态，不能被 AI 改写为已经确认。任何需要覆盖原因、主管权限或发布权限的动作仍由业务页面与后端权限规则执行。

典型顺序是：确认授权厂区与数据源状态，查看当前发布执行计划，创建或继续规划草案，导入并复核来源数据，在草案中排程和处理冲突，发布通过校验的草案，随后对发布任务进行生产回报。

## AI 能做与不能做

AI 可以解释本模块的状态含义和正常流程，并在服务端明确开放只读工具时查询最小必要的正式数据。AI 不能代替用户导入、编辑、发布、回滚、审批或回报，不能构造任意 URL、SQL、文件路径或工具名，也不能从测试文件、截图、演示数据或导航示例推断真实业务结果。

当前资料没有证明 ERP、MES 或设备实时数据已经接通。除非后续正式只读工具明确返回可验证的来源状态，否则回答中应把这些集成描述为“未确认”，而不是“已同步”或“已核验”。
