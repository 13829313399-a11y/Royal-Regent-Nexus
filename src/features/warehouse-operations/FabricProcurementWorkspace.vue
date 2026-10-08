<script setup lang="ts">
import { computed, inject, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { X, Truck } from '@lucide/vue'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription, DialogClose } from 'reka-ui'
import { Button } from '@/components/ui/button'
import FabricReceiptDialog from './FabricReceiptDialog.vue'
import FabricBatchReceiptDialog from './FabricBatchReceiptDialog.vue'
import CartonSelectionSummary from '@/components/CartonSelectionSummary.vue'
import { purchaseSearchKey } from './purchaseSearch'
import FabricChaseDialog from './FabricChaseDialog.vue'
import FabricPurchaseFilters from './FabricPurchaseFilters.vue'
import type { PurchaseFilters } from '@/api/fabricProcurement'
import type { FabricReceipt, ReceiveSourcesResult } from '@/api/fabricReceiving'
import { warehouseRequestId } from './requestIdentity'
import { getApiErrorMessage } from '@/lib/http'
import { fabricProcurementApi as api, type ImportAction, type PurchaseScope, type PurchasePreview, type PurchaseLine, type PurchaseDetail, type PurchaseImport, type PurchaseFacts, type PurchaseView, type TrackingSummary, type WithdrawalPreview } from '@/api/fabricProcurement'

