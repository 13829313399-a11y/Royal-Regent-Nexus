# 分离复审与修复记录

## 当前复审与补验

- 九条帮助扩充对照实际服务、schema、权限检查和路由；总览步骤只声明定位总览，未承诺逐按钮高亮。16 条源码指纹校验通过，范围见 HELP_COVERAGE.md。
- 旧报价测试改为断言现有五参数调用；供应商路由测试核对新采购页/收货/供应商参数；注册测试仍要求 AuthUser flush 先于依赖申请，忽略无内容的提前 autoflush。前端全量 2018 项通过。
- 六项迁移断言已修正：启动仍必须拒绝未迁移数据库；采购权限改为准确十项集合；0101 的 downgrade/upgrade 往返限定到该版本，避免跨越其他迁移禁止的回退。六项重测通过。没有削弱数据库启动门禁或修改生产迁移。
- 真实 NVDA 三个阶段各播一次；真实 200% 页缩放与 Chromium 24px 字体边界通过。截屏改用实际 DIP 视口，避免截图 API 在页面缩放时截掉右侧。
- 合并前后端全量在 25% 中止，原因是源码切换后不能继续算作同一版本回归；纸箱等模块已出现失败，诊断日志保留。34 项纸箱诊断为 29 通过、5 失败：两项 FakeDB 物料缺少当前必需的 `dimension_unit`；一项通知个人处理状态仍期待旧的 409；一项并发确认遇到当前文件作业准入的 429；另一项解析 429 可能受到并行诊断共用系统临时锁影响，不能认定为产品缺陷。后续诊断执行器改用独立临时目录隔离文件锁，不绕开产品并发限制；未改纸箱业务实现或这些断言。新全量结果不能用旧专项结果替代。
- 用户充值后，原配置七次真实上游请求完成多轮、视觉、思考加帮助工具、停止和历史恢复，七项浏览器检查通过且无页面脚本错误。只使用隔离库和合成账号，未读取或发送真实业务数据。证据目录为 `D:/RR/assistant-closure-20261008/`。
- 真实图片流程发现同图重传不触发 change：文件选择框保留上次值。`AssistantPanel.vue` 在取得文件列表后重置输入值，修复后上传→移除→同图重传→真实识别通过；助手前端 16 项专项、测试类型检查及完整构建通过。测试脚本另修正新建/选择会话后的异步等待，恢复时跳过已经成功的收费回合。

## 初次模型接入与历史复审

2026-10-08真实模型接入补充：一次授权请求成功，但结束时暴露HTTP异步迭代器关闭顺序警告。已用本机loopback服务复现，并为HTTP字节流和SSE帧增加显式关闭；新测试修复前失败、修复后通过，API及生命周期相关回归17项通过。详见[模型连接记录](MODEL_CONNECTION.md)。以下保留初次开发复审结果。

本轮由同一开发代理在首轮实现/测试后切换到单独审查轮次，并通过失败注入和浏览器重新验证；未虚构外部 reviewer 或代理审查。

| 问题 | 修复 | 重测证据 |
|---|---|---|
| 工具动态引用没有完整入库，身份范围改变后旧工具内容可能仍可见 | 工具结果与引用同事务保存，历史/导出/后续模型上下文均按当前受众过滤 | `test_tools_roundtrip_citations_audience_and_unknown_usage` |
| 工具多轮中缺失用量会显示不完整合计 | 任一轮缺失即 unknown/null；预算保留保守预留 | 同上及 budget/retention 专项 |
| 上传文件先落盘、归属记录尚未提交时崩溃会留下孤儿文件 | 先提交清理记录，再在受锁事务写文件；发送时复查大小和 SHA-256 | images/cleanup 专项，文件占用删除重试 |
| 首包前停止调用快照恢复会替换正在使用的增量缓冲 | lookup 只找 run ID，保留本地消息；并修复切回活动会话时重复显示 | `identityLifecycle.spec.ts` |
| 手机收起面板会连同引导隐藏；背景 inert 时无法列出目标 | 面板显示与引导显示分开，列语义 ID，定位时重新验证可见性；失败停止引导 | `mobile-guide.png`、browser acceptance、anchor tests |
| 窄屏按下入口时通用按钮 transform 覆盖其定位 | 入口排除按下位移 | 七尺寸截图和真实 click 回归 |
| fullPage 注塑用 URL 厂区，助手却取全局厂区 | 跟随页面厂区契约；3D/UV 固定华康 A | factory context unit case、`surface-injection.png` |
| 历史按随机 ID 排序 | 按最近更新时间及 ID 做游标分页 | 新会话/改名/分页 API与浏览器验收 |
| 私有 JSON 接口没有统一禁缓存标记 | 所有 `/api/assistant/` 响应 private,no-store | API headers 专项 |
| 空预算/保留期缺乏明确定义，附件缺少生产持久卷 | 空值 None；共享预算计数跨删除保留；有界清理；API 独立 assistant-assets 卷 | budget/retention 专项、Compose静态结构验证 |

## 与本次修改无关的全量测试失败

全量前端首轮有 13 个 5 秒超时；限制为 2 个 worker 后这 13 项通过。另 3 项 `InternalQuoteHairImport.spec.ts` 断言仍失败：测试预期 confirmImport 三个参数，当前组件传五个参数（末两项 undefined）。组件与测试的工作树 blob hash 均与基线 HEAD 完全一致：

- `InternalQuoteSectionEditor.vue`：`299d9ea342403724e850c2603d17e3775e36fcea`
- `InternalQuoteHairImport.spec.ts`：`c6457b3bd70f418492a5864c745b6a046edbefc5`

本次未改动报价导入实现或其测试，不把这三项写成通过。原始失败和复跑日志均保存在验收目录。

完整 `test_auth_api.py` 结果为 58 通过、1 失败：`test_register_flushes_new_user_before_registration_request` 假定第一次 flush 只包含 AuthUser，但实际先记录到空集合。注册 HTTP 本身为 200。使用 `git archive HEAD backend shared src` 导出**未修改基线**到隔离目录，以同一 Python 环境运行该单项，18.82 秒后得到相同失败。证据：`auth-baseline-repro.log`。未改动认证实现或这个断言。导出的临时基线源码副本清理被自动审批策略拒绝（`blocked by policy`），因此保留在证据目录，未改动业务数据；Vitest 的 include 明确限于根 `src/**/*.spec.ts`，不会把该副本作为前端测试输入。

最终新增专项：后端18项、前端16项通过；跨进程 PostgreSQL 与 Nginx 33秒流验证通过。共识别并保留4个基线断言失败（前端3、后端1）。真实模型、Docker干净镜像、手机实机、真实屏幕阅读器和200%系统缩放不在已通过范围。
