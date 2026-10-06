<script setup lang="ts">
import type { DeliveryRegistrationMode } from '@/api/cartonSupplierPortal'
import CartonActionNotice from '@/components/CartonActionNotice.vue'
import CartonFeedbackCenter from '@/components/CartonFeedbackCenter.vue'
import CartonSupplierMonthlyReview from '@/components/CartonSupplierMonthlyReview.vue'
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { ArrowLeft, BookOpen, ClipboardList, FileText, History, PackageCheck, Search, Truck, X } from '@lucide/vue'
import type { CartonSupplierGuideDestination } from '@/features/carton-procurement/supplierUsageGuide'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import { cartonSupplierPortalApi as api, type PortalOrder, type PortalPaper, type PortalShipment, type SupplierDocument, type SupplierActivity, type DeliveryImportPreview, type DeliveryImportGroup } from '@/api/cartonSupplierPortal'
import { factoryContexts } from '@/data/enterpriseMock'
import { formatBusinessDate, parseBusinessTimestamp } from '@/lib/dateTime'
import { getApiErrorMessage, getApiErrorMessageAsync } from '@/lib/http'
import { useAuthStore } from '@/stores/auth'

import CartonShipmentFilters from '@/components/CartonShipmentFilters.vue'
import { emptyShipmentFilters, filterShipments } from '@/features/carton-procurement/queryFilters'

type SupplierOrder = PortalOrder & { factory_id: string }
type SupplierShipment = PortalShipment & { factory_id: string }
type SupplierWorkspace = { supplier_name: string; orders: SupplierOrder[]; shipments: SupplierShipment[] }
const auth = useAuthStore()
const router = useRouter()
const canApprove = computed(() => auth.can('carton_supplier:approve', '*', '*'))
const canEdit = computed(() => auth.can('carton_supplier:edit', '*', '*'))
const memberships = ref<{ factory_id: string; supplier_name: string }[]>([])
const factoryFilter = ref('')
const workspace = ref<SupplierWorkspace | null>(null)
const activeTab = ref<'orders' | 'shipments' | 'documents' | 'activity' | 'settlements'>('orders')
const showUsageGuide = ref(false)
const feedbackCenter = ref<InstanceType<typeof CartonFeedbackCenter> | null>(null)
const usageGuideTrigger = ref<HTMLButtonElement | null>(null)
const CartonUsageGuide = defineAsyncComponent({
  loader: () => import('@/components/CartonUsageGuide.vue'),
  onError(reason, _retry, fail) {
    closeUsageGuide()
    error.value = `使用教程加载失败：${getApiErrorMessage(reason)}。请刷新页面后重试。`
    fail()
  },
})
function closeUsageGuide() {
  showUsageGuide.value = false
  void nextTick(() => usageGuideTrigger.value?.focus())
}
function openUsageGuideDestination(destination: CartonSupplierGuideDestination) {
  closeUsageGuide()
  if (destination === 'supplier-feedback') { void nextTick(() => feedbackCenter.value?.openFeedback()); return }
  if (destination === 'supplier-carton-mark') {
    void router.push('/carton-supplier/carton-mark')
    return
  }
  const tabs = {
    'supplier-orders': 'orders', 'supplier-documents': 'documents',
    'supplier-shipments': 'shipments', 'supplier-settlements': 'settlements',
    'supplier-activity': 'activity',
  } as const
  void openTab(tabs[destination])
}
const documents = ref<SupplierDocument[]>([])
const activity = ref<SupplierActivity[]>([])
const extraLoaded = reactive({ documents: false, activity: false })
const extraLoadingState = reactive({ documents: false, activity: false })
const extraLoading = computed(() => extraLoadingState.documents || extraLoadingState.activity)
const extraGeneration = { documents: 0, activity: 0 }
const documentSearch = ref('')
const documentFactory = ref('')
const documentKind = ref('')
const documentStatus = ref('')
const documentDateFrom = ref('')
const documentDateTo = ref('')
const selectedDocumentKeys = ref<string[]>([])
const detailDocument = ref<SupplierDocument | null>(null)
const detailDocumentPinned = ref(false)
const detailDocumentError = ref('')
const mergedDocumentsOpen = ref(false)
const documentDetailDialog = ref<HTMLElement | null>(null)
const mergedDocumentsDialog = ref<HTMLElement | null>(null)
const MAX_DOCUMENT_EXPORT = 100
let documentDetailTrigger: HTMLElement | null = null
let mergedDocumentsTrigger: HTMLElement | null = null
let restoringDocumentFocus = false
const activitySearch = ref('')
const activityFactory = ref('')
const activityEvent = ref(''), activityFrom = ref(''), activityTo = ref(''), activitySort = ref('DESC')
const activityPage = ref(1), activityTotal = ref(0)
const activityTypes: Record<string, string> = { PURCHASE_ORDER_ISSUED: '采购单发行', SUPPLIER_PAPER_ACCEPTED: '纸品确认接单', SUPPLIER_SHIPMENT_CREATED: '确认发货', SUPPLIER_SHIPMENT_RECEIVED: '仓库核实送货', SUPPLIER_SHIPMENT_NOT_RECEIVED: '仓库未收到', SUPPLIER_SHIPMENT_RECEIPT_REVERSED: '原收料冲销待更正', SUPPLIER_SHIPMENT_LINE_LINKED: '无单纸品关联订单' }
const bulkAcceptOpen = ref(false)
const search = ref('')
const customerFilter = ref('')
const statusFilter = ref('ALL')
const orderSort = ref('DEFAULT')
const orderDateField = ref('ORDER')
const shipmentFilters = ref(emptyShipmentFilters())
const orderDateFrom = ref('')
const orderDateTo = ref('')
const selectedOnly = ref(false)
const selectedOrderIds = ref<string[]>([])
const detailOrderId = ref('')
const detailPinned = ref(false)
const acceptOrderId = ref('')
const importOpen = ref(false)
const importFile = ref<File | null>(null)
const importPreview = ref<DeliveryImportPreview | null>(null)
const selectedImportNotes = ref<string[]>([])
const importModes = ref<Record<string, DeliveryRegistrationMode>>({})
let importGeneration = 0
watch([() => auth.sessionVersion, canEdit], () => {
  importGeneration++; importOpen.value = false; importFile.value = null; importPreview.value = null
  selectedImportNotes.value = []; importModes.value = {}; busy.value = false
})
onBeforeUnmount(() => { importGeneration++ })
function importGroupReady(group: DeliveryImportGroup) { return importModes.value[importNoteKey(group)] === 'EXISTING_RECEIPT' ? Boolean(group.receipt_link_ready) : group.ready }
const dates = reactive<Record<string, string>>({})
const dateIssueIds: Record<string, string> = {}
const dirtyDates = new Set<string>()
const error = ref('')
const message = ref('')
const loading = ref(false)
const discovering = ref(false)
const busy = ref(false)
let generation = 0

const orders = computed(() => workspace.value?.orders ?? [])
function factoryDisplayName(id: string) {
  return factoryContexts.find(item => item.id === id)?.shortName ?? id
}
const customers = computed(() => [...new Set(orders.value.map(order => order.customer_name))].sort((a, b) => a.localeCompare(b)))
const query = computed(() => search.value.trim().toLocaleLowerCase())
function orderQueryDate(order: PortalOrder) {
  if (orderDateField.value === 'PLANNED') return order.planned_date
  if (orderDateField.value === 'PROMISED') return order.lines.filter(line => line.accepted && Number(line.remaining_to_ship) > 0).map(line => line.promised_date).filter(Boolean).sort()[0] || ''
  return order.order_date
}
function compareOrders(a: SupplierOrder, b: SupplierOrder) {
  const promised = (order: PortalOrder) => order.lines.filter(line => line.accepted && Number(line.remaining_to_ship) > 0).map(line => line.promised_date).filter(Boolean).sort()[0] || ''
  const field = (order: PortalOrder) => orderSort.value === 'ORDER_DESC' ? order.order_date : orderSort.value === 'PROMISED_ASC' ? promised(order) : order.planned_date
  const left = field(a), right = field(b)
  return (orderSort.value === 'DEFAULT' ? (stagePriority[orderStage(a)] ?? 9) - (stagePriority[orderStage(b)] ?? 9) : 0)
    || Number(!left) - Number(!right) || (orderSort.value === 'ORDER_DESC' ? right.localeCompare(left) : left.localeCompare(right)) || a.order_no.localeCompare(b.order_no)
}
const filteredOrders = computed(() => orders.value.filter(order => {
  if (factoryFilter.value && order.factory_id !== factoryFilter.value) return false
  if (customerFilter.value && order.customer_name !== customerFilter.value) return false
  if (statusFilter.value !== 'ALL' && orderStage(order) !== statusFilter.value) return false
  if (orderDateFrom.value && (!orderQueryDate(order) || orderQueryDate(order) < orderDateFrom.value)) return false
  if (orderDateTo.value && (!orderQueryDate(order) || orderQueryDate(order) > orderDateTo.value)) return false
  if (!query.value) return true
  return [order.customer_name, order.contract_no, order.customer_po, order.item_no,
    order.order_no, order.document_no, order.product_name, ...order.lines.map(line => line.child_no)]
    .some(value => value.toLocaleLowerCase().includes(query.value))
}))
const visibleOrders = computed(() => (selectedOnly.value
  ? orders.value.filter(order => selectedOrderIds.value.includes(order.id))
  : filteredOrders.value).slice().sort(compareOrders))
const detailOrder = computed(() => orders.value.find(order => order.id === detailOrderId.value) ?? null)
const acceptOrder = computed(() => orders.value.find(order => order.id === acceptOrderId.value) ?? null)
const selectedOrders = computed(() => orders.value.filter(order => selectedOrderIds.value.includes(order.id)))
const selectableVisibleOrders = computed(() => visibleOrders.value.filter(canSelectOrder))
const allVisibleSelected = computed(() => selectableVisibleOrders.value.length > 0 && selectableVisibleOrders.value.every(order => selectedOrderIds.value.includes(order.id)))
const someVisibleSelected = computed(() => selectableVisibleOrders.value.some(order => selectedOrderIds.value.includes(order.id)))
function importNoteKey(group: Pick<DeliveryImportGroup, 'factory_id' | 'delivery_note_no'>) {
  return JSON.stringify([group.factory_id, group.delivery_note_no])
}
const matchingShipments = computed(() => filterShipments((workspace.value?.shipments ?? []).filter(row => !factoryFilter.value || row.factory_id === factoryFilter.value), shipmentFilters.value))
function openDeliveryImport() {
  importGeneration++
  error.value = ''
  importFile.value = null
  importPreview.value = null
  selectedImportNotes.value = []; importModes.value = {}
  importOpen.value = true
}
function closeDeliveryImport() {
  if (busy.value) return
  importGeneration++
  importOpen.value = false
  importFile.value = null
  importPreview.value = null
  selectedImportNotes.value = []; importModes.value = {}
}
function documentKey(row: Pick<SupplierDocument, 'factory_id' | 'kind' | 'id'>) {
  return [row.factory_id, row.kind, row.id].join('|')
}
const filteredDocuments = computed(() => documents.value.filter(row => {
  if (documentFactory.value && row.factory_id !== documentFactory.value) return false
  if (documentKind.value && row.kind !== documentKind.value) return false
  if (documentStatus.value && row.status !== documentStatus.value) return false
  if (documentDateFrom.value && row.date < documentDateFrom.value) return false
  if (documentDateTo.value && row.date > documentDateTo.value) return false
  const term = documentSearch.value.trim().toLocaleLowerCase()
  return !term || [row.document_no, ...row.lines.flatMap(line => [line.contract_no || '', line.item_no || '', line.source_document_no || '']), ...row.orders.flatMap(order => [
    order.order_no, order.customer_name, order.contract_no, order.customer_po, order.item_no,
  ])].some(value => value.toLocaleLowerCase().includes(term))
}))
const selectedDocuments = computed(() => documents.value.filter(row => selectedDocumentKeys.value.includes(documentKey(row))))
const mergedDocumentOrders = computed(() => {
  const groups = new Map<string, {
    factory_id: string
    order: SupplierDocument['orders'][number]
    sources: { document: SupplierDocument; lines: SupplierDocument['lines'] }[]
  }>()
  for (const document of selectedDocuments.value) {
    for (const order of document.orders) {
      const key = `${document.factory_id}|${order.order_no}`
      let group = groups.get(key)
      if (!group) {
        group = { factory_id: document.factory_id, order, sources: [] }
        groups.set(key, group)
      } else if (!group.order.customer_po && order.customer_po) {
        group.order = order
      }
      group.sources.push({ document, lines: document.lines.filter(line => line.order_no === order.order_no) })
    }
  }
  return [...groups.values()]
})
const mergedUnmatchedLines = computed(() => selectedDocuments.value.flatMap(document =>
  document.kind === 'DELIVERY' ? document.lines.filter(line => !line.order_no).map(line => ({ document, line })) : []))
