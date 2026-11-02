<script setup lang="ts">
import { originalSupplierReceiptPrice, supplierReceiptPrice } from '@/features/carton-procurement/supplierReceiptPrice'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import { cartonUnifiedDeliveriesApi as api, unifiedDeliveryLineKind, type UnifiedDelivery, type UnifiedDeliveryLine, type PriceAction } from '@/api/cartonUnifiedDeliveries'
import { cartonSpecialRequestsApi } from '@/api/cartonSpecialRequests'
import CartonReceiptAllocations from '@/components/CartonReceiptAllocations.vue'
import CartonSourceLinks from '@/components/CartonSourceLinks.vue'
import CartonSplitReceiptReview from '@/components/CartonSplitReceiptReview.vue'
import { cartonSupplierPortalApi, type PortalOrder, type PortalShipment, type ShipmentReceiptOption } from '@/api/cartonSupplierPortal'
import type { CartonLocation, LocationAllocation } from '@/api/cartonPositions'
import { getApiErrorMessage } from '@/lib/http'
import { formatBusinessDate } from '@/lib/dateTime'
import { createRandomUuid } from '@/lib/randomUuid'

const displayQuantity = (value: unknown) => {
  const number = Number(value ?? 0)
  return Number.isFinite(number) ? number.toLocaleString('zh-CN', { maximumFractionDigits: 4 }) : String(value ?? '')
}
const props = withDefaults(defineProps<{ group: UnifiedDelivery; supplier?: boolean; canReceive?: boolean; autoOpen?: boolean; reopenOnly?: boolean; locations?: CartonLocation[]; workshops?: { id: string; name: string }[]; viewerKey?: string; orders?: PortalOrder[] }>(), { locations: () => [], workshops: () => [], orders: () => [] })
const emit = defineEmits<{ changed: []; reverse: [receiptId: string]; 'link-receipt': [shipment: PortalShipment]; 'locations-changed': [] }>()
interface Row { source: UnifiedDeliveryLine; received: string; damaged: string; rejected: string; unusable: string; allocations: LocationAllocation[]; action: PriceAction; price: string; reason: string; difference: string; close: boolean }
const editing = ref(false), busy = ref(false), error = ref(''), message = ref(''), rows = ref<Row[]>([])
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
const splitLines = computed(() => rows.value.flatMap(row => row.source.source_kind === 'FORMAL' && row.source.order_line_id ? [{ order_line_id: row.source.order_line_id, effective_quantity: Number(decimal(effective(row))) }] : []))
const hasSplits = computed(() => splitLines.value.some(line => props.orders.some(order => order.lines.some(paper => paper.id === line.order_line_id) && order.split_records?.some(plan => plan.status !== 'CANCELLED'))))
async function checkCandidates() {
  if (!props.group.formal || props.supplier) return
  const token = generation; candidateLoading.value = true; candidateError.value = ''; candidates.value = []
  try { const result = await cartonSupplierPortalApi.receiptOptions(props.group.factory_id, props.group.formal.id); if (token === generation) candidates.value = result }
  catch (cause) { if (token === generation) candidateError.value = getApiErrorMessage(cause) }
  finally { if (token === generation) candidateLoading.value = false }
}
const extra = ref<Record<string, { kind: '' | 'SAMPLE' | 'WORKSHOP_MISC'; requester: string; workshop: string }>>({})
let generation = 0, controller = new AbortController()
const attempts = new Map<string, string>()
const canReceive = computed(() => !props.supplier && props.canReceive && props.group.can_operate)
const pending = computed(() => props.group.lines.some(line => Number(line.receivable_quantity ?? line.remaining_quantity ?? 0) > 0))
const businessLabel = (line: UnifiedDeliveryLine) => ({ REGULAR: '正单', SAMPLE: '样板', MISC: '杂单', UNKNOWN: line.origin === 'SUPPLIER_EXTRA' ? '额外送货 · 待核对用途' : '历史或无单' })[unifiedDeliveryLineKind(props.group, line)]
const originalPrice = (line: UnifiedDeliveryLine) => originalSupplierReceiptPrice(line)
const valid = (value: string, digits = 4) => new RegExp(`^\\d{1,14}(\\.\\d{1,${digits}})?$`).test(value)
const scaled = (value: string) => { if (!valid(value)) return 0n; const [whole = '0', fraction = ''] = value.split('.'); return BigInt(whole) * 10000n + BigInt(fraction.padEnd(4, '0')) }
const decimal = (value: bigint) => `${value / 10000n}.${(value % 10000n).toString().padStart(4, '0')}`
const effective = (row: Row) => scaled(row.received) - scaled(row.damaged) - scaled(row.rejected) - scaled(row.unusable)
function reset() { generation++; controller.abort(); controller = new AbortController(); editing.value = false; reopening.value = false; reopenReason.value = ''; reopenRows.value = []; busy.value = false; error.value = ''; message.value = ''; rows.value = []; candidates.value = []; candidateError.value = ''; candidateLoading.value = false; newDeliveryConfirmed.value = false; splitConfirmation.value = ''; attempts.clear() }
watch(() => [props.group.factory_id, props.group.id, props.group.revision, props.group.special.map(item => item.revision).join(','), props.viewerKey, props.supplier, props.canReceive], reset, { flush: 'sync' })
onBeforeUnmount(() => { generation++; controller.abort() })
watch(() => [props.autoOpen, props.group.id, props.viewerKey, canReceive.value], () => {
  if (props.autoOpen && canReceive.value && pending.value && !props.reopenOnly) open()
}, { immediate: true, flush: 'post' })
function sources(line: UnifiedDeliveryLine) {
  const request = props.group.special.find(row => row.id === line.special_request_id)
  return request ? [{ id: request.id, request_no: request.request_no, kind: request.kind, line_id: line.original_special_line_id }] : []
}
function open() {
  if (!canReceive.value || busy.value || props.reopenOnly) return
  reopening.value = false
  remainingAction.value = 'WAIT'; closeReason.value = ''
  error.value = ''; message.value = ''; editing.value = true; date.value = formatBusinessDate(new Date().toISOString()); correctionReason.value = ''; newDeliveryConfirmed.value = false; splitConfirmation.value = ''; void checkCandidates()
  rows.value = props.group.lines.filter(line => line.source_kind === 'FORMAL' || Number(line.receivable_quantity ?? line.remaining_quantity ?? 0) > 0).map(source => ({ source,
    received: source.receivable_quantity ?? source.remaining_quantity ?? '0', damaged: '0', rejected: '0', unusable: '0', allocations: [],
    action: originalPrice(source) == null ? 'PENDING' : Number(originalPrice(source)) === 0 ? source.free_confirmed ? 'FREE' : 'PENDING' : 'MATCH', price: originalPrice(source) ?? '', reason: supplierReceiptPrice(source).price_reason, difference: '', close: false }))
  extra.value = Object.fromEntries(props.group.special.filter(item => item.origin === 'SUPPLIER_EXTRA').map(item => [item.id, { kind: item.shipments.some(shipment => shipment.receipts?.some(receipt => receipt.status === 'POSTED')) && item.kind === 'SAMPLE' ? 'SAMPLE' : item.shipments.some(shipment => shipment.receipts?.some(receipt => receipt.status === 'POSTED')) && item.kind === 'WORKSHOP_MISC' ? 'WORKSHOP_MISC' : '', requester: item.requester_name || '', workshop: item.workshop_id || '' }]))
}
const whollyRejected = (line: UnifiedDeliveryLine) => Number(line.received_quantity || 0) > 0 && Number(line.rejected_quantity || 0) === Number(line.received_quantity) && Number(line.effective_quantity || 0) === 0
const allRejected = computed(() => !pending.value && props.group.lines.length > 0 && props.group.lines.every(whollyRejected))
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
    if (token === generation) { attempts.delete(signature); reopening.value = false; message.value = '选中纸品已恢复原单待收，未产生入库或应付；请核实实物后登记。'; emit('changed') }
  } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) busy.value = false }
}
async function submit() {
  if (!canReceive.value || busy.value) return
  error.value = ''
  if (props.group.formal && (candidateLoading.value || candidateError.value)) { error.value = '请先完成原收料重复检查，失败时点击重试。'; return }
  if (props.group.formal?.requires_receipt_link || candidates.value.length && !newDeliveryConfirmed.value) { error.value = '请关联原收料，或核对本次确为新一批到货。'; return }
  const arriving = rows.value.filter(row => scaled(row.received) > 0n)
  const chosen = (remainingAction.value === 'CLOSE' || !arriving.length ? rows.value : rows.value.filter(row => row.close || scaled(row.received) > 0n)).filter(row => Number(row.source.receivable_quantity ?? row.source.remaining_quantity ?? 0) > 0)
  if ((remainingAction.value === 'CLOSE' || rows.value.some(row => row.close)) && closeReason.value.trim().length < 4) { error.value = '短送结束须填写至少四字原因，采购欠数仍保留。'; return }
  if (!date.value || !chosen.length || rows.value.some(row => [row.received, row.damaged, row.rejected, row.unusable].some(value => !valid(value)) || effective(row) < 0n || scaled(row.received) > scaled(row.source.receivable_quantity ?? row.source.remaining_quantity ?? '0'))) { error.value = '请核对验收日期、实收和不合格数量，实收不能超过待收。'; return }
  if (chosen.some(row => effective(row) > 0n && (!row.allocations.length || row.allocations.some(part => !valid(String(part.quantity)) || scaled(String(part.quantity)) <= 0n || !props.locations.some(location => location.id === part.location_id && location.status !== 'INACTIVE')) || new Set(row.allocations.map(part => part.location_id)).size !== row.allocations.length || row.allocations.reduce((sum, part) => sum + scaled(String(part.quantity)), 0n) !== effective(row)))) { error.value = '请核对本厂仓位及分仓数量，合计须等于有效入库，仓位不能重复。'; return }
  if (props.group.requires_correction && props.group.formal && correctionReason.value.trim().length < 4) { error.value = '冲销后重新验收须填写至少四字更正原因。'; return }
  const common = (row: Row) => ({ shipment_line_id: row.source.id, received_quantity: row.received, damaged_quantity: row.damaged, rejected_quantity: row.rejected, unusable_quantity: row.unusable,
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
  const payload = { factory_id: props.group.factory_id, expected_revision: props.group.revision, acceptance_date: date.value, special,
    ...(formalRows.length && props.group.formal ? { formal: { expected_revision: props.group.formal.revision, remaining_action: remainingAction.value, split_confirmation: splitConfirmation.value, new_delivery_confirmation: newDeliveryConfirmed.value, correction_reason: correctionReason.value.trim(),
      lines: formalRows.map(row => ({ ...common(row), ...(row.source.source_type === 'AD_HOC_REVIEW' && scaled(row.received) > 0n && scaled(row.rejected) === scaled(row.received) ? { no_order_decision: 'WRONG_DELIVERY' as const } : {}), paper_quality: row.source.paper_quality, specification: row.source.specification, dimension_unit: row.source.dimension_unit === 'in' || row.source.dimension_unit === 'inch' ? 'in' : 'cm', difference_reason: row.difference || (remainingAction.value === 'CLOSE' || row.close ? closeReason.value.trim() : '') })) } } : {}) }
  const signature = JSON.stringify(payload)
  try { if (!attempts.has(signature)) attempts.set(signature, createRandomUuid()) }
  catch (cause) { error.value = getApiErrorMessage(cause); return }
  const token = generation; busy.value = true
  try { await api.receive(props.group.id, { ...payload, request_id: attempts.get(signature) }, controller.signal); if (token === generation) { attempts.delete(signature); editing.value = false; message.value = '本次收货已记录；按供应商原价入库，缺价明细等待供应商补价。'; emit('changed') } }
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
  <article class="unified-receipt space-y-3 border-t py-4" :data-testid="`unified-delivery-${group.id}`" :aria-label="`送货单 ${group.delivery_note_no}`">
    <div class="flex flex-wrap items-center justify-between gap-3"><div v-if="!reopenOnly"><h3 class="font-bold">{{ group.delivery_note_no }} · {{ group.delivery_date }}</h3><p class="mt-1 text-xs text-slate-500">{{ group.lines.length }} 条纸品 · <slot name="receipt-status">{{ pending ? '待核实实际收货' : allRejected ? '整单已拒收退回 · 入库 0' : '已核实' }}</slot></p></div><div class="flex flex-wrap gap-2"><Button v-if="canReceive && closedLines.length && !reopening" size="sm" variant="outline" :disabled="busy" @click="openReopening">更正短送结束</Button><Button v-if="canReceive && pending && !editing && !reopening && !reopenOnly" size="sm" :disabled="busy" @click="open">{{ group.requires_correction ? '更正原单验收' : '核实实际收到' }}</Button></div></div>
    <p v-if="error" role="alert" class="rounded-lg bg-red-50 p-3 text-xs text-red-700">{{ error }}</p><p v-if="message" role="status" class="text-xs text-teal-700">{{ message }}</p>
    <div v-show="!reopenOnly" v-for="line in group.lines" :key="line.id" class="rounded-lg bg-slate-50 p-3 text-xs"><p class="font-semibold">{{ businessLabel(line) }} · {{ line.order_no }} · {{ line.packaging_type }} · {{ line.paper_quality }} · {{ line.specification }} {{ line.dimension_unit }}</p><p v-if="line.customer_name || line.contract_no || line.item_no" class="mt-1 break-words">{{ line.customer_name }} · 合同 {{ line.contract_no || '未填写' }} · PO {{ line.customer_po || '未填写' }} · 货号 {{ line.item_no || '未填写' }}</p><CartonSourceLinks :factory-id="group.factory_id" :sources="sources(line)" :supplier="supplier" :marks="!supplier" /><p class="mt-1">发货 {{ displayQuantity(line.quantity) }} {{ line.unit }} · 到货 {{ displayQuantity(line.received_quantity) }} · 拒收退回 {{ displayQuantity(line.rejected_quantity) }} · 破损 {{ displayQuantity(line.damaged_quantity) }} · 其他不可用 {{ displayQuantity(line.unusable_quantity) }} · 实际入库 {{ line.effective_quantity == null ? '待核实' : displayQuantity(line.effective_quantity) }} · 待收 {{ displayQuantity(line.receivable_quantity ?? line.remaining_quantity) }} · 已结束余量 {{ displayQuantity(line.closed_quantity) }} · 供应商原价 {{ originalPrice(line) == null ? '待核实' : `${line.currency || 'CNY'} ${originalPrice(line)}` }}</p><p v-if="whollyRejected(line)" class="mt-1 font-semibold text-red-700">此项已全部拒收退回，入库 0，不计货款。</p><p v-if="line.source_origin === 'WAREHOUSE_MANUAL'" class="mt-1 text-amber-800">仓库代录 · 记录单价 {{ line.warehouse_unit_price == null ? '未填写' : line.warehouse_unit_price }} · 待双方核价</p><p v-if="originalPrice(line) != null && Number(originalPrice(line)) === 0" class="mt-1 font-semibold text-amber-800">{{ line.free_confirmed ? '供应商已明确本行免费，请核实实物。' : '原单价为 0，但未明确声明免费，等待供应商确认；可先收货，仓库不修改原价。' }}</p><Button v-if="line.mark_attachment_id" size="sm" variant="ghost" :disabled="busy" @click="download(line)">查看本批箱唛</Button><span v-else-if="line.source_kind === 'SPECIAL'" class="mt-1 block text-slate-500">{{ line.mark_mode === 'NONE' ? '无需箱唛 / 空白箱' : '原批资料待核实' }}</span></div>
    <form v-if="reopening && canReceive" class="space-y-3 rounded-xl border border-amber-200 p-4" aria-label="重开短送余量" @submit.prevent="submitReopening"><p class="text-xs text-slate-600">只更正本原单误关闭、真正未到货的余量，恢复待收，不增加库存或应付。已到货但损坏或不合格的数量不能在这里重开；相关月份已确认对账时须先由内部说明原因重核。</p><fieldset v-for="row in reopenRows" :key="row.source.id" :disabled="busy" class="grid gap-3 rounded-lg border p-3 sm:grid-cols-2"><label class="flex items-center gap-2"><input v-model="row.selected" type="checkbox" :aria-label="`${row.source.id}选择重开`" class="!m-0 !min-h-0 !w-4">{{ row.source.packaging_type }} · {{ row.source.specification }} · 已结束 {{ row.source.closed_quantity }} {{ row.source.unit }}</label><label>本次重开数量<input v-model="row.quantity" :aria-label="`${row.source.id}重开数量`" :disabled="!row.selected" inputmode="decimal"></label></fieldset><label>更正原因<input v-model="reopenReason" aria-label="重开短送原因" :disabled="busy" minlength="4" required></label><div class="flex flex-wrap gap-2"><Button :disabled="busy">{{ busy ? '正在保存…' : '确认恢复待收' }}</Button><Button type="button" variant="outline" :disabled="busy" @click="reopening = false">返回</Button></div></form>
    <form v-if="editing && canReceive" class="space-y-3 rounded-xl border border-teal-200 p-4" aria-label="统一送货验收" @submit.prevent="submit"><label>未收余货<select v-model="remainingAction" aria-label="统一未收余货处理" :disabled="busy"><option value="WAIT">余货继续待收</option><option value="CLOSE">本单短送结束，采购欠数保留</option></select></label><label v-if="remainingAction === 'CLOSE' || rows.some(row => row.close)">短送结束原因<input v-model="closeReason" aria-label="统一短送结束原因" :disabled="busy" minlength="4" required></label><p class="text-xs text-slate-500">短送结束只释放本送货单余量，不修改采购需求。误关闭可按纸品说明原因恢复原单待收；实际入库批次仍沿原批冲销更正。</p><label>实际验收日期<input v-model="date" type="date" aria-label="统一验收日期" :disabled="busy" required></label><label v-if="group.requires_correction && group.formal">更正原因<input v-model="correctionReason" :disabled="busy" required></label>
      <section v-for="request in group.special.filter(item => item.origin === 'SUPPLIER_EXTRA')" :key="request.id" class="grid gap-3 rounded-lg bg-amber-50 p-3 sm:grid-cols-3"><label>额外纸品用途<select v-model="extra[request.id]!.kind" :aria-label="`${request.id}额外用途`" :disabled="busy"><option value="">选择入库类型</option><option value="SAMPLE">样板</option><option value="WORKSHOP_MISC">杂单</option></select></label></section>
      <fieldset v-for="row in rows" :key="row.source.id" :disabled="busy" class="grid gap-3 rounded-lg border p-3 sm:grid-cols-2 lg:grid-cols-4"><legend class="px-1 text-xs font-bold">{{ row.source.packaging_type }} · {{ row.source.specification }}</legend><label class="flex items-center gap-2 sm:col-span-2"><input v-model="row.close" type="checkbox" :aria-label="`${row.source.id}关闭此纸品余量`" class="!m-0 !min-h-0 !w-4" :disabled="remainingAction === 'CLOSE'">此纸品短送结束，其他纸品继续待收</label><label>到货数量<input v-model="row.received" :aria-label="`${row.source.id}实收`" inputmode="decimal"></label><label>破损<input v-model="row.damaged" :aria-label="`${row.source.id}破损`" inputmode="decimal"></label><label>拒收<input v-model="row.rejected" :aria-label="`${row.source.id}拒收`" inputmode="decimal"></label><label>其他不可用<input v-model="row.unusable" :aria-label="`${row.source.id}不可用`" inputmode="decimal"></label><div class="sm:col-span-2"><span class="text-xs font-semibold">仓位 · 有效入库 {{ Number(decimal(effective(row))) }}</span><CartonReceiptAllocations v-model="row.allocations" :effective="Number(decimal(effective(row)))" :locations="locations" :factory-id="group.factory_id" :disabled="busy" @created="emit('locations-changed')" /></div><label>供应商单价 {{ row.source.currency || 'CNY' }}<input :value="row.action === 'PENDING' ? '' : row.price" :aria-label="row.source.id + '供应商单价'" readonly placeholder="待供应商补价"><span class="mt-1 block text-xs text-slate-500">{{ row.action === 'PENDING' ? '缺价或零价未注明免费，可先入库，等待供应商补价' : '按供应商送货原价入库' }}</span></label><label v-if="row.source.source_kind === 'FORMAL'" class="sm:col-span-2">收货差异说明<input v-model="row.difference" :aria-label="`${row.source.id}差异说明`" placeholder="破损、拒收等情况请说明"></label></fieldset>
      <CartonSplitReceiptReview v-if="hasSplits" :factory="group.factory_id" :lines="splitLines" @update:confirmation="splitConfirmation = $event" />
      <p v-if="candidateLoading" class="text-xs">正在检查原收料记录…</p><p v-if="candidateError" role="alert" class="text-xs text-red-700">{{ candidateError }}<button type="button" class="ml-2 underline" @click="checkCandidates">重试</button></p><div v-if="group.formal && (candidates.length || group.formal.requires_receipt_link)" class="rounded-lg bg-amber-50 p-3 text-xs"><p>原收料可能已入库，后补凭证须关联原记录，避免重复记账。</p><Button type="button" variant="outline" size="sm" :disabled="busy" @click="emit('link-receipt', group.formal)">关联原收料</Button><label v-if="!group.formal.requires_receipt_link" class="mt-2 flex items-center gap-2"><input v-model="newDeliveryConfirmed" type="checkbox" class="!m-0 !min-h-0 !w-4">已核对，这是新一批实际到货</label></div>
      <div class="flex flex-wrap gap-2"><Button :disabled="busy || candidateLoading || !!candidateError">{{ busy ? '正在保存…' : '确认本次收货' }}</Button><Button type="button" variant="outline" :disabled="busy" @click="editing = false">返回</Button></div>
    </form>
    <details v-if="closureNotes.length && !reopenOnly" class="text-xs"><summary class="cursor-pointer font-semibold">送货核对与短送结束说明</summary><p v-for="(note, index) in closureNotes" :key="index" class="mt-2">{{ note }}</p></details>
    <details v-if="group.shortfall_reopen_history?.length" class="text-xs"><summary class="cursor-pointer font-semibold">短送重开记录</summary><p v-for="(item, index) in group.shortfall_reopen_history" :key="index" class="mt-2">{{ item.created_at }} · {{ item.reason }} · 仅恢复原单待收</p></details>
    <details v-if="group.receipts.length && !reopenOnly" class="text-xs"><summary class="cursor-pointer font-semibold">验收记录（{{ group.receipts.length }}）</summary><p v-for="receipt in group.receipts" :key="receipt.id || receipt.receipt_id" class="mt-2">{{ receipt.receipt_no || '入库记录' }} · {{ receipt.acceptance_date }} · {{ receipt.status === 'REVERSED' ? '已冲销' : '已入库' }}<Button v-if="canReceive && receipt.status === 'POSTED' && (receipt.id || receipt.receipt_id)" variant="ghost" size="sm" :disabled="busy" @click="emit('reverse', (receipt.id || receipt.receipt_id)!)">冲销本次入库</Button></p></details>
  </article>
</template>
<style scoped>
.unified-receipt label { display:block; min-width:0; font-size:12px; font-weight:600; }
.unified-receipt input,.unified-receipt select { display:block; min-width:0; width:100%; min-height:38px; margin-top:6px; border:1px solid var(--input); border-radius:10px; padding:8px 10px; background:var(--card); font-weight:400; }
</style>
