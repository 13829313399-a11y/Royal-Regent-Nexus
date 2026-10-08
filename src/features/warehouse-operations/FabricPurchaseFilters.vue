<script setup lang="ts">
import { computed, shallowRef, watch } from 'vue'
import type { DateRange } from 'reka-ui'
import DateRangeFilter from '@/components/DateRangeFilter.vue'
import { Button } from '@/components/ui/button'
import type { PurchaseFilters, PurchaseView } from '@/api/fabricProcurement'
defineProps<{ busy: boolean; pending: boolean; headerSearch?: boolean; options?: { suppliers: string[]; units: string[]; imports?: { id: string; name: string }[] } }>()
const filters = defineModel<PurchaseFilters>({ required: true })
const view = defineModel<PurchaseView>('view', { required: true })
const search = defineModel<string>('search', { required: true })
const emit = defineEmits<{ query: []; clear: [] }>()
const calendarRange = shallowRef<DateRange>({ start: undefined, end: undefined })
const dates = computed({ get: () => calendarRange.value, set: (value: DateRange) => {
  calendarRange.value = value; filters.value.promise_from = value.start?.toString() ?? ''; filters.value.promise_to = value.end?.toString() ?? ''; emit('query')
} })
watch(() => [filters.value.promise_from, filters.value.promise_to], ([from, to]) => { if (!from && !to) calendarRange.value = { start: undefined, end: undefined } })
watch(() => filters.value.unit, unit => { if (!unit && filters.value.sort?.startsWith('QUANTITY')) filters.value.sort = 'OVERDUE' })
</script>
<template>
  <form class="fabric-purchase-filters" @submit.prevent="emit('query')">
    <label v-if="!headerSearch" class="fabric-search-fallback">查找采购明细<input v-model="search" type="search" maxlength="128" placeholder="采购单 / 生产单 / 款号 / 物料 / 供应商" aria-label="查找采购明细" /></label>
    <fieldset :disabled="busy" class="fabric-filter-bar">
      <label>供应商<select v-model="filters.supplier" aria-label="供应商筛选" @change="emit('query')"><option value="">全部供应商</option><option v-for="supplier in options?.suppliers" :key="supplier">{{ supplier }}</option></select></label>
      <label>采购类型<select v-model="filters.source_category" aria-label="采购类型筛选" @change="emit('query')"><option value="">全部类型</option><option value="PURCHASE">正常采购</option><option value="SUPPLEMENT">补数</option></select></label>
      <label v-if="pending">跟进范围<select v-model="view" aria-label="待收料跟进范围" @change="emit('query')"><option value="OUTSTANDING">全部未齐料</option><option value="NOT_ARRIVED">尚未收料 / 数量待核对</option><option value="PARTIAL">部分到货，仍有欠料</option><option value="ARRIVAL_REVIEW">采购报到货，仓库待核对</option><option value="CHANGED">订单变更未读</option><option value="OVERDUE">复期已过</option><option value="DUE_TODAY">今天到期</option><option value="AWAITING_DATE">待供应商复期</option><option value="QUANTITY_REVIEW">起始数量待核对</option></select></label>
      <div class="fabric-filter-date" role="group" aria-label="供应商复期范围"><span>复期</span><DateRangeFilter v-model="dates" label="选择供应商复期范围" /></div>
      <label>排序<select v-model="filters.sort" aria-label="采购明细排序" @change="emit('query')"><option value="OVERDUE">逾期最长优先</option><option value="PROMISE">复期由早到晚</option><option value="ORDER">采购单号</option><option value="SUPPLIER">供应商名称</option><option value="UPDATED">最近更新</option><option value="QUANTITY_ASC" :disabled="!filters.unit">待收数量从少到多（同单位）</option><option value="QUANTITY_DESC" :disabled="!filters.unit">待收数量从多到少（同单位）</option></select></label>
      <details class="fabric-filter-extra"><summary>更多筛选</summary><div class="fabric-filter-extra-fields">
        <label>物料分类<select v-model="filters.category" aria-label="物料分类筛选" @change="emit('query')"><option value="">全部分类</option><option value="FABRIC">布料</option><option value="ACCESSORY">辅料</option><option value="THREAD">线</option><option value="UNCLASSIFIED">未分类</option></select></label>
        <label>单位<select v-model="filters.unit" aria-label="采购单位筛选" @change="emit('query')"><option value="">全部单位</option><option v-for="unit in options?.units" :key="unit">{{ unit }}</option></select></label>
        <label>数量核对<select v-model="filters.quantity_review" aria-label="数量核对筛选" @change="emit('query')"><option value="">全部数量状态</option><option value="REVIEW">待核对</option><option value="KNOWN">已明确</option></select></label>
        <label>导入批次<select v-model="filters.import_batch" aria-label="导入批次筛选" @change="emit('query')"><option value="">全部有效导入</option><option v-for="batch in options?.imports" :key="batch.id" :value="batch.id">{{ batch.name }}</option></select></label>
      </div></details>
      <Button type="submit" variant="outline" size="sm">刷新</Button><Button type="button" variant="outline" size="sm" @click="emit('clear')">清空筛选</Button><slot />
    </fieldset>
  </form>
</template>
