<script setup lang="ts">
import CartonFilterBar from '@/components/CartonFilterBar.vue'
import '@/features/carton-procurement/layout.css'
import CartonSourceLinks from './CartonSourceLinks.vue'
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useMoneyPreference } from '@/features/carton-procurement/moneyPreference'
import { getApiErrorMessage } from '@/lib/http'
import { supplierSettlementApi as api, type StatementLine, type SettlementDocument, type SupplierWorkspace } from '@/api/cartonSupplierSettlement'
import { exportSettlementLines, settlementDateLabel, settlementSourceLabel } from '@/features/carton-procurement/settlementExport'
import CartonSettlementFilters from '@/components/CartonSettlementFilters.vue'
import CartonPriceReviews from '@/components/CartonPriceReviews.vue'
import CartonReturnDateEditor from '@/components/CartonReturnDateEditor.vue'
import { createRandomUuid } from '@/lib/randomUuid'
import { matchesSettlementLine, settlementStage, type SettlementLineFilter, type SettlementBusinessKind } from '@/features/carton-procurement/queryFilters'

const props = defineProps<{ factoryId: string; search?: string }>()
const emit = defineEmits<{ 'update:search': [value: string]; returns: []; prices: [receiptLineId?: string] }>()
const auth = useAuthStore()
const { preference: moneyPreference, reference: moneyReference } = useMoneyPreference(() => {
  const user = auth.currentUser
  return user?.id ? { userId: user.id, employmentEpoch: user.identity?.employment_epoch ?? 1 } : null
})
const today = () => new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
const period = ref(today().slice(0, 7)), currency = ref('CNY'), localQuery = ref('')
const query = computed({
  get: () => props.search ?? localQuery.value,
  set: (value: string) => { if (props.search === undefined) localQuery.value = value; else emit('update:search', value) },
})
const lineFilter = ref<SettlementLineFilter>('ALL'), documentFilter = ref('ALL'), businessKind = ref<SettlementBusinessKind>('')
const filteredDocuments = computed(() => workspace.value?.documents.filter(doc => documentFilter.value === 'ALL' || settlementStage(doc) === documentFilter.value || doc.id === document.value?.id) ?? [])
const workspace = ref<SupplierWorkspace | null>(null), document = ref<SettlementDocument | null>(null)
const busy = ref(false), dirty = ref(false), error = ref(''), message = ref(''), reopenReason = ref('')
const invoice = reactive({ origin: 'COLLABORATION' as 'MANUAL' | 'COLLABORATION', statement_no: '', tax_basis: 'INCLUSIVE' as 'INCLUSIVE' | 'EXCLUSIVE', same_price_basis: false, lines: [] as StatementLine[] })
const dateFix = reactive({ receipt_id: '', revision: 0, document_no: '', acceptance_date: '', reason: '' })
const returnDateFix = reactive({ movement_id: '', document_no: '', expected_posting_date: '', return_date: '', reason: '' })
const returnCorrectionId = ref('')
const viewerKey = computed(() => JSON.stringify([auth.currentUser?.id, auth.authorizationVersion, auth.authzMode, auth.currentUser?.identity?.effective_context_key, auth.currentUser?.identity?.employment_epoch]))
const expandedLines = ref(new Set<string>())
const showPriceReviews = ref(false)
const showComparison = ref(false)
const verifiedResult = computed(() => !!document.value && !dirty.value && !document.value.stale && !busy.value)
const sourceProblems = computed(() => sources.value.filter(row => row.issues.length).length + (workspace.value?.issues.length || 0) + unsettled.value.length)
const resultLabel = computed(() => cleanConfirmed.value ? '本月对账已完成' : document.value?.status === 'SUPERSEDED' ? '历史版本' : document.value?.stale ? '来源已更新，待重算' : dirty.value ? '修改待保存' : !document.value ? '待首次核对' : problemCount.value || sourceProblems.value ? '有待处理事项' : '核对无差异')
const nextStep = computed(() => cleanConfirmed.value ? '可查看确认记录与明细' : document.value?.status === 'SUPERSEDED' ? '切换当前版本继续处理' : document.value?.stale ? '更新来源并重新核对' : dirty.value || !document.value ? '本厂保存并核对差异' : problemCount.value || sourceProblems.value ? '本厂处理差异或缺项' : !supplierConfirmed.value ? '等待供应商确认当前版本' : !monthEnded.value ? '月份结束后，本厂确认' : '本厂确认对账完成')
const priceUpdates = computed(() => sources.value.filter(row => row.supplier_price_update))
const canReviewPrices = computed(() => ['read', 'receipt_write', 'inventory_write'].every(permission => ['carton', 'pmc-warehouse'].some(dept => auth.can(`carton_procurement:${permission}`, props.factoryId, dept))))
let generation = 0
const canManage = computed(() => ['carton', 'pmc-warehouse'].some(dept => auth.can('carton_procurement:closing_manage', props.factoryId, dept)))
const canConfirm = computed(() => canManage.value && ['carton', 'pmc-warehouse'].some(dept => auth.can('carton_procurement:order_adjust', props.factoryId, dept)))
const editable = computed(() => canManage.value && !busy.value && (!document.value || document.value.status === 'DRAFT'))
const sources = computed(() => document.value?.sources || (invoice.origin === 'COLLABORATION' ? workspace.value?.collaboration?.sources : undefined) || workspace.value?.sources || [])
const collaborative = computed(() => invoice.origin === 'COLLABORATION')
const supplierReview = computed(() => document.value?.result.supplier_review)
const supplierConfirmed = computed(() => !collaborative.value || (!dirty.value && !document.value?.stale && supplierReview.value?.decision === 'CONFIRMED'))
const unsettled = computed(() => document.value?.result.unsettled_shipments ?? workspace.value?.collaboration?.unsettled_shipments ?? [])
const sourceMap = computed(() => new Map(sources.value.map(row => [row.source_key, row])))
const shown = computed(() => invoice.lines.filter(line => {
  const source = sourceMap.value.get(line.source_key)
  return matchesSettlementLine(line, source, dirty.value ? undefined : document.value?.result.line_results.find(row => row.id === line.id), query.value, lineFilter.value, businessKind.value)
}))
const problemCount = computed(() => Math.max(document.value?.result.issues.length || 0, document.value?.result.line_results.reduce((sum, row) => sum + row.issues.length, 0) || 0))
const cleanConfirmed = computed(() => document.value?.status === 'CONFIRMED' && !document.value.stale)
const monthEnded = computed(() => !!workspace.value && workspace.value.period < today().slice(0, 7))
const lineResult = (id: string) => !dirty.value && !document.value?.stale ? document.value?.result.line_results.find(row => row.id === id) : undefined
const display = (value: string | null | undefined) => value == null ? '待核实' : value
function supplementReason(line: StatementLine) {
  const source = sourceMap.value.get(line.source_key)
  if (!source) return '供应商凭证有，本厂未匹配'
  if (managedReturn(source)) return ''
  if (source.kind === 'RETURN') return '退货需补齐独立贷项依据'
  if (!collaborative.value) return '历史或未接入协同的凭证补录'
  if (!source.supplier_delivery) return '历史收料未关联送货凭证'
  if (source.supplier_delivery.unit_price == null) return '供应商原单价待核实'
  if ([line.quantity, line.unit_price, line.amount].some(value => value == null || value === '')) return '结算数据待补齐'
  return ''
}
const managedReturn = (source?: import('@/api/cartonSupplierSettlement').SupplierSource) => source?.kind === 'RETURN_REFUND' || !!source?.return_agreement
function hasDifference(line: StatementLine) {
  const source = sourceMap.value.get(line.source_key), vendor = source?.supplier_delivery, result = lineResult(line.id)
  if (result) return !!source?.issues.length || !!result.issues.length
  return !!source?.issues.length || !!lineResult(line.id)?.issues.length || !!(vendor && (
    Number(vendor.quantity_difference) !== 0 || (vendor.price_difference != null && Number(vendor.price_difference) !== 0)))
}
const hasPendingPrice = (line: StatementLine) => !!sourceMap.value.get(line.source_key)?.price_review && sourceMap.value.get(line.source_key)?.price_review?.status !== 'CONFIRMED'
const editorVisible = (line: StatementLine) => !managedReturn(sourceMap.value.get(line.source_key)) && !hasPendingPrice(line) && (!line.source_key || expandedLines.value.has(line.id))
function expandLine(line: StatementLine) { expandedLines.value.add(line.id) }
function pricesChanged() {
  if (dirty.value) { message.value = '核价已更新，请先保存或放弃当前账单草稿，再刷新来源。'; return }
  void load()
}
function blank(source_key = '', document_no = ''): StatementLine {
  return { id: createRandomUuid(), source_key, document_no, quantity: null, unit_price: null, amount: null,
    approved_return_unit_price: null, credit_document_no: '', credit_date: null, note: '' }
}
function accept(doc: SettlementDocument) {
  document.value = doc
  expandedLines.value.clear()
  Object.assign(invoice, { origin: 'MANUAL' }, JSON.parse(JSON.stringify(doc.statement)))
  dirty.value = false; reopenReason.value = ''; message.value = ''
}
function resetForm() {
  document.value = null
  expandedLines.value.clear()
  const collab = workspace.value?.collaboration
  Object.assign(invoice, { origin: collab ? 'COLLABORATION' : 'MANUAL', statement_no: collab ? `协同月结-${workspace.value!.period}-${workspace.value!.currency}` : '', tax_basis: 'INCLUSIVE', same_price_basis: false,
    lines: collab ? JSON.parse(JSON.stringify(collab.lines)) : (workspace.value?.sources || []).map(row => blank(row.source_key, row.document_no)) })
  dirty.value = false
}
async function load() {
  const token = ++generation, factory = props.factoryId
  busy.value = true; error.value = ''; message.value = ''; workspace.value = null; document.value = null
  invoice.lines = []; dateFix.receipt_id = ''; returnDateFix.movement_id = ''; returnCorrectionId.value = ''
  try {
    const result = await api.workspace(factory, period.value, currency.value)
    if (token !== generation || factory !== props.factoryId) return
    workspace.value = result
    const current = result.documents[0]
    if (current) accept(current); else resetForm()
    return ''
  } catch (err) {
    if (token === generation && factory === props.factoryId) { error.value = getApiErrorMessage(err); return error.value }
  }
  finally { if (token === generation) busy.value = false }
}
function change() { dirty.value = true; message.value = '' }
function selectDocument(id: string) {
  const doc = workspace.value?.documents.find(row => row.id === id)
  if (doc) accept(doc)
}
function refreshSources() {
  if (!workspace.value || document.value?.status !== 'DRAFT' || dirty.value || busy.value) return
  const current = collaborative.value && workspace.value.collaboration ? { ...workspace.value, ...workspace.value.collaboration } : workspace.value
  const existing = new Map(invoice.lines.filter(row => row.source_key).map(row => [row.source_key, row]))
  const suggested = new Map(workspace.value.collaboration?.lines.map(row => [row.source_key, row]) ?? [])
  const previousSources = new Map(document.value.sources.map(row => [row.source_key, row]))
  function refreshedLine(row: import('@/api/cartonSupplierSettlement').SupplierSource) {
    const prior = existing.get(row.source_key), baseline = previousSources.get(row.source_key), next = suggested.get(row.source_key)
    // Only replace an unchanged automatic amount; retain deliberate manual adjustments for review.
    if (collaborative.value && row.supplier_price_update && prior && baseline && next &&
      (['quantity', 'unit_price', 'amount'] as const).every(key => prior[key] != null && baseline[key] != null && Number(prior[key]) === Number(baseline[key]))) {
      return { ...next, id: prior.id, note: prior.note }
    }
    return (collaborative.value && managedReturn(row) ? next : undefined) || prior || (collaborative.value ? next : undefined) || blank(row.source_key, row.document_no)
  }
  // Keep unmatched vendor rows visible: a removed receipt must not silently erase a bill line.
  const keys = new Set(current.sources.map(row => row.source_key))
  invoice.lines = [
    ...current.sources.map(refreshedLine),
    ...invoice.lines.filter(row => !keys.has(row.source_key)).map(row => ({ ...row, source_key: '' })),
  ]
  document.value = { ...document.value, sources: current.sources, source_fingerprint: current.source_fingerprint, stale: false,
    result: { ...document.value.result, ...(collaborative.value ? { unsettled_shipments: workspace.value.collaboration?.unsettled_shipments } : {}) } }
  change()
}
function useCollaboration() {
  if (!workspace.value?.collaboration || dirty.value || busy.value || !editable.value) return
  const doc = document.value
  const metadata = { statement_no: invoice.statement_no, tax_basis: invoice.tax_basis, same_price_basis: invoice.same_price_basis }
  const prior = invoice.lines.map(row => ({ ...row }))
  resetForm()
  Object.assign(invoice, metadata)
  const suggestedKeys = new Set(invoice.lines.map(row => row.source_key))
  const byKey = new Map(prior.filter(row => row.source_key).map(row => [row.source_key, row]))
  invoice.lines = [
    ...invoice.lines.map(row => { const source = workspace.value!.collaboration!.sources.find(source => source.source_key === row.source_key); return source?.supplier_delivery || managedReturn(source) ? row : byKey.get(row.source_key) || row }),
    ...prior.filter(row => !suggestedKeys.has(row.source_key)).map(row => ({ ...row, source_key: '' })),
  ]
  if (doc) document.value = { ...doc, sources: workspace.value.collaboration.sources, source_fingerprint: workspace.value.collaboration.source_fingerprint, stale: false,
    result: { ...doc.result, unsettled_shipments: workspace.value.collaboration.unsettled_shipments } }
  change()
}
async function act(action: 'save' | 'confirm' | 'reopen') {
  if (busy.value || !canManage.value || !workspace.value) return
  if (action !== 'save' && !canConfirm.value) return
  const factory = props.factoryId, token = generation, doc = document.value
  busy.value = true; error.value = ''; message.value = ''
  try {
    let result: SettlementDocument
    if (action === 'save') {
      const lines = invoice.lines.map(row => ({ ...row, quantity: row.quantity === '' ? null : row.quantity,
        unit_price: row.unit_price === '' ? null : row.unit_price, amount: row.amount === '' ? null : row.amount,
        approved_return_unit_price: row.approved_return_unit_price === '' ? null : row.approved_return_unit_price, credit_date: row.credit_date || null }))
      result = await api.save({ factory_id: factory, supplier_id: workspace.value.supplier_id, period: workspace.value.period,
        currency: workspace.value.currency, source_fingerprint: doc?.source_fingerprint || (collaborative.value ? workspace.value.collaboration?.source_fingerprint : undefined) || workspace.value.source_fingerprint,
        ...(doc ? { id: doc.id, expected_revision: doc.revision } : {}), ...invoice, lines })
    } else if (!doc) return
    else if (action === 'confirm') result = await api.confirm(doc.id, factory, doc.revision)
    else result = await api.reopen(doc.id, factory, doc.revision, reopenReason.value)
    if (token !== generation || factory !== props.factoryId) return
    accept(result)
    workspace.value.documents = [result, ...workspace.value.documents.filter(row => row.id !== result.id).map(row => action === 'reopen' && row.id === doc?.id ? { ...row, status: 'SUPERSEDED' as const } : row)]
    message.value = action === 'save' ? '草稿已保存，差异已重新计算。' : action === 'confirm' ? '供应商对账已确认；此状态不表示已付款。' : '已建立重核版本，请重新核对来源与账单。'
  } catch (err) { if (token === generation) error.value = getApiErrorMessage(err) }
  finally { if (token === generation) busy.value = false }
}
async function saveDate() {
  if (busy.value || dirty.value || !canManage.value || !dateFix.receipt_id) return
  const token = generation, factory = props.factoryId
  busy.value = true; error.value = ''
  try {
    await api.acceptance(dateFix.receipt_id, factory, dateFix.revision, dateFix.acceptance_date, dateFix.reason)
    if (token !== generation || factory !== props.factoryId) return
    const refreshError = await load()
    if (factory !== props.factoryId || token + 1 !== generation) return
    message.value = '验收日期已保存，对账月份按实际验收日期重新核对。'
    if (refreshError) error.value = `验收日期已保存，但对账刷新失败：${refreshError}。请刷新查看，勿重复保存。`
  } catch (err) { if (token === generation && factory === props.factoryId) error.value = `验收日期未保存：${getApiErrorMessage(err)}` }
  finally { if (token === generation) busy.value = false }
}
async function saveReturnDate() {
  if (busy.value || dirty.value || !canConfirm.value || !returnDateFix.movement_id) return
  const token = generation, factory = props.factoryId
  busy.value = true; error.value = ''
  try {
    await api.returnDate(returnDateFix.movement_id, factory, returnDateFix.expected_posting_date, returnDateFix.return_date, returnDateFix.reason)
    if (token !== generation || factory !== props.factoryId) return
    const refreshError = await load()
    if (factory !== props.factoryId || token + 1 !== generation) return
    message.value = '实际退货日期已核实；请在所属月份重新核对草稿，库存记账时间保持原值。'
    if (refreshError) error.value = `日期已保存，但月结刷新失败：${refreshError}。请刷新查看，勿重复保存。`
  } catch (err) { if (token === generation && factory === props.factoryId) error.value = `实际退货日期未保存：${getApiErrorMessage(err)}` }
  finally { if (token === generation) busy.value = false }
}
async function returnDateCorrected() {
  const factory = props.factoryId, viewer = viewerKey.value
  returnCorrectionId.value = ''
  const refreshError = await load()
  if (factory !== props.factoryId || viewer !== viewerKey.value) return
  message.value = '实际退货日期已更正，原库存记账与真实到账记录保留。请在受影响月份重新核对，并取得双方对最新日期版本的确认。'
  if (refreshError) error.value = `日期已更正，但月结刷新失败：${refreshError}。请刷新查看，勿重复保存。`
}
function leave() { return !dirty.value || window.confirm('供应商账单有未保存的内容，确定离开吗？') }
async function focusEvidence(targetPeriod: string | undefined, targetCurrency: string, id?: string) {
  if (!leave()) return false
  if (targetPeriod) period.value = targetPeriod
  currency.value = targetCurrency
  await load()
  if (id) selectDocument(id)
  return !!workspace.value
}
defineExpose({ refreshPrices: pricesChanged, focusEvidence })
onBeforeRouteLeave(leave)
onBeforeRouteUpdate((to, from) => to.fullPath === from.fullPath || leave())
const beforeUnload = (event: BeforeUnloadEvent) => { if (dirty.value) { event.preventDefault(); event.returnValue = '' } }
window.addEventListener('beforeunload', beforeUnload)
watch([() => props.factoryId, viewerKey], () => { dirty.value = false; showPriceReviews.value = false; localQuery.value = ''; lineFilter.value = 'ALL'; documentFilter.value = 'ALL'; businessKind.value = '';  void load() }, { immediate: true })
onBeforeUnmount(() => { generation++; window.removeEventListener('beforeunload', beforeUnload) })
</script>

