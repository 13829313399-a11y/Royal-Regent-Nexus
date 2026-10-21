<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import CartonReceiptAllocations from './CartonReceiptAllocations.vue'
import { cartonSpecialRequestsApi as api, type SpecialRequest, type SpecialManualReceipt } from '@/api/cartonSpecialRequests'
import type { CartonLocation, LocationAllocation } from '@/api/cartonPositions'
import { getApiErrorMessage } from '@/lib/http'
import { formatBusinessDate } from '@/lib/dateTime'
const props = defineProps<{ request: SpecialRequest; locations: CartonLocation[]; viewerKey?: string; disabled?: boolean }>()
const emit = defineEmits<{ saved: [SpecialRequest]; cancel: []; 'open-delivery': [string]; 'locations-changed': []; busy: [boolean] }>()
const busy = ref(false), error = ref(''), pendingDelivery = ref(false)
const form = reactive({ delivery_note_no: '', delivery_date: '', acceptance_date: '' })
interface Row { line_id: string; received_quantity: string; damaged_quantity: string; rejected_quantity: string; unusable_quantity: string; unit_price: string; allocations: LocationAllocation[] }
const rows = ref<Row[]>([])
let generation = 0, controller = new AbortController()
const attempts = new Map<string, string>()
const valid = (value: string, digits = 4) => new RegExp(`^\\d{1,14}(\\.\\d{1,${digits}})?$`).test(value)
function scaled(value: string) { if (!valid(value)) return 0n; const [whole = '0', fraction = ''] = value.split('.'); return BigInt(whole) * 10000n + BigInt(fraction.padEnd(4, '0')) }
const decimal = (value: bigint) => `${value / 10000n}.${(value % 10000n).toString().padStart(4, '0')}`
const effective = (row: Row) => scaled(row.received_quantity) - scaled(row.damaged_quantity) - scaled(row.rejected_quantity) - scaled(row.unusable_quantity)
// The shared picker assigns the entire effective quantity when only one bin exists.
// Preserve the exact decimal rather than its display-only Number conversion.
const allocations = (row: Row) => row.allocations.length === 1 ? [{ ...row.allocations[0]!, quantity: decimal(effective(row)) }] : row.allocations
const line = (id: string) => props.request.lines.find(paper => paper.id === id)
const hasPending = computed(() => props.request.shipments.some(shipment => shipment.lines.some(paper => scaled(paper.remaining_quantity) > 0n)))
const allowed = computed(() => props.request.permissions.can_manual_receive && !props.disabled && !hasPending.value && !pendingDelivery.value)
watch([() => props.request.id, () => props.request.factory_id, () => props.viewerKey], () => {
  generation++; controller.abort(); controller = new AbortController(); busy.value = false; emit('busy', false)
  error.value = ''; pendingDelivery.value = false; attempts.clear()
  const today = formatBusinessDate(new Date().toISOString())
  Object.assign(form, { delivery_note_no: '', delivery_date: today, acceptance_date: today })
  rows.value = props.request.lines.filter(paper => paper.id && scaled(paper.remaining_quantity ?? paper.quantity) > 0n).map(paper => ({ line_id: paper.id!, received_quantity: '', damaged_quantity: '0', rejected_quantity: '0', unusable_quantity: '0', unit_price: '', allocations: [] }))
}, { immediate: true })
onBeforeUnmount(() => { generation++; controller.abort() })
async function submit() {
  if (!allowed.value || busy.value) return
  error.value = ''
  const chosen = rows.value.filter(row => row.received_quantity !== '' && scaled(row.received_quantity) > 0n)
  if (!form.delivery_note_no.trim() || !form.delivery_date || !form.acceptance_date || !chosen.length) { error.value = '请填写真实送货单号、送货日期、验收日期，以及本次实际收到的数量。'; return }
  if (rows.value.some(row => row.received_quantity !== '' && !valid(row.received_quantity)) || chosen.some(row => [row.damaged_quantity, row.rejected_quantity, row.unusable_quantity].some(value => !valid(value)) || effective(row) < 0n || scaled(row.received_quantity) > scaled(line(row.line_id)?.remaining_quantity ?? '0'))) { error.value = '请核对数量：实收不能超过剩余需求，不合格合计不能超过实收，最多四位小数。'; return }
  if (chosen.some(row => row.unit_price.trim() && !valid(row.unit_price.trim(), 6))) { error.value = '仓库记录单价可留空；填写时须为非负数，最多六位小数。'; return }
  if (chosen.some(row => effective(row) > 0n && (!row.allocations.length || allocations(row).some(part => !props.locations.some(location => location.id === part.location_id && location.status !== 'INACTIVE') || !valid(String(part.quantity)) || scaled(String(part.quantity)) <= 0n) || new Set(row.allocations.map(part => part.location_id)).size !== row.allocations.length || allocations(row).reduce((sum, part) => sum + scaled(String(part.quantity)), 0n) !== effective(row)))) { error.value = '有效入库须选择本厂仓位，分仓合计须等于有效入库数量。'; return }
  const payload: Omit<SpecialManualReceipt, 'request_id'> = { factory_id: props.request.factory_id, expected_revision: props.request.revision, ...form, delivery_note_no: form.delivery_note_no.trim(),
    lines: chosen.map(row => ({ line_id: row.line_id, received_quantity: row.received_quantity, damaged_quantity: row.damaged_quantity, rejected_quantity: row.rejected_quantity, unusable_quantity: row.unusable_quantity, unit_price: row.unit_price.trim() || null, location_allocations: effective(row) > 0n ? allocations(row).map(part => ({ ...part })) : [] })) }
  const signature = JSON.stringify([props.request.id, payload])
  if (!attempts.has(signature)) attempts.set(signature, crypto.randomUUID())
  const token = generation; busy.value = true; emit('busy', true)
  try {
    const result = await api.manualReceive(props.request.id, { ...payload, request_id: attempts.get(signature)! } as SpecialManualReceipt, controller.signal)
    if (token === generation) { attempts.delete(signature); emit('saved', result) }
  } catch (cause) {
    if (token !== generation) return
    const detail = (cause as { response?: { data?: { detail?: { code?: string; message?: string } } } })?.response?.data?.detail
    if (detail?.code === 'EXISTING_DELIVERY_PENDING') { pendingDelivery.value = true; error.value = detail.message || '已有待收送货单，请沿原单验收。' }
    else error.value = getApiErrorMessage(cause)
  } finally { if (token === generation) { busy.value = false; emit('busy', false) } }
}
</script>
<template>
  <form class="space-y-4 rounded-xl border border-slate-200 bg-white p-4" aria-label="样板杂单手动收料" @submit.prevent="submit">
    <div class="flex flex-wrap items-center justify-between gap-2"><h3 class="text-base font-bold text-slate-950">登记收料 · {{ request.request_no }}</h3><Button type="button" variant="outline" :disabled="busy" @click="emit('cancel')">返回订单</Button></div>
    <p class="text-xs leading-6 text-slate-600">用于已到货但供应商未登记送货的纸品。填写真实送货凭证；本次记录由仓库录入，待供应商核实。单价留空或填写 0 都不会自动视为免费。</p>
    <p v-if="error" role="alert" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
    <div v-if="pendingDelivery || hasPending" class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm"><p>已有待收送货，请核对原单，避免重复入库。</p><Button type="button" class="mt-2" variant="outline" @click="emit('open-delivery', '')">查看待收送货单</Button></div>
    <fieldset :disabled="busy || !allowed" class="space-y-4">
      <div class="grid gap-3 sm:grid-cols-3"><label>真实送货单号 *<input v-model="form.delivery_note_no" aria-label="手动收料送货单号" maxlength="100" required></label><label>送货日期 *<input v-model="form.delivery_date" aria-label="手动收料送货日期" type="date" required></label><label>实际验收日期 *<input v-model="form.acceptance_date" aria-label="手动收料验收日期" type="date" required></label></div>
      <section v-for="row in rows" :key="row.line_id" class="space-y-3 rounded-lg border border-slate-200 p-3">
        <h4 class="text-sm font-semibold">{{ line(row.line_id)?.packaging_type }} · {{ line(row.line_id)?.item_no || '未填写货号' }}</h4>
        <p class="text-xs text-slate-500">{{ line(row.line_id)?.paper_quality }} · {{ line(row.line_id)?.specification }} {{ line(row.line_id)?.dimension_unit }} · 剩余 {{ line(row.line_id)?.remaining_quantity }} {{ line(row.line_id)?.unit }}</p>
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><label>实收数量<input v-model="row.received_quantity" :aria-label="`${row.line_id}手动实收`" inputmode="decimal" placeholder="未到货留空"></label><label>破损<input v-model="row.damaged_quantity" :aria-label="`${row.line_id}手动破损`" inputmode="decimal"></label><label>拒收<input v-model="row.rejected_quantity" :aria-label="`${row.line_id}手动拒收`" inputmode="decimal"></label><label>其他不可用<input v-model="row.unusable_quantity" :aria-label="`${row.line_id}手动不可用`" inputmode="decimal"></label></div>
        <div class="grid gap-3 sm:grid-cols-2"><div><p class="mb-2 text-xs font-semibold">仓位 · 有效入库 {{ decimal(effective(row) < 0n ? 0n : effective(row)) }}</p><CartonReceiptAllocations v-model="row.allocations" :effective="Number(decimal(effective(row) < 0n ? 0n : effective(row)))" :locations="locations" :factory-id="request.factory_id" :disabled="busy || !allowed" @created="emit('locations-changed')" /></div><label>仓库记录单价（选填）<input v-model="row.unit_price" :aria-label="`${row.line_id}仓库记录单价`" inputmode="decimal" placeholder="待供应商核实"><span class="mt-1 block text-xs font-normal text-slate-500">仅为仓库记录，不能替代供应商原价。</span></label></div>
      </section>
      <div class="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 pt-3"><p class="text-xs text-slate-500">核对本次实收数量和仓位后确认入库。</p><Button type="submit" :disabled="busy || !allowed">{{ busy ? '正在入库…' : '确认入库' }}</Button></div>
    </fieldset>
  </form>
</template>
<style scoped>
label { display: block; min-width: 0; font-size: 12px; font-weight: 600; }
input { display: block; width: 100%; min-width: 0; height: 40px; margin-top: 6px; border: 1px solid var(--input); border-radius: 8px; padding: 8px 10px; background: white; font-size: 14px; font-weight: 400; }
</style>
