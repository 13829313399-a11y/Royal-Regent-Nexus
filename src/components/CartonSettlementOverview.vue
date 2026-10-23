<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import CartonFilterBar from '@/components/CartonFilterBar.vue'
import { supplierSettlementApi as api, type MonthlySettlement, type MonthlySettlementLine } from '@/api/cartonSupplierSettlement'
import { getApiErrorMessage } from '@/lib/http'

const props = defineProps<{ factoryId: string; viewerKey?: string }>()

const today = () => new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
const period = ref(today().slice(0, 7))
const currency = ref('CNY')
const data = ref<MonthlySettlement | null>(null)
const busy = ref(false)
const error = ref('')
let generation = 0
let disposed = false

async function load() {
  const token = ++generation
  const query = { factory: props.factoryId, period: period.value, currency: currency.value, viewer: props.viewerKey }
  const current = () => !disposed && token === generation && query.factory === props.factoryId
    && query.period === period.value && query.currency === currency.value && query.viewer === props.viewerKey
  data.value = null; error.value = ''; busy.value = false
  if (!query.factory) { error.value = '请选择厂区后查看本月对账。'; return }
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(query.period)) { error.value = '请选择有效的对账月份。'; return }
  busy.value = true
  try {
    const result = await api.monthlyWorkspace(query.factory, query.period, query.currency)
    if (!current()) return
    if (result.factory_id !== query.factory || result.period !== query.period || result.currency !== query.currency) {
      throw new Error('返回的对账数据与当前厂区、月份或币种不一致，请刷新重试。')
    }
    data.value = result
  } catch (cause) {
    if (current()) error.value = getApiErrorMessage(cause)
  } finally { if (current()) busy.value = false }
}
watch([() => props.factoryId, () => props.viewerKey, period, currency], () => { void load() }, { immediate: true, flush: 'sync' })
onBeforeUnmount(() => { disposed = true; generation++ })

const lines = computed(() => data.value?.lines ?? [])
const receipts = computed(() => lines.value.filter(row => row.kind === 'RECEIPT'))
const returns = computed(() => lines.value.filter(row => row.kind === 'RETURN'))
const refunds = computed(() => lines.value.filter(row => row.kind === 'RETURN_REFUND'))
const blockers = computed(() => data.value?.blockers ?? [])
const format = (value: string | null) => value === null ? '待核价' : Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const currencyName = (code: string) => ({ CNY: '人民币', HKD: '港币', USD: '美元' } as Record<string, string>)[code] || code
const lineAmount = (row: MonthlySettlementLine) => row.amount === null ? '待核价' : format(row.amount)
const kindLabel = (kind: string) => kind === 'RETURN' ? '退货' : kind === 'RETURN_REFUND' ? '退款' : '送货'
const signedQuantity = (row: MonthlySettlementLine) => `${kindLabel(row.kind) === '送货' ? '' : '−'}${Number(row.quantity).toLocaleString('zh-CN', { maximumFractionDigits: 4 })}${row.unit ? ' ' + row.unit : ''}`

function quantityByUnit(rows: MonthlySettlementLine[]) {
  const byUnit = new Map<string, number>()
  for (const row of rows) byUnit.set(row.unit || '', (byUnit.get(row.unit || '') ?? 0) + Number(row.quantity || 0))
  return [...byUnit].filter(([, value]) => value !== 0).map(([unit, value]) => `${value.toLocaleString('zh-CN', { maximumFractionDigits: 4 })}${unit ? ' ' + unit : ''}`).join(' / ') || '0'
}
const byCustomer = computed(() => {
  const groups = new Map<string, MonthlySettlementLine[]>()
  for (const row of receipts.value) groups.set(row.customer_name || '未填写客户', [...(groups.get(row.customer_name || '未填写客户') ?? []), row])
  return [...groups].map(([name, rows]) => ({ name, rows, quantity: quantityByUnit(rows),
    amount: rows.every(row => row.amount !== null) ? format(String(rows.reduce((total, row) => total + Number(row.amount), 0))) : '待核价' }))
    .sort((left, right) => Number(right.rows.reduce((total, row) => total + Number(row.amount ?? 0), 0)) - Number(left.rows.reduce((total, row) => total + Number(row.amount ?? 0), 0))).slice(0, 8)
})
const byPackaging = computed(() => {
  const groups = new Map<string, MonthlySettlementLine[]>()
  for (const row of receipts.value) groups.set(row.packaging_type || '纸品类型待补', [...(groups.get(row.packaging_type || '纸品类型待补') ?? []), row])
  return [...groups].map(([name, rows]) => ({ name, rows, quantity: quantityByUnit(rows),
    amount: rows.every(row => row.amount !== null) ? format(String(rows.reduce((total, row) => total + Number(row.amount), 0))) : '待核价' }))
    .sort((left, right) => Number(right.rows.reduce((total, row) => total + Number(row.amount ?? 0), 0)) - Number(left.rows.reduce((total, row) => total + Number(row.amount ?? 0), 0))).slice(0, 8)
})
</script>

