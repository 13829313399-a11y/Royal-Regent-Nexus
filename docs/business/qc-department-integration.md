# QC_department 接入 Nexus

## 当前交付

原 `/modules/qc/inspection-operations` 页面已替换成 QC_department 宿主，点击 QC 部入口直接显示嵌入工作台。检验、审核、统计、PDF 和表格导出沿用独立系统；上方保留返回 QC 模块中心按钮。旧子路由继续进入这个宿主，不把旧 Nexus 记录 ID 对应到新系统记录。

唯一活动源码位于日常主项目 `/Users/chris/Desktop/QC Code/Royal-Regent-Nexus/services/qc-department`。QC_test 下的主项目入口指向同一目录；原独立 QC 和旧预览副本归档保存，不再作为运行入口。原 Nexus 的 QC 表、接口和历史附件保留，没有删库，也没有把两套记录混合。

## 业务部代码定位

| 层级 | 入口 |
| --- | --- |
| 业务部页面 | `src/views/CustomerOrderCenterView.vue` 的 `customer-schedule` / 各客排期 |
| 前端接口 | `src/api/customerOrderSchedule.ts` |
| 后端路由 | `backend/app/api/customer_order_ledger.py` 的 `schedule_customers`、`customer_schedule` |
| 查询与分组 | `backend/app/services/customer_order_schedule.py` 的 `read_schedule` |
| 数据源 API | `GET /api/customer-order-ledger/schedule/customers` 与 `GET /api/customer-order-ledger/schedule` |

业务接口按厂区、客户读取，包含未走货、已走货、取消及验货分组，并使用其原有业务权限。此次没有改动业务部接口或数据。

## 正式排期与验货任务

`GET api/schedule-source` 现在返回 `contract_version=2`、`status=ready`、`mapping_version=qc-task-v1`、`source_available=true`、`import_enabled=false`。数据来自当前厂区正式订单台账，空列表表示没有已保存的订单；不把示例导入为正式数据。只读映射客户、业务参考号、客PO、货号、名称、数量、包装和明确的验货日期；走货日期不代替验货日期，未知字段留空并在推送前确认。

原14列、组合筛选、行高列宽和导出样式保持。新增复选及确认推送：逐行确认行验/客验、计划日期、数量和批次；重复请求不重复建任务，同单分批/重验使用不同批次。正式排期的完成情况由关联任务生成，点击可查看全部相关验货。

华兴47条原表示例仍独立显示和导出，原示例反馈保存在 `_schedule_examples/feedback.sqlite3`，不进入真实任务或统计。正式订单存在时默认显示正式数据；仍可切换示例。示例接口及权限/版本保护保持。

验货明细新增待验、草稿、待审核、退回、已审核任务工作区；旧记录和原功能保存在可展开历史区。QC 保存草稿后明确确认提交，服务端锁定记录及附件。主管在审核中心查看完整信息并通过或退回，退回后可修改重提；通过不改变检验判定。详细合同、持久化与验收见 [验货流程](qc-inspection-workflow.md)。

页面通过 `api/schedule-export` 上传已生成的原样 XLSX，再使用普通 HTTP 附件地址下载；准备和下载都校验当前登录、厂区、actor 与 report_export。下载令牌 10 分钟有效；`_schedule_exports` 私有缓存采用后续请求触发清理，并限制文件大小、数量与总容量。该链路支持示例、空模板及正式排期，保留原工作簿样式与筛选范围，不写入验货或报表数据。下载失败显示错误，成功提示仅表示已发起下载。

## 登录、厂区与权限

- 所有嵌入资源和 API 都经过 Nexus 的 `rr_session` 和 QC 厂区权限校验。嵌入 URL 绑定当前用户和授权版本，旧账号页面不能利用新账号 Cookie 提交。
- 明确映射六个 Nexus 厂区至 QC 的 `hy-*` 子公司库；集团和未知厂区不会回落到东莞或华兴。
- Node 服务仅信任共享网关令牌，生产没有宿主机端口。浏览器不能调用独立登录、SSO 或账号管理 API，也拿不到原账号密码摘要。
- 新任务审批使用独立 `qc_inspection:review`，仅内置 QC 主管/经理拥有，检验员没有。旧 QC 整条记录同步同时要求 `qc_inspection:order_write`、`qc_inspection:result_write`。这是完整记录同步尚未拆成订单/结果接口前的保守边界。删除/覆盖再要求 `customer_manage`；客户/不良库维护使用 `customer_manage`；导出使用 `report_export`。
- 浏览器缓存按用户/厂区隔离在 sessionStorage。初始化失败不会回退示例记录；保存失败会阻断后续写入，提示重载核对。
- 云端 OCR 密钥不随源目录复制；没有配置时保留原本的本地 OCR 路径。

## QC 内部数据与日期规则

