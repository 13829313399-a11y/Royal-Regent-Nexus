<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import CartonFilterBar from '@/components/CartonFilterBar.vue'
import CartonOrderDetailDialog from '@/components/CartonOrderDetailDialog.vue'
import CartonUnifiedDeliveryNotes from '@/components/CartonUnifiedDeliveryNotes.vue'
import { cartonUnifiedDeliveriesApi, type UnifiedDelivery } from '@/api/cartonUnifiedDeliveries'
import { supplierSettlementApi as api, type MonthlyReconciliation, type MonthlySettlementLine } from '@/api/cartonSupplierSettlement'
import { factoryContexts } from '@/data/enterpriseMock'
import { formatBusinessDate } from '@/lib/dateTime'
import { getApiErrorMessage } from '@/lib/http'
import '@/features/carton-procurement/layout.css'

const props = withDefaults(defineProps<{
  factoryId?: string
  factories?: { factory_id: string }[]
  supplier?: boolean
  search?: string
  viewerKey?: string
  refreshKey?: number
  moneyReference?: (value: string, currency: string) => string
}>(), { supplier: false, search: '' })
const emit = defineEmits<{
  'open-receipt': [factory: string, receiptId: string, signal: AbortSignal]
  'open-return': [factory: string, movementId: string, refundId?: string]
}>()

const factories = computed(() => props.factories ?? [])
const selectedFactory = defineModel<string>('selectedFactory', { default: '' })
const factory = computed({
  get: () => props.supplier
    ? factories.value.find(item => item.factory_id === selectedFactory.value)?.factory_id ?? factories.value[0]?.factory_id ?? ''
    : props.factoryId ?? '',
  set: value => { selectedFactory.value = value },
})
const period = defineModel<string>('period', { default: () => formatBusinessDate(new Date().toISOString()).slice(0, 7) })
const currency = defineModel<string>('currency', { default: 'CNY' })
const customerKey = ref('')
const data = shallowRef<MonthlyReconciliation | null>(null)
const busy = ref(false)
const error = ref('')
let generation = 0

async function load() {
  const token = ++generation
  const query = { factory: factory.value, period: period.value, currency: currency.value, supplier: props.supplier }
  data.value = null; error.value = ''; busy.value = false
  if (!query.factory) {
    error.value = query.supplier ? '暂无可对账的服务厂区。' : '请选择厂区后查看本月对账。'
    return
  }
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(query.period)) { error.value = '请选择有效的对账月份。'; return }
  busy.value = true
  try {
    const read = query.supplier ? api.supplierMonthlyWorkspace : api.monthlyWorkspace
    const result = await read(query.factory, query.period, query.currency)
    if (token !== generation) return
    if (result.factory_id !== query.factory || result.period !== query.period || result.currency !== query.currency) {
      throw new Error('返回的对账数据与当前厂区、月份或币种不一致，请刷新重试。')
    }
    if (!result.customers?.some(customer => customer.key === customerKey.value)) customerKey.value = ''
    data.value = result
  } catch (cause) {
    if (token === generation) error.value = getApiErrorMessage(cause)
  } finally {
    if (token === generation) busy.value = false
  }
}

const customer = computed(() => data.value?.customers?.find(item => item.key === customerKey.value))
const allLines = computed(() => data.value?.lines ?? [])
const customerLines = computed(() => allLines.value.filter(row => !customerKey.value || row.customer_key === customerKey.value))
const lines = computed(() => {
  const query = props.search.trim().toLowerCase()
  return query ? customerLines.value.filter(row => [row.document_no, row.item_no, row.customer_name, row.contract_no]
    .some(value => value?.toLowerCase().includes(query))) : customerLines.value
})
const issueText = (value: string) => value.replace('，不能完成月结确认', '').replace('，不能提交核对', '')
const rowIssues = (row: MonthlySettlementLine) => row.issues?.length ? row.issues.map(issueText) : row.amount === null
  ? [row.kind === 'RETURN' ? '退货贷项待核实' : '单价待核实'] : []
