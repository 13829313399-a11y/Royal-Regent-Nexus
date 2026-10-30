# Office 文档引擎实测记录

## 2026-10-29：真实业务文件与线上环境复核

结论：密码处理需要修复；字体缺失和 Word 兼容排版同时影响结果。已完成现有 LibreOffice 与 ONLYOFFICE 的真实文件对照，两套服务器引擎均未通过本次同版验收，不能直接切换引擎或声称补字体即可修复。当前工具可以完成多种结构转换，但不能用历史合成样本通过率证明业务文件保真。

### 样本、线上记录与排版证据

- `华兴玩具企业环境管理手册.doc`：真实 OLE DOC、未加密，SHA-256 为 `9368de0e27088b17539fa69eb26d8e8de3e3421c89ce437724d1b497f15e6d15`。本机 Microsoft Word 16.0 只读打开、导出为 33 页，含 32 张表，源文件哈希不变。线上同哈希文件的两次 Word→PDF 输出均为 **47 页**，状态 `needs_review`，包含 `FONT_SUBSTITUTION`、`RENDERED_CONTENT_MISSING` 等提示。
- `（品管部）客投诉处理指引(16).doc`：真实加密 OLE DOC，SHA-256 为 `bea2cdfccb7ffebf9914387d5aacf84d4e28ecc9bfd0c5063d1ba96c0d27961c`；用户确认需要打开密码。线上同哈希文件有正常的 `PASSWORD_REQUIRED` 等待记录，也有读出结构后预览失败、四次 Word→PDF 返回 `OFFICE_OPEN_FAILED` 的记录。不能把后者解释成用户未输入密码。
- 用户在本机专用窗口完成认证后，读取了 API 和独立 worker 的版本、字体和上述哈希对应的任务记录；未部署、重启、写业务数据库或导出密码。两者都是 **LibreOffice 25.2.3.2**，UNO 为 `/usr/bin/python3`。宋体、楷体及 Times New Roman 等被 fontconfig 匹配为 DejaVu Sans/Serif；任务报告也记录了实际字体替代。字体缺失是已证实的排版风险，无法仅凭这些读数量化其与引擎差异各自造成的页数变化。
- 在隔离解包的官方 LibreOffice **26.8.1 Windows** 上，现有规范化路径和直接 DOC→PDF 试验均输出 33 页，但抽查第 1、17、23、33 页仍存在封面下移、表格跨页及末页内容分配差异。直接 DOC 输出的封面并未改善，因此**没有将直接转换作为新的默认路径**。页数相同不能代表分页、位置或内容等价；这份手册尚未通过排版验收。

### 两套排版引擎的隔离对照

