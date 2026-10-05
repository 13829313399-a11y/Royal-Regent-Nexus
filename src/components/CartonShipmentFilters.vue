<script setup lang="ts">
import { computed } from 'vue'
import type { PortalShipment } from '@/api/cartonSupplierPortal'
import { emptyShipmentFilters, type ShipmentFilters } from '@/features/carton-procurement/queryFilters'
const props = defineProps<{ rows: PortalShipment[] }>()
const emit = defineEmits<{ clear: [] }>()
const model = defineModel<ShipmentFilters>({ required: true })
const customers = computed(() => [...new Set(props.rows.flatMap(row => row.lines.map(line => line.customer_name)).filter(Boolean))].sort((a,b) => a.localeCompare(b, 'zh-CN')))
function clear() { const { sort, dateField } = model.value; model.value = { ...emptyShipmentFilters(), sort, dateField }; emit('clear') }
</script>
<template>
  <div class="flex flex-wrap items-end gap-2 rounded-xl border border-slate-200 bg-white p-3 text-xs" aria-label="送货单筛选">
    <label class="min-w-52 flex-1">关键字<input v-model="model.search" aria-label="送货单关键字" placeholder="客户 / 送货单 / 合同 / 货号" class="mt-1 h-9 w-full rounded-lg border px-3"></label>
    <label>客户<select v-model="model.customer" aria-label="送货单客户" class="mt-1 block h-9 rounded-lg border px-2"><option value="">全部客户</option><option v-for="customer in customers" :key="customer">{{ customer }}</option></select></label>
    <label>收货状态<select v-model="model.status" aria-label="送货单状态" class="mt-1 block h-9 rounded-lg border px-2"><option value="">全部状态</option><option value="SENT">待核实</option><option value="RECEIVED">已收货</option><option value="NOT_RECEIVED">未收到</option><option value="RECEIPT_REVERSED">冲销待更正</option></select></label>
    <label>订单关联<select v-model="model.association" aria-label="送货单订单关联" class="mt-1 block h-9 rounded-lg border px-2"><option value="">全部关联</option><option value="UNMATCHED">含无单待核实</option><option value="MATCHED">全部已关联订单</option></select></label>
    <label>日期口径<select v-model="model.dateField" aria-label="送货单日期口径" class="mt-1 block h-9 rounded-lg border px-2"><option value="DELIVERY">送货日期</option><option value="ACCEPTANCE">实际验收日期</option></select></label>
    <label>起始日期<input v-model="model.from" aria-label="送货单起始日期" type="date" class="mt-1 block h-9 rounded-lg border px-2"></label>
    <label>结束日期<input v-model="model.to" aria-label="送货单结束日期" type="date" class="mt-1 block h-9 rounded-lg border px-2"></label>
    <label>排序<select v-model="model.sort" aria-label="送货单排序" class="mt-1 block h-9 rounded-lg border px-2"><option value="DESC">所选日期由新到旧</option><option value="ASC">所选日期由旧到新</option></select></label>
    <button type="button" class="h-9 rounded-lg border px-3" @click="clear">清除筛选</button><button type="button" class="h-9 rounded-lg border px-3" @click="model.sort = 'DESC'">恢复默认排序</button>
    <p v-if="model.from && model.to && model.from > model.to" role="alert" class="w-full text-red-700">起始日期不能晚于结束日期。</p>
  </div>
</template>
