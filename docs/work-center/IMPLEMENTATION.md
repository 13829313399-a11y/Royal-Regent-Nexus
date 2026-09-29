# 事项工作台：实现、验收与迁移

依据用户提供的 `notification-action-center-codex-spec-2026-09-28.md`，在基线 `afdd8ddcbce568a5f38b6ad7d53332534c0c4295` 上完成本地开发、回归、独立审查修复、浏览器检查和隔离迁移演练。本文记录开发验收结果；Git 交付状态以对应 PR 为准。没有部署或迁移真实业务数据库。

## 当前能力与接入边界

| 来源 | 当前责任与结果 | 原业务入口 |
| --- | --- | --- |
| 啤办 | 主管/经理审核、驳回重填、执行厂开始生产、生产回填、待处理问题；开始/完成撤回、改派更新轮次；来源与执行厂区分别显示 | 工程啤办单、生产任务 |
| 内部报价 | 部门填写；v2 部门审核和最终提交；v3 指定审核人的整批审核只计一次，核验批次及计算快照；v4 不虚构旧审批；审核撤回/驳回恢复真实填写责任 | 对应报价 collaboration |
| 账户申请 | 注册审批、密码恢复核验；已批准等待申请人领取属于等待，过期退出；密码申请沿用目标用户完整当前/计划任职及附加授权范围 | 原注册/密码恢复工作区 |
| 供应商送货 | SENT 未收料、正式收料后的冲销更正；读过仍待收料；中心不执行入库或冲销 | 原 shipment 收料界面 |
| 任职/业务结果 | 任职更新、报价成果、生产结果属于知会；任职知会刷新本人上下文，不跳管理员用户页 | 本人上下文或授权源单据 |

3D、UV、喷油、订单中心、文件工具等尚未适配，本页不声称覆盖其待办。供应商门户账号不启动内部中心。

## 主要实现

- `/api/work-center` 提供同一数据库读取事务中的 summary、筛选总数、有限页、选中事项状态、服务器时间、授权边界、覆盖与核验健康状态。默认每页 30，最多 100；统计不依赖浏览器已下载数量，也没有默认日期截断。
- 源对象和当前 IAM 决定可见/可办性；普通管理授权不自动变成生产责任。当前查询不依赖投影已追平。适配器故障用 savepoint 隔离，返回 partial；不可核验来源不伪装为零。
- 四张表分别保存可重建责任投影、事件、按用户及员工身份周期隔离的个人状态、提醒偏好。原业务事务提交前同步受影响源的投影；轮次/关注版本避免旧已读吞掉新责任。事件分页使用时间与稳定 ID。
- 标读只确认客户端观察到的内容版本；稍后、置顶、跟进、归档只改变个人状态。活跃责任不可归档或手动完成。单项与批量共用每事项事务锁，批量在 savepoint 之外按固定顺序加锁；其他个人更改与偏好使用乐观版本。
- 旧通知 API 不再写共享阅读状态。仅在可以确定映射的事件/申请上同步 canonical 阅读；无法确认历史轮次的旧消息保留独立个人阅读，绝不把旧消息标读猜成新轮次已读。旧共享 status/read_at 保留在原表作为历史证据。
- `WorkCenterHost` 和 Pinia store 统一调度；铃铛、工作台及纸箱提醒复用有界数据。初次载入静默，跨页 Web Locks + storage 只领取一次相同关注版本；默认关声音。页面输入、深处阅读或详情打开时，新项以横幅提示，不插入当前位置。
- 401/403 清除内容，临时错误保留带同步时间的旧快照；账号/授权上下文改变后丢弃迟到响应。移动端 sheet、Esc/焦点返回、减少动效、上海业务时间均有对应处理。

主要文件：`backend/app/{api,models,schemas}/work_center.py`、`backend/app/services/work_center/`、`backend/alembic/versions/20260928_0126_work_center.py`、`backend/scripts/{reconcile_work_center,benchmark_work_center,seed_work_center_qa}.py`；`src/stores/workCenter.ts`、`src/api/workCenter.ts`、`src/features/work-center/`、`src/views/NotificationCenterView.vue`。已有 App、路由、旧通知消费端、啤办及纸箱页面做了对应接入。`PROJECT_MEMORY.md` 已更新长期契约。

## 已执行验证

