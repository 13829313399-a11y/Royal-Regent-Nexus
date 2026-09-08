<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { FileSpreadsheet, ArrowDownToLine, ArrowUpFromLine, SlidersHorizontal, X } from '@lucide/vue'
import type { DateRange } from 'reka-ui'
import DateRangeFilter from '@/components/DateRangeFilter.vue'
import CartonOrderTimeline from '@/components/CartonOrderTimeline.vue'
import type { CartonCustomerResponse } from '@/api/cartonProcurement'
import { cartonInventoryReportApi, type InventoryReport, type InventoryFlowCategory, type InventoryOrderReportRow } from '@/api/cartonInventoryReport'
import { getApiErrorMessage } from '@/lib/http'

const props = defineProps<{ factoryId: string; customers: CartonCustomerResponse[]; search: string; refreshKey: number; connected: boolean }>()
const emit = defineEmits<{ clearSearch: []; inventory: []; closing: [] }>()
const customerCode = ref('')
const dateRange = shallowRef<DateRange>({ start: undefined, end: undefined })
const mode = ref<'SUMMARY' | InventoryFlowCategory>('SUMMARY')
const timelineTarget = ref<{ orderId: string; inventoryKey: string; label: string } | null>(null)
const report = ref<InventoryReport>({ rows: [], order_rows: [], movements: [] })
const loading = ref(false)
const error = ref('')
let requestVersion = 0
let searchTimer: ReturnType<typeof setTimeout> | undefined
const options = computed(() => props.customers.filter(row => row.factory_id === props.factoryId))
const from = computed(() => dateRange.value.start?.toString() ?? '')
const to = computed(() => dateRange.value.end?.toString() ?? '')
const filtersActive = computed(() => Boolean(customerCode.value || from.value || to.value || props.search.trim()))
const modes = [
  { id: 'SUMMARY' as const, label: '订单汇总' },
  { id: 'INBOUND' as const, label: '入库明细' },
  { id: 'OUTBOUND' as const, label: '出库明细' },
  { id: 'ADJUSTMENT' as const, label: '调整明细' },
]
const orderCount = computed(() => new Set(report.value.order_rows.filter(row => row.order_id).map(row => row.order_id)).size)
const standaloneCount = computed(() => report.value.order_rows.filter(row => !row.order_id).length)
const detailRows = computed(() => report.value.movements.filter(row => row.flow_category === mode.value))
function format(value: string) {
  const negative = value.startsWith('-')
  const [whole = '0', fraction = ''] = value.replace(/^-/, '').split('.')
  const decimal = fraction.slice(0, 4).replace(/0+$/, '')
  return `${negative ? '-' : ''}${BigInt(whole).toLocaleString('zh-CN')}${decimal ? `.${decimal}` : ''}`
}
function scaled(value: string) {
  const [whole = '0', fraction = ''] = value.replace(/^-/, '').split('.')
  return (BigInt(whole) * 10000n + BigInt(fraction.padEnd(4, '0').slice(0, 4))) * (value.startsWith('-') ? -1n : 1n)
}
// The backend owns ledger classification and balances. Add only four-decimal
// display quantities here, keeping unlike units in separate totals.
function totals(field: 'inbound_quantity' | 'outbound_quantity' | 'adjustment_quantity') {
  const values = new Map<string, bigint>()
  for (const row of report.value.order_rows) values.set(row.unit, (values.get(row.unit) ?? 0n) + scaled(row[field]))
  return [...values].map(([unit, amount]) => {
    const absolute = amount < 0n ? -amount : amount
    return { unit: unit || '未标单位', quantity: `${amount < 0n ? '-' : ''}${absolute / 10000n}.${(absolute % 10000n).toString().padStart(4, '0')}` }
  })
}
const cards = computed(() => [
  { label: '入库净数量', values: totals('inbound_quantity'), icon: ArrowDownToLine, tone: 'text-teal-700' },
  { label: '出库净数量', values: totals('outbound_quantity'), icon: ArrowUpFromLine, tone: 'text-blue-700' },
  { label: '调整净数量', values: totals('adjustment_quantity'), icon: SlidersHorizontal, tone: 'text-amber-700' },
])
async function load() {
  const version = ++requestVersion
  report.value = { rows: [], order_rows: [], movements: [] }
  error.value = ''
  if (!props.connected) { loading.value = false; return }
  loading.value = true
  try {
    const data = await cartonInventoryReportApi.get(props.factoryId, {
      customer_code: customerCode.value, date_from: from.value, date_to: to.value, search: props.search.trim(),
    })
    if (!Array.isArray(data.order_rows)) throw new Error('订单汇总服务尚未启用，请刷新重试。')
    if (version === requestVersion) report.value = data
  } catch (cause) {
    if (version === requestVersion) error.value = getApiErrorMessage(cause) || '库存汇总读取失败，请重试。'
  } finally {
    if (version === requestVersion) loading.value = false
  }
}
function openOrderTimeline(row: InventoryOrderReportRow) {
  timelineTarget.value = { orderId: row.order_id ?? '', inventoryKey: row.order_id ? '' : row.key, label: `${row.contract_no || '无单库存'} · ${row.item_no}` }
}
function closeTimeline() {
  timelineTarget.value = null
}
function handleTimelineKey(event: KeyboardEvent) {
  if (event.key === 'Escape' && timelineTarget.value) closeTimeline()
}
onMounted(() => window.addEventListener('keydown', handleTimelineKey))
watch([() => props.factoryId, customerCode, () => props.search, () => props.connected, mode, from, to], closeTimeline, { flush: 'sync' })
function clearFilters() {
  customerCode.value = ''
  dateRange.value = { start: undefined, end: undefined }
  emit('clearSearch')
}
watch(() => props.factoryId, () => {
  customerCode.value = ''
  dateRange.value = { start: undefined, end: undefined }
  mode.value = 'SUMMARY'
}, { flush: 'sync' })
watch([() => props.factoryId, () => props.connected, () => props.refreshKey, customerCode, from, to], () => { void load() }, { immediate: true })
watch(() => props.search, () => {
  clearTimeout(searchTimer)
  ++requestVersion
  report.value = { rows: [], order_rows: [], movements: [] }
  loading.value = true
  searchTimer = setTimeout(() => { void load() }, 250)
})
onBeforeUnmount(() => { ++requestVersion; clearTimeout(searchTimer); window.removeEventListener('keydown', handleTimelineKey) })
</script>

