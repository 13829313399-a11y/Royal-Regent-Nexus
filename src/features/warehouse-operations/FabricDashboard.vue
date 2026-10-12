<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { ArrowUpRight, Boxes, ClipboardList, Clock3, RefreshCw, ScanLine, Truck } from '@lucide/vue'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import { fabricProcurementApi, type PurchaseLine } from '@/api/fabricProcurement'
import { handoverApi, type PendingDeliveries } from '@/api/materialHandover'
import { WAREHOUSE_FACTORY, WAREHOUSE_HOME } from './navigation'

const auth = useAuthStore(), route = useRoute()
const purchases = ref<Awaited<ReturnType<typeof fabricProcurementApi.lines>>>()
const deliveries = ref<PendingDeliveries>()
const purchaseError = ref(''), deliveryError = ref(''), loading = ref(false), updatedAt = ref('')
let generation = 0
const base = `${WAREHOUSE_HOME}/fabric-warehouse`
const warehouseLink = (section: string, view: string, extra: Record<string, string> = {}) => ({ path: `${base}/${section}`, query: { factory: WAREHOUSE_FACTORY, view, ...extra } })
const chaseLink = (tracking = 'OUTSTANDING', orderNo = '') => warehouseLink('receipts', 'pending', { tracking, ...(orderNo ? { order_no: orderNo } : {}) })
const deliveryLink = (document?: string) => ({ path: `${WAREHOUSE_HOME}/material-handover`, query: { factory: WAREHOUSE_FACTORY, tab: 'documents', deliveries: 'pending', ...(document ? { document } : {}) } })
const scanLink = { path: `${WAREHOUSE_HOME}/material-handover`, query: { factory: WAREHOUSE_FACTORY, tab: 'scan' } }
const summary = computed(() => purchases.value?.summary)
const priorityLines = computed(() => purchases.value?.items.slice(0, 3) ?? [])
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
async function load(reset = false) {
  const ticket = ++generation
  if (reset) { purchases.value = undefined; deliveries.value = undefined; updatedAt.value = '' }
  purchaseError.value = ''; deliveryError.value = ''
  if (route.query.factory !== WAREHOUSE_FACTORY) { purchases.value = undefined; deliveries.value = undefined; loading.value = false; return }
  loading.value = true
  const results = await Promise.allSettled([
    fabricProcurementApi.lines('PENDING', '', 0, 'OUTSTANDING', { sort: 'OVERDUE' }),
    handoverApi().pendingDeliveries(0, 3),
  ])
  if (ticket !== generation) return
  const [purchaseResult, deliveryResult] = results
  if (purchaseResult.status === 'fulfilled') purchases.value = purchaseResult.value
  else { purchases.value = undefined; purchaseError.value = getApiErrorMessage(purchaseResult.reason) }
  if (deliveryResult.status === 'fulfilled') deliveries.value = deliveryResult.value
  else { deliveries.value = undefined; deliveryError.value = getApiErrorMessage(deliveryResult.reason) }
  updatedAt.value = new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit' }).format(new Date())
  loading.value = false
}
function refreshWhenVisible() { if (!loading.value && document.visibilityState === 'visible') void load() }
watch(() => [route.query.factory, auth.currentUser?.id, auth.authorizationVersion], () => load(true), { immediate: true })
const timer = setInterval(refreshWhenVisible, 60_000)
window.addEventListener('focus', refreshWhenVisible)
document.addEventListener('visibilitychange', refreshWhenVisible)
onBeforeUnmount(() => { generation++; clearInterval(timer); window.removeEventListener('focus', refreshWhenVisible); document.removeEventListener('visibilitychange', refreshWhenVisible) })
</script>

