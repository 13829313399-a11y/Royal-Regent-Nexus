# 印尼走货明细：Nexus 接入与运行

## 交付范围与来源

新模块入口：业务部 → **印尼走货明细**，路由 `/modules/sales-business/indonesia-shipping?factory=huaxing`。它与现有“送印尼物料”独立，不替换原模块、数据或流程。

完整源码位于 `services/indonesia-shipping/`，来自 `charlesskl/RR-Portal` 的 `apps/印尼小组/印尼走货明细`，固定提交 `d2f5db84551690f9103dcb91f4b5d7480c4709c0`。`UPSTREAM.json` 保存每个上游文件的 SHA-256；`NEXUS_PATCHES.json` 列出接入修改后的校验值。运行 `python scripts/verify-indonesia-source.py` 检查原始文件完整性及明确记录的适配文件。原文 README 的 SQL Server 描述已过时：当前实际实现是 **.NET 8 / EF Core + Dapper / PostgreSQL，React + TypeScript + Vite + Ant Design**。

保留客户、货号及物料、供应商、工具及非生产物料、HS/翻译字典、报价、采购订单、生产单、排期、物料追踪、出库、走货、合并/装箱、Excel 导入审阅和原有报关/合同/发票导出逻辑。按用户要求，接入模式停用原系统账号管理和数据库管理，人员和权限统一由 Nexus 管理；业务资料通过对应业务页面维护，实际数据库与历史记录保留。所有三个报关工作簿与 vendored SheetJS 包均随源码保留。React 工作区放在同源 iframe，避免其样式覆盖 Nexus；业务页原表格、筛选、弹窗与操作习惯不重绘。原独立运行的账号及数据库维护源码保留以便核对上游，接入 Nexus 时不可使用。

导航按“基础资料”和“订单与走货”两组折叠显示，当前页面所属组自动展开。基础资料包含客户、货号库、工具及非生产物料、供应商汇总、供应商报价和 HS/翻译字典；订单与走货包含排期、采购订单、生产单、物料追踪、出库和走货明细。各页面保留原地址与独立权限，空分组隐藏；“供应商报价”继续为采购提供阶梯价。

## 身份、权限与厂区边界

