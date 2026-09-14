<script setup lang="ts">
import {
  AlertCircle,
  Check,
  ChevronLeft,
  ChevronRight,
  Inbox,
  LoaderCircle,
  RefreshCw,
} from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getApiErrorMessage, http } from '@/lib/http'
import {
  factoryContexts,
  isFactoryContextId,
  productionFactoryContextIds,
  type ProductionFactoryContextId,
} from '@/data/enterpriseMock'
import { useAppStore } from '@/stores/app'

export type CustomerOrderInboxRecipient = 'pmc' | 'warehouse' | 'injection'

interface CustomerOrderInboxSnapshot {
  factory_id?: string
  customer_code?: string
  customer_name?: string
  reference_no?: string
  product_no?: string
  po_no?: string
  contract_no?: string
  product_name_zh?: string
  product_name_en?: string
  quantity?: string | number
  shipped_quantity?: string
  remaining_quantity?: string
  history_cutoff_date?: string
  requested_ship_date?: string
  packaging?: string
  units_per_carton?: string | number
  carton_count?: string | number
  standard?: string
  customer_q?: string
  line_q?: string
  country?: string
  note?: string
  status?: string
  version?: string | number
  change_reason?: string
  manual?: string
  label?: string
  customer_label?: string
  carton_mark?: string
  fabric_label?: string
  date_code?: string
  barcode?: string
  parent_product_no?: string
  port?: string
  printing_requirement?: string
  contact?: string
  merchandiser?: string
  customer_release_no?: string
  recheck_notice?: string
  [key: string]: unknown
}

interface CustomerOrderInboxItem {
  id: string
  line_id: string
  factory_id: string
  recipient: CustomerOrderInboxRecipient
  version: number
  latest_version: number
  snapshot: CustomerOrderInboxSnapshot
  actor: string
  created_at: string
  received_at: string | null
  received_by: string | null
  status: 'sent' | 'received'
}

interface CustomerOrderInboxResponse {
  items: CustomerOrderInboxItem[]
  total: number
  page: number
  page_size: number
}

interface CustomerOrderInboxCapabilities {
  inbox_read: boolean
  inbox_receive: boolean
  [key: string]: unknown
}

const props = withDefaults(defineProps<{
  defaultRecipient?: CustomerOrderInboxRecipient
}>(), {
  defaultRecipient: 'pmc',
})

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()

const recipientOptions: Array<{ value: CustomerOrderInboxRecipient; label: string; hint: string }> = [
  { value: 'pmc', label: 'PMC', hint: '计划与物料协同' },
  { value: 'warehouse', label: '仓库', hint: '订单事实与出货衔接' },
  { value: 'injection', label: '啤机部', hint: '订单事实，不生成注塑任务' },
]

const pageSize = 20
const page = ref(1)
const items = ref<CustomerOrderInboxItem[]>([])
const total = ref(0)
const capabilities = ref<CustomerOrderInboxCapabilities | null>(null)
const loading = ref(false)
const receivingId = ref('')
const errorMessage = ref('')
const capabilityMessage = ref('')
const successMessage = ref('')
const expandedItemIds = ref<Set<string>>(new Set())
let requestGeneration = 0

const routeFactoryState = computed(() => {
  const routeFactory = typeof route.query.factory === 'string' ? route.query.factory : ''
  if (isFactoryContextId(routeFactory) && productionFactoryContextIds.includes(routeFactory as ProductionFactoryContextId)) {
    return { kind: 'valid' as const, value: routeFactory }
  }
  return { kind: routeFactory ? 'invalid' as const : 'missing' as const, value: routeFactory }
})

const factoryId = computed(() => routeFactoryState.value.kind === 'valid'
  ? routeFactoryState.value.value
  : routeFactoryState.value.kind === 'missing'
    ? appStore.activeProductionFactory.id
    : '')

const routeRecipient = computed<CustomerOrderInboxRecipient>(() => {
  const value = typeof route.query.recipient === 'string' ? route.query.recipient : ''
  return isRecipient(value) ? value : props.defaultRecipient
})

