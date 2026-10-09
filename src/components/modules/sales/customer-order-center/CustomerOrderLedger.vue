<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  customerOrderLedgerApi,
  customerOrderLedgerSourceUrl,
  type CustomerOrderLedgerCapabilities,
  type CustomerOrderLedgerDetail,
  type CustomerOrderLedgerLine,
  type CustomerOrderLedgerView,
} from '@/api/customerOrderLedger'
import { customerOrderHistoryApi } from '@/api/customerOrderHistory'
import CustomerOrderHistoryImport from './CustomerOrderHistoryImport.vue'
import { getApiErrorMessage } from '@/lib/http'
import type { FeedbackContext } from '@/api/moduleFeedback'

const props = withDefaults(defineProps<{
  factoryId: string
  factoryName: string
  initialView?: CustomerOrderLedgerView
  displayMode?: 'ledger' | 'schedule'
  detailOnly?: boolean
  focusLineId?: string
}>(), { initialView: 'all', displayMode: 'ledger' })

const emit = defineEmits<{ import: []; changed: []; 'close-detail': []; feedback: [context: FeedbackContext] }>()
const emptyCapabilities: CustomerOrderLedgerCapabilities = {
  read: false, write: false, dispatch: false, shipment_confirm: false, inbox_read: false, inbox_receive: false,
}
const capabilities = ref<CustomerOrderLedgerCapabilities>(emptyCapabilities)
const lines = ref<CustomerOrderLedgerLine[]>([])
const customers = ref<Array<{ code: string; name: string }>>([])
const total = ref(0)
const loading = ref(false)
const message = ref('')
const customerCode = ref('')
const view = ref<CustomerOrderLedgerView>(props.initialView)
const query = ref('')
const selected = ref<CustomerOrderLedgerDetail | null>(null)
const detailLoading = ref(false)
const actionError = ref('')
const actionBusy = ref(false)
const page = ref(1)
const amend = ref({ quantity: '', requested_ship_date: '', note: '', reason: '' })
const cancelReason = ref('')
const recipients = ref<Array<'pmc' | 'warehouse' | 'injection' | 'cutting'>>([])
const shipment = ref({ quantity: '', ship_date: '', document_no: '', note: '', idempotency_key: '' })
const reversalReason = ref('')
const historyOpening = ref({ quantity: '', reason: '' })
const showHistoryImport = ref(false)
let listRequestSequence = 0
let detailRequestSequence = 0
let actionSequence = 0

const displayLines = computed(() => lines.value)
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / 50)))
const requiresDispatchForEdit = computed(() => selected.value?.line.status === 'active'
  && selected.value.line.dispatch_status !== 'unsent')
const canEdit = computed(() => capabilities.value.write && selected.value?.line.status === 'active'
  && (!requiresDispatchForEdit.value || capabilities.value.dispatch))
const canShip = computed(() => capabilities.value.shipment_confirm && selected.value?.line.status === 'active')
const canReverseShipment = computed(() => capabilities.value.shipment_confirm)
const canCorrectHistoryOpening = computed(() => Boolean(selected.value && historyMigrationFields(selected.value.line.data).length)
  && capabilities.value.write && capabilities.value.shipment_confirm
  && (selected.value?.line.dispatch_status === 'unsent' || capabilities.value.dispatch))
const title = computed(() => props.displayMode === 'schedule' ? `${props.factoryName}总排期` : `${props.factoryName}订单数据台账`)

const BUSINESS_FIELD_LABELS: Record<string, string> = {
  po_no: '客户 P/O', contract_no: '合同号', customer_country: '客户/国家', country: '国家',
  product_no: '产品编号', parent_product_no: '母货号', product_name_zh: '中文名称', product_name_en: '英文名称',
  quantity: '订单数量', requested_ship_date: '客户要求交期', ship_date: '客户要求交期',
  units_per_carton: '装箱数', carton_count: '箱数', packaging: '包装', standard: '规格',
  unit_price_hkd: '单价（HKD）', amount_hkd: '金额（HKD）', unit_price_usd: '单价（USD）', amount_usd: '金额（USD）',
  line_q: '行要求', customer_q: '客户要求', note: '备注', remark: '备注', manual: '人工说明',
  label: '标签要求', customer_label: '客户标签', carton_mark: '箱唛', fabric_label: '布标', date_code: '日期码', barcode: '条码',
  port: '目的港', printing_requirement: '印刷要求', contact: '联系人', merchandiser: '跟单员',
  customer_release_no: '客户 Release 单号', factory_commit_date: '工厂承诺交期', planned_inspection_date: '验货日期',
  case_pack: '每箱数量', pack_qty: '每箱数量', master_carton_qty: '外箱数量', customer_po: '客户 P/O',
}
const INTERNAL_DATA_FIELDS = new Set([
  'id', 'issues', 'status', 'status_label', 'lineage', 'import_controls', 'source_kind',
  'source_po_file_name', 'received_date', 'input_template', 'target_template', 'item_sheet_name', 'recheck_notice', 'history_migration', 'history_fields', 'history_review',
])

