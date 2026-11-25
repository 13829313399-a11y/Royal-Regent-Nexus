<script setup lang="ts">
import { computed, inject, nextTick, onBeforeUnmount, ref, useId, watch } from 'vue'
import { parseDate } from '@internationalized/date'
import type { DateRange } from 'reka-ui'
import DateRangeFilter from '@/components/DateRangeFilter.vue'
import { RouterLink, onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { isAxiosError } from 'axios'
import { FocusScope } from 'reka-ui'
import { FileText } from '@lucide/vue'
import WarehouseDetailDialog from '@/features/warehouse-foundation/WarehouseDetailDialog.vue'
import WarehouseStockLedger from './WarehouseStockLedger.vue'
import { matchesLocationCategory } from './fabricLocationZones'
import WarehouseLocationPicker from './WarehouseLocationPicker.vue'
import WarehouseBulkIssueDialog from './WarehouseBulkIssueDialog.vue'
import FabricIssueGroupDialog from './FabricIssueGroupDialog.vue'
import FabricMovementDetail from './FabricMovementDetail.vue'
import SemiOrderProgress from './SemiOrderProgress.vue'
import SemiOrderTrace from './SemiOrderTrace.vue'
import { Button } from '@/components/ui/button'
import { getApiErrorMessage } from '@/lib/http'
import { formatBusinessDateTime } from '@/lib/dateTime'
import { warehouseOperationsApi as api, type CuttingReturnLimit, type WarehouseBatch, type WarehouseDocument, type WarehouseDocumentInput, type WarehouseDomain, type WarehouseOperationsWorkspace } from '@/api/warehouseOperations'
import { warehouseRequestId } from './requestIdentity'
import { documentProgress, remaining, fabricOperationLabel, hasUnissuedRemainder, operationLabels, operationsView, pendingHandoffQuantity, referenceKinds } from './operations'
import { inventorySearchKey, exceptionSearchKey } from './inventorySearch'
import { FABRIC_RECORD_KIND_BY_VIEW, WAREHOUSE_FACTORY, WAREHOUSE_HOME } from './navigation'
import { fabricIssueNoteHtml } from './fabricIssueNotePrint'
import { fabricIssueCsv } from './fabricIssueCsv'

const props = defineProps<{ warehouse: WarehouseDomain; section: string; view: string; title?: string; description?: string }>()
const route = useRoute()
const router = useRouter()
const data = ref<WarehouseOperationsWorkspace>(), loading = ref(false), saving = ref(false), error = ref(''), success = ref('')
const recordFilterId = 'warehouse-record-filter-' + useId()
const recordSearchInput = ref<HTMLInputElement>()
const localSearch = ref(''), offset = ref(0), from = ref(''), to = ref('')
const dates = computed<DateRange>({
  get: () => ({ start: from.value ? parseDate(from.value) : undefined, end: to.value ? parseDate(to.value) : undefined }),
  set: value => { from.value = value.start?.toString() ?? ''; to.value = value.end?.toString() ?? '' },
})
const inventoryHeader = inject(props.section === 'exceptions' ? exceptionSearchKey : inventorySearchKey, undefined)
const fabricInventory = computed(() => props.warehouse === 'fabric' && props.section === 'inventory')
const fabricExceptions = computed(() => props.warehouse === 'fabric' && props.section === 'exceptions')
const fabricFilters = computed(() => fabricInventory.value || fabricExceptions.value)
const correctionActors = computed(() => [...new Set((data.value?.documents ?? []).filter(row => row.kind === 'CORRECTION').map(row => row.actor_name))].sort((a, b) => a.localeCompare(b, 'zh-CN')))
const recordActor = ref('')
const originalKindLabels: Record<string, string> = { RECEIPT: '入库', ISSUE: '出库', TRANSFER: '调仓' }
const useHeaderSearch = computed(() => fabricFilters.value && inventoryHeader?.active.value)
const search = computed({ get: () => useHeaderSearch.value ? inventoryHeader!.search.value : localSearch.value, set: value => { if (useHeaderSearch.value) inventoryHeader!.search.value = value; else localSearch.value = value } })
const localRecordKind = ref(''), recordState = ref(''), recordSort = ref('DATE_DESC')
const movementKindLabels: Record<string, string> = { RECEIPT: '入库', ISSUE: '出库', TRANSFER: '调仓', RETURN: '车间退料', CORRECTION: '单据冲销', OPENING: '期初库存', STOCKTAKE: '盘点差异' }
const recordKinds = Object.keys(movementKindLabels)
const fabricMovements = computed(() => fabricInventory.value && props.view === 'movements')
const recordKind = computed({
  get: () => {
    if (!fabricMovements.value) return localRecordKind.value
    const legacyKind = typeof route.query.view === 'string' ? FABRIC_RECORD_KIND_BY_VIEW[route.query.view] : undefined
    const kind = legacyKind ?? route.query.kind
    return typeof kind === 'string' && recordKinds.includes(kind) ? kind : ''
  },
  set: (kind: string) => {
    if (fabricMovements.value) void router.replace({ path: route.path, query: { ...route.query, view: 'movements', kind: kind || undefined, record: undefined } })
    else localRecordKind.value = kind
  },
})
async function resetRecordFilters() {
  search.value = ''
  from.value = ''
  to.value = ''
  recordKind.value = ''
  recordState.value = ''
  recordSort.value = 'DATE_DESC'
  recordActor.value = ''
  if (!fabricMovements.value) return
  await nextTick()
  if (!fabricMovements.value) return
  if (useHeaderSearch.value) inventoryHeader?.focus?.()
  else recordSearchInput.value?.focus()
}
const recordFiltersActive = computed(() => !!(search.value || from.value || to.value || recordKind.value || recordState.value || recordActor.value || recordSort.value !== 'DATE_DESC'))
function matchesRecordState(row: WarehouseDocument) {
  if (!recordState.value) return true
  if (props.view === 'pending-issues') {
    if (row.reversed) return recordState.value === 'REVERSED'
    return recordState.value !== 'REVERSED' && (Number(remaining(row.data.quantity, row.issued_quantity)) > 0) === (recordState.value === 'PENDING')
  }
  return Boolean(row.reversed) === (recordState.value === 'REVERSED')
}
const draft = ref<WarehouseDocumentInput>(), detail = ref<WarehouseDocument>(), frozen = ref<WarehouseDocumentInput>()
const progressId = ref('')
const orderScope = ref('')
const progressList = ref<HTMLElement>()
let progressTrigger: HTMLElement | undefined
const printError = ref('')
watch(detail, () => { printError.value = '' })
let openedRecord = ''
watch(() => [route.query.record, props.warehouse, props.section, props.view, data.value, loading.value], () => {
  const id = typeof route.query.record === 'string' ? route.query.record : ''
  if (!id) { openedRecord = ''; return }
  if (draft.value || id === openedRecord || (!fabricInventory.value && !handoffView.value)) return
  if (handoffView.value && loading.value) return
  const allowedKinds = handoffView.value ? [props.view === 'processing' ? 'PROCESS_SEND' : 'PACK_SEND']
    : fabricMovements.value ? ['RECEIPT', 'ISSUE'] : props.view === 'pending-issues' ? ['REQUEST'] : []
  const row = data.value?.documents.find(row => row.id === id && allowedKinds.includes(row.kind))
  if (row) { detail.value = row; openedRecord = id }
}, { flush: 'post' })
const correctionTarget = ref<WarehouseDocument>()
const fixedOriginal = ref(false)
const returnOriginal = computed(() => draft.value?.kind === 'RETURN' ? data.value?.documents.find(row => row.id === draft.value?.original_id) : undefined)
const cuttingRequests = computed(() => new Set(data.value?.documents.filter(row => row.kind === 'REQUEST' && row.data.cutting_request).map(row => row.id)))
const cuttingIssue = (row: WarehouseDocument) => props.warehouse === 'fabric' && (row.cutting_return_limit != null || cuttingRequests.value.has(row.data.original_id))
const cuttingReturnId = computed(() => returnOriginal.value && cuttingIssue(returnOriginal.value) ? returnOriginal.value.id : '')
const returnLimit = ref<CuttingReturnLimit>(), returnLimitLoading = ref(false), returnLimitError = ref(''), returnLimitRetry = ref(0)
const returnDay = computed(() => draft.value?.business_date ?? '')
const validReturnLimit = computed(() => returnLimit.value?.day === returnDay.value ? returnLimit.value : undefined)
watch([cuttingReturnId, returnDay, data, returnLimitRetry], async ([id, day], _, onCleanup) => {
  let current = true
  onCleanup(() => { current = false })
  returnLimit.value = undefined; returnLimitError.value = ''; returnLimitLoading.value = Boolean(id && day)
  if (!id || !day) return
  try { const result = await api.cuttingReturnLimit(id, day); if (current) returnLimit.value = result }
  catch (e) { if (current) returnLimitError.value = getApiErrorMessage(e) }
  finally { if (current) returnLimitLoading.value = false }
}, { flush: 'sync' })
const returnQuantityExceeded = computed(() => {
  const amount = draft.value?.quantity?.trim() ?? ''
  return !!validReturnLimit.value && /^\d+(?:\.\d{1,6})?$/.test(amount)
    && remaining(validReturnLimit.value.quantity, amount).startsWith('-')
})
const cuttingReturnBlocked = computed(() => Boolean(cuttingReturnId.value &&
  (returnLimitLoading.value || !validReturnLimit.value || Number(validReturnLimit.value.quantity) <= 0 || returnQuantityExceeded.value)))
const formError = ref(''), initial = ref(''), fixedBatch = ref(false)
const fixedIssueRequest = ref(false)
const bulkRows = ref<WarehouseBatch[]>()
const issueGroupOpen = ref(false)
const activeLocations = computed(() => (data.value?.locations ?? []).filter(row => row.status === 'ACTIVE'))
const formElement = ref<HTMLElement>()
watch(() => !!draft.value, async open => { if (open) { await nextTick(); formElement.value?.querySelector<HTMLElement>('button')?.focus() } })
let sequence = 0
const config = computed(() => operationsView(props.warehouse, props.section, props.view)!)
const stockMode = computed(() => config.value.stock)
const orderProgressMode = computed(() => !!config.value.progress)
const pendingReceipts = computed(() => orderProgressMode.value && props.section === 'receipts')
const handoffView = computed(() => props.warehouse === 'semi' && props.section === 'inventory' && ['processing', 'packaging'].includes(props.view))
const pendingHandoffs = ref(false)
watch(() => [handoffView.value, route.query.followup], () => {
  pendingHandoffs.value = handoffView.value && route.query.followup === 'pending'
}, { immediate: true })
const releases = computed(() => props.warehouse === 'semi'
  ? (data.value?.documents ?? []).filter(row => row.kind === 'SEMI_RELEASE' && !row.reversed) : [])
const progress = computed(() => data.value?.order_progress?.find(row => row.release_id === progressId.value))
const progressRelease = computed(() => releases.value.find(row => row.id === progressId.value))
const linkedProgressId = computed(() => orderProgressMode.value && typeof route.query.release === 'string' ? route.query.release : '')
const linkedProgress = computed(() => data.value?.order_progress?.find(row => row.release_id === linkedProgressId.value))
let openedProgress = ''
watch([linkedProgressId, linkedProgress, loading], ([id, linked, busy]) => {
  if (!id) { openedProgress = ''; return }
  if (!busy && linked && !draft.value && id !== openedProgress) {
    progressTrigger = undefined
    progressId.value = id
    openedProgress = id
  }
}, { flush: 'post' })
const progressDocuments = computed(() => {
  if (!progress.value) return []
  const ids = new Set(progress.value.document_ids)
  return (data.value?.documents ?? []).filter(row => ids.has(row.id))
})
const progressHasStock = computed(() => data.value?.stock.some(row => row.release_id === progressId.value && Number(row.available_quantity) > 0) ?? false)
const progressHasTask = computed(() => data.value?.documents.some(row => row.kind === 'TASK' && !row.reversed
  && row.data.release_id === progressId.value
  && Number(remaining(row.data.quantity, row.received_quantity)) > 0) ?? false)
const linkedRelease = computed(() => releases.value.find(row => row.id === draft.value?.release_id))
const releaseUnavailable = computed(() => !!draft.value?.release_id && !linkedRelease.value)
const linkedReceipt = computed(() => draft.value?.kind === 'RECEIPT' && !!draft.value.release_id)
const detailOriginal = computed(() => data.value?.documents.find(row => row.id === detail.value?.data.original_id))
const detailHandoffAction = computed(() => {
  const row = detail.value
  if (!handoffView.value || !row || !pendingHandoffQuantity(row)) return undefined
  return row.kind === 'PROCESS_SEND' ? 'PROCESS_RETURN' : 'PACK_RECEIVE'
})
const detailRelease = computed(() => detail.value?.kind === 'SEMI_RELEASE' ? detail.value
  : data.value?.documents.find(row => row.id === detail.value?.data.release_id && row.kind === 'SEMI_RELEASE'))
const datesMatch = (value: string) => (!from.value || value >= from.value) && (!to.value || value <= to.value)
const matches = (value: unknown) => JSON.stringify(value).toLocaleLowerCase().includes(search.value.trim().toLocaleLowerCase())
const records = computed(() => {
  const movements = props.section === 'inventory' && props.view === 'movements'
  const rows = [...(data.value?.documents ?? []), ...(movements ? data.value?.original_receipts ?? [] : [])]
  return rows.filter(row => (!movements || ['RECEIPT', 'ISSUE', 'RETURN', 'TRANSFER', 'CORRECTION', 'OPENING', 'STOCKTAKE', 'PROCESS_SEND', 'PROCESS_RETURN', 'PACK_SEND'].includes(row.kind))
    && (!pendingHandoffs.value || !!pendingHandoffQuantity(row))
    && (!config.value.kinds.length || config.value.kinds.includes(row.kind)) && matches(row) && datesMatch(row.business_date)
    && (!fabricFilters.value || ((!recordKind.value || (fabricExceptions.value ? row.data.reversed_kind : row.kind) === recordKind.value) && matchesRecordState(row) && (!recordActor.value || row.actor_name === recordActor.value))))
    .sort((a, b) => (b.business_date.localeCompare(a.business_date) || b.sequence - a.sequence) * (fabricFilters.value && recordSort.value === 'DATE_ASC' ? -1 : 1))
})
const count = computed(() => records.value.length)
const issueRecords = computed(() => records.value.filter(row => row.kind === 'ISSUE'))
const visibleRecords = computed(() => records.value.slice(offset.value, offset.value + 50))
const needsBatch = computed(() => !!draft.value && ['ISSUE', 'TRANSFER', 'QUALITY', 'PROCESS_SEND', 'PACK_SEND', 'LOCATION_BIND'].includes(draft.value.kind))
const needsItem = computed(() => !!draft.value && ['RECEIPT', 'REQUEST', 'TASK', 'SEMI_RELEASE'].includes(draft.value.kind))
const needsLocation = computed(() => !!draft.value && ['RECEIPT', 'RETURN', 'TRANSFER', 'PROCESS_RETURN', 'LOCATION_BIND'].includes(draft.value.kind))
const selectedBatch = computed(() => data.value?.stock.find(row => row.id === draft.value?.batch_id))
const locationCategory = computed(() => {
  if (props.warehouse !== 'fabric' || draft.value?.kind === 'LOCATION_BIND') return undefined
  if (draft.value?.kind === 'RETURN') {
    const original = data.value?.documents.find(row => row.id === draft.value?.original_id)
    return original?.batch_snapshot?.material_category ?? original?.data.material_category ?? ''
  }
  if (draft.value?.kind === 'TRANSFER') return selectedBatch.value?.material_category ?? ''
  return draft.value?.material_category ?? ''
})
const fabricIssue = computed(() => props.warehouse === 'fabric' && draft.value?.kind === 'ISSUE')
function matchesIssueRequest(batch: WarehouseBatch, request: WarehouseDocument) {
  const item = request.data
  return batch.item_code === item.item_code && batch.unit === item.unit
    && (batch.process_state ?? '') === (item.process_state ?? '')
    && (!item.cutting_request || (batch.item_name === item.item_name && batch.material_category === item.material_category))
}
function canCloseRequest(row: WarehouseDocument) {
  return !!row.data.cutting_request && hasUnissuedRemainder(row)
}
const originalOptions = computed(() => (data.value?.documents ?? []).filter(row =>
  !row.reversed && !row.closed && (draft.value?.kind !== 'REQUEST_CLOSE' || canCloseRequest(row))
  && (row.kind !== 'TASK' || !!row.data.release_id)
  && (!orderScope.value || row.data.release_id === orderScope.value || row.id === orderScope.value)
  && referenceKinds(draft.value?.kind ?? 'RECEIPT').includes(row.kind)
  && (!fabricIssue.value || (hasUnissuedRemainder(row)
    && (!fixedBatch.value || !selectedBatch.value || matchesIssueRequest(selectedBatch.value, row))))))
const linkedFabricIssue = computed(() => fabricIssue.value && !!draft.value?.original_id)
const linkedIssueRequest = computed(() => linkedFabricIssue.value
  ? originalOptions.value.find(row => row.id === draft.value?.original_id)
  : undefined)
const tasks = computed(() => {
  const scope = orderScope.value || selectedBatch.value?.release_id
  return (data.value?.documents ?? []).filter(row => row.kind === 'TASK' && !row.reversed
    && ((!orderScope.value && !selectedBatch.value) || row.data.release_id === scope)
    && (!orderScope.value || Number(remaining(row.data.quantity, row.received_quantity)) > 0))
})
const selectedTask = computed(() => tasks.value.find(row => row.id === draft.value?.task_id))
const selectableBatches = computed(() => (data.value?.stock ?? []).filter(row =>
  Number(row.quantity) > 0 && (draft.value?.kind === 'LOCATION_BIND' ? !row.location_verified : row.location_verified)
  && (!orderScope.value || row.release_id === orderScope.value)
  && (!selectedTask.value || row.release_id === selectedTask.value.data.release_id)
  && (['TRANSFER', 'LOCATION_BIND'].includes(draft.value?.kind ?? '') || !['HOLD', 'REJECTED'].includes(row.quality_status))
  && (!linkedFabricIssue.value || (linkedIssueRequest.value && matchesIssueRequest(row, linkedIssueRequest.value)))))
const linkedIssueBatchBlocked = computed(() => linkedFabricIssue.value
  && !selectableBatches.value.some(row => row.id === draft.value?.batch_id))
const soleIssueBatch = computed(() => fixedIssueRequest.value && selectableBatches.value.length === 1
  ? selectableBatches.value[0] : undefined)
function issueChoiceLabels<T extends { id: string }>(rows: T[], label: (row: T) => string, source: (row: T) => string) {
  const choices = rows.map(row => ({ row, text: label(row) }))
  const counts = new Map<string, number>()
  for (const { text } of choices) counts.set(text, (counts.get(text) ?? 0) + 1)
  return new Map(choices.map(({ row, text }) => [row.id, counts.get(text) === 1
    ? text
    : [text, source(row), row.id.slice(-8)].filter(Boolean).join(' · ')]))
}
const issueRequestLabels = computed(() => issueChoiceLabels(originalOptions.value, ({ data: item }) => {
  const order = item.cutting_request?.order_no
  const reference = order ? `订单 ${order}` : item.production_no ? `放产单 ${item.production_no}` : item.source_no
  const task = item.cutting_request?.task_name
  return [item.item_name, item.item_code, reference, task && `裁床任务 ${task}`].filter(Boolean).join(' · ')
}, row => row.data.cutting_request ? row.business_date : row.data.source_no))
const issueBatchLabels = computed(() => issueChoiceLabels(selectableBatches.value, row => [
  !linkedFabricIssue.value && row.item_name,
  !linkedFabricIssue.value && row.item_code,
  row.location_label || row.location,
  row.lot && `${row.material_category === 'FABRIC' ? '缸号' : '批号'} ${row.lot}`,
  row.roll_no && `卷号 ${row.roll_no}`,
  `可发 ${row.available_quantity} ${row.unit}`,
].filter(Boolean).join(' · '), row => row.source_no || row.received_on))
const dirty = computed(() => !!draft.value && JSON.stringify(draft.value) !== initial.value)
function permitted(kind: WarehouseDocumentInput['kind']) { return kind !== 'QUALITY' && !!data.value?.permissions[['CORRECTION', 'LOCATION_BIND'].includes(kind) ? 'correct' : 'operate'] }
async function load() {
  const ticket = ++sequence
  loading.value = true; error.value = ''
  try {
    const includeCuttingReturns = fabricInventory.value && ['issues', 'movements'].includes(props.view)
    const result = await api.workspace(props.warehouse, includeCuttingReturns, orderProgressMode.value)
    if (ticket === sequence) data.value = result
  }
  catch (e) { if (ticket === sequence) { data.value = undefined; error.value = getApiErrorMessage(e) } }
  finally { if (ticket === sequence) loading.value = false }
}
function begin(kind: WarehouseDocumentInput['kind'], batchId = '') {
  if (!permitted(kind) || !data.value) return
  const businessDate = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date())
  correctionTarget.value = undefined
  orderScope.value = ''
  fixedOriginal.value = false
  fixedIssueRequest.value = false
  fixedBatch.value = !!batchId
  draft.value = { factory_id: 'huakang-c', request_id: warehouseRequestId(), expected_revision: data.value.revision, kind, business_date: businessDate,
    source_system: 'MANUAL', source_no: '', source_line: kind === 'SEMI_RELEASE' ? '' : '1', source_version: '', item_code: '', item_name: '', unit: '', process_state: '', material_category: 'FABRIC',
    location: '', location_id: '', confirmed: false, lot: '', roll_no: '', quantity: '', consumed_quantity: '', counterparty: '', production_no: '', purpose: '', due_date: null,
    batch_id: batchId, original_id: '', task_id: '', quality_status: 'PENDING_INSPECTION', responsible_person: '', reason: '', allocations: [] }
  initial.value = JSON.stringify(draft.value); formError.value = ''; frozen.value = undefined
}
function openProgress(id: string, event: MouseEvent) {
  progressTrigger = event.currentTarget instanceof HTMLElement ? event.currentTarget : undefined
  progressId.value = id
}
function closeProgress() { progressId.value = '' }
function restoreProgressFocus(event: Event) {
  event.preventDefault()
  if (!progressId.value && !draft.value && !detail.value) void nextTick(() => (progressTrigger ?? progressList.value?.querySelector('input'))?.focus())
}
function keepDialogFocus(event: Event) {
  if (draft.value || progressId.value || detail.value) event.preventDefault()
}
function beginFromOriginal(kind: WarehouseDocumentInput['kind'], original: WarehouseDocument, releaseId = '') {
  if (loading.value || !permitted(kind)) return false
  begin(kind)
  if (!draft.value) return false
  orderScope.value = releaseId
  draft.value.original_id = original.id
  if (kind === 'CORRECTION') {
    correctionTarget.value = original
    if (props.warehouse === 'fabric') draft.value.source_no = original.data.source_no
  } else if (kind !== 'REQUEST_CLOSE') {
    fixedIssueRequest.value = kind === 'ISSUE' && props.warehouse === 'fabric'
    fixedOriginal.value = kind !== 'ISSUE'
    selectOriginal()
    if (soleIssueBatch.value) draft.value.batch_id = soleIssueBatch.value.id
  }
  initial.value = JSON.stringify(draft.value)
  return true
}
function beginHandoffFromDetail() {
  const original = detail.value, kind = detailHandoffAction.value
  if (original && kind && beginFromOriginal(kind, original)) detail.value = undefined
}
function issueFromDetail() {
  const request = detail.value
  if (request && hasUnissuedRemainder(request) && beginFromOriginal('ISSUE', request)) detail.value = undefined
}
function selectRelease() {
  if (draft.value?.kind !== 'RECEIPT') return
  const source = linkedRelease.value?.data
  draft.value.production_no = source?.production_no ?? ''
  draft.value.item_code = source?.item_code ?? ''
  draft.value.item_name = source?.item_name ?? ''
  draft.value.unit = source?.unit ?? ''
  draft.value.process_state = source?.process_state ?? ''
}
function beginForOrder(kind: WarehouseDocumentInput['kind'], original?: WarehouseDocument) {
  const release = progressRelease.value
  if (!release || !permitted(kind) || loading.value) return
  if (original) { beginFromOriginal(kind, original, release.id); return }
  begin(kind)
  if (!draft.value) return
  orderScope.value = release.id
  if (kind === 'RECEIPT' || kind === 'TASK') {
    draft.value.release_id = release.id
    draft.value.production_no = release.data.production_no
    selectRelease()
  }
  initial.value = JSON.stringify(draft.value)
}
function selectProcessingBatch() {
  if (draft.value?.kind === 'PROCESS_SEND' && !selectedTask.value) draft.value.task_id = ''
}
function issueRequest(row: WarehouseDocument) { beginFromOriginal('ISSUE', row) }
function closeRequest(row: WarehouseDocument) { beginFromOriginal('REQUEST_CLOSE', row) }
function isReturnableIssue(row: WarehouseDocument) {
  return fabricInventory.value && ['issues', 'movements'].includes(props.view) && row.kind === 'ISSUE' && !row.read_only && !row.reversed
    && (cuttingIssue(row) || Number(remaining(row.data.quantity, row.returned_quantity)) > 0)
}
function returnIssue(row: WarehouseDocument) {
  if (isReturnableIssue(row)) beginFromOriginal('RETURN', row)
}
function canCorrectMovement(row: WarehouseDocument) {
  return props.warehouse === 'fabric' && row.kind !== 'RECEIPT' && !row.read_only && !row.reversed && referenceKinds('CORRECTION').includes(row.kind)
}
function correct(row: WarehouseDocument) {
  if (canCorrectMovement(row)) beginFromOriginal('CORRECTION', row)
}
function selectOriginal() {
  if (!draft.value) return
  const original = data.value?.documents.find(row => row.id === draft.value?.original_id)
  draft.value.counterparty = original?.data.counterparty ?? ''
  if (!fixedBatch.value && draft.value.batch_id && linkedIssueBatchBlocked.value) {
    draft.value.batch_id = ''
    draft.value.quantity = ''
  }
}
function canLeave() {
  if (saving.value || frozen.value) { formError.value = '本次保存结果尚未确认，请使用原内容重试。'; return false }
  return !dirty.value || window.confirm('当前单据尚未保存，离开将丢失填写内容。确定离开？')
}
function close() { if (canLeave()) { draft.value = undefined; frozen.value = undefined } }
onBeforeRouteLeave(canLeave)
onBeforeRouteUpdate(canLeave)
function beforeUnload(event: BeforeUnloadEvent) { if (dirty.value || saving.value || frozen.value) { event.preventDefault(); event.returnValue = '' } }
window.addEventListener('beforeunload', beforeUnload)
onBeforeUnmount(() => { sequence++; window.removeEventListener('beforeunload', beforeUnload) })
watch(() => [props.warehouse, props.section, props.view], () => {
  closeProgress(); orderScope.value = ''; openedProgress = ''; openedRecord = ''
  draft.value = undefined; detail.value = undefined; bulkRows.value = undefined; frozen.value = undefined; success.value = ''; localSearch.value = ''; from.value = ''; to.value = ''; localRecordKind.value = ''; recordState.value = ''; recordSort.value = 'DATE_DESC'; recordActor.value = ''; offset.value = 0; void load()
}, { immediate: true })
watch([search, from, to, recordKind, recordState, recordSort, recordActor, pendingHandoffs], () => { offset.value = 0 })
async function submit() {
  if (!draft.value || saving.value || (!frozen.value && !permitted(draft.value.kind))) return
  if (!frozen.value) {
    if (cuttingReturnBlocked.value || linkedIssueBatchBlocked.value || releaseUnavailable.value) return
    if (draft.value.kind === 'REQUEST_CLOSE' && !originalOptions.value.some(row => row.id === draft.value?.original_id)) {
      formError.value = '该领料申请已无可关闭的未发余量，请重新核对原单。'
      return
    }
    if (draft.value.kind === 'CORRECTION' && (!draft.value.confirmed || !draft.value.reason.trim())) { formError.value = '请填写原因并确认整单冲销'; return }
    if (needsLocation.value && !activeLocations.value.some(row => row.id === draft.value?.location_id && matchesLocationCategory(row, locationCategory.value))) { formError.value = '请选择基础资料中已启用的仓位'; return }
    if (draft.value.location_id) draft.value.location = activeLocations.value.find(row => row.id === draft.value?.location_id)?.label ?? ''
  }
  const input = frozen.value ?? JSON.parse(JSON.stringify(draft.value)) as WarehouseDocumentInput
  if (!frozen.value) {
    if (input.kind !== 'ISSUE') input.allocations = []
    if (input.kind === 'PROCESS_SEND') input.counterparty = selectedTask.value?.data.counterparty ?? ''
  }
  saving.value = true; formError.value = ''
  try {
    const saved = await api.post(props.warehouse, input)
    if (input.kind === 'CORRECTION' && input.original_id === progressId.value) closeProgress()
    draft.value = undefined; frozen.value = undefined; correctionTarget.value = undefined
    success.value = orderProgressMode.value ? '单据已保存。' : '单据已保存，可在记录中查看来源和经办信息。'
    if (input.kind === 'CORRECTION') {
      const originalKind = saved?.data?.reversed_kind
      success.value = originalKind === 'SEMI_RELEASE' || originalKind === 'TASK'
        ? '已冲销，可在操作日志查看原记录。' : '已整单冲销，库存与关联进度已恢复，原单保留。'
    } else if (input.kind === 'RETURN' && fabricInventory.value) {
      success.value = '退料已登记，可在收发记录筛选“车间退料”查看；原出库单保留。'
    }
    await load()
  } catch (e) {
    const status = isAxiosError(e) ? e.response?.status : undefined
    if (frozen.value || status === undefined || status === 408 || status >= 500) {
      frozen.value = input; formError.value = '保存结果尚未确认。已保留本次内容，请点击“用原内容重试”，避免重复登记。'
    } else {
      frozen.value = undefined; formError.value = getApiErrorMessage(e)
      if (status === 409) { await load(); if (draft.value && data.value) { draft.value.expected_revision = data.value.revision; draft.value.request_id = warehouseRequestId() } }
    }
  } finally { saving.value = false }
}
async function recover() {
  if (!frozen.value || saving.value) return
  saving.value = true
  try {
    const result = await api.recover(props.warehouse, frozen.value)
    frozen.value = undefined
    if (result.state === 'committed') { draft.value = undefined; success.value = '原操作已成功，已刷新记录。' }
    else if (draft.value) { draft.value.request_id = warehouseRequestId(); formError.value = '已停止原未执行操作，填写内容保留，请核对最新库存后重新提交。' }
    await load()
    if (draft.value && data.value) draft.value.expected_revision = data.value.revision
  } catch(e) { formError.value = getApiErrorMessage(e) }
  finally { saving.value = false }
}
function issueGroupFor(row: WarehouseDocument) { return row.data.issue_group ?? data.value?.issue_groups?.find(g => g.request_ids.includes(row.kind === 'REQUEST' ? row.id : row.data.original_id)) }
function rowTitle(row: WarehouseDocument) { return row.data.item_name || row.batch_snapshot?.item_name || row.data.source_no }
function printFabricIssueNote() {
  printError.value = ''
  if (props.warehouse !== 'fabric' || detail.value?.kind !== 'ISSUE') return
  const html = fabricIssueNoteHtml(detail.value, {})
  const note = window.open('', '_blank', 'width=960,height=1280')
  if (!note) { printError.value = '浏览器拦截了打印窗口，请允许本页弹窗后重试。'; return }
  note.document.write(html)
  note.document.close()
  note.focus()
  setTimeout(() => { if (!note.closed) note.print() }, 300)
}
function exportFabricIssues() {
  if (props.warehouse !== 'fabric' || props.view !== 'movements' || !issueRecords.value.length) return
  const file = new Blob(['\ufeff', fabricIssueCsv(issueRecords.value)], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(file), link = document.createElement('a')
  const date = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date())
  link.href = url; link.download = `布料仓领用记录-${date}.csv`; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 30000)
}
</script>

