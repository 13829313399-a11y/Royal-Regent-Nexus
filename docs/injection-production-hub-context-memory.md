# 注塑排产中枢前端重建上下文

## 当前边界

- 模块 ID：`injection-scheduling`
- 正式前端路由：`/modules/production/injection-scheduling?factory={factoryId}`
- 当前阶段：前端交互预览
- 当前数据：仅华兴厂区使用本地 Mock 快照
- 后端状态：未恢复旧接口、旧数据表和旧权限
- 写入规则：当前所有排程调整只存在于浏览器 Pinia 状态，不写入数据库

## 视觉与产品基线

视觉参照为：

`C:\Users\匡树杰\Desktop\啤机部项目资料\huaxing_injection_scheduling_ui_prototype.html`

新页面在现有 Royal Regent Nexus 视觉体系内保留以下核心结构：

1. 深绿色模块顶栏、返回生产部入口、厂区上下文和账号菜单。
2. 数据快照提示、计划标题、来源文件与版本标识。
3. 六项 KPI、粘性视图与筛选控制条。
4. 固定机台信息列、横向任务卡队列、当前任务锁定和风险语义。
5. 时间轴总览、待排订单池、候选机台解释、任务详情抽屉。
6. 调整确认、规则说明、异常列表、发布提示和 Toast 反馈。

## 代码结构

- `src/views/InjectionSchedulingHubView.vue`：页面编排、项目顶栏、厂区隔离与状态入口。
- `src/components/injection-scheduling/`：KPI、筛选器、机台板、任务卡、时间轴、待排池、候选机台和浮层组件。
- `src/types/injectionScheduling.ts`：机台、任务、订单、候选、筛选和移动请求类型。
- `src/data/injectionSchedulingMock.ts`：华兴前端演示快照。
- `src/stores/injectionScheduling.ts`：Pinia 页面状态与浏览器内草案交互。
- `src/api/injectionScheduling.ts`：未来后端接入契约和端点草案，不发起请求。

## 已实现业务交互

- 当前任务锁定，不允许移动。
- 后续任务可以发起跨机台调整，但必须二次确认后才修改本地草案。
- 待排订单选择后展示候选机台、评分、理由和风险提示。
- 选择候选机台后必须二次确认，确认后才从待排池生成本地草案任务。
- 建议排程、重算标记和发布动作均明确显示“前端演示 / 后端未接入”。
- 非华兴厂区显示独立空态，不回退或泄露华兴 Mock 数据。

## 后端接入约束

未来后端应实现 `InjectionSchedulingRepository` 所描述的读取、移动校验和版本发布能力，并至少保证：

1. 厂区级数据隔离。
2. 机台资格、吨位、机械手、螺杆、抽芯与模具约束校验。
3. 当前任务锁定与并发版本控制。
4. 排程版本发布、回滚和审计。
5. 正式交期、产能、换模时间与异常重算。
6. 权限由新业务模型重新设计，不复用已删除的 `injection_schedule:*` 权限。

## 验收基线

- 组件和 Pinia 聚焦测试通过。
- Vue TypeScript 构建通过。
- 1366、1440、1920 桌面视口无页面级横向溢出。
- Chrome 验证任务详情、时间轴、待排池、候选机台、确认流程和厂区空态。
- 视觉对照结果记录在根目录 `design-qa.md`。

