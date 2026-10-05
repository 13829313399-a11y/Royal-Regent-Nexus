<script setup lang="ts">
import type { CartonOrderResponse } from '@/api/cartonProcurement'

interface PaperDraft {
  id: string
  orderLineId: string
  selectedForReceipt?: boolean
  receivedQuantity: number
  remainingQuantity: number
}

defineProps<{ order: CartonOrderResponse; drafts: PaperDraft[]; disabled?: boolean }>()
const emit = defineEmits<{
  select: [id: string, checked: boolean]
  quantity: [id: string, quantity: number]
}>()
</script>

<template>
  <section :aria-label="`${order.order_no} 选择收料纸品`" class="border-t border-teal-100 bg-teal-50/40 px-4 py-3">
    <div class="mb-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-slate-600">
      <strong class="text-sm text-slate-900">{{ order.customer_name }} · 合同 {{ order.contract_no }}</strong>
      <span>客户 PO：{{ order.customer_po || '未填写' }}</span><span>货号：{{ order.item_no }}</span>
      <span>订单：{{ order.order_no }}</span>
    </div>
    <p class="mb-2 text-xs text-slate-500">勾选本次到货纸品，分别填写实际收到数量；未勾选的纸品继续待收。单价、缺陷及仓位在入库前核对。</p>
    <div class="overflow-x-auto">
      <table class="w-full min-w-[780px] text-left text-xs">
        <thead class="text-slate-500"><tr><th class="p-2">本次收料</th><th class="p-2">纸品类型</th><th class="p-2">纸质 / 规格</th><th class="p-2 text-right">需求</th><th class="p-2 text-right">已入库</th><th class="p-2 text-right">待入库</th><th class="p-2 text-right">本次实际收到</th></tr></thead>
        <tbody class="divide-y divide-teal-100">
          <tr v-for="line in order.lines" :key="line.id" :data-receipt-paper="line.id">
            <td class="p-2"><input v-if="drafts.some(draft => draft.orderLineId === line.id)" type="checkbox" :aria-label="`选择纸品 ${line.id}`" :checked="drafts.find(draft => draft.orderLineId === line.id)?.selectedForReceipt !== false" :disabled="disabled" class="size-4 accent-teal-600" @change="emit('select', `MANUAL-${line.id}`, ($event.target as HTMLInputElement).checked)"><span v-else class="text-emerald-700">已收齐</span></td>
            <td class="p-2 font-semibold">{{ line.packaging_type }}</td><td class="p-2"><div>{{ line.paper_quality || '待补纸质' }}</div><div class="mt-1 text-slate-500">{{ line.specification || '待补规格' }} {{ line.dimension_unit }}</div></td>
            <td class="p-2 text-right tabular-nums">{{ Number(line.required_quantity) }} {{ line.unit }}</td><td class="p-2 text-right tabular-nums">{{ Number(line.received_quantity) }} {{ line.unit }}</td>
            <td class="p-2 text-right tabular-nums"><div>{{ Number(line.remaining_quantity) }} {{ line.unit }}</div><div v-if="Number(line.pending_received_quantity) > 0" class="mt-1 text-amber-700">待确认占用 {{ Number(line.pending_received_quantity) }}</div></td>
            <td class="p-2 text-right"><input v-if="drafts.some(draft => draft.orderLineId === line.id)" :value="drafts.find(draft => draft.orderLineId === line.id)?.receivedQuantity || ''" :aria-label="`${line.id} 本次实际收到`" :disabled="disabled || drafts.find(draft => draft.orderLineId === line.id)?.selectedForReceipt === false" type="number" min="0" step="0.0001" :max="drafts.find(draft => draft.orderLineId === line.id)?.remainingQuantity" placeholder="填写实收" class="h-9 w-28 rounded border border-slate-200 bg-white px-2 text-right disabled:bg-slate-100" @input="emit('quantity', `MANUAL-${line.id}`, Number(($event.target as HTMLInputElement).value))"><span v-else>—</span></td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
