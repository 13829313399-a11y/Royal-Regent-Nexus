# 成员协作 R1 实施与验收

依据 2026-10-09《成员协作、私信与个人空间》规格。本文记录工程契约、隔离验收和发布边界。用户已授权分支提交、同步 main、PR 合并和生产更新；线上结果以发布回执为准。

## 实施顺序

1. P0/P1：集中内部成员资格，IAM 实时组织投影，目录生命周期修复；个人名片、偏好、常联系人。
2. P2：持久一对一会话、幂等消息、身份绑定事件游标、未读与同步。
3. P3：局部 `rr-connect` 视觉、目录/名片/个人空间/消息页及辅助面板协调。
4. P4/P5：附件、业务引用、草稿 CAS、撤回、私人感谢和消息偏好。
5. P6：隔离数据库迁移、事务/身份回归、构建、浏览器及真实代理验证。

## 已核实的基线

- 开发起点 HEAD：`5a564addef126d0dd2696de1e63fa9e794db2a42`；迁移头：`20261009_0150`。
- Cookie 会话与 IAM resolver 是身份权威；`group` 是浏览范围，`group-management` 是 functional_unit。
- 兼容资格排除 supplier-only 权限集合；有有效内部任职或混合内部业务权限的账号须独立覆盖测试。
- 私有所有权为 `(user_id, employment_epoch)`。普通刷新/调岗保留，离职复聘不继承。
- 数据库锁顺序：IAM mutation → 排序用户流 → 会话 → 排序附件。锁必须在修改 ORM 对象前取得。
- 不重置实际员工或业务记录，不改写已发布历史迁移，不纳入既有未跟踪测试产物。

## 当前交付状态（2026-10-10）

P0–P5 核心代码已接入真实 API；P6 完成自动化、独立评审、浏览器、Linux 容器及完整生产恢复副本验证。下方记录补充证据和用户明确接受的未验收项；Git 与线上发布状态以最终发布回执为准，不能将工程验收理解为现场设备验收全部完成。

## 实际实现与代码入口

| 范围 | 交付 |
| --- | --- |
| 目录与身份 | `backend/app/services/internal_members.py` 集中内部资格，排除无有效内部任职的供应商专用账号；复用 IAM 决策及批量来源，避免按人查询。directory API/schema/service 提供真实组织 catalog、详情、稳定排序、过滤后计数与展示白名单 |
| 数据与 API | `backend/app/models/collaboration.py`、`schemas/collaboration.py`、`api/collaboration.py`、`services/collaboration/core.py` 实现独立协作域 |
| 附件与业务引用 | `services/collaboration/assets.py`、`maintenance.py`、`references.py`；两个适配器为啤办单 molding_sample、内部报价 internal_quote；实际业务详情添加 BusinessShareButton |
| 前端核心 | `src/api/collaboration.ts`、`src/stores/messaging.ts`、`src/features/collaboration/` 实现名片、目录、消息、感谢、事件消费和局部样式 |
| 页面与入口 | `/people`、`/me`、`/messages`；TopBar、AccountMenu、App 和 router 接入能力控制；原目录页/抽屉包装新组件 |
| 生命周期 | useDirectoryQuery 统一取消/请求序号/身份/可见性；useDialogFocus 提供计数 inert、焦点恢复；panelCoordinator 协调曜灵、目录、账号、聊天及业务模态 |
| 可见模块 | useVisibleModules 抽取主页最终可见性规则用于个人快捷方式；更新对应 assistant-help 源码索引 |
| 配置与长期事实 | backend config/db/main、Compose 私有资源卷、Nginx 专用 events location；PROJECT_MEMORY、DESIGN 原位更新 |

### 行为契约

