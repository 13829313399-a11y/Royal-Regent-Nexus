# 给 rr 工作区的项目读取说明

这里是 ShinobuTranslator 本地网页版的源码快照，复制自 D:\mimo\shinobu-web。
用途：作为 Royal Regent Nexus 公共工具栏“图片 / PDF 翻译”的独立前端子项目，同时保留独立运行方式。
这是独立副本，不会自动与原项目同步。原项目仍保留在原路径，本地页面仍使用 http://127.0.0.1:8774/。

## 从哪里开始读

1. README_FOR_RR.md：本说明与最新改动。
2. CLAUDE.md：原项目开发约定。与 rr/AGENTS.md 一起阅读，用户当前指令优先。
3. apps/web/src/App.tsx：React 网页入口、图片队列、预览、补翻和 PDF 导出按钮。
4. apps/web/src/features/export/resultsPdf.ts：按队列顺序汇总结果为 PDF，保留比例，读取保存的历史结果和补翻合并图。
5. apps/web/src/features/history/HistoryView.tsx：历史批次及 PDF 导出入口。
6. apps/web/src/features/workbench/：队列、恢复状态、历史结果引用。
7. apps/web/src/features/patch/regionPatch.ts：框选补翻、结果合并、OPFS 存储。
8. packages/image-pipeline/src/：文字检测、OCR、去字与排版流水线。
9. tests/web/resultsPdf.test.ts：PDF 页序、图片比例、历史恢复、补翻排除与错误处理验证。

## 当前功能

- 图片/PDF 输入；rr 对 PDF 优先采用原生文字坐标，扫描内容才做 OCR，保留原页面并以局部译文图层覆盖。
- rr 主站模式由服务器执行保守原位回填，保护数字/型号/色号、表格线和图片，提供放大与逐项核对；文字翻译复用主站离线模型或管理员配置的在线服务。单独运行时仍采用原浏览器流水线。
- 局部框选补翻、合并补翻结果。
- 图片队列及历史记录均有“汇总导出 PDF”：已完成结果一图一页，优先保存的合并图，排除有补翻记录的小裁图。
- 简体/繁体界面、导出进度及失败提示。

## 读取副本与 rr 的边界

原项目是 React/TypeScript 的 npm workspaces；rr 主站是 Vue。公共工具栏通过同站点 `/image-translation/` 打开独立翻译页面，两个工程分别安装依赖。rr 构建使用 `apps/web/src/server/` 页面，复用主站登录、上传、任务队列、账号隔离与结果下载。模型统一安装在服务器，员工不用导入模型或填写密钥。`server/runner.ts` 在私有 Node 子进程中复用原识别模块，`server/documentTypeset.ts` 是工程资料专用回填器；Python 负责原生 PDF 坐标、数字隔离、集中翻译、取消、发布和 PDF 汇总。
本副本包含源码、配置、文档、测试及依赖锁文件；排除了 node_modules、构建产物、临时文件、模型权重、public/ort 运行时、演示视频和部分大型基准数据。
原始复制时的排除清单和逐文件 SHA-256 见 SOURCE_SNAPSHOT.json；这些哈希记录来源快照，不代表后续集成修改后的文件。
浏览器历史、用户图片、API Key、已安装模型和未导出的结果不属于源码文件，不在本副本中。
图片模型由管理员从已有合法来源校验并安装到 rr 的 `backend/models/image-translation/` 私有目录；不公开分发，不打入网页或镜像。rr 网页不包含浏览器推理运行库，历史与补翻结果在服务器按账号保存；旧浏览器历史未自动迁移。详细接入与部署要求见 `../docs/document-tools/image-translation.md`。

## 如需单独运行或修改此副本

使用 Node.js 24，在本子目录执行（不要在 rr 根目录安装本项目依赖）：

    npm ci
    npm run build:web
    node serve-local.cjs 8774

原服务正在使用 8774 时应停止旧服务或另选端口。换端口会使用另一套浏览器站点存储。
serve-local.cjs 提供构建后的 apps/web/dist；源码修改后需重新 npm run build:web。
单独运行浏览器推理/基准测试前需要补齐排除的运行资源或测试数据。接入 rr 时，在 rr 根目录执行 `npm run build:image-translation`，再启动 API 与文档 worker，从主站公共工具栏打开。rr 服务器模式支持普通 HTTP，不再依赖浏览器安全上下文；单独运行的浏览器模式仍需 HTTPS 或 localhost。

## 复制前已经完成的验证

原项目新增 PDF 功能通过 67 项相关测试、网页及测试类型检查、构建与依赖许可证检查；
浏览器实际下载验证了工作台和历史页导出，PDF 中文显示、横竖比例、页序及合并内容均已检查。
这些是复制前原项目的验证结果，不能代替 rr 集成后的验证。