<template>
  <section class="space-y-4" aria-label="本月对账">
    <CartonFilterBar label="本月对账筛选">
      <label>对账月份<input v-model="period" aria-label="本月对账月份" type="month" class="mt-1 block h-9 rounded-lg border px-3"></label>
      <label>原账币种<select v-model="currency" aria-label="本月对账币种" class="mt-1 block h-9 rounded-lg border px-3"><option value="CNY">人民币</option><option value="HKD">港币</option><option value="USD">美元</option></select></label>
      <template #actions>
        <button type="button" :disabled="busy" class="h-9 rounded-lg border px-4 text-xs font-semibold disabled:opacity-40" @click="load">刷新</button>
        <span class="pb-2 text-[10px] text-slate-500">只读对账，不提交、不锁定，不作为付款依据</span>
      </template>
      <template #footer><span class="pb-2 text-slate-500">{{ data?.supplier_name || (busy ? '读取供应商中' : '暂无对账数据') }} · {{ data?.period || period }} · {{ currencyName(data?.currency || currency) }} · <span class="rounded bg-slate-100 px-1.5 py-0.5 font-bold text-slate-600">只读</span></span></template>
    </CartonFilterBar>

    <p v-if="error" role="alert" class="rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-700">{{ error }}</p>
    <p class="rounded-xl border border-slate-200 bg-white p-3 text-[11px] text-slate-600">本页仅供核对本月送货、退货和应结金额；不提交、不确认、不锁定，也不生成应付。月结仍按原流程办理。</p>

    <p v-if="busy" role="status" class="rounded-xl border bg-white p-6 text-center text-xs text-slate-500">正在汇总 {{ period }} · {{ currencyName(currency) }} 的收料与退货…</p>

    <template v-else-if="data">
      <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <article class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div class="text-[11px] text-slate-500">本月已验收送货</div><div class="mt-2 text-xl font-bold tabular-nums">{{ format(data.totals.inbound) }} <span class="text-xs font-medium text-slate-400">{{ currencyName(data.currency) }}</span></div><div class="mt-1 text-[10px] text-slate-500">{{ data.totals.documents }} 张送货单 · {{ data.totals.receipt_lines }} 行</div></article>
        <article class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div class="text-[11px] text-slate-500">退货贷项</div><div class="mt-2 text-xl font-bold tabular-nums text-rose-700">{{ format(data.totals.returns) }}</div><div class="mt-1 text-[10px] text-slate-500">{{ data.totals.return_lines }} 笔{{ data.totals.refund_lines ? ` · 退款 ${format(data.totals.refunds)}` : '' }}</div></article>
        <article class="rounded-xl border border-teal-200 bg-teal-50/40 p-4 shadow-sm"><div class="text-[11px] font-bold text-teal-800">本月应结</div><div class="mt-2 text-2xl font-bold tabular-nums text-teal-900">{{ format(data.totals.net) }}</div><div class="mt-1 text-[10px] text-teal-700">送货金额 − 退货贷项 ＋ 已核实退款</div></article>
        <article class="rounded-xl border p-4 shadow-sm" :class="blockers.length ? 'border-amber-200 bg-amber-50' : 'border-slate-200 bg-white'"><div class="text-[11px]" :class="blockers.length ? 'font-bold text-amber-800' : 'text-slate-500'">待处理事项</div><div class="mt-2 text-xl font-bold tabular-nums" :class="blockers.length ? 'text-amber-900' : 'text-slate-900'">{{ blockers.length }}</div><div class="mt-1 text-[10px]" :class="blockers.length ? 'text-amber-700' : 'text-slate-500'">{{ blockers.length ? '请核对，暂不影响旧月结流程' : '本月没有发现明显异常' }}</div></article>
      </div>

      <article class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm" aria-label="本月对账待处理清单">
        <div class="border-b border-slate-100 px-4 py-3"><h2 class="font-bold text-slate-950">待处理清单</h2><p class="mt-1 text-[11px] text-slate-500">下面这些只作提示；供应商送货单金额会直接汇总。</p></div>
        <ul v-if="blockers.length" class="divide-y divide-slate-100 text-xs"><li v-for="(issue, index) in blockers" :key="index" class="px-4 py-2 text-amber-800">· {{ issue }}</li></ul>
        <p v-else class="px-4 py-6 text-center text-xs text-slate-500">没有待处理事项。</p>
      </article>

      <article class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm" aria-label="本月对账明细">
        <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3"><div><h2 class="font-bold text-slate-950">本月明细</h2><p class="mt-1 text-[11px] text-slate-500">送货单金额按供应商价格；退货显示为负数。缺价或来源异常的行会同时出现在待处理清单。</p></div><span class="text-[11px] text-slate-500">{{ receipts.length }} 行送货 · {{ returns.length }} 笔退货 · {{ refunds.length }} 笔退款</span></div>
        <div class="overflow-x-auto carton-table-wrap"><table class="w-full min-w-[1100px] text-left text-xs" aria-label="本月对账明细表">
          <thead class="bg-slate-50 text-[10px] font-bold text-slate-500"><tr><th class="px-3 py-2">类型</th><th class="px-3 py-2">单号</th><th class="px-3 py-2">验收/交接日</th><th class="px-3 py-2">客户</th><th class="px-3 py-2">货号 / 纸品</th><th class="px-3 py-2 text-right">数量</th><th class="px-3 py-2 text-right">单价</th><th class="px-3 py-2 text-right">金额</th><th class="px-3 py-2">说明</th></tr></thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-for="row in lines" :key="row.source_key" :class="row.kind === 'RETURN' ? 'bg-rose-50/40' : ''">
              <td class="px-3 py-2"><span class="rounded px-1.5 py-0.5 text-[10px] font-bold" :class="row.kind === 'RECEIPT' ? 'bg-teal-50 text-teal-800' : 'bg-rose-50 text-rose-700'">{{ kindLabel(row.kind) }}</span></td>
              <td class="px-3 py-2 font-mono">{{ row.document_no || '无单号' }}</td>
              <td class="px-3 py-2">{{ row.acceptance_date || '待核实' }}</td>
              <td class="px-3 py-2">{{ row.customer_name || '—' }}</td>
              <td class="px-3 py-2">{{ row.item_no || '—' }}<span class="text-slate-400"> · {{ row.packaging_type || '纸品待补' }}</span></td>
              <td class="px-3 py-2 text-right tabular-nums">{{ signedQuantity(row) }}</td>
              <td class="px-3 py-2 text-right tabular-nums">{{ row.unit_price === null ? '—' : format(row.unit_price) }}</td>
              <td class="px-3 py-2 text-right font-semibold tabular-nums">{{ lineAmount(row) }}</td>
              <td class="px-3 py-2 text-[10px] text-amber-800"><span v-if="row.price_basis === 'SUPPLIER_ORIGINAL'" class="mr-1 rounded bg-teal-50 px-1.5 py-0.5 text-teal-800">按供应商原单价</span>{{ row.issues.join('；') }}</td>
            </tr>
            <tr v-if="!lines.length"><td colspan="9" class="px-4 py-8 text-center text-slate-400">本月没有已验收送货或退货</td></tr>
          </tbody>
        </table></div>
      </article>

      <div class="grid gap-4 xl:grid-cols-2">
        <article class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"><div class="border-b border-slate-100 px-4 py-3"><h2 class="font-bold text-slate-950">按客户汇总</h2><p class="mt-1 text-[11px] text-slate-500">回答“这个月买了什么货、给哪个客户用”。</p></div>
          <table class="w-full text-left text-xs"><thead class="bg-slate-50 text-[10px] font-bold text-slate-500"><tr><th class="px-4 py-2">客户</th><th class="px-4 py-2">行数</th><th class="px-4 py-2">数量</th><th class="px-4 py-2 text-right">金额</th></tr></thead><tbody class="divide-y divide-slate-100">
            <tr v-for="row in byCustomer" :key="row.name"><td class="px-4 py-2 font-semibold">{{ row.name }}</td><td class="px-4 py-2 tabular-nums">{{ row.rows.length }}</td><td class="px-4 py-2 tabular-nums">{{ row.quantity }}</td><td class="px-4 py-2 text-right tabular-nums">{{ row.amount }}</td></tr>
            <tr v-if="!byCustomer.length"><td colspan="4" class="px-4 py-6 text-center text-slate-400">本月没有已验收送货</td></tr>
          </tbody></table>
        </article>
        <article class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"><div class="border-b border-slate-100 px-4 py-3"><h2 class="font-bold text-slate-950">按纸品类型汇总</h2><p class="mt-1 text-[11px] text-slate-500">回答“主要买了哪些纸箱/纸品”。</p></div>
          <table class="w-full text-left text-xs"><thead class="bg-slate-50 text-[10px] font-bold text-slate-500"><tr><th class="px-4 py-2">纸品类型</th><th class="px-4 py-2">行数</th><th class="px-4 py-2">数量</th><th class="px-4 py-2 text-right">金额</th></tr></thead><tbody class="divide-y divide-slate-100">
            <tr v-for="row in byPackaging" :key="row.name"><td class="px-4 py-2 font-semibold">{{ row.name }}</td><td class="px-4 py-2 tabular-nums">{{ row.rows.length }}</td><td class="px-4 py-2 tabular-nums">{{ row.quantity }}</td><td class="px-4 py-2 text-right tabular-nums">{{ row.amount }}</td></tr>
            <tr v-if="!byPackaging.length"><td colspan="4" class="px-4 py-6 text-center text-slate-400">本月没有已验收送货</td></tr>
          </tbody></table>
        </article>
      </div>
    </template>
  </section>
</template>
