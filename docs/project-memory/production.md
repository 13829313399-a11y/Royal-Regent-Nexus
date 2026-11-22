# 生产与质量

[项目记忆](../../PROJECT_MEMORY.md) · [全部主题与验证入口](../agent-routing/context-index.md)

<a id="molding"></a>
## 啤办生产与胶料

`/api/injection` 属于啤办。工程来源厂与执行厂分别保存，华康 C/D 的任务要明确派往华康 A/B、华登或华兴。原料货号是集团共享主档，领料、冲销和库存流水归执行厂。任务可见与可写分别授权。

月报按业务开单日和执行厂取整月数据，逐模对计划、领用、消耗、配方、估价与已存结算金额。补领、冲销须有原始关联凭据。

[molding-sample-business-flow.md](../business/molding-sample-business-flow.md) · [molding_sample.py](../../backend/app/api/molding_sample.py) · [test_molding_sample_api.py](../../backend/tests/test_molding_sample_api.py)

旧版字段和例外可追溯至[啤办与集团胶料](../archive/memory/molding.md)。

<a id="cutting"></a>
## 华康 C 裁床

按本厂订单来源、BOM 执行版本和已发布任务领料。`POST /api/cutting-operations/orders/{line_id}/materials/{action}` 接受 request、receive、void、close、reuse，所属路由、授权和幂等身份见源码。仓库分批实发后裁床签收，工资、月结、委外对账和付款另有锁定与纠错流程。

P2b 原岗位验收件未找到，保留[独立验收说明](../business/huakang-c-cutting-independent-acceptance.md)和后续各期实录。正式切换仍依赖真实订单、岗位和凭单的闭环记录。

[huakang-c-cutting-module-plan.md](../business/huakang-c-cutting-module-plan.md) · [cutting_operations.py](../../backend/app/api/cutting_operations.py) · [test_cutting_materials.py](../../backend/tests/test_cutting_materials.py)

旧版字段和例外可追溯至[裁床主档、报工与结算](../archive/memory/cutting.md)、[裁床 P5 切换、岗位与性能记录](../archive/memory/cutting-p5.md)。

<a id="injection"></a>
## 四厂注塑排产入口

华兴、华登、华康 A/B 保留生产部卡片和 `/modules/production/injection-scheduling` 路径，按厂显示「待重新设计」。旧排程 API、曜灵查询与注塑排程专属权限已退役。啤办继续使用 `/api/injection`。

重建从上述空白入口开始，字段、算法与开账数据按本次重建确认的资料建立。

已发布的退役版本 `20261116_inj_retire` 以 `20261116_0195` 为父版本，在 `20261121_inj_merge` 与 `20261119_0197` 汇合。升级会删除旧排程表和专属授权，并检查其他业务依赖。部署前须停止相关写入，备份数据库与私有文件，在独立副本验证升级、恢复和其他业务数据。遇到同名迁移以 `20261107_0193` 为父版本的早期草稿时，先核对实际库结构与迁移来源。[退役迁移](../../backend/alembic/versions/20261116_inj_retire_scheduling.py) · [退役测试](../../backend/tests/test_injection_retirement.py)

<a id="three-d"></a>
## 华康 A 3D 打印

华康 A 区分云端观察、现场采集和设备控制。机台编号、注册身份及日期边界要和源记录核对，历史编号不回写。图片与附件保留版本，导入保留墓碑和既有历史。

18 台回传是指定时点的观测。远程暂停/继续、长时间无人值守、真实员工浏览器验证分别需要对应证据。生产更新需保护现网连接器、设备网络与专用覆盖配置。

[three-d-printing-deployment.md](../three-d-printing-deployment.md) · [three_d_printing.py](../../backend/app/api/three_d_printing.py) · [test_three_d_printing_api.py](../../backend/tests/test_three_d_printing_api.py)

旧版字段和例外可追溯至[3D 设备观察与历史迁移](../archive/memory/three-d.md)。

<a id="qc"></a>
## QC 验货与审核

网关按 Nexus 会话、操作者、厂区及 QC 权限授权。订单事实归业务部，QC 建检查任务并维护行验、客验、审核和退回。审核锁定、附件证据和重复导入按真实记录与已确认字段处理。日报、周报、月报从相应范围的验货事实汇总。

周报模板以[清单](../../backend/app/templates/qc-weekly/templates.json)和[加载服务](../../backend/app/services/qc_weekly_templates.py)核对。验货审核、退回与附件规则见[业务要求](../business/QC验货运营中心业务需求.md)和[运行契约](../business/qc-legacy-runtime-contract.md)。

[qc-department-integration.md](../business/qc-department-integration.md) · [qc_department.py](../../backend/app/api/qc_department.py) · [test_qc_weekly_template_manifest.py](../../backend/tests/test_qc_weekly_template_manifest.py)

旧版字段和例外可追溯至[QC 单据、验货与审核](../archive/memory/qc.md)。

<a id="spray"></a>
## 喷油生产

喷油使用独立 SprayOps 域，保存真实物料批次、工艺版本、容量计划、确认报工和交接记录。工时工资独立核算。连接器可用状态与现场核验分别记录。

导入保留原件、行列坐标和来源，操作授权按实际配置核对。阶段验收覆盖范围见所属文档。

[API 契约](../spray-production/API_CONTRACT.md) · [阶段验收](../spray-production/ACCEPTANCE.md) · [spray_operations.py](../../backend/app/api/spray_operations.py) · [test_spray_ops.py](../../backend/tests/test_spray_ops.py)

旧版字段和例外可追溯至[喷油流程与接入](../archive/memory/spray.md)。

<a id="uv"></a>
## 华康 A UV 打印

华康 A 独立 UvOps 域由 `UV_OPS_ENABLED` 控制。机台、夹具、子批、开完工、更正链及结算按业务记录处理，固定岗位不自动取得新增权限。

手工或模拟数据可验证软件流程。现场 PrintMon 采样、实际设备可读字段和设备控制分别取证。

[API 契约](../uv-operations/API_CONTRACT.md) · [阶段验收](../uv-operations/ACCEPTANCE.md) · [uv_operations.py](../../backend/app/api/uv_operations.py) · [test_uv_ops.py](../../backend/tests/test_uv_ops.py)

旧版字段和例外可追溯至[UV 工作区与设备证据](../archive/memory/uv.md)。
