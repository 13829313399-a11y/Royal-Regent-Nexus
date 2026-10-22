<script setup lang="ts">
import '@/features/carton-procurement/layout.css'
interface ReceiptPaperOrder {
  order_no: string
  customer_name: string
  contract_no?: string
  customer_po?: string
  item_no?: string
  kind_label?: string
  lines: { id: string; packaging_type: string; paper_quality: string; specification: string; dimension_unit: string; required_quantity: string; received_quantity: string; remaining_quantity: string; pending_received_quantity?: string; unit: string }[]
}

interface PaperDraft {
  id: string
  orderLineId: string
  selectedForReceipt?: boolean
  receivedQuantity: number
  remainingQuantity: number
}

defineProps<{ order: ReceiptPaperOrder; drafts: PaperDraft[]; disabled?: boolean }>()
const emit = defineEmits<{
  select: [id: string, checked: boolean]
}>()
</script>

<template>
  <section :aria-label="`${order.order_no} 选择收料纸品`" class="border-t border-teal-100 bg-teal-50/40 px-4 py-3">
    <div class="mb-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-slate-600">
      <strong class="text-sm text-slate-900">{{ order.customer_name || '未关联客户' }} · {{ order.contract_no ? `合同 ${order.contract_no}` : order.kind_label }}</strong>
      <span v-if="order.contract_no">客户 PO：{{ order.customer_po || '未填写' }}</span><span v-if="order.item_no">货号：{{ order.item_no }}</span>
      <span>订单：{{ order.order_no }}</span>
    </div>
    <p class="mb-2 text-xs text-slate-500">勾选本次到货纸品，点击登记收料后填写送货数量、单价、缺陷和仓位；实收入库量自动扣减不可用数量，未勾选的纸品继续待收。</p>
    <div class="overflow-x-auto carton-table-wrap">
      <table class="w-full min-w-[780px] text-left text-xs carton-table-fit">
        <thead class="text-slate-500"><tr><th class="p-2">本次收料</th><th class="p-2">纸品类型</th><th class="p-2">纸质 / 规格</th><th class="p-2 text-right">需求</th><th class="p-2 text-right">已入库</th><th class="p-2 text-right">待入库</th></tr></thead>
        <tbody class="divide-y divide-teal-100">
          <tr v-for="line in order.lines" :key="line.id" :data-receipt-paper="line.id">
            <td data-label="本次收料" class="p-2"><input v-if="drafts.some(draft => draft.orderLineId === line.id)" type="checkbox" :aria-label="`选择纸品 ${line.id}`" :checked="drafts.find(draft => draft.orderLineId === line.id)?.selectedForReceipt !== false" :disabled="disabled" class="size-4 accent-teal-600" @change="emit('select', drafts.find(draft => draft.orderLineId === line.id)!.id, ($event.target as HTMLInputElement).checked)"><span v-else class="text-emerald-700">已收齐</span></td>
            <td data-label="纸品类型" class="p-2 font-semibold">{{ line.packaging_type }}</td><td data-label="纸质 / 规格" class="p-2"><div>{{ line.paper_quality || '待补纸质' }}</div><div class="mt-1 text-slate-500">{{ line.specification || '待补规格' }} {{ line.dimension_unit }}</div></td>
            <td data-label="需求" class="p-2 text-right tabular-nums">{{ Number(line.required_quantity) }} {{ line.unit }}</td><td data-label="已入库" class="p-2 text-right tabular-nums">{{ Number(line.received_quantity) }} {{ line.unit }}</td>
            <td data-label="待入库" class="p-2 text-right tabular-nums"><div>{{ Number(line.remaining_quantity) }} {{ line.unit }}</div><div v-if="Number(line.pending_received_quantity) > 0" class="mt-1 text-amber-700">待确认占用 {{ Number(line.pending_received_quantity) }}</div></td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