- 所有页面、静态资源、模板和 API 经 `/api/indonesia-shipping/{factory}/app/*`；Nexus 每次读取真实 `rr_session`，并使用 `authorization_decision`。`legacy` / `shadow` / `enforce` 均严格检查权限、厂区、业务部、停用状态和显式禁止；V2 固定版本/厂区上限沿用现有契约。
- `indonesia_shipping:read` 是工作区入口权限。九个域 `products/materials/customers/schedules/purchase/quotes/molding/outbound/shipments` 各有 `_read` 和 `_write` 权限，按原九位权限模型映射。写入同时要求本域 read。货号详情包含物料，改名/删除也影响物料，所以 `/products` 同时检查 products 与 materials 的相应权限，网关和侧车保持一致；图片和字典归 products，物料追踪归 purchase。客户端文件导出沿用原系统可读数据范围；会写数据库的导入/生成等 POST 要求 write。
- 身份指纹包含登录会话、账号、任职和授权版本，返回的只有散列。网关接收请求体前后均核对真实会话和权限，上传期间撤权或换账号不会继续转发。报价/生产单完整保留 `X-Blob-Version` 与 `X-Expected-Version`，旧版本保存继续返回原系统 409 冲突。
- 嵌入和独立窗口均监听 Nexus 身份广播，在获得焦点、每 45 秒及服务端提示的权限到期时间复核。退出、换账号或权限变化后立即清除已知失效状态并锁定当前文档，需返回业务部重新打开；旧异步响应、批量操作不能借新账号继续执行。普通时钟刷新不清除草稿。会话检查最多等待 15 秒；失败时关闭业务内容。客户端导出在点击时及实际下载前校验原操作的会话身份，防止耗时文件生成跨越登录边界。
- 只读走货保留“查看”、核对和报关导出，禁用表单、单元格、拖拽填充及保存入口。宿主切厂/离开/重连和原前端内部导航/浏览器前后退均先处理草稿提示；提交中禁止离开。尚无独立 dirty 标记的原编辑窗口采取保守提示，关闭编辑窗口后解除。使用两端已有的对话框组件；安全失效清空不受草稿提示阻挡。独立窗口显示厂区，返回业务部保留 factory 参数。
- `indonesia_shipping:users_manage` 和 `indonesia_shipping:database_manage` 均退出可授予目录，历史权限在 IAM 显示为停用，不能新增分配；已有授权保留追溯且不转换为任何新权限。接入模式不显示账号或数据库管理菜单，旧 `/users`、`/db-admin` 地址跳回有权访问的业务页；没有具体业务页权限时明确提示，不循环跳转。网关与侧车拒绝全部旧 `/api/users`（含 me/改密）、`/api/db`（含读取、新增、修改、单行删除及整表清空）及独立登录接口，旧令牌即使含管理标记也不放行。Nexus 会话返回 `databaseManage: false` 兼容旧客户端，桥接令牌不再签发该管理标记。当前身份仅从 `/api/session` 读取。
- Nexus 账号、停用状态、厂区、部门、任职周期及九域读写权限沿用现有 IAM；不维护第二份人员库。桥接启动不创建或激活原管理员，不迁移或导入旧账号，历史 Users 行保持原样。审计追加 `nexus_user_id`、`nexus_factory_id`、`nexus_employment_epoch` 和 `actor_display_name`，保留现系统字符串身份且不冒用旧整数账号；原审计行不重写，独立运行模式仍使用原账号与审计列。
- 没有给现有业务角色自动新增权限。管理员需在正常 IAM 流程明确授予当前厂区/业务部权限；V2 账号必须采用合适的显式授权或职位包升级。集团选择不回退到华兴。
- 浏览器不接收上游 JWT，不把 Nexus 会话放进 localStorage。服务端生成 60 秒 HMAC JWT，仅转发给侧车。侧车核对 issuer、audience、有效期及固定厂区。客户端 Authorization、Cookie 与任意代理头不传入侧车；上游 Cookie、跳转和认证头不回传。
- 业务 API 还核对账号/授权版本/任职周期指纹。旧页面不能在账号切换后继续提交；父页面切换厂区或身份时立即销毁旧 iframe。写请求要求专用同源请求头并拒绝跨站来源。静态模板无业务数据，仍要求有效工作区会话。
- **每个启用厂区一个侧车、一个独立 PostgreSQL 数据库。** `public.nexus_indonesia_factory_binding` 持久绑定数据库厂区，在任何原业务建表、导入或迁移前检查。重复绑定到另一厂区拒绝启动。已有未绑定数据库默认拒绝；确认备份/来源/厂区后才可临时设置 `NexusBridge__AdoptExistingDatabase=true`。Nexus 主数据库不得作为侧车数据库。

## 本地运行（不改变现有 .env）

需要 .NET 8 SDK、Node 22+、独立 PostgreSQL 16 数据库。无需 Docker即可开发。新建空库并使用独立账号，连接字符串必须包含 `Search Path=indo_shipping`。下面仅说明环境变量，不含任何真实凭据。

1. 在启动侧车的 PowerShell 中配置 `INDONESIA_SHIPPING_CONNECTION_STRING` 和随机 `INDONESIA_SHIPPING_BRIDGE_KEY`（至少 32 字节）。
2. 执行 `powershell -File scripts/start-indonesia-shipping.ps1 -Factory huaxing -Port 5180 -Build`。可用 `-Dotnet <SDK可执行文件>` 指定 SDK。脚本安装锁定依赖、以 `VITE_BASE_PATH=./` 构建完整 React 工作区、发布 .NET、复制静态文件并绑定 loopback。后续无需重建时省略 `-Build`。
3. 在 Nexus API 进程的环境配置 `INDONESIA_SHIPPING_UPSTREAMS={"huaxing":"http://127.0.0.1:5180"}` 与相同的 `INDONESIA_SHIPPING_BRIDGE_KEY`，按原启动方式启动/重启 API。不要覆盖它的现有数据库和 IAM 环境。
4. Nexus 前端仍用现有端口和 `/api` 代理，不启动另一个用户入口。确认正常账号已具备上面的明确权限，然后从业务部打开新模块。

