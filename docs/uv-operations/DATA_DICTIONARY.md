# 数据字典

新域限定 `huakang-a`，44 张表。以下从当前模型生成；金额和非整数计量为 Numeric(18,6)，API 为十进制字符串。业务日 Asia/Shanghai，时间为 UTC ISO 文本。

`id` 为稳定标识；`version` 检查并发。品质、工时、费用、工资、Run 成本的 `active_key=1` 表示有效，冲销后置 NULL，原始金额/数量/分配仍保留，`uv_ops_reversals` 保存理由。执行记录的 active_key 表示正在执行，完工置 NULL；它不产生核数。排程 batch_id 可空仅兼容旧整任务计划，新排程必须绑定实体批次。

迁移 `20260929_0127` 追加执行与冲销表、批次排程字段并保留旧数据和 CHECK。

## uv_ops_agent_event_inbox

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `agent_id` | `VARCHAR(64)` | 否 | uv_ops_agents.id |
| `machine_id` | `VARCHAR(64)` | 否 | uv_ops_machines.id |
| `binding_id` | `VARCHAR(64)` | 否 | uv_ops_source_bindings.id |
| `event_id` | `VARCHAR(64)` | 否 | — |
| `stream_id` | `VARCHAR(64)` | 否 | — |
| `sequence` | `INTEGER` | 否 | — |
| `observed_at` | `VARCHAR(40)` | 否 | — |
| `received_at` | `VARCHAR(40)` | 否 | — |
| `kind` | `VARCHAR(32)` | 否 | — |
| `payload_hash` | `VARCHAR(64)` | 否 | — |
| `evidence` | `JSON` | 否 | — |
| `late_closed_period` | `BOOLEAN` | 否 | — |
| `resolved_by` | `VARCHAR(64)` | 是 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | uv_ops_agents.factory_id, uv_ops_machines.factory_id, uv_ops_source_bindings.factory_id |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：factory_id = 'huakang-a'

唯一键：factory_id, agent_id, event_id；factory_id, agent_id, stream_id, sequence；factory_id, id

索引：ix_uv_ops_agent_event_inbox_factory_id, ix_uv_ops_inbox_machine_observed

## uv_ops_agents

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `name` | `VARCHAR(128)` | 否 | — |
| `token_hash` | `VARCHAR(64)` | 是 | — |
| `pairing_hash` | `VARCHAR(64)` | 是 | — |
| `pairing_expires_at` | `VARCHAR(40)` | 是 | — |
| `enrollment_id` | `VARCHAR(64)` | 是 | — |
| `enrollment_pairing_hash` | `VARCHAR(64)` | 是 | — |
| `revoked` | `BOOLEAN` | 否 | — |
| `last_seen_at` | `VARCHAR(40)` | 是 | — |
| `diagnostics` | `JSON` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | — |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：factory_id = 'huakang-a'

唯一键：factory_id, id；pairing_hash；token_hash

索引：ix_uv_ops_agents_factory_id

## uv_ops_audit

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `actor_id` | `VARCHAR(64)` | 否 | — |
| `operation_id` | `VARCHAR(64)` | 否 | — |
| `action` | `VARCHAR(128)` | 否 | — |
| `entity_id` | `VARCHAR(64)` | 否 | — |
| `reason` | `TEXT` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | — |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：factory_id = 'huakang-a'

唯一键：factory_id, id

索引：ix_uv_ops_audit_entity_id, ix_uv_ops_audit_factory_id

## uv_ops_batch_relations

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `source_id` | `VARCHAR(64)` | 否 | uv_ops_batches.id |
| `target_id` | `VARCHAR(64)` | 否 | uv_ops_batches.id |
| `quantity` | `INTEGER` | 否 | — |
| `kind` | `VARCHAR(24)` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | uv_ops_batches.factory_id, uv_ops_batches.factory_id |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：factory_id = 'huakang-a'；quantity > 0；source_id != target_id

唯一键：factory_id, id

索引：ix_uv_ops_batch_relations_factory_id

## uv_ops_batches

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `task_id` | `VARCHAR(64)` | 否 | uv_ops_tasks.id |
| `active` | `BOOLEAN` | 否 | — |
| `quantity` | `INTEGER` | 否 | — |
| `pass_index` | `INTEGER` | 否 | — |
| `remaining` | `INTEGER` | 否 | — |
| `intermediate` | `INTEGER` | 否 | — |
| `good` | `INTEGER` | 否 | — |
| `rework` | `INTEGER` | 否 | — |
| `scrap` | `INTEGER` | 否 | — |
| `pending` | `INTEGER` | 否 | — |
| `reserved` | `INTEGER` | 否 | — |
| `received` | `INTEGER` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | uv_ops_tasks.factory_id |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：factory_id = 'huakang-a'；good >= 0；intermediate >= 0；pending >= 0；quantity > 0；received >= 0；remaining + intermediate + good + rework + scrap + pending = quantity；remaining >= 0；reserved + received <= good；reserved >= 0；rework >= 0；scrap >= 0

