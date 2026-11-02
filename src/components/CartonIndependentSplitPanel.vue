<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { CartonOrderResponse } from '@/api/cartonProcurement'
import { cartonOrderDivisionsApi as api, type DivisionCommand, type DivisionContext, type OrderDivision } from '@/api/cartonOrderDivisions'
import { allocateSplitTargets, conversionPending, splitQuantityEditable, splitRemaining, type SplitDraftTarget } from '@/features/carton-procurement/splitAllocation'
import { createRandomUuid } from '@/lib/randomUuid'
import { getApiErrorMessage } from '@/lib/http'
const props = defineProps<{ order: CartonOrderResponse; context: DivisionContext; canCreate: boolean }>()
const emit = defineEmits<{ completed: [OrderDivision]; busy: [boolean] }>()
type Draft = SplitDraftTarget & { due_date: string }
const targets = ref<Draft[]>([]), reason = ref('按客户要求拆分订单'), busy = ref(false), error = ref('')
const pending = ref<DivisionCommand | null>(null)
let scope = 0
onBeforeUnmount(() => { scope++ })
const legacy = computed(() => props.context.plans.filter(p => p.status !== 'CANCELLED'))
const legacyBlocked = computed(() => legacy.value.some(p => p.status !== 'ACTIVE' || p.targets.some(t => t.lines.some(l => l.stock.length || Number(l.received_quantity) > 0))))
const editable = computed(() => props.canCreate && props.context.can_split && !legacyBlocked.value)
function add() {
  targets.value.push({ contract_no: '', customer_po: '', product_quantity: null, due_date: props.order.due_date,
    lines: props.context.lines.map(line => ({ order_line_id: line.order_line_id, quantity: '' })) })
}
watch(() => [props.order.factory_id, props.order.order_no, props.context.revision], () => {
  scope++; pending.value = null; error.value = ''
  targets.value = legacy.value.flatMap(plan => plan.targets.map(target => ({ contract_no: target.contract_no,
    customer_po: target.customer_po, product_quantity: target.product_quantity, due_date: props.order.due_date,
    lines: target.lines.map(line => ({ order_line_id: line.order_line_id, quantity: line.pending_quantity })) })))
  if (!targets.value.length) add()
}, { immediate: true })
const prepared = computed(() => targets.value.map(target => ({ ...target, lines: target.lines.filter(line =>
  props.order.quantity_basis !== 'EXPLICIT' || (String(line.quantity).trim() !== '' && Number(line.quantity) !== 0)) })))
const allocation = computed(() => allocateSplitTargets(props.order, { ...props.context, plans: [],
  lines: props.context.lines.map(line => ({ ...line, positions: [], pending_available: conversionPending(props.context, line.order_line_id, line.pending_available) })) }, prepared.value))
