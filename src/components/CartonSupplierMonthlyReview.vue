<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import { factoryContexts } from '@/data/enterpriseMock'
import { supplierSettlementApi as api, type SettlementDocument, type SupplierSettlementWorkspace } from '@/api/cartonSupplierSettlement'

const props = defineProps<{ factories: { factory_id: string; supplier_name: string }[] }>()
const auth = useAuthStore()
const today = () => new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
const factory = ref(''), period = ref(today().slice(0, 7)), currency = ref('CNY')
const workspace = ref<SupplierSettlementWorkspace | null>(null), selected = ref('')
const busy = ref(false), error = ref(''), message = ref(''), reason = ref('')
let generation = 0
const document = computed(() => workspace.value?.documents.find(row => row.id === selected.value))
const sourceMap = computed(() => new Map(document.value?.sources.map(row => [row.source_key, row]) ?? []))
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
watch(selected, () => { reason.value = ''; message.value = '' })
onBeforeUnmount(() => { generation++ })
</script>

<template>
  <section class="space-y-4" aria-label="供应商月结确认">
    <header class="rounded-xl border border-teal-200 bg-white p-4">
      <h2 class="font-bold text-slate-900">双方月结对账</h2>
      <p class="mt-2 text-xs leading-6 text-slate-600">核对供应商原送货、仓库有效验收与本月拟结算明细。进货按实际验收日期归月；本厂保存的协同月结草稿会显示在这里，核对确认不表示付款。</p>
      <div class="mt-3 flex flex-wrap items-end gap-3 text-xs">
        <label>厂区<select v-model="factory" :disabled="busy" aria-label="供应商月结厂区" class="mt-1 block h-9 rounded-lg border px-3"><option v-for="row in factories" :key="row.factory_id" :value="row.factory_id">{{ factoryName(row.factory_id) }}</option></select></label>
        <label>月份<input v-model="period" :disabled="busy" aria-label="供应商月结月份" type="month" class="mt-1 block h-9 rounded-lg border px-3"></label>
        <label>币种<input v-model="currency" :disabled="busy" aria-label="供应商月结币种" maxlength="8" class="mt-1 block h-9 w-24 rounded-lg border px-3"></label>
        <button type="button" :disabled="busy || !factory" class="h-9 rounded-lg border px-3" @click="load">查询 / 刷新</button>
      </div>
    </header>
    <p v-if="error" role="alert" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
    <p v-if="message" role="status" class="rounded-lg border border-teal-200 bg-teal-50 p-3 text-sm text-teal-800">{{ message }}</p>
    <p v-if="busy && !workspace" class="p-6 text-sm text-slate-500">正在读取月结明细…</p>
    <p v-else-if="!document" class="rounded-xl border bg-white p-8 text-sm text-slate-500">本期暂无本厂保存的协同月结草稿，请联系本厂核实月份或生成草稿。</p>
    <article v-if="document" class="overflow-hidden rounded-xl border bg-white">
      <div class="flex flex-wrap items-center gap-3 border-b p-4 text-xs">
        <select v-model="selected" :disabled="busy" aria-label="供应商月结版本" class="h-9 rounded-lg border px-3"><option v-for="doc in workspace!.documents" :key="doc.id" :value="doc.id">版本 {{ doc.version }} · {{ doc.statement.statement_no }} · {{ doc.status === 'CONFIRMED' ? '双方已确认' : doc.status === 'SUPERSEDED' ? '历史版本' : '核对草稿' }}</option></select>
        <span>{{ document.statement.tax_basis === 'INCLUSIVE' ? '含税' : '未税' }} · {{ document.currency }}</span>
        <span v-if="document.stale" class="text-amber-800">来源已变化，须本厂更新草稿后重新核对</span>
        <span v-else-if="document.result.supplier_review">{{ document.result.supplier_review.decision === 'CONFIRMED' ? '供应商已确认' : '供应商已提出异议' }} · {{ document.result.supplier_review.at }}</span>
        <span v-else>供应商待确认</span>
      </div>
      <div class="overflow-x-auto"><table class="w-full min-w-[960px] text-left text-xs" aria-label="双方月结明细"><thead class="bg-slate-50 text-slate-600"><tr><th class="p-3">单据 / 货号 / 规格</th><th class="p-3">供应商原送货</th><th class="p-3">本厂有效验收</th><th class="p-3">拟结算数量 / 单价 / 金额</th><th class="p-3">核对依据</th></tr></thead><tbody class="divide-y">
        <tr v-for="line in document.statement.lines" :key="line.id"><td class="p-3"><b>{{ line.document_no }}</b><p>{{ sourceMap.get(line.source_key)?.item_no }} · {{ sourceMap.get(line.source_key)?.packaging_type }} · {{ sourceMap.get(line.source_key)?.specification }}</p><p class="mt-1 text-slate-500">{{ sourceMap.get(line.source_key)?.kind === 'RETURN' ? '退货' : '验收' }} {{ sourceMap.get(line.source_key)?.acceptance_date || '待核实' }}</p></td>
          <td class="p-3"><template v-if="sourceMap.get(line.source_key)?.supplier_delivery">{{ sourceMap.get(line.source_key)?.supplier_delivery?.quantity }} {{ sourceMap.get(line.source_key)?.unit }}<p>单价 {{ display(sourceMap.get(line.source_key)?.supplier_delivery?.original_unit_price ?? sourceMap.get(line.source_key)?.supplier_delivery?.unit_price) }}</p><p>金额 {{ display(sourceMap.get(line.source_key)?.supplier_delivery?.amount) }}</p><p v-if="sourceMap.get(line.source_key)?.supplier_delivery?.price_warning" class="mt-1 text-amber-800">{{ sourceMap.get(line.source_key)?.supplier_delivery?.price_warning }}</p></template><span v-else>凭证补录 / 退货核对</span></td>
          <td class="p-3">{{ display(sourceMap.get(line.source_key)?.quantity) }} {{ sourceMap.get(line.source_key)?.unit }}<p>单价 {{ display(sourceMap.get(line.source_key)?.unit_price) }}</p><p>金额 {{ display(sourceMap.get(line.source_key)?.amount) }}</p></td>
          <td class="p-3">{{ display(line.quantity) }} {{ sourceMap.get(line.source_key)?.unit }}<p>单价 {{ display(line.unit_price) }}</p><p class="font-bold text-teal-700">金额 {{ display(line.amount) }}</p></td>
          <td class="max-w-72 break-words p-3"><p>{{ line.note || '—' }}</p><p v-if="sourceMap.get(line.source_key)?.supplier_delivery?.difference_reason" class="mt-1 text-amber-800">收料：{{ sourceMap.get(line.source_key)?.supplier_delivery?.difference_reason }}</p><p v-if="line.credit_document_no" class="mt-1">退货贷项 {{ line.credit_document_no }} · {{ line.credit_date }} · 认可单价 {{ display(line.approved_return_unit_price) }}</p></td></tr>
      </tbody></table></div>
      <div class="space-y-2 border-t p-4 text-xs"><p class="font-bold">本厂应结 {{ display(document.result.net_amount) }} · 拟结算 {{ display(document.result.statement_amount) }} {{ document.currency }}</p><p v-for="(issue, index) in document.result.issues" :key="index" class="text-amber-800">{{ issue }}</p><p v-for="row in document.result.unsettled_shipments" :key="row.line_id || row.shipment_id" class="text-slate-500">未计本期：{{ row.document_no }} · {{ row.item_no }} {{ row.specification }} · {{ row.quantity }} {{ row.unit }} · 原价 {{ display(row.original_unit_price) }} · {{ row.reason }}<span v-if="row.difference_reason"> · {{ row.difference_reason }}</span></p><p v-if="document.result.supplier_review?.reason">供应商反馈：{{ document.result.supplier_review.reason }}</p></div>
      <footer v-if="document.status === 'DRAFT'" class="space-y-3 border-t p-4 text-xs"><p v-if="document.period >= today().slice(0, 7)" class="text-slate-500">本月尚未结束，可先核对或提出异议，月份结束后再确认。</p><label class="block">核对反馈<input v-model="reason" :disabled="busy || !reviewable" aria-label="供应商月结反馈" maxlength="2000" placeholder="有异议时请填写具体单据及原因，至少四字" class="mt-1 block h-9 w-full rounded-lg border px-3"></label><div class="flex flex-wrap gap-3"><button type="button" :disabled="busy || !reviewable || reason.trim().length < 4" class="rounded-lg border border-amber-300 px-4 py-2 text-amber-800 disabled:opacity-40" @click="review('DISPUTED')">提出对账异议</button><button type="button" :disabled="busy || !confirmable" class="rounded-lg bg-teal-700 px-4 py-2 font-bold text-white disabled:opacity-40" @click="review('CONFIRMED')">确认本月结算明细</button></div></footer>
    </article>
  </section>
</template>
