<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  customerOrderScheduleApi,
  type CustomerOrderScheduleColumn,
  type CustomerOrderScheduleResult,
  type CustomerOrderScheduleSection,
} from '@/api/customerOrderSchedule'
import type { CustomerOrderLedgerLine } from '@/api/customerOrderLedger'
import type { FeedbackContext } from '@/api/moduleFeedback'
import { getApiErrorMessage } from '@/lib/http'
import CustomerOrderLedger from './CustomerOrderLedger.vue'

const props = defineProps<{ factoryId: string; factoryName: string }>()
const emit = defineEmits<{ import: []; feedback: [context: FeedbackContext] }>()

type SectionKey = 'unshipped' | 'shipped' | 'cancelled'
type AppliedFilters = { customerCode: string; q: string; dateFrom: string; dateTo: string }

const customers = ref<Array<{ code: string; name: string }>>([])
const customersLoading = ref(false)
const loading = ref(false)
const message = ref('')
const customerMessage = ref('')
const draft = ref<AppliedFilters>({ customerCode: '', q: '', dateFrom: '', dateTo: '' })
const applied = ref<AppliedFilters | null>(null)
const schedule = ref<CustomerOrderScheduleResult | null>(null)
const pages = ref<Record<SectionKey, number>>({ unshipped: 1, shipped: 1, cancelled: 1 })
const visibleColumnKeys = ref<string[]>([])
const selectedLineId = ref('')
let customersRequestSequence = 0
let scheduleRequestSequence = 0

const customerName = computed(() => schedule.value?.customer_name
  || customers.value.find((item) => item.code === applied.value?.customerCode)?.name
  || '')
const visibleColumns = computed(() => (schedule.value?.columns ?? [])
  .filter((column) => visibleColumnKeys.value.includes(column.key)))

function emptySection(): CustomerOrderScheduleSection {
  return { items: [], total: 0, page: 1, page_size: 50 }
}

function section(key: SectionKey) {
  return schedule.value?.sections[key] ?? emptySection()
}

function pageCount(key: SectionKey) {
  const current = section(key)
  return Math.max(1, Math.ceil(current.total / current.page_size))
}

function resetForFactory() {
  customersRequestSequence += 1
  scheduleRequestSequence += 1
  customers.value = []
  customerMessage.value = ''
  loading.value = false
  message.value = ''
  draft.value = { customerCode: '', q: '', dateFrom: '', dateTo: '' }
  applied.value = null
  schedule.value = null
  pages.value = { unshipped: 1, shipped: 1, cancelled: 1 }
  visibleColumnKeys.value = []
  selectedLineId.value = ''
}

function resetForCustomer() {
  scheduleRequestSequence += 1
  loading.value = false
  message.value = ''
  applied.value = null
  schedule.value = null
  pages.value = { unshipped: 1, shipped: 1, cancelled: 1 }
  visibleColumnKeys.value = []
  selectedLineId.value = ''
}

async function loadCustomers() {
  const token = ++customersRequestSequence
  const factoryId = props.factoryId
  if (!factoryId) return
  customersLoading.value = true
  customerMessage.value = ''
  try {
    const response = await customerOrderScheduleApi.customers(factoryId)
    if (token !== customersRequestSequence || factoryId !== props.factoryId) return
    if (response.factory_id !== factoryId) {
      customers.value = []
      customerMessage.value = '客户列表与当前厂区不一致，请刷新后重试。'
      return
    }
    customers.value = response.items
  } catch (error) {
    if (token !== customersRequestSequence || factoryId !== props.factoryId) return
    customers.value = []
    customerMessage.value = `无法读取客户列表：${getApiErrorMessage(error)}`
  } finally {
    if (token === customersRequestSequence) customersLoading.value = false
  }
}

function scheduleOptions(filters: AppliedFilters) {
  return {
    customerCode: filters.customerCode,
    q: filters.q,
    dateFrom: filters.dateFrom,
    dateTo: filters.dateTo,
    unshippedPage: pages.value.unshipped,
    shippedPage: pages.value.shipped,
    cancelledPage: pages.value.cancelled,
    pageSize: 50,
  }
}