function resetForFactory() {
  listRequestSequence += 1
  detailRequestSequence += 1
  actionSequence += 1
  lines.value = []
  customers.value = []
  total.value = 0
  selected.value = null
  detailLoading.value = false
  customerCode.value = ''
  page.value = 1
  message.value = ''
  actionError.value = ''
  actionBusy.value = false
  historyOpening.value = { quantity: '', reason: '' }
  showHistoryImport.value = false
}

async function loadList() {
  const token = ++listRequestSequence
  const factoryId = props.factoryId
  loading.value = true
  message.value = ''
  try {
    const [nextCapabilities, result] = await Promise.all([
      customerOrderLedgerApi.capabilities(factoryId),
      customerOrderLedgerApi.list(factoryId, { customerCode: customerCode.value, view: view.value, q: query.value.trim(), page: page.value }),
    ])
    if (token !== listRequestSequence || factoryId !== props.factoryId) return
    capabilities.value = nextCapabilities
    lines.value = result.items.filter((line) => line.factory_id === factoryId)
    customers.value = result.customers
    total.value = result.total
  } catch (error) {
    if (token !== listRequestSequence || factoryId !== props.factoryId) return
    lines.value = []
    message.value = `无法读取订单台账：${getApiErrorMessage(error)}`
  } finally {
    if (token === listRequestSequence) loading.value = false
  }
}

function applyFilters() {
  page.value = 1
  clearDetail()
  void loadList()
}

function goToPage(nextPage: number) {
  if (nextPage < 1 || nextPage > pageCount.value || nextPage === page.value) return
  page.value = nextPage
  clearDetail()
  void loadList()
}

function clearDetail() {
  if (actionBusy.value) return
  if (props.detailOnly) listRequestSequence += 1
  detailRequestSequence += 1
  selected.value = null
  detailLoading.value = false
  actionError.value = ''
  emit('close-detail')
}

async function openDetail(line: Pick<CustomerOrderLedgerLine, 'id'>) {
  const token = ++detailRequestSequence
  const factoryId = props.factoryId
  detailLoading.value = true
  actionError.value = ''
  try {
    const detail = await customerOrderLedgerApi.detail(line.id, factoryId)
    if (token !== detailRequestSequence || factoryId !== props.factoryId) return
    if (detail.line.factory_id !== factoryId || detail.line.id !== line.id) throw new Error('返回的订单与当前选择不一致，请重新打开详情。')
    applyDetail(detail)
  } catch (error) {
    if (token !== detailRequestSequence || factoryId !== props.factoryId) return
    actionError.value = `无法读取订单详情：${getApiErrorMessage(error)}`
  } finally {
    if (token === detailRequestSequence) detailLoading.value = false
  }
}

function stringField(data: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = data[key]
    if (typeof value === 'string') return value
  }
  return ''
}

function businessFields(data: Record<string, unknown>) {
  return Object.entries(data).flatMap(([key, value]) => {
    const label = BUSINESS_FIELD_LABELS[key]
    if (!label || INTERNAL_DATA_FIELDS.has(key) || !['string', 'number', 'boolean'].includes(typeof value)) return []
    return [{ key, label, value: typeof value === 'boolean' ? (value ? '是' : '否') : (String(value) || '—') }]
  })
}

