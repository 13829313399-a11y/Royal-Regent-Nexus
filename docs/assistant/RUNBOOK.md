# 曜灵配置、启用与回退

曜灵使用独立的 `/api/assistant` 接口、服务端配置和私有附件目录。所选实例的 `capabilities` 响应提供是否启用、数据库准备情况和模型能力。历史模型连通和本地试用记录分别见[连接验证](../archive/completed/assistant/MODEL_CONNECTION.md)和[本地接入](../archive/completed/assistant/LOCAL_ACTIVATION.md)。

## 配置语义

设置项样例见 [config.example.env](config.example.env)，有效字段、默认值和限制见[后端设置](../../backend/app/core/config.py)。助手的 key、地域 base URL、模型和能力文件独立于 `DOCUMENT_TOOLS_QWEN_*`。模型 key 只在服务端读取，不能使用 `VITE_` 前缀。base URL 必须是 HTTPS 的 `/v1` 兼容地址；不自动将 OCR 地址改成聊天地址。

- `ASSISTANT_ENABLED=false`：接口返回停用，前端不显示入口。capabilities 仍须登录；不发起模型探测。
- `configuration_status=configured` 仅表示配置形状有效，**不表示联通**。只有与当前 model/base URL 匹配且带验证时间、`text` 组合的能力文件才标记 verified。
- `model-profile.example.json` 是结构示例，不能当成验证记录。实际授权测试应逐个记录 text/thinking/vision/tools 的成功组合和文档依据。模型或地域改变后旧记录失效。未验证 vision 不显示图片入口，未验证 thinking toggle 不显示开关；旧兼容字段 `web_search` 固定为 false。联网入口读取独立的 `search` 能力，需模型、地域、端点和已验证的输入/思考组合匹配后才提供选项。`supported_modes` 仅含 `off` 时仍可普通问答。 [联网能力判定](../../backend/app/services/assistant/search_capabilities.py)
- `MAX_OUTPUT_TOKENS` 空值为不覆盖供应商默认；填写时须有匹配的能力文件及正确预算字段，核实该模型是否将推理包含在输出预算内。
- `CONTEXT_CHARACTER_BUDGET` 是保守字符限额，不冒充准确 tokenizer。按完整轮次保留最近原文；当前问题过大明确拒绝。较早轮次不发送时显示范围/版本和遗漏数，完整会话仍可导出。每张图片预留 8192 字符的图像额度，不按 base64 长度计语言预算。
- `DAILY_TOKEN_BUDGET` 空值为不限制。填写后是**整个部署按 UTC 请求开始日**的预算准入保护，须同时配置已核对的输出上限。共享数据库先保守预留 `(4 × 字符预算 + 输出上限) × (工具轮数上限 + 1)`；结束后用完整实际用量结算。任何轮次未报告用量时保留预留，未做预留的历史未知用量会阻止当日继续准入，避免按零费用处理。删除对话保留非内容会计计数，不能重置预算。它不是供应商账单对账工具。
- `RETENTION_DAYS` 空值为不限期限。配置后按会话最后更新时刻计算；过期内容立即不可读取，本人访问和维护命令每批处理最多 20 个会话。默认不删除历史。
- 连接/上游空闲/整次生成上限分别是 10/180/900 秒。Nginx 助手专用空闲超时 300 秒，10 秒心跳，30 秒 lease；长流至多约 10 秒复查登录/账号/任职变动，身份边界临近时提前复核。
- 公网通过 TLS 终止时，将实际 origin 放入 `ASSISTANT_TRUSTED_ORIGINS` JSON 数组。不要使用 wildcard credentials CORS。

## 部署前检查与启用顺序

生产更新须使用[当前部署的发布与回退流程](../aliyun-docker-deploy.md)，按目标版本操作。

1. 保留对应发布镜像和私有配置，备份 PostgreSQL 与助手附件卷。在隔离恢复副本核对完整迁移图、数据和约束。
2. 按根项目构建前后端及独立子工程，核对依赖和运行镜像。
3. API 镜像实际执行 `qc_dossier_release.py start`。启用 QC dossier 时校验准备标记、版本和结构，关闭时走 `alembic upgrade head`。核对源码末端、当前数据库身份以及旧编号冲突后再启动。 [启动入口](../../backend/scripts/qc_dossier_release.py) · [助手迁移身份](MIGRATION_IDENTITY.md)
4. 核对 API 的 `assistant-assets` 持久卷与实际附件路径，沿用该部署的完整 Compose 与单 API 约束。
5. 先保持关闭，确认 schema、权限、持久化卷及 Nginx 配置。开关打开但 schema 缺失时，capabilities 显示 `schema_pending`，助手返回 503，其他业务继续服务。
6. 按另行授权的最小付费请求验证实际模型、地域及能力组合，再填写能力文件。配置变更需重启 API；前端在打开/回到前台时节制刷新 capabilities，无每 token 轮询。
7. 用合成普通员工、只读、管理员、供应商验收聊天、完整导出、取消、跨人/跨任职隔离及源业务回归，之后再扩大范围。

## 清理与诊断

从仓库根使用现有 Python 环境执行（下例为模板，不是已执行的真实库命令）：

```powershell
backend/.venv/Scripts/python.exe backend/scripts/cleanup_assistant.py --database-url '<explicit database URL>' --storage-dir '<assistant storage root>'
# 默认只计数。审核目标后才执行：
backend/.venv/Scripts/python.exe backend/scripts/cleanup_assistant.py --database-url '<explicit database URL>' --storage-dir '<assistant storage root>' --apply
# 同时应用已配置保留期：追加 --expire-retention
```

命令只重试助手 tombstone，不扫描其他业务目录，不按文件名猜测删除范围。文件占用保留 pending；清理前等活动 run 终态/lease 到期。上传先提交归属记录再写文件，崩溃后可由整个会话清理该记录；不完整文件不能发送给模型。

日志只记录请求路径模板、请求 ID、run ID、首增量秒数和整次生成秒数，不记录问题、回答、Cookie、Authorization 或附件。中间件 Server-Timing 是响应头耗时，不是完整 run 耗时。供应商 401/403 映射为 provider 错误，不触发用户退出；429 额度与可重试限流分开。

## 回退

先关闭助手并重启服务，使活动流中断并通过 lease 收敛；核对入口隐藏与其他业务健康。然后回退助手前后端版本及配置。保留该版本的会话、消息、运行、材料及反馈等助手表和附件卷，紧急回退不运行 downgrade。`0131` downgrade 遇到任何会话或 tombstone 会明确拒绝；不回滚旧 AI 退役迁移。

## 能力与验证范围

受权限和厂区限制的业务读取与帮助来源由注册表和当前能力响应确定。独立图片翻译子应用不挂载助手。持久运行、恢复订阅、使用统计和反馈按对应 schema 与开关启用，相关验收需分别记录普通问答、业务读取、跨身份拒绝以及取消/恢复。 [业务帮助覆盖](HELP_COVERAGE.md) · [持久运行](DURABLE_RUNS.md) · [运维与反馈](OPERATIONS.md) · [版本回退](ROLLBACK.md)

本地真实模型连接、历史浏览器样本和移动端/系统字号等待验范围见[当轮验收矩阵](../archive/completed/assistant/ACCEPTANCE.md)。对新实例记录模型、地域、运行版本与实测组合。依赖安装、容器构建、设备验证和真实业务验收各自以该轮记录为准。