来料日期与检验日期独立保存，无法确定时留空；明细、审核、导入预览及相应报告记录行标红并显示文字提示。新增、继续录入、批量、Excel/JSON 和 OCR 不再自动补今天或复制另一种日期。OCR 只有明确标记的来料/来货/收货日期才进入来料字段，普通“日期”、送货日期、检验日期不猜归属。OCR 预览中人工核对的两种日期分别应用，多货品连续录入也保留。历史原始日期不批量改写，编辑无关字段保留原值。

日报、周报及其 PDF 内容按各自既有取数范围展示记录备注和不良明细备注原文，不重新分类、计数或判定。公司抬头使用当前厂区，数量字符串按数值求和；刷新明细同步刷新供应商/客户/加工类型候选；本地 CSV 在筛选无结果时只导出表头，不回退全部记录。服务端 CSV/Excel 的审核范围未变。

用户明确暂缓：日期统计归属、通过率、导出审核范围、平均不良率、高风险规则、不良统计。现有日报双日期取数、周报按来料日期取数等差异继续存在；周图的空来料日期仍可能按旧逻辑归当前周。这些限制不能宣称已统一。此前内部一致性修复未改业务部；客排期已按单独授权更新界面框架，新任务实际验货备注随已审核只读投影进入日报周报，示例备注不参与。

## 本地运行

唯一主项目为 `/Users/chris/Desktop/QC Code/Royal-Regent-Nexus`。从项目运行 `npm run dev`，或双击 QC_test 中“启动华兴企业系统.command”。统一入口为 `http://127.0.0.1:5173/`，API 为 8000，私有 QC 为 3411。`npm run dev:web` 仅启动前端，供已有后端的开发场景使用。

`backend/.env` 保留原主系统数据库和文件存储设置，启用 `QC_DEPARTMENT_MANAGED=true`。主 API 的 lifespan 自动启动私有 QC，等待受令牌保护的就绪响应；正常退出、启动异常或父进程消失均回收自己启动的 QC。占用端口时报错，不接管或结束未知服务。直接重启原有 uvicorn 后端也会启动最新 QC，不需要独立运行 QC_department。

QC 的固定持久目录由 `QC_DEPARTMENT_DATA_DIR` 指定，本机为主项目 `backend/data/qc-department/companies`。已确认的 QC 数据只在合并时迁入，启动脚本不复制、不重置任何数据库。网关令牌保存于其上一级私有文件，日志也在上一级。主系统继续使用原 `.local-dev/preview/preview.sqlite3`，未用旧 5174 的主库快照覆盖。旧 5174/8011 预览和 3401 独立 QC 不再运行。

生产 Compose 显式设置 `QC_DEPARTMENT_MANAGED=false`，继续由 Compose 管理私有服务。

## 生产包装与数据边界

`docker-compose.prod.yml` 已增加私有 `qc-department` 服务及 `qc-department-data` 持久卷，API 镜像打包前端资源。部署环境必须配置至少 32 字符随机 `QC_DEPARTMENT_GATEWAY_TOKEN`，API 与 Node 使用同一值。令牌不得提交到源码。Node 24 支持内置 SQLite，无需安装 npm 业务依赖。

新持久卷不会自动带入已有 QC 数据；本次没有操作生产服务器。生产上线前应通过一致性备份明确迁入哪些公司库，校验各库记录数并设置卷属主。不得把示例数据当成历史迁移，不删除原 Nexus QC 表。完整 Docker 构建、卷迁移及生产域名验收尚未执行。

## 验证边界

针对性测试覆盖真实 Nexus 会话、权限、跨厂拒绝、账号切换、静态路径保护、未映射排期、真实 Node 保存/读取/CSV 导出、PDF 导出权限、空库编号与前端宿主切换。合并时源副本经过一致性校验；后续 QC 内部修复以当前打包目录为准。

当前环境缺少 Chrome DevTools MCP，未执行完整浏览器布局/OCR/PDF 视觉验收。按用户要求，通过内置浏览器沿用现有 Nexus 登录并打开了华兴模块中心和 QC 工作台；这一打开操作发现的用户徽章 `esc` 未定义错误已改为现有 `_esc` 并加入登录初始化回归测试。该操作确认页面能显示，不代表全部业务流程验收。完整 `npm run build` 的 Vue 主应用类型检查和 Vite 构建通过，但最后的独立图片翻译构建因 shinobu-web 缺少依赖而失败。原 QC 安全测试中的一条移动端 textarea 字体断言在原目录也失败，属于已有问题；此次未修改该样式。

## 主要改动文件