const selectedRecipient = ref<CustomerOrderInboxRecipient>(routeRecipient.value)
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
const currentFactoryName = computed(() => {
  if (!factoryId.value) return '未选择具体厂区'
  return factoryContexts.find((factory) => factory.id === factoryId.value)?.shortName ?? factoryId.value
})
const factorySelectionMessage = computed(() => factoryId.value
  ? ''
  : '当前入口需要具体厂区，请选择华康A、华康B、华康C、华康D、华登或华兴；集团总览或无效厂区不能读取订单收件箱。')
const selectedRecipientLabel = computed(() => recipientOptions.find((item) => item.value === selectedRecipient.value)?.label ?? '收件单位')

const customerRequirementFields = [
  { key: 'shipped_quantity', label: '发送时累计已走货' },
  { key: 'remaining_quantity', label: '发送时剩余待交付' },
  { key: 'history_cutoff_date', label: '历史期初截止日期' },
  { key: 'manual', label: 'Manual' },
  { key: 'label', label: 'Label' },
  { key: 'customer_label', label: '客户标签' },
  { key: 'carton_mark', label: '箱唛' },
  { key: 'fabric_label', label: '布标' },
  { key: 'date_code', label: '日期码' },
  { key: 'barcode', label: '条码' },
  { key: 'parent_product_no', label: '母件号' },
  { key: 'port', label: '出货港口' },
  { key: 'printing_requirement', label: '印刷要求' },
  { key: 'contact', label: '客户联系人' },
  { key: 'merchandiser', label: '跟单员' },
  { key: 'customer_release_no', label: '客户放行号' },
  { key: 'recheck_notice', label: '复核提示' },
  { key: 'packaging', label: '包装' },
  { key: 'units_per_carton', label: '每箱数量' },
  { key: 'carton_count', label: '箱数' },
  { key: 'standard', label: '标准' },
  { key: 'customer_q', label: '客Q' },
  { key: 'line_q', label: '行Q' },
  { key: 'country', label: '国家' },
  { key: 'note', label: '备注' },
] as const

function isRecipient(value: string): value is CustomerOrderInboxRecipient {
  return value === 'pmc' || value === 'warehouse' || value === 'injection'
}

function displayValue(value: unknown, fallback = '—') {
  if (value === null || value === undefined || String(value).trim() === '') return fallback
  return String(value)
}

function snapshotStatus(item: CustomerOrderInboxItem) {
  const status = String(item.snapshot.status ?? '').toLowerCase()
  if (status.includes('cancel')) return '取消'
  if (item.version > 1 || status.includes('change') || status.includes('amend') || status.includes('update')) return '变更'
  if (item.snapshot.history_cutoff_date) return '历史迁入'
  return '新单'
}

function snapshotStatusClass(item: CustomerOrderInboxItem) {
  const status = snapshotStatus(item)
  return status === '取消' ? 'status-cancelled' : status === '变更' ? 'status-changed' : 'status-new'
}

function isHistorical(item: CustomerOrderInboxItem) {
  return item.version < item.latest_version
}

function isExpanded(itemId: string) {
  return expandedItemIds.value.has(itemId)
}

function toggleDetails(itemId: string) {
  const next = new Set(expandedItemIds.value)
  if (next.has(itemId)) next.delete(itemId)
  else next.add(itemId)
  expandedItemIds.value = next
}

function requirementEntries(item: CustomerOrderInboxItem) {
  return customerRequirementFields
    .map((field) => ({ ...field, value: displayValue(item.snapshot[field.key]) }))
    .filter((entry) => entry.value !== '—')
}

function formatDate(value: string | null | undefined) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

async function syncRouteQuery(nextRecipient = selectedRecipient.value) {
  const nextFactory = factoryId.value
  if (!nextFactory) return
  if (route.query.factory === nextFactory && route.query.recipient === nextRecipient) return
  await router.replace({
    query: {
      ...route.query,
      factory: nextFactory,
      recipient: nextRecipient,
    },
  })
}

