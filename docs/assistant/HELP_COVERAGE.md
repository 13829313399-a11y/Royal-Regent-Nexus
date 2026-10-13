# 系统说明覆盖清单

16 条说明已对照当前源码核对；本次补齐原来 9 条部分覆盖总览的主要字段、状态、权限限制与操作步骤，并更新来源指纹。`verified` 表示该条所述规则已核对，不表示模块所有字段和所有子页面均已登记。

范围是 15 个模块总览及 1 个注塑关键字段说明。总览步骤定位模块总览锚点，并提示用户在原页面完成业务操作；没有把总览定位写成具体按钮已高亮或业务已办理。未注册字段继续明确提示暂无说明，源码变化会触发构建失败或运行时 needs_review。

| 模块 / 条目 | 受众 | 状态 | 已核对范围 | 代码依据 |
|---|---|---|---|---|
| carton-mark / carton-mark.overview | internal | verified | 核对客户资料、印刷文件与实物照片，分别保留自动结果和人工放行依据。 | backend/app/api/carton_mark.py :: auto-check；backend/app/services/carton_mark_library.py :: manually_release_carton_mark_template |
| carton-procurement / carton-procurement.overview | internal | verified | 从采购、供应商送货到仓库确认入库，分别核对数量、状态和结算期间。 | backend/app/services/carton_procurement.py :: required_carton_quantity；backend/app/services/carton_procurement.py :: confirm_receipt；backend/app/api/carton_procurement.py :: receipt-preview；src/router/index.ts :: carton-supplier-management |
| carton-supplier / carton-supplier.overview | supplier | verified | 采购订单、送货与仓库反馈在原页面查看。 | src/views/CartonSupplierView.vue :: shipmentStatus |
| customer-orders / customer-orders.overview | internal | verified | 订单台账维护数量与交期，下发和实际走货另行确认。 | backend/app/services/customer_order_ledger.py :: def amend；backend/app/services/customer_order_ledger.py :: def ship；backend/app/api/customer_order_ledger.py :: authorize |
| document-tools / document-tools.overview | all | verified | 源文件检查、处理任务、质量复核和结果下载是四个不同环节。 | backend/app/api/document_tools.py :: source_detail；backend/app/services/document_tools/job_service.py :: execution_status；backend/app/schemas/document_tools.py :: Operation =；backend/app/services/document_tools/pdf_geometry.py :: crop |
| identity-management / identity-management.overview | internal | verified | 先预览权限和任职影响，再由具备范围的管理人员确认变更。 | backend/app/api/identity.py :: preview_change；backend/app/services/identity_changes.py :: commit_change；backend/app/services/identity_changes.py :: result_out |
| injection-scheduling / injection.remaining_shots | internal | verified | 尚需完成的啤数，顺序啤数和同啤产物有不同口径。 | backend/app/services/injection_scheduling/calculations.py :: quantities；backend/app/services/injection_scheduling/field_registry.py :: FIELDS |
| injection-scheduling / injection-scheduling.overview | internal | verified | 排产、白夜班报工与基础资料分别维护。 | src/views/InjectionSchedulingView.vue :: switchTab |
| internal-quote / internal-quote.overview | internal | verified | 不同 module_version 的审核流程不同。 | backend/app/services/internal_quote.py :: _ensure_section_review_workflow |
| molding-sample / molding-sample.overview | internal | verified | 啤办申请、审核、承接生产、问题与完成记录按实际订单流程衔接。 | backend/app/services/molding_sample.py :: MOLDING_FACTORY_CAPABILITIES；backend/app/services/molding_sample.py :: BOARD_SOURCE_STATUSES；backend/app/schemas/molding_sample.py :: validate_material_components |
| portal / portal.overview | all | verified | 按当前厂区和部门查找可见模块，再进入对应业务页。 | src/config/pageAccessPolicy.ts :: allowAuthenticatedReadOnlyAccess；src/views/ModuleCenterView.vue :: visibleModules；src/views/ModuleCenterView.vue :: detailPage |
| qc-inspection / qc-inspection.overview | internal | verified | 区分验货主单进度、验货结果、问题处理和报告文件。 | backend/app/schemas/qc_inspection.py :: QcOrderStatus；backend/app/schemas/qc_inspection.py :: QcScheduleDecisionAction；backend/app/api/qc_inspection.py :: _ensure_permission |
| spray-production / spray-production.overview | internal | verified | 需求、调度、执行、交收和材料核算分别记录，避免把生产完成当成交收完成。 | src/features/spray-production/routes.ts :: sprayProductionRoutes；backend/app/services/spray_ops/schemas.py :: Factory =；backend/app/services/spray_ops/production.py :: start_task；backend/app/services/spray_ops/handover.py :: partial_accepted |
| three-d-printing / three-d-printing.overview | internal | verified | 设备状态描述遥测，不自动证明业务入库。 | src/features/three-d-printing/printerPresentation.ts :: printerStateText |
| uv-operations / uv-operations.overview | internal | verified | 当前 UV 工作区固定为华康 A。 | src/features/uv-operations/contracts.ts :: UV_FACTORY |
| work-center / work-center.overview | internal | verified | 阅读状态与业务办理状态是两件事。 | backend/app/services/work_center/service.py :: flags |

校验：`node scripts/check-assistant-help.mjs` 返回 articles=16、partial=[]、issues=[]；源码指纹测试和完整构建均检查相同注册表。证据见 `D:/RR/assistant-closure-20261008/`。