- `src/views/QcOperationsCenterView.vue`：替换原页面内容，保留入口路由，处理连接失败和身份/厂区变化。
- `backend/app/api/qc_department.py`：登录/权限/厂区网关、嵌入上下文、正式排期和验货任务接口。
- `backend/app/main.py`、`backend/app/core/config.py`、`backend/.env.example`：注册网关和私有服务配置。
- `services/qc-department/`：原系统部署副本及 Nexus 适配；不包含原数据库和 AI 密钥。
- `scripts/start-system.py`、`scripts/dev-system.mjs`：统一启动 5173/8000；`backend/app/services/qc_department_runtime.py` 由 API 生命周期管理私有 QC。
- `Dockerfile.backend`、`docker-compose.prod.yml`、`.dockerignore`、`.gitignore`：部署包装与私有运行文件排除。
- `backend/tests/test_qc_department_gateway.py`、`src/views/__tests__/QcDepartmentHost.spec.ts`、`src/router/__tests__/qcInspectionRoutes.spec.ts`、副本内测试：接入回归。
- `shared/assistant-help/modules/qc-inspection.json`、`PROJECT_MEMORY.md`：使当前帮助和架构事实与新入口一致；旧合同另存说明。

## 本次验证记录

- `backend/.venv/bin/python -m pytest backend/tests/test_qc_department_gateway.py -q --disable-warnings --maxfail=1`：7 项通过，其中真实 Node 测试使用临时数据库。
- `npm run test:unit -- src/views/__tests__/QcDepartmentHost.spec.ts src/router/__tests__/qcInspectionRoutes.spec.ts src/data/__tests__/qcInspectionModule.spec.ts`：18 项通过。
- 副本 `nexus-integration.test.js`、`judgement-flow.test.js`、`server/record-sync.test.js` 与新增 `server/reference-data.test.js`：55 项通过；`server/export.test.js`：1 项通过。原版与接入版 24 项等价检查通过，覆盖 23 个图表；公司抬头差异单独归一。
- `app-safety.test.js`：16 项通过、1 项原有移动端字体断言失败；原 QC_department 同一测试也复现同样失败。
- `npm run build`：帮助指纹、Tailwind 扫描、Vue/TypeScript 及主应用 Vite 构建通过；最后 `build:image-translation` 报 shinobu-web 独立依赖未安装。
- Compose YAML 及私有端口/持久卷/健康依赖结构校验通过，未启动 Docker 生产容器。
- 实际主项目完成启动、正常停止、再次启动：5173 页面、8000 与 3411 健康检查均 HTTP 200；停止时三个端口全部释放。13 个 QC 库重启后与迁入时逐表摘要一致，主库仅在线状态表因打开页面发生正常变化。
- 生命周期和网关测试合计 10 项通过；独立审查另验证 API 管道关闭后 Node 退出。
- 原 QC 源码及数据库保留于 QC_test/历史副本-已停用-20261026。通过内置浏览器交付登录后的 5173 新工作台，截图位于 QC_test/合并备份-20261026/5173-重启后QC工作台.png；这不是完整 Chrome DevTools 视觉验收。

## 模板参考数据与清除边界

本地华兴 QC 按用户确认保留原东莞兴信库的 30 条记录（含模拟记录），仅用于功能和模板参考，不代表华兴实绩。原库及其他厂区不改动。`qc_reference_records` 独立记录来源公司、原编号、导入批次及原始行快照；不改变验货字段结构。参考数据原始回执保存在归档预览的 `outputs/qc-audit/`；主系统合并备份和逐库校验保存在 `QC_test/合并备份-20261026/`，不自动部署到生产。

数据导入页的“清除模板参考数据”先等待浏览器保存队列成功并冻结操作，再调用 `POST api/reference-data/clear`。接口要求 result_write、order_write 和 customer_manage，事务内只删除仍与导入快照一致的参考行并写入删除墓碑；新记录和已修改参考行保留。失败回滚，不整库替换。其他浏览器尚未保存的草稿不在服务器保护范围内，正式清理前应完成所有编辑。

含参考数据的 JSON 备份携带来源信息，当前禁止作为普通业务数据回灌，以免丢失参考身份。PDF、页面抬头和 CSV/Excel 内容有参考标记。原“恢复示例”在空种子下会清空记录，接入版已移除入口且函数阻止执行。正式排期已提供只读适配；保留全部参考记录，清理仍需用户另行授权。排期仅确认生成待验任务，不自动成为已验货/PASS 记录。

## 私有模板与示例部署

历史客户工作簿、累计模板及客户排期示例不随公开仓库发布。现有本地业务文件保留原位，不迁移或删除。新环境需通过私有渠道单独配置 `backend/app/templates/qc-cumulative/<factory>/` 下的已验证 `manifest.json`、`initial.xlsx` 与修复所需 `original.xls`；客排期示例为私有的 `services/qc-department/fixtures/qc-schedule-example.json`。缺少配置时，相应端点明确返回不可用，正式业务排期和独立验货流程保留。依赖历史文件的验收必须在配置文件后执行，不能将缺少私有资料的检查称为通过。
