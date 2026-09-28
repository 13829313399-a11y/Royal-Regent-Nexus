# IAM V2 验收证据

## 证据说明

I01–I68 的规定场景均已完成本地验收。“通过”限于下表实际执行的 API、数据库、前端和浏览器场景，不代表整个仓库全量回归或生产发布。时间边界按 Spec 21.2 注入服务器时钟；C/D 验证业务与设备 API 门禁；线上发布按 Spec 24 另行授权。

新测试简称：

- C：`backend/tests/test_identity_changes.py`（5 项）
- L：`backend/tests/test_identity_lifecycle_contract.py`（7 项）
- H：`backend/tests/test_identity_handover.py`（3 项）
- P：`backend/tests/test_identity_postgres.py`（4 项，真实 PostgreSQL）
- M：`backend/tests/test_identity_migration.py`（2 项，SQLite 与 PostgreSQL 实际 Alembic 链）
- E：`backend/tests/test_identity_edges.py`（5 项）
- N：`backend/tests/test_identity_acceptance.py`（14 项）
- F：`backend/tests/test_identity_preflight.py`（1 项，只读来源清单）
- R：`backend/tests/test_identity_compatibility.py`（1 项，独立构建包、独立 Python 进程）

共 42 个独立新增后端用例；`acceptance-collection.log` 保存收集清单，实际通过证据见下方分批日志。

旧测试：A=`test_auth_api.py`；I=`test_iam_api.py`；S=`test_system_user_management_api.py`；W=`test_warehouse_position_scope.py`；Q=`test_internal_quote_api.py`、`test_internal_quote_whole_review.py`、`test_internal_quote_reviewer_withdrawal.py` 的审核/业务负责人专项；D=`test_user_directory.py`。所有后端路径都位于 `backend/tests/`。

浏览器 B：隔离 SQLite、API 8096、Vite 5196，合成管理员与工程师。证据和运行日志保存在 `D:\RR\iam-v2-qa`。未读取或修改业务库，也没有借用生产登录。验证结束后已停止隔离 API、Vite、浏览器和 PostgreSQL；数据库、脚本及截图仍保留在上述目录。

## I01–I68

