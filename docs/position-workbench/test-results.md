# 人员与权限实现验证

日期：2026-10-13。基线 `17775d8fa89c39b69d82c0aee140741f2e73300f`。本报告是本次源码执行证据；交付包原型的 44 项检查和 52 条规格不计作本项目通过数。

## 执行结果

| 检查 | 结果与范围 |
|---|---|
| `npm run build` | 通过；说明来源指纹、vue-tsc、主应用 Vite、图片翻译子应用与发布边界检查均通过。存在非阻断的大包/PURE 注释提示。 |
| `npm run typecheck:test` | 通过。 |
| `npm run test:unit -- src/features/identity-management/__tests__ src/router/__tests__/iamCompatibility.spec.ts src/composables/__tests__/useNotificationCenter.spec.ts src/features/work-center/__tests__/presentation.spec.ts src/lib/__tests__/identitySync.spec.ts` | 9 文件、80 项通过，34.69 秒。覆盖自动预览、切人/切身份、时点权限变化、不明结果、兼容路由、通知与身份刷新。 |
| 入口回退补验：`npm run test:unit -- src/router/__tests__/iamCompatibility.spec.ts src/features/work-center/__tests__/presentation.spec.ts` | 2 文件、20 项通过，32.81 秒，其中新增 1 项，其他为重复回归；本次相关前端案例共 81 项，不能相加为 100 项。最后修改后再次完成 test TypeScript 检查与完整构建。 |
| `.venv/Scripts/python.exe -m pytest tests/test_position_reviews.py tests/test_position_workbench_boundaries.py tests/test_position_workbench_acceptance.py -q -s --tb=short` | 修复后 18 项通过，337.92 秒；使用隔离 SQLite 和真实本地 PostgreSQL。 |
| 新增边界/性能补验：`... pytest tests/test_position_workbench_acceptance.py -q -s --tb=short -k 'group_scope or bounded_queries'` | 2 项通过，31.82 秒。其中性能案例是重复执行；新增后端案例共 19 个，不能将 18+2 算作 20 个不同案例。 |
| 既有回归：`... pytest tests/test_identity_changes.py tests/test_identity_acceptance.py tests/test_identity_edges.py tests/test_identity_postgres.py tests/test_work_center_api.py tests/test_registration_departments.py -q --tb=short` | 44 项通过，804.48 秒。含真实 PostgreSQL 多连接竞争。 |
| 既有迁移用例 `tests/test_identity_migration.py` | 隔离 SQLite/PostgreSQL 迁移链检查通过；详见 migration-report.md。 |

PostgreSQL 测试使用 `IAM_TEST_POSTGRES_URL=postgresql+psycopg://position_test@127.0.0.1:55440/iam_v2_test`，数据库为本次创建的隔离实例，不能改为业务库运行。

基线检查曾有 25 passed、1 skipped、1 failed；固定岗位目录的历史数量断言已在本轮修正为权限分组/去重/明确边界契约，并补齐既有仓库作业排除。真实目录和授权未修改。该文件最终 7 passed。历史跳过项依赖未提供的兼容构建工件；独立 UI-off 浏览器回退已另验。

## 真实权限与事务证据

- 员工申报前后 `/api/auth/me` 正式身份与授权不变；多余权限字段 422、他人申报 404、旧 revision 冲突。
- 管理员实际替换当前主职方案，固定旧角色版本保留不会跟随目录升级；独立 allow 明确选择，deny 保持。
- 注册及在职审批在写回执处注入异常：账号/任职/事件/通知不出现部分提交；正常重试成功。
- 同一个员工 Cookie 调用真实 `POST /api/injection`：变更前 201，转仓管撤销开单能力后 403。不是只检查按钮或模拟 auth.can。
- PostgreSQL 独立连接同时审批：一份成功、一份 409；同命令重放同回执。同时员工提交只保留一个 open 记录。
- 相同命令改 body 拒绝；管理员预览后失权拒绝；冻结阻断、离职使旧 epoch 申请 invalidated。
- 注册历史也按当前与未来任职、独立来源完整鉴权；驳回后换厂重新注册，不把旧未确认资料误当正式任职。
- outbox 明确按 kind 分发，投递失败重试不回滚已完成业务；无接收人保留真实待办并给出可诊断状态。

## 浏览器执行

使用已连接的 Browser/CUA，在 `127.0.0.1:5186` 管理员与 `localhost:5186` 员工的独立 Cookie 会话完成。后端为 `127.0.0.1:8016`，仅使用临时 SQLite 合成账号。

