# 图片 / PDF 原位翻译

公共工具栏通过 `/image-translation/?factory=<id>` 打开独立 React 页面。`image_translate` 与公共工具的 `pdf_translate` 共用 `document-layout-v2`：先完整读取、翻译和复核内容，再尝试原位回填。内容完整性与版式回填独立记录；保留原图不代表已完成翻译。独立 Shinobu 浏览器模式继续使用自己的流水线。

## 内容与版式契约

- 支持 PNG/JPEG/WebP/PDF、中英互译及 PDF 选页。沿用个人文件、独立 worker、租约、撤回、重试、不可变版本和下载接口，无数据库迁移；厂区上下文不扩大文件权限。
- 在线模式将所选页的完整页图、OCR 候选、文字及术语发送至已配置的文档翻译模型。先分开整页逐字读取和覆盖复核，再用整份文档的上下文辨认名称和术语、分批翻译、独立校对语义。较长且字面相同的说明或独立分句共享译文；短标签按页和所属区域区分，不能给较短的原文补上不存在的后半句。MiMo 读取、覆盖复核和初译关闭深度思考，文档上下文和语义复核开启有上限的深度思考。PDF/图片不依赖另配 Qwen OCR。私钥仅由 Python 读取，不进浏览器、任务参数、Node 协议或日志。使用内部资料前需取得外发授权；界面显示发送范围。
- 在线原文识别按私有源文件、页图、原生文字层、提示版本及模型连接绑定，24 小时内可复用。缓存只存原文和识别证据，不存译文或密钥；重新翻译仍进行语义检查。勾选“重新识别原文”时不读缓存；离线不会使用在线识别缓存。
- 本地 RapidOCR 和 PDF 原生文字提供独立物理坐标。模型通过候选 ID 关联语义段落、列和表格单元格；模型估计的矩形不能直接用于回填。合并行仅在实际像素留白处分开；无法定位的真实内容进入完整译文，不猜坐标覆盖图稿。
- 独立 OCR 与整页读取不一致的候选会在带编号的真实裁图中复核；箭头、缝线等图形噪声不直接当文字加入全文。未获确认的候选仍列为需核对。PDF 文字层与视觉读取数字冲突时列为不确定，不能用一个来源掩盖另一个。
- 普通标题和含数字、型号、色号的句子仍参与翻译。正式标识、色号、表格符号、实际品牌名及 URL 可原样保留；说明仍翻译，描述性款名尽量同时给译义与原拼写。数量、小数、分数及型号严格比较；未译、数字变化、否定丢失等触发逐块修复，仍不可信的译文不冒充完成或导出串页内容。
- `document_pipeline.py` 和 `general_translation.py` 保存内容、证据、模型调用和核对状态；`documentLayout.ts` 只负责排版。回填限定在物理文字区域及有限留白，清理字形并保留原图稿/横竖线及先前译文；字号保持可读，对比不足时调整颜色。遇到选框、冲突、复杂底图、图稿碰撞、位置不明或空间不足时保留原区域；对照输出标明已识别的选框状态、表格归属及可由物理位置确认的并排图注列。
- 每项保留原文、完整译文和状态。始终生成 `complete_text`（UTF-8 TXT）及 `complete_pdf`（可读原译对照 PDF）；未能原位回填的译文仍可查看/下载，不因排不下而丢弃。存在未确认内容或未回填译文时，主 PDF 追加完整对照。完整对照 PDF 为分页栅格文字，复制文字请使用 TXT。`pdf_translate` 额外输出按阅读顺序的可编辑 DOCX，不宣称 Word 复现原版式。
- `content_status=reviewed|needs_review` 与 `layout_status=applied|partial` 分开报告。reviewed 只表示实际模型与规则检查通过，不是人工语义认证。未知原文、术语或不标准的描述不能因生成文件成功而宣称准确。页面同时提供“原位结果”“完整译文”及逐项来源/状态；需核对提示不藏在折叠列表内。
- 离线模式不外发页图或文字，保留本地 OCR 内容并用既有中英模型翻译；没有整页视觉/语义复核，始终提示核对。长句、低清/旋转/艺术字、歧义命名仍有识别或语义风险，在线不可用时不会自动降级离线。
- 图片输出无损页图 PDF；PDF 输出保留原规范化页面对象并叠加无损差分图层，原英文文字层仍可提取，不属于文字编辑或安全脱敏。差分边缘补足并避让受保护值和规则线；交互注释沿用规范化限制。
- 框选补翻扩展到相交的完整文字块，避免只替换半段而遗失其余内容。只合入确实回填的像素；内容合并核对文本归属，保留未替换原文、其余页和原有覆盖风险。生成新版本，原件和历史不修改。汇总按所选当前结果顺序合并 PDF。
- 超时、取消或租约丢失会丢弃迟到结果并回收 Node。远程调用和本地 OCR 在可中断的等待线程执行；底层正在运行的单次调用仍可能自行结束。单次原生 PDF 渲染仍可能延迟取消。连接错误和 HTTP 429/502/503/504 最多原批重试一次。鉴权等未恢复的服务错误明确失败。单页识别结构错误时最多重读一次，仍不可用时保留原页和已有候选并标为需核对，该页降级识别不缓存。分批翻译只采用可按唯一 ID 对应的回复，缺项单独重试；未完成复核的语义批次可拆半再核对一次。仍未确认的内容不覆盖原图。不从截断或结构错误的回复拼凑 JSON。
- 保留原有上传字节/页数限制。图片处理副本默认最多2400万像素；超出处理上限或12000像素边长时等比缩小到最长4096并提示尺寸，原字节不改；安全解码最多8000万像素/65535边长。PDF 按最多2倍点尺寸、4096最长边渲染，整份最多8000万像素、默认1800秒；大文件需选页分批。
- 原件/结果按账号隔离，删除记录不是物理擦除；默认无到期，配置期限时由读取接口执行。历史任务沿用其旧流水线证据，不会自动升级成完整翻译结果。