唯一键：factory_id, id

索引：ix_uv_ops_batches_factory_id

## uv_ops_demands

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `code` | `VARCHAR(64)` | 否 | — |
| `product_id` | `VARCHAR(64)` | 否 | uv_ops_products.id |
| `source_type` | `VARCHAR(32)` | 否 | — |
| `source_line_id` | `VARCHAR(128)` | 是 | — |
| `customer_snapshot` | `VARCHAR(128)` | 否 | — |
| `product_snapshot` | `VARCHAR(128)` | 否 | — |
| `quantity` | `INTEGER` | 否 | — |
| `allocated` | `INTEGER` | 否 | — |
| `cancelled` | `INTEGER` | 否 | — |
| `due_at` | `VARCHAR(40)` | 否 | — |
| `priority` | `INTEGER` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | uv_ops_products.factory_id |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：allocated + cancelled <= quantity；allocated >= 0；cancelled >= 0；factory_id = 'huakang-a'；quantity > 0

唯一键：factory_id, code；factory_id, id；factory_id, source_type, source_line_id

索引：ix_uv_ops_demands_factory_id

## uv_ops_executions

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `task_id` | `VARCHAR(64)` | 否 | uv_ops_tasks.id |
| `batch_id` | `VARCHAR(64)` | 否 | uv_ops_batches.id |
| `machine_id` | `VARCHAR(64)` | 否 | uv_ops_machines.id |
| `schedule_id` | `VARCHAR(64)` | 否 | uv_ops_schedule_blocks.id |
| `fixture_code` | `VARCHAR(64)` | 否 | — |
| `shift_id` | `VARCHAR(64)` | 否 | uv_ops_shifts.id |
| `started_at` | `VARCHAR(40)` | 否 | — |
| `ended_at` | `VARCHAR(40)` | 是 | — |
| `start_evidence` | `TEXT` | 否 | — |
| `end_evidence` | `TEXT` | 是 | — |
| `ended_shift_id` | `VARCHAR(64)` | 是 | uv_ops_shifts.id |
| `active_key` | `INTEGER` | 是 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | uv_ops_batches.factory_id, uv_ops_machines.factory_id, uv_ops_schedule_blocks.factory_id, uv_ops_shifts.factory_id, uv_ops_shifts.factory_id, uv_ops_tasks.factory_id |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：(active_key = 1 AND ended_at IS NULL) OR (active_key IS NULL AND ended_at IS NOT NULL)；ended_at IS NULL OR ended_at > started_at；factory_id = 'huakang-a'

唯一键：factory_id, batch_id, active_key；factory_id, fixture_code, active_key；factory_id, id；factory_id, machine_id, active_key

索引：ix_uv_ops_executions_factory_id

## uv_ops_expenses

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `active_key` | `INTEGER` | 是 | — |
| `category` | `VARCHAR(32)` | 否 | — |
| `task_id` | `VARCHAR(64)` | 是 | uv_ops_tasks.id |
| `cost_amount` | `NUMERIC(18, 6)` | 否 | — |
| `currency` | `VARCHAR(3)` | 否 | — |
| `business_date` | `VARCHAR(10)` | 否 | — |
| `allocation_end` | `VARCHAR(10)` | 是 | — |
| `evidence` | `TEXT` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | uv_ops_tasks.factory_id |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：category IN ('direct','department','investment')；cost_amount >= 0；factory_id = 'huakang-a'

唯一键：factory_id, id

索引：ix_uv_ops_expenses_business_date, ix_uv_ops_expenses_factory_id

## uv_ops_export_jobs

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `actor_id` | `VARCHAR(64)` | 否 | — |
| `kind` | `VARCHAR(32)` | 否 | — |
| `filters` | `JSON` | 否 | — |
| `permissions` | `JSON` | 否 | — |
| `status` | `VARCHAR(24)` | 否 | — |
| `lease_until` | `VARCHAR(40)` | 是 | — |
| `row_count` | `INTEGER` | 否 | — |
| `artifact` | `BLOB` | 是 | — |
| `error` | `VARCHAR(64)` | 是 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | — |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：factory_id = 'huakang-a'

唯一键：factory_id, id

索引：ix_uv_ops_export_jobs_factory_id

