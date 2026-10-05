# 公共文档工具

`/tools?factory=<id>` 为所有正常登录用户提供十种文档处理方向（七种转换/分页及三种文档翻译）。文件、任务、密码、结果与修订只属于上传账号；厂区仅作为上下文保存，不扩大文件访问权限。旧同步转换接口不再使用。

## 运行方式

### Word / PDF / Excel 翻译

`word_translate`、`pdf_translate`、`excel_translate` 复用上传、独立 worker、个人任务、撤回与结果下载。支持 `translation_direction=zh_to_en|en_to_zh` 和 `translation_engine=offline|online`。Word 输出 DOCX；旧 DOC/XLS 先经 LibreOffice 转为 DOCX/XLSX。Excel 按所选 `sheets` 翻译文字并保留公式、数字、合并格和原始包结构；空选择表示包含隐藏表在内的全部工作表。Word 翻译正文、表格、页眉页脚等文字，Office 图片中的文字不翻译。Word/Excel 不支持按预览页选取翻译范围。

PDF 支持 `page_selection`，先原生提取/扫描识别，再生成重新排版的 PDF 和可编辑 DOCX；必须有 Office 渲染引擎。译文不承诺原页数/布局不变，图片中的原文及扫描识别需核验。翻译结果提供原文对照、校样及下载；网页中的译文为只读，需要修改时下载编辑或重新发起翻译。

