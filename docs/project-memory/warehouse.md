# 采购、库存与工程物料

[项目记忆](../../PROJECT_MEMORY.md) · [全部主题与验证入口](../agent-routing/context-index.md)

<a id="carton"></a>
## 纸箱采购与仓库

正单、样板单及杂单按厂共用台账。供应商送货与仓库实收分别留单，收货需记录实物数量和库位，改错走可追溯的更正或冲销。零价不能自行推定免费。月结使用已确认的价格与收发凭据，原始 Excel、箱唛版本及订单关联保留。

基础资料的状态操作可对照[资料方案](../business/纸箱模块-基础资料建设方案.md)和[状态接口](../../backend/app/api/carton_materials.py)。旧仓库独立操作指引未找回。明细分为订单与收货、采购协同、基础资料与库存三册。

[纸箱模块业务逻辑说明书.md](../business/纸箱模块业务逻辑说明书.md) · [carton_procurement.py](../../backend/app/api/carton_procurement.py) · [test_carton_procurement_api.py](../../backend/tests/test_carton_procurement_api.py)

旧版字段和例外可追溯至[纸箱订单、送货与实收](../archive/memory/carton.md)、[纸箱采购协同、异常与价格](../archive/memory/carton-collaboration.md)、[纸箱基础资料、箱唛与库存](../archive/memory/carton-inventory.md)。

<a id="fabric"></a>
## 华康 C 布料仓与半成品仓

两个仓库各自保存单据、来源与流水。布料出库按实际卷、缸、库位和原单位，可分批发料。裁床提交申请，仓管实发，裁床按实物签收。申请数量、实发数量与裁床在手数量分别对账。退料关联原发料和仓库实收位置。

仓管从原出库退料、裁床查看回传已有旧交接记录。裁床主动申请后由仓库验收的双边退料、两仓委外开单责任、同一张真实订单的跨部门配料和岗位试走均须单独核实。[仓库交接与未决事项](../archive/warehouse/progress-20261118.md)

[warehouse-framework-reuse-plan.md](../business/warehouse-framework-reuse-plan.md) · [warehouse_operations.py](../../backend/app/api/warehouse_operations.py) · [test_warehouse_operations.py](../../backend/tests/test_warehouse_operations.py)

旧版字段和例外可追溯至[布料仓、半成品仓与采购交接](../archive/memory/fabric.md)。

<a id="bom"></a>
## 华康 C 工程 BOM 与物料计划

工程维护版本、来源、物料匹配与用量依据，业务确认订单需求，采购按批准来源办单。工程版本的审批和向裁床发布是两步。试算、候选匹配或旧表的示例系数不能直接变成正式采购数量。

恢复或切换须按版本核对原始行和单位。[工程审批检查](../business/huakang-c-engineering-bom-approval-check.md)与[物料计划流程](../business/huakang-c-material-plan-workflow.md)分别说明职责。

[huakang-c-engineering-bom-requirements.md](../business/huakang-c-engineering-bom-requirements.md) · [engineering_bom.py](../../backend/app/api/engineering_bom.py) · [test_engineering_bom.py](../../backend/tests/test_engineering_bom.py)

旧版字段和例外可追溯至[工程 BOM 与物料接续](../archive/memory/bom.md)。