function initialiseColumns(columns: CustomerOrderScheduleColumn[]) {
  visibleColumnKeys.value = columns.slice(0, 4).map((column) => column.key)
}

async function loadSchedule(resetColumns = false, keepDetail = false) {
  if (!applied.value?.customerCode) return
  const token = ++scheduleRequestSequence
  const factoryId = props.factoryId
  const filters = { ...applied.value }
  loading.value = true
  message.value = ''
  schedule.value = null
  if (!keepDetail) selectedLineId.value = ''
  try {
    const response = await customerOrderScheduleApi.get(factoryId, scheduleOptions(filters))
    if (token !== scheduleRequestSequence || factoryId !== props.factoryId) return
    if (response.factory_id !== factoryId || response.customer_code !== filters.customerCode
      || Object.values(response.sections).some((group) => group.items.some((line) => line.factory_id !== factoryId || line.customer_code !== filters.customerCode))) {
      message.value = '返回数据与当前厂区或客户不一致，未显示该结果。'
      return
    }
    schedule.value = response
    pages.value = {
      unshipped: response.sections.unshipped.page,
      shipped: response.sections.shipped.page,
      cancelled: response.sections.cancelled.page,
    }
    if (resetColumns) initialiseColumns(response.columns)
    else {
      const allowed = new Set(response.columns.map((column) => column.key))
      visibleColumnKeys.value = visibleColumnKeys.value.filter((key) => allowed.has(key))
    }
  } catch (error) {
    if (token !== scheduleRequestSequence || factoryId !== props.factoryId) return
    message.value = `无法读取客户排期：${getApiErrorMessage(error)}`
  } finally {
    if (token === scheduleRequestSequence) loading.value = false
  }
}

function applyFilters() {
  if (!draft.value.customerCode) {
    schedule.value = null
    applied.value = null
    message.value = '请先选择客户，再查询排期。'
    return
  }
  pages.value = { unshipped: 1, shipped: 1, cancelled: 1 }
  applied.value = { ...draft.value, q: draft.value.q.trim() }
  void loadSchedule(true)
}

function goToPage(key: SectionKey, nextPage: number) {
  if (!applied.value || nextPage < 1 || nextPage > pageCount(key) || nextPage === pages.value[key]) return
  pages.value = { ...pages.value, [key]: nextPage }
  void loadSchedule()
}

function refreshSchedule() {
  if (!applied.value) return
  void loadSchedule(false, true)
}

function displayValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? '是' : '否'
  return ['string', 'number'].includes(typeof value) ? String(value) : '—'
}

function mappedValue(line: CustomerOrderLedgerLine, column: CustomerOrderScheduleColumn) {
  return displayValue(line.data[column.key])
}

function stringField(line: CustomerOrderLedgerLine, keys: string[]) {
  for (const key of keys) {
    const value = line.data[key]
    if (typeof value === 'string' || typeof value === 'number') return String(value)
  }
  return '—'
}

function statusLabel(line: CustomerOrderLedgerLine) {
  return line.status === 'cancelled' ? '已取消' : '有效'
}

function dispatchLabel(line: CustomerOrderLedgerLine) {
  return ({ unsent: '未发送', sent: '已发送', changed: '有变更' } as Record<string, string>)[line.dispatch_status] ?? line.dispatch_status
}

function sectionTitle(key: SectionKey) {
  return ({ unshipped: '未走货订单', shipped: '已走货订单', cancelled: '已取消订单' } as Record<SectionKey, string>)[key]
}

function selectLine(line: CustomerOrderLedgerLine) {
  selectedLineId.value = line.id
}

watch(() => props.factoryId, () => {
  resetForFactory()
  void loadCustomers()
}, { immediate: true })
</script>