离线模式使用现有 `DOCUMENT_TRANSLATION_MODEL_DIR` 和 `DOCUMENT_TRANSLATION_DEVICE`，PDF OCR 强制本地，不外发内容。在线模式需要 `DOCUMENT_TOOLS_AI_MODE=auto`，复用服务器 `DOCUMENT_TOOLS_QWEN_API_KEY`、`DOCUMENT_TOOLS_QWEN_BASE_URL`、`DOCUMENT_TOOLS_QWEN_PROTOCOL` 和超时设置，新增 `DOCUMENT_TOOLS_TRANSLATION_MODEL`（默认 `qwen3-vl-plus`）。DashScope 使用多模态 generation 地址和支持纯文字输入的 VL 模型；兼容 Chat 协议使用配置的 `/chat/completions` 地址。协议参考：[千问文本生成官方文档](https://www.alibabacloud.com/help/en/model-studio/text-generation)。API 与 worker 必须同时获得这些配置并重启。

在线模式仅将需要翻译的文字和用户填写的 `glossary` 术语发送至已配置服务；PDF 扫描识别还可能发送图像区域。密钥只在服务器配置，不写入前端、任务或日志。在线批次最多 12 段，通常不超过 2400 字符；单段可独立发送至原有 6000 字符上限，不截断段内文字。截断、格式异常、空译文或数量不符时，失败批次按原顺序二分重试，单段最多再试一次；不会重复发送已经成功的批次。只接受完整 JSON 或完整 JSON 代码块，不猜测缺失译文的对应位置。网络、鉴权、限流、服务拒绝以及数字/型号变化仍明确失败，不自动切回离线；恢复失败的任务也不发布部分结果。离线批次仍为最多 30 段/6000 字符，总量上限仍为 50 万字符。能力接口的配置就绪状态不代表真实翻译精度已验证，上线应以合成样本对目标服务实测。

### 华兴批量改名

仅华兴厂区在工具栏显示“批量改名”，也可直接访问 `/tools?factory=huaxing&tool=pdf-batch-rename`。保留新版文档转换工作台及已有任务；集团和其他厂区不显示此入口，后端也不接受其改名处理请求。

- BuzzBee 行验报告：`#货号-PO+PO.pdf`，从报告正文读取货号与全部 PO，保留 PO 顺序及前导零。
- 彩星行验报告：`报告号-#货号-PO号-数量-日期.pdf`。报告号取 Batch no.，货号取 Item number 前 5 位，数量取 Quantity (Pcs)，日期按报告 DATE 转为 `年.月.日`。以报告正文为准，不从旧文件名反推。
- 先识别预览、人工复核，再下载 ZIP。识别异常可人工填写新文件名并逐项确认放行；无效 PDF、非法文件名、重名和过期预览仍被拦截。ZIP 内 PDF 内容与源文件一致，不修改本地原件。

改名使用独立 `/api/tools/pdf-rename/` 接口及本地 OCR，不进入持久任务队列，不依赖 Office、千问或文档 worker；仍受 `DOCUMENT_TOOLS_ENABLED` 开关控制。单批最多 50 份、单份 20 MB、总计 200 MB；生产需同时更新改名专属代理配置（205 MB 请求体、900 秒等待），不能只发布前端。

### 异步文档转换

API 接收上传并创建持久任务，独立 Python worker 领取任务。PostgreSQL 用短事务 `FOR UPDATE SKIP LOCKED`，SQLite 使用条件更新并限制单 worker。任务定期续租，进度和最终发布都校验当前租约；进程中断后从原件重跑，最多尝试三次。产物先写入私有尝试目录，校验大小及 SHA-256，再通过数据库条件更新一次性公开。旧尝试无法覆盖新结果。

本地在 `backend/.env` 配置；环境示例见 `backend/.env.example`。不要将真实密钥放入源码、前端、测试夹具或 Git。

```powershell
# 在 backend 目录，先完成数据库备份和迁移演练
.venv/Scripts/python.exe -m alembic -c alembic.ini upgrade head
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# 另一个终端，或使用隐藏的后台进程
.venv/Scripts/python.exe -m app.workers.document_tools
```

前端在仓库根目录运行 `npm run dev`。开发服务器忽略业务文件与转换输出目录，防止生成 HTML 预览触发整页重载。

迁移 `20260908_0103_docs` 添加四张文档表，合流迁移 `20260908_0105` 将它与已发布的纸箱 `20260908_0104` 分支汇合。它不修改已有业务记录；已有文档记录时拒绝直接降级删除。备份必须包含数据库与 `DOCUMENT_TOOLS_STORAGE_DIR` 整个持久目录，包括密码加密的 `.password-key`。只备份数据库无法恢复源文件和打开密码。

## 引擎与密钥

Word/Excel 原生结构使用 python-docx、openpyxl 和原始 OOXML；Office 渲染使用独立 LibreOffice profile。Calc 的工作表、打印和显示值由 UNO helper 处理；`DOCUMENT_TOOLS_UNO_PYTHON` 必须指向能 `import uno` 的解释器，与 API Python 可以不同。Docker 镜像使用 `/usr/bin/python3`；Windows 可用 LibreOffice 随附 Python。

PDF 使用可见页面坐标（左上角，单位 pt），规范化工作副本保留文本/矢量。原件保持不变。Rotate、CropBox、UserUnit 转换写入映射。裁切通过页面可见框完成，**不属于敏感信息涂黑/删除功能**，被裁掉的内容可能仍在 PDF 对象中。

千问 Base URL 必须来自该密钥所属地域/空间控制台。本实现支持 DashScope 多模态 generation 与 OpenAI 兼容 Chat 协议。DashScope 地址形如 `https://<控制台API-Host>/api/v1`；OpenAI 兼容地址为 `https://<控制台API-Host>/compatible-mode/v1`。不根据 key 前缀自动猜测地址，不跟随重定向转发密钥。

OCR 使用 qwen3.5-ocr，布局候选使用 qwen3-vl-plus。当前实测空间 OCR 参数上限为 16,384 tokens；截断输出拒绝落成完整表格。AI 只提供候选，不覆盖可靠原生或人工确认值。扫描/未知/冲突内容保持待核验；模型可读响应不等于业务验收。

能力接口分开报告 worker 在线、引擎已配置和已实测。实测记录按配置指纹匹配，换地址、密钥或模型后不能沿用旧验证标记。新部署必须在该实例重跑自建样本，不能直接复制开发机的 `engine-smoke.json`。

## 结果与限制

结果提供可编辑 DOCX/XLSX、PDF 校样、结构 IR、来源映射与检查报告。修订创建新任务和新版文件，保留旧版、修改人、原值、新值和原因。表格核对按窗口与虚拟行加载；问题可定位目标窗口。输出能重新打开与内容准确是不同检查；复杂图文布局、遮挡、缺失公式缓存或打印截断有明确核验项。

文件到期时间仅在部署设置保存期限时生成；默认无到期时间。到期结果的内容、下载和结构读取均返回 410。当前不自动清理源文件或历史输出；启用外部清理前必须排除运行中/排队修订及打包引用，不得仅凭文件修改时间删除。

## 验证与生产部署

真实样本与指标见 [PDF 验证](pdf-accuracy.md)、[Office 验证](office-accuracy.md)、[前端验证](frontend-qa.md) 和 [整体验证](validation.md)。测试失败与复杂文档限制必须独立报告，不能用样本通过率推断未知业务文件的准确率。

生产 compose 为 API 与独立 `document-tools-worker` 配置同一 `document-assets` 命名卷及同一后端镜像。新镜像包含 LibreOffice、CJK 字体与 python3-uno；worker 使用自己的心跳健康检查。部署前先备份数据库和共享卷，演练迁移，构建镜像，再启动 API/worker/web；检查worker心跳后实际上传自建 Word 和扫描 PDF、下载并复开结果。仅 `/health` 200 不算转换验收。这里提供部署步骤，当前开发任务没有执行生产发布。

## 合并前本地开发库的版本编号

远程纸箱迁移已使用 `20260908_0103`。早期文档工具仅在本地使用过相同编号，现将文档分支唯一标识改为 `20260908_0103_docs`，四张表的冻结定义不变；已发布纸箱迁移不改号。

生产或正常纸箱 0103/0104 数据库直接在备份和演练后 `upgrade head`。仅对于早期文档开发库：暂停 API/worker 并备份，确认四张文档表完整存在、`carton_locations`/`carton_position_entries` 不存在、纸箱新增列也不存在，且当前唯一版本标记为 `20260908_0103`，才可在事务中将该标记更正为 `20260908_0103_docs`。这只是恢复该库实际已执行的分支身份，不得对已迁移纸箱表的库套用。若同时存在两组表或结构不完整，应先核对具体迁移证据。

更正后在备份副本运行 `alembic upgrade head`，核验旧记录、库存迁移结果及外键，再对该本地库执行相同升级并重启。不能直接把版本标记写成 0105 来跳过纸箱迁移。本次 Git 合并只验证隔离测试库，没有升级现有业务数据库。
