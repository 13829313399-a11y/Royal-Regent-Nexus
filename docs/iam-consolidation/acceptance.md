# 权限模块整合验收

日期：2026-10-14。来源：`rrn_iam_consolidation_20261014.zip`；32 个清单文件校验完成。基线见 [baseline.md](baseline.md)。代码、文档与合成验收证据按用户后续授权进行 Git 交付；生产发布仍为独立步骤。

## 交付行为

- 新开关启用后提供人员与权限、权限方案、操作记录三个主页。人员浏览和深链只读，明确发起调整才创建或复用待办。
- 授权范围内的岗位、注册、密码找回和高级任职待办聚合后统一统计、排序和分页。读取失败的来源显示未知数量，不能被当成零。
- 普通岗位调整同屏核对资料、方案、范围和实际差异；可明确保留原权限。高级办理复用原向导，密码找回复用原浏览器认领流程。
- 目录、审计、人员和个人例外权限分别检查。仅有 access_manage 的账号不会请求人员身份或独立权限目录。
- 未知结果保留原命令/原请求，禁用编辑和离开；403 清空受保护详情，409 使原预览失效。
- 搜索图标与输入内容分列布局；另修复了搜索条件不改变网址时查询未执行的问题。
- 历史来源提示改为“首次办理：确认旧权限的归属”，解释随岗位权限和独立权限的区别，下拉框不默认选择。确认要求实际权限新增和停止均为零，没有取消保护条件。

## 执行环境与证据边界

浏览器通过 Chrome 插件操作正式 Vue 页面。隔离 API 为 `127.0.0.1:8018`，整合开启构建为 `127.0.0.1:5190`，关闭构建为 `127.0.0.1:5195`。本节所述隔离验收的全部浏览器写入使用合成账号和 `D:/RR/.tmp/iam-consolidation-qa-20261014/workspace.db`，未连接日常业务数据库。最初 511 人，补加低权限账号后为 512 人。

冲突、超时、403 和延迟截图使用该隔离服务的单次故障中间件，注入被清楚标明；不是生产故障。事务、拒绝优先和范围隔离由后端真实 HTTP/数据库测试证明，截图不代替这些断言。原型图片不计入验收。

真实 200% 缩放和 reduced-motion 使用用户已授权的独立 Playwright 浏览器。通过 Chrome 设置选择 200%，CDP 返回 `cssVisualViewport.zoom=2`、`scale=1`；不是 DPR 或 CSS transform。CSS 视口 640×360，页面宽度 640，按钮可滚动到达。减少动态效果时工作区 animationName 非 none 的元素数为 0。

## 检查结果

| 检查 | 结果 |
|---|---|
| `npm run build` | PASS；包含助手知识校验、应用类型检查、Vite 与图片翻译完整构建 |
| `npm run typecheck:test` | PASS |
| IAM、路由、工作中心与个人授权相关前端测试 | PASS；14 文件、121 项 |
| `pytest backend/tests/test_iam_workspace.py -q` | PASS；10 项，223.41 秒 |
| 岗位领域、事务、范围、闭环回归及早期聚合测试 | PASS；26 项；4 项 PostgreSQL 并发测试跳过 |
| 独立只读审查 | PASS；发现的问题均修正，最终范围内无未修复的 P0/P1；审查不冒充额外运行测试 |
| `git diff --check` | PASS；已有 Windows 换行提示不影响检查 |

前端命令：`npm run test:unit -- src/features/identity-management/__tests__ src/router/__tests__/iamCompatibility.spec.ts src/router/__tests__/iamConsolidation.spec.ts src/features/work-center/__tests__/presentation.spec.ts src/views/__tests__/userAccessManagementPositionRuntime.spec.ts src/views/__tests__/userAccessManagementView.spec.ts`。

后端回归：`SEED_DEFAULT_ACCOUNTS=true`，执行 `backend/tests/test_position_reviews.py`、`test_position_workbench_acceptance.py`、`test_position_workbench_boundaries.py`、`test_position_workbench_closure.py` 和 `test_iam_workspace.py`。每个测试由夹具创建新数据库。新增聚合测试已自行固定种子策略，不再继承日常 `.env` 的禁用默认账号设置。中途测试夹具初始化失败和浏览器发现的问题已修正，以上数字为修复后结果。日志摘要见 [verification.txt](evidence/verification.txt)。

