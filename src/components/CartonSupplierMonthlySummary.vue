<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { supplierSettlementApi as api, type SupplierMonthlySummary, type MonthlySettlementLine } from '@/api/cartonSupplierSettlement'
import { getApiErrorMessage } from '@/lib/http'
import { factoryContexts } from '@/data/enterpriseMock'

const props = withDefaults(defineProps<{ factories?: { factory_id: string }[]; search?: string }>(), {
  factories: () => [], search: '',
})
const today = () => new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
const factory = ref(props.factories[0]?.factory_id || '')
const period = ref(today().slice(0, 7))
const currency = ref('CNY')
const data = ref<SupplierMonthlySummary | null>(null)
const busy = ref(false)
const error = ref('')
let generation = 0

async function load() {
  if (!factory.value) { data.value = null; return }
  const token = ++generation, current = factory.value
  busy.value = true; error.value = ''
  try {
    const result = await api.supplierMonthlyWorkspace(current, period.value, currency.value)
    if (token !== generation || current !== factory.value) return
    data.value = result
  } catch (cause) {
    if (token === generation) { data.value = null; error.value = getApiErrorMessage(cause) }
  } finally {
    if (token === generation) busy.value = false
  }
}
onMounted(load)
watch(factory, load)
watch([period, currency], load)
watch(() => props.factories.map(row => row.factory_id).join(','), () => {
  if (!factory.value && props.factories.length) { factory.value = props.factories[0]!.factory_id; return }
  void load()
})

const lines = computed(() => {
  const query = (props.search || '').trim().toLowerCase()
  const rows = data.value?.lines ?? []
  if (!query) return rows
  return rows.filter(line => [line.document_no, line.item_no, line.customer_name, line.contract_no]
    .some(value => (value || '').toLowerCase().includes(query)))
})
const format = (value: string | null) => value === null ? '待核价' : Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const currencyName = (code: string) => ({ CNY: '人民币', HKD: '港币', USD: '美元' } as Record<string, string>)[code] || code
const kindLabel = (kind: MonthlySettlementLine['kind'] | string) => kind === 'RETURN' ? '退货' : kind === 'RETURN_REFUND' ? '退款' : '送货'
const signedQuantity = (row: MonthlySettlementLine) => `${row.kind === 'RECEIPT' ? '' : '−'}${Number(row.quantity).toLocaleString('zh-CN', { maximumFractionDigits: 4 })}${row.unit ? ' ' + row.unit : ''}`
const factoryName = (id: string) => factoryContexts.find(item => item.id === id)?.shortName ?? id
</script>