<template>
  <section class="customer-schedule" data-testid="customer-order-schedule">
    <header class="customer-schedule__header">
      <div>
        <p class="customer-schedule__eyebrow">客户订单中心</p>
        <h2>{{ factoryName }}客户排期</h2>
        <p>选择客户后查看已保存订单。未走货、已走货和已取消订单分开列示，数量汇总按订单只计算一次。</p>
      </div>
      <button class="customer-schedule__button customer-schedule__button--primary" type="button" @click="emit('import')">导入客户订单</button>
    </header>

    <form class="customer-schedule__filters" @submit.prevent="applyFilters">
      <label>客户
        <select v-model="draft.customerCode" :disabled="customersLoading" @change="resetForCustomer">
          <option value="">请选择客户</option>
          <option v-for="customer in customers" :key="customer.code" :value="customer.code">{{ customer.name }}（{{ customer.code }}）</option>
        </select>
      </label>
      <label>订单号或货号<input v-model="draft.q" type="search" placeholder="输入后点击查询"></label>
      <label>交期从<input v-model="draft.dateFrom" type="date"></label>
      <label>交期至<input v-model="draft.dateTo" type="date"></label>
      <button class="customer-schedule__button" type="submit" :disabled="loading">{{ loading ? '查询中…' : '查询' }}</button>
    </form>
    <p v-if="customerMessage" class="customer-schedule__message">{{ customerMessage }}</p>
    <p v-if="message" class="customer-schedule__message">{{ message }}</p>

    <template v-if="schedule">
      <section class="customer-schedule__summary" aria-label="订单汇总">
        <div><span>客户</span><strong>{{ customerName }}</strong></div>
        <div><span>订单数</span><strong>{{ schedule.summary.order_count }}</strong></div>
        <div><span>订单数量</span><strong>{{ schedule.summary.ordered_quantity }}</strong></div>
        <div><span>已走货</span><strong>{{ schedule.summary.shipped_quantity }}</strong></div>
        <div><span>未走货</span><strong>{{ schedule.summary.remaining_quantity }}</strong></div>
        <div><span>已取消</span><strong>{{ schedule.summary.cancelled_count }}</strong></div>
      </section>
      <p v-if="schedule.summary.unknown_quantity_count" class="customer-schedule__unknown">有 {{ schedule.summary.unknown_quantity_count }} 条订单数量无法汇总，请在订单详情中核对。</p>

      <details v-if="schedule.columns.length" class="customer-schedule__columns">
        <summary>选择补充显示字段（默认显示前 4 项）</summary>
        <label v-for="column in schedule.columns" :key="column.key"><input v-model="visibleColumnKeys" type="checkbox" :value="column.key"> {{ column.label }}</label>
      </details>

      <section v-for="key in (['unshipped', 'shipped'] as SectionKey[])" :key="key" class="customer-schedule__section">
        <h3>{{ sectionTitle(key) }} <small>{{ section(key).total }} 条</small></h3>
        <p v-if="key === 'unshipped'" class="customer-schedule__note">部分走货的订单仍会在这里显示剩余数量，也会出现在已走货订单中；上方汇总不会重复计算。</p>
        <div class="customer-schedule__table-wrap">
          <table>
            <thead><tr><th class="customer-schedule__sticky">参考号</th><th>合同号</th><th>客户 P/O</th><th>产品编号</th><th>中文名称</th><th>英文名称</th><th>订单数量</th><th>客户要求交期</th><th>已走货</th><th>未走货</th><th>状态</th><th>发送</th><th>版本</th><th v-for="column in visibleColumns" :key="column.key">{{ column.label }}</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="line in section(key).items" :key="line.id">
                <td class="customer-schedule__sticky customer-schedule__reference">{{ line.reference_no }}</td><td>{{ stringField(line, ['contract_no']) }}</td><td>{{ stringField(line, ['po_no', 'customer_po']) }}</td><td>{{ line.product_no || '—' }}</td><td>{{ stringField(line, ['product_name_zh']) }}</td><td>{{ stringField(line, ['product_name_en']) }}</td><td>{{ line.quantity }}</td><td>{{ stringField(line, ['requested_ship_date', 'ship_date']) }}</td><td>{{ line.shipped_quantity }}</td><td>{{ line.remaining_quantity }}</td><td>{{ statusLabel(line) }}</td><td>{{ dispatchLabel(line) }}</td><td>V{{ line.version }}</td><td v-for="column in visibleColumns" :key="column.key">{{ mappedValue(line, column) }}</td><td><button class="customer-schedule__link" type="button" @click="selectLine(line)">详情</button></td>
              </tr>
              <tr v-if="section(key).items.length === 0"><td :colspan="14 + visibleColumns.length">暂无符合条件的订单。</td></tr>
            </tbody>
          </table>
        </div>
        <footer class="customer-schedule__pagination"><span>第 {{ section(key).page }} / {{ pageCount(key) }} 页，共 {{ section(key).total }} 条</span><button class="customer-schedule__button" type="button" :disabled="loading || pages[key] <= 1" @click="goToPage(key, pages[key] - 1)">上一页</button><button class="customer-schedule__button" type="button" :disabled="loading || pages[key] >= pageCount(key)" @click="goToPage(key, pages[key] + 1)">下一页</button></footer>
      </section>

      <details class="customer-schedule__cancelled">
        <summary>{{ sectionTitle('cancelled') }}（{{ section('cancelled').total }} 条）</summary>
        <p>已取消订单的未走货数量为 0。</p>
        <div class="customer-schedule__table-wrap">
          <table><thead><tr><th class="customer-schedule__sticky">参考号</th><th>合同号</th><th>客户 P/O</th><th>产品编号</th><th>中文名称</th><th>英文名称</th><th>订单数量</th><th>客户要求交期</th><th>已走货</th><th>未走货</th><th>状态</th><th>发送</th><th>版本</th><th v-for="column in visibleColumns" :key="column.key">{{ column.label }}</th><th>操作</th></tr></thead><tbody><tr v-for="line in section('cancelled').items" :key="line.id"><td class="customer-schedule__sticky customer-schedule__reference">{{ line.reference_no }}</td><td>{{ stringField(line, ['contract_no']) }}</td><td>{{ stringField(line, ['po_no', 'customer_po']) }}</td><td>{{ line.product_no || '—' }}</td><td>{{ stringField(line, ['product_name_zh']) }}</td><td>{{ stringField(line, ['product_name_en']) }}</td><td>{{ line.quantity }}</td><td>{{ stringField(line, ['requested_ship_date', 'ship_date']) }}</td><td>{{ line.shipped_quantity }}</td><td>0</td><td>已取消</td><td>{{ dispatchLabel(line) }}</td><td>V{{ line.version }}</td><td v-for="column in visibleColumns" :key="column.key">{{ mappedValue(line, column) }}</td><td><button class="customer-schedule__link" type="button" @click="selectLine(line)">详情</button></td></tr><tr v-if="section('cancelled').items.length === 0"><td :colspan="14 + visibleColumns.length">暂无已取消订单。</td></tr></tbody></table>
        </div>
        <footer class="customer-schedule__pagination"><span>第 {{ section('cancelled').page }} / {{ pageCount('cancelled') }} 页，共 {{ section('cancelled').total }} 条</span><button class="customer-schedule__button" type="button" :disabled="loading || pages.cancelled <= 1" @click="goToPage('cancelled', pages.cancelled - 1)">上一页</button><button class="customer-schedule__button" type="button" :disabled="loading || pages.cancelled >= pageCount('cancelled')" @click="goToPage('cancelled', pages.cancelled + 1)">下一页</button></footer>
      </details>
    </template>

    <CustomerOrderLedger v-if="selectedLineId" :factory-id="factoryId" :factory-name="factoryName" detail-only :focus-line-id="selectedLineId" @changed="refreshSchedule" @close-detail="selectedLineId = ''" @feedback="emit('feedback', $event)" />
  </section>