## 合并最新 main 后的复验

- 前端 14 文件 / 121 项、测试类型检查、完整构建通过；修复后的助手知识源码指纹校验 17 篇、0 问题。
- 岗位领域及目录回归累计 27 项通过，4 项真实 PostgreSQL 并发用例因本轮未配置实例跳过。首次运行的旧迁移路径与新增 Indonesia 排除项断言失败已修正；对应降级用例和完整目录的 8 项重跑全部通过。
- 聚合工作区 10 项通过；新增通配来源的具体禁止项回归 5 项通过，覆盖两个管理权限、厂区/部门通配、集团总务和待注册人员，并验证拒绝后业务记录不变。
- 迁移专项与材料交接迁移回归共 19 项通过。真实备份的恢复副本升级后，387 张原表、24,248 行及原 schema 对象不变，完整性正常、外键错误 0。
- 独立复核覆盖 main 合并交点、迁移与权限边界，未发现剩余明确阻断；本次没有迁移真实日常数据库或发布生产。

## 交付包验收矩阵

PASS 表示下面明确列出的证据层通过，不代表所有项目都进行了生产或多数据库测试。

| ID | 状态 | 证据与实际覆盖 |
|---|---|---|
| IA-01 | PASS | 三个主页真实浏览；roles-search-1440、records-1440、workbench-1440 |
| IA-02 | PASS | 聚合四来源真实 HTTP 测试；岗位、注册、找回分别打开对应表单 |
| IA-03 | PASS | 一个完整目录和一个记录入口；办理区复用 PermissionPackageSummary |
| IA-04 | PASS | PositionWorkbench/旧页回归断言读取与显式创建分离，query.person 只读 |
| IA-05 | PASS | 明确发起按钮调用 adjust，复用提示与返回 task；浏览器显式发起 |
| IA-06 | PASS | 真实岗位同屏详情、原始申报、确认内容、方案及差异 |
| IA-07 | PASS | 合成账号保留 426 项、新增 0、停止 0；键盘提交成功；领域版本/ceiling 回归 |
| IA-08 | PASS | advanced-drawer-1440；保留原向导与领域 API |
| IA-09 | PASS | geometry.json：1440×900 为 10 行、1280×800 为 8 行、1366×768 为 8 行；按钮完整可见 |
| IA-10 | PASS | keyboard-success；下一位重新查询授权队列，进入密码核验且未自动提交 |
| ST-01 | PASS | 迟到 A 详情/预览及 viewer 更换回归，禁止覆盖 B |
| ST-02 | PASS | usePositionReview 字段变化同步使预览和风险确认失效 |
| ST-03 | PASS | 过期预览禁用提交；向导/工作台测试 |
| ST-04 | PASS | conflict-409；冲突后原预览清空、需重新核对 |
| ST-05 | PASS | uncertain-408；原命令锁定，导航不能离开；查询后以同一零差异命令恢复成功；回执测试 |
| ST-06 | PASS | 密码与高级任职读取原请求；真实 RouterView+Drawer 408 关闭、Esc、导航及 beforeunload 测试 |
| ST-07 | PASS | forbidden-403；受保护详情消失；账号/上下文迟到响应隔离测试 |
| ST-08 | PASS | 逐项独立允许处置的领域与组件回归 |
| ST-09 | PASS | 明确 deny 保留、跨厂范围与来源边界回归 |
| ST-10 | PASS | 注册事务失败回滚测试，身份/授权/审计/receipt/outbox 不部分提交 |
| ST-11 | PASS | queued/retrying 领域回归；成功反馈显示通知进入发送队列 |
| ST-12 | PASS | 浏览器核验前按钮禁用；专用面板4项回归及既有领域流程；未在浏览器改密码 |
| ST-13 | PASS | 员工申报前后正式身份和实际权限一致的真实 HTTP 测试 |
| ST-14 | PASS | 保留权限的固定版本、范围上限和来源差异领域回归 |
| AU-01 | PASS | 完整授权范围先过滤再统计，越权详情403；岗位预览/提交沿用领域校验 |
| AU-02 | PASS | 未来允许、历史/到期绑定、最新定义升级及确认取消旧 ceiling 的新测试 |
| AU-03 | PASS | group-management 与业务厂区分别处理；原领域边界回归 |
| AU-04 | PASS | access-only.jpg；真实仅 access_manage 合成账号；实际目录请求独立门控回归 |
| AU-05 | PASS | catalog-only/audit-only 能力和路由函数测试；各自领域读取守卫保持；未将其算作单独账号浏览器验收 |
| AU-06 | PASS | 注入单来源异常：partial=true、总数null、其他来源仍返回 |
| AU-07 | PASS | 四来源同时间混合分页，SQL count/order/limit，跨页无重复/遗漏 |
| AU-08 | PASS | 类型化目标与冲突/数组/非法 ID 路由测试；不静默更换对象 |
| AU-09 | PASS | 三个前端开关组合测试；rollback-flag-off；后端写开关拒绝三个找回命令；schedule关闭下预约有效状态派生 |
| AU-10 | PASS | 兼容路由幂等及通知/工作中心测试；旧 access 深链实际变为人员例外面板，目标保留 |
| AU-11 | PASS | raw_status 与展示状态独立；注册、岗位、找回、退回、预约状态测试及 records-1440 |
| AU-12 | PASS | 无整合 schema/migration；仅 QA 合成库；无日常批量确认或授权重建 |
| UI-01 | PASS | 三个桌面尺寸的截图与 geometry.json，左右区域独立滚动 |
| UI-02 | PASS | 1920×1080 队列宽 672.54px，13 整行 |
| UI-03 | PASS | 390×844、360×800 的列表/详情截图；返回隐藏详情；关键按钮44px |
| UI-04 | PASS | zoom-200.png、zoom-200-action.png；真实 zoom=2，横向无溢出 |
| UI-05 | PASS | Enter 查询/选择/提交/下一位，Space 选择保留权限；keyboard-success |
| UI-06 | PASS | 抽屉标题获焦、Tab 保持在抽屉内、Esc 后焦点回到原按钮；真实路由未知结果锁测试 |
| UI-07 | PASS | reduced-motion 媒体启用，工作区动画元素0；见 display-check.json |
| UI-08 | PASS | 511/512 人真实分页、32方案、1398项新增差异展开；长姓名/职位独立合成数据截图 |
| UI-09 | PASS | loading-detail、empty-search、forbidden-403、只读及回滚页；失败与空结果区别显示 |
| UI-10 | PASS | 核心按钮调用现有实际 API；无模拟授权或仅提示的假提交按钮 |

