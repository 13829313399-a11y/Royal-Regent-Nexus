<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import { cartonSupplierPortalApi as api, type PortalWorkspace, type PortalShipment, type ShipmentLine, type ReceiveLine, type SampleReceipt, type ShipmentReceiptOption } from '@/api/cartonSupplierPortal'
import { cartonPositionsApi, type CartonLocation } from '@/api/cartonPositions'
import { cartonProcurementApi, type CartonCustomerResponse } from '@/api/cartonProcurement'
import CartonReceiptAllocations from '@/components/CartonReceiptAllocations.vue'
import CartonSplitReceiptReview from '@/components/CartonSplitReceiptReview.vue'
import CartonShipmentFilters from '@/components/CartonShipmentFilters.vue'
import { emptyShipmentFilters, filterShipments } from '@/features/carton-procurement/queryFilters'
import { isSupplierOrderSource, supplierOrderPapers, supplierPaperCompatible, type SupplierOrderSource } from '@/features/carton-procurement/supplierOrderSource'
const props = defineProps<{ factoryId?: string; shipmentId?: string; responsibilityScope?: 'OWN' | 'ALL' }>()
const emit = defineEmits<{ changed: []; reverse: [receiptId: string]; 'create-order': [source: SupplierOrderSource] }>()
const route = useRoute(); const app = useAppStore(); const auth = useAuthStore()
const factory = computed(() => String(props.factoryId || route.query.factory || app.activeProductionFactory.id))
const data = ref<PortalWorkspace | null>(null); const locations = ref<CartonLocation[]>([]); const customers = ref<CartonCustomerResponse[]>([])
const error = ref(''); const message = ref(''); const busy = ref(false); const loading = ref(false)
const active = ref<PortalShipment | null>(null); const received = ref<ReceiveLine[]>([])
const splitConfirmation = ref('')
const correctionReason = ref('')
const remainingAction = ref<'WAIT' | 'CLOSE'>('WAIT')
const receivable = (line?: ShipmentLine) => Number(line?.receivable_quantity ?? line?.quantity ?? 0)
const differenceRequired = (row: ReceiveLine, line?: ShipmentLine) => effective(row) !== Number(row.received_quantity) || (remainingAction.value === 'CLOSE' && effective(row) !== receivable(line))
const linkActive = ref<PortalShipment | null>(null)
const receiptOptions = ref<ShipmentReceiptOption[]>([])
const receiptChoice = ref('')
const receiptLinkReason = ref('')
const candidateLoading = ref(false)
const candidateError = ref('')
const newDeliveryConfirmed = ref(false)
let candidateGeneration = 0
async function checkReceipts(shipment: PortalShipment) {
  const token = ++candidateGeneration, scope = factory.value, scopeToken = scopeGeneration
  receiptOptions.value = []; candidateError.value = ''; candidateLoading.value = true; newDeliveryConfirmed.value = false
  try {
    const result = await api.receiptOptions(scope, shipment.id)
    if (token === candidateGeneration && scopeToken === scopeGeneration && scope === factory.value) receiptOptions.value = result
  } catch (reason) {
    if (token === candidateGeneration && scopeToken === scopeGeneration && scope === factory.value) candidateError.value = getApiErrorMessage(reason)
  } finally { if (token === candidateGeneration && scopeToken === scopeGeneration) candidateLoading.value = false }
}
function openReceiptLink(shipment: PortalShipment) {
  if (!canReceive.value || shipment.can_operate === false || busy.value) return
  if (active.value?.id === shipment.id) suspendedReceiptDraft = captureReceiptDraft(shipment)
  active.value = null; linkActive.value = shipment; receiptChoice.value = ''; receiptLinkReason.value = ''; error.value = ''
  void checkReceipts(shipment)
}
async function confirmReceiptLink() {
  const shipment = linkActive.value, receipt = receiptOptions.value.find(row => row.id === receiptChoice.value && !row.already_linked)
  if (!canReceive.value || busy.value || candidateLoading.value || candidateError.value || !shipment) return
  if (!receipt || receiptLinkReason.value.trim().length < 4) { error.value = '请选择原收料记录，并填写至少四字关联原因'; return }
  const scope = factory.value, token = scopeGeneration; busy.value = true; error.value = ''
  try {
    const result = await api.linkReceipt(shipment.id, { factory_id: scope, expected_revision: shipment.revision,
      receipt_id: receipt.id, expected_receipt_revision: receipt.revision, reason: receiptLinkReason.value.trim() })
    if (scope === factory.value && token === scopeGeneration) {
      linkActive.value = null; suspendedReceiptDraft = null; message.value = result.requires_correction ? '已关联原冲销凭证；请沿原送货单更正验收，当前未重新入库。' : '后补送货凭证已关联原收料；库存和月结未重复记账。'; emit('changed'); await load()
    }
  } catch (reason) { if (scope === factory.value && token === scopeGeneration) failure(reason) }
  finally { if (scope === factory.value && token === scopeGeneration) busy.value = false }
}
function closeReceiptDialog() {
  if (busy.value) return
  if (active.value) suspendedReceiptDraft = captureReceiptDraft(active.value)
  active.value = null; linkActive.value = null; candidateGeneration++; candidateLoading.value = false; candidateError.value = ''; receiptOptions.value = []
}

