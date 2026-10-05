<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import { supplierSettlementApi as api, type StatementLine, type SettlementDocument, type SupplierWorkspace } from '@/api/cartonSupplierSettlement'

const props = defineProps<{ factoryId: string }>()
const auth = useAuthStore()
const today = () => new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
const period = ref(today().slice(0, 7)), currency = ref('CNY'), query = ref('')
const workspace = ref<SupplierWorkspace | null>(null), document = ref<SettlementDocument | null>(null)
const busy = ref(false), dirty = ref(false), error = ref(''), message = ref(''), reopenReason = ref('')
const invoice = reactive({ origin: 'COLLABORATION' as 'MANUAL' | 'COLLABORATION', statement_no: '', tax_basis: 'INCLUSIVE' as 'INCLUSIVE' | 'EXCLUSIVE', same_price_basis: false, lines: [] as StatementLine[] })
const dateFix = reactive({ receipt_id: '', revision: 0, document_no: '', acceptance_date: '', reason: '' })
const expandedLines = ref(new Set<string>())
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
  return [line.document_no, source?.customer_name, source?.contract_no, source?.item_no, source?.packaging_type, source?.specification].join(' ').toLowerCase().includes(query.value.trim().toLowerCase())
}))
const problemCount = computed(() => Math.max(document.value?.result.issues.length || 0, document.value?.result.line_results.reduce((sum, row) => sum + row.issues.length, 0) || 0))
const cleanConfirmed = computed(() => document.value?.status === 'CONFIRMED' && !document.value.stale)
const monthEnded = computed(() => !!workspace.value && workspace.value.period < today().slice(0, 7))
const lineResult = (id: string) => !dirty.value ? document.value?.result.line_results.find(row => row.id === id) : undefined
const display = (value: string | null | undefined) => value == null ? '待核实' : value
function supplementReason(line: StatementLine) {
  const source = sourceMap.value.get(line.source_key)
  if (!source) return '供应商凭证有，本厂未匹配'
  if (source.kind === 'RETURN') return '退货需补齐独立贷项依据'
  if (!collaborative.value) return '历史或未接入协同的凭证补录'
  if (!source.supplier_delivery) return '历史收料未关联送货凭证'
  if (source.supplier_delivery.unit_price == null) return '供应商原单价待核实'
  if ([line.quantity, line.unit_price, line.amount].some(value => value == null || value === '')) return '结算数据待补齐'
  return ''
}
function hasDifference(line: StatementLine) {
  const source = sourceMap.value.get(line.source_key), vendor = source?.supplier_delivery, result = lineResult(line.id)
  if (result) return !!source?.issues.length || !!result.issues.length
  return !!source?.issues.length || !!lineResult(line.id)?.issues.length || !!(vendor && (
    Number(vendor.quantity_difference) !== 0 || (vendor.price_difference != null && Number(vendor.price_difference) !== 0)))
}
const editorVisible = (line: StatementLine) => !!supplementReason(line) || expandedLines.value.has(line.id)
function expandLine(line: StatementLine) { expandedLines.value.add(line.id) }
function blank(source_key = '', document_no = ''): StatementLine {
  return { id: crypto.randomUUID(), source_key, document_no, quantity: null, unit_price: null, amount: null,
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
  invoice.lines = []; dateFix.receipt_id = ''
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
  // Keep unmatched vendor rows visible: a removed receipt must not silently erase a bill line.
  const keys = new Set(current.sources.map(row => row.source_key))
  invoice.lines = [
    ...current.sources.map(row => existing.get(row.source_key) || (collaborative.value ? suggested.get(row.source_key) : undefined) || blank(row.source_key, row.document_no)),
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
    ...invoice.lines.map(row => workspace.value!.collaboration!.sources.find(source => source.source_key === row.source_key)?.supplier_delivery ? row : byKey.get(row.source_key) || row),
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
function leave() { return !dirty.value || window.confirm('供应商账单有未保存的内容，确定离开吗？') }
onBeforeRouteLeave(leave)
onBeforeRouteUpdate((to, from) => to.fullPath === from.fullPath || leave())
const beforeUnload = (event: BeforeUnloadEvent) => { if (dirty.value) { event.preventDefault(); event.returnValue = '' } }
window.addEventListener('beforeunload', beforeUnload)
watch(() => props.factoryId, () => { dirty.value = false; void load() }, { immediate: true })
onBeforeUnmount(() => { generation++; window.removeEventListener('beforeunload', beforeUnload) })
</script>

<template>
  <section class="space-y-4" aria-label="双方月结对账">
    <header class="rounded-xl border border-teal-200 bg-white p-4">
      <h2 class="font-bold text-slate-900">双方月结对账</h2>
      <p class="mt-1 text-xs leading-6 text-slate-600">按实际验收入库日期分月：9 月下单、10 月验收计入 10 月；分批到货分别计算。只核对供应商进货和退货，车间领料、调仓不扣供应商金额。</p>
      <p v-if="collaborative" class="mt-2 text-xs leading-6 text-teal-800">供应商原送货、本厂有效验收与拟结算在同一份明细中核对。已关联数据自动带入，缺价、历史未关联和退货按凭证补录；调整结算数量或价格须填写依据。</p>
      <p v-else-if="workspace" class="mt-2 text-xs text-amber-800">{{ workspace.collaboration ? '当前为历史手工版本，原账单及确认记录保留。草稿可接入双方对账，保存后交由供应商确认。' : '当前供应商尚未接入协同，按供应商凭证补录并沿用本厂核对流程。' }}</p>
      <button v-if="!collaborative && workspace?.collaboration && editable" type="button" :disabled="busy || dirty" class="mt-2 rounded-lg border border-teal-300 px-3 py-2 text-xs text-teal-700" @click="useCollaboration">接入双方对账</button>
      <div class="mt-3 flex flex-wrap items-end gap-3 text-xs">
        <label>对账月份<input v-model="period" :disabled="busy || dirty" aria-label="供应商对账月份" type="month" class="mt-1 block h-9 rounded-lg border px-3"></label>
        <label>币种<input v-model="currency" :disabled="busy || dirty" aria-label="供应商对账币种" maxlength="8" class="mt-1 block h-9 w-24 rounded-lg border px-3"></label>
        <button type="button" :disabled="busy || dirty" class="h-9 rounded-lg border px-4 disabled:opacity-40" @click="load">查询 / 刷新</button>
        <button v-if="dirty" type="button" :disabled="busy" class="h-9 rounded-lg border px-3" @click="leave() && load()">放弃未保存内容</button>
        <span class="pb-2 text-slate-500">{{ workspace?.supplier_name || '读取供应商中' }} · {{ workspace?.period || period }} · {{ workspace?.currency || currency }}</span>
      </div>
    </header>
    <p v-if="error" role="alert" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
    <p v-if="message" role="status" class="text-sm text-teal-700">{{ message }}</p>
    <p v-if="busy && !workspace" class="p-8 text-center text-slate-500">正在核对本厂收料与退货记录…</p>
    <template v-if="workspace">
      <ol v-if="collaborative" class="grid gap-3 sm:grid-cols-3" aria-label="双方月结流程">
        <li class="rounded-lg border bg-white p-3 text-xs"><b class="text-slate-900">1 · 本厂核对并保存</b><p class="mt-2 text-slate-600">{{ document?.status === 'SUPERSEDED' ? '历史核对版本' : dirty ? '修改待保存' : document?.stale ? '来源已变化，待更新核对' : document ? '当前版本已保存' : '待保存月结草稿' }}</p></li>
        <li class="rounded-lg border bg-white p-3 text-xs"><b class="text-slate-900">2 · 供应商核对确认</b><p class="mt-2" :class="supplierConfirmed ? 'text-teal-700' : 'text-slate-600'">{{ document?.status === 'SUPERSEDED' ? '历史供应商核对记录' : dirty || document?.stale ? '更新后须重新确认' : supplierReview?.decision === 'CONFIRMED' ? '供应商已确认当前版本' : supplierReview?.decision === 'DISPUTED' ? '供应商提出异议，待本厂处理' : !document || problemCount ? '等待本厂保存并处理缺项或差异' : '待供应商在供应商协同 → 月结对账确认当前版本' }}</p></li>
        <li class="rounded-lg border bg-white p-3 text-xs"><b class="text-slate-900">3 · 本厂完成月结</b><p class="mt-2" :class="cleanConfirmed ? 'text-teal-700' : 'text-slate-600'">{{ cleanConfirmed ? '双方对账已完成' : document?.status === 'SUPERSEDED' ? '历史版本，仅供查阅' : !monthEnded ? '月份结束后完成确认' : supplierConfirmed ? '待本厂主管确认' : '等待供应商确认' }}</p></li>
      </ol>
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
        <p v-for="row in unsettled" :key="row.line_id || row.shipment_id" class="mt-2">{{ row.document_no }} · {{ row.item_no }} {{ row.specification }} · 送货 {{ row.delivery_date }} · {{ row.quantity }} {{ row.unit }} · 原价 {{ display(row.original_unit_price) }} · {{ row.reason }}<span v-if="row.difference_reason"> · {{ row.difference_reason }}</span></p>
      </details>
      <article class="overflow-hidden rounded-xl border border-slate-200 bg-white">
        <div class="flex flex-wrap items-center gap-3 border-b bg-slate-50 p-4 text-xs">
          <select :value="document?.id || ''" :disabled="dirty || busy" aria-label="供应商对账版本" class="h-9 max-w-full rounded-lg border bg-white px-2" @change="selectDocument(($event.target as HTMLSelectElement).value)"><option v-if="!document" value="">新草稿</option><option v-for="doc in workspace.documents" :key="doc.id" :value="doc.id">版本 {{ doc.version }} · {{ doc.status === 'CONFIRMED' ? '已确认' : doc.status === 'SUPERSEDED' ? '历史版本' : '草稿' }} · {{ doc.statement.statement_no || '未填账单号' }}</option></select>
          <span :class="cleanConfirmed ? 'text-teal-700' : 'text-amber-700'">{{ document?.stale ? '来源已变化，需要重新核对' : cleanConfirmed ? '对账完成（不代表付款）' : document?.status === 'SUPERSEDED' ? '历史版本 · 只读' : dirty ? '修改尚未保存，差异待重算' : document ? `待核对 · ${problemCount} 项差异或缺项` : '已生成拟结算明细，请核对后保存' }}</span>
          <input v-model="query" aria-label="查找供应商对账明细" placeholder="送货单 / 合同 / 货号 / 规格" class="ml-auto h-9 min-w-52 rounded-lg border px-3">
          <button v-if="document?.status === 'DRAFT' && document.stale && canManage" type="button" :disabled="busy || dirty" class="rounded-lg border border-amber-300 px-3 py-2 text-amber-800" @click="refreshSources">更新来源并重新核对</button>
        </div>
        <form @submit.prevent="act('save')" @input="change">
          <div class="flex flex-wrap items-center gap-4 border-b p-4 text-xs">
            <label>月结编号 / 凭证号<input v-model="invoice.statement_no" :disabled="!editable" maxlength="128" aria-label="供应商账单号" class="ml-2 h-9 rounded-lg border px-2"></label>
            <label>账单价格口径<select v-model="invoice.tax_basis" :disabled="!editable" aria-label="账单价格口径" class="ml-2 h-9 rounded-lg border px-2" @change="change"><option value="INCLUSIVE">含税价</option><option value="EXCLUSIVE">未税价</option></select></label>
            <label class="inline-flex items-center gap-2"><input v-model="invoice.same_price_basis" :disabled="!editable" type="checkbox" aria-label="确认同币种同价格口径" @change="change">已核实本厂单价与供应商账单使用同一币种及含税／未税口径</label>
          </div>
          <div class="overflow-x-auto"><table class="w-full min-w-[1100px] text-left text-xs" aria-label="双方逐笔对账明细">
            <thead class="bg-slate-50 text-slate-500"><tr><th class="p-3">来源单据 / 归属依据</th><th class="p-3">货号 / 纸品规格</th><th class="p-3 text-right">供应商原送货</th><th class="p-3 text-right">本厂有效验收</th><th class="w-44 p-3">拟结算数量 / 单价 / 金额</th><th class="p-3">核对结果 / 依据</th><th class="p-3 text-right">处理</th></tr></thead>
            <tbody v-for="line in shown" :key="line.id" class="border-t border-slate-100">
              <tr class="align-top">
                <td class="max-w-52 p-3"><span class="mb-1 inline-block rounded bg-slate-100 px-2 py-1">{{ sourceMap.get(line.source_key)?.kind === 'RETURN' ? '退回供应商' : line.source_key ? '进货' : '账单有，本厂未匹配' }}</span><div v-if="line.source_key" class="break-all font-mono">{{ sourceMap.get(line.source_key)?.document_no }}</div><input v-else v-model="line.document_no" :disabled="!editable" :aria-label="`未匹配送货单 ${line.id}`" placeholder="账单上的送货单号" class="w-full rounded border p-2"><p class="mt-1 text-slate-500">{{ sourceMap.get(line.source_key)?.kind === 'RETURN' ? '退货记账日期' : '验收日期' }} {{ sourceMap.get(line.source_key)?.acceptance_date || '待核实' }}</p><p class="mt-1">{{ sourceMap.get(line.source_key)?.customer_name }} {{ sourceMap.get(line.source_key)?.contract_no }}</p></td>
                <td class="max-w-48 break-words p-3"><b>{{ sourceMap.get(line.source_key)?.item_no || '未匹配' }}</b><p class="mt-1 text-slate-500">{{ sourceMap.get(line.source_key)?.packaging_type }} · {{ sourceMap.get(line.source_key)?.paper_quality }} · {{ sourceMap.get(line.source_key)?.specification }}</p></td>
                <td class="max-w-48 p-3 text-right tabular-nums"><template v-if="collaborative && sourceMap.get(line.source_key)?.supplier_delivery"><b>{{ sourceMap.get(line.source_key)?.supplier_delivery?.quantity }} {{ sourceMap.get(line.source_key)?.unit }}</b><p class="mt-1 break-all">原价 {{ display(sourceMap.get(line.source_key)?.supplier_delivery?.original_unit_price ?? sourceMap.get(line.source_key)?.supplier_delivery?.unit_price) }}</p><p class="mt-1">金额 {{ display(sourceMap.get(line.source_key)?.supplier_delivery?.amount) }}</p><p class="mt-2 text-slate-500">送货 {{ sourceMap.get(line.source_key)?.supplier_delivery?.delivery_date }}</p><p v-if="sourceMap.get(line.source_key)?.supplier_delivery?.price_warning" class="mt-2 text-amber-800">{{ sourceMap.get(line.source_key)?.supplier_delivery?.price_warning }}</p></template><span v-else class="text-amber-800">{{ sourceMap.get(line.source_key)?.kind === 'RETURN' ? '按独立退货贷项核对' : '按供应商凭证补录' }}</span></td>
                <td class="whitespace-nowrap p-3 text-right tabular-nums"><b>{{ sourceMap.get(line.source_key)?.quantity || '—' }} {{ sourceMap.get(line.source_key)?.unit }}</b><p v-if="sourceMap.get(line.source_key)?.kind === 'RETURN'" class="mt-2 text-slate-500">按下方退货依据结算</p><template v-else><p class="mt-1">单价 {{ display(sourceMap.get(line.source_key)?.unit_price) }}</p><p class="mt-1 font-bold text-teal-700">金额 {{ display(sourceMap.get(line.source_key)?.amount) }}</p></template></td>
                <td class="p-3"><div v-if="editorVisible(line)" class="space-y-2" :aria-label="`凭证补录与调整 ${line.id}`"><p class="text-amber-800">{{ supplementReason(line) || '调整结算须填写核对依据' }}</p><label class="flex items-center gap-2">数量<input v-model="line.quantity" :disabled="!editable" type="number" min="0" step="0.0001" :aria-label="`账单数量 ${line.id}`" class="h-8 min-w-0 flex-1 rounded border px-2 text-right"></label><label class="flex items-center gap-2">单价<input v-model="line.unit_price" :disabled="!editable" type="number" min="0" step="0.000001" :aria-label="`账单单价 ${line.id}`" class="h-8 min-w-0 flex-1 rounded border px-2 text-right"></label><label class="flex items-center gap-2">金额<input v-model="line.amount" :disabled="!editable" type="number" min="0" step="0.01" :aria-label="`账单金额 ${line.id}`" class="h-8 min-w-0 flex-1 rounded border px-2 text-right"></label></div><div v-else class="text-right tabular-nums" :aria-label="`拟结算明细 ${line.id}`"><b>{{ display(line.quantity) }} {{ sourceMap.get(line.source_key)?.unit }}</b><p class="mt-1">单价 {{ display(line.unit_price) }}</p><p class="mt-1 font-bold text-teal-700">金额 {{ display(line.amount) }}</p><p class="mt-2 text-slate-500">当前拟结算</p></div></td>
                <td class="max-w-64 p-3"><template v-if="lineResult(line.id)"><p class="leading-5">数量差 {{ display(lineResult(line.id)?.quantity_difference) }} · 单价差 {{ display(lineResult(line.id)?.price_difference) }} · 金额差 {{ display(lineResult(line.id)?.amount_difference) }}</p><p v-for="(issue, i) in lineResult(line.id)?.issues" :key="i" class="mt-1 text-amber-700">{{ issue }}</p></template><p v-else class="text-slate-400">保存草稿后计算差异</p><p v-if="sourceMap.get(line.source_key)?.supplier_delivery?.difference_reason" class="mt-2 text-amber-800">收料：{{ sourceMap.get(line.source_key)?.supplier_delivery?.difference_reason }}</p><input v-if="editorVisible(line)" v-model="line.note" :disabled="!editable" :aria-label="`对账依据 ${line.id}`" placeholder="核对备注 / 依据" class="mt-2 w-full rounded border p-2"><p v-else-if="line.note" class="mt-2">{{ line.note }}</p></td>
                <td class="p-3 text-right"><button v-if="editable && !editorVisible(line)" type="button" :aria-label="`处理结算明细 ${line.id}`" class="whitespace-nowrap rounded-lg border px-3 py-2 text-teal-700" @click="expandLine(line)">{{ hasDifference(line) ? '处理差异' : '调整结算' }}</button><span v-else-if="editable && line.source_key" class="text-amber-800">{{ supplementReason(line) ? '待补录核对' : '调整中' }}</span><button v-if="!line.source_key && editable" type="button" class="whitespace-nowrap text-red-700" @click="invoice.lines = invoice.lines.filter(row => row.id !== line.id); change()">移除录错行</button></td>
              </tr>
              <tr v-if="sourceMap.get(line.source_key)?.kind === 'RETURN'"><td colspan="7" class="bg-amber-50/50 px-3 pb-3"><div class="flex flex-wrap items-center gap-3"><b>本厂认可的退货依据</b><label>退货单价<input v-model="line.approved_return_unit_price" :disabled="!editable" type="number" min="0" step="0.000001" :aria-label="`认可退货单价 ${line.id}`" class="ml-2 w-28 rounded border p-2"></label><input v-model="line.credit_document_no" :disabled="!editable" :aria-label="`退货贷项单号 ${line.id}`" placeholder="供应商认可的退货 / 贷项单号" class="min-w-52 rounded border p-2"><label>贷项日期<input v-model="line.credit_date" :disabled="!editable" type="date" :aria-label="`贷项日期 ${line.id}`" class="ml-2 rounded border p-2"></label><span class="text-slate-500">依据核实后补齐拟结算价格；库存平均成本不作为退货结算价。</span></div></td></tr>
            </tbody>
            <tbody v-if="!shown.length"><tr><td colspan="7" class="p-10 text-center text-slate-400">{{ query ? '没有匹配明细' : '本期暂无已确定验收日期的供应商进退货记录' }}</td></tr></tbody>
          </table></div>
          <div v-if="editable" class="border-t p-3"><button type="button" class="rounded-lg border px-3 py-2 text-xs text-teal-700" @click="invoice.lines.push(blank()); change()">补录未匹配的供应商凭证</button></div>
          <div v-if="document && !dirty" class="border-t bg-slate-50 p-4 text-xs"><div class="flex flex-wrap gap-6 font-bold"><span>进货金额 {{ display(document.result.inbound_amount) }}</span><span>退货金额 {{ display(document.result.return_amount) }}</span><span>本厂应结 {{ display(document.result.net_amount) }}</span><span>拟结算应结 {{ display(document.result.statement_amount) }}</span><span>{{ workspace.currency }}</span></div><p v-for="(issue, i) in document.result.issues" :key="i" class="mt-2 text-amber-700">{{ issue }}</p></div>
          <footer class="flex flex-wrap items-center justify-between gap-3 border-t p-4 text-xs"><div class="space-y-1 text-slate-500"><p v-if="!monthEnded">本月尚未结束，可先保存核对草稿，月份结束后再确认。</p><p>确认后该月进退货更正需先建立重核版本。</p><p>账单有运费、折扣、税差等额外项目时，请保留未匹配行核实，不能直接忽略差额。</p><p v-if="collaborative && !supplierConfirmed">供应商尚未确认当前版本。</p></div><div class="flex gap-2"><button v-if="(!document || document.status === 'DRAFT') && canManage" :disabled="busy" class="rounded-lg border border-teal-300 px-4 py-2 text-teal-700">保存并核对差异</button><button v-if="document?.status === 'DRAFT' && canConfirm" type="button" :disabled="busy || dirty || !monthEnded || document.stale || problemCount > 0 || !invoice.same_price_basis || !supplierConfirmed" class="rounded-lg bg-teal-700 px-4 py-2 text-white disabled:opacity-40" @click="act('confirm')">确认对账完成</button></div></footer>
        </form>
      </article>
      <form v-if="document?.status === 'CONFIRMED' && canConfirm && !dirty" class="flex flex-wrap items-center gap-3 rounded-xl border bg-white p-4 text-xs" @submit.prevent="act('reopen')"><span>来源发生变化或需更正账单，请建立重核版本，原确认记录保留。</span><input v-model="reopenReason" required minlength="4" maxlength="2000" aria-label="供应商对账重核原因" placeholder="填写重核原因" class="h-9 min-w-52 flex-1 rounded border px-3"><button :disabled="busy" class="h-9 rounded-lg border px-4">建立重核版本</button></form>
    </template>
  </section>
</template>
