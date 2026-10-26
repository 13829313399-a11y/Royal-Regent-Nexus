<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { http, getApiErrorMessage } from '@/lib/http'
import type { PortalOrder } from '@/api/cartonSupplierPortal'
import type { SpecialRequest } from '@/api/cartonSpecialRequests'
import { factoryContexts } from '@/data/enterpriseMock'
import { createRandomUuid } from '@/lib/randomUuid'
const factoryName = (id: string) => factoryContexts.find(item => item.id === id)?.name || id
const props = defineProps<{ factories: { factory_id: string; supplier_name: string }[]; orders: (PortalOrder & { factory_id: string })[]; requests: SpecialRequest[]; initialFactory?: string; viewerKey: string }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const auth = useAuthStore(), factory = ref(props.initialFactory || props.factories[0]?.factory_id || '')
const note = ref(''), day = ref(new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })), error = ref(''), busy = ref(false), query = ref('')
type Draft = { selected: boolean; quantity: string; price: string; free: boolean }
const drafts = reactive<Record<string, Draft>>({})
type Extra = { key: string; packaging_type: string; paper_quality: string; specification: string; dimension_unit: 'cm' | 'in'; unit: string; quantity: string; unit_price: string; free_confirmed: boolean; purpose: string }
const extras = ref<Extra[]>([])
let generation = 0, retry: { fingerprint: string; id: string } | null = null
const canEdit = computed(() => props.factories.some(item => item.factory_id === factory.value) && auth.can('carton_supplier:edit', '*', '*') && auth.can('carton_supplier:edit', factory.value, '*'))
const candidates = computed(() => [
  ...props.orders.filter(order => order.factory_id === factory.value).flatMap(order => order.lines.filter(line => Number(line.remaining_to_ship) > 0).map(line => ({
    key: `formal:${line.id}`, kind: 'FORMAL' as const, id: line.id, order, request: null,
    label: `正单 · ${order.order_no} · ${order.customer_name} · ${order.item_no} · ${line.packaging_type}`,
    specification: `${line.paper_quality} · ${line.specification}`, remaining: line.remaining_to_ship, unit: line.unit,
    blocked: line.shipping_blocked_reason || (!line.accepted ? '请先确认接单和承诺交期' : order.awaiting_issue || ['CANCELLED', 'RETURNED'].includes(order.status) ? '当前订单不可发货' : ''),
  }))),
  ...props.requests.filter(request => request.factory_id === factory.value && !['DRAFT', 'SUBMITTED', 'CANCELLED'].includes(request.status)).flatMap(request => request.lines.filter(line => Number(line.remaining_to_ship ?? line.remaining_quantity ?? line.quantity) > 0).map(line => ({
    key: `special:${line.id}`, kind: 'SPECIAL' as const, id: line.id!, order: null, request,
    label: `${request.kind === 'SAMPLE' ? '样板单' : request.kind === 'WORKSHOP_MISC' ? '杂单' : '历史赠送'} · ${request.request_no} · ${line.item_no || request.requester_name} · ${line.packaging_type}`,
    specification: `${line.paper_quality} · ${line.specification}`, remaining: line.remaining_to_ship ?? line.remaining_quantity ?? line.quantity, unit: line.unit,
    blocked: !request.permissions.can_ship ? '当前需求不可发货，请核对接单及订单状态' : '',
  }))),
])
const visible = computed(() => candidates.value.filter(row => !query.value.trim() || `${row.label} ${row.specification}`.toLowerCase().includes(query.value.trim().toLowerCase())))
watch(candidates, rows => { for (const row of rows) drafts[row.key] ??= { selected: false, quantity: row.remaining, price: '', free: false } }, { immediate: true })
watch(() => [factory.value, props.viewerKey, canEdit.value], () => { generation++; retry = null; busy.value = false; error.value = ''; note.value = ''; extras.value = []; query.value = ''; for (const key of Object.keys(drafts)) delete drafts[key]; for (const row of candidates.value) drafts[row.key] = { selected: false, quantity: row.remaining, price: '', free: false } }, { flush: 'sync' })
watch(() => props.factories.map(item => item.factory_id).join('|'), () => { if (!props.factories.some(item => item.factory_id === factory.value)) factory.value = props.factories[0]?.factory_id || '' })
onBeforeUnmount(() => { generation++ })
function addExtra() { extras.value.push({ key: createRandomUuid(), packaging_type: '外箱', paper_quality: '', specification: '', dimension_unit: 'cm', unit: '个', quantity: '', unit_price: '', free_confirmed: false, purpose: '' }) }
function validQuantity(quantity: string) { return /^\d{1,14}(\.\d{1,4})?$/.test(String(quantity)) && Number(quantity) > 0 }
function validPrice(price: string, free: boolean) { return /^\d{1,12}(\.\d{1,6})?$/.test(String(price)) && Number.isFinite(Number(price)) && Number(price) >= 0 && (Number(price) > 0 || free) }
async function save() {
  if (busy.value || !canEdit.value) return
  error.value = ''
  const selected = candidates.value.filter(row => drafts[row.key]?.selected)
  if (!note.value.trim() || !day.value || !selected.length && !extras.value.length) { error.value = '请填写送货单号、日期，并选择本次送货纸品。'; return }
  if (selected.some(row => row.blocked || !validQuantity(drafts[row.key]!.quantity) || Number(drafts[row.key]!.quantity) > Number(row.remaining) || !validPrice(drafts[row.key]!.price, drafts[row.key]!.free))) { error.value = '请核对所选明细：数量不得超过待发数，单价必须填写，零价须勾选本行免费；接单及订单状态须允许发货。'; return }
  if (extras.value.some(row => !row.paper_quality.trim() || !row.specification.trim() || !row.packaging_type.trim() || !row.unit.trim() || !row.purpose.trim() || !validQuantity(row.quantity) || !validPrice(row.unit_price, row.free_confirmed))) { error.value = '额外纸品须填写纸质、规格、单位、数量、用途和单价，零价须确认免费。'; return }
  const special = new Map<string, { id: string; expected_revision: number; version_id: string; lines: { line_id: string; quantity: string; unit_price: string; free_confirmed: boolean }[] }>()
  for (const row of selected.filter(row => row.kind === 'SPECIAL')) {
    const request = row.request!, draft = drafts[row.key]!
    const group = special.get(request.id) ?? { id: request.id, expected_revision: request.revision, version_id: request.current_version_id, lines: [] }
    group.lines.push({ line_id: row.id, quantity: String(draft.quantity), unit_price: String(draft.price), free_confirmed: Number(draft.price) === 0 && draft.free }); special.set(request.id, group)
  }
  const body = { factory_id: factory.value, delivery_note_no: note.value.trim(), delivery_date: day.value,
    formal_lines: selected.filter(row => row.kind === 'FORMAL').map(row => ({ order_line_id: row.id, issue_id: row.order!.issue_id, quantity: String(drafts[row.key]!.quantity), unit_price: String(drafts[row.key]!.price), free_confirmed: Number(drafts[row.key]!.price) === 0 && drafts[row.key]!.free })),
    special_requests: [...special.values()], extra_lines: extras.value.map(({ key: _key, ...row }) => ({ ...row, free_confirmed: Number(row.unit_price) === 0 && row.free_confirmed })),
  }
  const fingerprint = JSON.stringify(body)
  if (retry?.fingerprint !== fingerprint) retry = { fingerprint, id: createRandomUuid() }
  const token = generation; busy.value = true
  try { await http.post('/carton-supplier/unified-deliveries', { ...body, request_id: retry!.id }); if (token === generation) { retry = null; emit('saved') } }
  catch (reason) { if (token === generation) error.value = getApiErrorMessage(reason) }
  finally { if (token === generation) busy.value = false }
}
</script>
<template>
  <section class="space-y-4 rounded-xl border border-teal-200 bg-white p-4" aria-label="新建统一送货单">
    <div class="flex items-start justify-between gap-3"><div><h2 class="font-bold">新建送货单</h2><p class="mt-1 text-xs text-slate-500">同一厂区的正单、样板和杂单可放在一张原送货单中；逐行填写本次单价。</p></div><button type="button" :disabled="busy" class="rounded border px-3 py-2 text-xs" @click="emit('close')">关闭</button></div>
    <p v-if="error" role="alert" class="rounded-lg bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
    <fieldset :disabled="busy" class="space-y-4 disabled:opacity-60">
      <div class="grid gap-3 sm:grid-cols-3"><label class="text-xs">送往厂区<select v-model="factory" aria-label="送货单厂区" class="mt-1 h-9 w-full rounded border px-2"><option v-for="item in factories" :key="item.factory_id" :value="item.factory_id">{{ factoryName(item.factory_id) }} · {{ item.supplier_name }}</option></select></label><label class="text-xs">原送货单号<input v-model="note" aria-label="统一送货单号" class="mt-1 h-9 w-full rounded border px-2" maxlength="128"></label><label class="text-xs">送货日期<input v-model="day" aria-label="统一送货日期" type="date" class="mt-1 h-9 w-full rounded border px-2"></label></div>
      <input v-model="query" aria-label="选择送货纸品" placeholder="搜索订单、客户、货号或纸品" class="h-9 w-full rounded border px-3 text-sm">
      <div class="max-h-96 space-y-2 overflow-y-auto"><article v-for="row in visible" :key="row.key" class="rounded-lg border border-slate-200 p-3 text-xs"><label class="flex items-start gap-2"><input v-model="drafts[row.key]!.selected" type="checkbox" :disabled="!!row.blocked" class="mt-0.5 accent-teal-700"><span><b>{{ row.label }}</b><span class="mt-1 block text-slate-500">{{ row.specification }} · 待发 {{ row.remaining }} {{ row.unit }}</span></span></label><p v-if="row.blocked" class="mt-1 text-amber-700">{{ row.blocked }}</p><div v-if="drafts[row.key]!.selected" class="mt-3 grid gap-3 sm:grid-cols-3"><label>本次送货数量<input v-model="drafts[row.key]!.quantity" type="number" min="0.0001" step="0.0001" :max="row.remaining" class="mt-1 h-9 w-full rounded border px-2"></label><label>本次单价（CNY）<input v-model="drafts[row.key]!.price" type="number" min="0" step="0.000001" class="mt-1 h-9 w-full rounded border px-2" placeholder="必填，不能留空"></label><label v-if="drafts[row.key]!.price !== '' && Number(drafts[row.key]!.price) === 0" class="self-end py-2"><input v-model="drafts[row.key]!.free" type="checkbox" class="mr-1 accent-teal-700">本行免费</label></div></article><p v-if="!visible.length" class="py-4 text-sm text-slate-500">暂无匹配纸品，可清除搜索或添加额外纸品。</p></div>
      <details><summary class="cursor-pointer text-sm font-semibold text-teal-800">额外送来的纸品（无原订单）</summary><p class="mt-2 text-xs text-slate-500">登记实际额外送来的纸品，仓库收货时核实用途和归属。箱唛资料选填，可另行上传或关联。</p><article v-for="row in extras" :key="row.key" class="mt-3 rounded-lg border p-3"><div class="grid gap-3 text-xs sm:grid-cols-3"><label>纸品类型<input v-model="row.packaging_type" class="mt-1 h-9 w-full rounded border px-2"></label><label>纸质<input v-model="row.paper_quality" class="mt-1 h-9 w-full rounded border px-2"></label><label>规格<input v-model="row.specification" placeholder="长×宽×高" class="mt-1 h-9 w-full rounded border px-2"></label><label>尺寸单位<select v-model="row.dimension_unit" class="mt-1 h-9 w-full rounded border px-2"><option value="cm">cm</option><option value="in">in</option></select></label><label>数量<input v-model="row.quantity" type="number" min="0.0001" step="0.0001" class="mt-1 h-9 w-full rounded border px-2"></label><label>计量单位<input v-model="row.unit" class="mt-1 h-9 w-full rounded border px-2"></label><label>单价（CNY）<input v-model="row.unit_price" type="number" min="0" step="0.000001" class="mt-1 h-9 w-full rounded border px-2"></label><label>用途<input v-model="row.purpose" class="mt-1 h-9 w-full rounded border px-2"></label><label v-if="row.unit_price !== '' && Number(row.unit_price) === 0" class="self-end py-2"><input v-model="row.free_confirmed" type="checkbox" class="mr-1">本行免费</label></div><p class="mt-2 text-xs">箱唛：不需要印刷</p><button type="button" class="mt-2 text-xs text-red-700" @click="extras = extras.filter(item => item.key !== row.key)">移除此行</button></article><button type="button" class="mt-3 rounded-lg border px-3 py-2 text-xs" @click="addExtra">添加额外纸品</button></details>
      <div class="flex flex-wrap items-center justify-between gap-3"><span class="text-xs text-slate-500">本单 {{ candidates.filter(row => drafts[row.key]?.selected).length + extras.length }} 条纸品；提交后进入仓库统一待收。</span><button type="button" :disabled="!canEdit || busy" class="rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40" @click="save">{{ busy ? '正在提交…' : '确认本单发货' }}</button></div>
    </fieldset>
  </section>
</template>
