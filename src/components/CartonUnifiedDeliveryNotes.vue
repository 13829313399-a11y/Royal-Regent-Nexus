<script setup lang="ts">
import { originalSupplierReceiptPrice, supplierReceiptPrice } from '@/features/carton-procurement/supplierReceiptPrice'
import { computed, nextTick, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { Button } from '@/components/ui/button'
import { cartonUnifiedDeliveriesApi as api, unifiedDeliveryLineKind, type UnifiedDelivery, type UnifiedDeliveryLine, type PriceAction } from '@/api/cartonUnifiedDeliveries'
import { cartonSpecialRequestsApi } from '@/api/cartonSpecialRequests'
import CartonReceiptAllocations from '@/components/CartonReceiptAllocations.vue'
import CartonSourceLinks from '@/components/CartonSourceLinks.vue'
import CartonSplitReceiptReview from '@/components/CartonSplitReceiptReview.vue'
import CartonMobileReceiptTotals from '@/features/carton-procurement/CartonMobileReceiptTotals.vue'
import { cartonSupplierPortalApi, type PortalOrder, type PortalShipment, type ShipmentReceiptOption } from '@/api/cartonSupplierPortal'
import type { CartonLocation, LocationAllocation } from '@/api/cartonPositions'
import { getApiErrorMessage } from '@/lib/http'
import { formatBusinessDate } from '@/lib/dateTime'
import { createRandomUuid } from '@/lib/randomUuid'
import { deliveryPaperNeedsReceipt } from '@/features/carton-procurement/receiptDisplay'

const displayQuantity = (value: unknown) => {
  const number = Number(value ?? 0)
  return Number.isFinite(number) ? number.toLocaleString('zh-CN', { maximumFractionDigits: 4 }) : String(value ?? '')
}
const props = withDefaults(defineProps<{ group: UnifiedDelivery; supplier?: boolean; collapsible?: boolean; canReceive?: boolean; readBlocked?: boolean; autoOpen?: boolean; receiptEntryPaperIds?: string[]; reopenOnly?: boolean; locations?: CartonLocation[]; workshops?: { id: string; name: string }[]; viewerKey?: string; orders?: PortalOrder[]; mobile?: boolean }>(), { locations: () => [], workshops: () => [], orders: () => [] })
const emit = defineEmits<{ changed: []; 'shortfall-reopened': [quantities: string]; reverse: [receiptId: string]; 'link-receipt': [shipment: PortalShipment]; 'locations-changed': []; busy: [value: boolean] }>()
interface Row { source: UnifiedDeliveryLine; received: string; damaged: string; rejected: string; unusable: string; allocations: LocationAllocation[]; action: PriceAction; price: string; reason: string; difference: string; close: boolean }
const editing = ref(false), busy = ref(false), error = ref(''), message = ref(''), rows = ref<Row[]>([])
const receiptForm = ref<HTMLFormElement | null>(null)
const focusedPaperIds = shallowRef<string[] | null>(null)
const editableRows = computed(() => focusedPaperIds.value
  ? rows.value.filter(row => focusedPaperIds.value?.includes(row.source.id)) : rows.value)
const focusedPaperAvailable = computed(() => !focusedPaperIds.value || editableRows.value.some(row =>
  Number(row.source.receivable_quantity ?? row.source.remaining_quantity ?? 0) > 0))
const usesFormalReceipt = computed(() => Boolean(props.group.formal && (!focusedPaperIds.value || editableRows.value.some(row =>
  row.source.source_kind === 'FORMAL' && Number(row.source.receivable_quantity ?? row.source.remaining_quantity ?? 0) > 0))))
const correctsFormalReceipt = computed(() => usesFormalReceipt.value && (focusedPaperIds.value
  ? Boolean(props.group.formal?.requires_correction) : props.group.requires_correction))
watch(busy, value => emit('busy', value))
const date = ref(''), correctionReason = ref(''), splitConfirmation = ref('')
const remainingAction = ref<'WAIT' | 'CLOSE'>('WAIT'), closeReason = ref('')
const reopening = ref(false), reopenReason = ref('')
const reopenRows = ref<{ source: UnifiedDeliveryLine; selected: boolean; quantity: string }[]>([])
const closedLines = computed(() => props.group.lines.filter(line => scaled(line.closed_quantity || '0') > 0n))
const closureNotes = computed(() => [
  ...(props.group.formal?.acceptance_history || []).flatMap(batch => batch.lines.filter(line => line.difference_reason).map(line => `${batch.acceptance_date || ''} · ${line.difference_reason}`)),
  ...props.group.special.flatMap(request => request.shipments.flatMap(shipment => (shipment.closures || []).map(item => `${item.acceptance_date} · ${item.reason}`))),
])
const candidateLoading = ref(false), candidateError = ref(''), candidates = ref<ShipmentReceiptOption[]>([]), newDeliveryConfirmed = ref(false)
const splitLines = computed(() => editableRows.value.flatMap(row => row.source.source_kind === 'FORMAL' && row.source.order_line_id ? [{ order_line_id: row.source.order_line_id, effective_quantity: Number(decimal(effective(row))) }] : []))
const hasSplits = computed(() => splitLines.value.some(line => props.orders.some(order => order.lines.some(paper => paper.id === line.order_line_id) && order.split_records?.some(plan => plan.status !== 'CANCELLED'))))
async function checkCandidates() {
  if (!props.group.formal || !usesFormalReceipt.value || props.supplier) return
  const token = generation; candidateLoading.value = true; candidateError.value = ''; candidates.value = []
  try { const result = await cartonSupplierPortalApi.receiptOptions(props.group.factory_id, props.group.formal.id); if (token === generation) candidates.value = result }
  catch (cause) { if (token === generation) candidateError.value = getApiErrorMessage(cause) }
  finally { if (token === generation) candidateLoading.value = false }
}
const extra = ref<Record<string, { kind: '' | 'SAMPLE' | 'WORKSHOP_MISC'; requester: string; workshop: string }>>({})
let generation = 0, controller = new AbortController()
const attempts = new Map<string, string>()
const receiptAuthority = computed(() => !props.supplier && props.canReceive && props.group.can_operate)
const canReceive = computed(() => !props.readBlocked && receiptAuthority.value)
const pending = computed(() => props.group.lines.some(line => Number(line.receivable_quantity ?? line.remaining_quantity ?? 0) > 0))
const businessLabel = (line: UnifiedDeliveryLine) => ({ REGULAR: '正单', SAMPLE: '样板', MISC: '杂单', UNKNOWN: line.origin === 'SUPPLIER_EXTRA' ? '额外送货 · 待核对用途' : '历史或无单' })[unifiedDeliveryLineKind(props.group, line)]
const originalPrice = (line: UnifiedDeliveryLine) => originalSupplierReceiptPrice(line)
const valid = (value: string, digits = 4) => new RegExp(`^\\d{1,14}(\\.\\d{1,${digits}})?$`).test(value)
const scaled = (value: string) => { if (!valid(value)) return 0n; const [whole = '0', fraction = ''] = value.split('.'); return BigInt(whole) * 10000n + BigInt(fraction.padEnd(4, '0')) }
const decimal = (value: bigint) => `${value / 10000n}.${(value % 10000n).toString().padStart(4, '0')}`
const effective = (row: Row) => scaled(row.received) - scaled(row.damaged) - scaled(row.rejected) - scaled(row.unusable)
const receivableQuantity = (line: UnifiedDeliveryLine) => line.receivable_quantity ?? line.remaining_quantity ?? '0'
const displayReceiptQuantity = (value: bigint) => decimal(value).replace(/\.?0+$/, '')
const receiptEntries = computed(() => editableRows.value
  .filter(row => scaled(receivableQuantity(row.source)) > 0n)
  .map(row => {
    const original = scaled(receivableQuantity(row.source))
    const actual = scaled(row.received)
    const inbound = effective(row)
    const entered = row.received !== ''
    const quantityValid = (!entered || valid(row.received)) && [row.damaged, row.rejected, row.unusable].every(value => valid(value))
      && inbound >= 0n && actual <= original
    const missingLocation = quantityValid && inbound > 0n && (!row.allocations.length || row.allocations.some(part => !part.location_id))
    return { row, actual, inbound, entered, quantityValid, missingLocation, remaining: original - actual,
      closing: remainingAction.value === 'CLOSE' || row.close }
  }))
const closingShortfall = computed(() => receiptEntries.value.some(entry => entry.closing))
const receiptSummary = computed(() => receiptEntries.value.filter(entry => entry.entered || entry.closing))
const mobileReceiptTotals = computed(() => receiptEntries.value.map(entry => ({
  unit: entry.row.source.unit,
  inbound: entry.quantityValid && entry.entered ? Number(decimal(entry.inbound)) : 0,
  remaining: Number(decimal(entry.quantityValid && entry.entered
    ? entry.closing ? 0n : entry.remaining
    : scaled(receivableQuantity(entry.row.source)))),
})))
const receiptProblem = computed(() => {
  const entries = receiptEntries.value
  if (entries.some(entry => entry.closing && !entry.entered)) return '请填写结案纸品的本批实到数量。未到填写 0。'
  if (!entries.some(entry => entry.entered)) return '请填写本批实到数量。未到填写 0。'
  if (entries.some(entry => !entry.quantityValid)) return '请核对本批实到和差异数量。实到不能超过原单待收，差异合计不能超过实到。'
  if (closingShortfall.value && closeReason.value.trim().length < 4) return '短送结案须填写至少四字原因。'
  if (entries.some(entry => entry.row.source.source_kind === 'FORMAL' && entry.actual !== entry.inbound
    && entry.row.difference.trim().length < 4 && !(entry.closing && entry.remaining > 0n))) {
    return '有破损、拒收或其他不可用数量时，请填写至少四字差异说明。'
  }
  if (entries.some(entry => entry.missingLocation)) return '请选择有效入库纸品的仓位。'
  return ''
})
function reset() { generation++; controller.abort(); controller = new AbortController(); editing.value = false; focusedPaperIds.value = null; reopening.value = false; reopenReason.value = ''; reopenRows.value = []; busy.value = false; error.value = ''; message.value = ''; rows.value = []; candidates.value = []; candidateError.value = ''; candidateLoading.value = false; newDeliveryConfirmed.value = false; splitConfirmation.value = ''; attempts.clear() }
watch([() => props.group.factory_id, () => props.group.id, () => props.group.revision,
  () => props.group.special.map(item => `${item.id}:${item.revision}`).join(','),
  () => props.viewerKey, () => props.supplier, () => props.canReceive], reset, { flush: 'sync' })
onBeforeUnmount(() => { generation++; controller.abort() })
watch([() => props.autoOpen, () => props.group.id, () => props.receiptEntryPaperIds, () => props.viewerKey, canReceive], () => {
  const available = props.receiptEntryPaperIds
    ? props.group.lines.some(line => props.receiptEntryPaperIds?.includes(line.id) && deliveryPaperNeedsReceipt(line)) : pending.value
  if (props.autoOpen && canReceive.value && available && !props.reopenOnly && !editing.value) open()
}, { immediate: true, flush: 'post' })
function sources(line: UnifiedDeliveryLine) {
  const request = props.group.special.find(row => row.id === line.special_request_id)
  return request ? [{ id: request.id, request_no: request.request_no, kind: request.kind, line_id: line.original_special_line_id }] : []
}
function open() {
  if (!canReceive.value || busy.value || props.reopenOnly) return
  reopening.value = false
  remainingAction.value = 'WAIT'; closeReason.value = ''
  error.value = ''; message.value = ''; editing.value = true; date.value = formatBusinessDate(new Date().toISOString()); correctionReason.value = ''; newDeliveryConfirmed.value = false; splitConfirmation.value = ''
  const papers = props.receiptEntryPaperIds
  focusedPaperIds.value = papers ?? null
  rows.value = props.group.lines.filter(line => line.source_kind === 'FORMAL' || Number(line.receivable_quantity ?? line.remaining_quantity ?? 0) > 0).map(source => ({ source,
    received: '', damaged: '0', rejected: '0', unusable: '0', allocations: [],
    action: originalPrice(source) == null ? 'PENDING' : Number(originalPrice(source)) === 0 ? source.free_confirmed ? 'FREE' : 'PENDING' : 'MATCH', price: originalPrice(source) ?? '', reason: supplierReceiptPrice(source).price_reason, difference: '', close: false }))
  void checkCandidates()
  extra.value = Object.fromEntries(props.group.special.filter(item => item.origin === 'SUPPLIER_EXTRA').map(item => [item.id, { kind: item.shipments.some(shipment => shipment.receipts?.some(receipt => receipt.status === 'POSTED')) && item.kind === 'SAMPLE' ? 'SAMPLE' : item.shipments.some(shipment => shipment.receipts?.some(receipt => receipt.status === 'POSTED')) && item.kind === 'WORKSHOP_MISC' ? 'WORKSHOP_MISC' : '', requester: item.requester_name || '', workshop: item.workshop_id || '' }]))
  if (props.mobile || papers) void nextTick(() => {
    if (props.mobile && editing.value) receiptForm.value?.focus({ preventScroll: true })
    if (!papers) return
    if (!editing.value || focusedPaperIds.value !== papers) return
    const field = receiptForm.value?.querySelector<HTMLElement>('[data-receipt-entry-focus], [data-receipt-entry-waiting]')
    field?.focus()
    field?.scrollIntoView?.({ block: 'nearest' })
  })
}
function showWholeReceipt() {
  const hadFormal = usesFormalReceipt.value
  focusedPaperIds.value = null
  if (!hadFormal) void checkCandidates()
}
const whollyRejected = (line: UnifiedDeliveryLine) => Number(line.received_quantity || 0) > 0 && Number(line.rejected_quantity || 0) === Number(line.received_quantity) && Number(line.effective_quantity || 0) === 0
const allRejected = computed(() => !pending.value && props.group.lines.length > 0 && props.group.lines.every(whollyRejected))
const receiptStatus = computed(() => {
  if (props.supplier) {
    if (props.group.requires_correction || props.group.status === 'RECEIPT_REVERSED') return '收料已冲销，待更正'
    if (props.group.status === 'NOT_RECEIVED') return '仓库未收到'
    if (pending.value && props.group.lines.some(line => Number(line.received_quantity) > 0)) return '部分已核实，余货待收'
  }
  return pending.value ? '待核实实际收货' : allRejected.value ? '整单已拒收退回 · 入库 0' : '已核实'
})
const receiptHistory = computed<UnifiedDelivery['receipts']>(() => {
  const { receipts, formal } = props.group
  if (!props.supplier) return receipts
  return [...receipts, ...(formal?.acceptance_history ?? []).filter(batch =>
    !batch.receipt_id || !receipts.some(receipt => (receipt.receipt_id || receipt.id) === batch.receipt_id))]
})
function inboundLabel(line: UnifiedDeliveryLine) {
  const awaitingReceipt = Number(line.receivable_quantity ?? line.remaining_quantity) > 0 && !Number(line.received_quantity)
  return line.effective_quantity == null || (props.collapsible && awaitingReceipt) ? '待核实' : displayQuantity(line.effective_quantity)
}
function openReopening() {
  if (!canReceive.value || busy.value) return
  editing.value = false; reopening.value = true; reopenReason.value = ''; error.value = ''; message.value = ''
  reopenRows.value = closedLines.value.map(source => ({ source, selected: false, quantity: source.closed_quantity || '0' }))
}
async function submitReopening() {
  if (!canReceive.value || busy.value) return
  error.value = ''
  const selected = reopenRows.value.filter(row => row.selected)
  if (reopenReason.value.trim().length < 4 || !selected.length || selected.some(row => !valid(row.quantity)
    || scaled(row.quantity) <= 0n || scaled(row.quantity) > scaled(row.source.closed_quantity || '0'))) {
    error.value = '请选择误关闭纸品，填写不超过已结束余量的重开数量及至少四字原因。'; return
  }
  const formal = selected.filter(row => row.source.source_kind === 'FORMAL')
  const special = props.group.special.flatMap(request => request.shipments.flatMap(shipment => {
    const chosen = selected.filter(row => row.source.special_shipment_id === shipment.id)
    return chosen.length ? [{ request_id: request.id, shipment_id: shipment.id, expected_revision: request.revision,
      lines: chosen.map(row => ({ shipment_line_id: row.source.id, quantity: row.quantity })) }] : []
  }))
  const payload = { factory_id: props.group.factory_id, reason: reopenReason.value.trim(), special,
    ...(formal.length && props.group.formal ? { formal: { expected_revision: props.group.formal.revision,
      lines: formal.map(row => ({ shipment_line_id: row.source.id, quantity: row.quantity })) } } : {}) }
  const signature = 'reopen:' + JSON.stringify(payload)
  try { if (!attempts.has(signature)) attempts.set(signature, createRandomUuid()) }
  catch (cause) { error.value = getApiErrorMessage(cause); return }
  const token = generation; busy.value = true
  try {
    await api.reopenShortfall(props.group.id, { ...payload, request_id: attempts.get(signature) }, controller.signal)
    if (token !== generation) return
    attempts.delete(signature)
    reopening.value = false
    const quantities = new Map<string, bigint>()
    for (const { source, quantity } of selected) {
      quantities.set(source.unit, (quantities.get(source.unit) ?? 0n) + scaled(quantity))
    }
    emit('shortfall-reopened', [...quantities].map(([unit, quantity]) => `${displayReceiptQuantity(quantity)} ${unit}`.trim()).join('、'))
    emit('changed')
  } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) busy.value = false }
}
async function submit() {
  if (!canReceive.value || busy.value) return
  error.value = ''
  if (usesFormalReceipt.value && (candidateLoading.value || candidateError.value)) { error.value = '请先完成原收料重复检查，失败时点击重试。'; return }
  if (usesFormalReceipt.value && (props.group.formal?.requires_receipt_link || candidates.value.length && !newDeliveryConfirmed.value)) { error.value = '请关联原收料，或核对本次确为新一批到货。'; return }
  if (receiptProblem.value) return
  if (!date.value) { error.value = '请填写实际验收日期。'; return }
  const hasArrival = receiptEntries.value.some(entry => entry.actual > 0n)
  const chosen = receiptEntries.value
    .filter(entry => entry.closing || (entry.entered && (!hasArrival || entry.actual > 0n)))
    .map(entry => entry.row)
  if (chosen.some(row => effective(row) > 0n && (!row.allocations.length || row.allocations.some(part => !valid(String(part.quantity)) || scaled(String(part.quantity)) <= 0n || !props.locations.some(location => location.id === part.location_id && location.status !== 'INACTIVE')) || new Set(row.allocations.map(part => part.location_id)).size !== row.allocations.length || row.allocations.reduce((sum, part) => sum + scaled(String(part.quantity)), 0n) !== effective(row)))) { error.value = '请核对本厂仓位及分仓数量，合计须等于有效入库，仓位不能重复。'; return }
  if (correctsFormalReceipt.value && correctionReason.value.trim().length < 4) { error.value = '冲销后重新验收须填写至少四字更正原因。'; return }
  const common = (row: Row) => ({ shipment_line_id: row.source.id, received_quantity: row.received || '0', damaged_quantity: row.damaged, rejected_quantity: row.rejected, unusable_quantity: row.unusable,
    location_allocations: effective(row) > 0n ? row.allocations : [],
    ...(row.close ? { close_remaining: true } : {}), price_action: row.action, price_reason: row.reason.trim(), unit_price: row.action === 'PENDING' ? originalPrice(row.source) ?? '0' : row.price,
    ...(row.action === 'FREE' || row.action === 'PROPOSE' && Number(row.price) === 0 ? { zero_price_kind: 'FREE' } : {}) })
  const special = props.group.special.flatMap(request => request.shipments.flatMap(shipment => {
    const groupRows = chosen.filter(row => row.source.special_shipment_id === shipment.id)
    if (!groupRows.length) return []
    const extraChoice = extra.value[request.id]
    return [{ request_id: request.id, shipment_id: shipment.id, expected_revision: request.revision, lines: groupRows.map(common), remaining_action: remainingAction.value, close_reason: closeReason.value.trim(),
      ...(extraChoice?.kind ? { received_kind: extraChoice.kind, requester_name: extraChoice.requester.trim(), workshop_id: extraChoice.kind === 'WORKSHOP_MISC' ? extraChoice.workshop : '' } : {}) }]
  }))
  if (chosen.some(row => effective(row) > 0n && row.source.origin === 'SUPPLIER_EXTRA' && !extra.value[row.source.special_request_id || '']?.kind)) { error.value = '额外送货须核对用途：请选择样板或杂单入库类型。'; return }
  const formalRows = chosen.some(row => row.source.source_kind === 'FORMAL') ? rows.value.filter(row => row.source.source_kind === 'FORMAL') : []
  const formalLines = formalRows.map(row => {
    const closing = (remainingAction.value === 'CLOSE' || row.close) && scaled(row.received) < scaled(receivableQuantity(row.source))
    const differenceReason = [row.difference.trim(), closing ? closeReason.value.trim() : ''].filter(Boolean).join('；')
    return { ...common(row),
      ...(row.source.source_type === 'AD_HOC_REVIEW' && scaled(row.received) > 0n && scaled(row.rejected) === scaled(row.received) ? { no_order_decision: 'WRONG_DELIVERY' as const } : {}),
      paper_quality: row.source.paper_quality, specification: row.source.specification,
      dimension_unit: row.source.dimension_unit === 'in' || row.source.dimension_unit === 'inch' ? 'in' as const : 'cm' as const,
      difference_reason: differenceReason }
  })
  if (formalLines.some(line => line.difference_reason.length > 1000)) {
    error.value = '差异说明与短送结案原因合计不能超过 1000 字。'; return
  }
  const payload = { factory_id: props.group.factory_id, expected_revision: props.group.revision, acceptance_date: date.value, special,
    ...(formalLines.length && props.group.formal ? { formal: { expected_revision: props.group.formal.revision, remaining_action: remainingAction.value, split_confirmation: splitConfirmation.value, new_delivery_confirmation: newDeliveryConfirmed.value, correction_reason: correctionReason.value.trim(),
       lines: formalLines } } : {}) }
  const signature = JSON.stringify(payload)
  try { if (!attempts.has(signature)) attempts.set(signature, createRandomUuid()) }
  catch (cause) { error.value = getApiErrorMessage(cause); return }
  const token = generation; busy.value = true
  const closesRemainder = receiptEntries.value.some(entry => entry.closing && entry.remaining > 0n)
  const hasInbound = chosen.some(row => effective(row) > 0n)
  try {
    await api.receive(props.group.id, { ...payload, request_id: attempts.get(signature) }, controller.signal)
    if (token !== generation) return
    attempts.delete(signature)
    editing.value = false
    message.value = closesRemainder ? '本批验收已记录。所选送货余量已结案，采购欠数保留。'
      : hasInbound ? '本批验收已记录。按供应商原价入库，缺价明细等待补价。' : '本批验收已记录，有效入库 0。'
    emit('changed')
  }
  catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) busy.value = false }
}
async function download(line: UnifiedDeliveryLine) {
  if (!line.special_request_id || !line.mark_attachment_id) return
  const token = generation
  try { const blob = await cartonSpecialRequestsApi.download(props.group.factory_id, line.special_request_id, line.mark_attachment_id, props.supplier, controller.signal); if (token !== generation) return
    const file = props.group.special.find(item => item.id === line.special_request_id)?.attachments.find(item => item.id === line.mark_attachment_id)
    const url = URL.createObjectURL(blob), anchor = document.createElement('a'); anchor.href = url; anchor.download = file?.filename || '本批箱唛'; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
}
</script>
<template>
  <article class="unified-receipt min-w-0 space-y-3 border-t py-4 [overflow-wrap:anywhere]" :data-testid="`unified-delivery-${group.id}`" :aria-label="`送货单 ${group.delivery_note_no}`">
    <div class="flex flex-wrap items-center justify-between gap-3"><div v-if="!reopenOnly" class="min-w-0"><h3 class="font-bold">{{ group.delivery_note_no }} · {{ group.delivery_date }}</h3><p class="mt-1 text-xs text-slate-500">{{ group.lines.length }} 条纸品 · <slot name="receipt-status">{{ receiptStatus }}</slot></p></div><div v-if="!supplier" class="flex flex-wrap gap-2"><Button v-if="canReceive && closedLines.length && !reopening" size="sm" variant="outline" :disabled="busy" @click="openReopening">恢复原单待收</Button><Button v-if="canReceive && pending && !editing && !reopening && !reopenOnly" size="sm" :disabled="busy" @click="open">{{ group.requires_correction ? '更正原单验收' : '核实实际收到' }}</Button></div></div>
    <component :is="collapsible ? 'details' : 'div'" :key="viewerKey" class="space-y-3">
    <summary v-if="collapsible" :aria-label="`送货单明细 ${group.delivery_note_no}`" class="w-fit cursor-pointer rounded-lg border border-teal-200 bg-teal-50 px-3 py-2 text-xs font-semibold text-teal-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700">送货单明细</summary>
    <p v-if="error && !editing" role="alert" class="rounded-lg bg-red-50 p-3 text-xs text-red-700">{{ error }}</p><p v-if="message" role="status" class="text-xs text-teal-700">{{ message }}</p>
    <div v-show="!reopenOnly" v-for="line in group.lines" :key="line.id" class="rounded-lg bg-slate-50 p-3 text-xs"><p class="font-semibold">{{ businessLabel(line) }} · {{ line.order_no }} · {{ line.packaging_type }} · {{ line.paper_quality }} · {{ line.specification }} {{ line.dimension_unit }}</p><p v-if="line.customer_name || line.contract_no || line.item_no" class="mt-1 break-words">{{ line.customer_name }} · 合同 {{ line.contract_no || '未填写' }} · PO {{ line.customer_po || '未填写' }} · 货号 {{ line.item_no || '未填写' }}</p><CartonSourceLinks :factory-id="group.factory_id" :sources="sources(line)" :supplier="supplier" :receiving="!supplier" :marks="!supplier && group.special.find(item => item.id === line.special_request_id)?.permissions.can_view_order_resources !== false" /><p class="mt-1">发货 {{ displayQuantity(line.quantity) }} {{ line.unit }} · 到货 {{ displayQuantity(line.received_quantity) }} · 拒收退回 {{ displayQuantity(line.rejected_quantity) }} · 破损 {{ displayQuantity(line.damaged_quantity) }} · 其他不可用 {{ displayQuantity(line.unusable_quantity) }} · 实际入库 {{ inboundLabel(line) }} · 待收 {{ displayQuantity(line.receivable_quantity ?? line.remaining_quantity) }} · 已结束余量 {{ displayQuantity(line.closed_quantity) }} · 供应商原价 {{ originalPrice(line) == null ? '未填写（待核价）' : `${line.currency || 'CNY'} ${originalPrice(line)}` }}</p><p v-if="whollyRejected(line)" class="mt-1 font-semibold text-red-700">此项已全部拒收退回，入库 0，不计货款。</p><p v-if="line.source_origin === 'WAREHOUSE_MANUAL'" class="mt-1 text-amber-800">仓库代录 · 记录单价 {{ line.warehouse_unit_price == null ? '未填写' : line.warehouse_unit_price }} · 待双方核价</p><p v-if="originalPrice(line) != null && Number(originalPrice(line)) === 0" class="mt-1 font-semibold text-amber-800">{{ line.free_confirmed ? '供应商已明确本行免费，请核实实物。' : '原单价为 0，但未明确声明免费，等待供应商确认；可先收货，仓库不修改原价。' }}</p><Button v-if="line.mark_attachment_id && group.special.find(item => item.id === line.special_request_id)?.permissions.can_view_order_resources !== false" size="sm" variant="ghost" :disabled="busy" @click="download(line)">查看本批箱唛</Button><span v-else-if="line.source_kind === 'SPECIAL'" class="mt-1 block text-slate-500">{{ line.mark_mode === 'NONE' ? '无需箱唛 / 空白箱' : '原批资料待核实' }}</span></div>
    <form v-if="reopening && receiptAuthority" class="space-y-3 rounded-xl border border-amber-200 p-4" aria-label="重开短送余量" @submit.prevent="submitReopening"><p class="text-xs text-slate-600">只更正本原单误关闭、真正未到货的余量，恢复待收，不增加库存或应付。已到货但损坏或不合格的数量不能在这里重开；相关月份已确认对账时须先由内部说明原因重核。</p><fieldset v-for="row in reopenRows" :key="row.source.id" :disabled="busy" class="grid gap-3 rounded-lg border p-3 sm:grid-cols-2"><label class="flex items-center gap-2"><input v-model="row.selected" type="checkbox" :aria-label="`${row.source.id}选择重开`" class="!m-0 !min-h-0 !w-4">{{ row.source.packaging_type }} · {{ row.source.specification }} · 已结束 {{ row.source.closed_quantity }} {{ row.source.unit }}</label><label>本次重开数量<input v-model="row.quantity" :aria-label="`${row.source.id}重开数量`" :disabled="!row.selected" inputmode="decimal"></label></fieldset><label>更正原因<input v-model="reopenReason" aria-label="重开短送原因" :disabled="busy" minlength="4" required></label><div class="flex flex-wrap gap-2"><Button :disabled="readBlocked || busy">{{ busy ? '正在保存…' : '确认恢复待收' }}</Button><Button type="button" variant="outline" :disabled="busy" @click="reopening = false">返回</Button></div></form>
    <div v-if="editing && receiptAuthority" :class="{ 'fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40': mobile }">
    <form ref="receiptForm" :role="mobile ? 'dialog' : undefined" :aria-modal="mobile ? true : undefined" :tabindex="mobile ? -1 : undefined" :class="mobile ? 'carton-phone-dialog carton-phone-receipt flex w-full max-w-xl flex-col bg-white' : 'rounded-xl border border-teal-200 p-3 sm:p-4'" aria-label="统一送货验收" @submit.prevent="submit" @keydown.esc="mobile && !busy && (editing = false)">
      <h2 v-if="mobile" class="shrink-0 break-words border-b px-4 py-3 text-lg font-bold">验收 {{ group.delivery_note_no }}</h2>
      <div class="space-y-4" :class="{ 'carton-phone-receipt-body flex-1 p-4': mobile }">
      <div v-if="focusedPaperIds" class="rounded-lg border border-teal-200 bg-teal-50 p-3 text-sm">
        <p class="break-words"><strong>原送货单 {{ group.delivery_note_no }}</strong> · 本次核实所选纸品，尚未核实的其他纸品继续待收。</p>
        <p v-if="!focusedPaperAvailable" tabindex="-1" data-receipt-entry-waiting>所选纸品须等当前原单更正完成后再收料。</p>
        <button type="button" class="mt-2 font-semibold text-teal-800 underline" :disabled="busy" @click="showWholeReceipt">查看整张送货单</button>
      </div>
      <div class="grid gap-3 sm:grid-cols-2">
        <label>实际验收日期<input v-model="date" type="date" aria-label="统一验收日期" :disabled="busy" required></label>
        <label v-if="correctsFormalReceipt">更正原因<input v-model="correctionReason" :disabled="busy" required></label>
      </div>
      <section v-for="request in group.special.filter(item => item.origin === 'SUPPLIER_EXTRA' && (!focusedPaperIds || editableRows.some(row => row.source.special_request_id === item.id)))" :key="request.id" class="grid gap-3 rounded-lg bg-amber-50 p-3 sm:grid-cols-3"><label>额外纸品用途<select v-model="extra[request.id]!.kind" :aria-label="`${request.id}额外用途`" :disabled="busy"><option value="">选择入库类型</option><option value="SAMPLE">样板</option><option value="WORKSHOP_MISC">杂单</option></select></label></section>
      <fieldset v-for="{ row, inbound, quantityValid, missingLocation } in receiptEntries" :key="row.source.id" :disabled="busy" class="min-w-0 space-y-3 rounded-lg border p-3">
        <legend class="px-1 text-sm font-semibold">{{ row.source.packaging_type }} · {{ row.source.specification }}</legend>
        <p class="break-words text-xs text-slate-600">客户 {{ row.source.customer_name || '未填写' }}<template v-if="row.source.contract_no"> · 合同 {{ row.source.contract_no }}</template> · 订单 {{ row.source.order_no || '未关联' }} · 货号 {{ row.source.item_no || '未填写' }}</p>
        <div class="grid items-end gap-3 sm:grid-cols-2">
          <div>
            <p class="text-xs text-slate-600">原单待收 <strong class="tabular-nums">{{ displayQuantity(receivableQuantity(row.source)) }} {{ row.source.unit }}</strong></p>
            <div class="mt-2 flex flex-wrap items-end gap-2">
              <label class="flex-1 basis-24">本批实到（{{ row.source.unit }}）
                <input v-model.trim="row.received" :data-receipt-entry-focus="focusedPaperIds ? '' : undefined" :aria-label="row.source.id + '实收'" inputmode="decimal" placeholder="按实物填写">
              </label>
              <Button type="button" size="sm" variant="outline" :aria-label="row.source.id + '按余量全收'" @click="row.received = receivableQuantity(row.source)">按余量全收</Button>
            </div>
          </div>
          <component :is="mobile ? 'details' : 'div'" :class="{ 'rounded-lg border px-3 py-1': mobile }">
          <summary v-if="mobile" class="flex cursor-pointer items-center text-xs font-semibold text-teal-800">查看供应商单价</summary>
          <label>供应商单价 {{ row.source.currency || 'CNY' }}
            <input :value="row.price" :aria-label="row.source.id + '供应商单价'" readonly placeholder="未填写（待核价）">
            <span class="mt-1 block text-xs text-slate-500">{{ row.action === 'PENDING' ? originalPrice(row.source) == null ? '原单未填写单价，可先入库，等待供应商补价' : '原单单价为0，未确认免费，等待供应商核实' : row.action === 'FREE' ? '供应商已明确确认免费' : '按供应商送货原价入库' }}</span>
          </label>
          </component>
        </div>
        <details class="rounded-lg border px-3 py-2">
          <summary class="cursor-pointer text-sm font-semibold text-teal-800" :aria-label="row.source.id + '填写验收差异'">
            破损、拒收及其他差异<span v-if="scaled(row.damaged) || scaled(row.rejected) || scaled(row.unusable) || row.difference" class="ml-2 text-xs font-normal text-amber-800">已填写</span>
          </summary>
          <div class="mt-3 grid gap-3 sm:grid-cols-3">
            <label>破损<input v-model.trim="row.damaged" :aria-label="row.source.id + '破损'" inputmode="decimal"></label>
            <label>拒收<input v-model.trim="row.rejected" :aria-label="row.source.id + '拒收'" inputmode="decimal"></label>
            <label>其他不可用<input v-model.trim="row.unusable" :aria-label="row.source.id + '不可用'" inputmode="decimal"></label>
            <label v-if="row.source.source_kind === 'FORMAL'" class="sm:col-span-3">收货差异说明
              <input v-model="row.difference" :aria-required="effective(row) !== scaled(row.received)" :aria-label="row.source.id + '差异说明'" maxlength="1000" placeholder="破损、拒收等情况请说明">
            </label>
          </div>
        </details>
        <div v-show="quantityValid && inbound > 0n" class="space-y-1">
          <p class="text-xs font-semibold">入库仓位</p>
          <CartonReceiptAllocations v-model="row.allocations" :mobile="mobile" :effective="quantityValid ? Number(decimal(inbound)) : 0" :locations="locations" :factory-id="group.factory_id" :disabled="busy" class="!min-w-0 [&>div]:flex-wrap" @created="emit('locations-changed')" />
          <p v-if="missingLocation" class="text-xs text-amber-800">请选择入库仓位。</p>
        </div>
      </fieldset>
      <details v-if="receiptEntries.length" class="rounded-lg border px-3 py-2">
        <summary class="cursor-pointer text-sm font-semibold text-teal-800" aria-label="短送结案选项">短送结案
          <span class="ml-2 text-xs font-normal text-slate-600">{{ closingShortfall ? '已选择结案' : '余货继续待收' }}</span>
        </summary>
        <div class="mt-3 space-y-3">
          <p class="text-xs text-slate-600">只结案本送货单的未到余量，采购欠数保留。实物未到的纸品，本批实到填 0。</p>
          <label v-if="!focusedPaperIds">未收余货
            <select v-model="remainingAction" aria-label="统一未收余货处理" :disabled="busy">
              <option value="WAIT">余货继续待收</option>
              <option value="CLOSE">整张送货单短送结案</option>
            </select>
          </label>
          <label v-for="{ row } in receiptEntries" :key="row.source.id" class="!flex items-start gap-2">
            <input v-model="row.close" type="checkbox" :aria-label="row.source.id + '关闭此纸品余量'" class="!m-0 !min-h-0 !w-4" :disabled="busy || remainingAction === 'CLOSE'">
            {{ row.source.packaging_type }} · {{ row.source.specification }} · {{ row.source.order_no }} · 此纸品短送结案
          </label>
        </div>
      </details>
      <label v-if="closingShortfall">短送结案原因（必填）
        <input v-model="closeReason" aria-label="统一短送结束原因" :disabled="busy" minlength="4" maxlength="1000" required placeholder="填写至少四字原因">
      </label>
      <CartonSplitReceiptReview v-if="hasSplits" :factory="group.factory_id" :lines="splitLines" @update:confirmation="splitConfirmation = $event" />
      <p v-if="candidateLoading" class="text-xs">正在检查原收料记录…</p><p v-if="candidateError" role="alert" class="text-xs text-red-700">{{ candidateError }}<button type="button" class="ml-2 underline" @click="checkCandidates">重试</button></p><div v-if="usesFormalReceipt && group.formal && (candidates.length || group.formal.requires_receipt_link)" class="rounded-lg bg-amber-50 p-3 text-xs"><p>原收料可能已入库，后补凭证须关联原记录，避免重复记账。</p><Button type="button" variant="outline" size="sm" :disabled="busy" @click="emit('link-receipt', group.formal)">关联原收料</Button><label v-if="!group.formal.requires_receipt_link" class="mt-2 flex items-center gap-2"><input v-model="newDeliveryConfirmed" type="checkbox" class="!m-0 !min-h-0 !w-4">已核对，这是新一批实际到货</label></div>
      </div>
      <div class="space-y-2 border-t pt-3" :class="mobile ? 'carton-phone-footer shrink-0 px-4' : 'mt-4'">
        <CartonMobileReceiptTotals v-if="mobile" :rows="mobileReceiptTotals" />
        <section v-else-if="receiptSummary.length" aria-label="本批验收汇总" aria-live="polite" class="space-y-2">
          <div v-for="entry in receiptSummary" :key="entry.row.source.id" class="rounded-lg bg-muted/60 px-3 py-2 text-xs">
            <p class="mb-1 font-semibold">{{ entry.row.source.packaging_type }} · {{ entry.row.source.specification }} · {{ entry.row.source.order_no }}</p>
            <dl class="flex flex-wrap gap-x-5 gap-y-1 tabular-nums">
              <div class="flex items-baseline gap-1">
                <dt>本批有效入库</dt>
                <dd class="font-semibold">{{ entry.quantityValid && entry.entered ? displayReceiptQuantity(entry.inbound) + ' ' + entry.row.source.unit : '—' }}</dd>
              </div>
              <div class="flex items-baseline gap-1">
                <dt>原单继续待收</dt>
                <dd class="font-semibold">{{ entry.quantityValid && entry.entered ? displayReceiptQuantity(entry.closing ? 0n : entry.remaining) + ' ' + entry.row.source.unit : '—' }}</dd>
              </div>
              <div v-if="entry.closing && entry.quantityValid && entry.entered && entry.remaining > 0n" class="flex items-baseline gap-1 text-amber-800">
                <dt>本次短送结案</dt><dd class="font-semibold">{{ displayReceiptQuantity(entry.remaining) }} {{ entry.row.source.unit }}</dd>
              </div>
            </dl>
          </div>
        </section>
        <p v-if="error" role="alert" class="rounded-lg bg-red-50 p-3 text-xs text-red-700">{{ error }}</p>
        <p v-if="receiptProblem && focusedPaperAvailable" class="text-xs text-slate-600" role="status">{{ receiptProblem }}</p>
        <div class="flex flex-wrap gap-2" :class="{ '[&>button:first-child]:flex-1': mobile }">
          <Button type="submit" :disabled="readBlocked || busy || !focusedPaperAvailable || candidateLoading || !!candidateError || !!receiptProblem">
            {{ busy ? '正在保存…' : closingShortfall ? '确认验收并结案' : '确认本次收货' }}
          </Button>
          <Button type="button" variant="outline" :disabled="busy" @click="editing = false">返回</Button>
        </div>
      </div>
    </form>
    </div>
    <details v-if="closureNotes.length && !reopenOnly" class="text-xs"><summary class="cursor-pointer font-semibold">送货核对与短送结束说明</summary><p v-for="(note, index) in closureNotes" :key="index" class="mt-2">{{ note }}</p></details>
    <details v-if="group.shortfall_reopen_history?.length" class="text-xs"><summary class="cursor-pointer font-semibold">短送重开记录</summary><p v-for="(item, index) in group.shortfall_reopen_history" :key="index" class="mt-2">{{ item.created_at }} · {{ item.reason }} · 仅恢复原单待收</p></details>
    <details v-if="receiptHistory.length && !reopenOnly" class="text-xs">
      <summary class="cursor-pointer font-semibold">验收记录（{{ receiptHistory.length }}）</summary>
      <p v-for="(receipt, index) in receiptHistory" :key="receipt.id || receipt.receipt_id || index" class="mt-2">
        {{ receipt.receipt_no || '验收记录' }} · {{ receipt.acceptance_date || '日期未记录' }} · {{ receipt.status === 'REVERSED' ? '已冲销' : receipt.status === 'NOT_RECEIVED' ? '仓库未收到' : receipt.status === 'POSTED' ? '已入库' : '已核实' }}
        <Button v-if="canReceive && receipt.status === 'POSTED' && (receipt.id || receipt.receipt_id)" variant="ghost" size="sm" :disabled="busy" @click="emit('reverse', (receipt.id || receipt.receipt_id)!)">冲销本次入库</Button>
      </p>
    </details>
    </component>
  </article>
</template>
<style scoped>
.unified-receipt label { display:block; min-width:0; font-size:12px; font-weight:600; }
.unified-receipt input,.unified-receipt select { display:block; min-width:0; width:100%; min-height:38px; margin-top:6px; border:1px solid var(--input); border-radius:10px; padding:8px 10px; background:var(--card); font-weight:400; }
.unified-receipt .carton-phone-receipt :is(input:not([type=checkbox]):not([type=radio]), select, textarea) { min-height:44px; font-size:16px; }
</style>
