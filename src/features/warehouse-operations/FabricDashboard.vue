<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { ArrowUpRight, Boxes, ClipboardList, Clock3, ScanLine, Truck } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import WarehouseDashboard from '@/features/warehouse-foundation/WarehouseDashboard.vue'
import WarehouseTodoPanel from '@/features/warehouse-foundation/WarehouseTodoPanel.vue'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import { fabricProcurementApi, type PurchaseLine } from '@/api/fabricProcurement'
import { handoverApi, type PendingDeliveries } from '@/api/materialHandover'
import { warehouseOperationsApi, type WarehouseDocument } from '@/api/warehouseOperations'
import HandoverRejectionSummary from '../material-handover/HandoverRejectionSummary.vue'
import { WAREHOUSE_FACTORY, WAREHOUSE_HOME } from './navigation'
import { hasUnissuedRemainder, remaining } from './operations'

const auth = useAuthStore(), route = useRoute()
const purchases = ref<Awaited<ReturnType<typeof fabricProcurementApi.lines>>>()
const deliveries = ref<PendingDeliveries>()
const pendingRequests = ref<WarehouseDocument[]>()
const purchaseError = ref(''), deliveryError = ref(''), requestError = ref(''), loading = ref(false), updatedAt = ref('')
let generation = 0, backgroundRead = false
const base = `${WAREHOUSE_HOME}/fabric-warehouse`
const warehouseLink = (section: string, view: string, extra: Record<string, string> = {}) => ({ path: `${base}/${section}`, query: { factory: WAREHOUSE_FACTORY, view, ...extra } })
const chaseLink = (tracking = 'OUTSTANDING', orderNo = '') => warehouseLink('receipts', 'pending', { tracking, ...(orderNo ? { order_no: orderNo } : {}) })
const deliveryLink = (document?: string) => ({ path: `${WAREHOUSE_HOME}/material-handover`, query: { factory: WAREHOUSE_FACTORY, tab: 'documents', deliveries: 'pending', ...(document ? { document } : {}) } })
const requestLink = (record?: string) => warehouseLink('inventory', 'pending-issues', record ? { record } : {})
function requestOrderLabel(row: WarehouseDocument) {
  const order = row.data.cutting_request?.order_no || row.data.production_no
  return order ? `订单 ${order}` : '未填订单号'
}
const scanLink = { path: `${WAREHOUSE_HOME}/material-handover`, query: { factory: WAREHOUSE_FACTORY, tab: 'scan' } }
const summary = computed(() => purchases.value?.summary)
const purchaseRows = computed(() => purchases.value?.items.map(line => ({
  id: line.id, title: line.facts.material_name || line.facts.material_code,
  context: `${line.facts.order_no || '未提供采购单号'} · ${line.facts.supplier}`,
  quantity: line.warehouse_outstanding_quantity == null ? '数量待核对' : `待收 ${line.warehouse_outstanding_quantity} ${line.facts.unit}`,
  date: chaseReason(line), overdue: line.tracking?.overdue, to: chaseLink('OUTSTANDING', line.facts.order_no),
})))
const deliveryRows = computed(() => deliveries.value?.items.map(row => ({
  id: row.id, title: `送货单 ${row.data.source_no}`,
  context: `${row.data.counterparty} · ${row.data.document_date || '日期未提供'} · ${row.first_item_name}`,
  quantity: `${row.pending_line_count} 项待收`, date: row.processing_status === 'PARTIAL' ? '部分已入库' : row.receipt_rejection ? undefined : '待核实入库',
  to: deliveryLink(row.id),
})))
const deliveryRejections = computed(() => new Map(deliveries.value?.items.map(row => [row.id, row.receipt_rejection])))
const requestRows = computed(() => pendingRequests.value?.map(row => ({
  id: row.id, title: row.data.item_name || row.data.item_code, subtitle: row.data.cutting_request?.task_name,
  context: requestOrderLabel(row), quantity: `待发 ${remaining(row.data.quantity, row.issued_quantity)} ${row.data.unit}`, to: requestLink(row.id),
})))
const stockLabel = computed(() => deliveries.value ? deliveries.value.stock_totals.map(row => `${row.quantity} ${row.unit}`).join(' · ') || '暂无库存' : '—')
const steps = [
  { title: '采购资料', detail: '导入已下达采购与补数', to: warehouseLink('receipts', 'import-review') },
  { title: '追货与核对', detail: '按复期跟进未到物料', to: chaseLink() },
  { title: '核实入库', detail: '打开送货单或扫码核实', to: deliveryLink() },
  { title: '库存与发料', detail: '按批次出库、退料、调仓', to: warehouseLink('inventory', 'stock') },
  { title: '收发对账', detail: '按供应商与领用方核对', to: warehouseLink('closing', 'monthly') },
]
function chaseReason(line: PurchaseLine) {
  if (line.tracking?.overdue) return `逾期 ${line.overdue_days} 天`
  if (line.tracking?.due_today) return '今日到期'
  if (line.tracking?.quantity_review) return '数量待核对'
  if (line.tracking?.awaiting_date) return '待确认复期'
  return line.promise_date ? `复期 ${line.promise_date}` : '待跟进'
}
async function load(reset = false, background = false) {
  const ticket = ++generation
  if (reset) { purchases.value = undefined; deliveries.value = undefined; pendingRequests.value = undefined; updatedAt.value = '' }
  if (!background) { purchaseError.value = ''; deliveryError.value = ''; requestError.value = '' }
  if (route.query.factory !== WAREHOUSE_FACTORY) { loading.value = false; return }
  if (!background) loading.value = true
  const results = await Promise.allSettled([
    fabricProcurementApi.lines('PENDING', '', 0, 'OUTSTANDING', { sort: 'OVERDUE' }),
    handoverApi().pendingDeliveries(0, 3),
    warehouseOperationsApi.workspace('fabric'),
  ])
  if (ticket !== generation) return
  const [purchaseResult, deliveryResult, requestResult] = results
  if (purchaseResult.status === 'fulfilled') { purchases.value = purchaseResult.value; purchaseError.value = '' }
  else { purchases.value = undefined; purchaseError.value = getApiErrorMessage(purchaseResult.reason) }
  if (deliveryResult.status === 'fulfilled') { deliveries.value = deliveryResult.value; deliveryError.value = '' }
  else { deliveries.value = undefined; deliveryError.value = getApiErrorMessage(deliveryResult.reason) }
  if (requestResult.status === 'fulfilled') {
    requestError.value = ''
    pendingRequests.value = requestResult.value.documents.filter(hasUnissuedRemainder)
      .sort((a, b) => b.business_date.localeCompare(a.business_date) || b.sequence - a.sequence)
  } else { pendingRequests.value = undefined; requestError.value = getApiErrorMessage(requestResult.reason) }
  updatedAt.value = new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit' }).format(new Date())
  loading.value = false
}
function refreshWhenVisible() {
  if (loading.value || backgroundRead || document.visibilityState !== 'visible') return
  backgroundRead = true
  void load(false, true).finally(() => { backgroundRead = false })
}
watch(() => [route.query.factory, auth.currentUser?.id, auth.authorizationVersion], () => load(true), { immediate: true })
const timer = setInterval(refreshWhenVisible, 60_000)
window.addEventListener('focus', refreshWhenVisible)
document.addEventListener('visibilitychange', refreshWhenVisible)
onBeforeUnmount(() => { generation++; clearInterval(timer); window.removeEventListener('focus', refreshWhenVisible); document.removeEventListener('visibilitychange', refreshWhenVisible) })
</script>

