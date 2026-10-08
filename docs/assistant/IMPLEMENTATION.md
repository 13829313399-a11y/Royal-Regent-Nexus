# 曜灵实施与验收

## 当前闭环进度

已补齐原 9 条部分帮助总览，16 条注册说明均通过来源校验。前端完整回归 2018 项通过、17 项跳过，测试类型检查及完整构建通过；六项旧迁移断言修正后重测通过。200% 浏览器缩放、Chromium 24px 字体及真实 NVDA 连续流播报通过。助手生产依赖在全新虚拟环境中安装并通过真实 HTTP/SSE 生命周期测试。

真实 Qwen3.7-Plus 的文本、思考 auto/on/off、合成图片、工具往返和三轮上下文探测通过，共九次请求、4087 token。期间因欠费出现 403；用户充值后，真实浏览器聊天、三轮追问、图片、深度思考下的帮助工具、停止和刷新后历史恢复全部通过。七次上游请求，五个完成回合共 5124 token，停止回合用量未知。修复了移除图片后不能再次选择同一文件的问题，真实重传与助手 16 项专项通过。后端全量回归仍在运行且发现纸箱等旧模块失败；系统字体缩放、真实手机、完整生产依赖与 Docker/Linux 验收仍缺环境或未完成。不能据此宣布全部闭环。

新证据目录：`D:/RR/assistant-closure-20261008/`；当前逐项状态见 [验收矩阵](ACCEPTANCE.md)。以下已注明日期的内容保留历史结果。

## 本地接入历史

2026-10-08 已按后续指令快进同步远程 `main` 到 `6e83ee62`，保留曜灵及原有未提交改动，完成数据库备份、副本演练、正式本地迁移和启用。实际登录页面已验证曜灵入口、侧舱及本页帮助。随后按明确授权创建独立千问密钥、配置北京地域 `qwen3.7-plus`，一次真实流式文本请求通过，共262 token；其他模型能力仍待逐项验证。新增专项18项、迁移路径4项、前端39项和完整构建通过。详见 [本地接入记录](LOCAL_ACTIVATION.md)与[模型连接记录](MODEL_CONNECTION.md)。没有提交曜灵代码、推送或生产部署。下文初次交付及验收边界保留当时的历史结果，以当前连接记录为准。

## 初次开发交付结论（2026-09-29）

已完成本地功能实现、分离复审、缺陷修复及二次验证，代码留在原工作分支。**未上线；未提交或推送；未迁移真实业务库；真实千问连接未验证，没有发起付费请求。**

- 后端18项新增专项、前端16项新增专项通过；应用/测试 TypeScript 检查和完整生产构建通过。
- 临时 SQLite 与 PostgreSQL 完整迁移链升到 `20260929_0131`；修订后的增量迁移再次降/升演练，表、FK、唯一约束、索引及 SQLite integrity/foreign_key_check 通过。独立 PostgreSQL 进程竞争只有一个准入，另一进程取消生效。
- 七种宽度、普通/全屏业务页、供应商与只读账号、指针停靠/缩放、手机引导、业务模态优先、跨页保留、中文输入法、停止、历史、改名及导出已在真实应用壳中使用合成数据验证。
- 本机 Nginx 配置检查通过，33秒模拟长流在代理后逐步返回正文与心跳，未被普通API的30秒规则截断。
- 既有回归有4个基线断言失败：前端报价导入3个、后端注册flush顺序1个。已复现并定位，未通过修改无关业务或删测试掩盖，详见 [复审记录](REVIEW.md)。

完整证据目录：`test-artifacts/assistant/20260929-yaoling/`。逐项状态见 [145项验收矩阵](ACCEPTANCE.md)，说明覆盖见 [帮助清单](HELP_COVERAGE.md)，开启/回退见 [运行手册](RUNBOOK.md)。

## 实现范围与主要文件