const pendingCustomers = ref<Record<string, string>>({})
const pendingTargets = ref<Record<string, string>>({})
const pendingReasons = ref<Record<string, string>>({})
const statusActive = ref<PortalShipment | null>(null)
const statusAction = ref<'defer' | 'reopen'>('defer')
const statusReason = ref('')
function openStatusChange(shipment: PortalShipment, action: 'defer' | 'reopen') {
  if (!canReceive.value || shipment.can_operate === false || busy.value) return
  statusActive.value = shipment; statusAction.value = action; statusReason.value = ''; error.value = ''
}
async function confirmStatusChange() {
  const shipment = statusActive.value
  if (!shipment || busy.value || !canReceive.value) return
  if (statusReason.value.trim().length < 4) { error.value = '请填写至少四字原因'; return }
  const scope = factory.value, token = scopeGeneration, action = statusAction.value
  busy.value = true; error.value = ''
  try {
    await api.changeNonArrival(shipment.id, action, { factory_id: scope, expected_revision: shipment.revision, reason: statusReason.value.trim() })
    if (scope === factory.value && token === scopeGeneration) {
      statusActive.value = null; active.value = null; received.value = []
      message.value = action === 'defer' ? '已记录暂未到货，原送货单继续待收，在途需求仍受保护。' : '原未到货反馈已保留，送货单重新待收，请重新核实实际到货。'
      emit('changed'); await load()
    }
  } catch (reason) { if (scope === factory.value && token === scopeGeneration) failure(reason) }
  finally { if (scope === factory.value && token === scopeGeneration) busy.value = false }
}
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
const canCreateOrder = computed(() => canRead.value && canReceive.value && can('carton_procurement:order_write'))
const shipmentView = ref<'PENDING' | 'HISTORY'>('PENDING')
const shipmentFilters = ref(emptyShipmentFilters())
const visibleShipments = computed(() => filterShipments(data.value?.shipments ?? [], shipmentFilters.value).filter(shipment => shipmentView.value === 'PENDING' ? awaitingReceipt(shipment) : !awaitingReceipt(shipment)))
watch(shipmentView, () => { shipmentFilters.value.status = '' })
watch(factory, () => { shipmentFilters.value = emptyShipmentFilters() })
const linkTargets = ref<Record<string, string>>({}); const linkReasons = ref<Record<string, string>>({})
let generation = 0
let scopeGeneration = 0
let suspendedReceiptDraft: ReceiptDraft | null = null
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
  if (!canRead.value) return false
  const token = ++generation, scope = factory.value; loading.value = true
  try {
    const [workspace, bins, activeCustomers] = await Promise.all([api.workspace(scope, true, props.responsibilityScope ?? 'OWN'), canReceive.value ? cartonPositionsApi.locations(scope) : Promise.resolve([]), canReceive.value ? cartonProcurementApi.listCustomers(scope, false) : Promise.resolve([])])
    if (token !== generation || scope !== factory.value) return false
    data.value = workspace; locations.value = bins; customers.value = activeCustomers
    openDeepLinkedShipment()
    return true
  } catch (reason) { if (token === generation) failure(reason); return false } finally { if (token === generation) loading.value = false }
}
// Focus-driven session refreshes can replace currentUser without changing access.
// Only actual identity, authorization or factory changes invalidate receipt drafts.
watch([
  factory, canRead, canReceive, canLink, canCreateOrder, () => props.responsibilityScope,
  () => auth.currentUser?.id,
  () => auth.authorizationVersion,
  () => auth.authzMode,
  () => auth.currentUser?.identity?.effective_context_key,
  () => auth.currentUser?.identity?.employment_epoch,
], () => {
  active.value = null; linkActive.value = null; received.value = []
  receiptOptions.value = []; receiptChoice.value = ''; receiptLinkReason.value = ''
  candidateGeneration++; candidateLoading.value = false; candidateError.value = ''
  data.value = null; locations.value = []; customers.value = []
  linkTargets.value = {}; linkReasons.value = {}; pendingCustomers.value = {}; pendingTargets.value = {}; pendingReasons.value = {}
  splitConfirmation.value = ''; correctionReason.value = ''; newDeliveryConfirmed.value = false
  openedDeepLinkKey = ''; error.value = ''; message.value = ''; busy.value = false; loading.value = false
  statusActive.value = null; statusReason.value = ''; shipmentView.value = 'PENDING'; acceptanceDate.value = new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
  generation++; scopeGeneration++
  suspendedReceiptDraft = null
  if (canRead.value) void load()
}, { immediate: true })
defineExpose({ refresh: load, resumeOrderSource })
onBeforeUnmount(() => { generation++; scopeGeneration++; candidateGeneration++; suspendedReceiptDraft = null })
watch(() => props.shipmentId || route.query.shipment, () => { openedDeepLinkKey = ''; openDeepLinkedShipment() })
function start(shipment: PortalShipment) {
  if (!canReceive.value || shipment.can_operate === false) return
  if (shipment.requires_receipt_link) { openReceiptLink(shipment); return }
  const savedDraft = suspendedReceiptDraft
  if (savedDraft?.shipment.id === shipment.id && savedDraft.factoryId === factory.value && savedDraft.scope === scopeGeneration) {
    suspendedReceiptDraft = null
    restoreReceiptDraft(shipment, savedDraft)
    return
  }
  linkActive.value = null
  if (!shipment.requires_correction) void checkReceipts(shipment)
  else { candidateGeneration++; receiptOptions.value = []; candidateError.value = ''; candidateLoading.value = false }
  splitConfirmation.value = ''
  correctionReason.value = ''
  remainingAction.value = 'WAIT'
  active.value = shipment; error.value = ''
  received.value = shipment.lines.map(receiptRow)
}
function receiptRow(line: ShipmentLine): ReceiveLine {
  return { shipment_line_id: line.id, received_quantity: receivable(line), damaged_quantity: 0, rejected_quantity: 0, unusable_quantity: 0, unit_price: Number(line.delivery_unit_price) > 0 && (line.currency ?? 'CNY').toUpperCase() === 'CNY' ? Number(line.delivery_unit_price) : Number(line.unit_price || 0), paper_quality: line.paper_quality, specification: line.specification, location_allocations: [], difference_reason: '', zero_price_kind: 'PENDING', no_order_decision: '', customer_code: '', sample_purpose: '', requested_by: '', unit: line.unit }
}
interface ReceiptDraft {
  factoryId: string
  scope: number
  shipment: PortalShipment
  sourceLineId?: string
  rows: Map<string, ReceiveLine>
  acceptanceDate: string
  correctionReason: string
  remainingAction: 'WAIT' | 'CLOSE'
  splitConfirmation: string
  newDeliveryConfirmed: boolean
}
const sourceKey = (line: ShipmentLine) => line.original_unmatched_line_id || line.id
const copyReceiptRow = (row: ReceiveLine): ReceiveLine => ({ ...row, location_allocations: row.location_allocations.map(part => ({ ...part })) })
function captureReceiptDraft(shipment: PortalShipment): ReceiptDraft {
  const current = active.value?.id === shipment.id
  const previous = suspendedReceiptDraft
  if (!current && previous?.factoryId === factory.value && previous.scope === scopeGeneration && previous.shipment.id === shipment.id) {
    return { ...previous, shipment, rows: new Map([...previous.rows].map(([key, row]) => [key, copyReceiptRow(row)])) }
  }
  return { factoryId: factory.value, scope: scopeGeneration, shipment,
    rows: new Map(shipment.lines.map((line, index) => [sourceKey(line), copyReceiptRow(current && received.value[index] ? received.value[index]! : receiptRow(line))])),
    remainingAction: remainingAction.value, acceptanceDate: acceptanceDate.value, correctionReason: current ? correctionReason.value : '',
    splitConfirmation: current ? splitConfirmation.value : '', newDeliveryConfirmed: current && newDeliveryConfirmed.value }
}
function restoreReceiptDraft(shipment: PortalShipment, draft?: ReceiptDraft | null, changedAssociation = false) {
  const validDraft = draft?.factoryId === factory.value && draft.scope === scopeGeneration && draft.shipment.id === shipment.id ? draft : null
  start(shipment)
  if (!active.value || active.value.id !== shipment.id || !validDraft) return
  received.value = shipment.lines.map(line => {
    const saved = validDraft.rows.get(sourceKey(line))
    if (!saved) return receiptRow(line)
    const row = { ...copyReceiptRow(saved), shipment_line_id: line.id }
    if (line.source_type !== 'AD_HOC_REVIEW') {
      row.no_order_decision = ''; row.customer_code = ''; row.sample_purpose = ''; row.requested_by = ''
      row.unit = line.unit; row.paper_quality = line.paper_quality; row.specification = line.specification
    }
    return row
  })
  acceptanceDate.value = validDraft.acceptanceDate
  correctionReason.value = validDraft.correctionReason
  remainingAction.value = validDraft.remainingAction
  splitConfirmation.value = changedAssociation ? '' : validDraft.splitConfirmation
  newDeliveryConfirmed.value = changedAssociation ? false : validDraft.newDeliveryConfirmed
}
function createOrderFromShipment(shipment: PortalShipment, line: ShipmentLine) {
  if (!canCreateOrder.value || busy.value || loading.value || shipment.can_operate === false || !awaitingReceipt(shipment)
    || shipment.requires_receipt_link || line.source_type !== 'AD_HOC_REVIEW') return
  const papers = supplierOrderPapers(shipment, line)
  if (!papers.length || !line.contract_no || !line.item_no) { error.value = '请先核对原送货单合同号和货号'; return }
  suspendedReceiptDraft = captureReceiptDraft(shipment)
  suspendedReceiptDraft.sourceLineId = line.id
  const source: SupplierOrderSource = { factoryId: factory.value, shipmentId: shipment.id, sourceLineId: line.id,
    deliveryNoteNo: shipment.delivery_note_no, supplierId: '', contractNo: line.contract_no, itemNo: line.item_no,
    customerPo: line.customer_po, papers,
    ...(pendingCustomers.value[line.id] ? { customerCode: pendingCustomers.value[line.id] } : {}) }
  active.value = null; received.value = []; candidateGeneration++; candidateLoading.value = false; candidateError.value = ''; receiptOptions.value = []
  emit('create-order', source)
}
async function resumeOrderSource(source: SupplierOrderSource, orderId?: string) {
  if (!isSupplierOrderSource(source) || source.factoryId !== factory.value || !canReceive.value || !canRead.value) return false
  if (suspendedReceiptDraft?.sourceLineId && suspendedReceiptDraft.shipment.id === source.shipmentId
    && suspendedReceiptDraft.sourceLineId !== source.sourceLineId) return false
  const token = scopeGeneration, draft = suspendedReceiptDraft?.shipment.id === source.shipmentId
    && suspendedReceiptDraft.sourceLineId === source.sourceLineId ? suspendedReceiptDraft : null
  if (orderId && !await load()) return false
  if (token !== scopeGeneration || source.factoryId !== factory.value) return false
  const shipment = data.value?.shipments.find(row => row.id === source.shipmentId)
  if (!shipment || !awaitingReceipt(shipment) || shipment.can_operate === false) {
    error.value = '原送货单状态或操作范围已变化，请刷新后核对，补建订单不会再次生成。'; return false
  }
  const order = orderId ? data.value?.orders.find(row => row.id === orderId) : undefined
  if (orderId && (!order?.customer_code || !['PENDING_SUPPLIER', 'PARTIALLY_RECEIVED'].includes(order.status)
    || order.awaiting_issue || materialText(order.contract_no) !== materialText(source.contractNo)
    || materialText(order.item_no) !== materialText(source.itemNo))) {
    error.value = '补建订单当前未处于可关联状态或操作范围已变化；订单已保存，请先核对确认锁定及当前采购版本，不要重新创建。'
    return false
  }
  restoreReceiptDraft(shipment, draft)
  if (orderId) {
    for (const line of shipment.lines.filter(row => source.papers.some(paper => paper.id === sourceKey(row)) && row.source_type === 'AD_HOC_REVIEW')) {
      if (!order?.customer_code) continue
      pendingCustomers.value[line.id] = order.customer_code
      const targets = pendingFormalTargets(line).filter(target => target.order.id === orderId)
      pendingTargets.value[line.id] = targets.length === 1 ? targets[0]!.line.id : ''
      pendingReasons.value[line.id] ||= '核对补建正式订单后关联'
    }
    message.value = '正式订单已锁定；请核对原送货行对应的纸品并确认关联，之后再按实际收料入库。'
  }
  suspendedReceiptDraft = null
  return true
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
  row.received_quantity = receivable(shipped)
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
  } else if (row.no_order_decision === 'SAMPLE' || row.no_order_decision === 'GIFT') {
    if (row.no_order_decision === 'GIFT') { row.unit_price = 0; row.zero_price_kind = 'FREE' }
    row.rejected_quantity = 0
  }
}
const effective = (line: ReceiveLine) => Math.max(0, Number(line.received_quantity) - Number(line.damaged_quantity) - Number(line.rejected_quantity) - Number(line.unusable_quantity))
const materialText = (value: string) => value.toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]/g, '')
function pendingFormalTargets(source: ShipmentLine) {
  return (data.value?.orders ?? []).filter(order =>
    ['PENDING_SUPPLIER', 'PARTIALLY_RECEIVED'].includes(order.status) && !order.awaiting_issue
    && order.customer_code === pendingCustomers.value[source.id]
    && materialText(order.contract_no) === materialText(source.contract_no)
    && materialText(order.item_no) === materialText(source.item_no))
    .flatMap(order => order.lines.filter(line => supplierPaperCompatible(source, line)).map(line => ({ order, line })))
}
function existingFormalOrderCount(source: ShipmentLine) {
  return (data.value?.orders ?? []).filter(order => ['PENDING_SUPPLIER', 'PARTIALLY_RECEIVED'].includes(order.status)
    && materialText(order.contract_no) === materialText(source.contract_no)
    && materialText(order.item_no) === materialText(source.item_no)
    && order.lines.some(line => supplierPaperCompatible(source, line))).length
}
async function linkPending(shipment: PortalShipment, source: ShipmentLine) {
  const target = pendingFormalTargets(source).find(candidate => candidate.line.id === pendingTargets.value[source.id])
  const reason = (pendingReasons.value[source.id] || '').trim()
  if (!canReceive.value) return
  if (!target?.order.revision || reason.length < 4 || busy.value) {
    error.value = '请选择客户及正式订单纸品，并填写至少四字关联原因'; return
  }
  const scope = factory.value, token = scopeGeneration
  const draft = active.value?.id === shipment.id ? captureReceiptDraft(shipment) : null
  busy.value = true; error.value = ''
  try {
    const result = await api.linkShipmentLine(shipment.id, source.id, { factory_id: scope, customer_code: pendingCustomers.value[source.id]!,
      order_line_id: target.line.id, expected_revision: shipment.revision, expected_order_revision: target.order.revision, reason })
    if (scope === factory.value && token === scopeGeneration) {
      if (data.value) data.value.shipments = data.value.shipments.map(row => row.id === shipment.id ? result : row)
      message.value = '原送货单已关联正式订单；验收草稿保留，请核对实际收到。'
      emit('changed'); await load()
      if (scope === factory.value && token === scopeGeneration) {
        const fresh = data.value?.shipments.find(row => row.id === shipment.id)
        if (draft && fresh && awaitingReceipt(fresh) && fresh.can_operate !== false) restoreReceiptDraft(fresh, draft, true)
        else { active.value = null; received.value = [] }
      }
    }
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
  if (candidateLoading.value || candidateError.value) { error.value = '请先完成原收料重复检查；检查失败时点击重试'; return }
  if (receiptOptions.value.length && !newDeliveryConfirmed.value && received.value.some(row => Number(row.received_quantity) > 0)) {
    error.value = '发现相同纸品和数量的原收料；请关联原记录，或核对本次确为新一批到货'; return
  }
  if (active.value.requires_correction && correctionReason.value.trim().length < 4) {
    error.value = '原收料已冲销，请填写至少四字更正原因'; return
  }
  for (const [index, line] of received.value.entries()) {
    if (active.value.lines[index]?.source_type === 'AD_HOC_REVIEW' && Number(line.received_quantity) > 0) {
      if (!line.no_order_decision) { error.value = '每条已到的无单纸品必须选“样板箱、免费赠送或送错货拒收”'; return }
      if (line.no_order_decision === 'SAMPLE' && (!line.customer_code || (line.requested_by || '').trim().length < 2)) {
        error.value = '样板箱须选择客户并填写需求人；零价可选择免费或暂未定价'; return
      }
      if (line.no_order_decision === 'WRONG_DELIVERY' && effective(line) !== 0) { error.value = '送错货的有效入库数量必须为 0'; return }
    }
    if (active.value.lines[index]?.material_correction_pending && effective(line) > 0) { error.value = '纸品资料更正待双方确认，请先处理更正，再刷新核实入库'; return }
    if (line.no_order_decision === 'GIFT' && (!line.customer_code || Number(line.unit_price) !== 0)) { error.value = '免费赠送须选择客户，单价为 0'; return }
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
  try { const result = await api.receive(shipment.id, { remaining_action: remainingAction.value, factory_id: scope, expected_revision: shipment.revision, ...(newDeliveryConfirmed.value ? { new_delivery_confirmation: true } : {}), acceptance_date: acceptanceDate.value, lines: received.value.map(row => ({ ...row, zero_price_kind: Number(row.unit_price) === 0 ? row.no_order_decision === 'GIFT' ? 'FREE' : row.zero_price_kind || 'PENDING' : undefined })), split_confirmation: splitConfirmation.value, correction_reason: correctionReason.value.trim() }); if (factory.value === scope && token === scopeGeneration) { active.value = null; received.value = []; message.value = result.status === 'SENT' ? '本次收货已保存；余货继续留在原送货单待收。' : result.receipt_id ? '本次收货已入库；本送货单验收已结束。' : '仓库核实已保存；本单没有有效入库数量。'; emit('changed'); await load() } } catch (reason) { if (scope === factory.value && token === scopeGeneration) failure(reason) } finally { if (scope === factory.value && token === scopeGeneration) busy.value = false }
}
</script>
<template>
  <section class="rounded-xl border border-slate-200 bg-white p-4 text-slate-800 sm:p-5" aria-label="供应商收货工作区">
    <header class="mb-4 flex flex-wrap items-center justify-between gap-3"><div><h2 class="text-base font-bold">供应商发货待收</h2><p class="mt-1 text-xs text-slate-500">{{ data?.supplier_name }} · 供应商确认送货后，仓库核实实际到货与仓位。</p></div><div class="flex flex-wrap items-center gap-2 text-xs"><button type="button" :aria-pressed="shipmentView === 'PENDING'" class="rounded-lg border px-3 py-2" :class="shipmentView === 'PENDING' ? 'border-teal-200 bg-teal-50 text-teal-800' : 'bg-white'" @click="shipmentView = 'PENDING'">待核实 {{ data?.shipments.filter(awaitingReceipt).length ?? 0 }}</button><button type="button" :aria-pressed="shipmentView === 'HISTORY'" class="rounded-lg border px-3 py-2" :class="shipmentView === 'HISTORY' ? 'border-teal-200 bg-teal-50 text-teal-800' : 'bg-white'" @click="shipmentView = 'HISTORY'">已核实记录</button><button type="button" :disabled="busy || loading" class="rounded-lg border bg-white px-3 py-2 disabled:opacity-50" @click="load">刷新</button></div></header>
    <CartonShipmentFilters v-model="shipmentFilters" :rows="data?.shipments ?? []" />
    <p class="mt-2 text-xs text-slate-500">显示 {{ visibleShipments.length }} 张送货单</p>
    <p v-if="loading" role="status" class="mb-3 text-sm text-slate-500">正在读取供应商送货单…</p>
    <p v-if="error" role="alert" class="mb-4 rounded bg-red-50 p-3 text-red-700">{{ error }}</p><p v-if="message" role="status" class="mb-4 rounded bg-emerald-50 p-3 text-emerald-800">{{ message }}</p>
    <section class="mt-4"><p class="mb-3 text-sm text-slate-500">供应商确认原系统送货单后进入本厂区待收货；实收默认带入剩余待收数量，仓库核对未到、短收、不合格和仓位后入库。</p><article v-for="shipment in visibleShipments" :key="shipment.id" class="border-t py-3"><div class="flex flex-wrap items-start justify-between gap-3"><strong>{{ shipment.delivery_note_no }} · {{ shipment.delivery_date }}<span v-if="shipment.source_filename" class="ml-2 text-xs font-normal text-slate-500">来源 {{ shipment.source_filename }}</span></strong><div class="ml-auto flex flex-wrap items-center justify-end gap-2" :aria-label="`送货单 ${shipment.delivery_note_no} 操作`"><button v-if="canReceive && shipment.can_operate !== false && shipment.status === 'SENT' && !shipment.receipt_id && !shipment.requires_receipt_link && !shipment.requires_correction" type="button" :disabled="busy" class="rounded-lg border border-teal-200 px-3 py-2 text-xs text-teal-800" @click="openReceiptLink(shipment)">关联已入库记录</button><button v-if="awaitingReceipt(shipment) && canReceive && shipment.can_operate !== false" :disabled="busy" class="rounded bg-teal-700 px-3 py-2 text-sm text-white" @click="start(shipment)">{{ shipment.requires_receipt_link ? '关联已入库记录' : shipment.requires_correction ? '更正原单验收' : shipment.partially_received ? '继续收余货' : '核实实际收到' }}</button><span v-else class="text-sm">{{ shipment.linked_existing_receipt && !shipment.requires_correction ? '已关联原入库' : shipment.status === 'SENT' ? '等待仓库确认' : shipment.status === 'NOT_RECEIVED' ? '未收到，已退回' : shipment.receipt_id ? '已核实入库' : '已核实，无有效入库' }} {{ shipment.receipt_status === 'REVERSED' ? '（收料已冲销）' : '' }}</span><button v-if="canReceive && shipment.can_operate !== false && shipment.status === 'NOT_RECEIVED' && !shipment.receipt_id" type="button" :disabled="busy" class="rounded-lg border border-amber-300 px-3 py-2 text-xs text-amber-800" @click="openStatusChange(shipment, 'reopen')">更正未到货，重新待收</button><button v-if="canReceive && shipment.can_operate !== false && shipment.receipt_id && shipment.receipt_status === 'POSTED'" type="button" :disabled="busy || loading" :aria-label="`冲销送货单 ${shipment.delivery_note_no} 的收料`" class="shrink-0 rounded-lg border border-red-200 px-3 py-2 text-xs font-semibold text-red-700" @click="emit('reverse', shipment.receipt_id)">冲销</button></div></div><p v-if="shipment.pending_reason" class="mt-2 text-xs text-amber-800">待收说明：{{ shipment.pending_reason }}</p><p v-for="line in shipment.lines" :key="line.id" class="mt-1 text-sm">{{ line.customer_name }} · {{ line.contract_no }} · 客户 PO {{ line.customer_po || '未填写' }} · {{ line.item_no }} · {{ line.source_type === 'AD_HOC_REVIEW' ? '无单待核实' : line.child_no }} · 纸品类型：{{ line.packaging_type || '未填写' }} · 纸质：{{ line.paper_quality || '未填写' }} · 规格：{{ line.specification || '未填写' }} · 发货 {{ line.quantity }} {{ line.unit }}<span v-if="line.remaining_quantity != null" class="ml-2 font-semibold text-teal-800">累计实收 {{ line.received_quantity }} · 待收 {{ line.remaining_quantity }} {{ line.unit }}<span v-if="Number(line.closed_quantity) > 0"> · 短送结束 {{ line.closed_quantity }}</span><span v-if="shipment.requires_correction && Number(line.receivable_quantity) > 0"> · 本批待更正 {{ line.receivable_quantity }}</span></span><span v-if="line.material_correction_pending" class="ml-2 font-semibold text-amber-800">资料更正待确认 · 暂停本纸品入库</span><span v-else-if="line.material_correction_note" class="ml-2 text-teal-800">{{ line.material_correction_note }}</span></p><div v-if="awaitingReceipt(shipment) && canReceive && shipment.can_operate !== false" class="mt-2 space-y-2"><section v-for="source in shipment.lines.filter(line => line.source_type === 'AD_HOC_REVIEW')" :key="source.id" class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs"><div class="flex flex-wrap items-center justify-between gap-2"><strong>无单待核实 · {{ source.contract_no }} / {{ source.item_no }}</strong><button v-if="canCreateOrder && !shipment.requires_receipt_link" type="button" :aria-label="source.id + ' 待核补建正式订单'" :disabled="busy || loading" class="rounded border border-teal-300 bg-white px-3 py-2 font-semibold text-teal-800 disabled:opacity-40" @click="createOrderFromShipment(shipment, source)">按此补建正式订单</button></div><p class="mt-1 text-amber-800">实际属于正单时，可补齐完整订单及全部纸品需求，确认锁定后关联原送货行。送货数量仅是本次到货，不代表整单总需求。</p><p v-if="existingFormalOrderCount(source)" class="mt-1 font-semibold text-teal-800">已有 {{ existingFormalOrderCount(source) }} 张兼容正式订单，请先核对是否应关联原订单，避免重复下单。</p><p class="mt-1 text-amber-800">关联已有正式订单：选择归属客户及匹配纸品；只有明确关联后才进入正常验收。</p><div class="mt-2 flex flex-wrap items-center gap-2"><select v-model="pendingCustomers[source.id]" :aria-label="source.id + ' 关联客户'" :disabled="busy" class="rounded border bg-white p-2" @change="pendingTargets[source.id] = ''"><option value="">选择归属客户</option><option v-for="customer in customers" :key="customer.customer_code" :value="customer.customer_code">{{ customer.customer_name }}</option></select><select v-model="pendingTargets[source.id]" :aria-label="source.id + ' 收货前关联订单'" :disabled="busy || !pendingCustomers[source.id]" class="rounded border bg-white p-2"><option value="">选择正式订单纸品</option><option v-for="target in pendingFormalTargets(source)" :key="target.line.id" :value="target.line.id">{{ target.order.order_no }} · {{ target.order.customer_name }} · PO {{ target.order.customer_po || '未填' }} · {{ target.line.packaging_type || '未填写' }} · {{ target.line.paper_quality || '未填写' }} · {{ target.line.specification }} {{ target.line.dimension_unit }} · 待送 {{ target.line.remaining_to_ship }} {{ target.line.unit }}</option></select><input v-model="pendingReasons[source.id]" :aria-label="source.id + ' 收货前关联原因'" :disabled="busy" placeholder="关联原因（至少四字）" class="rounded border p-2"><button type="button" :disabled="busy || !pendingTargets[source.id]" :aria-label="source.id + ' 确认收货前关联'" class="rounded border border-teal-300 bg-white px-3 py-2 text-teal-800 disabled:opacity-40" @click="linkPending(shipment, source)">关联正式订单</button></div></section></div><details v-if="shipment.acceptance_history?.length" class="mt-2 text-xs text-slate-600"><summary class="cursor-pointer">验收与冲销历史（{{ shipment.acceptance_history.length }} 次）</summary><p v-for="(history, index) in shipment.acceptance_history" :key="index" class="mt-1">{{ history.acceptance_date }} · {{ history.status === 'REVERSED' ? '已冲销' : '原验收' }} · {{ history.lines.map(line => '实收 ' + line.received_quantity).join('；') }}<button v-if="history.receipt_id && history.status === 'POSTED' && canReceive && shipment.can_operate !== false" type="button" :disabled="busy" class="ml-3 text-red-700 underline" @click="emit('reverse', history.receipt_id)">冲销本次入库</button></p></details><div v-for="sample in shipment.sample_receipts ?? []" :key="sample.receipt_line_id" class="mt-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs"><p class="font-semibold">无单样板收料记录 · {{ sample.customer_name }} · {{ sample.contract_no }} / {{ sample.item_no }} · {{ sample.quantity }} {{ sample.unit }}</p><p class="mt-1">纸品类型：{{ sample.packaging_type || '未填写' }} · 纸质：{{ sample.paper_quality || '未填写' }} · 规格：{{ sample.specification || '未填写' }}</p><p v-if="sample.linked_order_line_id" class="mt-1 text-teal-800">已关联正式订单纸品 {{ sample.linked_order_line_id }}；库存和月结不重复入账。</p><template v-else-if="canLink && shipment.receipt_status === 'POSTED'"><p class="mt-1 text-amber-800">后续正式订单出现后可人工关联。只关联需求，不再生成第二笔入库或月结。</p><div class="mt-2 flex flex-wrap gap-2"><select v-model="linkTargets[sample.receipt_line_id]" :aria-label="`${sample.receipt_line_id} 关联正式订单`" :disabled="busy" class="rounded border bg-white p-2"><option value="">选择正式订单纸品</option><option v-for="target in formalTargets(sample)" :key="target.line.id" :value="target.line.id">{{ target.order.order_no }} · {{ target.line.child_no }} · {{ target.line.packaging_type || '未填写' }} · {{ target.line.paper_quality || '未填写' }} · {{ target.line.specification }} · 需求 {{ target.line.required_quantity }} {{ target.line.unit }}</option></select><input v-model="linkReasons[sample.receipt_line_id]" :aria-label="`${sample.receipt_line_id} 关联原因`" :disabled="busy" class="rounded border p-2" placeholder="关联原因（至少四字）"><button type="button" :disabled="busy || !formalTargets(sample).length" class="rounded border border-teal-300 bg-white px-3 py-2 text-teal-800 disabled:opacity-40" @click="linkSample(sample)">关联后续订单</button></div><p v-if="!formalTargets(sample).length" class="mt-1 text-amber-800">目前没有同客户、货号、纸品类型、纸质和单位的待收正式订单。</p></template></div></article><p v-if="data && !loading && !error && !visibleShipments.length" class="py-5 text-slate-500">{{ shipmentView === 'PENDING' ? '本厂区当前没有待核实的供应商送货单。' : '暂无已核实的供应商送货记录。' }}</p></section>

    <div v-if="active" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-3"><form role="dialog" aria-modal="true" aria-label="核实供应商实际送货" class="max-h-[94vh] w-full max-w-6xl overflow-auto rounded-xl bg-white p-5" @submit.prevent="confirm"><h2 class="text-lg font-bold">核实送货单 {{ active.delivery_note_no }}</h2><p class="my-2 text-sm text-amber-800">本次实收默认带入剩余待收数量，请核对实物。未到的余货继续待收；破损、拒收或确认短送结束时填写原因。有效数量入库前仍须指定仓位；单价在采购单为 CNY 时优先带入供应商送货单，缺价或币种不同则带入采购单价，仓库核对后确认。</p><CartonSplitReceiptReview v-if="hasSplits" :factory="factory" :lines="splitLines" @update:confirmation="splitConfirmation = $event" />
<section v-if="active.requires_correction" class="mb-3 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm"><strong>本次入库已冲销，请核实该批次</strong><p class="mt-1 text-amber-800">只更正已冲销的这一批，其他有效入库保留。更正后仍有余货的，继续沿原送货单收货。</p><label class="mt-2 block">更正原因<input v-model="correctionReason" aria-label="送货单验收更正原因" :disabled="busy" required minlength="4" class="mt-1 w-full rounded border p-2"></label></section><button type="button" :disabled="busy" class="mb-3 rounded border border-amber-300 px-3 py-1.5 text-xs text-amber-800" @click="markAllNotReceived">本次未到</button><button v-if="active.status === 'SENT' && !active.receipt_id && !active.requires_receipt_link" type="button" :disabled="busy" class="mb-3 ml-2 rounded border border-teal-300 px-3 py-1.5 text-xs text-teal-800" @click="openStatusChange(active, 'defer')">暂未到货，继续待收</button><label class="mb-3 block text-sm font-semibold">未收余货<select v-model="remainingAction" aria-label="未收余货处理" :disabled="busy" class="ml-2 rounded border p-2"><option value="WAIT">余货继续待收</option><option value="CLOSE">本次短送结束</option></select></label><p class="mb-3 text-xs text-slate-500">继续待收：后续到货可在本单追加入库。短送结束：结束本送货单的余货，采购欠数保留。</p><label class="block text-sm">实际验收日期<input v-model="acceptanceDate" :disabled="busy" type="date" required aria-label="发货验收日期" class="ml-2 rounded border p-2"></label><article v-for="(row, index) in received" v-show="receivable(active.lines[index]) > 0" :key="row.shipment_line_id" class="mt-4 rounded-lg border p-3"><h3 class="font-semibold">{{ active.lines[index]?.source_type === 'AD_HOC_REVIEW' ? '无单待核实' : active.lines[index]?.child_no }} · {{ active.lines[index]?.contract_no }} · PO {{ active.lines[index]?.customer_po || '未填写' }} · {{ active.lines[index]?.item_no }} · 发货 {{ active.lines[index]?.quantity }} {{ active.lines[index]?.unit }} · 累计实收 {{ active.lines[index]?.received_quantity ?? 0 }} · 本次最多可收 {{ receivable(active.lines[index]) }}</h3><div v-if="active.lines[index]?.source_type === 'AD_HOC_REVIEW'" class="mt-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm"><strong class="text-amber-900">无正式订单 · 仓库必须核实</strong><p class="mt-1 text-amber-800">实际属于正单时，先补建完整正式订单或关联已有订单，再沿原送货单验收。样板箱按样板办理；赠品选择免费赠送；送错货全数拒收，未到货使用“此项未到”。</p><div class="mt-3 rounded-lg border border-teal-200 bg-white p-3"><div class="flex flex-wrap items-center justify-between gap-2"><strong class="text-teal-900">正单补建 / 关联</strong><button v-if="canCreateOrder && !active.requires_receipt_link" type="button" :aria-label="row.shipment_line_id + ' 补建正式订单'" :disabled="busy || loading" class="rounded border border-teal-300 px-3 py-2 font-semibold text-teal-800 disabled:opacity-40" @click="createOrderFromShipment(active, active.lines[index]!)">按此补建正式订单</button></div><p class="mt-1 text-xs text-slate-600">同合同、货号的未关联纸品一起带入，可补齐未送的纸品及整单需求；已填写的验收数量、价格和仓位会保留。</p><p v-if="existingFormalOrderCount(active.lines[index]!)" class="mt-1 text-xs font-semibold text-teal-800">已有兼容正式订单，请先核对并复用，避免重复下单。</p><div class="mt-2 grid gap-2 sm:grid-cols-2"><label>关联已有正式订单 · 客户<select v-model="pendingCustomers[row.shipment_line_id]" :aria-label="row.shipment_line_id + ' 验收关联客户'" :disabled="busy" class="mt-1 w-full rounded border bg-white p-2" @change="pendingTargets[row.shipment_line_id] = ''"><option value="">选择归属客户</option><option v-for="customer in customers" :key="customer.customer_code" :value="customer.customer_code">{{ customer.customer_name }}</option></select></label><label>正式订单纸品<select v-model="pendingTargets[row.shipment_line_id]" :aria-label="row.shipment_line_id + ' 验收关联订单'" :disabled="busy || !pendingCustomers[row.shipment_line_id]" class="mt-1 w-full rounded border bg-white p-2"><option value="">选择正式订单纸品</option><option v-for="target in pendingFormalTargets(active.lines[index]!)" :key="target.line.id" :value="target.line.id">{{ target.order.order_no }} · PO {{ target.order.customer_po || '未填' }} · {{ target.line.packaging_type }} · {{ target.line.paper_quality }} · {{ target.line.specification }} {{ target.line.dimension_unit }} · 待送 {{ target.line.remaining_to_ship }} {{ target.line.unit }}</option></select></label><label class="sm:col-span-2">关联原因<input v-model="pendingReasons[row.shipment_line_id]" :aria-label="row.shipment_line_id + ' 验收关联原因'" :disabled="busy" class="mt-1 w-full rounded border p-2" placeholder="核对原送货与正式订单的依据（至少四字）"></label></div><button type="button" :aria-label="row.shipment_line_id + ' 验收确认关联'" :disabled="busy || !pendingTargets[row.shipment_line_id]" class="mt-2 rounded border border-teal-300 px-3 py-2 text-teal-800 disabled:opacity-40" @click="linkPending(active, active.lines[index]!)">确认关联正式订单，继续验收</button></div><label class="mt-2 block">无单处理结论<select v-model="row.no_order_decision" :aria-label="`${row.shipment_line_id} 无单处理结论`" :disabled="busy || Number(row.received_quantity) === 0" class="ml-2 rounded border bg-white p-2" @change="setNoOrderDecision(index)"><option value="">请选择</option><option value="SAMPLE">确需入库样板箱</option><option value="GIFT">免费赠送</option><option value="WRONG_DELIVERY">送错货，拒收</option></select></label><div v-if="row.no_order_decision === 'SAMPLE' || row.no_order_decision === 'GIFT'" class="mt-2 grid gap-2 sm:grid-cols-3"><label>归属客户<select v-model="row.customer_code" :aria-label="`${row.shipment_line_id} 样板箱客户`" :disabled="busy" required class="mt-1 w-full rounded border bg-white p-2"><option value="">请选择客户</option><option v-for="customer in customers" :key="customer.customer_code" :value="customer.customer_code">{{ customer.customer_name }} · {{ customer.customer_code }}</option></select></label><label>用途（选填）<input v-model="row.sample_purpose" :aria-label="`${row.shipment_line_id} 样板箱用途`" :disabled="busy" class="mt-1 w-full rounded border p-2" placeholder="例如客户打板确认（选填）"></label><label>需求人{{ row.no_order_decision === 'GIFT' ? '（选填）' : '' }}<input v-model="row.requested_by" :aria-label="`${row.shipment_line_id} 样板箱需求人`" :disabled="busy" :required="row.no_order_decision === 'SAMPLE'" class="mt-1 w-full rounded border p-2"></label><label>收料单位<select v-model="row.unit" :aria-label="`${row.shipment_line_id} 样板箱单位`" :disabled="busy" required class="mt-1 w-full rounded border bg-white p-2"><option value="个">个</option><option value="张">张</option></select></label></div><p v-if="row.no_order_decision === 'WRONG_DELIVERY'" class="mt-2 text-amber-900">把实际到货数量填在下方，拒收数量须等于实收，并写明送错原因；不会入库或参与月结。</p></div><div class="mt-2 flex gap-2"><button type="button" :disabled="busy" class="rounded border border-amber-200 px-2 py-1 text-xs text-amber-800" @click="markNotReceived(index)">此项未到</button><button type="button" :disabled="busy" class="rounded border border-teal-200 px-2 py-1 text-xs text-teal-800" @click="markAsDelivered(index)">按剩余量恢复</button></div><div class="mt-3 grid gap-3 sm:grid-cols-4"><label class="text-sm">实际收到<input v-model.number="row.received_quantity" :aria-label="`${row.shipment_line_id} 实收`" :disabled="busy" type="number" min="0" step="0.0001" :max="receivable(active.lines[index])" required class="mt-1 w-full rounded border p-2"></label><label class="text-sm">破损<input v-model.number="row.damaged_quantity" :aria-label="`${row.shipment_line_id} 破损`" :disabled="busy" type="number" min="0" step="0.0001" class="mt-1 w-full rounded border p-2"></label><label class="text-sm">拒收<input v-model.number="row.rejected_quantity" :aria-label="`${row.shipment_line_id} 拒收`" :disabled="busy" type="number" min="0" step="0.0001" class="mt-1 w-full rounded border p-2"></label><label class="text-sm">其他不可用<input v-model.number="row.unusable_quantity" :aria-label="`${row.shipment_line_id} 其他不可用`" :disabled="busy" type="number" min="0" step="0.0001" class="mt-1 w-full rounded border p-2"></label><label class="text-sm">纸品类型<input :value="active.lines[index]?.packaging_type || '未填写'" :aria-label="`${row.shipment_line_id} 纸品类型`" readonly :disabled="busy" class="mt-1 w-full rounded border p-2"></label><label class="text-sm">纸质<input v-model="row.paper_quality" :aria-label="`${row.shipment_line_id} 纸质`" placeholder="未填写" :disabled="busy || Boolean(active.lines[index]?.paper_quality)" class="mt-1 w-full rounded border p-2"></label><label class="text-sm">规格<input v-model="row.specification" :aria-label="`${row.shipment_line_id} 规格`" placeholder="未填写" :disabled="busy || Boolean(active.lines[index]?.specification)" class="mt-1 w-full rounded border p-2"></label><label class="text-sm">入库单价 {{ active.lines[index]?.currency }}<input v-model.number="row.unit_price" :aria-label="`${row.shipment_line_id} 入库单价`" :disabled="busy" type="number" min="0" step="0.000001" required class="mt-1 w-full rounded border p-2"><span v-if="Number(active.lines[index]?.delivery_unit_price) > 0 && (active.lines[index]?.currency ?? 'CNY').toUpperCase() === 'CNY'" class="mt-1 block text-xs text-slate-500">已带入送货单单价</span><span v-if="Number(active.lines[index]?.delivery_unit_price) > 0 && (active.lines[index]?.currency ?? 'CNY').toUpperCase() === 'CNY' && Number(active.lines[index]?.unit_price) > 0 && Number(active.lines[index]?.delivery_unit_price) !== Number(active.lines[index]?.unit_price)" class="mt-1 block text-xs text-amber-700">送货单 CNY {{ active.lines[index]?.delivery_unit_price }} · 采购单 CNY {{ active.lines[index]?.unit_price }}，请核对</span><span v-if="Number(active.lines[index]?.delivery_unit_price) > 0 && (active.lines[index]?.currency ?? 'CNY').toUpperCase() !== 'CNY'" class="mt-1 block text-xs text-amber-700">送货单价按 CNY 识别；采购单为 {{ active.lines[index]?.currency }}，已带采购单价，请核对</span></label><label v-if="Number(row.unit_price) === 0" class="text-xs text-amber-800">零价处理<select v-model="row.zero_price_kind" :aria-label="row.shipment_line_id + ' 零价处理'" :disabled="busy || row.no_order_decision === 'GIFT'" class="mt-1 block w-full rounded border p-2"><option value="PENDING">暂未定价 · 后续核价</option><option value="FREE">免费赠送 · 应付 0</option></select></label><label class="text-sm sm:col-span-4">差异原因<input v-model="row.difference_reason" :disabled="busy" :required="differenceRequired(row, active.lines[index])" :aria-label="`${row.shipment_line_id} 差异原因`" class="mt-1 w-full rounded border p-2"></label></div><p class="my-2 font-semibold text-teal-700">有效入库 {{ effective(row) }} {{ active.lines[index]?.unit }}</p><CartonReceiptAllocations v-model="row.location_allocations" :effective="effective(row)" :locations="locations" :factory-id="factory" :disabled="busy" @created="load" /></article><div v-if="receiptOptions.length" class="my-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"><p>发现相同纸品和数量的已入库记录。后补凭证请关联原收料，避免重复入库。</p><button type="button" class="mt-2 rounded border bg-white px-3 py-2" :disabled="busy" @click="openReceiptLink(active!)">关联已入库记录</button><label class="mt-3 flex items-center gap-2"><input v-model="newDeliveryConfirmed" type="checkbox" :disabled="busy">我已核对，这是新一批实际到货</label></div><p v-if="candidateLoading" class="my-3 text-sm text-slate-500">正在检查原收料记录…</p><p v-if="candidateError" role="alert" class="my-3 text-red-700">原收料检查失败：{{ candidateError }}<button type="button" class="ml-2 underline" @click="checkReceipts(active!)">重试</button></p><p v-if="error" role="alert" class="my-3 text-red-700">{{ error }}</p><div class="mt-4 flex justify-end gap-3"><button type="button" :disabled="busy" class="rounded border px-4 py-2" @click="closeReceiptDialog">取消</button><button :disabled="busy || candidateLoading || Boolean(candidateError) || (receiptOptions.length > 0 && !newDeliveryConfirmed && received.some(row => Number(row.received_quantity) > 0))" class="rounded bg-teal-700 px-4 py-2 text-white">{{ busy ? '正在保存…' : received.every(row => Number(row.received_quantity) === 0) ? remainingAction === 'WAIT' ? '暂未到货，继续待收' : '确认未收余货不再送' : '确认本次收料并入库' }}</button></div></form></div>

    <div v-if="statusActive" class="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/45 p-4">
      <form role="dialog" aria-modal="true" :aria-label="statusAction === 'defer' ? '记录暂未到货' : '更正未到货反馈'" class="w-full max-w-xl rounded-xl bg-white p-5" @submit.prevent="confirmStatusChange">
        <h3 class="font-bold">{{ statusAction === 'defer' ? '暂未到货，继续待收' : '更正未到货，重新待收' }} · {{ statusActive.delivery_note_no }}</h3>
        <p class="mt-3 text-sm text-amber-800">{{ statusAction === 'defer' ? '适用于尚未到达、仍会继续送达的整张送货单。保留在途数量，不终结送货单，也不生成入库。' : '适用于误确认整单未收到的更正。原记录继续保留，重新保护在途数量；订单版本或剩余需求已变化时需先核对。' }}</p>
        <label class="mt-4 block text-sm">原因<textarea v-model="statusReason" :disabled="busy" required minlength="4" maxlength="1000" aria-label="未到货处理原因" class="mt-1 w-full rounded border p-2" /></label>
        <p v-if="error" role="alert" class="mt-3 text-red-700">{{ error }}</p>
        <div class="mt-4 flex justify-end gap-2"><button type="button" :disabled="busy" class="rounded border px-4 py-2" @click="statusActive = null">取消</button><button :disabled="busy || statusReason.trim().length < 4" class="rounded bg-teal-700 px-4 py-2 text-white disabled:opacity-40">{{ busy ? '正在保存…' : '确认保存' }}</button></div>
      </form>
    </div>
    <div v-if="linkActive" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 p-4">
      <form aria-label="关联已入库记录" class="max-h-[90vh] w-full max-w-3xl overflow-auto rounded-xl bg-white p-5" @submit.prevent="confirmReceiptLink">
        <header class="flex items-center justify-between gap-3"><h3 class="font-bold">关联已入库记录 · {{ linkActive.delivery_note_no }}</h3><button type="button" :disabled="busy" @click="closeReceiptDialog">关闭</button></header>
        <p class="mt-3 rounded-lg bg-teal-50 p-3 text-sm text-teal-900">确认本送货单为原收料的后补凭证。仅关联整张已入库记录，数量、价格、仓位和原验收日期保持原记录，库存与月结只记一次。</p>
        <p v-if="candidateLoading" class="mt-3 text-sm">正在查找原收料记录…</p>
        <p v-else-if="candidateError" role="alert" class="mt-3 text-red-700">{{ candidateError }} <button type="button" class="underline" @click="checkReceipts(linkActive!)">重试</button></p>
        <p v-else-if="!receiptOptions.length" class="mt-3 rounded bg-amber-50 p-3 text-sm text-amber-900">没有可关联的原收料。仅支持同厂区、供应商、整单纸品和数量一致的已入库记录；已关联、补单及拆分多张收料须人工核对。后补单上传后原收料被冲销，可关联原冲销凭证，再进入更正验收。</p>
        <label v-for="receipt in receiptOptions" :key="receipt.id" class="mt-3 block rounded-lg border p-3" :class="receiptChoice === receipt.id ? 'border-teal-500 bg-teal-50' : 'border-slate-200'">
          <span class="flex items-center gap-2"><input v-model="receiptChoice" :value="receipt.id" type="radio" name="original-receipt" :disabled="busy || receipt.already_linked" :aria-label="`选择原收料 ${receipt.receipt_no}`"><b>{{ receipt.receipt_no }}</b><span v-if="receipt.already_linked" class="text-xs text-amber-800">已关联其他送货单，不能再次关联</span><span v-if="receipt.status === 'REVERSED'" class="text-xs font-semibold text-amber-800">原收料已冲销 · 关联后须更正验收</span></span>
          <span class="mt-1 block text-xs text-slate-600">原送货单 {{ receipt.delivery_note_no }} · 原验收日期 {{ receipt.acceptance_date || '未记录' }}</span>
          <span v-for="line in receipt.lines" :key="line.order_line_id" class="mt-2 block text-sm">{{ line.contract_no }} · {{ line.item_no }} · 纸品类型：{{ line.packaging_type || '未填写' }} · 纸质：{{ line.paper_quality || '未填写' }} · 规格：{{ line.specification || '未填写' }} · 实收 {{ line.received_quantity }} / 有效 {{ line.effective_quantity }} {{ line.unit }} · 原单价 {{ line.currency }} {{ line.unit_price }}</span>
        </label>
        <label class="mt-4 block text-sm">关联原因<input v-model="receiptLinkReason" aria-label="后补凭证关联原因" :disabled="busy" minlength="4" maxlength="1000" required class="mt-1 w-full rounded border p-2" placeholder="例如已手动入库，供应商后补原送货单"></label>
        <p v-if="error" role="alert" class="mt-3 text-red-700">{{ error }}</p>
        <footer class="mt-4 flex justify-end gap-2"><button type="button" :disabled="busy" class="rounded border px-4 py-2" @click="closeReceiptDialog">取消</button><button :disabled="busy || candidateLoading || Boolean(candidateError) || !receiptChoice || receiptLinkReason.trim().length < 4" class="rounded bg-teal-700 px-4 py-2 text-white disabled:opacity-40">{{ busy ? '正在关联…' : '确认关联，不重复入库' }}</button></footer>
      </form>
    </div>
  </section>
</template>
