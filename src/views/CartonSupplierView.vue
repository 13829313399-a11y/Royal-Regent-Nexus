<script setup lang="ts">
import CartonSupplierPurchaseOrders from '@/components/CartonSupplierPurchaseOrders.vue'
import CartonOrderDetailContent from '@/components/CartonOrderDetailContent.vue'
import '@/features/carton-procurement/layout.css'
import CartonSupplierOrderRow, { type SupplierRowPresentation } from '@/components/CartonSupplierOrderRow.vue'
import CartonSupplierAcceptanceFields from '@/components/CartonSupplierAcceptanceFields.vue'
import CartonOrderDetailDialog from '@/components/CartonOrderDetailDialog.vue'
import CartonFilterBar from '@/components/CartonFilterBar.vue'
import type { DeliveryRegistrationMode } from '@/api/cartonSupplierPortal'
import CartonSpecialRequests from '@/components/CartonSpecialRequests.vue'
import CartonSupplierChangeTasks from '@/components/CartonSupplierChangeTasks.vue'
import { cartonSupplierChangesApi, type SupplierChangeTask } from '@/api/cartonSupplierChanges'
import CartonReplenishmentOrders from '@/components/CartonReplenishmentOrders.vue'
import CartonUnifiedDeliveryNotes from '@/components/CartonUnifiedDeliveryNotes.vue'
import CartonPriceReviews from '@/components/CartonPriceReviews.vue'
import { cartonUnifiedDeliveriesApi, toPortalShipment, type UnifiedDelivery } from '@/api/cartonUnifiedDeliveries'
import { cartonSpecialRequestsApi, type SpecialRequest } from '@/api/cartonSpecialRequests'
import CartonImportDifference from '@/components/CartonImportDifference.vue'
import { supplierWorkCounts, specialSupplierOrigin, specialSupplierActive, specialSupplierAccepted, specialSupplierNeedsAcceptance, specialSupplierCanPromise, specialSupplierPromise, specialSupplierStage, specialSupplierStatusLabel } from '@/features/carton-procurement/supplierWork'
import { deliveryNoteHtml } from '@/features/carton-procurement/deliveryNotePrint'
import CartonActionNotice from '@/components/CartonActionNotice.vue'
import CartonFeedbackCenter from '@/components/CartonFeedbackCenter.vue'
import CartonSupplierMonthlySummary from '@/components/CartonSupplierMonthlySummary.vue'
import CartonSupplierReturns from '@/components/CartonSupplierReturns.vue'
import CartonPayables from '@/components/CartonPayables.vue'
import CartonPriceCorrectionDialog from '@/components/CartonPriceCorrectionDialog.vue'
import CartonMarkAssetLibrary from '@/components/CartonMarkAssetLibrary.vue'
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { DialogRoot, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { ArrowLeft, BookOpen, ClipboardList, FileText, History, PackageCheck, Search, Truck, X } from '@lucide/vue'
import type { CartonSupplierGuideDestination } from '@/features/carton-procurement/supplierUsageGuide'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import { cartonSupplierPortalApi as api, type PortalOrder, type PortalPaper, type PortalShipment, type SupplierDocument, type SupplierActivity, type SupplierMarkAsset, type DeliveryImportPreview, type DeliveryImportGroup, type DeliveryImportRow, type DeliveryRowSelection } from '@/api/cartonSupplierPortal'
import { factoryContexts } from '@/data/enterpriseMock'
import { formatBusinessDate, parseBusinessTimestamp } from '@/lib/dateTime'
import { getApiErrorMessage, getApiErrorMessageAsync } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'
import { useAuthStore } from '@/stores/auth'

import CartonMaterialCorrectionDialog from '@/components/CartonMaterialCorrectionDialog.vue'
import type { MaterialCorrection } from '@/api/cartonMaterialCorrection'
import CartonShipmentFilters from '@/components/CartonShipmentFilters.vue'
import { emptyShipmentFilters, filterShipments } from '@/features/carton-procurement/queryFilters'

type SupplierOrder = PortalOrder & { factory_id: string }
type SupplierShipment = PortalShipment & { factory_id: string }
type SupplierWorkspace = { supplier_name: string; orders: SupplierOrder[]; shipments: SupplierShipment[] }
type SupplierSelection = { kind: 'REGULAR'; order: SupplierOrder } | { kind: 'SPECIAL'; order: SpecialRequest }
const selectionKey = (kind: SupplierSelection['kind'], order: { factory_id: string; id: string }) => JSON.stringify([kind, order.factory_id, order.id])
const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const orderKind = ref('ALL')
const specialRequests = ref<SpecialRequest[]>([])
const specialError = ref('')
const specialLoading = ref(false)
const specialReadFailures = ref(new Set<string>())
const specialSelection = ref<{ factoryId: string; id: string; create: boolean } | null>(null)
const specialKinds: Record<string, string> = { SAMPLE: '样板单', WORKSHOP_MISC: '车间杂单', SUPPLIER_GIFT: '供应商赠送' }
const serviceFactories = computed(() => [...new Map([...memberships.value, ...specialMemberships.value].map(row => [row.factory_id, row])).values()])
let specialGeneration = 0
async function loadSpecialRequests() {
  const token = ++specialGeneration, context = importContext.value
  specialLoading.value = true
  specialError.value = ''
  const results = await Promise.allSettled(specialMemberships.value.map(row => cartonSpecialRequestsApi.list(row.factory_id, true)))
  if (token !== specialGeneration || context !== importContext.value) return
  specialLoading.value = false
  const failedFactories = new Set(results.flatMap((result, index) => result.status === 'rejected' ? [specialMemberships.value[index]!.factory_id] : []))
  specialReadFailures.value = failedFactories
  specialRequests.value = [...results.flatMap(result => result.status === 'fulfilled' ? result.value.items : []), ...specialRequests.value.filter(row => failedFactories.has(row.factory_id))]
  syncSpecialDrafts()
  const validKeys = new Set(specialRequests.value.filter(row => failedFactories.has(row.factory_id) || canSelectSpecial(row)).map(row => selectionKey('SPECIAL', row)))
  selectedOrderIds.value = selectedOrderIds.value.filter(key => !key.startsWith('["SPECIAL",') || validKeys.has(key))
  const failures = results.flatMap((result, index) => result.status === 'rejected' ? [`${factoryDisplayName(specialMemberships.value[index]!.factory_id)}：${getApiErrorMessage(result.reason)}`] : [])
  specialError.value = failures.length ? `样板与杂单读取失败：${failures.join('；')}` : ''
}
function closeSpecial() { detailPinned.value = false; specialSelection.value = null; void router.replace({ query: { ...route.query, special_request: undefined } }) }
function openSpecial(id: string, factoryId: string, create = false) {
  detailOrderId.value = ''; detailPinned.value = true
  specialSelection.value = { id, factoryId, create }
}
watch(() => [route.query.special_request, route.query.factory], () => {
  openSpecialLink()
})
function openSpecialLink() {
  const id = route.query.special_request
  if (typeof id !== 'string') return
  const requestedFactory = typeof route.query.factory === 'string' ? route.query.factory : specialRequests.value.find(row => row.id === id)?.factory_id || specialFactory.value
  if (specialMemberships.value.some(row => row.factory_id === requestedFactory)) openSpecial(id, requestedFactory)
}
const canApprove = computed(() => auth.can('carton_supplier:approve', '*', '*'))
const canEdit = computed(() => auth.can('carton_supplier:edit', '*', '*'))
const memberships = ref<{ factory_id: string; supplier_name: string }[]>([])
const specialMemberships = ref<{ factory_id: string; supplier_name: string }[]>([])
const factoryFilter = ref('')
const selectedPriceFactory = ref('')
const priceReviewFactory = computed({
  get: () => [selectedPriceFactory.value, factoryFilter.value, serviceFactories.value[0]?.factory_id || ''].find(id => serviceFactories.value.some(item => item.factory_id === id)) || '',
  set: (value: string) => { selectedPriceFactory.value = value },
})
type PriceReviewState = { factoryId: string; loading: boolean; readError: string; error: string; pendingCount: number | null; canRead: boolean }
const priceReviewState = ref<PriceReviewState>({ factoryId: '', loading: true, readError: '', error: '', pendingCount: null, canRead: true })
watch(priceReviewFactory, factoryId => { priceReviewState.value = { factoryId, loading: true, readError: '', error: '', pendingCount: null, canRead: true } })
function updatePriceReviewState(state: PriceReviewState) { if (state.factoryId === priceReviewFactory.value) priceReviewState.value = state }
const priceReviewLabel = computed(() => {
  const state = priceReviewState.value, factory = priceReviewFactory.value
  if (!factory) return discovering.value ? '厂区读取中…' : membershipReadError.value ? '厂区暂不可用' : '暂无核价厂区'
  const name = factoryDisplayName(factory)
  if (state.factoryId !== factory || state.loading) return `${name} · 读取中…`
  if (!state.canRead) return `${name} · 无查看权限`
  if (state.readError) return `${name} · 读取失败`
  if (state.error) return `${name} · 处理待核对`
  return `${name} · 缺价/异议 ${state.pendingCount ?? '待核实'} 项`
})
watch(factoryFilter, () => { selectedPriceFactory.value = '' })
const specialFactory = computed(() => specialMemberships.value.some(row => row.factory_id === factoryFilter.value) ? factoryFilter.value : specialMemberships.value.some(row => row.factory_id === route.query.factory) ? String(route.query.factory) : specialMemberships.value[0]?.factory_id || '')
watch(factoryFilter, factory => { if (factory && specialSelection.value?.factoryId !== factory) specialSelection.value = null })
const workspace = ref<SupplierWorkspace | null>(null)
const workspaceReadError = ref('')
const membershipReadError = ref('')
const monthlySearch = ref('')
const returnSearch = ref('')
const payablesSearch = ref('')
const unifiedDeliveries = ref<UnifiedDelivery[]>([])
const deliveryError = ref('')
let deliveryGeneration = 0
async function loadUnifiedDeliveries() {
  const token = ++deliveryGeneration, context = importContext.value
  const scopes = serviceFactories.value.map(item => item.factory_id)
  const results = await Promise.allSettled(scopes.map(scope => cartonUnifiedDeliveriesApi.list(scope, true)))
  if (token !== deliveryGeneration || context !== importContext.value) return
  unifiedDeliveries.value = results.flatMap(result => result.status === 'fulfilled' ? result.value.items : [])
  deliveryError.value = results.flatMap((result, index) => result.status === 'rejected' ? [`${factoryDisplayName(scopes[index]!)}：${getApiErrorMessage(result.reason)}`] : []).join('；')
}
const unifiedShipmentRows = computed(() => unifiedDeliveries.value.map(group => ({ ...toPortalShipment(group), factory_id: group.factory_id, group })))
const matchingUnifiedShipments = computed(() => filterShipments(unifiedShipmentRows.value.filter(row => !factoryFilter.value || row.factory_id === factoryFilter.value), shipmentFilters.value))
type OrderMarkCount = { current: number; history: number }
type FactoryMarkState = { loading: boolean; error: string; counts: Record<string, OrderMarkCount> }
const orderMarks = ref<Record<string, FactoryMarkState>>({})
let orderMarksController = new AbortController()
const markOrderKey = (id: string, issueId: string) => JSON.stringify([id, issueId])
function clearOrderMarks() {
  orderMarksController.abort()
  orderMarksController = new AbortController()
  orderMarks.value = {}
}
function updateOrderMarks(factoryId: string, assets: SupplierMarkAsset[]) {
  if (!memberships.value.some(member => member.factory_id === factoryId)) return
  const counts: Record<string, OrderMarkCount> = {}
  for (const asset of assets) {
    const keys = new Set(asset.orders.map(order => markOrderKey(order.id, order.issue_id)))
    for (const key of keys) {
      const count = counts[key] ??= { current: 0, history: 0 }
      count[asset.workflow?.status === 'HISTORY' ? 'history' : 'current']++
    }
  }
  orderMarks.value[factoryId] = { loading: false, error: '', counts }
}
async function loadOrderMarks(scopes: string[], token: number) {
  clearOrderMarks()
  const signal = orderMarksController.signal
  orderMarks.value = Object.fromEntries(scopes.map(scope => [scope, { loading: true, error: '', counts: {} }]))
  await Promise.all(scopes.map(async scope => {
    try {
      const assets = await api.markAssets(scope, signal)
      if (token === generation && !signal.aborted) updateOrderMarks(scope, assets)
    } catch (reason) {
      if (token === generation && !signal.aborted) orderMarks.value[scope] = { loading: false, error: getApiErrorMessage(reason), counts: {} }
    }
  }))
}
function orderMarkLabel(order: SupplierOrder) {
  const state = orderMarks.value[order.factory_id]
  if (!state || state.loading) return '查询中…'
  if (state.error) return '资料查询失败'
  const count = state.counts[markOrderKey(order.id, order.issue_id)]
  return count?.current ? `已绑定 ${count.current} 份` : count?.history ? `仅历史资料 ${count.history} 份` : '未绑定'
}
function orderHasMarks(order: SupplierOrder) {
  const state = orderMarks.value[order.factory_id]
  return !state?.loading && !state?.error && Boolean(state?.counts[markOrderKey(order.id, order.issue_id)]?.current)
}
const workCounts = computed(() => {
  const regular = supplierWorkCounts(orders.value.filter(row => !factoryFilter.value || row.factory_id === factoryFilter.value), (workspace.value?.shipments || []).filter(row => !factoryFilter.value || row.factory_id === factoryFilter.value), specialRequests.value.filter(row => !factoryFilter.value || row.factory_id === factoryFilter.value))
  return { ...regular,
    receipt: unifiedDeliveries.value.filter(row => (!factoryFilter.value || row.factory_id === factoryFilter.value) && ['SENT', 'RECEIPT_REVERSED'].includes(row.status)).length,
  }
})
function openPendingReceipts() {
  if (specialRequests.value.some(row => (!factoryFilter.value || row.factory_id === factoryFilter.value) && specialStage(row) === 'RECEIPT_PENDING')) {
    activeTab.value = 'orders'; orderKind.value = 'ALL'; statusFilter.value = 'RECEIPT_PENDING'; customerFilter.value = ''; search.value = ''; selectedOnly.value = false; orderDateFrom.value = ''; orderDateTo.value = ''
  } else { activeTab.value = 'shipments'; shipmentFilters.value = { ...emptyShipmentFilters(), status: 'PENDING_RECEIPT' } }
}
const materialCorrection = ref<MaterialCorrection | null>(null)
const materialCorrections = computed(() => [...new Map((workspace.value?.orders.flatMap(order => order.material_corrections || []) || []).map(row => [row.id, row])).values()])
const pendingMaterialCorrections = computed(() => materialCorrections.value.filter(row => ['PENDING', 'RETURNED'].includes(row.status)))
const completedMaterialCorrections = computed(() => materialCorrections.value.filter(row => !['PENDING', 'RETURNED'].includes(row.status)))
const materialHistory = ref(false)
const visibleMaterialCorrections = computed(() => materialHistory.value ? completedMaterialCorrections.value : pendingMaterialCorrections.value)
const materialReadLoading = computed(() => discovering.value || loading.value || memberships.value.length > 0 && !workspace.value && !workspaceReadError.value)
const materialPendingLabel = computed(() => materialReadLoading.value ? '读取中…' : workspaceReadError.value ? '暂不可用' : `${pendingMaterialCorrections.value.length} 项待处理`)
const materialStatus = { PENDING: '待确认', RETURNED: '已退回仓库核实', APPROVED: '双方已确认', WITHDRAWN: '已撤回' }
const collaborationCategory = ref<'ORDERS' | 'MATERIAL' | 'REPLENISHMENT' | 'PRICES'>('ORDERS')
const collaborationExpanded = ref(false)
function toggleCollaboration(category: typeof collaborationCategory.value) {
  collaborationExpanded.value = category !== collaborationCategory.value || !collaborationExpanded.value
  collaborationCategory.value = category
}
const changeSourceKinds = computed<SupplierChangeTask['source_kind'][]>(() => collaborationCategory.value === 'REPLENISHMENT' ? ['REPLENISHMENT'] : ['REGULAR', 'SPECIAL'])
const changePendingState = ref({ loading: true, error: '', counts: { REGULAR: 0, SPECIAL: 0, REPLENISHMENT: 0 } })
function changePendingLabel(category: 'ORDERS' | 'REPLENISHMENT') {
  const state = changePendingState.value
  return discovering.value || state.loading ? '读取中…' : membershipReadError.value || state.error ? '暂不可用' : `${category === 'ORDERS' ? state.counts.REGULAR + state.counts.SPECIAL : state.counts.REPLENISHMENT} 项待确认`
}
const purchaseSelection = ref<{ factoryId: string; orderNo: string } | null>(null)
const activeTab = ref<'orders' | 'shipments' | 'documents' | 'activity' | 'settlements'>('orders')
const settlementView = ref(route.query.settlement_view === 'returns' ? 'RETURNS' : route.query.settlement_view === 'payables' ? 'PAYABLES' : 'MONTHLY')
const priceCorrectionOpen = ref(false), priceCorrectionLineId = ref(''), priceCorrectionFactory = ref('')
function openPriceCorrection(factory = '', line = '') {
  priceCorrectionFactory.value = factory; priceCorrectionLineId.value = line; priceCorrectionOpen.value = true
}
watch(() => route.query.price_correction, value => { if (typeof value === 'string' && value) openPriceCorrection(typeof route.query.factory === 'string' ? route.query.factory : '', value === 'workspace' ? '' : value) }, { immediate: true })
watch(() => route.query.settlement_view, value => { settlementView.value = value === 'returns' ? 'RETURNS' : value === 'payables' ? 'PAYABLES' : 'MONTHLY'; if (value === 'returns' || value === 'payables') activeTab.value = 'settlements' }, { immediate: true })
function selectSettlementView(value: 'RETURNS' | 'PAYABLES' | 'MONTHLY') {
  settlementView.value = value; activeTab.value = 'settlements'
  void router.replace({ query: { ...route.query, settlement_view: value === 'MONTHLY' ? undefined : value.toLowerCase() } })
}
watch(() => route.query.special_request, id => { if (typeof id === 'string') activeTab.value = 'orders' })
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
const documentBusinessKind = ref('')
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
const activityTypes: Record<string, string> = { ORDER_CANCELLED: '内部取消订单', ORDER_REDUCED: '内部减单', ORDER_RETURNED: '内部退单', ORDER_DATES_CHANGED: '内部变更交期', ORDER_RUSH_MARKED: '内部标记急单', ORDER_RUSH_CLEARED: '内部取消急单', SUPPLIER_CANCELLATION_ACKNOWLEDGED: '收到取消通知', SUPPLIER_RUSH_ACKNOWLEDGED: '确认收到急单', SUPPLIER_SHIPMENT_DEFERRED: '暂未到货继续待收', SUPPLIER_SHIPMENT_NON_ARRIVAL_REOPENED: '未到货反馈更正', PURCHASE_ORDER_ISSUED: '采购单生成', SUPPLIER_PAPER_ACCEPTED: '纸品确认接单', SUPPLIER_SHIPMENT_CREATED: '确认发货', SUPPLIER_SHIPMENT_RECEIVED: '仓库核实送货', SUPPLIER_SHIPMENT_NOT_RECEIVED: '仓库未收到', SUPPLIER_SHIPMENT_RECEIPT_REVERSED: '原收料冲销待更正', SUPPLIER_SHIPMENT_LINE_LINKED: '无单纸品关联订单' }
const bulkAcceptOpen = ref(false)
const bulkPromiseOpen = ref(false)
const bulkPromiseUniform = ref('')
const bulkPromiseDates = reactive<Record<string, string>>({})
const search = ref('')
const customerFilter = ref('')
const statusFilter = ref('ALL')
const orderSort = ref('DEFAULT')
const orderDateField = ref('ORDER')
const shipmentFilters = ref(emptyShipmentFilters())
const orderDateFrom = ref('')
const orderDateTo = ref('')
const headerSearch = computed({
  get: () => activeTab.value === 'settlements' ? settlementView.value === 'RETURNS' ? returnSearch.value : settlementView.value === 'PAYABLES' ? payablesSearch.value : monthlySearch.value : activeTab.value === 'shipments' ? shipmentFilters.value.search
    : activeTab.value === 'documents' ? documentSearch.value
      : activeTab.value === 'activity' ? activitySearch.value : search.value,
  set(value: string) {
    if (activeTab.value === 'settlements') { if (settlementView.value === 'RETURNS') returnSearch.value = value; else if (settlementView.value === 'PAYABLES') payablesSearch.value = value; else monthlySearch.value = value }
    else if (activeTab.value === 'shipments') shipmentFilters.value = { ...shipmentFilters.value, search: value }
    else if (activeTab.value === 'documents') documentSearch.value = value
    else if (activeTab.value === 'activity') activitySearch.value = value
    else search.value = value
  },
})
const headerSearchPlaceholder = computed(() => activeTab.value === 'settlements' ? settlementView.value === 'RETURNS' ? '搜索退货客户 / 合同 / 货号 / 退货单' : settlementView.value === 'PAYABLES' ? '搜索往来凭证 / 摘要 / 依据' : '搜索月结客户 / 合同 / 货号 / 送货单 / 依据' : activeTab.value === 'shipments' ? '搜索客户 / 送货单 / 合同 / 货号'
  : activeTab.value === 'documents' ? '搜索单据号 / 订单 / 客户 / 合同 / PO / 货号'
    : activeTab.value === 'activity' ? '搜索操作 / 单据 / 人员' : '搜索客户 / 合同 / PO / 货号 / 订单 / 单据')
const selectedOnly = ref(false)
const selectedOrderIds = ref<string[]>([])
const detailOrderId = ref('')
const detailPinned = ref(false)
const acceptOrderId = ref('')
const acceptSpecialKey = ref('')
const specialDates = reactive<Record<string, { version: string; revision: number; date: string; dirty: boolean }>>({})
type SpecialAcceptBody = { factory_id: string; source_kind: 'SPECIAL'; source_id: string; expected_revision: number; action: 'ACCEPT'; promised_date: string; request_id: string }
const specialRetries = reactive(new Map<string, SpecialAcceptBody>())
const unresolvedSpecialRequests = reactive(new Map<string, SpecialAcceptBody>())
const completedAcceptances = new Set<string>()
let bulkVersions = new Map<string, string>()
const changeTasks = ref<InstanceType<typeof CartonSupplierChangeTasks> | null>(null)
let specialAcceptTrigger: HTMLElement | null = null
const importOpen = ref(false)
const importFile = ref<File | null>(null)
const importPreview = ref<DeliveryImportPreview | null>(null)
const selectedImportNotes = ref<string[]>([])
const importModes = ref<Record<string, DeliveryRegistrationMode>>({})
const importChoices = ref<Record<string, string>>({})
const reviewedImportChoices = ref<DeliveryRowSelection[]>([])
const importChoicesDirty = ref(false)
const importRowKey = (row: DeliveryImportRow) => `${row.source_sheet}:${row.source_row}`
function importChoiceSelections(): DeliveryRowSelection[] {
  return (importPreview.value?.groups ?? []).flatMap(group => group.rows.flatMap(row => {
    const candidate = row.candidates?.find(item => `${item.order_line_id}|${item.issue_id}` === importChoices.value[importRowKey(row)] || item.order_line_id === importChoices.value[importRowKey(row)])
    return candidate ? [{ source_sheet: row.source_sheet, source_row: row.source_row, order_line_id: candidate.order_line_id, issue_id: candidate.issue_id, order_revision: candidate.order_revision }] : []
  }))
}
async function recheckImportChoices() {
  if (busy.value || !importFile.value || !canEdit.value) return
  const token = importGeneration, context = importContext.value
  const selections = importChoiceSelections()
  busy.value = true; error.value = ''
  try {
    const preview = await api.previewDeliveryImport(importFile.value, selections)
    if (token !== importGeneration || context !== importContext.value) return
    importPreview.value = preview; reviewedImportChoices.value = selections; importChoicesDirty.value = false
    selectedImportNotes.value = preview.groups.filter(importGroupReady).map(importNoteKey)
  } catch (reason) { if (token === importGeneration && context === importContext.value) failure(reason) }
  finally { if (token === importGeneration && context === importContext.value) busy.value = false }
}
let importGeneration = 0
// sessionVersion advances on every /auth/me refresh, including window focus.
// Use stable access facts for both draft resets and in-flight response checks.
const importContext = computed(() => JSON.stringify([
  auth.currentUser?.id, auth.authorizationVersion, auth.authzMode,
  auth.currentUser?.identity?.effective_context_key, auth.currentUser?.identity?.employment_epoch,
  canEdit.value, canApprove.value, auth.can('carton_supplier:read', '*', '*'),
]))
watch(importContext, () => {
  collaborationCategory.value = 'ORDERS'; collaborationExpanded.value = false; materialHistory.value = false; workspaceReadError.value = ''; membershipReadError.value = ''
  acceptSpecialKey.value = ''; specialRetries.clear(); unresolvedSpecialRequests.clear(); completedAcceptances.clear(); bulkVersions.clear()
  for (const key of Object.keys(specialDates)) delete specialDates[key]
  changePendingState.value = { loading: true, error: '', counts: { REGULAR: 0, SPECIAL: 0, REPLENISHMENT: 0 } }
  priceCorrectionOpen.value = false; priceCorrectionLineId.value = ''; priceCorrectionFactory.value = ''
  selectedPriceFactory.value = ''
  priceReviewState.value = { factoryId: '', loading: true, readError: '', error: '', pendingCount: null, canRead: true }
  deliveryGeneration++; unifiedDeliveries.value = []; deliveryError.value = ''; monthlySearch.value = ''; returnSearch.value = ''; payablesSearch.value = ''
  specialGeneration++; specialRequests.value = []; specialReadFailures.value = new Set(); specialSelection.value = null; specialError.value = ''; specialLoading.value = false; orderKind.value = 'ALL'
  specialMemberships.value = []
  importGeneration++; ++generation; importOpen.value = false; importFile.value = null; importPreview.value = null
  clearOrderMarks()
  materialCorrection.value = null; workspace.value = null; memberships.value = []; purchaseSelection.value = null; documents.value = []; activity.value = []; acceptOrderId.value = ''; selectedOrderIds.value = []; selectedDocumentKeys.value = []
  ++extraGeneration.documents; ++extraGeneration.activity; extraLoaded.documents = extraLoaded.activity = false; extraLoadingState.documents = extraLoadingState.activity = false
  closeDocumentDetail(); closeMergedDocuments(); bulkAcceptOpen.value = false; loading.value = false; discovering.value = false
  dirtyDates.clear(); for (const key of Object.keys(dates)) delete dates[key]; for (const key of Object.keys(dateIssueIds)) delete dateIssueIds[key]
  selectedImportNotes.value = []; importModes.value = {}; importChoices.value = {}; reviewedImportChoices.value = []; importChoicesDirty.value = false; busy.value = false
  search.value = ''; documentSearch.value = ''; activitySearch.value = ''
  shipmentFilters.value = { ...shipmentFilters.value, search: '' }
  activityTotal.value = 0
  if (activityTimer) clearTimeout(activityTimer)
})
onBeforeUnmount(() => { importGeneration++; generation++; specialGeneration++; deliveryGeneration++; clearOrderMarks() })
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
const customers = computed(() => [...new Set([...orders.value.map(order => order.customer_name), ...specialRequests.value.map(order => order.customer_name)].filter(Boolean))].sort((a, b) => a.localeCompare(b)))
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
  if (statusFilter.value !== 'ALL' && (statusFilter.value === 'PARTIALLY_RECEIVED' ? order.status !== statusFilter.value : orderStage(order) !== statusFilter.value)) return false
  if (orderDateFrom.value && (!orderQueryDate(order) || orderQueryDate(order) < orderDateFrom.value)) return false
  if (orderDateTo.value && (!orderQueryDate(order) || orderQueryDate(order) > orderDateTo.value)) return false
  if (!query.value) return true
  return [order.customer_name, order.contract_no, order.customer_po, order.item_no,
    order.order_no, order.document_no, order.product_name, ...order.lines.map(line => line.child_no)]
    .some(value => value.toLocaleLowerCase().includes(query.value))
}))
const visibleOrders = computed(() => (selectedOnly.value
  ? orders.value.filter(order => selectedOrderIds.value.includes(selectionKey('REGULAR', order)))
  : filteredOrders.value).filter(() => selectedOnly.value || ['ALL', 'PURCHASE'].includes(orderKind.value)).slice().sort(compareOrders))
