# 生产与质量

[项目记忆](../../PROJECT_MEMORY.md) · [全部主题与验证入口](../agent-routing/context-index.md)

<a id="molding"></a>
## 啤办生产与胶料

`/api/injection` 属于啤办。工程来源厂与执行厂分别保存，华康 C/D 的任务要明确派往华康 A/B、华登或华兴。原料货号是集团共享主档，领料、冲销和库存流水归执行厂。任务可见与可写分别授权。

月报按业务开单日和执行厂取整月数据，逐模对计划、领用、消耗、配方、估价与已存结算金额。补领、冲销须有原始关联凭据。

内部啤办任务完成后，承接厂有啤机回填权限的人员仍可按模具补填、修改试模报告。工程部查看最新报告，原任务的完工日期和结算记录保留。

[molding-sample-business-flow.md](../business/molding-sample-business-flow.md) · [molding_sample.py](../../backend/app/api/molding_sample.py) · [test_molding_sample_api.py](../../backend/tests/test_molding_sample_api.py)

旧版字段和例外可追溯至[啤办与集团胶料](../archive/memory/molding.md)。

<a id="cutting"></a>
## 华康 C 裁床

从裁床打开布料仓原采购明细时，重试焦点意图限定原明细与原账号。连续 403 及授权刷新重建按钮后，未主动移焦时恢复重试按钮；聚焦或点击其他位置、按 Tab、切换账号／明细及卸载时取消恢复。相同列表与明细权限错误只显示一次。列表汇总按自身请求区分读取中、读取失败和无读取权限，成功才显示真实数量（含零）；详情单独失败不覆盖有效列表，旧请求失败不覆盖新结果。会话过期后的登录返回地址保留厂区、视图与原明细编号，撤权清除旧业务数据。

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

报告中心的八个日、周、月、年报模板均在完整工作簿中开放有权限的空白业务字段，以浅绿色底色提示，不加角标。桌面工作簿保留四边留缝的圆角弹窗，原表可等比适宽。桌面单击选格，双击或 F2 编辑，方向键及 Shift 支持移动和扩选，支持选区复制粘贴与撤销／重做。Ctrl+D 和右下角手柄只填同列同类的空白补录格；已有内容和只读格不会被填充。已审核原值、统计合计、公式和来源身份保持只读。

工作簿补录只在当前标签页暂存，Ctrl+S／⌘S 或主动确认保存后才提交；不因切工作表或隐藏页面触发自动保存。关闭或切换模板可保存、放弃这次更改或取消；带未保存内容导出时先确认保存。保存失败保留草稿并沿用现有版本和幂等机制。该规则不改变验货台的自动保存。日报的两项 Q 货期独立补录；日报、年报统计及周／年问题跟踪按已审核记录的厂区、客户、有效月份和字段复用月报补录的版本及幂等记录，原周报明细保留独立周报库。LibreOffice 正常时预览原样式；缺失、超时或异常时从同一份导出文件读取简洁表格，保留格子、照片、补录和 Excel 导出，图表与排版简化。本机优先通过私有 `DOCUMENT_TOOLS_OFFICE_COMMAND` 指定可执行路径，不依赖启动 shell 的 PATH。[预览服务](../../backend/app/services/qc_report_workbook.py) · [补录及预览测试](../../backend/tests/test_qc_report_workbook.py)

报告中心的完整工作簿先生成并校验完整 Excel。有草稿时先确认保存。支持系统保存窗口时，生成较慢则原工具栏按钮改为「选择保存位置」，写入后逐字节回读校验才提示已保存。HTTP、没有保存窗口或窗口受限的浏览器，以及不支持可靠写入的 OpenCode Electron 宿主，直接将同一份已校验附件交给浏览器下载并提示「已发起下载」。主动取消选位置不另行下载。短版月度质量汇总的打印将签核栏和汇总保留在同页；长表正常分页，工作表内容和布局不变。

已保存的单笔报告补录按可验证的厂区与验货单 ID 只读呈现在验货汇总「QC验货 → 报告补录（本单）」；修改记录列出作者、时间与前后值，含清空。新旧报告周期、周报库与共用月度库明确区分，不覆盖已审核原值。汇总计数、整表备注、签核与未关联单笔的手工报表行不自动分摊。[完整资料及补录边界](../business/qc-complete-records.md#ui-和报告兼容)

审核中心待审核首屏采用居中的八字段预览；右上角图标打开报告工作簿编辑器。完整列名、顺序、条件列和批次对应关系来自现有待审核表，不从报告补录字段推断。文字、明细和照片列表先在当前标签页暂存，再按显式保存走原待审核记录接口；保存编号绑定操作者、内容和版本，同编号重试不重复写入，不覆盖较新的记录。照片标注仍调用原独立保存接口。审核确认仍独立、按原权限和原选中记录处理；已审核页面及其只读和反审核规则不变。

本地移动验货使用显式配置的私有 Wi-Fi 地址和独立受限监听；仅重启桌面 API 不会启动手机服务。签发局域网 HTTP 二维码前核对地址仍属于本机、手机监听及页面资源就绪。正式环境使用电脑和手机共用的固定 HTTPS 地址（域名或具备可信 IP 证书的固定公网 IPv4），发码前核对入口、手机资源和 QC 服务；反向代理保留正式 Host，不依赖任意转发头判断来源。发码自检不能证明厂区手机网络可达，上线须从实际使用网络探测并用真机扫码。[移动入口](../../backend/app/api/qc_mobile.py) · [局域网监听](../../backend/app/qc_mobile_app.py) · [生产验收](../aliyun-docker-deploy.md#移动验货上线验收)

周报模板以[清单](../../backend/app/templates/qc-weekly/templates.json)和[加载服务](../../backend/app/services/qc_weekly_templates.py)核对。验货审核、退回与附件规则见[业务要求](../business/QC验货运营中心业务需求.md)和[运行契约](../business/qc-legacy-runtime-contract.md)。

QC 记录删除与历史导入批次撤回统一受独立权限 `qc_inspection:record_delete` 管控（由内置六厂区 `qc_record_admin` 角色 / `QC_test` 账号及系统管理员持有，普通 QC 岗位不含该权限且界面保持无删除入口）。验货台与审核中心待审核支持带审计快照的软删除且不修改业务部客排期订单；已审核与审核同步汇总记录须先反审核退回待审核后再删除；已被历史记录引用的不良描述受保护仅允许停用。

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