已执行员工申报→管理员同屏选内置方案→自动真实预览→明确风险勾选→确认回执→员工正式资料刷新。员工另一次使用键盘提交“工程资料与打样协调”后，正式岗位仍为“工程主管”，管理员队列出现新申报。历史账号在同页先核实新增/停止均为 0，再确认岗位保留权限；成功后待办数 4→3，回执停留并提供下一位。

另启动 `127.0.0.1:5187`、显式关闭新 UI 入口：默认 `/system/users` 确实回到旧人员中心，兼容 `/system/users/position-reviews` 仍显示真实申请并成功退回“岗位验收甲”的待办；员工会话随后读到对应退回意见，正式岗位仍为工程主管。回执截图 `screenshots/rollback-success.jpg`。回退测试服务和临时 PostgreSQL 已停止，未操作生产实例。

已验证：管理员用键盘选择办理方式、搜索和选择方案；移动端回队列焦点恢复到原人员；真实增权预览未勾选时禁用确认；列表/详情切换；方案搜索；个人资料入口；成功回执。403/409、预览过期、乱序返回与 5xx uncertain 在组件/API 测试中覆盖，未声称所有错误场景都逐一在浏览器注入。

| 请求视口 | 文档宽度 / scrollWidth | 主按钮下缘 / 视口高度 |
|---|---|---|
| 1440×900 | 1425 / 1425 | 884 / 900 |
| 1280×800 | 1265 / 1265 | 784 / 800 |
| 1024×768 | 1009 / 1009 | 754 / 768 |
| 768×1024 | 753 / 753 | 1010 / 1024 |
| 390×844 | 375 / 375 | 830 / 844 |
| 360×800 | 345 / 345 | 786 / 800 |

宽度差为浏览器滚动条。上述是实际 DOM 尺寸与截图，不是仅调用设置视口。390 宽增权风险栏也单独检查：高 237.7px，确认按钮下缘 830，小于视口 844。截图在 `screenshots/`，原始测量为 `viewport-evidence.json`。

原 IAB 缺少真实缩放和媒体偏好接口。用户明确授权独立 Playwright 后，真实 Chromium 200% 页面缩放和 reduced-motion 动态补验均已完成，见下方补验记录与 closure-browser-evidence.json。物理手机软键盘、真实 IME、屏幕阅读器仍未做设备验收，不能由这些软件检查外推。

## 性能测量

50 名合成人员、相同 created_at；分页 1/20/50 条均为 33 次 SQL，没有随每页人数线性增加的查询。连续 3 页共 50 个不同 key，无重复或遗漏。

最后一次本地测试：冷请求 1097.63ms，后续 20/50 条 58.32/41.61ms；另 10 次已热队列请求 P50 35.38ms、nearest-rank P95 39.93ms。样本小且是合成 SQLite 数据，不能外推生产性能。未建立代表性真实数据详情/预览 P50/P95 基线。

## 独立安全复核

使用 Codex Security security-diff-scan；冻结的修复前快照已完成扫描，发现中风险 1、低风险 1。分别为注册历史范围检查遗漏、前端有效任职时点变化未清空保护数据。均已修复，并有可复现回归与独立后续复核；前端不明结果恢复也保留原命令并继续锁定。

扫描为本次任务改动范围，明确排除了原有 connect.css 和 1684 个 test-artifacts 文件，因此整体工作树 coverage 为 partial，不能宣称全仓无漏洞。封存报告仍描述修复前快照，未改写成虚假的修复后扫描：

`C:/Users/匡树杰/.codex/state/plugins/codex-security/scans/royal-regent-nexus/17775d8fa89c39b69d82c0aee140741f2e73300f_20261013T052042Z_py6z9eno/report.md`

扫描工具汇总报告 token 总量 13,764,719（其中缓存输入 13,224,704，输出 52,609，5 个线程）；这是工具采集的上下文用量，不作为费用估算。

## 52 条规格追踪

详见 `acceptance-trace.md` 和 `acceptance-results.json`。`covered` 表示下列执行证据覆盖该条核心行为；`partial` 指有执行但不能视为整条规格完整通过；`not_run` 明确未执行。规格编号数量不是自动化测试数量。

## 剩余 8 条闭环补验（最终结果）