## uv_ops_file_versions

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `process_version_id` | `VARCHAR(64)` | 否 | uv_ops_process_versions.id |
| `role` | `VARCHAR(24)` | 否 | — |
| `name` | `VARCHAR(200)` | 否 | — |
| `sha256` | `VARCHAR(64)` | 否 | — |
| `mime` | `VARCHAR(80)` | 否 | — |
| `size_bytes` | `INTEGER` | 否 | — |
| `content` | `BLOB` | 否 | — |
| `confirmed_by` | `VARCHAR(64)` | 是 | — |
| `confirmed_at` | `VARCHAR(40)` | 是 | — |
| `first_article_evidence` | `TEXT` | 是 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | uv_ops_process_versions.factory_id |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：factory_id = 'huakang-a'；role IN ('artwork','preview','production')；size_bytes > 0

唯一键：factory_id, id

索引：ix_uv_ops_file_versions_factory_id

## uv_ops_fixtures

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `code` | `VARCHAR(64)` | 否 | — |
| `revision` | `INTEGER` | 否 | — |
| `slots` | `INTEGER` | 否 | — |
| `width_mm` | `NUMERIC(18, 6)` | 否 | — |
| `height_mm` | `NUMERIC(18, 6)` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | — |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：factory_id = 'huakang-a'；height_mm > 0；slots > 0；width_mm > 0

唯一键：factory_id, code, revision；factory_id, id

索引：ix_uv_ops_fixtures_factory_id

## uv_ops_handover_events

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `handover_id` | `VARCHAR(64)` | 否 | uv_ops_handovers.id |
| `kind` | `VARCHAR(24)` | 否 | — |
| `quantity` | `INTEGER` | 否 | — |
| `business_date` | `VARCHAR(10)` | 否 | — |
| `evidence` | `TEXT` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | uv_ops_handovers.factory_id |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：factory_id = 'huakang-a'；quantity > 0

唯一键：factory_id, id

索引：ix_uv_ops_handover_events_factory_id

## uv_ops_handovers

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `batch_id` | `VARCHAR(64)` | 否 | uv_ops_batches.id |
| `target` | `VARCHAR(128)` | 否 | — |
| `receiver_id` | `VARCHAR(64)` | 否 | — |
| `business_date` | `VARCHAR(10)` | 否 | — |
| `quantity` | `INTEGER` | 否 | — |
| `received` | `INTEGER` | 否 | — |
| `rejected` | `INTEGER` | 否 | — |
| `returned` | `INTEGER` | 否 | — |
| `status` | `VARCHAR(24)` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | uv_ops_batches.factory_id |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：factory_id = 'huakang-a'；quantity > 0；received + rejected <= quantity；received >= 0；rejected >= 0；returned <= received；returned >= 0

唯一键：factory_id, id

索引：ix_uv_ops_handovers_business_date, ix_uv_ops_handovers_factory_id

## uv_ops_import_jobs

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `actor_id` | `VARCHAR(64)` | 否 | — |
| `template` | `VARCHAR(32)` | 否 | — |
| `file_hash` | `VARCHAR(64)` | 否 | — |
| `field_mapping` | `JSON` | 否 | — |
| `units_confirmed` | `BOOLEAN` | 否 | — |
| `rows` | `JSON` | 否 | — |
| `errors` | `JSON` | 否 | — |
| `status` | `VARCHAR(24)` | 否 | — |
| `source_name` | `VARCHAR(200)` | 否 | — |
| `source_content` | `BLOB` | 是 | — |
| `warnings` | `JSON` | 否 | — |
| `results` | `JSON` | 否 | — |
| `lease_until` | `VARCHAR(40)` | 是 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | — |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：factory_id = 'huakang-a'

唯一键：factory_id, id

索引：ix_uv_ops_import_jobs_factory_id

## uv_ops_import_rows

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `identity` | `VARCHAR(64)` | 否 | — |
| `job_id` | `VARCHAR(64)` | 否 | uv_ops_import_jobs.id |
| `entity_id` | `VARCHAR(64)` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | uv_ops_import_jobs.factory_id |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：factory_id = 'huakang-a'

唯一键：factory_id, id；factory_id, identity

索引：ix_uv_ops_import_rows_factory_id

## uv_ops_ink_balances

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `sku_id` | `VARCHAR(64)` | 否 | uv_ops_ink_skus.id |
| `lot` | `VARCHAR(64)` | 否 | — |
| `location` | `VARCHAR(64)` | 否 | — |
| `quantity_ml` | `NUMERIC(18, 6)` | 否 | — |
| `cost_value` | `NUMERIC(18, 6)` | 否 | — |
| `currency` | `VARCHAR(3)` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | uv_ops_ink_skus.factory_id |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：cost_value >= 0；factory_id = 'huakang-a'；quantity_ml >= 0