async function loadInbox() {
  const generation = ++requestGeneration
  const requestedFactoryId = factoryId.value
  const requestedRecipient = selectedRecipient.value
  loading.value = true
  errorMessage.value = ''
  capabilityMessage.value = ''
  capabilities.value = null
  items.value = []
  total.value = 0
  expandedItemIds.value = new Set()
  if (!requestedFactoryId) {
    errorMessage.value = factorySelectionMessage.value
    loading.value = false
    return
  }
  try {
    const [capabilityResponse, inboxResponse] = await Promise.all([
      http.get<CustomerOrderInboxCapabilities>('/customer-order-ledger/capabilities', {
        params: { factory_id: requestedFactoryId, recipient: requestedRecipient },
      }),
      http.get<CustomerOrderInboxResponse>('/customer-order-ledger/inbox', {
        params: {
          factory_id: requestedFactoryId,
          recipient: requestedRecipient,
          page: page.value,
          page_size: pageSize,
        },
      }),
    ])
    if (generation !== requestGeneration || requestedFactoryId !== factoryId.value || requestedRecipient !== selectedRecipient.value) return
    capabilities.value = capabilityResponse.data
    if (!capabilityResponse.data.inbox_receive) {
      capabilityMessage.value = `当前账号没有${selectedRecipientLabel.value}订单签收权限，仅可查看。`
    }
    items.value = inboxResponse.data.items.filter((item) => item.factory_id === requestedFactoryId && item.recipient === requestedRecipient)
    total.value = inboxResponse.data.total
    if (!capabilityResponse.data.inbox_read) {
      errorMessage.value = `当前账号没有${selectedRecipientLabel.value}订单收件箱查看权限。`
      items.value = []
      total.value = 0
    }
  } catch (error) {
    if (generation !== requestGeneration) return
    items.value = []
    total.value = 0
    capabilityMessage.value = ''
    errorMessage.value = `读取${selectedRecipientLabel.value}订单收件箱失败：${getApiErrorMessage(error)}`
  } finally {
    if (generation === requestGeneration) loading.value = false
  }
}

async function selectRecipient(recipient: CustomerOrderInboxRecipient) {
  if (recipient === selectedRecipient.value) return
  selectedRecipient.value = recipient
  page.value = 1
  successMessage.value = ''
  await syncRouteQuery(recipient)
  await loadInbox()
}

async function changePage(nextPage: number) {
  if (nextPage < 1 || nextPage > totalPages.value || nextPage === page.value) return
  page.value = nextPage
  await loadInbox()
}

async function receive(item: CustomerOrderInboxItem) {
  if (receivingId.value || item.status === 'received') return
  if (!capabilities.value?.inbox_receive) {
    errorMessage.value = `当前账号没有${selectedRecipientLabel.value}订单签收权限。`
    return
  }
  receivingId.value = item.id
  errorMessage.value = ''
  successMessage.value = ''
  try {
    await http.post(
      `/customer-order-ledger/inbox/${encodeURIComponent(item.id)}/receive`,
      undefined,
      { params: { factory_id: factoryId.value, recipient: selectedRecipient.value } },
    )
    successMessage.value = `订单 ${displayValue(item.snapshot.po_no, item.line_id)} 已签收；原版本仍保留可追溯。`
    await loadInbox()
  } catch (error) {
    errorMessage.value = `订单签收失败：${getApiErrorMessage(error)}`
  } finally {
    receivingId.value = ''
  }
}

watch(
  [factoryId, routeRecipient],
  async ([nextFactory, nextRecipient], [previousFactory, previousRecipient]) => {
    if (nextFactory === previousFactory && nextRecipient === previousRecipient) return
    selectedRecipient.value = nextRecipient
    page.value = 1
    successMessage.value = ''
    await syncRouteQuery(nextRecipient)
    await loadInbox()
  },
  { immediate: true },
)
</script>