<template>
  <WarehouseDashboard class="fabric-dashboard" subtitle="采购追货、送货入库与领料申请" :loading="loading" :updated-at="updatedAt" @refresh="load()">
    <template #primary><Button as-child><RouterLink :to="scanLink"><ScanLine :size="16" aria-hidden="true" />扫码入库</RouterLink></Button></template>
    <template #todos>
      <WarehouseTodoPanel class="todo-column chase-panel" title="采购追货" :icon="Clock3" :destination="chaseLink()" action="查看追货"
        :count-label="`待追货 ${summary?.outstanding ?? '—'} 项`" :rows="purchaseRows" loading-text="正在读取采购进度…" attention
        empty="当前没有待追货的采购明细。" :error="purchaseError && `追货数据未能读取。${purchaseError}`">
        <template #beforeRows>
          <div class="chase-filters"><RouterLink :to="chaseLink('OVERDUE')">逾期 <b>{{ summary?.overdue ?? '—' }}</b></RouterLink><RouterLink :to="chaseLink('DUE_TODAY')">今日到期 <b>{{ summary?.due_today ?? '—' }}</b></RouterLink><RouterLink :to="chaseLink('AWAITING_DATE')">待确认复期 <b>{{ summary?.awaiting_date ?? '—' }}</b></RouterLink></div>
        </template>
      </WarehouseTodoPanel>
      <WarehouseTodoPanel class="todo-column delivery-panel" title="供应商送货待入库" :icon="Truck" :destination="deliveryLink()"
        all-label="查看全部待入库送货单" action="核实入库" :count-label="`待入库 ${deliveries?.total ?? '—'} 张`" :rows="deliveryRows" primary-action
        loading-text="正在读取送货进度…" empty="当前没有待入库的供应商送货单。" :error="deliveryError && `送货及库存数据未能读取。${deliveryError}`">
        <template #beforeRows><p class="panel-note">按实收数量入库，未收完的送货单继续待收。</p></template>
        <template #rowEvidence="{ id }"><HandoverRejectionSummary v-if="deliveryRejections.get(id)" :summary="deliveryRejections.get(id)!" /></template>
      </WarehouseTodoPanel>
      <WarehouseTodoPanel class="request-panel" title="领料申请" :icon="ClipboardList" :destination="requestLink()" action="查看申请"
        :count-label="pendingRequests ? `待发 ${pendingRequests.length} 张` : undefined" :rows="requestRows" wide
        loading-text="正在读取领料申请…" empty="当前没有待发的领料申请。" :error="requestError && `领料申请未能读取。${requestError}`" />
    </template>

    <section class="dashboard-stats" aria-label="布料仓统计">
      <RouterLink :to="chaseLink()" class="stat-card"><span>待追货采购明细<ClipboardList :size="17" /></span><strong>{{ summary?.outstanding ?? '—' }}<small>项</small></strong><p>{{ purchaseError ? '读取失败，请刷新重试' : '包括未到货和部分到货的采购、补数' }}</p></RouterLink>
      <RouterLink :to="chaseLink('OVERDUE')" class="stat-card"><span>逾期需追货<Clock3 :size="17" /></span><strong class="overdue">{{ summary?.overdue ?? '—' }}<small>项</small></strong><p>超过供应商复期且仍有明确欠货</p></RouterLink>
      <RouterLink :to="deliveryLink()" class="stat-card"><span>送货单待入库<Truck :size="17" /></span><strong>{{ deliveries?.total ?? '—' }}<small>张</small></strong><p>{{ deliveryError ? '读取失败，请刷新重试' : '按整张送货单统计，部分入库不重复计数' }}</p></RouterLink>
      <RouterLink :to="warehouseLink('inventory', 'stock')" class="stat-card stock-card"><span>当前库存结存<Boxes :size="17" /></span><strong>{{ stockLabel }}</strong><p>按已登记收发汇总，各单位分别列示</p></RouterLink>
    </section>

    <section class="dashboard-flow" aria-label="布料仓业务流程">
      <header><div><h2>从采购追货到收发对账</h2><p>点选步骤进入对应工作区。</p></div><RouterLink :to="warehouseLink('inventory', 'movements')">查看收发流水<ArrowUpRight :size="14" /></RouterLink></header>
      <ol><li v-for="(step, index) in steps" :key="step.title"><RouterLink :to="step.to"><span>0{{ index + 1 }}<ArrowUpRight :size="14" /></span><strong>{{ step.title }}</strong><small>{{ step.detail }}</small></RouterLink></li></ol>
      <div class="flow-note">导入采购资料、确认送货单和扫码定位均不增加库存；核实本次实物并确认入库后，才更新库存与已关联采购的待收进度。</div>
    </section>
    <details class="dashboard-help"><summary>统计口径与使用说明</summary><p>待追货按采购明细计数，一张采购单可能包含多项物料；采购报到货待核对可在待收料页查看。供应商送货只统计已确认、尚未收完的单据。两类待办可能涉及同一批物料，不能相加作为订单总数。</p><p>库存结存包含已登记收发、已导入期初和已确认盘点差异，不含尚未建账的历史实物。月度数量对账已开放，正式月结锁定和计价尚未开放。</p><slot /></details>
  </WarehouseDashboard>
