<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { cartonPriceReviewsApi as api, type CartonPriceReview } from '@/api/cartonPriceReviews'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
const props = defineProps<{ factoryId: string; supplier?: boolean; shipmentId?: string }>()
const emit = defineEmits<{ changed: [] }>()
const auth = useAuthStore()
const items = ref<CartonPriceReview[]>([]), loading = ref(false), busy = ref(''), error = ref(''), message = ref(''), showAll = ref(false)
const drafts = reactive<Record<string, { price: string; free: boolean; reason: string }>>({})
const editing = reactive(new Set<string>())
let generation = 0, operation = 0, controller = new AbortController()
const retries = new Map<string, { fingerprint: string; requestId: string }>()
const internalAccess = (permission: string) => ['carton', 'pmc-warehouse'].some(dept => auth.can(`carton_procurement:${permission}`, props.factoryId, dept))
const supplierAccess = (permission: string) => auth.can(`carton_supplier:${permission}`, '*', '*') && auth.can(`carton_supplier:${permission}`, props.factoryId, '*')
const canRead = computed(() => props.supplier ? supplierAccess('read') : ['read', 'receipt_write', 'inventory_write'].every(internalAccess))
const canWrite = computed(() => canRead.value && (!props.supplier || supplierAccess('approve')))
const visible = computed(() => items.value.filter(row => showAll.value || row.status !== 'CONFIRMED' && row.receipt_status === 'POSTED'))
const labels = { PENDING: '待核价', PROPOSED: '待供应商确认', CONFIRMED: '双方价格已确认' }
async function load() {
  const token = ++generation; controller.abort(); controller = new AbortController()
  loading.value = true; error.value = ''
  if (!props.factoryId || !canRead.value) { items.value = []; loading.value = false; return }
  try {
    const rows = await api.list(props.factoryId, props.supplier, props.shipmentId, controller.signal)
    if (token !== generation) return
    const previous = new Map(items.value.map(row => [row.id, row.revision]))
    items.value = rows
    for (const row of rows) if (!drafts[row.id] || previous.get(row.id) !== row.revision) drafts[row.id] = { price: row.proposed_unit_price ?? '', free: row.proposed_unit_price != null && Number(row.proposed_unit_price) === 0, reason: '' }
  } catch (reason) { if (token === generation && !controller.signal.aborted) error.value = getApiErrorMessage(reason) }
  finally { if (token === generation) loading.value = false }
}
async function submit(row: CartonPriceReview, decision?: 'CONFIRM' | 'REJECT') {
  if (busy.value || !canWrite.value || !row.actionable || row.locked) return
  const draft = drafts[row.id]!
  draft.price = String(draft.price).trim()
  if (!props.supplier && (draft.reason.trim().length < 4 || draft.price !== '' && (!Number.isFinite(Number(draft.price)) || Number(draft.price) < 0) || draft.price !== '' && Number(draft.price) === 0 && !draft.free)) {
    error.value = '请填写至少四字原因和有效单价；零价请明确勾选免费。'; return
  }
  if (props.supplier && decision === 'REJECT' && draft.reason.trim().length < 4) { error.value = '退回核实须填写至少四字原因。'; return }
  const token = generation, operationToken = ++operation
  const content = { factory_id: props.factoryId, expected_revision: row.revision, reason: draft.reason.trim(), ...(props.supplier ? { decision } : { proposed_unit_price: draft.price === '' ? null : draft.price, free_confirmed: draft.price !== '' && Number(draft.price) === 0 && draft.free }) }
  const fingerprint = JSON.stringify(content), previous = retries.get(row.id)
  const requestId = previous?.fingerprint === fingerprint ? previous.requestId : crypto.randomUUID()
  retries.set(row.id, { fingerprint, requestId }); busy.value = row.id; error.value = ''; message.value = ''
  try {
    if (props.supplier && decision) await api.decide(row.id, { factory_id: props.factoryId, expected_revision: row.revision, request_id: requestId, decision, reason: draft.reason.trim() })
    else await api.propose(row.id, { factory_id: props.factoryId, expected_revision: row.revision, request_id: requestId, proposed_unit_price: draft.price === '' ? null : draft.price, free_confirmed: draft.price !== '' && Number(draft.price) === 0 && draft.free, reason: draft.reason.trim() })
    if (token !== generation) return
    retries.delete(row.id); editing.delete(row.id); drafts[row.id]!.reason = ''
    message.value = decision === 'CONFIRM' ? '双方已确认这一批收料的结算价格，原送货和入库凭证保留。' : decision === 'REJECT' ? '已退回核价，原价格和本次意见保留。' : '已保存核价意见；最终月结须等双方价格一致。'
    emit('changed'); await load()
  } catch (reason) { if (token === generation) error.value = getApiErrorMessage(reason) }
  finally { if (operationToken === operation) busy.value = '' }
}
watch(() => JSON.stringify([props.factoryId, props.supplier, props.shipmentId, auth.currentUser?.id, auth.authorizationVersion, auth.authzMode, auth.currentUser?.identity?.effective_context_key, auth.currentUser?.identity?.employment_epoch]), () => {
  generation++; operation++; controller.abort(); items.value = []; busy.value = ''; message.value = ''; retries.clear(); editing.clear()
  Object.keys(drafts).forEach(key => delete drafts[key]); void load()
}, { immediate: true })
onBeforeUnmount(() => { generation++; operation++; controller.abort() })
defineExpose({ refresh: load })
</script>
<template>
  <section v-if="canRead" class="rounded-xl border border-slate-200 bg-white p-4" aria-label="送货价格核对">
    <div class="flex flex-wrap items-center justify-between gap-2"><div><h2 class="text-sm font-bold">价格核对</h2><p class="mt-1 text-xs text-slate-500">仅处理缺价或价格有异议的收料；原送货价格保留，双方确认后用于结算。</p></div><div class="flex items-center gap-3 text-xs"><label><input v-model="showAll" type="checkbox" class="mr-1 accent-teal-700">显示已处理</label><button type="button" :disabled="loading || !!busy" class="rounded-lg border px-3 py-2" @click="load">刷新核价</button></div></div>
    <p v-if="error" role="alert" class="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">{{ error }}</p><p v-if="message" role="status" class="mt-3 text-sm text-teal-700">{{ message }}</p>
    <p v-if="loading" class="mt-3 text-sm text-slate-500">正在读取核价记录…</p><p v-else-if="!visible.length && !error" class="mt-3 text-sm text-slate-500">暂无需要处理的价格核对。</p>
    <article v-for="row in visible" :key="row.id" class="mt-3 space-y-2 border-t border-slate-100 pt-3 text-sm">
      <div class="flex flex-wrap items-center gap-2"><b>{{ row.document_no }}</b><span>{{ row.item_no }} · {{ row.packaging_type }} · {{ row.specification }}</span><span class="rounded bg-amber-50 px-2 py-1 text-xs text-amber-800">{{ labels[row.status] }}</span></div>
      <p class="text-xs text-slate-600">本批有效收货 {{ row.quantity }} {{ row.unit }} · 供应商原单价 {{ row.original_unit_price ?? '未填写' }} {{ row.currency }} · {{ row.status === 'CONFIRMED' ? '双方确认价格' : '仓库建议价格' }} {{ row.proposed_unit_price ?? '待核实' }}</p><p class="text-xs text-slate-600">{{ row.reason }}</p>
      <p v-if="row.locked || !row.actionable" class="text-xs text-slate-500">{{ row.locked ? '该月已确认，保留原结算记录。' : '原收料已冲销，此记录仅供核对。' }}</p>
      <button v-else-if="!supplier && canWrite && row.status === 'CONFIRMED' && !editing.has(row.id)" type="button" :disabled="!!busy" class="rounded-lg border px-3 py-2 text-xs text-teal-700" @click="editing.add(row.id)">提出价格更正</button>
      <div v-else-if="canWrite && (row.status !== 'CONFIRMED' || !supplier && editing.has(row.id))" class="flex flex-wrap items-end gap-3">
        <template v-if="!supplier"><label class="text-xs">建议单价<input v-model="drafts[row.id]!.price" :aria-label="`${row.document_no} 建议单价`" type="number" min="0" step="0.000001" :disabled="!!busy" class="mt-1 block h-9 w-36 rounded border px-2" placeholder="留空为待核价"></label><label v-if="drafts[row.id]!.price !== '' && Number(drafts[row.id]!.price) === 0" class="py-2 text-xs"><input v-model="drafts[row.id]!.free" type="checkbox" :disabled="!!busy" class="mr-1">确认本行免费</label></template>
        <label class="min-w-0 flex-1 text-xs">{{ supplier ? '核对意见' : '更正原因（至少四字）' }}<input v-model="drafts[row.id]!.reason" :aria-label="`${row.document_no} 核价原因`" :disabled="!!busy" class="mt-1 block h-9 w-full min-w-40 rounded border px-2"></label>
        <button v-if="!supplier" type="button" :disabled="!!busy" class="rounded-lg bg-teal-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-40" @click="submit(row)">保存核价意见</button><template v-else-if="row.status === 'PROPOSED'"><button type="button" :disabled="!!busy" class="rounded-lg bg-teal-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-40" @click="submit(row, 'CONFIRM')">确认本批价格</button><button type="button" :disabled="!!busy" class="rounded-lg border px-3 py-2 text-xs" @click="submit(row, 'REJECT')">退回核实</button></template>
      </div>
      <details class="text-xs text-slate-500"><summary class="cursor-pointer">核对记录</summary><p v-for="(entry, index) in row.history" :key="index" class="mt-1">{{ entry.occurred_at }} · {{ labels[entry.status as keyof typeof labels] || entry.status }} · {{ entry.reason }}</p></details>
    </article>
  </section>
</template>
