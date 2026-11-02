# 曜灵 V3 持久运行

后续运行指标、订阅确认和私有反馈由新迁移 `20261026_0177` 扩展，见 [运行统计与私有反馈](OPERATIONS.md)。本文件的原核心验收记录以 0176 为界，不应与后续检查相加或替换。

此文描述当前工作树实现。默认 `ASSISTANT_DURABLE_RUNS_ENABLED=false`；现有 QA 后端尚未加载新代码，真实 V3 浏览器断线验收和 PostgreSQL 实际迁移仍未完成。

## 执行与订阅

显式协议 `protocol_version=3` 的 POST 在同一事务内保存原 run、两条消息及 execution 队列记录，返回 202 和 run_id。重复相同请求复用原 run，不同内容仍返回 409。v1/v2 继续原 SSE 路径，canonical hash 不变。只有开关、显式迁移及当前进程管理的 worker 全部就绪时，capabilities 才声明 V3。

应用 lifespan 管理单实例 worker 和数据库队列，不引入 Redis。claim 原子更新随机租约 nonce、worker ID 和递增 fence。执行不依赖 HTTP 订阅；收起、换视图和断开订阅均不能重新执行它。未开始的队列任务可以在原截止时间内重启接手。已发出但未完成的供应商步骤不能续算或自动重发；进程崩溃后保存持久部分，租约到期进入 interrupted。显式重试创建带 parent_run_id 的新 run。

execution 仅保存原生 auth_session_id 引用，既不保存 Cookie、token、token hash，也不保存模型密钥。HTTP cookie 验证建立该引用，客户端不能选择它。worker 每次鉴权都复用原生会话状态、期限、账号可用性、强制改密及当前身份构建，再核对原 owner、任职周期和页面上下文。注销、撤权与周期变化不产生新的授予规则。

每个预定 provider step 在任何网络迭代前提交唯一 `(run_id, step_id)`。再次发出同一步会失败，搜索与综合等不同步骤仍可正常继续。请求 ID 和 usage 到达时及时落盘。新步骤开始时原子清除上一阶段的已知总用量；新阶段未知时不能沿用旧数值，更不能记零。保留全局 UTC 日预算、保守预留及原来的历史账目，不做自动付费重试。

## 事件与私有读取

事件唯一键为 `(run_id, seq)`，在原消息 checkpoint 的事务内分配序号并保存完整当前内容。取消和完成共享终态写锁；终态后拒绝旧 worker 的 checkpoint、事件及步骤更新。崩溃不会丢失已经落盘或已通过持久订阅显示的文本，也不会拼接两次已有前缀。

`GET /api/assistant/runs/{run_id}/events?after_seq=N` 只读取后续事件，不执行生成。每批重新验证当前登录、owner、任职周期及全运行已暴露来源的并集，适用于正文、标题、数量、工具结果及来源。来源从后续快照裁掉也不能解除旧事件的可见性依赖；历史快照及成果复用同一依赖。来源检查在释放写锁后执行，新增依赖在发布前再核对，避免慢读取阻塞取消。

订阅最长 25 秒，客户端以相同 run_id/cursor 重新 GET。重复事件忽略，序号缺口先读原 run 快照，再从其原子 event_seq 恢复。GET 网络失败最多退避重试五次，不再 POST。接收状态不明时只查询原 client_request_id。已知权限变化立即清除受影响正文、标题、草稿和来源层，停止相应订阅；一般身份刷新和无资料依赖的普通聊天仍保留。

## 预算、停机和回退

V3 保存 admission 的预算及非密钥连接指纹。配置变化不能提高已接收任务的输出、上下文或轮数上限，也不能静默换模型继续原 run。每步时限默认 300 秒，总时限仍使用原配置，排队时间计入原截止时间。只读业务工具超时后的迟到结果不能写入已终结运行。原 v1/v2 使用原总时限。

新运行遇到真实 `finish_reason=length` 时，在原模型文字之外保存 output_limit 提示；历史和授权导出包含该提示。不会从旧 token 数反推终止原因，也不会补写旧回答。

迁移 `20261026_0176` 仅增加 executions、run_events、provider_steps 三张私有表；启动 create_all 仍排除全部 nexus_assistant_ 表。Alembic env 识别新 head 并保留既有 native schema 校验，不改已应用迁移。关开关回退保留数据；非空 downgrade 拒绝删除。停机关闭上游并保存 interrupted，未知账目保守保留。

原核心证据在 `D:/RR/deliverables/yaoling-product-20261023/assistant-v3/P6-evidence.md`。SQLite 合成影子库原 331 表哈希一致；空库完整升级及再次升级通过。P6-04 后续完成真正0175旧库到0177、兼容旧代码和前进读取的隔离路由演练，见 [回退与数据保留](ROLLBACK.md) 及交互包 `P6-rollback-evidence.md`；裸旧代码的撤权缺口已有精确版本兼容补丁。PostgreSQL 仍仅做 SQL 编译，未取得实际隔离实例。当前 QA 进程停止/重启曾被自动审批拒绝，不能换工具或端口绕过；pytest、模拟 provider、离线路由和真实浏览器旧协议兼容检查分别记载，不代表已在 QA 或生产启用。