const issueRows = computed(() => lines.value.filter(row => rowIssues(row).length))
const globalIssues = computed(() => {
  const current = data.value
  if (!current || customer.value) return []
  return (current.global_issues ?? ('blockers' in current ? (current.blockers as string[]) : [])).map(issueText)
})
const issueCount = computed(() => issueRows.value.length + globalIssues.value.length)
const visibleCounts = computed(() => ({
  receipt: lines.value.filter(row => row.kind === 'RECEIPT').length,
  returns: lines.value.filter(row => row.kind === 'RETURN').length,
  refund: lines.value.filter(row => row.kind === 'RETURN_REFUND').length,
}))
const format = (value: string | null) => value === null ? '待核价' : Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const currencyName = (code: string) => ({ CNY: '人民币', HKD: '港币', USD: '美元' } as Record<string, string>)[code] || code
const factoryName = (id: string) => factoryContexts.find(item => item.id === id)?.shortName ?? id
const kindLabel = (kind: string) => kind === 'RETURN' ? '退货' : kind === 'RETURN_REFUND' ? '退款' : '送货'
const signedQuantity = (row: MonthlySettlementLine) => row.kind === 'RETURN_REFUND' ? '—'
  : (row.kind === 'RETURN' ? '−' : '') + Number(row.quantity).toLocaleString('zh-CN', { maximumFractionDigits: 4 }) + (row.unit ? ' ' + row.unit : '')
const signedAmount = (row: MonthlySettlementLine) => (row.kind === 'RETURN' && Number(row.amount) > 0 ? '−' : '') + format(row.amount)

const references = computed(() => {
  const current = data.value
  const reference = props.moneyReference
  if (current?.currency !== 'CNY' || !reference) return null
  const { inbound, returns, net } = current.totals
  return {
    inbound: inbound === null ? '' : reference(inbound, current.currency),
    returns: returns === null ? '' : reference(returns, current.currency),
    net: net === null ? '' : reference(net, current.currency),
  }
})
function quantityByUnit(rows: MonthlySettlementLine[]) {
  const byUnit = new Map<string, number>()
  for (const row of rows) byUnit.set(row.unit || '', (byUnit.get(row.unit || '') ?? 0) + Number(row.quantity || 0))
  return [...byUnit].filter(([, value]) => value !== 0).map(([unit, value]) => value.toLocaleString('zh-CN', { maximumFractionDigits: 4 }) + (unit ? ' ' + unit : '')).join(' / ') || '0'
}
const receiptLines = computed(() => allLines.value.filter(row => row.kind === 'RECEIPT'))
const byCustomer = computed(() => (data.value?.customers ?? []).filter(item => item.totals.receipt_lines > 0)
  .map(item => ({ key: item.key, name: item.name, count: item.totals.receipt_lines,
    quantity: quantityByUnit(receiptLines.value.filter(row => row.customer_key === item.key)), amount: item.totals.inbound }))
  .sort((left, right) => Number(right.amount ?? 0) - Number(left.amount ?? 0)).slice(0, 8))
const byPackaging = computed(() => (data.value?.packaging ?? []).map(item => {
  const rows = receiptLines.value.filter(row => (row.packaging_type || '纸品类型待补') === item.name)
  return { ...item, key: item.name, count: rows.length, quantity: quantityByUnit(rows) }
}).sort((left, right) => Number(right.amount ?? 0) - Number(left.amount ?? 0)).slice(0, 8))

const sourceRow = shallowRef<MonthlySettlementLine | null>(null)
const delivery = shallowRef<UnifiedDelivery | null>(null)
const sourceLoading = ref(false), sourceError = ref('')
let sourceOpener: HTMLElement | null = null
let sourceController = new AbortController()
const customerSelect = ref<HTMLSelectElement | null>(null)
const sourceAction = (row: MonthlySettlementLine) => row.reference?.kind === 'RECEIPT' ? '打开原收料单'
  : row.reference?.kind === 'DELIVERY' ? '打开原送货单' : row.kind === 'RETURN_REFUND' ? '查看原退款凭证' : '打开原退货单'