唯一键：factory_id, id；factory_id, sku_id, lot, location

索引：ix_uv_ops_ink_balances_factory_id

## uv_ops_ink_movements

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `balance_id` | `VARCHAR(64)` | 否 | uv_ops_ink_balances.id |
| `other_balance_id` | `VARCHAR(64)` | 是 | uv_ops_ink_balances.id |
| `task_id` | `VARCHAR(64)` | 是 | uv_ops_tasks.id |
| `kind` | `VARCHAR(24)` | 否 | — |
| `quantity_ml` | `NUMERIC(18, 6)` | 否 | — |
| `cost_value` | `NUMERIC(18, 6)` | 否 | — |
| `currency` | `VARCHAR(3)` | 否 | — |
| `business_date` | `VARCHAR(10)` | 否 | — |
| `reversal_of` | `VARCHAR(64)` | 是 | uv_ops_ink_movements.id |
| `evidence` | `TEXT` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | uv_ops_ink_balances.factory_id, uv_ops_ink_balances.factory_id, uv_ops_ink_movements.factory_id, uv_ops_tasks.factory_id |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：cost_value >= 0；factory_id = 'huakang-a'；quantity_ml > 0

唯一键：factory_id, id；factory_id, reversal_of

索引：ix_uv_ops_ink_movements_business_date, ix_uv_ops_ink_movements_factory_id

## uv_ops_ink_skus

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `code` | `VARCHAR(64)` | 否 | — |
| `supplier` | `VARCHAR(128)` | 否 | — |
| `model` | `VARCHAR(128)` | 否 | — |
| `ink_family` | `VARCHAR(64)` | 否 | — |
| `color` | `VARCHAR(32)` | 否 | — |
| `capacity_ml` | `NUMERIC(18, 6)` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | — |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：capacity_ml > 0；factory_id = 'huakang-a'

唯一键：factory_id, code；factory_id, id

索引：ix_uv_ops_ink_skus_factory_id

## uv_ops_machines

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `code` | `VARCHAR(64)` | 否 | — |
| `name` | `VARCHAR(128)` | 否 | — |
| `model` | `VARCHAR(128)` | 否 | — |
| `width_mm` | `NUMERIC(18, 6)` | 是 | — |
| `height_mm` | `NUMERIC(18, 6)` | 是 | — |
| `ink_family` | `VARCHAR(64)` | 否 | — |
| `maintenance` | `BOOLEAN` | 否 | — |
| `capability_evidence` | `TEXT` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | — |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：factory_id = 'huakang-a'；height_mm IS NULL OR height_mm > 0；width_mm IS NULL OR width_mm > 0

唯一键：factory_id, code；factory_id, id

索引：ix_uv_ops_machines_factory_id

## uv_ops_participations

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `active_key` | `INTEGER` | 是 | — |
| `shift_id` | `VARCHAR(64)` | 否 | uv_ops_shifts.id |
| `task_id` | `VARCHAR(64)` | 否 | uv_ops_tasks.id |
| `employee_id` | `VARCHAR(64)` | 否 | — |
| `employee_name` | `VARCHAR(128)` | 否 | — |
| `start_at` | `VARCHAR(40)` | 否 | — |
| `end_at` | `VARCHAR(40)` | 否 | — |
| `role_coefficient` | `NUMERIC(18, 6)` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | uv_ops_shifts.factory_id, uv_ops_tasks.factory_id |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：end_at > start_at；factory_id = 'huakang-a'；role_coefficient > 0

唯一键：factory_id, id

索引：ix_uv_ops_participations_factory_id

## uv_ops_periods

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `period` | `VARCHAR(7)` | 否 | — |
| `status` | `VARCHAR(24)` | 否 | — |
| `close_reason` | `TEXT` | 是 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | — |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：factory_id = 'huakang-a'；status IN ('open','closed')

唯一键：factory_id, id；factory_id, period

索引：ix_uv_ops_periods_factory_id

## uv_ops_price_policies

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `product_id` | `VARCHAR(64)` | 否 | uv_ops_products.id |
| `basis` | `VARCHAR(24)` | 否 | — |
| `rate` | `NUMERIC(18, 6)` | 否 | — |
| `currency` | `VARCHAR(3)` | 否 | — |
| `rectangle_area` | `BOOLEAN` | 否 | — |
| `measured_area_m2` | `NUMERIC(18, 6)` | 是 | — |
| `evidence` | `TEXT` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | uv_ops_products.factory_id |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：basis IN ('piece','area')；factory_id = 'huakang-a'；measured_area_m2 IS NULL OR measured_area_m2 > 0；rate >= 0

唯一键：factory_id, id

索引：ix_uv_ops_price_policies_factory_id

