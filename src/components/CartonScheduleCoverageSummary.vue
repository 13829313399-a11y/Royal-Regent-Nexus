<script setup lang="ts">
import { computed } from 'vue'
import type { CartonImportBatchResponse } from '@/api/cartonProcurement'
import StatusPill from '@/components/common/StatusPill.vue'
import { formatBusinessDateTime } from '@/lib/dateTime'

const props = defineProps<{ batch: CartonImportBatchResponse }>()
const scope = computed(() => props.batch.parse_summary.schedule_coverage)
const mode = computed(() => scope.value?.scope_mode === 'FULL' ? '全量声明' : scope.value?.scope_mode === 'INCREMENTAL' ? '增量更新' : '范围未声明')
const excludedCount = computed(() => scope.value?.excluded_count ?? scope.value?.excluded_rows?.length ?? 0)
const duplicateRows = computed(() => props.batch.parse_summary.rows?.filter(row => row.schedule_identity_duplicate).length ?? 0)
</script>

<template>
  <section class="space-y-2 rounded-xl border border-border bg-card p-4 text-xs" aria-label="本批排期覆盖声明"><div class="flex flex-wrap items-center gap-3"><b>本批排期范围</b><StatusPill :label="mode" :tone="scope?.scope_mode === 'FULL' ? 'teal' : 'slate'" compact /><span>排期版本 {{ scope?.as_of_date || '未声明' }}</span><span class="text-muted-foreground">上传 {{ formatBusinessDateTime(batch.created_at) }}</span></div><p v-if="scope?.coverage_start && scope.coverage_end">客户交期 {{ scope.coverage_start }} 至 {{ scope.coverage_end }}（含首尾）</p><p v-if="scope?.scope_mode === 'FULL'" class="text-muted-foreground">仅对本次声明范围做缺行核实；不会自动取消采购单。缺行 {{ scope.missing_count ?? scope.missing_rows?.length ?? 0 }} 项，日期不完整或无效而排除 {{ excludedCount }} 行。</p><p v-else class="text-muted-foreground">{{ scope?.scope_mode === 'INCREMENTAL' ? '仅更新文件出现行，不据此推断缺行。' : '历史未声明覆盖范围，不补标全量，也不据此推断缺行。' }}</p><p v-if="duplicateRows" class="text-amber-800">重复身份相关 {{ duplicateRows }} 行，原行及数量分别保留；按整组出现 / 缺失核对，不合并采购需求。</p><details v-if="scope?.excluded_rows?.length" class="rounded-lg border border-input p-3"><summary class="cursor-pointer font-semibold">查看排除行依据（{{ excludedCount }}）</summary><p v-for="(row, index) in scope.excluded_rows" :key="`${row.batch_id}:${row.source_sheet}:${row.source_row}:${index}`" class="mt-2 break-words">{{ row.source_sheet }} · 第 {{ row.source_row }} 行 · {{ row.contract_no }} · {{ row.item_no }} · 日期原文 {{ row.source_customer_due_date || '未记录' }} · {{ row.reason }}</p></details></section>
</template>