| 编号 | 结果 | 已执行证据 / 尚缺范围 |
|---|---|---|
| I01 | 通过 | L、N：注册填写“超级管理员”不产生系统权限，原申报保留；自定义含 system 权限的审核角色独立分类，不挂到普通任职。 |
| I02 | 通过 | S：地方管理员不能通过注册审核给范围外授权。 |
| I03 | 通过 | C：职位更正不改变权限集合；事务失败恢复原身份；变更审计同事务写入。 |
| I04 | 通过 | N：同厂权限包升级减少指定权限，原主职 ID、厂区、部门、职位保持一致。 |
| I05 | 通过 | C 与 B：A 工程 → 华兴仓库，预览停止 13 项、增加 14 项，办结后名册和时间线刷新；H 验证历史厂区和创建人保持。 |
| I06 | 通过 | C：结束 A 主职后，B 兼任仍有效。 |
| I07 | 通过 | L：A 工程+B 业务不产生 A 业务权限；C 验证 B 仓库范围不扩到 A。 |
| I08 | 通过 | C：跨厂权限包受 selected 厂区集合限制。 |
| I09 | 通过 | E：all_current 已批准后新增组织，不自动获得新组织权限。 |
| I10 | 通过 | L：集团总务注册审核后生产厂区为空，只有明确选择的 A 业务范围有效；前端空主厂归中性 group。 |
| I11 | 通过 | M：本厂 management 旧档案保留原厂区，未自动创建集团任职。 |
| I12 | 通过 | H：缺少 profile 时显示待确认，显式核实组织后才建立任职，不取角色猜主厂。 |
| I13 | 通过 | E、A：独立 deny 优先于任职及其他 allow。 |
| I14 | 通过 | A、I：canonical deny 与 wildcard/权限并集合约回归。 |
| I15 | 通过 | E：转岗时明确保留独立 allow/deny，supplier 能力不被全清。 |
| I16 | 通过 | E：同一能力还有其他任职来源时，预览记录 source_changed。 |
| I17 | 通过 | L：不运行 worker，在临时支援到期点失去授权及销售资格。 |
| I18 | 通过 | N：worker 停止，在 T−1 微秒/T/T+1 秒核对 auth/me、权限及默认组织；前端真实 identitySync 定时器以偏差 14 年的客户端时钟测试服务器边界刷新。 |
| I19 | 通过 | N：跨 T 实际调用人员列表、普通目录、旧用户列表、报价业务候选和密码重置接口，结果取当前任职；数据库兼容 profile 仍保留旧组织，证明不依赖物化。 |
| I20 | 通过 | L：预约后新增资料变更，撤回原计划返回 SOURCE_CHANGED。 |
| I21 | 通过 | L：过生效点撤回返回 CHANGE_ALREADY_EFFECTIVE，保留两条任职历史。 |
| I22 | 通过 | N：三个真实测试会话同时冻结后，四类受保护 API 全部 401；解冻仍拒绝三条旧 Cookie，新登录可用。 |
| I23 | 通过 | C：解冻不恢复旧 Cookie。 |
| I24 | 通过 | H：离职立即停止账号，未完成报价责任生成待接管项。 |
| I25 | 通过 | E：离职、复职后跨过旧未来兼任生效点，旧 epoch 不复活。 |
| I26 | 通过 | C：旧 status=active 不能恢复 left 人员。 |
| I27 | 通过 | L：地方管理者本人变更转独立审批，自己不能批准。 |
| I28 | 通过 | L、N、S、I：地方管理范围包含当前/未来任职、独立角色及个人 allow/deny；范围外人员不出现在列表或总数中，详情和账号级变更也拒绝。 |
| I29 | 通过 | E：只有转授登记没有管理权限时不能管理；撤销转授使预览失效。 |
| I30 | 通过 | P、N：另一连接停用 actor 后提交拒绝；持有旧 AuthContext 的密码重置批准、重开、驳回均锁后重读并返回 401。 |
| I31 | 通过 | E、I：权限包定义变动使旧预览失效。 |
| I32 | 通过 | L、N：批准未来任职后给 live role 增加 system 权限，T 前后均不获得新增权；冻结包不与活模板并集。 |
| I33 | 通过 | L：旧快照中的 inactive 权限仍拒绝。 |
| I34 | 通过 | C、L：同键同内容返回同一结果；批次重试不重复成功项。 |
| I35 | 通过 | C：同键不同内容返回 409。 |
| I36 | 通过 | E、C：他人 token 404、过期 410、已消费拒绝或幂等返回。 |
| I37 | 通过 | P：两位管理员、两个独立连接同时调同一人员，一成功一 409，无双主职。 |
| I38 | 通过 | P：两位有效管理员同时停用自己，不能双成功，管理不变量保留。 |
| I39 | 通过 | E：管理员未来到期形成空档时，ensure_admin_survives 拒绝。 |
| I40 | 通过 | N：在身份、来源、版本、审计、outbox、幂等回执 flush 后、commit 前注入失败，全部回滚；原预览重试成功。 |
| I41 | 通过 | P、N：旧 ORM actor 和旧 AuthContext 在共享锁后重新读取，被停用后不能办理身份或密码重置。 |
| I42 | 通过 | L：同批两项一成功一冲突，逐项返回，重试保持成功项幂等。 |
| I43 | 通过 | H：报价版本变化后旧接管请求 409；重新评估后按新版本接管。 |
| I44 | 通过 | H：接管人后续离职，未完成报价回到 pending/SUCCESSOR_UNAVAILABLE。 |
| I45 | 通过 | H、B：六类未适配模块明确标为未覆盖，零已识别项不代表交接完成。 |
| I46 | 通过 | H：通知写入失败不回滚冻结；重试只交付一次。 |
| I47 | 通过 | Q：宽权限工程人员不能绕过正式销售成员资格。 |
| I48 | 通过 | L：正式销售兼任在目标厂有效，到期失效；主职在另一厂不阻断。 |
| I49 | 通过 | Q：31 个审核/业务负责人专项通过，覆盖原分段审核、自审限制、整单指定审核及批次撤回，保留各版本既有差异。 |
| I50 | 通过 | A、I：总经理业务权限不产生 system 管理权。 |
| I51 | 通过 | W、A：经理跨厂、主管/仓管本厂及通知部门合约通过。 |
| I52 | 通过 | A：生产任务跨厂只读特例回归，未扩写入。V2 显式厂区上限仍优先。 |
| I53 | 通过 | N 与 8 个 supplier 专项：实际供应商成员兼任内职，从 A 调 B 后原华兴供应商工作区仍可读，B 供应商工作区仍 403，成员与独立权限保留。 |
| I54 | 通过 | A、I：一般写入需 enforce；V2 require_writes 另要求身份写入开关。supplier 例外未扩大。 |
| I55 | 通过 | N：C/D 的宽权限管理员仍被 3D、UV、喷油门禁拒绝；合法 pause 请求体在工厂门禁处被拒绝，适用厂在模块关闭时返回 503，没有发送设备命令。 |
| I56 | 通过 | N：实际 init_db 连跑两次，已撤销、过期、未来来源状态和拒绝结果不变；R 在三种授权模式分别启动兼容包，旧来源仍不复活。 |
| I57 | 通过 | C：旧 system-position 对 V2 返回 409，不执行清理。 |
| I58 | 通过 | 前端 authSessionConcurrency/authorizationRefresh：旧会话、旧请求不覆盖新会话。 |
| I59 | 通过 | authenticatedFactoryContext：业务表单期间保留原厂区，离开后采用新主厂；App 显示身份更新核对提示。 |
| I60 | 通过 | D：普通通讯录字段白名单、无账号/联系方式/角色/会话信息。 |
| I61 | 通过 | N、E、L、S：直接请求管理详情/任职/旧状态接口和新办理 API 均校验完整管理范围，不依赖按钮隐藏。 |
| I62 | 通过 | L：冻结权限包与 live role 不并集；inactive 无旧逻辑兜底；来源缺失关闭。 |
| I63 | 通过 | P：真实 PostgreSQL 独立连接并发执行旧 IAM deny 编辑、V2 存量确认和注册。确认等待共享锁后因最新事实变化返回 409，注册保留；重新预览后保留新 deny。结构迁移仍使用维护窗口。 |
| I64 | 通过 | R、B：独立构建的兼容 ZIP 校验 547 个文件摘要；分别以 legacy/shadow/enforce 启动新进程，旧 Cookie 和已撤任职权限不恢复，预约 T 边界保持，新写入 403。构建后的 UI 关闭新人员/变更入口，回到原账号管理。 |
| I65 | 通过 | N：显式停 worker 跨 T，权限、人员/目录/业务候选仍正确；返回 handover_refresh_pending，办理记录与界面保留交接延迟提示。 |
| I66 | 通过 | B：320/640/1024/1280/1536/1920 名册截图及 document.scrollWidth 断言；320 抽屉实查。仅浏览器视口证据。 |
| I67 | 通过 | B：35 次 Tab 保持抽屉焦点，Escape 关闭并回到人员按钮；reduce 时 animationName=none。 |
| I68 | 通过 | 前端单测区分空/筛选无结果/403/503；B 实际验证目录 503 后重试恢复完整目录及办理入口、真实并发提交 409 后重新预览办结、普通人员 403 不伪装成空列表。 |

