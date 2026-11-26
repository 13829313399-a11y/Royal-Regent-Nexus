# 报价、订单与发票

[项目记忆](../../PROJECT_MEMORY.md) · [全部主题与验证入口](../agent-routing/context-index.md)

<a id="quotes"></a>
## 内部报价与客价

华兴 BuzzBee 工程部的「其他外购」可逐行点 ƒx 选择本报价胶料及料型，填写单条重量（g）和单条啤工（RMB）。原单价 HKD = 冻结料价（HKD/lb）÷ 454 × 单条重量 + 单条啤工 ÷ 本报价 RMB/HKD 汇率。啤工已含后加工人工；行金额按原单价乘用量和损耗率。内部 Excel 的「外购计价」保留输入，报价明细保留可重算公式。

业务与装配必选，工程等部门可选。保存版本、方案和计算基线，乐观锁保护并发修订。审核人须具备本厂业务部有效审核权限。服务端计算并冻结放行版本，客价转换只输出所选客户白名单字段。

华康 A 的 360 正式路线与华兴 360 临时路线独立。Dickie、银辉、彩星等映射与源表版本绑定，客户单位换算、取整、放行与受控输出的例外见[分客户资料](../archive/memory/quotes-customers.md)。

银辉旧版报价完整读取“电子报价”“电子TX报价”和“电子RX报价”页，按页内型号与对应组件匹配。客表按需扩行，逐条列出 IC 数量、单价和小计，拆分前后各组件的合计一致。

[internal-quote-collaboration-design.md](../business/internal-quote-collaboration-design.md) · [internal_quote.py](../../backend/app/api/internal_quote.py) · [test_internal_quote_api.py](../../backend/tests/test_internal_quote_api.py)

旧版字段和例外可追溯至[内部协作、公式与受控导出](../archive/memory/quotes.md)、[客价白名单与客户例外](../archive/memory/quotes-customers.md)。

<a id="orders"></a>
## 客户订单中心

原始 PO、标准订单行、确认版本、发送记录、走货确认及余量归业务。预览、另存排期、写入台账是三个动作。历史迁入先预览，再按客户核对身份、状态和期初数量。业务向下游发出确认版本，采购明细、BOM 展开、机台计划及报工由下游管理。

华康 B 的 JP 问单与正式排期分开。模板和客户映射按厂使用，华康 C 的裁床测试桥有独立边界。首批真实切换、特殊交退货、印尼排期及仓库自动回传待业务确认。[订单路线图](../business/customer-order-center-erp-roadmap.md)

JP 问单品名优先取当前邮件，空白才使用匹配排期的品名；长码第三段可精确关联带后缀货号（如 77780-000-2A-006-PTQ 对应 77780-2A），包装版本仍取明确邮件或唯一历史，不把 2A/PTQ 猜成版本或子货号。复制44列提供 HTML 文本单元格及 TSV，普通编号不增加单引号；纯文本粘贴需目标编号列为文本以保留前导零。

JP 月单的 VSK 表支持 `Revised Qty (Pcs)` 等明确的修订数量表头；唯一修订数量列优先于旧数量列，修订空值保持空白，小计/总计不作为明细数量。当前邮件的多个产品表一并读取，引用历史保持隔离；Foxmail 纯文本竖向分隔表保留空单元格位置，不猜测或重组残缺行。

订单 Qwen 接口默认关闭。统一预览、旧版 BuzzBee/Dickie/彩星及 ZURU 原周排期支持对当前已支持的 Excel/PDF PO 提取并展示原文候选；不改业务值、不产生确认/补录授权键、不改变输入指纹。原生解析失败补救、客户格式白名单扩展及 JP 邮件 AI 路线尚未接入。2026-11-25 已用私有 Qwen3-VL-Plus 密钥实测：可提取部分扫描件，但存在货号/条码、单位及证据归属错误，不能声称全客户精度提升或自动采用验收通过。可选识别在有总时限的子进程执行，厂区/客户隔离快照复用；v2 支持已有原生证据 ID 短引用，页图仍须抄录且不算独立验证。密钥不进试用包或 Git。见[接入配置](../verification/order-qwen-20261124.md)及[真实测试记录](../verification/order-qwen-live-20261125.md)。

Windows 独立订单试用包固定厂区及客户，业务记录仅在本包 `data` 中。Win7 SP1/Win10 x86 运行环境另提供 `OPEN.vbs`（随包 pythonw，无控制台）与 `START.cmd` 两个入口；前者关闭程序窗口时退出本机服务。两者共用数据与实例锁，重复打开先验证后端实例；浏览器缓存按后端实例隔离，后端退出回收其自有浏览器。宿主机测试和 PE 静态检查不能替代 Windows 原生验收。[交付工具及验证](../../tools/factory-trial-delivery/README.md)

[customer-order-center-business-process.md](../business/customer-order-center-business-process.md) · [customer_order_ledger.py](../../backend/app/api/customer_order_ledger.py) · [test_customer_order_ledger.py](../../backend/tests/test_customer_order_ledger.py)

旧版字段和例外可追溯至[订单映射、台账与发运](../archive/memory/orders.md)。

<a id="mainland-invoice"></a>
## 大陆发票

会计部华康 A/B/D 可按开关进入，使用 `mainland_invoice:generate` 的部门和厂区授权。独立子应用在浏览器读取用户记录并生成文件，模板由服务端私有目录提供。账户、厂区或任职变化时销毁旧工作区。

生成、面单、下载须复核有效权限，财务仍需复核金额及票号。站点启用情况以该环境配置和验收为准。

[mainland-invoice-deployment.md](../business/mainland-invoice-deployment.md) · [mainland_invoice.py](../../backend/app/api/mainland_invoice.py) · [test_mainland_invoice_api.py](../../backend/tests/test_mainland_invoice_api.py)

旧版字段和例外可追溯至[大陆发票与面单](../archive/memory/mainland-invoice.md)。
