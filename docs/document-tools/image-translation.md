# 图片 / PDF 原位翻译

公共工具栏通过 `/image-translation/?factory=<id>` 打开独立 React 页面。rr 模式上传文件到服务器，员工无需安装模型、填写 API Key 或使用 OPFS/WebGPU。原生 PDF 优先提取文字坐标，图片和 PDF 内的大幅嵌图复用 Shinobu 的检测/OCR；服务器专用 documentTypeset 做保守原位回填，不使用漫画气泡合并、扩框排版或生成式擦图。Node 24 私有子进程负责图片识别/合成，Python make_translator 负责离线或已配置的在线翻译。独立浏览器版仍采用原流水线。

## 处理及数据边界

- 新增 image_translate，接受单帧 PNG/JPEG/WebP 和 PDF，使用现有上传、检查、独立 worker、个人任务、撤回、重试与 artifact 下载接口，不新增数据表或数据库迁移。
- 原图、任务、页图、译文 PDF 和历史均按主站账号隔离。厂区仅为上下文；模型为服务器共用资源。旧浏览器历史没有自动迁移到服务器。
- 登录和强制改密沿用主站；会话切换时卸载页面并回到登录流程。普通 HTTP 可使用此服务器页面，不再要求浏览器安全上下文；登录传输安全仍遵循主站部署要求。
- 支持英文到简体中文、中文到英文。离线模式不外发内容；在线模式把 OCR 后的文字及术语发送至配置的翻译服务，图片模型在服务器运行。密钥仅由 Python 后台读取，不进入浏览器、任务参数或 Node 协议。
- 在线翻译采用最多 12 段、通常不超过 2400 字符的小批次（单段沿用 6000 字符上限，不截断段内文字）。返回截断、格式错误、数量不符或空译文时，仅将失败批次二分重试；单段最多再试一次。已成功的批次不会因后续拆分而重复请求。只接受完整 JSON 或完整 JSON 代码块，不补齐、拼凑缺失译文。网络、鉴权、限流和服务拒绝不触发拆分；取消和原有处理时限仍有效。数字与型号校验保持严格，最终失败时显示具体原因，整份任务不发布不完整结果。此分批逻辑复用公共 Word/PDF/Excel 在线翻译引擎。
- 数字、尺寸、型号、材料代码（如 BR）、十六进制色值、PANTONE 色号和已知品牌标志保留原像素，不进入翻译；原生 PDF 按词隔离。OCR 混排只在可观测字间空隙处分词，逐段重识别后文本一致才采用。裁剪说明（Cut + 数量）可接受置信度至少 0.97 的逐词文字修正，但数字和代码必须与原识别一致；短横分隔符由原像素形状核实并保留。跨表格竖线的 OCR 候选分格重识别。普通彩色标题和图片说明参与翻译，回填沿用可辨别的原前景色。文档补检增加色度笔画分析，支持黑底红字及字母相连的粗体短词；仅对低置信度普通文字和漏识别的彩色笔画做高对比度重读，最多 96 个区域，不重复读取清晰文字或中性图形。逐词识别允许有限留白，回填仍使用原词框。可识别的方向箭头不阻挡相邻文字，箭头恢复原像素。编号下的产品名称、低置信度、区域冲突、复杂背景或无法安全排入的文字保留原文。
- 回填范围以原文字框为基准，有限扩边受邻区约束；擦除仅限原字形，彩色文字按测得的前景笔画颜色限制清除，保留深色裁片的弧边及邻近图形。横线/下划线及受保护框恢复原像素。中文采用普通无衬线字重，同列标签尽量统一字号，译文过长时适度缩小，低于可读阈值则保留。Windows 使用雅黑，Linux 使用已安装的 Noto CJK，Source Han 字体为后备。
- 每页输出 PNG。图片输入导出无损页图 PDF；PDF 输入在规范化原页面对象上叠加无损差分图层，保留原矢量、图片、文字层、数字及页面比例。差分遮盖向外补足 3 个页图像素，并保留透明位置的真实背景颜色，避免不同阅读器或缩放比例下露出英文轮廓、出现黑边；新增遮盖避开受保护数字和横竖线，线条仅留较窄的重采样余量，避免下划线上方漏出英文尾部。译文为图层，底层英文仍可提取；不是文字编辑或安全脱敏。交互注释沿用 normalize_pdf 的现有限制。
- 页面提供放大预览和逐项核对，显示回填/保留理由并定位对应原文；私有 translation_review JSON 不包含服务器路径。专业长句仍受翻译模型质量限制，保留不等于翻译完成。
- 框选补翻从原图截取区域，只将本次确实完成回填的区域合入父版结果；未重译部分沿用父版。生成不可变新版本，旧版留在历史；核对记录继承未替换的内容。当前队列替换为新版本，汇总 PDF 不重复收集旧版。汇总沿用 /packages 的 format=pdf，按所选结果顺序合并；默认 ZIP 行为保留。
- 每个尝试拥有独立临时目录，沿用租约校验和最终数据库 CAS。撤回或租约丢失时终止并回收 Node；Node 只通过私有 stdio 请求翻译，不监听网络端口。rr 的 ONNX CPU 会话使用可用逻辑 CPU 数的一半，至少 1、最多 4 个算子内线程，算子间线程为 1；独立 Shinobu 的默认设置不变。实际速度仍需按生产 CPU 配额、worker 并发和文件内容验收。
- 上传字节和页数沿用文档工具限制；单图默认最多 2400 万像素、最长边 12000。PDF 按最多 2 倍点尺寸、4096 最长边渲染，整份翻译默认最多 8000 万像素。超过总量时选较少页码分批处理。默认任务处理时限 1800 秒。翻译等待期间仍检查取消/超时并回收 Node；已经进入本地翻译模型或 HTTP 的单次调用会自行结束，迟到结果不发布。Python/原生单次 PDF 渲染完成前的取消有延迟。
- 原件、结果与删除行为沿用公共文档工具：删除记录不是物理擦除；默认无到期时间，设置保存期限时由读取接口强制执行。

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

    backend/.venv/Scripts/python.exe -m pytest backend/tests/test_image_document_layout.py backend/tests/test_image_translation.py backend/tests/test_document_tools_jobs.py backend/tests/test_document_tools_translation.py backend/tests/test_nginx_prod_config.py -q
    npm run test:unit -- src/views/__tests__/toolCenter.spec.ts src/features/document-tools/TaskActions.spec.ts
    npm run typecheck:test
    npm run build