function clearSource() {
  sourceController.abort()
  sourceRow.value = null; delivery.value = null; sourceLoading.value = false; sourceError.value = ''
}
async function openSource(row: MonthlySettlementLine, event: Event) {
  const reference = row.reference
  if (!reference || !factory.value) return
  sourceController.abort()
  sourceController = new AbortController()
  const signal = sourceController.signal, sourceFactory = factory.value
  if (reference.kind === 'RECEIPT') {
    if (!props.supplier) emit('open-receipt', sourceFactory, reference.id, signal)
    return
  }
  if (reference.kind === 'RETURN') {
    emit('open-return', sourceFactory, reference.id, reference.refund_id)
    return
  }
  if (!props.supplier) return
  sourceOpener = event.currentTarget as HTMLElement
  sourceRow.value = row
  sourceLoading.value = true; sourceError.value = ''; delivery.value = null
  try {
    const original = await cartonUnifiedDeliveriesApi.supplierDetail(sourceFactory, reference.id, signal)
    if (signal.aborted) return
    if (original.id !== reference.id || original.factory_id !== sourceFactory) throw new Error('返回的原送货单与当前厂区或凭证不符。')
    delivery.value = original
  } catch (cause) {
    if (!signal.aborted) sourceError.value = getApiErrorMessage(cause)
  } finally {
    if (!signal.aborted) sourceLoading.value = false
  }
}
function restoreSourceFocus(event: Event) {
  const target = sourceOpener?.isConnected ? sourceOpener : customerSelect.value
  if (target?.isConnected) { event.preventDefault(); target.focus() }
  sourceOpener = null
}
watch([factory, () => props.viewerKey, () => props.supplier], () => { customerKey.value = '' }, { flush: 'sync' })
watch([factory, period, currency, () => props.viewerKey, () => props.supplier], () => {
  clearSource()
  void load()
}, { immediate: true, flush: 'sync' })
watch(customerKey, () => { if (!sourceRow.value) sourceController.abort() }, { flush: 'sync' })
watch(() => props.refreshKey, () => { void load() })
onBeforeUnmount(() => { generation++; sourceController.abort() })
</script>

