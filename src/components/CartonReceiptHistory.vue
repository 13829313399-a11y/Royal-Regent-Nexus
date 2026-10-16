<script setup lang="ts">
import { ref, shallowRef, watch, onBeforeUnmount } from 'vue'
import type { DateRange } from 'reka-ui'
import DateRangeFilter from './DateRangeFilter.vue'
import { cartonProcurementApi as api, type CartonCustomerResponse, type CartonReceiptResponse, type CartonReceiptSummary } from '@/api/cartonProcurement'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'

const props = defineProps<{ factoryId: string; responsibilityScope: 'OWN' | 'ALL'; customers: CartonCustomerResponse[]; search: string; customer: string; refreshKey: number; canCorrect: boolean }>()
const emit = defineEmits<{ detail: [CartonReceiptResponse]; correct: [CartonReceiptResponse]; register: [CartonReceiptResponse]; clear: []; customer: [string] }>()
const auth = useAuthStore()
const rows = ref<CartonReceiptSummary[]>([]), total = ref(0), page = ref(1), loading = ref(false), error = ref('')
const status = ref(''), dateField = ref('ACCEPTANCE'), sort = ref('DESC')
const dateRange = shallowRef<DateRange>({ start: undefined, end: undefined })
const detailBusy = ref(''), detailErrors = ref<Record<string, string>>({})
let generation = 0, detailGeneration = 0
async function load() {
  const token = ++generation
  detailGeneration++; detailBusy.value = ''; detailErrors.value = {}; rows.value = []; loading.value = true; error.value = ''
  try {
    const customer = props.customers.find(row => row.customer_name === props.customer)?.customer_code ?? ''
    if (props.customer !== '全部客户' && !customer) throw new Error('客户资料尚未读取，请刷新后重试')
    const data = await api.receiptHistory(props.factoryId, { responsibility_scope: props.responsibilityScope, customer_code: customer,
      search: props.search, status_filter: status.value, date_field: dateField.value, date_from: dateRange.value.start?.toString() ?? '', date_to: dateRange.value.end?.toString() ?? '',
      sort: sort.value, limit: 25, offset: (page.value - 1) * 25 })
    if (token !== generation) return
    total.value = data.total; rows.value = data.items
    if (page.value > Math.max(1, Math.ceil(data.total / 25))) page.value = Math.max(1, Math.ceil(data.total / 25))
  } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) loading.value = false }
}
async function open(row: CartonReceiptSummary, action: 'detail' | 'correct' | 'register') {
  const token = ++detailGeneration
  detailBusy.value = row.id; delete detailErrors.value[row.id]
  try {
    const detail = await api.receiptDetail(props.factoryId, row.id, props.responsibilityScope)
    if (token !== detailGeneration) return
    if (action === 'detail') emit('detail', detail)
    else if (action === 'correct') emit('correct', detail)
    else emit('register', detail)
  } catch (cause) { if (token === detailGeneration) detailErrors.value[row.id] = getApiErrorMessage(cause) }
  finally { if (token === detailGeneration) detailBusy.value = '' }
}
watch(() => [props.factoryId, props.responsibilityScope, props.search, props.customer, props.refreshKey, auth.currentUser?.id, auth.authorizationVersion,
  status.value, dateRange.value, dateField.value, sort.value], () => { if (page.value !== 1) page.value = 1; else void load() }, { immediate: true })
watch(page, () => void load())
onBeforeUnmount(() => { generation++; detailGeneration++ })
</script>

