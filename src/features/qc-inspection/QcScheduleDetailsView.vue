<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { CalendarDays, ChevronLeft, ChevronRight } from '@lucide/vue'
import { qcInspectionApi, type QcInspectionOrder } from '@/api/qcInspection'
import { Button } from '@/components/ui/button'
import { getApiErrorMessage } from '@/lib/http'
import { useQcInspectionWorkspace } from './context'
import { effectiveInspectionDate, groupInspectionDays, inspectionToday, filterSchedule, isImportedPendingInspection, scheduleStatus, scheduleStatusLabels, type ScheduleFilters } from './schedule'
import QcScheduleEditDialog from './QcScheduleEditDialog.vue'
import QcBulkResultDialog from './QcBulkResultDialog.vue'
const context = useQcInspectionWorkspace()
const route = useRoute()
const allRecords = computed(() => route.name === 'qc-inspection-order-records')
const orders = ref<QcInspectionOrder[]>([])
const loading = ref(false)
const error = ref('')
const editing = ref<QcInspectionOrder | null>(null)
const bulkOrders = ref<QcInspectionOrder[] | null>(null)
const selected = ref<string[]>([])
const visibleDays = ref(7)
const weekOnly = ref(false)
const viewMode = ref(allRecords.value ? 'all' : 'day')
const day = ref(inspectionToday())
const filters = reactive<ScheduleFilters>({ customer: '', search: '', status: '', dateField: 'planned_inspection_date', from: '', to: '', agency: '' })
const scopedOrders = computed(() => allRecords.value ? orders.value : orders.value.filter(isImportedPendingInspection))
const statusOptions = computed(() => allRecords.value ? scheduleStatusLabels : { unplanned: '待安排', pending: '待验货' })
const customers = computed(() => [...new Set(scopedOrders.value.map(order => order.customer_name))].sort())
const agencies = computed(() => [...new Set(scopedOrders.value.map(order => order.inspection_agency).filter(Boolean))] as string[])
const filtered = computed(() => {
  const dateFilters = viewMode.value === 'range' ? filters : { ...filters, from: '', to: '' }
  if (viewMode.value === 'range' && filters.from && filters.to && filters.from > filters.to) return []
  return filterSchedule(scopedOrders.value, dateFilters).filter(order =>
    (!weekOnly.value || order.week_key === context.weekKey.value)
    && (viewMode.value !== 'day' || effectiveInspectionDate(order) === day.value)
    && (viewMode.value !== 'undated' || !effectiveInspectionDate(order)))
})
const groups = computed(() => groupInspectionDays(filtered.value))
const displayedGroups = computed(() => groups.value.slice(0, visibleDays.value))
const selectable = computed(() => !allRecords.value && context.canResultWrite.value)
const selectedOrders = computed(() => filtered.value.filter(order => selected.value.includes(order.id)))
function toggleGroup(items: QcInspectionOrder[], checked: boolean) {
  const ids = new Set(selected.value)
  for (const order of items) { if (checked) ids.add(order.id); else ids.delete(order.id) }
  selected.value = [...ids]
}
function selectedCount(items: QcInspectionOrder[]) { return items.filter(order => selected.value.includes(order.id)).length }
function dateTitle(date: string) {
  if (!date) return '待安排日期'
  const d = new Date(`${date}T12:00:00`)
  return `${date} · ${new Intl.DateTimeFormat('zh-CN', { weekday: 'long' }).format(d)}`
}
function moveDay(offset: number) {
  const next = new Date(`${day.value || inspectionToday()}T12:00:00Z`)
  next.setUTCDate(next.getUTCDate() + offset); day.value = next.toISOString().slice(0, 10); viewMode.value = 'day'
}
function today() { day.value = inspectionToday(); viewMode.value = 'day' }
function orderLink(order: QcInspectionOrder) { return { name: 'qc-inspection-order-detail', params: { orderId: order.id }, query: { factory: context.factoryId.value, week: order.week_key || context.weekKey.value } } }
let loadSequence = 0
async function load() {
  const sequence = ++loadSequence
  loading.value = true; error.value = ''; selected.value = []
  try { const result = await qcInspectionApi.listOrders(context.factoryId.value); if (sequence === loadSequence) orders.value = result }
  catch (cause) { if (sequence === loadSequence) error.value = getApiErrorMessage(cause) }
  finally { if (sequence === loadSequence) loading.value = false }
}
async function scheduleSaved(order: QcInspectionOrder) {
  editing.value = null; orders.value = orders.value.map(item => item.id === order.id ? order : item); await context.refresh()
}
async function resultsSaved(ids: string[]) {
  orders.value = orders.value.filter(order => !ids.includes(order.id)); selected.value = []
  await context.refresh()
}
function resetFilters() {
  Object.assign(filters, { customer: '', search: '', status: '', dateField: 'planned_inspection_date', from: '', to: '', agency: '' })
  weekOnly.value = false; viewMode.value = allRecords.value ? 'all' : 'day'; day.value = inspectionToday()
}
watch([filters, weekOnly, viewMode, day], () => { visibleDays.value = 7; selected.value = [] })
watch(() => context.workspace.value, () => { void load() })
onMounted(() => { void load() })
</script>