<template>
  <section class="customer-order-inbox" data-testid="customer-order-inbox">
    <header class="inbox-heading">
      <div>
        <p class="eyebrow"><Inbox aria-hidden="true" />订单事实收件箱</p>
        <h1>下游订单收件箱</h1>
        <p>{{ currentFactoryName }} · 只接收客户订单事实，不在此生成物料或注塑任务。</p>
      </div>
      <button type="button" class="refresh-button" :disabled="loading" @click="loadInbox">
        <RefreshCw :class="{ spinning: loading }" aria-hidden="true" />刷新
      </button>
    </header>

    <div class="recipient-bar" role="tablist" aria-label="订单接收单位">
      <button
        v-for="option in recipientOptions"
        :key="option.value"
        type="button"
        role="tab"
        :aria-selected="selectedRecipient === option.value"
        :class="{ active: selectedRecipient === option.value }"
        @click="selectRecipient(option.value)"
      >
        <span>{{ option.label }}</span>
        <small>{{ option.hint }}</small>
      </button>
    </div>

    <div v-if="errorMessage" class="message message-error" role="alert">
      <AlertCircle aria-hidden="true" />{{ errorMessage }}
    </div>
    <div v-if="capabilityMessage && !errorMessage" class="message message-warning" role="alert">
      <AlertCircle aria-hidden="true" />{{ capabilityMessage }}
    </div>
    <div v-if="successMessage" class="message message-success" role="status">
      <Check aria-hidden="true" />{{ successMessage }}
    </div>

    <div class="inbox-policy">
      <span>当前厂区：<b>{{ factoryId || '未选择' }}</b></span>
      <span>收件单位：<b>{{ selectedRecipientLabel }}</b></span>
      <span v-if="capabilities?.inbox_receive" class="capability-ok">具备签收权限</span>
      <span v-else class="capability-muted">仅查看或权限待确认</span>
    </div>

    <div v-if="loading" class="empty-state"><LoaderCircle class="spinning" aria-hidden="true" />正在读取订单收件箱…</div>
    <div v-else-if="!errorMessage && items.length === 0" class="empty-state">
      <Inbox aria-hidden="true" />当前收件单位暂无订单事实。
    </div>
    <div v-else-if="!errorMessage" class="inbox-table-wrap">
      <table class="inbox-table">
        <thead>
          <tr>
            <th>状态 / 版本</th><th>客户与订单</th><th>产品</th><th>数量</th><th>客户要求交期</th><th>发送记录</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="item in items" :key="item.id">
          <tr :class="{ historical: isHistorical(item) }">
            <td>
              <span :class="['status-chip', snapshotStatusClass(item)]">{{ snapshotStatus(item) }}</span>
              <strong class="version-label">V{{ item.version }}</strong>
              <small v-if="isHistorical(item)" class="history-hint">历史版本，最新 V{{ item.latest_version }}</small>
              <small v-if="item.snapshot.change_reason" class="history-hint">{{ item.snapshot.change_reason }}</small>
            </td>
            <td>
              <strong>{{ displayValue(item.snapshot.customer_name, item.snapshot.customer_code) }}</strong>
              <small>PO {{ displayValue(item.snapshot.po_no) }} · 合同 {{ displayValue(item.snapshot.contract_no) }}</small>
              <small>识别号 {{ displayValue(item.snapshot.reference_no, item.line_id) }}</small>
            </td>
            <td>
              <strong>{{ displayValue(item.snapshot.product_no) }}</strong>
              <small>{{ displayValue(item.snapshot.product_name_zh, item.snapshot.product_name_en) }}</small>
            </td>
            <td>
              <strong>{{ displayValue(item.snapshot.quantity) }}</strong>
              <small v-if="item.snapshot.remaining_quantity !== undefined">发送时剩余待交付 {{ displayValue(item.snapshot.remaining_quantity) }}</small>
              <small v-if="item.snapshot.shipped_quantity !== undefined">发送时累计已走货 {{ displayValue(item.snapshot.shipped_quantity) }}</small>
              <small v-if="item.snapshot.history_cutoff_date">历史期初截至 {{ item.snapshot.history_cutoff_date }}</small>
              <small>{{ displayValue(item.snapshot.units_per_carton) }} / 箱 · {{ displayValue(item.snapshot.carton_count) }} 箱</small>
            </td>
            <td>
              <strong>{{ displayValue(item.snapshot.requested_ship_date) }}</strong>
              <small>{{ displayValue(item.snapshot.country, item.snapshot.standard) }}</small>
            </td>
            <td>
              <small>发送人 {{ displayValue(item.actor) }}</small>
              <small>{{ formatDate(item.created_at) }}</small>
              <small v-if="item.status === 'received'" class="received-label">已签收 · {{ displayValue(item.received_by) }} · {{ formatDate(item.received_at) }}</small>
              <small v-else class="sent-label">待签收</small>
            </td>
            <td>
              <button type="button" class="requirement-button" @click="toggleDetails(item.id)">
                {{ isExpanded(item.id) ? '收起客户要求' : '客户要求' }}
              </button>
              <button
                type="button"
                class="receive-button"
                :disabled="item.status === 'received' || receivingId === item.id || !capabilities?.inbox_receive"
                :title="capabilities?.inbox_receive ? '幂等签收该版本' : `当前账号没有${selectedRecipientLabel}签收权限`"
                @click="receive(item)"
              >
                <LoaderCircle v-if="receivingId === item.id" class="spinning" aria-hidden="true" />
                <Check v-else-if="item.status === 'received'" aria-hidden="true" />
                {{ item.status === 'received' ? '已签收' : '签收' }}
              </button>
            </td>
          </tr>
          <tr v-if="isExpanded(item.id)" class="requirements-row">
            <td colspan="7">
              <div class="requirements-panel">
                <strong>客户要求</strong>
                <dl v-if="requirementEntries(item).length">
                  <div v-for="entry in requirementEntries(item)" :key="entry.key">
                    <dt>{{ entry.label }}</dt><dd>{{ entry.value }}</dd>
                  </div>
                </dl>
                <span v-else>该版本没有额外客户要求。</span>
              </div>
            </td>
          </tr>
          </template>
        </tbody>
      </table>
    </div>

    <footer v-if="!loading && total > 0 && !errorMessage" class="inbox-pagination">
      <span>共 {{ total }} 条 · 第 {{ page }} / {{ totalPages }} 页</span>
      <div>
        <button type="button" :disabled="page <= 1" aria-label="上一页" @click="changePage(page - 1)"><ChevronLeft aria-hidden="true" /></button>
        <button type="button" :disabled="page >= totalPages" aria-label="下一页" @click="changePage(page + 1)"><ChevronRight aria-hidden="true" /></button>
      </div>
    </footer>
  </section>