- Cookie 与当前 IAM resolver 为身份权威。group 仅为浏览根；group-management 为 functional_unit。账号组织、部门和职位优先实时身份，调岗不回读旧 profile。
- 名片、偏好、联系人、会话、草稿、感谢、游标按 user_id + employment_epoch 归属；管理员不能旁路查看第三方私信。
- 规范双方会话唯一；写入按 IAM mutation → 排序用户流 → 会话 → 排序附件锁。消息和双方事件原子提交；client_message_id 同键同内容返回同条，同键改内容/会话冲突。
- SSE 与 HTTP sync 共用持久游标，验证身份、floor/head 和分批进度；短快照查询后释放数据库事务，再等待。客户端先恢复实体再推进游标，隐藏暂停、恢复补拉、失败轮询。
- 回执只在主动操作或获得焦点的可见阅读区域推进；关闭回执后实时和历史投影均不泄露阅读位置。撤回 120 秒内可用，消息/引用/附件/事件回放统一墓碑。
- 草稿 800ms 防抖、单飞、CAS；多端冲突保留本机输入。发 A 期间输入 B，A 的成功响应不会删 B。PATCH 丢响应时回读确认云端版本；发送后云稿未能清空须明确选择，重放事件不能恢复已发送正文。结果未知时保留原发送标识。
- 会话摘要批量加载成员、最新消息、回执偏好和未读；文本会话页 1/10/30 条均固定 7 次 SELECT。感谢收件箱的私人置顶参与服务端 keyset 分页；发件人仍看不到收件人私有状态。
- 首未读、搜索跳转与最新页可形成历史空档，加载更早会补齐空档。按可见消息恢复滚动锚点；切换、往返会话或等待期间继续滚动均使旧锚点失效。补历史不计为新消息。
- HTTP 握手或降级轮询收到 RESET_REQUIRED 均自动重新 bootstrap，保留本机未发送内容；半开流 35 秒无数据后取消并降级。
- 偏好保存防重复提交；等待期间继续编辑会保留新内容，只推进已确认版本，并明确提示新修改尚未保存。
- 图片 15 MiB、文档 25 MiB、每条最多 6 个/合计 75 MiB；实际内容校验、私有路径、逐次下载鉴权。24 小时暂存到期清理，附着与清理共用锁，已发送文件保留。
- 业务引用每次读取重新核验当前权限；业务引用与附件是互斥消息类型，切换时提示处理已有内容，不能静默丢弃附件。异步核验绑定原会话及身份。
- 每小时维护暂存及 30 天事件重放窗口并推进 floor；不会因此删除消息历史。
- 四主题预览、自述、常联系人、消息偏好、私人感谢已接真实 API。感谢已查看/置顶/隐藏属收件人私有状态，不改变 DM 未读或工作中心责任。
- 慢筛选、关闭重开、卸载、同路由 query、账号切换受请求归属保护；旧头像响应不覆盖新账号。

## 新接口与迁移

接口前缀 `/api/collaboration`：capabilities、me/profile、me/preferences、me/contacts、bootstrap、sync、events、conversations/direct、会话 messages/draft/read/preferences/search/attachments、按 client ID 查询消息、撤回、私有附件、references/preview、appreciations。

迁移 `backend/alembic/versions/20261010_0156_member_collaboration.py` 显式创建 11 张表，不导入当前 ORM：member_social_profiles、member_preferences、member_contacts、collab_direct_conversations、collab_conversation_members、collab_messages、collab_user_streams、collab_user_events、collab_attachments、collab_drafts、member_appreciations。

后端 `COLLABORATION_ENABLED=false` 默认关闭，前端 `VITE_COLLABORATION_ENABLED` 控制入口，不能绕过服务端资格。既有库开启前必须显式迁移；缺协作 schema 时拒绝开启。Compose 私有卷与 Nginx 关闭 SSE 缓冲/压缩的配置已写入，本机 Windows Nginx 已实测；Linux 容器和生产代理仍需现场验收。

## 自动化与迁移结果

| 实际验证 | 结果 |
| --- | --- |
| 前端定向回归 | 最终 13 文件、161 项通过，命令见下 |
| npm run typecheck:test | 通过；应用类型检查也通过 |
| npm run build | 完整通过，含 16 篇 assistant-help 索引、vue-tsc、Vite、image-translation 和发布边界；有体积/第三方注释警告 |
| pytest tests/test_collaboration.py tests/test_user_directory.py tests/test_identity_acceptance.py -q --disable-warnings | 29 项通过（协作 9、目录 6、IAM 14） |
| PostgreSQL test_collaboration_postgres.py | 7 项真并发/进程退出用例通过，修复后重新验证 |
| SQLite 全链 Alembic 演练 | 隔离空库 → 0151 → 0150 → 0151 成功；最终 integrity_check=ok，外键 0 问题，新增表 11 张 |
| PostgreSQL 全链 Alembic 演练 | 新建隔离空库 → 0151 → 0150 → 0151 成功，另一个验收库使用完整迁移后装载合成数据 |
| 迁移保护与配置 | 非空协作表拒绝 downgrade；唯一约束测试、Compose YAML/资源卷解析通过 |
| git diff --check | 通过，仅换行格式提示 |