## 已运行命令与日志

运行环境：Windows，仓库 `backend/.venv/Scripts/python.exe`；真实 PostgreSQL 16.15，仅 `127.0.0.1:55439/iam_v2_test`，使用随机隔离 schema。PostgreSQL 项必须显式设置 `IAM_TEST_POSTGRES_URL`；兼容包项必须设置 `IAM_TEST_COMPAT_RELEASE`。未配置而跳过不算通过。

日志根目录：`D:\RR\iam-v2-qa`。以下均为实际执行结果，测试分批运行；早期失败日志保留，最终结论只使用修复后的通过日志。

| 范围 | 结果 | 最终日志 |
|---|---|---|
| C、L、E、N 的前 12 项 | 29 通过 | acceptance-identity-final.log |
| N 后段事务回滚、真实供应商兼内职 | 2 通过 | acceptance-atomic-supplier.log |
| 内置职位与交接 H | 7 + 3 通过 | acceptance-catalog-registration-handover.log（其余 3 个注册用例亦通过，1 个失败见下一行复测） |
| 注册部门、3D 审核兼容 | 4 通过 | acceptance-registration-final.log |
| PostgreSQL 并发 P | 4 通过 | acceptance-postgres-final.log |
| SQLite 实际升级、中断恢复、重新升级/重跑 | 1 通过 | acceptance-migration-recovery.log |
| PostgreSQL 实际完整 Alembic 链 | 1 通过 | postgres-migration.log |
| 只读副本清单 F | 1 通过 | acceptance-preflight-final.log |
| 独立兼容发布包 R | 1 通过 | acceptance-compat-release.log |
| 报价各版审核及业务负责人 | 31 通过 | acceptance-quote-review.log |
| 供应商工作区专项 | 8 通过 | acceptance-supplier.log |
| 旧用户管理与密码重置 | 31 通过 | acceptance-system-regression.log |
| IAM 范围/供应商/注册/职位/办理人 | 14 通过 | acceptance-iam-regression.log |
| 新界面、会话、组织刷新、原用户管理 | 8 文件、99 通过 | acceptance-frontend-accepted.log |
| 原权限编辑器、预览、无障碍与路由 | 5 文件、20 通过 | acceptance-frontend-legacy-final.log |
| 测试 TypeScript 检查 | 通过 | acceptance-typecheck-final.log |
| 应用类型检查和构建 | 通过 | acceptance-build-final.log |