## 保留的验证边界

- **BLOCKED：4 项 PostgreSQL 并发回归**。本次环境没有 `IAM_TEST_POSTGRES_URL`；SQLite 事务和领域回归通过，不能替代 PostgreSQL 多连接竞争证明。这是已有岗位领域并发验收边界，不声称所有数据库均通过。
- **PASS：后续用户授权的日常本地启用**。前端整合开关已持久化到 `.env.development.local`，5173/8000 服务重启，浏览器确认三页导航、实际待办、职位搜索和记录读取。没有执行迁移或授权提交；重启完成时 28 张账号与权限相关表逐表摘要相同；浏览器办理预览后，27 张保持相同，`auth_iam_state` 仅 `identity_mutation_lock.updated_at` 正常刷新，账号、任职及授权数据均未变化（对照排除会话、在线状态和临时预览表）。配置和 SQLite 完整备份保存在 `D:/RR/maintenance-backups/iam-consolidation-local-20261014-133946/`。
- **NOT RUN：生产激活与真实业务提交**。未发布生产，未代办真实员工调岗或密码认领。
- **NOT RUN：超大历史库容量压测**。512 人与混合分页通过。授权投影仍需检查候选记录的完整范围；未声明十万级历史记录的响应时间指标。
- 包内“access-only 可以读所有高级任职请求”的推测不覆盖现有领域 `user_manage`/requester 规则；没有借 UI 整合扩张该权限。个人例外入口已按独立权限实现并实测。

回滚和文件清单见 [delivery.md](delivery.md)。
