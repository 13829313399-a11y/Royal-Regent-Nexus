<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import StatusPill from '@/components/common/StatusPill.vue'
import CartonFilterBar from '@/components/CartonFilterBar.vue'
import { cartonPayablesApi as api, pendingPayableAction, clearPendingPayableAction, type PayableAction, type PayableActionName, type PayableDetail, type PayableEntry, type PayableKind, type PayablesWorkspace } from '@/api/cartonPayables'
import { getApiErrorMessage, getApiErrorMessageAsync } from '@/lib/http'
import { formatBusinessDate, formatBusinessDateTime } from '@/lib/dateTime'
import { factoryContexts } from '@/data/enterpriseMock'
import '@/features/carton-procurement/layout.css'

const props = withDefaults(defineProps<{ internal?: boolean; factoryId?: string; factories?: { factory_id: string }[]; viewerKey: string; search?: string }>(), { internal: false, factoryId: '' })
const emit = defineEmits<{ 'update:search': [value: string]; changed: [] }>()
const options = computed(() => [...new Set(props.internal ? [props.factoryId].filter(Boolean) : props.factories?.map(row => row.factory_id) || [])])
const factory = ref(''), currency = ref('CNY'), localSearch = ref('')
const query = computed({ get: () => props.search ?? localSearch.value, set: value => { if (props.search === undefined) localSearch.value = value; else emit('update:search', value) } })
const kind = ref<'ALL' | PayableKind>('ALL'), status = ref<'ALL' | 'PENDING'>('ALL'), offset = ref(0), limit = 25
const view = ref<'OVERVIEW' | 'RECORDS' | 'ALLOCATIONS'>('OVERVIEW')
const focusAllocationId = ref('')
const workspace = ref<PayablesWorkspace | null>(null), selected = ref<PayableDetail | null>(null)
const loading = ref(false), busy = ref(false), exporting = ref(false), error = ref(''), message = ref('')
const action = ref<PayableActionName | ''>(''), basis = ref<{ revision: number; source_fingerprint: string } | null>(null)
const pending = ref<PayableAction | null>(null)
const form = reactive({ amount: '', date: '', document_no: '', reason: '', direction: 'PAYABLE', category: 'FREIGHT', related_settlement_id: '', bank_reference: '', confirmation_reference: '', correction_reference: '', parent_payment_id: '', decision: 'CONFIRMED', acknowledge_unknown_sources: false })
const sourceId = ref(''), amounts = ref<Record<string, string>>({}), checkedTargets = ref<string[]>([]), releaseIds = ref<string[]>([])
const actionLabels: Record<PayableActionName, string> = { PROPOSE_OPENING: '提出期初余额', REVIEW_OPENING: '核对期初余额', CONFIRM_OPENING: '内部确认期初', PROPOSE_FEE: '提出独立费用', REVISE_FEE: '更正独立费用', VOID_FEE: '提出费用作废', REVIEW_FEE: '核对独立费用', CONFIRM_FEE: '内部确认费用', RECORD_PAYMENT: '登记实际付款', RECEIVE_PAYMENT: '确认收款或提出异议', DECLARE_PAYMENT_RETURN: '声明预付款实际退回', CONFIRM_PAYMENT_RETURN: '内部核实预付款退回', REQUEST_VOID: '申请更正错误资金记录', REVIEW_VOID: '核对错误记录更正', CONFIRM_VOID: '内部完成错误记录更正', ALLOCATE: '登记核销分配', DEALLOCATE: '解除原核销分配' }
const kindLabels: Record<string, string> = { OPENING: '期初余额', FEE: '独立费用', PAYMENT: '本厂付款', PAYMENT_RETURN: '预付款实际退回', SETTLEMENT: '货款月结', CREDIT: '贷方抵扣' }
const statusLabels: Record<string, string> = { PENDING_SUPPLIER: '供应商待核对', SUPPLIER_CONFIRMED: '供应商已确认，内部待确认', DISPUTED: '有异议', EFFECTIVE: '生效', SUPERSEDED: '历史版本', VOID: '已作废，证据保留', RECORDED: '已登记付款，收款待回执', RECEIVED: '供应商已确认收款', PENDING: '待回执', CONFIRMED: '已确认', DECLARED: '待内部核实入款', VOID_PENDING_SUPPLIER: '错误更正待供应商确认', VOID_PENDING_INTERNAL: '错误更正待内部完成', ACTIVE: '生效', RELEASED: '已解除', CURRENT: '当前有效', REOPENED_HOLD: '重核中，旧金额暂计', STALE: '依据变化，待重核' }
function focusAllocation(id: string | undefined, targetCurrency: string) { currency.value = targetCurrency; focusAllocationId.value = id || ''; view.value = 'ALLOCATIONS' }
defineExpose({ focusAllocation })
const focusedAllocation = computed(() => workspace.value?.allocations.find(row => row.id === focusAllocationId.value))
const label = (value?: string) => value ? statusLabels[value] || value : '未记录'
const money = (value?: string | null) => value == null ? '待核实' : value
const name = (id: string) => factoryContexts.find(row => row.id === id)?.name || id
const today = () => formatBusinessDate(new Date().toISOString())
const context = computed(() => JSON.stringify([options.value, factory.value, currency.value, props.viewerKey, props.internal]))
const allowed = (value: PayableActionName) => !!workspace.value?.allowed_actions.includes(value) && !pending.value
const externalActions: PayableActionName[] = ['REVIEW_OPENING', 'REVIEW_FEE', 'RECEIVE_PAYMENT', 'DECLARE_PAYMENT_RETURN', 'REVIEW_VOID']
const visibleAction = (value: string): value is PayableActionName => Object.prototype.hasOwnProperty.call(actionLabels, value) && (props.internal ? !externalActions.includes(value as PayableActionName) : externalActions.includes(value as PayableActionName))
const detailStale = computed(() => !!selected.value && !!workspace.value && (selected.value.account_revision !== workspace.value.revision || selected.value.source_fingerprint !== workspace.value.source_fingerprint))
const editorStale = computed(() => !!basis.value && !!workspace.value && (basis.value.revision !== workspace.value.revision || basis.value.source_fingerprint !== workspace.value.source_fingerprint))
const detailActions = computed(() => selected.value?.allowed_actions.filter(visibleAction) || [])
const createActions = computed(() => (props.internal ? ['PROPOSE_OPENING', 'PROPOSE_FEE', 'RECORD_PAYMENT'] : ['DECLARE_PAYMENT_RETURN']).filter(value => workspace.value?.allowed_actions.includes(value)) as PayableActionName[])
const source = computed(() => workspace.value?.allocation_sources.find(row => row.id === sourceId.value))
const targets = computed(() => workspace.value?.obligations.filter(row => row.direction === 'DEBIT' && row.can_allocate) || [])
const allocationTotal = computed(() => {
  if (!checkedTargets.value.length) return '0.00'
  let cents = 0n
  for (const id of checkedTargets.value) {
    const value = amounts.value[id] || ''
    if (!validMoney(value)) return '待填写完整金额'
    const [whole = '0', decimal = ''] = value.split('.')
    cents += BigInt(whole) * 100n + BigInt(decimal.padEnd(2, '0'))
  }
  return `${cents / 100n}.${String(cents % 100n).padStart(2, '0')}`
})
const returnParents = computed(() => workspace.value?.allocation_sources.filter(row => row.source_kind === 'PAYMENT' && row.can_declare_payment_return) || [])
const relatedBills = computed(() => workspace.value?.obligations.filter(row => row.kind === 'SETTLEMENT') || [])
const feeAction = computed(() => ['PROPOSE_FEE', 'REVISE_FEE'].includes(action.value))
const amountAction = computed(() => ['PROPOSE_OPENING', 'PROPOSE_FEE', 'REVISE_FEE', 'RECORD_PAYMENT', 'DECLARE_PAYMENT_RETURN'].includes(action.value))
const reviewAction = computed(() => ['REVIEW_OPENING', 'REVIEW_FEE', 'RECEIVE_PAYMENT', 'REVIEW_VOID'].includes(action.value))
const correctionAction = computed(() => ['REQUEST_VOID', 'REVIEW_VOID', 'CONFIRM_VOID'].includes(action.value))
const signedDirection = (row: PayableEntry) => row.kind === 'PAYMENT' ? '减少记录余额（本厂付款）' : row.kind === 'PAYMENT_RETURN' ? '增加记录余额（预付款退回）' : (row.active?.signed_amount || row.signed_amount || '').startsWith('-') ? '减少应付 / 贷方' : '增加应付'
const nextStep = (row: PayableEntry) => row.kind === 'PAYMENT' ? row.receipt_status === 'CONFIRMED' ? '收款已回执，可按可用额度办理核销' : '付款已计账，等待供应商确认收款；暂不可核销' : row.active && row.proposal ? '旧有效金额暂计，待新版本双方确认' : row.proposal ? '待双方核对当前提议' : row.kind === 'PAYMENT_RETURN' ? '实际退回须内部核实入款，独立于物料退货现金' : '查看生效依据或核实当前状态'
const directAction = (row: PayableEntry) => row.allowed_actions.filter(visibleAction).find(value => ['REVIEW_OPENING', 'REVIEW_FEE', 'CONFIRM_OPENING', 'CONFIRM_FEE', 'RECEIVE_PAYMENT', 'CONFIRM_PAYMENT_RETURN'].includes(value))
const recordButton = (row: PayableEntry) => { const value = directAction(row); return value ? actionLabels[value] : '详情与处理' }
let generation = 0, listSequence = 0, detailSequence = 0, controller = new AbortController(), timer: ReturnType<typeof setTimeout> | undefined
function resetEditor() { action.value = ''; basis.value = null; sourceId.value = ''; checkedTargets.value = []; amounts.value = {}; releaseIds.value = []; Object.assign(form, { amount: '', date: '', document_no: '', reason: '', direction: 'PAYABLE', category: 'FREIGHT', related_settlement_id: '', bank_reference: '', confirmation_reference: '', correction_reference: '', parent_payment_id: '', decision: 'CONFIRMED', acknowledge_unknown_sources: false }) }
function readPending() { pending.value = pendingPayableAction(props.internal, factory.value, currency.value, props.viewerKey) }
watch(options, ids => { if (!ids.includes(factory.value)) factory.value = ids[0] || '' }, { immediate: true })
watch(context, () => {
  generation++; listSequence++; detailSequence++; controller.abort(); controller = new AbortController(); workspace.value = null; selected.value = null; offset.value = 0; error.value = ''; message.value = ''; busy.value = false; exporting.value = false; resetEditor(); readPending(); void load()
}, { immediate: true, flush: 'sync' })
watch([kind, status, query], () => { if (timer) clearTimeout(timer); listSequence++; offset.value = 0; timer = setTimeout(() => { void load() }, 250) })
async function load() {
  if (!factory.value || !currency.value.trim()) { loading.value = false; return }
  const token = generation, read = ++listSequence
  loading.value = true; error.value = ''
  try {
    const data = await api.workspace(props.internal, { factory_id: factory.value, currency: currency.value, kind: kind.value, status: status.value, keyword: query.value.trim(), limit, offset: offset.value }, controller.signal)
    if (token === generation && read === listSequence) { workspace.value = data; readPending() }
  } catch (cause) { if (token === generation && read === listSequence) { workspace.value = null; error.value = getApiErrorMessage(cause) } }
  finally { if (token === generation && read === listSequence) loading.value = false }
}
async function open(row: PayableEntry, direct = false) {
  if (busy.value || loading.value) return
  const token = generation, read = ++detailSequence
  loading.value = true; error.value = ''; selected.value = null; resetEditor()
  try {
    const detail = await api.detail(props.internal, row.id, { factory_id: factory.value, currency: currency.value }, controller.signal)
    if (token === generation && read === detailSequence) selected.value = detail
  } catch (cause) { if (token === generation && read === detailSequence) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation && read === detailSequence) loading.value = false }
  if (direct && token === generation && read === detailSequence && selected.value) { const next = directAction(selected.value); if (next) begin(next, selected.value) }
}
function begin(value: PayableActionName, row?: PayableEntry) {
  if (busy.value || loading.value || pending.value || !workspace.value || !visibleAction(value)) return
  if (row ? !row.allowed_actions.includes(value) || detailStale.value : !allowed(value)) return
  resetEditor(); action.value = value; basis.value = { revision: workspace.value.revision, source_fingerprint: workspace.value.source_fingerprint }
  if (!row) selected.value = null
  const entry = row || (value === 'PROPOSE_OPENING' ? workspace.value.opening : null), prior = entry?.proposal || entry?.active
  if (prior) Object.assign(form, { amount: prior.amount, date: prior.cutoff_date || prior.date, document_no: prior.document_no, direction: prior.direction, category: prior.category || 'FREIGHT', related_settlement_id: prior.related_settlement_id || '' })
  if (feeAction.value && !prior) form.direction = 'ADD_PAYABLE'
  if (value === 'PROPOSE_OPENING' && workspace.value.opening?.active) form.date = workspace.value.opening.active.cutoff_date || workspace.value.opening.active.date
  error.value = ''; message.value = ''
}
const validMoney = (value: string, zero = false) => /^\d+(?:\.\d{1,2})?$/.test(value) && (zero || /[1-9]/.test(value))
function build(): Omit<PayableAction, 'request_id'> | null {
  if (!workspace.value || !action.value || !basis.value || editorStale.value || !visibleAction(action.value)) return null
  const body: Omit<PayableAction, 'request_id'> = { factory_id: factory.value, supplier_id: workspace.value.supplier_id, currency: currency.value, expected_revision: basis.value.revision, source_fingerprint: basis.value.source_fingerprint, action: action.value, reason: form.reason.trim() }
  if (body.reason.length < 4) { error.value = '请填写至少四字的凭证依据或处理原因。'; return null }
  if (!['PROPOSE_OPENING', 'PROPOSE_FEE', 'RECORD_PAYMENT', 'DECLARE_PAYMENT_RETURN', 'ALLOCATE', 'DEALLOCATE'].includes(action.value)) {
    if (!selected.value?.allowed_actions.includes(action.value) || detailStale.value) return null
    body.target_id = selected.value.id
  }
  if (amountAction.value) {
    if (!validMoney(form.amount, action.value === 'PROPOSE_OPENING') || !form.date || !form.document_no.trim()) { error.value = '请补齐真实日期、凭证号和金额（最多两位小数）。'; return null }
    Object.assign(body, { amount: form.amount, document_no: form.document_no.trim() })
  }
  if (action.value === 'PROPOSE_OPENING') Object.assign(body, { cutoff_date: form.date, direction: form.direction, acknowledge_unknown_sources: form.acknowledge_unknown_sources })
  if (feeAction.value) Object.assign(body, { fee_date: form.date, direction: form.direction, category: form.category, ...(form.related_settlement_id ? { related_settlement_id: form.related_settlement_id } : {}) })
  if (action.value === 'RECORD_PAYMENT' || action.value === 'DECLARE_PAYMENT_RETURN') {
    if (!form.bank_reference.trim()) { error.value = '请填写实际资金凭证或银行流水依据。'; return null }
    body.bank_reference = form.bank_reference.trim()
    if (action.value === 'RECORD_PAYMENT') body.payment_date = form.date
    else { if (!returnParents.value.some(row => row.record_id === form.parent_payment_id)) { error.value = '请选择服务器允许实际退回的原付款。'; return null }; body.parent_payment_id = form.parent_payment_id; body.return_date = form.date }
  }
  if (reviewAction.value) body.decision = form.decision as 'CONFIRMED' | 'DISPUTED'
  if (action.value === 'CONFIRM_PAYMENT_RETURN') { if (!form.confirmation_reference.trim()) { error.value = '请填写实际入款核实凭证。'; return null }; body.confirmation_reference = form.confirmation_reference.trim() }
  if (['REQUEST_VOID', 'CONFIRM_VOID'].includes(action.value)) { if (!form.correction_reference.trim()) { error.value = '请填写错误登记的更正凭证。'; return null }; body.correction_reference = form.correction_reference.trim() }
  if (action.value === 'ALLOCATE') {
    if (!allowed('ALLOCATE') || !source.value?.can_allocate || !checkedTargets.value.length || checkedTargets.value.length > 100 || checkedTargets.value.some(id => !targets.value.some(row => row.id === id) || !validMoney(amounts.value[id] || ''))) { error.value = '请显式选择有效资金或贷方来源及正应付目标，并逐项填写本次核销额（每次最多100项）。'; return null }
    Object.assign(body, { source_kind: source.value.source_kind, source_id: source.value.id, targets: targets.value.filter(row => checkedTargets.value.includes(row.id)).map(row => ({ target_kind: row.kind, target_id: row.id, amount: amounts.value[row.id]! })) })
  }
  if (action.value === 'DEALLOCATE') { if (!allowed('DEALLOCATE') || !releaseIds.value.length || releaseIds.value.length > 100 || releaseIds.value.some(id => !workspace.value?.allocations.some(row => row.id === id && row.status === 'ACTIVE'))) { error.value = '请选择仍生效的原核销记录。'; return null }; body.allocation_ids = [...releaseIds.value] }
  return body
}
async function send(body: Omit<PayableAction, 'request_id'>) {
  if (busy.value || loading.value) return
  const token = generation, viewer = props.viewerKey
  listSequence++; detailSequence++
  busy.value = true; error.value = ''; message.value = ''
  try {
    const result = await api.act(props.internal, body, viewer, controller.signal)
    if (token !== generation) return
    workspace.value = result; selected.value = null; resetEditor(); readPending(); emit('changed')
    message.value = `${actionLabels[body.action]}已保存。付款、收款回执与核销分别记录；本操作不执行银行转账。`
    await load()
    if (token === generation && error.value) error.value = `操作已保存，但往来余额刷新失败：${error.value}。请刷新核对，勿重复登记。`
  } catch (cause) { if (token === generation) { readPending(); error.value = getApiErrorMessage(cause) } }
  finally { if (token === generation) busy.value = false }
}
function submit() { if (!pending.value) { const body = build(); if (body) void send(body) } }
function retry() { if (pending.value) { const { request_id: ignored, ...body } = pending.value; void send(body) } }
function checkedPending() {
  if (busy.value || !window.confirm('请先核对往来凭证和核销历史。此操作仅清除此浏览器的待核实标识，不撤销任何记录；已经登记的业务不能重复创建。确认已核对原请求结果？')) return
  clearPendingPayableAction(props.internal, factory.value, currency.value, props.viewerKey); readPending(); resetEditor()
}
async function download() {
  if (exporting.value || !workspace.value) return
  const token = generation; exporting.value = true; error.value = ''
  try {
    const blob = await api.export(props.internal, { factory_id: factory.value, currency: currency.value }, controller.signal)
    if (token !== generation) return
    const url = URL.createObjectURL(blob), anchor = document.createElement('a'); anchor.href = url; anchor.download = `${factory.value}-供应商往来-${currency.value}.csv`; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
    message.value = '已导出同厂区、供应商、币种的完整往来账，未按当前页面筛选截断。'
  } catch (cause) { const detail = await getApiErrorMessageAsync(cause); if (token === generation) error.value = `导出失败：${detail}` }
  finally { if (token === generation) exporting.value = false }
}
function page(delta: number) { if (!loading.value && !busy.value) { offset.value += delta * limit; void load() } }
onBeforeUnmount(() => { generation++; controller.abort(); if (timer) clearTimeout(timer) })
</script>