function lineageFields(data: Record<string, unknown>) {
  const lineage = data.lineage
  if (!lineage || typeof lineage !== 'object' || Array.isArray(lineage)) return []
  return Object.entries(lineage as Record<string, unknown>).flatMap(([key, value]) => {
    const label = BUSINESS_FIELD_LABELS[key]
    if (!label || !['string', 'number', 'boolean'].includes(typeof value)) return []
    return [{ key, label, value: typeof value === 'boolean' ? (value ? '是' : '否') : (String(value) || '—') }]
  })
}

function historyMigrationFields(data: Record<string, unknown>) {
  const migration = data.history_migration
  if (!migration || typeof migration !== 'object' || Array.isArray(migration)) return []
  const labels: Record<string, string> = {
    cutoff_date: '历史截止日期', opening_shipped_quantity: '期初已走货数量', original_opening_shipped_quantity: '原始期初已走货数量',
    sheet: '来源工作表', row: '来源行号', section: '原排期分组', reason: '迁入原因', actor: '迁入人员', confirmed_at: '确认时间',
    correction_reason: '更正原因', corrected_by: '更正人员', corrected_at: '更正时间',
  }
  return Object.entries(migration as Record<string, unknown>).flatMap(([key, value]) => {
    if (!labels[key] || !['string', 'number', 'boolean'].includes(typeof value)) return []
    const display = key === 'section'
      ? ({ unshipped: '未走货', shipped: '已走货', cancelled: '已取消' } as Record<string, string>)[String(value)] ?? String(value)
      : typeof value === 'boolean' ? (value ? '是' : '否') : (String(value) || '—')
    return [{ key, label: labels[key], value: display }]
  })
}

function historyMigrationOpening(data: Record<string, unknown>) {
  const migration = data.history_migration
  if (!migration || typeof migration !== 'object' || Array.isArray(migration)) return ''
  const value = (migration as Record<string, unknown>).opening_shipped_quantity
  return typeof value === 'string' || typeof value === 'number' ? String(value) : ''
}

function historyOriginalFields(data: Record<string, unknown>) {
  const fields = data.history_fields
  if (!Array.isArray(fields)) return []
  return fields.flatMap((field) => {
    if (!field || typeof field !== 'object' || Array.isArray(field)) return []
    const source = field as Record<string, unknown>
    const column = typeof source.column === 'string' ? source.column : ''
    const header = typeof source.header === 'string' && source.header.trim() ? source.header.trim() : '未命名原始字段'
    return [{ key: `${column}-${header}`, column, header, value: displayHistoryOriginalValue(source.value) }]
  })
}

function historyOriginalLocation(data: Record<string, unknown>) {
  const migration = data.history_migration
  if (!migration || typeof migration !== 'object' || Array.isArray(migration)) return ''
  const source = migration as Record<string, unknown>
  const sheet = typeof source.sheet === 'string' ? source.sheet : ''
  const row = typeof source.row === 'number' || typeof source.row === 'string' ? String(source.row) : ''
  return sheet && row ? `${sheet} · 第 ${row} 行` : sheet || (row ? `第 ${row} 行` : '')
}

function displayHistoryOriginalValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value)
  try { return JSON.stringify(value) } catch { return '（无法显示的原始值）' }
}

function handleHistoryMigrationSaved() {
  showHistoryImport.value = false
  page.value = 1
  clearDetail()
  void loadList()
}

function sourceKindLabel(kind: string) {
  return ({ formal: '正式 PO', supplementary: '补充合同', schedule: '原排期' } as Record<string, string>)[kind] ?? '订单原件'
}

function recipientLabel(recipient: string) {
  return ({ pmc: 'PMC', warehouse: '仓库', injection: '啤机部', cutting: '裁床部' } as Record<string, string>)[recipient] ?? recipient
}