| 范围 | 实现与路径 |
|---|---|
| 应用入口 | `src/App.vue` 根层 `AssistantHost`，同账号/epoch正常刷新保留会话，账号变化清空；无新聊天权限门槛 |
| 对话与界面 | `src/features/assistant/`、`src/stores/assistant.ts`：曜核、侧舱、专注/手机模式、安全Markdown、思考区、历史、取消、显式恢复、完整Markdown导出 |
| API与隔离 | `backend/app/api/assistant.py`、`schemas/assistant.py`、`models/assistant.py`：cookie认证、Origin检查、no-store、稳定错误DTO、本人/epoch归属 |
| 运行器 | `backend/app/services/assistant/`：独立httpx2 Chat Completions、UTF-8/SSE解析、真实阶段、工具结果、短事务、共享准入/取消/lease、断线关闭上游、未知用量不计零 |
| 数据生命周期 | `20260929_0131_nexus_assistant.py`、`backend/scripts/cleanup_assistant.py`：显式迁移、pending墓碑、附件归属/解码/规范化、清理重试、可选预算与保留期 |
| 页面说明 | `shared/assistant-help/modules/*.json`、`schema.json`；构建源码指纹检查；各页面语义锚点；注塑组件主动 reveal 且遵守 dirty/busy 限制 |
| 配置/发布边界 | `backend/app/core/config.py`、依赖清单、`nginx.prod.conf`、`docker-compose.prod.yml` 的独立助手附件卷 |
| 文档与规范 | 当前目录、`DESIGN.md`局部例外、`PROJECT_MEMORY.md`原位新增长期事实；原4处未提交记忆修改完整保留 |

精确修改路径清单保存在证据目录 `changed-files.json`；不包含临时基线副本和测试产物。

## 验证命令与结果

以下命令均实际执行；日志位于证据目录。

| 验证 | 结果 | 日志/证据 |
|---|---|---|
| `npm run typecheck:app` | 通过 | `typecheck-app.log` |
| `npm run typecheck:test` | 通过 | `typecheck-test.log` |
| `npm run test:unit -- src/features/assistant/__tests__` | 5文件、16项通过 | `frontend-final.log` |
| `npm run test:unit` | 首轮1766通过、16失败、17跳过；其中13个超时项复跑通过，剩余3个基线断言失败 | `frontend-regression.log` |
| `npm run test:unit -- --maxWorkers=2` 加四个失败文件 | 208通过、3个基线断言失败 | `frontend-failures-retest.log` |
| `npm run build` | 通过，保留并通过 `build:image-translation` | `build-final.log` |
| `node scripts/check-assistant-help.mjs` | 16条，9条明确partial，源指纹/路由/字段问题0 | `help-golden.log` 与构建日志 |
| `python -m pytest` 加三个新助手测试文件 | 18项通过 | `backend-release-candidate.log` |
| 旧AI退役、Nginx、身份生命周期、文档Qwen专项 | 20项通过 | `backend-regression-core.log` |
| work-center 与首批运行器控制测试 | 14项通过（含12项既有work-center） | `backend-live-workcenter.log` |
| 完整 `test_auth_api.py` | 58通过、1个基线断言失败 | `backend-auth-regression.log` |
| 未修改HEAD源码副本复现认证失败 | 相同断言失败，注册响应200 | `auth-baseline-repro.log` |
| SQLite / PostgreSQL Alembic升级及增量重演 | 通过 | `*-migration.log`、`*-migration-final.log`、`database-evidence.json` |
| PostgreSQL独立进程准入与取消 | 通过 | `postgres-acceptance.log`、`database-evidence.json` |
| Nginx `-t` 与代理33秒流 | 通过 | `nginx-check.log`、`proxy-evidence.json` |
| Compose YAML/附件持久卷结构 | 通过；未启动Docker/部署 | 静态解析与 `RUNBOOK.md` |
| Browser acceptance / supplement / lifecycle / states / free-factory / copy-style | 通过、pageerror空；失败/未配置态明确使用合成HTTP快照 | 同名JSON与 `visual/` |
| 门户未遮挡区域前后像素对比 | 750500像素无差异（阈值2） | `style-pixel-evidence.json` |
| `git diff --check` | 通过；HEAD与分支保持不变 | `baseline.md` |