环境：Windows 11，AMD Ryzen 7 5800H，约 16 GiB 内存，Python 3.14.6；所有数据库测试均使用隔离 SQLite。

| 检查 | 结果与证据 |
| --- | --- |
| `npm run build` | 通过，含应用 TypeScript 检查 |
| `npm run typecheck:test` | 通过 |
| 工作中心 store、纸箱页面、TopBar 回退、旧通知 composable、声音 composable 五文件 | 194 项通过；补充阅读位置保护、6 分钟失败恢复、批量期间新消息后，store 的 12 项重新全部通过（合计 197 个不同用例） |
| `pytest tests/test_work_center_api.py tests/test_work_center_migration.py -q` | 10 项通过；随后批量锁补充回归 1 项通过、重复重放及同快照并发补充 2 项通过；后端中心/迁移合计 11 个不同用例 |
| `pytest tests/test_internal_quote_whole_review.py tests/test_internal_quote_reviewer_withdrawal.py -q` | 23 项通过 |
| 啤办、密码恢复、送货目标回归 | 21 项通过，125 项未选中；另外带中心断言的正式送货/冲销两项复验通过 |
| 只读快照并发 | WAL 隔离库中，在 summary 查询结束后用另一连接完成源业务；同次 summary/总数/页面仍一致，下一次快照归零 |
| 幂等与历史 | 同一责任重复物化 100 次不增加事件；回填两次稳定；迟到旧申请通知不重开已结束责任；旧完成结论在撤回后被替代 |
| 独立审查 | 已修复审核驳回后漏计、同账号撤权后迟到响应、总务组织密码申请遗漏、PostgreSQL savepoint 内锁缓存失配等发现；真实 PostgreSQL 并发仍需现场复验 |
| `git diff --check` | 通过 |

上述命令是目标回归，不代表仓库全部测试通过。前端旧测试保留验证 UI 回退，新的共享状态另有独立测试。

规格用例对应：A01–A08 覆盖知会/审核/个人阅读与权限；A09–A16 覆盖跨厂、轮次、撤回、收料冲销、密码等待；A17–A27 覆盖幂等、迟到、旧数据、核验、个人版本及旧接口；A28–A34 覆盖身份变更、失权、网络恢复、游标、并发快照和 partial；A35–A40 由 store 测试及下面的浏览器验收覆盖。部分业务转换通过直接构造源状态验证适配器，同时保留原领域 API 回归；没有把构造状态当作生产用户验收。

### 浏览器证据

使用独立 QA 库（12 待办、1 知会）实际登录并检查 1440、1280、768、390 宽度。1440 为三列、1280 为两列、较窄视口使用详情 sheet；页面无横向溢出。移动端详情与铃铛 Esc 关闭后焦点返回触发项。

补充验收在同一隔离库新增合成责任、已审批历史和一个缺失来源，实际服务快照返回 112 项待办、1 条知会、1 项历史、partial 核验状态。知会/历史视图分别截图；手机详情验证长编号和长中文产品名换行，铃铛显示 99+ 徽标、112 的准确总数及部分来源未核验提示，无页面横向溢出。这些补充数据不参与之前 13 项迁移副本的对账。

- 筛选无匹配时仍保留总责任数；500 时保留已核实列表、显示错误和同步时间；403 后旧事项行清空并显示无法读取。
- 三个真实浏览器页面在受控快照响应下同时读取同一新增关注版本，Web Locks 可用，toast 数为 `[1, 0, 0]`，storage 中只有一次领取。此测试验证跨页仲裁；没有启用实际音频播放。
- 美国洛杉矶时区、reduced-motion 环境：业务时区仍为 Asia/Shanghai，上海截止显示不变，逾期数 1、今日 0，无页面横向溢出。
- 控制台检查无未解释的运行错误；注入 500/403 所产生的请求错误属于预期验收数据。

截图与日志保存在 `D:/RR/outputs/notification-action-center-20260928/`：

| 场景 | 图片 |
| --- | --- |
| 桌面工作台和详情 | `output/playwright/work-center-1440-detail.png` |
| 中等桌面 | `output/playwright/work-center-1280.png` |
| 平板详情 | `output/playwright/work-center-768.png` |
| 手机列表、详情、铃铛 | `output/playwright/work-center-390-{list,detail,bell}.png` |
| 空筛选、500、403 | `output/playwright/work-center-{empty,stale,forbidden}.png` |
| 知会与已完成历史 | `output/playwright/work-center-{information,history}.png` |
| 112 项与待核验来源 | `output/playwright/work-center-partial-high-count.png` |
| 手机长编号/中文名、99+ 铃铛 | `output/playwright/work-center-long-reference-mobile.png`、`output/playwright/work-center-high-count-mobile-bell.png` |