未配置、无权限、未选择厂区、连接失败分别显示真实状态；模块不会伪造业务记录或静默使用其他厂服务。`/healthz` 只返回无身份信息的侧车就绪状态；业务健康接口仍通过已认证网关。原 SQL schema 与 HS 基础字典被 csproj 随 `dotnet publish` 复制，命令行发布和容器发布口径一致。

## 可选生产部署

当前本地已启用六个厂区。Nexus 仍是 5173/8000，专用 PostgreSQL 为 55433，每厂一个独立数据库和服务；未复制华兴资料到其他厂。私有运行目录为 `.local-dev/indonesia-shipping/`，现有 backend Python 执行其中的 `start.py` 可启动全部六厂，再按原方式启动 Nexus。运行包为该目录下 `publish-framework-audit/`。连接配置和数据不进入 Git；原验收库与这里的业务库分开。

| 厂区 | 服务端口 | 独立数据库 |
| --- | --- | --- |
| 华兴 | 5182 | `indonesia_huaxing` |
| 华康 A | 5190 | `indonesia_huakang_a` |
| 华康 B | 5191 | `indonesia_huakang_b` |
| 华康 C | 5192 | `indonesia_huakang_c` |
| 华康 D | 5193 | `indonesia_huakang_d` |
| 华登 | 5194 | `indonesia_huadeng` |

新五厂从空业务库开始，仅初始化原系统必要字典/设置，不创建旧账号。华兴升级前的数据库备份及行校验保存在私有运行目录；原业务表和历史账号行校验保持一致。数据库绑定与账号禁用均已逐厂实测，浏览器已逐厂切换验证。此配置不自动授予员工权限。

此交付不表示生产已部署或数据已迁移。按现有发布授权流程准备后，使用：

```text
docker compose --env-file .env.production -f docker-compose.prod.yml -f docker-compose.indonesia-shipping-all.yml up -d --build
```

六厂覆盖配置已明确绑定各厂服务、数据库和持久卷，不暴露侧车/数据库端口。设置 `INDONESIA_SHIPPING_BRIDGE_KEY`（随机至少 32 字节），以及六个独立数据库密码：`INDONESIA_SHIPPING_HUAKANG_A_DB_PASSWORD`、`HUAKANG_B`、`HUAKANG_C`、`HUAKANG_D`、`HUADENG`、`HUAXING`（后五项同样使用完整 `INDONESIA_SHIPPING_<厂区>_DB_PASSWORD` 名称）。不能仅修改同一数据库的厂区变量。旧单厂 `docker-compose.indonesia-shipping.yml` 仍保留原卷与显式厂区配置，勿与六厂覆盖文件叠加；切换已有生产单厂数据必须先备份恢复演练，六厂配置不会自动复制旧卷。

Nginx 已为模块设置 105MiB 上传上限与 190 秒等待，API 默认上传 100MiB、处理 180 秒；修改超时需同步两层。保留原部署的备份、密钥管理、受控发布和回滚规范。当前只完成六厂配置文件结构检查和本地运行，未执行生产 Docker 部署。

升级侧车前备份其独立 PostgreSQL 数据库。上游启动会执行幂等 schema/data migrations；涉及实际历史数据时必须先在恢复副本演练、核对行数和业务导出，再单独安排切换。回滚程序不能代替数据库恢复方案。

## 真实历史数据

上游 Git 不包含 `seed/business-data.json`，本次未取得原生产数据库备份；复制代码和模板不会复制历史采购、排期、库存、走货或账号。测试记录仅存在独立临时验收数据库。导入历史记录必须由业务确认原厂区归属、正式快照、备份与数据核对；不能把一份全局旧账复制到多个厂区制造隔离假象，也不能把测试库视为生产数据。桥接导入还要求 `NexusBridge__SeedFactoryId` 明确等于当前实例厂区，否则拒绝；快照里的旧账号部分被忽略，也允许快照完全不含账号字段。全厂本地启动不继承历史导入环境变量。

## 检查与验收

