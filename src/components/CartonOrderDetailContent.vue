<script setup lang="ts">
import { computed } from 'vue'
import CartonOrderSummary from './CartonOrderSummary.vue'
import CartonOrderPaperTable from './CartonOrderPaperTable.vue'
import CartonOrderPaperSummary from './CartonOrderPaperSummary.vue'
const props = defineProps<{
  fields: InstanceType<typeof CartonOrderSummary>['$props']['fields']
  rows: InstanceType<typeof CartonOrderPaperTable>['$props']['rows']
  supplier?: boolean
  ruleLabel?: string
}>()
const totals = computed(() => {
  const grouped = new Map<string, { required: number; received: number; remaining: number }>()
  for (const row of props.rows) {
    const group = grouped.get(row.unit) || { required: 0, received: 0, remaining: 0 }
    for (const key of ['required', 'received', 'remaining'] as const) group[key] += Math.round(row[key] * 10000)
    grouped.set(row.unit, group)
  }
  const text = (key: 'required' | 'received' | 'remaining') => [...grouped].map(([unit, value]) => `${(value[key] / 10000).toLocaleString('zh-CN', { maximumFractionDigits: 4 })} ${unit}`).join(' · ')
  return { required: text('required'), received: text('received'), remaining: text('remaining') }
})
</script>
<template>
  <div class="min-w-0 space-y-4" data-testid="shared-order-detail">
    <CartonOrderSummary :fields="fields" />
    <slot name="status" />
    <CartonOrderPaperTable :rows="rows" :supplier="supplier" :rule-label="ruleLabel" />
    <CartonOrderPaperSummary :count="rows.length" v-bind="totals" />
    <slot />
  </div>
</template>