## uv_ops_process_versions

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `product_id` | `VARCHAR(64)` | 否 | uv_ops_products.id |
| `fixture_id` | `VARCHAR(64)` | 否 | uv_ops_fixtures.id |
| `revision` | `INTEGER` | 否 | — |
| `name` | `VARCHAR(128)` | 否 | — |
| `ink_family` | `VARCHAR(64)` | 否 | — |
| `pieces_per_board` | `INTEGER` | 否 | — |
| `cycle_seconds` | `NUMERIC(18, 6)` | 是 | — |
| `width_mm` | `NUMERIC(18, 6)` | 否 | — |
| `height_mm` | `NUMERIC(18, 6)` | 否 | — |
| `faces` | `INTEGER` | 否 | — |
| `passes` | `INTEGER` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | uv_ops_fixtures.factory_id, uv_ops_products.factory_id |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：cycle_seconds IS NULL OR cycle_seconds > 0；faces > 0；factory_id = 'huakang-a'；height_mm > 0；passes > 0；pieces_per_board > 0；width_mm > 0

唯一键：factory_id, id；factory_id, product_id, revision

索引：ix_uv_ops_process_versions_factory_id

## uv_ops_production_entries

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `task_id` | `VARCHAR(64)` | 否 | uv_ops_tasks.id |
| `batch_id` | `VARCHAR(64)` | 否 | uv_ops_batches.id |
| `shift_id` | `VARCHAR(64)` | 否 | uv_ops_shifts.id |
| `business_date` | `VARCHAR(10)` | 否 | — |
| `pass_index` | `INTEGER` | 否 | — |
| `source_bucket` | `VARCHAR(24)` | 否 | — |
| `processed` | `INTEGER` | 否 | — |
| `good` | `INTEGER` | 否 | — |
| `rework` | `INTEGER` | 否 | — |
| `scrap` | `INTEGER` | 否 | — |
| `pending` | `INTEGER` | 否 | — |
| `final_pass` | `BOOLEAN` | 否 | — |
| `direction` | `INTEGER` | 否 | — |
| `reversal_of` | `VARCHAR(64)` | 是 | uv_ops_production_entries.id |
| `evidence` | `TEXT` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | uv_ops_batches.factory_id, uv_ops_production_entries.factory_id, uv_ops_shifts.factory_id, uv_ops_tasks.factory_id |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：direction IN (-1,1)；factory_id = 'huakang-a'；good >= 0；pending >= 0；processed = good + rework + scrap + pending；processed > 0；rework >= 0；scrap >= 0

唯一键：factory_id, id；factory_id, reversal_of

索引：ix_uv_ops_production_entries_business_date, ix_uv_ops_production_entries_factory_id, ix_uv_ops_production_task_date

## uv_ops_products

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `code` | `VARCHAR(64)` | 否 | — |
| `name` | `VARCHAR(128)` | 否 | — |
| `customer` | `VARCHAR(128)` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | — |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：factory_id = 'huakang-a'

唯一键：factory_id, code；factory_id, id

索引：ix_uv_ops_products_factory_id

## uv_ops_quality_entries

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `active_key` | `INTEGER` | 是 | — |
| `batch_id` | `VARCHAR(64)` | 否 | uv_ops_batches.id |
| `task_id` | `VARCHAR(64)` | 否 | uv_ops_tasks.id |
| `production_entry_id` | `VARCHAR(64)` | 否 | uv_ops_production_entries.id |
| `shift_id` | `VARCHAR(64)` | 否 | uv_ops_shifts.id |
| `business_date` | `VARCHAR(10)` | 否 | — |
| `pass_index` | `INTEGER` | 否 | — |
| `quantity` | `INTEGER` | 否 | — |
| `disposition` | `VARCHAR(24)` | 否 | — |
| `evidence` | `TEXT` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | uv_ops_batches.factory_id, uv_ops_production_entries.factory_id, uv_ops_shifts.factory_id, uv_ops_tasks.factory_id |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：disposition IN ('good','rework','scrap')；factory_id = 'huakang-a'；quantity > 0

唯一键：factory_id, id

索引：ix_uv_ops_quality_entries_business_date, ix_uv_ops_quality_entries_factory_id

## uv_ops_receipts

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `actor_id` | `VARCHAR(64)` | 否 | — |
| `operation_id` | `VARCHAR(64)` | 否 | — |
| `action` | `VARCHAR(128)` | 否 | — |
| `payload_hash` | `VARCHAR(64)` | 否 | — |
| `permissions` | `JSON` | 否 | — |
| `result` | `JSON` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | — |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：factory_id = 'huakang-a'

唯一键：factory_id, actor_id, operation_id；factory_id, id

