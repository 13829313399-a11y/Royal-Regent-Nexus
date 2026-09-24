<script setup lang="ts">
import { computed } from 'vue'
import type { CartonImportBatchResponse } from '@/api/cartonProcurement'

const props = defineProps<{ batch?: CartonImportBatchResponse }>()
const summary = computed(() => props.batch?.parse_summary)
const counts = computed(() => {
  const rows = summary.value?.rows ?? []
  return {
    formal: rows.filter(row => row.order_type === '正单').length,
    review: rows.filter(row => row.match_status === 'REVIEW_REQUIRED' || row.match_status === 'AMBIGUOUS' || row.procurement_state === 'REVIEW' || row.date_review_required).length,
    needs: rows.filter(row => row.procurement_state === 'NEEDS_ORDER').length,
    ordered: rows.filter(row => row.procurement_state === 'ORDERED').length,
    completed: rows.filter(row => row.procurement_state === 'COMPLETED').length,
  }
})
const fieldLabels: Record<string, string> = {
  contract_no: '合同号', source_reference: 'SO / Reference', customer_po: '客户 PO',
  order_type: '订单类型', production_no: '生产单号', customer_name: '业务客名',
  item_no: '货号', product_name: '产品名称', quantity: '产品数量', carton_rule: '装箱',
  carton_count: '箱数', inspection_window: '验货日期', customer_due_date: '客户走货期', note: '备注',
}
</script>

<template>
  <article v-if="summary?.engine === 'unified-item-header-mapping'" class="rounded-xl border border-teal-200 bg-teal-50/40 p-4" aria-label="统一业务模板核对摘要">
    <h3 class="font-semibold text-slate-900">统一业务模板 · ITEM 表</h3>
    <div class="mt-3 flex flex-wrap gap-x-6 gap-y-2 text-sm">
      <span>正单 {{ counts.formal }} 行</span>
      <span class="font-semibold text-amber-800">需要下单 {{ counts.needs }}</span>
      <span>已下单 {{ counts.ordered }}</span>
      <span>已完单 {{ counts.completed }}</span>
      <span class="text-amber-800">待人工确认 {{ counts.review }} 行</span>
    </div>
    <p class="mt-2 text-xs leading-5 text-slate-600">仅正单参与自动核对。已完单表示采购收料完成，对账进度单独保留。核对结果是本次导入时的快照。</p>
    <p v-for="warning in summary.warnings" :key="warning" class="mt-1 text-xs text-slate-600">{{ warning }}</p>
    <details class="mt-3 text-xs">
      <summary class="cursor-pointer font-medium text-teal-800">查看识别的工作表和字段</summary>
      <div v-for="mapping in summary.field_mappings" :key="mapping.sheet" class="mt-3 rounded-lg border border-slate-200 bg-white p-3">
        <p class="font-semibold">{{ mapping.sheet }} · 第 {{ mapping.header_row }} 行表头</p>
        <dl class="mt-2 grid gap-x-6 gap-y-1 sm:grid-cols-2 lg:grid-cols-3">
          <div v-for="(source, field) in mapping.fields" :key="field" class="flex gap-2">
            <dt class="text-slate-500">{{ fieldLabels[field] ?? field }}</dt><dd>{{ source }}</dd>
          </div>
        </dl>
      </div>
    </details>
  </article>
</template>