<template>
  <div class="warehouse-operations-live" :class="{ 'fabric-touch-workspace': warehouse === 'fabric' }">
    <div v-if="!stockMode" class="warehouse-table-heading">
      <div><h2>{{ title || '收发记录' }}</h2><p>{{ description || '查看实际办理记录，点击详情追溯原单与经办信息。' }}</p></div>
      <div class="warehouse-heading-actions">
        <template v-if="fabricExceptions"><RouterLink class="exception-source-link" to="/modules/pmc-warehouse/fabric-warehouse/receipts?factory=huakang-c&amp;view=history">查看入库记录 ↗</RouterLink><RouterLink class="exception-source-link" to="/modules/pmc-warehouse/fabric-warehouse/inventory?factory=huakang-c&amp;view=movements&amp;kind=ISSUE">查看出库记录 ↗</RouterLink></template>
        <Button variant="outline" :disabled="loading" @click="load">刷新</Button>
        <RouterLink v-if="pendingReceipts" class="exception-source-link" :to="{ path: `${WAREHOUSE_HOME}/semi-finished-warehouse/orders`, query: { factory: WAREHOUSE_FACTORY, view: 'tasks' } }">加工交接任务 ↗</RouterLink>
        <template v-if="orderProgressMode">
          <Button v-for="kind in config.actions.filter(permitted)" :key="kind" :disabled="loading" @click="begin(kind)">{{ operationLabels[kind] }}</Button>
        </template>
      </div>
    </div>
    <p v-if="loading" role="status" class="fabric-message">正在读取仓库记录…</p>
    <p v-if="error" role="alert" class="fabric-error">{{ error }}</p>
    <p v-if="success" role="status" class="fabric-message">{{ success }}</p>
    <WarehouseStockLedger v-if="data && stockMode" :key="`${warehouse}:${view}`" :title="title" :restricted-only="fabricExceptions && view === 'holds'" :rows="view === 'holds' ? data.stock.filter(row => ['HOLD', 'REJECTED'].includes(row.quality_status)) : data.stock" :warehouse="warehouse" :loading="loading" :can-operate="permitted('ISSUE')" :can-bind="permitted('LOCATION_BIND')" @bulk="ids => bulkRows = data?.stock.filter(row => ids.includes(row.id))" @action="begin" @refresh="load" />
    <WarehouseBulkIssueDialog v-if="bulkRows && data" :rows="bulkRows" :warehouse="warehouse" :revision="data.revision" @close="bulkRows = undefined" @saved="bulkRows = undefined; load()" />
    <div v-if="fabricInventory && view === 'pending-issues'" class="mb-4 flex items-center gap-3"><Button :disabled="loading || !permitted('ISSUE')" @click="issueGroupOpen = true">同订单配套发料</Button><span class="text-xs text-muted-foreground">多张领料单统一选缸，确认后分别更新进度。</span></div>
    <FabricIssueGroupDialog v-if="issueGroupOpen" @close="issueGroupOpen = false; load()" @saved="load" />
    <div v-if="orderProgressMode && data?.order_progress" ref="progressList">
      <p v-if="linkedProgressId && !linkedProgress && !loading" role="status" class="fabric-message mx-5">所选放产明细已冲销或无法查看。</p>
      <SemiOrderProgress :progress="data.order_progress" :releases="releases" :can-operate="permitted('SEMI_RELEASE')" :busy="loading"
        :pending-only="pendingReceipts" :extra-initially="route.query.receipt_progress === 'extra'" @open="openProgress" />
    </div>
    <p v-else-if="data && orderProgressMode && !loading" role="status" class="fabric-message">放产进度不可用，请核对服务版本。</p>
    <SemiOrderTrace v-if="orderProgressMode && progress && progressRelease && !draft && !detail"
      :order="progress" :release="progressRelease" :documents="progressDocuments"
      :can-operate="!loading && permitted('RECEIPT')" :can-correct="!loading && permitted('CORRECTION')"
      :has-stock="progressHasStock" :has-task="progressHasTask"
      @close="closeProgress" @close-auto-focus="restoreProgressFocus" @detail="detail = $event" @action="beginForOrder" />
    <template v-if="data && !stockMode && !orderProgressMode">
      <div class="warehouse-operation-toolbar" :class="{ 'fabric-inventory-toolbar': fabricFilters }">
        <label v-if="!useHeaderSearch" class="grow">查找记录
          <input ref="recordSearchInput" :id="`${recordFilterId}-query`" name="record_q" v-model="search" type="search"
            :placeholder="warehouse === 'semi' ? '产品 / 生产单号 / 加工方 / 仓位' : '物料名称 / 单号 / 领用方 / 仓位'" aria-label="查找仓库收发" />
        </label>
        <div class="flex min-w-0 flex-wrap items-center gap-2 whitespace-nowrap text-xs">
          <span>业务日期</span><DateRangeFilter v-model="dates" label="收发记录日期范围" />
        </div>
        <label v-if="handoffView">办理状态
          <select v-model="pendingHandoffs" aria-label="交接办理状态">
            <option :value="false">全部记录</option>
            <option :value="true">{{ view === 'processing' ? '待回货' : '待签收' }}</option>
          </select>
        </label>
        <template v-if="fabricFilters">
          <label v-if="fabricExceptions">原业务
            <select v-model="recordKind" aria-label="更正原业务">
              <option value="">全部业务</option>
              <option v-for="(label, kind) in originalKindLabels" :key="kind" :value="kind">{{ label }}</option>
            </select>
          </label>
          <label v-if="fabricExceptions">经办人
            <select v-model="recordActor" aria-label="更正经办人">
              <option value="">全部经办人</option>
              <option v-for="name in correctionActors" :key="name">{{ name }}</option>
            </select>
          </label>
          <label v-if="view === 'movements'">业务类型
            <select :id="`${recordFilterId}-kind`" name="record_kind" v-model="recordKind" aria-label="收发业务类型">
              <option value="">全部类型</option>
              <option v-for="kind in recordKinds" :key="kind" :value="kind">{{ movementKindLabels[kind] }}</option>
            </select>
          </label>
          <label v-if="!fabricExceptions">{{ view === 'pending-issues' ? '办理状态' : '单据状态' }}
            <select :id="`${recordFilterId}-state`" name="record_state" v-model="recordState" aria-label="收发单据状态">
              <option value="">全部状态</option>
              <template v-if="view === 'pending-issues'"><option value="PENDING">尚未发完</option><option value="COMPLETE">已发完</option><option value="REVERSED">已冲销</option></template>
              <template v-else><option value="ACTIVE">未冲销</option><option value="REVERSED">已冲销</option></template>
            </select>
          </label>
          <label>排序
            <select :id="`${recordFilterId}-sort`" name="record_sort" v-model="recordSort" aria-label="收发记录排序">
              <option value="DATE_DESC">业务日期 · 最新在前</option><option value="DATE_ASC">业务日期 · 最早在前</option>
            </select>
          </label>
          <Button variant="ghost" :disabled="!recordFiltersActive" @click="resetRecordFilters">重置筛选</Button>
        </template>
        <Button v-if="warehouse === 'fabric' && view === 'movements'" variant="outline" :disabled="!issueRecords.length" @click="exportFabricIssues">导出领用记录</Button>
        <Button v-for="kind in config.actions" :key="kind" :disabled="loading || !permitted(kind)" @click="begin(kind)">{{ operationLabels[kind] }}</Button>
      </div>
      <details v-if="section === 'overview' && warehouse === 'fabric'" class="warehouse-quick-help">
        <summary>登记领料申请怎么用？</summary><p>仓库代录车间需求，只建立申请，办理实际出库后才扣库存。</p>
      </details>
      <p v-if="fabricExceptions" class="exception-record-note">已办理的冲销记录 {{ count }} 笔 · 保留原单与更正原因，查看详情可追溯原单编号。</p>
      <div class="warehouse-table-scroll" tabindex="0" role="region" aria-label="业务记录">
        <table class="warehouse-records-table"><thead><tr><th>{{ fabricExceptions ? '更正日期 / 原业务' : '业务 / 日期' }}</th><th>物料 / 数量进度</th><th>{{ fabricExceptions ? '更正原因' : '仓位 / 去向' }}</th><th>来源凭证</th><th>经办人</th><th>操作</th></tr></thead><tbody>
          <tr v-for="row in visibleRecords" :key="row.id">
            <td :data-label="fabricExceptions ? '更正日期 / 原业务' : '业务 / 日期'"><template v-if="fabricExceptions"><strong>{{ row.business_date }}</strong><small>{{ originalKindLabels[row.data.reversed_kind || ''] || '原单' }}冲销</small></template><template v-else><strong>{{ warehouse === 'fabric' ? fabricOperationLabel(row.kind) : operationLabels[row.kind] }}</strong><small>{{ row.business_date }}</small></template></td>
            <td data-label="物料 / 数量进度"><strong>{{ rowTitle(row) }}</strong><small>{{ row.data.item_code || row.batch_snapshot?.item_code }}<template v-if="row.data.process_state || row.batch_snapshot?.process_state"> · {{ row.data.process_state || row.batch_snapshot?.process_state }}</template></small><span v-if="row.data.quantity">{{ row.data.quantity }} {{ row.data.unit || row.batch_snapshot?.unit }}</span><small v-if="fabricInventory && row.kind === 'ISSUE' && !row.reversed">已退 {{ row.returned_quantity || '0' }} · <template v-if="cuttingIssue(row)"><template v-if="row.cutting_return_limit">{{ row.cutting_return_limit.day }} 可退 {{ row.cutting_return_limit.quantity }} {{ row.data.unit || row.batch_snapshot?.unit }}</template><template v-else>可退额度待核对</template></template><template v-else>可退 {{ remaining(row.data.quantity, row.returned_quantity) }} {{ row.data.unit || row.batch_snapshot?.unit }}</template></small><small v-else>{{ documentProgress(row) }}</small></td>
            <td :data-label="fabricExceptions ? '更正原因' : '仓位 / 去向'"><template v-if="fabricExceptions">{{ row.data.reason || '—' }}</template><template v-else-if="row.kind === 'TRANSFER'">{{ row.batch_snapshot?.location }} → {{ row.data.location }}</template><template v-else>{{ row.data.location || row.batch_snapshot?.location || '—' }}<small>{{ row.data.counterparty || '—' }}</small></template></td>
            <td data-label="来源凭证">{{ row.data.source_no || '未另填凭证' }}<small v-if="row.data.original_id">已关联原单</small><small v-if="issueGroupFor(row)">配套：{{ issueGroupFor(row)?.order_no }} · {{ issueGroupFor(row)?.name }}</small><small v-if="row.data.cutting_request">裁床订单 {{row.data.cutting_request.order_no}} · {{row.data.cutting_request.task_name}} · BOM V{{row.data.cutting_request.bom_version}} / 计划V{{row.data.cutting_request.plan_version}}<br />仓库：{{row.data.cutting_request.warehouse_material.code}} / {{row.data.cutting_request.warehouse_material.spec}} / {{row.data.cutting_request.warehouse_material.color}} / {{row.data.cutting_request.warehouse_material.unit}}<br />裁床：{{row.data.cutting_request.cutting_material.code}} / {{row.data.cutting_request.cutting_material.specification}} / {{row.data.cutting_request.cutting_material.color}}<br />对应依据：{{row.data.cutting_request.mapping_basis}}</small></td>
            <td data-label="经办人">{{ row.actor_name }}</td>
            <td class="warehouse-record-actions">
              <Button v-if="canCorrectMovement(row)" title="原单录错时整单冲销，保留原记录和更正原因" variant="outline" size="sm" :disabled="loading || !permitted('CORRECTION')" @click="correct(row)">冲销</Button>
              <Button v-if="isReturnableIssue(row)" title="原出库正确，车间实际退回材料时登记；可分次退料" variant="outline" size="sm" :disabled="loading || !permitted('RETURN')" @click="returnIssue(row)">退料</Button>
              <Button v-if="hasUnissuedRemainder(row)" size="sm" :disabled="!permitted('ISSUE')" @click="issueRequest(row)">办理出库</Button>
              <Button v-if="canCloseRequest(row)" variant="outline" size="sm" :disabled="!permitted('REQUEST_CLOSE')" @click="closeRequest(row)">关闭未发余量</Button>
              <Button variant="outline" size="sm" @click="detail = row">详情</Button>
            </td>
          </tr>
        </tbody></table>
      </div>
      <div v-if="!count" class="warehouse-empty" role="status"><h3>暂无{{ title || '业务记录' }}</h3><p>{{ recordFiltersActive ? '试试调整筛选条件。' : fabricExceptions ? '从原单办理冲销后会显示在这里；正常分批到货请继续在待收料跟进。' : '办理对应业务后，记录会显示在这里。' }}</p></div>
      <footer class="warehouse-list-footer"><span>共 {{ count }} 条</span><div><Button variant="outline" size="sm" :disabled="offset === 0" @click="offset -= 50">上一页</Button><Button variant="outline" size="sm" :disabled="offset + 50 >= count" @click="offset += 50">下一页</Button></div></footer>
    </template>
    <Teleport to="body">
      <div v-if="draft" class="warehouse-operation-overlay" :class="{ 'fabric-touch-overlay': warehouse === 'fabric' }"><FocusScope as-child loop trapped><form ref="formElement" class="warehouse-operation-dialog" :class="{ 'fabric-touch-dialog': warehouse === 'fabric' }" role="dialog" aria-modal="true" :aria-label="operationLabels[draft.kind]" @keydown.esc.prevent="close" @submit.prevent="submit">
        <header><div><h2>{{ operationLabels[draft.kind] }}</h2><p>{{ warehouse === 'fabric' ? '布料仓' : '半成品仓' }} · 华康 C</p></div><Button type="button" variant="outline" :disabled="saving || !!frozen" @click="close">关闭</Button></header>
        <div class="warehouse-operation-form">
          <p v-if="draft.kind === 'SEMI_RELEASE'" class="fabric-message">按已有放产单登记计划。实际到仓时，另办实收并选择对应仓位。</p>
          <p v-if="draft.kind === 'CORRECTION'" class="fabric-message">冲销保留原单和原因。已有后续业务的单据需先核对关联记录。</p>
          <p v-if="draft.kind === 'PACK_RECEIVE'" class="fabric-message">此操作为仓库代录包装接收回执，须填写实际接收人，回执备注可选填；不会再次扣库存。</p>
          <p v-if="draft.kind === 'PROCESS_RETURN'" class="fabric-message">本次产出量按加工任务的产品和单位记录；本轮核销量按原发出单位填写，不能直接用产出量相减。</p>
          <p v-if="correctionTarget" class="fabric-message">本次整单冲销：{{ rowTitle(correctionTarget) }} · {{ correctionTarget.business_date }} · {{ correctionTarget.data.quantity }} {{ correctionTarget.data.unit || correctionTarget.batch_snapshot?.unit }} · {{ correctionTarget.data.counterparty }}。请核对原单及整单数量。</p>
          <div v-if="returnOriginal" class="operation-stock-card"><strong>原出库：{{ rowTitle(returnOriginal) }}</strong><span>{{ returnOriginal.data.item_code || returnOriginal.batch_snapshot?.item_code }} · {{ returnOriginal.business_date }} · 领用方：{{ returnOriginal.data.counterparty }}</span><div><span>实发 {{ returnOriginal.data.quantity }} · 已退 {{ returnOriginal.returned_quantity || '0' }}</span><strong v-if="cuttingReturnId && validReturnLimit">可退 {{ validReturnLimit.quantity }} {{ returnOriginal.data.unit || returnOriginal.batch_snapshot?.unit }}</strong><strong v-else-if="!cuttingReturnId">可退 {{ remaining(returnOriginal.data.quantity, returnOriginal.returned_quantity) }} {{ returnOriginal.data.unit || returnOriginal.batch_snapshot?.unit }}</strong></div><small>按实际收回数量登记，物料、单位和领用方沿用原出库单。</small>
            <template v-if="cuttingReturnId">
              <small v-if="returnLimitLoading" role="status">正在读取所选业务日期的裁床可退余料…</small>
              <small v-else-if="!returnDay">请选择业务日期后核对可退余料。</small>
              <small v-else-if="returnLimitError" role="alert">可退余料读取失败。{{ returnLimitError }} <Button type="button" variant="outline" size="sm" @click="returnLimitRetry++">重新读取</Button></small>
              <small v-else-if="validReturnLimit?.reason" role="status">{{ validReturnLimit.reason }}</small>
              <small v-else-if="returnQuantityExceeded" role="status">本次数量超过所选业务日期的可退余料。</small>
            </template>
          </div>
           <div v-if="selectedBatch && !fabricIssue" class="operation-stock-card"><strong>{{ selectedBatch.item_name }}</strong><span>{{ selectedBatch.item_code }} · {{ selectedBatch.lot || '—' }} <template v-if="selectedBatch.roll_no">· 卷 {{ selectedBatch.roll_no }}</template></span><div><span>当前仓位：{{ selectedBatch.location_label || selectedBatch.location }} <b v-if="!selectedBatch.location_verified">（待核实）</b></span><strong>结余 {{ selectedBatch.quantity }} {{ selectedBatch.unit }}</strong></div></div>
          <p v-if="needsLocation && !activeLocations.length" class="fabric-error">尚无可用仓位，请先到基础资料建立仓库与仓位。</p>
          <p v-if="draft.kind === 'LOCATION_BIND'" class="fabric-message">核实旧记录的实际存放位置，只关联正式仓位，不增加或扣减库存。实物已经移动的情况需另行登记调仓。</p>
          <fieldset :disabled="saving || !!frozen" class="warehouse-operation-fields">
            <label v-if="warehouse === 'semi' && draft.kind === 'RECEIPT' && !orderScope && (releases.length || draft.release_id)" class="full">
              关联放产明细（选填）
              <select v-model="draft.release_id" aria-label="关联放产明细" @change="selectRelease">
                <option value="">独立实收</option>
                <option v-for="row in releases" :key="row.id" :value="row.id">{{ row.data.production_no }} · {{ row.data.part }} · {{ row.data.label_code || '无布标' }} · {{ row.data.source_no }} / {{ row.data.source_line }}</option>
              </select>
            </label>
            <div v-if="linkedRelease || (orderScope && progressRelease)" class="full issue-readback" role="group" aria-label="已关联放产明细">
              <small>已关联放产明细</small>
              <p>{{ (linkedRelease || progressRelease)?.data.production_no }} · {{ (linkedRelease || progressRelease)?.data.part }} · {{ (linkedRelease || progressRelease)?.data.label_code || '无布标' }}</p>
              <small v-if="linkedReceipt && linkedRelease">{{ linkedRelease.data.item_code }} · {{ linkedRelease.data.item_name }} · {{ linkedRelease.data.process_state }} · 收料单位 {{ linkedRelease.data.unit }}</small>
              <small>{{ (linkedRelease || progressRelease)?.data.source_no }} / {{ (linkedRelease || progressRelease)?.data.source_line }}</small>
            </div>
            <p v-if="releaseUnavailable" class="full fabric-error" role="alert">所选放产明细已冲销或无法办理，请重新核对来源。</p>
            <label>{{ draft.kind === 'SEMI_RELEASE' ? '放产日期' : '业务日期' }}<input v-model="draft.business_date" type="date" required aria-label="业务日期" /></label>
            <label v-if="draft.kind === 'SEMI_RELEASE'">放产来源单号<input v-model.trim="draft.source_no" required maxlength="128" aria-label="来源单号" placeholder="填写已有放产单号" /></label>
            <label v-else>来源单号 / 手工凭证号{{ needsItem ? '' : '（选填）' }}<input v-model.trim="draft.source_no" :required="needsItem" maxlength="128" aria-label="来源单号" :placeholder="linkedReceipt ? '填写本次收货凭证号' : needsItem ? '保留原单编号，手工单可自行编号' : '有外部凭证时填写'" /></label>
            <template v-if="needsItem">
              <label>来源明细编号<input v-model.trim="draft.source_line" required maxlength="128" aria-label="来源明细编号" /></label>
              <label>来源版本（选填）<input v-model.trim="draft.source_version" maxlength="128" aria-label="来源版本" /></label>
              <template v-if="draft.kind === 'SEMI_RELEASE'">
                <label>生产单号<input v-model.trim="draft.production_no" required maxlength="128" aria-label="生产放产单号" /></label>
                <label>部位<input v-model.trim="draft.part" required maxlength="128" placeholder="如头、身体、衣服" /></label>
                <label>布标日期码（选填）<input v-model.trim="draft.label_code" maxlength="128" /></label>
              </template>
              <template v-if="!linkedReceipt">
                <label>物料 / 产品编码<input v-model.trim="draft.item_code" required maxlength="128" aria-label="物料产品编码" /></label>
                <label>名称规格<input v-model.trim="draft.item_name" required maxlength="255" aria-label="名称规格" /></label>
                <label>原单位<input v-model.trim="draft.unit" required maxlength="32" aria-label="原单位" placeholder="码、米、件等" /></label>
                <label v-if="warehouse === 'semi'">{{ draft.kind === 'TASK' ? '计划产出加工状态' : draft.kind === 'SEMI_RELEASE' ? '计划实收状态' : '加工状态' }}<input v-model.trim="draft.process_state" required maxlength="64" aria-label="加工状态" placeholder="如车缝完成、冲棉完成" /></label>
                <label v-else>物料分类<select v-model="draft.material_category" aria-label="物料分类"><option value="FABRIC">布料</option><option value="ACCESSORY">辅料</option><option value="THREAD">线</option></select></label>
              </template>
              <label v-if="draft.kind !== 'SEMI_RELEASE'">来源单位 / 领用方 / 加工方<input v-model.trim="draft.counterparty" required maxlength="255" aria-label="往来单位" /></label>
              <label v-if="draft.kind !== 'SEMI_RELEASE' && !draft.release_id">生产 / 放产单号（选填）<input v-model.trim="draft.production_no" maxlength="128" aria-label="生产放产单号" /></label>
              <label v-if="draft.kind === 'TASK' || draft.kind === 'REQUEST'">{{ draft.kind === 'TASK' ? '加工工序 / 返工说明' : '领用用途（选填）' }}<input v-model.trim="draft.purpose" :required="draft.kind === 'TASK'" maxlength="255" aria-label="用途工序" /></label>
              <label v-if="draft.kind === 'TASK' || draft.kind === 'SEMI_RELEASE'">{{ draft.kind === 'TASK' ? '要求回货日期（选填）' : '应收日期（选填）' }}<input v-model="draft.due_date" type="date" aria-label="要求回货日期" /></label>
            </template>
            <div v-if="fixedIssueRequest" class="full issue-readback" role="group" aria-label="已关联领料申请">
              <small>已关联领料申请</small>
              <p v-if="linkedIssueRequest">{{ issueRequestLabels.get(linkedIssueRequest.id) }}</p>
              <small v-if="linkedIssueRequest">本单待发 {{ remaining(linkedIssueRequest.data.quantity, linkedIssueRequest.issued_quantity) }} {{ linkedIssueRequest.data.unit }}</small>
              <p v-else role="status">该申请已无待发余量或已不可办理，请核对原单。</p>
            </div>
            <label v-else-if="referenceKinds(draft.kind).length" class="full">
              {{ draft.kind === 'ISSUE' ? '关联领料申请（选填）' : '关联原单' }}
              <select v-model="draft.original_id" :disabled="!!correctionTarget || fixedOriginal || !!orderScope" :required="draft.kind !== 'ISSUE'" aria-label="关联原单" @change="selectOriginal">
                <option value="">{{ draft.kind === 'ISSUE' ? '不关联申请，直接出库' : '请选择原发出单' }}</option>
                <option v-for="row in originalOptions" :key="row.id" :value="row.id">
                  <template v-if="fabricIssue">{{ issueRequestLabels.get(row.id) }}</template>
                  <template v-else>{{ row.data.source_no }} · {{ rowTitle(row) }} · {{ documentProgress(row) }} · {{ row.id }}</template>
                </option>
              </select>
              <small v-if="linkedIssueRequest">本单待发 {{ remaining(linkedIssueRequest.data.quantity, linkedIssueRequest.issued_quantity) }} {{ linkedIssueRequest.data.unit }}</small>
            </label>
            <label v-if="draft.kind === 'PROCESS_SEND'" class="full">本轮加工任务<select v-model="draft.task_id" required aria-label="本轮加工任务"><option value="">请选择任务</option><option v-for="row in tasks" :key="row.id" :value="row.id">{{ row.data.source_no }} · {{ row.data.item_name }} · {{ row.data.process_state }} · {{ row.data.counterparty }}</option></select></label>
            <p v-if="!fabricIssue && data?.documents.find(r => r.id === draft?.original_id)?.data.cutting_request" class="full fabric-message">裁床申请按冻结订单、任务、BOM及物料版本核对；发料不代表裁床已签收或生产耗用。关闭余量不冲回已发数量。</p>
            <div v-if="soleIssueBatch && draft.batch_id === soleIssueBatch.id" class="full issue-readback" role="group" aria-label="出库批次">
              <small>出库批次</small>
              <p>{{ issueBatchLabels.get(soleIssueBatch.id) }}</p>
            </div>
            <label v-else-if="needsBatch" class="full">
              {{ draft.kind === 'TRANSFER' ? '来源批次 / 仓位' : fabricIssue ? '出库批次' : '出入库批次' }}
              <select v-model="draft.batch_id" required :disabled="fixedBatch" aria-label="实际批次" @change="selectProcessingBatch">
                <option value="">{{ fixedIssueRequest ? '请选择实际出库的批次' : '请选择批次' }}</option>
                <option v-for="row in selectableBatches" :key="row.id" :value="row.id">
                  <template v-if="fabricIssue">{{ issueBatchLabels.get(row.id) }}</template>
                  <template v-else>{{ row.item_code }} · {{ row.item_name }} · {{ row.process_state }} · {{ row.location_label || row.location }}<template v-if="row.lot"> · {{ row.lot }}</template> · 结余 {{ row.quantity }} {{ row.unit }} · {{ row.received_on }} · {{ row.id.slice(-8) }}</template>
                </option>
              </select>
              <small v-if="selectedBatch && !fabricIssue">原单位：{{ selectedBatch.unit }}，实物结余：{{ selectedBatch.quantity }}，可出库：{{ selectedBatch.available_quantity }}</small>
              <small v-else-if="linkedIssueRequest && !selectableBatches.length" role="status">该申请暂无匹配的可出库批次。</small>
            </label>
            <label v-if="!['QUALITY', 'CORRECTION', 'LOCATION_BIND', 'REQUEST_CLOSE'].includes(draft.kind)">{{ draft.kind === 'REQUEST' ? '申请数量' : draft.kind === 'SEMI_RELEASE' ? '计划实收数量' : draft.kind === 'TASK' ? '计划产出数量' : draft.kind === 'PROCESS_RETURN' ? '本次实际产出数量' : '本次实际数量' }}<input v-model.trim="draft.quantity" required inputmode="decimal" aria-label="本次数量" :placeholder="draft.kind === 'SEMI_RELEASE' ? '按放产单填写' : '请按本次实物填写'" /></label>
            <label v-if="draft.kind === 'PROCESS_RETURN'">本次核销发出量（原发出单位）<input v-model.trim="draft.consumed_quantity" required inputmode="decimal" aria-label="核销发出量" /></label>
            <label v-if="draft.kind === 'ISSUE'">领用部门 / 领用方<input v-model.trim="draft.counterparty" required maxlength="255" aria-label="领用方" :readonly="!!draft.original_id" placeholder="例如裁床、车间或外发厂" /></label>
            <label v-if="draft.kind === 'ISSUE'">领用用途（选填）<input v-model.trim="draft.purpose" maxlength="255" aria-label="领用用途" /></label>
            <label v-if="draft.kind === 'PACK_SEND'">包装接收部门<input v-model.trim="draft.counterparty" required maxlength="255" aria-label="包装接收部门" /></label>
            <template v-if="needsLocation"><label>{{ draft.kind === 'LOCATION_BIND' ? '实际所在仓位' : draft.kind === 'TRANSFER' ? '调入仓位' : draft.kind === 'RETURN' ? '退回仓位' : '入库仓位' }}<WarehouseLocationPicker :category="locationCategory" :disabled="saving || !!frozen" v-model="draft.location_id" :locations="activeLocations" /></label><label v-if="draft.kind === 'RECEIPT' || draft.kind === 'PROCESS_RETURN'">缸号 / 批号{{ warehouse === 'fabric' && draft.material_category === 'FABRIC' ? '' : '（选填）' }}<input v-model.trim="draft.lot" :required="warehouse === 'fabric' && draft.material_category === 'FABRIC'" maxlength="128" aria-label="缸号批号" /></label><label v-if="warehouse === 'fabric' && draft.kind === 'RECEIPT'">卷号（选填）<input v-model.trim="draft.roll_no" maxlength="128" aria-label="卷号" /></label></template>
            <label v-if="draft.kind === 'PACK_RECEIVE'">实际接收人<input v-model.trim="draft.responsible_person" required maxlength="128" aria-label="实际接收人" /></label>
            <label class="full">{{ draft.kind === 'LOCATION_BIND' ? '仓位核对依据（必填）' : draft.kind === 'REQUEST_CLOSE' ? '关闭未发余量原因（必填）' : draft.kind === 'CORRECTION' ? '冲销原因（必填）' : '业务依据 / 差异原因 / 备注（选填）' }}<textarea v-model.trim="draft.reason" :required="['CORRECTION', 'LOCATION_BIND', 'REQUEST_CLOSE'].includes(draft.kind)" maxlength="1000" rows="3" aria-label="业务依据" :placeholder="draft.kind === 'LOCATION_BIND' ? '请填写实物位置的核对依据' : draft.kind === 'CORRECTION' ? '请说明录错或冲销的原因' : '有需要补充的情况再填写'" /></label>
            <label v-if="draft.kind === 'LOCATION_BIND'" class="full"><span><input v-model="draft.confirmed" type="checkbox" required aria-label="已核实实物仓位" /> 已核实实物在所选仓位，本次只补齐仓位身份</span></label>
            <label v-if="draft.kind === 'CORRECTION'" class="full"><span><input v-model="draft.confirmed" type="checkbox" required aria-label="确认整单冲销" /> 已核对原单，确认整单冲销并保留原记录</span></label>
            <p v-if="draft.kind === 'TRANSFER'" class="full fabric-message">来源仓位减少、目标仓位增加；总库存和原始入库日期保持不变。</p>
            <div v-if="draft.kind === 'ISSUE' && !data?.documents.find(r => r.id === draft?.original_id)?.data.cutting_request" class="full warehouse-operation-allocations"><h3>放产单用料分配（选填）</h3><p>需要按放产单分配时再添加；填写后合计须等于本次出库数量。</p><div v-for="(allocation, index) in draft.allocations" :key="index"><label>放产单 / 用途编号<input v-model.trim="allocation.production_no" required :aria-label="`分配编号 ${index + 1}`" /></label><label>分配数量<input v-model.trim="allocation.quantity" required inputmode="decimal" :aria-label="`分配数量 ${index + 1}`" /></label><Button type="button" variant="outline" @click="draft.allocations.splice(index, 1)">移除</Button></div><Button type="button" variant="outline" :disabled="draft.allocations.length >= 100" @click="draft.allocations.push({ production_no: '', quantity: '' })">添加放产单分配</Button></div>
          </fieldset>
          <div v-if="frozen"><a href="/login" target="_blank" rel="noopener">重新登录</a><Button type="button" variant="outline" :disabled="saving" @click="recover">核对保存结果／停止未执行操作</Button></div><p v-if="formError" role="alert" class="fabric-error">{{ formError }}</p>
        </div>
        <footer><span>保存后保留原单与经办记录</span><Button type="submit" :disabled="saving || (!frozen && (cuttingReturnBlocked || linkedIssueBatchBlocked || releaseUnavailable || (needsLocation && !activeLocations.length)))">{{ saving ? '正在保存…' : frozen ? '用原内容重试' : draft.kind === 'CORRECTION' ? '确认整单冲销' : '确认保存' }}</Button></footer>
      </form></FocusScope></div>
      <FabricMovementDetail v-if="detail && warehouse === 'fabric'" :record="detail" :issue-group="issueGroupFor(detail)" :print-error="printError"
        @close="detail = undefined" @close-auto-focus="keepDialogFocus" @print="printFabricIssueNote">
        <template v-if="hasUnissuedRemainder(detail) && permitted('ISSUE')" #actions>
          <Button :disabled="loading" @click="issueFromDetail">办理出库</Button>
        </template>
      </FabricMovementDetail>
      <WarehouseDetailDialog v-else-if="detail" :key="detail.id" :title="operationLabels[detail.kind]" :description="detail.id" :icon="FileText"
        :close-label="progressId ? '返回订单进度' : '关闭详情'" @close="detail = undefined" @close-auto-focus="keepDialogFocus">
        <dl class="fabric-detail-section fabric-detail-fields">
          <div><dt>业务日期</dt><dd>{{ detail.business_date }}</dd></div>
          <div><dt>来源</dt><dd>{{ detail.data.source_no || '未填写外部凭证' }}<template v-if="detail.data.source_no"> / {{ detail.data.source_line }} {{ detail.data.source_version }}</template></dd></div>
          <div><dt>物料 / 产品</dt><dd>{{ rowTitle(detail) }} {{ detail.data.item_code || detail.batch_snapshot?.item_code }}</dd></div>
          <div><dt>数量与进度</dt>
            <dd v-if="detail.kind === 'LOCATION_BIND'">数量未变，核实时结余 {{ detail.batch_snapshot?.quantity }} {{ detail.data.unit }}</dd>
            <dd v-else>{{ detail.data.quantity }} {{ detail.data.unit || detail.batch_snapshot?.unit }}<br />{{ documentProgress(detail) }}</dd>
          </div>
          <template v-if="detailRelease">
            <div><dt>生产单 / 部位</dt><dd>{{ detailRelease.data.production_no }} · {{ detailRelease.data.part }}</dd></div>
            <div><dt>布标 / 放产明细</dt><dd>{{ detailRelease.data.label_code || '—' }} · {{ detailRelease.data.source_no }} / {{ detailRelease.data.source_line }}</dd></div>
          </template>
          <div v-if="detail.kind === 'SEMI_RELEASE' && detail.data.due_date"><dt>应收日期</dt><dd>{{ detail.data.due_date }}</dd></div>
          <div v-if="detail.data.original_id || detail.data.task_id">
            <dt>原单 / 加工任务</dt>
            <dd><Button v-if="detailOriginal" variant="link" size="sm" class="h-auto p-0" @click="detail = detailOriginal">{{ detailOriginal.id }}</Button><template v-else>{{ detail.data.original_id || detail.data.task_id }}</template></dd>
          </div>
          <div v-if="detail.kind === 'PROCESS_RETURN'"><dt>原发出核销</dt><dd>{{ detail.data.consumed_quantity }} {{ detail.data.consumed_unit || detail.batch_snapshot?.unit }}</dd></div>
          <div v-if="detail.kind === 'LOCATION_BIND'"><dt>核实前仓位</dt><dd>{{ detail.batch_snapshot?.location || '未填写' }}</dd></div>
          <div v-if="detail.kind !== 'SEMI_RELEASE'"><dt>仓位 / 缸号</dt><dd>{{ detail.data.location || detail.batch_snapshot?.location || '—' }} / {{ detail.data.lot || detail.batch_snapshot?.lot || '—' }}</dd></div>
          <div><dt>加工状态 / 工序</dt><dd>{{ detail.data.process_state || detail.batch_snapshot?.process_state || '—' }}<template v-if="detail.data.purpose"> / {{ detail.data.purpose }}</template></dd></div>
          <div v-if="detail.kind !== 'SEMI_RELEASE'"><dt>往来单位 / 确认人</dt><dd>{{ detail.data.counterparty || '—' }} / {{ detail.data.responsible_person || '—' }}</dd></div>
          <div><dt>依据</dt><dd>{{ detail.data.reason || '—' }}</dd></div>
          <div><dt>登记</dt><dd>{{ detail.actor_name }} · {{ formatBusinessDateTime(detail.occurred_at) }}</dd></div>
        </dl>
        <section v-if="detail.data.allocations?.length" class="fabric-detail-section">
          <h3>用料分配</h3>
          <p v-for="(allocation, index) in detail.data.allocations" :key="index">{{ allocation.production_no }} · {{ allocation.quantity }}</p>
        </section>
        <template v-if="progressId || (detailHandoffAction && permitted(detailHandoffAction))" #actions>
          <Button v-if="progressId" variant="outline" @click="detail = undefined">返回订单进度</Button>
          <Button v-if="detailHandoffAction && permitted(detailHandoffAction)" :disabled="loading" @click="beginHandoffFromDetail">
            {{ detailHandoffAction === 'PROCESS_RETURN' ? '登记回货' : '代录签收' }}
          </Button>
        </template>
      </WarehouseDetailDialog>
    </Teleport>
  </div>