后端日志中的选择性 `deselected` 是未选择的同文件用例，不计入通过数。此前原认证/IAM/仓库/通讯录等 139 项回归已通过分批运行和定向复测，证据为 `regression-auth.log`、`auth-failures-fixed.log`、`regression-business.log`、`directory-final.log` 等；与上表有重复，不相加宣称独立总数。

复现入口（在项目根目录，按环境准备说明设置隔离参数）：

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_identity_changes.py backend/tests/test_identity_lifecycle_contract.py backend/tests/test_identity_handover.py backend/tests/test_identity_postgres.py backend/tests/test_identity_migration.py backend/tests/test_identity_edges.py backend/tests/test_identity_acceptance.py backend/tests/test_identity_preflight.py backend/tests/test_identity_compatibility.py -q
npm run typecheck:test
npm run build
```

前端用例路径记录在上述两份 Vitest 日志首行，使用实际 `npm run test:unit -- <路径>` 执行。不存在 `lint` 脚本，没有声称运行 lint。

## 浏览器与兼容包证据

- 正常流程：`transferred-people.png`、`transfer-impact.png`、`records.png`、`audit.png`、`restart-verified.png`。
- 视口与键盘：`people-320.png` 至 `people-1920.png`、`details-320.png`、`browser-responsive.log`、`browser-keyboard.log`。是浏览器视口证据，未声称物理移动设备验收。
- 异常与恢复：`catalog-failure.png`、`catalog-recovered.png`、`real-conflict.png`、`conflict-recovered.png`、`people-forbidden.png`。浏览器有故意触发的 401/403/409/503，不能写成“控制台零错误”。
- 来源显示：`source-assignment-status.png`，历史来源记录保留，关联任职已结束的状态明确展示。
- 兼容 UI：`compat-built-ui.png`、`compat-browser.log`。静态构建包的页面入口单独在浏览器检查；后端禁写和授权以独立进程的 R 验证。
- 最终回退包：`compat-20260927-release/iam-v2-compatible-fallback.zip`，SHA256 `856b6e60c786f62fd0f46fa79f407de60b1a62242d2d758f60f90c0ab80d667e`。包含后端源码、独立禁写入口、前端构建及逐文件清单；不含数据、配置、凭据或依赖环境。

## 独立复核与阶段结论

用户已明确允许独立审查，独立子代理完成只读检查与隔离复现。修复和复测记录见 [独立复核](independent-review.md)。这是独立代理复核，业务操作人员的生产启用确认仍按 Spec 23/24 另行办理。

P0–P7 的本地开发交付与 I01–I68 规定场景验收已完成。预约消费者、兼容回退包、迁移中断恢复和独立复核已有执行证据；保持默认关闭写入/预约是发布策略。生产配置核实、真实人员归属确认、生产备份和生产部署没有执行，也没有取得发布授权。六类未适配交接模块仍明确显示“未覆盖，需人工核实”，符合 I45，不能被解读成已自动接管。