前端实际命令：

```text
npm run test:unit -- src/features/collaboration/__tests__ src/components/directory/__tests__/MemberDirectory.spec.ts src/components/layout/__tests__/accountMenu.spec.ts src/components/layout/__tests__/topBarFactories.spec.ts src/features/assistant/__tests__/panelInteractions.spec.ts src/views/__tests__/moduleCenterFactoryScope.spec.ts src/router/__tests__/peopleDirectoryRoute.spec.ts src/views/__tests__/moldingSampleRuntime.spec.ts src/composables/__tests__/usePresenceHeartbeat.spec.ts src/views/__tests__/internalQuoteDeskLayout.spec.ts
```

后端协作用例覆盖会话/发送幂等、管理员和第三人拒绝、epoch、草稿 CAS、205 事件分批/错误游标、回执隐私、撤回重放、附件所有权、混合身份资格、两个业务引用的有权/无权/错厂区、暂存清理和附着文件保留。前端增加慢筛选、关闭重开、身份迟到响应、发 A 留 B、SSE UTF-8/CRLF 分片、实体恢复失败不推进游标、旧头像响应、实时任职及引用草稿保护测试。

### 基线测试修复

- 内部报价布局测试不再限制 `measured` 参数类型拼写，继续验证四位小数契约，9 项通过；SectionForm 业务源码未改。
- IAM 回滚测试的原注入条件依赖 `db.new`，被更早的 work-center before_commit flush 清空而失效。改为检查本事务已 flush 的 receipt 增量，并断言故障恰好注入一次，保持真实 audit/outbox/receipt 回滚与同预览重试验证；IAM 全套 14 项通过。

## 真实浏览器证据

Browser plugin not available；使用 Playwright CLI 与真实 Chrome。本机 `http://127.0.0.1:5186` 代理 `127.0.0.1:8126`，独立 SQLite，合成 Alice/Bob 身份；未接生产。

| 检查 | 观察结果 |
| --- | --- |
| 页面身份/非空/框架遮罩 | people/me/messages 的标题、路由及内容正确，无框架报错遮罩 |
| 双账号与幂等 | Alice 页面发送、Bob 独立 Cookie 读取/回复、Alice 收到；同发送标识只保留一条 |
| 四主题与失败恢复 | 切换主题；模拟保存 503 保留自述，解除故障后保存成功 |
| 私人感谢 | 查看、置顶、隐藏、显示隐藏及恢复成功；修复快速连点导致的版本竞争 |
| 图片 | 文件选择、暂存、发送、预览，Escape 关闭并恢复焦点 |
| 已提交响应丢失 | POST 在服务端提交后丢弃响应，页面恢复；按 client ID 核对仅一条；预期 ERR_FAILED 有记录 |
| 输入法事件保护 | compositionstart/Enter/compositionend 下不发 POST；不等同实机中文输入法/手机软键盘 |
| 目录弹窗 | Escape 关闭并恢复顶栏触发焦点 |
| 账号弹窗 | 头像预览 Escape 返回菜单头像；资料编辑 Escape 返回顶栏账号入口；无遗留 inert 锁 |
| 窄屏 | 桌面截图；390px 个人空间、320px 目录及聊天检查，无所查页面水平溢出；不等于全宽度矩阵完成 |
| 控制台 | 登录前 401、故障注入 503/ERR_FAILED、重启期 502 已解释；未观察到应用 JS 异常 |

本机证据在 `%TEMP%\rr-connect-20261010`：directory-desktop.png、directory-320.png、my-space-desktop.png、my-space-mobile.png、appreciations.png、chat-mobile-final.png、chat-attachment-recovery.png；构建/迁移日志 build-final.log、migration-forward.log。截图内容均为合成数据。本轮临时服务和浏览器验证结束后已停止，截图不依赖服务器继续运行。

## PostgreSQL、代理及补充浏览器验收

