<script setup lang="ts">
import { computed } from 'vue'
import type { CartonOrderLineResponse } from '@/api/cartonProcurement'

const props = defineProps<{
  balance: number
  unit: string
  formal: boolean
  line?: CartonOrderLineResponse
}>()
const facts = computed(() => {
  const line = props.line
  if (!line || line.unit !== props.unit) return null
  const required = Number(line.required_quantity), received = Number(line.received_quantity), remaining = Number(line.remaining_quantity)
  if (![required, received, remaining].every(value => Number.isFinite(value) && value >= 0)) return null
  return { required, received, remaining }
})
const format = (value: number) => value.toLocaleString('zh-CN', { maximumFractionDigits: 4 })
</script>

<template>
  <div class="space-y-1 text-xs leading-5" aria-label="订单到货情况">
    <template v-if="facts">
      <span v-if="facts.required === 0" class="text-slate-500">无订单需求</span>
      <span v-else-if="facts.remaining === 0" class="inline-flex rounded-md bg-teal-50 px-2 py-0.5 font-semibold text-teal-700">已到齐</span>
      <span v-else class="font-semibold text-amber-700">{{ facts.received > 0 ? '部分到货' : '未到货' }}</span>
      <div class="tabular-nums text-slate-500">已到 {{ format(facts.received) }} / 需求 {{ format(facts.required) }} {{ unit }}</div>
      <div v-if="facts.remaining > 0" class="text-amber-700">还差 {{ format(facts.remaining) }} {{ unit }}</div>
    </template>
    <span v-else class="text-slate-400">{{ formal ? '订单明细未匹配' : '无单库存' }}</span>
  </div>
</template>
