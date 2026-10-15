<script setup lang="ts">
import { computed, inject, onBeforeUnmount, ref, watch } from 'vue'
import { parseDate } from '@internationalized/date'
import type { DateRange } from 'reka-ui'
import DateRangeFilter from '@/components/DateRangeFilter.vue'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { Button } from '@/components/ui/button'
import { warehouseOperationsApi as api, type FabricOrderRow, type FabricOrderReport } from '@/api/warehouseOperations'
import { getApiErrorMessage } from '@/lib/http'
import { inventorySearchKey } from './inventorySearch'

type Mode = 'SUMMARY' | 'INBOUND' | 'OUTBOUND' | 'ADJUSTMENT'
const modes: { id: Mode; title: string }[] = [{ id: 'SUMMARY', title: '订单汇总' }, { id: 'INBOUND', title: '入库明细' }, { id: 'OUTBOUND', title: '出库明细' }, { id: 'ADJUSTMENT', title: '调整明细' }]
const mode = ref<Mode>('SUMMARY'), data = ref<FabricOrderReport>(), busy = ref(false), error = ref(''), selected = ref<FabricOrderRow>()
const headerSearch = inject(inventorySearchKey, undefined)
const dateFrom = ref(''), dateTo = ref(''), search = headerSearch?.search ?? ref(''), supplier = ref(''), offset = ref(0)
const dates = computed<DateRange>({
  get: () => ({ start: dateFrom.value ? parseDate(dateFrom.value) : undefined, end: dateTo.value ? parseDate(dateTo.value) : undefined }),
  set: value => { dateFrom.value = value.start?.toString() ?? ''; dateTo.value = value.end?.toString() ?? ''; void load() },
})
let searchTimer: ReturnType<typeof setTimeout> | undefined
const suppliers = ref<string[]>([])
let sequence = 0
const detailRows = computed(() => (data.value?.details ?? []).filter(row => row.mode === mode.value))
const count = computed(() => mode.value === 'SUMMARY' ? data.value?.rows.length ?? 0 : detailRows.value.length)
const pageRows = computed(() => data.value?.rows.slice(offset.value, offset.value + 50) ?? [])
const pageDetails = computed(() => detailRows.value.slice(offset.value, offset.value + 50))
const timeline = computed(() => data.value?.details.filter(row => row.key === selected.value?.key) ?? [])
function selectMode(value: Mode) { mode.value = value; offset.value = 0 }
async function load() {
  clearTimeout(searchTimer)
  const ticket = ++sequence
  busy.value = true; error.value = ''; data.value = undefined; selected.value = undefined; offset.value = 0
  try {
    const result = await api.orderSummary({ date_from: dateFrom.value, date_to: dateTo.value, search: search.value.trim(), supplier: supplier.value })
    if (ticket === sequence) { data.value = result; suppliers.value = result.suppliers }
  } catch (e) { if (ticket === sequence) { error.value = getApiErrorMessage(e); suppliers.value = [] } }
  finally { if (ticket === sequence) busy.value = false }
}
function clear() { dateFrom.value = ''; dateTo.value = ''; search.value = ''; supplier.value = ''; void load() }
watch(search, () => {
  if (!headerSearch?.active.value) return
  clearTimeout(searchTimer); sequence++; data.value = undefined; selected.value = undefined; busy.value = true
  searchTimer = setTimeout(() => { void load() }, 350)
}, { flush: 'sync' })
if (headerSearch) watch(headerSearch.submitted, () => { if (headerSearch.active.value) void load() })
onBeforeUnmount(() => { sequence++; clearTimeout(searchTimer) })
void load()
</script>

