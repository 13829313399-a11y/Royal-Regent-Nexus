# 增量迁移与回滚

新增 Alembic `20261013_0160`，父版本 `20261012_0159`。只创建 `position_reviews`、`position_review_events` 及相关索引、外键；不扫描生成在职历史申请，不改变任何原有任职、角色、权限或账号状态。同一 user/epoch 的 pending/returned 使用部分唯一索引。

已有数据库启动不会用 `create_all` 绕过新迁移。缺表时岗位接口返回明确的需迁移错误；实施前须针对实际 DATABASE_URL 检查 revision，并在停写、备份和副本演练后显式迁移。日常本地业务 SQLite 已按用户后续授权完成备份、副本演练及 0160 迁移；backend/.env 与 .env.development.local 已持久化启用岗位工作台。生产 PostgreSQL 与 Compose 未修改。

## 隔离验证

- 使用既有 `test_identity_migration.py` 在临时 SQLite 与本次临时 PostgreSQL 上执行迁移链；实际 PostgreSQL 版本 16.15，地址 127.0.0.1:55440。
- Browser QA 使用独立 `D:/RR/.tmp/position-qa-20261013/browser.db`，由隔离服务初始化/种入合成资料，不是业务数据库复制品。
- 新增 downgrade guard 用例在已有申报/事件时实际调用迁移 downgrade，得到 RuntimeError，原 pending 和事件仍存在。
- 关闭后端岗位写开关后，原申报/历史仍可读，新增/撤回写入被拒绝。既有深链的路由单元测试通过。独立启动关闭 UI 开关的开发实例，浏览器确认旧主页仍可用、兼容入口仍可读取并退回已有申请，员工能读到结果；最后完整构建也采用默认关闭新入口的配置。没有实施生产二进制切换。
- 未执行生产切换、生产备份恢复、旧生产二进制回滚；不能据本地测试宣称生产已迁移。

## 启用条件

前端保留既有 `VITE_IAM_IDENTITY_UI_ENABLED` 约定，并且必须显式设置 `VITE_POSITION_WORKBENCH_ENABLED=true` 才开启新主页/个人菜单，默认不切换现有入口。管理员日常入口使用 `/system/users`；员工入口 `/account/position`。

后端写入要求 `IAM_POSITION_WORKBENCH_ENABLED=true`、`IAM_IDENTITY_WRITES_ENABLED=true`、`AUTHZ_MODE=enforce`、`AUTHZ_WRITES_ENABLED=true`，并已经迁移到新 head。新增后端开关默认 false。正式启动参数由部署任务明确设置，不能将本次隔离 QA 的临时端口/账号当生产配置。

## 回退路径

1. 只回退新主页：关闭前端岗位 UI 开关，但保留新后端/worker；使用 `/system/users/position-reviews` 处理已存在申请，`/system/users/advanced` 仍可执行高级任职管理。
2. 需要暂停写入时，关闭岗位后端写开关，保留查询、历史与兼容 outbox dispatcher。此时停止新办理是明确的写闸门行为，不会把申请自动设为失败或已完成。
3. 不删除含申请/事件的表，不恢复无法识别新 kind/新 IAM 来源的旧后端。注册与密码恢复仍在 `/system/users/registration`。
4. 若将来正式发布，需要另行完成实际部署库的备份、迁移副本校验、实例切换和生产验收；本次代码交付不代替该流程。


## 日常本地启用验证（2026-10-13）

- 实际业务库：`D:/RR/royal-regent-nexus/backend/data/royal_regent_nexus.db`；明确确认进程没有 DATABASE_URL 环境覆盖，Settings 指向该路径。迁移 `20261012_0159 -> 20261013_0160`，386 -> 388 表，26 个账号保留。
- 先停止日常 8000/5173，再执行 integrity/FK 检查与 SQLite online backup。备份目录：`D:/RR/maintenance-backups/position-local-20261013-160240`；包含数据库、前后端启用前配置及逐表指纹。数据库 SHA-256：`65a5fd0cbbae676fc4b475e9aed046473bb5cb5f042d4aa7bc280b42b4168694`。
- 副本及源库迁移后，385 张原有业务表（排除 Alembic 版本表）的全量内容指纹和建表 SQL 均一致，只新增两张空表；integrity=ok，外键违规 0。副本执行 init_db() 亦未改变任何表。独立复核确认无待生效预约、待发 outbox 或助手文件恢复任务。
- 源库完整服务启动后的唯一既有表差异：`auth_iam_state.identity_mutation_lock.updated_at` 更新。已对照 lock_mutation 实现确认是原有 worker 获取数据库锁的时间戳；账号、任职、角色绑定、权限及其他业务表指纹保持一致。
- 后端持久化原有 enforce/authz/identity 开关，并设置岗位开关 true、scheduling=false、seed_default_accounts=false、明确固定本地 DATABASE_URL；其他原有 .env 值原样保留，没有顺带开启 cutting/collaboration。前端开发配置显式 position=true、identity=true、proxy=127.0.0.1:8000。
- 重启后实际 5173 返回的 Vite 环境确认两项 UI 开关 true；8000 /health=200；localhost 与 127.0.0.1 的人员入口及新工作台组件均 HTTP 200；匿名受保护接口经 5173 代理返回 401，认证边界保留。
- 用真实数据库的 `mode=ro` + `PRAGMA query_only=ON` 连接，在现有授权管理员的实际权限上下文中执行队列、岗位套餐目录、本人岗位读取，全部成功；后台岗位写开关计算为 true，没有提交人员/权限变更。
- 内置浏览器成功呈现 5173 登录页，URL 正确保留 redirect=/system/users，页面非空、无框架错误覆盖，控制台无 error/warn。该浏览器没有日常库的有效登录会话，因此没有冒充已完成真实账号登录后的页面办理；用户以原账号登录即可检查新入口。
- 原始检查数据及运行日志：`D:/RR/.tmp/position-local-activation-20261013/`。本轮为配置/迁移启用，按 AGENTS 不重复无关构建；无 Git 提交、无生产切换。
