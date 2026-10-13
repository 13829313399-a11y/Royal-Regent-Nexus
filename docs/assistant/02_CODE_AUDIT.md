# 曜灵开发前代码核查记录

**项目：Royal-Regent-Nexus**
**目录：`D:\RR\royal-regent-nexus`**
**核查日期：2026-09-29**
**目的：为新通用 AI 助手确定真实接入点、业务讲解口径和开发风险。**

本记录区分“代码已经存在”“设计建议”“尚未验证”。它不是整仓安全审计，不是浏览器实测报告，也不是模型连接成功证明。路径均相对上述项目根目录。

## 1. 核查基线与方法

| 项目 | 本次观察 |
|---|---|
| 授权设备 | `DESKTOP-CQQA2D6`，通过 Remote Desktop Commander 读取 |
| 当前分支 | `fix/three-d-telemetry-performance-20260929` |
| HEAD | `19332e167e0b990fb0900c868ba0620204f9bd26` |
| 最近提交 | `19332e16`，2026-09-29，`fix(3d): bound telemetry analytics and repair live record handling` |
| 已有未提交改动 | ` M PROJECT_MEMORY.md`；`?? test-artifacts/` |
| 本次操作 | 目录查看、源码读取、关键词定位、Git 只读信息查询 |
| 本次未做 | 写业务源码、改配置、启动应用、访问真实数据库、运行迁移、付费模型调用、提交或部署 |

读取了 `AGENTS.md`、`PROJECT_MEMORY.md`、`DESIGN.md` 和上下文索引，再沿着“根布局 → 路由 → 认证 → 网络 → 当前 Qwen 调用 → 数据库启动 → 业务字段 → 部署代理”追踪。

对 `src`、`backend/app`、`backend/tests`、`shared`、`scripts` 内匹配源码扩展名的 **1270 个文件**进行了文件清单建立；对相关前后端运行时代码做 AI/Qwen/assistant 关键词定位。**这不代表逐行读完 1270 个文件。**随后完整读取了下表中的关键文件，并对大型认证服务读取相关连续代码段。

远端 PATH 没有 `rg`，因此改用直接文件读取及原生搜索。一次对错误候选目录 `services/injection_v3` 的搜索没有得到可靠内容，未将其作为“代码不存在”的证据；随后定位实际目录 `services/injection_scheduling` 并读取实现。一个增强摘要脚本调用被工具层拦截，之后使用正常读取工具继续，没有依赖该脚本的结果。

未读取实际 `.env` 内容。配置类中的空默认值不能用于断言用户没有配置 Key，目录中存在 `.env` 也不能用于断言连接可用。

## 2. 已读取的主要代码与用途

“完整”表示本轮读取了该文件的完整文本，不代表其每条业务路径都经过运行验证。

