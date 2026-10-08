# 曜灵本地接入记录

## 当前结果

2026-10-08，按用户指令将 `D:/RR/royal-regent-nexus` 快进同步至远程 `origin/main` 的 `6e83ee62cefa22862b491474e27ee5fb714fd5cd`，随后启用当前本地环境。分支仍为 `fix/three-d-telemetry-performance-20260929`，曜灵及原有工作区改动仍未提交，没有推送或部署生产。

- 访问 `http://localhost:5173/`，登录后点击页面右侧“曜灵”，或使用 `Alt+J`。
- 后端 `http://127.0.0.1:8000/health` 返回正常，13个助手路由已加载。
- 本地开关开启，数据库状态 ready；随后按明确授权创建千问专用Key并配置北京地域 `qwen3.7-plus`，一次真实流式文本请求通过。运行服务已由用户重启，配置状态为 configured/verified，浏览器需重新登录。详见[模型连接记录](MODEL_CONNECTION.md)。
- 用户自行登录后，已在真实本地页面验证入口、展开侧舱、“讲解本页”和“系统门户”说明；没有框架错误覆盖层，控制台无 error/warn。截图 `D:/RR/assistant-local-integration-20261008/local-enabled.jpg`。
- Chrome 扩展连接返回 request-header policy 加载失败；改用内置浏览器完成上述验证，未复制浏览器 Cookie 或索取密码。

## 主线同步与兼容处理

同步前保存95个源码文件的压缩备份和SHA-256清单，并使用限定路径的 stash 保存改动。快进引入77个上游提交后恢复改动，保留全部测试产物及本地配置。恢复时处理6处冲突：App.vue 同时保留 DeploymentNotice 与 AssistantHost；纸箱采购、供应商、箱唛及报价页面保留最新布局和曜灵锚点；测试类型检查同时覆盖反馈与助手。

原助手迁移 `20260929_0131` 不改写。新增空合并迁移 `20261008_0140`，合并助手分支与主线 `20261006_0139`。迁移测试移除过时的 `0136` head 假定，仍要求单一 head、保留历史分支及原有数据，并补测已有助手会话的保留。

源码备份及本轮验证证据：`D:/RR/assistant-local-integration-20261008/`。保留恢复用 stash `5ca3eedd249db3e13631ba0b6906c62774eb7e42`，没有清理其他 stash。

## 数据与配置

实际数据库：`D:/RR/royal-regent-nexus/backend/data/royal_regent_nexus.db`，从 `20260928_0126` 升级到 `20261008_0140`。该路径与其他工作区的数据库相互独立。

停写状态下使用 SQLite backup API 保存副本，先演练，再比较原库与基线并升级。副本和原库都通过 integrity_check、foreign_key_check。320张原有业务/系统表、23,972行原有数据在原有字段上的内容指纹一致。上游模块反馈迁移新增一个权限目录项 `module_feedback:manage`；该目录新增有明确记录，不属于账号授权变更。新建21张表含4张助手表；未删除原表或原记录。

备份目录：`backend/data/maintenance-backups/assistant-local-20261008/`（被Git忽略）：

- `before.db`：迁移前数据库，SHA-256 `27449df258fb852af75ceaf0da0f8371d50e92bf66376739e6127f8b75fcaf09`。
- `rehearsal.db`：已升级的演练副本。
- `backend.env.before`：本地配置备份，包含私有配置，不应上传或输出。

初次启用仅修改 `ASSISTANT_ENABLED=true` 和助手可信来源（`http://localhost:5173`、`http://127.0.0.1:5173`）。后续模型接入补齐独立Key、地域地址、模型和能力文件路径；非助手配置逐行核对保留。没有复用OCR密钥。正常启动命令会继续加载此配置，无须每次重新开关。

## 本轮验证

| 检查 | 结果 | 证据 |
|---|---|---|
| 助手API、生命周期与帮助事实 | 18通过 | backend-tests.log |
| 四种迁移起点、重复升级与旧行保留 | 4通过 | migration-tests.log |
| 测试TypeScript | 通过 | typecheck-test.log |
| 助手、模块反馈与部署通知前端 | 7文件39项通过 | frontend-tests.log |
| 完整生产构建，含图片翻译 | 通过 | build.log |
| 16条帮助源指纹 | 0问题，9条仍为partial | help-reviewed.json及构建日志 |
| 本地迁移演练与原库数据核对 | 通过 | rehearsal-passed.json、source-migration-passed.json |
| 后端健康、前端HTTP、未登录隔离 | 200 / 200 / 401 | runtime-http.json |
| 用户实际登录、侧舱与本页帮助 | 通过，模型待配置 | local-enabled.jpg、api.stderr.log |

以上初次启用验证没有重跑全部业务测试，也没有将9月29日的全量基线失败改记通过。后续模型接入执行了一次用户明确授权的真实请求，见连接记录；没有执行生产部署、Docker镜像验收或手机实机验收。

## 启动与回退

从项目根启动后端：`backend/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000`。前端：`npm run dev`。已有同端口进程时不要重复启动；本轮服务已在后台运行。

关闭功能时，将本地 `ASSISTANT_ENABLED=false` 并重启后端，再刷新前端。保留助手表、主线新增表和附件，常规回退不要降级数据库。数据库备份恢复只用于受控故障恢复；恢复前停止写入并另存当前库，不能覆盖启用后产生的新业务数据。

真实千问配置已完成。以后更换Key、地域或模型时，在服务端更新独立的 `ASSISTANT_QWEN_API_KEY`、`ASSISTANT_QWEN_BASE_URL` 和 `ASSISTANT_MODEL`，重启并重新验证匹配的能力记录。不要把密钥提交到Git或放入VITE环境变量。
