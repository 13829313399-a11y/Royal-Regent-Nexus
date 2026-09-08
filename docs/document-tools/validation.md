# 公共工具栏本地验收

核验日期：2026-09-08。依据用户原始开发文档实施；原文只读。以下记录本地实现与实际测试，不代表生产部署或未知业务文件完全无损。本轮没有提交或推送 Git。

> 2026-09-08 开发清理：按用户要求，合成样本、下载包、临时测试库、截图及本地样本任务已清出项目。原始产物路径现为历史证据路径；关键日志、JUnit、失败复测映射和指标报告保留在 `D:/RR/maintenance-logs/document-tools-verification-20260908/`。永久删除被自动审批拦截，文件暂存于 `D:/RR/cleanup-quarantine/document-tools-20260908/`，尚未释放磁盘空间。测试源码、运行引擎、真实配置、业务文件与迁移备份保留。

## 七项真实路径

| 功能 | 实际引擎 | 已验证输出 |
| --- | --- | --- |
| Word → PDF | LibreOffice 独立 profile、UNO | 真 PDF、可提取文字 |
| PDF → Word | pypdf/pdfplumber 原生解析；扫描使用 RapidOCR、可选千问；OOXML 重建 | 可编辑文字、真实 Word 表格、PDF 校样 |
| Word → Excel | python-docx/OOXML 原生表格与说明提取 | 可编辑格、合并关系、编号文本、说明表 |
| Excel → Word | openpyxl + LibreOffice UNO 显示值与打印信息；OOXML 重建 | 真实 Word 表格、独立图表图像与校样 |
| PDF → Excel | 原生几何表格；扫描网格/OCR、可选千问候选 | 可编辑 XLSX、数值/编号类型、来源与核验提示 |
| Excel → PDF | LibreOffice Calc + UNO 打印参数 | 多页真实 PDF |
| PDF 精确分页 | pypdf 页面对象和可见框变换 | 页组、排序、重复页、双页与长页裁切；文字/矢量资源保留 |

DOC、DOCX、XLS、XLSX 均有实际成功样本。PDF→Word 的可编辑布局和定位布局分别实现；不以整页截图代替文字表格。Office 原生内容优先，AI 不重写可靠原文或人工确认值。

## 代码与运行

- 页面：`src/views/ToolCenterView.vue`、`src/features/document-tools/`、`src/api/documentTools.ts`；Vue/PDF.js 预览、窗口表格、局部修正、切线历史、任务抽屉。
- 后端：`backend/app/{api,schemas,models}/document_tools.py`、`backend/app/services/document_tools/`、`backend/app/workers/document_tools.py`；私有文件、持续任务、租约续期、取消/重试、不可变修订、Range 下载。
- 迁移：`backend/alembic/versions/20260908_0103_document_tool_jobs.py`；注册与启动检查在 `backend/alembic/env.py`、`backend/app/db.py`，路由在 `backend/app/main.py`。迁移测试的当前 head 更新为 0103。
- 配置/部署：环境示例、Python/前端依赖、`docker-compose.prod.yml`、`vite.config.ts`；API 与 worker 共享文件卷。开发服务忽略生成文件，减少 HTML 产物引发的重载。
- 回归环境：`backend/tests/conftest.py` 隔离旧测试的应用模块重新加载；`test_carton_inventory_relocation.py` 补齐现有接口要求的请求幂等编号。`test_internal_quote_reviewer_withdrawal.py` 显式设置各授权模式的合法写入开关；`test_qc_inspection_migration.py`、`test_three_d_schema_v2.py` 更新当前 head；`test_system_user_management_api.py` 核对已存在的三个 3D 职位及 32 个目录项。未为通过旧测试修改业务逻辑。
- 本地 LibreOffice 26.8.0 与独立 UNO Python 已实际运行；不更改系统默认 Office。真实密钥仅位于被 Git 忽略的 `backend/.env`。

## 实际验证