<template>
  <section class="space-y-4" aria-label="供应商本月对账">
    <div class="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-3 text-xs">
      <label v-if="factories.length > 1" class="space-y-1"><span class="block text-[10px] font-bold text-slate-500">厂区</span><select v-model="factory" aria-label="供应商对账厂区" class="h-9 rounded-lg border px-3"><option v-for="item in factories" :key="item.factory_id" :value="item.factory_id">{{ factoryName(item.factory_id) }}</option></select></label>
      <label class="space-y-1"><span class="block text-[10px] font-bold text-slate-500">对账月份</span><input v-model="period" aria-label="供应商对账月份" type="month" :disabled="busy" class="h-9 rounded-lg border px-3"></label>
      <label class="space-y-1"><span class="block text-[10px] font-bold text-slate-500">币种</span><select v-model="currency" aria-label="供应商对账币种" :disabled="busy" class="h-9 rounded-lg border px-3"><option value="CNY">人民币</option><option value="HKD">港币</option><option value="USD">美元</option></select></label>
      <button type="button" :disabled="busy" class="h-9 rounded-lg border px-4 font-semibold disabled:opacity-40" @click="load">刷新</button>
      <span class="ml-auto rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-bold text-slate-600">只读对账</span>
    </div>

    <p v-if="error" role="alert" class="rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-700">{{ error }}</p>
    <p class="rounded-xl border border-slate-200 bg-white p-3 text-[11px] text-slate-600">本页仅供核对你与本厂的本月送货、退货和应结金额；无需在系统内确认或提异议，月结按原流程办理。</p>

    <p v-if="busy && !data" class="rounded-xl border bg-white p-6 text-center text-xs text-slate-500">正在读取本月对账…</p>

    <template v-else-if="data">
      <div class="grid gap-3 sm:grid-cols-3">
        <article class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div class="text-[11px] text-slate-500">本月已验收送货</div><div class="mt-2 text-xl font-bold tabular-nums">{{ format(data.totals.inbound) }} <span class="text-xs font-medium text-slate-400">{{ currencyName(currency) }}</span></div><div class="mt-1 text-[10px] text-slate-500">{{ data.totals.documents }} 张送货单 · {{ data.totals.receipt_lines }} 行</div></article>
        <article class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div class="text-[11px] text-slate-500">退货贷项</div><div class="mt-2 text-xl font-bold tabular-nums text-rose-700">{{ format(data.totals.returns) }}</div><div class="mt-1 text-[10px] text-slate-500">{{ data.totals.return_lines }} 笔</div></article>
        <article class="rounded-xl border border-teal-200 bg-teal-50/40 p-4 shadow-sm"><div class="text-[11px] font-bold text-teal-800">本月应结</div><div class="mt-2 text-2xl font-bold tabular-nums text-teal-900">{{ format(data.totals.net) }}</div><div class="mt-1 text-[10px] text-teal-700">送货金额 − 退货贷项</div></article>
      </div>


      <article class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm" aria-label="供应商本月对账明细">
        <div class="border-b border-slate-100 px-4 py-3"><h2 class="font-bold text-slate-950">本月明细</h2><p class="mt-1 text-[11px] text-slate-500">按供应商送货单原价汇总；仅供核对，不需要在系统内确认。</p></div>
        <div class="overflow-x-auto carton-table-wrap"><table class="w-full min-w-[900px] text-left text-xs">
          <thead class="bg-slate-50 text-[10px] font-bold text-slate-500"><tr><th class="px-3 py-2">类型</th><th class="px-3 py-2">单号</th><th class="px-3 py-2">验收/交接日</th><th class="px-3 py-2">客户</th><th class="px-3 py-2">货号 / 纸品</th><th class="px-3 py-2 text-right">数量</th><th class="px-3 py-2 text-right">单价</th><th class="px-3 py-2 text-right">金额</th></tr></thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-for="row in lines" :key="row.source_key" :class="row.kind === 'RETURN' ? 'bg-rose-50/40' : ''">
              <td class="px-3 py-2"><span class="rounded px-1.5 py-0.5 text-[10px] font-bold" :class="row.kind === 'RECEIPT' ? 'bg-teal-50 text-teal-800' : 'bg-rose-50 text-rose-700'">{{ kindLabel(row.kind) }}</span></td>
              <td class="px-3 py-2 font-mono">{{ row.document_no || '无单号' }}</td>
              <td class="px-3 py-2">{{ row.acceptance_date || '待核实' }}</td>
              <td class="px-3 py-2">{{ row.customer_name || '—' }}</td>
              <td class="px-3 py-2">{{ row.item_no || '—' }}<span class="text-slate-400"> · {{ row.packaging_type || '纸品待补' }}</span></td>
              <td class="px-3 py-2 text-right tabular-nums">{{ signedQuantity(row) }}</td>
              <td class="px-3 py-2 text-right tabular-nums">{{ row.unit_price === null ? '—' : format(row.unit_price) }}</td>
              <td class="px-3 py-2 text-right font-semibold tabular-nums">{{ format(row.amount) }}</td>
            </tr>
            <tr v-if="!lines.length"><td colspan="8" class="px-4 py-8 text-center text-slate-400">本月没有已验收送货或退货</td></tr>
          </tbody>
        </table></div>
      </article>
    </template>
  </section>
</template>
