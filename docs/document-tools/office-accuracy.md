# Office 文档引擎实测记录

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