const allVisibleDocumentsSelected = computed(() => filteredDocuments.value.length > 0
  && filteredDocuments.value.every(row => selectedDocumentKeys.value.includes(documentKey(row))))
const filteredActivity = computed(() => activity.value)
async function loadActivity() {
  const token = ++extraGeneration.activity
  extraLoadingState.activity = true; error.value = ''; activity.value = []
  try {
    const result = await api.activityPage({ factory_id: activityFactory.value, search: activitySearch.value.trim(), event_type: activityEvent.value, date_from: activityFrom.value, date_to: activityTo.value, sort: activitySort.value, limit: 50, offset: (activityPage.value - 1) * 50 })
    if (token !== extraGeneration.activity) return
    activity.value = result.items; activityTotal.value = result.total; extraLoaded.activity = true
  } catch (cause) { if (token === extraGeneration.activity) error.value = getApiErrorMessage(cause) }
  finally { if (token === extraGeneration.activity) extraLoadingState.activity = false }
}
let activityTimer: ReturnType<typeof setTimeout> | undefined
watch([activitySearch, activityFactory, activityEvent, activityFrom, activityTo, activitySort], () => {
  extraGeneration.activity++; activityPage.value = 1; activity.value = []
  if (activityTimer) clearTimeout(activityTimer)
  if (activeTab.value === 'activity') activityTimer = setTimeout(() => void loadActivity(), 200)
})
watch(activityPage, () => { if (activeTab.value === 'activity') void loadActivity() })
onBeforeUnmount(() => { if (activityTimer) clearTimeout(activityTimer) })

