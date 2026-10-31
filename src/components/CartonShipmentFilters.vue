<script setup lang="ts">
import CartonFilterBar from '@/components/CartonFilterBar.vue'
import { computed } from 'vue'
import type { PortalShipment } from '@/api/cartonSupplierPortal'
import { emptyShipmentFilters, type ShipmentFilters } from '@/features/carton-procurement/queryFilters'
const props = defineProps<{ rows: PortalShipment[]; hideSearch?: boolean; hideStatus?: boolean }>()
const emit = defineEmits<{ clear: [] }>()
const model = defineModel<ShipmentFilters>({ required: true })
const customers = computed(() => [...new Set(props.rows.flatMap(row => row.lines.map(line => line.customer_name)).filter(Boolean))].sort((a,b) => a.localeCompare(b, 'zh-CN')))
function clear() { const { sort, dateField } = model.value; model.value = { ...emptyShipmentFilters(), sort, dateField }; emit('clear') }
</script>
<template>
  <CartonFilterBar label="送货单筛选">
<slot />
<label v-if="!hideSearch" class="min-w-52 flex-1">关键字<input v-model="model.search" aria-label="送货单关键字" placeholder="客户 / 送货单 / 合同 / 货号" class="mt-1 h-9 w-full rounded-lg border px-3"></label>
<label>客户<select v-model="model.customer" aria-label="送货单客户" class="mt-1 block h-9 rounded-lg border px-2"><option value="">全部客户</option><option v-for="customer in customers" :key="customer">{{ customer }}</option></select></label>
<label>业务类型<select v-model="model.businessKind" aria-label="送货单业务类型" class="mt-1 block h-9 rounded-lg border px-2"><option value="">全部类型</option><option value="REGULAR">正单</option><option value="SAMPLE">样板</option><option value="MISC">杂单</option><option value="UNKNOWN">历史或无单</option></select></label>
<label v-if="!hideStatus">收货状态<select v-model="model.status" aria-label="送货单状态" class="mt-1 block h-9 rounded-lg border px-2"><option value="">全部状态</option><option value="PENDING_RECEIPT">待验收（含部分已收、冲销待更正）</option><option value="RECEIVED">已收货</option><option value="NOT_RECEIVED">未收到</option><option value="RECEIPT_REVERSED">冲销待更正</option></select></label>
<template #more><label>订单关联<select v-model="model.association" aria-label="送货单订单关联" class="mt-1 block h-9 rounded-lg border px-2"><option value="">全部关联</option><option value="UNMATCHED">含无单待核实</option><option value="MATCHED">全部已关联订单</option></select></label>
<label>日期口径<select v-model="model.dateField" aria-label="送货单日期口径" class="mt-1 block h-9 rounded-lg border px-2"><option value="DELIVERY">送货日期</option><option value="ACCEPTANCE">实际验收日期</option></select></label>
<label>起始日期<input v-model="model.from" aria-label="送货单起始日期" type="date" class="mt-1 block h-9 rounded-lg border px-2"></label>
<label>结束日期<input v-model="model.to" aria-label="送货单结束日期" type="date" class="mt-1 block h-9 rounded-lg border px-2"></label>
<label>排序<select v-model="model.sort" aria-label="送货单排序" class="mt-1 block h-9 rounded-lg border px-2"><option value="DESC">所选日期由新到旧</option><option value="ASC">所选日期由旧到新</option></select></label></template>
<template #actions><button type="button" class="h-9 rounded-lg border px-3" @click="clear">清除筛选</button>
<button type="button" class="h-9 rounded-lg border px-3" @click="model.sort = 'DESC'">恢复默认排序</button></template>
<template #footer><p v-if="model.status === 'PENDING_RECEIPT'" class="w-full text-slate-500">含供应商已发货未收、部分已收和入库被冲销待更正的单。</p>
<p v-if="model.businessKind" class="w-full text-slate-500">显示包含所选类型的整张送货单，同单其他纸品一并保留。</p>
<p v-if="model.from || model.to" class="w-full text-slate-500">{{ model.dateField === 'ACCEPTANCE' ? '按各批实际验收日期筛选；同一送货单分批验收时各批按自己的日期计算。' : '按送货日期筛选；月结仍按实际验收日期归月。' }}</p>
<p v-if="model.from && model.to && model.from > model.to" role="alert" class="w-full text-red-700">起始日期不能晚于结束日期。</p></template>
</CartonFilterBar>
</template>
