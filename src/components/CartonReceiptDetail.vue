<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount } from 'vue'
import { X } from '@lucide/vue'
import type { CartonReceiptResponse } from '@/api/cartonProcurement'

const props = defineProps<{ receipt: CartonReceiptResponse; pinned: boolean; canContinue: boolean }>()
const emit = defineEmits<{ close: []; continue: [] }>()
const displayNote = computed(() => props.receipt.note?.startsWith('人工批量录入订单收料：') ? '人工录入收料' : props.receipt.note)
const status = computed(() => ({ DRAFT: '草稿', PENDING_CONFIRMATION: '待确认', POSTED: '已入库', REVERSED: props.receipt.confirmed_at ? '已冲销' : '已作废' })[props.receipt.status])
function quantity(value: string) {
  const [whole, fraction = ''] = value.split('.')
  const decimal = fraction.replace(/0+$/, '')
  return `${whole}${decimal ? `.${decimal}` : ''}`
}
function escape(event: KeyboardEvent) { if (event.key === 'Escape') emit('close') }
onMounted(() => window.addEventListener('keydown', escape))
onBeforeUnmount(() => window.removeEventListener('keydown', escape))
</script>

<template>
  <div data-testid="receipt-detail-overlay" class="fixed inset-0 z-[62] flex items-center justify-center p-4" :class="pinned ? 'pointer-events-auto bg-slate-950/45' : 'pointer-events-none bg-slate-950/25'" @click.self="emit('close')">
    <div role="dialog" aria-labelledby="receipt-detail-title" :aria-modal="pinned ? 'true' : undefined" :inert="!pinned" class="flex max-h-[88vh] w-full max-w-[1400px] flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
      <div class="flex shrink-0 items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
        <div><h2 id="receipt-detail-title" class="text-lg font-bold text-slate-950">收料明细 — {{ receipt.delivery_note_no }}</h2><p class="mt-1 text-xs text-teal-700">{{ pinned ? '已固定显示 · 可滚动查看整单明细' : '悬停预览 · 单击明细可固定' }}</p></div>
        <button type="button" aria-label="关闭收料明细" class="rounded-lg p-2 text-slate-400 hover:bg-slate-100" @click="emit('close')"><X class="size-4" /></button>
      </div>
      <div class="min-h-0 overflow-auto">
        <div class="flex flex-wrap gap-x-8 gap-y-3 border-b border-slate-100 bg-slate-50/60 px-5 py-4 text-xs text-slate-600">
          <span>收料单 <b class="ml-2 text-slate-900">{{ receipt.receipt_no }}</b></span><span>送货日期 <b class="ml-2 text-slate-900">{{ receipt.delivery_date }}</b></span><span>状态 <b class="ml-2 text-teal-700">{{ status }}</b></span>
          <span>登记人 <b class="ml-2 text-slate-900">{{ receipt.created_by_name || '未记录' }}</b></span><span v-if="receipt.confirmed_at">确认人 <b class="ml-2 text-slate-900">{{ receipt.confirmed_by_name || '未记录' }}</b></span>
        </div>
        <table aria-label="收料整单明细" class="w-full min-w-[1160px] text-left text-xs">
          <thead class="bg-slate-50 text-slate-500"><tr><th class="px-4 py-3">客户 / 合同 / 货号</th><th class="px-4 py-3">纸品 / 规格</th><th class="px-4 py-3 text-right">送货</th><th class="px-4 py-3 text-right">单价</th><th class="px-4 py-3 text-right">实收</th><th class="px-4 py-3 text-right">破损</th><th class="px-4 py-3 text-right">拒收</th><th class="px-4 py-3 text-right">其他不可用</th><th class="px-4 py-3 text-right">有效收料</th><th class="px-4 py-3">仓位</th></tr></thead>
          <tbody class="divide-y divide-slate-100"><tr v-for="line in receipt.lines" :key="line.id">
            <td class="px-4 py-4"><div class="font-semibold">{{ line.customer_name || line.customer_code }}</div><div class="mt-1 font-mono">{{ line.contract_no || '非正式收料' }}</div><div class="mt-1 font-mono text-slate-500">{{ line.item_no }}</div></td>
            <td class="px-4 py-4"><div class="font-semibold">{{ line.packaging_type }} {{ line.paper_quality }}</div><div class="mt-1 text-slate-500">{{ line.specification }}</div><div v-if="line.feedback_note" class="mt-1 text-slate-500">{{ line.feedback_note }}</div></td>
            <td class="px-4 py-4 text-right tabular-nums">{{ quantity(line.delivered_quantity) }}</td><td class="px-4 py-4 text-right tabular-nums"><div>{{ quantity(line.unit_price) }}</div><div class="mt-1 text-[10px] text-slate-500">{{ line.currency }} / {{ line.unit }}</div></td>
            <td class="px-4 py-4 text-right tabular-nums">{{ quantity(line.received_quantity) }}</td><td class="px-4 py-4 text-right tabular-nums">{{ quantity(line.damaged_quantity) }}</td><td class="px-4 py-4 text-right tabular-nums">{{ quantity(line.rejected_quantity) }}</td><td class="px-4 py-4 text-right tabular-nums">{{ quantity(line.unusable_quantity) }}</td><td class="whitespace-nowrap px-4 py-4 text-right font-bold text-teal-700">{{ quantity(line.effective_quantity) }} {{ line.unit }}</td><td class="px-4 py-4"><template v-if="line.location_allocations?.length"><div v-for="part in line.location_allocations" :key="part.location_id" class="whitespace-nowrap">{{ part.label || part.location_id }}：{{ Number(part.quantity) }} {{ line.unit }}</div></template><template v-else>{{ line.location || '未填写' }}</template></td>
          </tr></tbody>
        </table>
        <p v-if="displayNote" class="border-t border-slate-100 px-5 py-3 text-xs text-slate-500">备注：{{ displayNote }}</p>
      </div>
      <div v-if="pinned" class="flex shrink-0 justify-end gap-2 border-t border-slate-200 px-5 py-3">
        <button type="button" class="h-9 rounded-lg border border-slate-200 px-4 text-xs font-bold text-slate-600" @click="emit('close')">关闭</button>
        <button v-if="canContinue && receipt.status === 'PENDING_CONFIRMATION'" type="button" class="h-9 rounded-lg bg-teal-700 px-4 text-xs font-bold text-white" @click="emit('continue')">继续确认收料</button>
      </div>
    </div>
  </div>
</template>