</template>

<style scoped>
.customer-order-inbox { min-height: 100vh; background: #f7fafc; padding: 32px; color: #172033; font-family: Inter, "Microsoft YaHei", "PingFang SC", sans-serif; }
.inbox-heading { display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; margin: 0 auto 24px; max-width: 1440px; }
.eyebrow { display: inline-flex; align-items: center; gap: 7px; margin: 0 0 8px; color: #0f766e; font-size: 12px; font-weight: 800; letter-spacing: .08em; }
.eyebrow svg { width: 16px; height: 16px; }
h1 { margin: 0; color: #13213b; font-size: clamp(26px, 3vw, 38px); line-height: 1.1; }
.inbox-heading p:not(.eyebrow) { margin: 10px 0 0; color: #61708a; font-size: 14px; }
.refresh-button, .receive-button, .inbox-pagination button { display: inline-flex; align-items: center; justify-content: center; gap: 7px; border: 1px solid #cbd5e1; background: #fff; color: #31506e; font-weight: 800; cursor: pointer; }
.refresh-button { min-height: 38px; border-radius: 10px; padding: 0 14px; }
.refresh-button:disabled, .receive-button:disabled, .inbox-pagination button:disabled { cursor: not-allowed; opacity: .55; }
.refresh-button svg, .receive-button svg, .inbox-pagination svg { width: 16px; height: 16px; }
.recipient-bar, .inbox-policy, .inbox-table-wrap, .inbox-pagination, .message { max-width: 1440px; margin-inline: auto; }
.recipient-bar { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-bottom: 14px; }
.recipient-bar button { display: grid; gap: 4px; min-height: 68px; border: 1px solid #d6dee9; border-radius: 12px; background: #fff; padding: 12px 15px; color: #334155; text-align: left; cursor: pointer; }
.recipient-bar button:hover { border-color: #7dd3c6; }
.recipient-bar button.active { border-color: #0f766e; background: #ecfdf5; box-shadow: 0 0 0 2px #ccfbf1; color: #075e58; }
.recipient-bar span { font-size: 15px; font-weight: 900; }
.recipient-bar small { color: #718096; font-size: 11px; }
.message { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; border-radius: 10px; padding: 11px 14px; font-size: 13px; font-weight: 700; }
.message svg { width: 17px; height: 17px; flex: 0 0 auto; }
.message-error { border: 1px solid #fecaca; background: #fff1f2; color: #b42318; }
.message-warning { border: 1px solid #fde68a; background: #fffbeb; color: #92400e; }
.message-success { border: 1px solid #bbf7d0; background: #f0fdf4; color: #166534; }
.inbox-policy { display: flex; flex-wrap: wrap; gap: 8px 18px; margin-bottom: 12px; color: #64748b; font-size: 12px; }
.capability-ok { color: #047857; font-weight: 800; }
.capability-muted { color: #9a6700; font-weight: 800; }
.empty-state { display: flex; min-height: 220px; max-width: 1440px; align-items: center; justify-content: center; gap: 9px; margin: 20px auto; border: 1px dashed #cbd5e1; border-radius: 14px; background: #fff; color: #64748b; font-size: 14px; font-weight: 700; }
.empty-state svg { width: 19px; height: 19px; }
.inbox-table-wrap { overflow: auto; border: 1px solid #d8e0eb; border-radius: 14px; background: #fff; box-shadow: 0 8px 28px rgb(15 23 42 / 5%); }
.inbox-table { width: 100%; min-width: 1080px; border-collapse: collapse; font-size: 12px; }
.inbox-table th { background: #f8fafc; color: #526277; font-size: 11px; letter-spacing: .04em; text-align: left; white-space: nowrap; }
.inbox-table th, .inbox-table td { border-bottom: 1px solid #e8edf3; padding: 13px 12px; vertical-align: top; }
.inbox-table tbody tr:last-child td { border-bottom: 0; }
.inbox-table tbody tr.historical { background: #fafafa; }
.inbox-table td > strong, .inbox-table td > small { display: block; }
.inbox-table td > strong { color: #172033; font-size: 12px; }
.inbox-table td > small { margin-top: 5px; color: #718096; line-height: 1.35; }
.status-chip { display: inline-flex; border-radius: 999px; padding: 3px 8px; font-size: 11px; font-weight: 900; }
.status-new { background: #dcfce7; color: #166534; }
.status-changed { background: #fef3c7; color: #92400e; }
.status-cancelled { background: #fee2e2; color: #991b1b; }
.version-label { margin-top: 7px; }
.history-hint { color: #9a6700 !important; font-weight: 800; }
.received-label { color: #047857 !important; font-weight: 800; }
.sent-label { color: #9a6700 !important; font-weight: 800; }
.receive-button { min-height: 32px; border-radius: 8px; padding: 0 10px; color: #0f766e; font-size: 11px; }
.requirement-button { display: block; min-height: 28px; margin-bottom: 7px; border: 0; background: transparent; color: #2563eb; cursor: pointer; font-size: 11px; font-weight: 800; text-decoration: underline; text-underline-offset: 2px; }
.requirements-row td { background: #f8fafc; padding: 0; }
.requirements-panel { margin: 0; padding: 14px 16px 16px; border-top: 1px solid #dbe4ef; }
.requirements-panel > strong { color: #0f766e; font-size: 13px; }
.requirements-panel > span { display: block; margin-top: 9px; color: #718096; }
.requirements-panel dl { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 9px 18px; margin: 10px 0 0; }
.requirements-panel dl > div { min-width: 0; }
.requirements-panel dt { color: #718096; font-size: 11px; }
.requirements-panel dd { margin: 3px 0 0; color: #172033; font-size: 12px; overflow-wrap: anywhere; }
.inbox-pagination { display: flex; justify-content: space-between; align-items: center; padding: 13px 2px 0; color: #64748b; font-size: 12px; }
.inbox-pagination div { display: flex; gap: 6px; }
.inbox-pagination button { width: 32px; height: 30px; border-radius: 8px; padding: 0; }
.spinning { animation: spin 900ms linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 900px) { .requirements-panel dl { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 720px) { .customer-order-inbox { padding: 20px 14px; } .inbox-heading { flex-direction: column; } .recipient-bar { grid-template-columns: 1fr; } .requirements-panel dl { grid-template-columns: 1fr; } }
</style>
