<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { CartonOrderResponse } from '@/api/cartonProcurement'
import type { SplitContext } from '@/api/cartonOrderSplits'
import { cartonPrintSplitsApi as api, printStatus, type PrintContext, type PrintPlan, type PrintTarget } from '@/api/cartonPrintSplits'
import { allocateSplitTargets, conversionPending, splitQuantityEditable, type SplitDraftTarget } from '@/features/carton-procurement/splitAllocation'
import { createRandomUuid } from '@/lib/randomUuid'
import { getApiErrorMessage } from '@/lib/http'
const props = defineProps<{ order: CartonOrderResponse; context: SplitContext; canCreate: boolean }>()
const emit = defineEmits<{ changed: []; busy: [value: boolean] }>()
const data = ref<PrintContext>(), error = ref(''), message = ref(''), busy = ref(false), loading = ref(false)
const reason = ref('按客户要求拆分为独立订单'), originals = ref<string[]>([]), printChanged = ref(false)
const legacy = computed(() => props.context.plans.filter(p => p.status !== 'CANCELLED'))
const legacyBlocked = computed(() => legacy.value.some(p => p.status !== 'ACTIVE' || p.targets.some(t => t.lines.some(l => l.stock.length || Number(l.received_quantity) > 0))))
type Draft = SplitDraftTarget & { asset_ids: string[]; due_date: string }
const targets = ref<Draft[]>([])
let generation = 0
let scope = 0
onBeforeUnmount(() => { generation++; scope++ })
let request = createRandomUuid()
const actionRequests = new Map<string, string>()
const pending = ref<{ body: Parameters<typeof api.create>[2]; factory: string; number: string } | null>(null)
const allocation = computed(() => allocateSplitTargets(props.order, { ...props.context,
  plans: [], lines: props.context.lines.map(line => ({ ...line, positions: [], pending_available: conversionPending(props.context, line.order_line_id, line.pending_available) })) }, targets.value))