<template>
  <div class="fabric-dashboard" :aria-busy="loading">
    <header class="dashboard-heading">
      <div class="dashboard-title"><span class="title-icon"><ClipboardList :size="19" /></span><div><h1>工作看板</h1><p>采购追货与送货入库集中办理<span v-if="updatedAt"> · {{ updatedAt }} 更新</span></p></div></div>
      <div class="heading-actions"><RouterLink :to="scanLink" class="dashboard-primary"><ScanLine :size="16" />扫码入库</RouterLink><button type="button" class="dashboard-secondary" :disabled="loading" @click="load()"><RefreshCw :size="15" :class="{ spinning: loading }" />刷新</button></div>
    </header>

    <section class="dashboard-todos" aria-label="今日待办">
      <div class="todos-heading"><div><h2>今日待办 · 先看这里</h2><p>先追未到的物料，再核对供应商送货；实际收货后确认入库。</p></div><div class="todo-badges"><span class="amber-badge">待追货 {{ summary?.outstanding ?? '—' }} 项</span><span class="teal-badge">待入库 {{ deliveries?.total ?? '—' }} 张</span></div></div>
      <div class="todo-columns">
        <article class="todo-panel chase-panel">
          <header><h3><Clock3 :size="16" />采购追货</h3><RouterLink :to="chaseLink()">查看全部<ArrowUpRight :size="14" /></RouterLink></header>
          <p v-if="purchaseError" class="dashboard-error" role="alert">追货数据未能读取：{{ purchaseError }}</p>
          <p v-else-if="loading && !purchases" class="todo-empty">正在读取采购进度…</p>
          <template v-else-if="purchases">
            <div class="chase-filters"><RouterLink :to="chaseLink('OVERDUE')">逾期 <b>{{ summary?.overdue ?? '—' }}</b></RouterLink><RouterLink :to="chaseLink('DUE_TODAY')">今日到期 <b>{{ summary?.due_today ?? '—' }}</b></RouterLink><RouterLink :to="chaseLink('AWAITING_DATE')">待确认复期 <b>{{ summary?.awaiting_date ?? '—' }}</b></RouterLink></div>
            <p v-if="!priorityLines.length" class="todo-empty">当前没有待追货的采购明细。</p>
            <ul v-else class="todo-list"><li v-for="line in priorityLines" :key="line.id"><div class="todo-copy"><strong>{{ line.facts.material_name || line.facts.material_code }}</strong><p>{{ line.facts.order_no || '未提供采购单号' }} · {{ line.facts.supplier }}</p><p><span :class="{ overdue: line.tracking?.overdue }">{{ chaseReason(line) }}</span> · 待收 {{ line.warehouse_outstanding_quantity == null ? '数量待核对' : `${line.warehouse_outstanding_quantity} ${line.facts.unit}` }}</p></div><RouterLink class="todo-action" :to="chaseLink('OUTSTANDING', line.facts.order_no)">查看追货</RouterLink></li></ul>
          </template>
        </article>
        <article class="todo-panel delivery-panel">
          <header><h3><Truck :size="16" />供应商送货待入库</h3><RouterLink :to="deliveryLink()">查看全部<ArrowUpRight :size="14" /></RouterLink></header>
          <p v-if="deliveryError" class="dashboard-error" role="alert">送货及库存数据未能读取：{{ deliveryError }}</p>
          <p v-else-if="loading && !deliveries" class="todo-empty">正在读取送货进度…</p>
          <template v-else-if="deliveries">
            <p class="panel-note">已确认且尚未收完的送货单，部分入库继续保留。</p>
            <p v-if="!deliveries.items.length" class="todo-empty">当前没有待入库的供应商送货单。</p>
            <ul v-else class="todo-list"><li v-for="row in deliveries.items" :key="row.id"><div class="todo-copy"><strong>送货单 {{ row.data.source_no }}</strong><p>{{ row.data.counterparty }} · {{ row.data.document_date || '日期未提供' }}</p><p>{{ row.processing_status === 'PARTIAL' ? '部分已入库' : '待核实入库' }} · {{ row.pending_line_count }} 项待收 · {{ row.first_item_name }}</p></div><RouterLink class="todo-action filled" :to="deliveryLink(row.id)">核实入库</RouterLink></li></ul>
          </template>
        </article>
      </div>
    </section>

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
    <details class="dashboard-help"><summary>统计口径与使用说明</summary><p>待追货按采购明细计数，一张采购单可能包含多项物料；采购报到货待核对可在待收料页查看。供应商送货只统计已确认、尚未收完的单据。两类待办可能涉及同一批物料，不能相加作为订单总数。</p><p>库存结存是已登记业务的账面数量，不含尚未建立的历史期初。月度数量对账已开放，正式月结锁定和计价尚未开放。</p><slot /></details>
  </div>
</template>

