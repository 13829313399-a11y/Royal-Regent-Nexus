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

本地 sidecar 的端口与数据库版本见历史记录。核实当前服务时查实际目标环境。

[indonesia-shipping.md](../indonesia-shipping.md) · [indonesia_shipping.py](../../backend/app/api/indonesia_shipping.py) · [test_indonesia_shipping.py](../../backend/tests/test_indonesia_shipping.py)

旧版字段和例外可追溯至[印尼走货明细与本机试用](../archive/memory/shipping.md)。

<a id="materials-id"></a>
## 送印尼物料

`/modules/sales-business/indonesia-material-shipment` 管理合同计划、需求、收发及基础资料，收货方为 RRI/RRM。六厂的业务单分别保存，七组基础选项跨厂共享。每厂物料库内两收货方共用料号。

客户导出限定一个客户和一个收货方，保留原始工作簿与 57 栏明细。

[indonesia-materials-implementation.md](../business/indonesia-materials-implementation.md) · [indonesia_materials.py](../../backend/app/api/indonesia_materials.py) · [test_indonesia_materials.py](../../backend/tests/test_indonesia_materials.py)

旧版字段和例外可追溯至[送印尼物料与导出](../archive/memory/materials-id.md)。
