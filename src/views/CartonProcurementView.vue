<script setup lang="ts">
import CartonOpeningInventoryImport from '@/components/CartonOpeningInventoryImport.vue'
import CartonHistoryImportDialog from '@/components/CartonHistoryImportDialog.vue'
import CartonBusinessImportSummary from '@/components/CartonBusinessImportSummary.vue'
import CartonSupplierSettlement from '@/components/CartonSupplierSettlement.vue'
import { estimateMoney, moneyLabel, unitCostLabel, moneyTotals, type InventoryMoney } from '@/lib/cartonInventoryMoney'
import CartonPaperPicker from '@/components/CartonPaperPicker.vue'
import CartonMasterWorkspace from '@/components/CartonMasterWorkspace.vue'
import CartonMasterOrderAssist from '@/components/CartonMasterOrderAssist.vue'
import CartonNumberRuleHint from '@/components/CartonNumberRuleHint.vue'
import CartonMasterLookup from '@/components/CartonMasterLookup.vue'
import CartonCustomerPicker from '@/components/CartonCustomerPicker.vue'
import { cartonMasterApi, emptyMaster, masterDueRules, masterPaperOptions, type MasterRecord } from '@/api/cartonMaster'

import CartonLocationPicker from '@/components/CartonLocationPicker.vue'
import CartonReceiptAllocations from '@/components/CartonReceiptAllocations.vue'
import CartonReceiptPaperSelection from '@/components/CartonReceiptPaperSelection.vue'
import { cartonPositionsApi, type CartonLocation, type LocationAllocation } from '@/api/cartonPositions'

import { computed, nextTick, onBeforeUnmount, reactive, ref, shallowRef, watch, type Component } from 'vue'
import {
  AlertTriangle,
  ArrowLeft,
  Boxes,
  Building2,
  CalendarClock,
  CheckCircle2,
  ClipboardCheck,
  Download,
  FileSpreadsheet,
  GitBranch,
  LayoutDashboard,
  Minus,
  PackageCheck,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Send,
  ShieldCheck,
  Truck,
  Trash2,
  Upload,
  Users,
  X,
} from '@lucide/vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import {
  DialogRoot, DialogOverlay, DialogContent, DialogTitle, DialogDescription, DialogClose,
  PopoverRoot, PopoverTrigger, PopoverPortal, PopoverContent,
  type DateRange,
} from 'reka-ui'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import DateRangeFilter from '@/components/DateRangeFilter.vue'
import CartonStocktakeWorkspace from '@/components/CartonStocktakeWorkspace.vue'
import CartonSelectionSummary from '@/components/CartonSelectionSummary.vue'
import CartonInventoryProgress from '@/components/CartonInventoryProgress.vue'
import CartonInventorySummary from '@/components/CartonInventorySummary.vue'
import CartonReceiptDetail from '@/components/CartonReceiptDetail.vue'
import {
  cartonProcurementApi,
  type CartonAuditEventResponse,
  type CartonClosingResponse,
  type CartonPricingIssue,
  type CartonCustomerResponse,
  type CartonCustomerSaveRequest,
  type CartonExceptionResponse,
  type CartonImportBatchResponse,
  type CartonImportPreviewRow,
  type CartonInventoryBalanceResponse,
  type CartonInventoryMovementResponse,
  type CartonOrderHistorySuggestionResponse,
  type CartonOrderResponse,
  type CartonPurchaseOrderContextResponse,
  type CartonPurchaseOrderIssueResponse,
  type CartonReceiptResponse,
} from '@/api/cartonProcurement'
import {
  factoryContexts,
  getFactoryScopedRoute,
  isProductionFactoryContextId,
  type ProductionFactoryContextId,
} from '@/data/enterpriseMock'
import {
  cartonClosings as cartonClosingDemo,
  cartonCustomers,
  cartonExceptions,
  cartonOrders,
  inventoryMovements as inventoryMovementDemo,
  receiptSeed,
  weeklyChecks,
  type CartonMaterialLine,
  type CartonExceptionRow,
  type InventoryMovementRow,
  type CartonOrderRow,
  type CartonTone,
  type InspectionReminderRow,
  type ReceiptLineSeed,
  type WeeklyCheckRow,
} from '@/features/carton-procurement/demoData'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage, getApiErrorMessageAsync } from '@/lib/http'

type CartonTab = 'dashboard' | 'orders' | 'weekly-check' | 'receipts' | 'inventory' | 'inventory-movements' | 'inventory-summary' | 'master-data' | 'closing' | 'exceptions' | 'audit'
const DEFAULT_CARTON_SAFETY_LEAD_DAYS = 3

interface CartonTabItem {
  id: CartonTab
  label: string
  shortLabel: string
  icon: Component
}

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const authStore = useAuthStore()

const tabs: CartonTabItem[] = [
  { id: 'dashboard', label: '工作看板', shortLabel: '工作看板', icon: LayoutDashboard },
  { id: 'orders', label: '订单管理', shortLabel: '订单管理', icon: ClipboardCheck },
  { id: 'receipts', label: '收料入库', shortLabel: '收料入库', icon: PackageCheck },
  { id: 'inventory', label: '库存管理', shortLabel: '库存管理', icon: Boxes },
  { id: 'exceptions', label: '异常处理', shortLabel: '异常处理', icon: AlertTriangle },
  { id: 'closing', label: '月结对账', shortLabel: '月结对账', icon: FileSpreadsheet },
  { id: 'master-data', label: '基础资料', shortLabel: '基础资料', icon: Users },
  { id: 'audit', label: '操作日志', shortLabel: '操作日志', icon: GitBranch },
]
const subPages: CartonTabItem[] = [
  { id: 'weekly-check', label: '排期核对与交期提醒', shortLabel: '排期核对', icon: CalendarClock },
  { id: 'inventory-summary', label: '收发汇总', shortLabel: '收发汇总', icon: FileSpreadsheet },
  { id: 'inventory-movements', label: '库存流水', shortLabel: '库存流水', icon: GitBranch },
]

const validTabs = new Set<CartonTab>([...tabs, ...subPages].map((tab) => tab.id))
const selectedCustomer = ref('全部客户')
const weeklyOnlyAttention = ref(false), weeklyHistoryExpanded = ref(false), weeklyHistorySearch = ref('')
const closingView = ref(route.query.closing_view === 'inventory' ? 'INVENTORY' : 'SUPPLIER')
const closingQueryPeriod = ref(''), closingStatusFilter = ref('ALL')
let closingGeneration = 0
const exceptionStatusFilter = ref('OPEN'), exceptionTypeFilter = ref('ALL')
const showSharedSearch = computed(() => !['master-data', 'audit'].includes(activeTab.value) && !(activeTab.value === 'closing' && closingView.value === 'SUPPLIER') && !(activeTab.value === 'inventory' && showStocktake.value) && !(activeTab.value === 'receipts' && receiptPage.value === 'IMPORT'))
function clearOrderFilters() {
  selectedCustomer.value = '全部客户'; globalSearch.value = ''; orderStatusFilter.value = 'ALL'; orderDueFilter.value = 'ALL'
  orderDateRange.value = { start: undefined, end: undefined }
}
function clearMovementFilters() {
  selectedCustomer.value = '全部客户'; globalSearch.value = ''; inventoryMovementFilter.value = 'ALL'
  inventoryMovementDateRange.value = { start: undefined, end: undefined }
}
function clearWeeklyFilters() { selectedCustomer.value = '全部客户'; globalSearch.value = ''; weeklyOnlyAttention.value = false; weeklyHistorySearch.value = '' }

const globalSearch = ref('')
const actionMessage = ref('正在读取纸箱采购台账…')
const apiConnected = ref(false)
const backendLoading = ref(false)
let backendLoadGeneration = 0, backendLoadFactory = ''
const savingOrder = ref(false)
const exportingOrderNo = ref('')
const exportingSelectedOrders = ref(false)
const issuingSelectedPurchaseOrders = ref(false)
const purchaseBatchConfirmation = ref('')
let resolvePurchaseBatchConfirmation: ((confirmed: boolean) => void) | undefined
let purchaseBatchActive = true
function closePurchaseBatchConfirmation(confirmed = false) {
  const resolve = resolvePurchaseBatchConfirmation
  resolvePurchaseBatchConfirmation = undefined
  purchaseBatchConfirmation.value = ''
  resolve?.(confirmed)
}
function confirmPurchaseBatch(message: string) {
  purchaseBatchConfirmation.value = message
  return new Promise<boolean>(resolve => { resolvePurchaseBatchConfirmation = resolve })
}
onBeforeUnmount(() => {
  closingGeneration++; purchaseBatchActive = false; closePurchaseBatchConfirmation() })
const purchaseOrderDialogNo = ref('')
const purchaseOrderContextRecord = ref<CartonPurchaseOrderContextResponse | null>(null)
const loadingPurchaseOrderContext = ref(false)
const issuingPurchaseOrder = ref(false)
const downloadingPurchaseOrderIssueId = ref('')
const selectedOrderNos = ref<string[]>([])
const selectedExceptionNos = ref<string[]>([])
const bulkExceptionNote = ref('')
const deleteHistoryTarget = ref<CartonOrderResponse | null>(null)
const deleteHistoryTargets = ref<CartonOrderResponse[]>([])
const deleteHistoryReason = ref('历史订单导入有误')
const deletingHistory = ref(false)
const undoImportTarget = ref<CartonImportBatchResponse | null>(null)
const undoImportReason = ref('本次导入文件有误')
const undoingImport = ref(false)
const selectedWeeklyBatchId = ref('')
const selectedInspectionBatchId = ref('')
const replenishTarget = ref<CartonOrderResponse | null>(null)
const replenishResponsibility = ref<'' | 'OWN' | 'SUPPLIER'>('')
const replenishReason = ref('')
const replenishQuantities = ref<Record<string, number | string>>({})
const replenishing = ref(false)
const replenishError = ref('')
const orderDetailNo = ref('')
const orderDetailPinned = ref(false)
const openOrderMoreMenu = ref('')
const combinedPurchaseOrderMessage = ref('')
const combinedPurchaseOrderTone = ref<'progress' | 'success' | 'error'>('progress')
const orderStatusFilter = ref('ALL')
const orderDueFilter = ref<'ALL' | 'OVERDUE' | 'TODAY' | 'DUE_SOON' | 'UPCOMING'>('ALL')
const orderDateRange = shallowRef<DateRange>({ start: undefined, end: undefined })
const orderSort = ref<'DUE_ASC' | 'DUE_DESC' | 'ORDER_DESC'>('DUE_ASC')
const historyOrderFileInput = ref<HTMLInputElement | null>(null)
const importingHistoryOrders = ref(false)
const showOrderModal = ref(false)
const editingOrderNo = ref('')
const orderChangeReason = ref('')
const submitSupplierOrderNo = ref('')
const bulkSubmitSupplierOrderNos = ref<string[]>([])
const submittingSupplierOrder = ref(false)
const cancelOrderNo = ref('')
const cancelOrderReason = ref('')
const cancellingOrder = ref(false)
const appendOrderNo = ref('')
const appendOrderQuantity = ref(0)
const appendLineTargets = reactive<Record<string, number | ''>>({})
const reduceLineTargets = reactive<Record<string, number | ''>>({})
const DEFAULT_APPEND_ORDER_REASON = '客人追加订单'
const DEFAULT_REDUCE_ORDER_REASON = '客人退单'
const appendOrderReason = ref(DEFAULT_APPEND_ORDER_REASON)
const appendOrderCustomerDueDate = ref('')
const appendOrderDueDate = ref('')
const appendingOrder = ref(false)
const reduceOrderNo = ref('')
const reduceOrderQuantity = ref(0)
const reduceOrderReason = ref(DEFAULT_REDUCE_ORDER_REASON)
const reducingOrder = ref(false)
const showCustomerModal = ref(false)
const customerCreatedFromOrder = ref(false)
const customerEditError = ref('')
let customerEditGeneration = 0
const savingCustomer = ref(false)
const editingCustomerId = ref('')
const receiptFeedbackMessage = ref('')
const receiptFeedbackTone = ref<'error' | 'success'>('error')
const manualDeliveryNoteInput = ref<HTMLInputElement | null>(null)
const manualDeliveryDateInput = ref<HTMLInputElement | null>(null)
const manualAcceptanceDateInput = ref<HTMLInputElement | null>(null)
const receiptEntryMode = ref<'IMPORT' | 'MANUAL'>('MANUAL')
const receiptPage = ref<'PENDING' | 'IMPORT' | 'HISTORY'>('PENDING')
function openReceiptPage(page: typeof receiptPage.value) {
  receiptPage.value = page
  closeReceiptDetails()
}
const receiptOrderSort = ref<'DUE_ASC' | 'DUE_DESC' | 'DEFAULT'>('DUE_ASC')
const showReceiptDialog = ref(false)
const receiptDialogTrigger = ref<HTMLButtonElement | null>(null)
const manualReceiptOrderNos = ref<string[]>([])
const receiptContractKey = ref('')
const receiptDueCalendarValue = shallowRef<DateRange>({ start: undefined, end: undefined })
const receiptPlannedDueFrom = computed(() => receiptDueCalendarValue.value.start?.toString() ?? '')
const receiptPlannedDueTo = computed(() => receiptDueCalendarValue.value.end?.toString() ?? '')
const receiptFileInput = ref<HTMLInputElement | null>(null)
const selectedReceiptFileName = ref('')
const weeklyFileInput = ref<HTMLInputElement | null>(null)
const selectedWeeklyFileName = ref('')
const importingWeekly = ref(false)
const businessAlertStatusFilter = ref<'ACTIONABLE' | 'ALL'>('ACTIONABLE')
const businessAlertKindFilter = ref<'ALL' | 'MISSING_ORDER' | 'QUANTITY_INCREASE' | 'QUANTITY_DECREASE'>('ALL')
const weeklyCheckMode = ref<'ORDER_GAP' | 'INSPECTION_REMINDER'>('ORDER_GAP')
const inspectionFileInput = ref<HTMLInputElement | null>(null)
const selectedInspectionFileName = ref('')
const inspectionAdvanceDays = ref(3)
const importingInspection = ref(false)
const importingReceipt = ref(false)
const deletingReceiptImport = ref(false)
const savingReceipt = ref(false)
const confirmingReceipt = ref(false)
const receiptBatchId = ref('')
const receiptImportBatch = ref<CartonImportBatchResponse | null>(null)
const receiptImportRows = ref<CartonImportPreviewRow[]>([])
const receiptDeliveryNoteNo = ref('DN26061301')
const receiptDeliveryDate = ref(businessTodayIso())
const receiptAcceptanceDate = ref(businessTodayIso())
const currentReceipt = ref<CartonReceiptResponse | null>(null)
const receiptRecords = ref<CartonReceiptResponse[]>([])
const weeklyImportHistory = ref<CartonImportBatchResponse[]>([])
const inspectionImportHistory = ref<CartonImportBatchResponse[]>([])
const showInventoryImport = ref(false)
const showStocktake = ref(false)
const showInventoryOperation = ref(false)
const showInventoryRelocation = ref(false)
const relocationTarget = shallowRef<InventoryBalanceRow | null>(null)
const relocationLocation = ref('')
const relocationQuantity = ref(0)
const inventoryLocations = ref<CartonLocation[]>([])
const warehouseFilter = ref(''), locationFilter = ref(''), showLocationManager = ref(false), newLocationSelection = ref('')
const masterWorkspace = ref(emptyMaster())
const masterSection = ref('SETTINGS')
function openMaster(section: string) { masterSection.value = section; setActiveTab('master-data') }
const masterLoaded = ref(false), masterError = ref('')
const chosenMaster = ref<MasterRecord | null>(null)
const outboundWorkshop = ref(''), bulkWorkshops = ref<Record<string, string>>({})
const workshops = computed(() => masterWorkspace.value.records.filter(r => r.kind === 'WORKSHOP' && r.status === 'ACTIVE'))
let masterGeneration = 0
async function refreshMaster() {
  const generation = ++masterGeneration
  const factory = selectedFactoryId.value
  try {
    const data = await cartonMasterApi.get(factory)
    if (factory !== selectedFactoryId.value || generation !== masterGeneration) return
    masterWorkspace.value = data; masterLoaded.value = true; masterError.value = ''
  } catch (e) { if (factory === selectedFactoryId.value && generation === masterGeneration) { masterLoaded.value = false; masterError.value = getApiErrorMessage(e) } }
}
async function masterChanged() { await refreshMaster(); await refreshLocations() }
function applyMaster(row: MasterRecord) {
  if (editingOrderStructureLocked.value) return
  orderForm.itemNo = row.code; orderForm.productName = row.data.product_name || ''
  orderForm.materials.splice(0, orderForm.materials.length, ...(row.data.lines || []).map((l, i) => ({
    id: `MASTER-${row.id}-${i}`, packagingType: l.packaging_type, paperQuality: l.paper_quality,
    specification: l.specification, dimensionUnit: l.dimension_unit, unit: l.unit,
    unitsPerCarton: Number(l.usage_quantity), unitPrice: 0, currency: 'CNY', priceSource: 'manual', note: '',
  })))
  chosenMaster.value = row
}
function orderFromMaster(row: MasterRecord) { resetOrderForm(); showOrderModal.value = true; applyMaster(row) }
const outboundKind = ref('USAGE')
const outboundKinds = [{ id: 'USAGE', label: '正常领用／发货' }, { id: 'RETURN', label: '退供应商' }, { id: 'LOSS', label: '损耗／报损' }, { id: 'LOAN', label: '借出' }, { id: 'OTHER', label: '其他用途' }]
async function refreshLocations() {
  const factory = selectedFactoryId.value
  const rows = await cartonPositionsApi.locations(factory)
  if (factory === selectedFactoryId.value) inventoryLocations.value = rows
}
function usageLabel(orderNo: string) { return orderRecords.value.find(row => row.order_no === orderNo)?.usage_status_label || '未入库' }

const relocationNote = ref('')
const relocationBusy = ref(false)
const relocationFeedback = ref('')
const inventoryBulkMode = ref(false)
const inventoryBulkQuantities = ref<Record<string, string | number>>({})
const inventoryDialogTrigger = shallowRef<HTMLElement | null>(null)
const inventoryOperationType = ref<'OUTBOUND' | 'ADJUSTMENT'>('OUTBOUND')
const inventoryTargetId = ref('')
const inventoryOperationQuantity = ref(0)
const inventoryOperationLocation = ref('')
const inventoryOperationDocumentNo = ref('')
const inventoryOutboundReasons = computed(() => ({ USAGE: ['客户要货', '补货', '生产领用'], RETURN: ['退供应商'], LOSS: ['损耗', '报损'], LOAN: ['借出'], OTHER: ['其他'] }[outboundKind.value] ?? ['其他']))
watch(outboundKind, () => { inventoryOperationReason.value = outboundKind.value === 'OTHER' ? '' : inventoryOutboundReasons.value[0] ?? '' })
const inventoryOperationReason = ref('客户要货')
const selectedInventoryTargetIds = ref<string[]>([])
const inventoryBalanceDateRange = shallowRef<DateRange>({ start: undefined, end: undefined })
const inventoryBalanceDateFrom = computed(() => inventoryBalanceDateRange.value.start?.toString() ?? '')
const inventoryBalanceDateTo = computed(() => inventoryBalanceDateRange.value.end?.toString() ?? '')
const inventoryMovementFilter = ref<'ALL' | 'INBOUND' | 'OUTBOUND' | 'ADJUSTMENT' | 'REVERSAL'>('ALL')
const inventoryMovementDateRange = shallowRef<DateRange>({ start: undefined, end: undefined })
const inventoryDateFrom = computed(() => inventoryMovementDateRange.value.start?.toString() ?? '')
const inventoryDateTo = computed(() => inventoryMovementDateRange.value.end?.toString() ?? '')
const inventoryOperationBusy = ref(false)
const inventoryOperationFeedback = ref('')
const receiptHistoryStatus = ref('ALL')
const receiptHistoryDateRange = shallowRef<DateRange>({ start: undefined, end: undefined })
const receiptDetailTarget = ref<CartonReceiptResponse | null>(null)
const receiptDetailPinned = ref(false)
const receiptCorrectionTarget = ref<CartonReceiptResponse | null>(null)
const receiptCorrectionReason = ref('')
const receiptCorrectionError = ref('')
const receiptCorrectionBusy = ref(false)
const receiptCorrectionNote = ref('')
const canCorrectReceipt = computed(() => apiConnected.value
  && authStore.can('carton_procurement:receipt_write') && authStore.can('carton_procurement:inventory_write'))
const reversingMovementId = ref('')
const reversalReason = ref('')
const reversalBusy = ref(false)
const closingPeriod = ref(new Date(new Date().getFullYear(), new Date().getMonth() - 1, 1).toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' }).slice(0, 7))
const closingBusyId = ref('')
const closingDecision = ref<{ closing: CartonClosingResponse; action: 'LOCK' | 'UNLOCK' } | null>(null)
const closingDecisionReason = ref('')
const closingDecisionError = ref('')
const canFinalizeClosing = computed(() => apiConnected.value && authStore.can('carton_procurement:closing_manage')
  && authStore.can('carton_procurement:order_adjust'))
const exceptionBusyId = ref('')
const inventoryReportRefreshKey = ref(0)
const auditRecords = ref<CartonAuditEventResponse[]>([])
const auditSearch = ref('')
const auditEventFilter = ref('ALL')
const auditActorFilter = ref('ALL')
const auditDateFrom = ref('')
const auditDateTo = ref('')
const autoFilledProductName = ref('')
const historyItemSuggestions = ref<CartonOrderHistorySuggestionResponse[]>([])
const historyItemSuggestionsLoading = ref(false)
const showHistoryItemSuggestions = ref(false)
const selectedHistoryItemSource = ref<CartonOrderHistorySuggestionResponse | null>(null)
let historyItemSearchTimer: ReturnType<typeof setTimeout> | null = null
let historyItemSearchGeneration = 0
let skipHistoryItemSearchFor = ''
const resolutionNotes = reactive<Record<string, string>>({})
const localOrders = reactive<CartonOrderRow[]>(cartonOrders.map((row) => ({
  ...row,
  materials: row.materials.map((material) => ({ ...material })),
})))
type InventoryMovementViewRow = InventoryMovementRow & {
  sourceType?: string
  money?: InventoryMoney
  rawMovementType?: CartonInventoryMovementResponse['movement_type']
  reversalOfMovementId?: string | null
}

const localMovements = reactive<InventoryMovementViewRow[]>(inventoryMovementDemo.map((row) => ({ ...row })))
interface InventoryBalanceRow {
  money?: InventoryMoney & Partial<CartonInventoryBalanceResponse>
  locationId?: string
  warehouse?: string
  positionRevision?: number
  id: string
  customer: string
  poNumber: string
  itemNo: string
  packagingType: string
  paperQuality: string
  specification: string
  unit: string
  orderLineId: string | null
  latestMovementId: string
  latestDocumentNo: string
  inboundDate: string
  locationRevision: number
  balance: number
  location: string
  date: string
}

const localInventoryBalances = reactive<InventoryBalanceRow[]>(inventoryMovementDemo.map((row) => ({
  id: `${row.customer}|${row.poNumber}|${row.itemNo}|${row.packagingType}|${row.paperQuality}|${row.specification}`,
  customer: row.customer,
  poNumber: row.poNumber,
  itemNo: row.itemNo,
  packagingType: row.packagingType,
  paperQuality: row.paperQuality,
  specification: row.specification,
  unit: '',
  orderLineId: null,
  latestMovementId: row.id,
  latestDocumentNo: row.documentNo,
  inboundDate: row.movementType === '入库' ? row.date : '',
  locationRevision: 0,
  balance: row.balance,
  location: row.location,
  date: row.date,
})))
const localClosings = reactive(cartonClosingDemo.map((row) => ({ ...row })))
const localWeeklyChecks = reactive<WeeklyCheckRow[]>(weeklyChecks.map((row) => ({ ...row })))
const localInspectionChecks = reactive<InspectionReminderRow[]>([])
const localExceptions = reactive<CartonExceptionRow[]>(cartonExceptions.map((row) => ({ ...row })))
const closingRecords = ref<CartonClosingResponse[]>([])
const exceptionRecords = ref<CartonExceptionResponse[]>([])
const customerRecords = ref<CartonCustomerResponse[]>([])
const orderRecords = ref<CartonOrderResponse[]>([])
const inventoryOrderLines = computed(() => new Map(orderRecords.value.flatMap(order => order.lines.map(line => [line.id, line] as const))))

interface ReceiptReviewLine extends ReceiptLineSeed {
  selectedForReceipt?: boolean
  replenishmentIssueId?: string
  replacementResponsibility?: string
  replacementDocumentNo?: string
  allocations?: LocationAllocation[]
  sourceType: 'FORMAL_ORDER' | 'AD_HOC'
  orderLineId: string
  customerCode: string
  contractNo: string
  itemNo: string
  packagingType: string
  paperQuality: string
  unit: string
  currency: string
  location: string
  sourceLabel: string
  remainingQuantity: number
}

const receiptLines = reactive<ReceiptReviewLine[]>(receiptSeed.map((line) => ({
  ...line,
  sourceType: 'FORMAL_ORDER',
  orderLineId: '',
  customerCode: '',
  contractNo: '',
  itemNo: '',
  packagingType: '',
  paperQuality: '',
  unit: '个',
  currency: 'CNY',
  location: '',
  sourceLabel: '只读演示',
  remainingQuantity: 0,
})))

interface OrderFormMaterialLine extends Omit<CartonMaterialLine, 'id' | 'unitsPerCarton'> {
  unitsPerCarton: number | ''
  requiredQuantity?: number | ''
  id: string
  dimensionUnit: string
  unitPrice: number
  currency: string
  priceSource: string
  note: string
}

const historyImportFile = ref<File | null>(null)
function customerPoForOrder(orderNo: string) {
  return orderRecords.value.find(order => order.order_no === orderNo)?.customer_po || ''
}
function customerPoForLine(lineId: string) {
  return orderRecords.value.find(order => order.lines.some(line => line.id === lineId))?.customer_po || ''
}
const orderForm = reactive({
  customerPo: '',
  quantityBasis: 'CALCULATED' as 'CALCULATED' | 'EXPLICIT',
  customerCode: '',
  supplierId: '',
  contractNo: '',
  itemNo: '',
  productName: '',
  orderQuantity: 0 as number | '',
  orderDate: new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' }),
  customerDueDate: '',
  dueDate: '2026-08-12',
  note: '',
  materials: [
    {
      id: 'FORM-MAT-1',
      packagingType: '',
      paperQuality: '',
      specification: '',
      unitsPerCarton: 120,
      unit: '个',
      dimensionUnit: '',
      unitPrice: 0,
      currency: 'CNY',
      priceSource: 'manual',
      note: '',
    },
  ] as OrderFormMaterialLine[],
})

const customerForm = reactive<CartonCustomerSaveRequest>({
  factory_id: '',
  customer_code: '',
  customer_name: '',
  country_region: '',
  contact_name: '',
  contact_phone: '',
  note: '',
  status: 'ACTIVE',
})

function demoCustomers(factoryId: string): CartonCustomerResponse[] {
  return cartonCustomers.filter((name) => name !== '全部客户').map((name) => ({
    id: `DEMO-${factoryId}-${name}`,
    factory_id: factoryId,
    customer_code: ({ Dickie: 'DICKIE', '360': '360', 施信: 'SHIXIN', BuzzBee: 'BUZZBEE' } as Record<string, string>)[name] ?? name.toUpperCase(),
    customer_name: name,
    country_region: '',
    contact_name: '',
    contact_phone: '',
    note: '只读演示客户',
    status: 'ACTIVE',
    revision: 1,
    created_by: 'demo',
    created_by_name: '演示数据',
    updated_by: 'demo',
    updated_by_name: '演示数据',
    created_at: '',
    updated_at: '',
  }))
}

const selectedFactoryId = computed<ProductionFactoryContextId>(() => {
  const routeFactory = route.query.factory
  if (typeof routeFactory === 'string' && isProductionFactoryContextId(routeFactory)) {
    return routeFactory
  }

  return isProductionFactoryContextId(appStore.activeProductionFactory.id)
    ? appStore.activeProductionFactory.id
    : 'huaxing'
})

const activeFactory = computed(() =>
  factoryContexts.find((factory) => factory.id === selectedFactoryId.value)
  ?? factoryContexts.find((factory) => factory.id === 'huaxing')!,
)
const canIssuePurchaseOrders = computed(() =>
  authStore.can('carton_procurement:order_write', selectedFactoryId.value, 'carton')
  || authStore.can('carton_procurement:order_write', selectedFactoryId.value, 'pmc-warehouse'),
)
const canWriteCartonInventory = computed(() =>
  authStore.can('carton_procurement:inventory_write', selectedFactoryId.value, 'carton')
  || authStore.can('carton_procurement:inventory_write', selectedFactoryId.value, 'pmc-warehouse'),
)
const canAdjustSubmittedOrders = computed(() =>
  authStore.can('carton_procurement:order_adjust', selectedFactoryId.value, 'carton')
  || authStore.can('carton_procurement:order_adjust', selectedFactoryId.value, 'pmc-warehouse')
  || (canIssuePurchaseOrders.value && canWriteCartonInventory.value),
)
const canManageClosingPrices = computed(() =>
  authStore.can('carton_procurement:closing_manage', selectedFactoryId.value, 'carton')
  || authStore.can('carton_procurement:closing_manage', selectedFactoryId.value, 'pmc-warehouse'),
)
const pricingTarget = ref<CartonPricingIssue | null>(null)
const pricingAmount = ref('')
const pricingZeroConfirmed = ref(false)
const pricingReason = ref('')
const pricingFeedback = ref('')
const pricingBusy = ref(false)
const activeCustomers = computed(() => customerRecords.value.filter((customer) => customer.status === 'ACTIVE'))
const selectedOrderCustomer = computed(() =>
  activeCustomers.value.find((customer) => customer.customer_code === orderForm.customerCode) ?? null,
)
const editingOrderRecord = computed(() =>
  orderRecords.value.find((order) => order.order_no === editingOrderNo.value) ?? null,
)
const appendingOrderRecord = computed(() =>
  orderRecords.value.find((order) => order.order_no === appendOrderNo.value) ?? null,
)
const orderMasterRules = computed(() => masterDueRules(masterWorkspace.value.records, orderForm.customerCode))
const orderLeadDays = computed(() => editingOrderRecord.value?.safety_lead_days ?? orderMasterRules.value.lead_days)
const appendLeadDays = computed(() => appendingOrderRecord.value?.safety_lead_days ?? DEFAULT_CARTON_SAFETY_LEAD_DAYS)
const calculatedOrderDueDate = computed(() =>
  orderForm.customerDueDate && orderForm.quantityBasis !== 'EXPLICIT'
    ? derivePlanDueDate(orderForm.orderDate, orderForm.customerDueDate, orderLeadDays.value)
    : orderForm.dueDate,
)
const orderSafetyLeadWarning = computed(() =>
  safetyLeadWarning(orderForm.orderDate, orderForm.customerDueDate, orderLeadDays.value),
)
const calculatedAppendOrderDueDate = computed(() =>
  appendOrderCustomerDueDate.value && appendingOrderRecord.value && appendingOrderRecord.value.quantity_basis !== 'EXPLICIT'
    ? derivePlanDueDate(appendingOrderRecord.value.order_date, appendOrderCustomerDueDate.value, appendLeadDays.value)
    : appendOrderDueDate.value,
)
const appendSafetyLeadWarning = computed(() =>
  appendingOrderRecord.value?.quantity_basis === 'EXPLICIT' ? '' : safetyLeadWarning(
    appendingOrderRecord.value?.order_date ?? '',
    appendOrderCustomerDueDate.value, appendLeadDays.value,
  ),
)
const appendOrderGuidance = computed(() => {
  if (appendingOrderRecord.value?.status === 'COMPLETED') {
    return '该订单已经全部到货；追加后会自动恢复为“部分到货”，新增差额可继续登记入库。'
  }
  if (appendingOrderRecord.value?.status === 'PARTIALLY_RECEIVED') {
    return '该订单已有入库记录；追加只增加需求量，不修改既有入库流水，追加后仍为“部分到货”。'
  }
  if (appendingOrderRecord.value?.quantity_basis === 'EXPLICIT') return '逐纸品填写追加后的总需求，产品数量保持原记录；采购单只发行本次增加的纸品差额。'
  return '系统会沿用原订单纸品规则重新计算需求量，并生成追单提醒和操作记录。'
})
const reducingOrderRecord = computed(() =>
  orderRecords.value.find((order) => order.order_no === reduceOrderNo.value) ?? null,
)
const purchaseOrderDialogRecord = computed(() =>
  orderRecords.value.find((order) => order.order_no === purchaseOrderDialogNo.value) ?? null,
)
const orderDetailRecord = computed(() =>
  orderRecords.value.find((order) => order.order_no === orderDetailNo.value) ?? null,
)
const orderDetailRow = computed(() =>
  localOrders.find((order) => order.id === orderDetailNo.value) ?? null,
)
const orderDetailQuantitySummary = computed(() => {
  const grouped = new Map<string, { required: number; received: number; remaining: number }>()
  for (const material of orderDetailRow.value?.materials ?? []) {
    const unit = material.unit || '个'
    const current = grouped.get(unit) ?? { required: 0, received: 0, remaining: 0 }
    current.required += orderDetailRequiredQuantity(material)
    current.received += orderDetailReceivedQuantity(material)
    current.remaining += orderDetailRemainingQuantity(material)
    grouped.set(unit, current)
  }
  const summarize = (key: 'required' | 'received' | 'remaining') => [...grouped.entries()]
    .map(([unit, values]) => `${formatNumber(values[key])} ${unit}`)
    .join('、') || '0'
  return {
    required: summarize('required'),
    received: summarize('received'),
    remaining: summarize('remaining'),
  }
})
const reduceOrderMaximumQuantity = computed(() => (
  reducingOrderRecord.value ? maximumReducibleProductQuantity(reducingOrderRecord.value) : 0
))
const reduceOrderRemainingQuantity = computed(() => Math.max(
  0,
  Number(reducingOrderRecord.value?.product_order_quantity ?? 0) - Number(reduceOrderQuantity.value || 0),
))
const editingOrderHasPostedReceipts = computed(() =>
  Boolean(editingOrderRecord.value?.lines.some((line) => Number(line.received_quantity) > 0)),
)
const editingOrderStructureLocked = computed(() =>
  ['PENDING_SUPPLIER', 'PARTIALLY_RECEIVED', 'COMPLETED'].includes(editingOrderRecord.value?.status ?? '') || editingOrderHasPostedReceipts.value,
)
const customerFilterOptions = computed(() => [
  '全部客户',
  ...new Set([
    ...customerRecords.value.map((customer) => customer.customer_name),
    ...localOrders.map((order) => order.customer),
  ]),
])
const orderMasterPapers = computed(() => masterWorkspace.value.records
  .filter(r => r.kind === 'CONFIG' && r.status === 'ACTIVE')
  .flatMap(r => r.data.lines || []))
const orderPackagingOptions = computed(() => masterPaperOptions(masterWorkspace.value.records, 'packaging_type', masterWorkspace.value.paper_history))
const orderUnitOptions = computed(() => [...new Set(['个', '张', '套', ...orderMasterPapers.value.map(l => l.unit).filter(Boolean)])])
const paperQualitySuggestions = computed(() => masterPaperOptions(masterWorkspace.value.records, 'paper_quality', masterWorkspace.value.paper_history))
const specificationSuggestions = computed(() => masterPaperOptions(masterWorkspace.value.records, 'specification', masterWorkspace.value.paper_history))

const activeTab = computed<CartonTab>(() => {
  const routeTab = route.query.tab
  return typeof routeTab === 'string' && validTabs.has(routeTab as CartonTab)
    ? routeTab as CartonTab
    : 'dashboard'
})

const activeModule = computed<CartonTab>(() => activeTab.value === 'weekly-check' ? 'orders'
  : ['inventory', 'inventory-summary', 'inventory-movements'].includes(activeTab.value) ? 'inventory' : activeTab.value)
const activeTabItem = computed(() => tabs.find(tab => tab.id === activeModule.value) ?? tabs[0])
watch(activeTab, tab => { if (tab !== 'inventory') showStocktake.value = false })
function openModule(tab: CartonTab) {
  showStocktake.value = false
  showInventoryImport.value = false
  setActiveTab(tab)
}
function openInventoryPage(tab: CartonTab, stocktake = false, openingStock = false) {
  showStocktake.value = stocktake
  showInventoryImport.value = openingStock
  setActiveTab(tab)
}
const warehouseDepartmentRoute = computed(() => getFactoryScopedRoute(
  '/modules/pmc-warehouse',
  selectedFactoryId.value,
))
const normalizedSearch = computed(() => globalSearch.value.trim().toLowerCase())

function includesSearch(values: Array<string | number>) {
  if (!normalizedSearch.value) return true
  return values.join(' ').toLowerCase().includes(normalizedSearch.value)
}

function matchesCustomer(customer: string) {
  return selectedCustomer.value === '全部客户' || customer === selectedCustomer.value
}

const visibleOrders = computed(() => localOrders.filter((row) => {
  const rawOrder = orderRecords.value.find((order) => order.order_no === row.id)
  const statusMatches = orderStatusFilter.value === 'ALL'
    || rawOrder?.status === orderStatusFilter.value
  const dueMatches = orderDueFilter.value === 'ALL'
    || orderDueReminder(row).level === orderDueFilter.value
  const orderDateMatches = (!orderDateRange.value.start || row.orderDate >= orderDateRange.value.start.toString())
    && (!orderDateRange.value.end || row.orderDate <= orderDateRange.value.end.toString())
  return statusMatches
    && dueMatches
    && orderDateMatches
    && matchesCustomer(row.customer)
    && includesSearch([
      row.id,
      row.customer,
      row.contractNo,
      customerPoForOrder(row.id),
      rawOrder?.product_name || '',
      row.itemNo,
      row.status,
      ...row.materials.flatMap((material) => [
        material.packagingType,
        material.paperQuality,
        material.specification,
      ]),
    ])
}))
const selectedOrders = computed(() => orderRecords.value.filter((order) =>
  selectedOrderNos.value.includes(order.order_no),
))
const selectedSubmittableOrderCount = computed(() =>
  selectedOrders.value.filter((order) => order.status === 'CONFIRMED').length,
)
const selectedOrdersCanCancel = computed(() =>
  selectedOrders.value.length > 0
  && selectedOrders.value.every((order) => order.status === 'CONFIRMED'),
)
const selectedOrdersCanDeleteHistory = computed(() => apiConnected.value && canIssuePurchaseOrders.value
  && selectedOrders.value.length > 0 && selectedOrders.value.length <= 100
  && selectedOrders.value.every(order => order.can_delete_history))
const canUndoScheduleImport = computed(() => authStore.can('carton_procurement:import', selectedFactoryId.value, 'pmc-warehouse')
  || authStore.can('carton_procurement:import', selectedFactoryId.value, 'carton'))

const visibleWeeklyChecks = computed(() => localWeeklyChecks.filter((row) =>
  (!weeklyOnlyAttention.value || row.result !== '已匹配' || row.procurementState === '需要下单' || row.dateReviewRequired) && matchesCustomer(row.customer)
  && includesSearch([
    row.reference,
    row.poNumbers,
    row.customer,
    row.itemNo,
    row.productName,
    row.result,
    row.procurementState ?? '',
    row.businessCustomer ?? '',
  ]),
))

type BusinessOrderAlertKind = 'MISSING_ORDER' | 'QUANTITY_INCREASE' | 'QUANTITY_DECREASE' | 'QUANTITY_REVIEW'

interface BusinessOrderAlert {
  id: string
  alertNo: string
  kind: BusinessOrderAlertKind
  customerCode: string
  customerName: string
  contractNo: string
  itemNo: string
  productName: string
  scheduleQuantity: number
  orderQuantity: number
  differenceQuantity: number
  orderNo: string
  orderStatus: string
  sourceFilename: string
  sourceOperatorName: string
  sourceCreatedAt: string
  suggestion: string
  exception: CartonExceptionResponse
  sourceRow: CartonImportPreviewRow | null
  order: CartonOrderResponse | null
}

function businessIdentity(value: string | undefined) {
  return (value ?? '').trim().toLowerCase().replace(/[\s\-_/\\.]/g, '')
}

function weeklyRowForException(exception: CartonExceptionResponse, batch: CartonImportBatchResponse | undefined) {
  const contractKey = businessIdentity(exception.contract_no)
  const itemKey = businessIdentity(exception.item_no)
  return batch?.parse_summary.rows?.find((row) => {
    const rowContractKey = businessIdentity(row.contract_no ?? row.reference)
    const rowItemKey = businessIdentity(row.item_no)
    return (!contractKey || rowContractKey === contractKey)
      && (!itemKey || rowItemKey === itemKey)
  }) ?? null
}

function orderForBusinessAlert(row: CartonImportPreviewRow | null, exception: CartonExceptionResponse) {
  const exact = orderRecords.value.find((order) =>
    (row?.order_id && order.id === row.order_id)
    || (row?.order_no && order.order_no === row.order_no)
  )
  if (exact) return exact
  const candidates = orderRecords.value.filter((order) => (
      businessIdentity(order.contract_no) === businessIdentity(exception.contract_no || row?.contract_no || row?.reference)
      && businessIdentity(order.item_no) === businessIdentity(exception.item_no || row?.item_no)
      && (!row?.customer_po || order.customer_po?.trim().toLocaleLowerCase() === row.customer_po.trim().toLocaleLowerCase())
    ),
  )
  return candidates.length === 1 ? candidates[0] ?? null : null
}

const businessOrderAlerts = computed<BusinessOrderAlert[]>(() => {
  const batches = new Map(weeklyImportHistory.value.map((batch) => [batch.id, batch]))
  const latestByBusinessKey = new Map<string, BusinessOrderAlert>()
  const candidates = exceptionRecords.value
    .filter((exception) =>
      exception.source_type === 'WEEKLY_SCHEDULE'
      && ['MISSING_ORDER', 'QUANTITY_MISMATCH'].includes(exception.category),
    )
    .sort((left, right) => right.created_at.localeCompare(left.created_at))

  for (const exception of candidates) {
    const batch = batches.get(exception.source_id)
    const sourceRow = weeklyRowForException(exception, batch)
    const order = orderForBusinessAlert(sourceRow, exception)
    const scheduleQuantity = Number(sourceRow?.quantity ?? 0)
    const orderQuantity = Number(order?.product_order_quantity ?? 0)
    const differenceQuantity = scheduleQuantity - orderQuantity
    const kind: BusinessOrderAlertKind = exception.category === 'MISSING_ORDER'
      ? 'MISSING_ORDER'
      : !sourceRow
        ? 'QUANTITY_REVIEW'
        : differenceQuantity > 0
          ? 'QUANTITY_INCREASE'
          : differenceQuantity < 0
            ? 'QUANTITY_DECREASE'
            : 'QUANTITY_REVIEW'
    const identityKey = [
      businessIdentity(exception.contract_no || sourceRow?.contract_no || sourceRow?.reference),
      businessIdentity(exception.item_no || sourceRow?.item_no),
    ].join('|')
    const businessKey = identityKey === '|' ? exception.id : identityKey
    if (latestByBusinessKey.has(businessKey)) continue
    latestByBusinessKey.set(businessKey, {
      id: exception.id,
      alertNo: exception.exception_no,
      kind,
      customerCode: exception.customer_code || sourceRow?.customer_code || order?.customer_code || '',
      customerName: exception.customer_name || sourceRow?.customer_name || order?.customer_name || '待识别客户',
      contractNo: exception.contract_no || sourceRow?.contract_no || sourceRow?.reference || '',
      itemNo: exception.item_no || sourceRow?.item_no || '',
      productName: sourceRow?.product_name || order?.product_name || '',
      scheduleQuantity,
      orderQuantity,
      differenceQuantity,
      orderNo: order?.order_no || sourceRow?.order_no || '',
      orderStatus: order?.status || sourceRow?.order_status || '',
      sourceFilename: batch?.original_filename || '历史业务排期',
      sourceOperatorName: batch?.imported_by_name || '业务接单员',
      sourceCreatedAt: batch?.created_at || exception.created_at,
      suggestion: sourceRow?.suggestion || exception.description,
      exception,
      sourceRow,
      order,
    })
  }
  return [...latestByBusinessKey.values()]
})

const visibleBusinessOrderAlerts = computed(() => businessOrderAlerts.value.filter((alert) => {
  const statusMatches = businessAlertStatusFilter.value === 'ALL'
    || ['OPEN', 'IN_PROGRESS'].includes(alert.exception.status)
  const kindMatches = businessAlertKindFilter.value === 'ALL'
    || alert.kind === businessAlertKindFilter.value
  return statusMatches
    && kindMatches
    && matchesCustomer(alert.customerName)
    && includesSearch([
      alert.alertNo,
      alert.customerName,
      alert.contractNo,
      alert.itemNo,
      alert.productName,
      alert.orderNo,
      alert.sourceFilename,
      alert.sourceOperatorName,
    ])
}))

const businessAlertSummary = computed(() => {
  const actionable = visibleBusinessOrderAlerts.value.filter((alert) => ['OPEN', 'IN_PROGRESS'].includes(alert.exception.status))
  return {
    total: actionable.length,
    missing: actionable.filter((alert) => alert.kind === 'MISSING_ORDER').length,
    increase: actionable.filter((alert) => alert.kind === 'QUANTITY_INCREASE').length,
    decrease: actionable.filter((alert) => alert.kind === 'QUANTITY_DECREASE').length,
  }
})

const visibleMovements = computed(() => {
  return localMovements.filter((row) => {
    const rawType = row.rawMovementType ?? ''
    const movementMatches = inventoryMovementFilter.value === 'ALL'
      || rawType === inventoryMovementFilter.value
    const dateMatches = (!inventoryDateFrom.value || row.date.slice(0, 10) >= inventoryDateFrom.value)
      && (!inventoryDateTo.value || row.date.slice(0, 10) <= inventoryDateTo.value)
    const fields = [
      row.date,
      row.documentNo,
      row.customer,
      row.poNumber,
      row.itemNo,
      row.packagingType,
      row.paperQuality,
      row.specification,
      row.movementType,
      row.location,
    ]
    return movementMatches
      && dateMatches
      && matchesCustomer(row.customer)
      && includesSearch(fields)
  })
})

const visibleClosings = computed(() => localClosings.filter((row) =>
  (!closingQueryPeriod.value || row.period === closingQueryPeriod.value)
  && (closingStatusFilter.value === 'ALL' || (closingStatusFilter.value === 'OPEN' ? row.status !== '已锁账' : row.status === '已锁账'))
  && matchesCustomer(row.customer)
  && includesSearch([row.customer, row.period, row.status]),
))

const exceptionTypeOptions = computed(() => [...new Set(localExceptions.map(row => row.type))])
const visibleExceptions = computed(() => localExceptions.filter((row) =>
  (exceptionStatusFilter.value === 'ALL' || (exceptionStatusFilter.value === 'OPEN' ? ['待处理', '处理中'].includes(row.status) : row.status === exceptionStatusFilter.value))
  && (exceptionTypeFilter.value === 'ALL' || row.type === exceptionTypeFilter.value)
  && matchesCustomer(row.customer)
  && includesSearch([row.id, row.customer, row.type, row.title, row.detail, row.status]),
))

const selectedExceptions = computed(() => localExceptions.filter(row => selectedExceptionNos.value.includes(row.id)))
const allVisibleExceptionsSelected = computed(() => visibleExceptions.value.length > 0 && visibleExceptions.value.every(row => selectedExceptionNos.value.includes(row.id)))
const someVisibleExceptionsSelected = computed(() => visibleExceptions.value.some(row => selectedExceptionNos.value.includes(row.id)))
function selectVisibleExceptions(selected: boolean) {
  const ids = visibleExceptions.value.map(row => row.id)
  selectedExceptionNos.value = selected ? [...new Set([...selectedExceptionNos.value, ...ids])] : selectedExceptionNos.value.filter(id => !ids.includes(id))
}

const selectedReceiptLines = computed(() => receiptLines.filter(row => row.selectedForReceipt !== false))
const hasManualPaperSelection = computed(() => receiptLines.some(row => row.selectedForReceipt !== undefined))
const manualReceiptDialogSelection = computed(() => receiptEntryMode.value === 'MANUAL' && hasManualPaperSelection.value && !currentReceipt.value)
const receiptDialogRows = computed(() => manualReceiptDialogSelection.value ? receiptLines : visibleReceiptLines.value)
const visibleReceiptLines = computed(() => {
  if (showReceiptDialog.value) return selectedReceiptLines.value
  const term = globalSearch.value.trim().toLowerCase()
  if (!term) return selectedReceiptLines.value
  return selectedReceiptLines.value.filter((row) => [
    receiptDeliveryNoteNo.value,
    row.orderNo,
    row.description,
    row.specification,
  ].join(' ').toLowerCase().includes(term))
})

const manualReceiptOrders = computed(() => orderRecords.value.filter((order) =>
  ['PENDING_SUPPLIER', 'PARTIALLY_RECEIVED'].includes(order.status)
  && order.lines.some((line) => Number(line.remaining_quantity) > 0),
))
function contractReceiptKey(order: CartonOrderResponse) {
  return JSON.stringify([order.customer_code, order.contract_no])
}
const filteredManualReceiptOrders = computed(() => manualReceiptOrders.value.filter((order) => {
  const term = globalSearch.value.trim().toLowerCase()
  const text = [order.order_no, order.customer_name, order.contract_no, order.customer_po || '', order.item_no, order.product_name,
    ...order.lines.flatMap((line) => [line.packaging_type, line.paper_quality, line.specification])].join(' ').toLowerCase()
  return matchesCustomer(order.customer_name)
    && (!receiptPlannedDueFrom.value || order.due_date >= receiptPlannedDueFrom.value)
    && (!receiptPlannedDueTo.value || order.due_date <= receiptPlannedDueTo.value)
    && (!term || term.split(/\s+/).every((word) => text.includes(word)))
}))
const receiptContractOptions = computed(() => {
  const groups = new Map<string, { key: string; label: string; count: number }>()
  for (const order of filteredManualReceiptOrders.value) {
    const key = contractReceiptKey(order)
    const group = groups.get(key)
    if (group) group.count += 1
    else groups.set(key, { key, label: `${order.customer_name} · ${order.contract_no}`, count: 1 })
  }
  return [...groups.values()]
})
const visibleManualReceiptOrders = computed(() => filteredManualReceiptOrders.value.filter(order =>
  !receiptContractKey.value || contractReceiptKey(order) === receiptContractKey.value,
))

const receiptLedgerRows = computed(() => {
  const rows = visibleManualReceiptOrders.value.map((order) => ({
    ...mapOrder(order),
    productName: order.product_name,
  }))
  if (receiptOrderSort.value === 'DEFAULT') return rows
  return rows.sort((left, right) => {
    if (!left.dueDate) return right.dueDate ? 1 : 0
    if (!right.dueDate) return -1
    const dueComparison = left.dueDate.localeCompare(right.dueDate)
    return (receiptOrderSort.value === 'DUE_DESC' ? -dueComparison : dueComparison)
      || left.id.localeCompare(right.id)
  })
})

const receiptUnsubmittedOrderNos = computed(() => {
  const lineIds = new Set(selectedReceiptLines.value
    .filter((line) => line.sourceType === 'FORMAL_ORDER')
    .map((line) => line.orderLineId)
    .filter(Boolean))
  return orderRecords.value
    .filter((order) => order.status === 'CONFIRMED' && order.lines.some((line) => lineIds.has(line.id)))
    .map((order) => order.order_no)
})
const adHocReceiptLineCount = computed(() => receiptLines.filter((line) => line.sourceType === 'AD_HOC').length)
const hasAdHocReceiptLines = computed(() => adHocReceiptLineCount.value > 0)

const visibleInspectionChecks = computed(() => localInspectionChecks.filter((row) =>
  (!weeklyOnlyAttention.value || row.reminderStatus !== 'READY') && matchesCustomer(row.customer)
  && includesSearch([
    row.reference,
    row.poNumbers,
    row.customer,
    row.itemNo,
    row.productName,
    row.result,
    row.requiredDeliveryDate,
  ]),
))

type OrderDueLevel = 'OVERDUE' | 'TODAY' | 'DUE_SOON' | 'UPCOMING' | 'CLOSED' | 'INVALID'

interface OrderDueReminder {
  level: OrderDueLevel
  label: string
  days: number | null
  priority: number
}

const orderedVisibleOrders = computed(() => [...visibleOrders.value].sort((left, right) => {
  if (orderSort.value === 'DUE_DESC') return right.dueDate.localeCompare(left.dueDate) || left.id.localeCompare(right.id)
  if (orderSort.value === 'ORDER_DESC') return right.orderDate.localeCompare(left.orderDate) || right.id.localeCompare(left.id)
  const leftReminder = orderDueReminder(left)
  const rightReminder = orderDueReminder(right)
  return leftReminder.priority - rightReminder.priority
    || left.dueDate.localeCompare(right.dueDate)
    || left.id.localeCompare(right.id)
}))

const orderDueSummary = computed(() => visibleOrders.value.reduce((summary, order) => {
  const level = orderDueReminder(order).level
  if (level === 'OVERDUE') summary.overdue += 1
  if (level === 'TODAY') summary.today += 1
  if (level === 'DUE_SOON') summary.dueSoon += 1
  return summary
}, { overdue: 0, today: 0, dueSoon: 0 }))

const urgentOrderDueCount = computed(() =>
  orderDueSummary.value.overdue + orderDueSummary.value.today + orderDueSummary.value.dueSoon,
)
const selectedManualReceiptOrders = computed(() => manualReceiptOrders.value.filter((order) =>
  manualReceiptOrderNos.value.includes(order.order_no),
))

function receiptLineEffectiveQuantity(row: ReceiptReviewLine) {
  return Math.max(
    0,
    Number(row.receivedQuantity || 0)
      - Number(row.damagedQuantity || 0)
      - Number(row.rejectedQuantity || 0)
      - Number(row.unusableQuantity || 0),
  )
}

const manualReceiptWillCompleteOrder = computed(() =>
  receiptEntryMode.value === 'MANUAL'
  && selectedManualReceiptOrders.value.length > 0
  && selectedManualReceiptOrders.value.every(order => order.lines.every(line => {
    const remaining = Number(line.remaining_quantity)
    const draft = selectedReceiptLines.value.find(row => row.orderLineId === line.id)
    return remaining <= 0 || Boolean(draft && receiptLineEffectiveQuantity(draft) >= remaining)
  })),
)
const receiptConfirmButtonLabel = computed(() => {
  if (currentReceipt.value?.status === 'REVERSED') return '已作废 / 冲销'
  if (currentReceipt.value?.status === 'POSTED') return '已确认入库'
  if (confirmingReceipt.value) return '正在入库…'
  if (hasAdHocReceiptLines.value) return '确认入库并计入月结'
  if (manualReceiptWillCompleteOrder.value) return '确认入库并完成订单'
  if (receiptEntryMode.value === 'MANUAL') return '确认入库（订单转部分收料）'
  return '人工确认并入库'
})

const pendingOrderCount = computed(() => localOrders.filter(row => !['已完成', '已取消'].includes(row.status) && matchesCustomer(row.customer) && includesSearch([row.id, row.contractNo, row.itemNo, row.customer])).length)
const weeklyRiskCount = computed(() => visibleWeeklyChecks.value.filter((row) => row.result !== '已匹配' || row.procurementState === '需要下单' || row.dateReviewRequired).length)
const inspectionReminderCount = computed(() => visibleInspectionChecks.value.filter((row) => row.reminderStatus !== 'READY').length)
const weeklyAttentionCount = computed(() => weeklyRiskCount.value + inspectionReminderCount.value)
const openExceptionCount = computed(() => visibleExceptions.value.filter((row) => row.status !== '已关闭').length)
function inventoryBalanceLatestDocumentNo(row: InventoryBalanceRow) {
  return row.latestDocumentNo
}

const inventoryBalances = computed(() => {
  return localInventoryBalances.filter((row) => {
    const latestDocumentNo = inventoryBalanceLatestDocumentNo(row)
    const rowDate = row.inboundDate.slice(0, 10)
    const fields = [
      row.date,
      latestDocumentNo,
      row.customer,
      row.poNumber,
      row.itemNo,
      row.packagingType,
      row.paperQuality,
      row.specification,
      row.location,
    ]
    const dateMatches = (!(inventoryBalanceDateFrom.value || inventoryBalanceDateTo.value) || Boolean(rowDate))
      && (!inventoryBalanceDateFrom.value || rowDate >= inventoryBalanceDateFrom.value)
      && (!inventoryBalanceDateTo.value || rowDate <= inventoryBalanceDateTo.value)
    return row.balance > 0 && matchesCustomer(row.customer)
      && (!warehouseFilter.value || row.warehouse === warehouseFilter.value)
      && (!locationFilter.value || row.locationId === locationFilter.value)
      && dateMatches
      && includesSearch(fields)
  })
})
const hasInventoryBalanceFilters = computed(() => Boolean(
  selectedCustomer.value !== '全部客户'
  || globalSearch.value.trim()
  || inventoryBalanceDateFrom.value
  || inventoryBalanceDateTo.value
  || warehouseFilter.value || locationFilter.value,
))
const selectedInventoryBalances = computed(() => localInventoryBalances.filter((row) =>
  selectedInventoryTargetIds.value.includes(row.id),
))
const auditEventOptions = computed(() => [...new Set(auditRecords.value.map((row) => row.event_type))].sort())
const auditActorOptions = computed(() => [...new Map(
  auditRecords.value.map((row) => [row.actor_user_id, row.actor_name || row.actor_user_id]),
).entries()].map(([id, name]) => ({ id, name })).sort((left, right) => left.name.localeCompare(right.name, 'zh-CN')))
const visibleAuditRecords = computed(() => {
  const term = auditSearch.value.trim().toLowerCase()
  return auditRecords.value.filter((row) => {
    const eventMatches = auditEventFilter.value === 'ALL' || row.event_type === auditEventFilter.value
    const actorMatches = auditActorFilter.value === 'ALL' || row.actor_user_id === auditActorFilter.value
    const date = row.created_at.slice(0, 10)
    const dateMatches = (!auditDateFrom.value || date >= auditDateFrom.value)
      && (!auditDateTo.value || date <= auditDateTo.value)
    const textMatches = !term || [
      row.event_type,
      row.entity_type,
      row.entity_id,
      row.actor_name,
      JSON.stringify(row.detail),
    ].join(' ').toLowerCase().includes(term)
    return eventMatches && actorMatches && dateMatches && textMatches
  })
})
const hasAuditFilters = computed(() => Boolean(
  auditSearch.value
  || auditEventFilter.value !== 'ALL'
  || auditActorFilter.value !== 'ALL'
  || auditDateFrom.value
  || auditDateTo.value,
))

const inventoryBalanceSummary = computed(() => {
  const quantities = new Map<string, number>()
  for (const row of inventoryBalances.value) {
    const unit = row.unit.trim() || '单位未注明'
    quantities.set(unit, (quantities.get(unit) ?? 0) + Math.round(row.balance * 10_000))
  }
  return [...quantities].map(([unit, quantity]) =>
    `${(quantity / 10_000).toLocaleString('zh-CN', { maximumFractionDigits: 4 })} ${unit}`,
  ).join(' · ') || '暂无库存'
})

const operableInventoryBalances = computed(() => inventoryBalances.value.filter((row) =>
  inventoryOperationType.value === 'ADJUSTMENT' || row.balance > 0,
))

const selectedInventoryBalance = computed(() =>
  localInventoryBalances.find((row) => row.id === inventoryTargetId.value) ?? null,
)

const activeWeeklyImportHistory = computed(() =>
  weeklyCheckMode.value === 'ORDER_GAP' ? weeklyImportHistory.value : inspectionImportHistory.value,
)

const receiptHistoryRows = computed(() => {
  return receiptRecords.value.flatMap((receipt) => receipt.lines.map((line) => ({
    id: `${receipt.id}-${line.id}`,
    receiptId: receipt.id,
    receipt,
    receiptNo: receipt.receipt_no,
    deliveryNoteNo: receipt.delivery_note_no,
    deliveryDate: receipt.delivery_date,
    acceptanceDate: receipt.acceptance_date,
    status: receipt.status,
    sourceType: line.source_type,
    customer: line.customer_name,
    contractNo: line.contract_no,
    customerPo: customerPoForLine(line.order_line_id || ''),
    itemNo: line.item_no,
    packagingType: line.packaging_type,
    paperQuality: line.paper_quality,
    paper: `${line.packaging_type} ${line.paper_quality}`.trim(),
    specification: line.specification,
    effectiveQuantity: Number(line.effective_quantity),
    unit: line.unit,
    location: line.location_allocations?.length ? line.location_allocations.map(a => `${a.label || a.location_id}：${Number(a.quantity)} ${line.unit}`).join('；') : line.location,
    operator: receipt.confirmed_by_name || receipt.created_by_name,
    confirmedAt: receipt.confirmed_at || receipt.created_at,
  }))).filter((row) =>
    matchesCustomer(row.customer)
    && (receiptHistoryStatus.value === 'ALL' || row.status === receiptHistoryStatus.value)
    && (!receiptHistoryDateRange.value.start || row.deliveryDate >= receiptHistoryDateRange.value.start.toString())
    && (!receiptHistoryDateRange.value.end || row.deliveryDate <= receiptHistoryDateRange.value.end.toString())
    && includesSearch([
      row.receiptNo,
      row.deliveryNoteNo,
      row.customer,
      row.contractNo,
      row.customerPo,
      row.itemNo,
      row.paper,
      row.specification,
    ]),
  )
})

const receiptTotals = computed(() => visibleReceiptLines.value.reduce((totals, row) => {
  const unusable = Number(row.damagedQuantity || 0) + Number(row.rejectedQuantity || 0) + Number(row.unusableQuantity || 0)
  const effective = receiptLineEffectiveQuantity(row)
  totals.delivered += Number(row.deliveryQuantity || 0)
  totals.received += Number(row.receivedQuantity || 0)
  totals.unusable += unusable
  totals.effective += effective
  return totals
}, { delivered: 0, received: 0, unusable: 0, effective: 0 }))

const receiptImportStats = computed(() => ({
  total: receiptImportBatch.value?.parse_summary.row_count ?? receiptImportRows.value.length,
  matched: receiptImportBatch.value?.parse_summary.matched_count ?? 0,
  issues: receiptImportBatch.value?.parse_summary.issue_count ?? 0,
}))
const receiptImportNeedsReview = computed(() => receiptImportStats.value.total === 0 || receiptImportStats.value.matched === 0 || receiptImportStats.value.issues > 0)
const receiptImportPreviewRows = computed(() => receiptImportRows.value.slice(0, 50))
const receiptImportWarnings = computed(() => receiptImportBatch.value?.parse_summary.warnings ?? [])
const receiptImportRawText = computed(() => receiptImportBatch.value?.parse_summary.document?.raw_text_excerpt?.trim() ?? '')

watch(selectedFactoryId, (factoryId, previousFactory) => {
  closingGeneration++; if (closingBusyId.value === 'generate') closingBusyId.value = ''
  customerEditGeneration += 1
  showCustomerModal.value = false; customerEditError.value = ''; resetCustomerForm()
  if (previousFactory) {
    customerRecords.value = []; orderRecords.value = []; closingRecords.value = []; exceptionRecords.value = []; auditRecords.value = []
    localOrders.splice(0); localMovements.splice(0); localInventoryBalances.splice(0); localClosings.splice(0); localExceptions.splice(0)
    apiConnected.value = false
  }
  warehouseFilter.value = ''; locationFilter.value = ''; inventoryLocations.value = []; showLocationManager.value = false; newLocationSelection.value = ''
  pricingTarget.value = null
  closingDecision.value = null
  receiptHistoryStatus.value = 'ALL'
  receiptHistoryDateRange.value = { start: undefined, end: undefined }
  receiptCorrectionTarget.value = null
  receiptCorrectionNote.value = ''
  historyItemSearchGeneration += 1
  if (historyItemSearchTimer) {
    clearTimeout(historyItemSearchTimer)
    historyItemSearchTimer = null
  }
  appStore.setActiveFactory(factoryId)
  selectedCustomer.value = '全部客户'
  clearReceiptPlannedDueRange()
  receiptOrderSort.value = 'DUE_ASC'
  receiptContractKey.value = ''
  orderForm.customerCode = ''
  receiptImportBatch.value = null
  receiptImportRows.value = []
  receiptBatchId.value = ''
  selectedReceiptFileName.value = ''
  selectedWeeklyFileName.value = ''
  selectedInspectionFileName.value = ''
  weeklyImportHistory.value = []
  inspectionImportHistory.value = []
  receiptRecords.value = []
  receiptEntryMode.value = 'MANUAL'
  receiptPage.value = 'PENDING'
  showReceiptDialog.value = false
  manualReceiptOrderNos.value = []
  currentReceipt.value = null
  receiptDeliveryNoteNo.value = ''
  receiptDeliveryDate.value = businessTodayIso()
  receiptAcceptanceDate.value = businessTodayIso()
  selectedOrderNos.value = []
  selectedExceptionNos.value = []
  bulkExceptionNote.value = ''
  deleteHistoryTarget.value = null
  deleteHistoryTargets.value = []
  undoImportTarget.value = null
  selectedWeeklyBatchId.value = ''
  selectedInspectionBatchId.value = ''
  replenishTarget.value = null
  replenishQuantities.value = {}
  historyItemSuggestions.value = []
  showHistoryItemSuggestions.value = false
  selectedHistoryItemSource.value = null
  selectedInventoryTargetIds.value = []
  inventoryBulkQuantities.value = {}
  showInventoryImport.value = false
  showStocktake.value = false
  showInventoryOperation.value = false
  showInventoryRelocation.value = false
  relocationTarget.value = null
  inventoryBalanceDateRange.value = { start: undefined, end: undefined }
  inventoryMovementDateRange.value = { start: undefined, end: undefined }
  weeklyOnlyAttention.value = false; weeklyHistoryExpanded.value = false; weeklyHistorySearch.value = ''
  closingQueryPeriod.value = ''; closingStatusFilter.value = 'ALL'; exceptionStatusFilter.value = 'OPEN'; exceptionTypeFilter.value = 'ALL'
  orderStatusFilter.value = 'ALL'
  orderDueFilter.value = 'ALL'
  orderDateRange.value = { start: undefined, end: undefined }
  orderSort.value = 'DUE_ASC'
  masterWorkspace.value = emptyMaster(); masterLoaded.value = false; chosenMaster.value = null; outboundWorkshop.value = ''; bulkWorkshops.value = {}
  void loadBackendData(factoryId)
}, { immediate: true })

watch(
  [() => orderForm.itemNo, () => orderForm.customerCode, showOrderModal, apiConnected],
  ([itemNo, customerCode, orderModalOpen]) => {
  if (historyItemSearchTimer) {
    clearTimeout(historyItemSearchTimer)
    historyItemSearchTimer = null
  }
  const generation = ++historyItemSearchGeneration
  const rawItemNo = itemNo.trim()
  const normalized = rawItemNo.toLowerCase()
  if (selectedHistoryItemSource.value && selectedHistoryItemSource.value.item_no.toLowerCase() !== normalized) {
    selectedHistoryItemSource.value = null
  }
  if (editingOrderNo.value || !orderModalOpen) {
    historyItemSuggestions.value = []
    historyItemSuggestionsLoading.value = false
    showHistoryItemSuggestions.value = false
    return
  }
  if (skipHistoryItemSearchFor === rawItemNo) {
    skipHistoryItemSearchFor = ''
    historyItemSuggestionsLoading.value = false
    showHistoryItemSuggestions.value = false
    return
  }
  const historical = normalized
    ? orderRecords.value.find((order) => order.item_no.trim().toLowerCase() === normalized && order.product_name.trim())
    : null
  if (historical) {
    if (!orderForm.productName.trim() || orderForm.productName === autoFilledProductName.value) {
      orderForm.productName = historical.product_name
      autoFilledProductName.value = historical.product_name
    }
  } else if (orderForm.productName === autoFilledProductName.value) {
    orderForm.productName = ''
    autoFilledProductName.value = ''
  }
  if (!apiConnected.value || rawItemNo.length < 2) {
    historyItemSuggestions.value = []
    historyItemSuggestionsLoading.value = false
    showHistoryItemSuggestions.value = false
    return
  }
  historyItemSuggestionsLoading.value = true
  showHistoryItemSuggestions.value = true
  historyItemSearchTimer = setTimeout(async () => {
    try {
      const suggestions = await cartonProcurementApi.searchOrderHistoryItems(
        selectedFactoryId.value,
        rawItemNo,
        customerCode,
      )
      if (generation !== historyItemSearchGeneration || orderForm.itemNo.trim() !== rawItemNo) return
      historyItemSuggestions.value = suggestions
      showHistoryItemSuggestions.value = true
    } catch {
      if (generation !== historyItemSearchGeneration) return
      historyItemSuggestions.value = []
      showHistoryItemSuggestions.value = false
    } finally {
      if (generation === historyItemSearchGeneration) historyItemSuggestionsLoading.value = false
    }
  }, 220)
})

watch([selectedCustomer, globalSearch], () => {
  actionMessage.value = selectedCustomer.value === '全部客户'
    ? `当前显示全部客户的${apiConnected.value ? '正式台账' : '只读演示记录'}。`
    : `当前已筛选客户：${selectedCustomer.value}。`
})
watch(selectedCustomer, () => { receiptContractKey.value = '' })

watch(selectedOrderNos, () => {
  if (!exportingSelectedOrders.value && !issuingSelectedPurchaseOrders.value) combinedPurchaseOrderMessage.value = ''
}, { deep: true })
watch([selectedFactoryId, activeTab, () => JSON.stringify(selectedOrderNos.value)], () => closePurchaseBatchConfirmation())

function setActiveTab(tab: CartonTab) {
  void router.replace({
    query: {
      ...route.query,
      factory: selectedFactoryId.value,
      tab: tab === 'dashboard' ? undefined : tab,
    },
  })
}

function populateManualReceipt(orderNos: string[]) {
  const previous = new Map((!currentReceipt.value && receiptEntryMode.value === 'MANUAL' ? receiptLines : [])
    .filter(line => line.selectedForReceipt !== undefined)
    .map(line => [line.orderLineId, line]))
  const fresh = previous.size === 0
  receiptCorrectionNote.value = ''
  const orders = manualReceiptOrders.value.filter((item) => orderNos.includes(item.order_no))
  currentReceipt.value = null
  receiptEntryMode.value = 'MANUAL'
  receiptLines.splice(0)
  if (!orders.length) {
    actionMessage.value = manualReceiptOrders.value.length
      ? '请至少选择一张需要登记收料的正式订单。'
      : '当前没有待收料的正式订单。'
    return
  }
  receiptLines.push(...orders.flatMap((order) => order.lines
    .filter((line) => Number(line.remaining_quantity) > 0)
    .map((line) => previous.get(line.id) ?? ({
        id: `MANUAL-${line.id}`,
        selectedForReceipt: false,
        orderNo: `${order.order_no} · ${order.contract_no}-${order.item_no}`,
        description: `${line.packaging_type} ${line.paper_quality}`.trim(),
        specification: `${line.specification}${line.dimension_unit ? ` ${line.dimension_unit}` : ''}`,
        deliveryQuantity: 0,
        unitPrice: Number(line.unit_price),
        receivedQuantity: 0,
        damagedQuantity: 0,
        rejectedQuantity: 0,
        unusableQuantity: 0,
        sourceType: 'FORMAL_ORDER' as const,
        orderLineId: line.id,
        customerCode: order.customer_code,
        contractNo: order.contract_no,
        itemNo: order.item_no,
        packagingType: line.packaging_type,
        paperQuality: line.paper_quality,
        unit: line.unit,
        currency: line.currency,
        location: '',
        sourceLabel: '人工录入',
        remainingQuantity: Number(line.remaining_quantity),
      }))))
  for (const row of receiptLines) {
    if (previous.has(row.orderLineId)) continue
    const options = receiptReplacementOptions(row)
    if (options.length === 1 && Number(options[0]!.remaining_quantity) >= row.remainingQuantity) {
      row.replenishmentIssueId = options[0]!.replenishment_issue_id
    }
    if (options.length) changeReceiptReplacement(row)
  }
  if (fresh) {
    receiptDeliveryNoteNo.value = ''
    receiptDeliveryDate.value = businessTodayIso()
    receiptAcceptanceDate.value = businessTodayIso()
  }
  actionMessage.value = `已展开 ${orders.length} 张订单的 ${receiptLines.length} 条待收纸品；请勾选本次到货纸品并填写实际收到数量。`
}

function selectReceiptContract() {
  if (!receiptContractKey.value) return
  manualReceiptOrderNos.value = [...new Set([...manualReceiptOrderNos.value, ...visibleManualReceiptOrders.value.map(order => order.order_no)])]
  populateManualReceipt(manualReceiptOrderNos.value)
}

function selectReceiptPaper(id: string, checked: boolean) {
  if (currentReceipt.value || savingReceipt.value) return
  const row = receiptLines.find(line => line.id === id)
  if (row) row.selectedForReceipt = checked
}

function updateReceiptActual(row: ReceiptReviewLine, quantity: number) {
  if (currentReceipt.value || savingReceipt.value || row.selectedForReceipt === false) return
  if (receiptEntryMode.value === 'MANUAL' && (row.deliveryQuantity === row.receivedQuantity || !row.deliveryQuantity)) {
    row.deliveryQuantity = quantity
  }
  row.receivedQuantity = quantity
}

function setReceiptPaperQuantity(id: string, quantity: number) {
  if (currentReceipt.value || savingReceipt.value) return
  const row = receiptLines.find(line => line.id === id)
  if (!row || row.selectedForReceipt === false) return
  row.receivedQuantity = quantity
  row.deliveryQuantity = quantity
}

function restoreReceiptFocus(event: Event) {
  event.preventDefault()
  receiptDialogTrigger.value?.focus()
}

function clearReceiptPlannedDueRange() {
  receiptDueCalendarValue.value = { start: undefined, end: undefined }
}

function clearReceiptOrderFilters() {
  receiptContractKey.value = ''
  globalSearch.value = ''
  selectedCustomer.value = '全部客户'
  clearReceiptPlannedDueRange()
}

function toggleVisibleReceiptOrders(checked: boolean) {
  const visibleNos = new Set(visibleManualReceiptOrders.value.map((order) => order.order_no))
  manualReceiptOrderNos.value = checked
    ? [...new Set([...manualReceiptOrderNos.value, ...visibleNos])]
    : manualReceiptOrderNos.value.filter((orderNo) => !visibleNos.has(orderNo))
  populateManualReceipt(manualReceiptOrderNos.value)
}

function openManualReceipt(orderNo = '') {
  if (!apiConnected.value) {
    actionMessage.value = '后端未连接，不能登记正式收料。'
    return
  }
  const reopensCurrentSelection = !orderNo
    || (manualReceiptOrderNos.value.length === 1 && manualReceiptOrderNos.value[0] === orderNo)
  const canResumeReceipt = !currentReceipt.value || currentReceipt.value.status === 'PENDING_CONFIRMATION'
  if (reopensCurrentSelection && canResumeReceipt && receiptEntryMode.value === 'MANUAL' && (manualReceiptOrderNos.value.length || currentReceipt.value)) {
    showReceiptDialog.value = true
    return
  }
  receiptEntryMode.value = 'MANUAL'
  receiptFeedbackMessage.value = ''
  receiptPage.value = 'PENDING'
  receiptImportBatch.value = null
  receiptImportRows.value = []
  receiptBatchId.value = ''
  selectedReceiptFileName.value = ''
  const requestedOrderNos = orderNo ? [orderNo] : manualReceiptOrderNos.value
  const remainingSelection = manualReceiptOrders.value
    .filter((order) => requestedOrderNos.includes(order.order_no))
    .map((order) => order.order_no)
  manualReceiptOrderNos.value = remainingSelection.length
    ? remainingSelection
    : manualReceiptOrders.value[0]?.order_no ? [manualReceiptOrders.value[0].order_no] : []
  populateManualReceipt(manualReceiptOrderNos.value)
  showReceiptDialog.value = true
  setActiveTab('receipts')
}

function toneClass(tone: CartonTone, variant: 'badge' | 'surface' = 'badge') {
  const classes = {
    teal: variant === 'badge' ? 'bg-teal-50 text-teal-700 ring-teal-200' : 'border-teal-200 bg-teal-50 text-teal-900',
    blue: variant === 'badge' ? 'bg-blue-50 text-blue-700 ring-blue-200' : 'border-blue-200 bg-blue-50 text-blue-900',
    amber: variant === 'badge' ? 'bg-amber-50 text-amber-700 ring-amber-200' : 'border-amber-200 bg-amber-50 text-amber-900',
    red: variant === 'badge' ? 'bg-red-50 text-red-700 ring-red-200' : 'border-red-200 bg-red-50 text-red-900',
    green: variant === 'badge' ? 'bg-emerald-50 text-emerald-700 ring-emerald-200' : 'border-emerald-200 bg-emerald-50 text-emerald-900',
    slate: variant === 'badge' ? 'bg-slate-100 text-slate-600 ring-slate-200' : 'border-slate-200 bg-slate-50 text-slate-800',
  }
  return classes[tone]
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('zh-CN').format(value)
}

function formatUnitsPerCarton(value: number) {
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 8 }).format(Number(value || 0))
}

function calculateRequiredQuantity(unitsPerCarton: number | null | '', orderQuantity: number | null | '') {
  const normalizedUnitsPerCarton = Number(unitsPerCarton || 0)
  const normalizedOrderQuantity = Number(orderQuantity || 0)
  if (normalizedUnitsPerCarton <= 0 || normalizedOrderQuantity <= 0) return 0
  const result = normalizedOrderQuantity / normalizedUnitsPerCarton
  const nearestInteger = Math.round(result)
  return Math.abs(result - nearestInteger) < 1e-8 ? nearestInteger : Math.ceil(result)
}

function formatRequiredQuantity(unitsPerCarton: number | null | '', orderQuantity: number | null | '') {
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 }).format(
    calculateRequiredQuantity(unitsPerCarton, orderQuantity),
  )
}

function orderRowSourceLine(order: CartonOrderRow, material: CartonMaterialLine) {
  return orderRecords.value
    .find((record) => record.order_no === order.id)
    ?.lines.find((line) => line.id === material.id)
}

function orderRowMaterialQuantity(order: CartonOrderRow, material: CartonMaterialLine) {
  const sourceLine = orderRowSourceLine(order, material)
  return sourceLine
    ? Number(sourceLine.required_quantity || 0)
    : calculateRequiredQuantity(material.unitsPerCarton, order.orderQuantity)
}

function orderRowMaterialReceivedQuantity(order: CartonOrderRow, material: CartonMaterialLine) {
  const sourceLine = orderRowSourceLine(order, material)
  if (sourceLine) return Number(sourceLine.received_quantity || 0)
  return order.status === '已完成' ? orderRowMaterialQuantity(order, material) : 0
}

function materialDisplayUnit(material: CartonMaterialLine) {
  return material.packagingType.includes('箱') ? '箱' : (material.unit || '个')
}

function orderPaperItemQuantity(order: CartonOrderRow) {
  return order.materials
    .reduce((total, material) => total + orderRowMaterialQuantity(order, material), 0)
}

function orderPaperItemReceivedQuantity(order: CartonOrderRow) {
  return order.materials
    .reduce((total, material) => total + orderRowMaterialReceivedQuantity(order, material), 0)
}

function orderPaperItemRemainingQuantity(order: CartonOrderRow) {
  return Math.max(0, orderPaperItemQuantity(order) - orderPaperItemReceivedQuantity(order))
}

function orderPaperItemProgress(order: CartonOrderRow) {
  const required = orderPaperItemQuantity(order)
  if (required <= 0) return 0
  return Math.min(100, Math.round((orderPaperItemReceivedQuantity(order) / required) * 100))
}

function orderMaterialBreakdown(order: CartonOrderRow) {
  const grouped = new Map<string, { packagingType: string; quantity: number; unit: string }>()
  for (const material of order.materials) {
    const unit = materialDisplayUnit(material)
    const key = `${material.packagingType}\u0000${unit}`
    const current = grouped.get(key) ?? { packagingType: material.packagingType, quantity: 0, unit }
    current.quantity += orderRowMaterialQuantity(order, material)
    grouped.set(key, current)
  }
  return [...grouped.values()]
}

function orderDetailSourceLine(material: CartonMaterialLine) {
  return orderDetailRecord.value?.lines.find((line) => line.id === material.id) ?? null
}

function orderDetailRequiredQuantity(material: CartonMaterialLine) {
  const sourceLine = orderDetailSourceLine(material)
  return sourceLine
    ? Number(sourceLine.required_quantity || 0)
    : calculateRequiredQuantity(material.unitsPerCarton, orderDetailRow.value?.orderQuantity ?? 0)
}

function orderDetailReceivedQuantity(material: CartonMaterialLine) {
  return Number(orderDetailSourceLine(material)?.received_quantity || 0)
}

function orderDetailRemainingQuantity(material: CartonMaterialLine) {
  const sourceLine = orderDetailSourceLine(material)
  return sourceLine
    ? Number(sourceLine.remaining_quantity || 0)
    : Math.max(0, orderDetailRequiredQuantity(material) - orderDetailReceivedQuantity(material))
}

function orderDetailProgress(material: CartonMaterialLine) {
  const required = orderDetailRequiredQuantity(material)
  if (required <= 0) return 0
  return Math.min(100, Math.round((orderDetailReceivedQuantity(material) / required) * 100))
}

function formatMoney(value: number, currency = 'CNY') {
  const normalizedCurrency = currency.trim().toUpperCase() || 'CNY'
  try {
    return new Intl.NumberFormat(normalizedCurrency === 'HKD' ? 'zh-HK' : 'zh-CN', {
      style: 'currency',
      currency: normalizedCurrency,
      currencyDisplay: 'symbol',
      minimumFractionDigits: 2,
    }).format(value)
  } catch {
    return `${normalizedCurrency} ${new Intl.NumberFormat('zh-CN', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value)}`
  }
}

function importMatchLabel(status?: CartonImportPreviewRow['match_status']) {
  return ({
    MATCHED: '已匹配',
    MISSING_ORDER: '未找到订单',
    QUANTITY_MISMATCH: '数量不一致',
    AMBIGUOUS: '匹配不唯一',
  } as Record<string, string>)[status ?? ''] ?? '待人工复核'
}

function importMatchTone(status?: CartonImportPreviewRow['match_status']) {
  if (status === 'MATCHED') return 'bg-emerald-50 text-emerald-700 ring-emerald-200'
  if (status === 'QUANTITY_MISMATCH' || status === 'AMBIGUOUS') return 'bg-amber-50 text-amber-700 ring-amber-200'
  return 'bg-red-50 text-red-700 ring-red-200'
}

function importQuantityLabel(row: CartonImportPreviewRow) {
  const value = Number(row.delivered_quantity ?? row.quantity ?? 0)
  return value > 0 ? formatNumber(value) : '待复核'
}

function businessTodayIso() {
  return new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
}

function formatMonthDay(value?: string | null) {
  if (!value) return ''
  const match = value.match(/^\d{4}-(\d{2})-(\d{2})/)
  return match ? `${match[1]}/${match[2]}` : value
}

function dateOffsetIso(value: string, days: number) {
  const parsed = new Date(`${value}T00:00:00Z`)
  if (!Number.isFinite(parsed.getTime())) return ''
  parsed.setUTCDate(parsed.getUTCDate() + days)
  return parsed.toISOString().slice(0, 10)
}

function calendarDayDifference(fromDate: string, toDate: string) {
  const from = Date.parse(`${fromDate}T00:00:00Z`)
  const to = Date.parse(`${toDate}T00:00:00Z`)
  if (!Number.isFinite(from) || !Number.isFinite(to)) return null
  return Math.round((to - from) / 86_400_000)
}

function derivePlanDueDate(orderDate: string, customerDueDate: string, lead = DEFAULT_CARTON_SAFETY_LEAD_DAYS) {
  const leadAdjustedDate = dateOffsetIso(customerDueDate, -lead)
  if (!orderDate || !leadAdjustedDate) return ''
  return leadAdjustedDate < orderDate ? orderDate : leadAdjustedDate
}

function safetyLeadWarning(orderDate: string, customerDueDate: string, lead = DEFAULT_CARTON_SAFETY_LEAD_DAYS) {
  if (!orderDate || !customerDueDate) return ''
  const availableDays = calendarDayDifference(orderDate, customerDueDate)
  if (availableDays === null || availableDays < 0 || availableDays >= lead) return ''
  return `客户交期距下单仅 ${availableDays} 天，不足默认 ${lead} 天安全提前量；计划交期已设为下单当天，请重点跟进。`
}

watch(showOrderModal, open => { if (open && apiConnected.value) void refreshMaster() })
watch([() => orderForm.customerCode, () => orderForm.itemNo], () => { if (chosenMaster.value && (chosenMaster.value.code !== orderForm.itemNo)) chosenMaster.value = null })
const BUSINESS_IDENTIFIER_RE = /^[0-9A-Za-z\u4e00-\u9fff](?:[0-9A-Za-z\u4e00-\u9fff._/#()（）+& -]*[0-9A-Za-z\u4e00-\u9fff])?$/

function orderFormMemoryKey(factoryId = selectedFactoryId.value) {
  return `carton-order-form-memory:${factoryId}`
}

function readOrderFormMemory(): Pick<OrderFormMaterialLine, 'packagingType' | 'paperQuality' | 'specification' | 'unitsPerCarton' | 'unit'> | null {
  try {
    const raw = window.localStorage.getItem(orderFormMemoryKey())
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<OrderFormMaterialLine>
    if (!parsed.paperQuality || !parsed.specification) return null
    return {
      packagingType: parsed.packagingType || '外箱',
      paperQuality: parsed.paperQuality,
      specification: parsed.specification,
      unitsPerCarton: Number(parsed.unitsPerCarton || 1),
      unit: parsed.unit || '个',
    }
  } catch {
    return null
  }
}

function rememberOrderFormMaterial() {
  if (orderForm.quantityBasis === 'EXPLICIT') return
  const material = orderForm.materials[0]
  if (!material?.paperQuality.trim() || !material.specification.trim()) return
  window.localStorage.setItem(orderFormMemoryKey(), JSON.stringify({
    packagingType: material.packagingType,
    paperQuality: material.paperQuality.trim(),
    specification: material.specification.trim(),
    unitsPerCarton: Number(material.unitsPerCarton),
    unit: material.unit,
  }))
}

function dueDayDelta(dueDate: string) {
  const today = Date.parse(`${businessTodayIso()}T00:00:00Z`)
  const due = Date.parse(`${dueDate}T00:00:00Z`)
  return Number.isFinite(due) ? Math.round((due - today) / 86_400_000) : null
}

function orderDueReminder(order: CartonOrderRow): OrderDueReminder {
  if (order.status === '已完成' || order.status === '已取消') {
    return { level: 'CLOSED', label: order.status === '已完成' ? '交付已完成' : '订单已取消', days: null, priority: 5 }
  }
  const days = dueDayDelta(order.dueDate)
  if (days === null) return { level: 'INVALID', label: '交期待确认', days: null, priority: 4 }
  if (days < 0) return { level: 'OVERDUE', label: `已逾期 ${Math.abs(days)} 天`, days, priority: 0 }
  if (days === 0) return { level: 'TODAY', label: '今日交期', days, priority: 1 }
  if (days === 1) return { level: 'DUE_SOON', label: '明日交期', days, priority: 2 }
  if (days <= 3) return { level: 'DUE_SOON', label: `剩 ${days} 天`, days, priority: 2 }
  return { level: 'UPCOMING', label: `距交期 ${days} 天`, days, priority: 3 }
}

function orderTone(status: string): CartonTone {
  if (status === 'COMPLETED' || status === 'PENDING_SUPPLIER') return 'green'
  if (status === 'CONFIRMED') return 'teal'
  if (status === 'PARTIALLY_RECEIVED') return 'blue'
  if (status === 'CANCELLED') return 'red'
  if (status === 'DRAFT') return 'slate'
  return 'amber'
}

function orderStatusLabel(status: string) {
  return ({
    DRAFT: '草稿',
    PENDING_SUPPLIER: '已确认锁定',
    CONFIRMED: '待下单',
    PARTIALLY_RECEIVED: '部分收料',
    COMPLETED: '已完成',
    CANCELLED: '已取消',
  } as Record<string, string>)[status] ?? status
}

function rawOrderStatus(orderNo: string) {
  return orderRecords.value.find((order) => order.order_no === orderNo)?.status ?? ''
}

function canEditConfirmedOrder(orderNo: string) {
  return rawOrderStatus(orderNo) === 'CONFIRMED'
}

const replenishPositions = computed(() => {
  const ids = new Set(replenishTarget.value?.lines.map(line => line.id) || [])
  return localInventoryBalances.filter(row => row.orderLineId && ids.has(row.orderLineId) && row.balance > 0 && row.locationId)
})
function canReplenishOrder(orderNo: string) {
  return canIssuePurchaseOrders.value && canWriteCartonInventory.value
    && ['PARTIALLY_RECEIVED', 'COMPLETED'].includes(rawOrderStatus(orderNo))
}
function openReplenishOrder(orderNo: string) {
  if (!canReplenishOrder(orderNo)) return
  replenishTarget.value = orderRecords.value.find(row => row.order_no === orderNo) || null
  replenishResponsibility.value = ''; replenishReason.value = ''; replenishQuantities.value = {}; replenishError.value = ''
}
async function submitReplenishment() {
  const order = replenishTarget.value
  if (!order || replenishing.value || !apiConnected.value) return
  if (!replenishResponsibility.value) { replenishError.value = '请选择责任方：我方问题或供应商问题。'; return }
  const positions = replenishPositions.value.filter(row => Number(replenishQuantities.value[row.id]) > 0)
  if (!positions.length || replenishPositions.value.some(row => {
    const value = Number(replenishQuantities.value[row.id] || 0)
    return !Number.isFinite(value) || value < 0 || value > row.balance
  })) { replenishError.value = '请填写至少一项补单数量，且不能超过对应仓位库存。'; return }
  const factoryId = selectedFactoryId.value
  replenishing.value = true; replenishError.value = ''
  try {
    const result = await cartonProcurementApi.replenishOrder(factoryId, order, replenishResponsibility.value, replenishReason.value.trim(), positions.map(row => ({
      order_line_id: row.orderLineId!, location_id: row.locationId!, quantity: Number(replenishQuantities.value[row.id]),
    })))
    if (selectedFactoryId.value !== factoryId) return
    replenishTarget.value = null
    await loadBackendData()
    if (selectedFactoryId.value === factoryId) actionMessage.value = apiConnected.value
      ? `补单 ${result.issue.document_no} 已生成并自动出库；原订单数量不变，补货到仓后在收料入库登记。采购单中可下载补单。`
      : `补单 ${result.issue.document_no} 已提交，列表刷新失败，请点击刷新；不要重复下单。`
  } catch (error) {
    if (selectedFactoryId.value === factoryId) {
      if (replenishTarget.value) replenishError.value = getApiErrorMessage(error)
      else actionMessage.value = '补单已提交，列表刷新失败，请点击刷新；不要重复下单。'
    }
  } finally { replenishing.value = false }
}

function canDeleteHistoryOrder(orderNo: string) {
  return canIssuePurchaseOrders.value && Boolean(orderRecords.value.find(order => order.order_no === orderNo)?.can_delete_history)
}

async function deleteHistoryOrder() {
  const orders = deleteHistoryTarget.value ? [deleteHistoryTarget.value] : deleteHistoryTargets.value
  if (!orders.length || deletingHistory.value || deleteHistoryReason.value.trim().length < 4) return
  const factoryId = selectedFactoryId.value
  deletingHistory.value = true
  try {
    if (deleteHistoryTarget.value) await cartonProcurementApi.deleteHistoryOrder(factoryId, orders[0]!, deleteHistoryReason.value.trim())
    else await cartonProcurementApi.bulkDeleteHistoryOrders(factoryId, orders, deleteHistoryReason.value.trim())
    if (selectedFactoryId.value !== factoryId) return
    deleteHistoryTarget.value = null
    deleteHistoryTargets.value = []
    selectedOrderNos.value = selectedOrderNos.value.filter(id => !orders.some(order => order.order_no === id))
    orderRecords.value = orderRecords.value.filter(order => !orders.some(deleted => deleted.id === order.id))
    localOrders.splice(0, localOrders.length, ...orderRecords.value.map(mapOrder))
    await loadBackendData(factoryId, { supersede: true })
    if (selectedFactoryId.value !== factoryId) return
    actionMessage.value = apiConnected.value
      ? `${orders.length} 张历史订单已删除，删除前明细已保留在操作日志。`
      : `${orders.length} 张历史订单已删除，但台账刷新失败，请刷新页面；不要重复删除。`
  } catch (error) {
    if (selectedFactoryId.value === factoryId) actionMessage.value = `历史订单未删除：${getApiErrorMessage(error)}`
  } finally { deletingHistory.value = false }
}

function canAppendOrder(orderNo: string) {
  const status = rawOrderStatus(orderNo)
  return canIssuePurchaseOrders.value && (status === 'CONFIRMED'
    || (['PENDING_SUPPLIER', 'PARTIALLY_RECEIVED', 'COMPLETED'].includes(status) && canAdjustSubmittedOrders.value))
}

function pendingReceiptQuantity(orderLineId: string) {
  return receiptRecords.value.reduce((total, receipt) => {
    if (receipt.status !== 'PENDING_CONFIRMATION') return total
    return total + receipt.lines.reduce((lineTotal, line) => (
      line.order_line_id === orderLineId ? lineTotal + Number(line.effective_quantity || 0) : lineTotal
    ), 0)
  }, 0)
}

function maximumReducibleProductQuantity(order: CartonOrderResponse) {
  if (order.quantity_basis === 'EXPLICIT') return order.lines.reduce((sum, line) => sum + Math.max(0, Number(line.maximum_reducible_quantity ?? Number(line.required_quantity) - Number(line.received_quantity) - pendingReceiptQuantity(line.id))), 0)
  if (order.maximum_reducible_quantity !== undefined) {
    return Math.max(0, Number(order.maximum_reducible_quantity))
  }
  const protectedProductQuantity = order.lines.reduce((maximum, line) => {
    const protectedPaperQuantity = Number(line.received_quantity || 0) + pendingReceiptQuantity(line.id)
    if (protectedPaperQuantity <= 0) return maximum
    const unitsPerCarton = Number(line.usage_quantity || 0)
    return Math.max(maximum, protectedPaperQuantity * unitsPerCarton)
  }, 0)
  return Math.max(0, Number(order.product_order_quantity) - protectedProductQuantity)
}

function canReduceSubmittedOrder(orderNo: string) {
  const order = orderRecords.value.find((item) => item.order_no === orderNo)
  return Boolean(
    order
    && ['PENDING_SUPPLIER', 'PARTIALLY_RECEIVED'].includes(order.status)
    && canAdjustSubmittedOrders.value
    && maximumReducibleProductQuantity(order) > 0,
  )
}

function canReceiveOrder(orderNo: string) {
  return ['PENDING_SUPPLIER', 'PARTIALLY_RECEIVED'].includes(rawOrderStatus(orderNo))
}

function canReturnOrder(orderNo: string) {
  return ['PARTIALLY_RECEIVED', 'COMPLETED'].includes(rawOrderStatus(orderNo))
}

function mapOrder(row: CartonOrderResponse): CartonOrderRow {
  return {
    id: row.order_no,
    orderDate: row.order_date,
    customerDueDate: row.customer_due_date,
    safetyLeadDays: row.safety_lead_days ?? DEFAULT_CARTON_SAFETY_LEAD_DAYS,
    customer: row.customer_name,
    contractNo: row.contract_no,
    itemNo: row.item_no,
    orderQuantity: row.product_order_quantity == null ? null : Number(row.product_order_quantity),
    materials: row.lines.map((line) => ({
      id: line.id,
      packagingType: line.packaging_type,
      paperQuality: line.paper_quality,
      specification: `${line.specification}${line.dimension_unit ? ` ${line.dimension_unit}` : ''}`,
      unitsPerCarton: line.usage_quantity == null ? null : Number(line.usage_quantity),
      unit: line.unit,
    })),
    dueDate: row.due_date,
    status: orderStatusLabel(row.status),
    tone: orderTone(row.status),
    note: row.note,
  }
}

function inventoryQuantity(value?: string | null) {
  return value == null || !Number.isFinite(Number(value)) ? '—' : Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 4 })
}
function inventoryQuantityNotes(row?: Partial<CartonInventoryBalanceResponse>) {
  return ([['期初', row?.opening_quantity], ['调仓净额', row?.transfer_quantity], ['调整', row?.adjustment_quantity]] as const)
    .filter(([, value]) => value != null && Number(value) !== 0)
    .map(([label, value]) => `${label} ${label !== '期初' && Number(value) > 0 ? '+' : ''}${inventoryQuantity(value)} ${row?.unit || ''}`)
}

const showInventoryMoney = ref(false)
const inventoryMoneySummary = computed(() => moneyTotals(inventoryBalances.value.map(row => row.money)))
const outboundMoneySummary = computed(() => moneyTotals(inventoryBulkMode.value
  ? selectedInventoryBalances.value.map(row => estimateMoney(row.money, inventoryBulkQuantities.value[row.id] || ''))
  : [estimateMoney(selectedInventoryBalance.value?.money, inventoryOperationQuantity.value)]))

function mapMovement(row: CartonInventoryMovementResponse) {
  const movementType = row.source_type === 'HISTORY_INVENTORY'
    ? '期初' as const
    : row.movement_type === 'INBOUND'
    ? '入库' as const
    : row.movement_type === 'OUTBOUND'
      ? '出库' as const
      : row.movement_type === 'REVERSAL'
        ? '冲销' as const
        : '调整' as const
  return {
    id: row.id,
    date: row.occurred_at.replace('T', ' ').slice(0, 16),
    documentNo: row.document_no,
    customer: row.customer_name,
    poNumber: row.contract_no,
    itemNo: row.item_no,
    packagingType: row.packaging_type,
    paperQuality: row.paper_quality,
    specification: row.specification,
    movementType,
    quantity: Number(row.quantity),
    balance: Number(row.balance),
    location: row.location,
    operator: row.actor_name,
    source: row.source_type === 'RECEIPT'
      ? '收料反馈'
      : row.source_type === 'HISTORY_INVENTORY'
        ? '历史库存导入'
        : [row.reason, row.workshop_name ? `领用车间：${row.workshop_name}` : ''].filter(Boolean).join('；'),
    money: row,
    rawMovementType: row.movement_type,
    sourceType: row.source_type,
    reversalOfMovementId: row.reversal_of_movement_id,
  }
}

function mapInventoryBalance(row: CartonInventoryBalanceResponse): InventoryBalanceRow {
  return {
    money: row,
    id: row.position_key || row.inventory_key || row.order_line_id || JSON.stringify([
      row.customer_code,
      row.contract_no,
      row.item_no,
      row.packaging_type,
      row.paper_quality,
      row.specification,
      row.unit,
    ]),
    customer: row.customer_name,
    poNumber: row.contract_no,
    itemNo: row.item_no,
    packagingType: row.packaging_type,
    paperQuality: row.paper_quality,
    specification: row.specification,
    unit: row.unit,
    orderLineId: row.order_line_id,
    latestMovementId: row.latest_movement_id,
    latestDocumentNo: row.latest_document_no
      || localMovements.find((movement) => movement.id === row.latest_movement_id)?.documentNo
      || '',
    balance: Number(row.balance),
    location: row.latest_location,
    date: row.latest_movement_at.replace('T', ' ').slice(0, 16),
    inboundDate: row.latest_inbound_at?.replace('T', ' ').slice(0, 16) ?? '',
    locationRevision: row.location_revision ?? 0,
    locationId: row.location_id, warehouse: row.warehouse, positionRevision: row.position_revision,
  }
}

function mapClosing(row: CartonClosingResponse) {
  const status = ({ DRAFT: '草稿', PENDING: '待核对', CONFIRMED: '已核对确认', LOCKED: '已锁账' } as Record<string, string>)[row.status] ?? row.status
  const tone: CartonTone = row.status === 'LOCKED' || row.status === 'CONFIRMED'
    ? 'green'
    : row.status === 'PENDING'
      ? 'amber'
      : 'slate'
  return {
    id: row.id,
    customer: row.customer_name,
    period: row.period,
    openingQuantity: Number(row.opening_quantity),
    inboundQuantity: Number(row.inbound_quantity),
    outboundQuantity: Number(row.outbound_quantity),
    adjustmentQuantity: Number(row.adjustment_quantity),
    endingQuantity: Number(row.ending_quantity),
    endingAmount: Number(row.ending_amount),
    currency: row.currency,
    status,
    tone,
  }
}

function mapWeeklyPreview(row: CartonImportPreviewRow, index: number): WeeklyCheckRow {
  const result = ({
    MATCHED: '已匹配',
    MISSING_ORDER: '疑似漏单',
    QUANTITY_MISMATCH: '数量差异',
    AMBIGUOUS: '待人工选择',
    REVIEW_REQUIRED: '待人工确认',
    DATE_MISMATCH: '交期差异',
  } as Record<string, string>)[row.match_status ?? ''] ?? '待核对'
  const tone: CartonTone = row.match_status === 'MATCHED'
    ? 'green'
    : row.match_status === 'MISSING_ORDER'
      ? 'red'
      : 'amber'
  return {
    id: `WK-${row.source_sheet ?? 'S'}-${row.source_row ?? index + 1}`,
    orderType: row.order_type,
    sourceReference: row.source_reference,
    sourceLocation: row.source_sheet ? `${row.source_sheet} · 第 ${row.source_row} 行` : '',
    customerDueDate: row.customer_due_date || row.source_customer_due_date,
    dateReviewRequired: row.date_review_required,
    procurementState: ({ NEEDS_ORDER: '需要下单', ORDERED: '已下单', COMPLETED: '已完单', REVIEW: '待确认' } as Record<string, string>)[row.procurement_state ?? ''] ?? (row.template ? '待确认' : ''),
    quantityMissing: row.quantity === null || row.quantity === undefined,
    businessCustomer: row.source_customer_name,
    reference: row.reference ?? row.contract_no ?? '',
    poNumbers: row.po_numbers ?? '',
    customer: row.customer_name || '待识别客户',
    itemNo: row.item_no ?? '',
    productName: row.product_name ?? '',
    quantity: Number(row.quantity ?? 0),
    cartonRule: row.carton_rule ?? '',
    inspectionWindow: row.inspection_window || row.source_inspection_window || '',
    result,
    tone,
    linkedOrder: row.order_no ?? '—',
    suggestion: row.suggestion ?? '请人工复核',
  }
}

function mapException(row: CartonExceptionResponse): CartonExceptionRow {
  const tone: CartonTone = row.severity === 'HIGH' ? 'red' : row.severity === 'MEDIUM' ? 'amber' : 'blue'
  const status = ({ OPEN: '待处理', IN_PROGRESS: '处理中', RESOLVED: '已解决', CLOSED: '已关闭' } as Record<string, string>)[row.status] ?? row.status
  return {
    id: row.exception_no,
    customer: row.customer_name || '待识别客户',
    type: ({
      MISSING_ORDER: '疑似漏单',
      RECEIPT_UNMATCHED: '收料未匹配',
      QUANTITY_MISMATCH: '数量差异',
      SCHEDULE_DATE_MISMATCH: '业务交期差异',
      SCHEDULE_REVIEW_REQUIRED: '业务明细待确认',
      AMBIGUOUS_MATCH: '匹配不唯一',
      ORDER_APPENDED: '追单提醒',
      INSPECTION_ORDER_MISSING: '查货合同漏单',
      INSPECTION_ORDER_AMBIGUOUS: '查货订单待关联',
      INSPECTION_DATE_INVALID: '验货日期待补充',
      INSPECTION_DELIVERY_OVERDUE: '纸箱交货逾期',
      INSPECTION_DELIVERY_DUE: '纸箱交货临近',
      INSPECTION_DELIVERY_REMINDER: '纸箱提前交货提醒',
    } as Record<string, string>)[row.category] ?? row.category,
    title: row.title,
    detail: [row.contract_no, row.item_no, row.description].filter(Boolean).join(' · '),
    owner: row.owner_department,
    deadline: `创建于 ${row.created_at.replace('T', ' ').slice(0, 16)}`,
    status,
    tone: row.status === 'CLOSED' ? 'slate' : tone,
  }
}

function applyReceiptImport(batch: CartonImportBatchResponse) {
  const preserveAcceptanceDate = receiptBatchId.value === batch.id && !currentReceipt.value
  const rows = batch.parse_summary.rows ?? []
  receiptEntryMode.value = 'IMPORT'
  receiptFeedbackMessage.value = ''
  receiptPage.value = 'IMPORT'
  manualReceiptOrderNos.value = []
  receiptImportBatch.value = batch
  receiptImportRows.value = rows
  const matched = rows.filter((row) => row.match_status === 'MATCHED' && row.order_line_id)
  const deliveryNumbers = [...new Set(matched.map((row) => row.delivery_note_no).filter(Boolean))] as string[]
  const selectedDeliveryNo = deliveryNumbers[0]
    ?? batch.parse_summary.document?.delivery_note_no
    ?? `IMPORT-${batch.id.slice(-8).toUpperCase()}`
  const selectedRows = matched.filter((row) => !row.delivery_note_no || row.delivery_note_no === selectedDeliveryNo)
  receiptLines.splice(0, receiptLines.length, ...selectedRows.map((row, index) => ({
    id: receiptImportLineId(batch.id, row, index),
    orderNo: `${row.order_no ?? ''} · ${row.contract_no ?? ''}-${row.item_no ?? ''}`,
    description: `${row.packaging_type ?? '待复核'} ${row.paper_quality ?? ''}`.trim(),
    specification: row.specification ?? '',
    deliveryQuantity: Number(row.delivered_quantity ?? 0),
    unitPrice: Number(row.unit_price ?? 0),
    receivedQuantity: Number(row.delivered_quantity ?? 0),
    damagedQuantity: 0,
    rejectedQuantity: 0,
    unusableQuantity: 0,
    sourceType: 'FORMAL_ORDER' as const,
    orderLineId: row.order_line_id ?? '',
    customerCode: row.customer_code ?? '',
    contractNo: row.contract_no ?? row.reference ?? '',
    itemNo: row.item_no ?? '',
    packagingType: row.packaging_type ?? '',
    paperQuality: row.paper_quality ?? '',
    unit: row.unit ?? '个',
    currency: 'CNY',
    location: row.location ?? '',
    sourceLabel: `${row.source_sheet ?? 'OCR'} 第 ${row.source_row ?? index + 1} 行`,
    remainingQuantity: 0,
  })))
  if (!preserveAcceptanceDate) receiptAcceptanceDate.value = businessTodayIso()
  receiptBatchId.value = batch.id
  receiptDeliveryNoteNo.value = selectedDeliveryNo
  receiptDeliveryDate.value = rows.find((row) => row.delivery_date)?.delivery_date
    ?? batch.parse_summary.document?.delivery_date
    ?? new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
  currentReceipt.value = null
  const extraDocuments = Math.max(0, deliveryNumbers.length - 1)
  actionMessage.value = `送货单识别完成：共 ${batch.parse_summary.row_count ?? rows.length} 行，已匹配 ${batch.parse_summary.matched_count ?? matched.length} 行，${batch.parse_summary.issue_count ?? 0} 行需要人工处理。${extraDocuments ? `本次还包含 ${extraDocuments} 张其他送货单，请分批复核。` : ''}`
}

function receiptImportLineId(batchId: string, row: CartonImportPreviewRow, index: number) {
  return `${batchId}-${row.source_sheet ?? 'ROW'}-${row.source_row ?? index + 1}`
}

function receiptImportRowAdded(row: CartonImportPreviewRow, index: number) {
  if (!receiptImportBatch.value) return false
  return receiptLines.some((line) => line.id === receiptImportLineId(receiptImportBatch.value!.id, row, index))
}

function addAdHocReceiptLine(row: CartonImportPreviewRow, index: number) {
  const batch = receiptImportBatch.value
  if (!batch || row.match_status !== 'MISSING_ORDER') return
  const id = receiptImportLineId(batch.id, row, index)
  if (receiptLines.some((line) => line.id === id)) return
  const matchedCustomer = activeCustomers.value.find((customer) =>
    (row.customer_code && customer.customer_code === row.customer_code)
    || (row.customer_name && businessIdentity(customer.customer_name) === businessIdentity(row.customer_name)),
  )
  receiptLines.push({
    id,
    orderNo: '非正式 / 打板收料',
    description: `${row.packaging_type ?? ''} ${row.paper_quality ?? ''}`.trim(),
    specification: row.specification ?? '',
    deliveryQuantity: Number(row.delivered_quantity ?? row.quantity ?? 0),
    unitPrice: Number(row.unit_price ?? 0),
    receivedQuantity: Number(row.delivered_quantity ?? row.quantity ?? 0),
    damagedQuantity: 0,
    rejectedQuantity: 0,
    unusableQuantity: 0,
    sourceType: 'AD_HOC',
    orderLineId: '',
    customerCode: matchedCustomer?.customer_code ?? '',
    contractNo: row.contract_no ?? row.reference ?? '',
    itemNo: row.item_no ?? '',
    packagingType: row.packaging_type ?? '',
    paperQuality: row.paper_quality ?? '',
    unit: row.unit ?? '个',
    currency: 'CNY',
    location: row.location ?? '',
    sourceLabel: `非正式收料 · ${row.source_sheet ?? '文件'} 第 ${row.source_row ?? index + 1} 行`,
    remainingQuantity: 0,
  })
  currentReceipt.value = null
  receiptFeedbackMessage.value = ''
  showReceiptDialog.value = true
  actionMessage.value = '已把未匹配明细加入非正式/打板收料；请补齐客户与物料信息，核对无误后点击“确认入库”即可入库并计入月结。'
}

function removeAdHocReceiptLine(lineId: string) {
  const index = receiptLines.findIndex((line) => line.id === lineId && line.sourceType === 'AD_HOC')
  if (index < 0 || currentReceipt.value) return
  receiptLines.splice(index, 1)
  receiptFeedbackMessage.value = ''
}

async function loadBackendData(factoryId = selectedFactoryId.value, options: { supersede?: boolean } = {}) {
  // Successful destructive writes must invalidate any pre-write read already in flight.
  if (!options.supersede && backendLoading.value && backendLoadFactory === factoryId) return
  const generation = ++backendLoadGeneration
  backendLoadFactory = factoryId
  backendLoading.value = true
  try {
    const [
      customers,
      orders,
      movements,
      balances,
      closings,
      exceptions,
      latestReceiptImport,
      receipts,
      weeklyImports,
      inspectionImports,
      audits,
    ] = await Promise.all([
      cartonProcurementApi.listCustomers(factoryId),
      cartonProcurementApi.listOrders(factoryId),
      cartonProcurementApi.listMovements(factoryId),
      cartonProcurementApi.listInventoryBalances(factoryId),
      cartonProcurementApi.listClosings(factoryId),
      cartonProcurementApi.listExceptions(factoryId),
      cartonProcurementApi.latestReceiptImport(factoryId),
      cartonProcurementApi.listReceipts(factoryId),
      cartonProcurementApi.listImports(factoryId, 'WEEKLY_SCHEDULE'),
      cartonProcurementApi.listImports(factoryId, 'INSPECTION_SCHEDULE'),
      cartonProcurementApi.listAuditEvents(factoryId),
    ])
    if (factoryId !== selectedFactoryId.value || generation !== backendLoadGeneration) return
    customerRecords.value = customers
    orderRecords.value = orders
    if (!customers.some((customer) => customer.status === 'ACTIVE' && customer.customer_code === orderForm.customerCode)) {
      orderForm.customerCode = customers.find((customer) => customer.status === 'ACTIVE')?.customer_code ?? ''
    }
    localOrders.splice(0, localOrders.length, ...orders.map(mapOrder))
    localMovements.splice(0, localMovements.length, ...movements.map(mapMovement))
    localInventoryBalances.splice(0, localInventoryBalances.length, ...balances.map(mapInventoryBalance))
    localClosings.splice(0, localClosings.length, ...closings.map(mapClosing))
    closingRecords.value = closings
    exceptionRecords.value = exceptions
    localExceptions.splice(0, localExceptions.length, ...exceptions.map(mapException))
    receiptRecords.value = receipts
    weeklyImportHistory.value = weeklyImports
    inspectionImportHistory.value = inspectionImports
    inventoryReportRefreshKey.value += 1
    auditRecords.value = audits
    if (weeklyImports.find(batch => batch.id === selectedWeeklyBatchId.value)?.status === 'REJECTED') {
      selectedWeeklyFileName.value = ''; selectedWeeklyBatchId.value = ''; localWeeklyChecks.splice(0)
    }
    if (inspectionImports.find(batch => batch.id === selectedInspectionBatchId.value)?.status === 'REJECTED') {
      selectedInspectionFileName.value = ''; selectedInspectionBatchId.value = ''; localInspectionChecks.splice(0)
    }
    if (!selectedWeeklyFileName.value) {
      const active = weeklyImports.find(batch => batch.status !== 'REJECTED')
      if (active) restoreWeeklyImport(active)
      else localWeeklyChecks.splice(0)
    }
    if (!selectedInspectionFileName.value) {
      const active = inspectionImports.find(batch => batch.status !== 'REJECTED')
      if (active) restoreInspectionImport(active)
      else localInspectionChecks.splice(0)
    }
    if (receiptEntryMode.value === 'MANUAL' && !manualReceiptOrderNos.value.length && !currentReceipt.value) {
      receiptLines.splice(0)
    }
    if (receiptEntryMode.value === 'IMPORT' && !receiptBatchId.value) {
      receiptLines.splice(0)
      receiptDeliveryNoteNo.value = ''
      receiptDeliveryDate.value = ''
      receiptAcceptanceDate.value = businessTodayIso()
      if (latestReceiptImport) {
        selectedReceiptFileName.value = latestReceiptImport.original_filename
        const page = receiptPage.value
        applyReceiptImport(latestReceiptImport)
        receiptPage.value = page
      }
    }
    await refreshLocations()
    if (factoryId !== selectedFactoryId.value || generation !== backendLoadGeneration) return
    void refreshMaster()
    apiConnected.value = true
    actionMessage.value = receiptEntryMode.value === 'IMPORT' && latestReceiptImport && activeTab.value === 'receipts'
      ? `已恢复最近送货单导入：共 ${latestReceiptImport.parse_summary.row_count ?? 0} 行，已匹配 ${latestReceiptImport.parse_summary.matched_count ?? 0} 行，${latestReceiptImport.parse_summary.issue_count ?? 0} 行需要人工处理。`
      : `已连接 ${activeFactory.value.shortName} 正式台账；订单、收料导入、库存流水和月结均由后端保存。`
  } catch (error) {
    if (factoryId !== selectedFactoryId.value || generation !== backendLoadGeneration) return
    customerRecords.value = demoCustomers(factoryId)
    if (!orderForm.customerCode) orderForm.customerCode = customerRecords.value[0]?.customer_code ?? ''
    apiConnected.value = false
    actionMessage.value = `后端暂不可用，当前显示只读演示数据：${getApiErrorMessage(error)}`
  } finally {
    if (generation === backendLoadGeneration) backendLoading.value = false
  }
}

function replaceOrderState(order: CartonOrderResponse) {
  const recordIndex = orderRecords.value.findIndex((item) => item.order_no === order.order_no)
  if (recordIndex >= 0) orderRecords.value.splice(recordIndex, 1, order)
  else orderRecords.value.unshift(order)
  const rowIndex = localOrders.findIndex((item) => item.id === order.order_no)
  if (rowIndex >= 0) localOrders.splice(rowIndex, 1, mapOrder(order))
  else localOrders.unshift(mapOrder(order))
}

async function createLocalOrder() {
  const validMaterials = orderForm.materials.filter((material) =>
    material.packagingType.trim()
    && (orderForm.quantityBasis === 'EXPLICIT' ? Number(material.requiredQuantity) > 0 : material.paperQuality.trim() && material.specification.trim() && Number(material.unitsPerCarton) > 0),
  )
  const currentOrder = editingOrderRecord.value
  const selectedCustomer = selectedOrderCustomer.value
    ?? (currentOrder && currentOrder.customer_code === orderForm.customerCode ? {
      customer_code: currentOrder.customer_code,
      customer_name: currentOrder.customer_name,
    } : null)
  if (!selectedCustomer) {
    actionMessage.value = '请先搜索并选择客户；新客户须由有高级维护权限的人员核对并保存。'
    return
  }
  if (!orderForm.contractNo.trim() || !orderForm.itemNo.trim() || validMaterials.length !== orderForm.materials.length) {
    actionMessage.value = '请填写合同号、货号，并补齐每条纸品明细的类型、纸质、规格和每箱个数。'
    return
  }
  if (!BUSINESS_IDENTIFIER_RE.test(orderForm.contractNo.trim()) || !BUSINESS_IDENTIFIER_RE.test(orderForm.itemNo.trim())) {
    actionMessage.value = '合同号和货号仅允许中英文、数字、空格及 - _ . / # ( ) + &，且首尾必须为文字或数字。'
    return
  }
  if ((orderForm.quantityBasis !== 'EXPLICIT' || orderForm.orderQuantity !== '') && (!Number.isFinite(Number(orderForm.orderQuantity)) || Number(orderForm.orderQuantity) <= 0)) {
    actionMessage.value = '产品订单数量必须大于 0，系统不再预填 3600。'
    return
  }
  if (!orderForm.orderDate) {
    actionMessage.value = '请选择下单日期。'
    return
  }
  if (!currentOrder && !orderForm.customerDueDate) {
    actionMessage.value = '请选择客户交期，系统会自动生成计划交期。'
    return
  }
  if (orderForm.customerDueDate && orderForm.customerDueDate < orderForm.orderDate) {
    actionMessage.value = '客户交期不能早于下单日期。'
    return
  }
  if (!calculatedOrderDueDate.value) {
    actionMessage.value = '无法计算计划交期，请检查下单日期和客户交期。'
    return
  }
  const matchingProduct = orderRecords.value.find((order) =>
    order.item_no.trim().toLowerCase() === orderForm.itemNo.trim().toLowerCase() && order.product_name.trim(),
  )
  if (!currentOrder && !orderForm.productName.trim() && !matchingProduct) {
    actionMessage.value = '该货号尚无历史产品名称，请先填写产品名称；后续再用同一货号时会自动带出。'
    return
  }
  if (currentOrder && orderChangeReason.value.trim().length < 4) {
    actionMessage.value = '修改正式订单必须填写至少 4 个字的修改原因。'
    return
  }

  savingOrder.value = true
  try {
    const payload = {
      factory_id: selectedFactoryId.value,
      customer_code: selectedCustomer.customer_code,
      customer_name: selectedCustomer.customer_name,
      supplier_id: orderForm.supplierId || undefined,
      contract_no: orderForm.contractNo.trim(),
      customer_po: orderForm.customerPo.trim(),
      item_no: orderForm.itemNo.trim(),
      product_name: orderForm.productName.trim(),
      quantity_basis: orderForm.quantityBasis,
      product_order_quantity: orderForm.orderQuantity === '' ? null : Number(orderForm.orderQuantity),
      order_date: orderForm.orderDate,
      customer_due_date: orderForm.customerDueDate || null,
      due_date: calculatedOrderDueDate.value,
      master_config_id: chosenMaster.value?.id || '',
      master_config_revision: chosenMaster.value?.revision || 0,
      note: orderForm.note.trim(),
      lines: validMaterials.map((material) => ({
        packaging_type: material.packagingType.trim(),
        paper_quality: material.paperQuality.trim(),
        specification: material.specification.trim(),
        dimension_unit: material.dimensionUnit,
        usage_quantity: material.unitsPerCarton === '' ? null : Number(material.unitsPerCarton),
        ...(orderForm.quantityBasis === 'EXPLICIT' ? { required_quantity: Number(material.requiredQuantity) } : {}),
        unit: material.unit,
        unit_price: Number(material.unitPrice),
        currency: material.currency,
        price_source: material.priceSource,
        note: material.note,
      })),
    }
    const saved = currentOrder
      ? await cartonProcurementApi.updateOrder(currentOrder, {
        ...payload,
        reason: orderChangeReason.value.trim(),
      })
      : await cartonProcurementApi.createOrder({
        ...payload,
        status: 'CONFIRMED',
      })
    replaceOrderState(saved)
    void refreshMaster()
    rememberOrderFormMaterial()
    auditRecords.value = await cartonProcurementApi.listAuditEvents(selectedFactoryId.value)
    apiConnected.value = true
    showOrderModal.value = false
    actionMessage.value = currentOrder
      ? `正式纸箱订单 ${saved.order_no} 已按原因完成第 ${saved.revision} 版修订。`
      : `正式纸箱订单 ${saved.order_no} 已进入待下单，含 ${saved.lines.length} 条纸品明细；确认锁定前仍可修改、追加或取消。`
  } catch (error) {
    actionMessage.value = `${currentOrder ? '订单修改' : '订单新建'}失败：${getApiErrorMessage(error)}`
  } finally {
    savingOrder.value = false
  }
}

function openSubmitSupplierOrder(orderNo: string) {
  const order = orderRecords.value.find((item) => item.order_no === orderNo)
  if (!order || order.status !== 'CONFIRMED') {
    actionMessage.value = '只有待下单且尚未确认锁定的订单可以执行此操作。'
    return
  }
  bulkSubmitSupplierOrderNos.value = []
  submitSupplierOrderNo.value = orderNo
}

function openBulkSubmitSupplierOrders() {
  if (!selectedOrders.value.length) {
    actionMessage.value = '请先勾选需要确认并锁定的订单。'
    return
  }
  if (!selectedSubmittableOrderCount.value) {
    actionMessage.value = '所选订单中没有“待下单”订单。'
    return
  }
  submitSupplierOrderNo.value = ''
  bulkSubmitSupplierOrderNos.value = selectedOrders.value.map((order) => order.order_no)
}

function closeSubmitSupplierDialog() {
  submitSupplierOrderNo.value = ''
  bulkSubmitSupplierOrderNos.value = []
}

async function confirmSubmitSupplierOrder() {
  if (bulkSubmitSupplierOrderNos.value.length) {
    const selected = orderRecords.value.filter((order) => bulkSubmitSupplierOrderNos.value.includes(order.order_no))
    if (!selected.length) {
      actionMessage.value = '所选订单状态已变化，请刷新后重试。'
      closeSubmitSupplierDialog()
      return
    }
    submittingSupplierOrder.value = true
    try {
      const savedOrders = await cartonProcurementApi.bulkSubmitOrdersToSupplier(selectedFactoryId.value, selected)
      savedOrders.forEach(replaceOrderState)
      const submittedOrderNos = new Set(savedOrders.map((order) => order.order_no))
      selectedOrderNos.value = selectedOrderNos.value.filter((orderNo) => !submittedOrderNos.has(orderNo))
      const skippedCount = selected.length - savedOrders.length
      closeSubmitSupplierDialog()
      auditRecords.value = await cartonProcurementApi.listAuditEvents(selectedFactoryId.value)
      actionMessage.value = `已确认并锁定 ${savedOrders.length} 张订单${skippedCount ? `；跳过 ${skippedCount} 张非待下单订单` : ''}。`
      void refreshMaster()
    } catch (error) {
      actionMessage.value = `批量确认锁定失败：${getApiErrorMessage(error)}`
    } finally {
      submittingSupplierOrder.value = false
    }
    return
  }

  const order = orderRecords.value.find((item) => item.order_no === submitSupplierOrderNo.value)
  if (!order || order.status !== 'CONFIRMED') {
    actionMessage.value = '订单状态已变化，请刷新后重试。'
    closeSubmitSupplierDialog()
    return
  }
  submittingSupplierOrder.value = true
  try {
    const saved = await cartonProcurementApi.submitOrderToSupplier(selectedFactoryId.value, order)
    replaceOrderState(saved)
    closeSubmitSupplierDialog()
    auditRecords.value = await cartonProcurementApi.listAuditEvents(selectedFactoryId.value)
    actionMessage.value = `订单 ${saved.order_no} 已确认并锁定普通编辑；有权限的仓管或主管可追加或减单。`
    void refreshMaster()
  } catch (error) {
    actionMessage.value = `确认锁定失败：${getApiErrorMessage(error)}`
  } finally {
    submittingSupplierOrder.value = false
  }
}

function openCancelOrder(orderNo: string) {
  const order = orderRecords.value.find((item) => item.order_no === orderNo)
  if (!order || !['CONFIRMED', 'PARTIALLY_RECEIVED', 'COMPLETED'].includes(order.status)) {
    actionMessage.value = '该订单已确认锁定且尚未入库，不能取消或退单。'
    return
  }
  cancelOrderNo.value = orderNo
  cancelOrderReason.value = order.status === 'CONFIRMED' ? '客户取消订单' : ''
}

async function confirmCancelOrder() {
  const isBulk = cancelOrderNo.value === '__BULK__'
  const orders = isBulk
    ? selectedOrders.value
    : orderRecords.value.filter((item) => item.order_no === cancelOrderNo.value)
  if (!orders.length) {
    actionMessage.value = '未找到需要取消的正式订单，请刷新后重试。'
    return
  }
  if (cancelOrderReason.value.trim().length < 4) {
    actionMessage.value = '取消正式订单必须填写至少 4 个字的原因。'
    return
  }
  cancellingOrder.value = true
  try {
    const isInventoryReturn = !isBulk && ['PARTIALLY_RECEIVED', 'COMPLETED'].includes(orders[0].status)
    const cancelledOrders = isBulk
      ? await cartonProcurementApi.bulkCancelOrders(selectedFactoryId.value, orders, cancelOrderReason.value.trim())
      : [await (isInventoryReturn
        ? cartonProcurementApi.returnOrder(selectedFactoryId.value, orders[0], cancelOrderReason.value.trim())
        : cartonProcurementApi.cancelOrder(selectedFactoryId.value, orders[0], cancelOrderReason.value.trim()))]
    cancelledOrders.forEach(replaceOrderState)
    cancelOrderNo.value = ''
    cancelOrderReason.value = ''
    selectedOrderNos.value = selectedOrderNos.value.filter((orderNo) =>
      !cancelledOrders.some((order) => order.order_no === orderNo),
    )
    await loadBackendData()
    actionMessage.value = isBulk
      ? `已批量取消 ${cancelledOrders.length} 张尚未发生收发的订单，并保留审计记录。`
      : isInventoryReturn
        ? `正式纸箱订单 ${cancelledOrders[0].order_no} 已退单，相关库存已按规则转出并保留审计记录。`
        : `正式纸箱订单 ${cancelledOrders[0].order_no} 已取消并保留审计记录。`
  } catch (error) {
    actionMessage.value = `订单取消失败：${getApiErrorMessage(error)}`
  } finally {
    cancellingOrder.value = false
  }
}

function auditEventLabel(eventType: string) {
  return ({
    MASTER_DATA_SAVED: '基础资料维护',
    MASTER_LOCATION_UPDATED: '仓位资料维护',
    INVENTORY_LOCATION_CREATED: '仓位建档',
    ORDER_CREATED: '订单创建确认',
    ORDER_SUBMITTED_SUPPLIER: '确认订单并锁定',
    HISTORY_ORDER_PLACED: '历史已下单转待收料',
    HISTORY_ORDER_MATERIAL_COMPLETED: '收料补齐历史纸品资料',
    ORDER_UPDATED: '订单修改',
    ORDER_APPENDED: '追加订单',
    ORDER_REPLENISHED: '补单并出库',
    HISTORY_ORDER_DELETED: '删除历史订单',
    ORDER_REDUCED: '订单减单 / 退单',
    ORDER_CANCELLED: '订单取消',
    ORDER_RETURNED: '订单退单',
    RECEIPT_CREATED: '收料单创建',
    RECEIPT_DRAFT_CREATED: '收料草稿创建',
    RECEIPT_CONFIRMED: '收料确认入库',
    RECEIPT_REPLENISHMENT_LINKED: '补货关联补单及计费责任',
    RECEIPT_ORDINARY_CLASSIFIED: '收料确认为普通采购',
    RECEIPT_REVERSED: '收料作废 / 冲销',
    INVENTORY_MOVEMENT_CREATED: '库存流水登记',
    INVENTORY_PRICE_CONFIRMED: '入库单价核实',
    INVENTORY_LOCATION_CHANGED: '库存调仓',
    STOCKTAKE_CREATED: '生成盘点单',
    STOCKTAKE_SAVE: '盘点草稿保存',
    STOCKTAKE_CONFIRM: '盘点确认提交并入账',
    STOCKTAKE_SUBMIT: '盘点提交复核',
    STOCKTAKE_APPROVE: '盘点复核入账',
    STOCKTAKE_RETURN: '盘点退回重盘',
    STOCKTAKE_CANCEL: '盘点取消',
    INVENTORY_BULK_OUTBOUND_CREATED: '批量出库',
    INVENTORY_MOVEMENT_REVERSED: '库存流水冲销',
    HISTORY_INVENTORY_IMPORTED: '历史库存导入',
    IMPORT_BATCH_CREATED: '导入批次创建',
    SCHEDULE_IMPORT_UNDONE: '整批撤销排期导入',
    UNMATCHED_DELIVERY_IMPORT_DELETED: '未匹配送货导入删除',
    EXCEPTION_STATUS_UPDATED: '异常状态更新',
    CLOSING_GENERATED: '月结草稿生成',
    CLOSING_PENDING: '月结提交核对',
    CLOSING_CONFIRMED: '月结确认',
    CLOSING_LOCKED: '最终锁账',
    CLOSING_UNLOCKED: '主管解锁月结',
    CARTON_MARK_TEMPLATE_CREATED: '唛头模板创建',
    CARTON_MARK_TEMPLATE_RECHECKED: '唛头模板复核',
  } as Record<string, string>)[eventType] ?? eventType
}

function auditEntityLabel(row: CartonAuditEventResponse) {
  const detail = row.detail
  const orderNo = row.entity_type === 'carton_order'
    ? orderRecords.value.find((order) => order.id === row.entity_id)?.order_no
    : ''
  return String(detail.order_no || orderNo || detail.receipt_no || detail.document_no || row.entity_id)
}

function clearAuditFilters() {
  auditSearch.value = ''
  auditEventFilter.value = 'ALL'
  auditActorFilter.value = 'ALL'
  auditDateFrom.value = ''
  auditDateTo.value = ''
}

function auditDetailSummary(detail: Record<string, unknown>) {
  if (typeof detail.to_location === 'string') {
    return `${detail.customer_name || ''} · 合同 ${detail.contract_no || '—'} · 货号 ${detail.item_no || '—'} · 仓位：${detail.from_location || '未设置'} → ${detail.to_location} · ${detail.reason || ''}`
  }
  const preferredKeys = ['reason', 'change_reason', 'additional_quantity', 'reduction_quantity', 'before_quantity', 'after_quantity', 'old_quantity', 'new_quantity', 'status', 'receipt_no', 'document_no', 'count']
  const entries = preferredKeys
    .filter((key) => detail[key] !== undefined && detail[key] !== null && detail[key] !== '')
    .map((key) => `${({
      reason: '原因',
      change_reason: '修改原因',
      additional_quantity: '追加数量',
      reduction_quantity: '减少数量',
      before_quantity: '调整前数量',
      after_quantity: '调整后数量',
      old_quantity: '原数量',
      new_quantity: '新数量',
      status: '状态',
      receipt_no: '收料单',
      document_no: '单据号',
      count: '条数',
    } as Record<string, string>)[key] ?? key}：${String(detail[key])}`)
  const before = detail.before && typeof detail.before === 'object' ? detail.before as Record<string, unknown> : null
  const after = detail.after && typeof detail.after === 'object' ? detail.after as Record<string, unknown> : null
  if (before && after) {
    const changeLabels: Record<string, string> = {
      customer_code: '客户',
      contract_no: '合同号',
      item_no: '货号',
      product_order_quantity: '产品数量',
      order_date: '下单日期',
      customer_due_date: '客户交期',
      due_date: '计划交期',
      note: '备注',
      lines: '纸品明细',
    }
    const changes = Object.keys(changeLabels)
      .filter((key) => JSON.stringify(before[key]) !== JSON.stringify(after[key]))
      .map((key) => key === 'lines'
        ? `${changeLabels[key]}已变更`
        : `${changeLabels[key]}：${String(before[key] ?? '—')} → ${String(after[key] ?? '—')}`)
    if (changes.length) entries.push(`变更：${changes.join('；')}`)
  }
  return entries.join(' · ') || JSON.stringify(detail)
}

function openBulkCancelOrders() {
  if (!selectedOrdersCanCancel.value) {
    actionMessage.value = selectedOrders.value.length
      ? '批量取消只允许选择尚未确认锁定的待下单订单。'
      : '请先勾选需要批量取消的订单。'
    return
  }
  cancelOrderNo.value = '__BULK__'
  cancelOrderReason.value = '客户取消订单'
}

function toggleVisibleOrders(selected: boolean) {
  const visibleOrderNos = orderedVisibleOrders.value.map((order) => order.id)
  selectedOrderNos.value = selected
    ? [...new Set([...selectedOrderNos.value, ...visibleOrderNos])]
    : selectedOrderNos.value.filter((orderNo) => !visibleOrderNos.includes(orderNo))
}

function openOrderDetails(orderNo: string) {
  orderDetailNo.value = orderNo
  orderDetailPinned.value = true
  openOrderMoreMenu.value = ''
}

function previewOrderDetails(orderNo: string) {
  if (orderDetailPinned.value) return
  orderDetailNo.value = orderNo
}

function closeOrderDetailsPreview(orderNo: string) {
  if (!orderDetailPinned.value && orderDetailNo.value === orderNo) {
    orderDetailNo.value = ''
  }
}

function closeOrderDetails() {
  orderDetailNo.value = ''
  orderDetailPinned.value = false
}

function openOrderDetailPurchaseOrder() {
  const orderNo = orderDetailNo.value
  closeOrderDetails()
  if (orderNo) void openPurchaseOrderDialog(orderNo)
}

function toggleVisibleInventoryBalances(selected: boolean) {
  const visibleIds = inventoryBalances.value.filter((row) => row.balance > 0).map((row) => row.id)
  selectedInventoryTargetIds.value = selected
    ? [...new Set([...selectedInventoryTargetIds.value, ...visibleIds])]
    : selectedInventoryTargetIds.value.filter((id) => !visibleIds.includes(id))
}

function clearInventoryBalanceFilters() {
  warehouseFilter.value = ''; locationFilter.value = ''
  selectedCustomer.value = '全部客户'
  globalSearch.value = ''
  inventoryBalanceDateRange.value = { start: undefined, end: undefined }
}

function receiptReplacementOptions(row: ReceiptReviewLine) {
  return orderRecords.value.flatMap(order => order.lines).find(line => line.id === row.orderLineId)?.replenishment_options ?? []
}
function receiptReplacementNeedsReview(row: ReceiptReviewLine) {
  return orderRecords.value.flatMap(order => order.lines).find(line => line.id === row.orderLineId)?.replenishment_review_required
}
function receiptReplacement(row: ReceiptReviewLine) {
  return receiptReplacementOptions(row).find(option => option.replenishment_issue_id === row.replenishmentIssueId)
}
function freeReplacement(row: ReceiptReviewLine) {
  return (receiptReplacement(row)?.responsibility ?? row.replacementResponsibility) === 'SUPPLIER'
}
function changeReceiptReplacement(row: ReceiptReviewLine) {
  const option = receiptReplacement(row)
  row.replacementResponsibility = option?.responsibility
  row.replacementDocumentNo = option?.document_no
  const original = orderRecords.value.flatMap(order => order.lines).find(line => line.id === row.orderLineId)
  const ordinary = Math.max(0, Number(original?.remaining_quantity ?? row.remainingQuantity) - Number(original?.pending_received_quantity ?? 0)
    - receiptReplacementOptions(row).reduce((sum, item) => sum + Number(item.remaining_quantity), 0))
  row.remainingQuantity = option ? Number(option.remaining_quantity) : ordinary
  row.deliveryQuantity = Math.min(row.deliveryQuantity, row.remainingQuantity)
  row.receivedQuantity = Math.min(row.receivedQuantity, row.deliveryQuantity)
  row.damagedQuantity = 0; row.rejectedQuantity = 0; row.unusableQuantity = 0; row.allocations = []
  row.unitPrice = freeReplacement(row) ? 0 : Number(original?.unit_price ?? 0)
}
function paperProtectedQuantity(line: CartonOrderResponse['lines'][number]) {
  if (line.maximum_reducible_quantity != null) return Math.max(0, Number(line.required_quantity) - Number(line.maximum_reducible_quantity))
  return Number(line.received_quantity) + Number(line.pending_received_quantity ?? pendingReceiptQuantity(line.id))
}
function validatePaperTargets(order: CartonOrderResponse, targets: Record<string, number | ''>, increasing: boolean) {
  let changed = false
  for (const line of order.lines) {
    const target = targets[line.id], value = Number(target), current = Number(line.required_quantity)
    if (target === '' || target == null || !Number.isFinite(value) || value < 0 || Math.abs(value * 10000 - Math.round(value * 10000)) > 0.00001 || (increasing ? value < current : value > current || value < paperProtectedQuantity(line))) {
      actionMessage.value = increasing ? '请填写每条纸品的调整后需求量，追加不能低于当前需求。' : '减单目标不能超过当前需求，也不能低于已收和待确认数量。'
      return false
    }
    if (value !== current) changed = true
  }
  if (!changed) actionMessage.value = '纸品需求数量没有变化。'
  return changed
}
function openAppendOrder(orderNo: string) {
  const order = orderRecords.value.find((item) => item.order_no === orderNo)
  if (!order || !canAppendOrder(orderNo)) {
    actionMessage.value = ['PENDING_SUPPLIER', 'PARTIALLY_RECEIVED', 'COMPLETED'].includes(order?.status ?? '')
      ? '你没有当前厂区已锁定订单的追加权限。'
      : '该订单当前不能追加。'
    return
  }
  appendOrderNo.value = orderNo
  appendOrderQuantity.value = 0
  Object.keys(appendLineTargets).forEach(key => delete appendLineTargets[key])
  order.lines.forEach(line => { appendLineTargets[line.id] = Number(line.required_quantity) })
  appendOrderReason.value = DEFAULT_APPEND_ORDER_REASON
  appendOrderCustomerDueDate.value = order.customer_due_date ?? ''
  appendOrderDueDate.value = order.due_date
}

async function confirmAppendOrder() {
  const order = orderRecords.value.find((item) => item.order_no === appendOrderNo.value)
  if (!order || (order.quantity_basis !== 'EXPLICIT' && appendOrderQuantity.value <= 0)) {
    actionMessage.value = '追加数量必须大于 0。'
    return
  }
  if (appendOrderCustomerDueDate.value && appendOrderCustomerDueDate.value < order.order_date) {
    actionMessage.value = '追加订单的客户交期不能早于原订单的下单日期。'
    return
  }
  if (order.quantity_basis === 'EXPLICIT' && !validatePaperTargets(order, appendLineTargets, true)) return
  appendingOrder.value = true
  try {
    const wasCompleted = order.status === 'COMPLETED'
    const saved = await cartonProcurementApi.appendOrder(
      selectedFactoryId.value,
      order,
      order.quantity_basis === 'EXPLICIT' ? null : appendOrderQuantity.value,
      appendOrderReason.value.trim() || DEFAULT_APPEND_ORDER_REASON,
      calculatedAppendOrderDueDate.value,
      appendOrderCustomerDueDate.value,
      ...(order.quantity_basis === 'EXPLICIT' ? [order.lines.map(line => ({ order_line_id: line.id, required_quantity: Number(appendLineTargets[line.id]) }))] : []),
    )
    replaceOrderState(saved)
    appendOrderNo.value = ''
    await loadBackendData()
    actionMessage.value = order.quantity_basis === 'EXPLICIT' ? `订单 ${saved.order_no} 已按逐纸品目标数量追加，新增需求可继续收料。` : wasCompleted
      ? `订单 ${saved.order_no} 已追加 ${formatNumber(appendOrderQuantity.value)} 件，并已恢复为“部分到货”，可继续登记新增数量。`
      : `订单 ${saved.order_no} 已追加 ${formatNumber(appendOrderQuantity.value)} 件，追单提醒和操作记录已生成。`
  } catch (error) {
    actionMessage.value = `订单追加失败：${getApiErrorMessage(error)}`
  } finally {
    appendingOrder.value = false
  }
}

function openReduceOrder(orderNo: string) {
  const order = orderRecords.value.find((item) => item.order_no === orderNo)
  if (!order || !canReduceSubmittedOrder(orderNo)) {
    actionMessage.value = ['PENDING_SUPPLIER', 'PARTIALLY_RECEIVED'].includes(order?.status ?? '')
      ? '减单需要当前厂区的订单调整权限或订单与库存操作权限，且不能低于已入库及待确认收料数量。'
      : '当前订单状态不能减单。'
    return
  }
  reduceOrderNo.value = orderNo
  reduceOrderQuantity.value = 0
  Object.keys(reduceLineTargets).forEach(key => delete reduceLineTargets[key])
  order.lines.forEach(line => { reduceLineTargets[line.id] = Number(line.required_quantity) })
  reduceOrderReason.value = DEFAULT_REDUCE_ORDER_REASON
}

async function confirmReduceOrder() {
  const order = orderRecords.value.find((item) => item.order_no === reduceOrderNo.value)
  const maximumReduction = order ? maximumReducibleProductQuantity(order) : 0
  if (!order || (order.quantity_basis !== 'EXPLICIT' && (reduceOrderQuantity.value <= 0 || reduceOrderQuantity.value > maximumReduction))) {
    actionMessage.value = `减单数量必须大于 0，且不能超过可减数量 ${formatNumber(maximumReduction)}。`
    return
  }
  if (order.quantity_basis === 'EXPLICIT' && !validatePaperTargets(order, reduceLineTargets, false)) return
  const reductionQuantity = reduceOrderQuantity.value
  reducingOrder.value = true
  try {
    const wasPartiallyReceived = order.status === 'PARTIALLY_RECEIVED'
    const saved = await cartonProcurementApi.reduceOrder(
      selectedFactoryId.value,
      order,
      order.quantity_basis === 'EXPLICIT' ? null : reductionQuantity,
      reduceOrderReason.value.trim() || DEFAULT_REDUCE_ORDER_REASON,
      ...(order.quantity_basis === 'EXPLICIT' ? [order.lines.map(line => ({ order_line_id: line.id, required_quantity: Number(reduceLineTargets[line.id]) }))] : []),
    )
    replaceOrderState(saved)
    reduceOrderNo.value = ''
    await loadBackendData()
    actionMessage.value = saved.status === 'CANCELLED'
      ? `订单 ${saved.order_no} 已减至 0 并转为已取消（退单），操作记录已保存。`
      : wasPartiallyReceived && saved.status === 'COMPLETED'
        ? `订单 ${saved.order_no} 已退掉全部未入库数量，现有入库量已满足调整后订单，状态转为“全部到货”。`
        : order.quantity_basis === 'EXPLICIT' ? `订单 ${saved.order_no} 已按逐纸品目标数量减单；已收料及待确认数量保持不变。` : `订单 ${saved.order_no} 已减少 ${formatNumber(reductionQuantity)} 件，纸箱需求量已重新计算并留痕。`
  } catch (error) {
    actionMessage.value = `订单减单失败：${getApiErrorMessage(error)}`
  } finally {
    reducingOrder.value = false
  }
}

async function exportPurchaseOrder(orderNo: string) {
  if (!apiConnected.value || exportingOrderNo.value) return
  exportingOrderNo.value = orderNo
  try {
    const blob = await cartonProcurementApi.exportPurchaseOrder(selectedFactoryId.value, orderNo)
    downloadWorkbook(blob, `${orderNo}_纸箱采购单.xlsx`)
    actionMessage.value = `${orderNo} 采购单已生成并开始下载。`
  } catch (error) {
    actionMessage.value = `采购单导出失败：${await getApiErrorMessageAsync(error)}`
  } finally {
    exportingOrderNo.value = ''
  }
}

function purchaseOrderTypeLabel(type: CartonPurchaseOrderContextResponse['pending_type'] | CartonPurchaseOrderIssueResponse['document_type']) {
  return {
    NONE: '暂无待生成变更',
    LEGACY_BASELINE: '历史累计基线',
    INITIAL: '首次采购单',
    APPEND: '追加采购单',
    REDUCE: '减单通知',
    ADJUSTMENT: '采购变更单',
  }[type]
}

function signedQuantity(value: string | number | null) {
  if (value === null) return '未记录'
  const quantity = Number(value || 0)
  return `${quantity > 0 ? '+' : ''}${formatNumber(quantity)}`
}

async function loadPurchaseOrderContext() {
  if (!purchaseOrderDialogNo.value || !apiConnected.value) return
  loadingPurchaseOrderContext.value = true
  try {
    purchaseOrderContextRecord.value = await cartonProcurementApi.getPurchaseOrderContext(
      selectedFactoryId.value,
      purchaseOrderDialogNo.value,
    )
  } catch (error) {
    actionMessage.value = `采购单记录读取失败：${getApiErrorMessage(error)}`
    purchaseOrderContextRecord.value = null
  } finally {
    loadingPurchaseOrderContext.value = false
  }
}

async function openPurchaseOrderDialog(orderNo: string) {
  purchaseOrderDialogNo.value = orderNo
  purchaseOrderContextRecord.value = null
  await loadPurchaseOrderContext()
}

function closePurchaseOrderDialog() {
  if (issuingPurchaseOrder.value || downloadingPurchaseOrderIssueId.value) return
  purchaseOrderDialogNo.value = ''
  purchaseOrderContextRecord.value = null
}

async function issuePendingPurchaseOrder() {
  const order = purchaseOrderDialogRecord.value
  const context = purchaseOrderContextRecord.value
  if (!order || !context?.can_generate || issuingPurchaseOrder.value) return
  issuingPurchaseOrder.value = true
  try {
    const result = await cartonProcurementApi.issuePurchaseOrder(selectedFactoryId.value, order)
    downloadWorkbook(result.blob, `${result.documentNo}_${purchaseOrderTypeLabel(context.pending_type)}.xlsx`)
    actionMessage.value = `${result.documentNo} ${purchaseOrderTypeLabel(context.pending_type)}已固定生成并开始下载。`
    await loadPurchaseOrderContext()
  } catch (error) {
    actionMessage.value = `供应商采购单生成失败：${await getApiErrorMessageAsync(error)}`
  } finally {
    issuingPurchaseOrder.value = false
  }
}

async function downloadPurchaseOrderIssue(issue: CartonPurchaseOrderIssueResponse) {
  if (!purchaseOrderDialogNo.value || downloadingPurchaseOrderIssueId.value) return
  downloadingPurchaseOrderIssueId.value = issue.id
  try {
    const blob = await cartonProcurementApi.downloadPurchaseOrderIssue(
      selectedFactoryId.value,
      purchaseOrderDialogNo.value,
      issue.id,
    )
    downloadWorkbook(blob, `${issue.document_no}_${(issue.is_replenishment ? '补单采购单' : purchaseOrderTypeLabel(issue.document_type))}.xlsx`)
    actionMessage.value = `${issue.document_no} 已按原生成版本重新下载。`
  } catch (error) {
    actionMessage.value = `采购单历史下载失败：${await getApiErrorMessageAsync(error)}`
  } finally {
    downloadingPurchaseOrderIssueId.value = ''
  }
}

async function exportCumulativePurchaseOrderReference() {
  if (!purchaseOrderDialogNo.value) return
  await exportPurchaseOrder(purchaseOrderDialogNo.value)
}

function downloadWorkbook(blob: Blob, filename: string) {
  if (!(blob instanceof Blob) || blob.size === 0) {
    throw new Error('后端未返回有效的采购单文件')
  }

  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.style.display = 'none'
  document.body.appendChild(link)
  try {
    link.click()
  } catch (error) {
    window.URL.revokeObjectURL(url)
    throw error
  } finally {
    link.remove()
  }

  // Chromium may not consume the blob URL until after the click task has
  // completed. Revoking immediately can make the download appear to do
  // nothing, especially inside the in-app browser.
  window.setTimeout(() => window.URL.revokeObjectURL(url), 30_000)
}

async function exportSelectedPurchaseOrders() {
  if (!selectedOrderNos.value.length || exportingSelectedOrders.value) return
  if (!apiConnected.value) {
    combinedPurchaseOrderTone.value = 'error'
    combinedPurchaseOrderMessage.value = '后端未连接，当前演示订单不能导出；请刷新页面或重新登录后再试。'
    return
  }

  const orderNos = selectedOrders.value.map((order) => order.order_no)
  if (orderNos.length !== selectedOrderNos.value.length) {
    combinedPurchaseOrderTone.value = 'error'
    combinedPurchaseOrderMessage.value = '所选订单已发生变化，请刷新订单列表后重新勾选。'
    return
  }

  exportingSelectedOrders.value = true
  combinedPurchaseOrderTone.value = 'progress'
    combinedPurchaseOrderMessage.value = `正在合并生成 ${orderNos.length} 张订单的累计对账表，请稍候…`
  try {
    const blob = await cartonProcurementApi.exportPurchaseOrders(selectedFactoryId.value, orderNos)
    downloadWorkbook(blob, `纸箱累计对账表_${businessTodayIso()}.xlsx`)
    combinedPurchaseOrderTone.value = 'success'
    combinedPurchaseOrderMessage.value = `已将 ${orderNos.length} 张订单合并为累计对账表，文件已开始下载；该文件不代表新增下单。`
    actionMessage.value = `已将 ${orderNos.length} 张订单合并导出为累计对账表。`
  } catch (error) {
    const message = `合并导出失败：${await getApiErrorMessageAsync(error)}`
    combinedPurchaseOrderTone.value = 'error'
    combinedPurchaseOrderMessage.value = `${message}。请刷新订单列表后重试。`
    actionMessage.value = message
  } finally {
    exportingSelectedOrders.value = false
  }
}

function triggerHistoryOrderImport() {
  historyOrderFileInput.value?.click()
}

async function handleHistoryOrderFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (!/\.(xlsx|xlsm|xls)$/i.test(file.name)) {
    actionMessage.value = '历史订单仅支持 Excel 文件，请使用系统映射模板填写后再导入。'
    return
  }

  historyImportFile.value = file
}
async function completeHistoryImport(result: import('@/api/cartonProcurement').CartonHistoryOrderImportResponse) {
  historyImportFile.value = null
  const message = `历史订单“${result.original_filename}”已导入 ${result.imported_count} 张、${result.imported_line_count} 条纸品，重复跳过 ${result.skipped_count} 张。历史订单已直接进入待收料，无需再次确认锁定或发行采购单。`
  await loadBackendData()
  actionMessage.value = message + (apiConnected.value ? '' : ' 列表刷新失败，请刷新查看已保存订单。')
}
watch(selectedFactoryId, () => { historyImportFile.value = null })

function mapInspectionPreview(row: CartonImportPreviewRow, index: number): InspectionReminderRow {
  const result = ({
    READY: '纸箱已备齐',
    UPCOMING: '待提前交货',
    DUE_SOON: '交货临近',
    OVERDUE: '交货已逾期',
    MISSING_ORDER: '疑似漏单',
    AMBIGUOUS: '待人工关联',
    INVALID_DATE: '送货日期待补充',
    REVIEW_REQUIRED: '待人工确认',
  } as Record<string, string>)[row.reminder_status ?? ''] ?? '待核对'
  const tone: CartonTone = row.reminder_status === 'READY'
    ? 'green'
    : ['OVERDUE', 'MISSING_ORDER'].includes(row.reminder_status ?? '')
      ? 'red'
      : ['DUE_SOON', 'AMBIGUOUS', 'INVALID_DATE'].includes(row.reminder_status ?? '')
        ? 'amber'
        : 'blue'
  return {
    ...mapWeeklyPreview(row, index),
    id: `INSP-${row.source_sheet ?? 'S'}-${row.source_row ?? index + 1}`,
    result,
    tone,
    inspectionStartDate: row.inspection_start_date ?? '',
    requiredDeliveryDate: row.required_delivery_date ?? '',
    advanceDays: Number(row.advance_days ?? inspectionAdvanceDays.value),
    daysUntilDelivery: row.days_until_delivery ?? null,
    orderStatus: row.order_status ?? '',
    reminderStatus: row.reminder_status ?? 'INVALID_DATE',
  }
}

async function openingInventoryImported(result: import('@/api/cartonProcurement').CartonHistoryInventoryImportResponse) {
  const factory = selectedFactoryId.value
  const message = `期初库存已入账 ${result.imported_count} 行，跳过 ${result.skipped_count} 行。`
  try {
    await refreshInventoryLedger()
    if (factory === selectedFactoryId.value) actionMessage.value = message
  } catch {
    if (factory === selectedFactoryId.value) actionMessage.value = `${message} 库存列表刷新失败，请刷新查看；不要重复登记。`
  }
}

function openInventoryRelocation(row: InventoryBalanceRow, event: Event) {
  inventoryDialogTrigger.value = event.currentTarget as HTMLElement | null
  relocationTarget.value = { ...row }
  relocationLocation.value = ''
  relocationQuantity.value = row.balance
  relocationNote.value = ''
  relocationFeedback.value = ''
  showInventoryRelocation.value = true
}

async function submitInventoryRelocation() {
  const target = relocationTarget.value
  const factoryId = selectedFactoryId.value
  if (!target || relocationBusy.value) return
  const location = relocationLocation.value.trim()
  if (!location || location === target.locationId) {
    relocationFeedback.value = !location ? '请填写目标仓位。' : '目标仓位与当前仓位相同。'
    return
  }
  if (!Number.isFinite(relocationQuantity.value) || relocationQuantity.value <= 0 || relocationQuantity.value > target.balance
    || Math.abs(relocationQuantity.value * 10000 - Math.round(relocationQuantity.value * 10000)) > 0.00001) {
    relocationFeedback.value = '调仓数量须大于零、不超过本仓结存，最多四位小数。'
    return
  }
  relocationBusy.value = true
  relocationFeedback.value = ''
  try {
    const result = await cartonPositionsApi.transfer({
      factory_id: factoryId, position_key: target.id,
      expected_position_revision: target.positionRevision || 0,
      location_id: location, quantity: relocationQuantity.value, note: relocationNote.value.trim(),
    })
    if (selectedFactoryId.value !== factoryId || relocationTarget.value !== target) return
    actionMessage.value = `调仓完成：${result.from_location} → ${result.to_location}，${result.quantity} ${target.unit}；总库存不变。`
    showInventoryRelocation.value = false
    try {
      await refreshInventoryLedger()
    } catch {
      if (selectedFactoryId.value === factoryId) actionMessage.value += ' 操作日志暂未刷新，可稍后点击刷新。'
    }
  } catch (error) {
    if (selectedFactoryId.value !== factoryId || relocationTarget.value !== target) return
    relocationFeedback.value = `调仓失败：${getApiErrorMessage(error)}`
  } finally {
    relocationBusy.value = false
  }
}

function openInventoryOperation(type: 'OUTBOUND' | 'ADJUSTMENT', targetId: string, bulk: boolean, event: Event) {
  inventoryDialogTrigger.value = event.currentTarget as HTMLElement | null
  inventoryOperationType.value = type
  outboundKind.value = 'USAGE'
  outboundWorkshop.value = ''; bulkWorkshops.value = {}
  inventoryBulkMode.value = bulk
  inventoryBulkQuantities.value = bulk
    ? Object.fromEntries(selectedInventoryBalances.value.map((row) => [row.id, String(row.balance)]))
    : {}
  inventoryOperationReason.value = type === 'OUTBOUND' ? '客户要货' : ''
  inventoryOperationDocumentNo.value = ''
  selectInventoryTarget(targetId)
  showInventoryOperation.value = true
}

function setInventoryDialogOpen(open: boolean) {
  if (!inventoryOperationBusy.value) showInventoryOperation.value = open
}

function restoreInventoryFocus(event: Event) {
  event.preventDefault()
  inventoryDialogTrigger.value?.focus()
}

function selectInventoryTarget(targetId: string) {
  inventoryTargetId.value = targetId
  const target = localInventoryBalances.find((row) => row.id === targetId)
  inventoryOperationLocation.value = target?.location ?? ''
  inventoryOperationQuantity.value = inventoryOperationType.value === 'OUTBOUND'
    ? Number(target?.balance ?? 0)
    : 0
  inventoryOperationFeedback.value = ''
}

async function refreshInventoryLedger() {
  const factoryId = selectedFactoryId.value
  const [movements, balances, audits, updatedOrders] = await Promise.all([
    cartonProcurementApi.listMovements(factoryId),
    cartonProcurementApi.listInventoryBalances(factoryId),
    cartonProcurementApi.listAuditEvents(factoryId),
    cartonProcurementApi.listOrders(factoryId),
  ])
  if (selectedFactoryId.value !== factoryId) return
  localMovements.splice(0, localMovements.length, ...movements.map(mapMovement))
  localInventoryBalances.splice(0, localInventoryBalances.length, ...balances.map(mapInventoryBalance))
  inventoryReportRefreshKey.value += 1
  auditRecords.value = audits
  orderRecords.value = updatedOrders
  localOrders.splice(0, localOrders.length, ...updatedOrders.map(mapOrder))
}

async function submitInventoryOperation() {
  if (inventoryOperationBusy.value) return
  const target = selectedInventoryBalance.value
  const amount = Number(inventoryOperationQuantity.value)
  if (!target) {
    inventoryOperationFeedback.value = '请先选择需要出库或调整的库存记录。'
    return
  }
  if (!Number.isFinite(amount) || amount === 0 || (inventoryOperationType.value === 'OUTBOUND' && amount < 0)) {
    inventoryOperationFeedback.value = inventoryOperationType.value === 'OUTBOUND'
      ? '出库数量必须大于 0。'
      : '调整数量不能为 0；增加填正数，减少填负数。'
    return
  }
  if (!inventoryOperationDocumentNo.value.trim() || !inventoryOperationReason.value.trim()) {
    inventoryOperationFeedback.value = '请填写来源单据号和业务原因。'
    return
  }
  const factoryId = selectedFactoryId.value
  const action = inventoryOperationType.value === 'OUTBOUND' ? '出库' : '库存调整'
  inventoryOperationBusy.value = true
  inventoryOperationFeedback.value = ''
  try {
    await cartonProcurementApi.createInventoryMovement({
      factory_id: factoryId,
      order_line_id: target.orderLineId,
      reference_movement_id: target.orderLineId ? null : target.latestMovementId,
      movement_type: inventoryOperationType.value,
      location_id: target.locationId, issue_kind: outboundKind.value,
      workshop_id: outboundWorkshop.value,
      quantity: amount,
      location: target.locationId ? '' : inventoryOperationLocation.value.trim(),
      document_no: inventoryOperationDocumentNo.value.trim(),
      reason: inventoryOperationReason.value.trim(),
    })
    if (selectedFactoryId.value !== factoryId) return
    // A successful write stays successful even if the following read fails.
    inventoryOperationQuantity.value = 0
    inventoryOperationDocumentNo.value = ''
    inventoryOperationReason.value = inventoryOperationType.value === 'OUTBOUND' ? '客户要货' : ''
    inventoryOperationFeedback.value = `${action}已登记。`
    actionMessage.value = inventoryOperationFeedback.value
    if (inventoryOperationType.value === 'OUTBOUND') showInventoryOperation.value = false
    try {
      await refreshInventoryLedger()
    } catch {
      if (selectedFactoryId.value !== factoryId) return
      inventoryOperationFeedback.value += ' 结存暂未刷新，请稍后刷新台账，勿重复登记。'
    }
    if (selectedFactoryId.value !== factoryId) return
    actionMessage.value = inventoryOperationFeedback.value
  } catch (error) {
    if (selectedFactoryId.value !== factoryId) return
    inventoryOperationFeedback.value = `${inventoryOperationType.value === 'OUTBOUND' ? '出库' : '调整'}失败：${getApiErrorMessage(error)}`
    actionMessage.value = inventoryOperationFeedback.value
  } finally {
    inventoryOperationBusy.value = false
  }
}

async function submitBulkInventoryOutbound() {
  if (inventoryOperationBusy.value) return
  if (outboundKind.value === 'OTHER' && !inventoryOperationReason.value.trim()) {
    inventoryOperationFeedback.value = '其他出库请填写具体用途。'
    return
  }
  const rows = selectedInventoryBalances.value
  if (!rows.length || rows.length !== selectedInventoryTargetIds.value.length) {
    inventoryOperationFeedback.value = '请先勾选当前有结存的库存记录。'
    return
  }
  if (!inventoryOperationDocumentNo.value.trim()) {
    inventoryOperationFeedback.value = '批量出库前请填写来源单据号。'
    return
  }
  for (const row of rows) {
    const raw = String(inventoryBulkQuantities.value[row.id] ?? '').trim()
    const amount = Number(raw)
    const label = `${row.poNumber || row.customer} · ${row.itemNo} · ${row.packagingType}`
    if (!/^\d+(\.\d{1,4})?$/.test(raw) || !Number.isFinite(amount) || amount <= 0) {
      inventoryOperationFeedback.value = `${label}：请填写大于 0 的本次出库数量，最多 4 位小数。`
      return
    }
    if (amount > row.balance) {
      inventoryOperationFeedback.value = `${label}：本次出库数量不能超过当前结存 ${formatNumber(row.balance)} ${row.unit}。`
      return
    }
  }
  const factoryId = selectedFactoryId.value
  inventoryOperationBusy.value = true
  inventoryOperationFeedback.value = ''
  try {
    await cartonProcurementApi.createInventoryMovementsBulk({
      factory_id: factoryId,
      document_no: inventoryOperationDocumentNo.value.trim(),
      reason: inventoryOperationReason.value.trim() || '客户要货',
      issue_kind: outboundKind.value, workshop_id: outboundWorkshop.value,
      items: rows.map((row) => ({
        order_line_id: row.orderLineId,
        reference_movement_id: row.orderLineId ? null : row.latestMovementId,
        quantity: Number(inventoryBulkQuantities.value[row.id]),
        location_id: row.locationId, workshop_id: bulkWorkshops.value[row.id] || outboundWorkshop.value,
        location: row.locationId ? '' : row.location,
      })),
    })
    if (selectedFactoryId.value !== factoryId) return
    selectedInventoryTargetIds.value = []
    inventoryBulkQuantities.value = {}
    inventoryOperationDocumentNo.value = ''
    inventoryOperationReason.value = '客户要货'
    inventoryOperationFeedback.value = `已按填写数量批量出库 ${rows.length} 条记录。`
    actionMessage.value = inventoryOperationFeedback.value
    showInventoryOperation.value = false
    try {
      await refreshInventoryLedger()
    } catch {
      if (selectedFactoryId.value !== factoryId) return
      inventoryOperationFeedback.value += ' 结存暂未刷新，请稍后刷新台账，勿重复出库。'
    }
    if (selectedFactoryId.value !== factoryId) return
    actionMessage.value = inventoryOperationFeedback.value
  } catch (error) {
    if (selectedFactoryId.value !== factoryId) return
    inventoryOperationFeedback.value = `批量出库失败：${getApiErrorMessage(error)}`
  } finally {
    inventoryOperationBusy.value = false
  }
}

function bulkOutboundRemaining(row: InventoryBalanceRow) {
  const raw = String(inventoryBulkQuantities.value[row.id] ?? '').trim()
  const amount = Number(raw)
  return raw && Number.isFinite(amount) && amount > 0 && amount <= row.balance
    ? `${Number((row.balance - amount).toFixed(4)).toLocaleString('zh-CN', { maximumFractionDigits: 4 })} ${row.unit}`
    : '—'
}

function movementCanReverse(row: InventoryMovementViewRow) {
  return apiConnected.value
    && row.sourceType !== 'ORDER_REPLENISHMENT'
    && ['OUTBOUND', 'ADJUSTMENT'].includes(row.rawMovementType ?? '')
    && !localMovements.some((candidate) => candidate.reversalOfMovementId === row.id)
}

function openInventoryReversal(row: InventoryMovementViewRow) {
  reversingMovementId.value = row.id
  reversalReason.value = '原单录入有误，冲销重录'
}

async function confirmInventoryReversal() {
  if (!reversingMovementId.value || !reversalReason.value.trim()) {
    actionMessage.value = '冲销必须填写原因。'
    return
  }
  reversalBusy.value = true
  try {
    await cartonProcurementApi.reverseInventoryMovement(
      selectedFactoryId.value,
      reversingMovementId.value,
      reversalReason.value.trim(),
    )
    await refreshInventoryLedger()
    actionMessage.value = `库存流水 ${reversingMovementId.value} 已冲销；原记录未被覆盖。`
    reversingMovementId.value = ''
    reversalReason.value = ''
  } catch (error) {
    actionMessage.value = `库存冲销失败：${getApiErrorMessage(error)}`
  } finally {
    reversalBusy.value = false
  }
}

function clearReceiptHistoryFilters() {
  receiptHistoryStatus.value = 'ALL'
  receiptHistoryDateRange.value = { start: undefined, end: undefined }
  selectedCustomer.value = '全部客户'
  globalSearch.value = ''
}

function showReceiptDetails(receipt: CartonReceiptResponse, pinned = false) {
  if (receiptDetailPinned.value && !pinned) return
  receiptDetailTarget.value = receipt
  receiptDetailPinned.value = pinned
}
function closeReceiptDetailPreview() {
  if (!receiptDetailPinned.value) receiptDetailTarget.value = null
}
function closeReceiptDetails() {
  receiptDetailTarget.value = null
  receiptDetailPinned.value = false
}
function continueReceiptDetails() {
  const receipt = receiptDetailTarget.value
  closeReceiptDetails()
  if (receipt) openReceiptHistoryDocument(receipt)
}
watch([selectedFactoryId, activeTab, selectedCustomer, globalSearch, receiptHistoryStatus, receiptHistoryDateRange], () => {
  closeReceiptDetails()
}, { flush: 'sync' })

function openReceiptCorrection(receipt: CartonReceiptResponse) {
  receiptCorrectionTarget.value = receipt
  receiptCorrectionReason.value = receipt.status === 'POSTED' ? '原单录入有误，冲销重录' : '收料登记有误，作废重录'
  receiptCorrectionError.value = ''
}

function openReceiptHistoryDocument(receipt: CartonReceiptResponse, reenter = false) {
  if (reenter && receipt.status !== 'REVERSED') return
  const linkedOrders = orderRecords.value.filter((order) => order.lines.some((line) =>
    receipt.lines.some((item) => item.order_line_id === line.id)))
  const missingOrderLine = receipt.lines.some((line) => line.order_line_id
    && !linkedOrders.some((order) => order.lines.some((item) => item.id === line.order_line_id)))
  if (reenter && (missingOrderLine || linkedOrders.some((order) => !['PENDING_SUPPLIER', 'PARTIALLY_RECEIVED'].includes(order.status)))) {
    actionMessage.value = '关联订单当前不能收料，请先核对订单状态。'
    return
  }
  receiptEntryMode.value = 'MANUAL'
  receiptPage.value = 'PENDING'
  receiptBatchId.value = ''
  manualReceiptOrderNos.value = linkedOrders.map((order) => order.order_no)
  currentReceipt.value = reenter ? null : receipt
  receiptCorrectionNote.value = reenter ? `更正原收料单 ${receipt.receipt_no}；原送货单号 ${receipt.delivery_note_no}；原单已作废或冲销。` : receipt.note.startsWith('更正原收料单') ? receipt.note : ''
  // Keep the original business document immutable; a correction uses an explicit distinct registration identifier.
  const suffix = `-更正-${receipt.receipt_no}`
  receiptDeliveryNoteNo.value = reenter ? `${receipt.delivery_note_no.slice(0, 128 - suffix.length)}${suffix}` : receipt.delivery_note_no
  receiptDeliveryDate.value = receipt.delivery_date
  receiptAcceptanceDate.value = receipt.acceptance_date ?? ''
  receiptLines.splice(0, receiptLines.length, ...receipt.lines.map((line) => ({
    id: `HISTORY-${line.id}`, orderNo: receipt.receipt_no, sourceType: line.source_type || 'FORMAL_ORDER',
    orderLineId: line.order_line_id || '', customerCode: line.customer_code, contractNo: line.contract_no,
    itemNo: line.item_no, description: `${line.packaging_type} ${line.paper_quality}`, packagingType: line.packaging_type,
    paperQuality: line.paper_quality, specification: line.specification, unit: line.unit, currency: line.currency,
    replenishmentIssueId: line.replenishment_issue_id ?? undefined, replacementResponsibility: line.responsibility ?? undefined,
    replacementDocumentNo: line.document_no ?? undefined,
    unitPrice: Number(line.settlement_unit_price ?? line.unit_price), deliveryQuantity: Number(line.delivered_quantity),
    receivedQuantity: Number(line.received_quantity), damagedQuantity: Number(line.damaged_quantity),
    rejectedQuantity: Number(line.rejected_quantity), unusableQuantity: Number(line.unusable_quantity), location: line.location, allocations: line.location_allocations?.map(part => ({ ...part })),
    sourceLabel: reenter ? '更正重录' : '历史记录',
    remainingQuantity: Number(linkedOrders.flatMap((order) => order.lines).find((item) => item.id === line.order_line_id)?.remaining_quantity ?? 0),
  })))
  receiptFeedbackMessage.value = ''
  showReceiptDialog.value = true
}

async function confirmReceiptCorrection() {
  const target = receiptCorrectionTarget.value
  const factoryId = selectedFactoryId.value
  if (!target || receiptCorrectionBusy.value) return
  if (receiptCorrectionReason.value.trim().length < 4) {
    receiptCorrectionError.value = '请填写至少 4 个字的原因，说明哪些信息录错了。'
    return
  }
  receiptCorrectionBusy.value = true
  receiptCorrectionError.value = ''
  try {
    const result = await cartonProcurementApi.reverseReceipt(factoryId, target.id, target.revision, receiptCorrectionReason.value.trim())
    if (selectedFactoryId.value !== factoryId) return
    receiptCorrectionTarget.value = null
    if (currentReceipt.value?.id === result.id) currentReceipt.value = result
    const index = receiptRecords.value.findIndex((row) => row.id === result.id)
    if (index >= 0) receiptRecords.value[index] = result
    actionMessage.value = `收料单 ${result.receipt_no} 已${target.status === 'POSTED' ? '整单冲销' : '作废'}；原单保留，可从历史台账重新登记。`
    await loadBackendData(factoryId)
  } catch (error) {
    if (selectedFactoryId.value !== factoryId) return
    const message = getApiErrorMessage(error)
    if (receiptCorrectionTarget.value) receiptCorrectionError.value = `未完成：${message}。若提示 Not Found，当前后端尚未启用收料冲销接口。`
    else actionMessage.value = `收料单已处理，但刷新失败：${message}。请刷新台账，不要重复操作。`
  } finally {
    receiptCorrectionBusy.value = false
  }
}

function receiptStatusLabel(status: CartonReceiptResponse['status']) {
  return ({
    DRAFT: '草稿',
    PENDING_CONFIRMATION: '待确认',
    POSTED: '已入库',
    REVERSED: '已冲销',
  } as const)[status]
}

function resetCustomerForm() {
  editingCustomerId.value = ''
  Object.assign(customerForm, {
    factory_id: selectedFactoryId.value,
    customer_code: '',
    customer_name: '',
    country_region: '',
    contact_name: '',
    contact_phone: '',
    note: '',
    status: 'ACTIVE',
  } satisfies CartonCustomerSaveRequest)
}

function openCustomerManager(customer?: CartonCustomerResponse) {
  customerCreatedFromOrder.value = false
  customerEditGeneration += 1
  if (customer && customer.factory_id !== selectedFactoryId.value) return
  resetCustomerForm()
  customerEditError.value = ''
  if (customer) editCustomer(customer)
  showCustomerModal.value = true
}

function createOrderCustomer(name: string) {
  if (!masterLoaded.value || !masterWorkspace.value.can_manage || editingOrderStructureLocked.value) return
  openCustomerManager()
  customerForm.customer_name = name
  customerCreatedFromOrder.value = true
}

function editCustomer(customer: CartonCustomerResponse) {
  editingCustomerId.value = customer.id
  Object.assign(customerForm, {
    factory_id: selectedFactoryId.value,
    customer_code: customer.customer_code,
    customer_name: customer.customer_name,
    country_region: customer.country_region,
    contact_name: customer.contact_name,
    contact_phone: customer.contact_phone,
    note: customer.note,
    status: customer.status,
  } satisfies CartonCustomerSaveRequest)
}

async function saveCustomer() {
  if (savingCustomer.value) return
  customerEditError.value = ''
  if (customerForm.factory_id !== selectedFactoryId.value) { customerEditError.value = '厂区已变更，请重新打开客户资料。'; return }
  const editingId = editingCustomerId.value, generation = customerEditGeneration
  const current = editingId ? customerRecords.value.find(c => c.id === editingId && c.factory_id === customerForm.factory_id) : undefined
  if (editingId && !current) { customerEditError.value = '客户资料已变化，请刷新后重新打开。'; return }
  if (!customerForm.customer_name.trim()) {
    customerEditError.value = '请填写客户名称。'
    return
  }
  savingCustomer.value = true
  const payload: CartonCustomerSaveRequest = {
    ...customerForm,
    factory_id: selectedFactoryId.value,
    customer_code: editingCustomerId.value ? customerForm.customer_code : '',
    customer_name: customerForm.customer_name.trim(),
    country_region: customerForm.country_region.trim(),
    contact_name: customerForm.contact_name.trim(),
    contact_phone: customerForm.contact_phone.trim(),
    note: customerForm.note.trim(),
  }
  try {
    const saved = current
      ? await cartonProcurementApi.updateCustomer(current, payload)
      : await cartonProcurementApi.createCustomer(payload)
    if (payload.factory_id !== selectedFactoryId.value || generation !== customerEditGeneration) return
    const index = customerRecords.value.findIndex((customer) => customer.id === saved.id)
    if (index >= 0) customerRecords.value.splice(index, 1, saved)
    else customerRecords.value.push(saved)
    customerRecords.value.sort((left, right) => left.customer_name.localeCompare(right.customer_name, 'zh-CN'))
    if (customerCreatedFromOrder.value && showOrderModal.value && saved.status === 'ACTIVE') orderForm.customerCode = saved.customer_code
    actionMessage.value = current
      ? `客户 ${saved.customer_name} 的资料已更新。`
      : `客户 ${saved.customer_name} 已加入 ${activeFactory.value.shortName} 客户主数据。`
    resetCustomerForm()
    showCustomerModal.value = false
  } catch (error) {
    if (payload.factory_id === selectedFactoryId.value && generation === customerEditGeneration) customerEditError.value = `客户资料未保存：${getApiErrorMessage(error)}`
  } finally {
    savingCustomer.value = false
  }
}


async function issueSelectedPurchaseOrders() {
  if (!selectedOrderNos.value.length || issuingSelectedPurchaseOrders.value) return
  if (!apiConnected.value) {
    combinedPurchaseOrderTone.value = 'error'
    combinedPurchaseOrderMessage.value = '后端未连接，当前演示订单不能发行供应商采购单。'
    return
  }
  const orders = selectedOrders.value.map(order => ({ ...order }))
  const factoryId = selectedFactoryId.value
  const selection = JSON.stringify(selectedOrderNos.value)
  const isCurrent = () => purchaseBatchActive && selectedFactoryId.value === factoryId && activeTab.value === 'orders' && JSON.stringify(selectedOrderNos.value) === selection
  if (orders.length !== selectedOrderNos.value.length) {
    combinedPurchaseOrderTone.value = 'error'
    combinedPurchaseOrderMessage.value = '所选订单已发生变化，请刷新订单列表后重新勾选。'
    return
  }

  issuingSelectedPurchaseOrders.value = true
  combinedPurchaseOrderTone.value = 'progress'
  combinedPurchaseOrderMessage.value = `正在核对 ${orders.length} 张订单，只发行尚未生成的首次、追加或减单净变化…`
  try {
    const contexts = await Promise.all(orders.map((order) =>
      cartonProcurementApi.getPurchaseOrderContext(factoryId, order.order_no),
    ))
    if (!isCurrent()) return
    const nonInitialContexts = contexts.filter((context) =>
      context.can_generate && !['NONE', 'INITIAL'].includes(context.pending_type),
    )
    const reusedContexts = contexts.filter((context) =>
      !context.can_generate && context.issues.length > 0,
    )
    const warningContexts = [
      ...nonInitialContexts.map((context) => ({
        orderNo: context.order_no,
        label: purchaseOrderTypeLabel(context.pending_type),
      })),
      ...reusedContexts.map((context) => ({
        orderNo: context.order_no,
        label: `重新下载 ${context.issues[0]?.document_no}`,
      })),
    ]
    if (warningContexts.length) {
      const preview = warningContexts
        .slice(0, 3)
        .map((context) => `${context.orderNo}（${context.label}）`)
        .join('、')
      const remaining = warningContexts.length - 3
      const warningSummary = [
        nonInitialContexts.length ? `${nonInitialContexts.length} 张将生成非首次采购单` : '',
        reusedContexts.length ? `${reusedContexts.length} 张没有新变化、将重新打包最近一次历史快照` : '',
      ].filter(Boolean).join('；')
      const confirmed = await confirmPurchaseBatch(
        `本次选择包含 ${warningContexts.length} 张非首次或已发行采购单：${preview}${remaining > 0 ? `，另有 ${remaining} 张` : ''}。\n其中${warningSummary}；系统不会重复编号。供应商仍只按各采购单的“本次箱数变化”执行。是否继续生成？`,
      )
      if (!isCurrent()) return
      if (!confirmed) {
        combinedPurchaseOrderTone.value = 'progress'
        combinedPurchaseOrderMessage.value = '已取消批量发行，没有生成新的供应商采购单。'
        return
      }
    }
    combinedPurchaseOrderMessage.value = `正在处理 ${orders.length} 张所选订单${nonInitialContexts.length ? `，其中 ${nonInitialContexts.length} 张生成非首次采购单` : ''}${reusedContexts.length ? `、${reusedContexts.length} 张重新打包历史快照` : ''}…`
    const result = await cartonProcurementApi.issuePurchaseOrders(factoryId, orders)
    downloadWorkbook(result.blob, `供应商采购单批次_${businessTodayIso()}.xlsx`)
    if (!isCurrent()) return
    const skippedCount = Math.max(0, orders.length - result.issueCount)
    const reusedCount = Math.min(reusedContexts.length, result.issueCount)
    const createdCount = Math.max(0, result.issueCount - reusedCount)
    combinedPurchaseOrderTone.value = 'success'
    combinedPurchaseOrderMessage.value = `批次文件包含 ${result.issueCount} 份供应商采购单：新发行 ${createdCount} 份${reusedCount ? `，重新打包历史快照 ${reusedCount} 份` : ''}${skippedCount ? `；跳过 ${skippedCount} 张既无变化也无历史采购单的订单` : ''}。供应商只按“本次箱数变化”执行。`
    actionMessage.value = `已生成 ${result.issueCount} 份不可变供应商采购单的批次文件。`
  } catch (error) {
    if (!isCurrent()) return
    const message = `供应商采购单批量发行失败：${await getApiErrorMessageAsync(error)}`
    combinedPurchaseOrderTone.value = 'error'
    combinedPurchaseOrderMessage.value = message
    actionMessage.value = message
  } finally {
    issuingSelectedPurchaseOrders.value = false
  }
}

function resetOrderForm() {
  chosenMaster.value = null
  const remembered = readOrderFormMemory()
  editingOrderNo.value = ''
  orderChangeReason.value = ''
  orderForm.customerCode = ''
  orderForm.supplierId = ''
  orderForm.customerPo = ''
  orderForm.contractNo = ''
  orderForm.itemNo = ''
  orderForm.productName = ''
  orderForm.quantityBasis = 'CALCULATED'
  orderForm.orderQuantity = 0
  orderForm.orderDate = new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
  orderForm.customerDueDate = ''
  orderForm.dueDate = ''
  orderForm.note = ''
  autoFilledProductName.value = ''
  historyItemSuggestions.value = []
  historyItemSuggestionsLoading.value = false
  showHistoryItemSuggestions.value = false
  selectedHistoryItemSource.value = null
  skipHistoryItemSearchFor = ''
  orderForm.materials.splice(0, orderForm.materials.length, {
    id: 'FORM-MAT-1',
    packagingType: '',
    paperQuality: '',
    specification: '',
    unitsPerCarton: remembered?.unitsPerCarton ?? 120,
    unit: remembered?.unit ?? '个',
    dimensionUnit: '',
    unitPrice: 0,
    currency: 'CNY',
    priceSource: 'manual',
    note: '',
  })
}

function historyItemMatchLabel(matchType: CartonOrderHistorySuggestionResponse['match_type']) {
  return ({
    EXACT: '完全一致',
    PREFIX: '前缀匹配',
    CONTAINS: '包含匹配',
    SIMILAR: '相似货号',
  } as const)[matchType]
}

function applyHistoryItemSuggestion(suggestion: CartonOrderHistorySuggestionResponse) {
  if (editingOrderNo.value) return
  historyItemSearchGeneration += 1
  if (historyItemSearchTimer) {
    clearTimeout(historyItemSearchTimer)
    historyItemSearchTimer = null
  }
  skipHistoryItemSearchFor = suggestion.item_no
  orderForm.itemNo = suggestion.item_no
  orderForm.customerCode = suggestion.customer_code
  orderForm.productName = suggestion.product_name
  autoFilledProductName.value = suggestion.product_name
  orderForm.materials.splice(0, orderForm.materials.length, ...suggestion.lines.map((line, index) => ({
    id: `FORM-HISTORY-${index + 1}-${Date.now()}`,
    packagingType: line.packaging_type,
    paperQuality: line.paper_quality,
    specification: line.specification,
    unitsPerCarton: line.usage_quantity == null ? '' as const : Number(line.usage_quantity),
    unit: line.unit,
    dimensionUnit: line.dimension_unit,
    unitPrice: Number(line.unit_price),
    currency: line.currency,
    priceSource: line.price_source,
    note: line.note,
  })))
  selectedHistoryItemSource.value = suggestion
  historyItemSuggestions.value = []
  historyItemSuggestionsLoading.value = false
  showHistoryItemSuggestions.value = false
  actionMessage.value = `已复用历史货号 ${suggestion.item_no} 最近订单 ${suggestion.latest_order_no} 的客户、产品名称和 ${suggestion.lines.length} 条纸品资料；本次合同、数量和日期未覆盖。`
}

function openOrderModal() {
  resetOrderForm()
  showOrderModal.value = true
}

function openEditOrderModal(orderNo: string) {
  const order = orderRecords.value.find((item) => item.order_no === orderNo)
  if (!order) {
    actionMessage.value = '未找到需要修改的正式订单，请刷新后重试。'
    return
  }
  if (order.status !== 'CONFIRMED') {
    actionMessage.value = '订单确认并锁定后不能再修改。'
    return
  }
  editingOrderNo.value = order.order_no
  orderChangeReason.value = '修正订单录入信息'
  orderForm.customerCode = order.customer_code
  orderForm.supplierId = order.supplier_id
  orderForm.customerPo = order.customer_po || ''
  orderForm.contractNo = order.contract_no
  orderForm.itemNo = order.item_no
  orderForm.productName = order.product_name
  orderForm.quantityBasis = order.quantity_basis || 'CALCULATED'
  orderForm.orderQuantity = order.product_order_quantity == null ? '' : Number(order.product_order_quantity)
  orderForm.orderDate = order.order_date
  orderForm.customerDueDate = order.customer_due_date ?? ''
  orderForm.dueDate = order.due_date
  orderForm.note = order.note
  orderForm.materials.splice(0, orderForm.materials.length, ...order.lines.map((line) => ({
    id: line.id,
    requiredQuantity: Number(line.required_quantity),
    packagingType: line.packaging_type,
    paperQuality: line.paper_quality,
    specification: line.specification,
    unitsPerCarton: line.usage_quantity == null ? '' as const : Number(line.usage_quantity),
    unit: line.unit,
    dimensionUnit: line.dimension_unit,
    unitPrice: Number(line.unit_price),
    currency: line.currency,
    priceSource: line.price_source,
    note: line.note,
  })))
  showOrderModal.value = true
}

function businessAlertKindLabel(kind: BusinessOrderAlertKind) {
  return ({
    MISSING_ORDER: '漏下单',
    QUANTITY_INCREASE: '订单增加',
    QUANTITY_DECREASE: '订单减少 / 退单',
    QUANTITY_REVIEW: '数量待复核',
  } as Record<BusinessOrderAlertKind, string>)[kind]
}

function businessAlertKindClass(kind: BusinessOrderAlertKind) {
  return ({
    MISSING_ORDER: 'bg-red-50 text-red-700 ring-red-200',
    QUANTITY_INCREASE: 'bg-amber-50 text-amber-800 ring-amber-200',
    QUANTITY_DECREASE: 'bg-violet-50 text-violet-700 ring-violet-200',
    QUANTITY_REVIEW: 'bg-slate-100 text-slate-600 ring-slate-200',
  } as Record<BusinessOrderAlertKind, string>)[kind]
}

function businessAlertStatusLabel(status: CartonExceptionResponse['status']) {
  return ({
    OPEN: '待处理',
    IN_PROGRESS: '处理中',
    RESOLVED: '已解决',
    CLOSED: '已关闭',
  } as Record<CartonExceptionResponse['status'], string>)[status]
}

function businessAlertActionLabel(alert: BusinessOrderAlert) {
  if (alert.kind === 'MISSING_ORDER') return '按提醒新建'
  if (alert.kind === 'QUANTITY_INCREASE' && alert.order && canAppendOrder(alert.order.order_no)) return '追加订单'
  if (alert.kind === 'QUANTITY_DECREASE' && alert.orderStatus === 'CONFIRMED') {
    return alert.scheduleQuantity <= 0 ? '取消订单' : '调整订单数量'
  }
  if (alert.kind === 'QUANTITY_DECREASE' && alert.order && canReduceSubmittedOrder(alert.order.order_no)) return '减少未入库量'
  if (alert.orderNo) return alert.orderStatus === 'PENDING_SUPPLIER' ? '查看锁定订单' : '查看订单'
  return '核对提醒'
}

function businessAlertActionDisabled(alert: BusinessOrderAlert) {
  return !apiConnected.value || ['RESOLVED', 'CLOSED'].includes(alert.exception.status)
}

function openBusinessAlertException(alert: BusinessOrderAlert) {
  exceptionStatusFilter.value = 'ALL'; exceptionTypeFilter.value = 'ALL'
  globalSearch.value = alert.alertNo
  setActiveTab('exceptions')
}

function openBusinessAlertOrder(alert: BusinessOrderAlert) {
  if (businessAlertActionDisabled(alert)) return
  if (alert.kind === 'MISSING_ORDER') {
    const customer = activeCustomers.value.find((item) =>
      (alert.customerCode && item.customer_code === alert.customerCode)
      || item.customer_name.trim().toLowerCase() === alert.customerName.trim().toLowerCase(),
    )
    if (!customer) {
      actionMessage.value = `提醒 ${alert.alertNo} 的客户“${alert.customerName}”尚未进入本厂客户资料，请先维护客户后再补建订单。`
      setActiveTab('orders')
      return
    }
    resetOrderForm()
    orderForm.customerCode = customer.customer_code
    orderForm.contractNo = alert.contractNo
    orderForm.itemNo = alert.itemNo
    orderForm.productName = alert.productName
    orderForm.orderQuantity = alert.scheduleQuantity
    orderForm.note = `业务排期漏单提醒 ${alert.alertNo}；来源：${alert.sourceFilename}`
    showOrderModal.value = true
    actionMessage.value = `已从 ${alert.alertNo} 带入业务排期信息；请补齐纸品规格并人工确认。`
    return
  }

  if (alert.kind === 'QUANTITY_INCREASE' && alert.order && canAppendOrder(alert.order.order_no)) {
    openAppendOrder(alert.order.order_no)
    appendOrderQuantity.value = alert.differenceQuantity
    appendOrderReason.value = `业务排期数量增加（${alert.alertNo}）`
    return
  }

  if (alert.kind === 'QUANTITY_DECREASE' && alert.order?.status === 'CONFIRMED') {
    if (alert.scheduleQuantity <= 0) {
      openCancelOrder(alert.order.order_no)
      cancelOrderReason.value = `业务排期取消订单（${alert.alertNo}）`
    } else {
      openEditOrderModal(alert.order.order_no)
      orderForm.orderQuantity = alert.scheduleQuantity
      orderChangeReason.value = `业务排期数量减少（${alert.alertNo}）`
    }
    return
  }

  if (alert.kind === 'QUANTITY_DECREASE' && alert.order && canReduceSubmittedOrder(alert.order.order_no)) {
    openReduceOrder(alert.order.order_no)
    reduceOrderQuantity.value = alert.scheduleQuantity <= 0
      ? Number(alert.order.product_order_quantity)
      : Math.abs(alert.differenceQuantity)
    reduceOrderReason.value = `业务排期数量减少（${alert.alertNo}）`
    return
  }

  if (alert.kind === 'QUANTITY_DECREASE' && alert.order && ['PARTIALLY_RECEIVED', 'COMPLETED'].includes(alert.order.status)) {
    globalSearch.value = alert.order.order_no
    clearOrderFilters()
    globalSearch.value = alert.orderNo
    setActiveTab('orders')
    void nextTick(() => {
      actionMessage.value = `订单 ${alert.order!.order_no} 当前没有可直接减少的未入库量；请查看订单明细，已入库记录如有错误请按库存冲销流程处理。`
    })
    return
  }

  if (alert.orderNo) {
    globalSearch.value = alert.orderNo
    clearOrderFilters()
    globalSearch.value = alert.orderNo
    setActiveTab('orders')
    void nextTick(() => {
      actionMessage.value = alert.orderStatus === 'PENDING_SUPPLIER'
        ? `订单 ${alert.orderNo} 已确认锁定；有权限的仓管或主管可按订单状态追加，或减少受保护数量之外的未入库量。`
        : `已定位提醒 ${alert.alertNo} 关联的订单 ${alert.orderNo}。`
    })
    return
  }
  openBusinessAlertException(alert)
}

async function handleBusinessAlertStatus(alert: BusinessOrderAlert) {
  if (alert.exception.status === 'OPEN') {
    await advanceException(alert.alertNo)
    return
  }
  openBusinessAlertException(alert)
}

function addOrderMaterialLine() {
  orderForm.materials.push({
    id: `FORM-MAT-${orderForm.materials.length + 1}`,
    packagingType: '',
    paperQuality: '',
    specification: '',
    requiredQuantity: '',
    unitsPerCarton: orderForm.quantityBasis === 'EXPLICIT' ? '' : 1,
    unit: '张',
    dimensionUnit: '',
    unitPrice: 0,
    currency: 'CNY',
    priceSource: 'manual',
    note: '',
  })
}

function removeOrderMaterialLine(index: number) {
  if (orderForm.materials.length === 1) {
    actionMessage.value = '一张合同至少需要保留一条纸品明细。'
    return
  }
  orderForm.materials.splice(index, 1)
}

function triggerReceiptImport() {
  receiptFileInput.value?.click()
}

async function handleReceiptFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  selectedReceiptFileName.value = file.name
  input.value = ''
  importingReceipt.value = true
  try {
    const batch = await cartonProcurementApi.uploadReceipt(selectedFactoryId.value, file)
    apiConnected.value = true
    applyReceiptImport(batch)
    showReceiptDialog.value = receiptLines.length > 0
    if (batch.duplicate) {
      actionMessage.value = `送货单“${file.name}”已导入过，已恢复原复核批次 ${batch.id}；没有重复创建收料或库存。`
    }
  } catch (error) {
    actionMessage.value = `送货单导入失败：${getApiErrorMessage(error)}`
  } finally {
    importingReceipt.value = false
  }
}

async function removeUnmatchedReceiptImport() {
  const batch = receiptImportBatch.value
  if (!batch || receiptImportStats.value.matched > 0) return
  if (!window.confirm(`确定删除送货单导入“${batch.original_filename}”吗？\n\n系统会同时删除本批次生成的异常记录；正式订单、收料单和库存不会受影响。`)) return
  deletingReceiptImport.value = true
  try {
    await cartonProcurementApi.deleteReceiptImport(selectedFactoryId.value, batch.id)
    receiptImportBatch.value = null
    receiptImportRows.value = []
    receiptLines.splice(0)
    receiptBatchId.value = ''
    selectedReceiptFileName.value = ''
    receiptDeliveryNoteNo.value = ''
    receiptDeliveryDate.value = ''
    receiptAcceptanceDate.value = businessTodayIso()
    currentReceipt.value = null
    receiptFeedbackMessage.value = ''
    const exceptions = await cartonProcurementApi.listExceptions(selectedFactoryId.value)
    exceptionRecords.value = exceptions
    localExceptions.splice(0, localExceptions.length, ...exceptions.map(mapException))
    actionMessage.value = `送货单导入“${batch.original_filename}”已删除；其派生异常已清理，订单、收料和库存未受影响。`
  } catch (error) {
    actionMessage.value = `送货单导入未删除：${getApiErrorMessage(error)}`
  } finally {
    deletingReceiptImport.value = false
  }
}

function triggerWeeklyImport() {
  weeklyFileInput.value?.click()
}

function triggerInspectionImport() {
  inspectionFileInput.value?.click()
}

function rememberImportBatch(history: CartonImportBatchResponse[], batch: CartonImportBatchResponse) {
  const index = history.findIndex((item) => item.id === batch.id)
  if (index >= 0) history.splice(index, 1)
  history.unshift(batch)
}

function restoreWeeklyImport(batch: CartonImportBatchResponse) {
  if (batch.status === 'REJECTED') return
  selectedWeeklyBatchId.value = batch.id
  const rows = batch.parse_summary.rows ?? []
  selectedWeeklyFileName.value = batch.original_filename
  localWeeklyChecks.splice(0, localWeeklyChecks.length, ...rows.map(mapWeeklyPreview))
  actionMessage.value = `已查看 ${batch.original_filename} 的历史核对结果：${batch.parse_summary.row_count ?? rows.length} 行。`
}

function restoreInspectionImport(batch: CartonImportBatchResponse) {
  if (batch.status === 'REJECTED') return
  selectedInspectionBatchId.value = batch.id
  const rows = batch.parse_summary.rows ?? []
  selectedInspectionFileName.value = batch.original_filename
  inspectionAdvanceDays.value = batch.parse_summary.advance_days ?? inspectionAdvanceDays.value
  localInspectionChecks.splice(0, localInspectionChecks.length, ...rows.map(mapInspectionPreview))
  actionMessage.value = `已查看 ${batch.original_filename} 的历史交期提醒：${batch.parse_summary.reminder_count ?? rows.length} 条。`
}

async function undoScheduleImport() {
  const batch = undoImportTarget.value
  if (!batch || undoingImport.value || undoImportReason.value.trim().length < 4 || !canUndoScheduleImport.value) return
  const factoryId = selectedFactoryId.value
  undoingImport.value = true
  try {
    const updated = await cartonProcurementApi.undoScheduleImport(factoryId, batch.id, undoImportReason.value.trim())
    if (selectedFactoryId.value !== factoryId) return
    rememberImportBatch(batch.import_type === 'WEEKLY_SCHEDULE' ? weeklyImportHistory.value : inspectionImportHistory.value, updated)
    exceptionRecords.value = exceptionRecords.value.filter(item => item.source_id !== batch.id)
    localExceptions.splice(0, localExceptions.length, ...exceptionRecords.value.map(mapException))
    selectedExceptionNos.value = selectedExceptionNos.value.filter(id => exceptionRecords.value.some(item => item.exception_no === id))
    if (selectedWeeklyBatchId.value === batch.id) {
      selectedWeeklyFileName.value = ''; selectedWeeklyBatchId.value = ''; localWeeklyChecks.splice(0)
    }
    if (selectedInspectionBatchId.value === batch.id) {
      selectedInspectionFileName.value = ''; selectedInspectionBatchId.value = ''; localInspectionChecks.splice(0)
    }
    undoImportTarget.value = null
    await loadBackendData(factoryId, { supersede: true })
    if (selectedFactoryId.value !== factoryId) return
    actionMessage.value = apiConnected.value
      ? `已整批撤销 ${batch.original_filename} 的核对结果和异常工作项，原始记录保留在操作日志。`
      : `已整批撤销 ${batch.original_filename}，但台账刷新失败，请刷新页面；不要重复撤销。`
  } catch (error) {
    if (selectedFactoryId.value === factoryId) actionMessage.value = `撤销未完成：${getApiErrorMessage(error)}`
  } finally { undoingImport.value = false }
}

async function handleWeeklyFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  selectedWeeklyFileName.value = file.name
  input.value = ''
  importingWeekly.value = true
  try {
    const batch = await cartonProcurementApi.uploadWeeklySchedule(selectedFactoryId.value, file)
    const rows = batch.parse_summary.rows ?? []
    rememberImportBatch(weeklyImportHistory.value, batch)
    restoreWeeklyImport(batch)
    apiConnected.value = true
    actionMessage.value = batch.duplicate
      ? `排期“${file.name}”已导入过，已恢复原核对结果；没有重复生成异常。`
      : `排期已核对 ${batch.parse_summary.row_count ?? rows.length} 行：匹配 ${batch.parse_summary.matched_count ?? 0} 行，待处理 ${batch.parse_summary.issue_count ?? 0} 行；未创建任何正式订单。`
    const exceptions = await cartonProcurementApi.listExceptions(selectedFactoryId.value)
    exceptionRecords.value = exceptions
    localExceptions.splice(0, localExceptions.length, ...exceptions.map(mapException))
  } catch (error) {
    actionMessage.value = `排期导入失败：${getApiErrorMessage(error)}`
  } finally {
    importingWeekly.value = false
  }
}

async function handleInspectionFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  selectedInspectionFileName.value = file.name
  input.value = ''
  importingInspection.value = true
  inspectionAdvanceDays.value = Math.max(0, Math.min(30, Math.round(Number(inspectionAdvanceDays.value) || 0)))
  try {
    const batch = await cartonProcurementApi.uploadInspectionSchedule(
      selectedFactoryId.value,
      file,
      inspectionAdvanceDays.value,
    )
    const rows = batch.parse_summary.rows ?? []
    rememberImportBatch(inspectionImportHistory.value, batch)
    restoreInspectionImport(batch)
    apiConnected.value = true
    actionMessage.value = batch.duplicate
      ? `查货合同“${file.name}”已按提前 ${inspectionAdvanceDays.value} 天核对过，已恢复原提醒结果。`
      : `查货合同已核对 ${batch.parse_summary.row_count ?? rows.length} 行：生成 ${batch.parse_summary.reminder_count ?? 0} 条提醒，其中逾期 ${batch.parse_summary.overdue_count ?? 0} 条、临近 ${batch.parse_summary.due_soon_count ?? 0} 条；未创建订单或库存。`
    const exceptions = await cartonProcurementApi.listExceptions(selectedFactoryId.value)
    exceptionRecords.value = exceptions
    localExceptions.splice(0, localExceptions.length, ...exceptions.map(mapException))
  } catch (error) {
    actionMessage.value = `查货合同导入失败：${getApiErrorMessage(error)}`
  } finally {
    importingInspection.value = false
  }
}

function setReceiptFeedback(message: string, tone: 'error' | 'success' = 'error') {
  receiptFeedbackMessage.value = message
  receiptFeedbackTone.value = tone
  actionMessage.value = message
}

function focusReceiptField(field: HTMLInputElement | null) {
  void nextTick(() => {
    field?.focus()
    field?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
  })
}

async function saveReceiptFeedback() {
  if (savingReceipt.value || currentReceipt.value) return
  receiptFeedbackMessage.value = ''
  const candidateLines = selectedReceiptLines.value
  if (!candidateLines.length) {
    setReceiptFeedback(receiptEntryMode.value === 'MANUAL'
      ? '请先勾选本次到货的纸品，并填写本次实际收到数量。'
      : '当前没有已复核的送货明细；导入文件后须先完成字段匹配，才能提交正式收料反馈。')
    return
  }
  if (receiptEntryMode.value === 'IMPORT' && !receiptBatchId.value) {
    setReceiptFeedback('入库未完成：请先导入送货单并完成订单纸品匹配。')
    return
  }
  if (candidateLines.some((row) => row.sourceType === 'FORMAL_ORDER' && !row.orderLineId)) {
    setReceiptFeedback('入库未完成：正式订单收料必须先完成订单纸品匹配。')
    return
  }
  const incompleteAdHocLine = candidateLines.find((row) => row.sourceType === 'AD_HOC' && [
    row.customerCode,
    row.itemNo,
    row.packagingType,
    row.paperQuality,
    row.specification,
    row.unit,
  ].some((value) => !value.trim()))
  if (incompleteAdHocLine) {
    setReceiptFeedback('入库未完成：非正式/打板收料必须补齐客户、货号、纸品类型、纸质、规格和单位。')
    return
  }
  if (candidateLines.some(row => row.sourceType === 'FORMAL_ORDER' && (Number(row.deliveryQuantity) > 0 || Number(row.receivedQuantity) > 0) && (!row.paperQuality.trim() || !row.specification.trim()))) {
    setReceiptFeedback('入库未完成：请补齐本次收料纸品的纸质和规格。')
    return
  }
  if (receiptUnsubmittedOrderNos.value.length) {
    setReceiptFeedback(`入库未完成：订单 ${receiptUnsubmittedOrderNos.value.join('、')} 尚未确认锁定，必须先确认订单并锁定后才能登记收料。`)
    return
  }
  if (!receiptDeliveryNoteNo.value.trim()) {
    setReceiptFeedback('入库未完成：请先填写送货单号（送货单当前显示“待识别”）。')
    focusReceiptField(manualDeliveryNoteInput.value)
    return
  }
  if (!receiptDeliveryDate.value) {
    setReceiptFeedback('入库未完成：请先填写送货日期。')
    focusReceiptField(manualDeliveryDateInput.value)
    return
  }
  if (!receiptAcceptanceDate.value) {
    setReceiptFeedback('入库未完成：请填写实际验收日期，用于供应商对账月份。')
    focusReceiptField(manualAcceptanceDateInput.value)
    return
  }
  if (candidateLines.some((row) => Number(row.damagedQuantity) + Number(row.rejectedQuantity) + Number(row.unusableQuantity) > Number(row.receivedQuantity))) {
    setReceiptFeedback('入库未完成：破损、拒收和其他不可用数量之和不能大于实收数量。')
    return
  }
  if (candidateLines.some((row) => Number(row.receivedQuantity) > Number(row.deliveryQuantity))) {
    setReceiptFeedback('入库未完成：实收数量不能大于送货数量。')
    return
  }
  if (receiptEntryMode.value === 'MANUAL' && candidateLines.some((row) => row.sourceType === 'FORMAL_ORDER' && receiptLineEffectiveQuantity(row) > row.remainingQuantity)) {
    setReceiptFeedback('入库未完成：人工录入的有效收料不能大于该订单明细当前待收数量。')
    return
  }
  if (candidateLines.some(row => [row.deliveryQuantity, row.receivedQuantity, row.damagedQuantity, row.rejectedQuantity, row.unusableQuantity].some(value => !Number.isFinite(Number(value)) || Number(value) < 0))) {
    setReceiptFeedback('入库未完成：收料数量必须是大于或等于 0 的有效数字。')
    return
  }
  if (receiptEntryMode.value === 'MANUAL' && candidateLines.some(row => row.selectedForReceipt === true && Number(row.receivedQuantity) <= 0)) {
    setReceiptFeedback('入库未完成：请为每条勾选纸品填写大于 0 的本次实际收到数量；未到货纸品请取消勾选。')
    return
  }
  const linesToSubmit = candidateLines.filter((row) => Number(row.deliveryQuantity) > 0 || Number(row.receivedQuantity) > 0)
  if (linesToSubmit.some(receiptReplacementNeedsReview)) {
    setReceiptFeedback('历史补单收料尚未关联，请核对原收料后通过冲销重录关联补单，再继续入库。')
    return
  }
  if (!linesToSubmit.length) {
    setReceiptFeedback('入库未完成：请至少填写一条大于 0 的送货或实收数量。')
    return
  }
  const invalidPriceLine = linesToSubmit.find((row) => {
    if (freeReplacement(row)) return false
    const price = String(row.unitPrice ?? '').trim()
    return (receiptLineEffectiveQuantity(row) > 0 && (!price || Number(price) <= 0)) || (price !== '' && !/^\d{1,12}(\.\d{1,6})?$/.test(price))
  })
  if (invalidPriceLine) {
    setReceiptFeedback('入库未完成：有效入库明细必须填写大于 0 的单价，最多 12 位整数和 6 位小数。')
    return
  }
  savingReceipt.value = true
  const willCompleteOrder = manualReceiptWillCompleteOrder.value
  const includesAdHoc = hasAdHocReceiptLines.value
  const targetOrderNos = manualReceiptOrderNos.value.join('、')
  try {
    for (const row of candidateLines) {
      const effective = receiptLineEffectiveQuantity(row)
      if (effective > 0 && (!row.allocations?.length || row.allocations.some(part => !part.location_id || Number(part.quantity) <= 0) || Math.abs(row.allocations.reduce((sum, part) => sum + Number(part.quantity), 0) - effective) > 0.00001)) {
        throw new Error(`${row.contractNo} ${row.itemNo}：请选择入库仓位，分仓合计须等于有效入库数量。`)
      }
    }
    currentReceipt.value = await cartonProcurementApi.createReceipt({
      post_immediately: true,
      factory_id: selectedFactoryId.value,
      delivery_note_no: receiptDeliveryNoteNo.value.trim(),
      delivery_date: receiptDeliveryDate.value,
      acceptance_date: receiptAcceptanceDate.value,
      import_batch_id: receiptEntryMode.value === 'MANUAL' ? null : receiptBatchId.value,
      note: receiptCorrectionNote.value || (receiptEntryMode.value === 'MANUAL'
        ? `人工批量录入订单收料：${manualReceiptOrderNos.value.join('、')}`
        : `来源文件：${selectedReceiptFileName.value}；已逐行人工复核；非正式/打板明细 ${adHocReceiptLineCount.value} 行`),
      lines: linesToSubmit.map((row) => ({
        source_type: row.sourceType,
        replenishment_issue_id: row.replenishmentIssueId || undefined,
        order_line_id: row.orderLineId || null,
        customer_code: row.customerCode,
        contract_no: row.contractNo,
        item_no: row.itemNo,
        packaging_type: row.packagingType,
        paper_quality: row.paperQuality,
        specification: row.specification,
        unit: row.unit,
        currency: row.currency,
        delivered_quantity: Number(row.deliveryQuantity),
        received_quantity: Number(row.receivedQuantity),
        damaged_quantity: Number(row.damagedQuantity),
        rejected_quantity: Number(row.rejectedQuantity),
        unusable_quantity: Number(row.unusableQuantity),
        unit_price: freeReplacement(row) ? undefined : Number(row.unitPrice),
        location: row.location,
        location_allocations: receiptLineEffectiveQuantity(row) > 0 ? row.allocations : [],
        feedback_note: row.sourceType === 'AD_HOC'
          ? '送货单未匹配正式订单，作为非正式/打板收料人工复核'
          : receiptEntryMode.value === 'MANUAL' ? '仓管人工录入收料' : '导入识别后人工复核',
      })),
    })
    receiptAcceptanceDate.value = currentReceipt.value.acceptance_date ?? ''
    if (currentReceipt.value.status !== 'POSTED') {
      setReceiptFeedback(currentReceipt.value.status === 'REVERSED'
        ? '原入库单已被冲销，本次重试没有再次入库，请到收料历史查看原记录。'
        : '此单尚未入库，请继续确认原单；不要另建一张重复收料单。')
      return
    }
    const message = includesAdHoc
      ? `入库成功：送货单 ${receiptDeliveryNoteNo.value} 已生成独立入库流水，并纳入对应月份月结。`
      : willCompleteOrder
      ? `入库成功：订单 ${targetOrderNos} 的全部明细已收齐并自动完成。`
      : `入库成功：送货单 ${receiptDeliveryNoteNo.value} 已生成库存流水，未收齐订单保持“部分收料”。`
    // Keep the posted receipt locked before refreshing; a refresh failure is not a posting failure.
    setReceiptFeedback(message, 'success')
    try { await loadBackendData() } catch {
      setReceiptFeedback(`${message} 台账刷新失败，请刷新页面查看。`, 'success')
    }
  } catch (error) {
    setReceiptFeedback(`入库失败：${getApiErrorMessage(error)}`)
  } finally {
    savingReceipt.value = false
  }
}

async function confirmCurrentReceipt() {
  if (!currentReceipt.value || confirmingReceipt.value || currentReceipt.value.status !== 'PENDING_CONFIRMATION') return
  if (currentReceipt.value.lines.some(line => line.responsibility !== 'SUPPLIER' && Number(line.effective_quantity) > 0 && !(Number(line.unit_price) > 0))) {
    setReceiptFeedback('确认入库未完成：有效入库明细必须填写大于 0 的单价；这张待确认收料单缺价，请先作废后重新登记并补齐单价。')
    return
  }
  confirmingReceipt.value = true
  try {
    const willCompleteOrder = manualReceiptWillCompleteOrder.value
    const includesAdHoc = hasAdHocReceiptLines.value
    const targetOrderNos = manualReceiptOrderNos.value.join('、')
    currentReceipt.value = await cartonProcurementApi.confirmReceipt(
      selectedFactoryId.value,
      currentReceipt.value.id,
      currentReceipt.value.revision,
    )
    receiptAcceptanceDate.value = currentReceipt.value.acceptance_date ?? ''
    const confirmedReceiptNo = currentReceipt.value.receipt_no
    await loadBackendData()
    setReceiptFeedback(includesAdHoc
      ? `收料单 ${confirmedReceiptNo} 已人工确认；非正式/打板明细已生成独立入库流水，并纳入对应月份月结。`
      : willCompleteOrder
      ? `收料单 ${confirmedReceiptNo} 已确认入库，订单 ${targetOrderNos} 的全部明细已收齐并自动完成。`
      : `收料单 ${confirmedReceiptNo} 已确认入库；后端已生成库存流水，未收齐订单保持“部分收料”。`, 'success')
  } catch (error) {
    setReceiptFeedback(`确认入库失败：${getApiErrorMessage(error)}`)
  } finally {
    confirmingReceipt.value = false
  }
}

async function generateClosingSnapshot() {
  if (!apiConnected.value || !canManageClosingPrices.value || closingBusyId.value || !closingPeriod.value) return
  const factory = selectedFactoryId.value, period = closingPeriod.value, generation = ++closingGeneration
  const current = () => factory === selectedFactoryId.value && generation === closingGeneration
  closingQueryPeriod.value = period
  closingBusyId.value = 'generate'
  try {
    const closings = await cartonProcurementApi.generateClosings(factory, period)
    if (!current()) return
    closingRecords.value = [...closingRecords.value.filter(row => !closings.some(next => next.id === row.id)), ...closings]
    localClosings.splice(0, localClosings.length, ...closingRecords.value.map(mapClosing))
    actionMessage.value = `已生成 ${period} 月结草稿，共 ${closings.filter(row => row.status !== 'LOCKED').length} 份待重新核对；已锁账快照保留。`
  } catch (error) {
    if (current()) actionMessage.value = `月结生成失败：${getApiErrorMessage(error)}`
  } finally {
    if (current()) closingBusyId.value = ''
  }
}

function closingNextStatus(status: CartonClosingResponse['status']) {
  return ({ DRAFT: 'PENDING', PENDING: 'CONFIRMED', CONFIRMED: 'LOCKED' } as const)[status as 'DRAFT' | 'PENDING' | 'CONFIRMED']
}

function closingActionLabel(status: CartonClosingResponse['status']) {
  return ({ DRAFT: '提交核对', PENDING: '核对确认', CONFIRMED: '最终锁账', LOCKED: '已最终锁账' } as const)[status]
}

function closingRecord(rowId: string) {
  return closingRecords.value.find((row) => row.id === rowId)
}

function closingQuantityText(rowId: string, field: 'opening_quantity' | 'inbound_quantity' | 'outbound_quantity' | 'adjustment_quantity' | 'ending_quantity') {
  const amounts = closingRecord(rowId)?.quantities_by_unit ?? []
  return amounts.map(amount => {
    const value = Number(amount[field])
    const prefix = value > 0 && (field === 'inbound_quantity' || field === 'adjustment_quantity') ? '+' : value > 0 && field === 'outbound_quantity' ? '-' : ''
    return `${prefix}${value.toLocaleString('zh-CN', { maximumFractionDigits: 4 })} ${amount.unit}`
  }).join('\n') || '—'
}

function closingButtonLabel(rowId: string) {
  const closing = closingRecord(rowId)
  return closing ? closingActionLabel(closing.status) : '等待正式数据'
}

function closingButtonHint(rowId: string) {
  const closing = closingRecord(rowId)
  if (!closing) return '等待正式数据'
  if (closing.status === 'LOCKED' && closing.snapshot_stale) return '已锁账快照与当前流水不一致，请主管核对并按顺序解锁重核'
  if (closing.quantity_snapshot_missing) return closing.status === 'LOCKED' ? '旧锁账未保存分单位数量，原金额保留；如需补齐请解锁重核' : '旧月结未保存分单位数量，请重新生成草稿'
  if (closing.status === 'LOCKED') return '最终锁账后，禁止新增和冲销影响本期结存的流水'
  if (closing.snapshot_stale) return '收发数据已有变动，请重新生成草稿并核对'
  if (closing.status === 'CONFIRMED' && closing.period >= businessTodayIso().slice(0, 7)) return '月份尚未结束，可继续正常收发货'
  if (closing.status === 'CONFIRMED' && !canFinalizeClosing.value) return '最终锁账须由有权限的主管执行'
  return closing.status === 'CONFIRMED' ? '月份已结束，核对完成后可最终锁账' : '核对确认不限制正常收发货'
}

function closingButtonDisabled(rowId: string) {
  const closing = closingRecord(rowId)
  return !apiConnected.value || !authStore.can('carton_procurement:closing_manage')
    || !closing || closing.status === 'LOCKED' || Boolean(closingBusyId.value) || closing.snapshot_stale || closing.quantity_snapshot_missing
    || (closing.status === 'CONFIRMED' && (!canFinalizeClosing.value || closing.period >= businessTodayIso().slice(0, 7)))
    || (closing.status !== 'DRAFT' && Boolean(closing.pricing_issues?.length))
}

function openClosingDecision(closing: CartonClosingResponse, action: 'LOCK' | 'UNLOCK') {
  if (!canFinalizeClosing.value || closingBusyId.value) return
  closingDecision.value = { closing, action }
  closingDecisionReason.value = ''
  closingDecisionError.value = ''
}

async function confirmClosingDecision() {
  const decision = closingDecision.value
  const factoryId = selectedFactoryId.value
  if (!decision || closingBusyId.value || !canFinalizeClosing.value) return
  if (decision.action === 'UNLOCK' && closingDecisionReason.value.trim().length < 4) {
    closingDecisionError.value = '请填写至少 4 个字的解锁原因。'
    return
  }
  if (decision.action === 'LOCK' && closingButtonDisabled(decision.closing.id)) {
    closingDecisionError.value = closingButtonHint(decision.closing.id)
    return
  }
  closingBusyId.value = decision.closing.id
  try {
    const updated = decision.action === 'UNLOCK'
      ? await cartonProcurementApi.unlockClosing(factoryId, decision.closing, closingDecisionReason.value.trim())
      : await cartonProcurementApi.updateClosingStatus(factoryId, decision.closing, 'LOCKED')
    if (selectedFactoryId.value !== factoryId) return
    closingRecords.value = closingRecords.value.map((row) => row.id === updated.id ? updated : row)
    localClosings.splice(0, localClosings.length, ...closingRecords.value.map(mapClosing))
    closingDecision.value = null
    actionMessage.value = decision.action === 'UNLOCK'
      ? `${updated.customer_name} ${updated.period} ${updated.currency} 已解锁并退回草稿，原因已留痕；更正后需重新生成、核对确认。`
      : `${updated.customer_name} ${updated.period} ${updated.currency} 已最终锁账。`
  } catch (error) {
    if (selectedFactoryId.value !== factoryId) return
    const message = getApiErrorMessage(error)
    closingDecisionError.value = message.includes('Not Found') ? '当前后端尚未启用解锁接口，账目未改动。' : `操作失败：${message}`
  } finally {
    closingBusyId.value = ''
  }
}

function openPriceConfirmation(issue: CartonPricingIssue) {
  pricingTarget.value = issue
  pricingAmount.value = ''
  pricingZeroConfirmed.value = false
  pricingReason.value = ''
  pricingFeedback.value = ''
}

async function confirmClosingPrice() {
  const target = pricingTarget.value
  if (!target || pricingBusy.value || !canManageClosingPrices.value) return
  if (!pricingAmount.value.trim() || !Number.isFinite(Number(pricingAmount.value)) || Number(pricingAmount.value) < 0) {
    pricingFeedback.value = '请输入有效的单价。'
    return
  }
  if (Number(pricingAmount.value) === 0 && !pricingZeroConfirmed.value) {
    pricingFeedback.value = '零单价需要明确勾选免费物料。'
    return
  }
  if (pricingReason.value.trim().length < 4) {
    pricingFeedback.value = '请填写至少 4 个字的核价依据。'
    return
  }
  const factoryId = selectedFactoryId.value
  pricingBusy.value = true
  let saved = false
  try {
    await cartonProcurementApi.confirmInventoryPrice(target.movement_id, {
      factory_id: factoryId, unit_price: pricingAmount.value,
      zero_price_confirmed: pricingZeroConfirmed.value, reason: pricingReason.value.trim(),
    })
    saved = true
    if (factoryId !== selectedFactoryId.value) return
    pricingTarget.value = null
    actionMessage.value = '单价已核实，受影响的未锁账月结已退回草稿，请重新核对。'
    const rows = await cartonProcurementApi.listClosings(factoryId)
    if (factoryId !== selectedFactoryId.value) return
    closingRecords.value = rows
    localClosings.splice(0, localClosings.length, ...rows.map(mapClosing))
  } catch (error) {
    if (factoryId !== selectedFactoryId.value) return
    if (saved) actionMessage.value = '单价已保存，月结刷新失败，请点击刷新查看，勿重复补价。'
    else pricingFeedback.value = `核价失败：${getApiErrorMessage(error)}`
  } finally {
    pricingBusy.value = false
  }
}

async function advanceClosing(rowId: string) {
  const closing = closingRecords.value.find((row) => row.id === rowId)
  if (!closing || closingButtonDisabled(rowId)) return
  if (closing.status === 'CONFIRMED') {
    openClosingDecision(closing, 'LOCK')
    return
  }
  const nextStatus = closingNextStatus(closing.status)
  if (!nextStatus) return
  closingBusyId.value = rowId
  try {
    const updated = await cartonProcurementApi.updateClosingStatus(selectedFactoryId.value, closing, nextStatus)
    closingRecords.value = closingRecords.value.map((row) => row.id === updated.id ? updated : row)
    localClosings.splice(0, localClosings.length, ...closingRecords.value.map(mapClosing))
    actionMessage.value = `${updated.customer_name} ${updated.period} 月结已更新为“${mapClosing(updated).status}”。`
  } catch (error) {
    actionMessage.value = `月结状态更新失败：${getApiErrorMessage(error)}`
  } finally {
    closingBusyId.value = ''
  }
}

function canBulkAdvanceExceptions(status: CartonExceptionResponse['status']) {
  return apiConnected.value && !exceptionBusyId.value && selectedExceptionNos.value.length > 0
    && selectedExceptionNos.value.length <= 500 && authStore.can('carton_procurement:exception_manage', selectedFactoryId.value)
    && selectedExceptionNos.value.every(id => exceptionRecord(id)?.status === status)
}

async function bulkAdvanceExceptions(status: CartonExceptionResponse['status']) {
  if (!canBulkAdvanceExceptions(status)) return
  const nextStatus = nextExceptionStatus(status)
  const note = bulkExceptionNote.value.trim()
  const factoryId = selectedFactoryId.value
  const records = selectedExceptionNos.value.map(id => exceptionRecord(id)!)
  exceptionBusyId.value = '__BULK__'
  try {
    const updated = await cartonProcurementApi.bulkUpdateExceptions(factoryId, records, nextStatus, note)
    if (factoryId !== selectedFactoryId.value) return
    const byId = new Map(updated.map(row => [row.id, row]))
    exceptionRecords.value = exceptionRecords.value.map(row => byId.get(row.id) || row)
    localExceptions.splice(0, localExceptions.length, ...exceptionRecords.value.map(mapException))
    selectedExceptionNos.value = selectedExceptionNos.value.filter(id => !records.some(row => row.exception_no === id))
    bulkExceptionNote.value = ''
    actionMessage.value = `已批量更新 ${updated.length} 条异常。`
  } catch (error) {
    if (factoryId === selectedFactoryId.value) actionMessage.value = `批量处理未生效：${getApiErrorMessage(error)}`
  } finally { exceptionBusyId.value = '' }
}

function nextExceptionStatus(status: CartonExceptionResponse['status']) {
  return ({ OPEN: 'IN_PROGRESS', IN_PROGRESS: 'RESOLVED', RESOLVED: 'CLOSED', CLOSED: 'OPEN' } as const)[status]
}

function exceptionActionLabel(status: CartonExceptionResponse['status']) {
  return ({ OPEN: '开始处理', IN_PROGRESS: '标记已解决', RESOLVED: '关闭异常', CLOSED: '重新打开' } as const)[status]
}

function exceptionRecord(displayId: string) {
  return exceptionRecords.value.find((row) => row.exception_no === displayId)
}

function exceptionRecordId(displayId: string) {
  return exceptionRecord(displayId)?.id ?? displayId
}

function exceptionButtonLabel(displayId: string) {
  const exception = exceptionRecord(displayId)
  return exception ? exceptionActionLabel(exception.status) : '等待正式数据'
}

function exceptionButtonDisabled(displayId: string) {
  const exception = exceptionRecord(displayId)
  return !exception || Boolean(exceptionBusyId.value)
}

async function advanceException(displayId: string) {
  const exception = exceptionRecords.value.find((row) => row.exception_no === displayId)
  if (!exception) return
  const nextStatus = nextExceptionStatus(exception.status)
  const note = resolutionNotes[exception.id]?.trim() || exception.resolution_note
  exceptionBusyId.value = exception.id
  try {
    const updated = await cartonProcurementApi.updateException(selectedFactoryId.value, exception, nextStatus, note)
    exceptionRecords.value = exceptionRecords.value.map((row) => row.id === updated.id ? updated : row)
    localExceptions.splice(0, localExceptions.length, ...exceptionRecords.value.map(mapException))
    actionMessage.value = `异常 ${updated.exception_no} 已更新为“${mapException(updated).status}”。`
  } catch (error) {
    actionMessage.value = `异常更新失败：${getApiErrorMessage(error)}`
  } finally {
    exceptionBusyId.value = ''
  }
}

function refreshDemo() {
  void loadBackendData()
}
</script>

<template>
  <main class="min-h-screen bg-slate-100 text-[13px] leading-relaxed text-slate-900">
    <header class="sticky top-0 z-40 border-b border-slate-200 bg-white/95 backdrop-blur">
      <div class="mx-auto flex max-w-[1720px] items-center gap-3 px-4 py-2.5 sm:px-5">
        <RouterLink
          :to="warehouseDepartmentRoute"
          class="inline-flex h-9 shrink-0 items-center gap-2 whitespace-nowrap rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-600 transition hover:border-slate-300 hover:text-slate-950"
        >
          <ArrowLeft class="size-4" aria-hidden="true" />
          <span class="hidden sm:inline">PMC / 仓管模块</span>
          <span class="sm:hidden">返回</span>
        </RouterLink>

        <div class="flex min-w-0 items-center gap-2.5">
          <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-teal-700 text-white">
            <PackageCheck class="size-5" aria-hidden="true" />
          </span>
          <div class="min-w-0">
            <div class="truncate text-[15px] font-bold leading-tight">纸箱采购协同</div>
            <div class="hidden truncate text-[11px] text-slate-400 sm:block">Carton Procurement · 下单 / 收料 / 库存 / 月结</div>
          </div>
        </div>

        <label v-if="showSharedSearch" class="relative ml-1 hidden lg:block">
          <Search class="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
          <input
            v-model="globalSearch"
            placeholder="搜索合同 / PO / 货号 / 单据..."
            class="h-8 w-72 rounded-lg border border-slate-200 bg-slate-50 pl-8 pr-3 text-[12px] outline-none transition focus:border-teal-500 focus:bg-white"
          >
        </label>

        <div class="ml-auto flex items-center gap-2">
          <RouterLink :to="{ path: '/carton-supplier-management', query: { factory: selectedFactoryId } }" class="inline-flex h-8 items-center rounded-lg border border-teal-200 bg-teal-50 px-2.5 text-xs font-semibold text-teal-800">供应商协同</RouterLink>
          <span class="hidden h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 text-[12px] font-medium text-slate-600 md:inline-flex">
            <Building2 class="size-4" aria-hidden="true" />
            当前厂区：{{ activeFactory.shortName }}
          </span>
          <AccountMenu />
        </div>
      </div>

      <nav class="mx-auto flex max-w-[1720px] items-center gap-1 overflow-x-auto px-4 sm:px-5" aria-label="纸箱采购协同功能">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          type="button"
          class="inline-flex items-center gap-1.5 whitespace-nowrap rounded-t-lg px-3 py-2 text-[12px] font-semibold transition"
          :class="activeModule === tab.id ? 'bg-teal-700 text-white' : 'text-slate-500 hover:bg-slate-50 hover:text-slate-900'"
          :aria-current="activeModule === tab.id ? 'page' : undefined"
          @click="openModule(tab.id)"
        >
          <component :is="tab.icon" class="size-4" aria-hidden="true" />
          <span>{{ tab.label }}</span>
        </button>
      </nav>
    </header>

    <div class="mx-auto max-w-[1720px] space-y-4 px-4 pb-12 pt-4 sm:px-5">
      <section class="flex flex-col gap-3 rounded-xl border border-teal-200 bg-white px-4 py-3 shadow-[0_1px_2px_rgba(15,23,42,0.04)] lg:flex-row lg:items-center">
        <div class="flex min-w-0 items-start gap-3">
          <span class="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-teal-50 text-teal-700">
            <ShieldCheck class="size-4" aria-hidden="true" />
          </span>
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2">
              <h1 class="text-[14px] font-bold text-slate-950">{{ activeTabItem.label }}</h1>
              <span
                class="rounded-full px-2 py-0.5 text-[10px] font-bold ring-1 ring-inset"
                :class="apiConnected ? 'bg-emerald-50 text-emerald-700 ring-emerald-200' : 'bg-amber-50 text-amber-700 ring-amber-200'"
              >{{ apiConnected ? '正式台账 · 后端已连接' : '只读演示 · 后端不可用' }}</span>
            </div>
            <p class="mt-0.5 text-[11px] text-slate-500">{{ actionMessage }}</p>
          </div>
        </div>

        <div class="ml-auto flex flex-wrap items-center gap-2">
          <label v-if="showSharedSearch" class="relative block lg:hidden">
            <Search class="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
            <input
              v-model="globalSearch"
              aria-label="全局搜索"
              placeholder="搜索单据..."
              class="h-9 w-44 rounded-lg border border-slate-200 bg-slate-50 pl-8 pr-3 text-[12px] outline-none focus:border-teal-500"
            >
          </label>
          <select
            v-if="!(activeTab === 'closing' && closingView === 'SUPPLIER') && activeTab !== 'audit' && !(activeTab === 'inventory' && showStocktake) && activeTab !== 'master-data' && activeTab !== 'inventory-summary' && activeTab !== 'orders' && activeTab !== 'receipts' && activeTab !== 'inventory'"
            v-model="selectedCustomer"
            aria-label="客户筛选"
            class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-700 outline-none focus:border-teal-500"
          >
            <option v-for="customer in customerFilterOptions" :key="customer" :value="customer">{{ customer }}</option>
          </select>
          <button
            type="button"
            class="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-600 transition hover:border-slate-300 hover:text-slate-950"
            @click="refreshDemo"
          >
            <RefreshCw class="size-4" :class="backendLoading ? 'animate-spin' : ''" aria-hidden="true" />
            刷新
          </button>
        </div>
      </section>

      <nav v-if="activeModule === 'orders'" aria-label="订单管理子页面" class="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-white p-2 shadow-sm">
        <button v-for="page in [{ id: 'orders' as const, label: '订单台账' }, { id: 'weekly-check' as const, label: '排期核对与交期提醒' }]" :key="page.id" type="button" :aria-current="activeTab === page.id ? 'page' : undefined" class="rounded-lg px-4 py-2 text-xs font-semibold" :class="activeTab === page.id ? 'bg-teal-50 text-teal-800 ring-1 ring-teal-200' : 'text-slate-500 hover:bg-slate-50'" @click="setActiveTab(page.id)">{{ page.label }}</button>
      </nav>
      <nav v-if="activeModule === 'inventory'" aria-label="库存管理子页面" class="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-white p-2 shadow-sm">
        <button v-for="page in [{ id: 'inventory' as const, label: '实时库存' }, { id: 'inventory-summary' as const, label: '收发汇总' }, { id: 'inventory-movements' as const, label: '库存流水' }]" :key="page.id" type="button" :aria-current="activeTab === page.id && !showStocktake && !showInventoryImport ? 'page' : undefined" class="rounded-lg px-4 py-2 text-xs font-semibold" :class="activeTab === page.id && !showStocktake && !showInventoryImport ? 'bg-teal-50 text-teal-800 ring-1 ring-teal-200' : 'text-slate-500 hover:bg-slate-50'" @click="openInventoryPage(page.id)">{{ page.label }}</button>
        <button type="button" :disabled="!apiConnected" :aria-current="activeTab === 'inventory' && showStocktake ? 'page' : undefined" class="rounded-lg px-4 py-2 text-xs font-semibold disabled:opacity-40" :class="showStocktake ? 'bg-teal-50 text-teal-800 ring-1 ring-teal-200' : 'text-slate-500 hover:bg-slate-50'" @click="openInventoryPage('inventory', true)">库存盘点</button>
        <button type="button" :aria-current="activeTab === 'inventory' && showInventoryImport ? 'page' : undefined" class="rounded-lg px-4 py-2 text-xs font-semibold" :class="showInventoryImport ? 'bg-teal-50 text-teal-800 ring-1 ring-teal-200' : 'text-slate-500 hover:bg-slate-50'" @click="openInventoryPage('inventory', false, true)">期初库存</button>
      </nav>

      <section v-if="activeTab === 'dashboard'" class="space-y-4">
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <article class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div class="flex items-center justify-between text-[11px] font-semibold text-slate-500">
              待跟进订单
              <ClipboardCheck class="size-4 text-teal-600" aria-hidden="true" />
            </div>
            <div class="mt-2 text-3xl font-bold tabular-nums text-slate-950">{{ pendingOrderCount }}</div>
            <p class="mt-1 text-[11px] text-slate-400">人工录单并确认后才成为正式订单</p>
          </article>
          <article class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div class="flex items-center justify-between text-[11px] font-semibold text-slate-500">
              本周核对与提醒
              <CalendarClock class="size-4 text-amber-600" aria-hidden="true" />
            </div>
            <div class="mt-2 text-3xl font-bold tabular-nums text-slate-950">{{ weeklyAttentionCount }}</div>
            <p class="mt-1 text-[11px] text-slate-400">汇总漏单风险与下周查货交期提醒</p>
          </article>
          <article class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div class="flex items-center justify-between text-[11px] font-semibold text-slate-500">
              当前库存结存
              <Boxes class="size-4 text-blue-600" aria-hidden="true" />
            </div>
            <div aria-label="看板库存数量合计" class="mt-2 break-words text-2xl font-bold tabular-nums text-slate-950">{{ inventoryBalanceSummary }}</div>
            <p class="mt-1 text-[11px] text-slate-400">后端在线时取自不可变库存流水</p>
          </article>
          <article class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div class="flex items-center justify-between text-[11px] font-semibold text-slate-500">
              未关闭异常
              <AlertTriangle class="size-4 text-red-600" aria-hidden="true" />
            </div>
            <div class="mt-2 text-3xl font-bold tabular-nums text-slate-950">{{ openExceptionCount }}</div>
            <p class="mt-1 text-[11px] text-slate-400">异常需责任人反馈并人工关闭</p>
          </article>
        </div>

        <article data-testid="business-order-collaboration-panel" class="overflow-hidden rounded-xl border border-teal-200 bg-white shadow-sm">
          <div class="border-b border-teal-100 bg-gradient-to-r from-teal-50 via-white to-amber-50 px-4 py-4">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div class="flex flex-wrap items-center gap-2">
                  <h2 class="text-[14px] font-bold text-slate-950">业务下单协同面板</h2>
                  <span class="rounded-full bg-teal-100 px-2 py-0.5 text-[9px] font-bold text-teal-800 ring-1 ring-inset ring-teal-200">后端持久化</span>
                </div>
                <p class="mt-1 text-[11px] leading-5 text-slate-600">对接业务接单员上传的客户排期，集中提醒漏下单与数量更新；处理状态沿用异常工单，导入不会自动建单或改单。</p>
              </div>
              <button type="button" class="inline-flex h-9 items-center gap-2 rounded-lg bg-teal-700 px-3 text-[11px] font-bold text-white hover:bg-teal-800" @click="weeklyCheckMode = 'ORDER_GAP'; setActiveTab('weekly-check')"><Upload class="size-3.5" />导入 / 更新业务排期</button>
            </div>
            <div class="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
              <div class="rounded-lg border border-slate-200 bg-white/90 px-3 py-2"><div class="text-[9px] font-bold text-slate-400">当前待处理</div><div class="mt-1 text-xl font-bold text-slate-950 tabular-nums">{{ businessAlertSummary.total }}</div></div>
              <div class="rounded-lg border border-red-200 bg-red-50/80 px-3 py-2"><div class="text-[9px] font-bold text-red-600">漏下单</div><div class="mt-1 text-xl font-bold text-red-800 tabular-nums">{{ businessAlertSummary.missing }}</div></div>
              <div class="rounded-lg border border-amber-200 bg-amber-50/80 px-3 py-2"><div class="text-[9px] font-bold text-amber-700">需追加</div><div class="mt-1 text-xl font-bold text-amber-900 tabular-nums">{{ businessAlertSummary.increase }}</div></div>
              <div class="rounded-lg border border-violet-200 bg-violet-50/80 px-3 py-2"><div class="text-[9px] font-bold text-violet-700">需减单 / 退单</div><div class="mt-1 text-xl font-bold text-violet-900 tabular-nums">{{ businessAlertSummary.decrease }}</div></div>
            </div>
          </div>

          <div class="flex flex-wrap items-end gap-3 border-b border-slate-200 bg-slate-50/70 px-4 py-3">
            <label class="space-y-1"><span class="block text-[9px] font-bold text-slate-500">处理状态</span><select v-model="businessAlertStatusFilter" aria-label="业务提醒处理状态" class="h-8 rounded-lg border border-slate-200 bg-white px-2.5 text-[10px] font-semibold"><option value="ACTIONABLE">待处理 / 处理中</option><option value="ALL">全部状态</option></select></label>
            <label class="space-y-1"><span class="block text-[9px] font-bold text-slate-500">提醒类型</span><select v-model="businessAlertKindFilter" aria-label="业务提醒类型" class="h-8 rounded-lg border border-slate-200 bg-white px-2.5 text-[10px] font-semibold"><option value="ALL">全部类型</option><option value="MISSING_ORDER">漏下单</option><option value="QUANTITY_INCREASE">需追加</option><option value="QUANTITY_DECREASE">需减单 / 退单</option></select></label>
            <span class="ml-auto text-[10px] text-slate-500">显示 {{ visibleBusinessOrderAlerts.length }} 条 · 来源为最近一次业务排期核对</span>
          </div>

          <div v-if="visibleBusinessOrderAlerts.length" class="divide-y divide-slate-100">
            <div v-for="alert in visibleBusinessOrderAlerts.slice(0, 8)" :key="alert.id" class="grid gap-3 px-4 py-3 lg:grid-cols-[minmax(0,1.2fr)_minmax(240px,0.8fr)_auto] lg:items-center">
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <span class="rounded-full px-2 py-0.5 text-[9px] font-bold ring-1 ring-inset" :class="businessAlertKindClass(alert.kind)">{{ businessAlertKindLabel(alert.kind) }}</span>
                  <span class="font-mono text-[9px] text-slate-400">{{ alert.alertNo }}</span>
                  <span class="rounded-full bg-slate-100 px-2 py-0.5 text-[9px] font-bold text-slate-600">{{ businessAlertStatusLabel(alert.exception.status) }}</span>
                </div>
                <div class="mt-1.5 truncate text-[12px] font-bold text-slate-950">{{ alert.customerName }} · {{ alert.contractNo || '合同待识别' }} · {{ alert.itemNo || '货号待识别' }}</div>
                <div class="mt-1 truncate text-[10px] text-slate-500">{{ alert.productName || '产品名称待补充' }}<template v-if="alert.orderNo"> · 纸箱订单 {{ alert.orderNo }}（{{ orderStatusLabel(alert.orderStatus) }}）</template></div>
              </div>
              <div class="min-w-0">
                <div class="text-[11px] font-semibold text-slate-700">
                  <template v-if="alert.kind === 'MISSING_ORDER'">排期数量 {{ formatNumber(alert.scheduleQuantity) }}</template>
                  <template v-else>订单 {{ formatNumber(alert.orderQuantity) }} → 排期 {{ formatNumber(alert.scheduleQuantity) }} <span :class="alert.differenceQuantity > 0 ? 'text-amber-700' : 'text-violet-700'">（{{ alert.differenceQuantity > 0 ? '+' : '' }}{{ formatNumber(alert.differenceQuantity) }}）</span></template>
                </div>
                <div class="mt-1 truncate text-[9px] text-slate-400">{{ alert.sourceOperatorName }} · {{ alert.sourceFilename }} · {{ alert.sourceCreatedAt.replace('T', ' ').slice(0, 16) }}</div>
                <div class="mt-1 truncate text-[9px] text-slate-500" :title="alert.suggestion">{{ alert.suggestion }}</div>
              </div>
              <div class="flex flex-wrap justify-start gap-2 lg:justify-end">
                <button type="button" :disabled="businessAlertActionDisabled(alert)" :aria-label="`${businessAlertActionLabel(alert)} ${alert.alertNo}`" class="h-8 rounded-lg bg-teal-700 px-3 text-[10px] font-bold text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:bg-slate-300" @click="openBusinessAlertOrder(alert)">{{ businessAlertActionLabel(alert) }}</button>
                <button type="button" :disabled="Boolean(exceptionBusyId)" :aria-label="`${alert.exception.status === 'OPEN' ? '开始处理' : '查看处理'} ${alert.alertNo}`" class="h-8 rounded-lg border border-slate-200 bg-white px-3 text-[10px] font-bold text-slate-600 hover:border-teal-200 hover:text-teal-700 disabled:opacity-50" @click="handleBusinessAlertStatus(alert)">{{ alert.exception.status === 'OPEN' ? '开始处理' : alert.exception.status === 'IN_PROGRESS' ? '填写处理结果' : '查看处理结果' }}</button>
              </div>
            </div>
            <div v-if="visibleBusinessOrderAlerts.length > 8" class="border-t border-slate-100 px-4 py-3 text-center"><button type="button" class="text-[10px] font-bold text-teal-700" @click="setActiveTab('exceptions')">还有 {{ visibleBusinessOrderAlerts.length - 8 }} 条，前往异常处理查看</button></div>
          </div>
          <div v-else class="px-4 py-10 text-center text-[11px] text-slate-400">当前没有符合条件的业务漏单或订单更新提醒；可导入最新客户排期进行核对。</div>
        </article>

        <div class="grid gap-4 xl:grid-cols-[1.35fr_0.65fr]">
          <article class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 class="text-[14px] font-bold text-slate-950">从客户排期到月结的协同链路</h2>
                <p class="mt-1 text-[11px] text-slate-500">关键节点均保留人工确认，任何导入都不会直接形成正式业务数据。</p>
              </div>
              <span class="rounded-full bg-teal-50 px-2.5 py-1 text-[10px] font-bold text-teal-700 ring-1 ring-inset ring-teal-200">V2.1 核心闭环</span>
            </div>
            <div class="mt-5 grid gap-3 md:grid-cols-5">
              <button v-for="(step, index) in [
                { label: '人工下单', detail: '历史规格复用', tab: 'orders' },
                { label: '周排期核对', detail: '只提示不建单', tab: 'weekly-check' },
                { label: '送货与收料', detail: '逐行反馈数量', tab: 'receipts' },
                { label: '库存流水', detail: '入出调整留痕', tab: 'inventory' },
                { label: '客户月结', detail: '对账后再锁定', tab: 'closing' },
              ]"
              :key="step.label"
              type="button"
              class="relative rounded-xl border border-slate-200 bg-slate-50 p-3 text-left transition hover:border-teal-300 hover:bg-teal-50"
              @click="setActiveTab(step.tab as CartonTab)"
              >
                <span class="text-[10px] font-bold text-teal-700">0{{ index + 1 }}</span>
                <div class="mt-2 font-bold text-slate-900">{{ step.label }}</div>
                <div class="mt-1 text-[10px] text-slate-500">{{ step.detail }}</div>
              </button>
            </div>
          </article>

          <article class="rounded-xl border border-slate-200 bg-slate-950 p-5 text-white shadow-sm">
            <div class="flex items-center gap-2 text-[14px] font-bold">
              <ShieldCheck class="size-4 text-teal-300" aria-hidden="true" />
              本阶段数据边界
            </div>
            <ul class="mt-4 space-y-3 text-[11px] text-slate-300">
              <li class="flex gap-2"><CheckCircle2 class="mt-0.5 size-4 shrink-0 text-teal-300" />供应商固定为系统配置，不作为日常筛选条件</li>
              <li class="flex gap-2"><CheckCircle2 class="mt-0.5 size-4 shrink-0 text-teal-300" />周排期核对漏单；下周查货合同倒推纸箱最迟交货日</li>
              <li class="flex gap-2"><CheckCircle2 class="mt-0.5 size-4 shrink-0 text-teal-300" />有效收料 = 实收 − 破损 − 拒收 − 其他不可用</li>
              <li class="flex gap-2"><CheckCircle2 class="mt-0.5 size-4 shrink-0 text-teal-300" />库存流水采用冲销方式纠错，后端禁止直接覆盖历史</li>
            </ul>
          </article>
        </div>

        <div class="grid gap-4 xl:grid-cols-2">
          <article class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div class="flex items-center justify-between">
              <h2 class="font-bold text-slate-950">近期订单</h2>
              <button type="button" class="text-[11px] font-bold text-teal-700" @click="setActiveTab('orders')">查看全部</button>
            </div>
            <div class="mt-3 divide-y divide-slate-100">
              <div v-for="row in visibleOrders.slice(0, 3)" :key="row.id" class="flex items-center gap-3 py-3">
                <span class="flex size-9 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-600"><ClipboardCheck class="size-4" /></span>
                <div class="min-w-0 flex-1">
                  <div class="truncate font-semibold text-slate-900">{{ row.contractNo }} · {{ row.itemNo }}</div>
                  <div class="mt-0.5 truncate text-[10px] text-slate-500">{{ row.customer }} · {{ row.materials.length }} 项纸品 · 计划交期 {{ formatMonthDay(row.dueDate) }}</div>
                </div>
                <span class="rounded-full px-2 py-0.5 text-[10px] font-bold ring-1 ring-inset" :class="toneClass(row.tone)">{{ row.status }}</span>
              </div>
            </div>
          </article>
          <article class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div class="flex items-center justify-between">
              <h2 class="font-bold text-slate-950">优先处理异常</h2>
              <button type="button" class="text-[11px] font-bold text-teal-700" @click="setActiveTab('exceptions')">进入异常处理</button>
            </div>
            <div class="mt-3 divide-y divide-slate-100">
              <div v-for="row in visibleExceptions.filter((item) => item.status !== '已关闭').slice(0, 3)" :key="row.id" class="py-3">
                <div class="flex items-center gap-2">
                  <span class="rounded-full px-2 py-0.5 text-[10px] font-bold ring-1 ring-inset" :class="toneClass(row.tone)">{{ row.type }}</span>
                  <span class="text-[10px] text-slate-400">{{ row.id }}</span>
                </div>
                <div class="mt-1.5 font-semibold text-slate-900">{{ row.title }}</div>
                <div class="mt-1 text-[10px] text-slate-500">{{ row.customer }} · {{ row.owner }} · {{ row.deadline }}</div>
              </div>
            </div>
          </article>
        </div>
      </section>

      <section v-else-if="activeTab === 'orders'" class="space-y-4">
        <div class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div>
            <h2 class="font-bold text-slate-950">纸箱合同订单台账</h2>
            <p class="mt-1 text-[11px] text-slate-500">待下单订单确认后整单锁定；再另行发行供应商采购单。有权限的仓管或主管可继续追加，也可减少尚未入库部分；全部到货后追加会恢复为“部分到货”。</p>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <a href="/templates/carton-history-order-import-template.xlsx" download="纸箱历史订单导入模板.xlsx" class="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3.5 text-[12px] font-bold text-slate-700 transition hover:border-teal-200 hover:bg-teal-50 hover:text-teal-700">
              <Download class="size-4" aria-hidden="true" />
              下载历史订单模板
            </a>
            <input ref="historyOrderFileInput" type="file" accept=".xlsx,.xlsm,.xls" class="hidden" aria-label="选择历史订单文件" @change="handleHistoryOrderFile">
            <button type="button" :disabled="!apiConnected || importingHistoryOrders" class="inline-flex h-9 items-center gap-2 rounded-lg border border-teal-200 bg-white px-3.5 text-[12px] font-bold text-teal-700 transition hover:bg-teal-50 disabled:cursor-not-allowed disabled:border-slate-200 disabled:text-slate-400" @click="triggerHistoryOrderImport">
              <Upload class="size-4" aria-hidden="true" />
              {{ importingHistoryOrders ? '正在导入…' : '导入历史订单' }}
            </button>
            <button type="button" :disabled="apiConnected && activeCustomers.length === 0 && !masterWorkspace.can_manage" class="inline-flex h-9 items-center gap-2 rounded-lg bg-teal-700 px-3.5 text-[12px] font-bold text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:bg-slate-300" @click="openOrderModal">
              <Plus class="size-4" aria-hidden="true" />
              新建纸箱订单
            </button>
          </div>
        </div>

        <div
          aria-label="订单交期提醒汇总"
          class="!mt-2 flex flex-wrap items-center justify-between gap-3 rounded-xl border px-4 py-3 shadow-sm"
          :class="urgentOrderDueCount > 0 ? 'border-amber-200 bg-amber-50' : 'border-emerald-200 bg-emerald-50'"
        >
          <div class="flex min-w-0 items-center gap-3">
            <span class="flex size-9 shrink-0 items-center justify-center rounded-lg" :class="urgentOrderDueCount > 0 ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'">
              <CalendarClock class="size-4" aria-hidden="true" />
            </span>
            <div>
              <div class="font-bold text-slate-950">订单交期提醒</div>
              <p class="mt-0.5 text-[10px] text-slate-500">按计划交期自动倒计时，逾期及 3 天内待交订单优先显示。</p>
            </div>
          </div>
          <div class="flex flex-wrap items-center gap-2 text-[11px] font-bold">
            <span class="rounded-full bg-red-600 px-3 py-1 text-white">逾期 {{ orderDueSummary.overdue }}</span>
            <span class="rounded-full bg-red-50 px-3 py-1 text-red-700 ring-1 ring-inset ring-red-200">今日 {{ orderDueSummary.today }}</span>
            <span class="rounded-full bg-amber-100 px-3 py-1 text-amber-800 ring-1 ring-inset ring-amber-200">未来 3 天 {{ orderDueSummary.dueSoon }}</span>
            <span v-if="urgentOrderDueCount === 0" class="text-emerald-700">当前没有紧急交期</span>
          </div>
        </div>

        <div aria-label="订单台账与筛选" class="rounded-xl border border-slate-200 bg-white shadow-sm">
        <div aria-label="订单筛选与批量操作" class="flex flex-wrap items-end gap-3 rounded-t-xl border-b border-slate-200 bg-white p-3">
          <label class="space-y-1"><span class="block text-[10px] font-bold text-slate-500">客户</span><select v-model="selectedCustomer" aria-label="客户筛选" class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-[11px] font-semibold outline-none focus:border-teal-500"><option v-for="customer in customerFilterOptions" :key="customer" :value="customer">{{ customer }}</option></select></label>
          <label class="space-y-1"><span class="block text-[10px] font-bold text-slate-500">订单状态</span><select v-model="orderStatusFilter" aria-label="订单状态筛选" class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-[11px] font-semibold outline-none focus:border-teal-500"><option value="ALL">全部状态</option><option value="CONFIRMED">待下单</option><option value="PENDING_SUPPLIER">已确认锁定</option><option value="PARTIALLY_RECEIVED">部分收料</option><option value="COMPLETED">已完成</option><option value="CANCELLED">已取消</option></select></label>
          <label class="space-y-1"><span class="block text-[10px] font-bold text-slate-500">计划交期</span><select v-model="orderDueFilter" aria-label="订单计划交期筛选" class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-[11px] font-semibold outline-none focus:border-teal-500"><option value="ALL">全部计划交期</option><option value="OVERDUE">已逾期</option><option value="TODAY">今日交期</option><option value="DUE_SOON">3 天内</option><option value="UPCOMING">后续交期</option></select></label>
          <div class="space-y-1"><span class="block text-[10px] font-bold text-slate-500">下单日期</span><DateRangeFilter v-model="orderDateRange" label="订单下单日期筛选" /></div>
          <label class="space-y-1"><span class="block text-[10px] font-bold text-slate-500">排序</span><select v-model="orderSort" aria-label="订单排序" class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-[11px] font-semibold outline-none focus:border-teal-500"><option value="DUE_ASC">交期由近到远</option><option value="DUE_DESC">交期由远到近</option><option value="ORDER_DESC">下单日期最新</option></select></label>
          <button type="button" aria-label="清空订单筛选" class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-xs text-slate-600" @click="clearOrderFilters">清空筛选</button>
          <button type="button" :disabled="!apiConnected || !selectedSubmittableOrderCount || submittingSupplierOrder" class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-teal-200 bg-teal-50 px-3 text-[11px] font-bold text-teal-700 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-white disabled:text-slate-400" @click="openBulkSubmitSupplierOrders"><ShieldCheck class="size-3.5" />{{ submittingSupplierOrder ? '正在确认…' : `确认订单并锁定（${selectedSubmittableOrderCount}）` }}</button>
          <button type="button" :disabled="!apiConnected || !selectedOrderNos.length || issuingSelectedPurchaseOrders || !canIssuePurchaseOrders" title="首次与非首次采购单均可多选发行；包含追加或减单时会先确认" class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-amber-600 px-3 text-[11px] font-bold text-white disabled:cursor-not-allowed disabled:bg-slate-300" @click="issueSelectedPurchaseOrders"><Send class="size-3.5" />{{ issuingSelectedPurchaseOrders ? '发行中…' : `发行供应商采购单（${selectedOrderNos.length}）` }}</button>
          <button type="button" :disabled="!apiConnected || !selectedOrderNos.length || exportingSelectedOrders" :title="!apiConnected ? '后端未连接，当前演示订单不能导出' : '累计对账表不代表向供应商新增下单'" class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-teal-200 px-3 text-[11px] font-bold text-teal-700 disabled:cursor-not-allowed disabled:border-slate-200 disabled:text-slate-400" @click="exportSelectedPurchaseOrders"><Download class="size-3.5" />{{ exportingSelectedOrders ? '合并生成中…' : '导出累计对账表' }}</button>
          <button type="button" :disabled="!selectedOrdersCanCancel || cancellingOrder" title="仅尚未确认锁定的待下单订单可批量取消" class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-red-200 px-3 text-[11px] font-bold text-red-700 disabled:opacity-40" @click="openBulkCancelOrders"><X class="size-3.5" />批量取消</button>
          <button v-if="canIssuePurchaseOrders" type="button" :disabled="!selectedOrdersCanDeleteHistory || deletingHistory" title="仅可删除无任何收料或库存记录的历史导入订单；最多选择 100 张，全部校验通过后一次删除" class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-red-200 px-3 text-[11px] font-bold text-red-700 disabled:opacity-40" @click="deleteHistoryTarget = null; deleteHistoryTargets = [...selectedOrders]; deleteHistoryReason = '历史订单导入有误'"><Trash2 class="size-3.5" />批量删除历史订单</button>
          <p v-if="canIssuePurchaseOrders && selectedOrders.length && !selectedOrdersCanDeleteHistory" class="basis-full text-[11px] text-red-700">批量删除仅限无任何收料或库存记录的历史导入订单；普通订单、已有收料记录（含待确认或已冲销）的订单不可删除，每次最多 100 张。</p>
          <CartonSelectionSummary :rows="selectedOrders.map(row => ({ id: row.order_no, label: `${row.customer_name} · ${row.contract_no} · ${row.item_no}${row.customer_po ? ' · PO ' + row.customer_po : ''}` }))" :visible-ids="orderedVisibleOrders.map(row => row.id)" unit="张" @clear="selectedOrderNos = []" @remove="selectedOrderNos = selectedOrderNos.filter(id => id !== $event)" />
          <p
            v-if="selectedOrderNos.length && (!apiConnected || combinedPurchaseOrderMessage)"
            role="status"
            aria-live="polite"
            class="basis-full rounded-lg border px-3 py-2 text-[11px] font-semibold"
            :class="!apiConnected || combinedPurchaseOrderTone === 'error'
              ? 'border-red-200 bg-red-50 text-red-700'
              : combinedPurchaseOrderTone === 'success'
                ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                : 'border-blue-200 bg-blue-50 text-blue-700'"
          >
            {{ !apiConnected ? '后端未连接，当前演示订单不能导出；请刷新页面或重新登录后再试。' : combinedPurchaseOrderMessage }}
          </p>
        </div>

        <div aria-label="订单批量选择" class="border-b border-slate-100 bg-slate-50 px-4 py-2.5">
            <div class="flex min-h-10 items-center justify-between gap-3 lg:hidden">
              <label class="inline-flex min-h-10 cursor-pointer items-center gap-2.5 rounded-lg pr-2 text-[12px] font-bold text-slate-700 transition hover:bg-teal-50 hover:text-teal-700">
                <input
                  type="checkbox"
                  aria-label="全选当前订单结果"
                  class="size-5 shrink-0 cursor-pointer accent-teal-600 disabled:cursor-not-allowed disabled:opacity-40"
                  :checked="orderedVisibleOrders.length > 0 && orderedVisibleOrders.every((order) => selectedOrderNos.includes(order.id))"
                  :disabled="orderedVisibleOrders.length === 0"
                  @change="toggleVisibleOrders(($event.target as HTMLInputElement).checked)"
                >
                全选当前结果
              </label>
              <span class="rounded-lg bg-slate-100 px-3 py-2 text-[11px] font-bold text-slate-600">已选 {{ selectedOrderNos.length }} 张</span>
            </div>
            <div class="order-ledger-grid hidden min-h-9 items-center gap-x-3 text-[11px] font-bold tracking-wide text-slate-700 lg:grid">
              <label class="grid cursor-pointer grid-cols-[1.25rem_minmax(0,1fr)] items-center gap-x-1.5 rounded-lg py-1 transition hover:bg-teal-50 hover:text-teal-700">
                <input
                  type="checkbox"
                  aria-label="全选当前订单结果"
                  class="size-5 shrink-0 cursor-pointer accent-teal-600 disabled:cursor-not-allowed disabled:opacity-40"
                  :checked="orderedVisibleOrders.length > 0 && orderedVisibleOrders.every((order) => selectedOrderNos.includes(order.id))"
                  :disabled="orderedVisibleOrders.length === 0"
                  @change="toggleVisibleOrders(($event.target as HTMLInputElement).checked)"
                >
                <span class="text-left">下单日期</span>
              </label>
              <span class="text-left">客户</span>
              <span class="text-left">合同号</span>
              <span class="text-left">货号</span>
              <span class="text-left">纸品明细</span>
              <span class="text-left">交期（客户 / 计划）</span>
              <span class="text-left">到货进度</span>
              <span class="text-left">订单状态</span>
              <span class="text-left">交期提醒</span>
              <span class="relative flex items-center justify-start"><span>操作</span><span class="absolute right-0 shrink-0 rounded-lg bg-slate-100 px-2.5 py-1.5 text-[10px] text-slate-600">已选 {{ selectedOrderNos.length }} 张</span></span>
            </div>
          </div>
          <article
            v-for="row in orderedVisibleOrders"
            :key="row.id"
            :data-order-no="row.id"
            class="relative border-b border-slate-100 transition-colors last:rounded-b-xl last:border-b-0"
            :class="selectedOrderNos.includes(row.id) ? 'bg-teal-50/60' : 'hover:bg-teal-50/40'"
          >
            <div class="order-ledger-grid grid grid-cols-2 gap-x-4 gap-y-2 px-4 py-3.5 sm:grid-cols-3 lg:items-center lg:gap-x-3">
              <div class="min-w-0">
                <div class="mb-1 text-[10px] font-bold text-slate-400 lg:hidden">下单日期</div>
                <div class="grid min-w-0 grid-cols-[1.25rem_minmax(0,1fr)] items-center gap-x-1.5 text-left">
                  <input v-model="selectedOrderNos" type="checkbox" :value="row.id" :aria-label="`选择订单 ${row.id}`" class="size-5 shrink-0 cursor-pointer accent-teal-600">
                  <span class="truncate text-[13px] font-semibold leading-tight tabular-nums text-slate-800" :title="row.orderDate">{{ formatMonthDay(row.orderDate) }}</span>
                </div>
              </div>
              <div class="min-w-0 text-left">
                <div class="mb-1 text-[10px] font-bold text-slate-400 lg:hidden">客户</div>
                <div class="truncate text-[13px] font-semibold leading-tight text-slate-800">{{ row.customer }}</div>
              </div>
              <div class="min-w-0 text-left">
                <div class="mb-1 text-[10px] font-bold text-slate-400 lg:hidden">合同号</div>
                <div class="truncate font-mono text-[13px] font-bold leading-tight text-slate-950" :title="row.contractNo">{{ row.contractNo }}</div><div v-if="customerPoForOrder(row.id)" class="mt-1 break-all text-[10px] text-teal-700">客户 PO {{ customerPoForOrder(row.id) }}</div>
              </div>
              <div class="min-w-0 text-left"><div class="mb-1 text-[10px] font-bold text-slate-400 lg:hidden">货号</div><div class="truncate font-mono text-[13px] font-bold text-slate-950">{{ row.itemNo }}</div></div>
              <div class="min-w-0 text-left" :aria-label="`${row.id} 纸品明细`">
                <div class="mb-1 text-[10px] font-bold text-slate-400 lg:hidden">纸品明细</div>
                <div class="whitespace-nowrap text-[11px] text-slate-500">纸品合计 <b class="text-[13px] tabular-nums text-slate-950">{{ formatNumber(orderPaperItemQuantity(row)) }}</b> 件</div>
                <div class="mt-1 flex flex-wrap gap-1">
                  <span v-for="material in orderMaterialBreakdown(row)" :key="`${material.packagingType}-${material.unit}`" class="inline-flex items-center gap-1 rounded border border-slate-200 bg-white px-1.5 py-0.5 text-[9px] leading-none text-slate-600">
                    {{ material.packagingType }} <b class="tabular-nums text-teal-700">{{ formatNumber(material.quantity) }}</b><span>{{ material.unit }}</span>
                  </span>
                </div>
              </div>
              <div class="min-w-0 text-left">
                <div class="mb-1 text-[10px] font-bold text-slate-400 lg:hidden">交期（客户 / 计划）</div>
                <div class="grid w-fit max-w-full grid-cols-[1.5rem_minmax(0,1fr)] items-center gap-x-1 gap-y-1 text-left">
                  <span class="text-center text-[10px] font-bold text-slate-400">客</span>
                  <span class="truncate text-[13px] font-bold tabular-nums text-slate-950" :title="row.customerDueDate || undefined">{{ formatMonthDay(row.customerDueDate) || '未记录' }}</span>
                  <span class="text-center text-[10px] font-bold text-slate-400">计</span>
                  <span class="text-[13px] font-bold tabular-nums text-slate-950" :title="row.dueDate">{{ formatMonthDay(row.dueDate) }}</span>
                </div>
              </div>
              <div class="min-w-0 text-right" :aria-label="`${row.id} 到货进度`">
                <div class="mb-1 text-[10px] font-bold text-slate-400 lg:hidden">到货进度</div>
                <div class="flex items-center gap-2">
                  <span class="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-slate-200"><span class="block h-full rounded-full bg-emerald-600 transition-all" :style="{ width: `${orderPaperItemProgress(row)}%` }"></span></span>
                  <span class="shrink-0 text-[11px] font-semibold tabular-nums text-slate-700">{{ formatNumber(orderPaperItemReceivedQuantity(row)) }}/{{ formatNumber(orderPaperItemQuantity(row)) }}</span>
                </div>
                <div v-if="orderPaperItemRemainingQuantity(row) > 0" class="mt-1 text-[10px] font-semibold tabular-nums text-red-600">待 {{ formatNumber(orderPaperItemRemainingQuantity(row)) }} 件</div>
                <div v-else class="mt-1 text-[10px] font-semibold text-emerald-700">已齐</div>
              </div>
              <div class="min-w-0 text-left">
                <div class="mb-1 text-[10px] font-bold text-slate-400 lg:hidden">订单状态</div>
                <span class="inline-flex rounded-full px-2 py-0.5 text-[10px] font-bold ring-1 ring-inset" :class="toneClass(row.tone)">{{ row.status }}</span><div class="mt-1 whitespace-nowrap text-[10px] text-slate-500">领用：{{ usageLabel(row.id) }}</div>
              </div>
              <div class="min-w-0 text-left">
                <div class="mb-1 text-[10px] font-bold text-slate-400 lg:hidden">交期提醒</div>
                <span
                  class="text-[11px] font-semibold"
                  :class="orderDueReminder(row).level === 'OVERDUE' || orderDueReminder(row).level === 'TODAY' ? 'text-red-600' : orderDueReminder(row).level === 'DUE_SOON' ? 'text-amber-700' : 'text-slate-500'"
                >{{ orderDueReminder(row).label }}</span>
              </div>
              <div class="relative col-span-2 flex h-full min-w-0 items-center lg:col-span-1" :aria-label="`${row.id} 操作`">
                <div class="grid w-full grid-cols-[7.25rem_3.25rem_2.5rem] items-center justify-start gap-1 overflow-visible">
                  <button v-if="canEditConfirmedOrder(row.id)" type="button" :disabled="!apiConnected || submittingSupplierOrder" class="inline-flex h-8 w-full items-center justify-center gap-1 whitespace-nowrap rounded-md bg-teal-700 px-2 text-[10px] font-bold text-white transition hover:bg-teal-800 disabled:opacity-40" :aria-label="`确认订单 ${row.id} 并锁定`" @click="openSubmitSupplierOrder(row.id)"><ShieldCheck class="size-3.5" />确认订单并锁定</button>
                  <button v-else-if="canReceiveOrder(row.id)" type="button" :disabled="!apiConnected" class="inline-flex h-8 w-full items-center justify-center gap-1 whitespace-nowrap rounded-md bg-teal-700 px-2 text-[10px] font-bold text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:bg-slate-300" :aria-label="`登记 ${row.id} 收料`" @click="openManualReceipt(row.id)"><Truck class="size-3.5" />登记收料</button>
                  <button v-else type="button" :disabled="!apiConnected" class="inline-flex h-8 w-full items-center justify-center gap-1 whitespace-nowrap rounded-md bg-teal-700 px-2 text-[10px] font-bold text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:bg-slate-300" :aria-label="`管理 ${row.id} 采购单`" @click="openPurchaseOrderDialog(row.id)"><Download class="size-3.5" />采购单</button>
                  <div v-if="canEditConfirmedOrder(row.id) || canReceiveOrder(row.id) || canAppendOrder(row.id) || canReduceSubmittedOrder(row.id) || canDeleteHistoryOrder(row.id) || canReplenishOrder(row.id)" class="relative col-start-2 row-start-1 w-full">
                    <button type="button" class="inline-flex h-8 w-full items-center justify-center gap-1 whitespace-nowrap rounded-md border border-slate-200 bg-white px-1 text-[10px] font-bold text-slate-600 transition hover:border-slate-300 hover:bg-slate-100" :aria-label="`更多 ${row.id} 订单操作`" aria-haspopup="menu" :aria-expanded="openOrderMoreMenu === row.id" @click.stop="openOrderMoreMenu = openOrderMoreMenu === row.id ? '' : row.id">更多 <span class="text-[8px]">▾</span></button>
                    <button v-if="openOrderMoreMenu === row.id" type="button" class="fixed inset-0 z-20 cursor-default" :aria-label="`关闭 ${row.id} 更多操作`" @click="openOrderMoreMenu = ''"></button>
                    <div v-if="openOrderMoreMenu === row.id" role="menu" class="absolute right-0 top-full z-30 mt-1 w-44 overflow-hidden rounded-lg border border-slate-200 bg-white py-1 shadow-xl">
                      <button v-if="canEditConfirmedOrder(row.id)" type="button" role="menuitem" :disabled="!apiConnected" class="flex w-full items-center gap-2 px-3 py-2 text-left text-[10px] font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40" :aria-label="`修改 ${row.id} 订单`" @click="openOrderMoreMenu = ''; openEditOrderModal(row.id)"><Pencil class="size-3.5" />修改订单</button>
                      <button v-if="canEditConfirmedOrder(row.id) || canReceiveOrder(row.id)" type="button" role="menuitem" :disabled="!apiConnected" class="flex w-full items-center gap-2 px-3 py-2 text-left text-[10px] font-semibold text-teal-700 hover:bg-teal-50 disabled:opacity-40" :aria-label="`管理 ${row.id} 采购单`" @click="openOrderMoreMenu = ''; openPurchaseOrderDialog(row.id)"><Download class="size-3.5" />采购单</button>
                      <button v-if="canReplenishOrder(row.id)" type="button" role="menuitem" :disabled="!apiConnected || replenishing" class="flex w-full items-center gap-2 px-3 py-2 text-left text-[10px] font-semibold text-teal-700 hover:bg-teal-50 disabled:opacity-40" :aria-label="`补单 ${row.id}`" @click="openOrderMoreMenu = ''; openReplenishOrder(row.id)"><Plus class="size-3.5" />补单（原数量不变）</button>
                      <button v-if="canDeleteHistoryOrder(row.id)" type="button" role="menuitem" :disabled="!apiConnected || deletingHistory" class="flex w-full items-center gap-2 px-3 py-2 text-left text-[10px] font-semibold text-red-700 hover:bg-red-50 disabled:opacity-40" :aria-label="`删除历史订单 ${row.id}`" @click="openOrderMoreMenu = ''; deleteHistoryReason = '历史订单导入有误'; deleteHistoryTarget = orderRecords.find(order => order.order_no === row.id) || null"><Trash2 class="size-3.5" />删除历史订单</button>
                      <button v-if="canAppendOrder(row.id)" type="button" role="menuitem" :disabled="!apiConnected" :title="rawOrderStatus(row.id) === 'COMPLETED' ? '追加后恢复为部分到货，新增数量可继续入库' : '追加订单数量'" class="flex w-full items-center gap-2 px-3 py-2 text-left text-[10px] font-semibold text-amber-700 hover:bg-amber-50 disabled:opacity-40" :aria-label="`追加 ${row.id} 订单`" @click="openOrderMoreMenu = ''; openAppendOrder(row.id)"><Plus class="size-3.5" />追加订单</button>
                      <button v-if="canReduceSubmittedOrder(row.id)" type="button" role="menuitem" :disabled="!apiConnected || reducingOrder" class="flex w-full items-center gap-2 px-3 py-2 text-left text-[10px] font-semibold text-red-700 hover:bg-red-50 disabled:opacity-40" :aria-label="`减单 ${row.id}`" @click="openOrderMoreMenu = ''; openReduceOrder(row.id)"><Minus class="size-3.5" />{{ rawOrderStatus(row.id) === 'PARTIALLY_RECEIVED' ? '减少未入库量' : '减单 / 退单' }}</button>
                      <button v-if="canEditConfirmedOrder(row.id)" type="button" role="menuitem" :disabled="!apiConnected || cancellingOrder" class="flex w-full items-center gap-2 px-3 py-2 text-left text-[10px] font-semibold text-red-700 hover:bg-red-50 disabled:opacity-40" :aria-label="`取消 ${row.id}`" @click="openOrderMoreMenu = ''; openCancelOrder(row.id)"><X class="size-3.5" />取消订单</button>
                    </div>
                  </div>
                  <button type="button" title="悬停预览完整明细，单击后保持显示" class="col-start-3 row-start-1 inline-flex h-8 w-full items-center justify-center whitespace-nowrap rounded-md border border-slate-200 bg-white text-[10px] font-bold text-slate-600 transition hover:border-teal-300 hover:bg-teal-50 hover:text-teal-700" :aria-label="`查看 ${row.id} 完整订单明细`" @mouseenter="previewOrderDetails(row.id)" @mouseleave="closeOrderDetailsPreview(row.id)" @focus="previewOrderDetails(row.id)" @blur="closeOrderDetailsPreview(row.id)" @click="openOrderDetails(row.id)">明细</button>
                </div>
              </div>
            </div>

          </article>
          <div v-if="visibleOrders.length === 0" class="px-4 py-12 text-center text-slate-400">没有符合当前筛选条件的合同订单</div>
        </div>
      </section>

      <section v-else-if="activeTab === 'weekly-check'" class="space-y-4">
        <div class="flex flex-wrap items-center gap-3 rounded-xl border bg-white p-3"><label class="text-xs"><input v-model="weeklyOnlyAttention" aria-label="只看需要处理的核对结果" type="checkbox"> 只看需要处理</label><button type="button" class="h-9 rounded-lg border px-3 text-xs" @click="clearWeeklyFilters">清空筛选</button></div>
        <div class="grid gap-3 sm:grid-cols-2">
          <button
            type="button"
            :aria-pressed="weeklyCheckMode === 'ORDER_GAP'"
            class="rounded-xl border p-4 text-left shadow-sm transition"
            :class="weeklyCheckMode === 'ORDER_GAP' ? 'border-teal-500 bg-teal-50 ring-2 ring-teal-100' : 'border-slate-200 bg-white hover:border-teal-200'"
            @click="weeklyCheckMode = 'ORDER_GAP'"
          >
            <span class="flex items-center gap-2 font-bold text-slate-950"><ClipboardCheck class="size-4 text-teal-700" />下单防漏核对</span>
            <span class="mt-1 block text-[11px] leading-5 text-slate-500">导入跟客发出的每周排期，核对是否已经建立正式纸箱订单。</span>
          </button>
          <button
            type="button"
            :aria-pressed="weeklyCheckMode === 'INSPECTION_REMINDER'"
            class="rounded-xl border p-4 text-left shadow-sm transition"
            :class="weeklyCheckMode === 'INSPECTION_REMINDER' ? 'border-blue-500 bg-blue-50 ring-2 ring-blue-100' : 'border-slate-200 bg-white hover:border-blue-200'"
            @click="weeklyCheckMode = 'INSPECTION_REMINDER'"
          >
            <span class="flex items-center gap-2 font-bold text-slate-950"><CalendarClock class="size-4 text-blue-700" />下周查货提醒</span>
            <span class="mt-1 block text-[11px] leading-5 text-slate-500">导入下周需要查货的合同，倒推纸箱最迟交货日并生成跟进提醒。</span>
          </button>
        </div>

        <div class="grid gap-4 xl:grid-cols-[1fr_360px]">
          <article v-if="weeklyCheckMode === 'ORDER_GAP'" class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 class="font-bold text-slate-950">业务 ITEM 排期与下单核对</h2>
                <p class="mt-1 text-[11px] text-slate-500">使用公司统一业务排期表，读取各 ITEM 表的正单，核对合同、客户 PO、货号、数量和客户走货期。</p>
              </div>
              <input ref="weeklyFileInput" type="file" accept=".xlsx,.xls" class="hidden" aria-label="选择每周排期文件" @change="handleWeeklyFile">
              <div class="flex flex-wrap items-center gap-2">
                <a
                  href="/templates/carton-weekly-schedule-template.xlsx"
                  download="纸箱每周排期核对导入模板.xlsx"
                  class="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-bold text-slate-700 transition hover:border-teal-200 hover:bg-teal-50 hover:text-teal-700"
                >
                  <Download class="size-4" />旧版排期模板（兼容）
                </a>
                <button
                  type="button"
                  :disabled="importingWeekly"
                  class="inline-flex h-9 items-center gap-2 rounded-lg border border-teal-200 bg-white px-3 text-[12px] font-bold text-teal-700 transition hover:bg-teal-50 disabled:cursor-not-allowed disabled:border-slate-200 disabled:text-slate-400"
                  @click="triggerWeeklyImport"
                >
                  <FileSpreadsheet class="size-4" />{{ importingWeekly ? '正在核对…' : '导入业务排期' }}
                </button>
              </div>
            </div>
            <p v-if="selectedWeeklyFileName" class="mt-2 text-[10px] text-slate-500">当前文件：<span class="font-semibold text-slate-700">{{ selectedWeeklyFileName }}</span></p>
          </article>
          <article v-else class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div class="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 class="font-bold text-slate-950">下周查货合同交期提醒</h2>
                <p class="mt-1 text-[11px] text-slate-500">以验货期第一天倒推最迟交货日；已完成收料的订单不会催交。</p>
              </div>
              <div class="flex flex-wrap items-end gap-2">
                <label class="space-y-1">
                  <span class="block text-[10px] font-bold text-slate-500">提前交货天数</span>
                  <input v-model.number="inspectionAdvanceDays" aria-label="提前交货天数" type="number" min="0" max="30" class="h-9 w-24 rounded-lg border border-slate-200 bg-white px-3 text-right font-semibold outline-none focus:border-blue-500">
                </label>
                <input ref="inspectionFileInput" type="file" accept=".xlsx,.xls" class="hidden" aria-label="选择下周查货合同文件" @change="handleInspectionFile">
                <button
                  type="button"
                  :disabled="importingInspection"
                  class="inline-flex h-9 items-center gap-2 rounded-lg bg-blue-700 px-3 text-[12px] font-bold text-white transition hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-60"
                  @click="triggerInspectionImport"
                >
                  <Upload class="size-4" />{{ importingInspection ? '正在计算提醒…' : '导入下周查货合同' }}
                </button>
              </div>
            </div>
            <p v-if="selectedInspectionFileName" class="mt-2 text-[10px] text-slate-500">当前文件：<span class="font-semibold text-slate-700">{{ selectedInspectionFileName }}</span> · 提前 {{ inspectionAdvanceDays }} 天</p>
          </article>
          <article class="rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-900 shadow-sm">
            <div class="flex gap-2 font-bold"><ShieldCheck class="size-4 shrink-0" />{{ weeklyCheckMode === 'ORDER_GAP' ? '防误建规则' : '提醒计算规则' }}</div>
            <div v-if="weeklyCheckMode === 'ORDER_GAP'" class="mt-2 space-y-1.5 text-[11px] leading-5">
              <p>统一模板读取全部 <strong>ITEM 表</strong>，按合同号、货号及填写的客户 PO 核对。SO / Reference 单独保留；正单参与核对，其余类型待人工确认。旧排期模板仍兼容。</p>
              <p>唯一匹配后，将模板“数量”与正式订单的<strong>产品订单数量</strong>直接比较，不按装箱数换算。</p>
              <p>显示需要下单、已下单、已完单及数量或交期差异。文件缺少某行不代表取消订单；导入只生成核对结果和待办，<strong>不会自动创建或修改正式纸箱订单</strong>。</p>
            </div>
            <p v-else class="mt-2 text-[11px] leading-5">最迟交货日＝验货开始日－提前天数；只生成纸箱部提醒，<strong>不会修改订单或库存</strong>。</p>
          </article>
        </div>

        <article class="rounded-xl border border-slate-200 bg-white shadow-sm">
          <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
            <div>
              <h2 class="font-bold text-slate-950">核对历史</h2>
              <p class="mt-1 text-[11px] text-slate-500">每次导入及核对结果均由后端保存；点击历史批次可恢复当时的结果明细。</p>
            </div>
            <span class="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-bold text-slate-600">{{ activeWeeklyImportHistory.length }} 个批次</span><input v-model="weeklyHistorySearch" aria-label="查找核对历史" placeholder="文件名 / 导入日期" class="h-9 rounded-lg border px-3 text-xs"><button v-if="activeWeeklyImportHistory.length > 8" type="button" class="text-xs text-teal-700" @click="weeklyHistoryExpanded = !weeklyHistoryExpanded">{{ weeklyHistoryExpanded ? '收起历史' : '查看更多历史' }}</button>
          </div>
          <div v-if="activeWeeklyImportHistory.length" class="divide-y divide-slate-100">
            <div v-for="batch in activeWeeklyImportHistory.filter(batch => `${batch.original_filename} ${batch.created_at}`.toLowerCase().includes(weeklyHistorySearch.toLowerCase())).slice(0, weeklyHistoryExpanded || weeklyHistorySearch ? undefined : 8)" :key="batch.id" class="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
              <div class="min-w-0">
                <div class="truncate text-[12px] font-semibold text-slate-900">{{ batch.original_filename }}</div>
                <div class="mt-0.5 text-[10px] text-slate-500">{{ (batch.created_at || '').replace('T', ' ').slice(0, 16) || '历史时间待补充' }} · {{ batch.imported_by_name || '历史操作人' }} · {{ batch.parse_summary.row_count ?? 0 }} 行</div>
              </div>
              <div class="flex items-center gap-2">
                <span v-if="batch.status === 'REJECTED'" class="text-xs font-semibold text-slate-500">已整批撤销</span>
                <template v-else>
                  <button type="button" class="h-8 rounded-lg border border-slate-200 bg-white px-3 text-[11px] font-bold text-slate-700 hover:border-teal-300 hover:text-teal-700" @click="batch.import_type === 'WEEKLY_SCHEDULE' ? restoreWeeklyImport(batch) : restoreInspectionImport(batch)">查看结果</button>
                  <button v-if="canUndoScheduleImport" type="button" :disabled="undoingImport || !apiConnected" :aria-label="`撤销本次导入 ${batch.original_filename}`" class="h-8 rounded-lg border border-red-200 px-3 text-[11px] font-bold text-red-700 disabled:opacity-40" @click="undoImportTarget = batch; undoImportReason = '本次导入文件有误'">撤销本次导入</button>
                </template>
              </div>
            </div>
          </div>
          <div v-else class="px-4 py-8 text-center text-[11px] text-slate-400">尚无当前类型的核对历史</div>
        </article>

        <CartonBusinessImportSummary v-if="weeklyCheckMode === 'ORDER_GAP'" :batch="weeklyImportHistory.find(batch => batch.id === selectedWeeklyBatchId)" />
        <div v-if="weeklyCheckMode === 'ORDER_GAP'" class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div class="overflow-x-auto">
            <table class="min-w-[1250px] w-full text-left">
              <thead class="bg-slate-50 text-[10px] font-bold text-slate-500">
                <tr><th class="px-4 py-3">合同 / 客户 PO</th><th class="px-4 py-3">客户 / 产品</th><th class="px-4 py-3">货号 / 订单类型</th><th class="px-4 py-3 text-right">数量</th><th class="px-4 py-3">装箱</th><th class="px-4 py-3">验货期 / 客户走货期</th><th class="px-4 py-3">核对结果</th><th class="px-4 py-3">关联订单 / 下单状态</th><th class="px-4 py-3">处理建议</th></tr>
              </thead>
              <tbody class="divide-y divide-slate-100">
                <tr v-for="row in visibleWeeklyChecks" :key="row.id" class="hover:bg-slate-50/80">
                  <td class="px-4 py-3"><div class="font-semibold">{{ row.reference || '合同待确认' }}</div><div class="mt-0.5 text-[10px] text-slate-500">{{ row.poNumbers }}</div><div v-if="row.sourceReference" class="text-[10px] text-slate-500">SO: {{ row.sourceReference }}</div></td>
                  <td class="px-4 py-3"><div class="font-semibold">{{ row.customer }}</div><div v-if="row.businessCustomer && row.businessCustomer !== row.customer" class="text-[10px] text-slate-500">业务客名：{{ row.businessCustomer }}</div><div class="mt-0.5 text-[10px] text-slate-500">{{ row.productName }}</div></td>
                  <td class="px-4 py-3"><div class="font-mono font-semibold">{{ row.itemNo }}</div><div class="text-[10px] text-slate-500">{{ row.orderType }}</div></td>
                  <td class="px-4 py-3 text-right font-semibold tabular-nums">{{ row.quantityMissing ? '待确认' : formatNumber(row.quantity) }}</td>
                  <td class="px-4 py-3">{{ row.cartonRule }}</td>
                  <td class="px-4 py-3"><div class="font-semibold">{{ row.inspectionWindow || '验货期未填' }}</div><div v-if="row.customerDueDate" class="text-[10px] text-slate-500">走货 {{ row.customerDueDate }}</div><div v-if="row.dateReviewRequired" class="text-[10px] text-amber-800">日期原文待确认</div></td>
                  <td class="px-4 py-3"><span class="rounded-full px-2 py-0.5 text-[10px] font-bold ring-1 ring-inset" :class="toneClass(row.tone)">{{ row.result }}</span></td>
                  <td class="px-4 py-3 text-[11px]"><div class="font-mono">{{ row.linkedOrder }}</div><div class="mt-1 font-semibold" :class="row.procurementState === '需要下单' ? 'text-amber-800' : 'text-teal-800'">{{ row.procurementState }}</div></td>
                  <td class="max-w-[280px] px-4 py-3 text-[11px] text-slate-500"><div>{{ row.suggestion }}</div><div class="mt-1 text-[10px]">{{ row.sourceLocation }}</div></td>
                </tr>
                <tr v-if="visibleWeeklyChecks.length === 0"><td colspan="9" class="px-4 py-12 text-center text-slate-400">没有符合当前筛选条件的核对记录</td></tr>
              </tbody>
            </table>
          </div>
        </div>
        <div v-else class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div class="overflow-x-auto">
            <table class="min-w-[1260px] w-full text-left">
              <thead class="bg-slate-50 text-[10px] font-bold text-slate-500">
                <tr><th class="px-4 py-3">Reference / PO.NO</th><th class="px-4 py-3">客户 / 产品</th><th class="px-4 py-3">货号</th><th class="px-4 py-3">验货期</th><th class="px-4 py-3">最迟交货日</th><th class="px-4 py-3 text-center">提前天数</th><th class="px-4 py-3">提醒状态</th><th class="px-4 py-3">关联订单</th><th class="px-4 py-3">处理建议</th></tr>
              </thead>
              <tbody class="divide-y divide-slate-100">
                <tr v-for="row in visibleInspectionChecks" :key="row.id" class="hover:bg-slate-50/80">
                  <td class="px-4 py-3"><div class="font-semibold">{{ row.reference }}</div><div class="mt-0.5 text-[10px] text-slate-500">{{ row.poNumbers }}</div></td>
                  <td class="px-4 py-3"><div class="font-semibold">{{ row.customer }}</div><div class="mt-0.5 text-[10px] text-slate-500">{{ row.productName }}</div></td>
                  <td class="px-4 py-3 font-mono font-semibold">{{ row.itemNo }}</td>
                  <td class="px-4 py-3 font-semibold">{{ row.inspectionWindow }}</td>
                  <td class="px-4 py-3 font-mono font-bold" :class="row.reminderStatus === 'OVERDUE' ? 'text-red-700' : 'text-slate-900'">{{ row.requiredDeliveryDate || '待补充' }}</td>
                  <td class="px-4 py-3 text-center tabular-nums">{{ row.advanceDays }} 天</td>
                  <td class="px-4 py-3"><span class="rounded-full px-2 py-0.5 text-[10px] font-bold ring-1 ring-inset" :class="toneClass(row.tone)">{{ row.result }}</span></td>
                  <td class="px-4 py-3 font-mono text-[11px]">{{ row.linkedOrder }}</td>
                  <td class="max-w-[300px] px-4 py-3 text-[11px] leading-5 text-slate-500">{{ row.suggestion }}</td>
                </tr>
                <tr v-if="visibleInspectionChecks.length === 0"><td colspan="9" class="px-4 py-12 text-center text-slate-400">请导入下周查货合同，系统将计算最迟交货日和提醒状态</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section v-else-if="activeTab === 'receipts'" class="space-y-4">
        <nav aria-label="收料入库子页面" class="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-white p-2 shadow-sm">
          <button v-for="page in [{ id: 'PENDING' as const, label: '待收订单' }, { id: 'IMPORT' as const, label: '送货单导入' }, { id: 'HISTORY' as const, label: '收料历史' }]" :key="page.id" type="button" :aria-current="receiptPage === page.id ? 'page' : undefined" class="rounded-lg px-4 py-2 text-xs font-semibold" :class="receiptPage === page.id ? 'bg-teal-50 text-teal-800 ring-1 ring-teal-200' : 'text-slate-500 hover:bg-slate-50'" @click="openReceiptPage(page.id)">{{ page.label }}</button>
        </nav>
        <article v-if="receiptPage === 'PENDING'" class="overflow-hidden rounded-xl border border-blue-200 bg-white shadow-sm">
          <div class="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 px-5 py-4">
            <div>
              <h2 class="flex items-center gap-2 text-lg font-bold text-slate-950"><Truck class="size-5 text-teal-700" />待收订单 <span class="text-sm font-medium text-slate-500">{{ visibleManualReceiptOrders.length }} 张</span></h2>
              <p class="mt-1 text-sm text-slate-500">先选择大单（合同），再勾选外箱、内箱、平卡等本次到货纸品；各纸品可分批入库。</p>
            </div>
          </div>
          <div class="flex flex-wrap items-center justify-between gap-3 bg-slate-50 px-5 py-3">
            <div class="flex flex-1 flex-wrap items-center gap-3">
              <label class="inline-flex items-center gap-2 text-xs font-semibold text-slate-600"><span>客户</span><select v-model="selectedCustomer" aria-label="待收订单客户筛选" class="h-9 min-w-28 rounded-lg border border-slate-200 bg-white px-3 text-xs text-slate-700 outline-none focus:border-teal-500"><option v-for="customer in customerFilterOptions" :key="customer" :value="customer">{{ customer }}</option></select></label>
              <label class="inline-flex items-center gap-2 text-xs font-semibold text-slate-600"><span>选择大单（合同）</span><select v-model="receiptContractKey" aria-label="选择收料合同" class="h-9 max-w-80 rounded-lg border border-slate-200 bg-white px-3 text-xs" @change="selectReceiptContract"><option value="">全部合同</option><option v-for="contract in receiptContractOptions" :key="contract.key" :value="contract.key">{{ contract.label }} · {{ contract.count }} 张订单</option></select></label>
              <div role="group" aria-label="计划交期筛选" class="flex items-center gap-2 text-xs font-semibold text-slate-600">
                <span>计划交期</span>
                <DateRangeFilter v-model="receiptDueCalendarValue" label="选择计划交期范围" />
              </div>
              <label class="inline-flex items-center gap-2 text-xs font-semibold text-slate-600"><span>排序</span><select v-model="receiptOrderSort" aria-label="待收订单排序" class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-xs text-slate-700 outline-none focus:border-teal-500"><option value="DUE_ASC">交期由近到远</option><option value="DUE_DESC">交期由远到近</option><option value="DEFAULT">下单日期最新</option></select></label>
              <button v-if="selectedCustomer !== '全部客户' || globalSearch || receiptPlannedDueFrom || receiptPlannedDueTo || receiptContractKey" type="button" class="h-9 px-2 text-xs font-semibold text-teal-700 hover:text-teal-900" @click="clearReceiptOrderFilters">清除筛选</button>
            </div>
            <div class="flex items-center gap-4"><span class="text-sm text-slate-600">已选 <strong class="text-teal-700">{{ selectedManualReceiptOrders.length }}</strong> 张</span><button ref="receiptDialogTrigger" type="button" :disabled="!selectedManualReceiptOrders.length || !apiConnected" class="inline-flex h-10 items-center gap-2 rounded-lg bg-teal-700 px-4 text-sm font-bold text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-40" @click="openManualReceipt()"><Plus class="size-4" />登记所选订单收料</button></div>
            <CartonSelectionSummary :rows="selectedManualReceiptOrders.map(row => ({ id: row.order_no, label: `${row.customer_name} · ${row.contract_no} · ${row.item_no}${row.customer_po ? ' · PO ' + row.customer_po : ''}` }))" :visible-ids="visibleManualReceiptOrders.map(row => row.order_no)" unit="张" @clear="manualReceiptOrderNos = []; populateManualReceipt([])" @remove="manualReceiptOrderNos = manualReceiptOrderNos.filter(id => id !== $event); populateManualReceipt(manualReceiptOrderNos)" />
          </div>
          <div class="bg-white">
            <div class="receipt-order-ledger-grid grid min-h-11 items-center gap-x-3 border-b border-slate-100 bg-slate-50 px-4 text-[11px] font-bold tracking-wide text-slate-700" aria-label="待收订单列表表头">
              <div class="grid min-w-0 grid-cols-[1.25rem_minmax(0,1fr)] items-center gap-x-1.5">
                <label class="inline-flex cursor-pointer items-center" title="全选当前订单"><input type="checkbox" aria-label="全选待收订单" class="size-5 shrink-0 cursor-pointer accent-teal-600" :disabled="!visibleManualReceiptOrders.length" :checked="visibleManualReceiptOrders.length > 0 && visibleManualReceiptOrders.every((order) => manualReceiptOrderNos.includes(order.order_no))" @change="toggleVisibleReceiptOrders(($event.target as HTMLInputElement).checked)"><span class="sr-only">全选当前订单</span></label>
                <span class="hidden lg:inline">下单日期</span><span class="lg:hidden">全选当前订单</span>
              </div><span class="hidden lg:block">客户</span><span class="hidden lg:block">合同号</span><span class="hidden lg:block">货号 / 产品名称</span><span class="hidden lg:block">纸品明细</span><span class="hidden lg:block">交期（客户 / 计划）</span><span class="hidden lg:block">到货进度</span><span class="hidden lg:block">订单状态</span><span class="hidden lg:block">交期提醒</span><span class="hidden lg:block">操作</span>
            </div>
            <article v-for="row in receiptLedgerRows" :key="row.id" :data-receipt-order="row.id" class="relative border-b border-slate-100 transition-colors last:border-b-0" :class="manualReceiptOrderNos.includes(row.id) ? 'bg-teal-50/60' : 'hover:bg-teal-50/40'">
            <div class="receipt-order-ledger-grid grid grid-cols-2 gap-x-4 gap-y-2 px-4 py-3.5 sm:grid-cols-3 lg:items-center lg:gap-x-3">
              <div class="min-w-0">
                <div class="mb-1 text-[10px] font-bold text-slate-400 lg:hidden">下单日期</div>
                <div class="grid min-w-0 grid-cols-[1.25rem_minmax(0,1fr)] items-center gap-x-1.5 text-left">
                  <input v-model="manualReceiptOrderNos" type="checkbox" :value="row.id" :aria-label="`选择 ${row.id} 待收订单`" @change="populateManualReceipt(manualReceiptOrderNos)" class="size-5 shrink-0 cursor-pointer accent-teal-600">
                  <span class="truncate text-[13px] font-semibold leading-tight tabular-nums text-slate-800" :title="row.orderDate">{{ formatMonthDay(row.orderDate) }}</span>
                </div>
              </div>
              <div class="min-w-0 text-left">
                <div class="mb-1 text-[10px] font-bold text-slate-400 lg:hidden">客户</div>
                <div class="truncate text-[13px] font-semibold leading-tight text-slate-800">{{ row.customer }}</div>
              </div>
              <div class="min-w-0 text-left">
                <div class="mb-1 text-[10px] font-bold text-slate-400 lg:hidden">合同号</div>
                <div class="truncate font-mono text-[13px] font-bold leading-tight text-slate-950" :title="row.contractNo">{{ row.contractNo }}</div><div v-if="customerPoForOrder(row.id)" class="mt-1 break-all text-[10px] text-teal-700">客户 PO {{ customerPoForOrder(row.id) }}</div>
              </div>
              <div class="min-w-0 text-left"><div class="mb-1 text-[10px] font-bold text-slate-400 lg:hidden">货号 / 产品名称</div><div class="truncate font-mono text-[13px] font-bold text-slate-950" :title="row.itemNo">{{ row.itemNo }}</div><div v-if="row.productName" class="mt-1 truncate text-[11px] text-slate-500" :title="row.productName">{{ row.productName }}</div></div>
              <div class="min-w-0 text-left" :aria-label="`${row.id} 纸品明细`">
                <div class="mb-1 text-[10px] font-bold text-slate-400 lg:hidden">纸品明细</div>
                <div class="whitespace-nowrap text-[11px] text-slate-500">纸品合计 <b class="text-[13px] tabular-nums text-slate-950">{{ formatNumber(orderPaperItemQuantity(row)) }}</b> 件</div>
                <div class="mt-1 flex flex-wrap gap-1">
                  <span v-for="material in orderMaterialBreakdown(row)" :key="`${material.packagingType}-${material.unit}`" class="inline-flex items-center gap-1 rounded border border-slate-200 bg-white px-1.5 py-0.5 text-[9px] leading-none text-slate-600">
                    {{ material.packagingType }} <b class="tabular-nums text-teal-700">{{ formatNumber(material.quantity) }}</b><span>{{ material.unit }}</span>
                  </span>
                </div>
              </div>
              <div class="min-w-0 text-left">
                <div class="mb-1 text-[10px] font-bold text-slate-400 lg:hidden">交期（客户 / 计划）</div>
                <div class="grid w-fit max-w-full grid-cols-[1.5rem_minmax(0,1fr)] items-center gap-x-1 gap-y-1 text-left">
                  <span class="text-center text-[10px] font-bold text-slate-400">客</span>
                  <span class="truncate text-[13px] font-bold tabular-nums text-slate-950" :title="row.customerDueDate || undefined">{{ formatMonthDay(row.customerDueDate) || '未记录' }}</span>
                  <span class="text-center text-[10px] font-bold text-slate-400">计</span>
                  <span class="text-[13px] font-bold tabular-nums text-slate-950" :title="row.dueDate">{{ formatMonthDay(row.dueDate) }}</span>
                </div>
              </div>
              <div class="min-w-0 text-right" :aria-label="`${row.id} 到货进度`">
                <div class="mb-1 text-[10px] font-bold text-slate-400 lg:hidden">到货进度</div>
                <div class="flex items-center gap-2">
                  <span class="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-slate-200"><span class="block h-full rounded-full bg-emerald-600 transition-all" :style="{ width: `${orderPaperItemProgress(row)}%` }"></span></span>
                  <span class="shrink-0 text-[11px] font-semibold tabular-nums text-slate-700">{{ formatNumber(orderPaperItemReceivedQuantity(row)) }}/{{ formatNumber(orderPaperItemQuantity(row)) }}</span>
                </div>
                <div v-if="orderPaperItemRemainingQuantity(row) > 0" class="mt-1 text-[10px] font-semibold tabular-nums text-red-600">待 {{ formatNumber(orderPaperItemRemainingQuantity(row)) }} 件</div>
                <div v-else class="mt-1 text-[10px] font-semibold text-emerald-700">已齐</div>
              </div>
              <div class="min-w-0 text-left">
                <div class="mb-1 text-[10px] font-bold text-slate-400 lg:hidden">订单状态</div>
                <span class="inline-flex rounded-full px-2 py-0.5 text-[10px] font-bold ring-1 ring-inset" :class="toneClass(row.tone)">{{ row.status }}</span><div class="mt-1 whitespace-nowrap text-[10px] text-slate-500">领用：{{ usageLabel(row.id) }}</div>
              </div>
              <div class="min-w-0 text-left">
                <div class="mb-1 text-[10px] font-bold text-slate-400 lg:hidden">交期提醒</div>
                <span
                  class="text-[11px] font-semibold"
                  :class="orderDueReminder(row).level === 'OVERDUE' || orderDueReminder(row).level === 'TODAY' ? 'text-red-600' : orderDueReminder(row).level === 'DUE_SOON' ? 'text-amber-700' : 'text-slate-500'"
                >{{ orderDueReminder(row).label }}</span>
              </div>
              <div class="col-span-2 flex flex-wrap items-center gap-2 lg:col-span-1">
                <button type="button" :disabled="!apiConnected" class="inline-flex h-8 items-center justify-center gap-1 whitespace-nowrap rounded-md bg-teal-700 px-3 text-[11px] font-bold text-white transition hover:bg-teal-800 disabled:opacity-40" :aria-label="`登记 ${row.id} 收料`" @click="openManualReceipt(row.id)"><Truck class="size-3.5" />登记收料</button>
                <button type="button" title="悬停预览完整明细，单击后保持显示" class="inline-flex h-8 items-center justify-center rounded-md border border-slate-200 bg-white px-2 text-[11px] font-bold text-slate-600 transition hover:border-teal-300 hover:bg-teal-50 hover:text-teal-700" :aria-label="`查看 ${row.id} 完整订单明细`" @mouseenter="previewOrderDetails(row.id)" @mouseleave="closeOrderDetailsPreview(row.id)" @focus="previewOrderDetails(row.id)" @blur="closeOrderDetailsPreview(row.id)" @click="openOrderDetails(row.id)">明细</button>
              </div>
            </div>
            <CartonReceiptPaperSelection v-if="manualReceiptOrderNos.includes(row.id) && hasManualPaperSelection && receiptEntryMode === 'MANUAL' && !currentReceipt && !showReceiptDialog" :order="manualReceiptOrders.find(order => order.order_no === row.id)!" :drafts="receiptLines" :disabled="savingReceipt" @select="selectReceiptPaper" @quantity="setReceiptPaperQuantity" />
            </article>
            <p v-if="!visibleManualReceiptOrders.length" class="py-10 text-center text-sm text-slate-500">{{ backendLoading ? '正在加载待收订单…' : '当前没有符合条件的待收订单。只有已确认锁定或部分收料的订单会显示在这里。' }}</p>
          </div>
        </article>

        <article v-else-if="receiptPage === 'IMPORT'" class="rounded-xl border border-teal-200 bg-white p-5 shadow-sm">
          <div class="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 class="flex items-center gap-2 text-lg font-bold text-slate-950"><Upload class="size-5 text-teal-700" />送货单导入</h2>
              <p class="mt-1 text-sm text-slate-500">上传送货单，复核识别明细后登记收料。</p>
            </div>
            <div class="flex flex-wrap items-center gap-3">
              <input ref="receiptFileInput" type="file" accept=".pdf,.jpg,.jpeg,.png,.heic,.heif,image/heic,image/heif,.xlsx,.xls" class="hidden" aria-label="选择送货单文件" @change="handleReceiptFile">
              <button ref="receiptDialogTrigger" type="button" :disabled="importingReceipt" class="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-teal-700 px-4 text-xs font-bold text-white transition hover:bg-teal-800 disabled:opacity-60" @click="triggerReceiptImport"><Upload class="size-4" />{{ importingReceipt ? '正在识别…' : '导入送货单' }}</button>
            </div>
          </div>
          <p v-if="selectedReceiptFileName" class="mt-3 break-all text-xs text-slate-500">已选择：<span class="font-semibold text-slate-700">{{ selectedReceiptFileName }}</span></p>
        </article>

        <div v-if="receiptPage === 'IMPORT' && receiptEntryMode === 'IMPORT' && receiptLines.length" class="flex items-center justify-between gap-3 rounded-xl border border-teal-200 bg-teal-50 p-4">
          <span class="text-sm text-teal-900">{{ receiptLines.length }} 条明细待复核</span>
          <button type="button" class="h-10 rounded-lg bg-teal-700 px-4 text-sm font-bold text-white" @click="showReceiptDialog = true">填写收料反馈</button>
        </div>

        <article v-if="receiptPage === 'IMPORT' && receiptImportBatch" class="overflow-hidden rounded-xl border bg-white shadow-sm" :class="receiptImportNeedsReview ? 'border-amber-300' : 'border-emerald-300'">
          <div class="flex flex-wrap items-start justify-between gap-3 border-b px-4 py-3" :class="receiptImportNeedsReview ? 'border-amber-200 bg-amber-50' : 'border-emerald-200 bg-emerald-50'">
            <div>
              <div class="flex flex-wrap items-center gap-2 font-bold" :class="receiptImportNeedsReview ? 'text-amber-950' : 'text-emerald-950'">
                <CheckCircle2 class="size-4" />送货单识别完成
                <span v-if="receiptImportBatch.duplicate" class="rounded-full bg-white px-2 py-0.5 text-[9px] font-bold text-slate-600 ring-1 ring-inset ring-slate-200">重复文件 · 已恢复原结果</span>
              </div>
              <p class="mt-1 text-[11px]" :class="receiptImportNeedsReview ? 'text-amber-800' : 'text-emerald-800'">{{ receiptImportBatch.original_filename }} · {{ receiptImportBatch.parse_summary.engine || '文件解析' }} · 批次 {{ receiptImportBatch.id }}</p>
            </div>
            <div class="flex flex-wrap gap-2">
              <button v-if="receiptImportStats.issues" type="button" class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-amber-300 bg-white px-3 text-[11px] font-bold text-amber-800 hover:bg-amber-100" @click="setActiveTab('exceptions')"><AlertTriangle class="size-3.5" />前往异常处理</button>
              <button v-if="receiptImportStats.matched === 0 && !currentReceipt" type="button" :disabled="deletingReceiptImport" class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-red-300 bg-white px-3 text-[11px] font-bold text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50" @click="removeUnmatchedReceiptImport"><Trash2 class="size-3.5" />{{ deletingReceiptImport ? '正在删除…' : '删除本次导入' }}</button>
            </div>
          </div>
          <div class="grid gap-3 border-b border-slate-200 p-4 sm:grid-cols-3">
            <div class="rounded-lg border border-slate-200 bg-slate-50 p-3"><div class="text-[10px] text-slate-500">识别总行数</div><div class="mt-1 text-xl font-bold text-slate-950">{{ receiptImportStats.total }} 行</div></div>
            <div class="rounded-lg border border-emerald-200 bg-emerald-50 p-3"><div class="text-[10px] text-emerald-700">已匹配正式订单</div><div class="mt-1 text-xl font-bold text-emerald-900">{{ receiptImportStats.matched }} 行</div></div>
            <div class="rounded-lg border border-amber-200 bg-amber-50 p-3"><div class="text-[10px] text-amber-700">需要人工处理</div><div class="mt-1 text-xl font-bold text-amber-900">{{ receiptImportStats.issues }} 行</div></div>
          </div>
          <div v-if="receiptImportStats.matched === 0" class="border-b border-red-200 bg-red-50 px-4 py-3 text-[11px] leading-5 text-red-800">
            <strong v-if="receiptImportStats.total > 0">已识别 {{ receiptImportStats.total }} 行送货明细，但没有找到可关联的正式纸箱订单。</strong>
            <strong v-else>文件已成功导入，但未解析出结构化送货明细。</strong>
            系统尚未生成收料明细或库存。确认确属非正式/打板收料时，可在下方加入收料明细并补齐字段；核对无误后点击“确认入库”，才会入库并计入月结。
          </div>
          <details v-if="receiptImportWarnings.length || receiptImportRawText || receiptImportStats.total === 0" class="border-b border-blue-200 bg-blue-50 px-4 py-3 text-[10px] leading-5 text-blue-900" :open="receiptImportStats.matched === 0">
            <summary class="cursor-pointer select-none font-bold">识别诊断详情（OCR 原文、引擎与警告）</summary>
            <div class="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-blue-800">
              <span>识别引擎：<strong>{{ receiptImportBatch.parse_summary.engine || '未返回' }}</strong></span>
              <span v-if="receiptImportBatch.parse_summary.parser_version">解析版本：<strong>{{ receiptImportBatch.parse_summary.parser_version }}</strong></span>
              <span>结构化明细：<strong>{{ receiptImportStats.total }} 行</strong></span>
            </div>
            <div v-if="receiptImportWarnings.length" class="mt-2 rounded-lg border border-blue-200 bg-white/70 px-3 py-2">
              <div v-for="warning in receiptImportWarnings" :key="warning">• {{ warning }}</div>
            </div>
            <div class="mt-2">
              <div class="font-bold text-blue-950">OCR 识别原文</div>
              <pre v-if="receiptImportRawText" class="mt-1 max-h-56 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-blue-200 bg-white p-3 font-mono text-[10px] leading-5 text-slate-700">{{ receiptImportRawText }}</pre>
              <div v-else class="mt-1 rounded-lg border border-blue-200 bg-white/70 px-3 py-2 text-blue-700">OCR 未返回可展示原文。请检查图片清晰度、方向和表格边界，或删除后重新上传。</div>
            </div>
          </details>
          <div class="overflow-x-auto">
            <table class="min-w-[1320px] w-full text-left">
              <thead class="bg-slate-50 text-[10px] font-bold text-slate-500"><tr><th class="px-3 py-2.5">来源</th><th class="px-3 py-2.5">送货单 / 送货日期</th><th class="px-3 py-2.5">合同号</th><th class="px-3 py-2.5">货号</th><th class="px-3 py-2.5">纸品类型 / 纸质</th><th class="px-3 py-2.5">规格</th><th class="px-3 py-2.5 text-right">数量</th><th class="px-3 py-2.5">匹配结果</th><th class="px-3 py-2.5">处理建议</th><th class="px-3 py-2.5">收料处理</th></tr></thead>
              <tbody class="divide-y divide-slate-100">
                <tr v-for="(row, index) in receiptImportPreviewRows" :key="`${row.source_sheet}-${row.source_row}-${index}`" class="hover:bg-slate-50/70">
                  <td class="px-3 py-2.5 text-[10px] text-slate-500">{{ row.source_sheet || '文件' }} · 第 {{ row.source_row || index + 1 }} 行</td>
                  <td class="px-3 py-2.5"><div class="font-mono text-[11px] font-semibold">{{ row.delivery_note_no || receiptImportBatch.parse_summary.document?.delivery_note_no || '待识别' }}</div><div class="text-[9px] text-slate-400">{{ row.delivery_date || receiptImportBatch.parse_summary.document?.delivery_date || '送货日期待复核' }}</div></td>
                  <td class="px-3 py-2.5 font-mono text-[11px] font-semibold">{{ row.contract_no || row.reference || '待识别' }}</td>
                  <td class="px-3 py-2.5 font-mono text-[11px]">{{ row.item_no || '待识别' }}</td>
                  <td class="px-3 py-2.5 text-[11px]"><div class="font-semibold">{{ row.packaging_type || '待复核' }}</div><div class="text-[9px] text-slate-400">{{ row.paper_quality || '' }}</div></td>
                  <td class="px-3 py-2.5 text-[10px] text-slate-600">{{ row.specification || '待识别' }}</td>
                  <td class="px-3 py-2.5 text-right font-semibold tabular-nums">{{ importQuantityLabel(row) }}</td>
                  <td class="px-3 py-2.5"><span class="rounded-full px-2 py-0.5 text-[9px] font-bold ring-1 ring-inset" :class="importMatchTone(row.match_status)">{{ importMatchLabel(row.match_status) }}</span></td>
                  <td class="max-w-[260px] px-3 py-2.5 text-[10px] text-slate-500">{{ row.suggestion || '请人工复核识别结果' }}</td>
                  <td class="px-3 py-2.5">
                    <span v-if="row.match_status === 'MATCHED'" class="text-[10px] font-bold text-emerald-700">已关联正式订单</span>
                    <button v-else-if="row.match_status === 'MISSING_ORDER' && !receiptImportRowAdded(row, index)" type="button" :disabled="Boolean(currentReceipt) || savingReceipt" class="inline-flex h-8 items-center gap-1 rounded-lg border border-amber-300 bg-amber-50 px-2.5 text-[10px] font-bold text-amber-800 hover:bg-amber-100 disabled:opacity-40" @click="addAdHocReceiptLine(row, index)"><Plus class="size-3.5" />作为非正式/打板收料</button>
                    <span v-else-if="receiptImportRowAdded(row, index)" class="text-[10px] font-bold text-blue-700">已加入收料明细</span>
                    <span v-else class="text-[10px] text-slate-400">需先解决匹配不唯一</span>
                  </td>
                </tr>
                <tr v-if="receiptImportPreviewRows.length === 0"><td colspan="10" class="px-4 py-10 text-center text-slate-400">未解析出结构化明细；请查看上方“识别诊断详情”中的 OCR 原文和警告</td></tr>
              </tbody>
            </table>
          </div>
          <div v-if="receiptImportRows.length > receiptImportPreviewRows.length" class="border-t border-slate-200 px-4 py-2 text-[10px] text-slate-500">当前显示前 {{ receiptImportPreviewRows.length }} 行，共 {{ receiptImportRows.length }} 行；全部问题行均已保存。</div>
        </article>

        <div v-if="apiConnected && receiptPage === 'IMPORT' && !receiptImportBatch" class="rounded-xl border border-teal-200 bg-teal-50 p-5 text-teal-900 shadow-sm">
          <div class="flex items-center gap-2 font-bold"><Upload class="size-4" />等待导入并复核送货单</div>
          <p class="mt-1 text-[11px] leading-5 text-teal-800">选择文件后，后端先登记唯一指纹和待复核批次；字段匹配与数量确认完成前，不会创建收料单或库存流水。</p>
        </div>


        <article v-if="receiptPage === 'HISTORY'" class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
            <div>
              <h2 class="flex items-center gap-2 text-lg font-bold text-slate-950"><PackageCheck class="size-5 text-teal-700" />收料历史台账</h2>
              <p class="mt-1 text-[11px] text-slate-500">按送货单查看每项纸品的收料记录，客户、合同和纸品信息分别列示。</p>
            </div>
            <span class="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-bold text-slate-600">{{ receiptHistoryRows.length }} 条明细</span>
          </div>
          <div aria-label="收料历史筛选" class="flex flex-wrap items-center gap-3 border-b border-slate-200 bg-slate-50 px-4 py-3">
            <label class="flex items-center gap-2 text-xs"><span>客户</span><select v-model="selectedCustomer" aria-label="收料历史客户" class="h-9 rounded-lg border border-slate-200 bg-white px-3"><option v-for="customer in customerFilterOptions" :key="customer" :value="customer">{{ customer }}</option></select></label>
            <label class="flex items-center gap-2 text-xs"><span>状态</span><select v-model="receiptHistoryStatus" aria-label="收料历史状态" class="h-9 rounded-lg border border-slate-200 bg-white px-3"><option value="ALL">全部状态</option><option value="PENDING_CONFIRMATION">待确认</option><option value="POSTED">已入库</option><option value="REVERSED">已作废 / 冲销</option></select></label>
            <div class="flex items-center gap-2 text-xs"><span>送货日期</span><DateRangeFilter v-model="receiptHistoryDateRange" label="收料历史送货日期范围" /></div>
            <button type="button" class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-xs" @click="clearReceiptHistoryFilters">清空历史筛选</button>
          </div>
          <div class="overflow-x-auto">
            <table aria-label="收料历史台账明细" class="min-w-[1280px] w-full text-left">
              <thead class="bg-slate-50 text-[10px] font-bold text-slate-500"><tr><th scope="col" class="px-4 py-3">送货单号</th><th scope="col" class="px-4 py-3">送货日期</th><th scope="col" class="px-4 py-3">实际验收日期</th><th scope="col" class="px-4 py-3">客户</th><th scope="col" class="px-4 py-3">合同号</th><th scope="col" class="px-4 py-3">货号</th><th scope="col" class="px-4 py-3">纸品类型</th><th scope="col" class="px-4 py-3">纸质</th><th scope="col" class="px-4 py-3">规格</th><th scope="col" class="px-4 py-3">仓位</th><th scope="col" class="px-4 py-3 text-right">有效收料</th><th scope="col" class="px-4 py-3">状态</th><th scope="col" class="px-4 py-3">经手人 / 时间</th><th scope="col" class="px-4 py-3 text-right">操作</th></tr></thead>
              <tbody class="divide-y divide-slate-100">
                <tr v-for="row in receiptHistoryRows" :key="row.id" class="hover:bg-slate-50/80">
                  <td class="px-4 py-3 font-mono font-semibold">{{ row.deliveryNoteNo || '—' }}</td>
                  <td class="px-4 py-3 font-semibold">{{ row.deliveryDate }}</td>
                  <td class="px-4 py-3 whitespace-nowrap">{{ row.acceptanceDate || '历史未记录' }}</td>
                  <td class="px-4 py-3 font-semibold">{{ row.customer }}</td>
                  <td class="px-4 py-3 font-mono font-semibold">{{ row.contractNo || '—' }}</td>
                  <td class="px-4 py-3 font-mono font-semibold">{{ row.itemNo }}</td>
                  <td class="px-4 py-3 font-semibold">{{ row.packagingType }}</td>
                  <td class="px-4 py-3 font-semibold text-teal-700">{{ row.paperQuality || '—' }}</td>
                  <td class="px-4 py-3 text-slate-500">{{ row.specification || '—' }}</td>
                  <td class="px-4 py-3">{{ row.location || '未填写' }}</td>
                  <td class="px-4 py-3 text-right font-bold tabular-nums text-teal-700">{{ formatNumber(row.effectiveQuantity) }} {{ row.unit }}</td>
                  <td class="px-4 py-3"><span class="rounded-full px-2 py-0.5 text-[10px] font-bold ring-1 ring-inset" :class="row.status === 'POSTED' ? toneClass('green') : toneClass('amber')">{{ row.status === 'REVERSED' && !row.receipt.confirmed_at ? '已作废' : receiptStatusLabel(row.status) }}</span><div v-if="row.sourceType === 'AD_HOC'" class="mt-1 text-[9px] font-bold text-amber-700">非正式/打板收料</div></td>
                  <td class="px-4 py-3"><div class="font-semibold">{{ row.operator || '—' }}</div><div class="mt-0.5 text-[10px] text-slate-500">{{ (row.confirmedAt || '').replace('T', ' ').slice(0, 16) }}</div></td>
                  <td class="px-4 py-3"><div class="flex justify-end gap-2 whitespace-nowrap">
                    <button v-if="canCorrectReceipt && ['PENDING_CONFIRMATION', 'POSTED'].includes(row.status)" type="button" class="inline-flex h-8 items-center justify-center rounded-md border border-red-200 bg-white px-2 text-[11px] font-bold text-red-600 transition hover:bg-red-50" :aria-label="`更正收料单 ${row.receiptNo}`" :title="row.status === 'POSTED' ? '冲销整张收料单的入库，需填写原因并确认' : '作废待确认收料单，需填写原因并确认'" @click="openReceiptCorrection(row.receipt)">{{ row.status === 'POSTED' ? '冲销' : '作废' }}</button>
                    <button v-if="canCorrectReceipt && row.status === 'REVERSED'" type="button" class="inline-flex h-8 items-center justify-center rounded-md border border-teal-200 bg-white px-2 text-[11px] font-bold text-teal-700 transition hover:bg-teal-50" @click="openReceiptHistoryDocument(row.receipt, true)">重新登记</button>
                    <button type="button" class="inline-flex h-8 items-center justify-center rounded-md border border-slate-200 bg-white px-2 text-[11px] font-bold text-slate-600 transition hover:border-teal-300 hover:bg-teal-50 hover:text-teal-700" :aria-label="`查看收料单 ${row.receiptNo}`" title="悬停预览整单明细，单击后保持显示" aria-haspopup="dialog" @mouseenter="showReceiptDetails(row.receipt)" @mouseleave="closeReceiptDetailPreview" @focus="showReceiptDetails(row.receipt)" @blur="closeReceiptDetailPreview" @click="showReceiptDetails(row.receipt, true)">明细</button>
                  </div></td>
                </tr>
                <tr v-if="receiptHistoryRows.length === 0"><td colspan="14" class="px-4 py-10 text-center text-slate-400">没有符合条件的收料历史</td></tr>
              </tbody>
            </table>
          </div>
        </article>
      </section>

      <CartonMasterWorkspace v-else-if="activeTab === 'master-data'" :key="selectedFactoryId" :factory-id="selectedFactoryId" :customers="customerRecords" :initial-tab="masterSection" @changed="masterChanged" @customers="openCustomerManager" @use="orderFromMaster" />
      <section v-else-if="activeTab === 'inventory' || activeTab === 'inventory-movements'" class="space-y-4">
        <CartonStocktakeWorkspace v-if="showStocktake && activeTab === 'inventory'" :key="selectedFactoryId" :factory-id="selectedFactoryId" :initial-position-keys="selectedInventoryBalances.map(row => row.id)" @close="showStocktake = false" @posted="refreshInventoryLedger" />
        <CartonOpeningInventoryImport v-else-if="showInventoryImport && activeTab === 'inventory'" :key="selectedFactoryId" :factory-id="selectedFactoryId" :connected="apiConnected" :can-import="authStore.can('carton_procurement:inventory_write')" :customers="customerRecords" :locations="inventoryLocations" @close="showInventoryImport = false" @imported="openingInventoryImported" />
        <template v-else>
        <div v-if="activeTab === 'inventory'" class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div class="border-b border-slate-200 px-4 py-3">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div><h2 class="flex items-center gap-2 text-lg font-bold text-slate-950"><Boxes class="size-5 text-teal-700" />实时库存结存台账</h2><p class="mt-1 text-[11px] text-slate-500">收、发、存按本仓位累计；结余 = 期初 + 入库 − 出库 + 调仓净额 + 调整。冲销抵减原收发数量。</p></div>
              <div class="flex flex-wrap items-center gap-2"><label class="mr-2 inline-flex items-center gap-2 text-xs text-slate-600"><input v-model="showInventoryMoney" type="checkbox" class="accent-teal-700">显示金额</label><span aria-label="实时库存数量合计" class="mr-2 text-xs text-slate-500">当前结存 {{ inventoryBalanceSummary }} · 显示 {{ inventoryBalances.length }} / {{ localInventoryBalances.length }} 条</span><button type="button" class="h-9 rounded-lg border border-slate-200 px-3 text-xs font-bold text-slate-600" @click="setActiveTab('closing')">月结对账</button></div>
            </div>

          </div>
          <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-slate-50/70 px-4 py-3">
            <div class="flex flex-wrap items-center gap-3"><label class="inline-flex items-center gap-2"><span class="text-xs font-semibold text-slate-600">客户</span><select v-model="selectedCustomer" aria-label="库存台账客户筛选" class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-xs"><option v-for="customer in customerFilterOptions" :key="customer" :value="customer">{{ customer }}</option></select></label><div class="inline-flex items-center gap-2"><span class="text-xs font-semibold text-slate-600">最近入库日期</span><DateRangeFilter v-model="inventoryBalanceDateRange" label="结存台账最近入库日期范围" title="按最近入库日期筛选" /></div><button type="button" aria-label="清空结存台账筛选" :disabled="!hasInventoryBalanceFilters" class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-[11px] font-bold text-slate-600 disabled:cursor-not-allowed disabled:opacity-40" @click="clearInventoryBalanceFilters">清空筛选</button></div>
            <div class="flex flex-wrap items-center gap-2 text-xs"><label>仓库 <select v-model="warehouseFilter" aria-label="库存仓库筛选" class="h-9 rounded-lg border px-2" @change="locationFilter = ''"><option value="">全部仓库</option><option v-for="place in [...new Set(inventoryLocations.map(row => row.warehouse))]" :key="place">{{ place }}</option></select></label><label>仓位 <select v-model="locationFilter" aria-label="库存仓位筛选" class="h-9 rounded-lg border px-2"><option value="">全部仓位</option><option v-for="place in inventoryLocations.filter(row => !warehouseFilter || row.warehouse === warehouseFilter)" :key="place.id" :value="place.id">{{ place.label }}</option></select></label><button type="button" class="h-9 rounded-lg border px-3 text-teal-700" @click="openMaster('LOCATION')">仓位维护</button><CartonLocationPicker v-if="showLocationManager" v-model="newLocationSelection" :locations="inventoryLocations" :factory-id="selectedFactoryId" @created="refreshLocations" /></div><div class="flex flex-wrap items-center gap-2"><span class="mr-2 text-xs text-slate-600">已选 <b class="text-teal-700">{{ selectedInventoryTargetIds.length }}</b> 条</span><button type="button" :disabled="!apiConnected || !selectedInventoryTargetIds.length" class="inline-flex h-9 items-center gap-2 rounded-lg bg-teal-700 px-4 text-xs font-bold text-white disabled:opacity-40" @click="openInventoryOperation('OUTBOUND', '', true, $event)"><PackageCheck class="size-4" />登记所选库存出库</button></div>
            <CartonSelectionSummary :rows="selectedInventoryBalances.map(row => ({ id: row.id, label: `${row.customer} · ${row.poNumber} · ${row.itemNo} · ${row.packagingType} ${row.paperQuality} · ${row.location}` }))" :visible-ids="inventoryBalances.map(row => row.id)" @clear="selectedInventoryTargetIds = []" @remove="selectedInventoryTargetIds = selectedInventoryTargetIds.filter(id => id !== $event)" />
          </div>
          <div v-if="showInventoryMoney" class="flex flex-wrap items-center gap-x-5 gap-y-1 border-b bg-teal-50/50 px-4 py-3 text-xs" aria-label="库存金额汇总">
            <span class="text-slate-600">筛选范围 · {{ inventoryMoneySummary.pending ? '已计价小计' : '库存金额' }}</span><b v-for="amount in inventoryMoneySummary.amounts" :key="amount" class="text-teal-800">{{ amount }}</b><span v-if="inventoryMoneySummary.pending" class="text-amber-700">{{ inventoryMoneySummary.pending }} 条待核价／核算，未计入金额</span><span v-if="!inventoryBalances.length" class="text-slate-500">暂无库存</span>
          </div>
          <div class="overflow-x-auto">
            <table class="inventory-balance-table w-full table-fixed text-left text-xs">
              <colgroup><col style="width:3%"><col style="width:5%"><col style="width:15%"><col style="width:10%"><col style="width:11%"><col style="width:6%"><col style="width:7%"><col style="width:7%"><col style="width:10%"><col style="width:16%"><col style="width:10%"></colgroup>
              <thead class="bg-slate-50 text-[10px] font-bold text-slate-500"><tr><th scope="col" class="px-2 py-3"><label class="inline-flex cursor-pointer items-center" title="全选筛选结果"><input type="checkbox" aria-label="全选库存筛选结果" class="size-5 cursor-pointer accent-teal-600" :checked="inventoryBalances.filter((row) => row.balance > 0).length > 0 && inventoryBalances.filter((row) => row.balance > 0).every((row) => selectedInventoryTargetIds.includes(row.id))" @change="toggleVisibleInventoryBalances(($event.target as HTMLInputElement).checked)"><span class="sr-only">全选筛选结果</span></label></th><th class="px-2 py-3">客户</th><th class="px-2 py-3">合同号</th><th class="px-2 py-3">货号</th><th class="px-2 py-3">纸品类型 / 纸质 / 规格</th><th class="px-2 py-3">仓位</th><th class="px-2 py-3 text-right" title="本仓位累计净入库，含入库冲销">累计入库</th><th class="px-2 py-3 text-right" title="本仓位累计净出库，含退货及出库冲销">累计出库</th><th class="px-2 py-3 text-right bg-teal-50/60">当前结余</th><th class="px-2 py-3">到货情况</th><th class="px-2 py-3 text-right">操作</th></tr></thead>
              <tbody class="divide-y divide-slate-100">
                <tr v-for="row in inventoryBalances" :key="row.id" :data-inventory-balance="row.id" :title="`最近单据：${inventoryBalanceLatestDocumentNo(row) || '—'}；${row.date}`" class="hover:bg-teal-50/40" :class="selectedInventoryTargetIds.includes(row.id) ? 'bg-teal-50/50' : ''">
                  <td class="px-2 py-3"><input v-model="selectedInventoryTargetIds" class="size-5 accent-teal-600" type="checkbox" :value="row.id" :disabled="row.balance <= 0" :aria-label="`选择库存 ${row.itemNo} ${row.specification}`"></td>
                  <td class="px-2 py-3 font-semibold">{{ row.customer }}</td>
                  <td class="px-2 py-3"><div class="truncate font-mono font-semibold" :title="row.poNumber">{{ row.poNumber || '—' }}</div><div v-if="customerPoForLine(row.orderLineId || '')" class="mt-1 break-all text-[10px] text-teal-700">客户 PO {{ customerPoForLine(row.orderLineId || '') }}</div></td><td class="px-2 py-3"><div class="truncate font-mono font-semibold" :title="row.itemNo">{{ row.itemNo }}</div></td>
                  <td class="px-2 py-3"><div class="break-words font-semibold">{{ row.packagingType }} · {{ row.paperQuality }}</div><div class="mt-1 break-words text-slate-500">{{ row.specification }}</div></td>
                  <td class="break-words px-2 py-3">{{ row.location }}</td>
                  <td class="px-2 py-3 text-right tabular-nums text-sm whitespace-nowrap">{{ inventoryQuantity(row.money?.inbound_quantity) }} <span class="text-[10px] text-slate-400">{{ row.unit }}</span></td>
                  <td class="px-2 py-3 text-right tabular-nums text-sm whitespace-nowrap">{{ inventoryQuantity(row.money?.outbound_quantity) }} <span class="text-[10px] text-slate-400">{{ row.unit }}</span></td>
                  <td class="bg-teal-50/40 px-2 py-3 text-right"><div class="whitespace-nowrap text-base font-bold tabular-nums text-teal-800">{{ inventoryQuantity(String(row.balance)) }} <span class="text-xs font-normal">{{ row.unit }}</span></div><div v-if="showInventoryMoney" class="mt-1 break-words text-[11px] text-slate-600" :title="unitCostLabel(row.money)">{{ moneyLabel(row.money) }}</div><div v-for="note in inventoryQuantityNotes(row.money)" :key="note" class="mt-1 text-[11px] leading-4 text-slate-500">{{ note }}</div></td>
                  <td class="px-2 py-3"><CartonInventoryProgress :balance="row.balance" :unit="row.unit" :formal="Boolean(row.orderLineId)" :line="inventoryOrderLines.get(row.orderLineId || '')" /></td>
<td class="px-2 py-3"><div class="flex justify-end gap-2"><button type="button" :aria-label="`出库 ${row.id}`" :disabled="!apiConnected || row.balance <= 0" class="h-8 whitespace-nowrap rounded-md bg-teal-700 px-2 text-xs font-bold text-white disabled:opacity-40" @click="openInventoryOperation('OUTBOUND', row.id, false, $event)">出库</button><button type="button" :aria-label="`调仓 ${row.id}`" :disabled="!apiConnected || row.balance <= 0 || !authStore.can('carton_procurement:inventory_write')" class="h-8 whitespace-nowrap rounded-md border border-teal-200 px-2 text-xs font-bold text-teal-700 hover:bg-teal-50 disabled:opacity-40" @click="openInventoryRelocation(row, $event)">调仓</button></div></td>
                </tr>
                <tr v-if="inventoryBalances.length === 0"><td colspan="11" class="px-2 py-12 text-center text-slate-400">没有符合当前筛选条件的实时结存</td></tr>
              </tbody>
            </table>
          </div>
        </div>
        <div v-if="activeTab === 'inventory-movements'" class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div class="border-b border-slate-200 px-4 py-3">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div><h2 class="font-bold text-slate-950">逐笔交易流水</h2><p class="mt-1 text-[11px] text-slate-500">本表追踪库存数量与成本变化；提交、追加、退单和修改请在操作日志中追溯。</p></div>
              <label class="ml-auto inline-flex items-center gap-2 text-xs text-slate-600"><input v-model="showInventoryMoney" type="checkbox" class="accent-teal-700">显示金额</label><button type="button" class="h-9 rounded-lg border border-violet-200 bg-violet-50 px-3 text-[11px] font-bold text-violet-700 hover:bg-violet-100" @click="setActiveTab('audit')"><GitBranch class="mr-1 inline size-3.5" />查看操作日志</button>
            </div>
            <div class="mt-3 flex flex-wrap items-end gap-3 rounded-lg bg-slate-50 p-3">
              <label class="space-y-1"><span class="block text-[10px] font-bold text-slate-500">流水类型</span><select v-model="inventoryMovementFilter" aria-label="库存流水类型" class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-[11px]"><option value="ALL">全部</option><option value="INBOUND">入库</option><option value="OUTBOUND">出库</option><option value="ADJUSTMENT">调整</option><option value="REVERSAL">冲销</option></select></label>
              <div class="space-y-1"><span class="block text-[10px] font-bold text-slate-500">记账时间</span><DateRangeFilter v-model="inventoryMovementDateRange" label="库存流水记账时间范围" /></div><button type="button" aria-label="清空流水筛选" class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-xs text-slate-600" @click="clearMovementFilters">清空筛选</button><p class="w-full text-xs text-slate-500">按客户、合同或货号、流水类型和记账时间查询；仓位及最近入库日期筛选仅用于实时库存。</p>
            </div>
          </div>
          <div class="overflow-x-auto">
            <table class="min-w-[1380px] w-full text-left">
              <thead class="bg-slate-50 text-[10px] font-bold text-slate-500"><tr><th class="px-4 py-3">记账时间</th><th class="px-4 py-3">业务单据号</th><th class="px-4 py-3">客户 / PO</th><th class="px-4 py-3">货号</th><th class="px-4 py-3">纸品类型</th><th class="px-4 py-3">纸质</th><th class="px-4 py-3">类型</th><th class="px-4 py-3 text-right">变动数量</th><th v-if="showInventoryMoney" class="px-4 py-3 text-right">成本金额 / 单位成本</th><th class="px-4 py-3 text-right">结存</th><th class="px-4 py-3">仓位</th><th class="px-4 py-3">经手人</th><th class="px-4 py-3">操作</th></tr></thead>
              <tbody class="divide-y divide-slate-100">
                <tr v-for="row in visibleMovements" :key="row.id" class="hover:bg-slate-50/80">
                  <td class="whitespace-nowrap px-4 py-3"><time class="font-semibold" :title="`流水号：${row.id}`">{{ row.date }}</time></td>
                  <td class="px-4 py-3"><div class="font-mono font-semibold">{{ row.documentNo }}</div><div class="mt-0.5 text-[10px] text-slate-500">{{ row.source }}</div></td>
                  <td class="px-4 py-3"><div class="font-semibold">{{ row.customer }}</div><div class="mt-0.5 text-[10px] text-slate-500">{{ row.poNumber }}</div></td>
                  <td class="px-4 py-3 font-mono font-semibold">{{ row.itemNo }}</td>
                  <td class="px-4 py-3"><div class="font-semibold">{{ row.packagingType }}</div><div class="text-[10px] text-slate-500">{{ row.specification }}</div></td>
                  <td class="px-4 py-3 font-semibold text-teal-700">{{ row.paperQuality }}</td>
                  <td class="px-4 py-3"><span class="rounded-full px-2 py-0.5 text-[10px] font-bold ring-1 ring-inset" :class="row.movementType === '入库' ? toneClass('green') : row.movementType === '出库' ? toneClass('blue') : toneClass('amber')">{{ row.movementType }}</span></td>
                  <td class="px-4 py-3 text-right font-bold tabular-nums" :class="row.quantity < 0 ? 'text-red-600' : 'text-emerald-700'">{{ row.quantity > 0 ? '+' : '' }}{{ row.quantity }}</td>
                  <td v-if="showInventoryMoney" class="whitespace-nowrap px-4 py-3 text-right"><div class="font-semibold tabular-nums">{{ moneyLabel(row.money) }}</div><div class="mt-1 text-[10px] text-slate-500">{{ unitCostLabel(row.money) }}</div></td>
                  <td class="px-4 py-3 text-right font-bold tabular-nums">{{ row.balance }}</td>
                  <td class="px-4 py-3">{{ row.location }}</td><td class="px-4 py-3">{{ row.operator }}</td>
                  <td class="px-4 py-3"><button v-if="movementCanReverse(row)" type="button" class="h-8 rounded-lg border border-red-200 bg-white px-3 text-[10px] font-bold text-red-700 hover:bg-red-50" @click="openInventoryReversal(row)">冲销</button><span v-else-if="localMovements.some((candidate) => candidate.reversalOfMovementId === row.id)" class="text-[10px] font-bold text-slate-400">已冲销</span><span v-else class="text-[10px] text-slate-300">—</span></td>
                </tr>
                <tr v-if="visibleMovements.length === 0"><td :colspan="showInventoryMoney ? 13 : 12" class="px-4 py-12 text-center text-slate-400">没有符合当前筛选条件的库存流水</td></tr>
              </tbody>
            </table>
          </div>
        </div>
        </template>
      </section>

      <CartonInventorySummary v-else-if="activeTab === 'inventory-summary'" :factory-id="selectedFactoryId" :customers="customerRecords" :search="globalSearch" :refresh-key="inventoryReportRefreshKey" :connected="apiConnected" @clear-search="globalSearch = ''" @inventory="setActiveTab('inventory')" @closing="setActiveTab('closing')" />

      <section v-else-if="activeTab === 'closing'" class="space-y-4">
        <nav aria-label="月结对账子页面" class="flex gap-2 rounded-xl border bg-white p-2 text-xs"><button type="button" :aria-pressed="closingView === 'SUPPLIER'" class="rounded-lg px-4 py-2" :class="closingView === 'SUPPLIER' ? 'bg-teal-700 text-white' : 'text-slate-600'" @click="closingView = 'SUPPLIER'">供应商月结对账</button><button type="button" :aria-pressed="closingView === 'INVENTORY'" class="rounded-lg px-4 py-2" :class="closingView === 'INVENTORY' ? 'bg-teal-700 text-white' : 'text-slate-600'" @click="closingView = 'INVENTORY'">库存月结记录</button></nav>
        <CartonSupplierSettlement v-show="closingView === 'SUPPLIER'" :key="selectedFactoryId" :factory-id="selectedFactoryId" />
        <template v-if="closingView === 'INVENTORY'">
        <div class="flex flex-wrap items-center gap-3 rounded-xl border bg-white p-3 text-xs"><label>查询月份 <input v-model="closingQueryPeriod" aria-label="月结查询月份" type="month" class="h-9 rounded-lg border px-3"></label><select v-model="closingStatusFilter" aria-label="月结状态筛选" class="h-9 rounded-lg border px-3"><option value="ALL">全部状态</option><option value="OPEN">待处理</option><option value="LOCKED">已锁账</option></select><button type="button" class="h-9 rounded-lg border px-3" @click="closingQueryPeriod = ''; closingStatusFilter = 'ALL'; selectedCustomer = '全部客户'; globalSearch = ''">清空筛选</button><span class="text-slate-500">{{ closingQueryPeriod || '全部月份' }} · 查询不会生成或修改月结</span></div>
        <div class="grid gap-4 xl:grid-cols-[1fr_380px]">
          <article class="rounded-xl border border-violet-200 bg-violet-50 p-4 shadow-sm"><div class="flex items-center gap-2 font-bold text-violet-950"><FileSpreadsheet class="size-4" />期间库存月结核对页</div><p class="mt-1 text-[11px] leading-5 text-violet-800">回答“某客户在选定期间的期初、入库、出库、调整和期末是否对平”。此页核对库存账；供应商送货账单需另行逐笔核对。当月可以核对确认并继续收发货；月份结束、数据核对完成后，再由主管最终锁账。</p></article>
          <article class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div class="text-[11px] font-bold text-slate-900">与库存页面的区别</div><p class="mt-1 text-[11px] text-slate-500">要看当前余量、仓位或某一笔收发来源，应返回实时库存台账。</p><button type="button" class="mt-3 text-[11px] font-bold text-teal-700" @click="setActiveTab('inventory')">去实时库存台账 →</button></article>
        </div>
        <div class="grid gap-3 md:grid-cols-3">
          <article class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div class="text-[11px] text-slate-500">月结期间</div><div class="mt-2 flex flex-wrap items-center gap-2"><input v-model="closingPeriod" aria-label="月结期间" type="month" class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-[13px] font-bold outline-none focus:border-teal-500"><button type="button" :disabled="Boolean(closingBusyId) || !apiConnected || !canManageClosingPrices || !closingPeriod" :title="!apiConnected ? '后端未连接' : !canManageClosingPrices ? '需要月结管理权限' : '按月份生成或更新草稿'" class="h-9 rounded-lg bg-teal-700 px-3 text-[11px] font-bold text-white disabled:cursor-not-allowed disabled:opacity-50" @click="generateClosingSnapshot">{{ closingBusyId === 'generate' ? '生成中…' : '生成月结草稿' }}</button></div><div class="mt-1 text-[10px] text-slate-400">按所选月份形成快照，生成或更新草稿后需重新核对；已锁账客户不受影响</div></article>
          <article aria-label="库存月结记录统计" class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div class="text-[11px] text-slate-500">月结记录</div><div class="mt-2 text-2xl font-bold">{{ visibleClosings.length }} 份</div><div class="mt-1 text-[10px] text-slate-400">按月份、客户及币种分别统计</div></article>
          <article aria-label="库存月结待处理统计" class="rounded-xl border border-amber-200 bg-amber-50 p-4 shadow-sm"><div class="text-[11px] font-bold text-amber-800">待处理记录</div><div class="mt-2 text-2xl font-bold text-amber-900">{{ visibleClosings.filter((row) => row.status !== '已锁账').length }} 份</div><div class="mt-1 text-[10px] text-amber-700">草稿、待核对或已核对确认的月结记录</div></article>
        </div>
        <div class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div class="border-b border-slate-200 px-4 py-3"><h2 class="font-bold text-slate-950">客户月结汇总快照</h2><p class="mt-1 text-[11px] text-slate-500">期末 = 期初 + 入库 − 出库 + 调整；库存金额按移动加权成本计算。缺价或计价异常处理后才能确认、锁账。</p></div>
          <div class="overflow-x-auto">
            <table class="min-w-[1220px] w-full text-left">
              <thead class="bg-slate-50 text-[10px] font-bold text-slate-500"><tr><th class="px-4 py-3">客户</th><th class="px-4 py-3">期间</th><th class="px-4 py-3 text-right">期初</th><th class="px-4 py-3 text-right">入库</th><th class="px-4 py-3 text-right">出库</th><th class="px-4 py-3 text-right">调整</th><th class="px-4 py-3 text-right">期末</th><th class="px-4 py-3 text-right">期末金额</th><th class="px-4 py-3">对账状态</th><th class="px-4 py-3">操作</th></tr></thead>
              <tbody class="divide-y divide-slate-100">
                <tr v-for="row in visibleClosings" :key="row.id" class="hover:bg-slate-50/80">
                  <td class="px-4 py-3 font-bold">{{ row.customer }}</td><td class="px-4 py-3">{{ row.period }}</td><td class="px-4 py-3 text-right tabular-nums"><span class="whitespace-pre-line">{{ closingQuantityText(row.id, 'opening_quantity') }}</span></td><td class="px-4 py-3 text-right text-emerald-700 tabular-nums"><span class="whitespace-pre-line">{{ closingQuantityText(row.id, 'inbound_quantity') }}</span></td><td class="px-4 py-3 text-right text-blue-700 tabular-nums"><span class="whitespace-pre-line">{{ closingQuantityText(row.id, 'outbound_quantity') }}</span></td><td class="px-4 py-3 text-right tabular-nums"><span class="whitespace-pre-line">{{ closingQuantityText(row.id, 'adjustment_quantity') }}</span></td><td class="px-4 py-3 text-right text-[14px] font-bold tabular-nums"><span class="whitespace-pre-line">{{ closingQuantityText(row.id, 'ending_quantity') }}</span></td><td class="px-4 py-3 text-right"><div class="font-semibold tabular-nums">{{ formatMoney(row.endingAmount, row.currency) }}</div><div class="mt-0.5 text-[9px] font-bold text-slate-400">{{ row.currency }}</div><div v-if="closingRecord(row.id)?.pricing_issues?.length" class="mt-1 text-xs font-semibold text-amber-700">暂估金额 · 待核价</div></td><td class="px-4 py-3"><span class="rounded-full px-2 py-0.5 text-[10px] font-bold ring-1 ring-inset" :class="toneClass(row.tone)">{{ row.status }}</span></td><td class="px-4 py-3"><button type="button" :disabled="closingButtonDisabled(row.id)" :title="closingButtonHint(row.id)" class="h-8 rounded-lg border border-teal-200 bg-white px-3 text-[11px] font-bold text-teal-700 disabled:cursor-not-allowed disabled:border-slate-200 disabled:text-slate-400" @click="advanceClosing(row.id)">{{ closingBusyId === row.id ? '处理中…' : closingButtonLabel(row.id) }}</button><button v-if="closingRecord(row.id)?.status === 'LOCKED' && canFinalizeClosing" type="button" :disabled="Boolean(closingBusyId)" class="ml-2 h-8 rounded-lg border border-amber-300 px-3 text-xs font-bold text-amber-800" @click="openClosingDecision(closingRecord(row.id)!, 'UNLOCK')">解锁重核</button><p class="mt-1 max-w-52 text-[10px] text-slate-500">{{ closingButtonHint(row.id) }}</p></td>
                </tr>
                <tr v-if="visibleClosings.length === 0"><td colspan="10" class="px-4 py-12 text-center text-slate-400">没有符合当前筛选条件的月结记录；可先选择期间生成草稿</td></tr>
              </tbody>
            </table>
          </div>
          <div class="border-t border-slate-200 px-4 py-3"><p class="text-[11px] text-slate-500">核对流程：草稿 → 待核对 → 核对确认，期间可以正常收发货。月份结束后由主管最终锁账；误锁需填写原因解锁，并重新核对。</p></div>
        </div>
        <div v-for="closing in closingRecords.filter((row) => visibleClosings.some((visible) => visible.id === row.id) && row.status !== 'LOCKED' && row.pricing_issues?.length)" :key="`pricing-${closing.id}`" class="rounded-xl border border-amber-200 bg-amber-50 p-4">
          <h3 class="text-sm font-bold text-amber-900">{{ closing.customer_name }} · {{ closing.period }} · {{ closing.currency }} 待核价</h3>
          <p class="mt-1 text-xs text-amber-800">以下记录会影响库存金额，处理完成前不能确认或锁账。补价将保留原始记录，并重新核对相关月结。</p>
          <div v-for="issue in closing.pricing_issues" :key="issue.movement_id + issue.message" class="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-lg bg-white p-3 text-xs">
            <div><div class="font-semibold">{{ issue.document_no }} · {{ issue.item_no }} · {{ issue.packaging_type }}</div><div class="mt-1 text-slate-500">{{ issue.occurred_at.slice(0, 10) }} · {{ issue.message }}</div></div>
            <button v-if="issue.can_price" type="button" :disabled="!canManageClosingPrices" class="h-8 rounded-lg border border-amber-300 px-3 font-semibold text-amber-800 disabled:opacity-40" @click="openPriceConfirmation(issue)">核实单价</button>
          </div>
        </div>
        </template>
      </section>

      <section v-else-if="activeTab === 'exceptions'" class="space-y-4">
        <div class="flex flex-wrap items-center gap-3 rounded-xl border bg-white p-3 text-xs"><select v-model="exceptionStatusFilter" aria-label="异常状态筛选" class="h-9 rounded-lg border px-3"><option value="OPEN">待处理 / 处理中</option><option value="ALL">全部状态</option><option>待处理</option><option>处理中</option><option>已解决</option><option>已关闭</option></select><select v-model="exceptionTypeFilter" aria-label="异常类型筛选" class="h-9 rounded-lg border px-3"><option value="ALL">全部类型</option><option v-for="type in exceptionTypeOptions" :key="type">{{ type }}</option></select><button type="button" class="h-9 rounded-lg border px-3" @click="exceptionStatusFilter = 'ALL'; exceptionTypeFilter = 'ALL'; selectedCustomer = '全部客户'; globalSearch = ''">清空筛选</button></div>
        <div class="rounded-xl border border-blue-200 bg-blue-50 p-4 text-[11px] leading-5 text-blue-800"><div class="font-bold text-blue-950">导入异常会在这里形成正式待办</div><p class="mt-1">排期疑似漏单、送货单未匹配、数量差异和匹配不唯一均需人工处理；排期导入本身不会创建订单，送货单导入本身不会增加库存。</p></div>
        <div class="grid gap-3 md:grid-cols-3"><article class="rounded-xl border border-red-200 bg-red-50 p-4"><div class="text-[11px] font-bold text-red-800">高优先级</div><div class="mt-2 text-2xl font-bold text-red-900">{{ visibleExceptions.filter((row) => row.tone === 'red' && row.status !== '已关闭').length }}</div></article><article class="rounded-xl border border-amber-200 bg-amber-50 p-4"><div class="text-[11px] font-bold text-amber-800">待处理 / 处理中</div><div class="mt-2 text-2xl font-bold text-amber-900">{{ visibleExceptions.filter((row) => row.status === '待处理' || row.status === '处理中').length }}</div></article><article class="rounded-xl border border-slate-200 bg-white p-4"><div class="text-[11px] font-bold text-slate-600">已解决 / 已关闭</div><div class="mt-2 text-2xl font-bold text-slate-900">{{ visibleExceptions.filter((row) => row.status === '已解决' || row.status === '已关闭').length }}</div></article></div>
        <div class="rounded-xl border border-slate-200 bg-white p-3 space-y-2">
          <label class="flex items-center gap-2 text-xs font-semibold"><input type="checkbox" aria-label="全选当前筛选异常" :checked="allVisibleExceptionsSelected" :indeterminate="someVisibleExceptionsSelected && !allVisibleExceptionsSelected" :disabled="!visibleExceptions.length" class="size-4 accent-teal-600" @change="selectVisibleExceptions(($event.target as HTMLInputElement).checked)">全选当前筛选异常（{{ visibleExceptions.length }} 条）</label>
          <div class="flex flex-wrap items-center gap-2">
            <input v-model="bulkExceptionNote" aria-label="批量异常处理说明" placeholder="批量处理说明（选填）" maxlength="4000" class="h-9 min-w-60 flex-1 rounded-lg border px-3 text-xs" :disabled="Boolean(exceptionBusyId)">
            <button v-for="status in (['OPEN', 'IN_PROGRESS', 'RESOLVED'] as const)" :key="status" type="button" :disabled="!canBulkAdvanceExceptions(status)" class="h-9 rounded-lg border border-teal-200 px-3 text-xs font-semibold text-teal-700 disabled:opacity-40" @click="bulkAdvanceExceptions(status)">批量{{ exceptionActionLabel(status) }}</button>
          </div>
          <p v-if="selectedExceptionNos.length > 500" class="text-xs text-amber-700">单次最多处理 500 条，请在“查看已选”中减少选择。</p>
          <CartonSelectionSummary :rows="selectedExceptions.map(row => ({ id: row.id, label: `${row.customer} · ${row.id} · ${row.title}` }))" :visible-ids="visibleExceptions.map(row => row.id)" @clear="selectedExceptionNos = []" @remove="selectedExceptionNos = selectedExceptionNos.filter(id => id !== $event)" />
        </div>
        <div class="grid gap-3 xl:grid-cols-2">
          <article v-for="row in visibleExceptions" :key="row.id" class="rounded-xl border p-4 shadow-sm" :class="[toneClass(row.tone, 'surface'), selectedExceptionNos.includes(row.id) ? 'ring-2 ring-teal-500' : '']">
            <div class="flex items-start gap-3"><input v-model="selectedExceptionNos" type="checkbox" :value="row.id" :aria-label="`选择异常 ${row.id}`" class="mt-2 size-4 shrink-0 accent-teal-600"><span class="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-white/80"><AlertTriangle class="size-4" /></span><div class="min-w-0 flex-1"><div class="flex flex-wrap items-center gap-2"><span class="text-[10px] font-bold">{{ row.id }}</span><span class="rounded-full bg-white/70 px-2 py-0.5 text-[10px] font-bold">{{ row.type }}</span><span class="ml-auto rounded-full bg-white/70 px-2 py-0.5 text-[10px] font-bold">{{ row.status }}</span></div><h2 class="mt-2 text-[14px] font-bold">{{ row.title }}</h2><p class="mt-1 text-[11px] opacity-80">{{ row.detail }}</p><div class="mt-3 flex flex-wrap gap-4 text-[10px] font-semibold"><span>客户：{{ row.customer }}</span><span>责任部门：{{ row.owner }}</span><span>{{ row.deadline }}</span></div><div v-if="exceptionRecord(row.id)" class="mt-3 flex flex-col gap-2 border-t border-current/10 pt-3 sm:flex-row"><input v-model="resolutionNotes[exceptionRecordId(row.id)]" :aria-label="`${row.id} 处理说明`" placeholder="处理说明（选填）" class="h-9 min-w-0 flex-1 rounded-lg border border-white/80 bg-white/80 px-3 text-[11px] text-slate-800 outline-none focus:border-teal-500"><button type="button" :disabled="exceptionButtonDisabled(row.id)" class="h-9 rounded-lg bg-white px-3 text-[11px] font-bold text-teal-700 shadow-sm disabled:cursor-not-allowed disabled:text-slate-400" @click="advanceException(row.id)">{{ exceptionBusyId === exceptionRecord(row.id)?.id ? '处理中…' : exceptionButtonLabel(row.id) }}</button></div></div></div>
          </article>
          <div v-if="visibleExceptions.length === 0" class="col-span-full rounded-xl border border-slate-200 bg-white py-16 text-center text-slate-400">没有符合当前筛选条件的异常</div>
        </div>
      </section>

      <section v-else-if="activeTab === 'audit'" class="space-y-4">
        <div class="rounded-xl border border-violet-200 bg-violet-50 p-4"><div class="flex items-center gap-2 font-bold text-violet-950"><GitBranch class="size-4" />统一操作日志</div><p class="mt-1 text-[11px] leading-5 text-violet-800">确认订单并锁定、追加、退单、修改、收料和出入库均写入同一份不可变日志，统一记录时间、操作人、操作、业务对象和关键变更。</p></div>
        <div class="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
          <label class="space-y-1"><span class="block text-[10px] font-bold text-slate-500">开始日期</span><input v-model="auditDateFrom" aria-label="操作日志开始日期" type="date" class="h-9 rounded-lg border border-slate-200 px-3 text-[11px]"></label>
          <label class="space-y-1"><span class="block text-[10px] font-bold text-slate-500">结束日期</span><input v-model="auditDateTo" aria-label="操作日志结束日期" type="date" class="h-9 rounded-lg border border-slate-200 px-3 text-[11px]"></label>
          <label class="space-y-1"><span class="block text-[10px] font-bold text-slate-500">操作人</span><select v-model="auditActorFilter" aria-label="操作日志操作人" class="h-9 min-w-36 rounded-lg border border-slate-200 bg-white px-3 text-[11px]"><option value="ALL">全部操作人</option><option v-for="actor in auditActorOptions" :key="actor.id" :value="actor.id">{{ actor.name }}</option></select></label>
          <label class="space-y-1"><span class="block text-[10px] font-bold text-slate-500">操作</span><select v-model="auditEventFilter" aria-label="操作日志操作" class="h-9 min-w-36 rounded-lg border border-slate-200 bg-white px-3 text-[11px]"><option value="ALL">全部操作</option><option v-for="eventType in auditEventOptions" :key="eventType" :value="eventType">{{ auditEventLabel(eventType) }}</option></select></label>
          <label class="min-w-60 flex-1 space-y-1"><span class="block text-[10px] font-bold text-slate-500">关键字</span><input v-model="auditSearch" aria-label="查找操作日志" placeholder="订单号 / 单据号 / 原因 / 变更内容" class="h-9 w-full rounded-lg border border-slate-200 px-3 text-[11px] outline-none focus:border-violet-500"></label>
          <button type="button" aria-label="清空操作日志筛选" :disabled="!hasAuditFilters" class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-[11px] font-bold text-slate-600 disabled:cursor-not-allowed disabled:opacity-40" @click="clearAuditFilters">清空筛选</button>
          <span class="h-9 rounded-lg bg-slate-100 px-3 py-2 text-[11px] font-bold text-slate-600">{{ visibleAuditRecords.length }} 条</span>
        </div>
        <div class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"><div class="overflow-x-auto"><table class="min-w-[1120px] w-full text-left"><thead class="bg-slate-50 text-[10px] font-bold text-slate-500"><tr><th class="px-4 py-3">时间</th><th class="px-4 py-3">操作人</th><th class="px-4 py-3">操作</th><th class="px-4 py-3">业务对象</th><th class="px-4 py-3">变更内容</th></tr></thead><tbody class="divide-y divide-slate-100"><tr v-for="row in visibleAuditRecords" :key="row.id" class="hover:bg-slate-50/80"><td class="px-4 py-3"><div class="font-semibold">{{ row.created_at.replace('T', ' ').slice(0, 16) }}</div><div class="mt-0.5 font-mono text-[9px] text-slate-400">#{{ row.sequence }}</div></td><td class="px-4 py-3"><div class="font-semibold">{{ row.actor_name || row.actor_user_id }}</div><div class="mt-0.5 font-mono text-[9px] text-slate-400">{{ row.actor_user_id }}</div></td><td class="px-4 py-3"><span class="rounded-full bg-violet-50 px-2 py-1 text-[10px] font-bold text-violet-700 ring-1 ring-inset ring-violet-200">{{ auditEventLabel(row.event_type) }}</span></td><td class="px-4 py-3"><div class="font-semibold">{{ auditEntityLabel(row) }}</div><div class="text-[9px] text-slate-400">{{ row.entity_type }} · {{ row.entity_id }}</div></td><td class="max-w-[480px] px-4 py-3 text-[11px] leading-5 text-slate-600">{{ auditDetailSummary(row.detail) }}</td></tr><tr v-if="!visibleAuditRecords.length"><td colspan="5" class="px-4 py-12 text-center text-slate-400">没有符合当前筛选条件的操作日志</td></tr></tbody></table></div></div>
      </section>
    </div>

    <DialogRoot :open="Boolean(replenishTarget)" @update:open="open => { if (!open && !replenishing) replenishTarget = null }">
      <DialogOverlay class="fixed inset-0 z-[70] bg-slate-950/40" />
      <DialogContent class="fixed left-1/2 top-1/2 z-[71] max-h-[90vh] w-[calc(100%-2rem)] max-w-3xl -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-2xl bg-white p-6 shadow-xl" @interact-outside.prevent @escape-key-down="event => { if (replenishing) event.preventDefault() }">
        <DialogTitle class="text-lg font-bold">补单 {{ replenishTarget?.order_no }}</DialogTitle>
        <DialogDescription class="mt-2 text-sm text-slate-600">原订单数量保持不变。提交时按下面的仓位自动出库，生成独立补单；供应商补货到仓后，再通过收料入库补回。</DialogDescription>
        <form class="mt-5 space-y-4" @submit.prevent="submitReplenishment">
          <label class="block text-sm font-semibold">责任方 *<select v-model="replenishResponsibility" aria-label="补单责任方" required :disabled="replenishing" class="mt-2 h-10 w-full rounded-lg border bg-white px-3"><option value="" disabled>请选择责任方</option><option value="OWN">我方问题</option><option value="SUPPLIER">供应商问题</option></select></label>
          <p v-if="replenishResponsibility" class="text-sm text-teal-700">{{ replenishResponsibility === 'SUPPLIER' ? '供应商责任：补货免费，不新增月结应付；入库自动沿用本次出库成本，无需填写收费单价。' : '我方责任：补货按实际验收入库数量和单价计入月结一次；本次出库不重复收费。' }}</p>
          <div class="overflow-auto rounded-lg border"><table class="w-full text-left text-xs"><thead class="bg-slate-50"><tr><th class="p-3">纸品</th><th class="p-3">出库仓位</th><th class="p-3 text-right">可用库存</th><th class="p-3">本次补单 / 自动出库</th></tr></thead><tbody><tr v-for="row in replenishPositions" :key="row.id" class="border-t"><td class="p-3">{{ row.packagingType }} · {{ row.paperQuality }}<div class="mt-1 text-slate-500">{{ row.specification }}</div></td><td class="p-3">{{ row.location }}</td><td class="p-3 text-right">{{ formatNumber(row.balance) }} {{ row.unit }}</td><td class="p-3"><input v-model="replenishQuantities[row.id]" type="number" min="0" :max="row.balance" step="0.0001" :disabled="replenishing" :aria-label="`补单数量 ${row.id}`" placeholder="0" class="h-9 w-28 rounded-lg border px-2"> {{ row.unit }}</td></tr><tr v-if="!replenishPositions.length"><td colspan="4" class="p-5 text-center text-slate-500">该订单没有可用仓位库存，暂不能补单出库。</td></tr></tbody></table></div>
          <label class="block text-sm">补单说明（选填）<textarea v-model="replenishReason" aria-label="补单说明" maxlength="500" :disabled="replenishing" class="mt-2 w-full rounded-lg border p-3" /></label>
          <p v-if="replenishError" role="alert" class="text-sm text-red-600">{{ replenishError }}</p>
          <div class="flex justify-end gap-2"><DialogClose :disabled="replenishing" class="rounded-lg border px-4 py-2">返回</DialogClose><button type="submit" :disabled="replenishing || !replenishPositions.length || !apiConnected" class="rounded-lg bg-teal-700 px-4 py-2 font-semibold text-white disabled:opacity-40">{{ replenishing ? '正在提交…' : '确认补单并出库' }}</button></div>
        </form>
      </DialogContent>
    </DialogRoot>

    <DialogRoot :open="Boolean(deleteHistoryTarget) || deleteHistoryTargets.length > 0" @update:open="open => { if (!open && !deletingHistory) { deleteHistoryTarget = null; deleteHistoryTargets = [] } }">
      <DialogOverlay class="fixed inset-0 z-[70] bg-slate-950/40" />
      <DialogContent class="fixed left-1/2 top-1/2 z-[71] w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-2xl bg-white p-6 shadow-xl" @interact-outside.prevent @escape-key-down="event => { if (deletingHistory) event.preventDefault() }">
        <DialogTitle class="text-lg font-bold">{{ deleteHistoryTarget ? `删除历史订单 ${deleteHistoryTarget.order_no}` : `批量删除 ${deleteHistoryTargets.length} 张历史订单` }}</DialogTitle>
        <DialogDescription class="mt-2 text-sm text-slate-600">仅无收料或库存记录的历史导入订单可删除，全部校验通过后一次生效。删除后从订单台账移除，操作日志保留原始明细；已有收料记录（含待确认或已冲销）的订单不能删除。</DialogDescription>
        <p v-if="deleteHistoryTargets.length" class="mt-2 max-h-28 overflow-auto text-xs text-slate-600">{{ deleteHistoryTargets.map(order => order.order_no).join('、') }}</p>
        <form class="mt-4 space-y-4" @submit.prevent="deleteHistoryOrder">
          <label class="block text-sm">删除原因 *<textarea v-model="deleteHistoryReason" aria-label="历史订单删除原因" required minlength="4" maxlength="500" class="mt-2 w-full rounded-lg border p-3" /></label>
          <div class="flex justify-end gap-2"><DialogClose :disabled="deletingHistory" class="rounded-lg border px-4 py-2">返回</DialogClose><button type="submit" :disabled="deletingHistory || deleteHistoryReason.trim().length < 4" class="rounded-lg bg-red-600 px-4 py-2 text-white disabled:opacity-40">{{ deletingHistory ? '删除中…' : '确认删除历史订单' }}</button></div>
        </form>
      </DialogContent>
    </DialogRoot>

    <DialogRoot :open="Boolean(undoImportTarget)" @update:open="open => { if (!open && !undoingImport) undoImportTarget = null }">
      <DialogOverlay class="fixed inset-0 z-[70] bg-slate-950/40" />
      <DialogContent class="fixed left-1/2 top-1/2 z-[71] w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-2xl bg-white p-6 shadow-xl" @interact-outside.prevent @escape-key-down="event => { if (undoingImport) event.preventDefault() }">
        <DialogTitle class="text-lg font-bold">撤销本次导入</DialogTitle>
        <DialogDescription class="mt-2 text-sm text-slate-600">将一次性撤销 {{ undoImportTarget?.original_filename }} 的全部 {{ undoImportTarget?.parse_summary.row_count ?? 0 }} 行核对结果及关联异常工作项，不支持单条删除。正式订单和库存不受影响，原始记录与撤销原因保留在操作日志。撤销后不能再次操作此批次。</DialogDescription>
        <form class="mt-4 space-y-4" @submit.prevent="undoScheduleImport">
          <label class="block text-sm">撤销原因 *<textarea v-model="undoImportReason" aria-label="导入批次撤销原因" required minlength="4" maxlength="500" class="mt-2 w-full rounded-lg border p-3" /></label>
          <div class="flex justify-end gap-2"><DialogClose :disabled="undoingImport" class="rounded-lg border px-4 py-2">返回</DialogClose><button type="submit" :disabled="undoingImport || undoImportReason.trim().length < 4" class="rounded-lg bg-red-600 px-4 py-2 text-white disabled:opacity-40">{{ undoingImport ? '撤销中…' : '确认整批撤销' }}</button></div>
        </form>
      </DialogContent>
    </DialogRoot>

    <DialogRoot :open="showInventoryRelocation" @update:open="(open) => { if (!relocationBusy) showInventoryRelocation = open }">
      <DialogOverlay class="fixed inset-0 z-[70] bg-slate-950/40 backdrop-blur-sm" />
      <DialogContent class="fixed left-1/2 top-1/2 z-[71] max-h-[90vh] w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-2xl bg-white p-6 shadow-2xl" @interact-outside.prevent @escape-key-down="(event) => { if (relocationBusy) event.preventDefault() }" @close-auto-focus="restoreInventoryFocus">
        <div class="flex items-start justify-between gap-4">
          <div><DialogTitle class="text-lg font-bold text-slate-950">库存调仓</DialogTitle><DialogDescription class="mt-1 text-sm text-slate-500">将部分或全部库存移至另一仓位，总库存保持不变。</DialogDescription></div>
          <DialogClose :disabled="relocationBusy" aria-label="关闭调仓" class="rounded-lg p-1 text-slate-500 hover:bg-slate-100 disabled:opacity-40"><X class="size-5" /></DialogClose>
        </div>
        <form v-if="relocationTarget" class="mt-5 space-y-5" @submit.prevent="submitInventoryRelocation">
          <div class="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <div class="flex items-start justify-between gap-3"><div><p class="font-bold text-slate-950">{{ relocationTarget.customer }} · {{ relocationTarget.itemNo }}</p><p class="mt-1 text-xs text-slate-500">合同号 {{ relocationTarget.poNumber || '—' }}</p></div><span class="whitespace-nowrap text-lg font-bold text-teal-700">{{ formatNumber(relocationTarget.balance) }} <span class="text-xs font-medium">{{ relocationTarget.unit }}</span></span></div>
            <p class="mt-3 text-sm text-slate-600">{{ relocationTarget.packagingType }} · {{ relocationTarget.paperQuality }} · {{ relocationTarget.specification }}</p>
          </div>
          <div class="grid gap-3 sm:grid-cols-2">
            <div><span class="block text-xs font-semibold text-slate-500">当前仓位</span><div class="mt-2 flex h-9 items-center rounded-lg bg-slate-100 px-3 font-semibold text-slate-600">{{ relocationTarget.location || '未设置仓位' }}</div></div>
            <label><span class="block text-xs font-semibold text-teal-700">目标仓位 *</span><CartonLocationPicker class="mt-2" v-model="relocationLocation" :locations="inventoryLocations" :factory-id="selectedFactoryId" :disabled="relocationBusy" @created="refreshLocations" /></label><label class="block space-y-2 text-sm sm:col-span-2">调仓数量<input v-model.number="relocationQuantity" :disabled="relocationBusy" type="number" min="0.0001" step="0.0001" :max="relocationTarget?.balance" aria-label="调仓数量" class="h-10 w-full rounded-lg border px-3"><span v-if="relocationQuantity > 0 && relocationQuantity <= relocationTarget.balance" class="block text-xs text-teal-700">调后本仓剩余 {{ formatNumber(relocationTarget.balance - relocationQuantity) }} {{ relocationTarget.unit }}；目标仓位增加 {{ formatNumber(relocationQuantity) }} {{ relocationTarget.unit }}。</span></label>
          </div>
          <label class="block"><span class="text-xs font-semibold text-slate-600">调仓备注 <span class="font-normal text-slate-400">（选填）</span></span><textarea v-model="relocationNote" :disabled="relocationBusy" aria-label="调仓备注" maxlength="2000" rows="2" placeholder="例如 库位整理，移至靠近出货区" class="mt-2 w-full resize-none rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500" /></label>
          <p class="text-xs leading-5 text-slate-500">来源仓位扣减、目标仓位增加；不计入入库或领用数量。历史收发保留原仓位，调仓详情可在订单流水和操作日志中查看。</p>
          <p v-if="relocationFeedback" role="alert" class="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">{{ relocationFeedback }}</p>
          <div class="flex justify-end gap-3 border-t border-slate-100 pt-4"><DialogClose :disabled="relocationBusy" class="h-10 rounded-lg border border-slate-200 px-4 text-sm font-semibold text-slate-600 disabled:opacity-40">取消</DialogClose><button type="submit" :disabled="!apiConnected || relocationBusy || !authStore.can('carton_procurement:inventory_write')" class="h-10 rounded-lg bg-teal-700 px-5 text-sm font-bold text-white hover:bg-teal-800 disabled:opacity-40">{{ relocationBusy ? '正在调仓…' : '确认调仓' }}</button></div>
        </form>
      </DialogContent>
    </DialogRoot>

    <DialogRoot :open="showInventoryOperation" @update:open="setInventoryDialogOpen">
      <DialogOverlay class="fixed inset-0 z-[70] bg-slate-950/40 backdrop-blur-sm" />
      <DialogContent class="fixed left-1/2 top-1/2 z-[71] max-h-[90vh] w-[calc(100%-2rem)] max-w-5xl -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-2xl bg-white p-4 sm:p-6 shadow-2xl" @interact-outside.prevent @close-auto-focus="restoreInventoryFocus">

        <form class="space-y-5" @submit.prevent="inventoryBulkMode ? submitBulkInventoryOutbound() : submitInventoryOperation()">
          <div class="flex items-start justify-between gap-4 border-b border-slate-200 pb-4">
            <div>
              <DialogTitle class="text-lg font-bold text-slate-950">{{ inventoryBulkMode ? '批量出库' : '登记出库' }}</DialogTitle>
              <DialogDescription class="mt-1 text-sm text-slate-500">{{ inventoryBulkMode ? '逐条填写本次出库数量，核对出库后结存，再确认提交。' : '核对库存、数量和来源单据后确认；每次操作都会保留流水。' }}</DialogDescription>
            </div>
            <DialogClose :disabled="inventoryOperationBusy" aria-label="关闭库存作业" class="rounded-lg p-1 text-slate-500 hover:bg-slate-100 disabled:opacity-40"><X class="size-5" /></DialogClose>
          </div>
          <div v-if="inventoryBulkMode" class="mt-4 max-h-[45vh] overflow-auto rounded-lg border border-slate-200">
            <table class="w-full min-w-[760px] text-left text-xs">
              <thead class="sticky top-0 bg-slate-50 text-slate-500"><tr><th class="px-3 py-3">客户 / 合同</th><th class="px-3 py-3">货号 / 纸品</th><th class="px-3 py-3">仓位</th><th class="px-3 py-3 text-right">当前结存</th><th class="px-3 py-3 text-right">本次出库 *</th><th class="px-3 py-3 text-right">出库后结存</th><th class="px-3 py-3 text-right">预估成本金额</th></tr></thead>
              <tbody class="divide-y divide-slate-100"><tr v-for="row in selectedInventoryBalances" :key="row.id">
                <td class="px-3 py-3"><div class="font-semibold">{{ row.customer }}</div><div class="mt-1 font-mono text-slate-500">{{ row.poNumber || '无合同' }}</div></td>
                <td class="px-3 py-3"><div class="font-mono font-semibold">{{ row.itemNo }}</div><div class="mt-1 text-slate-500">{{ row.packagingType }} · {{ row.paperQuality }} · {{ row.specification }}</div></td>
                <td class="px-3 py-3">{{ row.location || '未设置' }}</td><td class="whitespace-nowrap px-3 py-3 text-right">{{ formatNumber(row.balance) }} {{ row.unit }}</td>
                <td class="px-3 py-3"><input v-model="inventoryBulkQuantities[row.id]" :aria-label="`本次出库数量 ${row.id}`" type="number" step="0.0001" min="0.0001" :max="row.balance" :disabled="inventoryOperationBusy" required class="h-10 w-28 rounded-lg border border-teal-200 bg-white px-3 text-right font-semibold outline-none focus:border-teal-500"><select v-model="bulkWorkshops[row.id]" :aria-label="`本行领用车间 ${row.id}`" class="mt-1 h-8 w-full rounded border text-xs"><option :value="undefined">沿用统一车间</option><option v-for="place in workshops" :key="place.id" :value="place.id">{{ place.code }}</option></select></td>
                <td class="whitespace-nowrap px-3 py-3 text-right font-semibold text-teal-700">{{ bulkOutboundRemaining(row) }}</td><td class="whitespace-nowrap px-3 py-3 text-right">{{ moneyLabel(estimateMoney(row.money, inventoryBulkQuantities[row.id] || '')) }}</td>
              </tr></tbody>
            </table>
          </div>
          <div class="grid gap-4 sm:grid-cols-3">
            <label v-if="!inventoryBulkMode" class="min-w-0 space-y-1.5 sm:col-span-3"><span class="block text-xs font-bold text-slate-600">库存记录 *</span><select v-model="inventoryTargetId" aria-label="库存作业记录" class="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 outline-none focus:border-teal-500" @change="selectInventoryTarget(inventoryTargetId)"><option value="">请选择客户、合同、货号和纸品</option><option v-for="row in operableInventoryBalances" :key="row.id" :value="row.id">{{ row.customer }} · {{ row.poNumber || '无合同' }} · {{ customerPoForLine(row.orderLineId || '') ? '客户 PO ' + customerPoForLine(row.orderLineId || '') + ' · ' : '' }}{{ row.itemNo }} · {{ row.packagingType }} {{ row.paperQuality }} · {{ row.location || '待核仓位' }} · 结存 {{ row.balance }}</option></select></label>
            <label v-if="!inventoryBulkMode" class="min-w-0 space-y-1.5"><span class="block text-xs font-bold text-slate-600">{{ inventoryOperationType === 'OUTBOUND' ? '出库数量' : '调整数量' }} *</span><input v-model.number="inventoryOperationQuantity" aria-label="库存作业数量" type="number" step="0.0001" :min="inventoryOperationType === 'OUTBOUND' ? 0.0001 : undefined" :placeholder="inventoryOperationType === 'OUTBOUND' ? '大于 0' : '盘盈正数 / 盘亏负数'" class="h-10 w-full rounded-lg border border-slate-200 px-3 text-right font-semibold outline-none focus:border-teal-500"></label>
            <label class="min-w-0 space-y-1.5"><span class="block text-xs font-bold text-slate-600">来源单据号 *</span><input v-model="inventoryOperationDocumentNo" aria-label="库存作业单据号" placeholder="例如 OUT-260811-001" class="h-10 w-full rounded-lg border border-slate-200 px-3 font-mono outline-none focus:border-teal-500"></label>
            <label v-if="!inventoryBulkMode" class="min-w-0 space-y-1.5"><span class="block text-xs font-bold text-slate-600">仓位</span><input :value="selectedInventoryBalance?.location" aria-label="库存作业仓位" readonly class="h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3"></label>
          </div>
          <div v-if="inventoryOperationType === 'OUTBOUND'" class="rounded-lg border border-teal-100 bg-teal-50/50 px-4 py-3 text-sm" aria-label="出库预估成本">
            <div class="flex flex-wrap items-center gap-x-4 gap-y-1"><span class="font-semibold">预估成本金额</span><b v-for="amount in outboundMoneySummary.amounts" :key="amount" class="text-teal-800">{{ amount }}</b><span v-if="outboundMoneySummary.pending" class="text-amber-700">{{ inventoryBulkMode ? `${outboundMoneySummary.pending} 条暂无法计价` : moneyLabel(estimateMoney(selectedInventoryBalance?.money, inventoryOperationQuantity)) }}</span></div>
            <p class="mt-1 text-xs text-slate-500"><span v-if="!inventoryBulkMode && unitCostLabel(selectedInventoryBalance?.money)">单位成本 {{ unitCostLabel(selectedInventoryBalance?.money) }} / {{ selectedInventoryBalance?.unit }}；</span>按当前移动平均成本预估，实际以提交后流水为准。缺价可正常出库，金额待核价后计算。</p>
          </div>
          <div class="grid gap-4 sm:grid-cols-2">
            <label v-if="inventoryOperationType === 'OUTBOUND'" class="min-w-0 space-y-1.5"><span class="block text-xs font-bold text-slate-600">领用车间（非车间用途可不选）</span><select v-model="outboundWorkshop" aria-label="领用车间" class="h-10 w-full rounded-lg border px-3"><option value="">未指定／其他去向</option><option v-for="place in workshops" :key="place.id" :value="place.id">{{ place.code }}</option></select></label><label v-if="inventoryOperationType === 'OUTBOUND'" class="min-w-0 space-y-1.5"><span class="block text-xs font-bold text-slate-600">出库用途 *</span><select v-model="outboundKind" aria-label="出库用途" class="h-10 w-full rounded-lg border border-slate-200 px-3"><option v-for="kind in outboundKinds" :key="kind.id" :value="kind.id">{{ kind.label }}</option></select><span class="text-[10px] text-slate-500">调仓请使用调仓按钮；仅正常领用／发货计入领用状态。</span></label><label class="min-w-0 space-y-1.5 sm:col-span-2">
              <span class="block text-xs font-bold text-slate-600">{{ inventoryOperationType === 'OUTBOUND' ? '出库原因' : '调整原因' }} *</span>
              <select v-if="inventoryOperationType === 'OUTBOUND' && outboundKind !== 'OTHER'" v-model="inventoryOperationReason" aria-label="库存作业原因" class="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 outline-none focus:border-teal-500">
                <option v-for="reason in inventoryOutboundReasons" :key="reason" :value="reason">{{ reason }}</option>
              </select>
              <input v-else v-model="inventoryOperationReason" aria-label="库存作业原因" :placeholder="inventoryOperationType === 'OUTBOUND' ? '请说明具体出库用途' : '请说明库存差异及调整依据'" class="h-10 w-full rounded-lg border border-slate-200 px-3 outline-none focus:border-teal-500">
            </label>
            <div class="flex justify-end gap-3 border-t border-slate-200 pt-4 sm:col-span-2">
              <DialogClose :disabled="inventoryOperationBusy" class="h-10 rounded-lg border border-slate-200 px-5 text-sm text-slate-600">取消</DialogClose>
            <button type="submit" :disabled="!apiConnected || inventoryOperationBusy" class="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-teal-700 px-5 text-[12px] font-bold text-white disabled:cursor-not-allowed disabled:opacity-50"><CheckCircle2 class="size-4" />{{ inventoryOperationBusy ? '正在登记…' : inventoryBulkMode ? '确认批量出库' : inventoryOperationType === 'OUTBOUND' ? '确认出库' : '确认调整' }}</button>
            </div>

          </div>
          <div v-if="inventoryOperationFeedback" role="status" class="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-[11px] font-semibold text-slate-700">{{ inventoryOperationFeedback }}</div>
        </form>
      </DialogContent>
    </DialogRoot>

    <DialogRoot v-model:open="showReceiptDialog">
      <DialogOverlay class="fixed inset-0 z-[70] bg-slate-950/45" />
      <DialogContent class="fixed left-1/2 top-1/2 z-[71] flex max-h-[92vh] w-[calc(100%-2rem)] max-w-[1500px] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl bg-white shadow-2xl" @interact-outside.prevent @close-auto-focus="restoreReceiptFocus">
        <div class="flex shrink-0 items-start justify-between gap-4 border-b border-slate-200 px-6 py-4">
          <div><DialogTitle class="text-lg font-bold text-slate-950">{{ receiptEntryMode === 'MANUAL' ? '人工录入订单收料' : '送货单收料反馈' }}</DialogTitle><DialogDescription class="mt-1 text-sm text-slate-500">核对送货信息、单价、数量及仓位，点击确认入库后立即更新库存。</DialogDescription></div>
          <DialogClose as-child><button type="button" aria-label="关闭收料录入" class="rounded-lg p-2 text-slate-500 hover:bg-slate-100"><X class="size-5" /></button></DialogClose>
        </div>
        <div class="min-h-0 space-y-4 overflow-y-auto p-4 sm:p-6">
          <div class="grid gap-4 rounded-xl border border-slate-200 bg-slate-50 p-4 sm:grid-cols-3">
            <label class="space-y-1.5"><span class="text-sm font-bold text-slate-600">送货单号 *</span><input ref="manualDeliveryNoteInput" v-model="receiptDeliveryNoteNo" :disabled="Boolean(currentReceipt) || savingReceipt" aria-label="人工送货单号" :aria-invalid="receiptFeedbackTone === 'error' && receiptFeedbackMessage.includes('送货单号')" placeholder="例如 DN26081001" class="h-11 w-full rounded-lg border bg-white px-3 font-mono outline-none focus:border-blue-500" :class="receiptFeedbackTone === 'error' && receiptFeedbackMessage.includes('送货单号') ? 'border-red-400 ring-2 ring-red-100' : 'border-slate-200'" @input="receiptFeedbackMessage = ''"></label>
            <label class="space-y-1.5"><span class="text-sm font-bold text-slate-600">送货日期 *</span><input ref="manualDeliveryDateInput" v-model="receiptDeliveryDate" :disabled="Boolean(currentReceipt) || savingReceipt" aria-label="人工送货日期" type="date" class="h-11 w-full rounded-lg border border-slate-200 bg-white px-3 outline-none focus:border-blue-500"></label>
            <label class="space-y-1.5"><span class="text-sm font-bold text-slate-600">实际验收日期 *</span><input ref="manualAcceptanceDateInput" v-model="receiptAcceptanceDate" :disabled="Boolean(currentReceipt) || savingReceipt" aria-label="实际验收日期" type="date" class="h-11 w-full rounded-lg border border-slate-200 bg-white px-3 outline-none focus:border-blue-500"><span class="block text-xs text-slate-500">{{ currentReceipt && !receiptAcceptanceDate ? '历史未记录，须核实实际验收日期。' : '按实际验收日期归属供应商对账月份，与下单、送货及记账时间分别记录。' }}</span></label>
          </div>
          <div class="flex flex-wrap gap-x-6 gap-y-2 text-sm text-slate-600">
            <p v-if="receiptCorrectionNote" class="w-full text-amber-700">{{ receiptCorrectionNote }} <span v-if="!currentReceipt">本次使用带“更正”后缀的新登记号，请核对后确认入库。</span></p>
            <span v-if="receiptEntryMode === 'MANUAL'">已选订单 <strong>{{ selectedManualReceiptOrders.length }} 张</strong></span><span>本次明细 <strong>{{ selectedReceiptLines.length }} 行</strong></span><span>有效收料<strong class="text-teal-700">{{ formatNumber(receiptTotals.effective) }}</strong></span>
            <span v-if="receiptEntryMode === 'MANUAL' && selectedReceiptLines.length && !currentReceipt" :class="manualReceiptWillCompleteOrder ? 'text-emerald-700' : 'text-amber-700'">{{ manualReceiptWillCompleteOrder ? '全部收齐，确认后自动完成' : '分批收料，未收齐的订单继续待收' }}</span>
          </div>
        <div class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div class="border-b border-slate-200 px-4 py-3">
            <h2 class="font-bold text-slate-950">收料反馈明细</h2>
            <p class="mt-1 text-sm text-teal-700">请按送货单核对本次入库单价，默认带出订单已有价格；有效入库明细必填，且必须大于 0。</p>
            <p class="mt-1 text-sm text-slate-500">有效收料 = 实收 − 破损 − 拒收 − 其他不可用；非正式/打板明细不补建正式订单，人工核对后点击确认入库，即生成库存流水并进入月结。</p>
          </div>
          <div class="overflow-x-auto">
            <table data-testid="receipt-review-table" class="min-w-[1440px] w-full text-left">
              <thead class="bg-slate-50 text-xs font-bold text-slate-500">
                <tr><th v-if="manualReceiptDialogSelection" class="px-3 py-3 whitespace-nowrap">本次收料</th><th class="px-4 py-3">合同 / 货号</th><th class="px-4 py-3">纸品类型 / 纸质 / 规格</th><th class="px-4 py-3 text-right">送货数量</th><th class="px-4 py-3 text-center">单价 / 单位 *</th><th class="px-3 py-3 text-right">实收</th><th class="px-3 py-3 text-right">破损</th><th class="px-3 py-3 text-right">拒收</th><th class="px-3 py-3 text-right">其他不可用</th><th class="px-4 py-3 text-right">有效收料</th><th class="px-4 py-3">仓位</th><th class="px-4 py-3">来源</th></tr>
              </thead>
              <tbody class="divide-y divide-slate-100">
                <tr v-for="row in receiptDialogRows" :key="row.id" class="[&>td]:align-top [&>td]:py-3">
                  <td v-if="manualReceiptDialogSelection" class="px-3 py-3"><input type="checkbox" :aria-label="`选择纸品 ${row.orderLineId}`" :checked="row.selectedForReceipt !== false" :disabled="savingReceipt" class="size-4 accent-teal-600" @change="selectReceiptPaper(row.id, ($event.target as HTMLInputElement).checked)"></td>
                  <td class="px-4 py-3">
                    <div v-if="row.sourceType === 'AD_HOC'" class="w-52 space-y-1.5">
                      <span class="inline-flex rounded-full bg-amber-50 px-2 py-0.5 text-[9px] font-bold text-amber-800 ring-1 ring-inset ring-amber-200">非正式 / 打板收料</span>
                      <select v-model="row.customerCode" :aria-label="`${row.id} 客户`" :disabled="Boolean(currentReceipt) || savingReceipt || row.selectedForReceipt === false" class="h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-xs outline-none focus:border-amber-500 disabled:bg-slate-50"><option value="">请选择客户 *</option><option v-for="customer in activeCustomers" :key="customer.id" :value="customer.customer_code">{{ customer.customer_name }}</option></select>
                      <input v-model="row.contractNo" :aria-label="`${row.id} 合同或来源号`" :disabled="Boolean(currentReceipt) || savingReceipt || row.selectedForReceipt === false" placeholder="合同/打板来源号（可空）" class="h-8 w-full rounded-md border border-slate-200 px-2 font-mono text-xs outline-none focus:border-amber-500 disabled:bg-slate-50">
                      <input v-model="row.itemNo" :aria-label="`${row.id} 货号`" :disabled="Boolean(currentReceipt) || savingReceipt || row.selectedForReceipt === false" placeholder="货号 *" class="h-8 w-full rounded-md border border-slate-200 px-2 font-mono text-xs outline-none focus:border-amber-500 disabled:bg-slate-50">
                    </div>
                    <div v-else class="space-y-1">
                      <div class="break-all font-mono text-sm font-semibold">{{ row.contractNo || '—' }}</div>
                      <div class="text-xs text-slate-500">{{ orderRecords.find(order => order.lines.some(line => line.id === row.orderLineId))?.customer_name }} · {{ row.orderNo }}</div>
                      <div v-if="customerPoForLine(row.orderLineId)" class="break-all text-xs text-teal-700">客户 PO {{ customerPoForLine(row.orderLineId) }}</div>
                      <div class="break-all font-mono text-xs text-slate-500">货号 {{ row.itemNo || '—' }}</div>
                    </div>
                  </td>
                  <td class="px-4 py-3">
                    <div v-if="row.sourceType === 'AD_HOC'" class="w-48 space-y-1.5">
                      <input v-model="row.packagingType" :aria-label="`${row.id} 纸品类型`" :disabled="Boolean(currentReceipt) || savingReceipt || row.selectedForReceipt === false" placeholder="纸品类型 *" class="h-8 w-full rounded-md border border-slate-200 px-2 text-xs outline-none focus:border-amber-500 disabled:bg-slate-50">
                      <input v-model="row.paperQuality" :aria-label="`${row.id} 纸质`" :disabled="Boolean(currentReceipt) || savingReceipt || row.selectedForReceipt === false" placeholder="纸质 *" class="h-8 w-full rounded-md border border-slate-200 px-2 text-xs outline-none focus:border-amber-500 disabled:bg-slate-50">
                      <input v-model="row.specification" :aria-label="`${row.id} 规格`" :disabled="Boolean(currentReceipt) || savingReceipt || row.selectedForReceipt === false" placeholder="规格 *" class="h-8 w-full rounded-md border border-slate-200 px-2 text-xs outline-none focus:border-amber-500 disabled:bg-slate-50">
                    </div>
                    <div v-else-if="orderRecords.some(order => order.lines.some(line => line.id === row.orderLineId && (!line.paper_quality || !line.specification)))" class="w-48 space-y-1.5">
                      <div class="font-semibold">{{ row.packagingType }}</div>
                      <input v-model="row.paperQuality" :aria-label="`${row.id} 纸质`" :disabled="Boolean(currentReceipt) || savingReceipt || row.selectedForReceipt === false || orderRecords.some(order => order.lines.some(line => line.id === row.orderLineId && Boolean(line.paper_quality)))" placeholder="补填纸质 *" class="h-8 w-full rounded-md border border-amber-300 px-2 text-xs">
                      <input v-model="row.specification" :aria-label="`${row.id} 规格`" :disabled="Boolean(currentReceipt) || savingReceipt || row.selectedForReceipt === false || orderRecords.some(order => order.lines.some(line => line.id === row.orderLineId && Boolean(line.specification)))" placeholder="补填规格 *" class="h-8 w-full rounded-md border border-amber-300 px-2 text-xs">
                      <p class="text-[10px] text-amber-700">历史资料待补齐，入库后保留记录</p>
                    </div>
                    <template v-else><div class="font-semibold">{{ row.description }}</div><div class="mt-0.5 text-xs text-slate-500">{{ row.specification }}</div></template>
                  </td>
                  <td class="px-4 py-2 text-right"><input v-if="receiptEntryMode === 'MANUAL' || row.sourceType === 'AD_HOC'" v-model.number="row.deliveryQuantity" :aria-label="`${row.id} 送货数量`" :disabled="Boolean(currentReceipt) || savingReceipt || row.selectedForReceipt === false" type="number" min="0" :max="row.sourceType === 'FORMAL_ORDER' && receiptEntryMode === 'MANUAL' ? row.remainingQuantity : undefined" class="ml-auto block h-8 w-24 rounded-md border border-slate-200 px-2 text-right font-semibold outline-none focus:border-blue-500 disabled:bg-slate-50"><div v-else class="font-semibold tabular-nums">{{ row.deliveryQuantity }}</div><div v-if="receiptEntryMode === 'MANUAL' && row.sourceType === 'FORMAL_ORDER'" class="mt-0.5 text-[9px] text-slate-400">待收 {{ formatNumber(row.remainingQuantity) }}</div></td>
                  <td class="px-4 py-2">
                    <div class="mx-auto w-28 text-center">
                      <div v-if="freeReplacement(row)" class="text-xs font-semibold text-teal-700">供应商责任 · 免费补货<br>应付 0，不计月结<span class="mt-1 block font-normal text-slate-500">库存成本沿用原补单出库成本</span></div><input v-else v-model.number="row.unitPrice" :aria-label="`${row.id} 单价`" :disabled="Boolean(currentReceipt) || savingReceipt || row.selectedForReceipt === false" type="number" min="0.000001" step="0.000001" :aria-required="row.selectedForReceipt !== false && receiptLineEffectiveQuantity(row) > 0" :aria-invalid="row.selectedForReceipt !== false && receiptLineEffectiveQuantity(row) > 0 && !(Number(row.unitPrice) > 0)" placeholder="必填：送货单单价" class="block h-8 w-full rounded-md border border-slate-200 px-2 text-right text-xs outline-none focus:border-amber-500 disabled:bg-slate-50">
                      <div v-if="row.sourceType === 'AD_HOC'" class="mt-1 flex justify-center gap-1">
                        <select v-model="row.currency" :aria-label="`${row.id} 币种`" :disabled="Boolean(currentReceipt) || savingReceipt || row.selectedForReceipt === false" class="h-7 w-16 rounded border border-slate-200 bg-white px-1 text-[9px] disabled:bg-slate-50"><option value="CNY">CNY</option><option value="HKD">HKD</option><option value="USD">USD</option></select>
                        <input v-model="row.unit" :aria-label="`${row.id} 单位`" :disabled="Boolean(currentReceipt) || savingReceipt || row.selectedForReceipt === false" placeholder="单位" class="h-7 w-12 rounded border border-slate-200 px-1 text-[9px] disabled:bg-slate-50">
                      </div>
                      <div v-else class="mt-1 text-xs text-slate-500">{{ row.currency }} / {{ row.unit }}</div>
                      <div v-if="!freeReplacement(row) && row.selectedForReceipt !== false && receiptLineEffectiveQuantity(row) > 0 && !(Number(row.unitPrice) > 0)" class="mt-1 text-xs text-red-600">{{ currentReceipt?.status === 'POSTED' ? '历史入库待核价' : '请填写大于 0 的单价' }}</div>
                    </div>
                  </td>
                  <td class="px-3 py-2"><input :value="row.receivedQuantity || ''" @input="updateReceiptActual(row, Number(($event.target as HTMLInputElement).value))" :aria-label="`${row.id} 实收`" :max="receiptEntryMode === 'MANUAL' ? row.remainingQuantity : undefined" step="0.0001" :disabled="Boolean(currentReceipt) || savingReceipt || row.selectedForReceipt === false" type="number" min="0" class="ml-auto block h-8 w-20 rounded-md border border-slate-200 px-2 text-right font-semibold outline-none focus:border-teal-500 disabled:bg-slate-50"></td>
                  <td class="px-3 py-2"><input v-model.number="row.damagedQuantity" :aria-label="`${row.id} 破损`" :disabled="Boolean(currentReceipt) || savingReceipt || row.selectedForReceipt === false" type="number" min="0" class="ml-auto block h-8 w-20 rounded-md border border-slate-200 px-2 text-right outline-none focus:border-teal-500 disabled:bg-slate-50"></td>
                  <td class="px-3 py-2"><input v-model.number="row.rejectedQuantity" :aria-label="`${row.id} 拒收`" :disabled="Boolean(currentReceipt) || savingReceipt || row.selectedForReceipt === false" type="number" min="0" class="ml-auto block h-8 w-20 rounded-md border border-slate-200 px-2 text-right outline-none focus:border-teal-500 disabled:bg-slate-50"></td>
                  <td class="px-3 py-2"><input v-model.number="row.unusableQuantity" :aria-label="`${row.id} 其他不可用`" :disabled="Boolean(currentReceipt) || savingReceipt || row.selectedForReceipt === false" type="number" min="0" class="ml-auto block h-8 w-20 rounded-md border border-slate-200 px-2 text-right outline-none focus:border-teal-500 disabled:bg-slate-50"></td>
                  <td class="px-4 py-3 text-right text-[14px] font-bold text-teal-700 tabular-nums">{{ row.selectedForReceipt === false ? '—' : receiptLineEffectiveQuantity(row) }}</td>
                  <td class="px-4 py-2"><CartonReceiptAllocations v-model="row.allocations" :effective="receiptLineEffectiveQuantity(row)" :locations="inventoryLocations" :factory-id="selectedFactoryId" :disabled="Boolean(currentReceipt) || savingReceipt || row.selectedForReceipt === false" @created="refreshLocations" /></td>
                  <td class="px-4 py-3"><p v-if="receiptReplacementNeedsReview(row)" class="mb-2 text-xs text-red-600">历史补单收料未关联，请核对并冲销重录。</p><div v-if="receiptReplacementOptions(row).length && !currentReceipt" class="mb-2 min-w-40"><select v-model="row.replenishmentIssueId" :aria-label="`${row.id} 收料来源`" :disabled="savingReceipt || row.selectedForReceipt === false" class="h-8 w-full rounded border px-1 text-xs" @change="changeReceiptReplacement(row)"><option :value="undefined">普通采购收料</option><option v-for="option in receiptReplacementOptions(row)" :key="option.replenishment_issue_id" :value="option.replenishment_issue_id">{{ option.document_no }} · {{ option.responsibility === 'SUPPLIER' ? '供应商责任／免费' : '我方责任／计费' }} · 待补 {{ option.remaining_quantity }}</option></select><p class="mt-1 text-xs text-slate-500">普通货与不同补单请分开登记。</p></div><p v-if="row.replacementDocumentNo" class="mb-1 text-xs text-teal-700">{{ row.replacementDocumentNo }} · {{ freeReplacement(row) ? '免费补货' : '我方责任／计入月结' }}</p><span class="inline-flex whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-bold ring-1 ring-inset" :class="row.sourceType === 'AD_HOC' ? 'bg-amber-50 text-amber-800 ring-amber-200' : 'bg-violet-50 text-violet-700 ring-violet-200'">{{ row.sourceLabel }}</span><button v-if="row.sourceType === 'AD_HOC' && !currentReceipt" type="button" class="mt-2 block text-[9px] font-bold text-red-600" @click="removeAdHocReceiptLine(row.id)">移除此行</button></td>
                </tr>
                <tr v-if="receiptDialogRows.length === 0"><td :colspan="manualReceiptDialogSelection ? 12 : 11" class="px-4 py-12 text-center text-slate-400">{{ receiptEntryMode === 'MANUAL' ? '所选订单暂无待收纸品' : '没有找到匹配的送货明细' }}</td></tr>
              </tbody>
              <tfoot class="border-t border-slate-200 bg-slate-50 font-bold">
                <tr><td :colspan="manualReceiptDialogSelection ? 3 : 2" class="px-4 py-3">本次合计</td><td class="px-4 py-3 text-right">{{ receiptTotals.delivered }}</td><td class="px-4 py-3 text-right">—</td><td class="px-3 py-3 text-right">{{ receiptTotals.received }}</td><td colspan="3" class="px-3 py-3 text-right text-red-600">不可用 {{ receiptTotals.unusable }}</td><td class="px-4 py-3 text-right text-teal-700">{{ receiptTotals.effective }}</td><td colspan="2" class="px-4 py-3">—</td></tr>
              </tfoot>
            </table>
          </div>
          <div class="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 px-4 py-3">
            <div class="min-w-0 flex-1">
              <p class="text-sm text-slate-500">核对无误后点击确认入库，按有效收料数量直接入库；填错可在历史台账冲销。</p>
              <div
                v-if="receiptFeedbackMessage"
                data-testid="receipt-save-feedback"
                :role="receiptFeedbackTone === 'error' ? 'alert' : 'status'"
                aria-live="polite"
                class="mt-2 flex items-start gap-2 rounded-lg border px-3 py-2 text-sm font-semibold leading-5"
                :class="receiptFeedbackTone === 'error' ? 'border-red-200 bg-red-50 text-red-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700'"
              >
                <AlertTriangle v-if="receiptFeedbackTone === 'error'" class="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
                <CheckCircle2 v-else class="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
                <span>{{ receiptFeedbackMessage }}</span>
              </div>
            </div>
            <div class="flex flex-wrap gap-2">
              <button v-if="!currentReceipt" type="button" :disabled="selectedReceiptLines.length === 0 || savingReceipt" class="inline-flex h-9 items-center gap-2 rounded-lg border border-teal-300 bg-white px-4 text-[12px] font-bold text-teal-700 disabled:cursor-not-allowed disabled:opacity-50" @click="saveReceiptFeedback">
                <CheckCircle2 class="size-4" />{{ savingReceipt ? '正在入库…' : '确认入库' }}
              </button>
              <button v-else type="button" :disabled="currentReceipt.status !== 'PENDING_CONFIRMATION' || confirmingReceipt" class="inline-flex h-9 items-center gap-2 rounded-lg bg-teal-700 px-4 text-[12px] font-bold text-white disabled:cursor-not-allowed disabled:opacity-50" @click="confirmCurrentReceipt">
                <ShieldCheck class="size-4" />{{ receiptConfirmButtonLabel }}
              </button>
            </div>
          </div>
        </div>


        </div>
        <div class="flex shrink-0 justify-end border-t border-slate-200 px-6 py-3"><DialogClose as-child><button type="button" class="h-9 rounded-lg border border-slate-200 px-4 text-sm font-semibold text-slate-600">{{ receiptEntryMode === 'MANUAL' ? '返回待收订单' : '返回导入结果' }}</button></DialogClose></div>
      </DialogContent>
    </DialogRoot>

    <div v-if="showCustomerModal" class="fixed inset-0 z-[65] flex items-center justify-center bg-slate-950/45 p-4" @keydown.esc.stop="!savingCustomer && (showCustomerModal = false)">
      <form role="dialog" aria-modal="true" aria-label="编辑客户资料" class="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl bg-white shadow-xl" @submit.prevent="saveCustomer">
        <div class="flex items-center justify-between border-b p-4"><div><h2 class="font-bold">{{ editingCustomerId ? '修改客户' : '新增客户' }}</h2><p class="mt-1 text-xs text-slate-500">仅维护 {{ activeFactory.shortName }} 客户；停用保留历史订单。</p></div><button type="button" :disabled="savingCustomer" aria-label="关闭客户资料维护" class="rounded-lg p-2 text-slate-400 hover:bg-slate-100" @click="showCustomerModal = false"><X class="size-4" /></button></div>
        <div class="min-h-0 space-y-3 overflow-y-auto p-5 text-xs"><div class="grid gap-3 sm:grid-cols-2">
          <label>客户名称 *<input v-model="customerForm.customer_name" required aria-label="客户名称" placeholder="客户正式名称" class="mt-1 h-9 w-full rounded-lg border px-3"></label>
          <label>状态<select v-model="customerForm.status" aria-label="客户状态" class="mt-1 h-9 w-full rounded-lg border px-3"><option value="ACTIVE">启用</option><option value="INACTIVE">停用</option></select></label>
          <label>联系人<input v-model="customerForm.contact_name" aria-label="客户联系人" class="mt-1 h-9 w-full rounded-lg border px-3"></label>
          <label>联系电话<input v-model="customerForm.contact_phone" aria-label="客户联系电话" class="mt-1 h-9 w-full rounded-lg border px-3"></label>
          <label>国家 / 地区<input v-model="customerForm.country_region" aria-label="客户国家地区" placeholder="例如 德国" class="mt-1 h-9 w-full rounded-lg border px-3"></label>
          <label>备注<textarea v-model="customerForm.note" aria-label="客户备注" rows="1" class="mt-1 min-h-9 w-full rounded-lg border px-3 py-2" /></label>
        </div><p class="text-slate-500">编号格式和默认交期可在客户列表的“规则”中设置。</p><p v-if="customerEditError" role="alert" class="text-red-700">{{ customerEditError }}</p></div>
        <div class="flex justify-end border-t p-4"><button type="submit" :disabled="savingCustomer" class="h-9 rounded-lg bg-teal-700 px-5 text-xs font-bold text-white disabled:opacity-60">{{ savingCustomer ? '正在保存…' : editingCustomerId ? '保存客户修改' : '新增客户' }}</button></div>
      </form>
    </div>

    <div v-if="orderDetailRow" data-testid="order-detail-overlay" class="fixed inset-0 z-[62] flex items-center justify-center p-4 transition-colors" :class="orderDetailPinned ? 'pointer-events-auto bg-slate-950/45' : 'pointer-events-none bg-slate-950/25'" @click.self="closeOrderDetails">
      <div class="max-h-[88vh] w-full max-w-5xl overflow-y-auto rounded-2xl bg-white shadow-2xl" role="dialog" :aria-modal="orderDetailPinned ? 'true' : undefined" aria-labelledby="order-detail-title">
        <div class="flex items-start justify-between border-b border-slate-200 px-5 py-4">
          <div>
            <p v-if="customerPoForOrder(orderDetailRow.id)" class="text-xs text-teal-700">客户 PO {{ customerPoForOrder(orderDetailRow.id) }}</p>
            <h2 id="order-detail-title" class="text-[18px] font-bold text-slate-950">订单明细 — {{ orderDetailRow.contractNo }} / {{ orderDetailRow.itemNo }}</h2>
            <p class="mt-1 text-[11px] text-slate-500">按合同查看纸品需求、实际入库和剩余待入库数量。<span class="ml-2 font-semibold text-teal-700">{{ orderDetailPinned ? '已固定显示' : '悬停预览 · 单击明细可固定' }}</span></p>
          </div>
          <button type="button" aria-label="关闭订单明细" class="rounded-lg p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700" @click="closeOrderDetails"><X class="size-4" /></button>
        </div>

        <div class="space-y-4 p-5">
          <section class="grid gap-x-5 gap-y-3 rounded-xl border border-emerald-200 bg-emerald-50/60 px-4 py-3 text-[12px] sm:grid-cols-2 lg:grid-cols-4">
            <div><span class="text-slate-500">客户</span><b class="ml-2 text-slate-900">{{ orderDetailRow.customer }}</b></div>
            <div><span class="text-slate-500">产品名称</span><b class="ml-2 text-slate-900">{{ orderDetailRecord?.product_name || '未记录' }}</b></div>
            <div><span class="text-slate-500">产品订单数量</span><b class="ml-2 tabular-nums text-slate-900">{{ orderDetailRow.orderQuantity == null ? '未记录' : formatNumber(orderDetailRow.orderQuantity) }}</b></div>
            <div><span class="text-slate-500">状态</span><span class="ml-2 inline-flex rounded-full px-2 py-0.5 text-[10px] font-bold ring-1 ring-inset" :class="toneClass(orderDetailRow.tone)">{{ orderDetailRow.status }}</span></div>
            <div><span class="text-slate-500">下单日期</span><b class="ml-2 tabular-nums text-slate-900" :title="orderDetailRow.orderDate">{{ formatMonthDay(orderDetailRow.orderDate) }}</b></div>
            <div><span class="text-slate-500">客户要求交期</span><b class="ml-2 tabular-nums text-slate-900" :title="orderDetailRow.customerDueDate || undefined">{{ formatMonthDay(orderDetailRow.customerDueDate) || '未记录' }}</b></div>
            <div><span class="text-slate-500">计划交期</span><b class="ml-2 tabular-nums text-slate-900" :title="orderDetailRow.dueDate">{{ formatMonthDay(orderDetailRow.dueDate) }}</b></div>
            <div class="min-w-0"><span class="text-slate-500">备注</span><b class="ml-2 break-words text-slate-900">{{ orderDetailRow.note || '—' }}</b></div>
          </section>

          <section class="overflow-hidden rounded-xl border border-slate-200">
            <div class="overflow-x-auto">
              <table class="w-full min-w-[900px] table-fixed text-left">
                <colgroup><col class="w-[12%]"><col class="w-[14%]"><col class="w-[20%]"><col class="w-[11%]"><col class="w-[12%]"><col class="w-[10%]"><col class="w-[10%]"><col class="w-[11%]"></colgroup>
                <thead class="bg-slate-100 text-[11px] font-bold text-slate-700">
                  <tr><th class="px-4 py-3">纸品类型</th><th class="px-4 py-3">纸质</th><th class="px-4 py-3">规格</th><th class="px-4 py-3 text-right">每箱个数</th><th class="px-4 py-3 text-right">纸品数量</th><th class="px-4 py-3 text-right">已入库</th><th class="px-4 py-3 text-right">待入库</th><th class="px-4 py-3">入库进度</th></tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                  <tr v-for="material in orderDetailRow.materials" :key="material.id" class="text-[12px] text-slate-700">
                    <td class="truncate px-4 py-3 font-semibold text-slate-950">{{ material.packagingType }}</td>
                    <td class="truncate px-4 py-3 font-semibold text-slate-900">{{ material.paperQuality }}</td>
                    <td class="truncate px-4 py-3" :title="material.specification">{{ material.specification }}</td>
                    <td class="px-4 py-3 text-right font-semibold tabular-nums">{{ material.unitsPerCarton == null ? '未记录' : formatUnitsPerCarton(material.unitsPerCarton) }}</td>
                    <td class="px-4 py-3 text-right font-semibold tabular-nums">{{ formatNumber(orderDetailRequiredQuantity(material)) }} {{ material.unit }}</td>
                    <td class="px-4 py-3 text-right font-semibold tabular-nums text-emerald-700">{{ formatNumber(orderDetailReceivedQuantity(material)) }} {{ material.unit }}</td>
                    <td class="px-4 py-3 text-right font-semibold tabular-nums" :class="orderDetailRemainingQuantity(material) > 0 ? 'text-amber-700' : 'text-slate-500'">{{ formatNumber(orderDetailRemainingQuantity(material)) }} {{ material.unit }}</td>
                    <td class="px-4 py-3">
                      <div class="flex items-center gap-2">
                        <span class="h-2 flex-1 overflow-hidden rounded-full bg-slate-200"><span class="block h-full rounded-full bg-emerald-600" :style="{ width: `${orderDetailProgress(material)}%` }"></span></span>
                        <span class="w-8 text-right font-semibold tabular-nums text-slate-600">{{ orderDetailProgress(material) }}%</span>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-[11px] leading-5 text-slate-600">
            共 <b class="text-slate-900">{{ orderDetailRow.materials.length }}</b> 项纸品；需求 <b class="text-slate-900">{{ orderDetailQuantitySummary.required }}</b>，已入库 <b class="text-emerald-700">{{ orderDetailQuantitySummary.received }}</b>，待入库 <b class="text-amber-700">{{ orderDetailQuantitySummary.remaining }}</b>。入库数量来自正式收料记录，追加或减单只改变需求量，不改写既有入库流水。
          </div>
        </div>

        <div class="flex justify-end gap-2 border-t border-slate-200 bg-slate-50 px-5 py-4">
          <button type="button" class="h-9 rounded-lg border border-slate-200 bg-white px-4 text-[12px] font-bold text-slate-600" @click="closeOrderDetails">关闭</button>
          <button type="button" :disabled="!apiConnected" class="h-9 rounded-lg bg-teal-700 px-4 text-[12px] font-bold text-white disabled:cursor-not-allowed disabled:bg-slate-300" @click="openOrderDetailPurchaseOrder">查看采购单</button>
        </div>
      </div>
    </div>

    <div v-if="showOrderModal" data-testid="order-form-overlay" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4">
      <form class="max-h-[92vh] w-full max-w-5xl overflow-y-auto rounded-2xl bg-white shadow-2xl" @submit.prevent="createLocalOrder">
        <div class="flex items-start justify-between border-b border-slate-200 px-5 py-4">
          <div><h2 class="text-[16px] font-bold text-slate-950">{{ editingOrderNo ? `修改纸箱合同订单 ${editingOrderNo}` : '新建纸箱合同订单' }}</h2><p class="mt-1 text-[11px] text-slate-500">{{ editingOrderNo ? '待下单且尚未确认锁定的订单可以修订，保存后生成新版本并保留原因。' : '先创建为“待下单”订单；复核无误后再从台账确认订单并锁定。' }}</p></div>
          <button type="button" :aria-label="editingOrderNo ? '关闭修改订单' : '关闭新建订单'" class="rounded-lg p-2 text-slate-400 hover:bg-slate-100" @click="showOrderModal = false"><X class="size-4" /></button>
        </div>
        <div class="space-y-5 p-5">
          <div v-if="editingOrderStructureLocked" class="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] font-semibold text-amber-800">该订单已确认锁定或发生正式收料，不能再保存修改。</div>
          <section>
            <div class="mb-3 text-[11px] font-bold text-slate-900">合同主信息</div>
            <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              <CartonCustomerPicker v-model="orderForm.customerCode" :customers="customerRecords" :can-create="masterLoaded && masterWorkspace.can_manage" :disabled="editingOrderStructureLocked" @create="createOrderCustomer" />
              <label class="space-y-1.5"><span class="text-[11px] font-bold text-slate-600">纸箱供应商</span><input value="河源东康纸品有限公司（系统固定）" aria-label="纸箱供应商" disabled class="h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-slate-500"></label>
              <label class="block space-y-1.5"><span class="text-[11px] font-bold text-slate-600">客户 PO（选填）</span><input v-model="orderForm.customerPo" aria-label="客户 PO" maxlength="128" :disabled="editingOrderStructureLocked" placeholder="同合同同货号时，用客户 PO 区分" class="h-10 w-full rounded-lg border border-slate-200 px-3 outline-none focus:border-teal-500 disabled:bg-slate-50"><CartonNumberRuleHint v-if="masterLoaded && orderForm.customerCode && orderForm.customerPo" :rule="orderMasterRules.customer_po_rule" :value="orderForm.customerPo" label="客户 PO" /><span v-else class="block text-[9px] text-slate-400">选填；格式规则可在基础资料按客户设置</span></label>
              <CartonMasterLookup :records="masterLoaded ? masterWorkspace.records : []" :customer="orderForm.customerCode" :query="orderForm.contractNo" field="contract" :disabled="editingOrderStructureLocked || !masterLoaded" @select="orderForm.contractNo = $event.code"><label class="space-y-1.5"><span class="text-[11px] font-bold text-slate-600">合同号 *</span><input v-model="orderForm.contractNo" aria-label="合同号" :disabled="editingOrderStructureLocked" placeholder="例如 SC700145365" class="h-10 w-full rounded-lg border border-slate-200 px-3 outline-none focus:border-teal-500 disabled:bg-slate-50 disabled:text-slate-500"></label><template #hint><CartonNumberRuleHint v-if="masterLoaded && orderForm.customerCode" :rule="masterDueRules(masterWorkspace.records, orderForm.customerCode).contract_rule" :value="orderForm.contractNo" label="合同号" /><span v-else class="mt-1.5 block text-[9px] text-slate-400">支持中英文、数字及 - _ . / # ( ) + &</span></template></CartonMasterLookup>
              <div class="relative space-y-1.5">
                <CartonMasterLookup :records="masterLoaded ? masterWorkspace.records : []" :customer="orderForm.customerCode" :query="orderForm.itemNo" field="item" :disabled="editingOrderStructureLocked || !masterLoaded" @select="applyMaster($event)"><label class="block space-y-1.5"><span class="text-[11px] font-bold text-slate-600">货号 *</span><input v-model="orderForm.itemNo" aria-label="货号" :disabled="editingOrderStructureLocked" autocomplete="off" placeholder="例如 203302044" class="h-10 w-full rounded-lg border border-slate-200 px-3 outline-none focus:border-teal-500 disabled:bg-slate-50 disabled:text-slate-500" @focus="showHistoryItemSuggestions = historyItemSuggestionsLoading || historyItemSuggestions.length > 0" @keydown.esc="showHistoryItemSuggestions = false"></label><template #hint><CartonNumberRuleHint v-if="masterLoaded && orderForm.customerCode" :rule="masterDueRules(masterWorkspace.records, orderForm.customerCode).item_rule" :value="orderForm.itemNo" label="货号" /></template></CartonMasterLookup>
                <div v-if="!masterLoaded && showHistoryItemSuggestions && (historyItemSuggestionsLoading || historyItemSuggestions.length > 0)" class="absolute left-0 top-[60px] z-30 max-h-80 w-[min(42rem,90vw)] overflow-y-auto rounded-xl border border-teal-200 bg-white p-1.5 shadow-2xl" aria-label="历史货号候选">
                  <div v-if="historyItemSuggestionsLoading" class="px-3 py-3 text-[11px] font-semibold text-slate-500">正在查找近似历史货号…</div>
                  <button v-for="suggestion in historyItemSuggestions" :key="`${suggestion.customer_code}-${suggestion.item_no}`" type="button" :aria-label="`复用历史货号 ${suggestion.item_no} ${suggestion.customer_name}`" class="block w-full rounded-lg px-3 py-2.5 text-left hover:bg-teal-50" @mousedown.prevent="applyHistoryItemSuggestion(suggestion)">
                    <span class="flex flex-wrap items-center gap-2"><span class="font-mono text-[12px] font-bold text-slate-950">{{ suggestion.item_no }}</span><span class="rounded-full bg-teal-50 px-2 py-0.5 text-[9px] font-bold text-teal-700">{{ historyItemMatchLabel(suggestion.match_type) }}</span><span class="text-[11px] font-semibold text-slate-700">{{ suggestion.product_name || '未记录产品名称' }}</span></span>
                    <span class="mt-1 block text-[10px] text-slate-500">{{ suggestion.customer_name }} · 最近 {{ suggestion.latest_order_no }} / {{ formatMonthDay(suggestion.latest_order_date) }} · {{ suggestion.lines.length }} 条纸品 · 历史 {{ suggestion.order_count }} 单</span>
                    <span class="mt-1 block truncate text-[10px] text-slate-400">{{ suggestion.lines.map((line) => `${line.packaging_type} ${line.paper_quality} ${line.specification}`).join('；') }}</span>
                  </button>
                </div>
                <span v-if="selectedHistoryItemSource" class="block text-[9px] font-semibold text-teal-700">已复用 {{ selectedHistoryItemSource.latest_order_no }}；本次合同、数量和日期仍需单独填写</span><span v-else class="block text-[9px] text-slate-400">输入货号后，可在下方选择本客户的基础资料；不同配置请逐项核对</span>
              </div>
              <CartonMasterLookup :records="masterLoaded ? masterWorkspace.records : []" :customer="orderForm.customerCode" :query="orderForm.productName" field="product" :disabled="editingOrderStructureLocked || !masterLoaded" @select="applyMaster($event)"><label class="space-y-1.5"><span class="text-[11px] font-bold text-slate-600">产品名称 *</span><input v-model="orderForm.productName" aria-label="产品名称" :disabled="editingOrderStructureLocked" placeholder="例如 仿真消防车" class="h-10 w-full rounded-lg border border-slate-200 px-3 outline-none focus:border-teal-500 disabled:bg-slate-50 disabled:text-slate-500"></label></CartonMasterLookup>
              <label class="space-y-1.5"><span class="text-[11px] font-bold text-slate-600">产品订单数量{{ orderForm.quantityBasis === 'EXPLICIT' ? '（选填）' : ' *' }}</span><input v-model.number="orderForm.orderQuantity" aria-label="订单数量" type="number" min="1" placeholder="请填写实际数量" :disabled="editingOrderStructureLocked" class="h-10 w-full rounded-lg border border-slate-200 px-3 outline-none focus:border-teal-500 disabled:bg-slate-50 disabled:text-slate-500"></label>
              <div class="grid gap-4 sm:col-span-2 sm:grid-cols-3">
                <label class="space-y-1.5"><span class="text-[11px] font-bold text-slate-600">下单日期</span><input v-model="orderForm.orderDate" aria-label="下单日期" type="date" :disabled="editingOrderStructureLocked" class="h-10 w-full rounded-lg border border-slate-200 px-3 outline-none focus:border-teal-500 disabled:bg-slate-50 disabled:text-slate-500"></label>
                <label class="space-y-1.5"><span class="text-[11px] font-bold text-slate-600">客户交期 *</span><input v-model="orderForm.customerDueDate" aria-label="客户交期" type="date" :min="orderForm.orderDate || undefined" class="h-10 w-full rounded-lg border border-blue-200 px-3 outline-none focus:border-blue-500"><span v-if="editingOrderRecord && !editingOrderRecord.customer_due_date && !orderForm.customerDueDate" class="block text-[9px] text-slate-400">历史订单未记录，可在本次修改时补充</span></label>
                <label class="space-y-1.5"><span class="text-[11px] font-bold text-slate-600">{{ orderForm.quantityBasis === 'EXPLICIT' ? '计划交期（原表）' : '计划交期（自动）' }}</span><input v-if="orderForm.quantityBasis === 'EXPLICIT'" v-model="orderForm.dueDate" aria-label="计划交期" type="date" class="h-10 w-full rounded-lg border px-3"><input v-else :value="calculatedOrderDueDate" aria-label="计划交期" type="date" readonly class="h-10 w-full cursor-not-allowed rounded-lg border border-teal-200 bg-teal-50 px-3 font-semibold text-teal-800 outline-none"><span class="block text-[9px] text-slate-500">{{ orderForm.quantityBasis === 'EXPLICIT' ? '保留原表计划，不自动覆盖' : `客户交期减 ${orderLeadDays} 个自然日` }}</span></label>
                <button v-if="!editingOrderNo && !orderForm.customerDueDate && orderMasterRules.customer_days != null" type="button" class="text-left text-xs text-teal-700 sm:col-span-3" @click="orderForm.customerDueDate = dateOffsetIso(orderForm.orderDate, orderMasterRules.customer_days)">采纳建议客户交期 {{ dateOffsetIso(orderForm.orderDate, orderMasterRules.customer_days) }}（请先核对客户要求）</button>
                <p v-if="orderSafetyLeadWarning" role="alert" class="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[10px] font-semibold text-red-700 sm:col-span-3">{{ orderSafetyLeadWarning }}</p>
              </div>
            </div>
          </section>

          <CartonMasterOrderAssist v-if="masterLoaded && orderForm.quantityBasis !== 'EXPLICIT'" :records="masterWorkspace.records" :customer="orderForm.customerCode" :item="orderForm.itemNo" :contract="orderForm.contractNo" :product="orderForm.productName" :disabled="editingOrderStructureLocked" :lines="orderForm.materials.map(l => ({ packaging_type: l.packagingType, paper_quality: l.paperQuality, specification: l.specification, dimension_unit: l.dimensionUnit, unit: l.unit, usage_quantity: l.unitsPerCarton }))" @select="applyMaster" />
          <p v-else-if="masterError" class="text-xs text-amber-700">基础资料暂未读到，可稍后刷新；{{ masterError }}</p>
          <section class="rounded-xl border border-slate-200">
            <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-slate-50 px-4 py-3">
              <div><div class="font-bold text-slate-950">合同内纸品明细</div><p class="mt-0.5 text-[10px] text-slate-500">{{ orderForm.quantityBasis === 'EXPLICIT' ? '按历史纸品需求数量登记；每箱个数选填，不用反推产品数量。缺失纸质、规格可先保存，确认锁定前须补齐。' : '每行填写每箱个数，纸箱数量自动按“产品订单数量 ÷ 每箱个数”计算，不足一箱向上取整。' }}</p></div>
              <button type="button" :disabled="editingOrderStructureLocked" class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-teal-200 bg-white px-3 text-[11px] font-bold text-teal-700 disabled:cursor-not-allowed disabled:border-slate-200 disabled:text-slate-400" @click="addOrderMaterialLine"><Plus class="size-3.5" />新增纸品明细</button>
            </div>
            <div class="space-y-3 p-4">
              <div v-for="(material, index) in orderForm.materials" :key="material.id" class="grid gap-3 rounded-lg border border-slate-200 bg-slate-50/60 p-3 lg:grid-cols-[1fr_1fr_1.7fr_0.8fr_0.9fr_0.65fr_auto] lg:items-end">
                <label class="space-y-1.5"><span class="text-[10px] font-bold text-slate-500">纸品类型 *</span><CartonPaperPicker v-model="material.packagingType" :options="orderPackagingOptions" :label="`纸品类型 ${index + 1}`" :disabled="editingOrderStructureLocked" /></label>
                <label class="space-y-1.5"><span class="text-[10px] font-bold text-slate-500">纸质 *</span><CartonPaperPicker v-model="material.paperQuality" :options="paperQualitySuggestions" :label="`纸质 ${index + 1}`" :disabled="editingOrderStructureLocked" /></label>
                <label class="space-y-1.5"><span class="text-[10px] font-bold text-slate-500">规格 *</span><CartonPaperPicker v-model="material.specification" :options="specificationSuggestions" :label="`规格 ${index + 1}`" :disabled="editingOrderStructureLocked" /></label>
                <label class="space-y-1.5"><span class="text-[10px] font-bold text-slate-500">每箱个数{{ orderForm.quantityBasis === 'EXPLICIT' ? '（选填）' : ' *' }}</span><input v-model.number="material.unitsPerCarton" :aria-label="`每箱个数 ${index + 1}`" type="number" min="0.00000001" step="any" :disabled="editingOrderStructureLocked" class="h-9 w-full rounded-lg border border-slate-200 bg-white px-2 text-right outline-none focus:border-teal-500 disabled:bg-slate-100"></label>
                <div class="space-y-1.5"><span class="text-[10px] font-bold text-slate-500">{{ orderForm.quantityBasis === 'EXPLICIT' ? '纸品需求数量 *' : '纸箱数量（自动）' }}</span><input v-if="orderForm.quantityBasis === 'EXPLICIT'" v-model.number="material.requiredQuantity" :aria-label="`纸品需求数量 ${index + 1}`" type="number" min="0.0001" step="0.0001" :disabled="editingOrderStructureLocked" class="h-9 w-full rounded-lg border border-teal-200 px-2 text-right font-bold text-teal-700"><output v-else :aria-label="`纸箱数量 ${index + 1}`" class="flex h-9 w-full items-center justify-end rounded-lg border border-teal-200 bg-teal-50 px-2 font-bold text-teal-700 tabular-nums">{{ formatRequiredQuantity(material.unitsPerCarton, orderForm.orderQuantity) }}</output></div>
                <label class="space-y-1.5"><span class="text-[10px] font-bold text-slate-500">单位</span><select v-model="material.unit" :aria-label="`纸品单位 ${index + 1}`" :disabled="editingOrderStructureLocked" class="h-9 w-full rounded-lg border border-slate-200 bg-white px-2 outline-none focus:border-teal-500 disabled:bg-slate-100"><option v-if="material.unit && !orderUnitOptions.includes(material.unit)">{{ material.unit }}</option><option v-for="value in orderUnitOptions" :key="value">{{ value }}</option></select></label>
                <button type="button" :disabled="editingOrderStructureLocked" :aria-label="`删除纸品明细 ${index + 1}`" class="flex size-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-400 transition hover:border-red-200 hover:text-red-600 disabled:cursor-not-allowed disabled:bg-slate-100" @click="removeOrderMaterialLine(index)"><X class="size-4" /></button>
              </div>
            </div>
          </section>
          <datalist id="carton-paper-quality-history"><option v-for="value in paperQualitySuggestions" :key="value" :value="value" /></datalist>
          <datalist id="carton-specification-history"><option v-for="value in specificationSuggestions" :key="value" :value="value" /></datalist>

          <label class="block space-y-1.5"><span class="text-[11px] font-bold text-slate-600">合同备注</span><textarea v-model="orderForm.note" aria-label="订单备注" rows="3" placeholder="历史规格来源、刀模版本或特殊交付要求" class="w-full rounded-lg border border-slate-200 px-3 py-2 outline-none focus:border-teal-500"></textarea></label>
          <label v-if="editingOrderNo" class="block space-y-1.5"><span class="text-[11px] font-bold text-slate-600">修改原因（默认已填写，可修改）</span><textarea v-model="orderChangeReason" aria-label="订单修改原因" rows="2" minlength="4" maxlength="500" placeholder="说明客户通知、数量修正或交期变化原因" class="w-full rounded-lg border border-amber-200 bg-amber-50/60 px-3 py-2 outline-none focus:border-amber-500"></textarea></label>
        </div>
        <div class="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 bg-slate-50 px-5 py-4"><p class="text-[10px] text-slate-500">{{ editingOrderNo ? '保存后版本号递增并写入修改原因。' : '创建后仍可修改、追加或取消；必须另行“确认订单并锁定”后才允许入库。' }}</p><div class="flex gap-2"><button type="button" class="h-9 rounded-lg border border-slate-200 bg-white px-4 text-[12px] font-bold text-slate-600" @click="showOrderModal = false">返回</button><button type="submit" :disabled="savingOrder" class="h-9 rounded-lg bg-teal-700 px-4 text-[12px] font-bold text-white disabled:opacity-60">{{ savingOrder ? '正在保存…' : editingOrderNo ? '保存订单修订' : '创建待下单订单' }}</button></div></div>
      </form>
    </div>

    <DialogRoot :open="Boolean(purchaseBatchConfirmation)" @update:open="!$event && closePurchaseBatchConfirmation()">
      <DialogOverlay class="fixed inset-0 z-[80] bg-slate-950/45" />
      <DialogContent class="fixed left-1/2 top-1/2 z-[81] w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 -translate-y-1/2 rounded-2xl bg-white p-5 shadow-2xl" aria-label="批量采购单确认">
        <DialogTitle class="text-lg font-bold text-slate-950">确认生成采购单批次</DialogTitle>
        <DialogDescription class="mt-3 whitespace-pre-line text-sm leading-6 text-slate-600">{{ purchaseBatchConfirmation }}</DialogDescription>
        <div class="mt-5 flex justify-end gap-3">
          <button type="button" class="h-9 rounded-lg border border-slate-200 px-4 text-sm text-slate-600" @click="closePurchaseBatchConfirmation()">取消</button>
          <button type="button" class="h-9 rounded-lg bg-teal-700 px-4 text-sm font-bold text-white" @click="closePurchaseBatchConfirmation(true)">确认并下载</button>
        </div>
      </DialogContent>
    </DialogRoot>

    <div v-if="submitSupplierOrderNo || bulkSubmitSupplierOrderNos.length" class="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/45 p-4" @click.self="closeSubmitSupplierDialog">
      <div class="w-full max-w-lg overflow-hidden rounded-2xl bg-white shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="submit-supplier-title">
        <div class="flex items-start justify-between border-b border-slate-200 px-5 py-4">
          <div><h2 id="submit-supplier-title" class="text-[16px] font-bold text-slate-950">{{ bulkSubmitSupplierOrderNos.length ? `批量确认并锁定 ${selectedSubmittableOrderCount} 张待下单订单` : `确认订单 ${submitSupplierOrderNo} 并锁定` }}</h2><p class="mt-1 text-[11px] text-slate-500">确认后订单进入“已确认锁定”状态并开放收料；这一步不会发送文件，之后需要另行发行供应商采购单。</p></div>
          <button type="button" aria-label="关闭确认订单并锁定" class="rounded-lg p-2 text-slate-400 hover:bg-slate-100" @click="closeSubmitSupplierDialog"><X class="size-4" /></button>
        </div>
        <div class="p-5"><div class="rounded-xl border border-amber-200 bg-amber-50 p-4 text-[12px] font-semibold leading-6 text-amber-900">此操作会锁定普通编辑：确认锁定后客户、合同、货号和纸品资料不可直接修改；有权限的仓管或主管可继续追加，也可减少尚未入库且未进入待确认收料单的数量。</div></div>
        <div class="flex justify-end gap-2 border-t border-slate-200 bg-slate-50 px-5 py-4"><button type="button" class="h-9 rounded-lg border border-slate-200 bg-white px-4 text-[12px] font-bold text-slate-600" @click="closeSubmitSupplierDialog">返回检查</button><button type="button" aria-label="执行确认订单并锁定" :disabled="submittingSupplierOrder" class="h-9 rounded-lg bg-teal-700 px-4 text-[12px] font-bold text-white disabled:opacity-60" @click="confirmSubmitSupplierOrder">{{ submittingSupplierOrder ? '正在确认…' : '确认订单并锁定' }}</button></div>
      </div>
    </div>

    <div v-if="cancelOrderNo" class="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/45 p-4">
      <form class="w-full max-w-lg overflow-hidden rounded-2xl bg-white shadow-2xl" @submit.prevent="confirmCancelOrder">
        <div class="flex items-start justify-between border-b border-slate-200 px-5 py-4">
          <div><h2 class="text-[16px] font-bold text-slate-950">{{ cancelOrderNo === '__BULK__' ? `批量取消 ${selectedOrders.length} 张订单` : canReturnOrder(cancelOrderNo) ? `退单 ${cancelOrderNo}` : `取消订单 ${cancelOrderNo}` }}</h2><p class="mt-1 text-[11px] text-slate-500">{{ cancelOrderNo === '__BULK__' ? '仅尚未确认锁定的待下单订单可批量取消，全部校验通过后一次生效。' : canReturnOrder(cancelOrderNo) ? '退单用于已发生入库的订单，会将当前可用库存转出并保留原订单。' : '该订单尚未确认锁定，可以取消；取消后保留审计记录。' }}</p></div>
          <button type="button" aria-label="关闭取消订单" class="rounded-lg p-2 text-slate-400 hover:bg-slate-100" @click="cancelOrderNo = ''"><X class="size-4" /></button>
        </div>
        <div class="p-5"><label class="block space-y-1.5"><span class="text-[11px] font-bold text-slate-600">{{ cancelOrderNo === '__BULK__' ? '批量取消原因' : canReturnOrder(cancelOrderNo) ? '退单原因' : '取消原因' }} *</span><textarea v-model="cancelOrderReason" aria-label="订单取消退单原因" rows="4" minlength="4" maxlength="500" placeholder="例如：客户正式取消合同" class="w-full rounded-lg border border-red-200 bg-red-50/40 px-3 py-2 outline-none focus:border-red-500"></textarea></label></div>
        <div class="flex justify-end gap-2 border-t border-slate-200 bg-slate-50 px-5 py-4"><button type="button" class="h-9 rounded-lg border border-slate-200 bg-white px-4 text-[12px] font-bold text-slate-600" @click="cancelOrderNo = ''">返回</button><button type="submit" :disabled="cancellingOrder" class="h-9 rounded-lg bg-red-600 px-4 text-[12px] font-bold text-white disabled:opacity-60">{{ cancellingOrder ? '处理中…' : cancelOrderNo === '__BULK__' ? '确认批量取消' : canReturnOrder(cancelOrderNo) ? '确认退单' : '确认取消' }}</button></div>
      </form>
    </div>

    <div v-if="purchaseOrderDialogNo" class="fixed inset-0 z-[65] flex items-center justify-center bg-slate-950/45 p-4" @click.self="closePurchaseOrderDialog">
      <div class="max-h-[88vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="purchase-order-dialog-title">
        <div class="flex items-start justify-between border-b border-slate-200 px-5 py-4">
          <div><h2 id="purchase-order-dialog-title" class="text-[16px] font-bold text-slate-950">供应商采购单 · {{ purchaseOrderDialogNo }}</h2><p class="mt-1 text-[11px] text-slate-500">合同订单保留累计数量；供应商执行只认每张采购单的“本次变化”列。</p></div>
          <button type="button" aria-label="关闭采购单记录" class="rounded-lg p-2 text-slate-400 hover:bg-slate-100" @click="closePurchaseOrderDialog"><X class="size-4" /></button>
        </div>
        <div v-if="loadingPurchaseOrderContext" class="p-8 text-center text-[12px] font-semibold text-slate-500">正在读取采购单发行记录…</div>
        <div v-else-if="purchaseOrderContextRecord" class="space-y-4 p-5">
          <div v-if="purchaseOrderContextRecord.historical_baseline" class="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-[11px] leading-5 text-blue-800">历史已下单数量已登记为历史基线；后续追加或减单只导出相对该基线的净变化，避免重复下单。</div>
          <section class="rounded-xl border p-4" :class="purchaseOrderContextRecord.can_generate ? 'border-amber-200 bg-amber-50/60' : 'border-slate-200 bg-slate-50'">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div class="text-[10px] font-bold uppercase tracking-wide text-slate-500">当前待处理</div>
                <div class="mt-1 text-[15px] font-bold text-slate-950">{{ purchaseOrderTypeLabel(purchaseOrderContextRecord.pending_type) }}</div>
                <p v-if="purchaseOrderContextRecord.pending_type !== 'NONE'" class="mt-1 text-[11px] text-slate-600">产品数量变化 {{ signedQuantity(purchaseOrderContextRecord.pending_product_quantity) }}；{{ purchaseOrderContextRecord.pending_line_count }} 条纸品产生箱数变化。</p>
                <p v-else class="mt-1 text-[11px] text-slate-500">当前累计数量与最近一次采购单快照一致，无需再次向供应商下单。</p>
              </div>
              <button v-if="purchaseOrderContextRecord.can_generate && canIssuePurchaseOrders" type="button" :disabled="issuingPurchaseOrder" class="h-9 rounded-lg bg-amber-600 px-4 text-[11px] font-bold text-white disabled:opacity-50" @click="issuePendingPurchaseOrder">{{ issuingPurchaseOrder ? '正在固定生成…' : `生成并下载${purchaseOrderTypeLabel(purchaseOrderContextRecord.pending_type)}` }}</button>
            </div>
            <p v-if="purchaseOrderContextRecord.pending_type !== 'NONE' && !purchaseOrderContextRecord.can_generate" class="mt-3 rounded-lg bg-white px-3 py-2 text-[11px] font-semibold text-amber-800">请先确认订单并锁定，再发行正式供应商采购单。</p>
            <p v-else-if="purchaseOrderContextRecord.can_generate && !canIssuePurchaseOrders" class="mt-3 rounded-lg bg-white px-3 py-2 text-[11px] font-semibold text-red-700">当前账号可查看记录，但没有生成供应商采购单的权限。</p>
          </section>

          <section class="overflow-hidden rounded-xl border border-slate-200">
            <div class="flex items-center justify-between bg-slate-50 px-4 py-3"><div><h3 class="text-[12px] font-bold text-slate-900">不可变采购单历史</h3><p class="mt-0.5 text-[10px] text-slate-500">重新下载始终使用当时快照，不会套用订单后续数量。</p></div><span class="rounded-full bg-white px-2.5 py-1 text-[10px] font-bold text-slate-600">{{ purchaseOrderContextRecord.issues.length }} 份</span></div>
            <div v-if="purchaseOrderContextRecord.issues.length" class="divide-y divide-slate-100">
              <div v-for="issue in purchaseOrderContextRecord.issues" :key="issue.id" class="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                <div><div class="flex items-center gap-2"><b class="font-mono text-[12px] text-slate-900">{{ issue.document_no }}</b><span class="rounded-full bg-teal-50 px-2 py-0.5 text-[9px] font-bold text-teal-700">{{ (issue.is_replenishment ? '补单采购单' : purchaseOrderTypeLabel(issue.document_type)) }}</span></div><p class="mt-1 text-[10px] text-slate-500">产品变化 {{ signedQuantity(issue.product_quantity_delta) }} · {{ issue.generated_by_name || '—' }} · {{ issue.generated_at.slice(0, 16).replace('T', ' ') }}</p></div>
                <button type="button" :disabled="Boolean(downloadingPurchaseOrderIssueId)" class="h-8 rounded-lg border border-teal-200 bg-white px-3 text-[10px] font-bold text-teal-700 disabled:opacity-40" @click="downloadPurchaseOrderIssue(issue)">{{ downloadingPurchaseOrderIssueId === issue.id ? '下载中…' : '重新下载原版本' }}</button>
              </div>
            </div>
            <div v-else class="px-4 py-6 text-center text-[11px] text-slate-400">还没有正式生成过供应商采购单</div>
          </section>

          <div class="rounded-xl border border-slate-200 bg-white p-4"><div class="flex flex-wrap items-center justify-between gap-3"><div><div class="text-[11px] font-bold text-slate-800">当前累计对账表</div><p class="mt-1 text-[10px] text-slate-500">仅供内部核对当前总量，不代表向供应商追加下单。</p></div><button type="button" :disabled="Boolean(exportingOrderNo)" class="h-8 rounded-lg border border-slate-200 px-3 text-[10px] font-bold text-slate-600 disabled:opacity-40" @click="exportCumulativePurchaseOrderReference">{{ exportingOrderNo ? '生成中…' : '导出累计参考' }}</button></div></div>
        </div>
        <div class="flex justify-end border-t border-slate-200 bg-slate-50 px-5 py-4"><button type="button" class="h-9 rounded-lg border border-slate-200 bg-white px-4 text-[12px] font-bold text-slate-600" @click="closePurchaseOrderDialog">关闭</button></div>
      </div>
    </div>

    <CartonHistoryImportDialog v-if="historyImportFile" :file="historyImportFile" :factory-id="selectedFactoryId" @close="historyImportFile = null" @imported="completeHistoryImport" />
    <div v-if="appendOrderNo" class="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/45 p-4">
      <form data-testid="append-order-form" class="w-full max-w-2xl overflow-hidden rounded-2xl bg-white shadow-2xl" @submit.prevent="confirmAppendOrder">
        <div class="flex items-start justify-between border-b border-slate-200 px-5 py-4"><div><h2 class="text-[16px] font-bold text-slate-950">追加订单 {{ appendOrderNo }}</h2><p class="mt-1 text-[11px] text-slate-500">{{ appendOrderGuidance }}</p></div><button type="button" aria-label="关闭追加订单" class="rounded-lg p-2 text-slate-400 hover:bg-slate-100" @click="appendOrderNo = ''"><X class="size-4" /></button></div>
        <div class="grid gap-4 p-5 sm:grid-cols-3"><label v-if="appendingOrderRecord?.quantity_basis !== 'EXPLICIT'" class="space-y-1.5"><span class="text-[11px] font-bold text-slate-600">追加产品数量 *</span><input v-model.number="appendOrderQuantity" aria-label="追加订单数量" type="number" min="1" class="h-10 w-full rounded-lg border border-amber-200 px-3 text-right font-semibold outline-none focus:border-amber-500"></label><label class="space-y-1.5"><span class="text-[11px] font-bold text-slate-600">新客户交期</span><input v-model="appendOrderCustomerDueDate" aria-label="追加订单客户交期" type="date" :min="appendingOrderRecord?.order_date" class="h-10 w-full rounded-lg border border-blue-200 px-3 outline-none focus:border-blue-500"><span v-if="!appendingOrderRecord?.customer_due_date" class="block text-[9px] text-slate-400">历史订单可留空并沿用原计划交期</span></label><label class="space-y-1.5"><span class="text-[11px] font-bold text-slate-600">新计划交期</span><input v-if="appendingOrderRecord?.quantity_basis === 'EXPLICIT'" v-model="appendOrderDueDate" aria-label="追加订单计划交期" type="date" class="h-10 w-full rounded-lg border px-3"><input v-else :value="calculatedAppendOrderDueDate" aria-label="追加订单计划交期" type="date" readonly class="h-10 w-full cursor-not-allowed rounded-lg border border-teal-200 bg-teal-50 px-3 font-semibold text-teal-800 outline-none"><span class="block text-[9px] text-slate-500">{{ appendingOrderRecord?.quantity_basis === 'EXPLICIT' ? '沿用原计划，可按实际修改' : `客户交期减 ${appendLeadDays} 个自然日` }}</span></label><p v-if="appendSafetyLeadWarning" role="alert" class="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[10px] font-semibold text-red-700 sm:col-span-3">{{ appendSafetyLeadWarning }}</p><label class="space-y-1.5 sm:col-span-3"><span class="text-[11px] font-bold text-slate-600">追加原因（默认已填写，可修改）</span><textarea v-model="appendOrderReason" aria-label="追加订单原因" rows="3" maxlength="500" placeholder="如有其他原因，可在这里修改" class="w-full rounded-lg border border-amber-200 bg-amber-50/40 px-3 py-2 outline-none focus:border-amber-500"></textarea></label></div>
        <div v-if="appendingOrderRecord?.quantity_basis === 'EXPLICIT'" class="overflow-x-auto px-5 pb-4"><p class="mb-2 text-xs text-teal-700">填写每条纸品追加后的总需求，不反推产品数量；未追加的行保持原值。</p><table class="w-full text-left text-xs"><thead><tr><th class="p-2">纸品 / 纸质 / 规格</th><th class="p-2">当前需求</th><th class="p-2">追加后总需求</th></tr></thead><tbody><tr v-for="line in appendingOrderRecord.lines" :key="line.id" class="border-t"><td class="p-2">{{ line.packaging_type }} {{ line.paper_quality }} {{ line.specification }}</td><td class="p-2">{{ line.required_quantity }} {{ line.unit }}</td><td class="p-2"><input v-model.number="appendLineTargets[line.id]" :aria-label="`追加后纸品需求 ${line.id}`" type="number" :min="Number(line.required_quantity)" step="0.0001" class="h-9 w-32 rounded border px-2 text-right"> {{ line.unit }}</td></tr></tbody></table></div><div class="flex justify-end gap-2 border-t border-slate-200 bg-slate-50 px-5 py-4"><button type="button" class="h-9 rounded-lg border border-slate-200 bg-white px-4 text-[12px] font-bold text-slate-600" @click="appendOrderNo = ''">返回</button><button type="submit" :disabled="appendingOrder" class="h-9 rounded-lg bg-amber-600 px-4 text-[12px] font-bold text-white disabled:opacity-60">{{ appendingOrder ? '正在追加…' : '确认追加并留痕' }}</button></div>
      </form>
    </div>

    <div v-if="reduceOrderNo" class="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/45 p-4">
      <form data-testid="reduce-order-form" class="w-full max-w-lg overflow-hidden rounded-2xl bg-white shadow-2xl" @submit.prevent="confirmReduceOrder">
        <div class="flex items-start justify-between border-b border-slate-200 px-5 py-4">
          <div><h2 class="text-[16px] font-bold text-slate-950">{{ reducingOrderRecord?.status === 'PARTIALLY_RECEIVED' ? '减少未入库量' : '减单 / 退单' }} {{ reduceOrderNo }}</h2><p class="mt-1 text-[11px] text-slate-500">{{ reducingOrderRecord?.status === 'PARTIALLY_RECEIVED' ? '仅可减少尚未入库且未进入待确认收料单的数量；减完全部余量后订单自动转为“全部到货”。' : '尚无入库时可部分减单或整单退单；待确认收料数量会预留保护。' }}</p></div>
          <button type="button" aria-label="关闭减单" class="rounded-lg p-2 text-slate-400 hover:bg-slate-100" @click="reduceOrderNo = ''"><X class="size-4" /></button>
        </div>
        <div class="space-y-4 p-5">
          <div v-if="reducingOrderRecord?.quantity_basis !== 'EXPLICIT'" class="grid grid-cols-3 gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3 text-[12px]"><div><span class="block text-slate-500">当前产品数量</span><b class="mt-1 block text-slate-900">{{ formatNumber(Number(reducingOrderRecord?.product_order_quantity ?? 0)) }}</b></div><div><span class="block text-slate-500">最大可减</span><b class="mt-1 block text-amber-700">{{ formatNumber(reduceOrderMaximumQuantity) }}</b></div><div><span class="block text-slate-500">调整后数量</span><b class="mt-1 block" :class="reduceOrderRemainingQuantity === 0 ? 'text-red-700' : 'text-teal-700'">{{ formatNumber(reduceOrderRemainingQuantity) }}</b></div></div>
          <label v-if="reducingOrderRecord?.quantity_basis !== 'EXPLICIT'" class="block space-y-1.5"><span class="text-[11px] font-bold text-slate-600">{{ reducingOrderRecord?.status === 'PARTIALLY_RECEIVED' ? '减少未入库产品数量' : '减少产品数量' }} *</span><input v-model.number="reduceOrderQuantity" aria-label="减单数量" type="number" min="1" :max="reduceOrderMaximumQuantity" class="h-10 w-full rounded-lg border border-red-200 px-3 text-right font-semibold outline-none focus:border-red-500"></label>
          <div v-if="reducingOrderRecord?.quantity_basis === 'EXPLICIT'" class="overflow-x-auto"><p class="mb-2 text-xs text-teal-700">逐纸品填写减少后的总需求，不修改产品数量；不能低于已收与待确认数量。</p><table class="w-full text-left text-xs"><thead><tr><th class="p-2">纸品 / 规格</th><th class="p-2">当前需求</th><th class="p-2">已收及待确认</th><th class="p-2">减少后总需求</th></tr></thead><tbody><tr v-for="line in reducingOrderRecord.lines" :key="line.id" class="border-t"><td class="p-2">{{ line.packaging_type }} {{ line.paper_quality }} {{ line.specification }}</td><td class="p-2">{{ line.required_quantity }} {{ line.unit }}</td><td class="p-2">{{ paperProtectedQuantity(line) }}</td><td class="p-2"><input v-model.number="reduceLineTargets[line.id]" :aria-label="`减少后纸品需求 ${line.id}`" type="number" :min="paperProtectedQuantity(line)" :max="Number(line.required_quantity)" step="0.0001" class="h-9 w-28 rounded border px-2 text-right"></td></tr></tbody></table></div><label class="block space-y-1.5"><span class="text-[11px] font-bold text-slate-600">减单 / 退单原因（默认已填写，可修改）</span><textarea v-model="reduceOrderReason" aria-label="减单原因" rows="3" maxlength="500" placeholder="如有其他原因，可在这里修改" class="w-full rounded-lg border border-red-200 bg-red-50/40 px-3 py-2 outline-none focus:border-red-500"></textarea></label>
          <div class="rounded-xl border border-amber-200 bg-amber-50 p-3 text-[11px] font-semibold leading-5 text-amber-900">最大可减数量已经按每条纸品的已入库量与待确认收料量计算；确认后只降低未入库需求，不修改任何既有收料单或库存流水。</div>
        </div>
        <div class="flex justify-end gap-2 border-t border-slate-200 bg-slate-50 px-5 py-4"><button type="button" class="h-9 rounded-lg border border-slate-200 bg-white px-4 text-[12px] font-bold text-slate-600" @click="reduceOrderNo = ''">返回</button><button type="submit" :disabled="reducingOrder" class="h-9 rounded-lg bg-red-600 px-4 text-[12px] font-bold text-white disabled:opacity-60">{{ reducingOrder ? '正在处理…' : reducingOrderRecord?.quantity_basis === 'EXPLICIT' ? '确认按纸品减单' : reduceOrderRemainingQuantity === 0 ? '确认整单退单' : reducingOrderRecord?.status === 'PARTIALLY_RECEIVED' ? '确认减少未入库量' : '确认减单并留痕' }}</button></div>
      </form>
    </div>

    <div v-if="closingDecision" class="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/45 p-4">
      <form role="dialog" aria-label="月结最终操作确认" aria-modal="true" class="w-full max-w-lg rounded-2xl bg-white p-5 shadow-xl" @submit.prevent="confirmClosingDecision">
        <h2 class="text-lg font-bold">{{ closingDecision.action === 'LOCK' ? '最终锁账确认' : '解锁并重新核对' }}</h2>
        <p class="mt-3 font-semibold">{{ closingDecision.closing.customer_name }} · {{ closingDecision.closing.period }} · {{ closingDecision.closing.currency }}</p>
        <p class="mt-3 rounded-lg bg-amber-50 p-3 text-sm leading-6 text-amber-900">{{ closingDecision.action === 'LOCK' ? '最终锁账后，该客户本月不能再新增入库、出库、调整或冲销。请确认该月收发记录已录齐，数量和单价已核对完毕。' : '解锁后回到草稿，原锁账快照和本次原因会保留在操作日志中。更正完成后须重新生成草稿并核对；如有后续已锁月份，需先从最新月份解锁。' }}</p>
        <label v-if="closingDecision.action === 'UNLOCK'" class="mt-3 block text-sm font-bold">解锁原因 *<textarea v-model="closingDecisionReason" :disabled="Boolean(closingBusyId)" aria-label="月结解锁原因" rows="3" maxlength="2000" class="mt-2 w-full rounded-lg border border-slate-200 p-3" placeholder="例如：本月尚未结束，误操作提前锁账"></textarea></label>
        <p v-if="closingDecisionError" role="alert" class="mt-3 text-sm text-red-600">{{ closingDecisionError }}</p>
        <div class="mt-5 flex justify-end gap-3"><button type="button" :disabled="Boolean(closingBusyId)" class="h-9 rounded-lg border px-4" @click="closingDecision = null">取消</button><button type="submit" :disabled="Boolean(closingBusyId)" class="h-9 rounded-lg bg-teal-700 px-4 font-bold text-white disabled:opacity-50">{{ closingBusyId ? '正在处理…' : closingDecision.action === 'LOCK' ? '确认最终锁账' : '确认解锁' }}</button></div>
      </form>
    </div>
    <CartonReceiptDetail v-if="receiptDetailTarget" :receipt="receiptDetailTarget" :pinned="receiptDetailPinned" :can-continue="canCorrectReceipt" @close="closeReceiptDetails" @continue="continueReceiptDetails" />

    <div v-if="receiptCorrectionTarget" class="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/45 p-4">
      <form role="dialog" aria-modal="true" aria-label="收料纠错确认" class="max-h-[90vh] w-full max-w-2xl overflow-auto rounded-2xl bg-white p-5 shadow-xl" @submit.prevent="confirmReceiptCorrection">
        <h2 class="text-lg font-bold">{{ receiptCorrectionTarget.status === 'POSTED' ? '整单冲销入库' : '作废待确认收料单' }}</h2>
        <p class="mt-2 text-sm text-slate-600">收料单 {{ receiptCorrectionTarget.receipt_no }} · 送货单 {{ receiptCorrectionTarget.delivery_note_no }}</p>
        <p class="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">{{ receiptCorrectionTarget.status === 'POSTED' ? '本操作会冲销这张收料单的全部明细，并恢复关联订单的待收数量。已锁账、库存不足或金额无法对平时会阻止操作。' : '本单尚未入库，作废会释放待确认数量，不改变库存。' }}原单长期保留；处理后可重新登记正确信息。</p>
        <ul class="my-3 divide-y divide-slate-100 text-sm"><li v-for="line in receiptCorrectionTarget.lines" :key="line.id" class="flex justify-between gap-3 py-2"><span>{{ line.contract_no }} / {{ line.item_no }} · {{ line.packaging_type }} {{ line.paper_quality }}</span><strong class="whitespace-nowrap">{{ formatNumber(Number(line.effective_quantity)) }} {{ line.unit }}</strong></li></ul>
        <label class="block text-sm font-semibold">原因（默认已填写，可修改）<textarea v-model="receiptCorrectionReason" :disabled="receiptCorrectionBusy" aria-label="收料纠错原因" rows="3" maxlength="2000" class="mt-2 w-full rounded-lg border border-slate-200 p-3" placeholder="说明录错的信息及更正原因"></textarea></label>
        <p v-if="receiptCorrectionError" role="alert" class="my-3 text-sm text-red-600">{{ receiptCorrectionError }}</p>
        <div class="mt-4 flex justify-end gap-3"><button type="button" :disabled="receiptCorrectionBusy" class="h-9 rounded-lg border px-4" @click="receiptCorrectionTarget = null">取消</button><button type="submit" :disabled="receiptCorrectionBusy" class="h-9 rounded-lg bg-red-600 px-4 font-bold text-white disabled:opacity-50">{{ receiptCorrectionBusy ? '正在处理…' : receiptCorrectionTarget.status === 'POSTED' ? '确认整单冲销' : '确认作废' }}</button></div>
      </form>
    </div>
    <div v-if="reversingMovementId" class="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/45 p-4">
      <form class="w-full max-w-lg overflow-hidden rounded-2xl bg-white shadow-2xl" @submit.prevent="confirmInventoryReversal">
        <div class="flex items-start justify-between border-b border-slate-200 px-5 py-4">
          <div><h2 class="text-[16px] font-bold text-slate-950">冲销库存流水</h2><p class="mt-1 text-[11px] text-slate-500">系统将新增一笔方向相反的冲销流水，原流水不会被修改或删除。</p></div>
          <button type="button" aria-label="关闭库存冲销" class="rounded-lg p-2 text-slate-400 hover:bg-slate-100" @click="reversingMovementId = ''"><X class="size-4" /></button>
        </div>
        <div class="space-y-3 p-5">
          <div class="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 font-mono text-[11px] text-slate-700">原流水：{{ reversingMovementId }}</div>
          <label class="block space-y-1.5"><span class="text-[11px] font-bold text-slate-600">冲销原因（默认已填写，可修改）</span><textarea v-model="reversalReason" aria-label="库存冲销原因" rows="4" maxlength="2000" placeholder="说明原单据错误或作废原因" class="w-full rounded-lg border border-red-200 bg-red-50/40 px-3 py-2 outline-none focus:border-red-500"></textarea></label>
        </div>
        <div class="flex justify-end gap-2 border-t border-slate-200 bg-slate-50 px-5 py-4"><button type="button" class="h-9 rounded-lg border border-slate-200 bg-white px-4 text-[12px] font-bold text-slate-600" @click="reversingMovementId = ''">返回</button><button type="submit" :disabled="reversalBusy" class="h-9 rounded-lg bg-red-600 px-4 text-[12px] font-bold text-white disabled:opacity-60">{{ reversalBusy ? '正在冲销…' : '确认冲销' }}</button></div>
      </form>
    </div>
        <div v-if="pricingTarget" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4" @keydown.esc="!pricingBusy && (pricingTarget = null)">
        <form role="dialog" aria-modal="true" aria-labelledby="inventory-price-title" class="w-full max-w-lg rounded-2xl bg-white p-5 shadow-xl" @submit.prevent="confirmClosingPrice">
          <h2 id="inventory-price-title" class="text-lg font-bold">核实入库单价</h2>
          <p class="mt-2 text-sm text-slate-600">{{ pricingTarget.document_no }} · {{ pricingTarget.item_no }} · {{ pricingTarget.packaging_type }}</p>
          <label class="mt-4 block text-sm font-semibold">单价（{{ pricingTarget.currency }} / {{ pricingTarget.unit }}）<input v-model="pricingAmount" :disabled="pricingBusy" aria-label="核实入库单价" type="text" inputmode="decimal" class="mt-2 h-10 w-full rounded-lg border border-slate-200 px-3"></label>
          <label v-if="pricingAmount !== '' && Number(pricingAmount) === 0" class="mt-3 flex items-center gap-2 text-sm"><input v-model="pricingZeroConfirmed" :disabled="pricingBusy" aria-label="确认免费物料" type="checkbox">已核实为免费物料，实际单价为 0</label>
          <label class="mt-4 block text-sm font-semibold">核价依据<textarea v-model="pricingReason" :disabled="pricingBusy" aria-label="核价依据" maxlength="500" rows="3" placeholder="填写报价单、对账单或免费供料依据" class="mt-2 w-full rounded-lg border border-slate-200 p-3" /></label>
          <p v-if="pricingFeedback" role="alert" class="mt-3 text-sm text-red-600">{{ pricingFeedback }}</p>
          <div class="mt-5 flex justify-end gap-2"><button type="button" :disabled="pricingBusy" class="h-9 rounded-lg border px-4" @click="pricingTarget = null">取消</button><button type="submit" :disabled="pricingBusy || !canManageClosingPrices" class="h-9 rounded-lg bg-teal-700 px-4 font-semibold text-white disabled:opacity-40">{{ pricingBusy ? '保存中…' : '确认单价' }}</button></div>
        </form>
      </div>
  </main>
</template>

<style scoped>
@media (min-width: 1024px) {
  .receipt-order-ledger-grid {
    grid-template-columns:
      minmax(0, 0.65fr)
      minmax(0, 0.6fr)
      minmax(0, 0.95fr)
      minmax(0, 0.7fr)
      minmax(0, 0.95fr)
      minmax(0, 0.75fr)
      8.75rem
      6rem
      6.25rem
      9rem;
  }
  .order-ledger-grid {
    grid-template-columns:
      minmax(0, 0.65fr)
      minmax(0, 0.25fr)
      minmax(0, 0.78fr)
      minmax(0, 0.55fr)
      minmax(0, 0.85fr)
      minmax(0, 0.74fr)
      8.75rem
      6.5rem
      6.25rem
      14.5rem;
  }
}

.inventory-balance-table td { overflow-wrap: anywhere; }
@media (max-width: 1023px) {
  .inventory-balance-table colgroup, .inventory-balance-table thead { display: none; }
  .inventory-balance-table, .inventory-balance-table tbody { display: block; width: 100%; }
  .inventory-balance-table tr { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); padding: 8px; }
  .inventory-balance-table td { min-width: 0; text-align: left; padding: 6px; }
  .inventory-balance-table td:nth-child(3), .inventory-balance-table td:nth-child(4), .inventory-balance-table td:nth-child(5), .inventory-balance-table td:nth-child(11), .inventory-balance-table td[colspan] { grid-column: 1 / -1; }
  .inventory-balance-table td:nth-child(6)::before { content: '仓位'; }
  .inventory-balance-table td:nth-child(7)::before { content: '累计入库'; }
  .inventory-balance-table td:nth-child(8)::before { content: '累计出库'; }
  .inventory-balance-table td:nth-child(9)::before { content: '当前结余'; }
  .inventory-balance-table td:nth-child(10)::before { content: '到货情况'; }
  .inventory-balance-table td::before { display: block; font-size: 10px; color: #64748b; margin-bottom: 4px; }
}
</style>