<template>
  <section class="space-y-4" aria-label="库存汇总工作台">
    <article class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div class="flex flex-wrap items-center justify-between gap-3 px-4 py-4">
        <div><h2 class="flex items-center gap-2 text-lg font-bold text-slate-950"><FileSpreadsheet class="size-5 text-teal-700" />订单收发汇总</h2><p class="mt-1 text-xs leading-5 text-slate-500">每张订单分别核对收发，不同纸品分行；结存 = 期初 + 入库 − 出库 + 调整。</p></div>
        <div class="flex gap-2"><button class="h-9 rounded-lg border border-slate-200 px-3 text-xs font-bold text-slate-600" @click="emit('inventory')">实时库存</button><button class="h-9 rounded-lg border border-slate-200 px-3 text-xs font-bold text-slate-600" @click="emit('closing')">月结金额</button></div>
      </div>

    </article>

      <div v-if="connected && !error && !loading" class="grid gap-3 sm:grid-cols-3">
        <article v-for="card in cards" :key="card.label" class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div class="flex items-center gap-2 text-xs font-semibold text-slate-500"><component :is="card.icon" class="size-4" />{{ card.label }}</div>
          <div class="mt-3 flex flex-wrap items-baseline gap-x-5 gap-y-2" :class="card.tone"><span v-for="value in card.values" :key="value.unit" class="text-2xl font-bold tabular-nums">{{ format(value.quantity) }}<span class="ml-1 text-xs font-medium">{{ value.unit }}</span></span><span v-if="!card.values.length" class="text-2xl font-bold">0</span></div>
        </article>
      </div>
      <article class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
          <div class="flex flex-wrap gap-1" role="tablist" aria-label="库存汇总视图"><button v-for="tab in modes" :key="tab.id" role="tab" :aria-selected="mode === tab.id" class="rounded-lg px-4 py-2 text-xs font-bold" :class="mode === tab.id ? 'bg-teal-700 text-white' : 'text-slate-500 hover:bg-slate-50'" @click="mode = tab.id">{{ tab.label }}</button></div>
          <span class="text-xs text-slate-500">{{ mode === 'SUMMARY' ? `${orderCount} 张订单 · ${report.order_rows.length} 项纸品${standaloneCount ? `（含 ${standaloneCount} 项无单库存）` : ''}` : `${detailRows.length} 条流水` }}</span>
        </div>
      <div class="flex flex-wrap items-center gap-3 border-b border-slate-200 bg-slate-50/80 px-4 py-3">
        <label class="inline-flex items-center gap-2 text-xs font-semibold text-slate-600">客户<select v-model="customerCode" aria-label="库存汇总客户" class="h-9 rounded-lg border border-slate-200 bg-white px-3"><option value="">全部客户</option><option v-for="customer in options" :key="customer.customer_code" :value="customer.customer_code">{{ customer.customer_name }}</option></select></label>
        <div class="inline-flex items-center gap-2 text-xs font-semibold text-slate-600"><span>记账时间</span><DateRangeFilter v-model="dateRange" label="库存汇总记账时间范围" /></div>
        <button :disabled="!filtersActive" class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-xs text-slate-600 disabled:opacity-40" @click="clearFilters">清空筛选</button>
        <span class="ml-auto text-xs text-slate-500">{{ from && to ? `${from} 至 ${to}` : '全部日期' }} · 统计随筛选更新</span>
      </div>
      <p v-if="search.trim()" class="border-t border-slate-100 px-4 py-2 text-xs text-teal-700">正在查询“{{ search.trim() }}”对应的库存，保留其完整收发记录。</p>
    <div v-if="!connected" role="status" class="rounded-xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-800">连接正式台账后显示库存汇总。</div>
    <div v-else-if="error" role="alert" class="flex items-center justify-between rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700"><span>{{ error }}</span><button class="rounded-lg border border-red-200 px-3 py-2 font-bold" @click="load">重新读取</button></div>
    <div v-else-if="loading" role="status" class="rounded-xl border border-slate-200 bg-white p-10 text-center text-sm text-slate-500">正在核对收发流水…</div>
      <template v-else>
        <div class="overflow-x-auto">
          <table v-if="mode === 'SUMMARY'" class="w-full min-w-[1220px] text-left text-xs" aria-label="收发汇总表">
            <thead class="bg-slate-50 text-slate-500"><tr><th class="px-4 py-3">下单日期</th><th class="px-4 py-3">客户</th><th class="px-4 py-3">合同号</th><th class="px-4 py-3">货号 / 产品名称</th><th class="px-4 py-3">纸品 / 规格</th><th class="px-4 py-3">单位</th><th class="px-4 py-3 text-right">期初</th><th class="px-4 py-3 text-right">入库</th><th class="px-4 py-3 text-right">出库</th><th class="px-4 py-3 text-right">调整</th><th class="px-4 py-3 text-right">{{ to ? '期末结存' : '当前结存' }}</th><th class="px-4 py-3">当前领用</th><th class="px-4 py-3">当前仓位分布</th><th class="px-4 py-3 text-right">操作</th></tr></thead>
            <tbody class="divide-y divide-slate-100">
              <tr v-for="row in report.order_rows" :key="row.key" class="hover:bg-slate-50/60">
                <td class="whitespace-nowrap px-4 py-4 font-semibold">{{ row.order_date || '—' }}</td>
                <td class="px-4 py-4 font-semibold">{{ row.customer_name }}</td>
                <td class="px-4 py-4"><div class="font-mono font-semibold">{{ row.contract_no || '—' }}</div><span v-if="!row.order_id" class="mt-1 inline-block rounded bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-700">无单库存</span></td>
                <td class="px-4 py-4"><div class="font-mono font-semibold">{{ row.item_no }}</div><div v-if="row.product_name" class="mt-1 text-slate-500">{{ row.product_name }}</div></td>
                <td class="px-4 py-4"><div class="font-semibold">{{ row.packaging_type }} {{ row.paper_quality }}</div><div class="mt-1 text-slate-400">{{ row.specification }}</div><div v-if="!row.line_count && scaled(row.opening_quantity) === 0n" class="mt-1 text-[10px] text-slate-400">暂无收发</div></td>
                <td class="px-4 py-4">{{ row.unit || '未标单位' }}</td>
                <td class="px-4 py-4 text-right tabular-nums">{{ format(row.opening_quantity) }}</td>
                <td class="px-4 py-4 text-right text-teal-700 tabular-nums">{{ format(row.inbound_quantity) }}</td>
                <td class="px-4 py-4 text-right text-blue-700 tabular-nums">{{ format(row.outbound_quantity) }}</td>
                <td class="px-4 py-4 text-right text-amber-700 tabular-nums">{{ format(row.adjustment_quantity) }}</td>
                <td class="px-4 py-4 text-right text-sm font-bold text-teal-800 tabular-nums">{{ format(row.ending_quantity) }}</td>
                <td class="whitespace-nowrap px-4 py-4"><div class="font-semibold text-teal-700">{{ row.current_usage_label || '未入库' }}</div><div class="mt-1 text-[10px] text-slate-500">{{ row.current_usage_status === 'UNKNOWN' ? '已明确领用' : '净领用' }} {{ format(row.current_usage_quantity || '0') }} {{ row.unit }}</div></td>
                <td class="px-4 py-4"><details v-if="row.current_positions?.length" class="min-w-32"><summary class="cursor-pointer text-teal-700">{{ row.current_positions.length }} 个仓位</summary><div v-for="part in row.current_positions" :key="part.location" class="mt-1 whitespace-nowrap text-[10px]">{{ part.location }}：{{ format(part.quantity) }} {{ row.unit }}</div></details><span v-else class="text-slate-400">无结存</span></td>
                <td class="px-4 py-4 text-right"><button type="button" :aria-label="`查看 ${row.contract_no || '无单库存'} ${row.item_no} 订单流水`" class="whitespace-nowrap rounded-lg border border-teal-200 px-3 py-2 text-xs font-bold text-teal-700 hover:bg-teal-50" title="点击查看订单流水" aria-haspopup="dialog" @click="openOrderTimeline(row)">订单流水</button></td>
              </tr>
              <tr v-if="!report.order_rows.length"><td colspan="14" class="px-4 py-12 text-center text-slate-400">所选条件下没有订单或库存记录</td></tr>
            </tbody>
          </table>
          <table v-else class="w-full min-w-[1150px] text-left text-xs" aria-label="库存汇总明细表">
            <thead class="bg-slate-50 text-slate-500"><tr><th class="px-4 py-3">记账时间 / 单据</th><th class="px-4 py-3">客户</th><th class="px-4 py-3">合同号</th><th class="px-4 py-3">货号</th><th class="px-4 py-3">纸品 / 规格</th><th class="px-4 py-3">类型</th><th class="px-4 py-3 text-right">{{ mode === 'OUTBOUND' ? '出库数量' : mode === 'INBOUND' ? '入库数量' : '调整数量' }}</th><th class="px-4 py-3">仓位</th><th class="px-4 py-3">经手人 / 原因</th></tr></thead>
            <tbody class="divide-y divide-slate-100"><tr v-for="row in detailRows" :key="row.id" class="hover:bg-slate-50/60"><td class="px-4 py-4"><div>{{ row.occurred_at.replace('T', ' ').slice(0, 16) }}</div><div class="mt-1 font-mono font-semibold">{{ row.document_no || '未填写' }}</div></td><td class="px-4 py-4">{{ row.customer_name }}</td><td class="px-4 py-4 font-mono">{{ row.contract_no || '非正式收料' }}</td><td class="px-4 py-4 font-mono">{{ row.item_no }}</td><td class="px-4 py-4"><div class="font-semibold">{{ row.packaging_type }} {{ row.paper_quality }}</div><div class="mt-1 text-slate-400">{{ row.specification }}</div></td><td class="px-4 py-4"><span :class="row.movement_type === 'REVERSAL' ? 'text-rose-700' : 'text-slate-600'">{{ row.movement_type === 'REVERSAL' ? '冲销' : mode === 'INBOUND' ? '入库' : mode === 'OUTBOUND' ? '出库' : '调整' }}</span></td><td class="px-4 py-4 text-right font-bold tabular-nums" :class="Number(row.flow_quantity) < 0 ? 'text-rose-700' : 'text-teal-700'">{{ format(row.flow_quantity) }} <span class="font-normal">{{ row.unit }}</span></td><td class="px-4 py-4">{{ row.location || '未填写' }}</td><td class="max-w-60 px-4 py-4"><div>{{ row.actor_name }}</div><div class="mt-1 break-words text-slate-400">{{ row.reason || '—' }}</div></td></tr><tr v-if="!detailRows.length"><td colspan="9" class="px-4 py-12 text-center text-slate-400">所选条件下没有{{ modes.find(tab => tab.id === mode)?.label }}</td></tr></tbody>
          </table>
        </div>
        <div class="space-y-1 border-t border-slate-100 bg-slate-50/60 px-4 py-3 text-[11px] leading-5 text-slate-500"><p>入库、出库均含冲销净数量；盘盈、盘亏和期初库存单列调整。每张订单按纸品分别统计，不同订单和单位不混加；无单入库单独标记。</p><p>未选日期时查看累计收发；选择日期后查看期间收发，期初保留此前结存。收发按记账时间筛选；未收发订单按下单日期筛选。金额在月结对账中核对。领用状态和仓位分布显示当前累计情况，不随所选历史日期回溯。</p></div>
      </template>
      </article>
    <div v-if="timelineTarget" data-testid="order-timeline-overlay" class="fixed inset-0 z-[62] flex items-center justify-center bg-slate-950/45 p-4" @click.self="closeTimeline">
      <div role="dialog" aria-modal="true" aria-labelledby="order-timeline-title" class="flex max-h-[88vh] w-full max-w-[1400px] flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
        <div class="flex shrink-0 items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
          <div><h2 id="order-timeline-title" class="text-lg font-bold text-slate-950">订单流水 — {{ timelineTarget.label }}</h2><p class="mt-1 text-xs text-teal-700">可滚动查看该订单的完整业务流水</p></div>
          <button type="button" aria-label="关闭订单流水" class="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700" @click="closeTimeline"><X class="size-4" /></button>
        </div>
        <div class="min-h-0 overflow-y-auto">
          <CartonOrderTimeline :factory-id="factoryId" customer-code="" date-from="" date-to="" search="" :order-id="timelineTarget.orderId" :inventory-key="timelineTarget.inventoryKey" target-label="" :refresh-key="refreshKey" />
        </div>
      </div>
    </div>
  </section>
</template>