<template>
  <section class="space-y-4" :aria-label="internal ? '应付与付款' : '应付与收款'">
    <p v-if="focusedAllocation" class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900" aria-label="单价更正关联核销">正在核对原分配：{{ focusedAllocation.source_document_no || '原资金凭证' }} → {{ focusedAllocation.target_document_no || '原应付凭证' }} · {{ focusedAllocation.target_period }} · 版本 {{ focusedAllocation.target_version }} · {{ focusedAllocation.amount }}。请在核销记录核对后显式解除；真实付款保留。</p>
    <header class="rounded-xl border border-teal-200 bg-card p-4"><h2 class="text-base font-semibold">{{ internal ? '应付与付款' : '应付与收款' }}</h2><p class="mt-2 text-xs leading-5 text-muted-foreground">期初、独立费用与货款月结分别留证。真实付款登记即计入本厂记录余额，供应商确认收款后才能核销；核销只分配款项，不再扣一次余额。本页记录不执行银行操作。</p><CartonFilterBar label="供应商往来范围" class="mt-3"><label>厂区<select v-model="factory" :disabled="busy" aria-label="应付厂区" class="mt-1 block h-10 rounded-lg border border-input bg-card px-3"><option v-for="id in options" :key="id" :value="id">{{ name(id) }}</option></select></label><label>原账币种<input :value="currency" @change="currency = ($event.target as HTMLInputElement).value.trim().toUpperCase()" :disabled="busy" aria-label="应付币种" maxlength="8" class="mt-1 block h-10 w-24 rounded-lg border border-input bg-card px-3"></label><label v-if="search === undefined">凭证关键词<input v-model="query" aria-label="应付关键词" class="mt-1 block h-10 rounded-lg border border-input bg-card px-3" placeholder="凭证号 / 摘要 / 依据"></label><template #actions><Button type="button" variant="outline" :disabled="busy || loading || !factory" @click="load">刷新往来账</Button><Button type="button" variant="outline" :disabled="busy || loading || exporting || !workspace" @click="download">导出完整往来账 CSV</Button></template></CartonFilterBar><p class="mt-2 text-xs text-muted-foreground">{{ workspace?.supplier_name || '供应商待读取' }} · 原账 {{ currency }} · 仅纳入已确认货款、有效期初及费用；未确认账单不计入。退货现金已在货款月结净额内，不重复计账。</p></header>
    <p v-if="error" role="alert" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{{ error }}</p><p v-if="message" role="status" class="rounded-lg border border-teal-200 bg-teal-50 p-3 text-sm text-teal-800">{{ message }}</p>
    <aside v-if="pending" class="space-y-2 rounded-xl border border-amber-300 bg-amber-50 p-4 text-xs" aria-label="往来请求结果待核实"><b>原请求结果待核实 · {{ actionLabels[pending.action] }}</b><p>先刷新记录核对；重试将发送原内容、原版本与同一请求标识。未核实前暂不创建其他写入。</p><div class="flex flex-wrap gap-2"><Button type="button" variant="outline" size="sm" :disabled="busy || loading" @click="retry">重试原未确认请求</Button><Button type="button" variant="ghost" size="sm" :disabled="busy" @click="checkedPending">已核对记录，解除待核实状态</Button></div></aside>
    <p v-if="loading && !workspace" role="status" class="p-8 text-center text-sm text-muted-foreground">正在读取供应商往来与核销证据…</p>
    <template v-if="workspace">
      <template v-if="workspace.opening?.active">
      <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="应付余额汇总"><div class="rounded-xl border bg-card p-4"><p class="text-xs text-muted-foreground">本厂按记录计算余额</p><b class="mt-2 block text-xl tabular-nums">{{ money(workspace.summary.balance_due_signed) }} {{ workspace.currency }}</b><p class="mt-2 text-xs text-muted-foreground">正数为应付；负数为预付 / 贷方余额。</p></div><div class="rounded-xl border bg-card p-4"><p class="text-xs text-muted-foreground">供应商尚未确认收款（待回执／异议）</p><b class="mt-2 block text-xl tabular-nums">{{ money(workspace.summary.paid_awaiting_receipt) }}</b><p class="mt-2 text-xs text-muted-foreground">已扣记录余额，尚不能核销。</p></div><div class="rounded-xl border bg-card p-4"><p class="text-xs text-muted-foreground">未分配付款</p><b class="mt-2 block text-xl tabular-nums">{{ money(workspace.summary.unapplied_payment) }}</b><p class="mt-2 text-xs text-muted-foreground">超付保留；不自动结清指定账单。</p></div><div class="rounded-xl border bg-card p-4"><p class="text-xs text-muted-foreground">未分配贷方抵扣</p><b class="mt-2 block text-xl tabular-nums">{{ money(workspace.summary.unapplied_credit) }}</b><p class="mt-2 text-xs text-muted-foreground">负期初、费用或月结的可用贷方。</p></div></div>
      <div class="rounded-lg border bg-card p-3 text-xs leading-6 tabular-nums">期初 {{ money(workspace.summary.opening_signed) }} + 已确认货款净额 {{ money(workspace.summary.confirmed_settlements) }} + 独立费用 {{ money(workspace.summary.fees_signed) }} − 本厂实际付款 {{ money(workspace.summary.internal_paid) }} + 已确认预付款退回 {{ money(workspace.summary.payment_returns_confirmed) }} = 记录余额 {{ money(workspace.summary.balance_due_signed) }} {{ workspace.currency }}<p class="text-muted-foreground">供应商已回执 {{ money(workspace.summary.supplier_received) }} · 累计核销 {{ money(workspace.summary.allocated) }}。核销不改变上述公式；退货现金退款与预付款退回是不同来源。</p></div>
      </template>
      <p v-else class="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900" aria-label="应付账户尚未启用">尚未建立有效期初余额：请先核对固定切账月首与未结余额，完成供应商及内部确认后启用账户。目前的零值只是未启用占位，不代表零欠款或已经结清。</p>
      <p v-if="workspace.summary.needs_reconfirmation" class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">历史依据或版本待重核：旧确认金额暂计，相关来源禁止新增核销。请完成双方重核，不会自动迁移旧分配。</p><p v-for="(issue, i) in workspace.issues" :key="i" class="text-xs text-amber-800">{{ issue }}</p>
      <nav aria-label="应付工作区" class="flex flex-wrap gap-2 rounded-xl border bg-card p-2 text-xs"><Button v-for="tab in [{ id: 'OVERVIEW' as const, label: '应付来源总览' }, { id: 'RECORDS' as const, label: '期初、费用与资金凭证' }, { id: 'ALLOCATIONS' as const, label: '核销与解除记录' }]" :key="tab.id" type="button" :variant="view === tab.id ? 'default' : 'ghost'" size="sm" :aria-pressed="view === tab.id" @click="view = tab.id">{{ tab.label }}</Button></nav>
      <div class="flex flex-wrap gap-2"><Button v-for="value in createActions" :key="value" type="button" variant="outline" size="sm" :disabled="busy || loading || !!pending" @click="begin(value)">{{ actionLabels[value] }}</Button><Button v-if="internal && workspace.allowed_actions.includes('ALLOCATE')" type="button" variant="outline" size="sm" :disabled="busy || loading || !!pending" @click="begin('ALLOCATE')">登记核销分配</Button><Button v-if="internal && workspace.allowed_actions.includes('DEALLOCATE')" type="button" variant="outline" size="sm" :disabled="busy || loading || !!pending" @click="begin('DEALLOCATE')">解除原核销分配</Button></div>
      <div v-if="view === 'OVERVIEW'" class="overflow-hidden rounded-xl border bg-card"><p class="p-3 text-xs text-muted-foreground">全部已确认应付 / 贷方来源，独立于凭证分页与关键词。剩余可分配额为正数幅度，不替代带方向余额。</p><div class="carton-table-wrap overflow-x-auto"><table aria-label="应付来源明细" class="carton-table-fit w-full text-left text-xs"><thead class="bg-muted/50"><tr><th class="p-3">来源 / 原凭证</th><th class="p-3">日期 / 版本</th><th class="p-3 text-right">原账方向 / 金额</th><th class="p-3 text-right">已核销 / 剩余</th><th class="p-3">当前依据</th></tr></thead><tbody class="divide-y"><tr v-for="row in workspace.obligations" :key="row.id"><td data-label="来源 / 原凭证" class="p-3"><b>{{ kindLabels[row.kind] }} · {{ row.document_no }}</b></td><td data-label="日期 / 版本" class="p-3">{{ row.period || row.date }} · 版本 {{ row.version }}</td><td data-label="原账方向 / 金额" class="p-3 text-right tabular-nums">{{ row.direction === 'CREDIT' ? '贷方抵扣' : '正应付' }} {{ money(row.signed_amount) }} {{ row.currency }}</td><td data-label="已核销 / 剩余" class="p-3 text-right tabular-nums">已核销 {{ money(row.allocated_amount) }}<p class="mt-1">剩余 {{ money(row.remaining_amount) }}</p></td><td data-label="当前依据" class="p-3"><StatusPill :label="label(row.status)" :tone="row.can_allocate ? 'teal' : 'amber'" compact /><p v-if="!row.can_allocate" class="mt-2 text-muted-foreground">当前不可新增核销</p></td></tr><tr v-if="!workspace.obligations.length"><td colspan="5" class="p-8 text-center text-muted-foreground">当前没有纳入的已确认应付来源；这不表示所有待核对账单均已结清。</td></tr></tbody></table></div></div>
      <section v-if="view === 'RECORDS'" class="space-y-3"><CartonFilterBar label="应付凭证筛选"><label>凭证类型<select v-model="kind" :disabled="busy" aria-label="应付凭证类型" class="ml-2 h-10 rounded-lg border border-input bg-card px-3"><option value="ALL">全部凭证</option><option v-for="value in ['OPENING', 'FEE', 'PAYMENT', 'PAYMENT_RETURN']" :key="value" :value="value">{{ kindLabels[value] }}</option></select></label><label>处理状态<select v-model="status" :disabled="busy" aria-label="应付凭证状态" class="ml-2 h-10 rounded-lg border border-input bg-card px-3"><option value="ALL">全部</option><option value="PENDING">待处理</option></select></label><template #footer><span>当前筛选 {{ workspace.records.total }} 笔；摘要和核销额度仍按完整账户计算。</span></template></CartonFilterBar><div class="overflow-hidden rounded-xl border bg-card"><div class="carton-table-wrap overflow-x-auto"><table aria-label="应付往来凭证" class="carton-table-fit w-full text-left text-xs"><thead class="bg-muted/50"><tr><th class="p-3">凭证 / 日期</th><th class="p-3">记录方向 / 金额</th><th class="p-3">有效值与待确认</th><th class="p-3">处理</th></tr></thead><tbody class="divide-y"><tr v-for="row in workspace.records.items" :key="row.id"><td data-label="凭证 / 日期" class="p-3"><b>{{ kindLabels[row.kind] }} · {{ row.document_no }}</b><p class="mt-2">{{ row.date }}</p></td><td data-label="记录方向 / 金额" class="p-3 tabular-nums">{{ signedDirection(row) }}<p class="mt-2">原金额 {{ money(row.active?.amount ?? row.amount) }} {{ row.currency }}</p></td><td data-label="有效值与待确认" class="p-3"><StatusPill :label="label(row.status)" compact /><p v-if="row.proposal && row.active" class="mt-2 text-amber-800">旧有效 {{ row.active.signed_amount }} 暂计；新提议 {{ row.proposal.signed_amount }} 待双方确认。</p><p v-if="row.receipt_status" class="mt-2">收款回执 {{ label(row.receipt_status) }}</p><p class="mt-2 text-muted-foreground">{{ nextStep(row) }}</p></td><td data-label="处理" class="p-3"><Button type="button" variant="outline" size="sm" :disabled="busy || loading" :aria-label="`查看往来凭证 ${row.document_no}`" @click="open(row, true)">{{ recordButton(row) }}</Button></td></tr><tr v-if="!workspace.records.items.length"><td colspan="4" class="p-8 text-center text-muted-foreground">当前筛选没有往来凭证。</td></tr></tbody></table></div><nav class="flex justify-end gap-3 border-t p-3 text-xs" aria-label="应付凭证分页"><span>共 {{ workspace.records.total }} 笔 · 第 {{ Math.floor(offset / limit) + 1 }} 页</span><Button type="button" variant="outline" size="sm" :disabled="busy || loading || !offset" @click="page(-1)">上一页</Button><Button type="button" variant="outline" size="sm" :disabled="busy || loading || offset + limit >= workspace.records.total" @click="page(1)">下一页</Button></nav></div></section>
      <section v-if="view === 'ALLOCATIONS'" class="space-y-3 rounded-xl border bg-card p-4 text-xs"><h3 class="font-semibold">完整核销历史</h3><p class="text-muted-foreground">解除仅撤销分配，原付款及真实资金事实保留；新版本不会自动继承旧分配。</p><div v-for="row in workspace.allocations" :key="row.id" class="space-y-1 rounded-lg bg-muted/40 p-3"><b>{{ row.source_kind === 'PAYMENT' ? '付款核销' : '贷方抵扣' }} · {{ row.amount }} {{ workspace.currency }} · {{ label(row.status) }}</b><p :title="`${row.source_id} → ${row.target_id}`">来源 {{ row.source_document_no || '历史原凭证' }} → {{ kindLabels[row.target_kind] }} {{ row.target_document_no || '历史目标凭证' }}<span v-if="row.target_period"> · {{ row.target_period }}</span><span v-if="row.target_version != null"> · 版本 {{ row.target_version }}</span></p><p>{{ row.actor_name }} · {{ formatBusinessDateTime(row.created_at) }} · {{ row.reason }}</p><p v-if="row.released_at">解除 {{ row.released_by }} · {{ formatBusinessDateTime(row.released_at) }}</p></div><p v-if="!workspace.allocations.length" class="p-4 text-muted-foreground">尚无核销分配记录。</p></section>
      <article v-if="selected" class="space-y-3 rounded-xl border bg-card p-4 text-xs" aria-label="往来凭证详情"><div class="flex flex-wrap items-center justify-between gap-3"><h3 class="font-semibold">{{ kindLabels[selected.kind] }} · {{ selected.document_no }}</h3><Button type="button" variant="ghost" size="sm" :disabled="busy" @click="selected = null; resetEditor()">收起凭证</Button></div><p>{{ selected.date }} · {{ signedDirection(selected) }} · {{ money(selected.amount) }} {{ selected.currency }} · {{ label(selected.status) }}</p><p v-if="selected.bank_reference">资金凭证 {{ selected.bank_reference }}</p><p v-if="selected.parent_payment_id" :title="selected.parent_payment_id">原付款 {{ selected.parent_payment_document_no || workspace.allocation_sources.find(row => row.record_id === selected!.parent_payment_id)?.document_no || '查看原付款关联凭证' }}；该退回不属于物料退货现金。</p><p v-if="selected.receipt_review">供应商收款反馈：{{ label(selected.receipt_review.decision) }} · {{ selected.receipt_review.reason }}</p><div v-for="(version, i) in [selected.active, selected.proposal].filter(Boolean)" :key="version!.event_id" class="rounded-lg bg-muted/40 p-3"><b>{{ i === 0 && selected.active ? '当前有效金额' : '待确认提议' }} · {{ version!.signed_amount }} {{ selected.currency }} · 版本 {{ version!.version }}</b><p class="mt-2">{{ label(version!.status) }} · {{ version!.document_no }} · {{ version!.reason }}</p><p v-if="version!.supplier_review" class="mt-2">供应商 {{ label(version!.supplier_review.decision) }} · {{ version!.supplier_review.reason }}</p></div><p v-if="detailStale" class="text-amber-800">依据或账户版本变化；请刷新往来账并重新读取此凭证，再办理当前可用动作。旧有效金额暂计，不自动重绑核销。</p><p v-else-if="selected.needs_reconfirmation" class="text-amber-800">切账前依据已变化，旧确认金额暂计；请提出期初新版本并完成双方核实，期间禁止新增核销，真实资金仍可登记。</p><div v-if="selected.void_request" class="space-y-2 rounded-lg border border-amber-200 bg-amber-50 p-3"><b>当前错误记录更正申请</b><p>更正凭证 {{ selected.void_request.correction_reference || '未记录' }} · {{ selected.void_request.reason }}</p><p v-if="selected.void_request.supplier_review">供应商 {{ label(selected.void_request.supplier_review.decision) }} · {{ selected.void_request.supplier_review.reason }}</p><p>原资金事实在双方更正完成前继续计账，不执行真实退款。</p></div><details v-if="selected.versions?.length" class="rounded-lg border p-3"><summary class="cursor-pointer font-semibold">历次金额版本（{{ selected.versions.length }}）</summary><p v-for="version in selected.versions" :key="version.event_id" class="mt-3 border-t pt-2 tabular-nums">版本 {{ version.version }} · {{ label(version.status) }} · {{ version.date }} · {{ version.document_no }} · {{ version.signed_amount }} {{ selected.currency }} · {{ version.reason }}<span v-if="version.confirmed_by"> · 内部确认 {{ version.confirmed_by }} {{ version.confirmed_at }}</span></p></details><div class="flex flex-wrap gap-2"><Button v-for="value in detailActions" :key="value" type="button" size="sm" variant="outline" :disabled="busy || loading || !!pending || detailStale" @click="begin(value, selected)">{{ actionLabels[value] }}</Button><Button type="button" size="sm" variant="ghost" :disabled="busy || loading" @click="open(selected)">重新读取此凭证</Button></div><details class="rounded-lg border p-3"><summary class="cursor-pointer font-semibold">全部历史（{{ selected.history.length }}）</summary><p v-for="entry in selected.history" :key="entry.id" class="mt-3 whitespace-pre-wrap break-words border-t pt-2">{{ formatBusinessDateTime(entry.created_at) }} · {{ entry.actor_name }} · {{ actionLabels[entry.action as PayableActionName] || entry.action }} · {{ entry.reason }}</p></details></article>
      <form v-if="action" class="space-y-3 rounded-xl border border-teal-200 bg-card p-4 text-xs" aria-label="应付处理表单" @submit.prevent="submit"><div class="flex justify-between gap-3"><h3 class="font-semibold">{{ actionLabels[action] }}</h3><Button type="button" variant="ghost" size="sm" :disabled="busy" @click="resetEditor">取消本次填写</Button></div><p v-if="editorStale" role="alert" class="text-amber-800">账户依据已更新，当前表单不能提交。请取消本次填写、核对新证据后重新办理。</p>
        <fieldset :disabled="busy || !!pending || editorStale" class="space-y-3">
        <div v-if="amountAction" class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3"><label>{{ action === 'PROPOSE_OPENING' ? '固定切账月首' : action === 'RECORD_PAYMENT' ? '实际付款日期' : action === 'DECLARE_PAYMENT_RETURN' ? '实际退回日期' : '费用日期' }}<input v-model="form.date" type="date" :max="today()" :disabled="busy || action === 'PROPOSE_OPENING' && !!workspace.opening?.active" required aria-label="应付业务日期" class="mt-1 block h-10 w-full rounded-lg border border-input bg-card px-3"></label><label>原始凭证号<input v-model="form.document_no" :disabled="busy" required maxlength="128" aria-label="应付凭证号" class="mt-1 block h-10 w-full rounded-lg border border-input bg-card px-3"></label><label>原账金额 {{ workspace.currency }}<input v-model="form.amount" :disabled="busy" required inputmode="decimal" aria-label="应付原金额" placeholder="最多两位小数" class="mt-1 block h-10 w-full rounded-lg border border-input bg-card px-3"></label></div>
        <label v-if="action === 'PROPOSE_OPENING' || feeAction" class="block">金额方向<select v-model="form.direction" :disabled="busy" aria-label="应付金额方向" class="mt-1 h-10 w-full rounded-lg border border-input bg-card px-3"><template v-if="action === 'PROPOSE_OPENING'"><option value="PAYABLE">期初应付供应商</option><option value="CREDIT">期初预付 / 贷方余额</option></template><template v-else><option value="ADD_PAYABLE">增加应付</option><option value="DEDUCT_PAYABLE">减少应付 / 贷方抵扣</option></template></select></label>
        <div v-if="feeAction" class="grid gap-3 sm:grid-cols-2"><label>费用类别<select v-model="form.category" :disabled="busy" aria-label="独立费用类别" class="mt-1 block h-10 w-full rounded-lg border border-input bg-card px-3"><option value="FREIGHT">运费</option><option value="DISCOUNT">折扣</option><option value="TAX">税费</option><option value="ROUNDING">尾差</option><option value="OTHER">其他</option></select></label><label>相关货款月结（可不填）<select v-model="form.related_settlement_id" :disabled="busy" aria-label="费用关联月结" class="mt-1 block h-10 w-full rounded-lg border border-input bg-card px-3"><option value="">独立凭证，不关联月结</option><option v-for="row in relatedBills" :key="row.id" :value="row.record_id">{{ row.period }} · {{ row.document_no }} · 版本 {{ row.version }}</option></select></label></div>
        <label v-if="action === 'PROPOSE_OPENING'" class="flex items-start gap-2 rounded-lg bg-amber-50 p-3"><input v-model="form.acknowledge_unknown_sources" :disabled="busy" type="checkbox" aria-label="确认历史未明来源依据"><span>如有无法归日的旧来源，我已凭外部对账资料核实本次未结余额。不会猜日期或把历史采购总额当期初；切账前证据变化须重新双方核实。</span></label>
        <label v-if="action === 'DECLARE_PAYMENT_RETURN'" class="block">原付款<select v-model="form.parent_payment_id" :disabled="busy" required aria-label="预付款退回原付款" class="mt-1 h-10 w-full rounded-lg border border-input bg-card px-3"><option value="">请选择可实际退回的原付款</option><option v-for="row in returnParents" :key="row.id" :value="row.record_id">{{ row.document_no }} · 可退回 {{ row.returnable_amount }} {{ row.currency }}</option></select><p class="mt-1 text-muted-foreground">按原付款未分配额度核对，未确认申报也占用退回额度；不自动替原付款补收款回执。</p></label>
        <label v-if="action === 'RECORD_PAYMENT' || action === 'DECLARE_PAYMENT_RETURN'" class="block">真实资金凭证 / 银行流水<input v-model="form.bank_reference" :disabled="busy" required aria-label="往来资金凭证" maxlength="128" class="mt-1 h-10 w-full rounded-lg border border-input bg-card px-3"></label>
        <label v-if="reviewAction" class="block">核对结果<select v-model="form.decision" :disabled="busy" aria-label="往来核对结果" class="mt-1 h-10 w-full rounded-lg border border-input bg-card px-3"><option value="CONFIRMED">确认本次明确记录</option><option value="DISPUTED">提出异议</option></select></label>
        <label v-if="action === 'CONFIRM_PAYMENT_RETURN'" class="block">实际入款核实凭证<input v-model="form.confirmation_reference" :disabled="busy" required aria-label="预付款退回核实凭证" maxlength="128" class="mt-1 h-10 w-full rounded-lg border border-input bg-card px-3"></label>
        <label v-if="['REQUEST_VOID', 'CONFIRM_VOID'].includes(action)" class="block">错误登记更正凭证<input v-model="form.correction_reference" :disabled="busy" required aria-label="错误资金更正凭证" maxlength="128" class="mt-1 h-10 w-full rounded-lg border border-input bg-card px-3"></label><p v-if="correctionAction" class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-amber-900">仅更正错误账务记录，不执行银行转账或真实退款。原资金事实在双方更正完成前继续计账；实际退回预付款请另录“预付款实际退回”。</p><p v-if="action === 'VOID_FEE'" class="text-amber-800">费用作废提出零值替代版本；旧有效费用继续计账，直到双方确认新版本。</p>
        <section v-if="action === 'ALLOCATE'" class="space-y-3"><label class="block">付款或贷方来源<select v-model="sourceId" :disabled="busy" required aria-label="核销来源" class="mt-1 h-10 w-full rounded-lg border border-input bg-card px-3" @change="checkedTargets = []; amounts = {}"><option value="">请选择允许核销的来源</option><option v-for="row in workspace.allocation_sources.filter(item => item.can_allocate)" :key="row.id" :value="row.id">{{ row.source_kind === 'PAYMENT' ? '已回执付款' : '贷方抵扣' }} · {{ row.document_no }} · 可用 {{ row.available_amount }} {{ row.currency }}</option></select></label><p v-if="source" class="text-muted-foreground">已分配 {{ source.allocated_amount }} · 退回预留 {{ source.reserved_return_amount }} · 当前可用 {{ source.available_amount }} {{ source.currency }}</p><label v-for="row in targets" :key="row.id" class="grid items-center gap-2 rounded-lg bg-muted/40 p-3 sm:grid-cols-[auto_1fr_10rem]"><input v-model="checkedTargets" type="checkbox" :value="row.id" :disabled="busy || !source" :aria-label="`选择核销目标 ${row.document_no}`"><span>{{ kindLabels[row.kind] }} {{ row.document_no }} · {{ row.period || row.date }} · 版本 {{ row.version }} · 未核销 {{ row.remaining_amount }} {{ row.currency }}</span><input v-model="amounts[row.id]" :disabled="busy || !checkedTargets.includes(row.id)" inputmode="decimal" :aria-label="`本次核销 ${row.document_no}`" class="h-10 rounded-lg border border-input bg-card px-3" placeholder="本次显式核销额"></label><p class="font-semibold tabular-nums" aria-label="本次核销金额合计">本次选中合计 {{ allocationTotal }} {{ workspace.currency }}（精确分值预览，生效额度以服务器校验为准）</p><p v-if="!targets.length" class="text-muted-foreground">无当前可分配的正应付目标；重核或过期来源须先核实。</p></section>
        <section v-if="action === 'DEALLOCATE'" class="space-y-2"><label v-for="row in workspace.allocations.filter(item => item.status === 'ACTIVE')" :key="row.id" class="flex items-start gap-2 rounded-lg bg-muted/40 p-3"><input v-model="releaseIds" :disabled="busy" type="checkbox" :value="row.id" :aria-label="`解除核销 ${row.id}`"><span :title="`${row.source_id} → ${row.target_id}`">{{ row.amount }} {{ workspace.currency }} · {{ row.source_document_no || '历史原凭证' }} → {{ row.target_document_no || '历史目标凭证' }}<span v-if="row.target_period"> · {{ row.target_period }}</span><span v-if="row.target_version != null"> · 版本 {{ row.target_version }}</span> · {{ row.reason }}</span></label><p class="text-muted-foreground">只解除选择的原分配，付款与已确认应付金额不消失。</p></section>
        </fieldset>
        <label class="block">凭证依据 / 原因<textarea v-model="form.reason" :disabled="busy || !!pending" required minlength="4" maxlength="2000" rows="2" aria-label="应付处理原因" class="mt-1 w-full rounded-lg border border-input bg-card px-3 py-2" /></label><p class="text-muted-foreground">依据按提交时的账户版本核对。保存成功后只刷新已完成阶段；结果不明保留原请求，先核对历史。</p><Button :disabled="busy || loading || !!pending || editorStale">{{ busy ? '正在保存…' : `保存${actionLabels[action]}` }}</Button>
      </form>
    </template>
  </section>
</template>
