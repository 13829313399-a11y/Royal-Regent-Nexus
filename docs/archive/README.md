# 历史资料与验收记录

生效的业务规则、操作手册和权限入口由[项目记忆](../../PROJECT_MEMORY.md)及[主题索引](../agent-routing/context-index.md)维护。查当时的范围、例外、证据或未决项时，用下面的资料。

## 后续任务归档

按[任务生命周期](../agent-routing/task-lifecycle.md)关闭复杂任务；完整任务报告与原始证据归仓库外本地任务档案，保留候选和哈希。仅经明确授权将脱敏的长期追溯摘要存于 completed/tasks/，不把历史交付重新当成现行指令。

## 移入专题的原文

| 主题 | 记录与现行入口 |
| --- | --- |
| 仓库交接（截至 2026-11-18） | [布料仓、裁床、纸箱仓与东康交接](warehouse/progress-20261118.md)。未决业务在[仓库专题](../project-memory/warehouse.md#fabric)。 |
| 两次视觉验收 | [IAM 注册审批](iam/registration-design-qa.md) · [Document Studio](document-studio/design-qa.md)。原机截图路径随原文保存。 |
| 早期同步文档工具 | [原始基线](document-studio/baseline.md) · [当时的实现情况](document-studio/implementation-status.md) · [当时的启用步骤](document-studio/activation-runbook.md)。现行[异步工具](../document-tools/README.md)，精度要求见[评估依据](../document-studio/evaluation.md)。 |
| 曜灵立项 | [初建委托](assistant/00_CODEX_START.md) · [立项时的代码核查](assistant/02_CODE_AUDIT.md)。[现行运行手册](../assistant/RUNBOOK.md)继续维护。 |
| 在线文档 | [2026-10-27 交接](document-tools/ONLINE_DOCUMENTS_HANDOFF_2026-10-27.md)记录 PR #541 的范围与当时验收。[维护入口](../document-tools/online-documents.md) |
| 项目记忆旧稿 | [逐段对照](memory/README.md)按范围定位 `b178eb67` 旧稿中的来源、客户或岗位例外、测试与发布观察。 |

## 历史版本资料（含已归档交付）

下列验收、交付和基线仅作历史追溯；已完成的独立报告整理至 completed/，保留原路径信息及相对引用。不得把历史开发步骤、旧视觉指标或当时的结论当成当前任务指令。

### 其他业务验收

- [成员协作 R1 实施与验收](completed/collaboration-r1.md)
- [QC 完整系统集成：审查与发布约束](../business/qc-full-integration-20261105.md)
- [QC 模块版本、主分支兼容性与 Git 安全同步审计](../business/qc-production-audit-20261104.md)
- [纸箱模块上线前最终验收报告](completed/business/纸箱上线前最终验收报告.md)
- [纸箱模块全流程核查报告](completed/business/纸箱全流程核查报告.md)
- [人员与权限工作区：设计与验收](completed/frontend/IAM_UI_REFRESH.md)

### 设备与生产

- [PR-06 本地代码验收](completed/three-d-pr06-acceptance.md)
- [PR-07～PR-09 本地开发交付与验收](completed/three-d-pr07-pr09-acceptance.md)
- [本地实现与验收证据](../spray-production/ACCEPTANCE.md)
- [喷油部重建实施计划](completed/spray-production/IMPLEMENTATION_STATUS.md)
- [只读原件核验](completed/spray-production/SOURCE_AUDIT.md)
- [A01–A39 验收台账](../uv-operations/ACCEPTANCE.md)
- [实施状态 · 2026-09-29](completed/uv-operations/IMPLEMENTATION_STATUS.md)
- [UV 软件与合成数据验收 · 2026-09-29](completed/uv-operations/SOFTWARE_ACCEPTANCE_20260929.md)
- [验证记录](../uv-operations/TEST_EVIDENCE.md)
- [视觉与交互验收](completed/uv-operations/VISUAL_QA.md)
- [UV 动效验收矩阵执行结果](completed/uv-operations/frontend-motion/ACCEPTANCE.md)
- [UV 工作区交互与动效实施记录](completed/uv-operations/frontend-motion/IMPLEMENTATION.md)

### 曜灵

- [曜灵逐项验收矩阵](completed/assistant/ACCEPTANCE.md)
- [曜灵实施与验收](completed/assistant/IMPLEMENTATION.md)
- [曜灵本地接入记录](completed/assistant/LOCAL_ACTIVATION.md)
- [千问本地连接验证](completed/assistant/MODEL_CONNECTION.md)
- [分离复审与修复记录](completed/assistant/REVIEW.md)

### 裁床与物料

- [华康 C 裁床 P3b：本地启用与验收清单](completed/business/huakang-c-cutting-p3b-local-acceptance.md)
- [华康 C 裁床 P4a：月结前核对验收](completed/business/huakang-c-cutting-p4a-acceptance.md)
- [华康 C 裁床部 P4b 首批：内部月结与锁月](completed/business/huakang-c-cutting-p4b-acceptance.md)
- [华康 C 裁床部 P4c 首批：外发加工费对账与结算](completed/business/huakang-c-cutting-p4c-acceptance.md)
- [华康 C 裁床部 P4d 首批：外发加工费付款登记与核销](completed/business/huakang-c-cutting-p4d-acceptance.md)
- [华康 C 裁床部 P4e：月结报表与冻结导出](completed/business/huakang-c-cutting-p4e-acceptance.md)
- [华康 C 裁床部 P5a 首批：历史期初核对与切入准备](completed/business/huakang-c-cutting-p5a-acceptance.md)
- [华康 C 裁床部 P5b：全流程与正式岗位验收](completed/business/huakang-c-cutting-p5b-acceptance.md)
- [裁床部 P5c：性能、打印与上线准备](completed/business/huakang-c-cutting-p5c-acceptance.md)
- [裁床工作区界面改版与验收](completed/cutting/cutting-workspace-redesign-acceptance.md)

### 文档工具

- [文档工作台前端验证](completed/document-tools/frontend-qa.md)
- [Office 文档引擎实测记录](../document-tools/office-accuracy.md)
- [PDF 引擎验证记录](../document-tools/pdf-accuracy.md)
- [公共工具栏本地验收](../document-tools/validation.md)

### 部门门户

- [模块导航过场验收报告](completed/frontend/module-transitions/ACCEPTANCE.md)
- [模块目录覆盖矩阵](../frontend/module-transitions/COVERAGE.md)
- [模块导航过场实施交付](completed/frontend/module-transitions/IMPLEMENTATION.md)

### 身份与岗位

- [权限模块整合验收](completed/iam-consolidation/acceptance.md)
- [IAM consolidation baseline and implementation plan](completed/iam-consolidation/baseline.md)
- [IAM V2 开发交付](../iam-v2-20260926/README.md)
- [Royal-Regent-Nexus｜人员、任职与权限管理 V2](../iam-v2-20260926/Royal-Regent-Nexus-IAM-V2-Codex-Spec.md)
- [IAM 界面重构：交付与验收](../iam-v2-20260926/UI-UX-交付与验收-20260928.md)
- [IAM V2 验收证据](completed/iam-v2-20260926/acceptance.md)
- [人员与权限 V2：基线与实施计划](completed/iam-v2-20260926/iam-v2-baseline.md)
- [IAM V2 独立复核](completed/iam-v2-20260926/independent-review.md)
- [52 条验收规格覆盖追踪](completed/position-workbench/acceptance-trace.md)
- [人员与权限轻流程实现](../position-workbench/implementation-map.md)
- [验证边界与已知事项](../position-workbench/known-issues.md)
- [人员与权限实现验证](completed/position-workbench/test-results.md)
