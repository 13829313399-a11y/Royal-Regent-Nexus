# 彩星行验报告批量改名

规则 `caixing-inspection` v1.0.0，仅适用于华兴（`huaxing`）。与 BuzzBee 规则独立，沿用公共工具栏的上传、预览、人工改名放行及 ZIP 下载流程。

## 命名与正文取值

`报告号-#货号-PO号-数量-日期.pdf`，例如 `RR6001P-#57812-1931575-4000-2026.1.8.pdf`。

| 文件名字段 | 首页正文来源 | 处理方式 |
| --- | --- | --- |
| 报告号 | Batch no. | RR + 4 位数字，可带 P 后缀；保留后缀及前导零 |
| 货号 | Item number | 5 位货号，允许后接字母开头的款式/包装后缀；命名仅取前 5 位 |
| PO 号 | P/O no. | 7 位数字字符串，保留前导零 |
| 数量 | Quantity (Pcs) | 正整数，允许规范千分位逗号；不使用箱数或抽样数 |
| 日期 | DATE | 月/日/年，校验真实日历日期；输出年.月.日，不补月份/日期前导零 |

报告号不是 Date Code，也不取空白 NO. 栏。Conf No.、O/R No.、页脚 ASST 和原文件名均不能补值。用户已确认按正文优先：所提供 RR6017 的 Item number 为 57810E8-02，因此生成 `RR6017-#57810-1931852-312-2026.4.9.pdf`，不沿用旧名中的 57811。

## 识别与校验

- 支持样本所示 Playmates International Company / SHIPMENT QUALITY INSPECTION REPORT 首页布局。
- 渲染第 1 页后，仅识别上部固定区域（归一化坐标 0.07、0.05、0.95、0.26），强制使用本地 RapidOCR；忽略可能错误的内嵌 OCR 层。渲染与识别仅在内存执行，不保存原件或识别历史。
- 使用识别文字框的相对位置与标签基线配对同一行右侧单元格，支持样本中的轻微倾斜；列边界防止取到邻列。OCR 输出顺序不作为字段关联依据。
- 标签/值缺失、重复、位置歧义、低置信度（低于 0.85）或字段格式错误时阻止自动命名；不猜测 O/0 等易混字符，不拼接缺失数字，也不截断多个 PO。
- 所有 OCR 结果均须对照 PDF 复核。异常可输入完整文件名、逐份确认放行、重新预览后再最终确认下载；损坏/加密 PDF、缺页、OCR 组件故障、非法文件名和重名仍不可绕过。
- 9 份提供的样本以无业务信息的上传名称完成实样验证；预览与执行再次识别结果一致，ZIP 内 9 份 PDF 的字节与输入完全一致。

## 运行边界

使用项目已有的 RapidOCR、ONNX Runtime、本地模型及 pypdfium2，不依赖云端识别。新部署应提前准备本地模型。复杂旋转、不同版式、多 PO、不同位数报告号/货号/PO 不在首版自动识别范围，可人工改名或补充独立规则。通用规则仍默认原生文字优先、Tesseract 回退，BuzzBee 的 OCR 参数和解析规则不变。

## 实现入口与验收

本次变更：

- `backend/app/services/pdf_rename/rules/caixing_inspection.py`：独立命名规则。
- `backend/app/services/pdf_rename/rules/__init__.py`：注册规则。
- `backend/app/services/pdf_rename/contracts.py`、`ocr.py`：可选版面识别与内部文字框证据，原有默认值保持不变。
- `src/features/document-studio/components/PdfBatchRenameWorkspace.vue`：人工文件名提示和最终复核文案通用化。
- `backend/tests/test_caixing_pdf_rename.py`、`src/features/document-studio/__tests__/PdfBatchRenameWorkspace.spec.ts`：规则、范围、异常及工作流测试。
- 本说明与 `PROJECT_MEMORY.md`：维护规则边界及取值约定。

已运行的验证：

- `pytest tests/test_caixing_pdf_rename.py tests/test_buzzbee_pdf_rename.py tests/test_pdf_rename_manual.py tests/test_pdf_batch_rename.py tests/test_document_tools_simplified.py -q -p no:cacheprovider`：159 项通过，使用进程级隔离 SQLite，不写入业务数据库。
- `vitest run` 定向运行 PdfBatchRenameWorkspace、tools API、documentStudio、toolCenter 四组测试：29 项通过。
- `vue-tsc -b`、`vue-tsc --noEmit -p tsconfig.test.json`、`vite build`：通过。项目未配置 lint；构建保留已有 VueUse PURE 注释提示。
- 实样 9/9 按正文匹配，ZIP 原字节校验通过；浏览器用 RR6015P、RR6017 完成规则选择、预览、复核和下载，页面明确显示已生成并打包下载 2 份 PDF。

该功能不新增数据库表或迁移。