const preview = computed(() => props.context.lines.map(line => {
  const quantities = allocation.value.targets.map(target => String(target.lines.find(p => p.order_line_id === line.order_line_id)?.pending_quantity ?? '0'))
  return { ...line, quantities, remaining: splitRemaining(line.required_quantity, quantities) }
}))
function quantityFor(index: number, lineId: string) {
  return allocation.value.details[index]?.[prepared.value[index]?.lines.findIndex(line => line.order_line_id === lineId) ?? -1]?.quantity || '0'
}
watch(busy, value => emit('busy', value))
async function submit() {
  if (busy.value || !editable.value) return
  error.value = ''
  if (!pending.value) {
    if (allocation.value.errors.length) { error.value = allocation.value.errors[0]!; return }
    if (reason.value.trim().length < 4) { error.value = '请填写至少四个字的拆单原因。'; return }
    pending.value = { request_id: createRandomUuid(), expected_revision: props.context.revision, reason: reason.value,
      legacy_splits: Object.fromEntries(legacy.value.map(plan => [plan.id, plan.revision])),
      targets: allocation.value.targets.map((target, index) => ({ contract_no: target.contract_no, customer_po: target.customer_po,
        product_quantity: target.product_quantity, due_date: targets.value[index]!.due_date,
        lines: target.lines.filter(line => Number(line.pending_quantity) > 0).map(line => ({ order_line_id: line.order_line_id, quantity: line.pending_quantity })) })) }
  }
  const token = scope
  busy.value = true
  try {
    const result = await api.create(props.order.factory_id, props.order.order_no, pending.value)
    if (token === scope) { pending.value = null; emit('completed', result) }
  } catch (cause) {
    if (token !== scope) return
    error.value = getApiErrorMessage(cause)
    const status = (cause as { response?: { status?: number } }).response?.status
    if (status && status >= 400 && status < 500) pending.value = null
  } finally { busy.value = false }
}
</script>
<template>
  <section aria-label="独立订单拆分" class="space-y-4">
    <p class="rounded-lg bg-sky-50 p-3 text-sm leading-6 text-sky-900">原单扣减，子单立即生成独立订单，各自送货、收料和核算库存。<template v-if="context.supplier_notified">原单已发送，本次拆分将同时通知供应商，在现有订单变更待办中分别确认。</template><template v-else>原单尚未发送，拆分后各订单按正常流程分别发送。</template></p>
    <p v-if="context.block_reason" role="status" class="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">{{ context.block_reason }}</p>
    <p v-if="legacyBlocked" role="alert" class="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">旧拆单已有库存分配或收料历史，不能直接转换。请核对旧收料、领用及库存记录；可撤销的方案在下方历史记录处理，已领用记录需主管核对，不能重写历史账务。</p>
    <p v-else-if="legacy.length" class="text-sm text-slate-600">已带入旧方案的合同和数量，本次确认会归档旧分配关系并生成真实独立订单。</p>
    <form v-if="editable" class="space-y-4" @submit.prevent="submit">
      <fieldset :disabled="busy || !!pending" class="space-y-4 disabled:opacity-60">
        <div v-for="(target, index) in targets" :key="index" class="space-y-3 rounded-xl border border-input p-4">
          <div class="flex items-center justify-between"><strong class="text-sm">子单 {{ index + 1 }}</strong><button v-if="!legacy.length && targets.length > 1" type="button" class="text-xs text-red-700" @click="targets.splice(index, 1)">移除此子单</button></div>
          <div class="grid gap-3 sm:grid-cols-2">
            <label class="text-sm">子单合同 *<input v-model="target.contract_no" :readonly="!!legacy.length" required maxlength="128" :aria-label="`子单 ${index+1} 合同`" class="mt-1 h-9 w-full rounded-lg border border-input bg-white px-3"></label>
            <label class="text-sm">客户 PO<input v-model="target.customer_po" :readonly="!!legacy.length" maxlength="128" :aria-label="`子单 ${index+1} 客户 PO`" class="mt-1 h-9 w-full rounded-lg border border-input bg-white px-3"></label>
            <label class="text-sm">产品数量{{ order.quantity_basis === 'EXPLICIT' ? '（可不填）' : ' *' }}<input v-model="target.product_quantity" :readonly="!!legacy.length" :required="order.quantity_basis !== 'EXPLICIT'" type="number" min="0.000001" step="0.000001" :aria-label="`子单 ${index+1} 产品数量`" class="mt-1 h-9 w-full rounded-lg border border-input bg-white px-3"></label>
            <label class="text-sm">计划交期 *<input v-model="target.due_date" required type="date" :min="order.order_date" :aria-label="`子单 ${index+1} 计划交期`" class="mt-1 h-9 w-full rounded-lg border border-input bg-white px-3"></label>
          </div>
          <p v-if="order.quantity_basis === 'EXPLICIT'" class="text-xs text-slate-500">只填写需要拆出的纸品；留空或 0 的纸品保留在原单。</p>
          <div v-for="line in target.lines" :key="line.order_line_id" class="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-2 text-sm">
            <span class="min-w-0 break-words">{{ context.lines.find(p => p.order_line_id === line.order_line_id)?.packaging_type }} · {{ context.lines.find(p => p.order_line_id === line.order_line_id)?.specification }}</span>
            <label class="shrink-0">拆出 <input v-if="splitQuantityEditable(order, line.order_line_id)" v-model="line.quantity" :readonly="!!legacy.length" :required="order.quantity_basis !== 'EXPLICIT'" type="number" min="0" step="0.0001" :aria-label="`子单 ${index+1} ${context.lines.find(p => p.order_line_id === line.order_line_id)?.packaging_type}拆出数量`" class="h-9 w-24 rounded-lg border border-input px-2"><b v-else class="mx-2 tabular-nums">{{ quantityFor(index, line.order_line_id) }}</b> {{ context.lines.find(p => p.order_line_id === line.order_line_id)?.unit }}</label>
          </div>
        </div>
        <button v-if="!legacy.length" type="button" :disabled="targets.length >= 20" class="text-sm font-semibold text-teal-700 disabled:opacity-40" @click="add">＋增加子单</button>
        <div class="overflow-x-auto rounded-lg border border-input" aria-label="拆分数量核对"><table class="w-full text-right text-xs tabular-nums"><thead class="bg-slate-50"><tr><th class="whitespace-nowrap p-2 text-left">纸品</th><th class="whitespace-nowrap p-2">拆前</th><th class="whitespace-nowrap p-2">原单保留</th><th v-for="(_, index) in targets" :key="index" class="whitespace-nowrap p-2">子单 {{ index+1 }}</th></tr></thead><tbody><tr v-for="line in preview" :key="line.order_line_id" class="border-t border-slate-100"><th class="p-2 text-left font-normal">{{ line.packaging_type }}（{{ line.unit }}）</th><td class="p-2">{{ line.required_quantity }}</td><td class="p-2 font-semibold">{{ line.remaining }}</td><td v-for="(value,index) in line.quantities" :key="index" class="p-2">{{ value }}</td></tr></tbody></table></div>
        <label class="block text-sm">拆单原因 *<input v-model="reason" required minlength="4" maxlength="500" aria-label="拆单原因" class="mt-1 h-9 w-full rounded-lg border border-input px-3"></label>
      </fieldset>
      <p v-if="error" role="alert" class="text-sm text-red-700">{{ error }}</p>
      <p v-if="pending" role="status" class="text-xs text-amber-800">提交结果未确认，已保留原内容。请重试同一请求，避免重复拆单。</p>
      <div class="sticky -bottom-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 bg-white py-3"><p class="text-xs text-slate-500">已入库数量保留在原单，本次只拆未入库需求。</p><button :disabled="busy" type="submit" class="h-10 rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white disabled:opacity-40">{{ busy ? '正在拆分…' : pending ? '核对原提交结果' : context.supplier_notified ? '确认拆分并通知供应商' : '确认拆分' }}</button></div>
    </form>
  </section>
</template>