| 路径 | 读取范围 | 提供的证据 |
|---|---|---|
| `AGENTS.md` | 完整 | 当前指令、源码优先、工作区与提交约定 |
| `PROJECT_MEMORY.md` | 完整 | 历史方向、模块演进线索；需要与现代码交叉验证 |
| `DESIGN.md` | 完整 | 主系统设计体系、局部样式与布局约定 |
| `docs/agent-routing/context-index.md` | 完整 | 模块上下文入口 |
| `package.json` | 完整 | 前端依赖、真实脚本、缺失的直接依赖 |
| `backend/requirements.txt` | 完整 | 本地后端依赖 |
| `backend/requirements.prod.txt` | 完整 | 生产依赖与本地差异 |
| `src/App.vue` | 完整 | `AppShell`、全局 `WorkCenterHost`、授权提示 |
| `src/main.ts` | 完整 | Pinia、Router、会话失效与身份同步安装顺序 |
| `src/components/layout/AppShell.vue` | 完整 | `fullPage` 分支、移动侧栏、门户样式范围 |
| `src/router/index.ts` | 完整，803 行 | 普通/全屏/公开路由、模块路由、权限及厂区守卫 |
| `src/lib/http.ts` | 完整 | Axios 配置、统一访问失败处理、普通请求超时 |
| `src/lib/sessionExpiryHandler.ts` | 完整 | 401 跳转与 403 刷新身份 |
| `src/lib/identitySync.ts` | 完整 | 45 秒同步、有效身份上下文变化事件 |
| `src/lib/bodyScrollLock.ts` | 完整 | 可重入、多锁协调的滚动锁 |
| `src/stores/auth.ts` | 完整 | `sessionVersion`、`can()`、授权快照及账号切换 |
| `src/stores/app.ts` | 完整 | 当前厂区、路由 factory 参数、身份刷新与业务页固定上下文 |
| `src/config/pageAccessPolicy.ts` | 完整 | 普通只读页面浏览与严格路由的区别 |
| `src/features/work-center/WorkCenterHost.vue` | 完整 | 全局通知宿主、声音与生命周期 |
| `src/features/work-center/types.ts` | 完整 | 待办生命周期、个人阅读状态、数据健康度 |
| `src/features/work-center/routes.ts` | 完整 | 固定 route key、实体 ID、厂区校验 |
| `src/features/injection-scheduling/types.ts` | 完整 | 四厂范围、字段、状态、业务班次 |
| `src/features/three-d-printing/printerPresentation.ts` | 完整 | 准备态、过期态与真实显示标签 |
| `src/features/uv-operations/contracts.ts` | 完整 | 华康 A 固定范围、模拟数据标签、迟到响应隔离 |
| `backend/app/main.py` | 完整 | 路由注册、应用启动副作用、计时中间件 |
| `backend/app/core/config.py` | 完整 | 文档 Qwen 设置、SecretStr、默认数据库配置 |
| `backend/app/api/auth.py` | 完整 | Cookie 登录及强制改密链路 |
| `backend/app/services/auth.py` | AuthContext 与文件尾部相关连续段 | 当前用户、会话有效性、强制改密、权限与范围校验 |
| `backend/app/api/document_tools.py` | 完整 | 已登录用户入口、本人文件归属与附件响应 |
| `backend/app/api/work_center.py` | 完整 | 供应商排除、快照一致性、降级处理 |
| `backend/app/services/quote_recognition.py` | 完整 | 受限候选识别提示词、Qwen 请求方式与输出校验 |
| `backend/app/services/injection_scheduling/field_registry.py` | 完整 | 字段名称、是否可编辑、旧表辅助字段说明 |
| `backend/app/services/injection_scheduling/calculations.py` | 完整 | 欠数、同啤产物、耗料、工时的实际公式 |
| `backend/app/services/work_center/service.py` | 完整 | 当前责任、已读、稍后、关注、历史重新鉴权 |
| `backend/app/db.py` | 完整，853 行 | `init_db()`、schema 检查、`create_all` 与播种 |
| `backend/alembic/versions/20260826_0084_remove_ai_subsystem.py` | 完整 | 旧 AI 退役与不可逆降级约定 |
| `backend/tests/test_retired_assistant_migration.py` | 完整 | 旧 AI 表删除及业务通知保留测试 |
| `backend/alembic/versions/20260929_0130_three_d_telemetry_rollups.py` | 完整 | 当时可见的新迁移及其父 revision |
| `nginx.prod.conf` | 完整 | 普通 API 的 30 秒代理超时和现有专用位置规则 |
| `Dockerfile.backend` | 完整 | Python 3.13 容器、生产依赖、启动时自动执行迁移 |
| `Dockerfile.frontend` | 完整 | 构建变量传递、独立图片翻译构建、Nginx 静态服务 |

另外查看了根目录、后端目录、feature 目录及 Alembic versions 文件清单。Qwen 相关关键词命中还涉及 OCR、PDF 命名和翻译服务；对没有进一步完整阅读的文件，不据此作出完整行为保证。

## 3. 直接影响实施的发现

### A01：没有可直接补皮肤的现役通用 AI 助手

当前根布局、路由和主 API 注册中未见通用聊天宿主或路由；退役迁移明确删除旧通用 AI 持久化数据。文档 OCR、翻译和报价候选识别不是同一个产品。

**实施结论：**新建 `src/features/assistant` 和 `/api/assistant`；旧迁移及其测试保留，不恢复十几张旧表，不声称旧会话可恢复。

### A02：只改侧边导航会漏掉核心业务页

`AppShell.vue` 在 `fullPage` 时直接渲染路由；注塑、3D、内部报价、QC、权限、供应商等页面使用这条路径。

**实施结论：**从 `App.vue` 并列挂载助手宿主，再由登录及页面状态控制入口。独立 `/image-translation/` 并不经过这个 Vue 根节点，必须明示覆盖边界。

### A03：“所有用户”不能复用事项工作台的 viewer

`work_center.py` 的 viewer 排除了纯供应商账号。助手需要面向所有合格登录账号，不能继承这项排除。

**实施结论：**直接复用 `get_current_user`，在知识受众层区分内部/供应商/通用，而不是拒绝供应商自由聊天。

### A04：正常身份刷新会增加 sessionVersion

`auth.applySession()` 每次应用快照都会增加 `sessionVersion`，而身份同步会周期调用 `/auth/me`。

**实施结论：**把 sessionVersion 变化一律当作会话终止，会造成长回答约每次刷新就中断。使用真实账号、任职周期和有效上下文判断；同时用请求 generation 阻止旧账号响应污染新状态。

### A05：已有网络客户端不适合直接承载聊天流