<template>
  <section class="space-y-4" aria-label="双方月结对账">
    <CartonReturnDateEditor v-if="returnCorrectionId" :factory-id="factoryId" :movement-id="returnCorrectionId" :viewer-key="viewerKey" :disabled="dirty" @saved="returnDateCorrected" @close="returnCorrectionId = ''" />
    <header class="rounded-xl border border-teal-200 bg-white p-4">
      <h2 class="font-bold text-slate-900">双方月结对账</h2>
      <p class="mt-2 text-sm text-slate-600">按验收入库月份汇总货款，处理差异后由双方确认。</p>
      <details class="mt-3 text-xs text-slate-500"><summary class="cursor-pointer text-teal-700">月结怎么算</summary><div class="mt-2 space-y-1 leading-6">
        <p>本月进货 − 退货贷项 + 已确认现金退款 = 本月货款净额。车间领料、调仓不扣供应商货款。</p>
        <p>手工入库后补来的原送货单，只关联同一批货；首次供应商原价自动用于货款核对，价格变化通知仓库。</p>
        <p>按实际验收日期分月，分批到货分别计算。已确认月份须先重开；付款与独立费用在“应付与付款”查看。</p>
        <p v-if="!collaborative && workspace">当前为历史手工核对版本，原账单与确认记录保留。</p>
      </div></details>
      <button v-if="!collaborative && workspace?.collaboration && editable" type="button" :disabled="busy || dirty" class="mt-2 rounded-lg border border-teal-300 px-3 py-2 text-xs text-teal-700" @click="useCollaboration">接入双方对账</button>
      <CartonFilterBar label="本厂对账期间筛选" class="mt-3 rounded-lg"><label>对账月份<input v-model="period" :disabled="busy || dirty" aria-label="供应商对账月份" type="month" class="mt-1 block h-9 rounded-lg border px-3"></label><label>原账币种<input v-model="currency" :disabled="busy || dirty" aria-label="供应商对账币种" list="carton-settlement-currencies" maxlength="8" class="mt-1 block h-9 w-24 rounded-lg border px-3"><datalist id="carton-settlement-currencies"><option value="CNY">人民币</option><option value="HKD">港币</option><option value="USD">美元</option></datalist></label><template #actions><button type="button" :disabled="busy || dirty" class="h-9 rounded-lg border px-4 disabled:opacity-40" @click="load">查询 / 刷新</button><button v-if="dirty" type="button" :disabled="busy" class="h-9 rounded-lg border px-3" @click="leave() && load()">放弃未保存内容</button></template><template #footer><span class="pb-2 text-slate-500">{{ workspace?.supplier_name || '读取供应商中' }} · {{ workspace?.period || period }} · {{ workspace?.currency || currency }}</span></template></CartonFilterBar>
      <p v-if="workspace" class="mt-3 text-xs text-slate-500">单价与金额按原账 {{ workspace.currency }} 核对，单价对应每行的计量单位。金额显示设置在基础资料顶部。</p>
      <p v-if="workspace?.currency === 'CNY' && moneyPreference.currency === 'HKD'" class="mt-2 text-xs text-teal-700" aria-label="月结港币参考汇率">港币参考：1 CNY = {{ moneyPreference.cnyToHkd }} HKD；人民币月结与导出保持原账。</p>
    </header>
    <p v-if="error" role="alert" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
    <p v-if="message" role="status" class="text-sm text-teal-700">{{ message }}</p>
    <form v-if="returnDateFix.movement_id" class="flex flex-wrap items-end gap-3 rounded-lg border border-amber-200 bg-amber-50 p-4 text-xs" @submit.prevent="saveReturnDate"><b class="w-full">核实实际退货日期 · {{ returnDateFix.document_no }}</b><p class="w-full text-slate-600">旧归属月份 {{ returnDateFix.expected_posting_date.slice(0, 7) }} 与实际退货月份均须开放。只补证一次；库存记账时间和成本保持原值。</p><label>实际退货交接日期<input v-model="returnDateFix.return_date" type="date" required :max="today()" aria-label="核实实际退货日期" class="mt-1 block rounded border p-2"></label><label class="flex-1">核实依据<input v-model="returnDateFix.reason" required minlength="4" maxlength="2000" aria-label="实际退货日期核实依据" placeholder="原退货交接单、经手人及核实情况" class="mt-1 block w-full min-w-52 rounded border p-2"></label><button :disabled="busy || dirty || returnDateFix.reason.trim().length < 4 || !returnDateFix.return_date" class="rounded bg-teal-700 px-3 py-2 text-white disabled:opacity-40">保存实际退货日期</button><button type="button" :disabled="busy" @click="returnDateFix.movement_id = ''">取消</button></form>
    <p v-if="busy && !workspace" class="p-8 text-center text-slate-500">正在核对本厂收料与退货记录…</p>
    <template v-if="workspace">
      <section class="grid gap-3 rounded-xl border border-teal-200 bg-white p-4 sm:grid-cols-3" aria-label="本月核对概览">
        <div class="min-w-0"><p class="text-xs text-slate-500">本月货款净额 · {{ workspace.currency }}</p><p class="mt-2 text-2xl font-bold tabular-nums text-slate-900">{{ verifiedResult ? display(document?.result.net_amount) : '待核对' }}</p><p class="mt-1 text-xs text-slate-500">按有效验收与退货依据计算</p></div>
        <div class="min-w-0"><p class="text-xs text-slate-500">核对状态</p><p class="mt-2 text-lg font-bold" :class="verifiedResult && !problemCount && !sourceProblems ? 'text-teal-700' : 'text-amber-800'">{{ resultLabel }}</p><button v-if="problemCount || sourceProblems" type="button" class="mt-1 text-xs text-teal-700 underline underline-offset-4" @click="lineFilter = 'DIFFERENCE'">查看待处理明细</button><p v-else class="mt-1 text-xs text-slate-500">{{ verifiedResult ? '数量、价格、金额已核对' : '保存后显示核对结果' }}</p></div>
        <div class="min-w-0 rounded-lg bg-teal-50 p-3"><p class="text-xs text-teal-700">下一步</p><p class="mt-2 font-semibold text-slate-900">{{ nextStep }}</p><p class="mt-1 text-xs text-slate-500">{{ collaborative ? '本厂核对 → 供应商确认 → 本厂完成' : '本厂核对 → 本厂完成' }}</p></div>
      </section>
      <details v-if="priceUpdates.length" class="rounded-xl border border-teal-200 bg-teal-50 p-4 text-xs" aria-label="供应商价格更新记录"><summary class="cursor-pointer font-semibold text-teal-900">已采用供应商原价 · {{ priceUpdates.length }} 项更新（仓库可查看）</summary><div v-for="source in priceUpdates" :key="source.source_key" class="mt-3 flex flex-wrap gap-x-4 gap-y-1 border-t border-teal-200 pt-3"><b>{{ source.document_no }} · {{ source.packaging_type }}</b><span>手工价 {{ display(source.supplier_price_update!.manual_unit_price) }} → 供应商价 {{ source.supplier_price_update!.supplier_unit_price }} {{ source.currency }}/{{ source.unit }}</span><span v-if="source.supplier_price_update!.amount_difference != null">货款差额 {{ source.supplier_price_update!.amount_difference }} {{ source.currency }}</span><span v-else>已补齐原缺失价格</span><span class="text-slate-500">沿用原入库数量</span></div></details>
      <div v-if="canReviewPrices" class="rounded-xl border bg-white p-3 text-xs">
        <button type="button" class="rounded-lg border px-3 py-2 text-teal-700" :aria-expanded="showPriceReviews" @click="showPriceReviews = !showPriceReviews">{{ showPriceReviews ? '收起异常价格核对' : '异常价格核对' }}</button>
        <p class="mt-2 text-slate-500">后补原单已采用的供应商价无需重复确认；缺价及后续价格更正在这里处理。</p>
        <CartonPriceReviews v-if="showPriceReviews" :factory-id="factoryId" class="mt-3" @changed="pricesChanged" @full-correction="emit('prices', $event)" />
      </div>
      <details v-if="collaborative" class="rounded-xl border bg-white p-3 text-xs"><summary class="cursor-pointer text-teal-700">查看双方确认进度</summary>
      <ol class="grid gap-3 sm:grid-cols-3" aria-label="双方月结流程">
        <li class="rounded-lg border bg-white p-3 text-xs"><b class="text-slate-900">1 · 本厂核对并保存</b><p class="mt-2 text-slate-600">{{ document?.status === 'SUPERSEDED' ? '历史核对版本' : dirty ? '修改待保存' : document?.stale ? '来源已变化，待更新核对' : document ? '当前版本已保存' : '待保存月结草稿' }}</p></li>
        <li class="rounded-lg border bg-white p-3 text-xs"><b class="text-slate-900">2 · 供应商核对确认</b><p class="mt-2" :class="supplierConfirmed ? 'text-teal-700' : 'text-slate-600'">{{ document?.status === 'SUPERSEDED' ? '历史供应商核对记录' : dirty || document?.stale ? '更新后须重新确认' : supplierReview?.decision === 'CONFIRMED' ? '供应商已确认当前版本' : supplierReview?.decision === 'DISPUTED' ? '供应商提出异议，待本厂处理' : !document || problemCount ? '等待本厂保存并处理缺项或差异' : '待供应商在供应商协同 → 月结对账确认当前版本' }}</p></li>
        <li class="rounded-lg border bg-white p-3 text-xs"><b class="text-slate-900">3 · 本厂完成月结</b><p class="mt-2" :class="cleanConfirmed ? 'text-teal-700' : 'text-slate-600'">{{ cleanConfirmed ? '双方对账已完成' : document?.status === 'SUPERSEDED' ? '历史版本，仅供查阅' : !monthEnded ? '月份结束后完成确认' : supplierConfirmed ? '待本厂主管确认' : '等待供应商确认' }}</p></li>
      </ol>
      </details>
      <article v-if="workspace.undated_receipts.length" class="rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs">
        <b>历史收料未记录实际验收日期，请核实后归入正确月份</b>
        <div v-for="row in workspace.undated_receipts" :key="row.receipt_id" class="mt-2 flex flex-wrap items-center justify-between gap-2"><span>{{ row.document_no }} · 原确认时间 {{ row.confirmed_at || '未记录' }}</span><button v-if="canManage" type="button" :disabled="busy || dirty" class="rounded-lg border bg-white px-3 py-2" @click="Object.assign(dateFix, { ...row, acceptance_date: '', reason: '' })">核实验收日期 {{ row.document_no }}</button></div>
        <form v-if="dateFix.receipt_id" class="mt-3 flex flex-wrap gap-2 rounded-lg bg-white p-3" @submit.prevent="saveDate">
          <label>实际验收日期<input v-model="dateFix.acceptance_date" required type="date" :max="today()" aria-label="补录实际验收日期" class="ml-2 rounded border p-2"></label>
          <input v-model="dateFix.reason" required minlength="4" maxlength="2000" aria-label="验收日期核实依据" placeholder="核实依据，例如签收单及经手人" class="min-w-52 flex-1 rounded border p-2">
          <button :disabled="busy || dirty" class="rounded bg-teal-700 px-3 py-2 text-white">保存核实日期</button><button type="button" @click="dateFix.receipt_id = ''">取消</button>
        </form>
      </article>
      <div v-if="workspace.issues.length" class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900"><p v-for="(issue, index) in workspace.issues" :key="index">{{ issue }}</p></div>
      <div v-if="collaborative && document" class="rounded-lg border bg-white p-3 text-xs" aria-label="双方月结确认状态">
        <p v-if="document.status === 'SUPERSEDED'">历史确认记录：{{ supplierReview?.decision === 'CONFIRMED' ? `供应商已确认 · ${supplierReview.at}` : supplierReview?.decision === 'DISPUTED' ? `供应商异议：${supplierReview.reason}` : '未记录供应商确认' }}</p>
        <p v-else>{{ dirty ? '明细有未保存修改，保存后需重新取得供应商确认' : document.stale ? '来源已变化，须更新并保存后重新取得供应商确认' : supplierReview?.decision === 'CONFIRMED' ? `供应商已确认 · ${supplierReview.at}` : supplierReview?.decision === 'DISPUTED' ? `供应商提出异议：${supplierReview.reason}` : '待供应商在供应商协同 → 月结对账确认当前版本' }}</p>
        <p class="mt-1 text-slate-500">本厂：{{ document.status === 'SUPERSEDED' ? '历史版本，仅供查阅' : cleanConfirmed ? '已确认' : '待确认' }} · 确认对账不代表付款</p>
      </div>
      <details v-if="collaborative && unsettled.length" class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs">
        <summary class="cursor-pointer font-semibold">送货明细未计入本期结算：{{ unsettled.length }} 条</summary>
        <p class="mt-2 text-slate-600">以下仅供核对，不计入本期应结；按实际验收日期归月，待验收记录继续到收料入口处理。</p>
        <p v-for="(row, index) in unsettled" :key="index" class="mt-2">{{ row.document_no }} · {{ row.item_no }} {{ row.specification }} · 送货 {{ row.delivery_date }} · {{ row.quantity }} {{ row.unit }} · 原价 {{ display(row.original_unit_price) }} · {{ row.reason }}<span v-if="row.difference_reason"> · {{ row.difference_reason }}</span></p>
      </details>
      <article class="overflow-hidden rounded-xl border border-slate-200 bg-white">
        <div class="flex flex-wrap items-center justify-between gap-2 border-b p-3 text-xs"><span>配卡专项按独立纸品明细核对，月份仍按实际验收入库日期。</span><button type="button" :disabled="busy || dirty || !shown.length" class="rounded-lg border border-teal-200 px-3 py-2 text-teal-800 disabled:opacity-40" @click="exportSettlementLines(shown, sourceMap, workspace.period, workspace.currency, lineFilter)">导出当前筛选明细 CSV</button></div>
        <CartonSettlementFilters v-model:query="query" v-model:lines="lineFilter" v-model:stage="documentFilter" v-model:business-kind="businessKind" :hide-search="search !== undefined" :dirty="dirty" :shown="shown.length" :total="invoice.lines.length" />
        <div class="flex flex-wrap items-center gap-3 border-b bg-slate-50 p-4 text-xs">
          <select :value="document?.id || ''" :disabled="dirty || busy" aria-label="供应商对账版本" class="h-9 max-w-full rounded-lg border bg-white px-2" @change="selectDocument(($event.target as HTMLSelectElement).value)"><option v-if="!document" value="">新草稿</option><option v-for="doc in filteredDocuments" :key="doc.id" :value="doc.id">版本 {{ doc.version }} · {{ doc.status === 'CONFIRMED' ? '已确认' : doc.status === 'SUPERSEDED' ? '历史版本' : '草稿' }} · {{ doc.statement.statement_no || '未填账单号' }}</option></select>
          <span :class="cleanConfirmed ? 'text-teal-700' : 'text-amber-700'">{{ document?.stale ? '来源已变化，需要重新核对' : cleanConfirmed ? '对账完成（不代表付款）' : document?.status === 'SUPERSEDED' ? '历史版本 · 只读' : dirty ? '修改尚未保存，差异待重算' : document ? `待核对 · ${problemCount} 项差异或缺项` : '已生成拟结算明细，请核对后保存' }}</span>
          <button v-if="document?.status === 'DRAFT' && document.stale && canManage" type="button" :disabled="busy || dirty" class="rounded-lg border border-amber-300 px-3 py-2 text-amber-800" @click="refreshSources">更新来源并重新核对</button>
        </div>
        <form @submit.prevent="act('save')" @input="change">
          <div class="flex flex-wrap items-center gap-4 border-b p-4 text-xs">
            <label>月结编号 / 凭证号<input v-model="invoice.statement_no" :disabled="!editable" maxlength="128" aria-label="供应商账单号" class="ml-2 h-9 rounded-lg border px-2"></label>
            <label>账单价格口径<select v-model="invoice.tax_basis" :disabled="!editable" aria-label="账单价格口径" class="ml-2 h-9 rounded-lg border px-2" @change="change"><option value="INCLUSIVE">含税价</option><option value="EXCLUSIVE">未税价</option></select></label>
            <label class="inline-flex items-center gap-2"><input v-model="invoice.same_price_basis" :disabled="!editable" type="checkbox" aria-label="确认同币种同价格口径" @change="change">已核实本厂单价与供应商账单使用同一币种及含税／未税口径</label>
          </div>
          <div class="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3 text-xs"><b>月结明细</b><button type="button" class="rounded-lg border px-3 py-2 text-teal-700" :aria-expanded="showComparison" @click="showComparison = !showComparison">{{ showComparison ? '收起原单与验收对照' : '展开原单与验收对照' }}</button></div>
          <div class="overflow-x-auto carton-table-wrap"><table class="w-full text-left text-xs carton-table-fit" :class="showComparison ? 'min-w-[1100px]' : 'min-w-[760px]'" aria-label="双方逐笔对账明细">
            <thead class="bg-slate-50 text-slate-500"><tr><th class="p-3">来源单据 / 归属依据</th><th class="p-3">货号 / 纸品规格</th><th v-if="showComparison" class="p-3 text-right">供应商原送货</th><th v-if="showComparison" class="p-3 text-right">本厂有效验收</th><th class="w-44 p-3">拟结算数量 / 单价 / 金额</th><th class="p-3">核对结果 / 依据</th><th class="p-3 text-right">处理</th></tr></thead>
            <tbody v-for="line in shown" :key="line.id" class="border-t border-slate-100">
              <tr class="align-top">
                <td data-label="来源单据 / 归属依据" class="max-w-52 p-3"><CartonSourceLinks :factory-id="factoryId" :sources="sourceMap.get(line.source_key)?.special_request_id ? [{ id: sourceMap.get(line.source_key)!.special_request_id!, request_no: sourceMap.get(line.source_key)!.special_request_no || '原需求单', kind: sourceMap.get(line.source_key)!.special_request_kind || 'SAMPLE' }] : []" :delivery-id="sourceMap.get(line.source_key)?.delivery_id" /><span class="mb-1 inline-block rounded bg-slate-100 px-2 py-1">{{ settlementSourceLabel(sourceMap.get(line.source_key)) }}</span><div v-if="line.source_key" class="break-all font-mono">{{ sourceMap.get(line.source_key)?.document_no }}</div><input v-else v-model="line.document_no" :disabled="!editable" :aria-label="`未匹配送货单 ${line.id}`" placeholder="账单上的送货单号" class="w-full rounded border p-2"><p class="mt-1 text-slate-500">{{ settlementDateLabel(sourceMap.get(line.source_key)) }} {{ sourceMap.get(line.source_key)?.acceptance_date || '待核实' }}</p><p v-if="sourceMap.get(line.source_key)?.posting_date" class="mt-1 text-slate-500">库存记账 {{ sourceMap.get(line.source_key)?.posting_date }}</p><button v-if="canConfirm && sourceMap.get(line.source_key)?.kind === 'RETURN' && sourceMap.get(line.source_key)?.date_basis === 'RETURN_POSTING'" type="button" :disabled="busy || dirty || cleanConfirmed" class="mt-2 rounded border px-2 py-1 text-teal-800 disabled:opacity-40" :aria-label="`核实退货日期 ${line.source_key}`" @click="Object.assign(returnDateFix, { movement_id: line.source_key.slice(7), document_no: sourceMap.get(line.source_key)?.document_no, expected_posting_date: sourceMap.get(line.source_key)?.acceptance_date, return_date: '', reason: '' })">核实实际退货日期</button><button v-if="canConfirm && sourceMap.get(line.source_key)?.kind === 'RETURN' && sourceMap.get(line.source_key)?.date_basis === 'RETURN_ACTUAL'" type="button" :disabled="busy || dirty" class="mt-2 rounded border px-2 py-1 text-teal-800 disabled:opacity-40" :aria-label="`更正退货日期 ${line.source_key}`" @click="returnCorrectionId = line.source_key.slice(7)">更正已录实际退货日期</button><p class="mt-1">{{ sourceMap.get(line.source_key)?.customer_name }} {{ sourceMap.get(line.source_key)?.contract_no }}</p></td>
                <td data-label="货号 / 纸品规格" class="max-w-48 break-words p-3"><b>{{ sourceMap.get(line.source_key)?.item_no || '未匹配' }}</b><p class="mt-1 text-slate-500">{{ sourceMap.get(line.source_key)?.packaging_type }} · {{ sourceMap.get(line.source_key)?.paper_quality }} · {{ sourceMap.get(line.source_key)?.specification }}</p></td>
                <td v-if="showComparison" data-label="供应商原送货" class="max-w-48 p-3 text-right tabular-nums"><template v-if="collaborative && sourceMap.get(line.source_key)?.supplier_delivery"><b>{{ sourceMap.get(line.source_key)?.supplier_delivery?.quantity }} {{ sourceMap.get(line.source_key)?.unit }}</b><p class="mt-1 break-all">原价 {{ display(sourceMap.get(line.source_key)?.supplier_delivery?.original_unit_price ?? sourceMap.get(line.source_key)?.supplier_delivery?.unit_price) }}</p><p class="mt-1">金额 {{ display(sourceMap.get(line.source_key)?.supplier_delivery?.amount) }}</p><p class="mt-2 text-slate-500">送货 {{ sourceMap.get(line.source_key)?.supplier_delivery?.delivery_date }}</p><p v-if="sourceMap.get(line.source_key)?.supplier_delivery?.original_quantity != null && Number(sourceMap.get(line.source_key)?.supplier_delivery?.original_quantity) !== Number(sourceMap.get(line.source_key)?.supplier_delivery?.quantity)" class="mt-1 text-teal-700">原单共 {{ sourceMap.get(line.source_key)?.supplier_delivery?.original_quantity }} {{ sourceMap.get(line.source_key)?.unit }}；此行数量和金额为本次验收分摊</p><p v-if="sourceMap.get(line.source_key)?.supplier_delivery?.price_warning" class="mt-2 text-amber-800">{{ sourceMap.get(line.source_key)?.supplier_delivery?.price_warning }}</p></template><span v-else class="text-amber-800">{{ sourceMap.get(line.source_key)?.kind === 'RETURN_REFUND' ? '已核实到账，按现金凭证加回应结' : sourceMap.get(line.source_key)?.kind === 'RETURN' ? '按独立退货贷项核对' : '按供应商凭证补录' }}</span></td>
                <td v-if="showComparison" data-label="本厂有效验收" class="whitespace-nowrap p-3 text-right tabular-nums"><template v-if="sourceMap.get(line.source_key)?.kind === 'RETURN_REFUND'"><b>资金凭证 · 现金到账</b><p class="mt-2 font-bold text-teal-700">已核实 {{ display(sourceMap.get(line.source_key)?.amount) }} {{ workspace.currency }}</p><p class="mt-1 text-slate-500">加回应结，不计实物收料</p></template><template v-else><b>{{ sourceMap.get(line.source_key)?.quantity || '—' }} {{ sourceMap.get(line.source_key)?.unit }}</b><p v-if="sourceMap.get(line.source_key)?.kind === 'RETURN'" class="mt-2 text-slate-500">按下方退货依据结算</p><template v-else><p class="mt-1">单价 {{ display(sourceMap.get(line.source_key)?.unit_price) }}</p><p v-if="moneyReference(sourceMap.get(line.source_key)?.unit_price, sourceMap.get(line.source_key)?.currency || workspace.currency, 6)" class="mt-1 text-[10px] text-teal-700">{{ moneyReference(sourceMap.get(line.source_key)?.unit_price, sourceMap.get(line.source_key)?.currency || workspace.currency, 6) }}</p><p class="mt-1 font-bold text-teal-700">金额 {{ display(sourceMap.get(line.source_key)?.amount) }}</p><p v-if="moneyReference(sourceMap.get(line.source_key)?.amount, sourceMap.get(line.source_key)?.currency || workspace.currency, 2)" class="mt-1 text-[10px] text-teal-700">{{ moneyReference(sourceMap.get(line.source_key)?.amount, sourceMap.get(line.source_key)?.currency || workspace.currency, 2) }}</p></template></template></td>
                <td data-label="拟结算数量 / 单价 / 金额" class="p-3"><div v-if="editorVisible(line)" class="space-y-2" :aria-label="`凭证补录与调整 ${line.id}`"><p class="text-amber-800">{{ supplementReason(line) || '调整结算须填写核对依据' }}</p><label class="flex items-center gap-2">数量<input v-model="line.quantity" :disabled="!editable" type="number" min="0" step="0.0001" :aria-label="`账单数量 ${line.id}`" class="h-8 min-w-0 flex-1 rounded border px-2 text-right"></label><label class="flex items-center gap-2">单价<input v-model="line.unit_price" :disabled="!editable" type="number" min="0" step="0.000001" :aria-label="`账单单价 ${line.id}`" class="h-8 min-w-0 flex-1 rounded border px-2 text-right"></label><label class="flex items-center gap-2">金额<input v-model="line.amount" :disabled="!editable" type="number" min="0" step="0.01" :aria-label="`账单金额 ${line.id}`" class="h-8 min-w-0 flex-1 rounded border px-2 text-right"></label><p v-if="moneyReference(line.unit_price, workspace.currency, 6)" class="text-[10px] text-teal-700">单价 {{ moneyReference(line.unit_price, workspace.currency, 6) }}</p><p v-if="moneyReference(line.amount, workspace.currency)" class="text-[10px] text-teal-700">金额 {{ moneyReference(line.amount, workspace.currency) }}</p></div><div v-else class="text-right tabular-nums" :aria-label="`拟结算明细 ${line.id}`"><b>{{ display(line.quantity) }} {{ sourceMap.get(line.source_key)?.unit }}</b><p class="mt-1">单价 {{ display(line.unit_price) }}</p><p v-if="moneyReference(line.unit_price, workspace.currency, 6)" class="mt-1 text-[10px] text-teal-700">{{ moneyReference(line.unit_price, workspace.currency, 6) }}</p><p class="mt-1 font-bold text-teal-700">金额 {{ display(line.amount) }}</p><p v-if="moneyReference(line.amount, workspace.currency, 2)" class="mt-1 text-[10px] text-teal-700">{{ moneyReference(line.amount, workspace.currency, 2) }}</p><p class="mt-2 text-slate-500">当前拟结算</p></div></td>
                <td data-label="核对结果 / 依据" class="max-w-64 p-3"><template v-if="lineResult(line.id)"><p v-if="!hasDifference(line)" class="inline-flex rounded-full bg-teal-50 px-2 py-1 font-semibold text-teal-700">无差异</p><p v-else class="leading-5">数量差 {{ display(lineResult(line.id)?.quantity_difference) }} · 单价差 {{ display(lineResult(line.id)?.price_difference) }} · 金额差 {{ display(lineResult(line.id)?.amount_difference) }}</p><p v-for="(issue, i) in lineResult(line.id)?.issues" :key="i" class="mt-1 text-amber-700">{{ issue }}</p></template><p v-else class="text-slate-400">保存草稿后计算差异</p><p v-if="sourceMap.get(line.source_key)?.supplier_delivery?.difference_reason" class="mt-2 text-amber-800">收料：{{ sourceMap.get(line.source_key)?.supplier_delivery?.difference_reason }}</p><input v-if="editorVisible(line)" v-model="line.note" :disabled="!editable" :aria-label="`对账依据 ${line.id}`" placeholder="核对备注 / 依据" class="mt-2 w-full rounded border p-2"><p v-else-if="line.note" class="mt-2">{{ line.note }}</p></td>
                <td data-label="处理" class="p-3 text-right"><button v-if="managedReturn(sourceMap.get(line.source_key))" type="button" class="rounded-lg border px-3 py-2 text-teal-700" @click="emit('returns')">查看退货回执</button><button v-else-if="hasPendingPrice(line) && canReviewPrices" type="button" class="rounded-lg border px-3 py-2 text-teal-700" @click="showPriceReviews = true">处理价格核对</button><span v-else-if="hasPendingPrice(line)" class="text-amber-800">待收料人员与供应商核价</span><button v-else-if="editable && !editorVisible(line)" type="button" :aria-label="`处理结算明细 ${line.id}`" class="whitespace-nowrap rounded-lg border px-3 py-2 text-teal-700" @click="expandLine(line)">{{ supplementReason(line) ? '展开凭证补录' : hasDifference(line) ? '处理差异' : '调整结算' }}</button><span v-else-if="editable && line.source_key" class="text-amber-800">{{ supplementReason(line) ? '待补录核对' : '调整中' }}</span><button v-if="!line.source_key && editable" type="button" class="whitespace-nowrap text-red-700" @click="invoice.lines = invoice.lines.filter(row => row.id !== line.id); change()">移除录错行</button></td>
              </tr>
              <tr v-if="sourceMap.get(line.source_key)?.kind === 'RETURN'"><td :colspan="showComparison ? 7 : 5" class="bg-amber-50/50 px-3 pb-3"><div v-if="sourceMap.get(line.source_key)?.return_agreement" class="flex flex-wrap items-center gap-3 py-2"><b>双方退货核定依据</b><span>贷项 {{ sourceMap.get(line.source_key)?.return_agreement?.credit_document_no || '待核实' }} · {{ sourceMap.get(line.source_key)?.return_agreement?.credit_date || '日期待核实' }} · 单价 {{ display(sourceMap.get(line.source_key)?.unit_price) }}</span><span class="text-slate-500">沿退货回执核实，月结中不重复改价。</span></div><div v-else class="flex flex-wrap items-center gap-3"><b>本厂认可的退货依据</b><label>退货单价<input v-model="line.approved_return_unit_price" :disabled="!editable" type="number" min="0" step="0.000001" :aria-label="`认可退货单价 ${line.id}`" class="ml-2 w-28 rounded border p-2"></label><input v-model="line.credit_document_no" :disabled="!editable" :aria-label="`退货贷项单号 ${line.id}`" placeholder="供应商认可的退货 / 贷项单号" class="min-w-52 rounded border p-2"><label>贷项日期<input v-model="line.credit_date" :disabled="!editable" type="date" :aria-label="`贷项日期 ${line.id}`" class="ml-2 rounded border p-2"></label><span class="text-slate-500">依据核实后补齐拟结算价格；库存平均成本不作为退货结算价。</span></div></td></tr>
            </tbody>
            <tbody v-if="!shown.length"><tr><td :colspan="showComparison ? 7 : 5" class="p-10 text-center text-slate-400">{{ query ? '没有匹配明细' : '本期暂无已确定验收日期的供应商进退货记录' }}</td></tr></tbody>
          </table></div>
          <div v-if="editable" class="border-t p-3"><button type="button" class="rounded-lg border px-3 py-2 text-xs text-teal-700" @click="invoice.lines.push(blank()); change()">补录未匹配的供应商凭证</button></div>
          <div v-if="document && !dirty" class="border-t bg-slate-50 p-4 text-xs"><div class="flex flex-wrap gap-6 font-bold"><span>进货金额 {{ display(document.result.inbound_amount) }}<small v-if="moneyReference(document.result.inbound_amount, workspace.currency)" class="mt-1 block font-normal text-teal-700">{{ moneyReference(document.result.inbound_amount, workspace.currency) }}</small></span><span>退货金额 {{ display(document.result.return_amount) }}<small v-if="moneyReference(document.result.return_amount, workspace.currency)" class="mt-1 block font-normal text-teal-700">{{ moneyReference(document.result.return_amount, workspace.currency) }}</small></span><span v-if="document.result.cash_refund_amount !== undefined">本月已确认现金退款 {{ display(document.result.cash_refund_amount) }}</span><span v-if="document.result.return_deduction_amount !== undefined">退货净抵扣 {{ display(document.result.return_deduction_amount) }}</span><span>本厂应结 {{ display(document.result.net_amount) }}<small v-if="moneyReference(document.result.net_amount, workspace.currency)" class="mt-1 block font-normal text-teal-700">{{ moneyReference(document.result.net_amount, workspace.currency) }}</small></span><span>拟结算应结 {{ display(document.result.statement_amount) }}<small v-if="moneyReference(document.result.statement_amount, workspace.currency)" class="mt-1 block font-normal text-teal-700">{{ moneyReference(document.result.statement_amount, workspace.currency) }}</small></span><span>{{ workspace.currency }}</span></div><p v-if="document.result.cash_refund_amount !== undefined" class="mt-3 font-normal text-slate-500">供货 − 退货贷项 + 本月已确认现金退款 = 本期净应结；月结抵扣仅分配贷项，不再另减。未核实现金申报不计到账。</p><p v-for="(issue, i) in document.result.issues" :key="i" class="mt-2 text-amber-700">{{ issue }}</p></div>
          <footer class="flex flex-wrap items-center justify-between gap-3 border-t p-4 text-xs"><div class="space-y-1 text-slate-500"><p v-if="!monthEnded">本月尚未结束，可先保存核对草稿，月份结束后再确认。</p><p>确认后，补录该月原送货凭证或更正进退货须先填写原因建立重核版本；进货仍按实际验收月份计入应结。</p><p>运费、折扣、税差等独立费用请到“应付与付款”登记并取得双方确认；货款原有数量、价格或金额差异仍须核实，不能借费用放行。</p><p v-if="collaborative && !supplierConfirmed">供应商尚未确认当前版本。</p></div><div class="flex gap-2"><button v-if="(!document || document.status === 'DRAFT') && canManage" :disabled="busy" class="rounded-lg border border-teal-300 px-4 py-2 text-teal-700">保存并核对差异</button><button v-if="document?.status === 'DRAFT' && canConfirm" type="button" :disabled="busy || dirty || !monthEnded || document.stale || problemCount > 0 || !invoice.same_price_basis || !supplierConfirmed" class="rounded-lg bg-teal-700 px-4 py-2 text-white disabled:opacity-40" @click="act('confirm')">确认对账完成</button></div></footer>
        </form>
      </article>
      <form v-if="document?.status === 'CONFIRMED' && canConfirm && !dirty" class="flex flex-wrap items-center gap-3 rounded-xl border bg-white p-4 text-xs" @submit.prevent="act('reopen')"><span>补录旧月原送货或更正来源前，请重开受影响的已确认月份。原确认记录保留，补证后须保存新草稿并由供应商和内部重新确认，金额不会自动调整。</span><input v-model="reopenReason" required minlength="4" maxlength="2000" aria-label="供应商对账重核原因" placeholder="填写重核原因" class="h-9 min-w-52 flex-1 rounded border px-3"><button :disabled="busy" class="h-9 rounded-lg border px-4">建立重核版本</button></form>
    </template>
  </section>
</template>
