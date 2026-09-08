# PDF 引擎验证记录

核验日期：2026-09-08。以下为本地真实执行证据，不是生产发布或任意业务文件的无损保证。全部样本由代码合成，未使用业务订单、用户上传资料或远程文档。

## 样本与测试分别计数

- `outputs/document-tools/benchmark/pdf-inputs/` 实际保存 **41 份 PDF 源文件**，对应 **41 个不同 SHA-256**。
- `outputs/document-tools/benchmark/pdf-manifest.json` 逐份记录 SHA-256、特征、操作、独立期望、实际结果、局限以及输出和 IR 路径。
- 样本分组为 16 份几何变体、8 份原生结构/混合页、6 份分页边界、8 份扫描挑战、2 份密码样本、1 份交互注释样本。几何变体有意共用固定源文字，分别改变 Rotate、CropBox 和 UserUnit 来隔离坐标误差；不是 16 份不同业务内容。
- 操作分布为 PDF 分页 25 份、PDF→Word 12 份、PDF→Excel 4 份。另有 Office 引擎自己的样本，不在这里重复计数。
- 41 份样本的独立期望均通过，其中 40 份生成可读结果，1 份按预期返回 `PASSWORD_REQUIRED`。扫描样本“通过”包含正确标为待核验或未知，并不表示识别文字全部正确。
- 原有 47 项 PDF/Qwen 专项测试通过；样本整理发现问题后新增“部分数字旁的遮挡不能当完整金额”和“双栏正文不能误判成表格”回归，最终为 **49 项测试通过**。测试数和源文件数不可互换。

实际命令：

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_document_tools_pdf_engine.py backend/tests/test_document_tools_qwen_ocr.py -q --basetemp=D:/RR/tmp-document-pdf-delivery -o cache_dir=D:/RR/tmp-document-pdf-cache
# 49 passed in 11.12s

