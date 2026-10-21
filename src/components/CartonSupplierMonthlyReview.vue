<script setup lang="ts">
import CartonFilterBar from '@/components/CartonFilterBar.vue'
import '@/features/carton-procurement/layout.css'
import CartonSourceLinks from './CartonSourceLinks.vue'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import { factoryContexts } from '@/data/enterpriseMock'
import { supplierSettlementApi as api, type SettlementDocument, type SupplierSettlementWorkspace } from '@/api/cartonSupplierSettlement'
import { exportSettlementLines, settlementDateLabel, settlementSourceLabel } from '@/features/carton-procurement/settlementExport'
import CartonSettlementFilters from '@/components/CartonSettlementFilters.vue'
import { matchesSettlementLine, settlementStage, type SettlementLineFilter, type SettlementBusinessKind } from '@/features/carton-procurement/queryFilters'

const props = defineProps<{ factories: { factory_id: string; supplier_name: string }[]; search?: string }>()
const emit = defineEmits<{ 'update:search': [value: string]; prices: [factoryId: string] }>()
const auth = useAuthStore()
const today = () => new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
const factory = ref(''), period = ref(today().slice(0, 7)), currency = ref('CNY')
const workspace = ref<SupplierSettlementWorkspace | null>(null), selected = ref('')
const localQuery = ref(''), lineFilter = ref<SettlementLineFilter>('ALL'), documentFilter = ref('ALL'), businessKind = ref<SettlementBusinessKind>('')
const query = computed({ get: () => props.search ?? localQuery.value, set: (value: string) => { if (props.search === undefined) localQuery.value = value; else emit('update:search', value) } })
const busy = ref(false), error = ref(''), message = ref(''), reason = ref('')
let generation = 0
const document = computed(() => workspace.value?.documents.find(row => row.id === selected.value))
const sourceMap = computed(() => new Map(document.value?.sources.map(row => [row.source_key, row]) ?? []))
const shown = computed(() => document.value?.statement.lines.filter(line => matchesSettlementLine(line, sourceMap.value.get(line.source_key), document.value?.result.line_results.find(row => row.id === line.id), query.value, lineFilter.value, businessKind.value)) ?? [])
const filteredDocuments = computed(() => workspace.value?.documents.filter(doc => documentFilter.value === 'ALL' || settlementStage(doc) === documentFilter.value || doc.id === selected.value) ?? [])
const canReview = computed(() => auth.can('carton_supplier:approve', '*', '*') && auth.can('carton_supplier:approve', factory.value, '*'))
const reviewable = computed(() => !!document.value && document.value.status === 'DRAFT' && !document.value.stale && canReview.value)
const confirmable = computed(() => reviewable.value && document.value!.period < today().slice(0, 7) && !document.value!.result.issues.length)
const display = (value: string | null | undefined) => value == null ? '待核实' : value
const factoryName = (id: string) => factoryContexts.find(row => row.id === id)?.shortName ?? id
async function load() {
  const token = ++generation
  workspace.value = null; selected.value = ''; error.value = ''; message.value = ''; reason.value = ''
  if (!factory.value) { busy.value = false; return }
  busy.value = true
  try {
    const result = await api.supplierWorkspace(factory.value, period.value, currency.value)
    if (token !== generation) return
    workspace.value = result; selected.value = result.documents[0]?.id ?? ''
  } catch (err) { if (token === generation) error.value = getApiErrorMessage(err) }
  finally { if (token === generation) busy.value = false }
}
async function review(decision: 'CONFIRMED' | 'DISPUTED') {
  if (busy.value || !reviewable.value || !document.value || (decision === 'CONFIRMED' && !confirmable.value)) return
  const token = generation, doc = document.value
  busy.value = true; error.value = ''; message.value = ''
  try {
    const result = await api.supplierReview(doc.id, factory.value, doc.revision, decision, reason.value)
    if (token !== generation) return
    workspace.value!.documents = workspace.value!.documents.map(row => row.id === result.id ? result : row)
    message.value = decision === 'CONFIRMED' ? '已确认当前版本结算明细，等待本厂完成确认；此状态不代表付款。' : '异议已记录，请与本厂核实后更新月结版本。'
    reason.value = ''
  } catch (err) { if (token === generation) error.value = getApiErrorMessage(err) }
  finally { if (token === generation) busy.value = false }
}
watch(() => props.factories, values => {
  if (!values.some(row => row.factory_id === factory.value)) factory.value = values[0]?.factory_id ?? ''
}, { immediate: true })
watch([factory, period, currency], () => void load(), { immediate: true })
watch(factory, () => { query.value = ''; lineFilter.value = 'ALL'; documentFilter.value = 'ALL'; businessKind.value = '' })
watch(selected, () => { reason.value = ''; message.value = '' })
onBeforeUnmount(() => { generation++ })
</script>