</template>

<style scoped>
.fabric-dashboard { color: var(--foreground); font-size: 12px; }
.dashboard-flow, .stat-card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; }
.chase-filters { display: flex; flex-wrap: wrap; gap: 8px; }
.chase-filters a { display: flex; gap: 8px; padding: 4px 8px; border-radius: 5px; background: #fff7e6; color: #785426; font-size: 11px; }
.panel-note { color: var(--muted-foreground); font-size: 12px; }
.dashboard-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.stat-card{display:block;padding:16px;text-decoration:none;min-width:0;color:inherit}
.stat-card>span{display:flex;justify-content:space-between;gap:8px;color:#64748b;font-size:11px}
.stat-card>span svg{color:#087f73}
.stat-card>strong{display:block;margin:12px 0 8px;font-size:27px;line-height:1.25;font-weight:750}
.stat-card strong small{font-size:11px;color:#64748b;font-weight:400;margin-left:6px}
.stat-card p{color:#64748b;font-size:10px;line-height:1.5}
.stock-card>strong{font-size:20px;overflow-wrap:anywhere}
.overdue{color:#c2410c!important}
.dashboard-flow{padding:18px}
.dashboard-flow ol{list-style:none;padding:0;margin:16px 0;display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px}
.dashboard-flow li a{display:flex;height:100%;flex-direction:column;gap:9px;padding:14px;border:1px solid #dce8e6;background:#f7fbfa;border-radius:9px;text-decoration:none;color:#0f172a}
.dashboard-flow li span{display:flex;justify-content:space-between;color:#087f73;font-size:10px}
.dashboard-flow li small{color:#64748b;font-size:10px;line-height:1.5}
.flow-note{border-top:1px solid #edf2f3;padding-top:13px;color:#64748b;font-size:11px;line-height:1.6}
.dashboard-help{padding:0 4px;color:#64748b;font-size:11px;line-height:1.8}
.dashboard-help summary{cursor:pointer;width:fit-content}
.dashboard-help p{margin-top:8px}
:is(.dashboard-stats, .dashboard-flow, .chase-filters) a:hover { background: var(--accent); }
:is(.dashboard-stats, .dashboard-flow, .chase-filters) a:focus-visible, .dashboard-help summary:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }
@media (min-width: 768px) {
  @supports (grid-template-rows: subgrid) {
    .fabric-dashboard :deep(.warehouse-dashboard-panels) { row-gap: 0; }
    .todo-column { display: grid; grid-row: 1 / span 5; grid-template-rows: subgrid; }
    .todo-column :deep(header) { grid-row: 1; }
    .todo-column :deep(.warehouse-todo-before) { grid-row: 2; align-self: center; }
    .todo-column :deep(:is(.warehouse-todo-list, .warehouse-todo-empty)) { grid-row: 3 / -1; }
    .todo-column :deep(.warehouse-todo-list) { display: grid; grid-template-rows: subgrid; }
    .request-panel { margin-top: 10px; }
  }
}
@media (max-width: 1000px) {
  .dashboard-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .dashboard-flow ol { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 639px) {
  .dashboard-flow, .stat-card { padding: 12px; }
  .dashboard-flow ol { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .stock-card > strong { font-size: 17px; }
}
</style>