- Nexus：`npm run build`、`npm run test:unit -- src/views/__tests__/indonesiaShippingEntry.spec.ts`、`npm run typecheck:test`。
- 网关：在 backend 运行 `python -m pytest tests/test_indonesia_shipping.py -q`，覆盖三种授权模式、V2 厂区上限、显式禁止、读写与管理分离、匿名、账号切换、跨站、上传大小、URL混淆及 HTML/模板基础路径。
- 原前端：在 service/web 运行 `npm ci`、`npm test -- --testTimeout=60000`、`VITE_BASE_PATH=./ npm run build`（PowerShell 使用环境变量语法）。大报关工作簿测试在普通 Windows CI 允许较长等待。
- 原后端：`dotnet test services/indonesia-shipping/IndoShipping.sln`。有些上游测试没有数据库配置时直接返回，因此“pass”数量本身不证明实际数据库执行；配置各测试声明的 `*_TEST_CONNECTION` 并指向专用临时 PostgreSQL，批量运行可使用 `Pooling=false`。`INDO_SHIPPING_TEST_CONNECTION` 优先覆盖原库存集成测试固定端口；`NEXUS_BRIDGE_TEST_CONNECTION` 的厂区绑定及账号兼容测试创建并删除随机命名的临时数据库，需专用测试服务器的建库权限。账号兼容测试包含无旧账号首启、保留历史账号、带冲突或不含账号的业务快照、错误快照厂区拒绝和 Nexus 审计身份。
- UI 简报见 `docs/frontend/indonesia-shipping-brief.md`。浏览器视觉验收遵循仓库 Chrome DevTools MCP 规则；用户明确授权替代工具时，记录实际使用的浏览器、视口、交互和限制，不能把编译/API检查声称为浏览器验收。桌面及窄屏、实际模板打印、真实业务样本与生产验收分别记录。
- 工作区统一在主框架内使用，顶部不提供“独立打开”入口；副标题只显示当前厂区和操作人。内嵌工作区不再重复显示内部标题栏；物料提醒及数量统一在主框架顶部显示，手机菜单按钮也位于顶部。提醒点击沿用原页面导航及未保存保护；消息校验来源、厂区和当前连接，重连或身份切换清除旧数量。内嵌页面的导出逻辑保留。此前内置浏览器未回传内嵌页面下载，历史独立页面下载验收不能替代内嵌下载验收，也不能据此宣称其他浏览器存在相同限制。
- 浏览器验收修复已记录到适配清单：报关文件名不因时区提前一天；工作表调整同步打印范围/定义名称并补齐合计缓存；出库编辑按原保存数量回加库存；走货汇总和工具栏按窗口换行。原始模板及上游源码仍由完整性脚本核对。
- 窄屏保持原工作区和业务语义：小于1024px时采购、排期、走货编辑占满可用宽度，表格在自身区域横向滚动并取消遮挡中间字段的固定列；走货虚拟表的焦点滚动使用同一组列设置，桌面仍保留固定列。已实际验收320/390/768宽及1366桌面回归；浏览器尺寸模拟不代替真实手机触控、软键盘和文件选择验收。
- 采购合同打印保留A:J全部字段，A4横向、横向一页、纵向自然分页。三套报关导出保留源模板样式、工作表隐藏状态及打印参数；销售合同、装箱单(2)、草稿大单和司机资料保证完整列宽，纵向自然分页。导出修复包含工作表/边框XML元素顺序、空合并集合、分类金额缓存与超范围公式同步。源模板不改写，异步导出仍在最终下载前验证当前会话。
- 原生Excel已验证采购合同及RRI/RRM/旧版印尼工作簿打开和打印预览，并实际输出RRI销售合同的虚拟打印PDF。超宽走货主表沿用源模板比例，A4字体很小，需按业务实际纸型另行验收。WPS已打开采购合同，但本机控制多次超时，打印预览未验证；实体打印机与真实业务文件同样未验证。
- 仍依赖真实样本的10个用例使用9个环境变量：`WPS_IMAGE_SAMPLE`、`SHIPMENT_IMPORT_SAMPLES`（字段与图片两例，JSON数组按三份样本顺序）、`SHIPMENT_IMPORT_VERSION_SAMPLE`、`TOOL_IMPORT_SAMPLE`、`ENGINEERING_L21106_FILE`、`ENGINEERING_IMPORT_FILE`、`MOLD_VARIANT_IMPORT_FILE`、`SPIN_SCHEDULE_FILE`、`SPIN_ENGINEERING_FILE`。保留原Excel工作表名、公式、合并与图片；同一原文件可用于多例。合成数据通过不代表这些用例已执行。
