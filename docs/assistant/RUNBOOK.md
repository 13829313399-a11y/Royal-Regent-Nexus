# 曜灵配置、启用与回退

代码默认关闭；当前 `D:/RR/royal-regent-nexus` 本地环境已按用户要求启用，数据库已备份并迁移至 `20261008_0140`。前端 `http://localhost:5173/`、后端 `http://127.0.0.1:8000`。北京地域 `qwen3.7-plus` 已通过独立专用密钥的一次授权真实流式请求，九项合成探测已验证文本、图片、思考开关、工具往返和多轮；期间账户欠费导致 403，用户充值后已用原配置完成真实浏览器多轮、图片、思考加帮助工具、停止和历史恢复，连接已恢复。没有部署生产。模型配置与验证范围见 [连接记录](MODEL_CONNECTION.md)，启用与回退见 [本地接入记录](LOCAL_ACTIVATION.md)。

## 配置语义

完整样例见 `config.example.env`。助手的 key、地域 base URL、模型和能力文件独立于 `DOCUMENT_TOOLS_QWEN_*`。模型 key 只在服务端读取，不能使用 `VITE_` 前缀。base URL 必须是 HTTPS 的 `/v1` 兼容地址；不自动将 OCR 地址改成聊天地址。

- `ASSISTANT_ENABLED=false`：接口返回停用，前端不显示入口。capabilities 仍须登录；不发起模型探测。
- `configuration_status=configured` 仅表示配置形状有效，**不表示联通**。只有与当前 model/base URL 匹配且带验证时间、`text` 组合的能力文件才标记 verified。
- `model-profile.example.json` 是结构示例，不能当成验证记录。实际授权测试应逐个记录 text/thinking/vision/tools 的成功组合和文档依据。模型或地域改变后旧记录失效。未验证 vision 不显示图片入口，未验证 thinking toggle 不显示开关；联网未实现，始终关闭。
- `MAX_OUTPUT_TOKENS` 空值为不覆盖供应商默认；填写时须有匹配的能力文件及正确预算字段，核实该模型是否将推理包含在输出预算内。
- `CONTEXT_CHARACTER_BUDGET` 是保守字符限额，不冒充准确 tokenizer。按完整轮次保留最近原文；当前问题过大明确拒绝。较早轮次不发送时显示范围/版本和遗漏数，完整会话仍可导出。每张图片预留 8192 字符的图像额度，不按 base64 长度计语言预算。
- `DAILY_TOKEN_BUDGET` 空值为不限制。填写后是**整个部署按 UTC 请求开始日**的预算准入保护，须同时配置已核对的输出上限。共享数据库先保守预留 `(4 × 字符预算 + 输出上限) × (工具轮数上限 + 1)`；结束后用完整实际用量结算。任何轮次未报告用量时保留预留，未做预留的历史未知用量会阻止当日继续准入，避免按零费用处理。删除对话保留非内容会计计数，不能重置预算。它不是供应商账单对账工具。
- `RETENTION_DAYS` 空值为不限期限。配置后按会话最后更新时刻计算；过期内容立即不可读取，本人访问和维护命令每批处理最多 20 个会话。默认不删除历史。
- 连接/上游空闲/整次生成上限分别是 10/180/900 秒。Nginx 助手专用空闲超时 300 秒，10 秒心跳，30 秒 lease；长流至多约 10 秒复查登录/账号/任职变动，身份边界临近时提前复核。
- 公网通过 TLS 终止时，将实际 origin 放入 `ASSISTANT_TRUSTED_ORIGINS` JSON 数组。不要使用 wildcard credentials CORS。

## 部署前检查与启用顺序

以下为生产部署步骤，尚未执行；本地启用不等于生产发布。

1. 保留当前发布镜像/配置，备份 PostgreSQL 与助手附件卷。先在业务库备份副本验证完整迁移图、约束和升级结果。
2. 依赖锁包含 `httpx2==2.9.0`、markdown-it 与类型包。按正常流程构建后端和前端；`npm run build` 必须保留独立图片翻译构建。当前未进行 Docker 干净镜像构建。
3. `Dockerfile.backend` 的 CMD 会执行 `alembic upgrade head`，启动镜像就是潜在数据库变更，不能当成无副作用的健康检查。助手迁移 `20260929_0131` 保留原父版本 `20260929_0130`；合并迁移 `20261008_0140` 将它与远程主线 `20261006_0139` 汇成单一 head。普通 init_db 不自动建助手表。
4. API 将 `assistant-assets` 挂载到 `/app/backend/data/assistant`；多个 API 副本须共享该卷和数据库。单独备份、授权清理，不能指向文档工具或设备资源目录。生产 Compose 仍需保留既有 `.deployment-prod-release.yml` 发布覆盖文件。
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

先关闭助手并重启服务，使活动流中断并通过 lease 收敛；核对入口隐藏与其他业务健康。然后回退助手前后端版本及配置。保留四张表和附件卷，紧急回退不运行 downgrade。`0131` downgrade 遇到任何会话或 tombstone 会明确拒绝；不回滚旧 AI 退役迁移。

## 固定范围

没有实时订单/价格/产量读取工具、业务写入工具、联网搜索、语音或后台自治生成。独立 `/image-translation/` 应用未挂助手。16 个说明条目覆盖 15 个模块总览和 1 个注塑关键字段，原 9 条部分总览已扩充并核对；这不代表模块每个字段均已注册。未知字段、虚拟列表目标和未注册区域不假装定位成功。当前真实模型已经通过合成场景验证；更广泛的业务语义质量、Docker/Linux生产环境和手机软键盘实机仍需对应环境验收。

## 剩余验收的实际步骤

1. 账户恢复与真实聊天已完成：用户充值后原配置成功，三轮追问、切换会话恢复、图片上传/移除/同图重传、系统帮助工具往返、停止和刷新后恢复均通过，详见 MODEL_CONNECTION.md。未来再遇 403 时仍需区分余额、服务资格、地域和权限；不自动更换凭证或重试收费请求。
2. 手机：本轮用户无可用手机。后续在本人测试手机登录合成账号，打开助手并唤起中文软键盘，核对输入/发送可见；键盘打开时横竖屏切换；核对底部安全区、收起与再次打开；异常记录系统/浏览器版本和截图。普通窄屏截图不能替代。
3. 系统大字体：已有 Chromium 默认/最小字体 24px 与浏览器 200% 验证；仍需 Windows 系统字体缩放或相应真实设备设置后检查，再还原测试前设置。
4. 生产依赖：全新虚拟环境中的助手 HTTP/SSE 测试已通过；完整 requirements.prod 的安装及 Python3.13 Linux Docker 干净镜像仍需适用环境。镜像验收只挂合成数据库/附件，不启动真实业务库迁移。
5. 回归：保留当前完整后端运行日志，等待最终统计并定位失败。通过项与已修复后重测项单列，不将未结束的运行标为通过。