在公司现有内部服务中运行测试副本，未部署、改字体库、重启服务或写业务任务表。ONLYOFFICE 10.0 的 [file upload Conversion API](https://api.onlyoffice.com/docs/docs-api/additional-api/conversion-api/request-from-file) 使用现有 JWT 认证，文件在公司内部传输。LibreOffice 25.2.3.2 使用临时加载的待发布转换模块，不替换正在运行的应用代码。

| 输入与引擎 | 环境手册页数 | 客诉指引页数 | 验收结论 |
| --- | ---: | ---: | --- |
| 本机 Microsoft Word 原件参考 | 33 | 1 | 作为本次对照；原件哈希保持不变 |
| Word 另存普通 DOCX，再由 Word 导出 | 33 | 1 | 全页栅格与上述参考相同，确认另存步骤未改变本次参考版面 |
| 原始 DOC／解密 DOC，服务器 LibreOffice | 47 | 1 | 手册分页变化；客诉字体和文字位置仍不同 |
| Word 普通 DOCX，服务器 LibreOffice | 48 | 1 | 不能靠另存 DOCX 消除服务器字体差异 |
| Word 嵌入字体 DOCX，服务器 LibreOffice | 33 | 1 | 手册封面下移、跨页内容分布不同、最后一页正文空白；客诉标题缺字 |
| 原始／解密 DOC、普通或嵌入字体 DOCX，ONLYOFFICE | 39 | 1 | 手册仍多页，客诉仍有字体和位置差异 |

上述两份文件共完成 **16 次内部服务器转换**，均可生成 PDF；这不是 16 次保真通过。最后四次关闭 Word“仅嵌入所用字符”的选项后重试，两套引擎的上述问题仍存在。ONLYOFFICE 在这些副本中仍输出 WenQuanYi Zen Hei Mono 等字体；不能据此推断所有版本都不支持嵌入字体。LibreOffice 的嵌入字体输出实际包含 SimSun；fontconfig 的系统字体匹配清单不能替代最终 PDF 字体检查。

环境手册保留 **27 个零行距段落**，包括白色文字。Word 与 LibreOffice 对其实际占高不同。只在副本中把零倍行距改成固定 0 或 1 twip、保留全部文字的试验改善了封面位置，却得到 **32 页**且仍不匹配，因此未采用这种自动改写。原样提取时增加 `WORD_ZERO_LINE_HEIGHT` 提示，不删除白色文字、不改行距、不按目标页数删页。

已检查手册嵌入字体候选与 Word 参考的全部 33 页对照图，以及客诉的单页对照；可见问题足以判定候选未通过。全页像素和字符分布统计只用于找差异，不是准确率。Word 参考保留其自身对原始浮动对象、表格和分页的解释，不宣称等同于作者当时的 WPS 显示结果。

用户在专用窗口输入正确密码后，客诉原件通过 Word 打开和 `msoffcrypto` 解密；解密后的同一 DOC 在服务器待发布 LibreOffice 路径生成 1 页 PDF、31 个原生文字单元全部通过文本覆盖检查，但仍有版面差异。这证明本次解密及后续转换路径可工作；没有把密码录入业务系统重新提交任务，因此不声称生产 UI 的完整加密上传流程已验收。密码未写入脚本、命令参数或报告。

本机字体按 Word 的嵌入权限写入文档副本，未将 Windows 字体文件复制安装到服务器；[微软字体授权说明](https://learn.microsoft.com/en-us/typography/fonts/font-faq) 区分文档嵌入与服务器字体安装。两份参考 PDF 在验收目录的 `交付PDF/` 中。

### 本次保留的修复

1. 支持的旧 DOC/XLS 加密方式先用现有 `msoffcrypto` 在临时副本中解密，保持二进制格式；错误密码返回 `INVALID_PASSWORD` 并继续允许重输。库不支持的旧加密方式仍交给 Office 读取器。
2. 解密、规范化或人工修订后的明文 DOCX/XLSX，不再携带原文件的打开密码调用渲染器。原流程把该密码带到未加密中间文件，可能导致再次打开失败。
3. DOC/XLS 规范化只应用读取所需选项；工作表、公式和打印参数在后续提取或最终输出时应用，避免规范化阶段先改动隐藏状态和打印布局。默认 PDF 排版流程保留。
4. 上传检查阶段也报告字体替代。旧 DOC 记录页数与输出不同时增加 `PAGE_COUNT_CHANGED`，明确该记录可能过期；不将缓存页数当成标准答案，也不自动删除空白页。
5. 必需 Office/UNO 组件缺失时，API 在创建转换任务前给出明确提示；Excel→PDF 能力状态同时检查 UNO。无需渲染器的原生结构转换仍可使用。
6. Windows 偶发的 Office profile 文件占用不再让临时清理错误覆盖转换结果或真正的转换异常。原任务进程隔离和取消逻辑保持。
7. 检测到 Word 正文或表格中的零行距设置时标记版面待核验，保留全部原文和格式。普通行距文件不增加此提示。

自建、已知密码的加密 DOC 对照中，修复前错误密码与正确密码均得到 `OFFICE_OPEN_FAILED`；最终修复后缺密码为 `PASSWORD_REQUIRED`、错误密码为 `INVALID_PASSWORD`、正确密码生成 1 页 PDF，输入哈希不变。真实客诉文件的密码与渲染验证边界见上文。

本轮实际验证：

- 相关 Office、任务、PDF、翻译契约回归 **130 passed**；默认跳过的真实 worker 用例随后显式开启，独立运行 **1 passed**，覆盖七个转换方向、三次源文件检查，共 10 个独立子进程任务，结果可复开、编号/金额保留、数据库完整性通过。
- 20 份合成 DOCX/XLSX 样本的 **40 次真实转换**全部生成可读产物且关键编号检查通过。其中 **5 个产物仍有质量提示**：两项不兼容公式结果、日期窄列截断、宽表 PDF 截断、宽表 Word 排版，不能写成“40 次无损”。
- 真实旧格式 DOC/XLS 四条转换路径均通过；A3 横向适合宽度、显式隐藏工作表、Word 人工修订、Excel 人工修订四组检查通过。
- 首轮旧格式补测遇到 Windows profile 清理文件占用，修复后重新完成四条旧格式路径和四组选项验证；保留原失败日志，不掩盖初次结果。
- 新增零行距风险提示后，Office 与文档任务回归再次运行，**74 passed**，包含原文不被改写、普通行距不误报及密码/任务行为检查；没有累加重叠用例作为新的全量通过数。
- 验证使用隔离数据库、临时存储与官方校验通过的测试运行包，未发送客户文件到外部 AI。两份用户原件的最终 SHA-256 与输入时一致。本轮未修改前端，没有新增浏览器视觉验收；后续 PDF 对照范围见上文。

相关自动测试命令为 `python -m pytest tests/test_document_tools_office.py tests/test_document_tools_jobs.py tests/test_document_tools_pdf_engine.py tests/test_document_tools_translation.py tests/test_document_tools_worker_process.py -q -p no:cacheprovider`，在 `backend` 目录运行。真实进程用例需另设 `RR_DOCUMENT_WORKER_SMOKE=1`、隔离的 `RR_DOCUMENT_WORKER_SMOKE_DIR` 及测试 Office/UNO 路径。实测日志为 `accepted-regression.log`、`worker-smoke.log`、`legacy-options-verified.log`。

### 其他方向的审计边界

| 方向 | 当前机制与结论 |
| --- | --- |
| Word→PDF | LibreOffice 排版；旧 DOC 先规范化。真实复杂 WPS DOC 未通过保真验收，字体、浮动对象、兼容排版都需核对。 |
| Excel→PDF | Calc/UNO 按工作表、区域与打印设置导出。宽表、窄列和不兼容公式会造成截断或错误值，现有检查保留提示。 |
| Word→Excel | 原生段落/表格结构提取，不是原 Word 页面的逐像素复制。图片中的表格需另行识别。 |
| Excel→Word | 静态表格和显示值输出；公式不再计算，图表以图像呈现。宽表使用横向页面并保留提示。 |
| PDF→Word | 原生文本/几何提取、必要时 OCR，然后重建可编辑文档。双栏、浮动元素、扫描件不能承诺原版式。 |
| PDF→Excel | 提取表格、类型和来源；扫描识别、跨页合并需核验。PDF 本身不携带可恢复的原 Excel 公式。 |
| PDF 精确分页 | 基于 PDF 页面对象和可见区域操作，相关几何、旋转、加密、取消回归覆盖；裁剪不等于安全删除隐藏内容。 |
| Word/Excel/PDF 翻译 | Office 结构与译文完整性契约已有回归；PDF 译文重新排版，翻译变长也可能改变分页。本次没有发送客户文档进行真实云翻译，也没有验收翻译语义质量。 |

### GitHub 方案复核

以下为 2026-10-29 查询项目与官方文档后的建议，没有把仓库仍可访问等同于仍受原作者维护。

| 项目 | 适用范围与建议 |
| --- | --- |
| [ONLYOFFICE DocumentServer](https://github.com/ONLYOFFICE/DocumentServer) | 已用公司现有 10.0 内部服务完成本次真实文件比较：手册 39 页，客诉 1 页，均有版面差异，未采用为新的默认转换引擎。[官方 Conversion API](https://api.onlyoffice.com/docs/docs-api/additional-api/conversion-api/request/) 可独立关闭，编辑器可用不代表转换接口已启用。尚未扩展到该引擎的 Excel 打印验收。 |
| [Gotenberg](https://github.com/gotenberg/gotenberg) | 成熟的 HTTP 文档转换服务，可减少自行维护进程、超时与转换接口的工作；[Office 路径底层仍是 LibreOffice](https://gotenberg.dev/docs/convert-with-libreoffice/convert-to-pdf)，不能靠替换服务包装保证修好当前排版。 |
| [unoserver](https://github.com/unoconv/unoserver) | LibreOffice 常驻服务和客户端，适合改善进程复用与吞吐；同样不会替换排版内核。其 README 仍说明 Windows/macOS 支持未验证，优先考虑服务器使用。 |
| [pdfplumber](https://github.com/jsvine/pdfplumber) | 当前系统已经使用，适合原生 PDF 文字和表格提取；项目明确更适合机器生成 PDF。无需因本次 Word 问题整体替换。 |
| [OCRmyPDF](https://github.com/ocrmypdf/OCRmyPDF) | 适合扫描 PDF 的识别层、纠偏和预处理，可作为补充；不直接恢复 Word 排版或 Excel 公式。 |
| [pdf2docx](https://github.com/ArtifexSoftware/pdf2docx) | README 明确声明 Artifex 已停止主动维护。可研究其实现，但不建议作为新的核心维护依赖。 |

本次两套引擎均未满足 Word 同版验收，因此没有发布转换引擎变更。后续若提供严格保持 Word 版面的线上服务，需要另行验证能够满足该约束的引擎与授权部署方案；不能把安装字体、换服务包装或自动调整行距当作已证实的通用修复。密码/旧格式兼容、运行条件检查、风险提示与“协同填表”移除已通过 `document-tools-61b57436-83010596-20261029` 发布；Excel 范围和预览状态修复随后通过 `document-tools-excel-e20e398a-20261030` 发布。测试后专用服务器/容器目录已清理，API、worker、ONLYOFFICE 均为 healthy，SSH 会话已关闭。

本轮证据目录：`D:/royal regent heyuan/outputs/document-conversion-audit-20261029`。`production-diagnostic.json` 是限定范围的线上只读结果；`word-reference.json`、`crypto-comparison.json`、`office-corpus/smoke-report.json` 和 `visual-comparison/` 保存本地证据。对照图中的直接 DOC 试验未采用，不能当成最终修复质量证明。

内部引擎对照证据目录：`D:/royal regent heyuan/outputs/document-conversion-acceptance-20261029`。`manual-engine-report.json`、`complaint-engine-report.json`、`full-font-engine-report.json` 记录 16 次转换；`*-layout-analysis.json` 和 `visual/` 记录全页对照；`zero-spacing-trial.json` 记录未采用的行距试验；`regression.log` 记录 74 项回归；`closure.json` 记录临时目录清理和服务健康。

## 已上线修复与主线范围

主线保留上述两个已验收发布包的运行代码；较新的主线配置继续保留。协同填表的历史迁移、数据库表和文件数据不删除，在线文档的账号与厂区校验独立保留。

Excel 仅对超限的自动选区收缩不可见的格式尾部。实际值、公式、空白模板的填充/边框、合并单元格及相关条件和整行/列格式保留；用户明确选区与打印区域不收缩。真实超过 250000 单元格的范围继续拒绝，并指出工作表和范围。Calc 回读沿用已验收的源范围，避免重算再次扩展范围。`EXCEL_UNUSED_RANGE_TRIMMED` 记录原始和有效范围，源文件不改写。

已发布的九工作表实文件验收保留全部 3822 个非空可见值及 44 个公式来源；服务器 Word 校样 43 页、本机 46 页，因此不代表分页保真通过。读取失败、取消和等待密码时，预览区显示真实状态，并保留原文下载。

两份 WPS PDF（33 页手册、1 页客诉）仍是 Word 排版验收标准。仅继续评估免费/开源方案；尚未通过的字距、分页、流程图和表格适配不包含在这次主线范围内。补回主线不触发再次上线，也不改变运行中的数据库。

发布证据：`outputs/document-tools-release-20261029/deployment-receipt.json` 与 `outputs/document-layout-fidelity-20261030/excel-release/deployment-receipt.json`。测试与源码核对记录保存在 `outputs/document-main-sync-20261030/`，私有样本和运行产物不进入源码仓库。

## 2026-09-08：历史合成样本记录

测试日期：2026-09-08。以下为本机真实运行结果，不代表生产环境已发布，也不代表真实业务文档已经验收。

使用 LibreOffice 26.8.0.3（构建 bce0998afefdbc355585ca324285661a2170ba77）、其自带 Python 3.13 UNO 解释器、python-docx 1.2.0、openpyxl 3.1.5。LibreOffice 位于隔离解包目录 `D:/RR/tool-runtimes/libreoffice/26.8.0`，未替换 Microsoft Office 或修改默认文件关联。原生 Office 转换没有调用千问。

## 样本与四个转换方向

生成器位于 `backend/tests/test_document_tools_office.py`，`generate_corpus` 可以重新生成全部 20 份样本。样本包含中文、真实段落、真实单元格与表格，而非两行占位文本。

| DOCX 十种样本 | XLSX 十种样本 |
| --- | --- |
| 普通段落与四列表格 | 普通订单表与单元格填充 |
| 横向合并 | 矩形合并 |
| 纵向合并 | 隐藏工作表、行、列 |
| 矩形合并 | 缺缓存 SUM 与不兼容函数 |
| 单元格内嵌套表 | 日期、时间 |
| 页眉表格及页脚说明 | 百分比、前导零显示、括号负数 |
| 55 段长文及明确分页 | 打印区域、重复标题行、横向纸张 |
| 多段说明与全文结构模式 | 命名范围 |
| 不同语义的多表 | 原生柱状图及底层数据 |
| 长编号、地区歧义字串、公式形文本 | 17 列宽表 |

四个方向各运行 10 次：Word→PDF、Word→Excel、Excel→PDF、Excel→Word，共 40 次，最终 40 份产物均成功生成并可读取。原生专项同时校验前导零和长编号、合并范围、嵌套来源、隐藏项、命名区域、公式缺缓存、输出可编辑对象，以及输入文件 SHA-256 不变。

最终合并报告：`outputs/document-tools-office-verified-20260908/final-report.json`。其中 Excel→Word 结果采用修复后的 `outputs/document-tools-office-word-final-20260908`，替代初轮视觉检查发现的默认填充颜色问题。初轮原始日志保留作为排错证据，不应当作最终质量记录。

“40 份产物成功”不等于“40 份完全无损”。下述 6 个结果保留待核验提示：

| 结果 | 实際发现与处理 |
| --- | --- |
| 不兼容公式样本→PDF | 缺缓存 SUM 可由 Calc 得到显示值；`_xlfn.UNKNOWN` 返回 `#NAME?`，保留缺缓存及兼容性问题，未写成零 |
| 不兼容公式样本→Word | 同上；Word 显示静态结果或显式公式文本，不继续执行 Excel 公式 |
| 日期样本→PDF | 原表日期列过窄，原打印布局没有完整显示日期；文本覆盖检查定位到对应单元格 |
| 数字格式样本→PDF | 原表列宽使括号负数无法完整显示；保留内容缺失问题 |
| 宽表样本→PDF | 原打印布局中的备注列被截断；定位到具体单元格，不通过“PDF 能打开”掩盖 |
| 宽表样本→Word | 17 列按横向纸张输出，保持 10 磅正文并跨两页；提示可选更大纸张或缩小选区，不无提示缩为极小字 |

PDF 内容检查使用 pypdf 内容流读取与 pdfplumber 几何读取，按去空白后的原生文本片段作覆盖核验，避免字体分段导致完整标题被误判缺失。该检查不是像素等价、阅读顺序的完整证明，也不是统计意义上的准确率。

## 旧格式、打印选项与修订

另用 LibreOffice 从自建样本生成真实 OLE `.doc` 和 `.xls`，验证四条实际路径均成功：DOC→PDF、DOC→XLSX、XLS→PDF、XLS→DOCX。记录在 `outputs/document-tools-office-legacy-20260908/legacy-report.json`；修复版 XLS→DOCX 校样位于同目录 `excel-to-word-final`。

额外四条实际断言通过，记录在 `outputs/document-tools-office-options-20260908/options-report.json`：

- 17 列工作表以 A3 横向、适合宽度输出为一页，纸张方向与页数符合选项。
- 明确选择隐藏工作表并包含隐藏项，输出只含所选隐藏表，不混入可见订单表。
- Word 原生单元格修订为 `CORRECTED9988` 后，实际 PDF 含新值、不含旧编号，原文件哈希不变。
- Excel 原生单元格同样修订后，实际 PDF 新旧值断言及原文件哈希不变均通过。

修订采用工作副本中的定点 OOXML 修改，不重建整个原工作簿。专项断言确认 XLSX 图表部件 `xl/charts/chart1.xml` 的原字节保持不变；Word 正文、嵌套表、页眉定位均有测试。

## 可编辑版式输出与视觉检查

PDF→Word 的版式模式在本引擎的 `write_docx` 内使用带真实文字和真实表格的 OOXML 文本框，按可见页面左上角 point 坐标定位，没有用整页截图替代可编辑内容。

两页双栏及表格自建样本已经由 LibreOffice 回渲染：源横坐标 40/320 pt 对应 PDF 文字 40.1/320.1 pt；源框顶部 80 pt 对应字形顶部 81.6 pt（字形基线与边框不是同一坐标）。两页数量保持，表格文字可提取，目视没有遮挡。产物与截图在 `outputs/document-tools-positioned-smoke`。这是一组定位样本的证据，不是所有复杂 PDF 已达到该误差的承诺。

另已目视检查普通中文 Word→PDF、修复后的 Excel→Word、图表导出和 17 列宽表。图表样本包含 1 个真实 Word 表格及 1 个独立图表图像，同页排布正常；原表数据仍可编辑。修复后的普通 Excel→Word 是白底表格，保留指定浅蓝单元格、长编号、列宽比例、备注换行。

## 运行边界与测试

每次渲染使用独立短路径临时 profile，防止 Windows 深层任务目录触及 Office profile 路径长度问题。UNO 由真实可导入的独立解释器运行，默认禁止宏执行及外部链接更新；原打印模式直接保留原页面样式，只有明确修改布局时才复制相应样式。取消/超时终止本任务进程树，不结束其他用户或其他任务实例。

原生专项命令：

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_document_tools_office.py -q --basetemp=backend/.pytest-tmp-office-document-final -o cache_dir=backend/.pytest-cache-office-document
```

结果：37 passed，最后一次运行 8.97 秒。另通过三个实现/测试文件的 `py_compile`。37 项包括真实加密 DOCX/XLSX 缺密码/错误密码/正确解密、两进程取消隔离、手改不被重算覆盖、仅匹配连续表头及上下文才合并、真实图像块、版式文本框等。

字体审计在有 fontconfig 的系统中报告请求字体及实际匹配替代；本机 Windows 未提供 fontconfig 清单，报告明确标为不可用，没有声称与 Microsoft Office 完全相同。复杂表格文字溢出、专有字体、特殊域/修订呈现、扫描图片表格仍需原文对照；Word 图片不会被伪称为已提取的原生表格。自建样本不能替代用户真实业务文件和生产环境的独立验收。

后端全量回归使用 `sqlite:///D:/RR/tmp-document-full-regression.db` 独立数据库，并在测试进程内将文档千问 key 清空、AI 模式设为 off。basetemp、cache、日志和 JUnit 输出位于 `D:/RR-test-artifacts/document-tools-full-regression-20260908`。原始全量实际结果为 **26 failed, 1586 passed, 15 skipped, 3 warnings，4710.47 秒**。原始日志和 JUnit 保留；该轮已收集的旧模块不会因运行期间完成的修复自动更新。

全量运行期间定位到跨测试的模块重载污染：部分历史 API 测试删除 `sys.modules` 内全部 `app.*` 模块，使预先收集的测试保留旧异常类，而后续延迟导入使用新异常类。最小顺序复现为认证登录测试通过、文档密码等待和路径校验两项失败（`2 failed, 1 passed`）；生产代码没有被改为按异常名称猜测类型。统一测试夹具仅在原应用模块被替换或删除时恢复原模块图，普通延迟导入保留缓存。

隔离修复后的完整认证加文档任务测试为 `66 passed in 328.78s`。统一夹具下继续按认证、客户订单、文档任务、受影响纸箱业务测试的顺序复验，`24 passed in 30.97s`：覆盖原先受污染的文档密码/路径校验，以及期末锁定、估值和盘点锁月测试。日志分别为 `auth-jobs-fixed.log` 和 `global-isolation.log`。这是有针对性的修复后复验，不能替代原全量运行的实际结论。

认证与客户订单前置之后执行全部 PDF 引擎测试为 `43 passed in 28.75s`（41 项 PDF 加 2 项前置）；同样前置后执行千问契约测试为 `10 passed in 21.59s`（8 项契约加 2 项前置）。日志 `pdf-isolation.log`、`qwen-isolation.log` 证明模块图恢复后真实本地 OCR 矩阵及云请求契约均通过；此处未发起真实云请求。

已逐项核对原始 JUnit 的全部 26 个实际失败节点，修复后均在针对性复验中通过：9 个过期迁移 head 断言、12 个模块重载污染、2 个缺 request_id 的旧测试数据、2 个继承本地认证开关导致模式矛盾、1 个旧职位数量断言。职位断言以现有 fixed-v24 契约为依据，除更新总数 32 外，还精确检查 3D 经理、主管和操作员三个角色。未改变旧业务逻辑或降低原业务断言。

额外复验：迁移 head 7 项全部通过（root 实测 1+6）；仓位调整完整文件 `3 passed in 31.99s`；最后 5 个遗漏失败及必要代表覆盖 `13 passed in 46.50s`。完整逐节点映射保存在外部证据目录的 `regression-failure-resolution.md` 与同名 JSON，含原始 JUnit SHA-256 及各复验日志路径。**没有第二次全量运行**；针对性复验存在重叠前置测试，不能累加后声称全量通过。15 项跳过仍分别保留为未在本轮执行的环境/业务样本测试。
