# 主题索引

[根记忆](../../PROJECT_MEMORY.md)记录跨模块约束，[仓库地图](repo-map.md)列开发入口和命令。查一项业务时，从它的专题、实际实现和对应测试开始。表中的测试用于定位已有契约。

## 账号、门户与工作台

| 主题 | 专题依据 | 源码入口 | 定向回归 |
| --- | --- | --- | --- |
| [账号与 IAM](../project-memory/platform.md#iam) | [iam-navigation.ts](../../src/components/iam/workspace/iam-navigation.ts) | [identity.py](../../backend/app/api/identity.py) | [test_iam_api.py](../../backend/tests/test_iam_api.py) |
| [集团首页](../project-memory/platform.md#dashboard) | [DashboardView.vue](../../src/views/DashboardView.vue) | [enterpriseMock.ts](../../src/data/enterpriseMock.ts) | [dashboardVisual.spec.ts](../../src/components/dashboard/__tests__/dashboardVisual.spec.ts) |
| [部门门户](../project-memory/platform.md#portal) | [WORKFLOWS.md](../frontend/WORKFLOWS.md) | [ModuleCenterView.vue](../../src/views/ModuleCenterView.vue) | [moduleCenterFactoryScope.spec.ts](../../src/views/__tests__/moduleCenterFactoryScope.spec.ts) |
| [通知与事项工作台](../project-memory/platform.md#work-center) | [IMPLEMENTATION.md](../work-center/IMPLEMENTATION.md) | [work_center.py](../../backend/app/api/work_center.py) | [test_work_center_api.py](../../backend/tests/test_work_center_api.py) |
| [模块目录与占位页](../project-memory/platform.md#catalog) | [pageAccessPolicy.ts](../../src/config/pageAccessPolicy.ts) | [enterpriseMock.ts](../../src/data/enterpriseMock.ts) | [productionModuleEntry.spec.ts](../../src/views/__tests__/productionModuleEntry.spec.ts) |
| [曜灵助手](../project-memory/platform.md#assistant) | [RUNBOOK.md](../assistant/RUNBOOK.md) | [assistant.py](../../backend/app/api/assistant.py) | [test_assistant_api.py](../../backend/tests/test_assistant_api.py) |

## 报价、订单与发票

| 主题 | 专题依据 | 源码入口 | 定向回归 |
| --- | --- | --- | --- |
| [内部报价与客价](../project-memory/commerce.md#quotes) | [internal-quote-collaboration-design.md](../business/internal-quote-collaboration-design.md) | [internal_quote.py](../../backend/app/api/internal_quote.py) | [test_internal_quote_api.py](../../backend/tests/test_internal_quote_api.py) |
| [客户订单中心](../project-memory/commerce.md#orders) | [customer-order-center-business-process.md](../business/customer-order-center-business-process.md) | [customer_order_ledger.py](../../backend/app/api/customer_order_ledger.py) | [test_customer_order_ledger.py](../../backend/tests/test_customer_order_ledger.py) |
| [大陆发票](../project-memory/commerce.md#mainland-invoice) | [mainland-invoice-deployment.md](../business/mainland-invoice-deployment.md) | [mainland_invoice.py](../../backend/app/api/mainland_invoice.py) | [test_mainland_invoice_api.py](../../backend/tests/test_mainland_invoice_api.py) |

## 采购、库存与工程物料

| 主题 | 专题依据 | 源码入口 | 定向回归 |
| --- | --- | --- | --- |
| [纸箱采购与仓库](../project-memory/warehouse.md#carton) | [纸箱模块业务逻辑说明书.md](../business/纸箱模块业务逻辑说明书.md) | [carton_procurement.py](../../backend/app/api/carton_procurement.py) | [test_carton_procurement_api.py](../../backend/tests/test_carton_procurement_api.py) |
| [华康 C 布料仓与半成品仓](../project-memory/warehouse.md#fabric) | [warehouse-framework-reuse-plan.md](../business/warehouse-framework-reuse-plan.md) | [warehouse_operations.py](../../backend/app/api/warehouse_operations.py) | [test_warehouse_operations.py](../../backend/tests/test_warehouse_operations.py) |
| [华康 C 工程 BOM 与物料计划](../project-memory/warehouse.md#bom) | [huakang-c-engineering-bom-requirements.md](../business/huakang-c-engineering-bom-requirements.md) | [engineering_bom.py](../../backend/app/api/engineering_bom.py) | [test_engineering_bom.py](../../backend/tests/test_engineering_bom.py) |

## 生产与质量

| 主题 | 专题依据 | 源码入口 | 定向回归 |
| --- | --- | --- | --- |
| [啤办生产与胶料](../project-memory/production.md#molding) | [molding-sample-business-flow.md](../business/molding-sample-business-flow.md) | [molding_sample.py](../../backend/app/api/molding_sample.py) | [test_molding_sample_api.py](../../backend/tests/test_molding_sample_api.py) |
| [华康 C 裁床](../project-memory/production.md#cutting) | [huakang-c-cutting-module-plan.md](../business/huakang-c-cutting-module-plan.md) | [cutting_operations.py](../../backend/app/api/cutting_operations.py) | [test_cutting_materials.py](../../backend/tests/test_cutting_materials.py) |
| [四厂注塑排产入口](../project-memory/production.md#injection) | [数据退役迁移](../../backend/alembic/versions/20261116_inj_retire_scheduling.py) | [占位页面](../../src/views/InjectionSchedulingPlaceholderView.vue) | [退役边界测试](../../backend/tests/test_injection_retirement.py) |
| [华康 A 3D 打印](../project-memory/production.md#three-d) | [three-d-printing-deployment.md](../three-d-printing-deployment.md) | [three_d_printing.py](../../backend/app/api/three_d_printing.py) | [test_three_d_printing_api.py](../../backend/tests/test_three_d_printing_api.py) |
| [QC 验货与审核](../project-memory/production.md#qc) | [qc-department-integration.md](../business/qc-department-integration.md) | [qc_department.py](../../backend/app/api/qc_department.py) | [test_qc_weekly_template_manifest.py](../../backend/tests/test_qc_weekly_template_manifest.py) |
| [喷油生产](../project-memory/production.md#spray) | [API 契约](../spray-production/API_CONTRACT.md) | [spray_operations.py](../../backend/app/api/spray_operations.py) | [test_spray_ops.py](../../backend/tests/test_spray_ops.py) |
| [华康 A UV 打印](../project-memory/production.md#uv) | [API 契约](../uv-operations/API_CONTRACT.md) | [uv_operations.py](../../backend/app/api/uv_operations.py) | [test_uv_ops.py](../../backend/tests/test_uv_ops.py) |

## 公共工具与印尼业务

| 主题 | 专题依据 | 源码入口 | 定向回归 |
| --- | --- | --- | --- |
| [公共文档工具与在线文档](../project-memory/documents-and-shipping.md#shared-tools) | [README.md](../document-tools/README.md) | [document_tools.py](../../backend/app/api/document_tools.py) | [test_document_tools_jobs.py](../../backend/tests/test_document_tools_jobs.py) |
| [箱唛与印尼发票核对](../project-memory/documents-and-shipping.md#marks-invoice) | [carton_mark.py](../../backend/app/api/carton_mark.py) | [indonesia_invoice.py](../../backend/app/api/indonesia_invoice.py) | [test_carton_mark_api.py](../../backend/tests/test_carton_mark_api.py) |
| [印尼走货明细](../project-memory/documents-and-shipping.md#shipping) | [indonesia-shipping.md](../indonesia-shipping.md) | [indonesia_shipping.py](../../backend/app/api/indonesia_shipping.py) | [test_indonesia_shipping.py](../../backend/tests/test_indonesia_shipping.py) |
| [送印尼物料（已下线）](../project-memory/documents-and-shipping.md#materials-id) | [历史实现](../business/indonesia-materials-implementation.md) | [历史接口实现](../../backend/app/api/indonesia_materials.py) | [test_indonesia_materials.py](../../backend/tests/test_indonesia_materials.py) |

## 发布、配置与历史

[已有现网更新与回退](../aliyun-docker-deploy.md) · [生效迁移图](../../backend/alembic/versions) · [代理配置](../../.codex/config.toml) · [历史资料与回执](../archive/README.md) · [旧记忆逐段去向](../archive/memory/README.md)
