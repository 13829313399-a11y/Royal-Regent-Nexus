<script setup lang="ts">
export interface LedgerOrderPresentation {
  orderNo: string; orderDate: string; kind: string; customer: string; identity: string; customerPo?: string; item: string
  papers: { label: string; quantity: number; unit: string }[]; quantity: number; received: number; remaining: number; progress: number
  dates: { label: string; value: string }[]; status: string; tone: string; due: string; dueTone: string
}
defineProps<{ row: LedgerOrderPresentation; selected: boolean }>()
const emit = defineEmits<{ select: [value: boolean] }>()
const format = (value: number) => value.toLocaleString('zh-CN', { maximumFractionDigits: 4 })
const shortDate = (value: string) => value ? value.slice(5, 10).replace('-', '/') : '未记录'
</script>
<template>
  <article class="relative border-b border-slate-100 transition-colors last:rounded-b-xl last:border-b-0" :class="selected ? 'bg-teal-50/60' : 'hover:bg-teal-50/40'">
    <div class="order-ledger-grid grid grid-cols-2 gap-x-4 gap-y-2 px-4 py-3.5 sm:grid-cols-3 xl:items-center xl:gap-x-3">
      <div class="min-w-0"><div class="label">下单日期</div><div class="grid grid-cols-[1.25rem_minmax(0,1fr)] items-center gap-x-1.5"><input type="checkbox" :checked="selected" :aria-label="`选择订单 ${row.orderNo}`" class="size-5 shrink-0 cursor-pointer accent-teal-600" @change="emit('select', ($event.target as HTMLInputElement).checked)"><span class="text-[13px] font-semibold leading-tight tabular-nums text-slate-800" :title="row.orderDate">{{ shortDate(row.orderDate) }}<span class="mt-1 block text-[10px] text-teal-700">{{ row.kind }}</span></span></div></div>
      <div class="min-w-0 text-left" :aria-label="`${row.orderNo} 客户`"><div class="label">客户</div><div class="truncate text-[13px] font-semibold leading-tight text-slate-800" :title="row.customer">{{ row.customer }}</div></div>
      <div class="min-w-0 text-left" :aria-label="`${row.orderNo} 单号`"><div class="label">合同 / 单号</div><div class="truncate font-mono text-[13px] font-bold leading-tight text-slate-950" :title="row.identity">{{ row.identity }}</div><div v-if="row.customerPo" class="mt-1 break-all text-[10px] text-teal-700">客户 PO {{ row.customerPo }}</div></div>
      <div class="min-w-0 text-left"><div class="label">货号</div><div class="truncate font-mono text-[13px] font-bold text-slate-950" :title="row.item">{{ row.item }}</div></div>
      <div class="min-w-0 text-left" :aria-label="`${row.orderNo} 纸品明细`"><div class="label">纸品明细</div><div class="whitespace-nowrap text-[11px] text-slate-500">纸品合计 <b class="text-[13px] tabular-nums text-slate-950">{{ format(row.quantity) }}</b> 件</div><div class="mt-1 flex flex-wrap gap-1"><span v-for="(line, index) in row.papers" :key="index" class="inline-flex items-center gap-1 rounded border border-slate-200 bg-white px-1.5 py-0.5 text-[9px] leading-none text-slate-600">{{ line.label }} <b class="tabular-nums text-teal-700">{{ format(line.quantity) }}</b><span>{{ line.unit }}</span></span></div></div>
      <div class="min-w-0 text-left"><div class="label">交期</div><div class="grid w-fit max-w-full grid-cols-[1.5rem_minmax(0,1fr)] items-center gap-x-1 gap-y-1"><template v-for="date in row.dates" :key="date.label"><span class="text-center text-[10px] font-bold text-slate-400">{{ date.label }}</span><span class="text-[13px] font-bold tabular-nums text-slate-950" :title="date.value">{{ shortDate(date.value) }}</span></template></div></div>
      <div class="min-w-0 text-right" :aria-label="`${row.orderNo} 到货进度`"><div class="label">到货进度</div><div class="flex items-center gap-2"><span class="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-slate-200"><span class="block h-full rounded-full bg-emerald-600" :style="{ width: `${row.progress}%` }"></span></span><span class="shrink-0 text-[11px] font-semibold tabular-nums text-slate-700">{{ format(row.received) }}/{{ format(row.quantity) }}</span></div><div v-if="row.remaining > 0" class="mt-1 text-[10px] font-semibold tabular-nums text-red-600">待 {{ format(row.remaining) }} 件</div><div v-else class="mt-1 text-[10px] font-semibold text-emerald-700">已齐</div></div>
      <div class="min-w-0 text-left"><div class="label">订单状态</div><span class="inline-flex rounded-full px-2 py-0.5 text-[10px] font-bold ring-1 ring-inset" :class="row.tone">{{ row.status }}</span><slot name="status" /></div>
      <div class="min-w-0 text-left" :aria-label="`${row.orderNo} 交期提醒`"><div class="label">交期提醒</div><span class="text-[11px] font-semibold" :class="row.dueTone">{{ row.due }}</span><slot name="reminders" /></div>
      <div class="relative col-span-2 flex h-full min-w-0 items-center xl:col-span-1" :aria-label="`${row.orderNo} 操作`"><slot name="actions" /></div>
    </div>
  </article>
</template>
<style scoped>
.label { margin-bottom:4px; font-size:10px; font-weight:700; color:#94a3b8; }
@media(min-width:1280px) { .label { display:none; } .order-ledger-grid { grid-template-columns:minmax(0,.65fr) minmax(4.25rem,.45fr) minmax(0,.78fr) minmax(0,.55fr) minmax(0,.85fr) minmax(0,.74fr) 8.75rem 6.5rem 6.25rem 14.5rem; } }
</style>