<template>
  <div class="fabric-order-summary" :aria-busy="busy">
    <nav class="order-modes" aria-label="订单收发明细类型"><button v-for="item in modes" :key="item.id" :aria-pressed="mode === item.id" @click="selectMode(item.id)">{{ item.title }}</button></nav>
    <header><div><h2>订单收发汇总</h2><p>按已登记采购来源、物料和原单位核对结余，冲销计入办理当日。</p></div><Button variant="outline" :disabled="busy" @click="load">刷新</Button></header>
    <form class="order-filters" role="search" aria-label="查询订单收发" @submit.prevent="load">
      <label v-if="!headerSearch?.active.value" class="grow">查找订单 / 物料 / 凭证<input v-model="search" type="search" maxlength="128" aria-label="订单收发关键字" placeholder="采购单、放产单、物料、送货单或领用方" /></label>
      <label>供应商<select v-model="supplier" aria-label="订单收发供应商"><option value="">全部供应商</option><option v-for="name in suppliers" :key="name" :value="name">{{ name }}</option></select></label>
      <div class="grid gap-1.5 text-xs"><span>业务日期</span><DateRangeFilter v-model="dates" label="订单收发日期范围" /></div>
      <Button type="submit" :disabled="busy">查询</Button><Button type="button" variant="outline" :disabled="busy" @click="clear">清空筛选</Button>
    </form>
    <p v-if="busy" role="status" class="order-state">正在核对订单收发记录…</p><p v-else-if="error" role="alert" class="fabric-error">{{ error }}</p>
    <template v-else-if="data">
      <p class="order-basis">当前统计：{{ data.date_from || '全部已记记录' }} 至 {{ data.date_to || '全部已记记录' }}<span v-if="data.search"> · {{ data.search }}</span><span v-if="data.supplier"> · {{ data.supplier }}</span></p>
      <div class="order-totals"><article v-for="total in data.totals" :key="total.unit"><h3>{{ total.unit }} · 分单位合计</h3><dl><div><dt>记录期初</dt><dd>{{ total.opening }}</dd></div><div><dt>净入库</dt><dd>{{ total.inbound }}</dd></div><div><dt>净出库</dt><dd>{{ total.outbound }}</dd></div><div><dt>调整</dt><dd>{{ total.adjustment }}</dd></div><div><dt>记录结余</dt><dd>{{ total.balance }}</dd></div></dl></article></div>
      <div class="order-table-scroll" tabindex="0" role="region" :aria-label="modes.find(item => item.id === mode)?.title">
        <table v-if="mode === 'SUMMARY'"><thead><tr><th>采购单 / 放产单</th><th>供应商</th><th>物料</th><th>单位</th><th>记录期初</th><th>净入库</th><th>净出库</th><th>调整</th><th>记录结余</th><th>操作</th></tr></thead><tbody><tr v-for="row in pageRows" :key="row.key"><td><strong>{{ row.order_no || '未关联采购订单' }}</strong><small>{{ row.production_no || '未记录放产单' }} {{ row.style_no }}</small><small v-if="!row.linked">未关联采购来源，不扣减采购欠货</small></td><td>{{ row.supplier || '未记录' }}</td><td><strong>{{ row.item_name }}</strong><small>{{ row.item_code }}</small></td><td>{{ row.unit }}</td><td>{{ row.opening }}</td><td>{{ row.inbound }}</td><td>{{ row.outbound }}</td><td>{{ row.adjustment }}</td><td class="balance">{{ row.balance }}</td><td><Button size="sm" variant="outline" @click="selected = row">订单流水</Button></td></tr></tbody></table>
        <table v-else><thead><tr><th>日期 / 业务</th><th>采购单 / 放产单</th><th>供应商 / 领用方</th><th>物料 / 单位</th><th>{{ mode === 'ADJUSTMENT' ? '库存调整量' : '净数量（冲销为负）' }}</th><th v-if="mode === 'ADJUSTMENT'">调仓移动量</th><th>来源凭证 / 原单</th><th>仓位 / 经办人</th><th>原因</th></tr></thead><tbody><tr v-for="row in pageDetails" :key="row.id"><td>{{ row.date }}<small>{{ row.label }}</small></td><td>{{ row.order_no || '未关联采购订单' }}<small>{{ row.production_no }}</small></td><td>{{ row.supplier }}<small>{{ row.recipient }}</small></td><td>{{ row.item_name }}<small>{{ row.item_code }} · {{ row.unit }}</small></td><td>{{ row.quantity }} {{ row.unit }}</td><td v-if="mode === 'ADJUSTMENT'">{{ row.moved_quantity }} {{ row.unit }}</td><td>{{ row.source_no }}<small v-if="row.original_id">原单 {{ row.original_id }}</small></td><td>{{ row.location || '—' }}<small>{{ row.actor_name }}</small></td><td>{{ row.reason || '—' }}</td></tr></tbody></table>
      </div>
      <p v-if="!count" class="order-state" role="status">当前条件下没有已登记记录；上传单据和采购计划本身不计入收发。</p>
      <footer><span>共 {{ count }} 条</span><div><Button variant="outline" size="sm" :disabled="offset === 0" @click="offset -= 50">上一页</Button><Button variant="outline" size="sm" :disabled="offset + 50 >= count" @click="offset += 50">下一页</Button></div></footer>
      <p class="order-basis">{{ data.basis }} 记录结余 = 记录期初 + 净入库 − 净出库 + 调整。</p>
    </template>
    <DialogRoot :open="!!selected" @update:open="open => { if (!open) selected = undefined }"><DialogPortal><DialogOverlay class="order-overlay" /><DialogContent v-if="selected" class="order-dialog"><header><div><DialogTitle>订单流水 · {{ selected.order_no || '未关联采购订单' }}</DialogTitle><DialogDescription>{{ selected.item_name }} · {{ selected.unit }} · 当前查询期间</DialogDescription></div><Button variant="outline" @click="selected = undefined">关闭流水</Button></header><div class="order-table-scroll"><table><thead><tr><th>日期 / 业务</th><th>凭证</th><th>库存增减</th><th>领用方 / 经办人</th><th>原因</th></tr></thead><tbody><tr v-for="row in timeline" :key="row.id"><td>{{ row.date }}<small>{{ row.label }}</small></td><td>{{ row.source_no }}</td><td>{{ row.stock_change }} {{ row.unit }}<small v-if="row.moved_quantity !== '0'">调仓 {{ row.moved_quantity }} {{ row.unit }}</small></td><td>{{ row.recipient }}<small>{{ row.actor_name }}</small></td><td>{{ row.reason || '—' }}</td></tr></tbody></table><p v-if="!timeline.length" class="order-state">本期间无流水，结余由期间前记录带入。</p></div></DialogContent></DialogPortal></DialogRoot>
  </div>
