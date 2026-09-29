# API 契约 v1

完整路径、请求字段、枚举及校验以 [openapi.json](openapi.json) 与 `backend/app/schemas/uv_operations.py` 为准，共 100 个路径。JSON 金额、比率、长度、时间计量等精确小数使用十进制字符串；件数和版本为整数。时间需带时区，业务日为 YYYY-MM-DD。

## 权限与响应

用户 API 前缀 `/api/uv-operations`，沿用平台 HttpOnly 会话。读请求显式 `factory_id=huakang-a`；写请求的 factory_id 固定华康 A。所有新接口直接执行 canonical scope 决策，即使平台处在 legacy/shadow 模式。基础 read、操作权限、cost_read、payroll_read 独立；部门固定 production。其他厂区、group、缺厂参数均不返回 A 数据。

成功响应 `{data, meta}`；meta 含 factory_id、authorization_version、view_revision、data_mode、coverage、warnings。列表附 pagination（total、has_more、next_cursor），默认 100、最多 200；客户端必须继续游标分页。workspace 提供各类最近 100 条，加经过当前来源核验的运行及每机下一计划、关联任务，并提供完整数量，不是完整导出源。

错误为 `{code,message,...}`；403 权限不足，409 幂等载荷/版本/业务冲突，422 输入或规则校验，503 模块关闭/迁移未就绪。内部数据库错误经过白名单处理。未获金额权限时直接省略字段，包括派生合计、回执、SSE、下载；不靠前端隐藏。已经生成的敏感文件在权限被撤销后拒绝下载。

## 命令与账本

每条命令携带 operation_id（8–64 字符）、expected_version（新建 0）和必要 reason/evidence。作用域为用户+operation_id，摘要包含动作、对象和 canonical 载荷。授权先于回执读取。业务写、版本、审计及回执原子提交。响应不确定时沿用原 operation_id 和原载荷；确定的 409 修正数据后重新生成操作号。

| 资源/动作 | 语义 |
|---|---|
| products / fixtures / processes / files | 产品、版本工艺、物理治具；生产文件确认首件；预览与生产文件分离 |
| demands / tasks / schedule/preview / schedule | 需求分配、冻结任务、资源冲突预览后提交 |
| production/confirm / production/{id}/reverse | 唯一实体产量依据及带原因冲销；禁止穿透后续依赖 |
| batches/{id}/split、merge / rework-tasks | 未加工且未绑定 Run 的批次重组；返工子任务绑定原批次 |
| quality / shifts / participations | 待检处置、班次缺项/关闭、参与区间；已核工资冻结来源 |
| handovers / receive、reject、return、cancel | 部分交接、接收人权限、预留及已签收日期余额守恒 |
| ink-skus / ink-movements | SKU+批号+库位移动平均；转移不计消耗，退回/冲销沿用来源成本 |
| pricing-policies / wage-policies / expenses / wages/confirm | 版本价格工资、明确费用、核准与稳定分尾差 |
| runs/{id}/match / run-costs | 同遍共用物理治具、槽位互斥、份额和为 1；一笔 Run 成本池 |
| reports / machine-time / periods / late-events | 完整范围核算、跨日机时、账期封存和迟到差异处理 |
| imports / exports | 持久作业、行级预览、原子导入、完整范围导出 |

## 实时与代理

`GET /live` 是每 2 秒读取数据库的一致快照 SSE，事件 reset、snapshot、access_revoked、unavailable。每次 tick 重新认证、脱敏；重连发完整 reset，不依赖内存广播。前端按账号/厂区/授权代次隔离请求，切换或撤权清缓存，隐藏/离线停止流。

代理前缀 `/api/internal/uv-agent`，不使用用户会话。enroll 使用单次 15 分钟配对码和本地预先持久化的 token/enrollment_id；之后仅 Bearer 凭据。config 下发绑定，heartbeat 仅白名单诊断，events/batch 每事件明确 persisted/duplicate/rejected。最高序号不是累计确认。新流需重新绑定的拒绝带 retryable=true，保留待发；不可恢复坏事件隔离。旧绑定/旧序号的历史证据不覆盖实时状态。

commands 始终为空且 dispatch_supported=false；receipt 拒绝不支持的派发。程序不读任意 URL、不执行文件、不控制 RIP 或打印按钮。

## 导入导出限制

产品、工艺、需求、人工核数、费用、参考效率模板均有版本。CSV 仅 UTF-8，XLSX 仅读缓存值、不执行公式/宏；16 MB 压缩输入、64 MB 解压、128 列、每批 10000 行。先明确映射及单位，再预览行错误；大于 128 KB 使用持久后台预览。封账行保留为 adjustment_required，重开后重新预览才能提交。

导出最多 366 天，明确 selected_ids 或完整日期范围；500 行分块读取、流式 XLSX、元数据及完整行数。日报月报在同一个 PostgreSQL REPEATABLE READ 事务中构建，各工作表复用同一次核算。金额数值、编号文本、用户字符串强制文本防公式注入；异步任务重启后租约可回收。

## 批次排程、执行与纠错

`POST schedule/recommendations` 是只读计算，无 operation_id/expected_version；返回分钟对齐且保留完整时长的可用窗口。`GET schedule/window` 读取最多31天区间，limit<=500，返回 total/next_cursor/has_more 和每批 started。`schedule/preview` / `schedule/commit` 携带 batch_id/batch_version、任务/机台/计划版本；未知节拍提供 manual_estimated_seconds、estimate_reason，替代实体治具提供 fixture_id/version/evidence。preview 返回 conflicts、changes、warnings，当前在制资源的预计释放警示不替代实际完工。

`schedule/{id}/start` 和 `executions/{id}/finish` 记录人工开工/完工依据；finish 必须指定当前完成班次 shift_id。它们不产生 Run 或核数。`schedule/{id}/unlock`、cancel 及 `tasks/{id}/cancel` 需要原因和当前版本。已执行计划不能重排。

`quality/{id}/reverse`、`participations/{id}/reverse`、`expenses/{id}/reverse`、`wages/{id}/reverse`、`run-costs/{id}/reverse` 保留原单、写 reversals、取消 active_key；已封账或存在后续依赖时拒绝。常规集合默认有效账本，history=true 可在原权限内查看历史；reversals 需 audit_read。

导出生产含品质与来源、交接含事件与原单、工资含员工分配及撤销依据。日期筛选按事实自身业务日，selected_ids按选择的原单保留关联历史。日报/月报拒绝 selected_ids，防止被误认为只导出选中任务。
