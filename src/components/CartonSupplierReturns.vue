<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import CartonReturnDateEditor from './CartonReturnDateEditor.vue'
import { cartonSupplierReturnsApi as api, type ReturnAction, type ReturnActionBody, type SupplierReturn } from '@/api/cartonSupplierReturns'
import { createRandomUuid } from '@/lib/randomUuid'
import { getApiErrorMessage } from '@/lib/http'
import { factoryContexts } from '@/data/enterpriseMock'
import { formatBusinessDate } from '@/lib/dateTime'
import '@/features/carton-procurement/layout.css'

const props = withDefaults(defineProps<{ factoryId?: string; factories?: { factory_id: string }[]; internal?: boolean; viewerKey?: string; search?: string }>(), { internal: false, factoryId: '' })
const emit = defineEmits<{ changed: []; 'update:search': [value: string] }>()
const options = computed(() => [...new Set(props.factories?.map(row => row.factory_id) ?? (props.factoryId ? [props.factoryId] : []))])
const factory = ref(''), rows = ref<SupplierReturn[]>([]), total = ref(0), offset = ref(0), history = ref(false)
const localSearch = ref(''), loading = ref(false), busy = ref(false), error = ref(''), message = ref('')
const selected = ref<SupplierReturn | null>(null), dateEditor = ref(false), action = ref<ReturnAction | ''>('')
const form = reactive({ quantity: '', receipt_date: '', document_no: '', reason: '', unit_price: '', credit_date: '',
  kind: 'CASH' as 'CASH' | 'OFFSET', amount: '', refund_date: '', target_event_id: '', confirmation_reference: '' })
