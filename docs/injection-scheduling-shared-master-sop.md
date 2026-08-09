# 注塑排产共享模具与下单表运营 SOP

## 1. 适用范围与安全边界

本 SOP 适用于所有注塑厂区的 `DEMAND_ORDER`、`MASTER_DATA`、共享模具、厂区实物资产、能力和价格规则治理。真实 Excel 只读；上传文件保留为有期限 artifact，系统不得回写原文件。

当前默认策略为：下单表 `MANUAL_CONFIRM`、主数据 `PROPOSAL_ONLY`、业务合同 `UNSIGNED`、价格激活关闭、排期预占 30 分钟。十四项业务定义未签字前，不得把 `安数`、`啤数`、`啤机复期` 或来源单价提升为生产硬约束或 ACTIVE 价格。

## 2. 下单表导入

1. 上传时优先选择“自动识别”；无法命中 ACTIVE Profile 的文件必须停在映射或 Profile 审核阶段。
2. 对照源 Sheet/行、稳定订单行 ID、模号、货号、数量、交期、匹配原因和字段 provenance；客户文字仅保留在来源快照，不参与排期导入判定。
3. 无效订单事实、重复 fallback 身份和未知必填表头不得确认；模具未命中或候选歧义不阻断接收订单，而是进入待补齐状态。
4. `NOT_FACTORY_READY` 可作为 DRAFT/BACKLOG 保存，但在模具关联和工艺资料补齐前不得生成 Task。
5. 下单表确认不解析或冻结商业价格；客户、价格和模具主数据暂缺均不得阻断啤机文员把有效需求导入待排。
6. 只勾选已复核行。确认只写不可变 OrderIdentity/DemandOrderVersion、DRAFT PlanOrderState/BACKLOG 和冻结快照，不改 PUBLISHED、不生成 Task。
7. 刷新后使用 `?batch=<batch_id>` 恢复同厂区批次；切换厂区会清除该参数。摘要或 generation 变化时重新预览，不绕过 stale 409。
8. 模具库补充或修订后，在待排订单页执行“从模具库补齐”；系统按当前厂区模号、公司共享定义和别名重新匹配。唯一命中才关联，零命中保留待补齐，多命中保留歧义，均写审计。

## 3. Profile 治理

1. 未知表头先保存 mapping draft，再提交新 Profile revision。
2. 提交人与批准人分离；批准人核对文档种类、Sheet role、标题/锚点、动态表头、终止标志、转换器和厂区绑定。
3. 激活新 revision 后，使用原 artifact 重试识别；不得新增厂区专用 parser 分支。
4. 退役 Profile 前确认没有待确认批次依赖该 revision，并保留审计记录。

## 4. 共享模具与价格主数据

1. `机安` 和 `单价` Sheet 只生成 Proposal 与 FieldEvidence。预览中的每个值必须显示源文件摘要、Sheet、行、单元格和原始/显示值。
2. 公司模具定义、别名、输出规格与厂区实物、厂区能力分开审批；“公司可见”不等于“本厂可排”。
3. 一模多货号/配件按多个 OutputSpec 表达，不得压成首行。
4. 模号相同但公司身份或权威别名不足时只提交 MERGE Proposal；合并、拆分和别名重定向均需独立审批、影响清单和可追溯原因。
5. 价格 Proposal 必须明确 owner scope、适用厂区、客户、产品/模具输出、日期、计价单位、币种和优先级。合同未标记 `SIGNED` 或策略未开启时，即使 Proposal 已批准也不得 ACTIVE。
6. 紧急临时价必须走限时规则：填写起止时间、原因和批准人；不得覆盖历史订单/发布快照，过期后退役而不是删除。

## 5. 旧模具候选与实体核验

1. 只有已关联共享 MoldDefinition 的旧模具可按 `copy_count` 生成 `LEGACY_UNVERIFIED` 候选；候选不可预约、不可排产。
2. 现场核对资产号、实物副号、所在厂区和状态后，由资产管理员激活 LegacyMoldCopyBinding。
3. 激活事务会锁定资产、factory/mold/copy 绑定及未完成 DRAFT/PUBLISHED 旧 Task；时间窗无效、映射歧义或重叠时必须停止并盘点。
4. 激活会为旧 Task 建立 ACTIVE reservation，但不改写已发布 Task；迁移期通过 binding 与 reservation 双读。此后新 Task 必须直接写 `physical_mold_asset_id`。

## 6. 排产、调拨与占用释放

1. 自动排期预览为新任务建立有期限的 TENTATIVE hold；过期、资产状态改变或出现其他占用时，应用方案必须失败并重新生成。
2. 应用方案把对应 hold 原子转为 ACTIVE reservation。手工追加、移动、启发式、CP-SAT、发布与签名导出使用同一实体资产 lineage。
3. 移动前重新检查时间窗；取消、完工和接班发布时释放或转移 reservation。发布事务失败时由数据库回滚，不留下半激活占用。
4. 维修、借出、调拨中和运输中的资产不可排。调拨按 `PLANNED → APPROVED → EFFECTIVE` 执行，生效前核对未完成 reservation；不得直接修改资产厂区绕过 Movement。

## 7. 监控与分厂推广

每厂按 `SHADOW → PREVIEW_ONLY → MANUAL_CONFIRM → AUTO_ENRICH` 推进。升级前检查 Profile 命中率、未匹配率、歧义率、补齐覆盖率、价格缺失率、主数据审批时长、stale 冲突和占用冲突。新厂只配置/审批 Profile、公司 membership、本厂资产/能力与权限，不复制 parser。

## 8. 故障与回滚

1. 业务错误先保留 batch/run/request ID、预览 generation、摘要和审计序号，不删除证据。
2. Profile 或主数据错误：停止确认/激活，退役错误 revision，创建修订 Proposal，再用原 artifact 重试。
3. 资产占用错误：停止发布，核对 ACTIVE/TENTATIVE reservation、Legacy binding 和 Movement；不得直接删 reservation。
4. 数据库迁移前必须做可验证备份；仅在迁移 downgrade guard 允许且无新业务数据时降级。否则恢复备份并回退应用版本。
5. 恢复后检查 Alembic revision、schema gate、SQLite/PostgreSQL 完整性、API `/health`、关键旧表行数和权限范围。

## 9. 权限分离

- 导入预览、DRAFT 确认、Profile 提交/激活、公司模具提案/审核、厂区资产维护、价格查看/提案/批准/策略管理分别授权。
- 提交人不得批准自己的模具或价格 Proposal。
- 无价格查看权限的确认人员只能看到服务端冻结的最终价格摘要，不能枚举规则。
- 所有越权 batch、资产和 Proposal 查询按厂区/公司范围返回 403 或 404，不泄漏行内容。