## 本地构建与模型安装

在 shinobu-web 中执行 npm ci，然后在 rr 根目录运行 npm run build。仅重建翻译网页及 Node 引擎使用 npm run build:image-translation。

管理员从已有合法模型目录安装（逐项核验固定 SHA-256 和长度）：

    backend/.venv/Scripts/python.exe backend/scripts/install_image_translation_models.py --source-dir D:/mimo/shinobu-web/public/models

本地尚未安装主站离线翻译模型时：

    backend/.venv/Scripts/python.exe backend/scripts/install_document_translation_models.py --model-dir backend/models/document-translation --download-dir .tmp/document-translation-downloads

分别运行主站前端、API 及独立文档 worker：

    npm run dev
    backend/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
    cd backend
    .venv/Scripts/python.exe -m app.workers.document_tools

五个图片模型约 196 MiB，安装在忽略 Git 的 backend/models/image-translation/。模型不进入静态站点或镜像；保留原项目的模型发布限制。管理员需要事先获取有权使用的固定版本资产。构建生成 Node bundle 和解压后的中英文字体；shinobu-web/server/runtime/package-lock.json 锁定实际部署的 canvas 与 ONNX Node 依赖。

配置入口：IMAGE_TRANSLATION_MODEL_DIR、IMAGE_TRANSLATION_RUNNER、IMAGE_TRANSLATION_NODE、IMAGE_TRANSLATION_TIMEOUT_SECONDS、IMAGE_TRANSLATION_MAX_PIXELS、IMAGE_TRANSLATION_MAX_TOTAL_PIXELS。API 与 worker 必须使用一致配置。能力接口检查模型哈希、字体和原生运行依赖；这属于就绪检查，不代表推理质量验收。

## 生产部署

Dockerfile.backend 包含 Node 24、canvas/ONNX CPU 原生依赖与流水线 bundle，API 与 worker 使用相同镜像。Compose 的 image-translation-models 命名卷在正常运行时只读挂载；仅管理员安装时临时以可写方式挂载到安装容器。

服务器必须保留现有 .deployment-prod-release.yml 的镜像固定配置，先将其中 API/worker/web 更新为本次实际构建的镜像。模型安装示意（在服务器项目目录，环境变量为服务器上的来源目录）：

    export IMAGE_MODEL_IMPORT_DIR=/srv/rr/private-image-models
    docker compose -f docker-compose.prod.yml -f .deployment-prod-release.yml -f docker-compose.image-model-install.yml run --rm --no-deps api python scripts/install_image_translation_models.py --source-dir /model-import
    docker compose -f docker-compose.prod.yml -f .deployment-prod-release.yml up -d api document-tools-worker web

模型安装 override 仅用于一次性命令，不加入普通启动。站点无模型下载接口，不把服务器私有模型目录挂到 web。备份包括数据库、document-assets 和模型卷。CPU 运行会消耗服务器资源，部署时需根据机器内存和真实文件调整文档 worker 并发；当前没有生产压测数据。

## 验证与当前限制

    backend/.venv/Scripts/python.exe -m pytest backend/tests/test_general_translation.py backend/tests/test_document_pipeline.py backend/tests/test_image_document_layout.py backend/tests/test_image_translation.py backend/tests/test_document_tools_jobs.py backend/tests/test_document_tools_translation.py -q
    npm run test:unit -- src/views/__tests__/toolCenter.spec.ts src/features/document-tools/TaskActions.spec.ts
    npm run typecheck:test
    npm run build

backend/scripts/smoke_image_translation.py --output <目录> 使用合成图片、真实本地图片模型和真实离线翻译。serve_image_translation_smoke.py 与 shinobu-web/scripts/rr-server-smoke.mjs 提供独立数据库/账号的浏览器验证；测试服务仅绑定 127.0.0.1，不可部署到生产。RR_IMAGE_QA_DIR 必须指向专用测试目录，端口 8001。

通用真实资料回归使用 `backend/scripts/benchmark_general_translation.py --manifest <私有清单> --output <私有目录> --engine online`。清单项包含 name/path/pages 和可选 direction/glossary。执行成功、源件哈希不变与语义/视觉验收分别记录，不能以状态或可打开文件替代准确率。测试资料包括服装技术图、18页规格表、17页毛绒纸样/工艺、大幅设计 PDF、刺绣材料表和历史 DECO 源页渲染；后者不能证明原 JPEG 元数据兼容。中译英、模糊旋转扫描、异常文字层与生产负载仍需要对应真实资料验收。原件和衍生结果不提交 Git。当前真实测试报告见私有 outputs/general-translation-20261104/qa/；实际已验证范围以报告为准。

前端通过项目 visual-qa-loop 使用 Chrome DevTools MCP。本次浏览器配置目录被占用，实际路由、桌面/窄屏、键盘与下载交互尚未完成浏览器复核；构建和组件测试不能替代它。本地翻译使用已绑定的 MiMo-V2.6-Flash，生产镜像/配置不因此变更，生产部署及并发验收另行授权。