Axios 的普通请求超时为 15000ms。现有 `dispatchAccessFailure` 正是 fetch 请求接回共同会话处理的适配点。

**实施结论：**采用 fetch 流；明确处理 401/403、跨块 UTF-8、SSE 分帧、末尾 usage、断线和取消。供应商认证失败不能映射成用户登录失效。

### A06：模型连接存在，但现有调用约束不能继承

`quote_recognition.py` 的目标是从候选 ID 中选字段，要求 JSON、限制 reason、关闭思考，并使用固定输出预算；这是正确的识别业务边界，不适合作为自由问答提示词。

**实施结论：**新 provider 与配置独立；保持现有 OCR/翻译正常。不要把文档工具 `ai_mode=off` 变成所有聊天也被关闭。

### A07：本地和生产依赖并不相同

本地 `requirements.txt` 包含 `httpx2`；生产文件明确包含 `openai==2.53.0` 和 `httpx2==2.9.0`。直接假定本地已经装 OpenAI SDK 会制造环境差异。

**实施结论：**明确只使用一个验证过的接入方式，对齐该功能必需依赖；检查实际异步流接口。不要盲目升级与本功能无关的全套依赖。

### A08：页面可见性不是数据访问权限

普通页面允许已登录只读浏览，但严格路由、私有客价参数、UV、供应商仍有特定权限规则。

**实施结论：**讲解通用字段与读取真实订单分开。不能为了让助手“看懂页面”上传整个 DOM、复用管理员接口或凭前端路由参数放行数据。

### A09：新增模型可能触发启动时偷偷建表

`db.init_db()` 会注册多模块模型并执行 `Base.metadata.create_all`。只加 `ASSISTANT_ENABLED=false` 并不能阻止被 metadata 收录的表创建。

**实施结论：**明确从启动自动建表列表排除 `nexus_assistant_*`，新增显式迁移；关闭或缺表时只影响助手，不加整站硬失败条件。

### A10：生产代理可能把流式回答变成等待或超时

普通 `/api/` 只有 30 秒代理超时，未为助手关闭缓冲。

**实施结论：**独立助手 location、SSE 响应头、心跳与超时联调；不能以开发服务器能逐字显示为生产已可用的证明。

### A11：后端镜像启动会执行真实迁移

`Dockerfile.backend` 的启动命令包含 `alembic upgrade head`。把新迁移打入镜像再启动，可能直接修改目标数据库。

**实施结论：**实施、隔离库演练和正式部署分开；本轮不启动真实项目或发布镜像。文件夹里最后一个迁移编号也不代表实际 head 已核实。

### A12：业务讲解必须保留“未知”和“部分”

注塑字段有未解释辅助值；UV 有 synthetic；事项快照有 partial；3D 有 STALE。它们不能被简单翻译为“正常”“已完成”或“没有待办”。

**实施结论：**把这些状态作为知识和测试的正式内容，而不是让模型润色后抹掉区别。

## 4. 可直接转成帮助条目与测试的数据口径

以下公式来自实际代码；数字示例全部为**构造测试数据**，不是厂区实绩。

### 4.1 注塑：顺序啤数分配

来源：`calculations.py::quantities`。

```text
已啤数 = 期初啤数 opening_shots + 本期已上报啤数 reported_shots
有符号欠数 = 计划啤数 planned_shots + 补数调整 adjustment_shots - 已啤数
显示欠数 remaining_shots = max(0, 有符号欠数)
超产啤数 overproduced_shots = max(0, -有符号欠数)
```

计划值缺失时有符号欠数与显示欠数为未知，不自动成为 0。

**测试向量：**计划 1000、期初 100、已上报 200、补数 +50 → 已啤 300、欠数 750、超产 0。计划 100、期初 0、上报 120、补数 0 → 欠数 0、超产 20。

### 4.2 注塑：同啤产物口径

```text
欠良品件 = max(0, required_units - good_units)
欠啤数 = ceil(欠良品件 / effective_outputs_per_shot)
```

required_units 缺失、有效每啤出件缺失或不大于 0 时，不能给出有效欠啤数。组级计算在普通顺序口径求和；同啤产物按实际产品归集所需良品件，再取各产品所需啤数的最大值。

**测试向量：**需求良品 1001、累计良品 201、每啤有效出件 3 → 欠良品 800、欠啤数 267。两种同时产出的产品分别需要 200、150 啤 → 共需 200 啤，而不是 350 啤；复杂产品归集继续按 `remaining_for_group` 的实现验证。

### 4.3 注塑：时间、料重和加工金额

```text
每小时目标 = target_shots_per_day / target_basis_hours
纯生产小时 = 欠啤数 / 每小时目标
剩余料重 kg = 欠啤数 × 每啤净重 g / 1000 × (1 + allowance_rate)
剩余加工金额 = 欠啤数 × 单价/啤
```

