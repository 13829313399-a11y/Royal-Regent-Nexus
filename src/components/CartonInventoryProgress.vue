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
  return { required, received, remaining, percent: required > 0 ? Math.min(100, Math.max(0, props.balance / required * 100)) : 0 }
})
const format = (value: number) => value.toLocaleString('zh-CN', { maximumFractionDigits: 4 })
</script>

<template>
  <div class="space-y-1.5 text-[10px] leading-4" aria-label="库存与到货进度">
    <div class="flex justify-between gap-2 tabular-nums"><span class="font-semibold text-teal-700">在库 {{ format(balance) }} {{ unit }}</span><span v-if="facts" class="text-slate-500">需求 {{ format(facts.required) }} {{ unit }}</span></div>
    <template v-if="facts">
      <div v-if="facts.required > 0" role="progressbar" aria-label="本仓位在库占订单需求" :aria-valuenow="facts.percent" :aria-valuemin="0" :aria-valuemax="100" :aria-valuetext="`本仓位在库 ${format(balance)} ${unit}，订单需求 ${format(facts.required)} ${unit}`" class="h-1.5 overflow-hidden rounded-full bg-slate-200"><div class="h-full rounded-full bg-teal-600" :style="{ width: `${facts.percent}%` }" /></div>
      <div class="flex flex-wrap items-center gap-x-2 gap-y-0.5 border-t border-slate-100 pt-1.5">
        <span class="tabular-nums text-slate-500">累计到货 {{ format(facts.received) }} {{ unit }}</span>
        <span v-if="facts.required === 0" class="text-slate-500">无订单需求</span>
        <span v-else-if="facts.remaining === 0" class="font-semibold text-teal-700">已到齐</span>
        <span v-else class="font-semibold text-amber-700">{{ facts.received > 0 ? '部分到货' : '未到货' }} · 还差 {{ format(facts.remaining) }} {{ unit }}</span>
      </div>
    </template>
    <span v-else class="text-slate-400">{{ formal ? '订单明细未匹配，暂不显示进度' : '无单库存 · 无订单到货进度' }}</span>
  </div>
</template>