<template>
  <div class="space-y-5">
    <section class="qc-card">
      <div class="qc-section-heading"><div><p class="qc-eyebrow">DAILY INSPECTION SCHEDULE</p><h2>{{ allRecords ? '全部验货记录' : '排期明细' }}</h2><p class="qc-muted">{{ allRecords ? '查看导入订单、临时加单及历史验货记录。' : '一天一张排期表，只显示已导入且未完成验货的订单。客户未指定验货日期时，按走货日期排期。' }}</p></div><Button as-child variant="outline"><RouterLink :to="{ name: 'qc-inspection-schedule', query: { factory: context.factoryId.value, week: context.weekKey.value } }">返回总排期</RouterLink></Button></div>
      <div class="qc-day-controls">
        <div class="qc-view-switch"><button v-for="mode in [{ value: 'day', label: '按天查看' }, { value: 'range', label: '日期范围' }, { value: 'all', label: '全部日期' }, { value: 'undated', label: '待安排日期' }]" :key="mode.value" :aria-pressed="viewMode === mode.value" @click="viewMode = mode.value">{{ mode.label }}</button></div>
        <div v-if="viewMode === 'day'" class="flex flex-wrap items-center gap-2"><Button variant="outline" aria-label="前一天" @click="moveDay(-1)"><ChevronLeft class="size-4" /></Button><input v-model="day" aria-label="查看日期" type="date" class="qc-input !w-auto"><Button variant="outline" aria-label="后一天" @click="moveDay(1)"><ChevronRight class="size-4" /></Button><Button variant="outline" @click="today">今天</Button></div>
      </div>
      <div class="qc-filter-grid"><label class="qc-field"><span>客户</span><input v-model="filters.customer" list="qc-schedule-customers" placeholder="全部客户，可输入查找"><datalist id="qc-schedule-customers"><option v-for="name in customers" :key="name" :value="name" /></datalist></label><label class="qc-field"><span>搜索订单</span><input v-model="filters.search" placeholder="验货单号 / 合同 / PO / 货号"></label><label class="qc-field"><span>排期状态</span><select v-model="filters.status"><option value="">全部状态</option><option v-for="(label, key) in statusOptions" :key="key" :value="key">{{ label }}</option><option value="problem">涉及问题</option></select></label><label class="qc-field"><span>验货机构</span><select v-model="filters.agency"><option value="">全部机构</option><option v-for="name in agencies" :key="name">{{ name }}</option></select></label></div>
      <div class="qc-toolbar"><template v-if="viewMode === 'range'"><label class="qc-field"><span>日期类型</span><select v-model="filters.dateField"><option value="planned_inspection_date">计划验货日期</option><option value="shipment_date">走货日期</option><option value="actual_inspection_date">实际验货日期</option></select></label><label class="qc-field"><span>开始日期</span><input v-model="filters.from" type="date"></label><label class="qc-field"><span>结束日期</span><input v-model="filters.to" type="date" :min="filters.from"></label></template><label class="flex items-center gap-2 text-sm"><input v-model="weekOnly" aria-label="仅当前业务周" type="checkbox">仅业务周 {{ context.weekKey.value }}</label><Button variant="ghost" @click="resetFilters">重置筛选</Button></div>
      <p v-if="viewMode === 'range' && filters.from && filters.to && filters.from > filters.to" class="qc-error" role="alert">开始日期不能晚于结束日期。</p>
    </section>
    <div class="qc-daily-summary"><div><strong>{{ allRecords ? '验货记录' : '待验排期' }} {{ filtered.length }} 条</strong><p class="qc-muted">{{ groups.length }} 个日期区块 · {{ weekOnly ? context.weekKey.value : '全部业务周' }} · 按计划验货日期分组</p></div><div v-if="selectable && filtered.length && !loading && !error" class="flex flex-wrap items-center gap-3"><label class="flex items-center gap-2 text-sm"><input type="checkbox" :checked="selectedOrders.length === filtered.length" :indeterminate="selectedOrders.length > 0 && selectedOrders.length < filtered.length" @change="toggleGroup(filtered, ($event.target as HTMLInputElement).checked)">全选筛选结果（{{ filtered.length }} 条）</label><span class="text-sm text-teal-800">已选 {{ selectedOrders.length }} 条</span><Button :disabled="!selectedOrders.length" @click="bulkOrders = [...selectedOrders]">批量填写验货结果</Button></div></div>
    <section v-if="loading || error || !filtered.length" class="qc-card">
      <p v-if="error" class="qc-error" role="alert">{{ error }} <button class="underline" @click="load">重新加载</button></p><p v-else-if="loading" class="qc-muted" role="status">正在读取排期…</p>
      <div v-else class="qc-empty"><CalendarDays class="mx-auto mb-3 size-8 text-teal-700" /><h3>{{ !scopedOrders.length ? allRecords ? '还没有验货记录' : '暂无已导入的待验排期' : viewMode === 'day' ? '这一天没有符合条件的待验订单' : '没有符合筛选条件的订单' }}</h3><p>可切换日期、客户或查看全部日期；已完成的订单可在全部验货记录中查看。</p><Button variant="outline" class="mt-3" @click="viewMode = 'all'">查看全部日期</Button></div>
    </section>
    <template v-else>
      <section v-for="group in displayedGroups" :key="group.date" class="qc-card qc-day-card" :aria-label="dateTitle(group.date)">
        <header class="qc-day-heading"><div class="flex flex-wrap items-center gap-3"><label v-if="selectable" class="flex items-center"><input type="checkbox" :aria-label="`选择 ${group.date || '待安排'} 全部订单`" :checked="selectedCount(group.orders) === group.orders.length" :indeterminate="selectedCount(group.orders) > 0 && selectedCount(group.orders) < group.orders.length" @change="toggleGroup(group.orders, ($event.target as HTMLInputElement).checked)"></label><h3>{{ dateTitle(group.date) }}</h3><span v-if="group.date === inspectionToday()" class="qc-badge">今天</span><span class="text-sm text-slate-600">{{ group.orders.length }} 条</span></div><span v-if="selectedCount(group.orders)" class="text-sm text-teal-800">已选 {{ selectedCount(group.orders) }} 条</span></header>
        <div class="qc-table-scroll !rounded-none !border-0"><table class="qc-table qc-day-table"><thead><tr><th v-if="selectable">选择</th><th>客户 / 合同</th><th>PO / 货号</th><th>出口国</th><th>产品名称</th><th>数量</th><th>装箱 / 箱数</th><th>验货机构 / 进度</th><th>走货日期</th><th>操作</th></tr></thead><tbody><tr v-for="order in group.orders" :key="order.id" :class="{ 'qc-row-selected': selected.includes(order.id) }"><td v-if="selectable"><input v-model="selected" type="checkbox" :value="order.id" :aria-label="`选择订单 ${order.inspection_no || order.id}`"></td><td><b>{{ order.customer_name }}</b><small>{{ order.sales_contract_no }}</small><span v-if="order.source_type === 'MANUAL'" class="qc-badge">临时单</span></td><td>{{ order.customer_po_no }}<small>{{ order.customer_item_no }}</small></td><td>{{ order.export_country_code || '—' }}</td><td>{{ order.product_name || '—' }}</td><td class="tabular-nums">{{ Number(order.quantity || 0).toLocaleString('zh-CN', { maximumFractionDigits: 4 }) }}</td><td>{{ order.packing || '—' }}<small>箱数 {{ order.carton_count || '—' }}</small></td><td>{{ order.inspection_agency || '待定' }}<small><span class="qc-badge">{{ scheduleStatusLabels[scheduleStatus(order)] }}</span></small><small v-if="order.has_problem" class="!text-red-700">涉及问题</small></td><td class="whitespace-nowrap">{{ order.shipment_date || '—' }}<small v-if="!order.planned_inspection_date && order.shipment_date">按走货日期排期</small></td><td class="whitespace-nowrap"><RouterLink :to="orderLink(order)" class="font-semibold text-teal-700">查看 / 验货</RouterLink><small>{{ order.inspection_no }}</small><button v-if="context.canOrderWrite.value" type="button" class="mt-2 block text-xs text-teal-700" @click="editing = order">调整排期</button></td></tr></tbody></table></div>
      </section>
      <div v-if="groups.length > visibleDays" class="text-center"><Button variant="outline" @click="visibleDays += 7">显示更多日期（剩余 {{ groups.length - visibleDays }} 天）</Button></div>
    </template>
    <QcScheduleEditDialog v-if="editing && context.canOrderWrite.value" :order="editing" @close="editing = null" @saved="scheduleSaved" />
    <QcBulkResultDialog v-if="bulkOrders && context.canResultWrite.value" :orders="bulkOrders" @close="bulkOrders = null" @saved="resultsSaved" />
  </div>
</template>

<style scoped>
.qc-day-controls { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 20px; }
.qc-view-switch { display: flex; flex-wrap: wrap; gap: 4px; padding: 4px; border-radius: 10px; background: #f1f5f5; }
.qc-view-switch button { padding: 8px 12px; border-radius: 7px; font-size: 13px; color: #526672; }
.qc-view-switch button[aria-pressed=true] { background: #0f766e; color: white; }
.qc-daily-summary { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 16px; align-items: center; padding: 4px; }
.qc-day-card { padding: 0; overflow: hidden; }
.qc-day-heading { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px; padding: 16px 20px; background: #fffbeb; border-bottom: 1px solid #f3e6b9; border-left: 5px solid #e9b949; }
.qc-day-heading h3 { font-size: 17px; color: #503e19; }
.qc-day-table { min-width: 1080px; }
.qc-day-table td { padding: 12px; }
.qc-day-table th { padding: 10px 12px; }
.qc-row-selected { background: #effaf7; }
input[type=checkbox] { width: 16px; height: 16px; accent-color: #0f766e; }
</style>