const hiddenSelectedCount = computed(() => selectedOrderIds.value.filter(key => ![
  ...filteredOrders.value.filter(() => ['ALL', 'PURCHASE'].includes(orderKind.value)).map(row => selectionKey('REGULAR', row)),
  ...filteredSpecialOrders.value.map(row => selectionKey('SPECIAL', row)),
].includes(key)).length)
const specialStage = specialSupplierStage
const specialStatus = specialSupplierStatusLabel
function specialDate(row: SpecialRequest) { return orderDateField.value === 'ORDER' ? row.created_at ? formatBusinessDate(row.created_at) : '' : orderDateField.value === 'PROMISED' ? specialSupplierPromise(row) : row.required_date }
const filteredSpecialOrders = computed(() => specialRequests.value.filter(row => (orderKind.value === 'ALL' || orderKind.value === row.kind)
  && (!factoryFilter.value || row.factory_id === factoryFilter.value)
  && (!customerFilter.value || row.customer_name === customerFilter.value)
  && (statusFilter.value === 'ALL' || (statusFilter.value === 'PARTIALLY_RECEIVED' ? row.status === statusFilter.value : ['SENT', 'QUOTED', 'READY'].includes(statusFilter.value) ? ['SAMPLE', 'WORKSHOP_MISC'].includes(row.kind) && row.status === statusFilter.value : specialStage(row) === statusFilter.value))
  && (!orderDateFrom.value || specialDate(row) >= orderDateFrom.value)
  && (!orderDateTo.value || Boolean(specialDate(row)) && specialDate(row) <= orderDateTo.value)
  && (!query.value || [row.request_no, row.title, row.requester_name, row.customer_name, row.purpose, ...row.lines.flatMap(line => [line.packaging_type, line.paper_quality, line.specification, line.item_no])].join(' ').toLocaleLowerCase().includes(query.value))))