function open(order: PortalOrder) {
  return ['PENDING_SUPPLIER', 'PARTIALLY_RECEIVED'].includes(order.status) && !order.awaiting_issue
}
function canSelectOrder(order: PortalOrder) {
  return (canApprove.value || canEdit.value) && order.status !== 'COMPLETED' && order.status !== 'CANCELLED'
}
function needsAcceptance(line: PortalPaper) {
  return Number(line.required_quantity) > 0 && !line.accepted
}
function orderStage(order: PortalOrder) {
  if (order.awaiting_issue) return 'PENDING_ISSUE'
  if (order.status === 'CANCELLED') return 'CANCELLED'
  if (order.status === 'COMPLETED') return 'COMPLETED'
  if (order.lines.some(line => Number(line.in_transit_quantity) > 0)) return 'RECEIPT_PENDING'
  if (order.lines.some(needsAcceptance)) return 'PENDING_ACCEPTANCE'
  if (order.status === 'PARTIALLY_RECEIVED' && order.lines.some(line => Number(line.remaining_to_ship) > 0)) return 'WAITING_SHIPMENT'
  return 'ACCEPTED'
}
const stagePriority: Record<string, number> = {
  PENDING_ACCEPTANCE: 0, WAITING_SHIPMENT: 1, ACCEPTED: 2,
  RECEIPT_PENDING: 3, PENDING_ISSUE: 4, COMPLETED: 5, CANCELLED: 6,
}
function progressLines(order: PortalOrder) {
  return order.lines.filter(line => Number(line.required_quantity) > 0)
}
function orderStatus(order: PortalOrder) {
  const labels: Record<string, string> = {
    CANCELLED: '已取消', COMPLETED: '已完成', PENDING_ISSUE: '变更待发行',
    RECEIPT_PENDING: '送货待确定', PENDING_ACCEPTANCE: '待接单', WAITING_SHIPMENT: '待送货', ACCEPTED: '已确认接单',
  }
  return labels[orderStage(order)]
}
function dueReminder(order: PortalOrder) {
  if (order.status === 'COMPLETED') return { label: '交付已完成', level: 'CLOSED' }
  if (order.status === 'CANCELLED') return { label: '订单已取消', level: 'CLOSED' }
  const today = parseBusinessTimestamp(formatBusinessDate(new Date().toISOString()))
  const due = parseBusinessTimestamp(order.planned_date)
  if (today === null || due === null) return { label: '交期待确认', level: 'INVALID' }
  const days = Math.round((due - today) / 86_400_000)
  if (days < 0) return { label: `已逾期 ${Math.abs(days)} 天`, level: 'OVERDUE' }
  if (days === 0) return { label: '今日交期', level: 'TODAY' }
  if (days === 1) return { label: '明日交期', level: 'DUE_SOON' }
  if (days <= 3) return { label: `剩 ${days} 天`, level: 'DUE_SOON' }
  return { label: `距交期 ${days} 天`, level: 'UPCOMING' }
}
function dueReminderClass(order: PortalOrder) {
  const level = dueReminder(order).level
  if (level === 'OVERDUE' || level === 'TODAY') return 'text-red-600'
  if (level === 'DUE_SOON') return 'text-amber-700'
  return 'text-slate-500'
}
function statusClass(order: PortalOrder) {
  const stage = orderStage(order)
  if (stage === 'PENDING_ISSUE' || stage === 'RECEIPT_PENDING') return 'bg-amber-50 text-amber-700 ring-amber-200'
  if (stage === 'COMPLETED' || stage === 'ACCEPTED' || stage === 'WAITING_SHIPMENT') return 'bg-emerald-50 text-emerald-700 ring-emerald-200'
  if (stage === 'CANCELLED') return 'bg-slate-100 text-slate-500 ring-slate-200'
  return 'bg-sky-50 text-sky-700 ring-sky-200'
}
function shipmentStatus(shipment: PortalShipment) {
  return shipment.requires_receipt_link ? '后补凭证待关联' : shipment.linked_existing_receipt && !shipment.requires_correction ? '已关联原入库' : shipment.status === 'RECEIPT_REVERSED' ? '收料已冲销，待更正' : shipment.status === 'SENT' ? '待仓库确认' : shipment.status === 'NOT_RECEIVED' ? '仓库未收到' : '仓库已核实'
}
function clearFilters() {
  factoryFilter.value = ''
  search.value = ''
  customerFilter.value = ''
  statusFilter.value = 'ALL'
  orderDateFrom.value = ''
  orderDateTo.value = ''
  selectedOnly.value = false
}
function toggleVisibleOrders(checked: boolean) {
  const ids = new Set(selectedOrderIds.value)
  for (const order of selectableVisibleOrders.value) checked ? ids.add(order.id) : ids.delete(order.id)
  selectedOrderIds.value = [...ids]
}
function showOrderDetail(id: string, pinned = false) {
  if (detailPinned.value && !pinned) return
  detailOrderId.value = id
  detailPinned.value = pinned
}
function closeOrderDetailPreview() {
  if (!detailPinned.value) detailOrderId.value = ''
}
function closeOrderDetail() {
  detailOrderId.value = ''
  detailPinned.value = false
}
function showDocumentDetail(row: SupplierDocument, pinned = false) {
  if (restoringDocumentFocus && !pinned) return
  if (detailDocumentPinned.value && !pinned) return
  detailDocument.value = row
  detailDocumentPinned.value = pinned
  detailDocumentError.value = ''
  if (pinned) {
    documentDetailTrigger = document.activeElement instanceof HTMLElement ? document.activeElement : null
    void nextTick(() => documentDetailDialog.value?.querySelector<HTMLElement>('[aria-label="关闭单据明细"]')?.focus())
  }
}
function closeDocumentDetailPreview() {
  if (!detailDocumentPinned.value) detailDocument.value = null
}
function closeDocumentDetail() {
  const restore = detailDocumentPinned.value ? documentDetailTrigger : null
  detailDocument.value = null
  detailDocumentPinned.value = false
  detailDocumentError.value = ''
  documentDetailTrigger = null
  if (restore) void nextTick(() => {
    if (!restore.isConnected) return
    restoringDocumentFocus = true
    restore.focus()
    void nextTick(() => { restoringDocumentFocus = false })
  })
}
function openMergedDocuments() {
  mergedDocumentsTrigger = document.activeElement instanceof HTMLElement ? document.activeElement : null
  mergedDocumentsOpen.value = true
  void nextTick(() => mergedDocumentsDialog.value?.querySelector<HTMLElement>('[aria-label="关闭合并预览"]')?.focus())
}
function closeMergedDocuments() {
  const restore = mergedDocumentsTrigger
  mergedDocumentsOpen.value = false
  mergedDocumentsTrigger = null
  if (restore) void nextTick(() => { if (restore.isConnected) restore.focus() })
}
function trapDialogTab(event: KeyboardEvent) {
  if (event.key !== 'Tab') return
  const dialog = event.currentTarget as HTMLElement
  const controls = [...dialog.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])')]
  if (!controls.length) return
  const first = controls[0]!
  const last = controls[controls.length - 1]!
  if (event.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && (document.activeElement === last || !dialog.contains(document.activeElement))) {
    event.preventDefault()
    first.focus()
  }
}
function onDetailKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    closeOrderDetail()
    acceptOrderId.value = ''
    closeDeliveryImport()
    bulkAcceptOpen.value = false
    closeDocumentDetail()
    closeMergedDocuments()
  }
}
function showAccept(order: SupplierOrder) {
  if (!canApprove.value) return
  closeOrderDetail()
  closeDeliveryImport()
  error.value = ''
  message.value = ''
  acceptOrderId.value = order.id
}
function openBulkAccept() {
  if (!canApprove.value) return
  error.value = ''
  if (!selectedOrders.value.length || selectedOrders.value.some(order =>
    !open(order) || !order.lines.some(needsAcceptance))) {
    error.value = '请只选择待接单且当前采购单已发行的订单。'
    return
  }
  bulkAcceptOpen.value = true
}
async function confirmBulkAccept() {
  if (busy.value || !canApprove.value) return
  const pending = selectedOrders.value.flatMap(order => order.lines.filter(needsAcceptance)
    .map(line => ({ order, line })))
  if (!pending.length || pending.some(({ line }) => !dates[line.id])) {
    error.value = '请为每条待接纸品填写承诺交期。'
    return
  }
  busy.value = true
  error.value = ''
  message.value = ''
  const succeeded: string[] = []
  let failureMessage = ''
  try {
    for (const factoryId of [...new Set(pending.map(({ order }) => order.factory_id))]) {
      const lines = pending.filter(({ order }) => order.factory_id === factoryId)
      await api.acceptBatch(factoryId, lines.map(({ order, line }) => ({
        order_line_id: line.id, issue_id: order.issue_id,
        expected_revision: line.commitment_revision, promised_date: dates[line.id]!,
      })))
      succeeded.push(factoryDisplayName(factoryId))
      for (const { line } of lines) dirtyDates.delete(line.id)
      extraLoaded.activity = false
    }
    message.value = `已确认 ${selectedOrders.value.length} 张订单的 ${pending.length} 条纸品。`
    extraLoaded.activity = false
    bulkAcceptOpen.value = false
  } catch (reason) {
    failure(reason)
    failureMessage = `${succeeded.length ? `已完成 ${succeeded.join('、')}；` : ''}接单失败：${error.value}`
  } finally {
    const refreshError = await load()
    if (failureMessage) error.value = `${failureMessage}${refreshError ? `；列表刷新失败：${refreshError}` : ''}`
    else if (refreshError) error.value = `${message.value} 接单已保存，但列表刷新失败：${refreshError}。请刷新查看，勿重复接单。`
    busy.value = false
  }
}
async function openTab(tab: typeof activeTab.value) {
  if (tab !== 'documents') {
    closeDocumentDetail()
    closeMergedDocuments()
  }
  activeTab.value = tab
  if (tab === 'documents' || tab === 'activity') await loadExtra(tab)
}
async function loadExtra(tab: 'documents' | 'activity') {
  if (tab === 'activity') { await loadActivity(); return }
  if (extraLoadingState[tab] || extraLoaded[tab] || !memberships.value.length) return
  const token = ++extraGeneration[tab]
  extraLoadingState[tab] = true
  try {
    const data = await Promise.all(memberships.value.map(item =>
      tab === 'documents' ? api.documents(item.factory_id) : api.activity(item.factory_id)))
    if (token !== extraGeneration[tab]) return
    if (tab === 'documents') {
      documents.value = (data as SupplierDocument[][]).flat().sort((a, b) => b.created_at.localeCompare(a.created_at))
      selectedDocumentKeys.value = selectedDocumentKeys.value.filter(key => documents.value.some(row => documentKey(row) === key))
      const openDocument = detailDocument.value
      if (openDocument) {
        detailDocument.value = documents.value.find(row => documentKey(row) === documentKey(openDocument)) ?? null
        if (!detailDocument.value) detailDocumentPinned.value = false
      }
      if (!selectedDocumentKeys.value.length) closeMergedDocuments()
    } else {
      activity.value = (data as SupplierActivity[][]).flat().sort((a, b) => b.created_at.localeCompare(a.created_at))
    }
    extraLoaded[tab] = true
    return ''
  } catch (reason) {
    if (token === extraGeneration[tab]) { failure(reason); return error.value }
  } finally {
    if (token === extraGeneration[tab]) extraLoadingState[tab] = false
  }
}
function toggleDocument(row: SupplierDocument, event: Event) {
  const input = event.target as HTMLInputElement
  const key = documentKey(row)
  const keys = new Set(selectedDocumentKeys.value)
  if (input.checked && !keys.has(key) && keys.size >= MAX_DOCUMENT_EXPORT) {
    input.checked = false
    error.value = `一次最多选择 ${MAX_DOCUMENT_EXPORT} 张单据导出，请缩小选择范围。`
    return
  }
  input.checked ? keys.add(key) : keys.delete(key)
  selectedDocumentKeys.value = [...keys]
  error.value = ''
}
function toggleVisibleDocuments(event: Event) {
  const input = event.target as HTMLInputElement
  const keys = new Set(selectedDocumentKeys.value)
  const next = new Set(keys)
  for (const row of filteredDocuments.value) input.checked ? next.add(documentKey(row)) : next.delete(documentKey(row))
  if (next.size > MAX_DOCUMENT_EXPORT) {
    input.checked = allVisibleDocumentsSelected.value
    error.value = `一次最多选择 ${MAX_DOCUMENT_EXPORT} 张单据导出，请缩小选择范围。`
    return
  }
  error.value = ''
  keys.clear()
  for (const key of next) keys.add(key)
  selectedDocumentKeys.value = [...keys]
}
async function exportSelectedDocuments() {
  if (busy.value || !selectedDocuments.value.length) return
  busy.value = true
  error.value = ''
  try {
    await api.exportDocuments(selectedDocuments.value)
    extraLoaded.documents = false
    const refreshError = await loadExtra('documents')
    if (refreshError) error.value = `文件已生成并开始下载，但单据记录刷新失败：${refreshError}。可稍后刷新记录。`
  }
  catch (reason) { error.value = await getApiErrorMessageAsync(reason) }
  finally { busy.value = false }
}
async function exportDocument(row: SupplierDocument) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  detailDocumentError.value = ''
  try {
    await api.exportDocuments([row])
    extraLoaded.documents = false
    const refreshError = await loadExtra('documents')
    if (refreshError) {
      error.value = `文件已生成并开始下载，但单据记录刷新失败：${refreshError}。可稍后刷新记录。`
      if (detailDocument.value && documentKey(detailDocument.value) === documentKey(row)) detailDocumentError.value = error.value
    }
  } catch (reason) {
    const message = await getApiErrorMessageAsync(reason)
    error.value = message
    if (detailDocument.value && documentKey(detailDocument.value) === documentKey(row)) detailDocumentError.value = message
  }
  finally { busy.value = false }
}
async function exportSelectedOrderImports() {
  const purchases = selectedDocuments.value.filter(row => row.kind === 'PURCHASE')
  if (busy.value || !purchases.length) return
  busy.value = true
  error.value = ''
  try {
    await api.exportOrderImport(purchases)
    extraLoaded.documents = false
    const refreshError = await loadExtra('documents')
    if (refreshError) error.value = `导入模板已生成并开始下载，但单据记录刷新失败：${refreshError}。可稍后刷新记录。`
  }
  catch (reason) { error.value = await getApiErrorMessageAsync(reason) }
  finally { busy.value = false }
}
function failure(reason: unknown) {
  error.value = getApiErrorMessage(reason)
}
async function load() {
  const token = ++generation
  const scopes = memberships.value.map(member => member.factory_id)
  if (!scopes.length) return
  loading.value = true
  error.value = ''
  try {
    const workspaces = await Promise.all(scopes.map(scope => api.workspace(scope)))
    if (token !== generation) return
    const data: SupplierWorkspace = {
      supplier_name: workspaces[0]?.supplier_name ?? '',
      orders: workspaces.flatMap(item => item.orders.map(order => ({ ...order, factory_id: item.factory_id })))
        .sort((a, b) => (stagePriority[orderStage(a)] ?? 9) - (stagePriority[orderStage(b)] ?? 9)
          || a.planned_date.localeCompare(b.planned_date) || a.order_no.localeCompare(b.order_no)),
      shipments: workspaces.flatMap(item => item.shipments.map(shipment => ({ ...shipment, factory_id: item.factory_id })))
        .sort((a, b) => b.created_at.localeCompare(a.created_at)),
    }
    workspace.value = data
    const orderIds = new Set(data.orders.map(order => order.id))
    const selectableOrderIds = new Set(data.orders.filter(canSelectOrder).map(order => order.id))
    selectedOrderIds.value = selectedOrderIds.value.filter(id => selectableOrderIds.has(id))
    if (detailOrderId.value && !orderIds.has(detailOrderId.value)) closeOrderDetail()
    if (acceptOrderId.value && !orderIds.has(acceptOrderId.value)) acceptOrderId.value = ''
    for (const order of data.orders) for (const line of order.lines) {
      if (dateIssueIds[line.id] !== order.issue_id) {
        dirtyDates.delete(line.id)
        dateIssueIds[line.id] = order.issue_id
      }
      if (!dirtyDates.has(line.id)) dates[line.id] = line.promised_date || order.planned_date
    }
    return ''
  } catch (reason) {
    if (token === generation) { workspace.value = null; failure(reason); return error.value }
  } finally {
    if (token === generation) loading.value = false
  }
}
async function refresh() {
  if (busy.value || discovering.value) return
  discovering.value = true
  error.value = ''
  workspace.value = null
  documents.value = []
  activity.value = []
  selectedDocumentKeys.value = []
  closeDocumentDetail()
  closeMergedDocuments()
  extraLoaded.documents = false
  extraLoaded.activity = false
  ++extraGeneration.documents
  ++extraGeneration.activity
  extraLoadingState.documents = false
  extraLoadingState.activity = false
  ++generation
  try {
    const available = await api.memberships()
    memberships.value = available
    if (factoryFilter.value && !available.some(item => item.factory_id === factoryFilter.value)) factoryFilter.value = ''
    if (available.length) {
      await load()
      if (activeTab.value === 'documents' || activeTab.value === 'activity') await loadExtra(activeTab.value)
    }
    else error.value = '暂无可查看的已下单厂区，请确认已授予供应商协同查看权限且东康采购单已发行。'
  } catch (reason) { failure(reason) } finally { discovering.value = false }
}
onMounted(() => { void refresh(); window.addEventListener('keydown', onDetailKeydown) })
onBeforeUnmount(() => window.removeEventListener('keydown', onDetailKeydown))
async function accept(order: SupplierOrder, line: PortalPaper) {
  if (busy.value || !canApprove.value) return
  if (!dates[line.id]) { error.value = '请填写承诺交期'; return }
  busy.value = true
  error.value = ''
  try {
    await api.accept(line, order, order.factory_id, dates[line.id]!)
    dirtyDates.delete(line.id)
    extraLoaded.activity = false
    message.value = `${line.child_no} 已确认接单`
    const refreshError = await load()
    if (refreshError) error.value = `${line.child_no} 已确认接单，但列表刷新失败：${refreshError}。请刷新查看，勿重复接单。`
    if (order.lines.every(item => item.id === line.id || !needsAcceptance(item))) acceptOrderId.value = ''
  } catch (reason) { failure(reason) } finally { busy.value = false }
}
async function onDeliveryFile(event: Event) {
  if (!canEdit.value) return
  const token = ++importGeneration, session = auth.sessionVersion
  const file = (event.target as HTMLInputElement).files?.[0]
  importFile.value = file ?? null
  importPreview.value = null
  selectedImportNotes.value = []; importModes.value = {}
  error.value = ''
  if (!file) return
  busy.value = true
  try {
    const preview = await api.previewDeliveryImport(file)
    if (token !== importGeneration || session !== auth.sessionVersion || !canEdit.value) return
    importPreview.value = preview
    importModes.value = Object.fromEntries(preview.groups.map(group => [importNoteKey(group), !group.ready && group.receipt_link_ready ? 'EXISTING_RECEIPT' : 'SHIPMENT']))
    selectedImportNotes.value = preview.groups.filter(importGroupReady).map(importNoteKey)
  } catch (reason) { if (token === importGeneration && session === auth.sessionVersion) failure(reason) } finally { if (token === importGeneration && session === auth.sessionVersion) busy.value = false }
}
async function confirmDeliveryImport() {
  const token = importGeneration, session = auth.sessionVersion
  if (busy.value || !canEdit.value || !importFile.value || !importPreview.value) return
  const selectedGroups = importPreview.value.groups.filter(group => selectedImportNotes.value.includes(importNoteKey(group)))
  if (!selectedGroups.length || selectedGroups.some(group => !importGroupReady(group))) {
    error.value = '请先选择匹配成功的送货单。'
    return
  }
  busy.value = true
  error.value = ''
  try {
    const result = await api.confirmDeliveryImport(importFile.value, importPreview.value,
      selectedGroups.map(group => ({ factory_id: group.factory_id, delivery_note_no: group.delivery_note_no, ...(importModes.value[importNoteKey(group)] === 'EXISTING_RECEIPT' ? { registration_mode: 'EXISTING_RECEIPT' as const } : {}) })))
    if (token !== importGeneration || session !== auth.sessionVersion || !canEdit.value) return
    importOpen.value = false
    importFile.value = null
    importPreview.value = null
    selectedImportNotes.value = []; importModes.value = {}
    extraLoaded.documents = false
    extraLoaded.activity = false
    activeTab.value = 'shipments'
    message.value = `已提交 ${result.shipments.length} 张供应商送货单；新发货由仓库验收，后补凭证由仓库关联原入库，不重复入库。`
    const refreshError = await load()
    if (refreshError) error.value = `${message.value} 发货已保存，但列表刷新失败：${refreshError}。请刷新查看，勿重复发货。`
  } catch (reason) { if (token === importGeneration && session === auth.sessionVersion) failure(reason) } finally { if (token === importGeneration && session === auth.sessionVersion) busy.value = false }
}
async function download(id: string, factoryId: string, filename: string) {
  error.value = ''
  try { await api.download(id, factoryId, filename) } catch (reason) { error.value = `附件下载失败：${await getApiErrorMessageAsync(reason)}` }
}
</script>