隔离目录 `D:\RR\collaboration-qa-20261010-acceptance`。复查发现本机已有便携 PostgreSQL 16.15 与 Windows Nginx 1.30.5；此前“未发现执行环境”的判断已纠正，未安装新依赖。新建 PGDATA 只监听 `127.0.0.1:18542`，测试库为 `rr_connect_acceptance` 和 `rr_connect_migration`，与既有业务库及生产完全分离。155 名合成成员另加种子管理员、35 个会话、7,000 条历史消息；六厂区、总务、多任职、未登记组织、同名、缺头像、长职位均有合成覆盖。

PostgreSQL 用例通过 `COLLABORATION_TEST_POSTGRES_URL` 显式启用，拒绝非回环地址及其他数据库名称；每次只创建并清理自己的随机 schema。覆盖同时建会话/同键发送、阻塞事务提交与回滚序号、读/发/撤回与草稿 CAS 竞争、附件发送与过期清理竞争、子进程提交后退出再恢复。

实际入口 `http://127.0.0.1:8197` 使用 Nginx，API 为独立的 `8127`，最终浏览器读取完整构建产物 `dist`。SSE location 从仓库配置提取，仅替换测试上游；Windows 结果不代表 Linux 容器现场。

| 检查 | 实测结果与证据 |
| --- | --- |
| 目录与规模 | 156 总人数、每页 36；同名成员按组织消歧，数千历史不整段返回 |
| 摘要性能 | 10 次 bootstrap 中位 41ms、最大 539ms，每次 30 个摘要；不是生产压测承诺 |
| 4 条并发 SSE | 首帧 53–63ms；发送请求起点至 4 端接收为 1.073–1.134s，proxy-results.json |
| 心跳/会话终止 | 下一心跳 15.795s；冻结后 1.012s 终止，Cookie 过期同样终止；数据库 idle-in-transaction=0 |
| 代理超时/半开 | 额外回环端口将 Nginx 超时缩为 2 秒，实测 2.011s 断开且首帧已到达；客户端 35 秒无数据取消及计时器释放有回归测试 |
| API 重启 | 强制终止并重新启动本次 API，页面重连、草稿保留、重新发送成功；381,596 字节已发送附件 SHA-256 前后一致，restart-verify.log |
| 宽度与渲染 | people/me/messages × 320/375/640/768/1024/1366/1920，共 21 组无页面水平溢出、无框架遮罩；有截图，browser-matrix.log |
| 历史/断线 | 实际浏览器补齐 206 条历史且连续无重复；离线继续编辑、联网后发送成功，browser-recovery.log |
| 偏好/提醒 | rich/simple/off 保存生效；系统 reduced-motion 下协作区运行动画 0；DND 不弹提醒；4 个真实标签模拟同时可见，Web Locks 只允许 1 个提醒 |
| 完整业务页 | 啤办、内部报价、3D 打印页账号菜单可打开并进入协作入口；Escape 关闭，无遗留 inert；browser-fullpages.log |
| 控制台 | 最终产物流程无应用 pageerror；预期断网、重启及测试冲突错误单独记录。早期 Vite 经代理的 HMR 握手错误在切换构建产物后消除 |

短视口 `683×450` 下输入可操作；此项仅为缩放等效布局与键盘占用空间模拟，不能写成真实 200% 浏览器缩放或手机软键盘通过。前端断线、缩放与动效脚本、截图、请求日志均在上述隔离目录。

## 独立评审闭环

独立只读评审发现并复验修复：草稿未知提交结果恢复旧正文、历史跳转造成中间空档、会话摘要 N+1、老感谢卡置顶丢出首屏、HTTP 握手/轮询游标过期不自愈。追加复审进一步验证了发送后 draft.updated 竞态、滚动锚点（同会话、切换、往返、等待中继续滚动）及补历史误报新消息的修复。浏览器发现的偏好重复保存/覆盖新编辑问题也经独立真实组件复验。最终审查范围内无剩余明确问题。

独立评审使用合成数据和真实组件内存挂载，并未代替上表的真实数据库/代理/浏览器验证。

## 发布与回退步骤

生产切换按以下顺序执行，并将结果保存在发布证据目录：

