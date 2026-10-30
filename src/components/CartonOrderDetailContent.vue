<script setup lang="ts">
import { computed } from 'vue'
import CartonPrintSplitInfo from './CartonPrintSplitInfo.vue'
import { projectSplitLedger } from '@/features/carton-procurement/splitLedgerProjection'
import type { CartonOrderResponse } from '@/api/cartonProcurement'
import CartonOrderSummary from './CartonOrderSummary.vue'
import CartonOrderPaperTable from './CartonOrderPaperTable.vue'
import CartonOrderPaperSummary from './CartonOrderPaperSummary.vue'
const props = defineProps<{
  fields: InstanceType<typeof CartonOrderSummary>['$props']['fields']
  rows: InstanceType<typeof CartonOrderPaperTable>['$props']['rows']
  supplier?: boolean
  ruleLabel?: string
  order?: CartonOrderResponse
}>()
const splitSource = computed(() => {
  const source = props.order?.schedule_split_source
  return source?.current_contract_no === props.order?.contract_no ? source : null
})
const splitRecords = computed(() => props.order?.split_records?.filter(record =>
  record.factory_id === props.order?.factory_id && record.order_id === props.order?.id &&
  record.customer_code === props.order?.customer_code && record.item_no === props.order?.item_no) || [])
const allocation = computed(() => props.order ? projectSplitLedger(props.order) : null)
const targetAllocation = (planId: string, index: number) => allocation.value?.children.find(child => child.planId === planId && child.targetIndex === index)
const splitStatus = { ACTIVE: '已生效', PENDING_WAREHOUSE: '待仓库确认', CANCELLED: '已取消（历史记录）' }
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
  <CartonPrintSplitInfo v-if="order?.print_split" :info="order.print_split" :factory="order.factory_id" :supplier="supplier" />
  <p v-if="order?.order_split?.source_order_no" class="rounded-lg bg-sky-50 p-3 text-sm text-sky-900">拆单来源：{{ order.order_split.source_contract_no }}（{{ order.order_split.source_order_no }}）。本单独立送货、收料和核算库存。</p>
  <p v-if="order?.order_split?.children.length" class="text-xs text-slate-600">已拆出：{{ order.order_split.children.map(child => `${child.contract_no}（${child.order_no}）`).join('、') }}</p>
  <div class="min-w-0 space-y-4" data-testid="shared-order-detail">
    <CartonOrderSummary :fields="fields" />
    <slot name="status" />
    <section v-if="splitSource || splitRecords.length" aria-label="拆单来源与去向" class="min-w-0 space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-4 text-xs">
      <h3 class="font-semibold text-slate-800">拆单来源与去向</h3>
      <div v-if="splitSource" class="space-y-1 break-words">
        <p><span class="text-slate-500">排期拆单来源：</span><strong>{{ splitSource.source_contract_no }} → {{ splitSource.current_contract_no }}</strong></p>
        <p class="text-slate-500">排期 {{ splitSource.source_sheet }} · 第 {{ splitSource.source_row }} 行。来源由业务排期提供。</p>
      </div>
      <div v-if="allocation?.valid && allocation.children.length" class="space-y-1 rounded-lg border border-teal-200 bg-white p-3" aria-label="原合同保留数量">
        <p class="font-semibold text-teal-800">原合同 {{ order?.contract_no }} · 当前保留</p>
        <p v-for="line in allocation.parent.lines" :key="line.orderLineId">{{ line.packagingType }} · {{ line.paperQuality }} · {{ line.specification }}：{{ line.quantity }} {{ line.unit }}，已到 {{ line.received }} {{ line.unit }}，待到 {{ line.remaining }} {{ line.unit }}</p>
        <p class="text-slate-500">待仓库确认的拆分尚未扣减；原合同与生效子单合计等于原采购量。</p>
      </div>
      <p v-if="allocation && !allocation.valid" role="alert" class="text-amber-800">{{ allocation.errors[0] }}</p>
      <div v-for="record in splitRecords" :key="record.id" class="space-y-2 border-t border-slate-200 pt-3" :class="record.status === 'CANCELLED' ? 'text-slate-500' : 'text-slate-800'">
        <div class="flex flex-wrap items-center gap-2">
          <span class="font-semibold">{{ record.status === 'CANCELLED' ? '历史拆出去向（已取消）' : '本单拆出' }}</span>
          <span class="rounded border px-2 py-1" :class="record.status === 'PENDING_WAREHOUSE' ? 'border-amber-200 bg-amber-50 text-amber-800' : 'border-slate-200'">{{ splitStatus[record.status] }}</span>
        </div>
        <ul class="space-y-2">
          <li v-for="(target, index) in record.targets" :key="index" class="flex flex-wrap gap-x-5 gap-y-1 break-words">
            <strong>{{ record.original_contract_no || order?.contract_no }} → {{ target.contract_no }}</strong>
            <span>客户 PO：{{ target.customer_po || '未填写' }}</span>
            <span>产品数量：{{ target.product_quantity ?? '未填写' }}</span>
            <div v-if="targetAllocation(record.id, index)" class="basis-full space-y-1 text-slate-600">
              <p v-for="line in targetAllocation(record.id, index)!.lines" :key="line.orderLineId">
                {{ line.packagingType }} · {{ line.paperQuality }} · {{ line.specification }}：{{ line.quantity }} {{ line.unit }}
                <template v-if="record.status === 'ACTIVE'">，已到 {{ line.received }} {{ line.unit }}，待到 {{ line.remaining }} {{ line.unit }}</template>
                <template v-else>（预计归属，尚未计入到货）</template>
              </p>
            </div>
          </li>
        </ul>
      </div>
      <p class="text-slate-500">采购拆分记录的是本单数量归属，不另建重复采购单；已取消记录仅供追溯。</p>
    </section>
    <h3 v-if="allocation?.children.length" class="text-sm font-semibold text-slate-800">原采购单纸品（含拆出数量）</h3>
    <CartonOrderPaperTable :rows="rows" :supplier="supplier" :rule-label="ruleLabel" />
    <CartonOrderPaperSummary :count="rows.length" v-bind="totals" />
    <slot />
  </div>
</template>
