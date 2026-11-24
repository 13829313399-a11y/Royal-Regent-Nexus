# 公共工具与印尼业务

[项目记忆](../../PROJECT_MEMORY.md) · [全部主题与验证入口](../agent-routing/context-index.md)

<a id="shared-tools"></a>
## 公共文档工具与在线文档

长任务提交 `POST /api/tools/jobs` 返回 202，独立 `document-tools-worker` 执行。结果、源文件、修订与下载关联任务所有者。华兴 PDF 批量改名等专用预览与执行另有自己的契约。图片翻译独立构建。

在线文档用独立的同源编辑器与服务端保存流程，文件夹归类不授予共享权，所有者、收件人、厂区及任职边界需分别检查。[在线文档](../document-tools/online-documents.md) · [图片翻译集成](../../shinobu-web/README_FOR_RR.md)

[README.md](../document-tools/README.md) · [document_tools.py](../../backend/app/api/document_tools.py) · [test_document_tools_jobs.py](../../backend/tests/test_document_tools_jobs.py)

旧版字段和例外可追溯至[文档工具、在线编辑与图片翻译](../archive/memory/shared-tools.md)。

<a id="marks-invoice"></a>
## 箱唛与印尼发票核对

箱唛库保留客户原件、工作表范围、文件指纹、版本和放行身份。把订单或排期与模板关联之前要按授权核对客户及明确的业务来源。供应商、仓库、QC 和客户可见的资料依各自范围。

印尼发票核对是独立文件工具，支持规定版式的 Faith Jet 与 RRI 源单。两个入口分别见[箱唛接口](../../backend/app/api/carton_mark.py)和[印尼发票接口](../../backend/app/api/indonesia_invoice.py)。[印尼发票回归](../../backend/tests/test_indonesia_invoice_service.py)

[箱唛回归](../../backend/tests/test_carton_mark_api.py)

旧版字段和例外可追溯至[箱唛模板与印尼发票处理](../archive/memory/marks-invoice.md)。

<a id="shipping"></a>
## 印尼走货明细

`/modules/sales-business/indonesia-shipping` 嵌入 RR-Portal，按厂解析目标服务与数据。客户、货柜、出货和海关单证留在所属厂区。导出的日期、Excel 定义名称与打印范围跟随所选业务数据。

待保存的供应商复期按采购行防重复提交，刷新结束后才解除等待状态。并发修改冲突需要重新读取并核对。

四份空白导入模板随工作区提供。货号库下载产品转移工程表，工具及非生产物料下载物料表，供应商报价下载标准价和阶梯价共用的工作簿，走货明细下载走货资料表。报价的两种格式按需择一填写。清除历史业务内容时须按工作表和单元格保留原公式、跨表联动及数组范围。公式中的历史报价和批次数值改取「公式输入」页的空白输入格。工程喷油资料从本工作簿的排模表取数。走货原件「销售合同」的 E52、F52、I52、I53 已失去对发票的引用，须取得完好原件才能确定目标。

本地 sidecar 的端口与数据库版本见历史记录。核实当前服务时查实际目标环境。

[indonesia-shipping.md](../indonesia-shipping.md) · [indonesia_shipping.py](../../backend/app/api/indonesia_shipping.py) · [test_indonesia_shipping.py](../../backend/tests/test_indonesia_shipping.py)

旧版字段和例外可追溯至[印尼走货明细与本机试用](../archive/memory/shipping.md)。

<a id="materials-id"></a>
## 送印尼物料（已下线）

原 `/modules/sales-business/indonesia-material-shipment` 链接回到业务部并保留有效厂区。旧 `/api/indonesia-materials` 未注册，四项 `indonesia_material:*` 权限只保留历史审计用途。原表、文件、命令审计、迁移记录和浏览器草稿继续保留；历史资料仍在原库。

[indonesia-materials-implementation.md](../business/indonesia-materials-implementation.md) · [indonesia_materials.py](../../backend/app/api/indonesia_materials.py) · [test_indonesia_materials.py](../../backend/tests/test_indonesia_materials.py)

旧版字段和例外可追溯至[送印尼物料与导出](../archive/memory/materials-id.md)。