const query = computed({ get: () => props.search ?? localSearch.value, set: (value: string) => { if (props.search === undefined) localSearch.value = value; else emit('update:search', value) } })
const limit = 20, today = () => formatBusinessDate(new Date().toISOString())
const context = computed(() => JSON.stringify([options.value, factory.value, props.viewerKey, props.internal]))
const actionLabels: Record<ReturnAction, string> = { ENROLL: '将此退货接入协同', RECEIVE: '登记本次签收', DISPUTE: '登记本次异议', PROPOSE_CREDIT: '提出整笔退货贷项', CONFIRM_CREDIT: '内部确认贷项', DECLARE_REFUND: '登记退款或抵扣凭证', CONFIRM_REFUND: '内部核实到账 / 抵扣', VOID: '更正已录凭证', RECONFIRM_DATE: '供应商确认新退货日期', CONFIRM_DATE: '内部确认新退货日期' }
const statusLabels: Record<string, string> = { PENDING: '待处理', LEGACY: '未接入协同', SOURCE_REVERSED: '原退货已冲销', RECONFIRM_REQUIRED: '日期版本待复核', NOT_PROPOSED: '尚未提议', SUPERSEDED: '已被新版本替代', ACTIVE: '生效', PARTIAL: '部分签收', RECEIVED: '已签收', ACCEPTED: '已签收', DISPUTED: '有异议', PROPOSED: '待内部核实', CONFIRMED: '已核实', APPROVED: '已核实', VOID: '已更正，保留历史', VOIDED: '已更正，保留历史', NONE: '尚未登记', COMPLETE: '已完成' }
const allowed = computed(() => selected.value?.allowed_actions.filter((value): value is ReturnAction => Object.prototype.hasOwnProperty.call(actionLabels, value)) ?? [])
const canDate = computed(() => props.internal && !!selected.value && (selected.value.can_correct_date || selected.value.allowed_actions.includes('CORRECT_DATE')))
const needsReceipt = computed(() => action.value === 'RECEIVE' || action.value === 'DISPUTE')
const needsCredit = computed(() => action.value === 'PROPOSE_CREDIT')
const needsRefund = computed(() => action.value === 'DECLARE_REFUND')
const needsTarget = computed(() => ['CONFIRM_CREDIT', 'CONFIRM_REFUND', 'VOID'].includes(action.value))
const needsConfirmationReference = computed(() => action.value === 'CONFIRM_REFUND' || action.value === 'VOID' && selected.value?.void_confirmation_required_event_ids?.includes(form.target_event_id))
const targets = computed(() => {
  const row = selected.value
  if (!row) return []
  if (action.value === 'CONFIRM_CREDIT') return row.credit ? [{ id: row.credit.id, label: `贷项 ${row.credit.document_no} · ${row.credit.amount} ${row.currency}` }] : []
  const refunds = row.refunds.filter(item => action.value === 'CONFIRM_REFUND' ? item.status === 'PROPOSED' : item.status !== 'VOID').map(item => ({ id: item.id, label: `${item.kind === 'CASH' ? '现金退款申报' : '月结抵扣申报'} ${item.document_no} · ${item.amount} ${row.currency} · ${label(item.status)}` }))
  const all = [...row.receipts.filter(item => item.status !== 'VOID').map(item => ({ id: item.id, label: `签收 / 异议 ${item.document_no} · ${item.quantity} ${row.unit} · ${label(item.status)}` })), ...(row.credit ? [{ id: row.credit.id, label: `贷项提议 ${row.credit.document_no}` }] : []), ...refunds]
  return action.value === 'CONFIRM_REFUND' ? refunds : all.filter(item => row.voidable_event_ids?.includes(item.id))
})
const label = (value: string) => statusLabels[value] || value
const money = (value?: string | null) => value == null ? '待核实' : value
const factoryName = (id: string) => factoryContexts.find(row => row.id === id)?.name || id
let generation = 0, sequence = 0, controller = new AbortController(), searchTimer: ReturnType<typeof setTimeout> | undefined
const requests = new Map<string, string>()
function clearForm() {
  action.value = ''; dateEditor.value = false
  Object.assign(form, { quantity: '', receipt_date: '', document_no: '', reason: '', unit_price: '', credit_date: '', kind: 'CASH', amount: '', refund_date: '', target_event_id: '', confirmation_reference: '' })
}
watch(options, ids => { if (!ids.includes(factory.value)) factory.value = ids[0] || '' }, { immediate: true })
watch(context, () => {
  generation++; sequence++; controller.abort(); controller = new AbortController(); rows.value = []; selected.value = null
  total.value = 0; offset.value = 0; busy.value = false; error.value = ''; message.value = ''; requests.clear(); clearForm()
  void load()
}, { immediate: true, flush: 'sync' })
watch([history, query], () => {
  if (searchTimer) clearTimeout(searchTimer)
  offset.value = 0; selected.value = null; clearForm()
  searchTimer = setTimeout(() => { void load() }, 250)
})
watch(action, () => { form.target_event_id = targets.value.length === 1 ? targets.value[0]!.id : ''; error.value = '' })
async function load() {
  if (!factory.value) { loading.value = false; return }
  const token = generation, read = ++sequence
  loading.value = true; error.value = ''
  try {
    const data = await api.list(factory.value, props.internal, { limit, offset: offset.value, ...(history.value ? {} : { status: 'PENDING' }), ...(query.value.trim() ? { keyword: query.value.trim() } : {}) }, controller.signal)
    if (token !== generation || read !== sequence) return
    rows.value = data.items; total.value = data.total
  } catch (cause) { if (token === generation && read === sequence) { rows.value = []; total.value = 0; error.value = getApiErrorMessage(cause) } }
  finally { if (token === generation && read === sequence) loading.value = false }
}
async function open(row: SupplierReturn) {
  if (busy.value || loading.value) return
  const token = generation, read = ++sequence
  loading.value = true; error.value = ''; message.value = ''; selected.value = null; clearForm()
  try {
    const data = await api.detail(row.movement_id, factory.value, props.internal, controller.signal)
    if (token === generation && read === sequence) selected.value = data
  } catch (cause) { if (token === generation && read === sequence) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation && read === sequence) loading.value = false }
}
async function refresh() {
  if (busy.value || loading.value) return
  const row = selected.value, token = generation
  await load()
  if (token === generation && row && !error.value) await open(row)
}
function payload(): Omit<ReturnActionBody, 'request_id'> | null {
  const row = selected.value
  if (!row || !action.value || !allowed.value.includes(action.value)) return null
  const base: Omit<ReturnActionBody, 'request_id'> = { factory_id: factory.value, expected_revision: row.revision, source_fingerprint: row.source_fingerprint, action: action.value, reason: form.reason.trim() }
  if (base.reason.length < 4) { error.value = '请填写至少四字的凭证依据或处理原因。'; return null }
  if (needsReceipt.value) Object.assign(base, { quantity: form.quantity, receipt_date: form.receipt_date, document_no: form.document_no.trim() })
  if (needsCredit.value) Object.assign(base, { unit_price: form.unit_price, document_no: form.document_no.trim(), credit_date: form.credit_date })
  if (needsRefund.value) Object.assign(base, { kind: form.kind, amount: form.amount, refund_date: form.refund_date, document_no: form.document_no.trim() })
  if (needsTarget.value) base.target_event_id = form.target_event_id
  if (needsConfirmationReference.value) base.confirmation_reference = form.confirmation_reference.trim()
  if (needsReceipt.value && (!/^\d+(?:\.\d+)?$/.test(form.quantity) || Number(form.quantity) <= 0 || !form.receipt_date || !base.document_no)
    || needsCredit.value && (!/^\d+(?:\.\d+)?$/.test(form.unit_price) || !form.credit_date || !base.document_no)
    || needsRefund.value && (!/^\d+(?:\.\d+)?$/.test(form.amount) || Number(form.amount) <= 0 || !form.refund_date || !base.document_no)
    || needsTarget.value && !form.target_event_id
    || needsConfirmationReference.value && !form.confirmation_reference.trim()) {
    error.value = '请补齐本次数量、日期、金额及对应凭证；金额和数量请使用十进制数。'; return null
  }
  return base
}
async function submit() {
  if (busy.value || loading.value) return
  const body = payload(), row = selected.value
  if (!body || !row) return
  const token = generation, identity = JSON.stringify([row.movement_id, body])
  const request = requests.get(identity) || createRandomUuid(); requests.set(identity, request)
  busy.value = true; error.value = ''; message.value = ''
  try {
    const result = await api.act(row.movement_id, props.internal, { ...body, request_id: request }, controller.signal)
    if (token !== generation) return
    requests.delete(identity); selected.value = result; clearForm()
    message.value = '回执已保存，历史凭证保留。未核实的现金申报不表示已经到账。'
    emit('changed'); await load()
    if (token === generation && error.value) error.value = `回执已保存，列表刷新失败：${error.value}。请刷新核对，勿重复登记。`
  } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) busy.value = false }
}
async function dateSaved() {
  const row = selected.value
  if (!row) return
  const token = generation
  dateEditor.value = false
  await open(row)
  if (token !== generation) return
  message.value = '实际退货日期已更正，真实回款记录保留。请按新日期版本完成双方复核。'
  emit('changed'); await load()
}
function page(delta: number) { if (!busy.value && !loading.value) { offset.value += delta * limit; selected.value = null; clearForm(); void load() } }
onBeforeUnmount(() => { generation++; controller.abort(); if (searchTimer) clearTimeout(searchTimer) })
</script>

