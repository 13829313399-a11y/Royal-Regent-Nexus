<script setup lang="ts">
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
const props = withDefaults(defineProps<{ group: UnifiedDelivery; supplier?: boolean; canReceive?: boolean; autoOpen?: boolean; locations?: CartonLocation[]; workshops?: { id: string; name: string }[]; viewerKey?: string; orders?: PortalOrder[] }>(), { locations: () => [], workshops: () => [], orders: () => [] })
const emit = defineEmits<{ changed: []; reverse: [receiptId: string]; 'link-receipt': [shipment: PortalShipment]; 'locations-changed': [] }>()
interface Row { source: UnifiedDeliveryLine; received: string; damaged: string; rejected: string; unusable: string; allocations: LocationAllocation[]; action: PriceAction; price: string; reason: string; difference: string }
const editing = ref(false), busy = ref(false), error = ref(''), message = ref(''), rows = ref<Row[]>([])
const date = ref(''), correctionReason = ref(''), splitConfirmation = ref('')
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
const extra = ref<Record<string, { kind: 'SAMPLE' | 'WORKSHOP_MISC'; requester: string; workshop: string }>>({})
let generation = 0, controller = new AbortController()
const attempts = new Map<string, string>()
const canReceive = computed(() => !props.supplier && props.canReceive && props.group.can_operate)
const pending = computed(() => props.group.lines.some(line => Number(line.receivable_quantity ?? line.remaining_quantity ?? 0) > 0))
const businessLabel = (line: UnifiedDeliveryLine) => ({ REGULAR: '正单', SAMPLE: '样板', MISC: '杂单', UNKNOWN: line.origin === 'SUPPLIER_EXTRA' ? '额外送货 · 待核对用途' : '历史或无单' })[unifiedDeliveryLineKind(props.group, line)]
const originalPrice = (line: UnifiedDeliveryLine) => line.delivery_unit_price == null || line.delivery_unit_price === '' ? null : line.delivery_unit_price
const valid = (value: string, digits = 4) => new RegExp(`^\\d{1,14}(\\.\\d{1,${digits}})?$`).test(value)
const scaled = (value: string) => { if (!valid(value)) return 0n; const [whole = '0', fraction = ''] = value.split('.'); return BigInt(whole) * 10000n + BigInt(fraction.padEnd(4, '0')) }
const decimal = (value: bigint) => `${value / 10000n}.${(value % 10000n).toString().padStart(4, '0')}`
const effective = (row: Row) => scaled(row.received) - scaled(row.damaged) - scaled(row.rejected) - scaled(row.unusable)
function reset() { generation++; controller.abort(); controller = new AbortController(); editing.value = false; busy.value = false; error.value = ''; message.value = ''; rows.value = []; candidates.value = []; candidateError.value = ''; candidateLoading.value = false; newDeliveryConfirmed.value = false; splitConfirmation.value = ''; attempts.clear() }
watch(() => [props.group.factory_id, props.group.id, props.group.revision, props.viewerKey, props.supplier, props.canReceive], reset, { flush: 'sync' })
onBeforeUnmount(() => { generation++; controller.abort() })
watch(() => [props.autoOpen, props.group.id, props.viewerKey, canReceive.value], () => {
  if (props.autoOpen && canReceive.value && pending.value) open()
}, { immediate: true, flush: 'post' })
function sources(line: UnifiedDeliveryLine) {
  const request = props.group.special.find(row => row.id === line.special_request_id)
  return request ? [{ id: request.id, request_no: request.request_no, kind: request.kind, line_id: line.original_special_line_id }] : []
}
function open() {
  if (!canReceive.value || busy.value) return
  error.value = ''; message.value = ''; editing.value = true; date.value = formatBusinessDate(new Date().toISOString()); correctionReason.value = ''; newDeliveryConfirmed.value = false; splitConfirmation.value = ''; void checkCandidates()
  rows.value = props.group.lines.filter(line => line.source_kind === 'FORMAL' || Number(line.receivable_quantity ?? line.remaining_quantity ?? 0) > 0).map(source => ({ source,
    received: source.receivable_quantity ?? source.remaining_quantity ?? '0', damaged: '0', rejected: '0', unusable: '0', allocations: [],
    action: originalPrice(source) == null ? 'PENDING' : Number(originalPrice(source)) === 0 ? source.free_confirmed ? 'FREE' : 'PENDING' : 'MATCH', price: originalPrice(source) ?? '', reason: '', difference: '' }))
  extra.value = Object.fromEntries(props.group.special.filter(item => item.origin === 'SUPPLIER_EXTRA').map(item => [item.id, { kind: 'WORKSHOP_MISC', requester: item.requester_name || '', workshop: item.workshop_id || '' }]))
}
function changePrice(row: Row) { if (row.action === 'FREE') row.price = '0'; else if (row.action === 'MATCH') row.price = originalPrice(row.source) ?? '' }
async function submit() {
  if (!canReceive.value || busy.value) return
  error.value = ''
  if (props.group.formal && (candidateLoading.value || candidateError.value)) { error.value = '请先完成原收料重复检查，失败时点击重试。'; return }
  if (props.group.formal?.requires_receipt_link || candidates.value.length && !newDeliveryConfirmed.value) { error.value = '请关联原收料，或核对本次确为新一批到货。'; return }
  const chosen = rows.value.filter(row => scaled(row.received) > 0n)
  if (!date.value || !chosen.length || rows.value.some(row => [row.received, row.damaged, row.rejected, row.unusable].some(value => !valid(value)) || effective(row) < 0n || scaled(row.received) > scaled(row.source.receivable_quantity ?? row.source.remaining_quantity ?? '0'))) { error.value = '请核对验收日期、实收和不合格数量，实收不能超过待收。'; return }
  if (chosen.some(row => effective(row) > 0n && (!row.allocations.length || row.allocations.some(part => !valid(String(part.quantity)) || scaled(String(part.quantity)) <= 0n || !props.locations.some(location => location.id === part.location_id && location.status !== 'INACTIVE')) || new Set(row.allocations.map(part => part.location_id)).size !== row.allocations.length || row.allocations.reduce((sum, part) => sum + scaled(String(part.quantity)), 0n) !== effective(row)))) { error.value = '请核对本厂仓位及分仓数量，合计须等于有效入库，仓位不能重复。'; return }
  if (chosen.some(row => effective(row) > 0n && (row.action !== 'PENDING' && !valid(row.price, 6) || ['PROPOSE', 'PENDING'].includes(row.action) && !row.reason.trim()))) { error.value = '请核对价格；待核价或更正价格须填写原因。'; return }
  if (chosen.some(row => effective(row) > 0n && (row.action === 'PROPOSE' || row.action === 'FREE' && !(Number(originalPrice(row.source)) === 0 && row.source.free_confirmed)) && row.reason.trim().length < 4)) { error.value = '变更原价或补认免费须填写至少四字原因，由双方核实。'; return }
  if (props.group.requires_correction && props.group.formal && correctionReason.value.trim().length < 4) { error.value = '冲销后重新验收须填写至少四字更正原因。'; return }
  const common = (row: Row) => ({ shipment_line_id: row.source.id, received_quantity: row.received, damaged_quantity: row.damaged, rejected_quantity: row.rejected, unusable_quantity: row.unusable,
    location_allocations: effective(row) > 0n ? row.allocations : [],
    price_action: row.action, price_reason: row.reason.trim(), unit_price: row.action === 'PENDING' ? originalPrice(row.source) ?? '0' : row.price,
    ...(row.action === 'FREE' || row.action === 'PROPOSE' && Number(row.price) === 0 ? { zero_price_kind: 'FREE' } : {}) })
  const special = props.group.special.flatMap(request => request.shipments.flatMap(shipment => {
    const groupRows = chosen.filter(row => row.source.special_shipment_id === shipment.id)
    if (!groupRows.length) return []
    const extraChoice = extra.value[request.id]
    return [{ request_id: request.id, shipment_id: shipment.id, expected_revision: request.revision, lines: groupRows.map(common),
      ...(extraChoice ? { received_kind: extraChoice.kind, requester_name: extraChoice.requester.trim(), workshop_id: extraChoice.kind === 'WORKSHOP_MISC' ? extraChoice.workshop : '' } : {}) }]
  }))
  if (special.some(item => item.received_kind && (!item.requester_name || item.received_kind === 'WORKSHOP_MISC' && !props.workshops.some(workshop => workshop.id === item.workshop_id)))) { error.value = '额外送货须核对用途、需求人，杂单还须选择车间。'; return }
  const formalRows = chosen.some(row => row.source.source_kind === 'FORMAL') ? rows.value.filter(row => row.source.source_kind === 'FORMAL') : []
  const payload = { factory_id: props.group.factory_id, expected_revision: props.group.revision, acceptance_date: date.value, special,
    ...(formalRows.length && props.group.formal ? { formal: { expected_revision: props.group.formal.revision, remaining_action: 'WAIT', split_confirmation: splitConfirmation.value, new_delivery_confirmation: newDeliveryConfirmed.value, correction_reason: correctionReason.value.trim(),
      lines: formalRows.map(row => ({ ...common(row), paper_quality: row.source.paper_quality, specification: row.source.specification, dimension_unit: row.source.dimension_unit === 'in' || row.source.dimension_unit === 'inch' ? 'in' : 'cm', difference_reason: row.difference })) } } : {}) }
  const signature = JSON.stringify(payload); if (!attempts.has(signature)) attempts.set(signature, crypto.randomUUID())
  const token = generation; busy.value = true
  try { await api.receive(props.group.id, { ...payload, request_id: attempts.get(signature) }, controller.signal); if (token === generation) { attempts.delete(signature); editing.value = false; message.value = '本次收货已记录；价格异常明细等待双方核实。'; emit('changed') } }
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
    <div class="flex flex-wrap items-center justify-between gap-3"><div><h3 class="font-bold">{{ group.delivery_note_no }} · {{ group.delivery_date }}</h3><p class="mt-1 text-xs text-slate-500">{{ group.lines.length }} 条纸品 · {{ pending ? '待核实实际收货' : '已核实' }}</p></div><Button v-if="canReceive && pending && !editing" size="sm" :disabled="busy" @click="open">{{ group.requires_correction ? '更正原单验收' : '核实实际收到' }}</Button></div>
    <p v-if="error" role="alert" class="rounded-lg bg-red-50 p-3 text-xs text-red-700">{{ error }}</p><p v-if="message" role="status" class="text-xs text-teal-700">{{ message }}</p>
    <div v-for="line in group.lines" :key="line.id" class="rounded-lg bg-slate-50 p-3 text-xs"><p class="font-semibold">{{ businessLabel(line) }} · {{ line.order_no }} · {{ line.packaging_type }} · {{ line.paper_quality }} · {{ line.specification }} {{ line.dimension_unit }}</p><p v-if="line.customer_name || line.contract_no || line.item_no" class="mt-1 break-words">{{ line.customer_name }} · 合同 {{ line.contract_no || '未填写' }} · PO {{ line.customer_po || '未填写' }} · 货号 {{ line.item_no || '未填写' }}</p><CartonSourceLinks :factory-id="group.factory_id" :sources="sources(line)" :supplier="supplier" :marks="!supplier" /><p class="mt-1">发货 {{ line.quantity }} {{ line.unit }} · 实收 {{ line.received_quantity || '0' }} · 待收 {{ line.receivable_quantity ?? line.remaining_quantity ?? '0' }} · 供应商原价 {{ originalPrice(line) == null ? '待核实' : `${line.currency || 'CNY'} ${originalPrice(line)}` }}</p><p v-if="line.source_origin === 'WAREHOUSE_MANUAL'" class="mt-1 text-amber-800">仓库代录 · 记录单价 {{ line.warehouse_unit_price == null ? '未填写' : line.warehouse_unit_price }} · 待双方核价</p><p v-if="originalPrice(line) != null && Number(originalPrice(line)) === 0" class="mt-1 font-semibold text-amber-800">{{ line.free_confirmed ? '供应商已明确本行免费，请核实实物。' : '原单价为 0，但未明确声明免费，默认待核价；可先收货，核实后选择免费或提出价格更正。' }}</p><Button v-if="line.mark_attachment_id" size="sm" variant="ghost" :disabled="busy" @click="download(line)">查看本批箱唛</Button><span v-else-if="line.source_kind === 'SPECIAL'" class="mt-1 block text-slate-500">{{ line.mark_mode === 'NONE' ? '无需箱唛 / 空白箱' : '原批资料待核实' }}</span></div>
    <form v-if="editing && canReceive" class="space-y-3 rounded-xl border border-teal-200 p-4" aria-label="统一送货验收" @submit.prevent="submit"><label>实际验收日期<input v-model="date" type="date" aria-label="统一验收日期" :disabled="busy" required></label><label v-if="group.requires_correction && group.formal">更正原因<input v-model="correctionReason" :disabled="busy" required></label>
      <section v-for="request in group.special.filter(item => item.origin === 'SUPPLIER_EXTRA')" :key="request.id" class="grid gap-3 rounded-lg bg-amber-50 p-3 sm:grid-cols-3"><label>额外纸品用途<select v-model="extra[request.id]!.kind" :aria-label="`${request.id}额外用途`" :disabled="busy"><option value="SAMPLE">样板</option><option value="WORKSHOP_MISC">杂单</option></select></label><label>需求人<input v-model="extra[request.id]!.requester" :aria-label="`${request.id}需求人`" :disabled="busy"></label><label v-if="extra[request.id]!.kind === 'WORKSHOP_MISC'">使用车间<select v-model="extra[request.id]!.workshop" :aria-label="`${request.id}车间`" :disabled="busy"><option value="">选择车间</option><option v-for="workshop in workshops" :key="workshop.id" :value="workshop.id">{{ workshop.name }}</option></select></label></section>
      <fieldset v-for="row in rows" :key="row.source.id" :disabled="busy" class="grid gap-3 rounded-lg border p-3 sm:grid-cols-2 lg:grid-cols-4"><legend class="px-1 text-xs font-bold">{{ row.source.packaging_type }} · {{ row.source.specification }}</legend><label>实收<input v-model="row.received" :aria-label="`${row.source.id}实收`" inputmode="decimal"></label><label>破损<input v-model="row.damaged" :aria-label="`${row.source.id}破损`" inputmode="decimal"></label><label>拒收<input v-model="row.rejected" :aria-label="`${row.source.id}拒收`" inputmode="decimal"></label><label>其他不可用<input v-model="row.unusable" :aria-label="`${row.source.id}不可用`" inputmode="decimal"></label><div class="sm:col-span-2"><span class="text-xs font-semibold">仓位 · 有效入库 {{ Number(decimal(effective(row))) }}</span><CartonReceiptAllocations v-model="row.allocations" :effective="Number(decimal(effective(row)))" :locations="locations" :factory-id="group.factory_id" :disabled="busy" @created="emit('locations-changed')" /></div><label>价格核对<select v-model="row.action" :aria-label="`${row.source.id}价格核对`" @change="changePrice(row)"><option v-if="originalPrice(row.source) != null && Number(originalPrice(row.source)) > 0" value="MATCH">与供应商原价一致</option><option value="FREE">确认免费</option><option value="PENDING">价格待核实</option><option value="PROPOSE">提出价格更正</option></select></label><label v-if="row.action === 'PROPOSE'">建议单价<input v-model="row.price" :aria-label="`${row.source.id}建议单价`" inputmode="decimal"></label><label v-if="row.action !== 'MATCH'">价格说明<input v-model="row.reason" :aria-label="`${row.source.id}价格说明`" maxlength="1000" placeholder="说明免费或更正原因"></label><label v-if="row.source.source_kind === 'FORMAL'" class="sm:col-span-2">收货差异说明<input v-model="row.difference" :aria-label="`${row.source.id}差异说明`" placeholder="破损、拒收等情况请说明"></label></fieldset>
      <CartonSplitReceiptReview v-if="hasSplits" :factory="group.factory_id" :lines="splitLines" @update:confirmation="splitConfirmation = $event" />
      <p v-if="candidateLoading" class="text-xs">正在检查原收料记录…</p><p v-if="candidateError" role="alert" class="text-xs text-red-700">{{ candidateError }}<button type="button" class="ml-2 underline" @click="checkCandidates">重试</button></p><div v-if="group.formal && (candidates.length || group.formal.requires_receipt_link)" class="rounded-lg bg-amber-50 p-3 text-xs"><p>原收料可能已入库，后补凭证须关联原记录，避免重复记账。</p><Button type="button" variant="outline" size="sm" :disabled="busy" @click="emit('link-receipt', group.formal)">关联原收料</Button><label v-if="!group.formal.requires_receipt_link" class="mt-2 flex items-center gap-2"><input v-model="newDeliveryConfirmed" type="checkbox" class="!m-0 !min-h-0 !w-4">已核对，这是新一批实际到货</label></div>
      <div class="flex flex-wrap gap-2"><Button :disabled="busy || candidateLoading || !!candidateError">{{ busy ? '正在保存…' : '确认本次收货' }}</Button><Button type="button" variant="outline" :disabled="busy" @click="editing = false">返回</Button></div>
    </form>
    <details v-if="group.receipts.length" class="text-xs"><summary class="cursor-pointer font-semibold">验收记录（{{ group.receipts.length }}）</summary><p v-for="receipt in group.receipts" :key="receipt.id || receipt.receipt_id" class="mt-2">{{ receipt.receipt_no || '入库记录' }} · {{ receipt.acceptance_date }} · {{ receipt.status === 'REVERSED' ? '已冲销' : '已入库' }}<Button v-if="canReceive && receipt.status === 'POSTED' && (receipt.id || receipt.receipt_id)" variant="ghost" size="sm" :disabled="busy" @click="emit('reverse', (receipt.id || receipt.receipt_id)!)">冲销本次入库</Button></p></details>
  </article>
</template>
<style scoped>
.unified-receipt label { display:block; min-width:0; font-size:12px; font-weight:600; }
.unified-receipt input,.unified-receipt select { display:block; min-width:0; width:100%; min-height:38px; margin-top:6px; border:1px solid var(--input); border-radius:10px; padding:8px 10px; background:var(--card); font-weight:400; }
</style>
