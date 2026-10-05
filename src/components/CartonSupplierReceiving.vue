<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import { cartonSupplierPortalApi as api, type PortalWorkspace, type PortalShipment, type ShipmentLine, type ReceiveLine, type SampleReceipt } from '@/api/cartonSupplierPortal'
import { cartonPositionsApi, type CartonLocation } from '@/api/cartonPositions'
import { cartonProcurementApi, type CartonCustomerResponse } from '@/api/cartonProcurement'
import CartonReceiptAllocations from '@/components/CartonReceiptAllocations.vue'
import CartonSplitReceiptReview from '@/components/CartonSplitReceiptReview.vue'
import CartonShipmentFilters from '@/components/CartonShipmentFilters.vue'
import { emptyShipmentFilters, filterShipments } from '@/features/carton-procurement/queryFilters'
const props = defineProps<{ factoryId?: string; shipmentId?: string }>()
const emit = defineEmits<{ changed: []; reverse: [receiptId: string] }>()
const route = useRoute(); const app = useAppStore(); const auth = useAuthStore()
const factory = computed(() => String(props.factoryId || route.query.factory || app.activeProductionFactory.id))
const data = ref<PortalWorkspace | null>(null); const locations = ref<CartonLocation[]>([]); const customers = ref<CartonCustomerResponse[]>([])
const error = ref(''); const message = ref(''); const busy = ref(false); const loading = ref(false)
const active = ref<PortalShipment | null>(null); const received = ref<ReceiveLine[]>([])
const splitConfirmation = ref('')
const correctionReason = ref('')
const pendingCustomers = ref<Record<string, string>>({})
const pendingTargets = ref<Record<string, string>>({})
const pendingReasons = ref<Record<string, string>>({})
const awaitingReceipt = (shipment: PortalShipment) => ['SENT', 'RECEIPT_REVERSED'].includes(shipment.status)
const splitLines = computed(() => received.value.flatMap((line, index) => {
  const identifier = active.value?.lines[index]?.order_line_id
  return identifier ? [{ order_line_id: identifier, effective_quantity: effective(line) }] : []
}))
const hasSplits = computed(() => splitLines.value.some(line => data.value?.orders.some(order =>
  order.lines.some(paper => paper.id === line.order_line_id) && order.split_records?.some(plan => plan.status !== 'CANCELLED'))))