- 前端完整相关命令同上：**11 文件 / 86 passed**，6.20 秒。相对前轮新增 5 项：员工表单提交/取消/冲突焦点、冲突刷新期间换身份、迟到人员响应不得抢焦点。此前 16 项组件集是子集，不重复累加。
- `npm run typecheck:test` 与最后 CSS 修复后的 `npm run build` 均通过；帮助指纹 17 篇无 issues；`git diff --check` 通过。
- `IAM_TEST_POSTGRES_URL=postgresql+psycopg://position_test@127.0.0.1:55440/iam_v2_test .venv/Scripts/python.exe -m pytest tests/test_position_workbench_closure.py -q --tb=short`：**5 passed，102.93 秒**；这是 PowerShell 环境变量赋值加 pytest 的简写。新增业务测试累计 24 项，原 19 项的既有通过结果仍保留，不能说本轮重新执行了全部 24 项。
- `.venv/Scripts/python.exe -m pytest tests/test_system_position_catalog.py -q --tb=short`：最终 **7 passed，39.11 秒**。此前迭代暴露的过时数量/仓库排除断言均已解决；不修改业务授权以迎合测试。
- `.venv/Scripts/python.exe -m pytest tests/test_password_reset_workflow.py -q --tb=short`：**9 passed，103.69 秒**，覆盖批准不提前改密、同浏览器 claim、一次性完成/撤销会话、失效/重开、范围和并发。

### 本轮发现与修复

1. 员工表单的“取消”按钮缺少 type，原生 Enter 会触发取消。改为 `type=button`；编辑、取消、成功和错误焦点明确，空岗位 Enter 不提交，有效岗位 Enter 正常提交。
2. 选人异步 watcher 的迟到完成可抢走新人的输入焦点；409 刷新期间换身份可显示旧错误。使用 watcher 清理、viewer/存活复核；两项延迟响应回归及独立复核通过。
3. 200% 下 640×360 CSS 视口，固定 280px 底部滚动留白使保存按钮上沿被页头遮住。改为 `min(280px,30vh)`，按钮上下沿均命中自身，完整可见。额外 CSS 360/390/768 宽且真实 200% 的复验也通过。

本轮变更文件：`MyPositionPanel.vue`、`PositionReviewPane.vue`、`position-workbench.css`、两份前端组件回归、`test_position_workbench_closure.py`、过期目录测试及本目录证据。独立复核先发现上述两处异步问题，修复后无阻断发现；复核者只读审查，测试由主执行器完成。

### 浏览器 QA

环境：隔离 `localhost:5186` 员工、`127.0.0.1:5186` 管理员，API `127.0.0.1:8016`。浏览器插件可用，常规键盘/兼容流使用内置 Browser。因 IAB 不提供真实 page zoom/media emulation，只有获用户明确授权的 200% 与 reduced-motion 使用独立 Playwright CLI；新建专用配置目录，不读取日常 Chrome 资料。实际 200% 使用 Chrome 设置的“网页缩放”，不是 device scale 或 CSS zoom 替代。

| 检查 | 结果 |
|---|---|
| 页面身份 | 人员与权限、我的岗位与权限、注册审核与密码找回、调整权限职位均为对应实际路由 |
| 非空和框架覆盖层 | 真实人员/申报/方案/成功状态存在，无 Vite 错误覆盖层 |
| 控制台 | 15:43:51 最终刷新后管理员/员工均无新增 error/warn；15:03:58 恢复服务时员工旧标签的 HMR/动态导入日志已通过刷新消除。独立浏览器登录前 `/api/auth/me` 的预期 401 单独记录 |
| 200% | Chromium `cssVisualViewport.zoom=2`、DPR=2；640×360 无横向溢出；员工/管理员主要动作完整可见 |
| reduced-motion | matchMedia=true；进入、切换和成功状态的 `.pw-root` 子树无动画/非零过渡，成功标题获焦 |
| 键盘交互 | 员工修改→空值拦截→Enter 保存；管理员队列→radio 方向键→提交→成功→下一位→退回原因和提交，全程无鼠标 |
| 旧深链交互 | person 确认保留权限、registration 审批开通、access 独立授权保存、password-reset 驳回；普通员工旧 access 页不显示保护资料 |
| 截图 | `screenshots/zoom-200-*.png`、`reduced-motion-success.png`、`keyboard-*.png`、`legacy-*.png` |

原始测量与截图说明见 `closure-browser-evidence.json`。真实 Chrome 缩放使 Playwright 高层截图裁切坐标不匹配；最终缩放截图由同一获授权 Playwright 会话调用 Chromium viewport capture 保存，并逐张视觉复核。

52 条软件规格现为 **covered 52 / partial 0 / not_run 0**。这不是“52 个自动化测试”或生产上线证明。物理手机键盘/IME、屏幕阅读器与生产规模性能仍是独立边界。

最终隔离前端与 `/health` 均 HTTP 200；5186/8016 留作本地复核，55440 PostgreSQL 与独立测试浏览器已关闭。该轮隔离验收未修改默认业务/生产数据库；随后用户明确授权的日常本地启用结果见 migration-report.md，生产仍未修改。