<template>
  <main class="min-h-screen bg-[#f3f8fc] text-slate-800">
    <CartonActionNotice :message="error" @dismiss="error = ''" />
    <header :inert="detailDocumentPinned || mergedDocumentsOpen ? true : undefined" class="sticky top-0 z-20 border-b border-slate-200 bg-white/95 shadow-sm backdrop-blur">
      <div class="mx-auto flex max-w-[1720px] flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
        <div class="flex min-w-0 items-center gap-3">
          <RouterLink to="/modules/pmc-warehouse" aria-label="返回 PMC / 仓管模块" class="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-600 hover:border-teal-300 hover:text-teal-700"><ArrowLeft class="size-4" aria-hidden="true" />返回</RouterLink>
          <div class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-teal-700 text-white"><PackageCheck class="size-5" /></div>
          <div class="min-w-0"><h1 class="truncate text-lg font-bold leading-tight">纸箱供应商协同</h1><p class="truncate text-xs text-slate-500">{{ workspace?.supplier_name || '供应商工作区' }} · 已下单订单 / 接单 / 发货 / 仓库反馈</p></div>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <button ref="usageGuideTrigger" type="button" aria-label="打开供应商协同使用教程" class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-teal-200 bg-teal-50 px-3 text-xs font-semibold text-teal-800 hover:bg-teal-100" @click="showUsageGuide = true"><BookOpen class="size-4" aria-hidden="true" />使用教程</button>
          <RouterLink to="/carton-supplier/carton-mark" class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-teal-200 bg-teal-50 px-3 text-xs font-semibold text-teal-800 hover:bg-teal-100"><FileText class="size-4" />箱唛资料库</RouterLink>
          <CartonFeedbackCenter ref="feedbackCenter" :factory-id="factoryFilter" factory-name="供应商工作区" supplier :supplier-factories="memberships.map(item => ({ id: item.factory_id, name: factoryContexts.find(factory => factory.id === item.factory_id)?.shortName || item.factory_id }))" :viewer-key="`${auth.currentUser?.id ?? ''}:${auth.currentUser?.authorization_version ?? ''}:${auth.sessionVersion}`" />
          <span v-if="memberships.length" class="rounded-lg bg-slate-100 px-3 py-2 text-xs font-semibold text-slate-600">服务厂区：{{ memberships.length }} 个 · 订单合并展示</span>
          <button type="button" :disabled="busy || loading || discovering" class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-600 hover:border-teal-300 disabled:opacity-50" @click="refresh">{{ discovering ? '更新中…' : '刷新' }}</button>
          <AccountMenu />
        </div>
      </div>
      <nav class="mx-auto flex max-w-[1720px] items-center gap-1 overflow-x-auto px-4 sm:px-6" aria-label="供应商协同功能">
        <button type="button" :aria-current="activeTab === 'orders' ? 'page' : undefined" :class="activeTab === 'orders' ? 'border-teal-700 bg-teal-50 text-teal-800' : 'border-transparent text-slate-500 hover:text-teal-700'" class="inline-flex h-11 shrink-0 items-center gap-2 border-b-2 px-4 text-sm font-semibold" @click="openTab('orders')"><ClipboardList class="size-4" />订单管理 <span class="rounded-full bg-white px-2 py-0.5 text-[10px]">{{ orders.length }}</span></button>
        <button type="button" :aria-current="activeTab === 'shipments' ? 'page' : undefined" :class="activeTab === 'shipments' ? 'border-teal-700 bg-teal-50 text-teal-800' : 'border-transparent text-slate-500 hover:text-teal-700'" class="inline-flex h-11 shrink-0 items-center gap-2 border-b-2 px-4 text-sm font-semibold" @click="openTab('shipments')"><Truck class="size-4" />发货与仓库反馈 <span class="rounded-full bg-white px-2 py-0.5 text-[10px]">{{ workspace?.shipments.length ?? 0 }}</span></button>
        <button type="button" :aria-current="activeTab === 'documents' ? 'page' : undefined" :class="activeTab === 'documents' ? 'border-teal-700 bg-teal-50 text-teal-800' : 'border-transparent text-slate-500 hover:text-teal-700'" class="inline-flex h-11 shrink-0 items-center gap-2 border-b-2 px-4 text-sm font-semibold" @click="openTab('documents')"><FileText class="size-4" />采购单与送货单</button>
        <button type="button" :aria-current="activeTab === 'activity' ? 'page' : undefined" :class="activeTab === 'activity' ? 'border-teal-700 bg-teal-50 text-teal-800' : 'border-transparent text-slate-500 hover:text-teal-700'" class="inline-flex h-11 shrink-0 items-center gap-2 border-b-2 px-4 text-sm font-semibold" @click="openTab('activity')"><History class="size-4" />操作日志</button>
        <button type="button" :aria-current="activeTab === 'settlements' ? 'page' : undefined" :class="activeTab === 'settlements' ? 'border-teal-700 bg-teal-50 text-teal-800' : 'border-transparent text-slate-500 hover:text-teal-700'" class="inline-flex h-11 shrink-0 items-center gap-2 border-b-2 px-4 text-sm font-semibold" @click="openTab('settlements')"><FileText class="size-4" />月结对账</button>
      </nav>
    </header>

    <CartonUsageGuide v-if="showUsageGuide" audience="supplier" :factory-name="workspace?.supplier_name || '供应商工作区'" :can-review-supplier-deliveries="false" @close="closeUsageGuide" @supplier-navigate="openUsageGuideDestination" />

    <div class="mx-auto max-w-[1720px] space-y-4 px-4 py-5 sm:px-6">
      <p v-if="error" role="alert" class="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
      <p v-if="message" role="status" class="rounded-xl border border-teal-200 bg-teal-50 p-3 text-sm text-teal-800">{{ message }}</p>
      <p v-if="loading && !workspace" class="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-500">正在读取供应商订单…</p>
      <section v-if="workspace" class="space-y-4">
        <div :inert="detailDocumentPinned || mergedDocumentsOpen ? true : undefined" class="grid gap-3 sm:grid-cols-3">
          <div class="rounded-xl border border-slate-200 bg-white px-4 py-3"><p class="text-xs text-slate-500">已下单订单</p><p class="mt-1 text-xl font-bold text-slate-900">{{ orders.length }} <span class="text-xs font-medium text-slate-500">张</span></p></div>
          <div class="rounded-xl border border-slate-200 bg-white px-4 py-3"><p class="text-xs text-slate-500">待接单 / 待送货 / 已确认接单</p><p class="mt-1 text-xl font-bold text-teal-700">{{ orders.filter(order => ['PENDING_ACCEPTANCE', 'WAITING_SHIPMENT', 'ACCEPTED'].includes(orderStage(order))).length }} <span class="text-xs font-medium text-slate-500">张</span></p></div>
          <div class="rounded-xl border border-slate-200 bg-white px-4 py-3"><p class="text-xs text-slate-500">送货待确定</p><p class="mt-1 text-xl font-bold text-amber-700">{{ orders.filter(order => orderStage(order) === 'RECEIPT_PENDING').length }} <span class="text-xs font-medium text-slate-500">张</span></p></div>
        </div>

        <CartonSupplierMonthlyReview v-if="activeTab === 'settlements'" :factories="memberships" />
        <template v-else-if="activeTab === 'orders'">
          <section class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <div class="flex flex-wrap items-center gap-2 border-b border-slate-100 bg-slate-50/60 p-3">
              <label class="relative min-w-56 flex-1"><Search class="pointer-events-none absolute left-3 top-2.5 size-4 text-slate-400" /><input v-model="search" aria-label="搜索供应商订单" placeholder="搜索客户 / 合同 / PO / 货号 / 订单 / 单据" class="h-9 w-full rounded-lg border border-slate-200 bg-white pl-9 pr-3 text-xs outline-none focus:border-teal-500"></label>
              <select v-model="factoryFilter" aria-label="供应商订单厂区筛选" class="h-9 rounded-lg border border-slate-200 bg-white px-2 text-xs font-semibold text-slate-700"><option value="">全部厂区</option><option v-for="item in memberships" :key="item.factory_id" :value="item.factory_id">{{ factoryDisplayName(item.factory_id) }} · {{ item.supplier_name }}</option></select>
              <select v-model="customerFilter" aria-label="供应商订单客户筛选" class="h-9 rounded-lg border border-slate-200 bg-white px-2 text-xs"><option value="">全部客户</option><option v-for="name in customers" :key="name" :value="name">{{ name }}</option></select>
              <select v-model="statusFilter" aria-label="供应商订单状态筛选" class="h-9 rounded-lg border border-slate-200 bg-white px-2 text-xs"><option value="ALL">全部状态</option><option value="PENDING_ACCEPTANCE">待接单</option><option value="WAITING_SHIPMENT">待送货</option><option value="ACCEPTED">已确认接单</option><option value="RECEIPT_PENDING">送货待确定</option><option value="COMPLETED">已完成</option><option value="CANCELLED">已取消</option><option value="PENDING_ISSUE">变更待发行</option></select>
              <label class="flex items-center gap-1 text-xs text-slate-600">起始日期<input v-model="orderDateFrom" type="date" aria-label="下单日期开始" :max="orderDateTo || undefined" class="h-9 rounded-lg border border-slate-200 bg-white px-2 text-xs"></label>
              <label class="flex items-center gap-1 text-xs text-slate-600">至<input v-model="orderDateTo" type="date" aria-label="下单日期结束" :min="orderDateFrom || undefined" class="h-9 rounded-lg border border-slate-200 bg-white px-2 text-xs"></label>
              <select v-model="orderDateField" aria-label="供应商订单日期口径" class="h-9 rounded-lg border px-2 text-xs"><option value="ORDER">下单日期</option><option value="PLANNED">计划交期</option><option value="PROMISED">最早未交纸品承诺交期</option></select>
              <select v-model="orderSort" aria-label="供应商订单排序" class="h-9 rounded-lg border px-2 text-xs"><option value="DEFAULT">处理阶段 / 计划交期</option><option value="PLANNED_ASC">计划交期由近到远</option><option value="PROMISED_ASC">最早未交纸品承诺交期</option><option value="ORDER_DESC">下单日期由新到旧</option></select>
              <button type="button" class="h-9 rounded-lg border px-3 text-xs" @click="orderSort = 'DEFAULT'">恢复默认排序</button>
              <button type="button" class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-600 hover:text-teal-700" @click="clearFilters">清空筛选</button>
            </div>
            <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-2.5 text-xs">
              <div class="flex flex-wrap items-center gap-3"><span class="font-semibold text-slate-700">订单 {{ visibleOrders.length }} / {{ orders.length }} 张</span><span class="text-slate-500">已选 <b class="text-teal-700">{{ selectedOrderIds.length }}</b> 张订单（筛选外 {{ selectedOrderIds.filter(id => !filteredOrders.some(row => row.id === id)).length }} 张）</span><button type="button" class="font-semibold text-teal-700 hover:text-teal-900" @click="selectedOnly = !selectedOnly">{{ selectedOnly ? '查看全部' : '查看已选' }}</button><button type="button" :disabled="!selectedOrderIds.length" class="text-slate-500 hover:text-slate-800 disabled:opacity-40" @click="selectedOrderIds = []; selectedOnly = false">清空选择</button></div>
              <div class="flex flex-wrap gap-2"><button v-if="canApprove" type="button" :disabled="!selectedOrderIds.length || busy" class="h-9 rounded-lg border border-teal-300 bg-teal-50 px-3 font-semibold text-teal-800 disabled:opacity-40" @click="openBulkAccept">批量确认接单</button><button v-if="canEdit" type="button" :disabled="busy" class="h-9 rounded-lg bg-teal-700 px-3 font-semibold text-white hover:bg-teal-800 disabled:opacity-40" @click="openDeliveryImport">导入送货单</button></div>
            </div>
            <div class="overflow-x-auto">
              <table class="w-full min-w-[1260px] text-left text-xs">
                <thead class="bg-slate-50 text-[11px] font-bold text-slate-600"><tr><th class="w-12 px-4 py-3"><input type="checkbox" aria-label="全选当前筛选订单" :checked="allVisibleSelected" :indeterminate="someVisibleSelected && !allVisibleSelected" :disabled="!selectableVisibleOrders.length" class="size-4 accent-teal-700" @change="toggleVisibleOrders(($event.target as HTMLInputElement).checked)"></th><th class="px-3 py-3">送货厂区</th><th class="px-3 py-3">客户</th><th class="px-3 py-3">合同号 / PO</th><th class="px-3 py-3">货号 / 产品</th><th class="px-3 py-3">下单日期</th><th class="px-3 py-3">计划交期</th><th class="px-3 py-3">交期提醒</th><th class="px-3 py-3">纸品明细</th><th class="px-3 py-3">送货进度</th><th class="px-3 py-3">订单状态</th><th class="px-3 py-3 text-right">操作</th></tr></thead>
                <tbody class="divide-y divide-slate-100">
                  <tr v-for="order in visibleOrders" :key="order.id" class="hover:bg-teal-50/40"><td class="px-4 py-3 align-top"><input v-model="selectedOrderIds" :value="order.id" type="checkbox" :aria-label="`选择订单 ${order.order_no}`" :disabled="!canSelectOrder(order)" class="size-4 accent-teal-700 disabled:cursor-not-allowed disabled:opacity-40"></td><td class="px-3 py-3 align-top font-semibold text-teal-800">{{ factoryDisplayName(order.factory_id) }}</td><td class="px-3 py-3 align-top"><b class="text-slate-900">{{ order.customer_name }}</b></td><td class="px-3 py-3 align-top"><b>{{ order.contract_no }}</b><p class="mt-1 text-slate-500">客户 PO {{ order.customer_po || '纸箱订单未填写' }}</p></td><td class="px-3 py-3 align-top"><b>{{ order.item_no }}</b><p class="mt-1 text-slate-500">{{ order.product_name }}</p></td><td class="px-3 py-3 align-top">{{ order.order_date || '历史未记录' }}</td><td class="px-3 py-3 align-top">{{ order.planned_date || '待确认' }}</td><td class="px-3 py-3 align-top"><span :class="dueReminderClass(order)" class="whitespace-nowrap font-semibold">{{ dueReminder(order).label }}</span></td><td class="px-3 py-3 align-top">{{ order.lines.filter(line => Number(line.required_quantity) > 0).length }} 条有效<span class="ml-1 text-slate-500">· {{ order.lines.filter(line => Number(line.required_quantity) > 0 && line.accepted).length }} 条已接</span></td><td class="px-3 py-3 align-top"><div v-for="line in progressLines(order)" :key="line.id" class="mb-1 whitespace-nowrap"><b>{{ line.packaging_type }}</b> {{ line.received_quantity }} / {{ line.required_quantity }} {{ line.unit }}<span v-if="Number(line.in_transit_quantity) > 0" class="block text-amber-700">在途 {{ line.in_transit_quantity }} {{ line.unit }}</span></div><span v-if="!progressLines(order).length" class="text-slate-400">无有效需求</span></td><td class="px-3 py-3 align-top"><span :class="statusClass(order)" class="inline-flex rounded-full px-2 py-1 text-[11px] font-bold ring-1 ring-inset">{{ orderStatus(order) }}</span></td><td class="px-3 py-3 text-right align-top"><div class="flex justify-end gap-1"><button v-if="canApprove && open(order) && order.lines.some(needsAcceptance)" type="button" :aria-label="`确认订单 ${order.order_no} 接单`" class="rounded-lg border border-teal-200 bg-teal-50 px-2 py-1.5 font-semibold text-teal-800" @click="showAccept(order)">确认接单</button><button type="button" :aria-label="`查看订单 ${order.order_no} 明细`" title="悬停预览整单明细，单击后保持显示" aria-haspopup="dialog" class="rounded-lg border border-slate-200 bg-white px-3 py-1.5 font-semibold text-slate-700 hover:border-teal-300 hover:text-teal-700" @mouseenter="showOrderDetail(order.id)" @mouseleave="closeOrderDetailPreview" @focus="showOrderDetail(order.id)" @blur="closeOrderDetailPreview" @click="showOrderDetail(order.id, true)">明细</button></div></td></tr>
                  <tr v-if="!visibleOrders.length"><td colspan="12" class="px-4 py-10 text-center text-slate-500">{{ orders.length ? '没有符合当前筛选条件的订单' : '暂无已下单订单；请联系内部仓管确认订单已锁定。' }}</td></tr>
                </tbody>
              </table>
            </div>
          </section>

          <div v-if="detailOrder" data-testid="supplier-order-detail-overlay" class="fixed inset-0 z-[62] flex items-center justify-center p-4" :class="detailPinned ? 'pointer-events-auto bg-slate-950/45' : 'pointer-events-none bg-slate-950/25'" @click.self="closeOrderDetail">
            <div role="dialog" aria-labelledby="supplier-order-detail-title" :aria-modal="detailPinned ? 'true' : undefined" :inert="detailPinned ? undefined : true" class="flex max-h-[88vh] w-full max-w-[1400px] flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
              <div class="flex shrink-0 items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
                <div><h2 id="supplier-order-detail-title" class="text-lg font-bold text-slate-950">订单明细 · {{ factoryDisplayName(detailOrder.factory_id) }} · {{ detailOrder.customer_name }}</h2><p class="mt-1 text-xs text-teal-700">{{ detailPinned ? '已固定显示 · 查看纸品和交付资料' : '悬停预览 · 单击明细可固定查看' }}</p></div>
                <button type="button" aria-label="关闭供应商订单明细" class="rounded-lg p-2 text-slate-400 hover:bg-slate-100" @click="closeOrderDetail"><X class="size-4" /></button>
              </div>
              <div class="min-h-0 overflow-auto">
                <div class="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 bg-slate-50/60 p-4">
                  <div><p class="text-sm font-bold text-slate-900">合同 {{ detailOrder.contract_no }} · 货号 {{ detailOrder.item_no }}</p><p class="mt-1 text-xs text-slate-500">客户 PO {{ detailOrder.customer_po || '纸箱订单未填写' }} · {{ detailOrder.product_name }}</p><p class="mt-1 text-xs text-slate-500">下单日期 {{ detailOrder.order_date || '历史未记录' }} · 计划交期 {{ detailOrder.planned_date || '待确认' }} · {{ orderStatus(detailOrder) }}</p><p class="mt-1 text-xs text-slate-500">纸箱采购单据 {{ detailOrder.document_no }}</p><p v-if="detailOrder.awaiting_issue" class="mt-2 text-xs font-semibold text-amber-700">订单有尚未发行的变更，旧承诺暂停执行；请等待新版本发行后重新确认接单。</p><p v-else-if="!open(detailOrder)" class="mt-2 text-xs text-slate-500">{{ detailOrder.status === 'COMPLETED' ? '订单已收齐' : '订单已取消' }}，不可接单或发货。</p></div>
                  <div class="flex flex-wrap items-center gap-2"><button v-for="file in detailOrder.attachments" :key="file.id" type="button" class="rounded-lg border border-teal-200 bg-teal-50 px-2.5 py-1.5 text-xs font-semibold text-teal-700" @click="download(file.id, detailOrder.factory_id, file.filename)">{{ file.filename }} · v{{ file.version }}</button></div>
                </div>
                <div class="overflow-x-auto"><table class="w-full min-w-[900px] text-left text-xs"><thead class="bg-slate-50 text-[11px] font-bold text-slate-600"><tr><th class="px-3 py-3">纸品子单</th><th class="px-3 py-3">纸质 / 规格</th><th class="px-3 py-3">需求数量</th><th class="px-3 py-3">已入库</th><th class="px-3 py-3">在途 / 剩余未送</th><th class="px-3 py-3">接单 / 承诺交期</th></tr></thead><tbody class="divide-y divide-slate-100"><tr v-for="line in detailOrder.lines" :key="line.id"><td class="px-3 py-3"><b>{{ line.packaging_type }} · {{ line.child_no }}</b><p v-if="line.shipping_blocked_reason" class="mt-1 text-[11px] text-amber-700">{{ line.shipping_blocked_reason }}</p></td><td class="px-3 py-3">{{ line.paper_quality }} · {{ line.specification }} {{ line.dimension_unit }}</td><td class="px-3 py-3">{{ line.required_quantity }} {{ line.unit }}</td><td class="px-3 py-3">{{ line.received_quantity }} {{ line.unit }}</td><td class="px-3 py-3">{{ line.in_transit_quantity }} / {{ line.remaining_to_ship }} {{ line.unit }}</td><td class="px-3 py-3">{{ Number(line.required_quantity) <= 0 ? '无需接单' : line.accepted ? '已确认' : '待确认' }} · {{ Number(line.required_quantity) <= 0 ? '需求已归零' : line.promised_date || '未承诺' }}</td></tr></tbody></table></div>
              </div>
              <div v-if="detailPinned" class="flex shrink-0 justify-end border-t border-slate-200 px-5 py-3"><button type="button" class="h-9 rounded-lg border border-slate-200 px-4 text-xs font-bold text-slate-600" @click="closeOrderDetail">关闭</button></div>
            </div>
          </div>

          <div v-if="canApprove && acceptOrder" class="fixed inset-0 z-[64] flex items-center justify-center bg-slate-950/45 p-4" @click.self="acceptOrderId = ''">
            <div role="dialog" aria-modal="true" aria-labelledby="supplier-accept-title" class="flex max-h-[88vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
              <div class="flex items-start justify-between border-b border-slate-200 p-5"><div><h2 id="supplier-accept-title" class="text-lg font-bold">确认接单 · {{ factoryDisplayName(acceptOrder.factory_id) }}</h2><p class="mt-1 text-xs text-slate-500">{{ acceptOrder.customer_name }} · 合同 {{ acceptOrder.contract_no }} · 货号 {{ acceptOrder.item_no }}</p></div><button type="button" aria-label="关闭接单窗口" class="rounded-lg p-2 text-slate-500 hover:bg-slate-100" @click="acceptOrderId = ''"><X class="size-4" /></button></div>
              <div class="min-h-0 overflow-auto p-5"><p v-if="error" role="alert" class="mb-3 rounded-lg border border-red-200 bg-red-50 p-2 text-xs text-red-700">{{ error }}</p><p v-if="message" role="status" class="mb-3 rounded-lg border border-teal-200 bg-teal-50 p-2 text-xs text-teal-800">{{ message }}</p><p class="mb-3 text-xs text-slate-500">逐条确认纸品及承诺交期；全部确认后，订单进入可发货状态。</p><div v-for="line in acceptOrder.lines" :key="line.id" class="flex flex-wrap items-center gap-3 border-b border-slate-100 py-3 text-xs"><div class="min-w-64 flex-1"><b>{{ line.packaging_type }} · {{ line.child_no }}</b><p class="mt-1 text-slate-500">{{ line.paper_quality }} · {{ line.specification }} {{ line.dimension_unit }} · 需求 {{ line.required_quantity }} {{ line.unit }}</p><p v-if="line.promised_date && !line.accepted" class="mt-1 text-amber-700">旧交期 {{ line.promised_date }}，需重新确认</p></div><span v-if="Number(line.required_quantity) <= 0" class="font-semibold text-slate-500">需求已归零 · 无需接单</span><span v-else-if="line.accepted" class="font-semibold text-emerald-700">已确认 · {{ line.promised_date }}</span><template v-else><label class="font-semibold text-slate-600">承诺交期 <input v-model="dates[line.id]" @input="dirtyDates.add(line.id)" type="date" :aria-label="`${line.child_no} 承诺交期`" :disabled="busy || !open(acceptOrder)" class="ml-1 h-9 rounded-lg border border-slate-200 px-2"></label><button type="button" :disabled="busy || !open(acceptOrder) || Number(line.required_quantity) <= 0" class="h-9 rounded-lg bg-teal-700 px-3 font-semibold text-white disabled:opacity-40" @click="accept(acceptOrder, line)">确认接单</button></template></div></div>
              <div class="flex justify-end border-t border-slate-200 p-4"><button type="button" class="rounded-lg border border-slate-200 px-4 py-2 text-xs font-semibold" @click="acceptOrderId = ''">关闭</button></div>
            </div>
          </div>

          <div v-if="canApprove && bulkAcceptOpen" class="fixed inset-0 z-[64] flex items-center justify-center bg-slate-950/45 p-4" @click.self="bulkAcceptOpen = false">
            <div role="dialog" aria-modal="true" aria-labelledby="supplier-bulk-accept-title" class="flex max-h-[88vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
              <div class="flex items-start justify-between border-b border-slate-200 p-5"><div><h2 id="supplier-bulk-accept-title" class="text-lg font-bold">批量确认接单 · {{ selectedOrders.length }} 张订单</h2><p class="mt-1 text-xs text-slate-500">按厂区分别提交；同一厂区的纸品全部校验通过后才一起保存。</p></div><button type="button" aria-label="关闭批量接单窗口" class="rounded-lg p-2 text-slate-500" @click="bulkAcceptOpen = false"><X class="size-4" /></button></div>
              <div class="min-h-0 space-y-3 overflow-auto p-5"><div v-for="order in selectedOrders" :key="order.id" class="rounded-lg border border-slate-200 p-3"><h3 class="mb-2 text-sm font-bold">{{ factoryDisplayName(order.factory_id) }} · {{ order.customer_name }} · {{ order.contract_no }} · {{ order.item_no }}</h3><div v-for="line in order.lines.filter(needsAcceptance)" :key="line.id" class="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 py-2 text-xs"><span>{{ line.packaging_type }} · {{ line.child_no }} · 需求 {{ line.required_quantity }} {{ line.unit }}</span><label>承诺交期 <input v-model="dates[line.id]" @input="dirtyDates.add(line.id)" type="date" :aria-label="`批量接单 ${line.child_no} 承诺交期`" :disabled="busy" class="ml-1 h-9 rounded-lg border border-slate-200 px-2"></label></div></div></div>
              <div class="flex justify-end gap-2 border-t border-slate-200 p-4"><button type="button" :disabled="busy" class="rounded-lg border border-slate-200 px-4 py-2 text-xs font-semibold" @click="bulkAcceptOpen = false">取消</button><button type="button" :disabled="busy" class="rounded-lg bg-teal-700 px-4 py-2 text-xs font-bold text-white disabled:opacity-40" @click="confirmBulkAccept">{{ busy ? '正在确认…' : '确认所选订单接单' }}</button></div>
            </div>
          </div>

          <div v-if="canEdit && importOpen" class="fixed inset-0 z-[64] flex items-center justify-center bg-slate-950/45 p-4" @click.self="closeDeliveryImport">
            <div role="dialog" aria-modal="true" aria-labelledby="supplier-delivery-import-title" class="flex max-h-[90vh] w-full max-w-6xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
              <div class="flex items-start justify-between border-b border-slate-200 p-5"><div><h2 id="supplier-delivery-import-title" class="text-lg font-bold">导入东康送货单</h2><p class="mt-1 text-xs text-slate-500">上传原系统 Excel，核对厂区、合同、货号、纸品及发货数量后确认。确认后送到各厂区仓库待收货，不立即计入库存。</p></div><button type="button" aria-label="关闭送货单导入" :disabled="busy" class="rounded-lg p-2 text-slate-500 hover:bg-slate-100 disabled:opacity-40" @click="closeDeliveryImport"><X class="size-4" /></button></div>
              <div class="min-h-0 space-y-4 overflow-auto p-5">
                <label class="block text-sm font-semibold">选择送货明细表（.xls / .xlsx）<input type="file" accept=".xls,.xlsx" :disabled="busy" class="mt-2 block w-full rounded-lg border border-slate-200 p-2 text-xs" @change="onDeliveryFile"></label>
                <p v-if="busy" role="status" class="text-sm text-teal-700">正在处理送货单…</p>
                <p v-if="error" role="alert" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
                <p v-if="importPreview" class="text-xs text-slate-600">{{ importPreview.filename }} · 共 {{ importPreview.row_count }} 行 · {{ importPreview.groups.length }} 张送货单；无单候选将送仓库逐条核实，确认发货不等于入库。</p>
                <section v-for="group in importPreview?.groups ?? []" :key="importNoteKey(group)" class="rounded-xl border p-3" :class="importGroupReady(group) ? 'border-teal-200' : 'border-amber-200 bg-amber-50/40'">
                  <div class="flex flex-wrap items-center gap-3 text-sm"><input v-model="selectedImportNotes" :value="importNoteKey(group)" type="checkbox" :disabled="!importGroupReady(group) || busy" :aria-label="`确认送货单 ${group.delivery_note_no || '未填单号'}`" class="size-4 accent-teal-700"><b>{{ group.delivery_note_no || '未填送货单号' }}</b><span>{{ factoryDisplayName(group.factory_id) }} · {{ group.delivery_date || '未填日期' }}</span><span :class="importGroupReady(group) ? 'text-teal-700' : 'text-amber-700'" class="font-semibold">{{ importModes[importNoteKey(group)] === 'EXISTING_RECEIPT' && group.receipt_link_ready ? '后补凭证 · 仅关联已有入库' : group.ready ? group.rows.some(row => row.status === 'AD_HOC_REVIEW') ? '可发货 · 含仓库待核实无单纸品' : '可确认发货' : '需核对' }}</span></div>
                  <div v-if="group.receipt_link_ready" class="mt-3 rounded-lg bg-teal-50 p-3 text-xs text-teal-900"><p>发现 {{ group.existing_receipt_count }} 张可匹配的已入库记录。若本单是已手动收料的后补凭证，请选择仅关联；确为新一批到货才选择新发货。</p><label class="mt-2 flex items-center gap-2">提交方式<select v-model="importModes[importNoteKey(group)]" :aria-label="`送货单 ${group.delivery_note_no} 提交方式`" :disabled="busy" class="rounded border bg-white p-2"><option value="SHIPMENT" :disabled="!group.ready">新发货，等待仓库验收</option><option value="EXISTING_RECEIPT">后补凭证，仅关联已有入库</option></select></label><p class="mt-2">由仓库选择原收料并确认关联；原数量、价格和验收日期保持不变。</p></div><p v-for="issue in group.issues" :key="issue" class="mt-2 text-xs text-amber-700">{{ issue }}</p>
                  <div class="mt-2 overflow-x-auto"><table class="w-full min-w-[820px] text-left text-xs"><thead class="bg-slate-50 text-slate-600"><tr><th class="p-2">原表位置</th><th class="p-2">客户单号 / 客户料号</th><th class="p-2">纸质 / 规格</th><th class="p-2">发货量</th><th class="p-2">送货单价</th><th class="p-2">匹配订单 / 纸品</th><th class="p-2">校验</th></tr></thead><tbody><tr v-for="row in group.rows" :key="`${row.source_sheet}-${row.source_row}`" class="border-t border-slate-100"><td class="p-2">{{ row.source_sheet }} · {{ row.source_row }}</td><td class="p-2">{{ row.contract_no || '—' }} / {{ row.item_no || '—' }}</td><td class="p-2">{{ row.paper_quality || '—' }} · {{ row.specification || '—' }}</td><td class="p-2">{{ row.delivered_quantity }}</td><td class="p-2">{{ Number(row.unit_price) > 0 ? row.unit_price : '未填写' }}</td><td class="p-2">{{ row.order_no || (row.status === 'AD_HOC_REVIEW' ? '无单待仓库核实' : '未匹配') }} {{ row.child_no }}</td><td class="p-2" :class="importModes[importNoteKey(group)] === 'EXISTING_RECEIPT' && group.receipt_link_ready ? 'text-teal-700' : row.status === 'READY' ? 'text-teal-700' : row.status === 'AD_HOC_REVIEW' ? 'text-amber-700' : 'text-red-700'">{{ importModes[importNoteKey(group)] === 'EXISTING_RECEIPT' && group.receipt_link_ready ? '已匹配原入库凭证，等待仓库选择并关联' : row.reason }}</td></tr></tbody></table></div>
                </section>
              </div>
              <div class="flex justify-end gap-2 border-t border-slate-200 p-4"><button type="button" :disabled="busy" class="rounded-lg border border-slate-200 px-4 py-2 text-xs font-semibold" @click="closeDeliveryImport">取消</button><button type="button" :disabled="busy || !selectedImportNotes.length" class="rounded-lg bg-teal-700 px-4 py-2 text-xs font-bold text-white disabled:opacity-40" @click="confirmDeliveryImport">确认 {{ selectedImportNotes.length }} 张送货单{{ selectedImportNotes.some(key => importModes[key] === 'EXISTING_RECEIPT') ? '（含后补凭证）' : '发货' }}</button></div>
            </div>
          </div>
        </template>

        <template v-else-if="activeTab === 'shipments'">
          <section class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"><div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 p-4"><div><h2 class="text-sm font-bold">发货与仓库反馈</h2><p class="mt-1 text-xs text-slate-500">供应商上传原系统送货单并确认发货后，记录按送货厂区进入仓库待确认；仓库填写实收与不合格数量。</p></div><div class="flex flex-wrap items-center gap-2"><select v-model="factoryFilter" aria-label="供应商发货厂区筛选" class="h-9 rounded-lg border border-slate-200 bg-white px-2 text-xs font-semibold text-slate-700"><option value="">全部厂区</option><option v-for="item in memberships" :key="item.factory_id" :value="item.factory_id">{{ factoryDisplayName(item.factory_id) }} · {{ item.supplier_name }}</option></select></div></div><CartonShipmentFilters v-model="shipmentFilters" :rows="workspace?.shipments ?? []" @clear="factoryFilter = ''" /><p class="px-4 pt-3 text-xs text-slate-500">显示 {{ matchingShipments.length }} 张送货单</p><div class="space-y-0 divide-y divide-slate-100"><article v-for="shipment in matchingShipments" :key="shipment.id" class="p-4"><div class="flex flex-wrap items-center justify-between gap-2"><div class="flex flex-wrap items-center gap-3"><b class="text-sm">{{ shipment.delivery_note_no }}</b><span class="text-xs font-semibold text-teal-800">送往{{ factoryDisplayName(shipment.factory_id) }}</span><span class="text-xs text-slate-500">{{ shipment.delivery_date }}</span><span class="rounded-full bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-700">{{ shipmentStatus(shipment) }}</span></div><span class="text-xs text-slate-500">{{ shipment.lines.length }} 条纸品<span v-if="shipment.source_filename"> · 来源 {{ shipment.source_filename }}</span></span></div><p v-for="line in shipment.lines" :key="line.id" class="mt-2 text-xs text-slate-600">{{ line.source_type === 'AD_HOC_REVIEW' ? (shipment.status === 'SENT' ? '无单待核实' : '无单纸品') : line.order_no + ' · ' + line.child_no }} · {{ line.packaging_type }} · 发货 {{ line.quantity }} {{ line.unit }}<template v-for="accepted in shipment.acceptance_lines.filter(item => item.shipment_line_id === line.id)" :key="accepted.shipment_line_id"> · 实收 {{ accepted.received_quantity }} · 不可用 {{ Number(accepted.damaged_quantity) + Number(accepted.rejected_quantity) + Number(accepted.unusable_quantity) }} · {{ accepted.no_order_decision === 'SAMPLE' ? '样板箱已确认' : accepted.no_order_decision === 'WRONG_DELIVERY' ? '送错货已拒收' : '' }} · {{ accepted.difference_reason }}</template></p><details v-if="shipment.acceptance_history?.length" class="mt-3 text-xs text-slate-500"><summary class="cursor-pointer">验收历史（已冲销记录不计入当前实收）</summary><p v-for="(history, index) in shipment.acceptance_history" :key="index" class="mt-1">{{ history.acceptance_date }} · {{ history.status === 'REVERSED' ? '已冲销' : '验收记录' }} · {{ history.lines.map(line => '实收 ' + line.received_quantity).join('；') }}</p></details></article><p v-if="!matchingShipments.length" class="p-10 text-center text-sm text-slate-500">暂无符合条件的发货单</p></div></section>
        </template>

        <template v-else-if="activeTab === 'documents'">
          <section :inert="detailDocumentPinned || mergedDocumentsOpen ? true : undefined" class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 p-4"><div><h2 class="text-base font-bold">采购单与送货单</h2><p class="mt-1 text-xs text-slate-500">仓库同一次批量确认的订单自动合并为一张采购单，保留各订单明细；勾选采购单可导出东康导入模板或统一预览导出。</p></div><div class="flex flex-wrap gap-2"><button type="button" :disabled="busy || !selectedDocuments.some(row => row.kind === 'PURCHASE')" class="h-9 rounded-lg border border-teal-300 bg-teal-50 px-4 text-xs font-bold text-teal-800 disabled:opacity-40" @click="exportSelectedOrderImports">导出东康导入模板（{{ selectedDocuments.filter(row => row.kind === 'PURCHASE').length }} 张采购单）</button><button type="button" :disabled="!selectedDocuments.length" class="h-9 rounded-lg bg-teal-700 px-4 text-xs font-bold text-white disabled:opacity-40" @click="openMergedDocuments">预览并导出 {{ selectedDocuments.length }} 张单据</button></div></div>
            <div class="flex flex-wrap items-center gap-2 border-b border-slate-100 bg-slate-50/60 p-3">
              <label class="relative min-w-56 flex-1"><Search class="pointer-events-none absolute left-3 top-2.5 size-4 text-slate-400" /><input v-model="documentSearch" aria-label="搜索供应商单据" placeholder="搜索单据号 / 订单 / 客户 / 合同 / PO / 货号" class="h-9 w-full rounded-lg border border-slate-200 bg-white pl-9 pr-3 text-xs"></label>
              <select v-model="documentFactory" aria-label="单据厂区筛选" class="h-9 rounded-lg border border-slate-200 bg-white px-2 text-xs"><option value="">全部厂区</option><option v-for="item in memberships" :key="item.factory_id" :value="item.factory_id">{{ factoryDisplayName(item.factory_id) }}</option></select>
              <select v-model="documentKind" aria-label="单据类型筛选" class="h-9 rounded-lg border border-slate-200 bg-white px-2 text-xs"><option value="">全部类型</option><option value="PURCHASE">采购单</option><option value="DELIVERY">送货单</option></select>
              <select v-model="documentStatus" aria-label="单据状态筛选" class="h-9 rounded-lg border border-slate-200 bg-white px-2 text-xs"><option value="">全部状态</option><option value="已发行">已发行</option><option value="SENT">待仓库确认</option><option value="RECEIVED">已核实</option><option value="RECEIPT_REVERSED">收料已冲销，待更正</option><option value="NOT_RECEIVED">仓库未收到</option></select>
              <label class="text-xs">日期从 <input v-model="documentDateFrom" type="date" aria-label="单据日期开始" class="h-9 rounded-lg border border-slate-200 px-2"></label><label class="text-xs">至 <input v-model="documentDateTo" type="date" aria-label="单据日期结束" class="h-9 rounded-lg border border-slate-200 px-2"></label>
              <button type="button" class="h-9 rounded-lg border border-slate-200 px-3 text-xs" @click="documentSearch = ''; documentFactory = ''; documentKind = ''; documentStatus = ''; documentDateFrom = ''; documentDateTo = ''">清空筛选</button>
            </div>
            <div class="flex items-center gap-3 border-b border-slate-100 px-4 py-2 text-xs"><span>单据 {{ filteredDocuments.length }} / {{ documents.length }} 张</span><span>已选 {{ selectedDocuments.length }} 张单据 · {{ mergedDocumentOrders.length }} 张订单</span><span class="text-slate-400">一次最多 100 张单据</span><button type="button" :disabled="!selectedDocumentKeys.length" class="text-slate-500 disabled:opacity-40" @click="selectedDocumentKeys = []">清空选择</button></div>
            <div class="overflow-x-auto"><table class="w-full min-w-[980px] text-left text-xs"><thead class="bg-slate-50 font-bold text-slate-600"><tr><th class="px-4 py-3"><input type="checkbox" aria-label="全选当前筛选单据" :checked="allVisibleDocumentsSelected" @change="toggleVisibleDocuments($event)"></th><th class="px-3 py-3">类型</th><th class="px-3 py-3">送货厂区</th><th class="px-3 py-3">单据号</th><th class="px-3 py-3">日期</th><th class="px-3 py-3">包含订单</th><th class="px-3 py-3">纸品条数</th><th class="px-3 py-3">状态</th><th class="px-3 py-3" title="从启用导出次数记录起，每次成功生成 Excel 累计一次；合并导出涉及的每张单据分别计一次">导出次数</th><th class="px-3 py-3 text-right">操作</th></tr></thead><tbody class="divide-y divide-slate-100"><tr v-for="row in filteredDocuments" :key="documentKey(row)"><td class="px-4 py-3"><input :checked="selectedDocumentKeys.includes(documentKey(row))" type="checkbox" :aria-label="`选择单据 ${row.document_no}`" @change="toggleDocument(row, $event)"></td><td class="px-3 py-3">{{ row.kind === 'PURCHASE' ? (row.is_batch ? '合并采购单' : '采购单') : '送货单' }}</td><td class="px-3 py-3">{{ factoryDisplayName(row.factory_id) }}</td><td class="px-3 py-3 font-bold">{{ row.document_no }}</td><td class="px-3 py-3">{{ row.date }}</td><td class="px-3 py-3">{{ row.orders.length }} 张订单<span v-if="row.unmatched_line_count"> · {{ row.unmatched_line_count }} 条无单纸品</span> · {{ row.orders.map(item => item.contract_no).join('、') }}</td><td class="px-3 py-3">{{ row.lines.length }}</td><td class="px-3 py-3">{{ row.status === 'RECEIPT_REVERSED' ? '收料已冲销，待更正' : row.status === 'SENT' ? '待仓库确认' : row.status === 'RECEIVED' ? '已核实' : row.status === 'NOT_RECEIVED' ? '仓库未收到' : row.status }}</td><td class="px-3 py-3" :aria-label="`${row.document_no} 导出 ${row.export_count ?? 0} 次`">{{ row.export_count ?? 0 }}</td><td class="px-3 py-3 text-right"><button type="button" :aria-label="`查看单据 ${row.document_no} 明细`" title="悬停预览单据明细，单击后保持显示" aria-haspopup="dialog" class="rounded-lg border border-slate-200 px-3 py-1.5 font-semibold" @mouseenter="showDocumentDetail(row)" @mouseleave="closeDocumentDetailPreview" @focus="showDocumentDetail(row)" @blur="closeDocumentDetailPreview" @click="showDocumentDetail(row, true)">明细</button></td></tr><tr v-if="!filteredDocuments.length"><td colspan="10" class="p-10 text-center text-slate-500">{{ extraLoading ? '正在读取单据…' : '暂无符合条件的单据' }}</td></tr></tbody></table></div>
          </section>
          <div v-if="detailDocument" data-testid="supplier-document-detail-overlay" class="fixed inset-0 z-[64] flex items-center justify-center p-4" :class="detailDocumentPinned ? 'pointer-events-auto bg-slate-950/45' : 'pointer-events-none bg-slate-950/25'" @click.self="closeDocumentDetail">
            <div ref="documentDetailDialog" role="dialog" aria-labelledby="supplier-document-title" :aria-modal="detailDocumentPinned ? 'true' : undefined" :inert="detailDocumentPinned ? undefined : true" class="flex max-h-[88vh] w-full max-w-5xl flex-col rounded-2xl bg-white shadow-2xl" @keydown="trapDialogTab">
              <div class="flex justify-between border-b border-slate-200 p-5"><div><h2 id="supplier-document-title" class="text-lg font-bold">{{ detailDocument.kind === 'PURCHASE' ? (detailDocument.is_batch ? '合并采购单' : '采购单') : '送货单' }} · {{ detailDocument.document_no }}</h2><p class="mt-1 text-xs text-slate-500">{{ factoryDisplayName(detailDocument.factory_id) }} · {{ detailDocument.date }} · {{ detailDocument.orders.length }} 张订单<span v-if="detailDocument.unmatched_line_count"> · {{ detailDocument.unmatched_line_count }} 条无单明细</span></p><p v-if="detailDocument.source_filename" class="mt-1 text-xs text-slate-500">原送货文件：{{ detailDocument.source_filename }}</p><p class="mt-1 text-xs text-teal-700">{{ detailDocumentPinned ? '已固定显示 · 可滚动查看单据' : '悬停预览 · 单击明细可固定查看' }}</p></div><button v-if="detailDocumentPinned" type="button" aria-label="关闭单据明细" @click="closeDocumentDetail"><X class="size-4" /></button></div>
              <div class="min-h-0 overflow-auto p-5"><div v-for="order in detailDocument.orders" :key="order.order_no" class="mb-2 rounded-lg border border-slate-200 p-3 text-xs"><b>{{ order.customer_name }} · {{ order.contract_no }} · {{ order.item_no }}</b><span class="ml-2 text-slate-500">PO {{ order.customer_po || '未填写' }} · 订单 {{ order.order_no }}</span><span v-if="order.product_name" class="ml-2 text-slate-500">{{ order.product_name }}</span></div><table class="w-full min-w-[720px] text-left text-xs"><thead class="bg-slate-50"><tr><th class="p-2">订单 / 纸品</th><th class="p-2">纸品类型</th><th class="p-2">纸质 / 规格</th><th class="p-2">{{ detailDocument.kind === 'PURCHASE' ? '变更前 / 本次变化 / 变更后' : '发货 / 实收' }}</th></tr></thead><tbody><tr v-for="(line, index) in detailDocument.lines" :key="`${line.order_no}|${line.child_no}|${index}`" class="border-t border-slate-100"><td class="p-2">{{ line.child_no || `无单纸品 · ${line.contract_no || '无合同号'} / ${line.item_no || '无货号'}` }}<span v-if="line.source_document_no" class="mt-1 block text-slate-500">原采购单 {{ line.source_document_no }}</span></td><td class="p-2">{{ line.packaging_type }}</td><td class="p-2">{{ line.paper_quality }} · {{ line.specification }}</td><td class="p-2">{{ detailDocument.kind === 'PURCHASE' ? `${line.before_quantity} / ${line.change_quantity} / ${line.quantity}` : `${line.quantity} / ${line.received_quantity || 0}` }} {{ line.unit }}</td></tr></tbody></table></div>
              <p v-if="detailDocumentPinned && detailDocumentError" role="alert" class="mx-5 mb-3 shrink-0 rounded-lg bg-red-50 p-3 text-xs text-red-700">{{ detailDocumentError }}</p>
              <div v-if="detailDocumentPinned" class="flex shrink-0 justify-end border-t border-slate-200 p-4"><button type="button" :disabled="busy" class="h-9 rounded-lg bg-teal-700 px-4 text-xs font-bold text-white disabled:opacity-40" @click="exportDocument(detailDocument)">导出这张{{ detailDocument.kind === 'PURCHASE' ? '采购单' : '送货单' }}</button></div>
            </div>
          </div>
          <div v-if="mergedDocumentsOpen && selectedDocuments.length" class="fixed inset-0 z-[65] flex items-center justify-center bg-slate-950/45 p-4" @click.self="closeMergedDocuments">
            <div ref="mergedDocumentsDialog" role="dialog" aria-modal="true" aria-labelledby="supplier-merged-document-title" class="flex max-h-[88vh] w-full max-w-6xl flex-col rounded-2xl bg-white shadow-2xl" @keydown="trapDialogTab">
              <div class="flex shrink-0 items-start justify-between gap-3 border-b border-slate-200 p-5"><div><h2 id="supplier-merged-document-title" class="text-lg font-bold">合并预览 · {{ selectedDocuments.length }} 张单据 / {{ mergedDocumentOrders.length }} 张订单<span v-if="mergedUnmatchedLines.length"> / {{ mergedUnmatchedLines.length }} 条无单纸品</span></h2><p class="mt-1 text-xs text-slate-500">按厂区和订单汇总；同一订单涉及多张单据时，纸品行按原单据分别列示，数量不重复相加。</p></div><button type="button" aria-label="关闭合并预览" @click="closeMergedDocuments"><X class="size-4" /></button></div>
              <div class="min-h-0 space-y-4 overflow-auto p-5"><section v-for="(entry, index) in mergedUnmatchedLines" :key="`${documentKey(entry.document)}-unmatched-${index}`" class="rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs"><b>无单纸品 · {{ factoryDisplayName(entry.document.factory_id) }} · 送货单 {{ entry.document.document_no }}</b><p class="mt-1">客户单号 {{ entry.line.contract_no || '未填写' }} · 客户料号 {{ entry.line.item_no || '未填写' }} · {{ entry.line.packaging_type }} · {{ entry.line.paper_quality }} / {{ entry.line.specification }} · 发货 {{ entry.line.quantity }} {{ entry.line.unit }} · 仓库实收 {{ entry.line.received_quantity || 0 }}</p><p class="mt-1 text-amber-800">{{ entry.document.status === 'SENT' ? '仓库待核实是否确需无单入库' : '仓库处理记录已保留在送货单中' }}</p></section><section v-for="group in mergedDocumentOrders" :key="`${group.factory_id}|${group.order.order_no}`" class="rounded-xl border border-slate-200"><div class="border-b border-slate-100 bg-slate-50 px-4 py-3 text-xs"><b>{{ factoryDisplayName(group.factory_id) }} · {{ group.order.customer_name }} · 合同 {{ group.order.contract_no }} · 货号 {{ group.order.item_no }}</b><p class="mt-1 text-slate-500">客户 PO {{ group.order.customer_po || '纸箱订单未填写' }} · 订单 {{ group.order.order_no }} · {{ group.sources.length }} 张关联单据</p></div><div v-for="source in group.sources" :key="documentKey(source.document)" class="border-t border-slate-100 px-4 py-3 text-xs"><p class="font-bold text-teal-800">{{ source.document.kind === 'PURCHASE' ? '采购单' : '送货单' }} {{ source.document.document_no }} · {{ source.document.date }}</p><div v-for="(line, index) in source.lines" :key="`${line.child_no}|${index}`" class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-slate-600"><span>{{ line.child_no }} · {{ line.packaging_type }} · {{ line.paper_quality }} / {{ line.specification }}</span><span>{{ source.document.kind === 'PURCHASE' ? `变更前 ${line.before_quantity} · 本次变化 ${line.change_quantity} · 变更后 ${line.quantity}` : `发货 ${line.quantity} · 实收 ${line.received_quantity || 0}` }} {{ line.unit }}</span></div></div></section></div>
              <div class="flex shrink-0 justify-end gap-2 border-t border-slate-200 p-4"><button type="button" class="h-9 rounded-lg border border-slate-200 px-4 text-xs font-bold" @click="closeMergedDocuments">关闭</button><button type="button" :disabled="busy" class="h-9 rounded-lg bg-teal-700 px-4 text-xs font-bold text-white disabled:opacity-40" @click="exportSelectedDocuments">导出所选 {{ selectedDocuments.length }} 张 Excel</button></div>
            </div>
          </div>
        </template>

        <template v-else-if="activeTab === 'activity'">
          <section class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"><div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 p-4"><div><h2 class="text-base font-bold">操作日志</h2><p class="mt-1 text-xs text-slate-500">显示本供应商可见订单的采购发行、接单、送货与仓库反馈。</p></div><div class="flex gap-2"><input v-model="activitySearch" aria-label="搜索供应商操作日志" placeholder="搜索操作 / 单据 / 人员" class="h-9 rounded-lg border border-slate-200 px-3 text-xs"><select v-model="activityFactory" aria-label="操作日志厂区筛选" class="h-9 rounded-lg border border-slate-200 px-2 text-xs"><option value="">全部厂区</option><option v-for="item in memberships" :key="item.factory_id" :value="item.factory_id">{{ factoryDisplayName(item.factory_id) }}</option></select></div></div><div class="flex flex-wrap items-end gap-2 border-b p-3 text-xs"><label>操作类型<select v-model="activityEvent" aria-label="供应商日志操作类型" class="ml-2 h-9 rounded-lg border px-2"><option value="">全部类型</option><option v-for="(label, code) in activityTypes" :key="code" :value="code">{{ label }}</option></select></label><label>操作日期从<input v-model="activityFrom" type="date" aria-label="供应商日志起始日期" class="ml-2 h-9 rounded-lg border px-2"></label><label>至<input v-model="activityTo" type="date" aria-label="供应商日志结束日期" class="ml-2 h-9 rounded-lg border px-2"></label><select v-model="activitySort" aria-label="供应商日志排序" class="h-9 rounded-lg border px-2"><option value="DESC">最新操作优先</option><option value="ASC">最早操作优先</option></select><button type="button" class="h-9 rounded-lg border px-3" @click="activitySearch = ''; activityFactory = ''; activityEvent = ''; activityFrom = ''; activityTo = ''">清除筛选</button><button type="button" class="h-9 rounded-lg border px-3" @click="activitySort = 'DESC'">恢复默认排序</button><button type="button" class="h-9 rounded-lg border px-3" :disabled="extraLoading" @click="loadActivity">刷新</button><span>共 {{ activityTotal }} 条</span></div><div class="overflow-x-auto"><table class="w-full min-w-[700px] text-left text-xs"><thead class="bg-slate-50 text-slate-600"><tr><th class="p-3">时间</th><th class="p-3">厂区</th><th class="p-3">操作</th><th class="p-3">单据 / 订单</th><th class="p-3">操作人</th></tr></thead><tbody class="divide-y divide-slate-100"><tr v-for="row in filteredActivity" :key="row.id"><td class="p-3">{{ row.created_at }}</td><td class="p-3">{{ factoryDisplayName(row.factory_id) }}</td><td class="p-3 font-semibold">{{ row.action }}</td><td class="p-3">{{ row.reference_no }}</td><td class="p-3">{{ row.actor_name }}</td></tr><tr v-if="!filteredActivity.length"><td colspan="5" class="p-10 text-center text-slate-500">{{ extraLoading ? '正在读取操作日志…' : '暂无相关操作记录' }}</td></tr></tbody></table></div><div class="flex items-center justify-end gap-3 border-t p-3 text-xs"><button type="button" :disabled="extraLoading || activityPage <= 1" class="rounded-lg border px-3 py-2 disabled:opacity-40" @click="activityPage--">上一页</button><span>第 {{ activityPage }} / {{ Math.max(1, Math.ceil(activityTotal / 50)) }} 页</span><button type="button" :disabled="extraLoading || activityPage * 50 >= activityTotal" class="rounded-lg border px-3 py-2 disabled:opacity-40" @click="activityPage++">下一页</button></div></section>
        </template>
      </section>
    </div>
  </main>
</template>
