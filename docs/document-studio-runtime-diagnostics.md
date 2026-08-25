# Document Studio 运行时诊断基线

- 诊断日期：2026-08-16
- 代码基线：`6043832921a0f5bf3dad1456b866b0f533e84e7d`
- 诊断范围：公共工具栏中的 PDF 转 Excel、PDF 转 Word、Word 转 PDF、PDF 翻译、PDF 拆分，以及千问 OCR 和运行时能力暴露
- 诊断原则：区分转换器本身是否可用、HTTP 路由是否可用、千问是否可用、前端是否选择了正确链路

## 结论

五个同步转换器和对应 HTTP 路由在当前生产容器中均可完成最小真实文件处理，生成物可以重新打开。当前主要问题不是五个转换器全部失效，而是前端存在两套执行路径、功能可用性被硬编码、缺少统一能力接口、AI 增强仍绑定 Artifact/Task 任务链路、同步 PDF 翻译没有调用千问翻译模型、成功后自动下载。

因此，后续改造应保留已经可用的本地确定性转换器，新增直接、可诊断的千问服务，并让 Document Studio 只调用 `/api/tools/*` 一套接口。

## 本地开发环境

| 检查项 | 结果 | 说明 |
| --- | --- | --- |
| 前端/API 监听 | 未运行 | 5173、8000、5432、3310 均未监听 |
| 数据库 | SQLite | 本地默认配置 |
| 千问密钥与 Workspace | 已配置 | 仅检查是否存在，未输出任何密钥 |
| Document Studio / 云 OCR 开关 | 关闭 | 本地默认配置不会启用旧任务链路 |
| OCR / 表格核对模型 | `qwen3.5-ocr` / `qwen3.7-plus` | 表格核对开关关闭 |
| 离线翻译模型 | 不可用 | 本地模型目录缺失 |
| LibreOffice 渲染器 | 未启用 | 本地没有声明可用的 Office 渲染器 |
| Artifact 扫描器 | ClamAV | 配置存在，但本地服务未运行 |
| Task Worker | 关闭 | 本地默认配置 |

这意味着本地不能代表生产运行能力，不能仅根据本地开关推断线上工具不可用。

## Phase 0 生产运行环境（改造前只读检查）

| 检查项 | 结果 |
| --- | --- |
| 服务器代码 | 与上述 Phase 0 代码基线一致，跟踪文件干净 |
| API / Worker / PostgreSQL / ClamAV / Broker / Web | 改造前均为健康状态 |
| 容器重启 / OOM | 0 次 / 未发现 |
| Alembic | `20260814_0077 (head)` |
| LibreOffice | `25.2.3.2` |
| Tesseract | `5.5.0` |
| CJK 字体 | Noto CJK 已安装 |
| 千问 Provider | 可用，模型 `qwen3.5-ocr` |
| 离线翻译 | 可用 |
| Office 隔离验证 | 未启用 |
| `/` / `/health` | HTTP 200 |
| `/api/tools/capabilities` | HTTP 404，尚未实现 |
| `/api/tools/diagnostics` | HTTP 404，尚未实现 |

## Phase 0 五项工具真实 Smoke Test

使用内存中的两页 PDF 和一份 DOCX 调用生产容器服务，并重新打开输出文件验证格式。随后通过 FastAPI TestClient、真实路由函数和认证依赖覆盖再次验证 HTTP 路由。

| 工具 | 服务级结果 | HTTP 路由 | 输出验证 |
| --- | --- | --- | --- |
| PDF 转 Excel | 通过；2 页、1 个表格、0 个 OCR 页 | 200 | 工作簿可重新打开 |
| PDF 转 Word | 通过；2 页、1 个表格、0 张图片 | 200 | DOCX 可重新打开 |
| Word 转 PDF | 通过；1 页、0 空白页 | 200 | PDF 可重新打开 |
| PDF 翻译 | 通过；2 页、7 个文本单元、0 个 OCR 页 | 200 | PDF 可重新打开 |
| PDF 拆分 | 通过；2 个单页 PDF | 200 | 两个 PDF 均可重新打开 |