1. 目标数据库恢复副本演练，核对迁移头、完整性和业务记录数量；备份数据库及私有附件卷。
2. 停写后在后端实际环境执行 `python -m alembic upgrade 20261010_0156`，核对约束及无关数据不变。
3. 配置私有持久目录、开启后端开关、部署前端和 SSE 代理；验收 Cookie/长连接/冻结终止/重启及文件卷后再开放。
4. 回退优先关闭功能并保留表和文件；任一新增表非空，迁移会拒绝破坏性 downgrade。

## 早期验收边界（补充结果见下方）

- Linux 容器和目标生产代理的上线验收、容器私有持久卷重启；本机证明的是 Windows Nginx 与 API 进程重启后同一私有目录可读。
- 四标签同时运行真实外部 AI 长回答及真实设备 3D 实时流；本轮验证 4 条并发消息流、4 标签提醒争用，以及 3D 页面账号入口，未调用外部模型或真实设备。
- 实机中文输入法、手机软键盘、真实浏览器 200% 缩放；composition 事件保护、21 组宽度和短视口模拟已有证据。
- 账号 light、compact/obsidian 有组件回归，三个业务 fullPage 已实测 light；其余宿主页面/主题组合及真实音频输出仍需对应设备验证。

以上为先前阶段的边界记录。用户后续授权新分支提交、同步 main、PR 合并和上线；下方补充验收覆盖前文已完成的项目，未完成项仍明确保留。

## 授权发布补充验收

发布分支同步 `origin/main` 的 `97c1ec87` 后，原未发布协作迁移改为 `20261010_0156`，接在 `20261010_0155` 之后；切割、仓库、箱唛既有迁移未改写。补齐上游箱唛渲染所需的生产 `reportlab>=4.4,<5` 依赖；Linux 候选使用 4.5.1 并通过 pip check。

- 合并后前端 15 文件 / 170 项通过，完整 build、应用及测试 TypeScript 检查通过。后端定向 32 项通过，另一个迁移测试因文件改名的旧路径失败，修正后单独复跑通过；PostgreSQL 并发 7 项通过。
- HTTP 随机 ID 统一使用 createRandomUuid。Docker 构建正式传递前端开关。无 Web Locks 时改用 IndexedDB readwrite 事务，真实 Chrome 四标签同时争用只出现一个提醒。
- 在独立 Chrome 配置的“网页缩放”选择 200%，原有 125% Windows 显示缩放下 devicePixelRatio 从 1.25 变为 2.5。people/me/messages 实测 CSS 视口 518px，均无水平溢出，私信可发送；此处是实际浏览器缩放。
- Linux 独立 API 容器、独立持久卷重启后，草稿及附件保留；双方仍可下载，666 字节 PNG 的 SHA-256 前后一致。此前 Windows 重启验收的 381,596 字节附件结果仍保留。
- Linux Nginx 使用实际 SSE 配置，HTTP 200、事件流类型正确，重复验证首帧 14–17ms、30 秒持续心跳正常。Linux 后端定向 32 项通过，旧迁移测试路径修正后该项单独通过，共 33 项。
- 10 个代表性真实宿主页面的账号入口、我的空间链接及 Escape 关闭通过，无残留 inert；包括实际面料仓、半成品仓路径。light/compact 使用真实宿主，未被当前宿主采用的 obsidian 保留组件契约测试。
- 浏览器实际 AudioContext 运行、两个振荡器与非零波形通过；这不能证明现场扬声器听感。
- 完整生产 PostgreSQL 备份（包括全部历史打印机状态事件）已恢复至独立演练库，0152 → 0156 迁移后原有表的记录数、内容摘要和列定义一致；无历史事件省略。
- 恢复副本启动核对覆盖 358 张受保护表：仅新增上游切割模块的 6 个权限目录及相应说明；全部原有权限记录、员工授权、业务记录摘要不变，新增说明逐字段符合代码定义。

证据目录：本机 `D:\RR\outputs\collaboration-release-20261010`，服务器 `/opt/royal-regent/builds/collaboration-20261010` 与 `/opt/royal-regent/backups/collaboration-20261010`。生产切换另行执行最终停写备份、原有记录摘要比对、镜像哈希和健康检查。

用户明确接受以下项目保留为未验收并继续合并上线：实机中文输入法、手机软键盘、实际扬声器听感，以及四标签真实外部 AI 长回答与真实 3D 设备实时流联合运行。后一项启动命令被自动审批拒绝，仅返回 blocked by policy；没有把合成事件或单项流验收计作真实联合负载通过。