const props = defineProps<{ mode: 'import' | 'pending' | 'orders' | 'returned' }>()
const file = ref<File>(), scope = ref<PurchaseScope>('TRACKING'), preview = ref<PurchasePreview>()
const busy = ref(false), error = ref(''), result = ref<PurchaseImport>(), confirmOpen = ref(false), acknowledged = ref(false)
const previewAction = ref<ImportAction>('ALL'), previewOffset = ref(0), requestId = ref('')
const headerSearch = inject(purchaseSearchKey, undefined)
const search = headerSearch?.search ?? ref(''), lines = ref<PurchaseLine[]>([]), total = ref<number>(), offset = ref(0)
const history = ref<PurchaseImport[]>([]), detail = ref<PurchaseDetail>(), detailOpen = ref(false)
const historyOffset = ref(0)
const pendingView = ref<PurchaseView>('OUTSTANDING'), summary = ref<TrackingSummary>()
const defaultFilters = (): PurchaseFilters => ({ supplier: '', unit: '', source_category: '', category: '', promise_from: '', promise_to: '', order_no: '', production_no: '', material_code: '', style_no: '', import_batch: '', quantity_review: '', sort: 'OVERDUE' })
const filters = ref(defaultFilters()), options = ref<{ suppliers: string[]; units: string[]; imports?: { id: string; name: string }[] }>()
const chaseSource = ref<PurchaseDetail>()
const withdrawal = ref<WithdrawalPreview>(), withdrawOpen = ref(false), withdrawReason = ref(''), withdrawConfirmed = ref(false)
const notice = ref('')
const canReceive = ref(false), receiptSource = ref<PurchaseDetail>()
const selected = ref<PurchaseLine[]>([]), batchSources = ref<PurchaseDetail[]>()
const selectedRows = computed(() => selected.value.map(line => ({ id: line.id, label: `${line.facts.order_no} · ${line.facts.material_code} · ${line.facts.material_name}` })))
const visibleIds = computed(() => lines.value.map(line => line.id))
function eligible(line: PurchaseLine) { return !line.receipt_reconciliation_required && !line.receipt_identity_review_required && !line.receipt_quantity_conflict && line.master_material?.status !== 'INACTIVE' }
const selectable = computed(() => lines.value.filter(eligible))
const allSelected = computed(() => selectable.value.length > 0 && selectable.value.every(line => selected.value.some(item => item.id === line.id)))
function removeSelected(id: string) { selected.value = selected.value.filter(line => line.id !== id) }
function selectLine(line: PurchaseLine, checked: boolean) {
  if (!checked) { removeSelected(line.id); return }
  if (!canReceive.value || !eligible(line) || selected.value.some(item => item.id === line.id)) return
  if (selected.value.length >= 50) { error.value = '一次最多选择 50 项物料，请分批登记。'; return }
  selected.value.push(line)
}
function selectPage(checked: boolean) {
  if (!checked) { selected.value = selected.value.filter(line => !selectable.value.some(item => item.id === line.id)); return }
  if (!canReceive.value) return
  const combined = [...selected.value, ...selectable.value.filter(line => !selected.value.some(item => item.id === line.id))]
  if (combined.length > 50) { error.value = '一次最多选择 50 项物料，请取消部分选择后再勾选当前页。'; return }
  selected.value = combined
}
let sequence = 0
const status = computed<Exclude<PurchaseScope, 'TRACKING'>>(() => props.mode === 'pending' ? 'PENDING' : props.mode === 'returned' ? 'RETURNED' : 'ALL')
const ready = computed(() => preview.value ? preview.value.counts.new + preview.value.counts.updated + preview.value.counts.unchanged : 0)
const actionNames = { NEW: '新增', UPDATE: '更新', UNCHANGED: '内容相同', BLOCKED: '待核对' }
const labels: Partial<Record<keyof PurchaseFacts, string>> = {
  source_category: '来源类别', supplement_no: '补数单号', style_no: '款号', workshop_group: '车间组别', release_date: '放产日期', release_date_raw: '放产日期原文',
  status: '采购来源状态',
  order_no: '采购订单号', supplier: '供应商', production_no: '生产 / 放产单号', plan_no: '计划跟踪号',
  material_code: '物料编码', old_material_code: '旧物料编码', material_name: '物料名称规格', contract_no: '合同号',
  unit: '原表单位', ordered_quantity: '订单数量', reported_received_quantity: '采购已回参考数量', unit_price: '采购单价',
  reported_received_quantity_basis: '已回数量依据',
  order_date: '订单日期', order_date_raw: '订单日期原文', supplier_reply: '供应商复期原文', supplier_reply_date: '供应商复期日期',
  second_reply: '二次复期原文', second_reply_date: '二次复期日期', delivery_detail: '交货明细原文',
  delivery_note_no: '送货单号原文', delivery_note_date: '送货单日期', delivery_note_date_raw: '送货单日期原文',
  reported_receipt_date: '原表入库日期', reported_receipt_date_raw: '原表入库日期原文', note: '备注', warehouse_note: '仓库备注', source_line_id: '采购明细 ID',
}
function shown(value: unknown) { return value === null || value === undefined || value === '' ? '未提供 / 待核对' : String(value) }
function factShown(field: string, value: unknown) { return field === 'reported_received_quantity_basis' && value === 'EMPTY_PENDING_DELIVERY' ? '未回表交货记录为空，按尚未到货处理' : field === 'source_category' ? value === 'SUPPLEMENT' ? '补数' : '正常采购' : field === 'status' && value ? (value === 'PENDING' ? '未回物料' : '已回料') : shown(value) }
function time(value: string) { return new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', dateStyle: 'short', timeStyle: 'short' }).format(new Date(value)) }
function clearImport() {
  sequence++; preview.value = undefined; result.value = undefined; confirmOpen.value = false; acknowledged.value = false; requestId.value = ''; error.value = ''; previewOffset.value = 0; previewAction.value = 'ALL'
}
function chooseFile(event: Event) {
  clearImport(); file.value = (event.target as HTMLInputElement).files?.[0]
}
watch(scope, clearImport)
async function load() {
  const ticket = ++sequence
  busy.value = true; error.value = ''; lines.value = []; total.value = undefined; history.value = []; detail.value = undefined; detailOpen.value = false; summary.value = undefined; canReceive.value = false
  try {
    if (props.mode === 'import') {
      const records = await api.imports(historyOffset.value)
      if (ticket === sequence) history.value = records
    } else {
      const data = await api.lines(status.value, search.value.trim(), offset.value, props.mode === 'pending' ? pendingView.value : undefined, filters.value)
      if (ticket === sequence) {
        lines.value = data.items; total.value = data.total; summary.value = data.summary; options.value = data.options; canReceive.value = !!data.can_receive
        if (!canReceive.value) selected.value = []
        else selected.value = selected.value.flatMap(line => { const current = data.items.find(item => item.id === line.id); return current ? eligible(current) ? [current] : [] : [line] })
      }
    }
  } catch (e) { if (ticket === sequence) error.value = getApiErrorMessage(e) }
  finally { if (ticket === sequence) busy.value = false }
}
watch(() => props.mode, () => { clearImport(); file.value = undefined; search.value = ''; filters.value = defaultFilters(); chaseSource.value = undefined; offset.value = 0; pendingView.value = 'OUTSTANDING'; withdrawOpen.value = false; withdrawal.value = undefined; receiptSource.value = undefined; batchSources.value = undefined; selected.value = []; notice.value = ''; void load() }, { immediate: true })
let searchTimer: ReturnType<typeof setTimeout> | undefined
watch(search, () => { clearTimeout(searchTimer); if (props.mode !== 'import') searchTimer = setTimeout(query, 350) })
if (headerSearch) watch(headerSearch.submitted, query)
const refreshTimer = setInterval(() => {
  if (props.mode === 'pending' && !busy.value && !detailOpen.value && !receiptSource.value && !batchSources.value && !chaseSource.value && document.visibilityState === 'visible') void load()
}, 60_000)
onBeforeUnmount(() => { sequence++; clearInterval(refreshTimer); clearTimeout(searchTimer) })
async function inspectFile(nextOffset = 0, action: ImportAction = previewAction.value) {
  if (!file.value || busy.value) return
  const ticket = ++sequence
  busy.value = true; error.value = ''; preview.value = undefined; confirmOpen.value = false; acknowledged.value = false; result.value = undefined; requestId.value = ''
  previewOffset.value = nextOffset; previewAction.value = action
  try {
    const data = await api.preview(file.value, scope.value, nextOffset, action)
    if (ticket === sequence) { preview.value = data; requestId.value = warehouseRequestId() }
  } catch (e) { if (ticket === sequence) error.value = getApiErrorMessage(e) }
  finally { if (ticket === sequence) busy.value = false }
}
async function saveImport() {
  if (!file.value || !preview.value || busy.value || !acknowledged.value || !requestId.value) return
  const ticket = ++sequence
  busy.value = true; error.value = ''
  try {
    const saved = await api.apply(file.value, scope.value, preview.value.preview_token, requestId.value, acknowledged.value)
    if (ticket === sequence) {
      result.value = saved; preview.value = undefined; confirmOpen.value = false
      history.value = []; historyOffset.value = 0
      const records = await api.imports()
      if (ticket === sequence) history.value = records
    }
  } catch (e) {
    if (ticket === sequence) {
      error.value = getApiErrorMessage(e)
      const statusCode = (e as { response?: { status?: number } }).response?.status
      if (statusCode === 401 || statusCode === 403 || statusCode === 409) { preview.value = undefined; confirmOpen.value = false; detail.value = undefined; history.value = [] }
      // Network failures keep the same request ID: a retry retrieves a committed result.
    }
  } finally { if (ticket === sequence) busy.value = false }
}
async function showDetail(id: string) {
  const ticket = ++sequence
  busy.value = true; error.value = ''; detail.value = undefined; detailOpen.value = false
  try { const data = await api.detail(id); if (ticket === sequence) { detail.value = data; detailOpen.value = true } }
  catch (e) { if (ticket === sequence) { error.value = getApiErrorMessage(e); lines.value = []; total.value = undefined } }
  finally { if (ticket === sequence) busy.value = false }
}
async function startReceive(id: string) {
  const ticket = ++sequence
  busy.value = true; error.value = ''; detailOpen.value = false
  try {
    const data = await api.detail(id)
    if (ticket === sequence) {
      if (!data.can_receive) error.value = data.receipt_reconciliation_required ? '来源物料或单位等已有变化，请核对导入和入库记录后处理。' : data.receipt_quantity_review_required ? '来源数量需核对，请检查来源文件和导入记录，修正后重新导入。' : '当前账号无登记入库权限，或来源已撤销。'
      else receiptSource.value = data
    }
  } catch (e) { if (ticket === sequence) { error.value = getApiErrorMessage(e); lines.value = []; total.value = undefined } }
  finally { if (ticket === sequence) busy.value = false }
}
async function receiptSaved(receipt: FabricReceipt) {
  receiptSource.value = undefined
  notice.value = `已保存入库单 ${receipt.id}，本次实收 ${receipt.quantity} ${receipt.unit} 已计入待检库存。`
  await load()
}
async function startBatchReceive() {
  if (busy.value || !canReceive.value || !selected.value.length) return
  clearTimeout(searchTimer)
  const ticket = ++sequence, ids = selected.value.map(line => line.id)
  busy.value = true; error.value = ''; detailOpen.value = false
  try {
    const results = await Promise.allSettled(ids.map(id => api.detail(id)))
    if (ticket !== sequence) return
    const failed = results.find(result => result.status === 'rejected')
    if (failed?.status === 'rejected') throw failed.reason
    const details = results.map(result => (result as PromiseFulfilledResult<PurchaseDetail>).value)
    const blocked = details.find(item => !item.can_receive)
    if (blocked) error.value = `${blocked.facts.order_no} · ${blocked.facts.material_code} 当前不能入库，请查看来源核对后重新选择。`
    else batchSources.value = details
  } catch (e) { if (ticket === sequence) error.value = getApiErrorMessage(e) }
  finally { if (ticket === sequence) busy.value = false }
}
async function batchSaved(result: ReceiveSourcesResult) {
  batchSources.value = undefined; selected.value = []
  notice.value = `已保存 ${result.receipts.length} 项物料的入库记录，本次实收已计入待检库存。`
  await load()
}
async function receiptStale(message: string) {
  receiptSource.value = undefined
  batchSources.value = undefined
  await load()
  error.value = message
}
async function startWithdrawal(id: string) {
  const ticket = ++sequence
  busy.value = true; error.value = ''; withdrawal.value = undefined; withdrawReason.value = ''; withdrawConfirmed.value = false
  try { const data = await api.withdrawalPreview(id); if (ticket === sequence) { withdrawal.value = data; withdrawOpen.value = true } }
  catch (e) { if (ticket === sequence) error.value = getApiErrorMessage(e) }
  finally { if (ticket === sequence) busy.value = false }
}
async function withdrawImport() {
  if (!withdrawal.value || !withdrawReason.value.trim() || !withdrawConfirmed.value || busy.value) return
  const ticket = ++sequence
  busy.value = true; error.value = ''
  try {
    await api.withdraw(withdrawal.value.id, withdrawal.value.preview_token, withdrawReason.value.trim())
    if (ticket !== sequence) return
    withdrawOpen.value = false; preview.value = undefined; result.value = undefined; requestId.value = ''
    notice.value = '已撤销本次导入，来源列表已回退；原始证据与撤销记录保留。库存未变化。'
    await load()
  } catch (e) { if (ticket === sequence) error.value = getApiErrorMessage(e) }
  finally { if (ticket === sequence) busy.value = false }
}
async function reviewChanges() {
  if (!detail.value || busy.value) return
  const ticket = ++sequence
  busy.value = true; error.value = ''
  try {
    await api.reviewChanges(detail.value.id, detail.value.revision)
    if (ticket !== sequence) return
    notice.value = '变更已标记已读；采购报到货待核对事项继续保留，未登记实收或增加库存。'
    await load()
  } catch (e) { if (ticket === sequence) error.value = getApiErrorMessage(e) }
  finally { if (ticket === sequence) busy.value = false }
}
function selectPendingView(view: PurchaseView) { pendingView.value = view; query() }
function query() { clearTimeout(searchTimer); offset.value = 0; void load() }
function clearFilters() { filters.value = defaultFilters(); search.value = ''; pendingView.value = 'OUTSTANDING'; query() }
function startChase() { if (detail.value) { chaseSource.value = detail.value; detailOpen.value = false } }
async function chaseSaved() { chaseSource.value = undefined; notice.value = '起始待收量已确认，已扣除本系统实收；库存未改变。'; await load() }
function page(delta: number) { offset.value += delta * 50; void load() }
const importTarget = { path: '/modules/pmc-warehouse/fabric-warehouse/receipts', query: { factory: 'huakang-c', view: 'import-review' } }
const importedOrdersTarget = { ...importTarget, query: { ...importTarget.query, source: 'all' } }
const returnedOrdersTarget = { ...importTarget, query: { ...importTarget.query, source: 'returned' } }
const pendingTarget = { ...importTarget, query: { factory: 'huakang-c', view: 'pending' } }
</script>

<template>
  <div class="fabric-procurement">
    <div class="warehouse-table-heading"><h2><Truck v-if="mode === 'pending'" :size="20" aria-hidden="true" />{{ mode === 'import' ? '采购订单文档导入' : mode === 'pending' ? '采购待收料' : mode === 'returned' ? '已回料历史参考' : '已导入采购订单' }}</h2><p>{{ mode === 'pending' ? '勾选本次到货物料，填写实收数量、仓位；布料同时填写缸号，可分批入库。' : '保留采购原表依据；导入订单和采购历史不增加库存。' }}</p></div>
    <p v-if="error" class="fabric-error" role="alert">{{ error }}</p>
    <p v-if="notice" class="fabric-success" role="status">{{ notice }}</p>
    <p v-if="busy" class="fabric-message" role="status">{{ mode === 'import' ? '正在读取或保存采购资料…' : '正在查询采购资料…' }}</p>
    <template v-if="mode === 'import'">
      <div class="fabric-import-controls">
        <label>采购跟踪文档<input type="file" accept=".xlsx" aria-label="选择采购跟踪文档" :disabled="busy" @change="chooseFile" /></label>
        <label>导入范围<select v-model="scope" aria-label="采购导入范围" :disabled="busy"><option value="TRACKING">正常采购与补数未回 + 已有订单变化（推荐）</option><option value="PENDING">仅正常采购与补数未回（不检查移入已回）</option><option value="RETURNED">正常采购与补数已回（历史参考）</option><option value="ALL">全部采购与补数历史 / 未回</option></select></label>
        <Button :disabled="!file || busy" @click="inspectFile(0, 'ALL')">读取并核对</Button>
      </div>
      <p class="fabric-message">支持物料跟踪表 .xlsx，最大 20 MiB / 50,000 条。导入未回物料、补数未回物料，补数独立标记。退货记录需核对是否补回，罚款记录属于扣款跟进，本次不生成待收料。缺少唯一采购明细编号时，多行变化须核对对应关系。</p>
      <p class="fabric-message">推荐范围检查已有来源是否移入已回料或补数已回；其他已回历史不新增。采购报到货会提醒仓库核对，仓库按本次实物另行登记入库。原表未出现的旧订单仍保留，不推断取消。</p>
      <div v-if="result" class="fabric-success" role="status">已保存：新增 {{ result.counts.new }} 条，更新 {{ result.counts.updated }} 条，相同 {{ result.counts.unchanged }} 条，待核对 {{ result.counts.blocked }} 条。库存未增加。</div>
      <template v-if="preview">
        <div class="fabric-preview-summary"><p>本次接入 {{ preview.counts.total }} 条 · 新增 {{ preview.counts.new }} · 更新 {{ preview.counts.updated }} · 相同 {{ preview.counts.unchanged }} · 待核对 {{ preview.counts.blocked }}</p><p>来自 {{ preview.sheets.join('、') }}。未回 {{ preview.counts.pending }} 条，已回参考 {{ preview.counts.returned }} 条；{{ preview.counts.warnings }} 条含核对提醒。</p><p v-if="preview.excluded_history">已排除 {{ preview.excluded_history }} 条未关联的已回历史，不新增到仓库来源。</p></div>
        <div class="fabric-preview-controls"><label>核对明细<select :value="previewAction" aria-label="筛选导入核对结果" :disabled="busy" @change="inspectFile(0, ($event.target as HTMLSelectElement).value as ImportAction)"><option value="ALL">全部明细</option><option value="NEW">新增</option><option value="UPDATE">更新</option><option value="UNCHANGED">内容相同</option><option value="BLOCKED">待核对</option></select></label><Button :disabled="!ready || busy" @click="confirmOpen = true">确认导入可用明细（{{ ready }}）</Button></div>
        <div class="warehouse-table-scroll" role="region" aria-label="采购导入核对明细" tabindex="0"><table><thead><tr><th>核对结果 / 来源</th><th>采购单 / 供应商</th><th>生产单 / 跟踪号</th><th>物料</th><th>订单数量</th><th>采购已回参考</th><th>单位 / 单价</th><th>核对问题 / 变化</th></tr></thead><tbody><tr v-for="row in preview.items" :key="row.row_key"><td><strong>{{ actionNames[row.action] }}</strong><small>{{ row.sheet }} 第 {{ row.row_number }} 行</small></td><td>{{ row.facts.order_no }}<small>{{ row.facts.supplier }}</small></td><td>{{ row.facts.production_no }}<small>{{ row.facts.plan_no }}</small></td><td>{{ row.facts.material_code }}<small>{{ row.facts.material_name }}</small></td><td>{{ shown(row.facts.ordered_quantity) }}</td><td>{{ shown(row.facts.reported_received_quantity) }}</td><td>{{ row.facts.unit }}<small>{{ shown(row.facts.unit_price) }}</small></td><td><p v-for="problem in row.errors" :key="problem" class="fabric-row-error">{{ problem }}</p><p v-for="warning in row.warnings" :key="warning">{{ warning }}</p><p v-for="field in row.changes" :key="field">{{ labels[field as keyof PurchaseFacts] || field }}：{{ factShown(field, row.previous?.[field as keyof PurchaseFacts]) }} → {{ factShown(field, row.facts[field as keyof PurchaseFacts]) }}</p></td></tr></tbody></table></div>
        <footer class="warehouse-list-footer"><span>当前 {{ preview.filtered_total ? previewOffset + 1 : 0 }}–{{ Math.min(previewOffset + preview.limit, preview.filtered_total) }} / {{ preview.filtered_total }} 条核对明细</span><div><Button variant="outline" size="sm" :disabled="busy || !previewOffset" @click="inspectFile(previewOffset - preview.limit)">上一页</Button><Button variant="outline" size="sm" :disabled="busy || previewOffset + preview.limit >= preview.filtered_total" @click="inspectFile(previewOffset + preview.limit)">下一页</Button></div></footer>
      </template>
      <section class="fabric-import-history">
        <nav class="fabric-import-lookups" aria-label="采购订单查询"><RouterLink :to="pendingTarget" class="fabric-import-link">查看未齐料与变更提醒</RouterLink><RouterLink :to="importedOrdersTarget" class="fabric-import-link">全部已导入来源（含历史）</RouterLink><RouterLink :to="returnedOrdersTarget" class="fabric-import-link">查看已回料历史参考</RouterLink></nav>
        <h3>最近导入记录</h3><p>误导入可撤销最近一次有效导入；有后续导入时须依次撤销。操作留痕，不删除原始证据。</p>
        <p v-if="!busy && !error && !history.length">尚未保存采购导入记录。</p>
        <ul><li v-for="batch in history" :key="batch.id" class="fabric-batch">
          <div><strong>{{ batch.source_name }}</strong><span>{{ batch.actor_name }} · {{ time(batch.occurred_at) }}</span><span>新增 {{ batch.counts.new }} / 更新 {{ batch.counts.updated }} / 相同 {{ batch.counts.unchanged }} / 待核对 {{ batch.counts.blocked }}</span>
            <p v-if="batch.withdrawal">已撤销 · {{ batch.withdrawal.actor_name }} · {{ time(batch.withdrawal.occurred_at) }} · {{ batch.withdrawal.reason }}</p>
          </div>
          <Button v-if="!batch.withdrawal && batch.can_withdraw" variant="outline" size="sm" :disabled="busy" @click="startWithdrawal(batch.id)">撤销导入</Button>
          <span v-else-if="!batch.withdrawal">有后续导入或无撤销权限</span>
        </li></ul>
        <footer class="warehouse-list-footer"><span>第 {{ historyOffset / 20 + 1 }} 页导入记录</span><div><Button variant="outline" size="sm" :disabled="busy || historyOffset === 0" @click="historyOffset -= 20; load()">较新记录</Button><Button variant="outline" size="sm" :disabled="busy || history.length < 20" @click="historyOffset += 20; load()">较早记录</Button></div></footer>
      </section>
    </template>
    <template v-else>
      <section v-if="mode === 'pending'" class="fabric-follow-up" aria-label="采购跟进提醒">
        <div class="fabric-follow-up-tabs">
          <Button variant="ghost" :aria-pressed="pendingView === 'OUTSTANDING'" :disabled="busy" @click="selectPendingView('OUTSTANDING')">未齐料 <span>{{ summary?.outstanding ?? '—' }}</span></Button>
          <Button variant="ghost" :aria-pressed="pendingView === 'ARRIVAL_REVIEW'" :disabled="busy" @click="selectPendingView('ARRIVAL_REVIEW')">采购报到货 · 待核对 <span>{{ summary?.arrival_review ?? '—' }}</span></Button>
          <Button variant="ghost" class="fabric-follow-up-overdue" :aria-pressed="pendingView === 'OVERDUE'" :disabled="busy" @click="selectPendingView('OVERDUE')">复期已过 <span>{{ summary?.overdue ?? '—' }}</span></Button>
          <Button variant="ghost" :aria-pressed="pendingView === 'DUE_TODAY'" :disabled="busy" @click="selectPendingView('DUE_TODAY')">今天到期 <span>{{ summary?.due_today ?? '—' }}</span></Button>
          <Button variant="ghost" :aria-pressed="pendingView === 'AWAITING_DATE'" :disabled="busy" @click="selectPendingView('AWAITING_DATE')">待复期 <span>{{ summary?.awaiting_date ?? '—' }}</span></Button>
          <Button variant="ghost" :aria-pressed="pendingView === 'QUANTITY_REVIEW'" :disabled="busy" @click="selectPendingView('QUANTITY_REVIEW')">起始数量待核对 <span>{{ summary?.quantity_review ?? '—' }}</span></Button>
          <Button variant="ghost" :aria-pressed="pendingView === 'CHANGED'" :disabled="busy" @click="selectPendingView('CHANGED')">订单变更 · 未读 <span>{{ summary?.changed ?? '—' }}</span></Button>
        </div>
        <p v-if="pendingView === 'ARRIVAL_REVIEW'" class="fabric-follow-up-context">采购报到货不代表仓库已确认，请按本次实物登记入库。</p>
        <p v-else-if="pendingView === 'CHANGED'" class="fabric-follow-up-context">来源详情可看前后变化；标记已读不代表完成收料。</p>
      </section>
      <FabricPurchaseFilters v-model="filters" v-model:view="pendingView" v-model:search="search" :busy="busy" :header-search="!!headerSearch" :pending="mode === 'pending'" :options="options" @query="query" @clear="clearFilters"><RouterLink :to="importTarget" class="fabric-import-link">{{ mode === 'pending' ? '订单导入' : '返回订单导入' }}</RouterLink></FabricPurchaseFilters>
      <div v-if="canReceive || selected.length" class="fabric-selection-toolbar"><CartonSelectionSummary :rows="selectedRows" :visible-ids="visibleIds" unit="项" @clear="selected = []" @remove="removeSelected" /><Button :disabled="busy || !canReceive || !selected.length" @click="startBatchReceive">登记所选订单入库<span v-if="selected.length">（{{ selected.length }}）</span></Button></div>
      <div class="warehouse-table-scroll" role="region" aria-label="采购来源列表" tabindex="0"><table class="fabric-pending-table"><thead><tr><th class="fabric-select-cell"><input v-if="canReceive" type="checkbox" aria-label="全选当前页可入库物料" :checked="allSelected" :indeterminate="!allSelected && selectable.some(line => selected.some(item => item.id === line.id))" :disabled="busy || !selectable.length" @change="selectPage(($event.target as HTMLInputElement).checked)" /></th><th>采购单 / 状态</th><th>供应商 / 复期</th><th>生产单 / 款号</th><th>物料</th><th>起始待收</th><th>本系统已入库</th><th>剩余待收</th><th>单位</th><th>办理</th></tr></thead><tbody>
        <tr v-for="line in lines" :key="line.id" :class="{ 'fabric-selected': selected.some(item => item.id === line.id) }">
          <td class="fabric-select-cell"><input v-if="canReceive && eligible(line)" type="checkbox" :aria-label="`选择 ${line.facts.order_no} · ${line.facts.material_code}`" :checked="selected.some(item => item.id === line.id)" :disabled="busy" @change="selectLine(line, ($event.target as HTMLInputElement).checked)" /></td><td>{{ line.facts.order_no }}<small>{{ line.facts.source_category === 'SUPPLEMENT' ? '补数追货' : '正常采购' }}</small><small>{{ line.tracking?.arrival_review ? '采购报到货 · 仓库待核对' : line.warehouse_outstanding_quantity === '0' || line.warehouse_outstanding_quantity === '0.0' ? '已收齐' : line.receipt_count ? '已部分收料' : '待收料' }}</small><strong v-if="line.unreviewed_changes" class="fabric-change-badge">{{ line.unreviewed_changes }} 次变更未读</strong></td>
          <td>{{ line.facts.supplier }}<small>{{ line.promise_date || line.promise_text || '待供应商复期' }}</small><strong v-if="line.tracking?.overdue" class="fabric-overdue">复期已过 {{ line.overdue_days }} 天</strong><strong v-else-if="line.tracking?.due_today" class="fabric-due-today">今天到期</strong><small v-else-if="line.warehouse_outstanding_quantity == null && line.promise_elapsed_days && line.promise_elapsed_days > 0" class="fabric-due-today">复期已过 {{ line.promise_elapsed_days }} 天 · 数量待核对</small></td><td>{{ line.facts.production_no }}<small>{{ line.facts.plan_no || line.facts.style_no }}</small></td><td>{{ line.facts.material_code }}<small>{{ line.facts.material_name }}</small><small v-if="line.material_category">{{ line.material_category === 'FABRIC' ? '布料' : line.material_category === 'ACCESSORY' ? '辅料' : '线' }}</small></td>
          <td>{{ line.starting_chase_quantity ?? '待核对' }}<small>订单总量 {{ line.facts.ordered_quantity }}</small><small v-if="line.prior_received_quantity != null">此前已回 {{ line.prior_received_quantity }}</small></td><td>{{ line.warehouse_received_quantity ?? '0' }}</td><td><strong>{{ line.warehouse_outstanding_quantity ?? '待核对' }}</strong><small v-if="line.receipt_quantity_review_required">{{ line.receipt_quantity_conflict ? '数量来源冲突，先核对' : '到货记录不明确 · 可按实物收料' }}</small><strong v-if="line.receipt_reconciliation_required">来源身份已变，须核对</strong></td><td>{{ line.facts.unit }}</td><td><div class="fabric-row-actions"><Button v-if="canReceive && eligible(line)" size="sm" :disabled="busy" @click="startReceive(line.id)">登记入库</Button><Button variant="outline" size="sm" :disabled="busy" @click="showDetail(line.id)">来源 / 核对</Button></div></td>
        </tr>
      </tbody></table></div>
      <p v-if="total === 0 && !busy" class="fabric-message" role="status">{{ search ? '没有匹配的采购明细，请调整查询条件。' : mode === 'pending' ? '当前跟进范围没有记录，可切换范围查看或导入最新跟踪表。' : '尚未导入该范围的采购明细。' }}</p>
      <footer v-if="total !== undefined" class="warehouse-list-footer"><span>共 {{ total }} 条 · {{ total ? offset + 1 : 0 }}–{{ Math.min(offset + 50, total) }}</span><div><Button variant="outline" size="sm" :disabled="busy || offset === 0" @click="page(-1)">上一页</Button><Button variant="outline" size="sm" :disabled="busy || offset + 50 >= total" @click="page(1)">下一页</Button></div></footer>
    </template>
    <DialogRoot v-model:open="confirmOpen"><DialogPortal><DialogOverlay class="warehouse-guide-overlay" /><DialogContent class="warehouse-guide fabric-confirm"><DialogTitle>确认保存采购来源</DialogTitle><DialogDescription>保存所选工作表全部可用明细，包括核对表的其他分页。待核对行本次跳过，采购已回料只作历史参考，库存不会增加。</DialogDescription><p v-if="preview">新增 {{ preview.counts.new }} 条，更新 {{ preview.counts.updated }} 条，相同 {{ preview.counts.unchanged }} 条，跳过待核对 {{ preview.counts.blocked }} 条。</p><label><input v-model="acknowledged" type="checkbox" :disabled="busy" />已核对数量、单位、来源和更新差异，确认仅保存可用明细</label><p v-if="error" class="fabric-error" role="alert">{{ error }}</p><div class="fabric-dialog-actions"><DialogClose as-child><Button variant="outline" :disabled="busy">返回核对</Button></DialogClose><Button :disabled="busy || !acknowledged" @click="saveImport">{{ busy ? '正在保存…' : '保存采购来源' }}</Button></div></DialogContent></DialogPortal></DialogRoot>
    <DialogRoot v-model:open="withdrawOpen"><DialogPortal><DialogOverlay class="warehouse-guide-overlay" /><DialogContent class="warehouse-guide fabric-confirm">
      <DialogTitle>撤销这次导入</DialogTitle><DialogDescription>将本次新增来源移出业务列表，并恢复本次更新前的来源内容。原始证据与操作记录保留，库存不会变化。</DialogDescription>
      <template v-if="withdrawal"><strong>{{ withdrawal.source_name }}</strong><p>移出新增来源 {{ withdrawal.remove_count }} 条；恢复原有来源 {{ withdrawal.restore_count }} 条。</p></template>
      <label>撤销原因<input v-model="withdrawReason" aria-label="撤销导入原因" maxlength="500" :disabled="busy" placeholder="例如：选错文件，需要重新导入" /></label>
      <label><input v-model="withdrawConfirmed" type="checkbox" :disabled="busy" />已核对上述影响，确认撤销</label>
      <p v-if="error" class="fabric-error" role="alert">{{ error }}</p>
      <div class="fabric-dialog-actions"><DialogClose as-child><Button variant="outline" :disabled="busy">保留导入</Button></DialogClose><Button :disabled="busy || !withdrawConfirmed || !withdrawReason.trim()" @click="withdrawImport">确认撤销导入</Button></div>
    </DialogContent></DialogPortal></DialogRoot>
    <DialogRoot v-model:open="detailOpen"><DialogPortal><DialogOverlay class="warehouse-guide-overlay" /><DialogContent class="warehouse-guide"><header class="warehouse-guide-heading"><div><DialogTitle>采购来源详情</DialogTitle><DialogDescription>原表采购事实与历次保存依据；采购已回数量只供核对。</DialogDescription></div><DialogClose class="warehouse-guide-close" aria-label="关闭采购来源详情"><X :size="20" /></DialogClose></header><div v-if="detail" class="warehouse-guide-body"><div class="fabric-source-chase"><p>起始待收 <strong>{{ detail.starting_chase_quantity ?? '待核对' }}</strong> − 本系统已入库 <strong>{{ detail.warehouse_received_quantity ?? '0' }}</strong> = 剩余待收 <strong>{{ detail.warehouse_outstanding_quantity ?? '待核对' }} {{ detail.facts.unit }}</strong></p><Button v-if="detail.can_review && !detail.receipt_identity_review_required && detail.active" variant="outline" :disabled="busy" @click="startChase">核对起始待收量</Button></div><section v-if="detail.chase_resolution_history?.length" class="fabric-source-evidence"><h3>起始数量核对记录</h3><p v-for="entry in detail.chase_resolution_history" :key="entry.id">第 {{ entry.revision }} 次：起始 {{ entry.starting_quantity }} {{ detail.facts.unit }} · {{ entry.actor_name }} · {{ time(entry.occurred_at) }}<br />{{ entry.evidence }}<br />确认时本系统已入库 {{ entry.cutoff.warehouse_received_at_confirmation }} {{ detail.facts.unit }}，计算仍扣除本系统全部实收。</p></section><dl class="fabric-facts"><template v-for="(label, field) in labels" :key="field"><dt>{{ label }}</dt><dd>{{ factShown(field, detail.facts[field]) }}</dd></template></dl><p v-if="detail.tracking?.arrival_review" class="fabric-success">采购已报到货，仍须核对仓库实收；此处不增加库存。</p><Button v-if="detail.unreviewed_changes && detail.can_review" :disabled="busy" @click="reviewChanges">将变更标记已读（不确认收料）</Button><p v-if="error" class="fabric-error" role="alert">{{ error }}</p><h3>来源与变化记录（最近 100 次）</h3><section v-for="source in detail.evidence" :key="source.id || `${source.occurred_at}-${source.row_number}`" class="fabric-source-evidence"><h4>{{ source.source_name }}<span v-if="source.withdrawal"> · 此次导入已撤销</span></h4><p>{{ source.sheet }} 第 {{ source.row_number }} 行 · {{ source.actor_name }} · {{ time(source.occurred_at) }}</p><template v-if="Object.keys(source.before).length"><p v-for="(label, field) in labels" :key="field"><template v-if="source.before[field] !== source.after[field]">{{ label }}：{{ factShown(field, source.before[field]) }} → {{ factShown(field, source.after[field]) }}</template></p></template><p v-else>首次保存采购来源。</p></section></div></DialogContent></DialogPortal></DialogRoot>
  </div>
  <FabricChaseDialog v-if="chaseSource" :source="chaseSource" @close="chaseSource = undefined" @saved="chaseSaved" @stale="message => { chaseSource = undefined; receiptStale(message) }" />
  <FabricBatchReceiptDialog v-if="batchSources" :sources="batchSources" @close="batchSources = undefined" @saved="batchSaved" @stale="receiptStale" />
  <FabricReceiptDialog v-if="receiptSource" :source="receiptSource" @close="receiptSource = undefined" @saved="receiptSaved" @stale="receiptStale" />
</template>