<template>
  <section class="space-y-4" :aria-label="supplier ? '供应商本月对账' : '本月对账'">
    <CartonFilterBar label="本月对账筛选">
      <label v-if="supplier && factories.length > 1">厂区<select v-model="factory" aria-label="供应商对账厂区"><option v-for="item in factories" :key="item.factory_id" :value="item.factory_id">{{ factoryName(item.factory_id) }}</option></select></label>
      <label>对账月份<input v-model="period" :aria-label="supplier ? '供应商对账月份' : '本月对账月份'" type="month"></label>
      <label>原账币种<select v-model="currency" :aria-label="supplier ? '供应商对账币种' : '本月对账币种'"><option value="CNY">人民币</option><option value="HKD">港币</option><option value="USD">美元</option></select></label>
      <label>客户<select ref="customerSelect" v-model="customerKey" aria-label="本月对账客户" :disabled="!data || busy"><option value="">全部客户</option><option v-for="item in data?.customers" :key="item.key" :value="item.key">{{ item.name }}</option></select></label>
      <template #actions>
        <button type="button" :disabled="busy" class="rounded-lg border px-4 font-semibold disabled:opacity-40" @click="load">刷新</button>
        <span class="pb-2 text-[10px] text-slate-500">只读对账</span>
      </template>
      <template #footer>
        <span class="text-slate-500">{{ data?.supplier_name || (busy ? '读取供应商中' : '暂无对账数据') }} · {{ factoryName(factory) }} · {{ data?.period || period }} · {{ currencyName(data?.currency || currency) }}</span>
      </template>
    </CartonFilterBar>

    <p v-if="error" role="alert" class="rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-700">{{ error }}</p>
    <p v-if="supplier" class="rounded-xl border border-slate-200 bg-white p-3 text-xs text-slate-600">按厂区、月份和原币核对送货、退货和应结金额。退货或退款在原凭证办理，付款回执在「应付与收款」办理。</p>
    <p v-else class="rounded-xl border border-slate-200 bg-white p-3 text-xs text-slate-600">仓库在这里核对送货、退货、应结金额与待处理事项。退货回执、实际付款及库存锁期在对应入口按原凭证办理。</p>
    <p v-if="busy" role="status" class="rounded-xl border bg-white p-6 text-center text-xs text-slate-500">正在汇总 {{ period }} · {{ currencyName(currency) }} 的收料与退货…</p>

    <template v-else-if="data">
      <section aria-label="本厂东康总额" class="space-y-2">
        <h2 class="text-sm font-bold text-slate-800">本厂东康总额</h2>
        <div class="grid gap-3 sm:grid-cols-3">
          <article class="min-w-0 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div class="text-[11px] text-slate-500">本月已验收送货</div>
            <div class="mt-2 break-words text-xl font-bold tabular-nums">{{ format(data.totals.inbound) }} <span class="text-xs font-medium text-slate-500">{{ currencyName(data.currency) }}</span></div>
            <p v-if="references?.inbound" class="mt-1 break-words text-xs tabular-nums text-teal-700">{{ references.inbound }}</p>
            <div class="mt-1 text-[10px] text-slate-500">{{ data.totals.documents }} 张送货单 · {{ data.totals.receipt_lines }} 行</div>
          </article>
          <article class="min-w-0 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div class="text-[11px] text-slate-500">退货贷项</div>
            <div class="mt-2 break-words text-xl font-bold tabular-nums text-rose-700">{{ format(data.totals.returns) }} <span class="text-xs font-medium text-slate-500">{{ currencyName(data.currency) }}</span></div>
            <p v-if="references?.returns" class="mt-1 break-words text-xs tabular-nums text-teal-700">{{ references.returns }}</p>
            <div class="mt-1 text-[10px] text-slate-500">{{ data.totals.return_lines }} 笔{{ data.totals.refund_lines ? ' · 已核实退款 ' + format(data.totals.refunds) : '' }}</div>
          </article>
          <article class="min-w-0 rounded-xl border border-teal-200 bg-teal-50/40 p-4 shadow-sm">
            <div class="text-[11px] font-bold text-teal-800">本月应结</div>
            <div class="mt-2 break-words text-2xl font-bold tabular-nums text-teal-900">{{ format(data.totals.net) }} <span class="text-xs font-medium text-slate-500">{{ currencyName(data.currency) }}</span></div>
            <p v-if="references?.net" class="mt-1 break-words text-xs tabular-nums text-teal-700">{{ references.net }}</p>
            <div class="mt-1 text-[10px] text-teal-700">送货金额 − 退货贷项 ＋ 本月已核实现金退款</div>
          </article>
        </div>
        <p v-if="data.global_issues?.length" class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">有全厂凭证待核实。金额按已纳入本期的凭证汇总，可在「全部客户」查看提示。</p>
      </section>

      <section v-if="customer" aria-label="所选客户小计" class="space-y-2 rounded-xl border border-slate-200 bg-white p-4 text-xs">
        <h2 class="break-words text-sm font-bold">{{ customer.name }} · 客户小计（{{ currencyName(data.currency) }}）</h2>
        <div class="flex flex-wrap gap-x-6 gap-y-2 tabular-nums">
          <span>已验收送货 <b>{{ format(customer.totals.inbound) }}</b></span>
          <span>退货贷项 <b>{{ format(customer.totals.returns) }}</b></span>
          <span>已核实退款 <b>{{ format(customer.totals.refunds) }}</b></span>
          <span class="text-teal-800">应结 <b>{{ format(customer.totals.net) }}</b></span>
        </div>
      </section>

      <article class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm" aria-label="本月对账待处理清单">
        <div class="border-b border-slate-100 px-4 py-3">
          <h2 class="font-bold text-slate-950">待处理清单 · {{ issueCount }} 笔</h2>
          <p class="mt-1 text-[11px] text-slate-500">按单号打开原凭证核对，处理后刷新本月对账。</p>
        </div>
        <ul v-if="issueCount" class="divide-y divide-slate-100 text-xs">
          <li v-for="row in issueRows" :key="row.source_key" class="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
            <div class="min-w-0 break-words"><p class="font-semibold">{{ row.customer_name || '未填写客户' }} · {{ row.document_no || '无单号' }}<span v-if="row.item_no"> · {{ row.item_no }}</span></p><p class="mt-1 text-amber-800">{{ rowIssues(row).join(' · ') }}</p></div>
            <button v-if="row.reference" type="button" class="rounded-lg border px-3 py-2 font-semibold text-teal-800" @click="openSource(row, $event)">{{ sourceAction(row) }}</button>
            <span v-else class="text-slate-500">{{ supplier ? '请联系仓库核对原凭证' : '原凭证待定位' }}</span>
          </li>
          <li v-for="issue in globalIssues" :key="issue" class="px-4 py-3 text-amber-800">全厂提示 · {{ issue }}</li>
        </ul>
        <p v-else class="px-4 py-6 text-center text-xs text-slate-500">当前范围没有待处理事项。</p>
      </article>

      <article class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm" :aria-label="supplier ? '供应商本月对账明细' : '本月对账明细'">
        <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
          <div><h2 class="font-bold text-slate-950">本月明细<span v-if="customer"> · {{ customer.name }}</span></h2><p class="mt-1 text-[11px] text-slate-500">金额按原币，退货列为扣减，现金退款列为正项。</p></div>
          <span class="text-[11px] text-slate-500">{{ visibleCounts.receipt }} 行送货 · {{ visibleCounts.returns }} 笔退货 · {{ visibleCounts.refund }} 笔退款</span>
        </div>
        <div class="overflow-x-auto carton-table-wrap"><table class="w-full text-left text-xs carton-table-fit" aria-label="本月对账明细表">
          <thead class="bg-slate-50 text-[10px] font-bold text-slate-500"><tr><th class="px-3 py-2">类型</th><th class="px-3 py-2">单号</th><th class="px-3 py-2">验收/交接日</th><th class="px-3 py-2">客户</th><th class="px-3 py-2">货号 / 纸品</th><th class="px-3 py-2 text-right">数量</th><th class="px-3 py-2 text-right">单价</th><th class="px-3 py-2 text-right">金额</th><th class="px-3 py-2">原凭证</th></tr></thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-for="row in lines" :key="row.source_key" :class="row.kind === 'RETURN' ? 'bg-rose-50/40' : ''">
              <td data-label="类型" class="px-3 py-2"><span class="rounded px-1.5 py-0.5 text-[10px] font-bold" :class="row.kind === 'RECEIPT' ? 'bg-teal-50 text-teal-800' : 'bg-rose-50 text-rose-700'">{{ kindLabel(row.kind) }}</span></td>
              <td data-label="单号" class="px-3 py-2 font-mono">{{ row.document_no || '无单号' }}</td>
              <td data-label="验收/交接日" class="px-3 py-2">{{ row.acceptance_date || '待核实' }}</td>
              <td data-label="客户" class="px-3 py-2">{{ row.customer_name || '—' }}</td>
              <td data-label="货号 / 纸品" class="px-3 py-2">{{ row.item_no || '—' }}<span class="text-slate-500"> · {{ row.packaging_type || '纸品待补' }}</span></td>
              <td data-label="数量" class="px-3 py-2 text-right tabular-nums">{{ signedQuantity(row) }}</td>
              <td data-label="单价" class="px-3 py-2 text-right tabular-nums">{{ row.unit_price === null ? '—' : format(row.unit_price) }}</td>
              <td data-label="金额" class="px-3 py-2 text-right font-semibold tabular-nums">{{ signedAmount(row) }}</td>
              <td data-label="原凭证" class="px-3 py-2"><button v-if="row.reference" type="button" class="rounded text-left font-semibold text-teal-800 underline underline-offset-2" @click="openSource(row, $event)">{{ sourceAction(row) }}</button><span v-else>—</span><p v-if="row.price_basis === 'SUPPLIER_ORIGINAL'" class="mt-1 text-[10px] text-teal-800">按供应商原单价</p></td>
            </tr>
            <tr v-if="!lines.length"><td colspan="9" class="px-4 py-8 text-center text-xs text-slate-500">当前范围没有已验收送货、退货或退款明细</td></tr>
          </tbody>
        </table></div>
      </article>

      <div v-if="!supplier && !customer && (byCustomer.length || byPackaging.length)" class="grid gap-4 xl:grid-cols-2">
        <article v-for="group in [{ label: '按客户汇总', rows: byCustomer }, { label: '按纸品类型汇总', rows: byPackaging }]" :key="group.label" class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div class="border-b border-slate-100 px-4 py-3"><h2 class="font-bold text-slate-950">{{ group.label }} · 已验收送货</h2></div>
          <table class="w-full text-left text-xs"><thead class="bg-slate-50 text-[10px] font-bold text-slate-500"><tr><th class="px-4 py-2">分类</th><th class="px-4 py-2">行数</th><th class="px-4 py-2">数量</th><th class="px-4 py-2 text-right">金额</th></tr></thead><tbody class="divide-y divide-slate-100">
            <tr v-for="row in group.rows" :key="row.key"><td class="break-words px-4 py-2 font-semibold">{{ row.name }}</td><td class="px-4 py-2 tabular-nums">{{ row.count }}</td><td class="px-4 py-2 tabular-nums">{{ row.quantity }}</td><td class="px-4 py-2 text-right tabular-nums">{{ format(row.amount) }}</td></tr>
          </tbody></table>
        </article>
      </div>
    </template>

    <CartonOrderDetailDialog v-if="sourceRow?.reference" :title="sourceAction(sourceRow) + ' · ' + (sourceRow.document_no || '原凭证')" description="本月对账来源" close-label="关闭原凭证" @close="clearSource" @close-auto-focus="restoreSourceFocus">
      <p v-if="sourceLoading" role="status" class="text-xs text-slate-500">正在读取原送货单…</p>
      <p v-else-if="sourceError" role="alert" class="rounded-lg bg-red-50 p-3 text-xs text-red-700">{{ sourceError }}</p>
      <CartonUnifiedDeliveryNotes v-else-if="delivery" :group="delivery" supplier :viewer-key="viewerKey" />
    </CartonOrderDetailDialog>
  </section>
</template>