### 性能

数据量：10,000 活跃责任、100,000 历史事件，每页 30，并发 1，每组 20 个热态样本。完整查询计划保存于 `work-center-benchmark-http.json`。

| 范围 | P50 | P95 | 说明 |
| --- | ---: | ---: | --- |
| 服务快照 SQL + DTO | 218.33 ms | 349.59 ms | 首次 468.71 ms；4 次 SELECT/WITH，不含鉴权、HTTP、网络 |
| 带鉴权 ASGI 请求 | 232.97 ms | 239.81 ms | 在前组之后测量，缓存已热；包含路由、鉴权、查询、序列化，不含 TCP、代理与浏览器 |

此前与其他验收并发运行时服务 P95 为 579.87 ms；独立空闲组 P95 为 346.74 ms。保留各组原始报告，不把单线程热态结果当作负载容量承诺。优化点是复用当前来源 CTE、仅扫描已结束历史投影做 anti-join、合并核验统计；未删真实数据或缩小合成规模。

## 迁移演练与运行步骤

`migration-rehearsal.db` 是 QA 库副本，先恢复到 0125 结构，再通过真实 `alembic upgrade head` 路径升级。结果：revision=0126、integrity_check=ok、foreign_key_check=[]，抽查用户/会话/啤办/报价/注册/通知表前后行数一致。首次回填创建 13 entry/13 event，第二次 created=0、updated=0、unchanged=13；三次盘点 canonical SHA-256 一致。

证据：`migration-{before,after}.json`、`migration-upgrade.log`、`rehearsal-{dry,first,second}.json`。已经有个人阅读的 QA 库也执行了两次回填；读取状态不会复制或重置。所有旧业务表与通知原记录保留。

上线应由实际运行环境执行以下顺序；下列是操作步骤，本次没有对真实库执行：

1. 确认运行时 DATABASE_URL、当前 Alembic revision 和部署版本，停止写入；备份数据库并核验完整性、外键、关键表行数和备份哈希。先在备份副本演练。
2. 在 backend 下为当前进程显式指定副本 DATABASE_URL，运行 `.venv/Scripts/python.exe -m alembic upgrade 20260928_0126`。不要靠应用启动自动创建旧库缺失结构。
3. 运行 `.venv/Scripts/python.exe scripts/reconcile_work_center.py --database-url <明确的数据库URL> --report <盘点文件>`；检查来源计数、坏 payload、孤儿、未支持类型及 canonical 摘要。
4. 对通过演练的目标库执行同一迁移，再运行上一步并加 `--apply`，重复一次核对 created/updated 为零、canonical 集合稳定。核对旧业务、个人状态、事件数量及库完整性。
5. 启动兼容后端与新前端；按真实角色检查跨厂审核、指定整批审核、密码申请、正式收料/冲销、撤回及失权。仍有未核验来源时保留 partial 提示并处理其源数据。

回退：设置前端构建变量 `VITE_WORK_CENTER_ENABLED=false` 恢复旧铃铛，保留兼容后端、四张表及个人状态；不回写旧共享已读。不要直接降库删除阅读记录；downgrade 遇到个人状态/偏好会拒绝执行。

## 未验证边界

- 没有连接真实 PostgreSQL；方言分支与锁边界已审查，但需要在实际数据库验证查询计划、隔离级别和并发。
- 没有执行真实业务数据盘点、生产迁移、生产角色验收或真实手机设备验收。当前截图来自桌面浏览器视口；长时间失败恢复使用可控时钟推进 6 分钟，验证退避重试、旧快照保留与恢复后结束事项清除，并未实际等待五分钟断网。补充结果见 `work-center-store-supplement.log`（12 项通过）及 `work-center-typecheck-supplement.log`。
- 旧通知轮次无法可靠恢复时保留原始历史证据，不伪造逐人阅读或新的完成结论。未知来源以盘点/partial 暴露，需真实库验收确认其数量。
- 代码、测试、迁移与本报告已形成可审阅的开发交付；Git 交付按单独授权执行，生产发布尚未执行。