const visibleSpecialOrders = computed(() => selectedOnly.value ? specialRequests.value.filter(row => selectedOrderIds.value.includes(selectionKey('SPECIAL', row))) : filteredSpecialOrders.value)
const visibleOrderRows = computed(() => {
  const rows: { key: string; date: string; stage: string; regular?: SupplierOrder; special?: SpecialRequest }[] = [
    ...visibleOrders.value.map(regular => ({ key: selectionKey('REGULAR', regular), date: orderSort.value === 'ORDER_DESC' ? regular.order_date : orderSort.value === 'PROMISED_ASC' ? regular.lines.map(line => line.promised_date).filter(Boolean).sort()[0] || '' : regular.planned_date, stage: orderStage(regular), regular })),
    ...visibleSpecialOrders.value.map(special => ({ key: selectionKey('SPECIAL', special), date: orderSort.value === 'ORDER_DESC' ? special.created_at ? formatBusinessDate(special.created_at) : '' : orderSort.value === 'PROMISED_ASC' ? specialSupplierPromise(special) : special.required_date, stage: specialStage(special), special })),
  ]
  return rows.sort((a, b) => Number(!a.regular?.rush) - Number(!b.regular?.rush) || (orderSort.value === 'DEFAULT' ? (stagePriority[a.stage] ?? 9) - (stagePriority[b.stage] ?? 9) : 0) || Number(!a.date) - Number(!b.date) || (orderSort.value === 'ORDER_DESC' ? b.date.localeCompare(a.date) : a.date.localeCompare(b.date)) || a.key.localeCompare(b.key))
})
const detailSpecial = computed(() => specialRequests.value.find(row => row.id === specialSelection.value?.id && row.factory_id === specialSelection.value?.factoryId) || null)
const detailOrder = computed(() => orders.value.find(order => order.id === detailOrderId.value) ?? null)
watch([factoryFilter, customerFilter, statusFilter, orderKind, search, orderDateFrom, orderDateTo, orderDateField, selectedOnly], () => { if (!detailPinned.value) closeOrderDetail() })
const acceptOrder = computed(() => orders.value.find(order => order.id === acceptOrderId.value) ?? null)
const acceptSpecial = computed(() => specialRequests.value.find(row => selectionKey('SPECIAL', row) === acceptSpecialKey.value) || null)
const selectedOrders = computed(() => orders.value.filter(order => selectedOrderIds.value.includes(selectionKey('REGULAR', order))))
const selectedSpecialOrders = computed(() => specialRequests.value.filter(order => selectedOrderIds.value.includes(selectionKey('SPECIAL', order))))
const selectedSources = computed<SupplierSelection[]>(() => [...selectedOrders.value.map(order => ({ kind: 'REGULAR' as const, order })), ...selectedSpecialOrders.value.map(order => ({ kind: 'SPECIAL' as const, order }))])
const selectableVisibleOrders = computed(() => [...visibleOrders.value.filter(canSelectOrder).map(row => selectionKey('REGULAR', row)), ...visibleSpecialOrders.value.filter(canSelectSpecial).map(row => selectionKey('SPECIAL', row))])
const allVisibleSelected = computed(() => selectableVisibleOrders.value.length > 0 && selectableVisibleOrders.value.every(key => selectedOrderIds.value.includes(key)))
const someVisibleSelected = computed(() => selectableVisibleOrders.value.some(key => selectedOrderIds.value.includes(key)))
function importNoteKey(group: Pick<DeliveryImportGroup, 'factory_id' | 'delivery_note_no'>) {
  return JSON.stringify([group.factory_id, group.delivery_note_no])
}
const matchingShipments = computed(() => filterShipments((workspace.value?.shipments ?? []).filter(row => !factoryFilter.value || row.factory_id === factoryFilter.value), shipmentFilters.value))
function openDeliveryImport() {
  importGeneration++
  error.value = ''
  importFile.value = null
  importPreview.value = null
  selectedImportNotes.value = []; importModes.value = {}; importChoices.value = {}; reviewedImportChoices.value = []; importChoicesDirty.value = false
  importOpen.value = true
}
function closeDeliveryImport() {
  if (busy.value) return
  importGeneration++
  importOpen.value = false
  importFile.value = null
  importPreview.value = null
  selectedImportNotes.value = []; importModes.value = {}; importChoices.value = {}; reviewedImportChoices.value = []; importChoicesDirty.value = false
}
function documentKey(row: Pick<SupplierDocument, 'factory_id' | 'kind' | 'id'>) {
  return [row.factory_id, row.kind, row.id].join('|')
}
function documentBusinessKinds(row: SupplierDocument) {
  const kinds = [...row.orders, ...row.lines].map(item => item.order_kind || (row.kind === 'PURCHASE' ? 'REGULAR' : 'UNKNOWN'))
  return [...new Set(kinds.length ? kinds : [row.kind === 'PURCHASE' ? 'REGULAR' : 'UNKNOWN'])]
}
function documentBusinessLabel(row: SupplierDocument) {
  return documentBusinessKinds(row).map(kind => ({ REGULAR: '正单', SAMPLE: '样板', MISC: '杂单', UNKNOWN: '待分类' }[kind] || '待分类')).join(' / ')
}
const filteredDocuments = computed(() => documents.value.filter(row => {
  if (documentFactory.value && row.factory_id !== documentFactory.value) return false
  if (documentKind.value && row.kind !== documentKind.value) return false
  if (documentBusinessKind.value && !documentBusinessKinds(row).includes(documentBusinessKind.value)) return false
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
  if (!memberships.value.length || !auth.can('carton_supplier:read', '*', '*')) return
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
  if (activeTab.value === 'activity' && memberships.value.length && auth.can('carton_supplier:read', '*', '*')) activityTimer = setTimeout(() => void loadActivity(), 200)
})
watch(activityPage, () => { if (activeTab.value === 'activity') void loadActivity() })
onBeforeUnmount(() => { if (activityTimer) clearTimeout(activityTimer) })

function open(order: PortalOrder) {
  return ['PENDING_SUPPLIER', 'PARTIALLY_RECEIVED'].includes(order.status) && !order.awaiting_issue
}
function canSelectOrder(order: PortalOrder) {
  return (canApprove.value || canEdit.value) && order.status !== 'COMPLETED' && order.status !== 'CANCELLED'
}
function canSelectSpecial(order: SpecialRequest) {
  return !specialReadFailures.value.has(order.factory_id) && (specialApprovalAllowed(order) || canEdit.value && auth.can('carton_supplier:edit', order.factory_id, '*')) && specialSupplierActive(order)
}
function specialApprovalAllowed(order: SpecialRequest) { return !specialReadFailures.value.has(order.factory_id) && canApprove.value && auth.can('carton_supplier:approve', order.factory_id, '*') }
function specialVersion(row: SpecialRequest) { return JSON.stringify([row.current_version_id, row.revision]) }
function syncSpecialDrafts() {
  for (const row of specialRequests.value) {
    const key = selectionKey('SPECIAL', row), previous = specialDates[key]
    if (previous && (previous.version !== row.current_version_id || previous.revision !== row.revision)) {
      if (acceptSpecialKey.value === key) {
        closeSpecialAccept()
        error.value = specialRetries.has(key) ? '订单版本已变化；上次接单结果仍未确认，已保留原提交，请先核对版本回执。' : '订单版本已变化，已关闭旧接单窗口；请核对当前版本后重新操作。'
      }
    }
    if (!previous || previous.version !== row.current_version_id || previous.revision !== row.revision || !previous.dirty && !specialRetries.has(key)) {
      const retry = specialRetries.get(key)
      specialDates[key] = { version: row.current_version_id, revision: row.revision, date: retry?.source_id === row.current_version_id ? retry.promised_date : specialSupplierPromise(row) || row.required_date, dirty: false }
    }
  }
}
function closeSpecialAccept() {
  acceptSpecialKey.value = ''
  void nextTick(() => specialAcceptTrigger?.isConnected && specialAcceptTrigger.focus())
}
function showSpecialAccept(row: SpecialRequest, event: Event) {
  if (!specialApprovalAllowed(row) || !specialSupplierCanPromise(row)) return
  specialAcceptTrigger = event.currentTarget as HTMLElement
  closeOrderDetail(); closeDeliveryImport(); acceptOrderId.value = ''; error.value = ''; message.value = ''
  acceptSpecialKey.value = selectionKey('SPECIAL', row)
}
async function submitSpecialAcceptance(row: SpecialRequest, context: string) {
  const key = selectionKey('SPECIAL', row), draft = specialDates[key]
  if (context !== importContext.value || !specialApprovalAllowed(row) || !specialSupplierCanPromise(row) || !draft?.date
    || draft.version !== row.current_version_id || draft.revision !== row.revision) throw new Error('采购版本或权限已变化，请刷新后重新核对承诺交期。')
  let body = specialRetries.get(key)
  if (body && body.source_id !== row.current_version_id) throw new Error('旧提交结果尚未确认，采购版本已替换，请先核对历史回执，再明确选择处理当前版本。')
  if (!body) {
    body = { factory_id: row.factory_id, source_kind: 'SPECIAL', source_id: row.current_version_id, expected_revision: row.revision, action: 'ACCEPT', promised_date: draft.date, request_id: createRandomUuid() }
    specialRetries.set(key, body)
  }
  let result: SupplierChangeTask
  try { result = await cartonSupplierChangesApi.respond(body) }
  catch (reason) {
    const status = (reason as { response?: { status?: number } })?.response?.status
    if (context === importContext.value && status === 409 && body.source_id === row.current_version_id
      && body.expected_revision !== row.revision && getApiErrorMessage(reason).includes('订单修订已变化')) {
      specialRetries.delete(key)
      throw new Error('原提交未记录成功回执，订单修订已变化；请核对当前资料后重新确认。')
    }
    throw reason
  }
  if (context !== importContext.value) return
  specialRetries.delete(key)
  draft.dirty = false
  const current = specialRequests.value.find(item => selectionKey('SPECIAL', item) === key)
  if (current?.current_version_id === body.source_id && current.revision === body.expected_revision) {
    current.promised_date = body.promised_date
    current.supplier_confirmation = { status: 'ACCEPTED', version_id: body.source_id, promised_date: body.promised_date, reason: '', responded_at: result.responded_at || '', responded_by: result.responded_by || '' }
  }
}
function useCurrentSpecialVersion(row: SpecialRequest) {
  const key = selectionKey('SPECIAL', row), previous = specialRetries.get(key)
  if (!previous || previous.source_id === row.current_version_id) return
  unresolvedSpecialRequests.set(key, previous)
  specialRetries.delete(key)
  error.value = '旧版本提交结果仍待核实；以下只处理当前采购版本，旧版本不视为已同意。'
}
async function saveSpecialAcceptance(row: SpecialRequest) {
  if (busy.value || !canApprove.value) return
  const context = importContext.value, accepted = specialSupplierAccepted(row)
  if (!specialDates[selectionKey('SPECIAL', row)]?.date) { error.value = '请填写承诺交期。'; return }
  busy.value = true; error.value = ''; message.value = ''
  try {
    await submitSpecialAcceptance(row, context)
    if (context !== importContext.value) return
    message.value = `${row.request_no} ${accepted ? '承诺交期已更新' : '已确认本版本全部纸品并接单'}`
    closeSpecialAccept(); extraLoaded.activity = false
    await loadSpecialRequests(); void changeTasks.value?.refresh()
    if (context === importContext.value && specialError.value) error.value = `${message.value}，但列表刷新失败：${specialError.value}。请刷新核对，勿重复接单。`
  } catch (reason) { if (context === importContext.value) failure(reason) }
  finally { if (context === importContext.value) busy.value = false }
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
    CANCELLED: '已取消', COMPLETED: '已完成', PENDING_ISSUE: '变更待生成',
    RECEIPT_PENDING: '待仓库验收', PENDING_ACCEPTANCE: '待接单', WAITING_SHIPMENT: '待送货', ACCEPTED: '已确认接单',
  }
  return labels[orderStage(order)]
}
function dueReminder(order: Pick<PortalOrder, 'status' | 'planned_date'>) {
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
function dueReminderClass(order: Pick<PortalOrder, 'status' | 'planned_date'>) {
  const level = dueReminder(order).level
  if (level === 'OVERDUE' || level === 'TODAY') return 'text-red-600'
  if (level === 'DUE_SOON') return 'text-amber-700'
  return 'text-slate-500'
}
function statusClass(order: PortalOrder) {
  return stageClass(orderStage(order))
}
function stageClass(stage: string) {
  if (stage === 'PENDING_ISSUE' || stage === 'RECEIPT_PENDING') return 'bg-amber-50 text-amber-700 ring-amber-200'
  if (stage === 'COMPLETED' || stage === 'ACCEPTED' || stage === 'WAITING_SHIPMENT') return 'bg-emerald-50 text-emerald-700 ring-emerald-200'
  if (stage === 'CANCELLED') return 'bg-slate-100 text-slate-500 ring-slate-200'
  return 'bg-sky-50 text-sky-700 ring-sky-200'
}
function shipmentStatus(shipment: PortalShipment) {
  return shipment.requires_receipt_link ? '后补凭证待关联' : shipment.linked_existing_receipt && !shipment.requires_correction ? '已关联原入库' : shipment.status === 'RECEIPT_REVERSED' ? '收料已冲销，待更正' : shipment.status === 'SENT' ? shipment.partially_received ? '部分已收，余货待收' : '待仓库验收' : shipment.status === 'NOT_RECEIVED' ? '仓库未收到' : '仓库已核实'
}
function clearFilters() {
  orderKind.value = 'ALL'
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
  for (const key of selectableVisibleOrders.value) checked ? ids.add(key) : ids.delete(key)
  selectedOrderIds.value = [...ids]
}
type OrderEntry = { regular?: SupplierOrder; special?: SpecialRequest }
function toggleOrderSelection(key: string, checked: boolean) { selectedOrderIds.value = checked ? [...new Set([...selectedOrderIds.value, key])] : selectedOrderIds.value.filter(value => value !== key) }
function specialTransit(line: SpecialRequest['lines'][number]) { return line.remaining_to_ship == null ? undefined : Math.max(0, Number(line.quantity) - Number(line.received_quantity || 0) - Number(line.remaining_to_ship)) }
function supplierRow(entry: OrderEntry): SupplierRowPresentation {
  if (entry.special) {
    const row = entry.special, active = row.lines.filter(line => Number(line.quantity) > 0)
    const marks = new Set((row.mark_assets || []).map(file => file.id)); for (const line of row.lines) if (line.mark_attachment_id) marks.add(line.mark_attachment_id)
    const due = { status: row.status, planned_date: row.required_date }
    const difference = specialSupplierPromise(row) ? promiseDifference(row.required_date, specialSupplierPromise(row)) : ''
    return { orderNo: row.request_no, factory: factoryDisplayName(row.factory_id), kind: specialKinds[row.kind] || row.kind, customer: row.customer_name || '未关联客户', identity: row.request_no, context: '需求人 ' + row.requester_name, items: [...new Set(row.lines.map(line => line.item_no).filter(Boolean))].join(' · ') || '未填写货号', product: row.purpose || '', marks: marks.size ? '已绑定 ' + marks.size + ' 份' : '未绑定', marksTone: marks.size ? 'bg-teal-50 text-teal-800 hover:bg-teal-100' : 'bg-slate-100 text-slate-600', orderDate: row.created_at ? formatBusinessDate(row.created_at) : '历史未记录', plannedDate: row.required_date || '待确认', due: dueReminder(due).label, dueTone: dueReminderClass(due), differences: difference ? [difference] : [], progress: active.length + ' 条有效 · ' + (specialSupplierOrigin(row) ? '供应商原送货来源' : (specialSupplierAccepted(row) ? active.length : 0) + ' 条已接'), lines: active.map((line, index) => ({ id: line.id || String(index), label: line.packaging_type, required: Number(line.quantity), received: Number(line.received_quantity || 0), inTransit: specialTransit(line), unit: line.unit })), status: specialStatus(row), statusTone: stageClass(specialStage(row)), notice: row.supplier_confirmation?.status === 'DISPUTED' ? row.supplier_confirmation.reason : '', noticeTone: 'text-red-700' }
  }
  const row = entry.regular!
  return { orderNo: row.order_no, factory: factoryDisplayName(row.factory_id), kind: '正单', customer: row.customer_name, identity: row.contract_no, context: '客户 PO ' + (row.customer_po || '纸箱订单未填写'), items: row.item_no, product: row.product_name, marks: orderMarkLabel(row), marksHelp: orderMarks.value[row.factory_id]?.error, marksTone: orderMarks.value[row.factory_id]?.error ? 'bg-red-50 text-red-700' : orderHasMarks(row) ? 'bg-teal-50 text-teal-800 hover:bg-teal-100' : 'bg-slate-100 text-slate-600', orderDate: row.order_date || '历史未记录', plannedDate: row.planned_date || '待确认', due: dueReminder(row).label, dueTone: dueReminderClass(row), differences: orderPromiseDifferences(row), progress: row.lines.filter(line => Number(line.required_quantity) > 0).length + ' 条有效 · ' + row.lines.filter(line => Number(line.required_quantity) > 0 && line.accepted).length + ' 条已接', lines: progressLines(row).map(line => ({ id: line.id, label: line.packaging_type, required: Number(line.required_quantity), received: Number(line.received_quantity), inTransit: Number(line.in_transit_quantity), unit: line.unit })), status: orderStatus(row), statusTone: statusClass(row), notice: row.cancellation_notice ? row.cancellation_notice.acknowledged ? '取消通知已收到' : row.cancellation_notice.issued ? '待确认收到取消通知' : '取消变更待生成' : '', noticeTone: row.cancellation_notice?.acknowledged ? 'text-emerald-700' : 'text-red-700' }
}
function showEntryDetail(entry: OrderEntry, pinned = false) {
  if (detailPinned.value && !pinned) return
  if (entry.regular) showOrderDetail(entry.regular.id, pinned)
  else if (entry.special) { detailOrderId.value = ''; detailPinned.value = pinned; specialSelection.value = { id: entry.special.id, factoryId: entry.special.factory_id, create: false } }
}
function showOrderDetail(id: string, pinned = false) {
  if (!visibleOrders.value.some(row => row.id === id)) return
  if (detailPinned.value && !pinned) return
  specialSelection.value = null
  detailOrderId.value = id
  detailPinned.value = pinned
}
function closeOrderDetailPreview() {
  if (!detailPinned.value) { detailOrderId.value = ''; specialSelection.value = null }
}
function closeOrderDetail() {
  specialSelection.value = null
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
    closeSpecialAccept()
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
  if (!selectedSources.value.length || selectedSources.value.some(source => source.kind === 'REGULAR'
    ? !open(source.order) || !source.order.lines.some(needsAcceptance)
    : !specialApprovalAllowed(source.order) || !specialSupplierCanPromise(source.order) || !specialSupplierNeedsAcceptance(source.order))) {
    error.value = '请只选择待接单且当前采购单已生成的订单。'
    return
  }
  bulkVersions = new Map(selectedSources.value.map(source => [selectionKey(source.kind, source.order), acceptanceVersion(source)]))
  bulkAcceptOpen.value = true
}
function acceptanceVersion(source: SupplierSelection) {
  return source.kind === 'SPECIAL' ? specialVersion(source.order) : JSON.stringify([source.order.issue_id, source.order.lines.filter(needsAcceptance).map(line => [line.id, line.commitment_revision])])
}
async function confirmBulkAccept() {
  if (busy.value || !canApprove.value) return
  if (selectedSources.value.some(source => bulkVersions.get(selectionKey(source.kind, source.order)) !== acceptanceVersion(source)
    || (source.kind === 'SPECIAL' ? !specialApprovalAllowed(source.order) || !specialSupplierCanPromise(source.order) || !specialSupplierNeedsAcceptance(source.order) : !open(source.order)))) {
    error.value = '所选订单版本或接单状态已变化，请关闭窗口并重新核对。'; return
  }
  const pending = selectedOrders.value.flatMap(order => order.lines.filter(needsAcceptance)
    .map(line => ({ order, line })))
  const specialPending = selectedSpecialOrders.value.filter(specialSupplierNeedsAcceptance)
  if ((!pending.length && !specialPending.length) || pending.some(({ line }) => !dates[line.id])
    || specialPending.some(row => !specialDates[selectionKey('SPECIAL', row)]?.date)) {
    error.value = '请为每条待接纸品及样板／杂单填写承诺交期。'
    return
  }
  busy.value = true
  error.value = ''
  message.value = ''
  const context = importContext.value
  const succeeded: string[] = []
  let failureMessage = ''
  try {
    for (const factoryId of [...new Set(pending.map(({ order }) => order.factory_id))]) {
      if (context !== importContext.value) return
      const lines = pending.filter(({ order }) => order.factory_id === factoryId)
      const sources = selectedSources.value.filter(source => source.kind === 'REGULAR' && source.order.factory_id === factoryId)
      const signature = JSON.stringify(sources.map(source => [selectionKey(source.kind, source.order), acceptanceVersion(source)]))
      if (completedAcceptances.has(signature)) continue
      await api.acceptBatch(factoryId, lines.map(({ order, line }) => ({
        order_line_id: line.id, issue_id: order.issue_id,
        expected_revision: line.commitment_revision, promised_date: dates[line.id]!,
      })))
      if (context !== importContext.value) return
      completedAcceptances.add(signature)
      succeeded.push(factoryDisplayName(factoryId))
      for (const { line } of lines) dirtyDates.delete(line.id)
      const keys = sources.map(source => selectionKey(source.kind, source.order))
      selectedOrderIds.value = selectedOrderIds.value.filter(key => !keys.includes(key))
      extraLoaded.activity = false
    }
    for (const row of specialPending) {
      if (context !== importContext.value) return
      await submitSpecialAcceptance(row, context)
      if (context !== importContext.value) return
      succeeded.push(`${factoryDisplayName(row.factory_id)} ${row.request_no}`)
      selectedOrderIds.value = selectedOrderIds.value.filter(key => key !== selectionKey('SPECIAL', row))
    }
    message.value = `已确认 ${pending.length} 条正单纸品及 ${specialPending.length} 张样板／杂单；各厂区和来源分别保存。`
    extraLoaded.activity = false
    bulkAcceptOpen.value = false
  } catch (reason) {
    if (context !== importContext.value) return
    failure(reason)
    failureMessage = `${succeeded.length ? `已完成 ${succeeded.join('、')}；` : ''}接单失败：${error.value}`
  } finally {
    if (context !== importContext.value) return
    const [refreshError] = await Promise.all([load(false, false), loadSpecialRequests()])
    void changeTasks.value?.refresh()
    if (context !== importContext.value) return
    const refreshFailure = [refreshError, specialError.value].filter(Boolean).join('；')
    if (failureMessage) error.value = `${failureMessage}${refreshFailure ? `；列表刷新失败：${refreshFailure}` : ''}`
    else if (refreshFailure) error.value = `${message.value} 接单已保存，但列表刷新失败：${refreshFailure}。请刷新查看，勿重复接单。`
    busy.value = false
  }
}
const selectedPromiseLines = computed(() => selectedOrders.value.flatMap(order => order.lines
  .filter(line => line.accepted && order.issue_id)
  .map(line => ({ order, line }))))
function openBulkPromise() {
  if (!canApprove.value) return
  error.value = ''
  if (!selectedPromiseLines.value.length) { error.value = '请选择已接单的订单；待接单请用“批量确认接单”。'; return }
  for (const { line } of selectedPromiseLines.value) bulkPromiseDates[line.id] = line.promised_date || ''
  bulkPromiseUniform.value = ''
  bulkPromiseOpen.value = true
}
function applyBulkPromiseDate() {
  if (!bulkPromiseUniform.value) return
  for (const { line } of selectedPromiseLines.value) bulkPromiseDates[line.id] = bulkPromiseUniform.value
}
async function confirmBulkPromise() {
  if (busy.value || !canApprove.value) return
  error.value = ''
  const pending = selectedPromiseLines.value.filter(({ line }) => bulkPromiseDates[line.id])
  if (pending.length !== selectedPromiseLines.value.length) { error.value = '请为每条纸品填写承诺交期。'; return }
  busy.value = true
  message.value = ''
  const context = importContext.value
  try {
    for (const factoryId of [...new Set(pending.map(({ order }) => order.factory_id))]) {
      if (context !== importContext.value) return
      const lines = pending.filter(({ order }) => order.factory_id === factoryId)
      await api.acceptBatch(factoryId, lines.map(({ order, line }) => ({
        order_line_id: line.id, issue_id: order.issue_id,
        expected_revision: line.commitment_revision, promised_date: bulkPromiseDates[line.id]!,
      })))
    }
    if (context !== importContext.value) return
    message.value = `已更新 ${pending.length} 条纸品的承诺交期；订单页会显示新的承诺日期和差异。`
    selectedOrderIds.value = []
    bulkPromiseOpen.value = false
  } catch (reason) {
    if (context === importContext.value) failure(reason)
  } finally {
    if (context !== importContext.value) return
    const [refreshError] = await Promise.all([load(false, false), loadSpecialRequests()])
    if (refreshError) error.value = `${message.value} 提交已保存，但列表刷新失败：${refreshError}。请刷新查看。`
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
function printDeliveryNote(row: SupplierDocument) {
  if (row.kind !== 'DELIVERY') return
  const note = window.open('', '_blank', 'width=960,height=1280')
  if (!note) { error.value = '浏览器拦截了打印窗口，请允许本页弹窗后重试。'; return }
  note.document.write(deliveryNoteHtml(row, {
    supplierName: workspace.value?.supplier_name || '', factoryName: factoryDisplayName(row.factory_id),
  }))
  note.document.close()
  note.focus()
  setTimeout(() => note.print(), 300)
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
  if (purchases.some(document => document.orders.some(order => order.order_kind === 'SAMPLE' || order.order_kind === 'MISC'))) { error.value = '样板和杂单请下载采购单；东康正单导入模板要求真实合同及货号，不能用需求单号代填。'; return }
  if (purchases.some(document => document.is_cancellation)) { error.value = '取消采购通知请下载原文件，并在东康 ERP 停止或关闭原单；不能作为新增订单导入。'; return }
  const unaccepted = purchases.filter(row => row.supplier_acceptance?.status !== 'ACCEPTED')
  if (unaccepted.length && !window.confirm(`所选采购单中有 ${unaccepted.length} 张尚未确认完整接单：\n${unaccepted.map(row => `${row.document_no}：${row.supplier_acceptance?.label || '接单状态待核实'}`).join('\n')}\n建议先到订单页面确认接单，再导入东康系统。导出不会自动接单。仍要继续导出吗？`)) return
  busy.value = true
  error.value = ''
  try {
    await api.exportOrderImport(purchases, unaccepted.length > 0)
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
function promiseDifference(planned: string, promised: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(planned) || !/^\d{4}-\d{2}-\d{2}$/.test(promised)) return ''
  const days = (Date.parse(promised) - Date.parse(planned)) / 86400000
  if (!Number.isFinite(days) || !days) return ''
  return `承诺 ${promised}，较我方计划 ${planned} ${days > 0 ? '延后' : '提前'} ${Math.abs(days)} 天，请核对`
}
function orderPromiseDifferences(order: SupplierOrder) {
  if (order.awaiting_issue || order.status === 'CANCELLED') return []
  return order.lines.filter(line => line.accepted && Number(line.required_quantity) > 0)
    .flatMap(line => { const text = promiseDifference(order.planned_date, line.promised_date); return text ? [`${line.packaging_type}：${text}`] : [] })
}
async function load(quiet = false, includeSpecial = true) {
  if (includeSpecial) void loadSpecialRequests()
  void loadUnifiedDeliveries()
  const token = ++generation
  const scopes = memberships.value.map(member => member.factory_id)
  if (!scopes.length) return
  void loadOrderMarks(scopes, token)
  loading.value = true
  if (!quiet) error.value = ''
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
    const versionKey = (value: SupplierWorkspace | null) => JSON.stringify(value?.orders.map(order => [order.id, order.issue_id, order.revision, order.cancellation_notice?.acknowledged, order.lines.map(line => line.commitment_revision)]))
    if (versionKey(workspace.value) !== versionKey(data)) { extraLoaded.documents = false; extraLoaded.activity = false }
    workspace.value = data
    workspaceReadError.value = ''
    const orderIds = new Set(data.orders.map(order => order.id))
    const selectableOrderIds = new Set(data.orders.filter(canSelectOrder).map(order => selectionKey('REGULAR', order)))
    selectedOrderIds.value = selectedOrderIds.value.filter(key => !key.startsWith('["REGULAR",') || selectableOrderIds.has(key))
    if (detailOrderId.value && !orderIds.has(detailOrderId.value)) closeOrderDetail()
    if (acceptOrderId.value && !orderIds.has(acceptOrderId.value)) acceptOrderId.value = ''
    for (const order of data.orders) for (const line of order.lines) {
      if (dateIssueIds[line.id] !== order.issue_id) {
        dirtyDates.delete(line.id)
        dateIssueIds[line.id] = order.issue_id
      }
      if (!dirtyDates.has(line.id)) dates[line.id] = line.promised_date || order.planned_date
    }
    if (quiet && (activeTab.value === 'documents' || activeTab.value === 'activity')) await loadExtra(activeTab.value)
    return ''
  } catch (reason) {
    if (token === generation) { workspaceReadError.value = getApiErrorMessage(reason); if (!quiet) workspace.value = null; failure(reason); return error.value }
  } finally {
    if (token === generation) loading.value = false
  }
}
async function refresh() {
  if (busy.value || discovering.value) return
  discovering.value = true
  error.value = ''
  workspace.value = null
  clearOrderMarks()
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
  const context = importContext.value
  try {
    const [regularResult, specialResult] = await Promise.allSettled([api.memberships(), cartonSpecialRequestsApi.factories()])
    if (context !== importContext.value) return
    const available = regularResult.status === 'fulfilled' ? regularResult.value : []
    membershipReadError.value = regularResult.status === 'rejected' ? getApiErrorMessage(regularResult.reason) : ''
    workspaceReadError.value = membershipReadError.value
    specialMemberships.value = specialResult.status === 'fulfilled' ? specialResult.value : []
    memberships.value = available
    if (factoryFilter.value && ![...available, ...specialMemberships.value].some(item => item.factory_id === factoryFilter.value)) factoryFilter.value = ''
    if (available.length) {
      await load()
      if (context !== importContext.value) return
      if (activeTab.value === 'documents' || activeTab.value === 'activity') await loadExtra(activeTab.value)
    }
    else if (specialMemberships.value.length) { workspace.value = { supplier_name: specialMemberships.value[0]?.supplier_name || '', orders: [], shipments: [] }; await Promise.all([loadSpecialRequests(), loadUnifiedDeliveries()]) }
    else error.value = regularResult.status === 'rejected' ? getApiErrorMessage(regularResult.reason) : specialResult.status === 'rejected' ? getApiErrorMessage(specialResult.reason) : '暂无可查看的服务厂区，请确认供应商协同权限。'
    if (regularResult.status === 'rejected') error.value = `采购订单服务厂区读取失败：${getApiErrorMessage(regularResult.reason)}`
    if (specialResult.status === 'rejected') specialError.value = `样板与杂单服务厂区读取失败：${getApiErrorMessage(specialResult.reason)}`
    openSpecialLink()
  } catch (reason) { if (context === importContext.value) failure(reason) } finally { if (context === importContext.value) discovering.value = false }
}
let automaticRefresh: ReturnType<typeof setInterval> | undefined
function refreshOnFocus() {
  if (!busy.value && !loading.value && !discovering.value && !importOpen.value && auth.can('carton_supplier:read', '*', '*') && serviceFactories.value.length) void load(true)
}
onMounted(() => { automaticRefresh = setInterval(refreshOnFocus, 45000); window.addEventListener('focus', refreshOnFocus); void refresh(); window.addEventListener('keydown', onDetailKeydown) })
onBeforeUnmount(() => { if (automaticRefresh) clearInterval(automaticRefresh); window.removeEventListener('focus', refreshOnFocus); window.removeEventListener('keydown', onDetailKeydown) })
async function acknowledgeCancellation(order: SupplierOrder) {
  if (busy.value || !canApprove.value) return
  const context = importContext.value
  busy.value = true; error.value = ''
  try {
    await api.acknowledgeCancellation(order, order.factory_id)
    if (context !== importContext.value) return
    message.value = `合同 ${order.contract_no} 的取消通知已确认收到，请停止按原订单生产或发货。`
    extraLoaded.activity = false; extraLoaded.documents = false
    await load()
    if (context !== importContext.value) return
    if (activeTab.value === 'documents' || activeTab.value === 'activity') await loadExtra(activeTab.value)
  } catch (reason) { if (context === importContext.value) failure(reason) } finally { if (context === importContext.value) busy.value = false }
}
async function acknowledgeRush(order: SupplierOrder) {
  if (busy.value || !canApprove.value) return
  const context = importContext.value
  busy.value = true; error.value = ''
  try {
    await api.acknowledgeRush(order, order.factory_id)
    if (context !== importContext.value) return
    message.value = `合同 ${order.contract_no} 的急单已确认收到，会优先安排处理。`
    await load()
  } catch (reason) { if (context === importContext.value) failure(reason) } finally { if (context === importContext.value) busy.value = false }
}
async function accept(order: SupplierOrder, line: PortalPaper) {
  if (busy.value || !canApprove.value) return
  if (!dates[line.id]) { error.value = '请填写承诺交期'; return }
  const context = importContext.value
  busy.value = true
  error.value = ''
  try {
    await api.accept(line, order, order.factory_id, dates[line.id]!)
    if (context !== importContext.value) return
    dirtyDates.delete(line.id)
    extraLoaded.activity = false
    message.value = `${line.child_no} ${line.accepted ? "承诺交期已更新" : "已确认接单"}`
    const refreshError = await load()
    if (context !== importContext.value) return
    if (refreshError) error.value = `${line.child_no} 已确认接单，但列表刷新失败：${refreshError}。请刷新查看，勿重复接单。`
    if (order.lines.every(item => item.id === line.id || !needsAcceptance(item))) acceptOrderId.value = ''
  } catch (reason) { if (context === importContext.value) failure(reason) } finally { if (context === importContext.value) busy.value = false }
}
async function onDeliveryFile(event: Event) {
  if (!canEdit.value) return
  const token = ++importGeneration, context = importContext.value
  const file = (event.target as HTMLInputElement).files?.[0]
  importFile.value = file ?? null
  importPreview.value = null
  selectedImportNotes.value = []; importModes.value = {}; importChoices.value = {}; reviewedImportChoices.value = []; importChoicesDirty.value = false
  error.value = ''
  if (!file) return
  busy.value = true
  try {
    const preview = await api.previewDeliveryImport(file)
    if (token !== importGeneration || context !== importContext.value || !canEdit.value) return
    importPreview.value = preview
    importModes.value = Object.fromEntries(preview.groups.map(group => [importNoteKey(group), !group.ready && group.receipt_link_ready ? 'EXISTING_RECEIPT' : 'SHIPMENT']))
    selectedImportNotes.value = preview.groups.filter(importGroupReady).map(importNoteKey)
  } catch (reason) { if (token === importGeneration && context === importContext.value) failure(reason) } finally { if (token === importGeneration && context === importContext.value) busy.value = false }
}
async function confirmDeliveryImport() {
  const token = importGeneration, context = importContext.value
  if (busy.value || !canEdit.value || !importFile.value || !importPreview.value) return
  const selectedGroups = importPreview.value.groups.filter(group => selectedImportNotes.value.includes(importNoteKey(group)))
  if (importChoicesDirty.value || !selectedGroups.length || selectedGroups.some(group => !importGroupReady(group))) {
    error.value = '请先重新校验订单选择，再选择匹配成功的送货单。'
    return
  }
  busy.value = true
  error.value = ''
  try {
    const selections = selectedGroups.map(group => ({ factory_id: group.factory_id, delivery_note_no: group.delivery_note_no, ...(importModes.value[importNoteKey(group)] === 'EXISTING_RECEIPT' ? { registration_mode: 'EXISTING_RECEIPT' as const } : {}) }))
    const result = reviewedImportChoices.value.length
      ? await api.confirmDeliveryImport(importFile.value, importPreview.value, selections, reviewedImportChoices.value)
      : await api.confirmDeliveryImport(importFile.value, importPreview.value, selections)
    if (token !== importGeneration || context !== importContext.value || !canEdit.value) return
    importOpen.value = false
    importFile.value = null
    importPreview.value = null
    selectedImportNotes.value = []; importModes.value = {}; importChoices.value = {}; reviewedImportChoices.value = []; importChoicesDirty.value = false
    extraLoaded.documents = false
    extraLoaded.activity = false
    activeTab.value = 'shipments'
    message.value = `已提交 ${result.shipments.length} 张供应商送货单；新发货由仓库验收；已匹配手工收料的后补原单采用供应商价，其他后补凭证由仓库关联，不重复入库。`
    const refreshError = await load()
    if (token === importGeneration && context === importContext.value && refreshError) error.value = `${message.value} 发货已保存，但列表刷新失败：${refreshError}。请刷新查看，勿重复发货。`
  } catch (reason) { if (token === importGeneration && context === importContext.value) failure(reason) } finally { if (token === importGeneration && context === importContext.value) busy.value = false }
}
async function download(id: string, factoryId: string, filename: string) {
  error.value = ''
  try { await api.download(id, factoryId, filename) } catch (reason) { error.value = `附件下载失败：${await getApiErrorMessageAsync(reason)}` }
}
</script>

<template>
  <main class="min-h-screen bg-[#f3f8fc] text-slate-800" data-yl-help="carton-supplier.overview">
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
          <span v-if="serviceFactories.length" class="rounded-lg bg-slate-100 px-3 py-2 text-xs font-semibold text-slate-600">服务厂区：{{ serviceFactories.length }} 个 · 订单合并展示</span>
          <button type="button" :disabled="busy || loading || discovering" class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-600 hover:border-teal-300 disabled:opacity-50" @click="refresh">{{ discovering ? '更新中…' : '刷新' }}</button>
          <AccountMenu />
        </div>
      </div>
      <div class="mx-auto max-w-[1720px] px-4 pb-2 sm:px-6">
        <label class="relative block w-full"><Search class="pointer-events-none absolute left-3 top-2.5 size-4 text-slate-400" aria-hidden="true" /><input v-model="headerSearch" aria-label="顶部搜索" :placeholder="headerSearchPlaceholder" class="h-9 w-full rounded-lg border border-slate-200 bg-slate-50 pl-9 pr-3 text-sm outline-none focus:border-teal-500 focus:bg-white"></label>
      </div>
      <nav class="mx-auto flex max-w-[1720px] flex-wrap items-center gap-1 px-4 sm:px-6" aria-label="供应商协同功能">
        <button type="button" :aria-current="activeTab === 'orders' ? 'page' : undefined" :class="activeTab === 'orders' ? 'border-teal-700 bg-teal-50 text-teal-800' : 'border-transparent text-slate-500 hover:text-teal-700'" class="inline-flex h-11 shrink-0 items-center gap-2 border-b-2 px-4 text-sm font-semibold" @click="openTab('orders')"><ClipboardList class="size-4" />订单管理 <span class="rounded-full bg-white px-2 py-0.5 text-[10px]">{{ orders.length + specialRequests.length }}</span></button>
        <button type="button" :aria-current="activeTab === 'shipments' ? 'page' : undefined" :class="activeTab === 'shipments' ? 'border-teal-700 bg-teal-50 text-teal-800' : 'border-transparent text-slate-500 hover:text-teal-700'" class="inline-flex h-11 shrink-0 items-center gap-2 border-b-2 px-4 text-sm font-semibold" @click="openTab('shipments')"><Truck class="size-4" />发货与仓库反馈 <span class="rounded-full bg-white px-2 py-0.5 text-[10px]">{{ unifiedDeliveries.length }}</span></button>
        <button type="button" :aria-current="activeTab === 'documents' ? 'page' : undefined" :class="activeTab === 'documents' ? 'border-teal-700 bg-teal-50 text-teal-800' : 'border-transparent text-slate-500 hover:text-teal-700'" class="inline-flex h-11 shrink-0 items-center gap-2 border-b-2 px-4 text-sm font-semibold" @click="openTab('documents')"><FileText class="size-4" />采购单与送货单</button>
        <button type="button" :aria-current="activeTab === 'activity' ? 'page' : undefined" :class="activeTab === 'activity' ? 'border-teal-700 bg-teal-50 text-teal-800' : 'border-transparent text-slate-500 hover:text-teal-700'" class="inline-flex h-11 shrink-0 items-center gap-2 border-b-2 px-4 text-sm font-semibold" @click="openTab('activity')"><History class="size-4" />操作日志</button>
        <button type="button" :aria-current="activeTab === 'settlements' ? 'page' : undefined" :class="activeTab === 'settlements' ? 'border-teal-700 bg-teal-50 text-teal-800' : 'border-transparent text-slate-500 hover:text-teal-700'" class="inline-flex h-11 shrink-0 items-center gap-2 border-b-2 px-4 text-sm font-semibold" @click="openTab('settlements')"><FileText class="size-4" />月结对账</button>
      </nav>
    </header>

    <CartonUsageGuide v-if="showUsageGuide" audience="supplier" :factory-name="workspace?.supplier_name || '供应商工作区'" :can-review-supplier-deliveries="false" @close="closeUsageGuide" @supplier-navigate="openUsageGuideDestination" />

    <div class="mx-auto max-w-[1720px] space-y-3 px-4 py-3 sm:px-6">
      <p v-if="error" role="alert" class="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
      <p v-if="message" role="status" class="rounded-xl border border-teal-200 bg-teal-50 p-3 text-sm text-teal-800">{{ message }}</p>
      <p v-if="loading && !workspace" class="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-500">正在读取供应商订单…</p>
      <section v-if="workspace || serviceFactories.length" class="space-y-4">
        <div :inert="detailDocumentPinned || mergedDocumentsOpen ? true : undefined" class="grid grid-cols-2 gap-2 lg:grid-cols-4" aria-label="供应商工作统计">
          <div class="rounded-xl border bg-white px-4 py-2"><p class="text-xs text-slate-500">已发送订单</p><p class="text-xl font-bold">{{ orders.length + specialRequests.length }} <span class="text-xs font-normal">张</span></p></div>
          <div class="rounded-xl border bg-white px-4 py-2"><p class="text-xs text-slate-500">待接单</p><p class="text-xl font-bold text-teal-700">{{ workCounts.acceptance }} <span class="text-xs font-normal">张订单</span></p></div>
          <div class="rounded-xl border bg-white px-4 py-2"><p class="text-xs text-slate-500">待发货</p><p class="text-xl font-bold text-teal-700">{{ workCounts.shipment }} <span class="text-xs font-normal">张订单</span></p></div>
          <button type="button" class="rounded-xl border bg-white px-4 py-2 text-left hover:border-teal-400" @click="openPendingReceipts"><p class="text-xs text-slate-500">待仓库验收</p><p class="text-xl font-bold text-amber-700">{{ workCounts.receipt }} <span class="text-xs font-normal">张送货单</span></p></button>
        </div>

          <section v-show="activeTab === 'orders' || activeTab === 'shipments'" class="enterprise-panel min-w-0 rounded-xl" aria-label="供应商协同工作台">
            <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
              <h2 class="text-sm font-semibold text-slate-900">供应商协同工作台</h2>
              <button type="button" class="rounded-lg px-2 py-2 text-xs font-semibold text-teal-800 hover:bg-teal-50" @click="selectSettlementView('RETURNS')">查看退货签收与退款待办 →</button>
            </div>
            <nav class="flex flex-wrap gap-2 border-b border-slate-100 px-4 py-3" aria-label="供应商协同分类">
              <button type="button" :aria-expanded="collaborationExpanded && collaborationCategory === 'ORDERS'" aria-controls="supplier-collaboration-content" :aria-pressed="collaborationExpanded && collaborationCategory === 'ORDERS'" class="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border px-3 py-2 text-left text-xs focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700" :class="collaborationExpanded && collaborationCategory === 'ORDERS' ? 'border-teal-300 bg-teal-50 font-semibold text-teal-900' : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'" @click="toggleCollaboration('ORDERS')">订单与变更<span class="font-normal">{{ changePendingLabel('ORDERS') }}</span></button>
              <button type="button" :aria-expanded="collaborationExpanded && collaborationCategory === 'MATERIAL'" aria-controls="supplier-collaboration-content" :aria-pressed="collaborationExpanded && collaborationCategory === 'MATERIAL'" class="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border px-3 py-2 text-left text-xs focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700" :class="collaborationExpanded && collaborationCategory === 'MATERIAL' ? 'border-teal-300 bg-teal-50 font-semibold text-teal-900' : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'" @click="toggleCollaboration('MATERIAL')">纸品资料更正<span class="font-normal">{{ materialPendingLabel }}</span></button>
              <button type="button" :aria-expanded="collaborationExpanded && collaborationCategory === 'REPLENISHMENT'" aria-controls="supplier-collaboration-content" :aria-pressed="collaborationExpanded && collaborationCategory === 'REPLENISHMENT'" class="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border px-3 py-2 text-left text-xs focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700" :class="collaborationExpanded && collaborationCategory === 'REPLENISHMENT' ? 'border-teal-300 bg-teal-50 font-semibold text-teal-900' : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'" @click="toggleCollaboration('REPLENISHMENT')">补单接单与交期<span class="font-normal">{{ changePendingLabel('REPLENISHMENT') }}</span></button>
              <button type="button" :aria-expanded="collaborationExpanded && collaborationCategory === 'PRICES'" aria-controls="supplier-collaboration-content" :aria-pressed="collaborationExpanded && collaborationCategory === 'PRICES'" class="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border px-3 py-2 text-left text-xs focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700" :class="collaborationExpanded && collaborationCategory === 'PRICES' ? 'border-teal-300 bg-teal-50 font-semibold text-teal-900' : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'" @click="toggleCollaboration('PRICES')">收料核价<span class="font-normal">{{ priceReviewLabel }}</span></button>
            </nav>
            <p v-if="!collaborationExpanded && (membershipReadError || changePendingState.error || workspaceReadError)" role="alert" class="px-4 pb-3 text-xs text-red-700">协同资料暂不可用：{{ membershipReadError || changePendingState.error || workspaceReadError }}。请选择相应分类重新读取。</p>
            <p v-if="priceReviewState.error && (!collaborationExpanded || collaborationCategory !== 'PRICES')" role="alert" class="px-4 pb-3 text-xs text-red-700">{{ factoryDisplayName(priceReviewState.factoryId) }}收料核价：{{ priceReviewState.error }}。请展开收料核价核对。</p>
            <div id="supplier-collaboration-content" v-show="collaborationExpanded" class="min-w-0 p-4">
              <div v-if="membershipReadError && ['ORDERS', 'REPLENISHMENT'].includes(collaborationCategory)" role="alert" class="flex flex-wrap items-center gap-2 text-sm text-red-700">版本回执服务厂区读取失败：{{ membershipReadError }}<button type="button" :disabled="discovering" class="rounded-lg border border-red-200 bg-white px-3 py-2 text-xs font-semibold disabled:opacity-40" @click="refresh()">重新读取</button></div>
              <CartonSupplierChangeTasks ref="changeTasks" v-show="['ORDERS', 'REPLENISHMENT'].includes(collaborationCategory) && !membershipReadError" :factories="memberships" :viewer-key="importContext" :source-kinds="changeSourceKinds" embedded @pending-state="changePendingState = $event" @changed="load()" />
              <div v-show="collaborationCategory === 'MATERIAL'" aria-label="纸品资料更正待办">
                <div class="flex flex-wrap items-center justify-between gap-3">
                  <p class="text-xs leading-5 text-slate-600">核对前后资料及实物；涉及纸品暂停发货和正式入库，双方确认后生效。</p>
                  <div class="flex flex-wrap gap-2 text-xs" aria-label="资料更正记录范围">
                    <button type="button" :aria-pressed="!materialHistory" class="rounded-lg border px-3 py-2" :class="!materialHistory ? 'border-teal-300 bg-teal-50 font-semibold text-teal-900' : 'border-slate-200 text-slate-600'" @click="materialHistory = false">待处理</button>
                    <button type="button" :aria-pressed="materialHistory" class="rounded-lg border px-3 py-2" :class="materialHistory ? 'border-teal-300 bg-teal-50 font-semibold text-teal-900' : 'border-slate-200 text-slate-600'" @click="materialHistory = true">已处理记录<template v-if="!materialReadLoading && !workspaceReadError">（{{ completedMaterialCorrections.length }}）</template></button>
                  </div>
                </div>
                <p v-if="materialReadLoading" role="status" class="mt-3 text-xs text-slate-500">正在读取纸品资料更正…</p>
                <div v-else-if="workspaceReadError" role="alert" class="mt-3 flex flex-wrap items-center gap-2 text-sm text-red-700">纸品资料更正读取失败：{{ workspaceReadError }}<button type="button" :disabled="loading || discovering" class="rounded-lg border border-red-200 bg-white px-3 py-2 text-xs font-semibold disabled:opacity-40" @click="membershipReadError ? refresh() : load()">重新读取</button></div>
                <p v-else-if="!visibleMaterialCorrections.length" class="mt-3 text-xs text-slate-500">{{ materialHistory ? '暂无已处理的资料更正记录。' : '当前没有待处理的资料更正。' }}</p>
                <div v-if="!materialReadLoading && !workspaceReadError" class="divide-y divide-slate-100">
                  <div v-for="row in visibleMaterialCorrections" :key="row.id" class="flex flex-wrap items-center justify-between gap-3 py-3 text-xs">
                    <span class="min-w-0 flex-1 basis-56 break-words leading-5 [overflow-wrap:anywhere]">{{ factoryDisplayName(row.factory_id) }} · {{ row.contract_no }} · {{ row.item_no }} · {{ row.before.packaging_type }}<span class="ml-2 font-semibold" :class="['PENDING', 'RETURNED'].includes(row.status) ? 'text-amber-800' : 'text-slate-600'">{{ materialStatus[row.status] }}</span></span>
                    <button type="button" class="rounded-lg border border-slate-200 bg-white px-3 py-2 font-semibold text-teal-800 hover:border-teal-300" @click="materialCorrection = row">{{ materialHistory ? '查看更正记录' : '查看并核对' }}</button>
                  </div>
                </div>
              </div>
              <CartonReplenishmentOrders v-show="collaborationCategory === 'REPLENISHMENT'" :orders="workspace?.orders || []" :can-approve="canApprove" :viewer-key="importContext" accepted-only embedded @changed="load()" />
              <section v-show="collaborationCategory === 'PRICES'" class="min-w-0 space-y-4" aria-label="供应商价格核对厂区">
                <label class="flex flex-wrap items-center gap-2 text-xs font-semibold text-slate-600">核价厂区<select v-model="priceReviewFactory" aria-label="供应商核价厂区" :disabled="!serviceFactories.length" class="h-9 max-w-full rounded-lg border border-slate-200 bg-white px-2 text-xs"><option v-for="item in serviceFactories" :key="item.factory_id" :value="item.factory_id">{{ factoryDisplayName(item.factory_id) }}</option></select></label>
                <p class="text-xs leading-5 text-slate-600">下方核对当前厂区的缺价或价格异议；月结按供应商送货单原价计算，与本厂使用同一份金额。</p>
                <p v-if="!priceReviewFactory" class="text-xs text-slate-500">{{ discovering ? '正在读取核价厂区…' : membershipReadError ? '核价厂区暂不可用，请刷新页面重新读取。' : '暂无可核价的服务厂区。' }}</p>
                <CartonPriceReviews v-if="priceReviewFactory" :factory-id="priceReviewFactory" :viewer-key="importContext" supplier embedded @review-state="updatePriceReviewState" @changed="load()" @full-correction="openPriceCorrection(priceReviewFactory, $event)" />
                <p v-if="priceReviewFactory && !priceReviewState.canRead" class="text-xs text-slate-600">当前账号无本厂核价查看权限，请核对厂区或联系授权人员。</p>
              </section>
            </div>
          </section>
          <CartonMaterialCorrectionDialog v-if="materialCorrection" :factory-id="materialCorrection.factory_id" :order-no="materialCorrection.order_no" :record-id="materialCorrection.id" supplier @close="materialCorrection = null" @changed="load()" />
          <section v-if="orders.some(order => order.cancellation_notice?.issued && !order.cancellation_notice.acknowledged)" class="mb-4 rounded-xl border border-red-200 bg-red-50 p-4" aria-label="待确认取消通知">
            <h2 class="text-sm font-bold text-red-800">有订单取消，请核对生产及 ERP 原单</h2>
            <div v-for="order in orders.filter(item => item.cancellation_notice?.issued && !item.cancellation_notice.acknowledged)" :key="order.id" class="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-red-800"><span>{{ factoryDisplayName(order.factory_id) }} · {{ order.contract_no }} · PO {{ order.customer_po || '纸箱订单未填写' }} · {{ order.item_no }} · {{ order.document_no }}</span><button v-if="canApprove" type="button" :disabled="busy" class="rounded border border-red-300 bg-white px-3 py-2 font-semibold" @click="acknowledgeCancellation(order)">确认收到取消通知</button></div>
          </section>

        <section v-if="activeTab === 'settlements'" class="space-y-4"><nav aria-label="供应商月结子页面" class="flex flex-wrap gap-2 rounded-xl border bg-card p-2 text-xs"><button type="button" :aria-pressed="settlementView === 'MONTHLY'" class="rounded-lg px-4 py-2" :class="settlementView === 'MONTHLY' ? 'bg-teal-700 text-white' : 'text-muted-foreground'" @click="selectSettlementView('MONTHLY')">本月对账</button><button type="button" :aria-pressed="settlementView === 'RETURNS'" class="rounded-lg px-4 py-2" :class="settlementView === 'RETURNS' ? 'bg-teal-700 text-white' : 'text-muted-foreground'" @click="selectSettlementView('RETURNS')">退货签收与退款</button><button type="button" :aria-pressed="settlementView === 'PAYABLES'" class="rounded-lg px-4 py-2" :class="settlementView === 'PAYABLES' ? 'bg-teal-700 text-white' : 'text-muted-foreground'" @click="selectSettlementView('PAYABLES')">应付与收款</button></nav><CartonSupplierMonthlySummary v-if="settlementView === 'MONTHLY'" v-model:search="monthlySearch" :factories="memberships" /><CartonSupplierReturns v-else-if="settlementView === 'RETURNS'" :factories="serviceFactories" :viewer-key="importContext" v-model:search="returnSearch" /><CartonPayables v-else :factories="memberships" :viewer-key="importContext" v-model:search="payablesSearch" /></section>
        <template v-else-if="activeTab === 'orders'">
          <p v-if="specialError" role="alert" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{{ specialError }}</p>
          <section class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <CartonFilterBar label="供应商订单筛选" >
<label >厂区<select v-model="factoryFilter" aria-label="供应商订单厂区筛选" class="h-9 rounded-lg border border-slate-200 bg-white px-2 text-xs font-semibold text-slate-700"><option value="">全部厂区</option><option v-for="item in serviceFactories" :key="item.factory_id" :value="item.factory_id">{{ factoryDisplayName(item.factory_id) }} · {{ item.supplier_name }}</option></select></label>
<label >类型<select v-model="orderKind" aria-label="供应商订单类型筛选" class="h-9 rounded-lg border border-slate-200 bg-white px-2 text-xs"><option value="ALL">全部类型</option><option value="PURCHASE">正单</option><option value="SAMPLE">样板单</option><option value="WORKSHOP_MISC">车间杂单</option><option value="SUPPLIER_GIFT">供应商赠送</option></select></label>
<label >客户<select v-model="customerFilter" aria-label="供应商订单客户筛选" class="h-9 rounded-lg border border-slate-200 bg-white px-2 text-xs"><option value="">全部客户</option><option v-for="name in customers" :key="name" :value="name">{{ name }}</option></select></label>
<label >状态<select v-model="statusFilter" aria-label="供应商订单状态筛选" class="h-9 rounded-lg border border-slate-200 bg-white px-2 text-xs"><option value="ALL">全部状态</option><option value="PENDING_ACCEPTANCE">待接单</option><option value="WAITING_SHIPMENT">待送货</option><option value="ACCEPTED">已确认接单</option><option value="PARTIALLY_RECEIVED">部分收料</option><option value="RECEIPT_PENDING">待仓库验收</option><option value="COMPLETED">已完成</option><option value="CANCELLED">已取消</option><option value="PENDING_ISSUE">变更待生成</option></select></label>
<template #more><label class="flex items-center gap-1 text-xs text-slate-600">起始日期<input v-model="orderDateFrom" type="date" aria-label="下单日期开始" :max="orderDateTo || undefined" class="h-9 rounded-lg border border-slate-200 bg-white px-2 text-xs"></label>
<label class="flex items-center gap-1 text-xs text-slate-600">至<input v-model="orderDateTo" type="date" aria-label="下单日期结束" :min="orderDateFrom || undefined" class="h-9 rounded-lg border border-slate-200 bg-white px-2 text-xs"></label>
<label >日期口径<select v-model="orderDateField" aria-label="供应商订单日期口径" class="h-9 rounded-lg border px-2 text-xs"><option value="ORDER">下单日期</option><option value="PLANNED">计划交期</option><option value="PROMISED">最早未交纸品承诺交期</option></select></label>
<label >排序<select v-model="orderSort" aria-label="供应商订单排序" class="h-9 rounded-lg border px-2 text-xs"><option value="DEFAULT">处理阶段 / 计划交期</option><option value="PLANNED_ASC">计划交期由近到远</option><option value="PROMISED_ASC">最早未交纸品承诺交期</option><option value="ORDER_DESC">下单日期由新到旧</option></select></label>
<button type="button" class="h-9 rounded-lg border px-3 text-xs" @click="orderSort = 'DEFAULT'">恢复默认排序</button></template>
<template #actions><button type="button" class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-600 hover:text-teal-700" @click="clearFilters">清空筛选</button></template>

</CartonFilterBar>
            <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-2.5 text-xs">
              <div class="flex flex-wrap items-center gap-3"><span class="font-semibold text-slate-700">订单台账 {{ visibleOrderRows.length }} / {{ orders.length + specialRequests.length }} 张</span><span class="text-slate-500">已选 <b class="text-teal-700">{{ selectedOrderIds.length }}</b> 张订单（筛选外 {{ hiddenSelectedCount }} 张）</span><button type="button" class="font-semibold text-teal-700 hover:text-teal-900" @click="selectedOnly = !selectedOnly">{{ selectedOnly ? '查看全部' : '查看已选' }}</button><button type="button" :disabled="!selectedOrderIds.length" class="text-slate-500 hover:text-slate-800 disabled:opacity-40" @click="selectedOrderIds = []; selectedOnly = false">清空选择</button></div>
              <div class="flex flex-wrap gap-2"><button v-if="canApprove" type="button" :disabled="!selectedOrderIds.length || busy" class="h-9 rounded-lg border border-teal-300 bg-teal-50 px-3 font-semibold text-teal-800 disabled:opacity-40" @click="openBulkAccept">批量确认接单</button><button v-if="canApprove" type="button" :disabled="!selectedOrderIds.length || busy" class="h-9 rounded-lg border border-teal-200 bg-white px-3 font-semibold text-teal-800 disabled:opacity-40" @click="openBulkPromise">批量改承诺交期</button><button v-if="canEdit" type="button" :disabled="busy" class="h-9 rounded-lg bg-teal-700 px-3 font-semibold text-white hover:bg-teal-800 disabled:opacity-40" @click="openDeliveryImport">导入送货单</button></div>
            </div>
            <div class="supplier-order-surface carton-table-wrap">
              <table class="supplier-order-table text-left text-xs carton-table-fit">
                <colgroup><col style="width:3%"><col style="width:7%"><col style="width:17%"><col style="width:12%"><col style="width:8%"><col style="width:13%"><col style="width:16%"><col style="width:10%"><col style="width:14%"></colgroup>
                <thead class="bg-slate-50 text-slate-600"><tr><th><input type="checkbox" aria-label="全选当前筛选订单" :checked="allVisibleSelected" :indeterminate="someVisibleSelected && !allVisibleSelected" :disabled="!selectableVisibleOrders.length" class="size-4 accent-teal-700" @change="toggleVisibleOrders(($event.target as HTMLInputElement).checked)"></th><th>厂区 / 类型</th><th>客户 / 合同 / 单号</th><th>货号 / 产品</th><th>箱唛资料</th><th>下单日期 / 交期提醒</th><th>纸品 / 送货进度</th><th>订单状态</th><th class="text-right">操作</th></tr></thead>
                <tbody class="divide-y divide-slate-100">
                  <CartonSupplierOrderRow v-for="entry in visibleOrderRows" :key="entry.key" :data-testid="entry.special ? 'supplier-special-order-row' : 'supplier-regular-order-row'" :row="supplierRow(entry)" :selected="selectedOrderIds.includes(entry.key)" :selectable="entry.special ? canSelectSpecial(entry.special) : !!entry.regular && canSelectOrder(entry.regular)" @select="toggleOrderSelection(entry.key, $event)" @marks="showEntryDetail(entry, true)" @preview="showEntryDetail(entry)" @leave="closeOrderDetailPreview" @detail="showEntryDetail(entry, true)"><template #actions><span v-if="entry.regular?.rush" class="inline-flex items-center rounded-md bg-red-600 px-2 py-1 text-[10px] font-bold text-white" :title="entry.regular.rush_reason || '本厂要求优先处理这一单'">急单</span><button v-if="entry.regular?.rush && !entry.regular.rush_acknowledged && canApprove" type="button" :disabled="busy" class="rounded-lg border border-red-300 bg-red-50 px-2 py-1.5 font-semibold text-red-700 disabled:opacity-40" @click="acknowledgeRush(entry.regular)">确认收到急单</button><span v-else-if="entry.regular?.rush && entry.regular.rush_acknowledged" class="px-1 text-[10px] font-semibold text-red-700">急单已确认</span><template v-if="entry.special"><button v-if="specialApprovalAllowed(entry.special) && specialSupplierCanPromise(entry.special)" type="button" :aria-label="specialSupplierAccepted(entry.special) ? `更新订单 ${entry.special.request_no} 承诺交期` : `确认订单 ${entry.special.request_no} 接单`" :disabled="busy" class="rounded-lg border px-2 py-1.5 font-semibold text-teal-800 disabled:opacity-40" :class="specialSupplierAccepted(entry.special) ? 'border-slate-200 bg-white hover:border-teal-300' : 'border-teal-200 bg-teal-50'" @click="showSpecialAccept(entry.special, $event)">{{ specialSupplierAccepted(entry.special) ? '更新承诺交期' : '确认接单' }}</button></template><template v-for="order in entry.regular ? [entry.regular] : []" :key="order.id"><button v-if="canApprove && open(order) && order.lines.some(needsAcceptance)" type="button" :aria-label="`确认订单 ${order.order_no} 接单`" class="rounded-lg border border-teal-200 bg-teal-50 px-2 py-1.5 font-semibold text-teal-800" @click="showAccept(order)">确认接单</button><button v-if="canApprove && order.cancellation_notice?.issued && !order.cancellation_notice.acknowledged" type="button" :disabled="busy" class="rounded-lg border border-red-200 bg-red-50 px-2 py-1.5 font-semibold text-red-700" @click="acknowledgeCancellation(order)">确认收到取消通知</button><button v-if="canApprove && open(order) && !order.lines.some(needsAcceptance) && order.lines.some(line => Number(line.required_quantity) > 0)" type="button" :aria-label="`更新订单 ${order.order_no} 承诺交期`" class="rounded-lg border border-slate-200 bg-white px-2 py-1.5 font-semibold text-teal-800 hover:border-teal-300" @click="showAccept(order)">更新承诺交期</button></template></template></CartonSupplierOrderRow>
                  <tr v-if="!visibleOrderRows.length"><td colspan="9" class="px-4 py-10 text-center text-slate-500">{{ loading || specialLoading ? '正在读取订单…' : specialError ? '部分订单未能读取，请刷新重试。' : orders.length + specialRequests.length ? '没有符合当前筛选条件的订单' : '暂无已发送的订单。' }}</td></tr>
                </tbody>
              </table>
            </div>
          </section>

          <CartonSupplierPurchaseOrders v-if="purchaseSelection" :key="purchaseSelection.factoryId + purchaseSelection.orderNo" :factory-id="purchaseSelection.factoryId" :order-no="purchaseSelection.orderNo" @close="purchaseSelection = null" />
          <CartonOrderDetailDialog v-if="detailOrder || specialSelection" data-testid="supplier-order-detail-overlay" :pinned="detailPinned" :title="'订单明细 · ' + factoryDisplayName(detailOrder?.factory_id || specialSelection!.factoryId) + ' · ' + (detailOrder?.customer_name || detailSpecial?.customer_name || '未关联客户')" close-label="关闭供应商订单明细" @close="closeOrderDetail">
            <template v-if="detailOrder">
              <CartonOrderDetailContent :fields="[{ label: '客户', value: detailOrder.customer_name }, { label: '订单类型', value: '正单' }, { label: '合同号', value: detailOrder.contract_no }, { label: '状态', value: orderStatus(detailOrder) }, { label: '货号', value: detailOrder.item_no }, { label: '产品名称', value: detailOrder.product_name }, { label: '客户 PO', value: detailOrder.customer_po || '纸箱订单未填写' }, { label: '下单日期', value: detailOrder.order_date || '历史未记录' }, { label: '计划交期', value: detailOrder.planned_date || '待确认' }, { label: '纸箱采购单据', value: detailOrder.document_no }]" :rows="detailOrder.lines.map(line => ({ id: line.id, label: line.packaging_type + ' · ' + line.child_no, quality: line.paper_quality, specification: line.specification + ' ' + line.dimension_unit, unit: line.unit, rule: '', required: Number(line.required_quantity), received: Number(line.received_quantity), remaining: Math.max(0, Number(line.required_quantity) - Number(line.received_quantity)), progress: 0, note: line.shipping_blocked_reason, inTransit: Number(line.in_transit_quantity), remainingToShip: Number(line.remaining_to_ship), acceptance: Number(line.required_quantity) <= 0 ? '无需接单' : line.accepted ? '已确认' : '待确认', promised: Number(line.required_quantity) <= 0 ? '需求已归零' : line.promised_date || '未承诺' }))" supplier>
<template #status>
              <p v-if="detailOrder.awaiting_issue" class="text-xs font-semibold text-amber-700">订单有尚未生成的变更，旧承诺暂停执行；请等待新版本生成后重新确认接单。</p><p v-else-if="!open(detailOrder)" class="text-xs text-slate-500">{{ detailOrder.status === 'COMPLETED' ? '订单已收齐' : '订单已取消' }}，不可接单或发货。</p>
              </template>
</CartonOrderDetailContent><div v-if="detailPinned" class="flex justify-end"><button type="button" class="h-9 rounded-lg bg-teal-700 px-4 text-xs font-bold text-white" @click="purchaseSelection = { factoryId: detailOrder.factory_id, orderNo: detailOrder.order_no }">查看采购单</button></div>
              <div class="flex flex-wrap gap-2"><button v-for="file in detailOrder.attachments" :key="file.id" type="button" class="rounded-lg border border-teal-200 bg-teal-50 px-2.5 py-1.5 text-xs font-semibold text-teal-700" @click="download(file.id, detailOrder.factory_id, file.filename)">{{ file.filename }} · v{{ file.version }}</button></div>
              <div v-if="detailPinned" data-testid="supplier-order-marks"><CartonMarkAssetLibrary :key="detailOrder.factory_id + detailOrder.id + detailOrder.issue_id" :factory-id="detailOrder.factory_id" :order-id="detailOrder.id" :supplier-issue-id="detailOrder.issue_id" supplier read-only /></div>
            </template>
            <CartonSpecialRequests v-else-if="specialSelection" :key="specialSelection.factoryId + ':' + specialSelection.id + ':' + detailPinned" :factory-id="specialSelection.factoryId" :viewer-key="importContext" supplier supplier-read-only mode="detail" :request-id="detailPinned ? specialSelection.id : undefined" :preview-request="detailPinned ? undefined : detailSpecial || undefined" @changed="loadSpecialRequests" />
          </CartonOrderDetailDialog>

          <CartonOrderDetailDialog v-if="canApprove && (acceptOrder || acceptSpecial)" :title="(acceptSpecial && specialSupplierAccepted(acceptSpecial) || acceptOrder && !acceptOrder.lines.some(needsAcceptance) ? '更新承诺交期' : '确认接单') + ' · ' + factoryDisplayName(acceptOrder?.factory_id || acceptSpecial!.factory_id)" :description="acceptOrder ? acceptOrder.customer_name + ' · 合同 ' + acceptOrder.contract_no + ' · 货号 ' + acceptOrder.item_no : specialKinds[acceptSpecial!.kind] + ' · ' + acceptSpecial!.request_no + ' · ' + (acceptSpecial!.customer_name || '未关联客户')" :busy="busy" close-label="关闭接单窗口" @close="acceptSpecial ? closeSpecialAccept() : acceptOrderId = ''">
            <p v-if="error" role="alert" class="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">{{ error }}</p><p v-if="message" role="status" class="rounded-lg border border-teal-200 bg-teal-50 p-3 text-xs text-teal-800">{{ message }}</p>
            <template v-if="acceptOrder"><CartonSupplierAcceptanceFields :planned-date="acceptOrder.planned_date" :busy="busy" :disabled="!open(acceptOrder)" :lines="acceptOrder.lines.map(line => ({ id: line.id, label: line.packaging_type + ' · ' + line.child_no, description: line.paper_quality + ' · ' + line.specification + ' ' + line.dimension_unit + ' · 需求 ' + line.required_quantity + ' ' + line.unit, required: Number(line.required_quantity), accepted: line.accepted, promised: line.promised_date, date: dates[line.id] || '', dateLabel: line.child_no + ' 承诺交期', difference: promiseDifference(acceptOrder!.planned_date, dates[line.id] || '') }))" @date="(id, value) => { dates[id] = value; dirtyDates.add(id) }" @accept="id => { const line = acceptOrder!.lines.find(line => line.id === id); if (line) accept(acceptOrder!, line) }" /></template>
            <template v-else-if="acceptSpecial"><CartonSupplierAcceptanceFields whole-order :planned-date="acceptSpecial.required_date" :busy="busy" :date-locked="specialRetries.has(acceptSpecialKey)" :accepted="specialSupplierAccepted(acceptSpecial)" :date="specialDates[acceptSpecialKey]!.date" :date-label="acceptSpecial.request_no + ' 整单承诺交期'" :difference="promiseDifference(acceptSpecial.required_date, specialDates[acceptSpecialKey]!.date)" :lines="acceptSpecial.lines.map((line, index) => ({ id: line.id || String(index), label: line.packaging_type, description: line.paper_quality + ' · ' + line.specification + ' ' + line.dimension_unit + ' · 需求 ' + line.quantity + ' ' + line.unit, required: Number(line.quantity), accepted: specialSupplierAccepted(acceptSpecial!), dateLabel: '', date: '' }))" @date="(_id, value) => { specialDates[acceptSpecialKey]!.date = value; specialDates[acceptSpecialKey]!.dirty = true }" />
                <p v-if="specialRetries.has(acceptSpecialKey)" class="rounded-lg bg-amber-50 p-3 text-amber-900">上次提交结果未确认，日期与提交内容已保留；重试将核对同一次提交。<template v-if="specialRetries.get(acceptSpecialKey)?.source_id !== acceptSpecial.current_version_id">采购版本已替换，须先查看历史回执，不能直接重发旧版本。</template></p>
                <p v-if="unresolvedSpecialRequests.has(acceptSpecialKey)" class="text-amber-900">旧版本提交结果仍待核实，旧版本不视为已同意；请在工作台查看历史回执。</p>
                <button v-if="specialRetries.has(acceptSpecialKey) && specialRetries.get(acceptSpecialKey)?.source_id !== acceptSpecial.current_version_id" type="button" :disabled="busy" class="rounded-lg border border-amber-300 px-3 py-2 font-semibold text-amber-900" @click="useCurrentSpecialVersion(acceptSpecial)">已核对历史回执，处理当前版本</button>
            </template>
            <template #footer><template v-if="acceptSpecial"><button type="button" :disabled="busy || !specialApprovalAllowed(acceptSpecial) || !specialSupplierCanPromise(acceptSpecial) || (specialRetries.has(acceptSpecialKey) && specialRetries.get(acceptSpecialKey)?.source_id !== acceptSpecial.current_version_id)" class="rounded-lg bg-teal-700 px-4 py-2 text-xs font-semibold text-white disabled:opacity-40" @click="saveSpecialAcceptance(acceptSpecial)">{{ busy ? '正在保存…' : specialRetries.has(acceptSpecialKey) ? '重试原接单提交' : specialSupplierAccepted(acceptSpecial) ? '保存承诺交期' : '确认接单' }}</button></template></template>
          </CartonOrderDetailDialog>

          <DialogRoot :open="canApprove && bulkAcceptOpen" @update:open="value => { if (!value) bulkAcceptOpen = false }">
            <DialogOverlay class="fixed inset-0 z-[64] bg-slate-950/45" />
            <DialogContent class="fixed left-1/2 top-1/2 z-[65] flex max-h-[88vh] w-[calc(100%-2rem)] max-w-5xl -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl bg-white shadow-2xl" @interact-outside.prevent>
              <div class="flex items-start justify-between border-b border-slate-200 p-5"><div><DialogTitle id="supplier-bulk-accept-title" class="text-lg font-bold">批量确认接单 · {{ selectedSources.length }} 张订单</DialogTitle><DialogDescription class="mt-1 text-xs text-slate-500">正单纸品按厂区保存，样板／杂单逐张保存；各次保存独立生效。部分失败时保留未完成来源，重试不会重复提交已完成来源。</DialogDescription></div><button type="button" aria-label="关闭批量接单窗口" class="rounded-lg p-2 text-slate-500" @click="bulkAcceptOpen = false"><X class="size-4" /></button></div>
              <p v-if="error" role="alert" class="mx-5 mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">{{ error }}</p>
              <div class="min-h-0 space-y-3 overflow-auto p-5"><div v-for="order in selectedOrders" :key="order.id" class="rounded-lg border border-slate-200 p-3"><h3 class="mb-2 text-sm font-bold">{{ factoryDisplayName(order.factory_id) }} · {{ order.customer_name }} · {{ order.contract_no }} · {{ order.item_no }}</h3><div v-for="line in order.lines.filter(needsAcceptance)" :key="line.id" class="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 py-2 text-xs"><span>{{ line.packaging_type }} · {{ line.child_no }} · 需求 {{ line.required_quantity }} {{ line.unit }}</span><label>承诺交期 <input v-model="dates[line.id]" @input="dirtyDates.add(line.id)" type="date" :aria-label="`批量接单 ${line.child_no} 承诺交期`" :disabled="busy" class="ml-1 h-9 rounded-lg border border-slate-200 px-2"></label><p v-if="promiseDifference(order.planned_date, dates[line.id] || '')" role="status" class="w-full font-semibold text-amber-700">{{ promiseDifference(order.planned_date, dates[line.id] || '') }}</p></div></div>
              <div v-for="row in selectedSpecialOrders" :key="selectionKey('SPECIAL', row)" class="rounded-lg border border-slate-200 p-3 text-xs"><h3 class="font-semibold">{{ factoryDisplayName(row.factory_id) }} · {{ specialKinds[row.kind] }} · {{ row.request_no }}</h3><p class="mt-1 text-slate-600">本版本全部纸品共用一个承诺交期。</p><label class="mt-2 block">承诺交期<input v-model="specialDates[selectionKey('SPECIAL', row)]!.date" type="date" :aria-label="`批量接单 ${row.request_no} 整单承诺交期`" :disabled="busy || specialRetries.has(selectionKey('SPECIAL', row))" class="ml-2 h-9 rounded-lg border border-slate-200 px-2" @input="specialDates[selectionKey('SPECIAL', row)]!.dirty = true"></label><p v-if="specialRetries.has(selectionKey('SPECIAL', row))" class="mt-2 text-amber-900">上次结果未确认，重试保留原日期与同一次提交。</p></div></div>
              <div class="flex justify-end gap-2 border-t border-slate-200 p-4"><button type="button" :disabled="busy" class="rounded-lg border border-slate-200 px-4 py-2 text-xs font-semibold" @click="bulkAcceptOpen = false">取消</button><button type="button" :disabled="busy" class="rounded-lg bg-teal-700 px-4 py-2 text-xs font-bold text-white disabled:opacity-40" @click="confirmBulkAccept">{{ busy ? '正在确认…' : '确认所选订单接单' }}</button></div>
            </DialogContent>
          </DialogRoot>

          <DialogRoot :open="canApprove && bulkPromiseOpen" @update:open="value => { if (!value) bulkPromiseOpen = false }">
            <DialogOverlay class="fixed inset-0 z-[64] bg-slate-950/45" />
            <DialogContent class="fixed left-1/2 top-1/2 z-[65] flex max-h-[88vh] w-[calc(100%-2rem)] max-w-4xl -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl bg-white shadow-2xl" @interact-outside.prevent>
              <div class="flex items-start justify-between border-b border-slate-200 p-5"><div><DialogTitle class="text-lg font-bold">批量更新承诺交期 · {{ selectedPromiseLines.length }} 条纸品</DialogTitle><DialogDescription class="mt-1 text-xs text-slate-500">只更新已接单的纸品；未接单请先用“批量确认接单”。改期会通知本厂，并在订单页显示新的承诺日期和差异。</DialogDescription></div><button type="button" aria-label="关闭批量改期窗口" class="rounded-lg p-2 text-slate-500" @click="bulkPromiseOpen = false"><X class="size-4" /></button></div>
              <p v-if="error" role="alert" class="mx-5 mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">{{ error }}</p>
              <div class="min-h-0 space-y-3 overflow-auto p-5">
                <div class="flex flex-wrap items-end gap-2 rounded-lg border border-teal-200 bg-teal-50 p-3 text-xs"><label class="space-y-1"><span class="block text-[10px] font-bold text-teal-900">统一日期</span><input v-model="bulkPromiseUniform" type="date" aria-label="统一承诺日期" :disabled="busy" class="h-9 rounded-lg border px-2"></label><button type="button" :disabled="busy || !bulkPromiseUniform" class="h-9 rounded-lg bg-teal-700 px-3 font-bold text-white disabled:opacity-40" @click="applyBulkPromiseDate">应用到全部</button><span class="text-[10px] text-teal-800">再逐条核对，可单独改某一条。</span></div>
                <div v-for="order in selectedOrders.filter(order => order.lines.some(line => line.accepted))" :key="order.id" class="rounded-lg border border-slate-200 p-3">
                  <h3 class="mb-2 text-sm font-bold">{{ factoryDisplayName(order.factory_id) }} · {{ order.customer_name }} · {{ order.contract_no }} · {{ order.item_no }}</h3>
                  <div v-for="line in order.lines.filter(line => line.accepted)" :key="line.id" class="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 py-2 text-xs">
                    <span>{{ line.packaging_type }} · {{ line.child_no }} · 原承诺 {{ line.promised_date || '未填写' }}</span>
                    <label>新承诺 <input v-model="bulkPromiseDates[line.id]" type="date" :aria-label="`批量改期 ${line.child_no} 承诺日期`" :disabled="busy" class="ml-1 h-9 rounded-lg border border-slate-200 px-2"></label>
                    <p v-if="promiseDifference(order.planned_date, bulkPromiseDates[line.id] || '')" class="w-full font-semibold text-amber-700">{{ promiseDifference(order.planned_date, bulkPromiseDates[line.id] || '') }}</p>
                  </div>
                </div>
                <p class="text-xs text-slate-500">样板／杂单的承诺交期请在订单明细里逐张更新。</p>
              </div>
              <div class="flex justify-end gap-2 border-t border-slate-200 p-4"><button type="button" :disabled="busy" class="rounded-lg border border-slate-200 px-4 py-2 text-xs font-semibold" @click="bulkPromiseOpen = false">取消</button><button type="button" :disabled="busy || !selectedPromiseLines.length" class="rounded-lg bg-teal-700 px-4 py-2 text-xs font-bold text-white disabled:opacity-40" @click="confirmBulkPromise">{{ busy ? '正在保存…' : '确认更新承诺交期' }}</button></div>
            </DialogContent>
          </DialogRoot>

          <div v-if="canEdit && importOpen" class="fixed inset-0 z-[64] flex items-center justify-center bg-slate-950/45 p-4" @click.self="closeDeliveryImport">
            <div role="dialog" aria-modal="true" aria-labelledby="supplier-delivery-import-title" class="flex max-h-[90vh] w-full max-w-6xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
              <div class="flex items-start justify-between border-b border-slate-200 p-5"><div><h2 id="supplier-delivery-import-title" class="text-lg font-bold">导入东康送货单</h2><p class="mt-1 text-xs text-slate-500">上传原系统 Excel，核对厂区、合同、货号、纸品及发货数量后确认。确认后送到各厂区仓库待收货，不立即计入库存。</p></div><button type="button" aria-label="关闭送货单导入" :disabled="busy" class="rounded-lg p-2 text-slate-500 hover:bg-slate-100 disabled:opacity-40" @click="closeDeliveryImport"><X class="size-4" /></button></div>
              <div class="min-h-0 space-y-4 overflow-auto p-5">
                <label class="block text-sm font-semibold">选择送货明细表（.xls / .xlsx）<input type="file" accept=".xls,.xlsx" :disabled="busy" class="mt-2 block w-full rounded-lg border border-slate-200 p-2 text-xs" @change="onDeliveryFile"></label>
                <p v-if="busy" role="status" class="text-sm text-teal-700">正在处理送货单…</p>
                <p v-if="error" role="alert" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
                <button v-if="importPreview?.groups.some(group => group.rows.some(row => row.candidates?.length))" type="button" :disabled="busy" class="rounded-lg border border-teal-300 px-3 py-2 text-xs text-teal-800" @click="recheckImportChoices">重新校验订单选择</button><p v-if="importChoicesDirty" class="text-xs text-amber-700">订单选择已改变，请重新校验后提交。</p><p v-if="importPreview" class="text-xs text-slate-600">{{ importPreview.filename }} · 共 {{ importPreview.row_count }} 行 · {{ importPreview.groups.length }} 张送货单；无单候选将送仓库逐条核实，确认发货不等于入库。</p>
                <section v-for="group in importPreview?.groups ?? []" :key="importNoteKey(group)" class="rounded-xl border p-3" :class="importGroupReady(group) ? 'border-teal-200' : 'border-amber-200 bg-amber-50/40'">
                  <div class="flex flex-wrap items-center gap-3 text-sm"><input v-model="selectedImportNotes" :value="importNoteKey(group)" type="checkbox" :disabled="!importGroupReady(group) || busy" :aria-label="`确认送货单 ${group.delivery_note_no || '未填单号'}`" class="size-4 accent-teal-700"><b>{{ group.delivery_note_no || '未填送货单号' }}</b><span>{{ factoryDisplayName(group.factory_id) }} · {{ group.delivery_date || '未填日期' }}</span><span :class="importGroupReady(group) ? 'text-teal-700' : 'text-amber-700'" class="font-semibold">{{ importModes[importNoteKey(group)] === 'EXISTING_RECEIPT' && group.receipt_link_ready ? '后补凭证 · 仅关联已有入库' : group.ready ? group.rows.some(row => row.status === 'AD_HOC_REVIEW') ? '可发货 · 含仓库待核实无单纸品' : '可确认发货' : '需核对' }}</span></div>
                  <div v-if="group.receipt_link_ready" class="mt-3 rounded-lg bg-teal-50 p-3 text-xs text-teal-900"><p>发现 {{ group.existing_receipt_count }} 张可匹配的已入库记录。若本单是已手动收料的后补凭证，请选择仅关联；确为新一批到货才选择新发货。</p><label class="mt-2 flex items-center gap-2">提交方式<select v-model="importModes[importNoteKey(group)]" :aria-label="`送货单 ${group.delivery_note_no} 提交方式`" :disabled="busy" class="rounded border bg-white p-2"><option value="SHIPMENT" :disabled="!group.ready">新发货，等待仓库验收</option><option value="EXISTING_RECEIPT">后补凭证，仅关联已有入库</option></select></label><p class="mt-2">{{ group.manual_delivery_id ? '已匹配原手工收料，确认后补入供应商原价；价格变化通知仓库，数量和验收日期保留。' : '由仓库确认关联原收料；采用供应商原价并通知仓库，数量和验收日期保留。' }}</p></div><p v-for="issue in group.issues" :key="issue" class="mt-2 text-xs text-amber-700">{{ issue }}</p>
                  <div class="mt-2 overflow-x-auto carton-table-wrap"><table class="w-full min-w-[960px] text-left text-xs carton-table-fit"><thead class="bg-slate-50 text-slate-600"><tr><th class="p-2">原表位置</th><th class="p-2">客户单号 / 客户料号</th><th class="whitespace-nowrap p-2">纸品类型</th><th class="p-2">纸质 / 规格</th><th class="p-2">发货量</th><th class="p-2">送货单价</th><th class="p-2">匹配订单 / 纸品</th><th class="p-2">校验</th></tr></thead><tbody><tr v-for="row in group.rows" :key="`${row.source_sheet}-${row.source_row}`" class="border-t border-slate-100"><td data-label="原表位置" class="p-2">{{ row.source_sheet }} · {{ row.source_row }}</td><td data-label="客户单号 / 客户料号" class="p-2">{{ row.contract_no || '—' }} / {{ row.item_no || '—' }}</td><td data-label="纸品类型" class="whitespace-nowrap p-2">{{ row.packaging_type || '未填写' }}</td><td data-label="纸质 / 规格" class="p-2">{{ row.paper_quality || '未填写' }} · {{ row.specification || '未填写' }}</td><td data-label="发货量" class="p-2">{{ row.delivered_quantity }}</td><td data-label="送货单价" class="p-2">{{ Number(row.unit_price) > 0 ? row.unit_price : '未填写' }}</td><td data-label="匹配订单 / 纸品" class="p-2">{{ row.order_no || (row.status === 'AD_HOC_REVIEW' ? '无单待仓库核实' : '未匹配') }} {{ row.child_no }}<label v-if="row.candidates?.length" class="mt-2 block">对应订单<select v-model="importChoices[importRowKey(row)]" :disabled="busy" :aria-label="`${row.source_sheet} 第${row.source_row}行对应订单`" class="mt-1 w-full rounded border bg-white p-2" @change="importChoicesDirty = true; selectedImportNotes = []"><option value="">请选择对应订单</option><option v-for="candidate in row.candidates" :key="`${candidate.order_line_id}|${candidate.issue_id}`" :value="`${candidate.order_line_id}|${candidate.issue_id}`">{{ candidate.document_no || candidate.order_no }} · {{ candidate.replenishment ? candidate.responsibility === 'SUPPLIER' ? '补单 · 供应商责任免费' : '补单 · 我方责任计费' : '普通采购' }} · PO {{ candidate.customer_po || '未填写' }} · 交期 {{ candidate.planned_date }} · 未送 {{ candidate.remaining_to_ship }} {{ candidate.unit }}</option></select></label></td><td data-label="校验" class="p-2" :class="importModes[importNoteKey(group)] === 'EXISTING_RECEIPT' && group.receipt_link_ready ? 'text-teal-700' : row.status === 'READY' ? 'text-teal-700' : row.status === 'AD_HOC_REVIEW' ? 'text-amber-700' : 'text-red-700'"><CartonImportDifference :message="importModes[importNoteKey(group)] === 'EXISTING_RECEIPT' && group.receipt_link_ready ? '已匹配原入库凭证，等待仓库选择并关联' : row.reason" /></td></tr></tbody></table></div>
                </section>
              </div>
              <div class="flex justify-end gap-2 border-t border-slate-200 p-4"><button type="button" :disabled="busy" class="rounded-lg border border-slate-200 px-4 py-2 text-xs font-semibold" @click="closeDeliveryImport">取消</button><button type="button" :disabled="busy || importChoicesDirty || !selectedImportNotes.length" class="rounded-lg bg-teal-700 px-4 py-2 text-xs font-bold text-white disabled:opacity-40" @click="confirmDeliveryImport">确认 {{ selectedImportNotes.length }} 张送货单{{ selectedImportNotes.some(key => importModes[key] === 'EXISTING_RECEIPT') ? '（含后补凭证）' : '发货' }}</button></div>
            </div>
          </div>
        </template>

        <template v-else-if="activeTab === 'shipments'">
          <section class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 p-4"><div><h2 class="text-sm font-bold">发货与仓库反馈</h2><p class="mt-1 text-xs text-slate-500">同一张送货单统一核实正单、样板、杂单与额外纸品，保留各批实际收货和原箱唛。</p></div></div>
            <CartonShipmentFilters v-model="shipmentFilters" :rows="unifiedShipmentRows" hide-search @clear="factoryFilter = ''"><label>厂区<select v-model="factoryFilter" aria-label="供应商发货厂区筛选" class="h-9 max-w-full rounded-lg border px-2 text-xs"><option value="">全部厂区</option><option v-for="item in serviceFactories" :key="item.factory_id" :value="item.factory_id">{{ factoryDisplayName(item.factory_id) }} · {{ item.supplier_name }}</option></select></label></CartonShipmentFilters>
            <p v-if="deliveryError" role="alert" class="m-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">送货单读取失败：{{ deliveryError }}</p>
            <p class="px-4 pt-3 text-xs text-slate-500">显示 {{ matchingUnifiedShipments.length }} 张送货单</p>
            <div class="space-y-3 p-4"><div v-for="shipment in matchingUnifiedShipments" :key="shipment.id"><p class="mb-1 text-xs font-semibold text-teal-800">送往{{ factoryDisplayName(shipment.factory_id) }}</p><CartonUnifiedDeliveryNotes :group="shipment.group" supplier :viewer-key="importContext" /></div><p v-if="!matchingUnifiedShipments.length && !deliveryError" class="py-8 text-center text-sm text-slate-500">暂无符合条件的发货单</p></div>
          </section>
        </template>

        <template v-else-if="activeTab === 'documents'">
          <section :inert="detailDocumentPinned || mergedDocumentsOpen ? true : undefined" class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 p-4"><div><h2 class="text-base font-bold">采购单与送货单</h2><p class="mt-1 text-xs text-slate-500">仓库同一次批量确认的订单自动合并为一张采购单，保留各订单明细；请先核对是否接单；未完整接单导出东康导入模板时必须确认提醒，导出不会自动接单。</p></div><div class="flex flex-wrap gap-2"><button type="button" :disabled="busy || !selectedDocuments.some(row => row.kind === 'PURCHASE')" class="h-9 rounded-lg border border-teal-300 bg-teal-50 px-4 text-xs font-bold text-teal-800 disabled:opacity-40" @click="exportSelectedOrderImports">导出东康导入模板（{{ selectedDocuments.filter(row => row.kind === 'PURCHASE').length }} 张采购单）</button><button type="button" :disabled="!selectedDocuments.length" class="h-9 rounded-lg bg-teal-700 px-4 text-xs font-bold text-white disabled:opacity-40" @click="openMergedDocuments">预览并导出 {{ selectedDocuments.length }} 张单据</button></div></div>
            <CartonFilterBar label="供应商单据筛选" >
<label >厂区<select v-model="documentFactory" aria-label="单据厂区筛选" class="h-9 rounded-lg border border-slate-200 bg-white px-2 text-xs"><option value="">全部厂区</option><option v-for="item in memberships" :key="item.factory_id" :value="item.factory_id">{{ factoryDisplayName(item.factory_id) }}</option></select></label>
<label >类型<select v-model="documentKind" aria-label="单据类型筛选" class="h-9 rounded-lg border border-slate-200 bg-white px-2 text-xs"><option value="">全部类型</option><option value="PURCHASE">采购单</option><option value="DELIVERY">送货单</option></select></label>
<label >业务类型<select v-model="documentBusinessKind" aria-label="单据业务类型筛选" class="h-9 rounded-lg border border-slate-200 bg-white px-2 text-xs"><option value="">全部业务类型</option><option value="REGULAR">正单</option><option value="SAMPLE">样板</option><option value="MISC">杂单</option><option value="UNKNOWN">待分类</option></select></label>
<label >状态<select v-model="documentStatus" aria-label="单据状态筛选" class="h-9 rounded-lg border border-slate-200 bg-white px-2 text-xs"><option value="">全部状态</option><option value="已生成">已生成</option><option value="SENT">待仓库确认</option><option value="RECEIVED">已核实</option><option value="RECEIPT_REVERSED">收料已冲销，待更正</option><option value="NOT_RECEIVED">仓库未收到</option></select></label>
<label class="text-xs">日期从 <input v-model="documentDateFrom" type="date" aria-label="单据日期开始" class="h-9 rounded-lg border border-slate-200 px-2"></label>
<label class="text-xs">至 <input v-model="documentDateTo" type="date" aria-label="单据日期结束" class="h-9 rounded-lg border border-slate-200 px-2"></label>

<template #actions><button type="button" class="h-9 rounded-lg border border-slate-200 px-3 text-xs" @click="documentSearch = ''; documentFactory = ''; documentKind = ''; documentBusinessKind = ''; documentStatus = ''; documentDateFrom = ''; documentDateTo = ''">清空筛选</button></template>

</CartonFilterBar>
            <div class="flex items-center gap-3 border-b border-slate-100 px-4 py-2 text-xs"><span>单据 {{ filteredDocuments.length }} / {{ documents.length }} 张</span><span>已选 {{ selectedDocuments.length }} 张单据 · {{ mergedDocumentOrders.length }} 张订单</span><span class="text-slate-400">一次最多 100 张单据</span><button type="button" :disabled="!selectedDocumentKeys.length" class="text-slate-500 disabled:opacity-40" @click="selectedDocumentKeys = []">清空选择</button></div>
            <div class="overflow-x-auto carton-table-wrap"><table class="w-full min-w-[980px] text-left text-xs carton-table-fit"><thead class="bg-slate-50 font-bold text-slate-600"><tr><th class="px-4 py-3"><input type="checkbox" aria-label="全选当前筛选单据" :checked="allVisibleDocumentsSelected" @change="toggleVisibleDocuments($event)"></th><th class="px-3 py-3">类型</th><th class="px-3 py-3">送货厂区</th><th class="px-3 py-3">单据号</th><th class="px-3 py-3">日期</th><th class="px-3 py-3">包含订单</th><th class="px-3 py-3">纸品条数</th><th class="px-3 py-3">状态</th><th class="px-3 py-3">是否接单</th><th class="px-3 py-3" title="从启用导出次数记录起，每次成功生成 Excel 累计一次；合并导出涉及的每张单据分别计一次">导出次数</th><th class="px-3 py-3 text-right">操作</th></tr></thead><tbody class="divide-y divide-slate-100"><tr v-for="row in filteredDocuments" :key="documentKey(row)"><td data-label="选择" class="px-4 py-3"><input :checked="selectedDocumentKeys.includes(documentKey(row))" type="checkbox" :aria-label="`选择单据 ${row.document_no}`" @change="toggleDocument(row, $event)"></td><td data-label="类型" class="px-3 py-3">{{ row.kind === 'PURCHASE' ? (row.is_cancellation ? '取消采购通知' : row.is_batch ? '合并采购单' : '采购单') : '送货单' }}</td><td data-label="送货厂区" class="px-3 py-3">{{ factoryDisplayName(row.factory_id) }}</td><td data-label="单据号" class="px-3 py-3 font-bold">{{ row.document_no }}</td><td data-label="日期" class="px-3 py-3">{{ row.date }}</td><td data-label="包含订单" class="px-3 py-3">{{ row.orders.length }} 张订单<span v-if="row.unmatched_line_count"> · {{ row.unmatched_line_count }} 条无单纸品</span><span v-if="row.orders.some(item => item.contract_no?.trim())"> · {{ row.orders.map(item => item.contract_no?.trim()).filter(Boolean).join('、') }}</span><p class="mt-1 text-slate-500">{{ documentBusinessLabel(row) }}</p></td><td data-label="纸品条数" class="px-3 py-3">{{ row.lines.length }}</td><td data-label="状态" class="px-3 py-3">{{ row.status === 'RECEIPT_REVERSED' ? '收料已冲销，待更正' : row.status === 'SENT' ? '待仓库确认' : row.status === 'RECEIVED' ? '已核实' : row.status === 'NOT_RECEIVED' ? '仓库未收到' : row.status }}</td><td data-label="是否接单" class="px-3 py-3" :aria-label="`${row.document_no} 接单状态`"><span :class="row.supplier_acceptance?.status === 'ACCEPTED' ? 'text-emerald-700' : 'text-amber-700'">{{ row.kind === 'PURCHASE' ? row.supplier_acceptance?.label || '接单状态待核实' : '—' }}</span><p v-if="row.kind === 'PURCHASE' && row.supplier_acceptance" class="mt-1 text-slate-500">{{ row.supplier_acceptance.accepted_line_count }}/{{ row.supplier_acceptance.total_line_count }} 条已接</p></td><td data-label="导出次数" class="px-3 py-3" :aria-label="`${row.document_no} 导出 ${row.export_count ?? 0} 次`">{{ row.export_count ?? 0 }}</td><td data-label="操作" class="px-3 py-3 text-right"><button v-if="row.kind === 'DELIVERY'" type="button" :aria-label="`打印送货单 ${row.document_no}`" class="mr-1 rounded-lg border border-teal-200 bg-teal-50 px-3 py-1.5 font-semibold text-teal-800" @click="printDeliveryNote(row)">打印</button><button type="button" :aria-label="`查看单据 ${row.document_no} 明细`" title="悬停预览单据明细，单击后保持显示" aria-haspopup="dialog" class="rounded-lg border border-slate-200 px-3 py-1.5 font-semibold" @mouseenter="showDocumentDetail(row)" @mouseleave="closeDocumentDetailPreview" @focus="showDocumentDetail(row)" @blur="closeDocumentDetailPreview" @click="showDocumentDetail(row, true)">明细</button></td></tr><tr v-if="!filteredDocuments.length"><td colspan="11" class="p-10 text-center text-slate-500">{{ extraLoading ? '正在读取单据…' : '暂无符合条件的单据' }}</td></tr></tbody></table></div>
          </section>
          <div v-if="detailDocument" data-testid="supplier-document-detail-overlay" class="fixed inset-0 z-[64] flex items-center justify-center p-4" :class="detailDocumentPinned ? 'pointer-events-auto bg-slate-950/45' : 'pointer-events-none bg-slate-950/25'" @click.self="closeDocumentDetail">
            <div ref="documentDetailDialog" role="dialog" aria-labelledby="supplier-document-title" :aria-modal="detailDocumentPinned ? 'true' : undefined" :inert="detailDocumentPinned ? undefined : true" class="flex max-h-[88vh] w-full max-w-5xl flex-col rounded-2xl bg-white shadow-2xl" @keydown="trapDialogTab">
              <div class="flex justify-between border-b border-slate-200 p-5"><div><h2 id="supplier-document-title" class="text-lg font-bold">{{ detailDocument.kind === 'PURCHASE' ? (detailDocument.is_batch ? '合并采购单' : '采购单') : '送货单' }} · {{ detailDocument.document_no }}</h2><p class="mt-1 text-xs text-slate-500">{{ factoryDisplayName(detailDocument.factory_id) }} · {{ detailDocument.date }} · {{ detailDocument.orders.length }} 张订单<span v-if="detailDocument.unmatched_line_count"> · {{ detailDocument.unmatched_line_count }} 条无单明细</span></p><p v-if="detailDocument.source_filename" class="mt-1 text-xs text-slate-500">原送货文件：{{ detailDocument.source_filename }}</p><p class="mt-1 text-xs text-teal-700">{{ detailDocumentPinned ? '已固定显示 · 可滚动查看单据' : '悬停预览 · 单击明细可固定查看' }}</p></div><button v-if="detailDocumentPinned" type="button" aria-label="关闭单据明细" @click="closeDocumentDetail"><X class="size-4" /></button></div>
              <div class="min-h-0 overflow-auto p-5 carton-table-wrap"><div v-for="order in detailDocument.orders" :key="order.order_no" class="mb-2 rounded-lg border border-slate-200 p-3 text-xs"><b>{{ order.customer_name }} · {{ order.contract_no }} · {{ order.item_no }}</b><span class="ml-2 text-slate-500">PO {{ order.customer_po || '纸箱订单未填写' }} · 订单 {{ order.order_no }}</span><span v-if="order.product_name" class="ml-2 text-slate-500">{{ order.product_name }}</span></div><table class="w-full min-w-[720px] text-left text-xs carton-table-fit"><thead class="bg-slate-50"><tr><th class="p-2">订单 / 纸品</th><th class="p-2">纸品类型</th><th class="p-2">纸质 / 规格</th><th class="p-2">{{ detailDocument.kind === 'PURCHASE' ? '变更前 / 本次变化 / 变更后' : '发货 / 到货 / 拒收 / 入库' }}</th></tr></thead><tbody><tr v-for="(line, index) in detailDocument.lines" :key="`${line.order_no}|${line.child_no}|${index}`" class="border-t border-slate-100"><td data-label="订单 / 纸品" class="p-2">{{ line.child_no || `无单纸品 · ${line.contract_no || '无合同号'} / ${line.item_no || '无货号'}` }}<span v-if="line.source_document_no" class="mt-1 block text-slate-500">原采购单 {{ line.source_document_no }}</span></td><td data-label="纸品类型" class="p-2">{{ line.packaging_type }}</td><td data-label="纸质 / 规格" class="p-2">{{ line.paper_quality }} · {{ line.specification }}</td><td :data-label="detailDocument.kind === 'PURCHASE' ? '变更前 / 本次变化 / 变更后' : '发货 / 到货 / 拒收 / 入库'" class="p-2">{{ detailDocument.kind === 'PURCHASE' ? `${line.before_quantity} / ${line.change_quantity} / ${line.quantity}` : `${line.quantity} / ${line.received_quantity || 0} / ${line.rejected_quantity || 0} / ${line.effective_quantity ?? '待核实'}` }} {{ line.unit }}</td></tr></tbody></table></div>
              <p v-if="detailDocumentPinned && detailDocumentError" role="alert" class="mx-5 mb-3 shrink-0 rounded-lg bg-red-50 p-3 text-xs text-red-700">{{ detailDocumentError }}</p>
              <div v-if="detailDocumentPinned" class="flex shrink-0 justify-end gap-2 border-t border-slate-200 p-4"><button v-if="detailDocument.kind === 'DELIVERY'" type="button" class="h-9 rounded-lg border border-teal-300 bg-teal-50 px-4 text-xs font-bold text-teal-800" @click="printDeliveryNote(detailDocument)">打印送货单</button><button type="button" :disabled="busy" class="h-9 rounded-lg bg-teal-700 px-4 text-xs font-bold text-white disabled:opacity-40" @click="exportDocument(detailDocument)">导出这张{{ detailDocument.kind === 'PURCHASE' ? '采购单' : '送货单' }}</button></div>
            </div>
          </div>
          <div v-if="mergedDocumentsOpen && selectedDocuments.length" class="fixed inset-0 z-[65] flex items-center justify-center bg-slate-950/45 p-4" @click.self="closeMergedDocuments">
            <div ref="mergedDocumentsDialog" role="dialog" aria-modal="true" aria-labelledby="supplier-merged-document-title" class="flex max-h-[88vh] w-full max-w-6xl flex-col rounded-2xl bg-white shadow-2xl" @keydown="trapDialogTab">
              <div class="flex shrink-0 items-start justify-between gap-3 border-b border-slate-200 p-5"><div><h2 id="supplier-merged-document-title" class="text-lg font-bold">合并预览 · {{ selectedDocuments.length }} 张单据 / {{ mergedDocumentOrders.length }} 张订单<span v-if="mergedUnmatchedLines.length"> / {{ mergedUnmatchedLines.length }} 条无单纸品</span></h2><p class="mt-1 text-xs text-slate-500">按厂区和订单汇总；同一订单涉及多张单据时，纸品行按原单据分别列示，数量不重复相加。</p></div><button type="button" aria-label="关闭合并预览" @click="closeMergedDocuments"><X class="size-4" /></button></div>
              <div class="min-h-0 space-y-4 overflow-auto p-5"><section v-for="(entry, index) in mergedUnmatchedLines" :key="`${documentKey(entry.document)}-unmatched-${index}`" class="rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs"><b>无单纸品 · {{ factoryDisplayName(entry.document.factory_id) }} · 送货单 {{ entry.document.document_no }}</b><p class="mt-1">客户单号 {{ entry.line.contract_no || '未填写' }} · 客户料号 {{ entry.line.item_no || '未填写' }} · {{ entry.line.packaging_type }} · {{ entry.line.paper_quality }} / {{ entry.line.specification }} · 发货 {{ entry.line.quantity }} {{ entry.line.unit }} · 到货 {{ entry.line.received_quantity || 0 }} · 拒收 {{ entry.line.rejected_quantity || 0 }} · 实际入库 {{ entry.line.effective_quantity ?? '待核实' }}</p><p class="mt-1 text-amber-800">{{ entry.document.status === 'SENT' ? '仓库待核实是否确需无单入库' : '仓库处理记录已保留在送货单中' }}</p></section><section v-for="group in mergedDocumentOrders" :key="`${group.factory_id}|${group.order.order_no}`" class="rounded-xl border border-slate-200"><div class="border-b border-slate-100 bg-slate-50 px-4 py-3 text-xs"><b>{{ factoryDisplayName(group.factory_id) }} · {{ group.order.customer_name }} · 合同 {{ group.order.contract_no }} · 货号 {{ group.order.item_no }}</b><p class="mt-1 text-slate-500">客户 PO {{ group.order.customer_po || '纸箱订单未填写' }} · 订单 {{ group.order.order_no }} · {{ group.sources.length }} 张关联单据</p></div><div v-for="source in group.sources" :key="documentKey(source.document)" class="border-t border-slate-100 px-4 py-3 text-xs"><p class="font-bold text-teal-800">{{ source.document.kind === 'PURCHASE' ? '采购单' : '送货单' }} {{ source.document.document_no }} · {{ source.document.date }}</p><div v-for="(line, index) in source.lines" :key="`${line.child_no}|${index}`" class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-slate-600"><span>{{ line.child_no }} · {{ line.packaging_type }} · {{ line.paper_quality }} / {{ line.specification }}</span><span>{{ source.document.kind === 'PURCHASE' ? `变更前 ${line.before_quantity} · 本次变化 ${line.change_quantity} · 变更后 ${line.quantity}` : `发货 ${line.quantity} · 到货 ${line.received_quantity || 0} · 拒收 ${line.rejected_quantity || 0} · 实际入库 ${line.effective_quantity ?? '待核实'}` }} {{ line.unit }}</span></div></div></section></div>
              <div class="flex shrink-0 justify-end gap-2 border-t border-slate-200 p-4"><button type="button" class="h-9 rounded-lg border border-slate-200 px-4 text-xs font-bold" @click="closeMergedDocuments">关闭</button><button type="button" :disabled="busy" class="h-9 rounded-lg bg-teal-700 px-4 text-xs font-bold text-white disabled:opacity-40" @click="exportSelectedDocuments">导出所选 {{ selectedDocuments.length }} 张 Excel</button></div>
            </div>
          </div>
        </template>

        <template v-else-if="activeTab === 'activity'">
          <section class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"><div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 p-4"><div><h2 class="text-base font-bold">操作日志</h2><p class="mt-1 text-xs text-slate-500">显示本供应商可见订单的采购生成、接单、送货与仓库反馈。</p></div><div class="flex gap-2"><select v-model="activityFactory" aria-label="操作日志厂区筛选" class="h-9 rounded-lg border border-slate-200 px-2 text-xs"><option value="">全部厂区</option><option v-for="item in memberships" :key="item.factory_id" :value="item.factory_id">{{ factoryDisplayName(item.factory_id) }}</option></select></div></div><CartonFilterBar label="供应商日志筛选" >
<label>操作类型<select v-model="activityEvent" aria-label="供应商日志操作类型" class="ml-2 h-9 rounded-lg border px-2"><option value="">全部类型</option><option v-for="(label, code) in activityTypes" :key="code" :value="code">{{ label }}</option></select></label>
<label>操作日期从<input v-model="activityFrom" type="date" aria-label="供应商日志起始日期" class="ml-2 h-9 rounded-lg border px-2"></label>
<label>至<input v-model="activityTo" type="date" aria-label="供应商日志结束日期" class="ml-2 h-9 rounded-lg border px-2"></label>
<label >排序<select v-model="activitySort" aria-label="供应商日志排序" class="h-9 rounded-lg border px-2"><option value="DESC">最新操作优先</option><option value="ASC">最早操作优先</option></select></label>

<template #actions><button type="button" class="h-9 rounded-lg border px-3" @click="activitySearch = ''; activityFactory = ''; activityEvent = ''; activityFrom = ''; activityTo = ''">清除筛选</button>
<button type="button" class="h-9 rounded-lg border px-3" @click="activitySort = 'DESC'">恢复默认排序</button>
<button type="button" class="h-9 rounded-lg border px-3" :disabled="extraLoading" @click="loadActivity">刷新</button></template>
<template #footer><span>共 {{ activityTotal }} 条</span></template>
</CartonFilterBar><div class="overflow-x-auto carton-table-wrap"><table class="w-full min-w-[700px] text-left text-xs carton-table-fit"><thead class="bg-slate-50 text-slate-600"><tr><th class="p-3">时间</th><th class="p-3">厂区</th><th class="p-3">操作</th><th class="p-3">单据 / 订单</th><th class="p-3">操作人</th></tr></thead><tbody class="divide-y divide-slate-100"><tr v-for="row in filteredActivity" :key="row.id"><td data-label="时间" class="p-3">{{ row.created_at }}</td><td data-label="厂区" class="p-3">{{ factoryDisplayName(row.factory_id) }}</td><td data-label="操作" class="p-3 font-semibold">{{ row.action }}</td><td data-label="单据 / 订单" class="p-3">{{ row.reference_no }}</td><td data-label="操作人" class="p-3">{{ row.actor_name }}</td></tr><tr v-if="!filteredActivity.length"><td colspan="5" class="p-10 text-center text-slate-500">{{ extraLoading ? '正在读取操作日志…' : '暂无相关操作记录' }}</td></tr></tbody></table></div><div class="flex items-center justify-end gap-3 border-t p-3 text-xs"><button type="button" :disabled="extraLoading || activityPage <= 1" class="rounded-lg border px-3 py-2 disabled:opacity-40" @click="activityPage--">上一页</button><span>第 {{ activityPage }} / {{ Math.max(1, Math.ceil(activityTotal / 50)) }} 页</span><button type="button" :disabled="extraLoading || activityPage * 50 >= activityTotal" class="rounded-lg border px-3 py-2 disabled:opacity-40" @click="activityPage++">下一页</button></div></section>
        </template>
      </section>
    </div>
    <CartonPriceCorrectionDialog v-if="priceCorrectionOpen" v-model:open="priceCorrectionOpen" :factory-id="priceCorrectionFactory" :factories="serviceFactories" :receipt-line-id="priceCorrectionLineId" :viewer-key="importContext" @changed="load()" />
  </main>
</template>

<style scoped>
.supplier-order-table { width: 100%; table-layout: fixed; }
.supplier-order-table th, .supplier-order-table :deep(td) { padding: 12px 8px; vertical-align: top; overflow-wrap: anywhere; }
.supplier-order-table th:first-child, .supplier-order-table :deep(td:first-child) { padding-left: 12px; }
.supplier-order-actions { text-align: right; }
.supplier-order-table :deep(summary) { white-space: normal; }
@media (max-width: 1023px) {
  .supplier-order-table, .supplier-order-table tbody { display: block; }
  .supplier-order-table colgroup, .supplier-order-table thead { display: none; }
  .supplier-order-table :deep(tr) { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); padding: 8px; }
  .supplier-order-table :deep(td) { display: block; min-width: 0; padding: 8px; }
  .supplier-order-table :deep(td[data-label]::before) { content: attr(data-label); display: block; color: #64748b; font-size: 11px; margin-bottom: 5px; }
  .supplier-order-table :deep(td:first-child), .supplier-order-table :deep(td:last-child) { grid-column: 1 / -1; }
  .supplier-order-table :deep(td:first-child) { display: flex; align-items: center; gap: 8px; }
  .supplier-order-table :deep(td:first-child::before) { margin-bottom: 0; }
}
</style>
