# UV打印模块开发文档包

> **本文件在仓库内的文件名是 `PACK_README.md`**（避免与根目录 `README.md` 混淆）。
> 开发包 → 本目录的文件名映射：
>
> | 开发包原名 | 本目录文件名 |
> |---|---|
> | `README.md` | `PACK_README.md`（本文件） |
> | `UV_PRINT_SHARED_SPEC.md` | 同名 |
> | `UV_PRINT_SOURCE_AUDIT.md` | 同名 |
> | `DSH_FRONTEND_PROMPT.md` | 同名（DSH 阶段提示词，Codex 无需执行） |
> | `CODEX_BACKEND_REVIEW_PROMPT.md` | 同名（**Codex 的启动提示词**） |
> | `HANDOFF_TEMPLATE.md` | `HANDOFF_TEMPLATE_blank.md`（空白模板） |
>
> 已填写的实际交接文件是 **`HANDOFF_DSH_TO_CODEX.md`**（取代空白模板）；
> 契约差异与待确认口径见 **`DECISIONS.md`**；浏览器证据见 **`evidence/`**。
> `DSH_FRONTEND_PROMPT.md` 与 `HANDOFF_TEMPLATE_blank.md` 只为溯源保留。

目标：在 `rrceshi-3` 新增 **华康A → 生产部 → UV打印管理**，由DSH做前端，用户worktree验收后由Codex审查并实现后端。

## 使用顺序

先把本目录复制到实际项目的 `docs/uv-printing/`。**两位代理都以 `UV_PRINT_SHARED_SPEC.md` 为共同规格**，不是各自理解一套要求。

| 文件 | 用途 |
|---|---|
| [UV_PRINT_SHARED_SPEC.md](UV_PRINT_SHARED_SPEC.md) | 主文档：旧业务提炼、修正规则、完整UI、数据模型、接口、权限、worktree、45项验收、待确认口径 |
| [UV_PRINT_SOURCE_AUDIT.md](UV_PRINT_SOURCE_AUDIT.md) | 审计附录：本地40个证据源文件的路径/行号/hash，宿主实际入口及未验证边界 |
| [DSH_FRONTEND_PROMPT.md](DSH_FRONTEND_PROMPT.md) | 打开前端worktree后给DSH的启动提示词 |
| [CODEX_BACKEND_REVIEW_PROMPT.md](CODEX_BACKEND_REVIEW_PROMPT.md) | 前端验收合并后，给Codex的审查与后端启动提示词 |
| [HANDOFF_TEMPLATE.md](HANDOFF_TEMPLATE.md) | 交接模板：页面、契约、变更文件、实际测试与未完成项 |

DSH先做DEV专属样例预览，正式入口仍关闭；用户测试通过并明确提交/合并后，Codex从该main创建后端工作树。前端没有真实UV权限时，不修改用户权限或绕过正式页面鉴权，使用独立DEV样例路由测试。

文档包含完整目标，但阶段不是同时完成：F为前端，B0为真实人工业务闭环，B1为可靠自动采集和核对，B2为额外扩展。未完成阶段不能拿样例冒充可用业务。

本包只包含新编写文档，不含原项目、依赖、数据库、账号、现场配置或真实业务数据。本次完成的是选择性静态源码分析和规格编制，不是项目构建、现场硬件测试或GitHub改动。