const acceptanceDate = ref(new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' }))
const can = (permission: string) => ['carton', 'pmc-warehouse'].some(department => auth.can(permission, factory.value, department))
const canReceive = computed(() => can('carton_procurement:receipt_write') && can('carton_procurement:inventory_write'))
const canLink = computed(() => can('carton_procurement:order_adjust'))
const canRead = computed(() => can('carton_procurement:read'))
const shipmentView = ref<'PENDING' | 'HISTORY'>('PENDING')
const shipmentFilters = ref(emptyShipmentFilters())
const visibleShipments = computed(() => filterShipments(data.value?.shipments ?? [], shipmentFilters.value).filter(shipment => shipmentView.value === 'PENDING' ? awaitingReceipt(shipment) : !awaitingReceipt(shipment)))
watch(shipmentView, () => { shipmentFilters.value.status = '' })
watch(factory, () => { shipmentFilters.value = emptyShipmentFilters() })
const linkTargets = ref<Record<string, string>>({}); const linkReasons = ref<Record<string, string>>({})
let generation = 0
let scopeGeneration = 0
let openedDeepLinkKey = ''
function openDeepLinkedShipment() {
  const shipmentId = props.shipmentId || (typeof route.query.shipment === 'string' ? route.query.shipment : '')
  const key = `${factory.value}:${shipmentId}`
  if (!shipmentId || openedDeepLinkKey === key || !canReceive.value) return
  const shipment = data.value?.shipments.find(row => row.id === shipmentId && awaitingReceipt(row))
  if (!shipment) return
  openedDeepLinkKey = key
  start(shipment)
}
function failure(reason: unknown) { error.value = getApiErrorMessage(reason) }
async function load() {
  if (!canRead.value) return
  const token = ++generation, scope = factory.value; loading.value = true
  try {
    const [workspace, bins, activeCustomers] = await Promise.all([api.workspace(scope, true), canReceive.value ? cartonPositionsApi.locations(scope) : Promise.resolve([]), canReceive.value ? cartonProcurementApi.listCustomers(scope, false) : Promise.resolve([])])
    if (token !== generation || scope !== factory.value) return
    data.value = workspace; locations.value = bins; customers.value = activeCustomers
    openDeepLinkedShipment()
  } catch (reason) { if (token === generation) failure(reason) } finally { if (token === generation) loading.value = false }
}
watch([factory, canRead, canReceive], () => { active.value = null; data.value = null; received.value = []; linkTargets.value = {}; linkReasons.value = {}; pendingCustomers.value = {}; pendingTargets.value = {}; pendingReasons.value = {}; correctionReason.value = ''; openedDeepLinkKey = ''; error.value = ''; message.value = ''; busy.value = false; loading.value = false; shipmentView.value = 'PENDING'; acceptanceDate.value = new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' }); generation++; scopeGeneration++; if (canRead.value) void load() }, { immediate: true })
defineExpose({ refresh: load })
onBeforeUnmount(() => { generation++; scopeGeneration++ })
watch(() => props.shipmentId || route.query.shipment, () => { openedDeepLinkKey = ''; openDeepLinkedShipment() })
function start(shipment: PortalShipment) {
  if (!canReceive.value) return
  splitConfirmation.value = ''
  correctionReason.value = ''
  active.value = shipment; error.value = ''
  received.value = shipment.lines.map(line => ({ shipment_line_id: line.id, received_quantity: Number(line.quantity), damaged_quantity: 0, rejected_quantity: 0, unusable_quantity: 0, unit_price: Number(line.delivery_unit_price) > 0 && (line.currency ?? 'CNY').toUpperCase() === 'CNY' ? Number(line.delivery_unit_price) : Number(line.unit_price || 0), paper_quality: line.paper_quality, specification: line.specification, location_allocations: [], difference_reason: '', no_order_decision: '' as const, customer_code: '', sample_purpose: '', requested_by: '', unit: line.unit }))
}
function markNotReceived(index: number) {
  const row = received.value[index]
  if (!row) return
  row.received_quantity = 0
  row.damaged_quantity = 0
  row.rejected_quantity = 0
  row.unusable_quantity = 0
  row.location_allocations = []
  row.difference_reason = '货物尚未实际送到'
  row.no_order_decision = ''
}
function markAllNotReceived() {
  received.value.forEach((_, index) => markNotReceived(index))
}
function markAsDelivered(index: number) {
  const row = received.value[index], shipped = active.value?.lines[index]
  if (!row || !shipped) return
  row.received_quantity = Number(shipped.quantity)
  row.damaged_quantity = 0
  row.rejected_quantity = 0
  row.unusable_quantity = 0
  row.difference_reason = ''
}
function setNoOrderDecision(index: number) {
  const row = received.value[index]
  if (!row) return
  if (row.no_order_decision === 'WRONG_DELIVERY') {
    row.rejected_quantity = Number(row.received_quantity)
    row.damaged_quantity = 0
    row.unusable_quantity = 0
    row.location_allocations = []
  } else if (row.no_order_decision === 'SAMPLE') {
    row.rejected_quantity = 0
  }
}
const effective = (line: ReceiveLine) => Math.max(0, Number(line.received_quantity) - Number(line.damaged_quantity) - Number(line.rejected_quantity) - Number(line.unusable_quantity))
const materialText = (value: string) => value.toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]/g, '')
const materialDimensions = (value: string) => (value.match(/\d+(?:[.,]\d+)?/g) ?? []).map(part => Number(part.replace(',', '.'))).join('*')
function pendingFormalTargets(source: ShipmentLine) {
  return (data.value?.orders ?? []).filter(order =>
    ['PENDING_SUPPLIER', 'PARTIALLY_RECEIVED'].includes(order.status) && !order.awaiting_issue
    && order.customer_code === pendingCustomers.value[source.id]
    && materialText(order.contract_no) === materialText(source.contract_no)
    && materialText(order.item_no) === materialText(source.item_no))
    .flatMap(order => order.lines.filter(line => materialText(line.packaging_type) === materialText(source.packaging_type)
      && materialText(line.paper_quality) === materialText(source.paper_quality)
      && materialDimensions(line.specification) === materialDimensions(source.specification)).map(line => ({ order, line })))
}
async function linkPending(shipment: PortalShipment, source: ShipmentLine) {
  const target = pendingFormalTargets(source).find(candidate => candidate.line.id === pendingTargets.value[source.id])
  const reason = (pendingReasons.value[source.id] || '').trim()
  if (!canReceive.value) return
  if (!target?.order.revision || reason.length < 4 || busy.value) {
    error.value = '请选择客户及正式订单纸品，并填写至少四字关联原因'; return
  }
  const scope = factory.value, token = scopeGeneration; busy.value = true; error.value = ''
  try {
    await api.linkShipmentLine(shipment.id, source.id, { factory_id: scope, customer_code: pendingCustomers.value[source.id]!,
      order_line_id: target.line.id, expected_revision: shipment.revision, expected_order_revision: target.order.revision, reason })
    if (scope === factory.value && token === scopeGeneration) { active.value = null; received.value = []; message.value = '原送货单已关联正式订单；请重新核实实际收到。'; emit('changed'); await load() }
  } catch (reason) { if (scope === factory.value && token === scopeGeneration) failure(reason) } finally { if (scope === factory.value && token === scopeGeneration) busy.value = false }
}
function formalTargets(sample: SampleReceipt) {
  return (data.value?.orders ?? []).filter(order =>
    ['PENDING_SUPPLIER', 'PARTIALLY_RECEIVED'].includes(order.status)
    && !order.awaiting_issue
    && order.customer_code === sample.customer_code
    && order.item_no.trim().toLowerCase() === sample.item_no.trim().toLowerCase())
    .flatMap(order => order.lines.filter(line =>
      line.packaging_type === sample.packaging_type && line.paper_quality === sample.paper_quality
      && line.unit === sample.unit).map(line => ({ order, line })))
}
async function linkSample(sample: SampleReceipt) {
  const selected = formalTargets(sample).find(target => target.line.id === linkTargets.value[sample.receipt_line_id])
  const reason = (linkReasons.value[sample.receipt_line_id] || '').trim()
  if (!canLink.value) return
  if (!selected || !selected.order.revision || reason.length < 4 || busy.value) {
    error.value = '请选择后续正式订单纸品，填写至少四字关联原因并刷新后重试'; return
  }
  busy.value = true; error.value = ''; const scope = factory.value, token = scopeGeneration
  try {
    await api.linkSampleReceipt(sample.receipt_line_id, { factory_id: scope, order_line_id: selected.line.id,
      expected_order_revision: selected.order.revision, reason })
    if (scope === factory.value && token === scopeGeneration) { message.value = '样板箱已关联后续正式订单；原入库和月结记录保留，不重复过账。'; emit('changed'); await load() }
  } catch (reason) { if (scope === factory.value && token === scopeGeneration) failure(reason) } finally { if (scope === factory.value && token === scopeGeneration) busy.value = false }
}
async function confirm() {
  if (!active.value || busy.value || !canReceive.value) return
  if (active.value.requires_correction && correctionReason.value.trim().length < 4) {
    error.value = '原收料已冲销，请填写至少四字更正原因'; return
  }
  for (const [index, line] of received.value.entries()) {
    if (active.value.lines[index]?.source_type === 'AD_HOC_REVIEW' && Number(line.received_quantity) > 0) {
      if (!line.no_order_decision) { error.value = '每条已到的无单纸品必须选“确需入库样板箱”或“送错货拒收”'; return }
      if (line.no_order_decision === 'SAMPLE' && (!line.customer_code || (line.sample_purpose || '').trim().length < 4 || (line.requested_by || '').trim().length < 2 || Number(line.unit_price) <= 0)) {
        error.value = '样板箱须选择客户、填写用途与需求人，并确认大于 0 的入库单价'; return
      }
      if (line.no_order_decision === 'WRONG_DELIVERY' && effective(line) !== 0) { error.value = '送错货的有效入库数量必须为 0'; return }
    }
    const quantity = effective(line)
    if (quantity <= 0) continue
    const allocations = line.location_allocations
    if (!allocations.length || allocations.some(part => !locations.value.some(location => location.id === part.location_id && location.status === 'ACTIVE') || !Number.isFinite(Number(part.quantity)) || Number(part.quantity) <= 0)) {
      error.value = '每条有效入库纸品必须选择有效仓位并填写分仓数量'; return
    }
    if (new Set(allocations.map(part => part.location_id)).size !== allocations.length || allocations.some(part => Math.abs(Number(part.quantity) * 10000 - Math.round(Number(part.quantity) * 10000)) > 0.000001) || Math.abs(allocations.reduce((sum, part) => sum + Number(part.quantity), 0) - quantity) > 0.000001) {
      error.value = '仓位不能重复，分仓数量最多四位小数，合计必须等于该纸品有效入库数量'; return
    }
  }
  busy.value = true; error.value = ''; const scope = factory.value, token = scopeGeneration, shipment = active.value
  try { const result = await api.receive(shipment.id, { factory_id: scope, expected_revision: shipment.revision, acceptance_date: acceptanceDate.value, lines: received.value, split_confirmation: splitConfirmation.value, correction_reason: correctionReason.value.trim() }); if (factory.value === scope && token === scopeGeneration) { active.value = null; received.value = []; message.value = result.receipt_id ? '仓库核实已保存；有效实收已入库，未收到的纸品保留原待收需求。' : '仓库核实已保存；本单没有有效入库数量。'; emit('changed'); await load() } } catch (reason) { if (scope === factory.value && token === scopeGeneration) failure(reason) } finally { if (scope === factory.value && token === scopeGeneration) busy.value = false }
}
</script>
<template>
  <section class="rounded-xl border border-slate-200 bg-white p-4 text-slate-800 sm:p-5" aria-label="供应商收货工作区">
    <header class="mb-4 flex flex-wrap items-center justify-between gap-3"><div><h2 class="text-base font-bold">供应商发货待收</h2><p class="mt-1 text-xs text-slate-500">{{ data?.supplier_name }} · 供应商确认送货后，仓库核实实际到货与仓位。</p></div><div class="flex flex-wrap items-center gap-2 text-xs"><button type="button" :aria-pressed="shipmentView === 'PENDING'" class="rounded-lg border px-3 py-2" :class="shipmentView === 'PENDING' ? 'border-teal-200 bg-teal-50 text-teal-800' : 'bg-white'" @click="shipmentView = 'PENDING'">待核实 {{ data?.shipments.filter(awaitingReceipt).length ?? 0 }}</button><button type="button" :aria-pressed="shipmentView === 'HISTORY'" class="rounded-lg border px-3 py-2" :class="shipmentView === 'HISTORY' ? 'border-teal-200 bg-teal-50 text-teal-800' : 'bg-white'" @click="shipmentView = 'HISTORY'">已核实记录</button><button type="button" :disabled="busy || loading" class="rounded-lg border bg-white px-3 py-2 disabled:opacity-50" @click="load">刷新</button></div></header>
    <CartonShipmentFilters v-model="shipmentFilters" :rows="data?.shipments ?? []" />
    <p class="mt-2 text-xs text-slate-500">显示 {{ visibleShipments.length }} 张送货单</p>
    <p v-if="loading" role="status" class="mb-3 text-sm text-slate-500">正在读取供应商送货单…</p>
    <p v-if="error" role="alert" class="mb-4 rounded bg-red-50 p-3 text-red-700">{{ error }}</p><p v-if="message" role="status" class="mb-4 rounded bg-emerald-50 p-3 text-emerald-800">{{ message }}</p>
    <section class="mt-4"><p class="mb-3 text-sm text-slate-500">供应商确认原系统送货单后进入本厂区待收货；实收默认带入送货数量，仓库核对未到、短收、不合格和仓位后入库。</p><article v-for="shipment in visibleShipments" :key="shipment.id" class="border-t py-3"><div class="flex justify-between gap-3"><strong>{{ shipment.delivery_note_no }} · {{ shipment.delivery_date }}<span v-if="shipment.source_filename" class="ml-2 text-xs font-normal text-slate-500">来源 {{ shipment.source_filename }}</span></strong><button v-if="awaitingReceipt(shipment) && canReceive" :disabled="busy" class="rounded bg-teal-700 px-3 py-2 text-sm text-white" @click="start(shipment)">{{ shipment.requires_correction ? '更正原单验收' : '核实实际收到' }}</button><span v-else class="text-sm">{{ shipment.status === 'SENT' ? '等待仓库确认' : shipment.status === 'NOT_RECEIVED' ? '未收到，已退回' : shipment.receipt_id ? '已核实入库' : '已核实，无有效入库' }} {{ shipment.receipt_status === 'REVERSED' ? '（收料已冲销）' : '' }}</span><button v-if="canReceive && shipment.receipt_id && shipment.receipt_status === 'POSTED'" type="button" :disabled="busy || loading" :aria-label="`冲销送货单 ${shipment.delivery_note_no} 的收料`" class="shrink-0 rounded-lg border border-red-200 px-3 py-2 text-xs font-semibold text-red-700" @click="emit('reverse', shipment.receipt_id)">冲销</button></div><p v-for="line in shipment.lines" :key="line.id" class="mt-1 text-sm">{{ line.customer_name }} · {{ line.contract_no }} · 客户 PO {{ line.customer_po || '未填写' }} · {{ line.item_no }} · {{ line.source_type === 'AD_HOC_REVIEW' ? '无单待核实' : line.child_no }} · {{ line.packaging_type }} {{ line.specification }} · 发货 {{ line.quantity }} {{ line.unit }}</p><div v-if="awaitingReceipt(shipment) && canReceive" class="mt-2 space-y-2"><section v-for="source in shipment.lines.filter(line => line.source_type === 'AD_HOC_REVIEW')" :key="source.id" class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs"><strong>补建订单后关联 · {{ source.contract_no }} / {{ source.item_no }}</strong><p class="mt-1 text-amber-800">如已补建正式订单，先选择客户及完整匹配的纸品，再沿原送货单验收。</p><div class="mt-2 flex flex-wrap items-center gap-2"><select v-model="pendingCustomers[source.id]" :aria-label="source.id + ' 关联客户'" :disabled="busy" class="rounded border bg-white p-2" @change="pendingTargets[source.id] = ''"><option value="">选择归属客户</option><option v-for="customer in customers" :key="customer.customer_code" :value="customer.customer_code">{{ customer.customer_name }}</option></select><select v-model="pendingTargets[source.id]" :aria-label="source.id + ' 收货前关联订单'" :disabled="busy || !pendingCustomers[source.id]" class="rounded border bg-white p-2"><option value="">选择正式订单纸品</option><option v-for="target in pendingFormalTargets(source)" :key="target.line.id" :value="target.line.id">{{ target.order.order_no }} · {{ target.order.customer_name }} · PO {{ target.order.customer_po || '未填' }} · {{ target.line.specification }} {{ target.line.dimension_unit }} · 待送 {{ target.line.remaining_to_ship }} {{ target.line.unit }}</option></select><input v-model="pendingReasons[source.id]" :aria-label="source.id + ' 收货前关联原因'" :disabled="busy" placeholder="关联原因（至少四字）" class="rounded border p-2"><button type="button" :disabled="busy || !pendingTargets[source.id]" :aria-label="source.id + ' 确认收货前关联'" class="rounded border border-teal-300 bg-white px-3 py-2 text-teal-800 disabled:opacity-40" @click="linkPending(shipment, source)">关联正式订单</button></div></section></div><details v-if="shipment.acceptance_history?.length" class="mt-2 text-xs text-slate-600"><summary class="cursor-pointer">验收与冲销历史（{{ shipment.acceptance_history.length }} 次）</summary><p v-for="(history, index) in shipment.acceptance_history" :key="index" class="mt-1">{{ history.acceptance_date }} · {{ history.status === 'REVERSED' ? '已冲销' : '原验收' }} · {{ history.lines.map(line => '实收 ' + line.received_quantity).join('；') }}</p></details><div v-for="sample in shipment.sample_receipts ?? []" :key="sample.receipt_line_id" class="mt-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs"><p class="font-semibold">无单样板收料记录 · {{ sample.customer_name }} · {{ sample.contract_no }} / {{ sample.item_no }} · {{ sample.quantity }} {{ sample.unit }}</p><p v-if="sample.linked_order_line_id" class="mt-1 text-teal-800">已关联正式订单纸品 {{ sample.linked_order_line_id }}；库存和月结不重复入账。</p><template v-else-if="canLink && shipment.receipt_status === 'POSTED'"><p class="mt-1 text-amber-800">后续正式订单出现后可人工关联。只关联需求，不再生成第二笔入库或月结。</p><div class="mt-2 flex flex-wrap gap-2"><select v-model="linkTargets[sample.receipt_line_id]" :aria-label="`${sample.receipt_line_id} 关联正式订单`" :disabled="busy" class="rounded border bg-white p-2"><option value="">选择正式订单纸品</option><option v-for="target in formalTargets(sample)" :key="target.line.id" :value="target.line.id">{{ target.order.order_no }} · {{ target.line.child_no }} · {{ target.line.specification }} · 需求 {{ target.line.required_quantity }} {{ target.line.unit }}</option></select><input v-model="linkReasons[sample.receipt_line_id]" :aria-label="`${sample.receipt_line_id} 关联原因`" :disabled="busy" class="rounded border p-2" placeholder="关联原因（至少四字）"><button type="button" :disabled="busy || !formalTargets(sample).length" class="rounded border border-teal-300 bg-white px-3 py-2 text-teal-800 disabled:opacity-40" @click="linkSample(sample)">关联后续订单</button></div><p v-if="!formalTargets(sample).length" class="mt-1 text-amber-800">目前没有同客户、货号、纸品类型、纸质和单位的待收正式订单。</p></template></div></article><p v-if="data && !loading && !error && !visibleShipments.length" class="py-5 text-slate-500">{{ shipmentView === 'PENDING' ? '本厂区当前没有待核实的供应商送货单。' : '暂无已核实的供应商送货记录。' }}</p></section>

    <div v-if="active" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-3"><form role="dialog" aria-modal="true" aria-label="核实供应商实际送货" class="max-h-[94vh] w-full max-w-6xl overflow-auto rounded-xl bg-white p-5" @submit.prevent="confirm"><h2 class="text-lg font-bold">核实送货单 {{ active.delivery_note_no }}</h2><p class="my-2 text-sm text-amber-800">实收已按送货单预填，请核对实际到货。未到的纸品可一键标记；破损、拒收或短收填写实际数量及原因。有效数量入库前仍须指定仓位；单价在采购单为 CNY 时优先带入供应商送货单，缺价或币种不同则带入采购单价，仓库核对后确认。</p><CartonSplitReceiptReview v-if="hasSplits" :factory="factory" :lines="splitLines" @update:confirmation="splitConfirmation = $event" />
<section v-if="active.requires_correction" class="mb-3 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm"><strong>原收料已冲销，请重新核实整张送货单</strong><p class="mt-1 text-amber-800">本次更正关联原送货单与已冲销收料，旧验收保留，不重复计入库存或月结。</p><label class="mt-2 block">更正原因<input v-model="correctionReason" aria-label="送货单验收更正原因" :disabled="busy" required minlength="4" class="mt-1 w-full rounded border p-2"></label></section><button type="button" :disabled="busy" class="mb-3 rounded border border-amber-300 px-3 py-1.5 text-xs text-amber-800" @click="markAllNotReceived">整单未到</button><label class="block text-sm">实际验收日期<input v-model="acceptanceDate" :disabled="busy" type="date" required aria-label="发货验收日期" class="ml-2 rounded border p-2"></label><article v-for="(row, index) in received" :key="row.shipment_line_id" class="mt-4 rounded-lg border p-3"><h3 class="font-semibold">{{ active.lines[index]?.source_type === 'AD_HOC_REVIEW' ? '无单待核实' : active.lines[index]?.child_no }} · {{ active.lines[index]?.contract_no }} · PO {{ active.lines[index]?.customer_po || '未填写' }} · {{ active.lines[index]?.item_no }} · {{ active.lines[index]?.packaging_type }} · 发货 {{ active.lines[index]?.quantity }} {{ active.lines[index]?.unit }}</h3><div v-if="active.lines[index]?.source_type === 'AD_HOC_REVIEW'" class="mt-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm"><strong class="text-amber-900">无正式订单 · 仓库必须核实</strong><p class="mt-1 text-amber-800">先核对实物和需求：确需入库的样板箱须填写客户、用途、需求人和价格；送错货须全数拒收。未到货使用“此项未到”。</p><label class="mt-2 block">处理结论<select v-model="row.no_order_decision" :aria-label="`${row.shipment_line_id} 无单处理结论`" :disabled="busy || Number(row.received_quantity) === 0" class="ml-2 rounded border bg-white p-2" @change="setNoOrderDecision(index)"><option value="">请选择</option><option value="SAMPLE">确需入库样板箱</option><option value="WRONG_DELIVERY">送错货，拒收</option></select></label><div v-if="row.no_order_decision === 'SAMPLE'" class="mt-2 grid gap-2 sm:grid-cols-3"><label>归属客户<select v-model="row.customer_code" :aria-label="`${row.shipment_line_id} 样板箱客户`" :disabled="busy" required class="mt-1 w-full rounded border bg-white p-2"><option value="">请选择客户</option><option v-for="customer in customers" :key="customer.customer_code" :value="customer.customer_code">{{ customer.customer_name }} · {{ customer.customer_code }}</option></select></label><label>用途<input v-model="row.sample_purpose" :aria-label="`${row.shipment_line_id} 样板箱用途`" :disabled="busy" required class="mt-1 w-full rounded border p-2" placeholder="例如客户打板确认"></label><label>需求人<input v-model="row.requested_by" :aria-label="`${row.shipment_line_id} 样板箱需求人`" :disabled="busy" required class="mt-1 w-full rounded border p-2"></label><label>收料单位<select v-model="row.unit" :aria-label="`${row.shipment_line_id} 样板箱单位`" :disabled="busy" required class="mt-1 w-full rounded border bg-white p-2"><option value="个">个</option><option value="张">张</option></select></label></div><p v-if="row.no_order_decision === 'WRONG_DELIVERY'" class="mt-2 text-amber-900">把实际到货数量填在下方，拒收数量须等于实收，并写明送错原因；不会入库或参与月结。</p></div><div class="mt-2 flex gap-2"><button type="button" :disabled="busy" class="rounded border border-amber-200 px-2 py-1 text-xs text-amber-800" @click="markNotReceived(index)">此项未到</button><button type="button" :disabled="busy" class="rounded border border-teal-200 px-2 py-1 text-xs text-teal-800" @click="markAsDelivered(index)">按送货量恢复</button></div><div class="mt-3 grid gap-3 sm:grid-cols-4"><label class="text-sm">实际收到<input v-model.number="row.received_quantity" :aria-label="`${row.shipment_line_id} 实收`" :disabled="busy" type="number" min="0" step="0.0001" :max="active.lines[index]?.quantity" required class="mt-1 w-full rounded border p-2"></label><label class="text-sm">破损<input v-model.number="row.damaged_quantity" :disabled="busy" type="number" min="0" step="0.0001" class="mt-1 w-full rounded border p-2"></label><label class="text-sm">拒收<input v-model.number="row.rejected_quantity" :disabled="busy" type="number" min="0" step="0.0001" class="mt-1 w-full rounded border p-2"></label><label class="text-sm">其他不可用<input v-model.number="row.unusable_quantity" :disabled="busy" type="number" min="0" step="0.0001" class="mt-1 w-full rounded border p-2"></label><label class="text-sm">入库单价 {{ active.lines[index]?.currency }}<input v-model.number="row.unit_price" :disabled="busy" type="number" min="0" step="0.000001" required class="mt-1 w-full rounded border p-2"><span v-if="Number(active.lines[index]?.delivery_unit_price) > 0 && (active.lines[index]?.currency ?? 'CNY').toUpperCase() === 'CNY'" class="mt-1 block text-xs text-slate-500">已带入送货单单价</span><span v-if="Number(active.lines[index]?.delivery_unit_price) > 0 && (active.lines[index]?.currency ?? 'CNY').toUpperCase() === 'CNY' && Number(active.lines[index]?.unit_price) > 0 && Number(active.lines[index]?.delivery_unit_price) !== Number(active.lines[index]?.unit_price)" class="mt-1 block text-xs text-amber-700">送货单 CNY {{ active.lines[index]?.delivery_unit_price }} · 采购单 CNY {{ active.lines[index]?.unit_price }}，请核对</span><span v-if="Number(active.lines[index]?.delivery_unit_price) > 0 && (active.lines[index]?.currency ?? 'CNY').toUpperCase() !== 'CNY'" class="mt-1 block text-xs text-amber-700">送货单价按 CNY 识别；采购单为 {{ active.lines[index]?.currency }}，已带采购单价，请核对</span></label><label class="text-sm">纸质<input v-model="row.paper_quality" :disabled="busy || Boolean(active.lines[index]?.paper_quality)" class="mt-1 w-full rounded border p-2"></label><label class="text-sm">规格<input v-model="row.specification" :disabled="busy || Boolean(active.lines[index]?.specification)" class="mt-1 w-full rounded border p-2"></label><label class="text-sm">差异原因<input v-model="row.difference_reason" :disabled="busy" :required="effective(row) !== Number(active.lines[index]?.quantity)" :aria-label="`${row.shipment_line_id} 差异原因`" class="mt-1 w-full rounded border p-2"></label></div><p class="my-2 font-semibold text-teal-700">有效入库 {{ effective(row) }} {{ active.lines[index]?.unit }}</p><CartonReceiptAllocations v-model="row.location_allocations" :effective="effective(row)" :locations="locations" :factory-id="factory" :disabled="busy" @created="load" /></article><p v-if="error" role="alert" class="my-3 text-red-700">{{ error }}</p><div class="mt-4 flex justify-end gap-3"><button type="button" :disabled="busy" class="rounded border px-4 py-2" @click="active = null">取消</button><button :disabled="busy" class="rounded bg-teal-700 px-4 py-2 text-white">{{ busy ? '正在保存…' : received.every(row => Number(row.received_quantity) === 0) ? '确认整单未收到并退回' : '确认实际收料并入库' }}</button></div></form></div>
  </section>
</template>