</template>

<style scoped>
.fabric-order-summary{color:#0f172a;background:white}.fabric-order-summary>header,.order-dialog>header{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:20px 24px}.fabric-order-summary h2{font-size:19px;font-weight:650}header p,.order-basis{font-size:12px;color:#64748b;line-height:1.8}.order-filters{display:flex;align-items:end;gap:10px;flex-wrap:wrap;padding:0 24px 20px}.order-filters label{display:grid;gap:6px;font-size:12px;color:#475569}.order-filters .grow{flex:1;min-width:200px}input,select{border:1px solid #cbd5e1;background:white;border-radius:6px;padding:8px 10px;font:inherit;min-height:36px}.order-basis{padding:8px 24px}.order-totals{display:flex;flex-wrap:wrap;gap:12px;padding:8px 24px 16px}.order-totals article{flex:1;min-width:280px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:14px}.order-totals h3{font-size:13px;font-weight:600}.order-totals dl{display:flex;gap:16px;flex-wrap:wrap;margin-top:12px}.order-totals dt{font-size:11px;color:#64748b}.order-totals dd{font-weight:600;color:#0f766e;font-variant-numeric:tabular-nums;margin-top:4px}.order-modes{display:flex;gap:6px;flex-wrap:wrap;padding:12px 24px;border-bottom:1px solid #e2e8f0}.order-modes button{padding:8px 12px;border-radius:6px;font-size:13px;color:#475569}.order-modes button[aria-pressed=true]{color:#0f766e;background:#f0fdfa;border:1px solid #99f6e4}.order-table-scroll{overflow:auto;max-height:65dvh}table{width:100%;min-width:900px;border-collapse:collapse;text-align:left;font-size:13px}th{font-size:12px;color:#64748b;background:#f8fafc;font-weight:500;white-space:nowrap;position:sticky;top:0}td,th{padding:12px 16px;border-bottom:1px solid #e2e8f0}td{vertical-align:top;overflow-wrap:anywhere}small{display:block;color:#64748b;font-size:11px;margin-top:5px}strong{font-weight:600}.balance{color:#0f766e;font-weight:650}.order-state{padding:28px 24px;color:#64748b;font-size:13px}.fabric-order-summary>footer{display:flex;justify-content:space-between;align-items:center;padding:16px 24px;font-size:12px;color:#64748b}.fabric-order-summary>footer>div{display:flex;gap:10px}.order-overlay{position:fixed;inset:0;background:#0f172a60;z-index:140}.order-dialog{position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);z-index:150;background:white;width:min(1000px,95vw);max-height:90dvh;border-radius:12px;overflow:hidden}.order-dialog h2{font-weight:650}.order-dialog p{font-size:12px;color:#64748b}.order-dialog table{min-width:700px}@media(max-width:640px){.order-filters{padding:0 16px 16px}.order-filters label{flex:1;min-width:140px}.order-totals{padding:8px 16px}.fabric-order-summary>header{padding:16px}.order-basis{padding:8px 16px}.order-modes{padding:12px 16px}}
</style>
