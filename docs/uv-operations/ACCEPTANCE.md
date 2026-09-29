# A01–A39 验收台账

2026-09-29 补齐软件差距，最新完整证据见 [软件验收](SOFTWARE_ACCEPTANCE_20260929.md)。真实采集与真实资料配置按用户要求延期。

“软件通过”只指合成自动化/浏览器证据，不代表现场通过。测试在 backend/tests/test_uv_ops*.py、src/features/uv-operations/__tests__/、edge/uv-printing-agent/tests/test_agent.py。未测项不能由通过数替代。

| 编号 | 结果 | 证据或边界 |
|---|---|---|
| A01 | 软件通过 | factory_is_always_explicit：非A、group、空factory拒绝 |
| A02 | 软件通过 | prices_are_frozen_and_projected、workspace_pg_json_null_and_sensitive_projection、SSE每tick脱敏、导出撤权 |
| A03 | 软件通过 | workspace生命周期：旧HTTP/SSE不回写；浏览器实际撤销read后清空数据 |
| A04 | 软件通过 | concurrent_same_operation_commits_once，双数据库竞争同号仅一次 |
| A05 | 软件通过 | idempotent_replay_and_conflict，载荷变化409 |
| A06 | 软件通过 | agent_partial_batch_retransmit_payload_conflict_and_counts |
| A07 | 软件通过 | 去重基于稳定job identity；exe 4个独立Run保留，人工核数仍2笔 |
| A08 | 软件通过/现场待验 | 无结束证据不自动完成；停API保留旧快照，未知进度 |
| A09 | 软件通过 | 板槽尾件换算、多遍不重复成品 |
| A10 | 软件通过 | manual_conservation_rework_handover：119良品/1废/126尝试 |
| A11 | 软件通过 | task_prices_are_frozen_and_projected，旧任务冻结 |
| A12 | 软件通过 | rounding_and_piece_rate，0.015×1000=15.00 |
| A13 | 软件通过 | rounding_and_piece_rate，100元三人稳定分尾差 |
| A14 | 软件通过 | 实际人时重叠分摊；gang_run_cost_once_and_cross_midnight_time：22–06分日7200/21600秒 |
| A15 | 软件通过 | sunday_production_and_explicit_zero_cost_are_retained：周日产量10件，明确零成本保留 |
| A16 | 软件通过 | SKU/批号/库位唯一余额，不按颜色合并；模型和库存用例 |
| A17 | 软件通过 | concurrent_ink_and_transfer_not_consumption，末余额竞争 |
| A18 | 软件通过 | 转移不增加耗用，遥测只在Run/Inbox不能扣正式账 |
| A19 | 软件通过 | 部分交接、拒收、退回、日期余额和接收权限用例 |
| A20 | 软件通过 | period_close_serializes_writer_and_unresolved_late_blocks_reclose |
| A21 | 软件通过 | late_evidence_is_separate_and_closed_snapshot_is_immutable |
| A22 | 软件通过 | 毒事件/旧流/撤销/主源唯一，配对重试身份测试 |
| A23 | 软件通过/现场待验 | outbox持久重启；exe强停重启队列0；真实断网和72h连续运行待现场 |
| A24 | 软件通过 | duplicate逐事件ACK，连续确认水位不跨缺口 |
| A25 | 软件通过/厂商待验 | UTF8/GB、半行、轮转/截断、超长坏行；仅synthetic-csv-v1 |
| A26 | 软件通过 | same_timestamp_old_sequence_and_rebinding_do_not_rewind_run |
| A27 | 待现场 | 已打包exe联调；未安装SCM或改变锁屏/登录/RDP |
| A28 | 软件通过 | 背压保留队列/游标；259200条容量模型 |
| A29 | 软件通过/发布待验 | DB快照/SSE重置、上下文隔离；多worker隔离联调见测试记录，Nginx待验 |
| A30 | 软件通过 | progress=null、未知墨量不置0；实际截图标示模拟/过期 |
| A31 | 未启用 | dispatch_supported=false，无原生投递 |
| A32 | 软件通过 | 文件名/魔数/32MB、压缩比/64MB解压/工作表限制、HTTPS来源限制 |
| A33 | 软件通过 | 重传去重、跨厂/封账行预览、1000行持久大预览回滚正式表 |
| A34 | 软件通过 | full_export_over_5000_records_and_formula_safe_ids：5002条完整；数据库汇总不受分页影响 |
| A35 | 软件通过 | 缺成本/工资利润null，分币、零分母；浏览器“资料待补齐” |
| A36 | 软件通过 | 409冲突、守恒禁提交、502空代理响应重试、实际撤权 |
| A37 | 软件通过 | 0127 最终副本保持321张原表行数及所有旧CHECK，integrity/FK通过；双库有数据迁移回归通过；PostgreSQL全链及新域模型零差异。实际库仍0126，未发布 |
| A38 | 软件通过 | 稳定ID和冻结快照；名称不作为外键 |
| A39 | 软件通过 | gang_run_cost_once_and_cross_midnight_time：24/12件，成本30分20/10，同治具/互斥槽位/唯一成本池 |

另有返工取消不复活、拆合谱系、Run匹配后禁止重组、返工UI唯一批次、封账迟到阻断、工资冻结竞争、报表导出一次计算等回归。补充1000组随机分币及各15步核数纠错/库存幂等序列；未宣称全面模糊测试。

截图见 [VISUAL_QA](VISUAL_QA.md)，命令、容量及限制见 [TEST_EVIDENCE](TEST_EVIDENCE.md)。

本轮补充：未知节拍人工估时、子批多机/同治具版本冲突、在制未来推荐、跨班完工、有效账本冲销、库存历史日期、30天6000条完整分页、原生拖动预览取消确认及四类实际XLSX下载通过。
