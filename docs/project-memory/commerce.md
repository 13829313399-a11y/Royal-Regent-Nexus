# 报价、订单与发票

[项目记忆](../../PROJECT_MEMORY.md) · [全部主题与验证入口](../agent-routing/context-index.md)

<a id="quotes"></a>
## 内部报价与客价

业务与装配必选，工程等部门可选。保存版本、方案和计算基线，乐观锁保护并发修订。审核人须具备本厂业务部有效审核权限。服务端计算并冻结放行版本，客价转换只输出所选客户白名单字段。

华康 A 的 360 正式路线与华兴 360 临时路线独立。Dickie、银辉、彩星等映射与源表版本绑定，客户单位换算、取整、放行与受控输出的例外见[分客户资料](../archive/memory/quotes-customers.md)。

[internal-quote-collaboration-design.md](../business/internal-quote-collaboration-design.md) · [internal_quote.py](../../backend/app/api/internal_quote.py) · [test_internal_quote_api.py](../../backend/tests/test_internal_quote_api.py)

旧版字段和例外可追溯至[内部协作、公式与受控导出](../archive/memory/quotes.md)、[客价白名单与客户例外](../archive/memory/quotes-customers.md)。

<a id="orders"></a>
## 客户订单中心

原始 PO、标准订单行、确认版本、发送记录、走货确认及余量归业务。预览、另存排期、写入台账是三个动作。历史迁入先预览，再按客户核对身份、状态和期初数量。业务向下游发出确认版本，采购明细、BOM 展开、机台计划及报工由下游管理。

华康 B 的 JP 问单与正式排期分开。模板和客户映射按厂使用，华康 C 的裁床测试桥有独立边界。首批真实切换、特殊交退货、印尼排期及仓库自动回传待业务确认。[订单路线图](../business/customer-order-center-erp-roadmap.md)

Windows 独立订单试用包固定厂区及客户，业务记录仅在本包 `data` 中。Win7 SP1/Win10 x86 运行环境另提供 `OPEN.vbs`（随包 pythonw，无控制台）与 `START.cmd` 两个入口；前者关闭程序窗口时退出本机服务。两者共用数据与实例锁，重复打开先验证后端实例；浏览器缓存按后端实例隔离，后端退出回收其自有浏览器。宿主机测试和 PE 静态检查不能替代 Windows 原生验收。[交付工具及验证](../../tools/factory-trial-delivery/README.md)

[customer-order-center-business-process.md](../business/customer-order-center-business-process.md) · [customer_order_ledger.py](../../backend/app/api/customer_order_ledger.py) · [test_customer_order_ledger.py](../../backend/tests/test_customer_order_ledger.py)

旧版字段和例外可追溯至[订单映射、台账与发运](../archive/memory/orders.md)。

<a id="mainland-invoice"></a>
## 大陆发票

会计部华康 A/B/D 可按开关进入，使用 `mainland_invoice:generate` 的部门和厂区授权。独立子应用在浏览器读取用户记录并生成文件，模板由服务端私有目录提供。账户、厂区或任职变化时销毁旧工作区。

生成、面单、下载须复核有效权限，财务仍需复核金额及票号。站点启用情况以该环境配置和验收为准。

[mainland-invoice-deployment.md](../business/mainland-invoice-deployment.md) · [mainland_invoice.py](../../backend/app/api/mainland_invoice.py) · [test_mainland_invoice_api.py](../../backend/tests/test_mainland_invoice_api.py)

旧版字段和例外可追溯至[大陆发票与面单](../archive/memory/mainland-invoice.md)。