</template>

<style scoped>
.warehouse-operation-dialog.fabric-touch-dialog > header { flex-wrap: wrap; }
.warehouse-operation-dialog.fabric-touch-dialog > header > div { min-width: 0; overflow-wrap: anywhere; }
.warehouse-operation-dialog.fabric-touch-dialog > header .warehouse-record-actions { display: flex; flex-wrap: wrap; gap: 8px; white-space: normal; }
.warehouse-operation-dialog.fabric-touch-dialog > header .warehouse-record-actions button { margin: 0; }
.issue-readback{min-width:0;padding:8px 12px;border:1px solid var(--border);border-radius:6px;background:var(--muted);font-size:13px;overflow-wrap:anywhere}
.issue-readback small:first-child{margin-top:0}
.warehouse-quick-help{padding:12px 24px;background:#f8fafc;font-size:13px;color:#475569}.warehouse-quick-help summary{cursor:pointer;color:#0f766e}.warehouse-quick-help p{margin-top:8px}
.operation-stock-card{border:1px solid var(--border);border-radius:9px;padding:16px;background:var(--muted);display:grid;gap:6px;margin-bottom:20px}.operation-stock-card>span{font-size:12px;color:var(--muted-foreground)}.operation-stock-card>div{display:flex;justify-content:space-between;gap:16px;font-size:13px}.operation-stock-card b{color:#b45309}
.warehouse-operation-toolbar{padding:0 24px}.warehouse-records-table{width:100%;border-collapse:collapse;text-align:left}.warehouse-records-table th{padding:12px 20px}.warehouse-records-table td{padding:16px 20px;border-bottom:1px solid var(--border);vertical-align:top;min-width:120px}.warehouse-records-table td strong{font-size:14px;font-weight:600}.warehouse-record-actions{white-space:nowrap}.warehouse-record-actions button+button{margin-left:8px}.warehouse-operations-live>.fabric-message,.warehouse-operations-live>.fabric-error{margin:16px 24px}

.warehouse-operation-summary{display:flex;gap:24px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px 16px;font-size:13px;margin:12px 0}.warehouse-operation-summary strong{font-size:18px;margin-left:8px;color:#0f766e}.warehouse-operation-toolbar{display:flex;align-items:end;flex-wrap:wrap;gap:12px;margin:16px 0}.grow{flex:1;min-width:200px}.warehouse-operation-toolbar label,.warehouse-operation-fields label{display:flex;flex-direction:column;gap:6px;font-size:13px;color:#334155}input,select,textarea{border:1px solid #cbd5e1;border-radius:6px;background:white;padding:8px 10px;min-width:0;color:#0f172a;font:inherit}input:focus,select:focus,textarea:focus{outline:2px solid #99f6e4;outline-offset:1px}small{display:block;font-size:12px;color:#64748b;margin-top:4px;overflow-wrap:anywhere}.warehouse-quality{background:#fff7ed;color:#9a3412;border-radius:4px;padding:3px 8px;white-space:nowrap}.warehouse-quality.qualified{background:#ecfdf5;color:#047857}.warehouse-operation-overlay{position:fixed;inset:0;background:#0f172a80;z-index:90;display:grid;place-items:center;padding:24px}.warehouse-operation-dialog{display:flex;flex-direction:column;width:min(960px,100%);max-height:92dvh;background:white;border-radius:12px;box-shadow:0 20px 60px #0003;overflow:hidden}.warehouse-operation-dialog header,.warehouse-operation-dialog footer{padding:16px 24px;display:flex;justify-content:space-between;align-items:center;gap:12px;border-bottom:1px solid #e2e8f0}.warehouse-operation-dialog h2{font-size:20px;font-weight:600}.warehouse-operation-dialog header p,.warehouse-operation-dialog footer span{font-size:12px;color:#64748b}.warehouse-operation-dialog footer{border-bottom:0;border-top:1px solid #e2e8f0}.warehouse-operation-form{padding:20px 24px;overflow:auto}.warehouse-operation-fields{display:grid;grid-template-columns:1fr 1fr;gap:16px;border:0}.full{grid-column:1/-1}.warehouse-operation-fields:disabled{opacity:.65}.warehouse-operation-allocations{background:#f8fafc;border-radius:8px;padding:16px}.warehouse-operation-allocations h3{font-weight:600}.warehouse-operation-allocations p{font-size:12px;color:#64748b;margin-bottom:12px}.warehouse-operation-allocations>div{display:flex;align-items:end;gap:12px;margin-bottom:12px}.warehouse-operation-allocations label{flex:1}.warehouse-operation-form>.fabric-message{margin-bottom:16px}@media(max-width:640px){.warehouse-operation-summary{flex-direction:column;gap:8px}.warehouse-operation-overlay{padding:8px}.warehouse-operation-dialog{max-height:96dvh}.warehouse-operation-fields{grid-template-columns:1fr}.warehouse-operation-dialog header,.warehouse-operation-dialog footer,.warehouse-operation-form{padding:16px}.warehouse-operation-allocations>div{flex-wrap:wrap}.warehouse-operation-allocations label{min-width:120px}.warehouse-operation-toolbar label{flex:1}.warehouse-operation-toolbar input{width:100%}}
</style>
<style scoped>
.warehouse-operation-toolbar.fabric-inventory-toolbar { align-items: center; margin: 0; padding: 14px 22px; border-block: 1px solid var(--border); gap: 12px; }
.fabric-inventory-toolbar label { flex-direction: row; align-items: center; gap: 8px; white-space: nowrap; font-size: 12px; }
.fabric-inventory-toolbar input, .fabric-inventory-toolbar select { min-height: 36px; padding: 7px 10px; max-width: 200px; font-size: 12px; background: #f8fafc; }
@media(max-width:760px){.warehouse-operation-toolbar.fabric-inventory-toolbar{padding:12px 16px}.fabric-inventory-toolbar label{flex:1;min-width:210px;justify-content:space-between}.fabric-inventory-toolbar input,.fabric-inventory-toolbar select{flex:1;max-width:none;min-width:0}}
</style>