backend/scripts/smoke_image_translation.py --output <目录> 使用合成图片、真实本地图片模型和真实离线翻译。serve_image_translation_smoke.py 与 shinobu-web/scripts/rr-server-smoke.mjs 提供独立数据库/账号的浏览器验证；测试服务仅绑定 127.0.0.1，不可部署到生产。RR_IMAGE_QA_DIR 必须指向专用测试目录，端口 8001。

真实资料回归使用用户提供的英文规格 PDF、DECO 配色图及毛绒玩具纸样 PDF；运行 `benchmark_image_documents.py --image <文件> --pdf <文件> --output <私有目录>`。纸样回归应包含黑色裁片内的红字、带裁剪数量和材料代码的说明、领圈与方向箭头。导出回归覆盖小数页面尺寸、白色及彩色底稿、多个缩放比例，以及遮盖范围附近的数字和线条；真实 PDF 还应使用与生成预览不同的阅读器复核。原件和衍生产物不提交 Git。确定性术语表仅用于图片工具离线翻译，包含裁片与材料语义，并允许完整字母一致的 OCR 词内空格归一；不猜测缺失字母。每次任务复用重复文本结果，在线自定义术语继续交在线服务处理。当前离线长句仍有语义错误，不能把版式/数字保护验证当作专业译文准确率验证；本地未配置在线服务。生产员工会话和并发负载仍需部署验收；当前生产镜像与发布状态以 PROJECT_MEMORY.md 的部署事实为准。