千问 OCR 使用一页真实非空 PDF 进行实时调用：`qwen3.5-ocr` 返回 1 页、8 个内容块，耗时约 29.6 秒，结果通过。

完全空白 PDF 的千问响应没有内容结构，旧适配器返回 `DOCUMENT_OCR_SCHEMA_INVALID`。这是无内容样本边界，不应被描述为普通业务文档 OCR 不可用；后续服务应把“空白页”转换为明确、可操作的空内容结果或警告。

## 已确认的产品与架构缺口

1. `DocumentWorkspaceShell.vue` 同时维护同步 API 和 Artifact/Task 两套路径；用户选择 AI 增强时会进入更重的任务系统。
2. 五个工具的 `available` 在前端常量中固定为 `true`，没有反映 LibreOffice、离线翻译、千问、字体等真实运行能力。
3. 后端没有统一的 `/api/tools/capabilities` 和管理员诊断接口。
4. 当前同步 PDF 转 Excel、PDF 转 Word 路由只调用本地转换器，没有在同一路由内根据模式调用千问 OCR/表格结构化。
5. 当前同步 PDF 翻译调用本地翻译器，没有直接调用千问翻译模型。
6. 成功结果会自动下载，用户无法先确认结果、文件名、告警和处理方式。
7. LibreOffice 对外部关系和缺失字体采取硬失败，边界比“阻断真正危险输入、普通兼容性问题给警告”的目标更严格。
8. 前端错误主要从响应文本推断，缺少稳定错误码、用户可执行建议和统一结果元数据。

## 诊断过程中的非产品故障

- 生产容器未安装 `reportlab`，最初的临时测试夹具无法生成 PDF；改用已安装的 `pypdf` 后继续测试。这不是 Document Studio 故障。
- 初次 DOCX 重新打开检查写错了测试脚本类型判断；修正脚本后五项均通过。这不是产品故障。

## 阶段 1 入口条件

基线已满足继续开发的条件：本地转换器、LibreOffice、离线翻译和千问 OCR 的生产可用性均已用真实调用确认。阶段 1 将先统一能力接口和同步主路径，再接入简化的千问服务；在全链路真实文件 Smoke Test 通过前，不执行旧 Document Studio 任务链路和数据库表的删除。

## 简化版生产 Smoke Gate 与 Phase 4

简化版五工具在生产合并提交 `6d8ff11b2eb267cf37bb590c6612ad34c5a89c8f`
完成真实服务级 Smoke Test，所有生成物均重新打开验证：

- PDF 转 Excel `QWEN`：1 页千问 OCR、1 个表格；`qwen3.5-ocr` 与
  `qwen3.7-plus` 均实际参与，前导零 `00125` 保留。
- PDF 转 Word `QWEN`：1 页千问 OCR，生成 DOCX 可重新打开。
- PDF 翻译 `QWEN`：4 个翻译单元，`qwen-mt-plus` 实际参与，生成 PDF
  可重新打开。
- Word 转 PDF：生产 LibreOffice `25.2.3.2` 完成转换，生成 PDF 可重新打开。
- PDF 拆分：生成 2 个安全命名的 PDF，ZIP 和两个 PDF 均可重新打开。

上述门禁通过后执行 Phase 4：移除旧 Document Job API/UI、Review、六步骤
Task Tool、五个专用 Skill/Prompt 和 Signed File Broker Provider；保留其他模块仍
使用的通用 AI Task/Artifact/Skill/Tool Registry。生产库中旧五类任务共 13 条，
检查时全部是 `COMPLETED`、`FAILED` 或 `CANCELLED` 终态，没有活跃任务。
数据库表、历史数据和 Alembic Migration 保留一个版本周期。

每次部署 Phase 4 及后续版本仍必须重复上述五工具生产 Smoke Gate；仓库测试或
Mock Provider 不能替代真实 Qwen、LibreOffice 与生成物重开检查。