索引：ix_uv_ops_receipts_factory_id

## uv_ops_reference_efficiency

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `name` | `VARCHAR(128)` | 否 | — |
| `pieces_per_board` | `INTEGER` | 否 | — |
| `cycle_seconds` | `NUMERIC(18, 6)` | 否 | — |
| `available_seconds` | `NUMERIC(18, 6)` | 否 | — |
| `cost_amount` | `NUMERIC(18, 6)` | 是 | — |
| `currency` | `VARCHAR(3)` | 否 | — |
| `evidence` | `TEXT` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | — |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：available_seconds > 0；cost_amount >= 0；cycle_seconds > 0；factory_id = 'huakang-a'；pieces_per_board > 0

唯一键：factory_id, id

索引：ix_uv_ops_reference_efficiency_factory_id

## uv_ops_report_snapshots

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `period_id` | `VARCHAR(64)` | 否 | uv_ops_periods.id |
| `report` | `JSON` | 否 | — |
| `ledger_revision` | `VARCHAR(128)` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | uv_ops_periods.factory_id |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：factory_id = 'huakang-a'

唯一键：factory_id, id

索引：ix_uv_ops_report_snapshots_factory_id

## uv_ops_reversals

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `kind` | `VARCHAR(32)` | 否 | — |
| `entity_id` | `VARCHAR(64)` | 否 | — |
| `business_date` | `VARCHAR(10)` | 否 | — |
| `reason` | `TEXT` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | — |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：factory_id = 'huakang-a'；kind IN ('quality','expense','wage','run_cost','participation')

唯一键：factory_id, id；factory_id, kind, entity_id

索引：ix_uv_ops_reversals_factory_id

## uv_ops_rework_bindings

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `task_id` | `VARCHAR(64)` | 否 | uv_ops_tasks.id |
| `batch_id` | `VARCHAR(64)` | 否 | uv_ops_batches.id |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | uv_ops_batches.factory_id, uv_ops_tasks.factory_id |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：factory_id = 'huakang-a'

唯一键：factory_id, id；factory_id, task_id

索引：ix_uv_ops_rework_bindings_factory_id

## uv_ops_run_allocations

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `run_id` | `VARCHAR(64)` | 否 | uv_ops_runs.id |
| `task_id` | `VARCHAR(64)` | 否 | uv_ops_tasks.id |
| `batch_id` | `VARCHAR(64)` | 否 | uv_ops_batches.id |
| `pass_index` | `INTEGER` | 否 | — |
| `slots` | `JSON` | 否 | — |
| `full_boards` | `INTEGER` | 否 | — |
| `tail_pieces` | `INTEGER` | 否 | — |
| `share` | `NUMERIC(18, 6)` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | uv_ops_batches.factory_id, uv_ops_runs.factory_id, uv_ops_tasks.factory_id |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：factory_id = 'huakang-a'；full_boards >= 0；share <= 1；share > 0；tail_pieces >= 0

唯一键：factory_id, id；factory_id, run_id, task_id, batch_id, pass_index

索引：ix_uv_ops_run_allocations_factory_id

## uv_ops_run_costs

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `active_key` | `INTEGER` | 是 | — |
| `run_id` | `VARCHAR(64)` | 否 | uv_ops_runs.id |
| `business_date` | `VARCHAR(10)` | 否 | — |
| `cost_amount` | `NUMERIC(18, 6)` | 否 | — |
| `currency` | `VARCHAR(3)` | 否 | — |
| `evidence` | `TEXT` | 否 | — |
| `cost_allocations` | `JSON` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | uv_ops_runs.factory_id |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：cost_amount >= 0；factory_id = 'huakang-a'

唯一键：factory_id, id；factory_id, run_id, active_key

索引：ix_uv_ops_run_costs_factory_id

## uv_ops_runs

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `machine_id` | `VARCHAR(64)` | 否 | uv_ops_machines.id |
| `binding_id` | `VARCHAR(64)` | 否 | uv_ops_source_bindings.id |
| `native_job_id` | `VARCHAR(128)` | 否 | — |
| `native_identity` | `VARCHAR(64)` | 否 | — |
| `last_sequence` | `INTEGER` | 否 | — |
| `last_stream_id` | `VARCHAR(64)` | 是 | — |
| `last_binding_version` | `INTEGER` | 否 | — |
| `last_observed_at` | `VARCHAR(40)` | 否 | — |
| `file_name` | `VARCHAR(200)` | 否 | — |
| `file_hash` | `VARCHAR(64)` | 是 | — |
| `task_token` | `VARCHAR(64)` | 是 | — |
| `started_at` | `VARCHAR(40)` | 否 | — |
| `ended_at` | `VARCHAR(40)` | 是 | — |
| `state` | `VARCHAR(24)` | 否 | — |
| `raw_count` | `NUMERIC(18, 6)` | 是 | — |
| `count_unit` | `VARCHAR(16)` | 否 | — |
| `counter_mode` | `VARCHAR(24)` | 否 | — |
| `ink_total_ml` | `NUMERIC(18, 6)` | 是 | — |
| `match_evidence` | `TEXT` | 是 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | uv_ops_machines.factory_id, uv_ops_source_bindings.factory_id |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：factory_id = 'huakang-a'