代码默认 target_basis_hours=24、allowance_rate=0.01，但实际显式配置优先；不要把日目标一律当作白班 12 小时目标。任何相关数值缺失都应保留未知状态。

**测试向量：**欠 750 啤，日目标 600、折算 24 小时，净重 20g、附加系数 0.01、单价 0.1 → 每小时 25 啤、纯生产 30 小时、料重 15.15kg、加工金额 75。纯生产时长不包含所有换模、换色、日历和下游时间。

### 4.4 注塑旧字段和厂区

`field_registry.py` 把 `ratio_raw` 标为“原比例（未解释）”，`legacy_weeknum_delta` 标为“原周序号差（非检修）”，`legacy_lookup_at_raw` 标为“原 AT 查找值（未解释）”。助手不能自行解释成成本倍率、检修周期或确定交期。

当前注塑的 FACTORIES 是华兴、华登、华康 A、华康 B。全项目组织已经包含六个生产厂区，不代表注塑现有模块也支持六厂。

### 4.5 事项工作台

来源：`work_center/service.py::flags / snapshot / patch_state`。

```text
可处理责任 = task 且 can_act=true 且 lifecycle 为 open 或 in_progress
有效稍后提醒 = 可处理责任 且提醒时间在未来 且 attention_version 仍匹配
当前聚焦 = 可处理责任排除有效稍后提醒
```

`read_state` 不改变源业务生命周期；正在办理的 task 不能靠归档结束。`summary` 与应用查询筛选之后的 `filtered_total` 不一定同范围；回答数量前必须辨明所指范围。`health=partial` 不能解释为数据全部完整。

### 4.6 3D 与 UV

`printerPresentation.ts` 将 PREPARE/PREPARING/DOWNLOADING/SLICING 归为准备态，将 STALE 显示为等待状态更新。它不证明业务记账和入库已经完成。当前未对整个设备执行/对账状态机做完整审查。

`uv-operations/contracts.ts` 固定 `UV_FACTORY='huakang-a'`；Meta 中 `data_mode='synthetic'` 必须解释为模拟数据，不可当真实生产数据。未知/离线/采集延迟分别说明，不把未知一律变故障。

## 5. 帮助知识范围与尚需补读的业务

主规格要求为当前模块建立帮助覆盖表。以下业务本次已定位路由/相关契约，但**没有完整逐行核实其全部业务流程**：内部报价各版本、啤办全流程、客户订单、纸箱采购、供应商协同、箱唛核验、QC、喷油、身份变更以及 3D/UV 的完整后端状态机。

Codex 在 P0/P3 必须沿各页面实际 API 和服务读取：入口与按钮条件 → 后端授权 → 业务状态转换 → 字段字典 → 现有测试。帮助文章中的流程顺序、按钮可用条件、审批要求和公式必须由当前实现证明。

尤其不能用旧 PROJECT_MEMORY 或设计文档直接推定某种报价版本的审批步骤，不能因为界面有一个菜单就把尚未实现功能写进帮助。

## 6. 尚未验证的事项

| 未验证项 | 对交付的影响 | 实施阶段如何补齐 |
|---|---|---|
| 真实 UI 的尺寸、层级、动画效果 | 当前只能给设计规格，不能保证现网无遮挡 | 在真实业务页使用合成账号/数据截图与交互测试 |
| Key、实际地域/业务空间、模型权限与计费 | 官方模型列表不等于用户账号可用列表 | 经授权在受控环境做最小付费连接测试，不显示秘密 |
| 图片、联网、思考、工具调用的实际组合 | 不保证所有候选模型都支持这些组合 | 分组合记录真实请求参数和结果状态 |
| 当前 Alembic 全部 heads / 实际数据库 revision | 0130 文件不是最终数据库状态证明 | 安全加载配置后检查迁移图；仅在隔离数据库演练 |
| 本地/生产运行依赖与版本 | 清单不等于已安装成功 | 核对解释器、锁文件和容器，运行新功能兼容测试 |
| 所有业务模块完整帮助覆盖 | 少数关键语义已核实，不应泛化为整仓全懂 | P0 建矩阵，P3 按来源补写、审阅、运行一致性测试 |
| 新功能测试和性能 | 此次没有实现，也没有执行功能测试 | 使用 `03_ACCEPTANCE_CASES.md` 落地并填入真实证据 |
| 网关/CDN/线上反向代理额外规则 | Nginx 文件未必是全链路唯一代理 | 发布前检查实际网络链路与流式空闲超时 |

**结论：**当前代码足以明确助手的架构接入与几个最易讲错的业务口径。未验证部分已经转成实施任务，而不是被包装成“全部审核通过”。
