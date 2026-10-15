# 人员与权限轻流程实现

本次依据 `rrn_permission_handoff_20261013.zip` 实施。基线 HEAD 为
`17775d8fa89c39b69d82c0aee140741f2e73300f`，9 个证据文件哈希一致。
原有 `src/features/collaboration/connect.css` 和 `test-artifacts/` 不属于本次修改。

## 已实现的流程与复用边界

1. 增量岗位待办/不可变事件，员工白名单接口，管理范围过滤的统一队列。
2. 复用 IAM 锁、实际权限矩阵、任职计划、固定角色版本和回执。
   注册抽取 flush-only 事务内核；在职替换只针对当前主职，不调用注册清理。
3. 同屏自动预览/确认、员工个人入口、通知 dispatcher 与身份刷新。
4. 隔离 SQLite/PostgreSQL、迁移与回滚、真实浏览器和独立复核。

高级任职、独立系统权限、供应商权限、预约、交接和旧注册/密码恢复入口继续保留。
不自动提交 Git，不改生产配置或业务数据库。迁移只在隔离测试库演练。

## 需求追踪

| 需求 | 实现与复用 | 执行证据 |
|---|---|---|
| R01 注册一次确认与授权 | `position_workbench.py`、`position_workbench_plan.py`、`system.py`/`identity_registration.py` 的 flush-only 内核；单事务回执、账号、主职和 outbox | 注册正常/异常回滚集成测试 |
| R02 员工声明不改权 | `MyPositionPanel.vue`、`AccountMenu.vue`、`position_reviews.py`、严格 schema、`PositionReview`/事件与 0160 迁移 | 自助声明/越权字段/IDOR/修改/退回/撤回测试，employee-390.jpg |
| R03 管理员同屏 | `PositionWorkbench.vue`、`PositionReviewPane.vue`，待分配/全部人员/内置权限/历史，移动主从切换 | 六种视口、真实审批和 legacy-success.jpg |
| R04 真实固定方案 | 使用当前 fixed-v33 32 角色目录、定义 hash 与 pinned `IamRoleVersion`，方案带可授范围 | 目录变化冲突、旧版本保持；final-admin-package.jpg |
| R05 保留或替换主职 | `position_workbench_plan.py` 仅替换当前 assignment 来源；保留沿用原固定版本/ceiling | 主职 id 保持、实际权限差异、旧角色不隐式升级 |
| R06 自动预览和风险 | 服务 SAVEPOINT 实际执行后回滚计算 tuple 差异；`usePositionReview.ts` 防抖/失效/过期/明确勾选 | 自动预览组件测试与 final-admin-risk-390.jpg |
| R07 独立来源 | 逐项 independent_allow 决策；保留 deny、系统、供应商及其他任职来源 | 四类独立来源同场景逐列/有效授权保持、future allow/deny、缺少处置 422 |
| R08 通知闭环 | `position_review_notifications.py`、`identity_outbox.py`、work-center registry/projection/route | 聚合/未知 kind/失败重试/无接收人、工作中心回归 |
| R09 并发与不明结果 | shared IAM lock、fresh_actor、fingerprint、唯一 open 索引、actor/command 回执；前端原命令重试 | PostgreSQL 独立连接竞态与 flush 后故障注入；竞争 edit/approve、响应丢失/receipt 恢复、改 body 冲突 |
| R10 范围与生命周期 | `position_workbench_read.py` 先完整 scope 后 total；functional org 不作 factory；scheduled/epoch 约束 | 跨范围/总务/未来来源/冻结/离职/注册历史与重申请回归 |
| R11 真失权 | 复用后端授权、identitySync，前端 effective_context_key 边界清数据 | 同 Cookie 的业务开单 201→403；同员工会话正式岗位刷新 |
| R12 兼容与回滚 | advanced/registration/position-reviews 路由保留，写闸门，兼容 kind，无破坏性数据回退 | 深链单元回归、关闭写闸门与非空 downgrade 拒绝；UI-off 独立开发实例中旧主页/兼容申请退回实测，rollback-success.jpg |
| R13 视觉键盘 | 局部 pw-* 样式、现有 token、原生 radio/select/disclosure、sticky 操作栏与焦点恢复 | 六种视口、完整键盘流；真实 200% 与 reduced-motion 动态补验通过；异步焦点回归 |

详细命令和范围见 `test-results.md`，52 条规格的覆盖/部分覆盖/未执行见 `acceptance-trace.md`；迁移/回滚见 `migration-report.md`；未验证事项见 `known-issues.md`。52 条规格没有被冒充为 52 项已通过测试。

## 本地可审阅入口

隔离验收使用 `http://127.0.0.1:5186/system/users`；员工入口 `http://localhost:5186/account/position`。数据文件位于本次临时 QA 目录，仅含合成人员。正常业务开发端口和真实数据库没有切换到该实例。补验以受控前台会话恢复隔离服务，当前地址可供本地复核；仅并发测试用 PostgreSQL 与独立 Playwright 测试浏览器已关闭。完整证据也保存在本目录。

源码处于当前工作树。文档/截图位于本目录，受既有 ignore 规则影响，尚未纳入 Git。若后续正式提交，应按明确路径纳入，不能使用 `git add -A` 吞入原有无关内容。