浏览器通过独立本地 Chromium 运行。内置浏览器工具两次返回 request-header policy 加载失败，已按测试技能回退；没有把工具故障记作产品失败。截图均为合成账户与隔离数据库，不包含生产私聊或真实订单。

## 截图索引

- 宽度：`visual/width-320.png`、`390`、`768`、`1024`、`1280`、`1536`、`1920`。
- 阅读：`long-answer.png`、`focus-final.png`、`cancelled.png`、`reading-new-content.png`、`mobile-code-table.png`。
- 共存：`surface-work-center.png`、`surface-injection.png`、`surface-three-d.png`、`surface-internal-quote.png`、`surface-identity.png`、`surface-qc.png`、`qa-supplier.png`。
- 行为：`injection-reveal.png`、`mobile-guide.png`、`business-modal-priority.png`、`spa-session-preserved.png`、`free-chat-factory-switch.png`、`panel-360.png`、`panel-600.png`。
- 未配置/失败：`unconfigured-fixture.png`、`provider-error-fixture.png`（合成前端HTTP边界；实际后端错误分类另有专项）。

## 验收边界

1. 真实千问账户、地域、模型权限、回答语义及thinking/vision/tools组合尚未联通验证。联网没有适配器和按钮。现有验证证明协议与本地程序行为，不证明供应商效果。
2. 九条帮助为部分覆盖；未知字段、未注册区域或源码变化明确提示待核对。没有真实业务数据读取/写入工具，不将说明冒充实时数据。
3. 真实200%桌面缩放/系统大字体、手机软键盘/安全区/旋转、屏幕阅读器及Docker干净镜像安装仍未运行；不能用窄屏截图代替这些验证。
4. PostgreSQL、Nginx和浏览器测试都是本机隔离环境，不能替代生产Linux/容器、设备或正式业务验收。副本数据库和证据保留；没有修改真实业务库。

## 开发基线与实施计划

基线：`19332e167e0b990fb0900c868ba0620204f9bd26`，分支 `fix/three-d-telemetry-performance-20260929`。已有 `PROJECT_MEMORY.md` 修改与 `test-artifacts/` 保留。迁移图实际只有 `20260929_0130` 一个 head。

- P0：核实认证、根宿主、数据库初始化、帮助来源、依赖与代理。
- P1：四张独立表、显式增量迁移、数据库原子准入、取消/lease、协议解析、本人接口。
- P2：局部 SVG 曜核、翡翠侧舱、阅读态、历史与完整导出、键盘/窄屏。
- P3：服务端帮助注册、代码指纹、语义锚点与只读引导。
- P4：保守能力文件、明确连接状态、隔离模拟供应商、失败与恢复。
- P5：专项与既有回归、浏览器截图、分离复审、修复、验收矩阵与运行手册。

视觉以提供的开发规格为准：432px 白色阅读侧舱，深翡翠舱头，香槟金轨道 SVG；所有图形用本地 SVG/CSS，不依赖生成位图。保持现有 Vue / Pinia / Reka 技术栈。

开发与测试均使用隔离合成数据。没有授权真实模型付费探测、真实库迁移、部署或 Git 提交。

## 协议依据

实施时核对了阿里云 [Chat Completions 兼容接口](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope)、[流式输出](https://help.aliyun.com/zh/model-studio/stream) 与 [思考模式](https://help.aliyun.com/zh/model-studio/deep-thinking)。地域地址由部署配置给出；不硬编码某个候选模型。模型权限和组合能力仍需真实连接验收。