| 验证 | 结果 |
| --- | --- |
| Office 专项 | 37 项通过 |
| PDF 与千问协议专项 | 49 项通过；其中千问契约 8 项，不等于云端精度测试 |
| 上传/权限/任务/修订/下载专项及旧接口退役检查 | 13 项通过，12.94 秒；含 16 线程密码 key 初始化、万格渲染缓存不随窗口重复发送、原生 Excel 数字修订类型保持 |
| PostgreSQL 16.15 实际并发 | 3 项通过：20 作业 6 线程唯一领取、SKIP LOCKED、过期租约恢复与旧发布者隔离、12 并发重复请求去重 |
| 独立 worker 进程 | 1 项通过，216.90 秒；3 次检查及全部 7 方向共 10 作业，44 产物哈希/大小/复开检查通过 |
| 前端本模块 | 18 项通过 |
| `npm run typecheck:test` | 通过 |
| `npm run build` | 通过 |
| `npm run test:unit` 全量 | 1023 通过、11 超时、13 跳过；两组未修改模块单工作进程复跑 105/105 通过，不能把原始全量记为全绿 |
| 后端全量（原始运行） | 1586 通过、26 失败、15 跳过、3 条弃用警告，4710.47 秒；修复与逐项复测另列，不改写原始结果 |
| 当前迁移 head 复验 | 7 项通过；单 head 1.14 秒，其余 6 项 173.82 秒 |
| `git diff --check`、Python compileall | 通过；仓库没有 npm lint 脚本，未虚报 lint |

原始全量日志与 JUnit 保存在 `D:/RR-test-artifacts/document-tools-full-regression-20260908/pytest.log`、`junit.xml`。该轮运行期间完成的修复不会使已经收集的旧测试模块自动更新，因此原始失败数与后续复测分别记录。

主要命令（pytest 使用外部独立数据库、临时目录和缓存）：

```powershell
npm run test:unit
npm run test:unit -- src/views/__tests__/toolCenter.spec.ts src/features/document-tools
npm run typecheck:test
npm run build
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_document_tools_jobs.py backend/tests/test_tool_center_retired.py -q
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_document_tools_office.py -q
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_document_tools_pdf_engine.py backend/tests/test_document_tools_qwen_ocr.py -q
# 为专用临时 PostgreSQL 设置 DOCUMENT_TOOLS_TEST_POSTGRES_URL 后
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_document_tools_postgres.py -q
# RR_DOCUMENT_WORKER_SMOKE=1，并配置真实本地 Office
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_document_tools_worker_process.py -q
# 全量回归设置 DATABASE_URL 指向独立测试库，AI off
backend/.venv/Scripts/python.exe -m pytest backend/tests -q
```

用户原有本地库先备份、在副本演练后从 0102 升级 0103。备份与证据位于 `D:/RR/maintenance-backups/document-tools-before-0103-20260908-180902/`。原有 127 表、11991 行的逐表内容哈希保持，SQLite quick_check 正常，外键错误 0。之后浏览器合成测试只新增文档任务与正常会话/在线状态记录。

全量发现历史环境测试删除 `sys.modules` 内整个 app 模块图后未恢复，导致后续测试持有的异常类/配置对象与动态导入对象不同。实际复现了同名 ToolError 无法捕获的问题，在 `backend/tests/conftest.py` 增加恢复隔离：仅当原模块被替换或删除时恢复，保留正常延迟导入缓存，不修改生产异常识别。完整 auth+jobs 66 项通过；全局隔离后的 auth/customer 代表、jobs 与受影响纸箱项连续 24 项通过；auth/customer 前置后 PDF 41 项与千问 8 项分别通过（含前置分别为 43/10 项）。这不是把原始全量结果改写为全部通过。

仓位旧测试的两个参数分支漏传 OUTBOUND 接口已要求的 request_id，单独复现为 HTTP 422。补齐合法唯一编号后完整该文件 3 项通过（31.99 秒），没有降低断言或修改库存逻辑；采购导出完整文件独立 6 项通过。

最后实际失败清单另有 5 项：legacy/shadow 测试继承了仅 enforce 合法的写开关、QC/3D 两处旧 head 断言、职位目录漏计已存在的三个 3D 职位。修正测试环境及契约断言后，原失败节点与必要代表共 **13 项通过，46.50 秒**。职位测试同时核对三个 code/name，不只调整数量。

原后端全量的 **26 个实际失败节点均已在修复后的针对性复测中通过**。逐节点原因、修复与证据见 `D:/RR-test-artifacts/document-tools-full-regression-20260908/regression-failure-resolution.md` 和同名 JSON；最终 13 项有 `final-five.xml`。修复后未重新运行整个全量，重叠复测数量不累加为新的全量通过数。

## 样本与内容证据

Office 20 份、PDF 41 份，共 61 份合成源文件。Office 四方向共 40 份输出可复开，其中 6 份按设计保留核验项；PDF 40 份结果成功、1 份缺密码按预期拒绝。样本数、自动化测试数、输出数分别计算。