function createIdempotencyKey() {
  return globalThis.crypto?.randomUUID?.() ?? `shipment-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function today() {
  const date = new Date()
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function applyDetail(detail: CustomerOrderLedgerDetail) {
  selected.value = detail
  amend.value = {
    quantity: detail.line.quantity,
    requested_ship_date: stringField(detail.line.data, ['requested_ship_date', 'ship_date']),
    note: stringField(detail.line.data, ['note', 'remark']),
    reason: '',
  }
  cancelReason.value = ''
  recipients.value = []
  shipment.value = { quantity: detail.line.remaining_quantity, ship_date: today(), document_no: '', note: '', idempotency_key: createIdempotencyKey() }
  reversalReason.value = ''
  historyOpening.value = { quantity: historyMigrationOpening(detail.line.data), reason: '' }
}

async function refreshAfterWrite(id: string, factoryId: string, actionToken: number) {
  if (!props.detailOnly) await loadList()
  if (actionToken !== actionSequence || factoryId !== props.factoryId) return
  const detailToken = ++detailRequestSequence
  const detail = await customerOrderLedgerApi.detail(id, factoryId)
  if (actionToken !== actionSequence || detailToken !== detailRequestSequence || factoryId !== props.factoryId) return
  if (detail.line.factory_id !== factoryId || detail.line.id !== id) throw new Error('返回的订单与当前选择不一致，请重新打开详情。')
  applyDetail(detail)
}

async function runAction(action: () => Promise<unknown>) {
  const factoryId = props.factoryId
  const lineId = selected.value?.line.id
  if (!lineId) return
  const actionToken = ++actionSequence
  detailRequestSequence += 1
  actionError.value = ''
  actionBusy.value = true
  try {
    await action()
    if (actionToken !== actionSequence || factoryId !== props.factoryId) return
    emit('changed')
    await refreshAfterWrite(lineId, factoryId, actionToken)
  } catch (error) {
    if (actionToken !== actionSequence || factoryId !== props.factoryId) return
    actionError.value = getApiErrorMessage(error)
  } finally {
    if (actionToken === actionSequence) actionBusy.value = false
  }
}

function submitAmend() {
  if (!selected.value || amend.value.reason.trim().length < 4) {
    actionError.value = '修改数量、交期或备注必须填写至少 4 个字的修改原因。'
    return
  }
  void runAction(() => customerOrderLedgerApi.amend(selected.value!.line.id, props.factoryId, {
    expected_revision: selected.value!.line.revision,
    quantity: amend.value.quantity,
    requested_ship_date: amend.value.requested_ship_date,
    note: amend.value.note,
    reason: amend.value.reason.trim(),
  }))
}

function submitCancel() {
  if (!selected.value || cancelReason.value.trim().length < 4) {
    actionError.value = '取消订单必须填写至少 4 个字的原因。'
    return
  }
  void runAction(() => customerOrderLedgerApi.cancel(selected.value!.line.id, props.factoryId, {
    expected_revision: selected.value!.line.revision, reason: cancelReason.value.trim(),
  }))
}

function submitDispatch() {
  if (!selected.value || recipients.value.length === 0) {
    actionError.value = '请选择至少一个接收部门。'
    return
  }
  void runAction(() => customerOrderLedgerApi.dispatch(selected.value!.line.id, props.factoryId, {
    expected_revision: selected.value!.line.revision, recipients: recipients.value,
  }))
}

function submitShipment() {
  if (!selected.value || !shipment.value.quantity.trim() || !shipment.value.ship_date || !shipment.value.document_no.trim()) {
    actionError.value = '请填写出货单号、走货日期和数量。'
    return
  }
  void runAction(() => customerOrderLedgerApi.confirmShipment(selected.value!.line.id, props.factoryId, {
    expected_revision: selected.value!.line.revision,
    idempotency_key: shipment.value.idempotency_key,
    quantity: shipment.value.quantity,
    ship_date: shipment.value.ship_date,
    document_no: shipment.value.document_no.trim(),
    note: shipment.value.note,
  }))
}

function submitReversal(shipmentId: string) {
  if (!selected.value || reversalReason.value.trim().length < 4) {
    actionError.value = '撤销走货必须填写至少 4 个字的纠错原因。'
    return
  }
  void runAction(() => customerOrderLedgerApi.reverseShipment(shipmentId, props.factoryId, {
    expected_revision: selected.value!.line.revision, reason: reversalReason.value.trim(),
  }))
}

function submitHistoryOpeningCorrection() {
  if (!selected.value || !historyOpening.value.quantity.trim()) {
    actionError.value = '请填写更正后的期初已走货数量。'
    return
  }
  if (historyOpening.value.reason.trim().length < 4) {
    actionError.value = '更正历史期初必须填写至少 4 个字的原因。'
    return
  }
  void runAction(() => customerOrderHistoryApi.correctOpening(selected.value!.line.id, props.factoryId, {
    expected_revision: selected.value!.line.revision,
    opening_shipped_quantity: historyOpening.value.quantity.trim(),
    reason: historyOpening.value.reason.trim(),
  }))
}

async function loadFocusedDetail() {
  const factoryId = props.factoryId
  const id = props.focusLineId
  if (!id) return
  const token = ++listRequestSequence
  detailLoading.value = true
  try {
    const nextCapabilities = await customerOrderLedgerApi.capabilities(factoryId)
    if (token !== listRequestSequence || factoryId !== props.factoryId || id !== props.focusLineId) return
    capabilities.value = nextCapabilities
    await openDetail({ id })
  } catch (error) {
    if (token !== listRequestSequence) return
    detailLoading.value = false
    actionError.value = `无法读取订单详情：${getApiErrorMessage(error)}`
  }
}

watch(() => [props.factoryId, props.detailOnly, props.focusLineId], () => {
  resetForFactory()
  capabilities.value = emptyCapabilities
  if (props.detailOnly) void loadFocusedDetail()
  else void loadList()
}, { immediate: true })
watch(() => props.initialView, (next) => { view.value = next; applyFilters() })
onBeforeUnmount(() => {
  listRequestSequence += 1
  detailRequestSequence += 1
  actionSequence += 1
})
</script>

<template>
  <section class="ledger" data-testid="customer-order-ledger">
    <template v-if="!detailOnly">
    <header class="ledger__header">
      <div>
        <p class="ledger__eyebrow">订单事实台账</p>
        <h2>{{ title }}</h2>
        <p>{{ displayMode === 'schedule' ? '仅展示本厂各客户订单的公共字段、发送状态和走货数量。' : '显示本厂已保存的订单、版本、发送和业务人员凭出货单确认的分批走货记录。' }}</p>
      </div>
      <div class="ledger__header-actions"><button class="ledger__button" type="button" :disabled="!capabilities.write || !capabilities.shipment_confirm" title="需要写入订单和确认走货权限" @click="showHistoryImport = true">历史排期迁入</button><button class="ledger__button ledger__button--primary" type="button" @click="emit('import')">新建导入</button></div>
    </header>

    <div class="ledger__filters">
      <input v-model="query" type="search" placeholder="搜索客户、参考号或产品编号" @keyup.enter="applyFilters">
      <select v-model="customerCode" aria-label="筛选客户" @change="applyFilters"><option value="">全部客户</option><option v-for="customer in customers" :key="customer.code" :value="customer.code">{{ customer.name || customer.code }}</option></select>
      <select v-model="view" aria-label="筛选走货状态" @change="applyFilters"><option value="all">全部订单</option><option value="unshipped">未走货</option><option value="shipped">已走货</option><option value="cancelled">已取消</option></select>
      <button class="ledger__button" type="button" :disabled="loading" @click="loadList">{{ loading ? '加载中…' : '刷新' }}</button>
      <span>共 {{ total }} 条</span>
    </div>
    <p v-if="message" class="ledger__message">{{ message }}</p>
    <div class="ledger__table-wrap">
      <table>
        <thead><tr><th>客户</th><th>参考号 / P/O</th><th>产品编号</th><th>订单数量</th><th>客户要求交期</th><th>已走货</th><th>未走货</th><th>状态</th><th>发送</th><th>版本</th><th></th></tr></thead>
        <tbody>
          <tr v-for="line in displayLines" :key="line.id"><td>{{ line.customer_name || line.customer_code }}</td><td class="mono">{{ line.reference_no }}</td><td class="mono">{{ line.product_no }}</td><td>{{ line.quantity }}</td><td>{{ stringField(line.data, ['requested_ship_date', 'ship_date']) || '—' }}</td><td>{{ line.shipped_quantity }}</td><td>{{ line.remaining_quantity }}</td><td>{{ line.status === 'cancelled' ? '已取消' : '有效' }}</td><td>{{ line.dispatch_status === 'unsent' ? '未发送' : line.dispatch_status === 'changed' ? '有变更' : '已发送' }}</td><td>V{{ line.version }}</td><td><button class="ledger__link" type="button" @click="openDetail(line)">详情</button></td></tr>
          <tr v-if="!loading && displayLines.length === 0"><td colspan="11">当前筛选范围没有订单记录。</td></tr>
        </tbody>
      </table>
    </div>
    <footer class="ledger__pagination" aria-label="订单台账分页">
      <span>第 {{ page }} / {{ pageCount }} 页</span>
      <button class="ledger__button" type="button" :disabled="loading || page <= 1" @click="goToPage(page - 1)">上一页</button>
      <button class="ledger__button" type="button" :disabled="loading || page >= pageCount" @click="goToPage(page + 1)">下一页</button>
    </footer>
    </template>

    <div v-if="selected || detailLoading || (detailOnly && actionError)" class="ledger__backdrop" @click.self="clearDetail">
      <aside class="ledger__detail" role="dialog" aria-modal="true">
        <button class="ledger__close" type="button" aria-label="关闭详情" :disabled="actionBusy" @click="clearDetail">×</button>
        <p v-if="detailLoading">正在读取详情…</p>
        <p v-else-if="!selected && actionError" class="ledger__message">{{ actionError }}</p>
        <template v-else-if="selected">
          <h3>{{ selected.line.customer_name || selected.line.customer_code }} · {{ selected.line.product_no }}</h3>
          <p class="ledger__muted">参考号 {{ selected.line.reference_no }} · V{{ selected.line.version }} · 修订 {{ selected.line.revision }}</p>
          <button type="button" class="ledger__button" @click="emit('feedback', { page: '订单详情', section: displayMode === 'schedule' ? 'schedule' : 'ledger', order_id: selected.line.id, customer_code: selected.line.customer_code, order_reference: selected.line.reference_no, product_no: selected.line.product_no, error_message: actionError.slice(0, 1000) || undefined })">反馈此订单的问题</button>
          <p v-if="actionError" class="ledger__message">{{ actionError }}</p>
          <p v-if="typeof selected.line.data.recheck_notice === 'string'" class="ledger__recheck">{{ selected.line.data.recheck_notice }}</p>
          <section v-if="historyMigrationFields(selected.line.data).length"><h4>历史排期迁入期初</h4><p class="ledger__muted">历史截止日期包含当日走货。该期初不是新的出货单；截止日期后的实际走货仍须凭出货单确认。</p><dl><template v-for="field in historyMigrationFields(selected.line.data)" :key="field.key"><dt>{{ field.label }}</dt><dd>{{ field.value }}</dd></template></dl><div v-if="canCorrectHistoryOpening" class="ledger__history-correction"><h5>更正期初走货</h5><p class="ledger__muted">更正会保留原始期初和原因；已发送订单还需要订单发送权限。</p><div class="ledger__form"><label>更正后的期初已走货数量<input v-model="historyOpening.quantity" type="text"></label><label>更正原因（至少 4 个字）<textarea v-model="historyOpening.reason" rows="2" /></label><button class="ledger__button ledger__button--primary" type="button" :disabled="actionBusy" @click="submitHistoryOpeningCorrection">保存历史期初更正</button></div></div></section>
          <section v-if="historyOriginalFields(selected.line.data).length"><h4>历史排期原始字段</h4><details class="ledger__details"><summary>展开原排期字段{{ historyOriginalLocation(selected.line.data) ? `（${historyOriginalLocation(selected.line.data)}）` : '' }}</summary><dl><template v-for="field in historyOriginalFields(selected.line.data)" :key="field.key"><dt>{{ field.header }}{{ field.column ? `（${field.column}列）` : '' }}</dt><dd>{{ field.value }}</dd></template></dl></details></section>
          <section><h4>原件与客户字段</h4><p v-if="selected.sources.length === 0" class="ledger__muted">暂无关联原件。</p><ul><li v-for="source in selected.sources" :key="source.id"><a :href="customerOrderLedgerSourceUrl(source.id, factoryId)" target="_blank" rel="noopener">{{ source.file_name }}</a> <small>{{ sourceKindLabel(source.kind) }}</small></li></ul><dl v-if="businessFields(selected.line.data).length"><template v-for="field in businessFields(selected.line.data)" :key="field.key"><dt>{{ field.label }}</dt><dd>{{ field.value }}</dd></template></dl><p v-else class="ledger__muted">暂无可展示的客户字段。</p><details v-if="lineageFields(selected.line.data).length" class="ledger__details"><summary>字段来源说明</summary><dl><template v-for="field in lineageFields(selected.line.data)" :key="field.key"><dt>{{ field.label }}</dt><dd>{{ field.value }}</dd></template></dl></details></section>
          <section><h4>版本记录</h4><div class="ledger__versions"><details v-for="item in selected.versions" :key="`${item.version}-${item.created_at}`" class="ledger__details"><summary>V{{ item.version }} · {{ item.reason || '初始确认' }} · {{ item.actor }} · {{ item.created_at }}</summary><dl v-if="businessFields(item.data).length"><template v-for="field in businessFields(item.data)" :key="field.key"><dt>{{ field.label }}</dt><dd>{{ field.value }}</dd></template></dl><p v-else class="ledger__muted">该版本没有可展示的客户字段。</p></details></div></section>
          <section><h4>发送记录</h4><p v-if="selected.dispatches.length === 0" class="ledger__muted">尚未发送给接收部门。</p><ul v-else><li v-for="item in selected.dispatches" :key="item.id">{{ recipientLabel(item.recipient) }} · V{{ item.version }} · {{ item.status === 'received' ? '已接收' : '已发送' }} · {{ item.created_at }}<template v-if="item.received_at"> · 接收于 {{ item.received_at }}{{ item.received_by ? `（${item.received_by}）` : '' }}</template></li></ul></section>
          <section v-if="capabilities.write && selected.line.status === 'active'"><h4>修改订单</h4><p v-if="requiresDispatchForEdit && !capabilities.dispatch" class="ledger__muted">该订单已发送；修改或取消需要订单发送权限。</p><div class="ledger__form"><label>数量<input v-model="amend.quantity" type="text"></label><label>客户要求交期<input v-model="amend.requested_ship_date" type="date"></label><label>备注<textarea v-model="amend.note" rows="2" /></label><label>修改原因（必填）<textarea v-model="amend.reason" rows="2" /></label><button class="ledger__button ledger__button--primary" type="button" :disabled="actionBusy || !canEdit" @click="submitAmend">保存修改</button></div></section>
          <section v-if="capabilities.dispatch && selected.line.status === 'active'"><h4>发送接收部门</h4><div class="ledger__checks"><label><input v-model="recipients" type="checkbox" value="pmc"> PMC</label><label><input v-model="recipients" type="checkbox" value="warehouse"> 仓库</label><label><input v-model="recipients" type="checkbox" value="injection"> 啤机部</label><label v-if="capabilities.cutting_dispatch_enabled"><input v-model="recipients" type="checkbox" value="cutting"> 裁床部</label></div><button class="ledger__button" type="button" :disabled="actionBusy" @click="submitDispatch">发送订单</button></section>
          <section v-if="canShip"><h4>凭出货单确认分批走货</h4><div class="ledger__form"><label>走货数量<input v-model="shipment.quantity" type="text"></label><label>走货日期<input v-model="shipment.ship_date" type="date"></label><label>出货单号<input v-model="shipment.document_no" type="text"></label><label>备注<textarea v-model="shipment.note" rows="2" /></label><button class="ledger__button ledger__button--primary" type="button" :disabled="actionBusy" @click="submitShipment">确认走货</button></div></section>
          <section><h4>走货批次与纠错</h4><p v-if="selected.shipments.length === 0" class="ledger__muted">暂无走货确认。</p><ul class="ledger__shipments"><li v-for="item in selected.shipments" :key="item.id"><span>{{ item.ship_date }} · {{ item.document_no }} · {{ item.quantity }}{{ item.reversed ? ` · 已撤销：${item.reversal_reason}` : '' }}</span><button v-if="canReverseShipment && !item.reversed" class="ledger__link" type="button" :disabled="actionBusy" @click="submitReversal(item.id)">撤销</button></li></ul><label v-if="canReverseShipment && selected.shipments.some((item) => !item.reversed)">纠错原因（撤销必填）<textarea v-model="reversalReason" rows="2" /></label></section>
          <section v-if="capabilities.write && selected.line.status === 'active'"><h4>取消订单</h4><label>取消原因（必填）<textarea v-model="cancelReason" rows="2" /></label><button class="ledger__button ledger__button--danger" type="button" :disabled="actionBusy || !canEdit" @click="submitCancel">取消该订单明细</button></section>
        </template>
      </aside>
    </div>
    <CustomerOrderHistoryImport v-if="showHistoryImport" :factory-id="factoryId" @close="showHistoryImport = false" @saved="handleHistoryMigrationSaved" />
  </section>
</template>

<style scoped>
.ledger { color: #191b23; } .ledger__header { display:flex; justify-content:space-between; gap:18px; align-items:start; margin-bottom:18px; } .ledger__header-actions{display:flex;flex-wrap:wrap;gap:8px}.ledger__header h2,.ledger__header p,.ledger h3,.ledger h4 { margin:0; } .ledger__header h2 { margin-top:4px; font-size:28px; } .ledger__header>div>p:last-child,.ledger__muted { color:#596070; font-size:13px; line-height:1.5; } .ledger__eyebrow { color:#003d9b; font-size:11px !important; font-weight:800; letter-spacing:.08em; } .ledger__filters,.ledger__checks,.ledger__pagination { display:flex; flex-wrap:wrap; gap:9px; align-items:center; margin-bottom:14px; } .ledger__pagination { justify-content:flex-end; margin-top:10px; } .ledger__pagination span { color:#596070; font-size:12px; } .ledger__filters input,.ledger__filters select,.ledger__form input,.ledger__form textarea,.ledger__detail>section>label textarea { border:1px solid #c3c6d6; border-radius:6px; padding:8px; font:inherit; } .ledger__filters input { min-width:260px; } .ledger__filters span { color:#596070; font-size:12px; } .ledger__button { border:1px solid #c3c6d6; border-radius:6px; background:#fff; padding:8px 12px; color:#303440; font-weight:800; } .ledger__button:disabled{cursor:not-allowed;opacity:.55}.ledger__button--primary { border-color:#003d9b; background:#003d9b; color:white; } .ledger__button--danger { border-color:#ba1a1a; background:#ba1a1a; color:white; } .ledger__table-wrap { overflow:auto; border:1px solid #cfd2df; border-radius:8px; background:white; } table { min-width:980px; width:100%; border-collapse:collapse; font-size:12px; } th,td { padding:11px 10px; border-bottom:1px solid #e6e7ee; text-align:left; } th { background:#f3f3fd; color:#434654; white-space:nowrap; } .mono { font-family:ui-monospace,Consolas,monospace; } .ledger__link { border:0; background:transparent; color:#003d9b; font-weight:800; } .ledger__message { margin:8px 0; color:#93000a; } .ledger__recheck { margin:10px 0; border-left:3px solid #a86500; background:#fff3dc; padding:9px; color:#6b3d00; font-size:12px; line-height:1.5; } .ledger__backdrop { position:fixed; inset:0; z-index:90; display:flex; justify-content:flex-end; background:rgb(16 20 30 / 35%); } .ledger__detail { width:min(650px,100vw); overflow:auto; background:#fff; padding:24px; box-shadow:-12px 0 28px rgb(0 0 0 / 18%); } .ledger__close { float:right; border:0; background:transparent; font-size:26px; } .ledger__detail>section { display:grid; gap:9px; margin-top:22px; padding-top:18px; border-top:1px solid #e1e2e8; } .ledger__detail h4 { font-size:15px; } .ledger__detail ul { display:grid; gap:7px; margin:0; padding-left:18px; } .ledger__detail dl { display:grid; grid-template-columns:minmax(120px,.42fr) 1fr; gap:7px 12px; margin:0; font-size:12px; } .ledger__detail dt { color:#596070; } .ledger__detail dd { margin:0; word-break:break-word; } .ledger__form { display:grid; grid-template-columns:1fr 1fr; gap:9px; } .ledger__form label,.ledger__detail>section>label { display:grid; gap:4px; color:#434654; font-size:12px; font-weight:700; } .ledger__form textarea,.ledger__form label:nth-child(3),.ledger__form label:nth-child(4) { grid-column:1 / -1; } .ledger__shipments li { display:flex; justify-content:space-between; gap:8px; } @media(max-width:700px){.ledger__header{display:grid}.ledger__filters input{min-width:0;width:100%}.ledger__form{grid-template-columns:1fr}}
.ledger__details { border:1px solid #d9dbe5; border-radius:6px; background:#fafaff; padding:9px; }
.ledger__details summary { cursor:pointer; color:#003d9b; font-size:12px; font-weight:800; }
.ledger__details dl { margin-top:10px; }
.ledger__versions { display:grid; gap:8px; }
</style>