<template>
  <section class="space-y-4" aria-label="退货签收与退款">
    <header class="rounded-xl border border-teal-200 bg-card p-4">
      <div class="flex flex-wrap items-start justify-between gap-3"><div><h2 class="text-base font-semibold text-foreground">退货签收与退款</h2><p class="mt-2 max-w-4xl text-xs leading-5 text-muted-foreground">按实际退货逐纸品核对发出、分次签收、异议与贷项。现金退款须内部核实到账；月结抵扣只是贷项分配，不重复扣减。</p></div><Button type="button" variant="outline" size="sm" :disabled="busy || loading || !factory" @click="refresh">刷新退货</Button></div>
      <div class="mt-4 flex flex-wrap items-end gap-3 text-xs"><label v-if="options.length > 1">厂区<select v-model="factory" :disabled="busy" aria-label="退货厂区" class="mt-1 block h-10 rounded-lg border border-input bg-card px-3"><option v-for="id in options" :key="id" :value="id">{{ factoryName(id) }}</option></select></label><label v-if="search === undefined" class="min-w-48 flex-1">搜索退货<input v-model="query" aria-label="退货搜索" placeholder="客户 / 合同 / 货号 / 退货单" class="mt-1 block h-10 w-full rounded-lg border border-input bg-card px-3"></label><label class="flex h-10 items-center gap-2"><input v-model="history" :disabled="busy" type="checkbox" aria-label="显示全部退货历史">显示全部历史及未接入退货</label><span class="pb-3 text-muted-foreground">{{ history ? '全部历史' : '当前待办' }} · {{ total }} 笔</span></div>
      <p class="mt-2 text-xs text-muted-foreground">未接入协同的退货仅供查阅；可接入记录由内部明确启用，其他供方沿原手工贷项核对。原月结确认保留。</p>
    </header>
    <p v-if="error" role="alert" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{{ error }}</p><p v-if="message" role="status" class="rounded-lg border border-teal-200 bg-teal-50 p-3 text-sm text-teal-800">{{ message }}</p>
    <p v-if="loading && !rows.length" role="status" class="p-6 text-sm text-muted-foreground">正在读取退货与回执…</p>
    <div v-if="rows.length" class="overflow-hidden rounded-xl border bg-card"><div class="carton-table-wrap overflow-x-auto"><table aria-label="供应商退货协同明细" class="carton-table-fit w-full min-w-[980px] text-left text-xs"><thead class="bg-muted/50 text-muted-foreground"><tr><th class="p-3">退货来源 / 纸品</th><th class="p-3">发出 / 签收 / 异议</th><th class="p-3">贷项 / 退款 / 抵扣</th><th class="p-3">复核状态</th><th class="p-3">处理</th></tr></thead><tbody class="divide-y"><tr v-for="row in rows" :key="row.movement_id"><td data-label="退货来源 / 纸品" class="max-w-64 break-words p-3"><b>{{ row.document_no }}</b><p class="mt-1">{{ row.customer_name }} · {{ row.contract_no }} · {{ row.item_no }}</p><p class="mt-1">{{ row.packaging_type }} · {{ row.paper_quality }} · {{ row.specification }}</p><p class="mt-1 text-muted-foreground">{{ row.date_evidence?.date_basis === 'RETURN_ACTUAL' ? '实际退货' : '历史记账（实际退货日期待核实）' }} {{ row.date_evidence?.return_date || row.posting_date }}</p></td><td data-label="发出 / 签收 / 异议" class="p-3 tabular-nums"><p>发出 {{ row.quantity }} {{ row.unit }}</p><p class="mt-1">已签收 {{ row.received_quantity }} · 异议 {{ row.disputed_quantity }}</p><p class="mt-1">待签收 {{ row.remaining_quantity }} {{ row.unit }}</p></td><td data-label="贷项 / 退款 / 抵扣" class="p-3 tabular-nums"><b>贷项 {{ money(row.credit?.amount) }} {{ row.currency }}</b><p class="mt-1">已核实现金 {{ money(row.cash_confirmed_amount) }}</p><p class="mt-1">已分配抵扣 {{ money(row.offset_confirmed_amount) }}</p><p class="mt-1 text-muted-foreground">此退货累计净抵扣（跨月合计） {{ money(row.deduction_amount) }}</p></td><td data-label="复核状态" class="max-w-52 p-3"><b :class="row.pending ? 'text-amber-800' : 'text-teal-800'">{{ !row.enabled ? '未接入协同' : row.date_reconfirmation_required ? '日期已更正，待双方复核' : row.pending ? '待处理' : '已完成' }}</b><p class="mt-1">签收 {{ label(row.receipt_status) }} · 贷项 {{ label(row.credit_status) }}</p><p v-if="!row.source_active" class="mt-1 text-red-700">原退货已冲销，只读核对</p></td><td data-label="处理" class="p-3"><Button type="button" size="sm" variant="outline" :disabled="busy || loading" :aria-label="`查看退货 ${row.document_no}`" @click="open(row)">查看与处理</Button></td></tr></tbody></table></div>
      <nav class="flex items-center justify-end gap-3 border-t p-3 text-xs" aria-label="退货分页"><span>第 {{ Math.floor(offset / limit) + 1 }} 页 · 共 {{ total }} 笔</span><Button type="button" variant="outline" size="sm" :disabled="busy || loading || offset === 0" @click="page(-1)">上一页</Button><Button type="button" variant="outline" size="sm" :disabled="busy || loading || offset + limit >= total" @click="page(1)">下一页</Button></nav>
    </div>
    <p v-else-if="!loading && !error" class="rounded-xl border bg-card p-8 text-center text-sm text-muted-foreground">{{ history ? '没有匹配的退货记录。' : '当前没有退货待办。可查看全部历史及尚未接入的退货。' }}</p>
    <article v-if="selected" class="space-y-4 rounded-xl border border-teal-200 bg-card p-4" aria-label="退货回执详情">
      <div class="flex items-start justify-between gap-3"><div><h3 class="text-sm font-semibold">{{ selected.document_no }} · {{ selected.packaging_type }} {{ selected.item_no }}</h3><p class="mt-1 text-xs text-muted-foreground">{{ factoryName(selected.factory_id) }} · {{ selected.customer_name }} · {{ selected.contract_no }} · 版本 {{ selected.revision }}</p></div><Button type="button" size="sm" variant="ghost" :disabled="busy" @click="selected = null; clearForm()">收起</Button></div>
      <p v-if="selected.date_reconfirmation_required" class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">实际退货日期已更正。原签收和真实到账记录保留，双方须针对最新日期版本重新确认；未解决前不能完成相关月结。</p>
      <p v-if="!selected.enabled" class="rounded-lg bg-muted/50 p-3 text-xs text-muted-foreground">此退货未接入协同，原有账单不自动变更。可接入记录经内部明确启用后才产生供应商待办，其他供方沿原手工贷项流程核对。</p>
      <div class="grid gap-3 text-xs sm:grid-cols-2"><div class="rounded-lg bg-muted/40 p-3"><b>签收与异议记录</b><p v-if="!selected.receipts.length" class="mt-2 text-muted-foreground">尚未登记</p><p v-for="item in selected.receipts" :key="item.id" class="mt-2 break-words">{{ item.receipt_date }} · {{ item.document_no }} · {{ item.quantity }} {{ selected.unit }} · {{ item.decision === 'DISPUTE' ? '异议' : '签收' }} · {{ label(item.status) }}<span v-if="item.reason"> · {{ item.reason }}</span></p></div><div class="rounded-lg bg-muted/40 p-3"><b>退款 / 抵扣凭证</b><p v-if="!selected.refunds.length" class="mt-2 text-muted-foreground">尚未登记；现金申报待内部核实才计到账</p><p v-for="item in selected.refunds" :key="item.id" class="mt-2 break-words">{{ item.kind === 'CASH' ? '现金退款' : '月结抵扣' }} · {{ item.refund_date }} · {{ item.document_no }} · {{ item.amount }} {{ selected.currency }} · {{ label(item.status) }}<span v-if="item.confirmation_reference"> · 内部核实 {{ item.confirmation_reference }}</span></p></div></div>
      <p v-if="internal && !selected.date_evidence?.return_date" class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">此退货尚未核实实际日期。请先在双方月结按原记账月份 {{ selected.posting_date.slice(0, 7) }} 找到此退货，使用“核实实际退货日期”补证，再明确接入协同。</p><div v-if="allowed.length || canDate" class="flex flex-wrap items-center gap-3 text-xs"><label v-if="allowed.length">本次处理<select v-model="action" :disabled="busy || loading || dateEditor" aria-label="退货处理动作" class="ml-2 h-10 max-w-full rounded-lg border border-input bg-card px-3"><option value="">选择处理事项</option><option v-for="item in allowed" :key="item" :value="item">{{ actionLabels[item] }}</option></select></label><Button v-if="canDate" type="button" size="sm" variant="outline" :disabled="busy || loading" @click="action = ''; dateEditor = true">更正已录实际退货日期</Button></div>
      <CartonReturnDateEditor v-if="dateEditor" :factory-id="factory" :movement-id="selected.movement_id" :viewer-key="viewerKey" @saved="dateSaved" @close="dateEditor = false" />
      <form v-if="action" class="space-y-3 rounded-lg border border-input p-4 text-xs" aria-label="退货处理表单" @submit.prevent="submit">
        <h4 class="font-semibold">{{ actionLabels[action] }}</h4><p v-if="action === 'ENROLL'" class="text-amber-900">接入后将按当前退货建立签收与贷项待办。请先核实历史是否已退款或抵扣，避免重复处理。</p><p v-if="action === 'VOID'" class="text-amber-900">用于有依据地更正错误凭证，原记录保留。真实已到账资金不会因日期更正自动撤回；此处请核实具体错误凭证及更正依据。</p>
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <label v-if="needsReceipt">本次数量<input v-model="form.quantity" :disabled="busy" required inputmode="decimal" aria-label="本次签收或异议数量" class="mt-1 block h-10 w-full rounded-lg border border-input bg-card px-3"></label><label v-if="needsReceipt">签收 / 异议日期<input v-model="form.receipt_date" :disabled="busy" required type="date" :max="today()" aria-label="签收或异议日期" class="mt-1 block h-10 w-full rounded-lg border border-input bg-card px-3"></label>
          <label v-if="needsCredit">整笔退货认可单价<input v-model="form.unit_price" :disabled="busy" required inputmode="decimal" aria-label="整笔退货贷项单价" class="mt-1 block h-10 w-full rounded-lg border border-input bg-card px-3"></label><label v-if="needsCredit">贷项日期<input v-model="form.credit_date" :disabled="busy" required type="date" :max="today()" aria-label="退货贷项日期" class="mt-1 block h-10 w-full rounded-lg border border-input bg-card px-3"></label>
          <label v-if="needsRefund">处理方式<select v-model="form.kind" :disabled="busy" aria-label="退款或抵扣方式" class="mt-1 block h-10 w-full rounded-lg border border-input bg-card px-3"><option value="CASH">现金退款（内部核实到账）</option><option value="OFFSET">月结抵扣（不再另减）</option></select></label><label v-if="needsRefund">本次金额 · {{ selected.currency }}<input v-model="form.amount" :disabled="busy" required inputmode="decimal" aria-label="本次退款或抵扣金额" class="mt-1 block h-10 w-full rounded-lg border border-input bg-card px-3"></label><label v-if="needsRefund">{{ form.kind === 'CASH' ? '实际到账日期' : '抵扣凭证日期' }}<input v-model="form.refund_date" :disabled="busy" required type="date" :max="today()" aria-label="退款或抵扣日期" class="mt-1 block h-10 w-full rounded-lg border border-input bg-card px-3"></label>
          <label v-if="needsReceipt || needsCredit || needsRefund">凭证单号<input v-model="form.document_no" :disabled="busy" required maxlength="128" aria-label="退货处理凭证单号" class="mt-1 block h-10 w-full rounded-lg border border-input bg-card px-3"></label><label v-if="needsTarget" class="sm:col-span-2">对应凭证<select v-model="form.target_event_id" :disabled="busy" required aria-label="对应退货凭证" class="mt-1 block h-10 w-full rounded-lg border border-input bg-card px-3"><option value="">请选择对应凭证</option><option v-for="item in targets" :key="item.id" :value="item.id">{{ item.label }}</option></select></label><label v-if="needsConfirmationReference">内部核实 / 更正凭证<input v-model="form.confirmation_reference" :disabled="busy" required maxlength="128" aria-label="内部到账或抵扣核实凭证" class="mt-1 block h-10 w-full rounded-lg border border-input bg-card px-3"></label>
          <label class="sm:col-span-2 lg:col-span-3">凭证依据 / 处理原因<textarea v-model="form.reason" :disabled="busy" required minlength="4" maxlength="2000" rows="2" aria-label="退货处理原因" class="mt-1 block w-full rounded-lg border border-input bg-card px-3 py-2" /></label>
        </div><p v-if="needsRefund" class="text-muted-foreground">供货 − 退货贷项 + 本月已确认现金退款 = 本期净应结。现金退款按实际到账月份计入，避免再由月结重复抵扣；未核实申报不自动计到账。</p><div class="flex gap-2"><Button size="sm" :disabled="busy || loading">{{ busy ? '正在保存…' : '保存本次回执' }}</Button><Button type="button" variant="outline" size="sm" :disabled="busy" @click="clearForm">返回详情</Button></div>
      </form>
      <details v-if="selected.credits?.length" class="rounded-lg border border-input p-3 text-xs"><summary class="cursor-pointer font-semibold">历次退货贷项凭证（{{ selected.credits.length }}）</summary><div v-for="credit in selected.credits" :key="credit.id" class="mt-3 space-y-1 break-words border-t pt-2"><p><b>{{ credit.document_no }}</b> · {{ credit.credit_date }} · {{ label(credit.status) }}</p><p>认可单价 {{ credit.unit_price }} · 整笔贷项 {{ credit.amount }} {{ selected.currency }}</p><p v-if="credit.actor_name">提议 {{ credit.actor_name }} · {{ credit.created_at }}</p><p v-if="credit.confirmed_by">内部核实 {{ credit.confirmed_by }} · {{ credit.confirmed_at }}</p><p v-if="credit.reason">依据：{{ credit.reason }}</p></div></details><details v-if="selected.date_history?.length" class="rounded-lg border border-input p-3 text-xs"><summary class="cursor-pointer font-semibold">实际退货日期版本历史</summary><p v-for="entry in selected.date_history" :key="entry.id" class="mt-3 break-words border-t pt-2">{{ entry.created_at }} · {{ entry.actor_name }} · {{ entry.before_date || '首次核实' }} → {{ entry.return_date }}<span v-if="entry.revision"> · 日期版本 {{ entry.revision }}</span><span v-if="entry.reason"> · {{ entry.reason }}</span></p></details><details class="rounded-lg border border-input p-3 text-xs"><summary class="cursor-pointer font-semibold">历史凭证与操作记录（{{ selected.history.length }}）</summary><p v-for="item in selected.history" :key="item.id" class="mt-3 whitespace-pre-wrap break-words border-t pt-2">{{ item.created_at }} · {{ item.actor_name }} · {{ actionLabels[item.action as ReturnAction] || item.action }}<span v-if="item.reason"> · {{ item.reason }}</span></p></details>
    </article>
  </section>
</template>