唯一键：factory_id, id；factory_id, native_identity

索引：ix_uv_ops_runs_factory_id, ix_uv_ops_runs_machine_started, ix_uv_ops_runs_recent, ix_uv_ops_runs_unmatched

## uv_ops_schedule_blocks

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `machine_id` | `VARCHAR(64)` | 否 | uv_ops_machines.id |
| `task_id` | `VARCHAR(64)` | 否 | uv_ops_tasks.id |
| `batch_id` | `VARCHAR(64)` | 是 | uv_ops_batches.id |
| `fixture_id` | `VARCHAR(64)` | 是 | uv_ops_fixtures.id |
| `fixture_evidence` | `TEXT` | 是 | — |
| `estimate_basis` | `VARCHAR(24)` | 否 | — |
| `estimated_seconds` | `NUMERIC(18, 6)` | 是 | — |
| `estimate_reason` | `TEXT` | 是 | — |
| `start_at` | `VARCHAR(40)` | 否 | — |
| `end_at` | `VARCHAR(40)` | 否 | — |
| `fixed` | `BOOLEAN` | 否 | — |
| `status` | `VARCHAR(24)` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | uv_ops_batches.factory_id, uv_ops_fixtures.factory_id, uv_ops_machines.factory_id, uv_ops_tasks.factory_id |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：end_at > start_at；estimate_basis IN ('standard','manual')；estimated_seconds IS NULL OR estimated_seconds > 0；factory_id = 'huakang-a'

唯一键：factory_id, id；factory_id, task_id, batch_id

索引：ix_uv_ops_schedule_blocks_factory_id, ix_uv_ops_schedule_blocks_machine_id, ix_uv_ops_schedule_blocks_start_at, ix_uv_ops_schedule_machine_time

## uv_ops_settings

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `timezone` | `VARCHAR(64)` | 否 | — |
| `currency` | `VARCHAR(3)` | 否 | — |
| `stale_seconds` | `INTEGER` | 否 | — |
| `data_mode` | `VARCHAR(24)` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | — |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：factory_id = 'huakang-a'

唯一键：factory_id；factory_id, id

索引：ix_uv_ops_settings_factory_id

## uv_ops_shifts

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `name` | `VARCHAR(128)` | 否 | — |
| `business_date` | `VARCHAR(10)` | 否 | — |
| `start_at` | `VARCHAR(40)` | 否 | — |
| `end_at` | `VARCHAR(40)` | 否 | — |
| `breaks` | `JSON` | 否 | — |
| `status` | `VARCHAR(24)` | 否 | — |
| `close_reason` | `TEXT` | 是 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | — |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：end_at > start_at；factory_id = 'huakang-a'；status IN ('open','closed')

唯一键：factory_id, id

索引：ix_uv_ops_shifts_business_date, ix_uv_ops_shifts_factory_id

## uv_ops_source_bindings

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `agent_id` | `VARCHAR(64)` | 否 | uv_ops_agents.id |
| `machine_id` | `VARCHAR(64)` | 否 | uv_ops_machines.id |
| `source_id` | `VARCHAR(64)` | 否 | — |
| `adapter_type` | `VARCHAR(64)` | 否 | — |
| `binding_version` | `INTEGER` | 否 | — |
| `active_key` | `VARCHAR(64)` | 是 | — |
| `active_source_key` | `VARCHAR(64)` | 是 | — |
| `capabilities` | `JSON` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | uv_ops_agents.factory_id, uv_ops_machines.factory_id |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：factory_id = 'huakang-a'

唯一键：active_key；active_source_key；factory_id, agent_id, source_id, binding_version；factory_id, id

索引：ix_uv_ops_source_bindings_factory_id

## uv_ops_source_cursors

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `binding_id` | `VARCHAR(64)` | 否 | uv_ops_source_bindings.id |
| `stream_id` | `VARCHAR(64)` | 否 | — |
| `sequence` | `INTEGER` | 否 | — |
| `observed_at` | `VARCHAR(40)` | 否 | — |
| `work_state` | `VARCHAR(24)` | 否 | — |
| `progress` | `NUMERIC(18, 6)` | 是 | — |
| `progress_meaning` | `VARCHAR(32)` | 否 | — |
| `native_job_id` | `VARCHAR(128)` | 是 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | uv_ops_source_bindings.factory_id |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：factory_id = 'huakang-a'