function add() {
  targets.value.push({ contract_no: '', customer_po: '', product_quantity: null, asset_ids: [], due_date: props.order.due_date,
    lines: props.context.lines.map(line => ({ order_line_id: line.order_line_id, quantity: '' })) })
}
async function load() {
  const token = ++generation
  loading.value = true
  try { const value = await api.context(props.order.factory_id, props.order.order_no); if (token === generation) { data.value = value; if (value.fixed_original_files?.length) originals.value = value.fixed_original_files.map(f => f.id); else if (!originals.value.length && value.inherited_original_files?.length) originals.value = value.inherited_original_files.map(f => f.id) } }
  catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) loading.value = false }
}
function resetTargets() {
  targets.value = legacy.value.flatMap(p => p.targets.map(t => ({ contract_no: t.contract_no, customer_po: t.customer_po, product_quantity: t.product_quantity, asset_ids: [], due_date: props.order.due_date, lines: t.lines.map(l => ({ order_line_id: l.order_line_id, quantity: l.pending_quantity })) })))
  if (!targets.value.length) add()
}
watch(() => [props.order.factory_id, props.order.order_no], () => { scope++; resetTargets(); originals.value = []; printChanged.value = false; pending.value = null; actionRequests.clear(); error.value = message.value = ''; void load() }, { immediate: true })
watch(() => props.context, () => { if (!pending.value && !busy.value) resetTargets() })
watch([targets, originals, reason, printChanged], () => { if (!pending.value) request = createRandomUuid() }, { deep: true })
watch(busy, value => emit('busy', value))
async function save() {
  if (busy.value || !data.value || !props.canCreate) return
  const token = scope
  error.value = ''
  if (!pending.value) {
    if (allocation.value.errors.length) { error.value = allocation.value.errors[0]!; return }
    const values: PrintTarget[] = allocation.value.targets.map((target, i) => ({ contract_no: target.contract_no,
      customer_po: target.customer_po, product_quantity: target.product_quantity, asset_ids: printChanged.value ? targets.value[i]!.asset_ids : [...originals.value],
      due_date: targets.value[i]!.due_date, lines: target.lines.map(line => ({ order_line_id: line.order_line_id, quantity: line.pending_quantity })) }))
    pending.value = { factory: props.order.factory_id, number: props.order.order_no, body: JSON.parse(JSON.stringify({ request_id: request,
      expected_revision: data.value.revision, reason: reason.value, original_asset_ids: [...originals.value], print_changed: printChanged.value,
      legacy_splits: Object.fromEntries(legacy.value.map(p => [p.id, p.revision])), targets: values })) }
  }
  busy.value = true
  try {
    await api.create(pending.value.factory, pending.value.number, pending.value.body)
    if (token !== scope) return
    pending.value = null; resetTargets(); request = createRandomUuid()
    message.value = '草稿已保存。核对下面的数量与印刷资料后，点击发给供应商。'; emit('changed'); await load()
  } catch (cause) {
    if (token !== scope) return
    error.value = getApiErrorMessage(cause)
    const status = (cause as { response?: { status?: number } }).response?.status
    if (status && status >= 400 && status < 500) { pending.value = null; request = createRandomUuid() }
  }
  finally { busy.value = false }
}
async function act(plan: PrintPlan, action: 'send' | 'withdraw') {
  if (busy.value) return
  const token = scope
  const key = `${plan.id}:${plan.revision}:${action}`
  if (!actionRequests.has(key)) actionRequests.set(key, createRandomUuid())
  busy.value = true; error.value = ''
  try {
    await api.act(plan, action, actionRequests.get(key)!, action === 'send' ? '核对数量与固定印刷版本后发送' : '请求撤回本次印刷拆单方案')
    if (token !== scope) return
    actionRequests.delete(key); emit('changed'); await load()
    message.value = action === 'send' ? '已发送，原单暂缓执行，等待供应商明确回应。' : '已提交撤回；已发送的方案须供应商确认收到后解除暂停。'
  } catch (cause) { error.value = getApiErrorMessage(cause) }
  finally { busy.value = false }
}
</script>
<template>
  <section class="mt-4 space-y-4" aria-label="独立订单拆分">
    <p class="rounded-lg border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900">拆单后各订单分别送货、收料和核算库存。保存草稿不会发送；供应商确认后原单扣减并生成真实子单。本入口拆分未入库数量，已入库记录保留在原单。</p>
    <p v-if="error" role="alert" class="text-sm text-red-700">{{ error }}</p><p v-if="message" role="status" class="text-sm text-teal-800">{{ message }}</p>
    <p v-if="loading" role="status">正在读取拆单…</p>
    <article v-for="plan in data?.plans" :key="plan.id" class="space-y-2 rounded-lg border p-3 text-sm">
      <strong>{{ printStatus[plan.status] }}</strong><p>{{ plan.contract_no }} → {{ plan.targets.map(t => t.contract_no).join('、') }}</p>
      <p>原单资料：{{ plan.original_files.map(f => f.file_name).join('、') || '未选择' }}</p>
      <div v-for="target in plan.targets" :key="target.contract_no" class="rounded bg-slate-50 p-2"><b>{{ target.contract_no }}</b> · 产品 {{ target.product_quantity ?? '未记录' }} · 计划交期 {{ target.due_date }}<p>印刷资料：{{ target.files?.map(f => f.file_name).join('、') || '未选择' }}</p><p v-for="line in target.lines" :key="line.order_line_id">{{ context.lines.find(p => p.order_line_id === line.order_line_id)?.packaging_type }}：{{ line.quantity }} {{ context.lines.find(p => p.order_line_id === line.order_line_id)?.unit }}</p></div>
      <p v-if="plan.response_reason" class="text-red-700">供应商异议：{{ plan.response_reason }}</p>
      <p v-if="plan.members.length" class="text-teal-800">执行订单：{{ plan.members.map(m => `${m.contract_no}（${m.order_no}）`).join('、') }}。请从各订单登记收料。</p>
      <div v-if="canCreate && plan.order_id === order.id" class="flex flex-wrap gap-2"><button v-if="plan.status === 'DRAFT'" :disabled="busy" type="button" class="rounded-lg bg-teal-700 px-3 py-2 font-semibold text-white disabled:opacity-40" @click="act(plan, 'send')">发给供应商确认拆单</button><button v-if="['DRAFT', 'SENT', 'DISPUTED'].includes(plan.status)" :disabled="busy" type="button" class="rounded-lg border px-3 py-2" @click="act(plan, 'withdraw')">{{ plan.status === 'DRAFT' ? '撤销草稿' : '请求撤回拆单' }}</button></div>
    </article>
    <p v-if="legacyBlocked" role="alert" class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm">旧拆单已有入库或库存分配，不能直接转换。请先核对原收料、领用和库存记录，保留历史账务。</p>
    <p v-else-if="legacy.length" class="rounded-lg border border-sky-200 bg-sky-50 p-3 text-sm">已载入旧拆分合同和数量。保存转换草稿、发给供应商确认后，旧分配记录归档并生成独立子单；无需先入库。</p>
    <form v-if="data && canCreate && !legacyBlocked && !data.plans.some(p => ['SENT','DISPUTED','WITHDRAWING'].includes(p.status))" class="space-y-4 border-t pt-4" @submit.prevent="save">
      <fieldset :disabled="busy || !!pending" class="space-y-4 disabled:opacity-60">
        <label class="block text-sm">拆单原因<input v-model="reason" required minlength="4" maxlength="500" class="mt-1 h-9 w-full rounded border px-2"></label>
        <label class="flex items-center gap-2 text-sm"><input v-model="printChanged" type="checkbox" aria-label="子单印刷不同">子单印刷不同，需要单独选择资料</label><p v-if="!printChanged" class="text-xs text-slate-500">子单沿用原印刷资料；无电子原件时可留空，独立收料不受影响。</p>
        <label class="block text-sm">原单继续使用的印刷资料<span v-if="data.fixed_original_files?.length" class="ml-2 text-teal-700">已固定，保留量沿用原印刷</span><select v-model="originals" :disabled="!!data.fixed_original_files?.length" multiple aria-label="原单印刷资料" class="mt-1 max-h-32 min-h-20 w-full rounded border p-2"><option v-for="file in data.fixed_original_files?.length ? data.fixed_original_files : data.files" :key="file.id" :value="file.id">{{ file.file_name }} · 版本 {{ file.revision }}</option></select></label>
        <p v-if="!data.files.length" class="text-sm text-amber-800">暂无可选资料，请先到箱唛资料库上传原件，再返回刷新。资料选择不代表 QC 审核。</p>
        <div v-for="(target, index) in targets" :key="index" class="space-y-3 rounded-lg border bg-slate-50 p-3">
          <div class="grid gap-3 sm:grid-cols-2"><label>子单合同<input v-model="target.contract_no" :readonly="!!legacy.length" required :aria-label="`印刷子单 ${index+1} 合同`" class="mt-1 h-9 w-full rounded border bg-white px-2"></label><label>客户 PO<input v-model="target.customer_po" :readonly="!!legacy.length" class="mt-1 h-9 w-full rounded border bg-white px-2"></label><label>产品数量<input v-model="target.product_quantity" :readonly="!!legacy.length" :required="order.quantity_basis !== 'EXPLICIT'" type="number" min="0.000001" step="0.000001" :aria-label="`印刷子单 ${index+1} 产品数量`" class="mt-1 h-9 w-full rounded border bg-white px-2"></label><label>计划交期<input v-model="target.due_date" required type="date" class="mt-1 h-9 w-full rounded border bg-white px-2"></label></div>
          <label v-if="printChanged" class="block">子单印刷资料<select v-model="target.asset_ids" multiple :aria-label="`印刷子单 ${index+1} 资料`" class="mt-1 max-h-32 min-h-20 w-full rounded border bg-white p-2"><option v-for="file in data.files" :key="file.id" :value="file.id">{{ file.file_name }} · 版本 {{ file.revision }}</option></select></label>
          <div v-for="(line, pi) in target.lines" :key="line.order_line_id" class="flex flex-wrap items-center justify-between gap-2 text-sm"><span>{{ context.lines.find(p => p.order_line_id === line.order_line_id)?.packaging_type }} · {{ context.lines.find(p => p.order_line_id === line.order_line_id)?.specification }}</span><label>拆出 {{ context.lines.find(p => p.order_line_id === line.order_line_id)?.unit }}<input v-if="splitQuantityEditable(order,line.order_line_id)" v-model="line.quantity" :readonly="!!legacy.length" type="number" min="0.0001" step="0.0001" required class="ml-2 h-9 w-28 rounded border bg-white px-2"><b v-else class="ml-2">{{ allocation.details[index]?.[pi]?.quantity }}</b></label></div>
          <button v-if="!legacy.length && targets.length > 1" type="button" class="text-sm text-red-700" @click="targets.splice(index,1)">移除此子单</button>
        </div>
        <button type="button" :disabled="!!legacy.length || targets.length >= 20" class="text-sm font-semibold text-teal-700" @click="add">＋增加子单</button>
      </fieldset>
      <div class="flex flex-wrap justify-end gap-2"><button type="button" :disabled="busy" class="rounded-lg border px-3 py-2" @click="load">刷新资料与记录</button><button :disabled="busy || loading" class="rounded-lg bg-teal-700 px-4 py-2 font-semibold text-white disabled:opacity-40">{{ busy ? '正在保存…' : pending ? '重试同一拆单草稿' : '保存拆单草稿' }}</button></div>
      <p v-if="pending" class="text-xs text-amber-800">提交结果未确认时保留原请求，请重试核对，勿重复新建。</p>
    </form>
  </section>
</template>