backend/.venv/Scripts/python.exe outputs/document-tools/benchmark/build_pdf_benchmark.py
# input_count=41, unique_source_hashes=41, passed=41, failed=0
```

`outputs/` 中保留当前本地证据和可重复运行的生成器，未作为业务输入或提交到 Git。重跑生成器会重建其专属合成样本与结果。

## 原生结构与分页

已断言：一页两张有线表、两张无线表、横向与纵向合并、真实 Word 表格和 Excel 单元格、`00123` 前导零、超过 15 位编号文本、可计算的 `12` 和 `12.50`、`1,234` 地区歧义保留、跨页衔接的严格条件、原文单元格坐标、重复文字层去重与双栏阅读顺序。

分页样本覆盖 Rotate 0/90/180/270、非零 CropBox、UserUnit 0.75/1/2、混合纸张、重排、重复页、双页分片和 1800 pt 长页。16 份几何变体逐份验证输出页数、尺寸之和、分片无缺口及切点误差小于 0.001 pt；专项测试还使用 PDFium 打开、渲染并验证尺寸，确认文字资源仍存在。这是这些合成页面的结果，不能外推到所有畸形 PDF。

裁切分页通过页面对象和视口实现，不光栅化原页。来源映射中的 `visible_text` 排除裁切外文字，但底层 PDF 内容仍可能被通用文字提取器读取，**不属于物理删除或脱敏**。标准页提取保留外部链接和普通文字注释，移除内部跳转与 Widget，避免产生失效目标；裁切工作副本不保留交互注释。重新生成的文件不继承原数字签名有效性，原件保留。

## 本地 OCR 的真实结果

实际运行 RapidOCR + 本地 PP-OCRv6 ONNX 模型；扫描样本没有使用 mock。六个文本样本的独立真值都是 `ITEM 00123 QTY 12 AMOUNT 12.50`。CER 为 Levenshtein 字符距离除以真值长度，包含空格和顺序。

| 样本 | 实际变换 | CER | 三个关键字段 `00123`、`12`、`12.50` | 自动通过 |
| --- | --- | ---: | --- | --- |
| scan-clear | 清晰扫描 | 0 | 均匹配 | 否，待核验 |
| scan-blur | GaussianBlur 2.2 | 0 | 均匹配 | 否，待核验 |
| scan-skew | 旋转 3° | 0 | 均匹配 | 否，待核验 |
| scan-stamp | 红色圆形章线覆盖 | 3.33% | 均匹配；`QTY` 误读为 `QT` | 否，待核验 |
| scan-lowcontrast | 灰色文字 | 0 | 均匹配 | 否，待核验 |
| scan-small | 缩至 330×96 | 0 | 均匹配 | 否，待核验 |

这些样本的关键字段检查为明示真值子串存在性，不是通用字段定位准确率；不能用它掩盖章覆盖文字错误。没有把不同难度样本平均成一个“高准确率”。六份均未自动放行，自动通过覆盖率为 0，测试集中错误自动放行数量为 0。

`scan-merged-table` 使用实际扫描图与本地 OCR，恢复 3×3 网格和 `A1:B1` 合并；8 个有内容的源单元格原字串全部匹配，`00123` 按文本写出，数量和金额按数字写出，XLSX 重新打开检查通过。

`scan-occluded-table-cell` 故意用黑块覆盖 `12.50` 的大部分，只剩部分数字 `1` 可见。引擎保留 `1` 为候选，把正式显示值标为 `[无法辨认]`、`resolution=unknown`、`value=null`，输出具体 `OCR_CELL_UNKNOWN`；不把部分数字当完整金额，也不把未知当空白。新增实测回归覆盖此情况。未知识别依赖可观测遮挡/墨迹，不能承诺发现世界上所有缺失或改写。

另有原生文本与扫描图分区的混合页、可疑 ToUnicode 映射、局部重识别不覆盖原生或人工确认值的验证。

## Qwen：契约验证与真实调用分开

契约测试覆盖 DashScope `parameters.ocr_options.task=table_parsing`、OpenAI 兼容 Chat 不携带 DashScope 专有参数、HTML `rowspan/colspan`、空白与未知区别、缺格/未闭合表格拒绝、有限重试、截断不重试和实际 usage 透传。协议依据当日重新核对的[阿里云官方 API 参考](https://help.aliyun.com/zh/model-studio/qwen-vl-ocr-api-reference)。

用户更正北京业务空间专属地址后，2026-09-08 使用新 Python 进程重新加载配置，以不含业务数据的自建 3×3 表格完成以下真实 DashScope 调用：

| 真实调用 | 实际模型 | input / output / total tokens | 耗时 | 识别结果 |
| --- | --- | --- | ---: | --- |
| PNG OCR smoke | qwen3.5-ocr | 509 / 143 / 652 | 1.168 s | 3×3 网格和 9 个单元格全部匹配 |
| PNG 布局 smoke | qwen3-vl-plus | 446 / 137 / 583 | 2.645 s | 3×3 网格和 9 个单元格全部匹配 |
| 扫描 PDF→Excel 云增强 | qwen3.5-ocr | 3442 / 143 / 3585 | 1.393 s（模型调用） | 真实扫描页、3×3 可编辑单元格、6 个关键数值全部匹配 |

关键数值为 `00123`、`12`、`12.50`、`00456`、`24`、`24.50`。云增强的最终 IR 包含真实 `qwen_calls` usage，生成可打开的 XLSX，仍为 **needs_review**，带 `OCR_REVIEW_REQUIRED`，没有因模型返回正确样本就自动批准所有扫描识别。上述耗时仅为单次观测，不是性能保证；usage 为服务实际返回，不换算成账单费用。

当前专属地址对 `qwen3.5-ocr` 的实际 `max_tokens` 上限是 **16384**。最初照通用官方文档请求 32768 返回 `InvalidParameter`，错误明确要求 `[1, 16384]`；适配器已按该实际服务限制修正并成功重测，截断拒绝机制仍保留。

此前错误地址的 HTTP 403 / `Endpoint.AccessDenied` 已因用户更正地址而解决，历史安全诊断仅保留作证据，**不再是当前阻塞**。没有从密钥前缀猜地址，也没有把密钥发往未授权地域或其他域名。

成功证据在 `outputs/document-tools/qwen-live-20260908/verified-host/`：`successful-smoke-results.json` 汇总两模型的成功调用；另有 `ocr-success.json`、`conversion-result.json`、`output-validation.json`、`conversion/ir.json`、`conversion/result.xlsx`。历史 `smoke-results.json` 保留修正 token 上限前的 OCR 失败，不能将它误当作当前状态。报告不含密钥、请求头或完整配置。OpenAI 兼容方式仅完成契约测试，此次真实调用使用 DashScope；没有把两个协议的验证混为一谈。

## 已知边界

- 原生无线表和阅读顺序使用几何规则；复杂嵌套版面、文本框重叠、公式和异常字体仍可能需要核验。
- 扫描有线表通过真实图像线条恢复网格；没有稳定边界的复杂扫描表格依赖 Qwen 或人工局部修正。Qwen 已在自建清晰表格上通过真实调用，尚未完成复杂业务扫描矩阵评估。
- HTML 无坐标时，只提供真实的区域锚点，不能伪造每个单元格的精确位置。
- PDF→Word 为真实可编辑内容重建，不承诺与 Microsoft Word 或任意原 PDF 完全相同。版式模式的定位写出和回渲染由 Office 引擎负责；此份基准不拿文件能打开当作全版式验收。
- 本报告是本地合成证据；未开展真实业务授权样本评估、生产负载测试或生产部署。