</template>

<style scoped>
.customer-schedule{color:#191b23}.customer-schedule__header{display:flex;justify-content:space-between;gap:18px;align-items:start;margin-bottom:18px}.customer-schedule__header h2,.customer-schedule__header p,.customer-schedule h3{margin:0}.customer-schedule__header h2{margin-top:4px;font-size:28px}.customer-schedule__header>div>p:last-child,.customer-schedule__note,.customer-schedule__cancelled>p{color:#596070;font-size:13px;line-height:1.5}.customer-schedule__eyebrow{color:#003d9b;font-size:11px!important;font-weight:800;letter-spacing:.08em}.customer-schedule__filters{display:flex;flex-wrap:wrap;gap:10px;align-items:end;margin-bottom:10px}.customer-schedule__filters label{display:grid;gap:4px;color:#434654;font-size:12px;font-weight:700}.customer-schedule__filters input,.customer-schedule__filters select{min-width:150px;border:1px solid #c3c6d6;border-radius:6px;padding:8px;font:inherit}.customer-schedule__button{border:1px solid #c3c6d6;border-radius:6px;background:#fff;padding:8px 12px;color:#303440;font-weight:800}.customer-schedule__button:disabled{cursor:not-allowed;opacity:.55}.customer-schedule__button--primary{border-color:#003d9b;background:#003d9b;color:#fff}.customer-schedule__message{margin:8px 0;color:#93000a}.customer-schedule__summary{display:grid;grid-template-columns:repeat(6,minmax(110px,1fr));gap:10px;margin:18px 0}.customer-schedule__summary div{display:grid;gap:4px;padding:12px;border:1px solid #dce0eb;border-radius:8px;background:#fff}.customer-schedule__summary span{color:#596070;font-size:12px}.customer-schedule__summary strong{font-size:17px}.customer-schedule__unknown{margin:0 0 12px;border-left:3px solid #a86500;background:#fff3dc;padding:9px;color:#6b3d00;font-size:13px}.customer-schedule__columns{margin:0 0 16px;border:1px solid #d9dbe5;border-radius:7px;padding:10px;background:#fafaff}.customer-schedule__columns summary{cursor:pointer;color:#003d9b;font-size:13px;font-weight:800}.customer-schedule__columns label{display:inline-flex;gap:4px;margin:9px 12px 0 0;font-size:12px}.customer-schedule__section,.customer-schedule__cancelled{margin-top:20px}.customer-schedule__section h3,.customer-schedule__cancelled summary{font-size:17px}.customer-schedule__section h3 small{color:#596070;font-size:12px;font-weight:400}.customer-schedule__table-wrap{overflow:auto;margin-top:10px;border:1px solid #cfd2df;border-radius:8px;background:#fff}.customer-schedule table{width:100%;min-width:1500px;border-collapse:separate;border-spacing:0;font-size:12px}.customer-schedule th,.customer-schedule td{padding:10px;border-bottom:1px solid #e6e7ee;text-align:left;white-space:nowrap;background:#fff}.customer-schedule th{background:#f3f3fd;color:#434654}.customer-schedule__sticky{position:sticky;left:0;z-index:1;box-shadow:1px 0 0 #d9dbe5}.customer-schedule th.customer-schedule__sticky{z-index:2;background:#f3f3fd}.customer-schedule__reference{font-family:ui-monospace,Consolas,monospace}.customer-schedule__link{border:0;background:transparent;color:#003d9b;font-weight:800}.customer-schedule__pagination{display:flex;justify-content:flex-end;align-items:center;gap:8px;margin-top:10px}.customer-schedule__pagination span{margin-right:auto;color:#596070;font-size:12px}.customer-schedule__cancelled{border:1px solid #d9dbe5;border-radius:8px;padding:14px;background:#fafaff}.customer-schedule__cancelled summary{cursor:pointer;font-weight:800}@media(max-width:800px){.customer-schedule__header{display:grid}.customer-schedule__summary{grid-template-columns:repeat(2,minmax(0,1fr))}.customer-schedule__filters label{width:100%}.customer-schedule__filters input,.customer-schedule__filters select{width:100%}}
</style>