唯一键：factory_id, binding_id；factory_id, id

索引：ix_uv_ops_source_cursors_factory_id

## uv_ops_tasks

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `code` | `VARCHAR(64)` | 否 | — |
| `demand_id` | `VARCHAR(64)` | 否 | uv_ops_demands.id |
| `process_version_id` | `VARCHAR(64)` | 否 | uv_ops_process_versions.id |
| `file_version_id` | `VARCHAR(64)` | 否 | uv_ops_file_versions.id |
| `wage_policy_id` | `VARCHAR(64)` | 是 | uv_ops_wage_policies.id |
| `price_policy_id` | `VARCHAR(64)` | 是 | uv_ops_price_policies.id |
| `parent_task_id` | `VARCHAR(64)` | 是 | uv_ops_tasks.id |
| `quantity` | `INTEGER` | 否 | — |
| `status` | `VARCHAR(24)` | 否 | — |
| `product_snapshot` | `VARCHAR(128)` | 否 | — |
| `process_snapshot` | `JSON` | 否 | — |
| `cost_price_snapshot` | `JSON` | 是 | — |
| `payroll_policy_snapshot` | `JSON` | 是 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | uv_ops_demands.factory_id, uv_ops_file_versions.factory_id, uv_ops_price_policies.factory_id, uv_ops_process_versions.factory_id, uv_ops_tasks.factory_id, uv_ops_wage_policies.factory_id |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：factory_id = 'huakang-a'；quantity > 0

唯一键：factory_id, code；factory_id, id

索引：ix_uv_ops_tasks_factory_id

## uv_ops_wage_accruals

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `active_key` | `INTEGER` | 是 | — |
| `shift_id` | `VARCHAR(64)` | 否 | uv_ops_shifts.id |
| `task_id` | `VARCHAR(64)` | 否 | uv_ops_tasks.id |
| `business_date` | `VARCHAR(10)` | 否 | — |
| `payroll_amount` | `NUMERIC(18, 6)` | 否 | — |
| `currency` | `VARCHAR(3)` | 否 | — |
| `payroll_evidence` | `JSON` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | uv_ops_shifts.factory_id, uv_ops_tasks.factory_id |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：factory_id = 'huakang-a'；payroll_amount >= 0

唯一键：factory_id, id；factory_id, shift_id, task_id, active_key

索引：ix_uv_ops_wage_accruals_business_date, ix_uv_ops_wage_accruals_factory_id

## uv_ops_wage_allocations

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `accrual_id` | `VARCHAR(64)` | 否 | uv_ops_wage_accruals.id |
| `employee_id` | `VARCHAR(64)` | 否 | — |
| `payroll_weight_seconds` | `NUMERIC(18, 6)` | 否 | — |
| `payroll_amount` | `NUMERIC(18, 6)` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | uv_ops_wage_accruals.factory_id |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：factory_id = 'huakang-a'；payroll_amount >= 0；payroll_weight_seconds >= 0

唯一键：factory_id, accrual_id, employee_id；factory_id, id

索引：ix_uv_ops_wage_allocations_factory_id

## uv_ops_wage_policies

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `name` | `VARCHAR(128)` | 否 | — |
| `basis` | `VARCHAR(24)` | 否 | — |
| `rate` | `NUMERIC(18, 6)` | 否 | — |
| `bonus_rate` | `NUMERIC(18, 6)` | 否 | — |
| `currency` | `VARCHAR(3)` | 否 | — |
| `evidence` | `TEXT` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | — |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：basis IN ('piece','hour','base_bonus')；bonus_rate >= 0；factory_id = 'huakang-a'；rate >= 0

唯一键：factory_id, id

索引：ix_uv_ops_wage_policies_factory_id

## uv_ops_workers

| 字段 | 类型 | 可空 | 关联 |
|---|---|---|---|
| `employee_id` | `VARCHAR(64)` | 否 | — |
| `name` | `VARCHAR(128)` | 否 | — |
| `id` | `VARCHAR(64)` | 否 | — |
| `factory_id` | `VARCHAR(32)` | 否 | — |
| `version` | `INTEGER` | 否 | — |
| `created_at` | `VARCHAR(40)` | 否 | — |
| `updated_at` | `VARCHAR(40)` | 否 | — |
| `created_by` | `VARCHAR(64)` | 否 | — |

约束：factory_id = 'huakang-a'

唯一键：factory_id, employee_id；factory_id, id

索引：ix_uv_ops_workers_factory_id
