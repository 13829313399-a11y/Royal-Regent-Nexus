# 52 条验收规格覆盖追踪

规格覆盖不等于 52 项自动化测试。covered=规格要求的软件行为已有执行证据；具体测试数量、命令和环境见 test-results.md。生产部署与物理设备边界见 known-issues.md。

覆盖统计：covered 52、partial 0、not_run 0。原余下 8 条已补验。

| 编号 | 规格 | 状态 | 执行证据 |
|---|---|---|---|
| PR-001 | 注册一次激活与分配 | covered | registration_single_transaction_and_original_declaration；employee_to_admin_real_permission_flow_and_receipt |
| PR-002 | 注册中途失败整体回滚 | covered | registration_single_transaction_and_original_declaration：回执故障注入整体回滚 |
| PR-003 | 员工提交只产生声明 | covered | employee_to_admin_real_permission_flow_and_receipt：申报前后身份/权限响应一致；浏览器双会话 |
| PR-004 | 员工不可过量提交 | covered | strict_self_fields_idor_revisions_return_withdraw：权限字段 422 |
| PR-005 | 员工不能改他人的请求 | covered | strict_self_fields_idor_revisions_return_withdraw：非本人 PATCH 404 |
| PR-006 | 同人唯一open申请 | covered | postgres_simultaneous_self_submission_has_one_open_review：两个独立连接 |
| PR-007 | 修改待办使预览失效 | covered | changed_role_revision_or_declaration_invalidates_preview |
| PR-008 | 完全相同输入不刷通知 | covered | employee_to_admin_real_permission_flow_and_receipt：相同提交返回原 id/revision；notification_dispatch 聚合 |
| PR-009 | 退回与重提 | covered | strict_self_fields_idor_revisions_return_withdraw：returned→pending |
| PR-010 | 撤回不改正式权限 | covered | strict_self_fields_idor_revisions_return_withdraw：withdrawn、正式版本不变 |
| PR-011 | 已完成不可撤回 | covered | keep_pinned_version_independent_deny_and_no_implicit_upgrade：applied 后撤回 409 |
| PR-012 | 同部门只改职位保留授权 | covered | keep_pinned_version_independent_deny_and_no_implicit_upgrade；浏览器 legacy 保留路径 |
| PR-013 | 只换方案不伪造调动 | covered | employee_to_admin_real_permission_flow_and_receipt：主职 assignment id 不变；业务写撤权 |
| PR-014 | 独立授权不被注册清理误删 | covered | test_package_replacement_preserves_all_four_independent_sources：同一人员同时含独立 allow、deny、system_administration、external_collaboration；替换主职后逐列保持，实际授权和跨厂边界均断言通过。 |
| PR-015 | 独立allow需要真实确认 | covered | independent_future_allow_and_deny_preserved_and_scheduled_binding_blocks：缺少独立 allow 选择 422 |
| PR-016 | 新增实际权限就地确认 | covered | risk=false 服务 422；usePositionReview 明确风险组件测试；390 宽实际禁用截图 |
| PR-017 | 模板并发更新 | covered | changed_role_revision_or_declaration_invalidates_preview：目录权限定义及授权版本变化拒绝旧预览 |
| PR-018 | 保留不偷偷升级角色 | covered | keep_pinned_version_independent_deny_and_no_implicit_upgrade：绑定版本与 deny 保持 |
| PR-019 | 总务不等于全厂 | covered | group_scope_self_escalation_and_changed_idempotency_payload：functional org + home 范围返回 INVALID_SCOPE |
| PR-020 | 跨厂管理范围不足 | covered | scope_filters_before_total_and_no_recipient_diagnostic；注册转厂历史完整范围 403 |
| PR-021 | 角色文本不自动赋权 | covered | 员工总经理文本提交仍为声明；group_scope/self_escalation 与 schema 白名单 |
| PR-022 | 管理员自己增权 | covered | group_scope_self_escalation_and_changed_idempotency_payload：本人新增方案 SELF_ESCALATION 403 |
| PR-023 | 两个管理员并发 | covered | postgres_two_commits_and_replay_use_independent_connections：同时两命令 200/409 |
| PR-024 | 幂等相同命令重试 | covered | employee_to_admin_real_permission_flow_and_receipt；PostgreSQL 胜出命令重放同回执 |
| PR-025 | 幂等key不同body | covered | group_scope_self_escalation_and_changed_idempotency_payload：原 command 改 body 拒绝 |
| PR-026 | 不明结果不盲目重提 | covered | usePositionReview 5xx→uncertain→receipt/retry 原命令，not_observed 不解锁 |
| PR-027 | 通知失败不伪造失败授权 | covered | notification_dispatch_aggregation_unknown_kind_and_failure：业务 applied 后通知失败 retry |
| PR-028 | 没有通知仍有待办 | covered | scope_filters_before_total_and_no_recipient_diagnostic：无通知仍存在真实 queue row |
| PR-029 | 新kind不会发成旧通知 | covered | notification_dispatch_aggregation_unknown_kind_and_failure；既有 identity outbox 回归 |
| PR-030 | 管理员通知聚合 | covered | notification_dispatch_aggregation_unknown_kind_and_failure：两次编辑聚合一条 revision=2 |
| PR-031 | 无合适接收人 | covered | scope_filters_before_total_and_no_recipient_diagnostic：routing_attention、请求保留 |
| PR-032 | 队列计数无越界泄露 | covered | scope_filters_before_total_and_no_recipient_diagnostic；registration_history 当前范围回归 |
| PR-033 | 跨页分页稳定 | covered | test_mixed_same_timestamp_queue_has_stable_pages_and_totals：31 注册+31 岗位，同秒且跨表重复 source id；page_size 7/20/50 顺序、总数、去重及分类型过滤全部通过。 |
| PR-034 | 离职epoch失效 | covered | test_leave_rehire_rejects_old_epoch_and_accepts_new_declaration：完整离职→复职，新 epoch；旧 Cookie 401、旧申请编辑 404、旧预览 409；旧记录 invalidated，新 epoch 可重新申报。 |
| PR-035 | 冻结状态可恢复 | covered | freeze_leave_and_actor_loss_block_workbench_commit：冻结后旧预览阻断、解冻可重新预览 |
| PR-036 | 未来任职冲突 | covered | independent_future_allow_and_deny_preserved_and_scheduled_binding_blocks：未来主职绑定转高级办理 |
| PR-037 | Legacy无漂移核实 | covered | 浏览器 legacy explicit assignment 分类，实际新增/停止 0→确认来源→继续；既有 identity 回归 |
| PR-038 | Legacy禁止浏览器伪原子 | covered | 浏览器明确单独来源核实动作/回执；后续岗位确认另一动作，未伪装两个提交为原子 |
| PR-039 | 输入修改马上撤销token | covered | usePositionReview：任一 draft 编辑同步清 token/risk |
| PR-040 | 快速切人不串资料 | covered | usePositionReview：慢详情和 preview 在切人后丢弃 |
| PR-041 | 权限撤销清空保护数据 | covered | usePositionReview：403 清详情；effective_context_key 改变清缓存及迟到响应 |
| PR-042 | 管理员普通全程同屏 | covered | 浏览器标准在职审批与 legacy 保留同页完成；注册单事务接口完成 |
| PR-043 | 员工完整闭环 | covered | 浏览器员工 localhost/管理员 127.0.0.1 独立会话闭环；HTTP 同原 Cookie 业务权限验证 |
| PR-044 | 失权真正阻止业务写 | covered | business_write_revoked_in_existing_employee_session：POST /api/injection 201→403 |
| PR-045 | 移动无横向溢出和遮挡 | covered | 真实 Chromium 设置页面缩放 200%，CDP cssVisualViewport.zoom=2，DPR=2；640×360 管理员和员工按钮完整可见。修复短视口滚动留白后，另在 CSS 360/390/768 宽、200% 下检查无横向溢出及焦点边缘无遮挡；closure-browser-evidence.json、zoom-200-*.png。 |
| PR-046 | 键盘完整操作 | covered | 内置浏览器纯键盘执行员工编辑/空值拦截/Enter 保存，管理员 Tab/方向键 radio 选择、提交、办理下一位和退回原因提交；成功/错误/取消焦点及乱序请求回归通过；keyboard-*.png。 |
| PR-047 | reduced-motion | covered | 经用户授权独立 Playwright emulateMedia(reducedMotion=reduce)，matchMedia=true；进入员工页、切换方案目录和审批成功均验证 .pw-root 子树 animation=none、transition=0，状态可见；reduced-motion-success.png。 |
| PR-048 | 旧路由与密码重置 | covered | 浏览器实际执行旧 person 保留权限确认、旧 registration 注册开通、旧 access 供应商独立授权保存、旧 password-reset 深链驳回；普通员工 access 不读取明细/无提交；密码重置完整后端回归 9 passed；legacy-*.png。 |
| PR-049 | UI回滚仍可处理请求 | covered | 独立 UI-off 实例浏览器验证旧主页、兼容入口读取并成功退回已有申请，员工读到意见；后台 gate/dispatcher 已执行；rollback-success.jpg。未实施生产切换。 |
| PR-050 | 数据库真实并发 | covered | test_postgres_competing_writer_survives_failed_approval[approve/edit]：独立 PG Session 竞争锁，真实身份/事件/outbox/receipt flush 后注入故障；失败事务无残留，等待写者继续；重复回执一致或旧预览409后重新审批成功。 |
| PR-051 | 直接管理员调整仍允许本人更新 | covered | admin_origin_reuse_employee_edit_and_writes_gate：本人改声明不改 admin origin/正式权限 |
| PR-052 | 管理员撤回权限发生在预览后 | covered | freeze_leave_and_actor_loss_block_workbench_commit：预览后撤销 actor 角色 403；既有 fresh_actor 回归 |