<style scoped>
.fabric-dashboard{display:grid;gap:16px;color:#0f172a;font-size:12px}
.dashboard-heading,.dashboard-todos,.dashboard-flow,.stat-card{background:#fff;border:1px solid #dbe4eb;border-radius:12px;box-shadow:0 1px 2px #0f172a06}
.dashboard-heading{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:14px 18px;border-color:#b8ded8}
.dashboard-title,.heading-actions,.dashboard-primary,.dashboard-secondary{display:flex;align-items:center;gap:8px}
.title-icon{display:grid;place-items:center;width:34px;height:34px;border-radius:9px;background:#eaf7f3;color:#087f73}
.fabric-dashboard h1,.fabric-dashboard h2,.fabric-dashboard h3,.fabric-dashboard p{margin:0}
.fabric-dashboard h1,.fabric-dashboard h2{font-size:14px;font-weight:750}
.fabric-dashboard h3{font-size:12px;font-weight:700}
.dashboard-title p,.todos-heading p,.dashboard-flow header p{margin-top:4px;font-size:11px;color:#64748b}
.dashboard-primary,.dashboard-secondary{padding:8px 12px;border-radius:8px;text-decoration:none;font-weight:650;white-space:nowrap}
.dashboard-primary{background:#087f73;color:#fff}
.dashboard-secondary{background:#fff;border:1px solid #dbe4eb;color:#334155;cursor:pointer}
.dashboard-secondary:disabled{opacity:.5;cursor:wait}
.dashboard-todos{overflow:hidden;border-color:#edcf85}
.todos-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:16px 18px;background:linear-gradient(100deg,#fffae8,#edf9f6)}
.todo-badges{display:flex;gap:8px;flex-wrap:wrap;white-space:nowrap}
.todo-badges span{border-radius:20px;padding:4px 10px;font-size:11px;font-weight:700}
.amber-badge{background:#fff0c9;color:#985a0d}
.teal-badge{background:#087f73;color:#fff}
.todo-columns{display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:14px}
.todo-panel{border:1px solid;border-radius:10px;padding:14px;min-width:0}
.chase-panel{background:#fffef9;border-color:#f3dfa9}
.delivery-panel{background:#f8fdfc;border-color:#bee6df}
.todo-panel header,.dashboard-flow header{display:flex;align-items:center;justify-content:space-between;gap:12px}
.todo-panel h3,.todo-panel header a,.dashboard-flow header a{display:flex;align-items:center;gap:5px}
.todo-panel header a,.dashboard-flow header a{font-size:11px;font-weight:650;color:#087f73;text-decoration:none;white-space:nowrap}
.chase-filters{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.chase-filters a{display:flex;gap:8px;padding:4px 8px;border-radius:5px;background:#fff7e6;color:#785426;text-decoration:none;font-size:11px}
.panel-note{padding-top:15px;color:#64748b;font-size:11px}
.todo-list{list-style:none;padding:0;margin:8px 0 0}
.todo-list li{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 0;border-bottom:1px solid #e8eeed}
.todo-list li:last-child{border-bottom:0;padding-bottom:2px}
.todo-copy{min-width:0}
.todo-copy strong{display:block;font-size:12px;overflow-wrap:anywhere}
.todo-copy p{font-size:11px;color:#64748b;line-height:1.6;margin-top:3px;overflow-wrap:anywhere}
.todo-action{flex-shrink:0;color:#087f73;border:1px solid #b8ded8;border-radius:7px;padding:6px 9px;background:white;text-decoration:none;font-weight:650;font-size:11px}
.todo-action.filled{background:#087f73;color:white;border-color:#087f73}
.todo-empty{padding:24px 0;color:#64748b}
.dashboard-error{padding:16px 0;line-height:1.6;color:#b42318}
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
.fabric-dashboard a:hover{filter:brightness(.96)}
.fabric-dashboard a:focus-visible,.fabric-dashboard button:focus-visible,.dashboard-help summary:focus-visible{outline:2px solid #0d9488;outline-offset:3px}
.spinning{animation:spin 1s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
@media(prefers-reduced-motion:reduce){.spinning{animation:none}}
@media(max-width:1000px){.dashboard-stats{grid-template-columns:repeat(2,minmax(0,1fr))}
.dashboard-flow ol{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:700px){.dashboard-heading,.todos-heading{align-items:flex-start;flex-direction:column;gap:12px}
.heading-actions{width:100%;justify-content:flex-end}
.todo-columns{grid-template-columns:1fr;padding:10px}
.dashboard-flow{padding:14px}
.dashboard-flow ol{grid-template-columns:repeat(2,minmax(0,1fr))}
.todo-copy strong{font-size:11px}
.stat-card{padding:12px}
.stock-card>strong{font-size:17px}}
</style>