<template>
  <section class="space-y-4" aria-label="供应商月结确认">
    <header class="rounded-xl border border-teal-200 bg-white p-4">
      <h2 class="font-bold text-slate-900">双方月结对账</h2>
      <p class="mt-2 text-xs text-muted-foreground">本页货款净额不含独立费用或付款核销；完整往来与收款回执请到“应付与收款”查看。</p>
      <button type="button" :disabled="!factory" class="mt-3 rounded-lg border px-3 py-2 text-xs font-semibold text-teal-800" @click="emit('prices', factory)">收料单价更正 / 待办</button>
      <p class="mt-2 text-xs leading-6 text-slate-600">核对供应商原送货、仓库有效验收与本月拟结算明细。进货按实际验收日期归月；已确认月份补录原送货凭证，须由内部说明原因重开，补证后双方重新确认。本厂保存的协同月结草稿会显示在这里，核对确认不表示付款。</p>
      <CartonFilterBar label="月结期间筛选" class="mt-3 rounded-lg">
        <label>厂区<select v-model="factory" :disabled="busy" aria-label="供应商月结厂区" class="mt-1 block h-9 rounded-lg border px-3"><option v-for="row in factories" :key="row.factory_id" :value="row.factory_id">{{ factoryName(row.factory_id) }}</option></select></label>
        <label>月份<input v-model="period" :disabled="busy" aria-label="供应商月结月份" type="month" class="mt-1 block h-9 rounded-lg border px-3"></label>
        <label>币种<input v-model="currency" :disabled="busy" aria-label="供应商月结币种" maxlength="8" class="mt-1 block h-9 w-24 rounded-lg border px-3"></label>
        <template #actions><button type="button" :disabled="busy || !factory" class="h-9 rounded-lg border px-3" @click="load">查询 / 刷新</button></template>
      </CartonFilterBar>
    </header>
    <p v-if="error" role="alert" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
    <p v-if="message" role="status" class="rounded-lg border border-teal-200 bg-teal-50 p-3 text-sm text-teal-800">{{ message }}</p>
    <p v-if="busy && !workspace" class="p-6 text-sm text-slate-500">正在读取月结明细…</p>
    <p v-else-if="!document" class="rounded-xl border bg-white p-8 text-sm text-slate-500">本期暂无本厂保存的协同月结草稿，请联系本厂核实月份或生成草稿。</p>
    <article v-if="document" class="overflow-hidden rounded-xl border bg-white">
      <div class="flex flex-wrap items-center gap-3 border-b p-4 text-xs">
        <select v-model="selected" :disabled="busy" aria-label="供应商月结版本" class="h-9 rounded-lg border px-3"><option v-for="doc in filteredDocuments" :key="doc.id" :value="doc.id">版本 {{ doc.version }} · {{ doc.statement.statement_no }} · {{ doc.status === 'CONFIRMED' ? '双方已确认' : doc.status === 'SUPERSEDED' ? '历史版本' : '核对草稿' }}</option></select>
        <span>{{ document.statement.tax_basis === 'INCLUSIVE' ? '含税' : '未税' }} · {{ document.currency }}</span>
        <span v-if="document.stale" class="text-amber-800">来源已变化，须本厂更新草稿后重新核对</span>
        <span v-else-if="document.result.supplier_review">{{ document.result.supplier_review.decision === 'CONFIRMED' ? '供应商已确认' : '供应商已提出异议' }} · {{ document.result.supplier_review.at }}</span>
        <span v-else>供应商待确认</span>
      </div>
      <div class="flex flex-wrap items-center justify-between gap-2 border-b p-3 text-xs"><span>可筛选配卡专项并导出当前版本明细。</span><button type="button" :disabled="busy || !document || !shown.length" class="rounded border px-3 py-2 text-teal-800 disabled:opacity-40" @click="document && exportSettlementLines(shown, sourceMap, document.period, document.currency, lineFilter)">导出当前筛选明细 CSV</button></div>
        <CartonSettlementFilters :hide-search="props.search !== undefined" v-model:query="query" v-model:lines="lineFilter" v-model:stage="documentFilter" v-model:business-kind="businessKind" :shown="shown.length" :total="document.statement.lines.length" />
      <div class="overflow-x-auto carton-table-wrap"><table class="w-full min-w-[960px] text-left text-xs carton-table-fit" aria-label="双方月结明细"><thead class="bg-slate-50 text-slate-600"><tr><th class="p-3">单据 / 货号 / 规格</th><th class="p-3">供应商原送货</th><th class="p-3">本厂有效验收</th><th class="p-3">拟结算数量 / 单价 / 金额</th><th class="p-3">核对依据</th></tr></thead><tbody class="divide-y">
        <tr v-for="line in shown" :key="line.id"><td data-label="单据 / 货号 / 规格" class="p-3"><b>{{ line.document_no }}</b><span class="ml-2 rounded bg-muted px-2 py-1">{{ settlementSourceLabel(sourceMap.get(line.source_key)) }}</span><CartonSourceLinks :factory-id="factory" supplier :sources="sourceMap.get(line.source_key)?.special_request_id ? [{ id: sourceMap.get(line.source_key)!.special_request_id!, request_no: sourceMap.get(line.source_key)!.special_request_no || '原需求单', kind: sourceMap.get(line.source_key)!.special_request_kind || 'SAMPLE' }] : []" /><p>{{ sourceMap.get(line.source_key)?.item_no }} · {{ sourceMap.get(line.source_key)?.packaging_type }} · {{ sourceMap.get(line.source_key)?.specification }}</p><p class="mt-1 text-slate-500">{{ settlementDateLabel(sourceMap.get(line.source_key)) }} {{ sourceMap.get(line.source_key)?.acceptance_date || '待核实' }}</p><p v-if="sourceMap.get(line.source_key)?.posting_date" class="mt-1 text-slate-500">库存记账 {{ sourceMap.get(line.source_key)?.posting_date }}</p></td>
          <td data-label="供应商原送货" class="p-3"><template v-if="sourceMap.get(line.source_key)?.supplier_delivery">{{ sourceMap.get(line.source_key)?.supplier_delivery?.quantity }} {{ sourceMap.get(line.source_key)?.unit }}<p>单价 {{ display(sourceMap.get(line.source_key)?.supplier_delivery?.original_unit_price ?? sourceMap.get(line.source_key)?.supplier_delivery?.unit_price) }}</p><p>金额 {{ display(sourceMap.get(line.source_key)?.supplier_delivery?.amount) }}</p><p v-if="sourceMap.get(line.source_key)?.supplier_delivery?.original_quantity != null && Number(sourceMap.get(line.source_key)?.supplier_delivery?.original_quantity) !== Number(sourceMap.get(line.source_key)?.supplier_delivery?.quantity)" class="mt-1 text-teal-700">原单共 {{ sourceMap.get(line.source_key)?.supplier_delivery?.original_quantity }} {{ sourceMap.get(line.source_key)?.unit }}；此行数量和金额为本次验收分摊</p><p v-if="sourceMap.get(line.source_key)?.supplier_delivery?.price_warning" class="mt-1 text-amber-800">{{ sourceMap.get(line.source_key)?.supplier_delivery?.price_warning }}</p></template><span v-else>{{ sourceMap.get(line.source_key)?.kind === 'RETURN_REFUND' ? '现金到账凭证，加回应结' : '凭证补录 / 退货核对' }}</span></td>
          <td data-label="本厂有效验收" class="p-3"><template v-if="sourceMap.get(line.source_key)?.kind === 'RETURN_REFUND'"><b>资金凭证 · 现金到账</b><p class="mt-1">已核实 {{ display(sourceMap.get(line.source_key)?.amount) }} {{ document.currency }}</p><p class="mt-1 text-slate-500">加回应结，不计实物收料</p></template><template v-else>{{ display(sourceMap.get(line.source_key)?.quantity) }} {{ sourceMap.get(line.source_key)?.unit }}<p>单价 {{ display(sourceMap.get(line.source_key)?.unit_price) }}</p><p>金额 {{ display(sourceMap.get(line.source_key)?.amount) }}</p></template></td>
          <td data-label="拟结算数量 / 单价 / 金额" class="p-3">{{ display(line.quantity) }} {{ sourceMap.get(line.source_key)?.unit }}<p>单价 {{ display(line.unit_price) }}</p><p class="font-bold text-teal-700">金额 {{ display(line.amount) }}</p></td>
          <td data-label="核对依据" class="max-w-72 break-words p-3"><p>{{ line.note || '—' }}</p><p v-if="sourceMap.get(line.source_key)?.supplier_delivery?.difference_reason" class="mt-1 text-amber-800">收料：{{ sourceMap.get(line.source_key)?.supplier_delivery?.difference_reason }}</p><p v-if="line.credit_document_no" class="mt-1">退货贷项 {{ line.credit_document_no }} · {{ line.credit_date }} · 认可单价 {{ display(line.approved_return_unit_price) }}</p></td></tr>
      </tbody></table></div>
      <div class="space-y-2 border-t p-4 text-xs"><p class="font-bold">本厂应结 {{ display(document.result.net_amount) }} · 拟结算 {{ display(document.result.statement_amount) }} {{ document.currency }}</p><p v-if="document.result.cash_refund_amount !== undefined" class="tabular-nums">供货 {{ display(document.result.inbound_amount) }} − 退货贷项 {{ display(document.result.return_amount) }} + 本月已确认现金退款 {{ display(document.result.cash_refund_amount) }} = 本期净应结 {{ display(document.result.net_amount) }} {{ document.currency }}</p><p v-if="document.result.cash_refund_amount !== undefined" class="text-slate-500">月结抵扣仅分配贷项，不再另减。现金按实际到账月份计入，未核实申报不计到账。</p><p v-for="(issue, index) in document.result.issues" :key="index" class="text-amber-800">{{ issue }}</p><p v-for="(row, index) in document.result.unsettled_shipments" :key="index" class="text-slate-500">未计本期：{{ row.document_no }} · {{ row.item_no }} {{ row.specification }} · {{ row.quantity }} {{ row.unit }} · 原价 {{ display(row.original_unit_price) }} · {{ row.reason }}<span v-if="row.difference_reason"> · {{ row.difference_reason }}</span></p><p v-if="document.result.supplier_review?.reason">供应商反馈：{{ document.result.supplier_review.reason }}</p></div>
      <footer v-if="document.status === 'DRAFT'" class="space-y-3 border-t p-4 text-xs"><p v-if="document.period >= today().slice(0, 7)" class="text-slate-500">本月尚未结束，可先核对或提出异议，月份结束后再确认。</p><label class="block">核对反馈<input v-model="reason" :disabled="busy || !reviewable" aria-label="供应商月结反馈" maxlength="2000" placeholder="有异议时请填写具体单据及原因，至少四字" class="mt-1 block h-9 w-full rounded-lg border px-3"></label><div class="flex flex-wrap gap-3"><button type="button" :disabled="busy || !reviewable || reason.trim().length < 4" class="rounded-lg border border-amber-300 px-4 py-2 text-amber-800 disabled:opacity-40" @click="review('DISPUTED')">提出对账异议</button><button type="button" :disabled="busy || !confirmable" class="rounded-lg bg-teal-700 px-4 py-2 font-bold text-white disabled:opacity-40" @click="review('CONFIRMED')">确认本月结算明细</button></div></footer>
    </article>
  </section>
</template>