便于查看的输出包为 `outputs/document-tools/delivery-samples.zip`：独立 worker 七方向各一份结果，加一份真实千问扫描转 Excel，共八个样本；附逐文件 SHA-256 和质量状态。这些是已验证产物的原样副本，不是另外生成的演示结果。

- `outputs/document-tools-office-verified-20260908/final-report.json`：20 源、40 输出，编号、数值、格式、合并与说明核验。
- `outputs/document-tools-office-legacy-20260908/legacy-report.json`：实际 DOC/XLS 四条路径。
- `outputs/document-tools/benchmark/pdf-manifest.json`：41 个不同源 SHA，旋转、CropBox、UserUnit、长页、原生多表、合并、扫描、密码等期望。
- `D:/RR-test-artifacts/document-worker-smoke/20260908-183017-4deb4e3d/report.json`：独立子进程实际全链及 44 产物。
- `D:/RR-test-artifacts/document-tools-browser-20260908/revision-verification.json`：浏览器把 `12.50` 修为 `13.75`，旧版哈希和值不变，新版可复开；21 位带前导零编号保持。
- 同目录 `pdf-cut-verification.json`：浏览器输入 650pt，下载实际两片 CropBox 高度 650/1150pt，总计 1800pt，字体资源存在。

## 千问真实调用

用户确认北京业务空间 `ws-5n53bcsat3og63b5` 后，使用对应专属 Host 的 `/api/v1` DashScope 协议，2026-09-08 实际调用 `qwen3.5-ocr`、`qwen3-vl-plus` 成功。OCR 表格 9 格及 6 个关键数值匹配；扫描 PDF→Excel 实际云增强、生成后重新打开 XLSX 检查通过，仍标为待核验。实际服务限制 max_tokens=16384，已按返回限制调整。

实际返回 usage：OCR PNG 652 tokens，布局 PNG 583 tokens，扫描 PDF→Excel 3585 tokens。没有换算或虚构账单费用。证据 `outputs/document-tools/qwen-live-20260908/verified-host/`。错误空间的历史 403 已解决；OpenAI 兼容协议只完成契约测试，本次真实调用是 DashScope。复杂业务扫描的真实识别矩阵仍需使用获授权业务样本评估。

## 浏览器与容量

在已有登录状态、`http://127.0.0.1:5173/tools?factory=huakang-a` 实际完成上传、后台任务、任务重开、原文定位、修订生成、PDF 下载、切线键盘 10pt 精调/撤销以及真实指针拖动。宽屏 1538×850、笔记本 1366×768、窄屏 390×844 均完成截图与标签/抽屉核验；不足 1000px 的中间工作区使用单栏标签，专注模式获得足够空间后可并排。浏览器控制台最终无 error/warn。临时视口已恢复。

截图在 `D:/RR-test-artifacts/document-tools-browser-20260908/`：`desktop-revision.png`、`laptop-revision.png`、`mobile-revision.png`、`mobile-tasks.png`、`desktop-pdf-cut.png`。开发期间源码热更新会重建当前内存状态，持久任务可重新打开；截图和交互验证在最后前端源码冻结后完成。旋转/高 DPI 坐标数学有专项覆盖，但未把所有设备倍率和浏览器组合都称作真人交互验收。

本地容量：100 页原生 PDF 提取 0.146 秒，10000 格 XLSX 检查及 15 页真实 PDF 校样 41.155 秒。HTTP 首/中/尾 200 格窗口复核了单元格 ID 与值。发现并修复完整显示缓存重复发送后，响应从约 1.02MB 减至约 0.10MB，最终复验耗时 0.072–0.121 秒。证据 `D:/RR-test-artifacts/document-tools-capacity-20260908/184339/`。单次本地结果不是生产并发容量保证；没有开展生产负载测试。

## 已知限制

复杂嵌套/无边框扫描表、遮挡、异常字体、Word 域/修订、专有公式和原打印截断保留明确核验项。本地带章扫描的文字 CER 有 3.33% 错误，不能用关键金额匹配掩盖正文错字。Windows 字体替换清单不可用，未宣称与 Microsoft Office 完全一致。裁切改变可见框，不负责安全脱敏。

默认不自动清理源文件/历史产物；启用保存期限时到期内容与结构接口拒绝读取。生产部署必须使用同一文件卷、备份密码加密 key、演练数据库迁移并重跑该环境真实 smoke；具体步骤见 README。本轮仅完成本地开发与验证。