<template>
  <article class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
    <div class="flex flex-wrap items-center justify-between gap-3 border-b p-4"><div><h2 class="font-bold">收料历史台账</h2><p class="mt-1 text-xs text-slate-500">先查看送货单摘要，点击明细核对纸品、数量和仓位。</p></div><span class="text-xs">共 {{ total }} 张收料单</span></div>
    <div aria-label="收料历史筛选" class="flex flex-wrap items-center gap-3 border-b bg-slate-50 p-3 text-xs">
      <select :value="customer" aria-label="收料历史客户" class="h-9 rounded-lg border px-3" @change="emit('customer', ($event.target as HTMLSelectElement).value)"><option value="全部客户">全部客户</option><option v-for="item in customers" :key="item.customer_code" :value="item.customer_name">{{ item.customer_name }}</option></select>
      <select v-model="status" aria-label="收料历史状态" class="h-9 rounded-lg border px-3"><option value="">全部状态</option><option value="PENDING_CONFIRMATION">待确认</option><option value="POSTED">已入库</option><option value="REVERSED">已作废 / 冲销</option></select>
      <select v-model="dateField" aria-label="收料历史日期口径" class="h-9 rounded-lg border px-3"><option value="ACCEPTANCE">实际验收日期</option><option value="DELIVERY">送货日期</option></select>
      <DateRangeFilter v-model="dateRange" :label="dateField === 'ACCEPTANCE' ? '收料历史验收日期范围' : '收料历史送货日期范围'" />
      <select v-model="sort" aria-label="收料历史排序" class="h-9 rounded-lg border px-3"><option value="DESC">最新优先</option><option value="ASC">最早优先</option></select>
      <button type="button" class="rounded-lg border px-3 py-2" @click="sort = 'DESC'">恢复默认排序</button><button type="button" class="rounded-lg border px-3 py-2" @click="status = ''; dateRange = { start: undefined, end: undefined }; emit('clear')">清空历史筛选</button><button type="button" :disabled="loading" class="rounded-lg border px-3 py-2" @click="load">刷新历史</button>
    </div>
    <p v-if="error" role="alert" class="p-4 text-xs text-red-700">收料历史读取失败：{{ error }}</p>
    <p v-if="loading" class="p-4 text-xs text-slate-500">正在读取收料历史…</p>
    <div class="overflow-x-auto"><table aria-label="收料历史台账摘要" class="w-full min-w-[950px] text-left text-xs"><thead class="bg-slate-50 text-slate-500"><tr><th class="p-3">送货单号</th><th class="p-3">送货 / 验收日期</th><th class="p-3">客户 / 合同</th><th class="p-3">纸品项数</th><th class="p-3">状态</th><th class="p-3">经手人</th><th class="p-3">操作</th></tr></thead><tbody class="divide-y">
      <tr v-for="row in rows" :key="row.id"><td class="p-3 font-semibold">{{ row.delivery_note_no || row.receipt_no }}</td><td class="p-3">{{ row.delivery_date }}<br>{{ row.acceptance_date || '历史未记录' }}</td><td class="max-w-72 p-3"><div>{{ row.customers }}</div><div class="break-all text-slate-500">{{ row.contracts || '非正式收料' }}</div></td><td class="p-3">{{ row.line_count }} 项</td><td class="p-3">{{ row.status === 'POSTED' ? '已入库' : row.status === 'REVERSED' ? (row.confirmed_at ? '已冲销' : '已作废') : '待确认' }}</td><td class="p-3">{{ row.operator }}</td><td class="p-3"><div class="flex gap-2 whitespace-nowrap">
        <button type="button" :disabled="!!detailBusy" :aria-label="`查看收料单 ${row.receipt_no}`" class="rounded-lg border px-3 py-2 text-teal-700" @click="open(row, 'detail')">{{ detailBusy === row.id ? '读取中…' : '明细' }}</button>
        <button v-if="canCorrect" type="button" :disabled="!!detailBusy" :aria-label="`更正收料单 ${row.receipt_no}`" class="rounded-lg border px-3 py-2" @click="open(row, row.status === 'REVERSED' ? 'register' : 'correct')">{{ row.status === 'REVERSED' ? '重新登记' : row.status === 'POSTED' ? '冲销' : '作废' }}</button>
      </div><p v-if="detailErrors[row.id]" role="alert" class="mt-2 text-red-700">{{ detailErrors[row.id] }}</p></td></tr>
      <tr v-if="!rows.length && !loading && !error"><td colspan="7" class="p-10 text-center text-slate-400">没有符合条件的收料历史</td></tr>
    </tbody></table></div>
    <div class="flex justify-end gap-3 border-t p-3 text-xs"><button type="button" :disabled="loading || page <= 1" @click="page--">上一页</button><span>第 {{ page }} / {{ Math.max(1, Math.ceil(total / 25)) }} 页</span><button type="button" :disabled="loading || page * 25 >= total" @click="page++">下一页</button></div>
  </article>
</template>
