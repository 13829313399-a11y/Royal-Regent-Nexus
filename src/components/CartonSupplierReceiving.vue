<script setup lang="ts">
import { cartonUnifiedDeliveriesApi, toPortalShipment, type UnifiedDelivery } from '@/api/cartonUnifiedDeliveries'
import CartonUnifiedDeliveryNotes from '@/components/CartonUnifiedDeliveryNotes.vue'
import { cartonDimensionParts } from '@/lib/cartonDimensions'
import { originalSupplierReceiptPrice, supplierReceiptPrice } from '@/features/carton-procurement/supplierReceiptPrice'
import { computed, nextTick, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
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
import CartonMobileReceiptTotals from '@/features/carton-procurement/CartonMobileReceiptTotals.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { Button } from '@/components/ui/button'
import { shipmentNeedsReceipt, shipmentReceiptDisplay } from '@/features/carton-procurement/receiptDisplay'
import { emptyShipmentFilters, filterShipments } from '@/features/carton-procurement/queryFilters'
import { isSupplierOrderSource, supplierOrderPapers, supplierPaperCompatible, type SupplierOrderSource } from '@/features/carton-procurement/supplierOrderSource'
const props = defineProps<{ factoryId?: string; shipmentId?: string; receiptEntryPapers?: Record<string, string[]>; responsibilityScope?: 'OWN' | 'ALL'; search?: string; hideSearch?: boolean; mobile?: boolean }>()
const emit = defineEmits<{ changed: []; reverse: [receiptId: string]; 'create-order': [source: SupplierOrderSource]; 'update:search': [value: string]; 'clear-focus': [] }>()
const route = useRoute(); const app = useAppStore(); const auth = useAuthStore()
const factory = computed(() => String(props.factoryId || route.query.factory || app.activeProductionFactory.id))
const data = ref<PortalWorkspace | null>(null); const locations = ref<CartonLocation[]>([]); const customers = ref<CartonCustomerResponse[]>([])
const unifiedGroups = ref<UnifiedDelivery[]>([]), workshops = ref<{ id: string; name: string }[]>([])
const unifiedMap = computed(() => new Map(unifiedGroups.value.filter(group => !group.id.startsWith('FORMAL:')).map(group => [group.id, group])))
const formalReopenMap = computed(() => new Map(unifiedGroups.value.flatMap(group => group.id.startsWith('FORMAL:') && group.formal ? [[group.formal.id, group] as const] : [])))
const receivingViewerKey = computed(() => JSON.stringify([auth.currentUser?.id, auth.authorizationVersion, auth.authzMode, auth.currentUser?.identity?.effective_context_key, auth.currentUser?.identity?.employment_epoch]))
const error = ref(''); const message = ref(''); const busy = ref(false); const loading = ref(false)
const supportReady = ref(false), supportLoading = ref(false), supportError = ref('')
const primaryReadReady = ref(false)
const operationsReady = computed(() => primaryReadReady.value && supportReady.value)
type ReceiptDraftLine = Omit<ReceiveLine, 'received_quantity'> & { received_quantity: number | '' }
const active = ref<PortalShipment | null>(null); const received = ref<ReceiptDraftLine[]>([])
const receiptForm = ref<HTMLFormElement | null>(null)
const focusedPaperIds = shallowRef<string[] | null>(null)
const expandedOrderSources = ref<Record<string, boolean>>({})
const splitConfirmation = ref('')
const correctionReason = ref('')
const remainingAction = ref<'WAIT' | 'CLOSE'>('WAIT')
const closeReason = ref('')
const receivable = (line?: ShipmentLine) => Number(line?.receivable_quantity ?? line?.remaining_quantity ?? line?.quantity ?? 0)
const focusedPaperAvailable = computed(() => !focusedPaperIds.value || active.value?.lines.some(line =>
  focusedPaperIds.value?.includes(line.id) && receivable(line) > 0))
const displayQuantity = (value: unknown) => {
  const number = Number(value ?? 0)
  return Number.isFinite(number) ? number.toLocaleString('zh-CN', { maximumFractionDigits: 4 }) : String(value ?? '')
}
const differenceRequired = (row: ReceiptDraftLine) => effective(row) !== Number(row.received_quantity)
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
  if (!operationsReady.value || !canReceive.value || shipment.can_operate === false || busy.value) return
  if (active.value?.id === shipment.id) suspendedReceiptDraft = captureReceiptDraft(shipment)
  active.value = null; linkActive.value = shipment; receiptChoice.value = ''; receiptLinkReason.value = ''; error.value = ''
  void checkReceipts(shipment)
}
async function confirmReceiptLink() {
  const shipment = linkActive.value, receipt = receiptOptions.value.find(row => row.id === receiptChoice.value && !row.already_linked)
  if (!operationsReady.value || !canReceive.value || busy.value || candidateLoading.value || candidateError.value || !shipment) return
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
  if (!operationsReady.value || !shipment || busy.value || !canReceive.value) return
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
const awaitingReceipt = shipmentNeedsReceipt
const splitLines = computed(() => received.value.flatMap((line, index) => {
  if (focusedPaperIds.value && !focusedPaperIds.value.includes(line.shipment_line_id)) return []
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
const shipmentView = ref<'PENDING' | 'HISTORY' | 'ALL'>('PENDING')
const shipmentViews = [{ value: 'PENDING', label: '待收货' }, { value: 'HISTORY', label: '已处理' }, { value: 'ALL', label: '全部' }] as const
const shipmentFilters = ref(emptyShipmentFilters())
const reopenedShipment = shallowRef<{ id: string; number: string; quantities: string } | null>(null)
const focusedReopenedShipmentId = ref('')
const reopenNotice = ref<HTMLDivElement | null>(null)
const shipmentList = ref<HTMLElement | null>(null)
watch(() => props.search, value => { if (value !== undefined && value !== shipmentFilters.value.search) shipmentFilters.value.search = value }, { immediate: true })
watch(() => shipmentFilters.value.search, value => { if (props.search !== undefined && value !== props.search) emit('update:search', value) })
function resolveShipmentId(id: string) {
  const original = id.startsWith('FORMAL:') ? id.slice(7) : id
  return [...unifiedMap.value.values()].find(group => group.id === id || group.formal?.id === original
    || group.special.some(request => request.shipments.some(shipment => shipment.id === original)))?.id || original
}
const requestedShipmentId = computed(() => resolveShipmentId(props.shipmentId || (typeof route.query.shipment === 'string' ? route.query.shipment : '')))
const requestedShipmentIds = computed(() => new Set([requestedShipmentId.value, ...(typeof route.query.shipment_ids === 'string' ? route.query.shipment_ids.split(',').map(resolveShipmentId) : [])].filter(Boolean)))
const entryPapers = computed(() => new Map(Object.entries(props.receiptEntryPapers ?? {}).map(([id, papers]) => [resolveShipmentId(id), papers])))
const chosenReceiptShipment = ref('')
const unifiedReceiptBusy = ref(false)
const chooseReceiptShipment = computed(() => !requestedShipmentId.value && requestedShipmentIds.value.size > 1)
const receiptShipmentId = computed(() => requestedShipmentId.value || (chooseReceiptShipment.value
  ? chosenReceiptShipment.value : [...requestedShipmentIds.value][0] || ''))
const filteredShipments = computed(() => {
  const shipments = data.value?.shipments ?? []
  if (requestedShipmentIds.value.size) return shipments.filter(row => requestedShipmentIds.value.has(row.id))
  return filterShipments(shipments, { ...shipmentFilters.value, status: '' })
})
const shipmentCounts = computed(() => {
  const pending = filteredShipments.value.filter(awaitingReceipt).length
  return { PENDING: pending, HISTORY: filteredShipments.value.length - pending, ALL: filteredShipments.value.length }
})
const visibleShipments = computed(() => {
  const focusedId = focusedReopenedShipmentId.value
  if (focusedId) return data.value?.shipments.filter(shipment => shipment.id === focusedId) ?? []
  return filteredShipments.value.filter(shipment =>
    chooseReceiptShipment.value ? shipment.id === chosenReceiptShipment.value
      : requestedShipmentIds.value.size || shipmentView.value === 'ALL' || (shipmentView.value === 'PENDING' ? awaitingReceipt(shipment) : !awaitingReceipt(shipment)))
})
const closedAssociationShipments = computed(() => canRead.value && canReceive.value ? visibleShipments.value
  .filter(shipment => shipment.can_operate !== false)
  .map(shipment => unifiedMap.value.get(shipment.id)?.formal || shipment)
  .filter(shipment => shipment.status === 'NOT_RECEIVED' && shipment.lines.some(line => line.source_type === 'AD_HOC_REVIEW' && line.closed_source_linkable)) : [])
watch(factory, () => { shipmentFilters.value = emptyShipmentFilters() })
const linkTargets = ref<Record<string, string>>({}); const linkReasons = ref<Record<string, string>>({})
let generation = 0
let scopeGeneration = 0
let suspendedReceiptDraft: ReceiptDraft | null = null
let openedDeepLinkKey = ''
function openDeepLinkedShipment() {
  const shipmentId = receiptShipmentId.value
  const key = `${factory.value}:${shipmentId}`
  if (!shipmentId || openedDeepLinkKey === key || !data.value) return
  if (canReceive.value && !operationsReady.value) return
  const shipment = data.value.shipments.find(row => row.id === shipmentId)
  if (!shipment) { error.value = '未找到当前权限内的原送货单，请核对厂区、客户责任范围及原单。'; return }
  openedDeepLinkKey = key
  shipmentView.value = awaitingReceipt(shipment) ? 'PENDING' : 'HISTORY'
  if (!unifiedMap.value.has(shipment.id) && awaitingReceipt(shipment) && canReceive.value) start(shipment)
}
function failure(reason: unknown) { error.value = getApiErrorMessage(reason) }
async function load() {
  if (!canRead.value) return false
  const token = ++generation, scope = factory.value; loading.value = true
  const current = () => token === generation && scope === factory.value
  primaryReadReady.value = false; supportReady.value = false; supportLoading.value = true; supportError.value = ''
  let primaryReady = false
  const support = Promise.all([
    canReceive.value ? cartonPositionsApi.locations(scope) : Promise.resolve([]),
    canReceive.value ? cartonProcurementApi.listCustomers(scope, false) : Promise.resolve([]),
  ]).then(([bins, activeCustomers]) => {
    if (!current()) return
    locations.value = bins; customers.value = activeCustomers; supportReady.value = true
    if (primaryReady) openDeepLinkedShipment()
  }).catch(reason => {
    if (current()) supportError.value = getApiErrorMessage(reason)
  }).finally(() => { if (current()) supportLoading.value = false })
  try {
    const [workspace, unified] = await Promise.all([api.workspace(scope, true, props.responsibilityScope ?? 'OWN'), canReceive.value ? cartonUnifiedDeliveriesApi.list(scope) : Promise.resolve({ items: [], options: { workshops: [] } })])
    if (!current()) return false
    unifiedGroups.value = unified.items; workshops.value = unified.options?.workshops || []
    const grouped = [...unifiedMap.value.values()]
    const groupedFormal = new Set(grouped.flatMap(group => group.formal ? [group.formal.id] : []))
    data.value = { ...workspace, shipments: [...workspace.shipments.filter(row => !groupedFormal.has(row.id)), ...grouped.map(toPortalShipment)] }
    primaryReady = true; primaryReadReady.value = true; error.value = ''; loading.value = false
    if (supportReady.value) openDeepLinkedShipment()
    await support
    return current() && supportReady.value
  } catch (reason) { if (current()) failure(reason); return false } finally { if (current()) loading.value = false }
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
  active.value = null; linkActive.value = null; received.value = []; focusedPaperIds.value = null
  receiptOptions.value = []; receiptChoice.value = ''; receiptLinkReason.value = ''
  candidateGeneration++; candidateLoading.value = false; candidateError.value = ''
  data.value = null; unifiedGroups.value = []; workshops.value = []; locations.value = []; customers.value = []
  linkTargets.value = {}; linkReasons.value = {}; pendingCustomers.value = {}; pendingTargets.value = {}; pendingReasons.value = {}
  splitConfirmation.value = ''; correctionReason.value = ''; newDeliveryConfirmed.value = false
  openedDeepLinkKey = ''; chosenReceiptShipment.value = ''; unifiedReceiptBusy.value = false; error.value = ''; message.value = ''; busy.value = false; loading.value = false
  reopenedShipment.value = null; focusedReopenedShipmentId.value = ''
  statusActive.value = null; statusReason.value = ''; shipmentView.value = 'PENDING'; acceptanceDate.value = new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
  generation++; scopeGeneration++
  suspendedReceiptDraft = null
  if (canRead.value) void load()
}, { immediate: true })
defineExpose({ refresh: load, resumeOrderSource, saving: computed(() => busy.value || unifiedReceiptBusy.value) })
onBeforeUnmount(() => { generation++; scopeGeneration++; candidateGeneration++; suspendedReceiptDraft = null })
watch([() => [...requestedShipmentIds.value].join(','), () => props.receiptEntryPapers], () => {
  focusedReopenedShipmentId.value = ''
  chosenReceiptShipment.value = ''
  openedDeepLinkKey = ''
  openDeepLinkedShipment()
})
function focusReceivingTarget(target?: HTMLElement | null) {
  target?.focus({ preventScroll: true })
  target?.scrollIntoView?.({ block: 'start' })
}
function recordReopenedShipment(shipment: PortalShipment, quantities: string) {
  const result = { id: shipment.id, number: shipment.delivery_note_no, quantities }
  message.value = ''
  reopenedShipment.value = result
  void nextTick(() => {
    if (reopenedShipment.value === result) focusReceivingTarget(reopenNotice.value)
  })
}
async function viewReopenedShipment() {
  const result = reopenedShipment.value
  if (!result || !canRead.value || loading.value || busy.value || unifiedReceiptBusy.value) return
  if (!primaryReadReady.value) await load()
  if (reopenedShipment.value !== result || !primaryReadReady.value) return
  const id = resolveShipmentId(result.id)
  const shipment = data.value?.shipments.find(row => row.id === id)
  if (!shipment) { error.value = '未找到这张原送货单，请刷新后核对。'; return }
  shipmentView.value = awaitingReceipt(shipment) ? 'PENDING' : 'HISTORY'
  focusedReopenedShipmentId.value = id
  await nextTick()
  if (focusedReopenedShipmentId.value === id) focusReceivingTarget(shipmentList.value?.querySelector<HTMLElement>('[data-receiving-note-id]'))
}
async function returnToShipmentList() {
  focusedReopenedShipmentId.value = ''
  await nextTick()
  focusReceivingTarget(reopenNotice.value)
}
function selectReceiptShipment(id: string) {
  if (busy.value || unifiedReceiptBusy.value) return
  chosenReceiptShipment.value = id
  openedDeepLinkKey = ''
  if (id) openDeepLinkedShipment()
}
function focusReceiptPapers(shipment: PortalShipment) {
  const papers = entryPapers.value.get(shipment.id)
  focusedPaperIds.value = papers ?? null
  if (!papers) return
  remainingAction.value = 'WAIT'
  received.value = received.value.map((row, index) => papers.includes(row.shipment_line_id) ? row
    : receiptRow(shipment.lines[index]!))
  void nextTick(() => {
    if (active.value?.id !== shipment.id || focusedPaperIds.value !== papers) return
    const field = receiptForm.value?.querySelector<HTMLElement>('[data-receipt-entry-focus], [data-receipt-entry-waiting]')
    field?.focus()
    field?.scrollIntoView?.({ block: 'nearest' })
  })
}
function showWholeReceipt() {
  focusedPaperIds.value = null
}
function start(shipment: PortalShipment, restoringDraft = false) {
  if ((!operationsReady.value && !restoringDraft) || !canReceive.value || shipment.can_operate === false) return
  if (shipment.requires_receipt_link) { openReceiptLink(shipment); return }
  const savedDraft = suspendedReceiptDraft
  if (savedDraft?.shipment.id === shipment.id && savedDraft.factoryId === factory.value && savedDraft.scope === scopeGeneration) {
    suspendedReceiptDraft = null
    restoreReceiptDraft(shipment, savedDraft)
    return
  }
  linkActive.value = null
  expandedOrderSources.value = {}
  if (!shipment.requires_correction) void checkReceipts(shipment)
  else { candidateGeneration++; receiptOptions.value = []; candidateError.value = ''; candidateLoading.value = false }
  splitConfirmation.value = ''
  correctionReason.value = ''
  remainingAction.value = 'WAIT'
  closeReason.value = ''
  active.value = shipment; error.value = ''
  received.value = shipment.lines.map(line => {
    const original = legacyCorrection(line.id, shipment)
    const draft = receiptRow(line)
    return original ? { ...draft, ...original, ...supplierReceiptPrice(line, original.no_order_decision === 'GIFT'), received_quantity: draft.received_quantity, close_remaining: false, location_allocations: [] } : draft
  })
  focusReceiptPapers(shipment)
  if (props.mobile && !focusedPaperIds.value) void nextTick(() => {
    if (active.value?.id !== shipment.id) return
    receiptForm.value?.focus({ preventScroll: true })
    receiptForm.value?.querySelector('[data-mobile-first-paper]')?.scrollIntoView?.({ block: 'nearest', behavior: 'instant' })
  })
}
function legacyCorrection(lineId: string, shipment = active.value) {
  if (!shipment?.requires_correction || shipment.receipt_status !== 'REVERSED') return undefined
  return shipment.legacy_correction_lines?.find(row => row.shipment_line_id === lineId && ['SAMPLE', 'MISC', 'GIFT', 'UNORDERED'].includes(row.no_order_decision || ''))
}
const legacyLabel = (decision?: string) => decision === 'MISC' ? '原杂单 · 冲销更正' : decision === 'SAMPLE' ? '原样板箱 · 冲销更正' : decision === 'GIFT' ? '原免费赠送 · 冲销更正' : '原无落单收料 · 冲销更正'
function receiptRow(line: ShipmentLine): ReceiptDraftLine {
  return { shipment_line_id: line.id, received_quantity: receivable(line) > 0 ? '' : 0, damaged_quantity: 0, rejected_quantity: 0, unusable_quantity: 0,
    ...supplierReceiptPrice(line), paper_quality: line.paper_quality, specification: line.specification, location_allocations: [], difference_reason: '',
    dimension_unit: cartonDimensionParts(line.specification, line.dimension_unit).unit === 'in' || line.dimension_unit === 'inch' ? 'in' : 'cm',
    no_order_decision: '', customer_code: '', sample_purpose: '', requested_by: '', workshop_id: '', unit: line.unit, ...line.receipt_classification, ...supplierReceiptPrice(line, line.receipt_classification?.no_order_decision === 'GIFT') }
}
interface ReceiptDraft {
  factoryId: string
  scope: number
  shipment: PortalShipment
  sourceLineId?: string
  rows: Map<string, ReceiptDraftLine>
  acceptanceDate: string
  correctionReason: string
  remainingAction: 'WAIT' | 'CLOSE'
  closeReason: string
  splitConfirmation: string
  newDeliveryConfirmed: boolean
}
const sourceKey = (line: ShipmentLine) => line.original_unmatched_line_id || line.id
const copyReceiptRow = (row: ReceiptDraftLine): ReceiptDraftLine => ({ ...row, location_allocations: row.location_allocations.map(part => ({ ...part })) })
function captureReceiptDraft(shipment: PortalShipment): ReceiptDraft {
  const current = active.value?.id === shipment.id
  const previous = suspendedReceiptDraft
  if (!current && previous?.factoryId === factory.value && previous.scope === scopeGeneration && previous.shipment.id === shipment.id) {
    return { ...previous, shipment, rows: new Map([...previous.rows].map(([key, row]) => [key, copyReceiptRow(row)])) }
  }
  return { factoryId: factory.value, scope: scopeGeneration, shipment,
    rows: new Map(shipment.lines.map((line, index) => [sourceKey(line), copyReceiptRow(current && received.value[index] ? received.value[index]! : receiptRow(line))])),
    remainingAction: remainingAction.value, closeReason: current ? closeReason.value : '', acceptanceDate: acceptanceDate.value, correctionReason: current ? correctionReason.value : '',
    splitConfirmation: current ? splitConfirmation.value : '', newDeliveryConfirmed: current && newDeliveryConfirmed.value }
}
function restoreReceiptDraft(shipment: PortalShipment, draft?: ReceiptDraft | null, changedAssociation = false) {
  const validDraft = draft?.factoryId === factory.value && draft.scope === scopeGeneration && draft.shipment.id === shipment.id ? draft : null
  start(shipment, Boolean(validDraft))
  if (!active.value || active.value.id !== shipment.id || !validDraft) return
  received.value = shipment.lines.map(line => {
    const saved = validDraft.rows.get(sourceKey(line))
    if (!saved) return receiptRow(line)
    const row = { ...copyReceiptRow(saved), shipment_line_id: line.id }
    if (line.source_type !== 'AD_HOC_REVIEW') {
      row.no_order_decision = ''; row.customer_code = ''; row.sample_purpose = ''; row.requested_by = ''; row.workshop_id = ''
      row.unit = line.unit; row.paper_quality = line.paper_quality; row.specification = line.specification
    }
    return row
  })
  acceptanceDate.value = validDraft.acceptanceDate
  correctionReason.value = validDraft.correctionReason
  remainingAction.value = validDraft.remainingAction
  closeReason.value = validDraft.closeReason
  splitConfirmation.value = changedAssociation ? '' : validDraft.splitConfirmation
  newDeliveryConfirmed.value = changedAssociation ? false : validDraft.newDeliveryConfirmed
  focusReceiptPapers(shipment)
}
function createOrderFromShipment(shipment: PortalShipment, line: ShipmentLine) {
  if (!operationsReady.value) return
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
function markAsDelivered(index: number) {
  const row = received.value[index], shipped = active.value?.lines[index]
  if (!row || !shipped) return
  row.received_quantity = receivable(shipped)
  if (row.difference_reason === '货物尚未实际送到') row.difference_reason = ''
}
function setNoOrderDecision(index: number) {
  const row = received.value[index]
  if (!row) return
  if (row.no_order_decision === 'WRONG_DELIVERY') {
    row.rejected_quantity = Number(row.received_quantity)
    row.damaged_quantity = 0
    row.unusable_quantity = 0
    row.location_allocations = []
  } else {
    row.rejected_quantity = 0
  }
  Object.assign(row, supplierReceiptPrice(active.value?.lines[index] || {}, row.no_order_decision === 'GIFT'))
}
const effective = (line: ReceiptDraftLine) => Math.max(0, Math.round(
  (Number(line.received_quantity) - Number(line.damaged_quantity) - Number(line.rejected_quantity) - Number(line.unusable_quantity)) * 10000,
)) / 10000
const missingReceiptLocation = (line: ReceiptDraftLine) => effective(line) > 0
  && (!line.location_allocations.length || line.location_allocations.some(part => !part.location_id))
const receiptEntries = computed(() => received.value.flatMap((row, index) => {
  const source = active.value?.lines[index]
  const original = receivable(source)
  if (!source || original <= 0 || (focusedPaperIds.value && !focusedPaperIds.value.includes(row.shipment_line_id))) return []
  const [actual, damaged, rejected, unusable] = [Number(row.received_quantity), Number(row.damaged_quantity), Number(row.rejected_quantity), Number(row.unusable_quantity)] as const
  const quantityValid = [actual, damaged, rejected, unusable].every(value => Number.isFinite(value) && value >= 0
    && Math.abs(value * 10000 - Math.round(value * 10000)) <= 0.000001)
    && actual <= original && Math.round((actual - damaged - rejected - unusable) * 10000) >= 0
  return [{ row, source, entered: row.received_quantity !== '', quantityValid, remaining: original - actual,
    closing: remainingAction.value === 'CLOSE' || Boolean(row.close_remaining) }]
}))
const closingShortfall = computed(() => receiptEntries.value.some(entry => entry.closing))
const receiptSummary = computed(() => receiptEntries.value.filter(entry => entry.entered || entry.closing))
const mobileReceiptTotals = computed(() => receiptEntries.value.map(entry => ({
  unit: entry.source.unit,
  inbound: entry.quantityValid && entry.entered ? effective(entry.row) : 0,
  remaining: entry.quantityValid && entry.entered ? entry.closing ? 0 : entry.remaining : receivable(entry.source),
})))
const receiptProblem = computed(() => {
  const entries = receiptEntries.value
  if (entries.some(entry => entry.closing && !entry.entered)) return '请填写结案纸品的本批实到数量。未到填写 0。'
  if (!entries.some(entry => entry.entered)) return '请填写本批实到数量。未到填写 0。'
  if (entries.some(entry => !entry.quantityValid)) return '请核对本批实到和差异数量。实到不能超过原单待收，差异合计不能超过实到。'
  if (closingShortfall.value && closeReason.value.trim().length < 4) return '短送结案须填写至少四字原因。'
  if (entries.some(entry => differenceRequired(entry.row) && entry.row.difference_reason.trim().length < 4
    && !(entry.closing && entry.remaining > 0))) {
    return '有破损、拒收或其他不可用数量时，请填写至少四字差异原因。'
  }
  return ''
})
const needsReceiptLocation = computed(() => receiptEntries.value.some(entry => entry.quantityValid && missingReceiptLocation(entry.row)))
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
  if (!operationsReady.value) return
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
      message.value = shipment.status === 'NOT_RECEIVED' ? '原送货行已关联正式订单；零到货关闭记录保留，请在原单逐行重开后核实到货。' : '原送货单已关联正式订单；验收草稿保留，请核对实际收到。'
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
  if (!operationsReady.value) return
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
  if (!operationsReady.value || !active.value || busy.value || !canReceive.value) return
  if (!focusedPaperAvailable.value) { error.value = '所选纸品须等当前原单更正完成后再收料。'; return }
  if (candidateLoading.value || candidateError.value) { error.value = '请先完成原收料重复检查；检查失败时点击重试'; return }
  error.value = ''
  if (receiptProblem.value) return
  if (!acceptanceDate.value) { error.value = '请填写实际验收日期。'; return }
  if (receiptOptions.value.length && !newDeliveryConfirmed.value && received.value.some(row => Number(row.received_quantity) > 0)) {
    error.value = '发现相同纸品和数量的原收料；请关联原记录，或核对本次确为新一批到货'; return
  }
  if (active.value.requires_correction && correctionReason.value.trim().length < 4) {
    error.value = '原收料已冲销，请填写至少四字更正原因'; return
  }
  const shipment = active.value
  const lines: ReceiveLine[] = []
  for (const [index, line] of received.value.entries()) {
    const source = shipment.lines[index]
    const actual = Number(line.received_quantity)
    if (source?.source_type === 'AD_HOC_REVIEW' && actual > 0) {
      const original = legacyCorrection(line.shipment_line_id)
      if (original && line.no_order_decision !== 'WRONG_DELIVERY' && (line.no_order_decision !== original.no_order_decision || line.customer_code !== original.customer_code || line.requested_by !== original.requested_by || (line.workshop_id || '') !== (original.workshop_id || ''))) { error.value = '冲销更正须保留原分类、客户与需求人'; return }
      if (!original && !['SAMPLE', 'MISC', 'GIFT', 'WRONG_DELIVERY'].includes(line.no_order_decision || '')) { error.value = '请选择样板单、杂单、免费赠送或送错货；正单请先补建或关联订单'; return }
      if (line.no_order_decision === 'GIFT' && Number(originalSupplierReceiptPrice(source)) > 0) { error.value = '供应商原单有收费价格，请先与供应商核实赠送，不能直接改为免费'; return }
      if (line.no_order_decision === 'WRONG_DELIVERY' && effective(line) !== 0) { error.value = '送错货的有效入库数量必须为 0'; return }
    }
    const quantity = effective(line)
    if (source?.material_correction_pending && quantity > 0) { error.value = '纸品资料更正待双方确认，请先处理更正，再刷新核实入库'; return }
    const allocations = quantity > 0 ? line.location_allocations : []
    if (quantity > 0) {
      if (missingReceiptLocation(line)) { error.value = '请选择有效入库纸品的仓位。'; return }
      if (allocations.some(part => !locations.value.some(location => location.id === part.location_id && location.status === 'ACTIVE') || !Number.isFinite(Number(part.quantity)) || Number(part.quantity) <= 0)) {
        error.value = '每条有效入库纸品必须选择有效仓位并填写分仓数量'; return
      }
      if (new Set(allocations.map(part => part.location_id)).size !== allocations.length || allocations.some(part => Math.abs(Number(part.quantity) * 10000 - Math.round(Number(part.quantity) * 10000)) > 0.000001) || Math.abs(allocations.reduce((sum, part) => sum + Number(part.quantity), 0) - quantity) > 0.000001) {
        error.value = '仓位不能重复，分仓数量最多四位小数，合计必须等于该纸品有效入库数量'; return
      }
    }
    const closing = (remainingAction.value === 'CLOSE' || line.close_remaining) && actual < receivable(source)
    const differenceReason = [line.difference_reason.trim(), closing ? closeReason.value.trim() : ''].filter(Boolean).join('；')
    if (differenceReason.length > 1000) {
      error.value = '差异说明与短送结案原因合计不能超过 1000 字。'; return
    }
    const decision = actual > 0 ? line.no_order_decision : ''
    const price = supplierReceiptPrice(source || {}, decision === 'GIFT')
    lines.push({ ...line, ...price, no_order_decision: decision, received_quantity: actual,
      damaged_quantity: Number(line.damaged_quantity), rejected_quantity: Number(line.rejected_quantity), unusable_quantity: Number(line.unusable_quantity),
      location_allocations: allocations, difference_reason: differenceReason })
  }
  busy.value = true
  const scope = factory.value, token = scopeGeneration
  const closesRemainder = receiptEntries.value.some(entry => entry.closing && entry.remaining > 0)
  try {
    const result = await api.receive(shipment.id, {
      remaining_action: remainingAction.value, factory_id: scope, expected_revision: shipment.revision,
      ...(newDeliveryConfirmed.value ? { new_delivery_confirmation: true } : {}), acceptance_date: acceptanceDate.value,
      lines, split_confirmation: splitConfirmation.value, correction_reason: correctionReason.value.trim(),
    })
    if (factory.value !== scope || token !== scopeGeneration) return
    active.value = null
    received.value = []
    message.value = closesRemainder ? '本批验收已保存。所选送货余量已结案，采购欠数保留。'
      : result.status === 'SENT' ? '本次收货已保存；余货继续留在原送货单待收。'
      : result.receipt_id ? '本次收货已入库；本送货单验收已结束。' : '仓库核实已保存；本单没有有效入库数量。'
    emit('changed')
    await load()
  } catch (reason) {
    if (scope === factory.value && token === scopeGeneration) failure(reason)
  } finally {
    if (scope === factory.value && token === scopeGeneration) busy.value = false
  }
}
</script>
<template>
  <section class="min-w-0 rounded-xl border border-slate-200 bg-white text-slate-800" :class="mobile ? 'p-3' : 'p-4 sm:p-5'" aria-label="供应商收货工作区">
    <header v-if="!mobile" class="mb-4"><h2 class="text-base font-bold">供应商发货待收</h2><p class="mt-1 text-xs text-slate-500">{{ data?.supplier_name }} · 供应商确认送货后，仓库核实实际到货与仓位。</p></header>
    <label v-if="mobile && !requestedShipmentIds.size" class="mb-3 block">
      <span class="sr-only">搜索供应商送货单</span>
      <input v-model="shipmentFilters.search" type="search" placeholder="搜索送货单号、合同或货号" class="h-12 w-full rounded-xl border bg-white px-3 text-base">
    </label>
    <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
      <div role="group" aria-label="收货列表切换" class="flex flex-wrap gap-2">
        <button v-for="view in shipmentViews" v-show="!mobile || view.value !== 'ALL'" :key="view.value" type="button" :aria-label="`显示${view.label}送货单`" :aria-pressed="shipmentView === view.value" :disabled="!!requestedShipmentIds.size" class="rounded-lg border py-2 text-sm font-semibold disabled:cursor-not-allowed" :class="[mobile ? 'min-h-11 px-2.5' : 'min-h-10 px-4', shipmentView === view.value ? 'border-teal-700 bg-teal-700 text-white' : 'border-slate-200 bg-white text-slate-700 hover:bg-teal-50']" @click="focusedReopenedShipmentId = ''; shipmentView = view.value">{{ view.label }}（{{ loading || !data || error ? '—' : shipmentCounts[view.value] }} 张）</button>
      </div>
      <button type="button" :disabled="busy || loading" class="min-h-10 rounded-lg border bg-white px-3 py-2 text-xs disabled:opacity-50" @click="load">刷新</button>
    </div>
    <CartonShipmentFilters v-if="!mobile" v-show="!focusedReopenedShipmentId" v-model="shipmentFilters" hide-status :hide-search="hideSearch || search !== undefined" :rows="data?.shipments ?? []" />
    <p v-if="!focusedReopenedShipmentId && chooseReceiptShipment && !chosenReceiptShipment" class="mt-2 text-xs text-slate-500">有 {{ loading || !data || error ? '—' : filteredShipments.length }} 张原送货单待选择</p>
    <p v-else class="mt-2 text-xs text-slate-500">显示 {{ visibleShipments.length }} 张送货单<span v-if="shipmentView !== 'PENDING'"> · 已处理含收货结束、拒收或零到货关闭，具体情况以单据状态为准。</span></p>
    <div v-if="!focusedReopenedShipmentId && chooseReceiptShipment" class="mt-3 flex flex-wrap items-center gap-2" aria-label="选择本次到货的原送货单"><p class="text-xs font-semibold text-slate-700">选择本次到货的原送货单</p><template v-if="!chosenReceiptShipment"><button v-for="shipment in filteredShipments" :key="shipment.id" type="button" class="rounded border bg-white px-3 py-2 text-xs font-semibold" :disabled="!operationsReady || busy" @click="selectReceiptShipment(shipment.id)">{{ shipment.delivery_note_no }} · {{ shipment.delivery_date }}</button></template><button v-else type="button" class="rounded border bg-white px-3 py-2 text-xs" :disabled="busy || unifiedReceiptBusy" @click="selectReceiptShipment('')">重选送货单</button></div>
    <p v-if="focusedReopenedShipmentId" class="mt-2 flex flex-wrap items-center gap-3 text-xs text-teal-700">正在查看恢复待收的原送货单<button type="button" class="underline" :disabled="busy || unifiedReceiptBusy" @click="returnToShipmentList">返回送货单列表</button></p>
    <p v-else-if="requestedShipmentIds.size" class="mt-2 flex flex-wrap items-center gap-3 text-xs text-teal-700">正在查看链接对应的原送货记录<button type="button" class="underline" :disabled="busy || unifiedReceiptBusy" @click="emit('clear-focus')">查看全部送货单</button></p>
    <p v-if="loading" role="status" class="mb-3 text-sm text-slate-500">正在读取供应商送货单…</p>
    <p v-if="supportLoading" role="status" class="mb-3 text-sm text-slate-500">正在读取收料所需的客户和仓位资料…</p>
    <p v-else-if="supportError" role="alert" class="mb-3 rounded bg-amber-50 p-3 text-amber-900">收料资料读取失败：{{ supportError }}。核实操作暂不可用。<button type="button" class="ml-2 underline" @click="load">重试读取</button></p>
    <p v-if="error" role="alert" class="mb-4 rounded bg-red-50 p-3 text-red-700">{{ error }}</p><p v-if="message" role="status" class="mb-4 rounded bg-emerald-50 p-3 text-emerald-800">{{ message }}</p>
    <div v-if="reopenedShipment" ref="reopenNotice" tabindex="-1" class="mb-4 flex scroll-mt-36 flex-wrap items-center justify-between gap-3 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">
      <p role="status">送货单 {{ reopenedShipment.number }} 已恢复 {{ reopenedShipment.quantities }}为待收。到货后再验收。</p>
      <Button type="button" variant="outline" size="sm" :disabled="busy || unifiedReceiptBusy || loading" @click="viewReopenedShipment">查看这张待收单</Button>
    </div>
    <section v-for="shipment in closedAssociationShipments" :key="shipment.id" class="my-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs" :aria-label="`零到货原单 ${shipment.delivery_note_no} 补齐来源`">
      <strong>原送货单 {{ shipment.delivery_note_no }} · 零到货已关闭，待核实正式来源</strong>
      <p class="mt-1 text-amber-800">先明确关联有效正式纸品；原关闭记录保留，关联不恢复待收、不增加库存。供应商确认接单后，再在原单点“恢复原单待收”。</p>
      <div v-for="source in shipment.lines.filter(line => line.source_type === 'AD_HOC_REVIEW' && line.closed_source_linkable)" :key="source.id" class="mt-3 space-y-2">
        <p>{{ source.contract_no }} / {{ source.item_no }} · {{ source.packaging_type }} · {{ source.paper_quality }} · {{ source.specification }} · 原单 {{ source.quantity }} {{ source.unit }}</p>
        <div class="flex flex-wrap items-center gap-2">
          <select v-model="pendingCustomers[source.id]" :aria-label="source.id + ' 关闭后关联客户'" :disabled="busy" class="rounded border bg-white p-2" @change="pendingTargets[source.id] = ''"><option value="">选择归属客户</option><option v-for="customer in customers" :key="customer.customer_code" :value="customer.customer_code">{{ customer.customer_name }}</option></select>
          <select v-model="pendingTargets[source.id]" :aria-label="source.id + ' 关闭后关联订单'" :disabled="busy || !pendingCustomers[source.id]" class="rounded border bg-white p-2"><option value="">选择正式订单纸品</option><option v-for="target in pendingFormalTargets(source)" :key="target.line.id" :value="target.line.id">{{ target.order.order_no }} · {{ target.line.packaging_type }} · {{ target.line.paper_quality }} · {{ target.line.specification }} · 待送 {{ target.line.remaining_to_ship }} {{ target.line.unit }}</option></select>
          <input v-model="pendingReasons[source.id]" :aria-label="source.id + ' 关闭后关联原因'" :disabled="busy" placeholder="关联原因（至少四字）" class="rounded border bg-white p-2">
          <button type="button" :aria-label="source.id + ' 确认关闭后关联'" :disabled="!operationsReady || busy || !pendingTargets[source.id]" class="rounded border border-teal-300 bg-white px-3 py-2 text-teal-800 disabled:opacity-40" @click="linkPending(shipment, source)">关联正式订单，保留关闭</button>
        </div>
      </div>
    </section>
    <section ref="shipmentList" class="mt-4" :class="{ 'carton-phone-receiving-list': mobile }"><p v-if="!mobile" class="mb-3 text-sm text-slate-500">供应商确认原送货单后进入本厂区待收货。按本批实物填写实到量，核对差异和入库仓位。</p><template v-for="shipment in visibleShipments" :key="shipment.id"><CartonUnifiedDeliveryNotes v-if="unifiedMap.has(shipment.id)" :group="unifiedMap.get(shipment.id)!" @shortfall-reopened="recordReopenedShipment(shipment, $event)" :data-receiving-note-id="focusedReopenedShipmentId === shipment.id ? shipment.id : undefined" :tabindex="focusedReopenedShipmentId === shipment.id ? -1 : undefined" class="scroll-mt-36" :mobile="mobile" :auto-open="receiptShipmentId === shipment.id" :receipt-entry-paper-ids="entryPapers.get(shipment.id)" @busy="unifiedReceiptBusy = $event" :can-receive="canReceive" :read-blocked="!operationsReady" :locations="locations" :workshops="workshops" :orders="data?.orders || []" :viewer-key="receivingViewerKey" @link-receipt="openReceiptLink" @locations-changed="load" @changed="load(); emit('changed')" @reverse="emit('reverse', $event)"><template #receipt-status><StatusPill v-bind="shipmentReceiptDisplay(shipment)" compact /></template></CartonUnifiedDeliveryNotes><article v-else :data-receiving-note-id="focusedReopenedShipmentId === shipment.id ? shipment.id : undefined" :tabindex="focusedReopenedShipmentId === shipment.id ? -1 : undefined" class="scroll-mt-36 border-t py-3"><div class="flex flex-wrap items-start justify-between gap-3"><strong><StatusPill v-bind="shipmentReceiptDisplay(shipment)" class="mr-2" compact />{{ shipment.delivery_note_no }} · {{ shipment.delivery_date }}<span v-if="shipment.source_filename" class="ml-2 text-xs font-normal text-slate-500"> · 来源 {{ shipment.source_filename }}</span></strong><div class="ml-auto flex flex-wrap items-center justify-end gap-2" :aria-label="`送货单 ${shipment.delivery_note_no} 操作`"><button v-if="canReceive && shipment.can_operate !== false && shipment.status === 'SENT' && !shipment.receipt_id && !shipment.requires_receipt_link && !shipment.requires_correction" type="button" :disabled="!operationsReady || busy" class="rounded-lg border border-teal-200 px-3 py-2 text-xs text-teal-800" @click="openReceiptLink(shipment)">关联已入库记录</button><button v-if="awaitingReceipt(shipment) && canReceive && shipment.can_operate !== false" :disabled="!operationsReady || busy" class="rounded-lg bg-teal-700 px-3 py-2 text-sm text-white" @click="start(shipment)">{{ shipment.requires_receipt_link ? '关联已入库记录' : shipment.requires_correction ? '更正原单验收' : shipment.partially_received ? '继续收余货' : '核实实际收到' }}</button><span v-else class="text-sm">{{ shipment.linked_existing_receipt && !shipment.requires_correction ? '已关联原入库' : shipment.status === 'SENT' ? '等待仓库确认' : shipment.status === 'NOT_RECEIVED' ? '未收到，已退回' : shipment.receipt_id ? '已核实入库' : '已核实，无有效入库' }} {{ shipment.receipt_status === 'REVERSED' ? '（收料已冲销）' : '' }}</span><button v-if="canReceive && shipment.can_operate !== false && shipment.status === 'NOT_RECEIVED' && !shipment.receipt_id" type="button" :disabled="!operationsReady || busy" class="rounded-lg border border-amber-300 px-3 py-2 text-xs text-amber-800" @click="openStatusChange(shipment, 'reopen')">更正未到货，重新待收</button><button v-if="canReceive && shipment.can_operate !== false && shipment.receipt_id && shipment.receipt_status === 'POSTED'" type="button" :disabled="busy || loading" :aria-label="`冲销送货单 ${shipment.delivery_note_no} 的收料`" class="shrink-0 rounded-lg border border-red-200 px-3 py-2 text-xs font-semibold text-red-700" @click="emit('reverse', shipment.receipt_id)">冲销</button></div></div><p v-if="shipment.pending_reason" class="mt-2 text-xs text-amber-800">待收说明：{{ shipment.pending_reason }}</p><p v-for="line in shipment.lines" :key="line.id" class="mt-1 text-sm">{{ line.customer_name }} · {{ line.contract_no }} · 客户 PO {{ line.customer_po || '未填写' }} · {{ line.item_no }} · {{ line.source_type === 'AD_HOC_REVIEW' ? '无单待核实' : line.child_no }} · 纸品类型：{{ line.packaging_type || '未填写' }} · 纸质：{{ line.paper_quality || '未填写' }} · 规格：{{ line.specification || '未填写' }} · 发货 {{ displayQuantity(line.quantity) }} {{ line.unit }}<span v-if="line.remaining_quantity != null" class="ml-2 font-semibold text-teal-800">累计到货 {{ displayQuantity(line.received_quantity) }} · 待收 {{ displayQuantity(line.remaining_quantity) }} {{ line.unit }}<span v-if="Number(line.closed_quantity) > 0"> · 短送结束 {{ displayQuantity(line.closed_quantity) }}</span><span v-if="shipment.requires_correction && Number(line.receivable_quantity) > 0"> · 本批待更正 {{ displayQuantity(line.receivable_quantity) }}</span></span><span v-if="line.material_correction_pending" class="ml-2 font-semibold text-amber-800">资料更正待确认 · 暂停本纸品入库</span><span v-else-if="line.material_correction_note" class="ml-2 text-teal-800">{{ line.material_correction_note }}</span></p><CartonUnifiedDeliveryNotes v-if="formalReopenMap.has(shipment.id) && shipment.lines.some(line => Number(line.closed_quantity) > 0)" :group="formalReopenMap.get(shipment.id)!" :reopen-only="true" @shortfall-reopened="recordReopenedShipment(shipment, $event)" :can-receive="canReceive" :read-blocked="!operationsReady" :viewer-key="receivingViewerKey" @changed="load(); emit('changed')" /><details v-if="shipment.acceptance_history?.length" class="mt-2 text-xs text-slate-600"><summary class="cursor-pointer">验收与冲销历史（{{ shipment.acceptance_history.length }} 次）</summary><p v-for="(history, index) in shipment.acceptance_history" :key="index" class="mt-1">{{ history.acceptance_date }} · {{ history.status === 'REVERSED' ? '已冲销' : '原验收' }} · {{ history.lines.map(line => '实收 ' + line.received_quantity).join('；') }}<button v-if="history.receipt_id && history.status === 'POSTED' && canReceive && shipment.can_operate !== false" type="button" :disabled="busy" class="ml-3 text-red-700 underline" @click="emit('reverse', history.receipt_id)">冲销本次入库</button></p></details><div v-for="sample in shipment.sample_receipts ?? []" :key="sample.receipt_line_id" class="mt-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs"><p class="font-semibold">无单样板收料记录 · {{ sample.customer_name }} · {{ sample.contract_no }} / {{ sample.item_no }} · {{ sample.quantity }} {{ sample.unit }}</p><p class="mt-1">纸品类型：{{ sample.packaging_type || '未填写' }} · 纸质：{{ sample.paper_quality || '未填写' }} · 规格：{{ sample.specification || '未填写' }}</p><p v-if="sample.linked_order_line_id" class="mt-1 text-teal-800">已关联正式订单纸品 {{ sample.linked_order_line_id }}；库存和月结不重复入账。</p><template v-else-if="canLink && shipment.receipt_status === 'POSTED'"><p class="mt-1 text-amber-800">后续正式订单出现后可人工关联。只关联需求，不再生成第二笔入库或月结。</p><div class="mt-2 flex flex-wrap gap-2"><select v-model="linkTargets[sample.receipt_line_id]" :aria-label="`${sample.receipt_line_id} 关联正式订单`" :disabled="busy" class="rounded border bg-white p-2"><option value="">选择正式订单纸品</option><option v-for="target in formalTargets(sample)" :key="target.line.id" :value="target.line.id">{{ target.order.order_no }} · {{ target.line.child_no }} · {{ target.line.packaging_type || '未填写' }} · {{ target.line.paper_quality || '未填写' }} · {{ target.line.specification }} · 需求 {{ target.line.required_quantity }} {{ target.line.unit }}</option></select><input v-model="linkReasons[sample.receipt_line_id]" :aria-label="`${sample.receipt_line_id} 关联原因`" :disabled="busy" class="rounded border p-2" placeholder="关联原因（至少四字）"><button type="button" :disabled="!operationsReady || busy || !formalTargets(sample).length" class="rounded border border-teal-300 bg-white px-3 py-2 text-teal-800 disabled:opacity-40" @click="linkSample(sample)">关联后续订单</button></div><p v-if="!formalTargets(sample).length" class="mt-1 text-amber-800">目前没有同客户、货号、纸品类型、纸质和单位的待收正式订单。</p></template></div></article></template><p v-if="data && !loading && !error && (!chooseReceiptShipment || !filteredShipments.length) && !visibleShipments.length" class="py-5 text-slate-500">{{ shipmentView === 'PENDING' ? '当前条件下没有待收货送货单。' : shipmentView === 'HISTORY' ? '当前条件下没有已处理送货单。' : '当前条件下没有送货单。' }}</p></section>

    <div v-if="active" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40" :class="{ 'p-3': !mobile }">
      <form ref="receiptForm" role="dialog" aria-modal="true" aria-label="核实供应商实际送货" :tabindex="mobile ? -1 : undefined" class="w-full bg-white" :class="mobile ? 'carton-phone-dialog carton-phone-receipt flex max-w-xl flex-col' : 'max-h-[94vh] max-w-6xl overflow-auto rounded-xl p-3 sm:p-5'" @submit.prevent="confirm" @keydown.esc="mobile && closeReceiptDialog()">
      <h2 class="break-words text-lg font-bold" :class="{ 'shrink-0 border-b px-4 py-3': mobile }">{{ mobile ? '验收' : '核实送货单' }} {{ active.delivery_note_no }}</h2>
      <div :class="{ 'carton-phone-receipt-body flex-1 p-4': mobile }">
      <p v-if="!mobile" class="my-2 text-sm text-slate-600">按本批实物填写实到数量。原单余货可在后续到货时继续验收。</p>
      <CartonSplitReceiptReview v-if="hasSplits" :factory="factory" :lines="splitLines" @update:confirmation="splitConfirmation = $event" />
<section v-if="active.requires_correction" class="mb-3 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm"><strong>本次入库已冲销，请核实该批次</strong><p class="mt-1 text-amber-800">只更正已冲销的这一批，其他有效入库保留。更正后仍有余货的，继续沿原送货单收货。</p><label class="mt-2 block">更正原因<input v-model="correctionReason" aria-label="送货单验收更正原因" :disabled="busy" required minlength="4" class="mt-1 w-full rounded border p-2"></label></section><div v-if="focusedPaperIds" class="mb-3 rounded-lg border border-teal-200 bg-teal-50 p-3 text-sm"><p>本次核实所选纸品，尚未核实的其他纸品继续待收。</p><p v-if="!focusedPaperAvailable" tabindex="-1" data-receipt-entry-waiting>所选纸品须等当前原单更正完成后再收料。</p><button type="button" class="mt-2 font-semibold text-teal-800 underline" :disabled="busy" @click="showWholeReceipt">查看整张送货单</button></div>
      <label class="block text-sm">实际验收日期<input v-model="acceptanceDate" :disabled="busy" type="date" required aria-label="发货验收日期" class="ml-2 rounded border p-2"></label><article v-for="(row, index) in received" v-show="receivable(active.lines[index]) > 0 && (!focusedPaperIds || focusedPaperIds.includes(row.shipment_line_id))" :key="row.shipment_line_id" class="mt-4 rounded-lg border p-3"><h3 class="font-semibold">{{ active.lines[index]?.source_type === 'AD_HOC_REVIEW' ? '无单待核实' : active.lines[index]?.child_no }} · {{ active.lines[index]?.contract_no }} · PO {{ active.lines[index]?.customer_po || '未填写' }} · {{ active.lines[index]?.item_no }} · 发货 {{ displayQuantity(active.lines[index]?.quantity) }} {{ active.lines[index]?.unit }} · 累计到货 {{ displayQuantity(active.lines[index]?.received_quantity) }}</h3><div v-if="active.lines[index]?.source_type === 'AD_HOC_REVIEW'" class="mt-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm"><strong class="text-amber-900">无正式订单 · 仓库必须核实</strong><p class="mt-1 text-amber-800">实际属于正单时，先补建完整正式订单或关联已有订单，再沿原送货单验收。样板单、杂单和免费赠送可在下方选择类型直接验收入库，无需补建正单。送错货全数拒收，未到货使用“此项未到”。</p><div class="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2" :aria-label="row.shipment_line_id + ' 验收处理操作'"><div class="flex flex-wrap items-center gap-2"><button v-if="canCreateOrder && !active.requires_receipt_link" type="button" :aria-label="row.shipment_line_id + ' 补建正式订单'" :disabled="!operationsReady || busy || loading" class="rounded border border-teal-300 h-8 px-3 font-semibold text-teal-800 disabled:opacity-40" @click="createOrderFromShipment(active, active.lines[index]!)">补建正单</button><button type="button" :aria-label="row.shipment_line_id + ' 展开或收起已有订单关联'" :aria-expanded="Boolean(expandedOrderSources[row.shipment_line_id])" :aria-controls="'order-source-' + row.shipment_line_id" class="inline-flex min-h-8 items-center gap-1 rounded border border-teal-300 bg-white px-2 py-1 text-xs font-semibold text-teal-800" @click="expandedOrderSources[row.shipment_line_id] = !expandedOrderSources[row.shipment_line_id]"><span aria-hidden="true">{{ expandedOrderSources[row.shipment_line_id] ? '▾' : '▸' }}</span>关联已有订单</button></div><label class="flex flex-wrap items-center gap-2">无单处理结论<select v-model="row.no_order_decision" :aria-label="`${row.shipment_line_id} 无单处理结论`" :disabled="busy || Number(row.received_quantity) === 0" class="h-8 min-w-36 rounded border bg-white px-2" @change="setNoOrderDecision(index)"><option value="">请选择</option><option v-if="legacyCorrection(row.shipment_line_id)" :value="legacyCorrection(row.shipment_line_id)!.no_order_decision">{{ legacyLabel(legacyCorrection(row.shipment_line_id)!.no_order_decision) }}</option><template v-if="!legacyCorrection(row.shipment_line_id)"><option value="SAMPLE">样板单入库</option><option value="MISC">杂单入库</option><option value="GIFT">免费赠送入库</option></template><option value="WRONG_DELIVERY">送错货，拒收</option></select></label></div><div v-show="expandedOrderSources[row.shipment_line_id]" :id="'order-source-' + row.shipment_line_id" class="mt-2 rounded-lg border border-teal-200 bg-white p-3"><div class="flex flex-wrap items-center justify-between gap-2"><strong class="text-teal-900">关联已有订单</strong></div><p class="mt-1 text-xs text-slate-600">关联只允许匹配的纸品类型、纸质、规格及尺寸单位；不同资料须先核实，不能强行关联。计量单位沿正式订单，原送货资料保留。</p><p v-if="existingFormalOrderCount(active.lines[index]!)" class="mt-1 text-xs font-semibold text-teal-800">已有兼容正式订单，请先核对并复用，避免重复下单。</p><div class="mt-2 grid gap-2 sm:grid-cols-2"><label>关联已有正式订单 · 客户<select v-model="pendingCustomers[row.shipment_line_id]" :aria-label="row.shipment_line_id + ' 验收关联客户'" :disabled="busy" class="mt-1 w-full rounded border bg-white p-2" @change="pendingTargets[row.shipment_line_id] = ''"><option value="">选择归属客户</option><option v-for="customer in customers" :key="customer.customer_code" :value="customer.customer_code">{{ customer.customer_name }}</option></select></label><label>正式订单纸品<select v-model="pendingTargets[row.shipment_line_id]" :aria-label="row.shipment_line_id + ' 验收关联订单'" :disabled="busy || !pendingCustomers[row.shipment_line_id]" class="mt-1 w-full rounded border bg-white p-2"><option value="">选择正式订单纸品</option><option v-for="target in pendingFormalTargets(active.lines[index]!)" :key="target.line.id" :value="target.line.id">{{ target.order.order_no }} · PO {{ target.order.customer_po || '未填' }} · {{ target.line.packaging_type }} · {{ target.line.paper_quality }} · {{ target.line.specification }} {{ target.line.dimension_unit }} · 待送 {{ target.line.remaining_to_ship }} {{ target.line.unit }}</option></select></label><label class="sm:col-span-2">关联原因<input v-model="pendingReasons[row.shipment_line_id]" :aria-label="row.shipment_line_id + ' 验收关联原因'" :disabled="busy" class="mt-1 w-full rounded border p-2" placeholder="核对原送货与正式订单的依据（至少四字）"></label></div><button type="button" :aria-label="row.shipment_line_id + ' 验收确认关联'" :disabled="!operationsReady || busy || !pendingTargets[row.shipment_line_id]" class="mt-2 rounded border border-teal-300 px-3 py-2 text-teal-800 disabled:opacity-40" @click="linkPending(active, active.lines[index]!)">确认关联正式订单，继续验收</button></div><p v-if="legacyCorrection(row.shipment_line_id)" class="mt-2 text-xs text-slate-600">沿原冲销批次更正，保留原类型、客户与需求人：{{ legacyCorrection(row.shipment_line_id)!.customer_code || '未关联客户' }} · {{ legacyCorrection(row.shipment_line_id)!.requested_by || '原记录未填写' }}</p><p v-if="row.no_order_decision === 'WRONG_DELIVERY'" class="mt-2 text-amber-900">此项全部拒收退回，实际入库为 0；下方到货数量保留原实物记录，拒收数量与到货数量相等。</p></div>
        <div class="mt-3 space-y-2">
          <p class="text-sm text-slate-600">原单待收 <strong class="tabular-nums">{{ displayQuantity(receivable(active.lines[index])) }} {{ active.lines[index]?.unit }}</strong></p>
          <div class="flex flex-wrap items-end gap-2">
            <label class="block min-w-0 max-w-xs flex-1 basis-32 text-sm font-semibold">本批实到（{{ active.lines[index]?.unit }}）
              <input v-model.number="row.received_quantity" :data-mobile-first-paper="mobile ? '' : undefined" :data-receipt-entry-focus="focusedPaperIds?.includes(row.shipment_line_id) && receivable(active.lines[index]) > 0 ? '' : undefined" :aria-label="row.shipment_line_id + ' 实收'" :disabled="busy" type="number" inputmode="decimal" min="0" step="0.0001" :max="receivable(active.lines[index])" placeholder="按实物填写" class="mt-1 w-full rounded border p-2">
            </label>
            <button type="button" :aria-label="row.shipment_line_id + ' 按余量全收'" :disabled="busy" class="rounded border border-teal-200 px-3 py-2 text-xs font-semibold text-teal-800" @click="markAsDelivered(index)">按余量全收</button>
            <button type="button" :disabled="busy" class="rounded border px-3 py-2 text-xs font-semibold text-slate-700" @click="markNotReceived(index)">此项未到</button>
          </div>
        </div>
        <details class="mt-3 rounded-lg border px-3 py-2">
          <summary class="cursor-pointer text-sm font-semibold text-teal-800" :aria-label="row.shipment_line_id + ' 填写验收差异'">
            破损、拒收及其他差异<span v-if="row.damaged_quantity || row.rejected_quantity || row.unusable_quantity || row.difference_reason" class="ml-2 text-xs font-normal text-amber-800">已填写</span>
          </summary>
          <div class="mt-3 grid gap-3 sm:grid-cols-3">
            <label class="text-sm">破损<input v-model.number="row.damaged_quantity" :aria-label="row.shipment_line_id + ' 破损'" :disabled="busy" type="number" min="0" step="0.0001" class="mt-1 w-full rounded border p-2"></label>
            <label class="text-sm">拒收<input v-model.number="row.rejected_quantity" :aria-label="row.shipment_line_id + ' 拒收'" :disabled="busy" type="number" min="0" step="0.0001" class="mt-1 w-full rounded border p-2"></label>
            <label class="text-sm">其他不可用<input v-model.number="row.unusable_quantity" :aria-label="row.shipment_line_id + ' 其他不可用'" :disabled="busy" type="number" min="0" step="0.0001" class="mt-1 w-full rounded border p-2"></label>
            <label class="text-sm sm:col-span-3">差异原因
              <input v-model="row.difference_reason" :disabled="busy" :aria-required="differenceRequired(row)" :aria-label="row.shipment_line_id + ' 差异原因'" maxlength="1000" class="mt-1 w-full rounded border p-2">
            </label>
          </div>
        </details>
        <component :is="mobile && active.lines[index]?.source_type !== 'AD_HOC_REVIEW' && row.paper_quality && row.specification ? 'details' : 'div'" :class="{ 'mt-3 rounded-lg border px-3 py-1': mobile }">
          <summary v-if="mobile && active.lines[index]?.source_type !== 'AD_HOC_REVIEW' && row.paper_quality && row.specification" class="flex cursor-pointer items-center text-xs font-semibold text-teal-800">查看纸品资料与单价</summary>
          <div class="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><label class="text-sm">纸品类型<input :value="active.lines[index]?.packaging_type || '未填写'" :aria-label="`${row.shipment_line_id} 纸品类型`" readonly :disabled="busy" class="mt-1 w-full rounded border p-2"></label><label class="text-sm">纸质<input v-model="row.paper_quality" :aria-label="`${row.shipment_line_id} 纸质`" placeholder="未填写" :disabled="busy || Boolean(active.lines[index]?.paper_quality)" class="mt-1 w-full rounded border p-2"></label><label class="text-sm">规格<input v-model="row.specification" :aria-label="`${row.shipment_line_id} 规格`" placeholder="未填写" :disabled="busy || Boolean(active.lines[index]?.specification)" class="mt-1 w-full rounded border p-2"></label><label class="text-sm">供应商单价 {{ active.lines[index]?.currency || 'CNY' }}<input :value="originalSupplierReceiptPrice(active.lines[index] || {}) ?? ''" :aria-label="row.shipment_line_id + ' 入库单价'" readonly placeholder="未填写（待核价）" class="mt-1 w-full rounded border bg-slate-50 p-2"><span class="mt-1 block text-xs text-slate-500">{{ row.no_order_decision === 'GIFT' ? '免费赠送；供应商未注明免费的，保留待确认记录' : row.price_action === 'PENDING' ? originalSupplierReceiptPrice(active.lines[index] || {}) == null ? '原单未填写单价，可先入库，等待供应商补价' : '原单单价为0，未确认免费，等待供应商核实' : row.price_action === 'FREE' ? '供应商已明确确认免费' : '按供应商送货原价入库' }}</span></label></div>
        </component>
        <div v-show="effective(row) > 0" class="mt-3 space-y-1">
          <p class="text-xs font-semibold">入库仓位</p>
          <CartonReceiptAllocations v-model="row.location_allocations" :mobile="mobile" :effective="effective(row)" :locations="locations" :factory-id="factory" :disabled="busy" class="!min-w-0 [&>div]:flex-wrap" @created="load" />
          <p v-if="missingReceiptLocation(row)" class="text-xs text-amber-800">请选择入库仓位。</p>
        </div>
      </article>
      <details v-if="receiptEntries.length" class="mt-4 rounded-lg border px-3 py-2">
        <summary class="cursor-pointer text-sm font-semibold text-teal-800" aria-label="短送结案选项">短送结案
          <span class="ml-2 text-xs font-normal text-slate-600">{{ closingShortfall ? '已选择结案' : '余货继续待收' }}</span>
        </summary>
        <div class="mt-3 space-y-3">
          <p class="text-xs text-slate-600">只结案本送货单的未到余量，采购欠数保留。实物未到的纸品，本批实到填 0。</p>
          <label v-if="!focusedPaperIds" class="block text-sm font-semibold">未收余货
            <select v-model="remainingAction" aria-label="未收余货处理" :disabled="busy" class="mt-1 block w-full max-w-xs rounded border p-2">
              <option value="WAIT">余货继续待收</option>
              <option value="CLOSE">整张送货单短送结案</option>
            </select>
          </label>
          <label v-for="{ row, source } in receiptEntries" :key="row.shipment_line_id" class="flex items-start gap-2 text-sm">
            <input v-model="row.close_remaining" type="checkbox" :aria-label="row.shipment_line_id + ' 关闭此纸品余量'" :disabled="busy || remainingAction === 'CLOSE'">
            {{ source.packaging_type }} · {{ source.specification }} · {{ source.child_no || source.item_no }} · 此纸品短送结案
          </label>
        </div>
      </details>
      <label v-if="closingShortfall" class="mt-3 block text-sm font-semibold">短送结案原因（必填）
        <input v-model="closeReason" aria-label="短送结案原因" :disabled="busy" minlength="4" maxlength="1000" required placeholder="填写至少四字原因" class="mt-1 w-full rounded border p-2">
      </label>
      <div v-if="receiptOptions.length" class="my-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"><p>发现相同纸品和数量的已入库记录。后补凭证请关联原收料，避免重复入库。</p><button type="button" class="mt-2 rounded border bg-white px-3 py-2" :disabled="!operationsReady || busy" @click="openReceiptLink(active!)">关联已入库记录</button><label class="mt-3 flex items-center gap-2"><input v-model="newDeliveryConfirmed" type="checkbox" :disabled="busy">我已核对，这是新一批实际到货</label></div><p v-if="candidateLoading" class="my-3 text-sm text-slate-500">正在检查原收料记录…</p><p v-if="candidateError" role="alert" class="my-3 text-red-700">原收料检查失败：{{ candidateError }}<button type="button" class="ml-2 underline" @click="checkReceipts(active!)">重试</button></p><p v-if="error" role="alert" class="my-3 text-red-700">{{ error }}</p>
      </div>
      <div class="space-y-2 border-t pt-3" :class="mobile ? 'carton-phone-footer shrink-0 px-4' : 'mt-4'">
        <CartonMobileReceiptTotals v-if="mobile" :rows="mobileReceiptTotals" />
        <section v-else-if="receiptSummary.length" aria-label="本批验收汇总" aria-live="polite" class="space-y-2">
          <div v-for="entry in receiptSummary" :key="entry.row.shipment_line_id" class="rounded-lg bg-muted/60 px-3 py-2 text-xs">
            <p class="mb-1 font-semibold">{{ entry.source.packaging_type }} · {{ entry.source.specification }} · {{ entry.source.child_no || entry.source.item_no }}</p>
            <dl class="flex flex-wrap gap-x-5 gap-y-1 tabular-nums">
              <div class="flex items-baseline gap-1">
                <dt>本批有效入库</dt>
                <dd class="font-semibold">{{ entry.quantityValid && entry.entered ? displayQuantity(effective(entry.row)) + ' ' + entry.source.unit : '—' }}</dd>
              </div>
              <div class="flex items-baseline gap-1">
                <dt>原单继续待收</dt>
                <dd class="font-semibold">{{ entry.quantityValid && entry.entered ? displayQuantity(entry.closing ? 0 : entry.remaining) + ' ' + entry.source.unit : '—' }}</dd>
              </div>
              <div v-if="entry.closing && entry.quantityValid && entry.entered && entry.remaining > 0" class="flex items-baseline gap-1 text-amber-800">
                <dt>本次短送结案</dt><dd class="font-semibold">{{ displayQuantity(entry.remaining) }} {{ entry.source.unit }}</dd>
              </div>
            </dl>
          </div>
        </section>
        <p v-if="focusedPaperAvailable && (receiptProblem || needsReceiptLocation)" role="status" class="text-xs text-slate-600">{{ receiptProblem || '请选择有效入库纸品的仓位。' }}</p>
        <div class="flex flex-wrap justify-end gap-2" :class="{ '[&>button:last-child]:flex-1': mobile }">
          <button type="button" :disabled="busy" class="rounded border px-4 py-2" @click="closeReceiptDialog">取消</button>
          <button type="submit" :disabled="!operationsReady || busy || !focusedPaperAvailable || candidateLoading || Boolean(candidateError) || !!receiptProblem || needsReceiptLocation || (receiptOptions.length > 0 && !newDeliveryConfirmed && received.some(row => Number(row.received_quantity) > 0))" class="rounded bg-teal-700 px-4 py-2 text-white disabled:opacity-50">
            {{ busy ? '正在保存…' : closingShortfall ? '确认验收并结案' : !receiptProblem && received.every(row => Number(row.received_quantity) === 0) ? '暂未到货，继续待收' : '确认本次收货' }}
          </button>
        </div>
      </div>
    </form>
    </div>

    <div v-if="statusActive" class="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/45 p-4">
      <form role="dialog" aria-modal="true" :aria-label="statusAction === 'defer' ? '记录暂未到货' : '更正未到货反馈'" class="w-full max-w-xl rounded-xl bg-white p-5" @submit.prevent="confirmStatusChange">
        <h3 class="font-bold">{{ statusAction === 'defer' ? '暂未到货，继续待收' : '更正未到货，重新待收' }} · {{ statusActive.delivery_note_no }}</h3>
        <p class="mt-3 text-sm text-amber-800">{{ statusAction === 'defer' ? '适用于尚未到达、仍会继续送达的整张送货单。保留在途数量，不终结送货单，也不生成入库。' : '适用于误确认整单未收到的更正。原记录继续保留，重新保护在途数量；订单版本或剩余需求已变化时需先核对。' }}</p>
        <label class="mt-4 block text-sm">原因<textarea v-model="statusReason" :disabled="busy" required minlength="4" maxlength="1000" aria-label="未到货处理原因" class="mt-1 w-full rounded border p-2" /></label>
        <p v-if="error" role="alert" class="mt-3 text-red-700">{{ error }}</p>
        <div class="mt-4 flex justify-end gap-2"><button type="button" :disabled="busy" class="rounded border px-4 py-2" @click="statusActive = null">取消</button><button :disabled="!operationsReady || busy || statusReason.trim().length < 4" class="rounded bg-teal-700 px-4 py-2 text-white disabled:opacity-40">{{ busy ? '正在保存…' : '确认保存' }}</button></div>
      </form>
    </div>
    <div v-if="linkActive" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 p-4">
      <form aria-label="关联已入库记录" class="max-h-[90vh] w-full max-w-3xl overflow-auto rounded-xl bg-white p-5" @submit.prevent="confirmReceiptLink">
        <header class="flex items-center justify-between gap-3"><h3 class="font-bold">关联已入库记录 · {{ linkActive.delivery_note_no }}</h3><button type="button" :disabled="busy" @click="closeReceiptDialog">关闭</button></header>
        <p class="mt-3 rounded-lg bg-teal-50 p-3 text-sm text-teal-900">确认本送货单为原收料的后补凭证。仅关联整张已入库记录，数量、仓位和原验收日期保持原记录，库存只记一次。货款自动采用首次有效供应商原价，价格变化通知仓库；手工原价保留备查。</p>
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
        <footer class="mt-4 flex justify-end gap-2"><button type="button" :disabled="busy" class="rounded border px-4 py-2" @click="closeReceiptDialog">取消</button><button :disabled="!operationsReady || busy || candidateLoading || Boolean(candidateError) || !receiptChoice || receiptLinkReason.trim().length < 4" class="rounded bg-teal-700 px-4 py-2 text-white disabled:opacity-40">{{ busy ? '正在关联…' : '确认关联，不重复入库' }}</button></footer>
      </form>
    </div>
  </section>
</template>
