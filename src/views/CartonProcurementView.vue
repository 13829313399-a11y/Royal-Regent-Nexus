<script setup lang="ts">
import { computed, nextTick, reactive, ref, shallowRef, watch, type Component } from 'vue'
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

type CartonTab = 'dashboard' | 'orders' | 'weekly-check' | 'receipts' | 'inventory' | 'inventory-summary' | 'closing' | 'exceptions' | 'audit'
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
  { id: 'dashboard', label: '纸箱采购协同看板', shortLabel: '协同看板', icon: LayoutDashboard },
  { id: 'orders', label: '纸箱订单管理', shortLabel: '订单管理', icon: ClipboardCheck },
  { id: 'weekly-check', label: '每周核对与交期提醒', shortLabel: '周核对', icon: CalendarClock },
  { id: 'receipts', label: '收料反馈平台', shortLabel: '收料反馈', icon: PackageCheck },
  { id: 'inventory', label: '库存台账与交易流水', shortLabel: '库存流水', icon: Boxes },
  { id: 'inventory-summary', label: '库存汇总', shortLabel: '库存汇总', icon: FileSpreadsheet },
  { id: 'closing', label: '库存月结与对账报表', shortLabel: '月结对账', icon: FileSpreadsheet },
  { id: 'exceptions', label: '异常中心', shortLabel: '异常中心', icon: AlertTriangle },
  { id: 'audit', label: '统一操作日志', shortLabel: '操作日志', icon: GitBranch },
]

const validTabs = new Set<CartonTab>(tabs.map((tab) => tab.id))
const selectedCustomer = ref('全部客户')
const globalSearch = ref('')
const actionMessage = ref('正在读取纸箱采购台账…')
const apiConnected = ref(false)
const backendLoading = ref(false)
const savingOrder = ref(false)
const exportingOrderNo = ref('')
const exportingSelectedOrders = ref(false)
const issuingSelectedPurchaseOrders = ref(false)
const purchaseOrderDialogNo = ref('')
const purchaseOrderContextRecord = ref<CartonPurchaseOrderContextResponse | null>(null)
const loadingPurchaseOrderContext = ref(false)
const issuingPurchaseOrder = ref(false)
const downloadingPurchaseOrderIssueId = ref('')
const selectedOrderNos = ref<string[]>([])
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
const historyInventoryFileInput = ref<HTMLInputElement | null>(null)
const importingHistoryInventory = ref(false)
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
const customerSearch = ref('')
const savingCustomer = ref(false)
const deletingCustomerId = ref('')
const editingCustomerId = ref('')
const receiptFeedbackMessage = ref('')
const receiptFeedbackTone = ref<'error' | 'success'>('error')
const manualDeliveryNoteInput = ref<HTMLInputElement | null>(null)
const manualDeliveryDateInput = ref<HTMLInputElement | null>(null)
const receiptEntryMode = ref<'IMPORT' | 'MANUAL'>('MANUAL')
const showManualReceipt = ref(true)
const receiptOrderSort = ref<'DUE_ASC' | 'DUE_DESC' | 'DEFAULT'>('DUE_ASC')
const showReceiptDialog = ref(false)
const receiptDialogTrigger = ref<HTMLButtonElement | null>(null)
const manualReceiptOrderNos = ref<string[]>([])
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
const receiptDeliveryDate = ref('2026-06-13')
const currentReceipt = ref<CartonReceiptResponse | null>(null)
const receiptRecords = ref<CartonReceiptResponse[]>([])
const weeklyImportHistory = ref<CartonImportBatchResponse[]>([])
const inspectionImportHistory = ref<CartonImportBatchResponse[]>([])
const showInventoryImport = ref(false)
const inventoryMoreOpen = ref(false)
const showStocktake = ref(false)
const showInventoryOperation = ref(false)
const showInventoryRelocation = ref(false)
const relocationTarget = shallowRef<InventoryBalanceRow | null>(null)
const relocationLocation = ref('')
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
const inventoryOutboundReasons = ['客户要货', '补货', '借出', '调拨', '损耗', '其他'] as const
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
  rawMovementType?: CartonInventoryMovementResponse['movement_type']
  reversalOfMovementId?: string | null
}

const localMovements = reactive<InventoryMovementViewRow[]>(inventoryMovementDemo.map((row) => ({ ...row })))
interface InventoryBalanceRow {
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

interface ReceiptReviewLine extends ReceiptLineSeed {
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

interface OrderFormMaterialLine extends Omit<CartonMaterialLine, 'id'> {
  id: string
  dimensionUnit: string
  unitPrice: number
  currency: string
  priceSource: string
  note: string
}

const orderForm = reactive({
  customerCode: '',
  supplierId: '',
  contractNo: '',
  itemNo: '',
  productName: '',
  orderQuantity: 0,
  orderDate: new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' }),
  customerDueDate: '',
  dueDate: '2026-08-12',
  note: '',
  materials: [
    {
      id: 'FORM-MAT-1',
      packagingType: '外箱',
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
const canManageCustomers = computed(() =>
  authStore.can('carton_procurement:customer_manage', selectedFactoryId.value, 'carton')
  || authStore.can('carton_procurement:customer_manage', selectedFactoryId.value, 'pmc-warehouse'),
)
const canAdjustSubmittedOrders = computed(() =>
  authStore.can('carton_procurement:order_adjust', selectedFactoryId.value, 'carton')
  || authStore.can('carton_procurement:order_adjust', selectedFactoryId.value, 'pmc-warehouse'),
)
const canIssuePurchaseOrders = computed(() =>
  authStore.can('carton_procurement:order_write', selectedFactoryId.value, 'carton')
  || authStore.can('carton_procurement:order_write', selectedFactoryId.value, 'pmc-warehouse'),
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
const calculatedOrderDueDate = computed(() =>
  orderForm.customerDueDate
    ? derivePlanDueDate(orderForm.orderDate, orderForm.customerDueDate)
    : orderForm.dueDate,
)
const orderSafetyLeadWarning = computed(() =>
  safetyLeadWarning(orderForm.orderDate, orderForm.customerDueDate),
)
const calculatedAppendOrderDueDate = computed(() =>
  appendOrderCustomerDueDate.value && appendingOrderRecord.value
    ? derivePlanDueDate(appendingOrderRecord.value.order_date, appendOrderCustomerDueDate.value)
    : appendOrderDueDate.value,
)
const appendSafetyLeadWarning = computed(() =>
  safetyLeadWarning(
    appendingOrderRecord.value?.order_date ?? '',
    appendOrderCustomerDueDate.value,
  ),
)
const appendOrderGuidance = computed(() => {
  if (appendingOrderRecord.value?.status === 'COMPLETED') {
    return '该订单已经全部到货；追加后会自动恢复为“部分到货”，新增差额可继续登记入库。'
  }
  if (appendingOrderRecord.value?.status === 'PARTIALLY_RECEIVED') {
    return '该订单已有入库记录；追加只增加需求量，不修改既有入库流水，追加后仍为“部分到货”。'
  }
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
const visibleCustomerRecords = computed(() => {
  const term = customerSearch.value.trim().toLowerCase()
  if (!term) return customerRecords.value
  return customerRecords.value.filter((customer) => [
    customer.customer_name,
    customer.country_region,
    customer.contact_name,
    customer.contact_phone,
  ].join(' ').toLowerCase().includes(term))
})
const paperQualitySuggestions = computed(() => [...new Set(
  orderRecords.value.flatMap((order) => order.lines.map((line) => line.paper_quality.trim())).filter(Boolean),
)].slice(0, 30))
const specificationSuggestions = computed(() => [...new Set(
  orderRecords.value.flatMap((order) => order.lines.map((line) => line.specification.trim())).filter(Boolean),
)].slice(0, 30))

const activeTab = computed<CartonTab>(() => {
  const routeTab = route.query.tab
  return typeof routeTab === 'string' && validTabs.has(routeTab as CartonTab)
    ? routeTab as CartonTab
    : 'dashboard'
})

const activeTabItem = computed(() => tabs.find((tab) => tab.id === activeTab.value) ?? tabs[0])
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

const visibleWeeklyChecks = computed(() => localWeeklyChecks.filter((row) =>
  matchesCustomer(row.customer)
  && includesSearch([
    row.reference,
    row.poNumbers,
    row.customer,
    row.itemNo,
    row.productName,
    row.result,
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
  return orderRecords.value.find((order) =>
    (row?.order_id && order.id === row.order_id)
    || (row?.order_no && order.order_no === row.order_no)
    || (
      businessIdentity(order.contract_no) === businessIdentity(exception.contract_no || row?.contract_no || row?.reference)
      && businessIdentity(order.item_no) === businessIdentity(exception.item_no || row?.item_no)
    ),
  ) ?? null
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
  const actionable = businessOrderAlerts.value.filter((alert) => ['OPEN', 'IN_PROGRESS'].includes(alert.exception.status))
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
    const dateMatches = (!inventoryDateFrom.value || row.date >= inventoryDateFrom.value)
      && (!inventoryDateTo.value || row.date <= inventoryDateTo.value)
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
  matchesCustomer(row.customer)
  && includesSearch([row.customer, row.period, row.status]),
))

const visibleExceptions = computed(() => localExceptions.filter((row) =>
  matchesCustomer(row.customer)
  && includesSearch([row.id, row.customer, row.type, row.title, row.detail, row.status]),
))

const visibleReceiptLines = computed(() => {
  if (showReceiptDialog.value) return receiptLines
  const term = globalSearch.value.trim().toLowerCase()
  if (!term) return receiptLines
  return receiptLines.filter((row) => [
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
const visibleManualReceiptOrders = computed(() => manualReceiptOrders.value.filter((order) => {
  const term = globalSearch.value.trim().toLowerCase()
  const text = [order.order_no, order.customer_name, order.contract_no, order.item_no, order.product_name,
    ...order.lines.flatMap((line) => [line.packaging_type, line.paper_quality, line.specification])].join(' ').toLowerCase()
  return matchesCustomer(order.customer_name)
    && (!receiptPlannedDueFrom.value || order.due_date >= receiptPlannedDueFrom.value)
    && (!receiptPlannedDueTo.value || order.due_date <= receiptPlannedDueTo.value)
    && (!term || term.split(/\s+/).every((word) => text.includes(word)))
}))

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
  const lineIds = new Set(receiptLines
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
  matchesCustomer(row.customer)
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
  && receiptLines.length > 0
  && receiptLines.every((row) => receiptLineEffectiveQuantity(row) >= row.remainingQuantity),
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

const pendingOrderCount = computed(() => visibleOrders.value.filter((row) => row.status !== '已完成').length)
const weeklyRiskCount = computed(() => visibleWeeklyChecks.value.filter((row) => row.result !== '已匹配').length)
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
    return matchesCustomer(row.customer)
      && dateMatches
      && includesSearch(fields)
  })
})
const hasInventoryBalanceFilters = computed(() => Boolean(
  selectedCustomer.value !== '全部客户'
  || globalSearch.value.trim()
  || inventoryBalanceDateFrom.value
  || inventoryBalanceDateTo.value,
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

const inventoryBalance = computed(() => inventoryBalances.value.reduce((sum, row) => sum + row.balance, 0))

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
    status: receipt.status,
    sourceType: line.source_type,
    customer: line.customer_name,
    contractNo: line.contract_no,
    itemNo: line.item_no,
    paper: `${line.packaging_type} ${line.paper_quality}`.trim(),
    specification: line.specification,
    effectiveQuantity: Number(line.effective_quantity),
    unit: line.unit,
    location: line.location,
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

watch(selectedFactoryId, (factoryId) => {
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
  showManualReceipt.value = true
  showReceiptDialog.value = false
  manualReceiptOrderNos.value = []
  currentReceipt.value = null
  receiptDeliveryNoteNo.value = ''
  receiptDeliveryDate.value = new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
  selectedOrderNos.value = []
  historyItemSuggestions.value = []
  showHistoryItemSuggestions.value = false
  selectedHistoryItemSource.value = null
  selectedInventoryTargetIds.value = []
  inventoryBulkQuantities.value = {}
  showInventoryImport.value = false
  inventoryMoreOpen.value = false
  showStocktake.value = false
  showInventoryOperation.value = false
  showInventoryRelocation.value = false
  relocationTarget.value = null
  inventoryBalanceDateRange.value = { start: undefined, end: undefined }
  inventoryMovementDateRange.value = { start: undefined, end: undefined }
  orderStatusFilter.value = 'ALL'
  orderDueFilter.value = 'ALL'
  orderDateRange.value = { start: undefined, end: undefined }
  orderSort.value = 'DUE_ASC'
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

watch(selectedOrderNos, () => {
  if (!exportingSelectedOrders.value && !issuingSelectedPurchaseOrders.value) combinedPurchaseOrderMessage.value = ''
}, { deep: true })

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
  receiptCorrectionNote.value = ''
  const orders = manualReceiptOrders.value.filter((item) => orderNos.includes(item.order_no))
  currentReceipt.value = null
  receiptLines.splice(0)
  if (!orders.length) {
    actionMessage.value = manualReceiptOrders.value.length
      ? '请至少选择一张需要登记收料的正式订单。'
      : '当前没有待收料的正式订单。'
    return
  }
  receiptLines.push(...orders.flatMap((order) => order.lines
    .filter((line) => Number(line.remaining_quantity) > 0)
    .map((line) => ({
        id: `MANUAL-${line.id}`,
        orderNo: `${order.order_no} · ${order.contract_no}-${order.item_no}`,
        description: `${line.packaging_type} ${line.paper_quality}`.trim(),
        specification: `${line.specification}${line.dimension_unit ? ` ${line.dimension_unit}` : ''}`,
        deliveryQuantity: Number(line.remaining_quantity),
        unitPrice: Number(line.unit_price),
        receivedQuantity: Number(line.remaining_quantity),
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
  receiptDeliveryNoteNo.value = ''
  receiptDeliveryDate.value = new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
  actionMessage.value = `已批量载入 ${orders.length} 张订单的 ${receiptLines.length} 条待收纸品；默认全量收料，可逐行修改。`
}

function restoreReceiptFocus(event: Event) {
  event.preventDefault()
  receiptDialogTrigger.value?.focus()
}

function clearReceiptPlannedDueRange() {
  receiptDueCalendarValue.value = { start: undefined, end: undefined }
}

function clearReceiptOrderFilters() {
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
  showManualReceipt.value = true
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

function returnToPendingReceiptOrders() {
  receiptEntryMode.value = 'MANUAL'
  showManualReceipt.value = true
  showReceiptDialog.value = false
  receiptFeedbackMessage.value = ''
  receiptImportBatch.value = null
  receiptImportRows.value = []
  receiptBatchId.value = ''
  selectedReceiptFileName.value = ''
  manualReceiptOrderNos.value = []
  currentReceipt.value = null
  receiptLines.splice(0)
  receiptDeliveryNoteNo.value = ''
  receiptDeliveryDate.value = new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
}

function cancelManualReceipt() {
  showReceiptDialog.value = false
  receiptEntryMode.value = 'IMPORT'
  receiptFeedbackMessage.value = ''
  showManualReceipt.value = false
  manualReceiptOrderNos.value = []
  currentReceipt.value = null
  receiptLines.splice(0)
  receiptDeliveryNoteNo.value = ''
  receiptDeliveryDate.value = ''
  receiptBatchId.value = ''
  void loadBackendData()
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

function calculateRequiredQuantity(unitsPerCarton: number, orderQuantity: number) {
  const normalizedUnitsPerCarton = Number(unitsPerCarton || 0)
  const normalizedOrderQuantity = Number(orderQuantity || 0)
  if (normalizedUnitsPerCarton <= 0 || normalizedOrderQuantity <= 0) return 0
  const result = normalizedOrderQuantity / normalizedUnitsPerCarton
  const nearestInteger = Math.round(result)
  return Math.abs(result - nearestInteger) < 1e-8 ? nearestInteger : Math.ceil(result)
}

function formatRequiredQuantity(unitsPerCarton: number, orderQuantity: number) {
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

function derivePlanDueDate(orderDate: string, customerDueDate: string) {
  const leadAdjustedDate = dateOffsetIso(customerDueDate, -DEFAULT_CARTON_SAFETY_LEAD_DAYS)
  if (!orderDate || !leadAdjustedDate) return ''
  return leadAdjustedDate < orderDate ? orderDate : leadAdjustedDate
}

function safetyLeadWarning(orderDate: string, customerDueDate: string) {
  if (!orderDate || !customerDueDate) return ''
  const availableDays = calendarDayDifference(orderDate, customerDueDate)
  if (availableDays === null || availableDays < 0 || availableDays >= DEFAULT_CARTON_SAFETY_LEAD_DAYS) return ''
  return `客户交期距下单仅 ${availableDays} 天，不足默认 ${DEFAULT_CARTON_SAFETY_LEAD_DAYS} 天安全提前量；计划交期已设为下单当天，请重点跟进。`
}

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

function canAppendOrder(orderNo: string) {
  const status = rawOrderStatus(orderNo)
  return status === 'CONFIRMED'
    || (['PENDING_SUPPLIER', 'PARTIALLY_RECEIVED', 'COMPLETED'].includes(status) && canAdjustSubmittedOrders.value)
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
    orderQuantity: Number(row.product_order_quantity),
    materials: row.lines.map((line) => ({
      id: line.id,
      packagingType: line.packaging_type,
      paperQuality: line.paper_quality,
      specification: `${line.specification}${line.dimension_unit ? ` ${line.dimension_unit}` : ''}`,
      unitsPerCarton: Number(line.usage_quantity),
      unit: line.unit,
    })),
    dueDate: row.due_date,
    status: orderStatusLabel(row.status),
    tone: orderTone(row.status),
    note: row.note,
  }
}

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
        : row.reason,
    rawMovementType: row.movement_type,
    reversalOfMovementId: row.reversal_of_movement_id,
  }
}

function mapInventoryBalance(row: CartonInventoryBalanceResponse): InventoryBalanceRow {
  return {
    id: row.order_line_id || [
      row.customer_code,
      row.contract_no,
      row.item_no,
      row.packaging_type,
      row.paper_quality,
      row.specification,
      row.unit,
    ].join('|'),
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
  } as Record<string, string>)[row.match_status ?? ''] ?? '待核对'
  const tone: CartonTone = row.match_status === 'MATCHED'
    ? 'green'
    : row.match_status === 'MISSING_ORDER'
      ? 'red'
      : 'amber'
  return {
    id: `WK-${row.source_sheet ?? 'S'}-${row.source_row ?? index + 1}`,
    reference: row.reference ?? row.contract_no ?? '',
    poNumbers: row.po_numbers ?? '',
    customer: row.customer_name || '待识别客户',
    itemNo: row.item_no ?? '',
    productName: row.product_name ?? '',
    quantity: Number(row.quantity ?? 0),
    cartonRule: row.carton_rule ?? '',
    inspectionWindow: row.inspection_window ?? '',
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
  const rows = batch.parse_summary.rows ?? []
  receiptEntryMode.value = 'IMPORT'
  receiptFeedbackMessage.value = ''
  showManualReceipt.value = false
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
  actionMessage.value = '已把未匹配明细加入非正式/打板收料；请补齐客户与物料信息，保存后仍需再次人工确认才会入库并计入月结。'
}

function removeAdHocReceiptLine(lineId: string) {
  const index = receiptLines.findIndex((line) => line.id === lineId && line.sourceType === 'AD_HOC')
  if (index < 0 || currentReceipt.value) return
  receiptLines.splice(index, 1)
  receiptFeedbackMessage.value = ''
}

async function loadBackendData(factoryId = selectedFactoryId.value) {
  if (backendLoading.value) return
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
    if (!selectedWeeklyFileName.value) {
      if (weeklyImports[0]) restoreWeeklyImport(weeklyImports[0])
      else localWeeklyChecks.splice(0)
    }
    if (!selectedInspectionFileName.value) {
      if (inspectionImports[0]) restoreInspectionImport(inspectionImports[0])
      else localInspectionChecks.splice(0)
    }
    if (receiptEntryMode.value === 'MANUAL' && !manualReceiptOrderNos.value.length && !currentReceipt.value) {
      receiptLines.splice(0)
    }
    if (receiptEntryMode.value === 'IMPORT' && !receiptBatchId.value) {
      receiptLines.splice(0)
      receiptDeliveryNoteNo.value = ''
      receiptDeliveryDate.value = ''
      if (latestReceiptImport) {
        selectedReceiptFileName.value = latestReceiptImport.original_filename
        applyReceiptImport(latestReceiptImport)
      }
    }
    apiConnected.value = true
    actionMessage.value = receiptEntryMode.value === 'IMPORT' && latestReceiptImport && activeTab.value === 'receipts'
      ? `已恢复最近送货单导入：共 ${latestReceiptImport.parse_summary.row_count ?? 0} 行，已匹配 ${latestReceiptImport.parse_summary.matched_count ?? 0} 行，${latestReceiptImport.parse_summary.issue_count ?? 0} 行需要人工处理。`
      : `已连接 ${activeFactory.value.shortName} 正式台账；订单、收料导入、库存流水和月结均由后端保存。`
  } catch (error) {
    customerRecords.value = demoCustomers(factoryId)
    if (!orderForm.customerCode) orderForm.customerCode = customerRecords.value[0]?.customer_code ?? ''
    apiConnected.value = false
    actionMessage.value = `后端暂不可用，当前显示只读演示数据：${getApiErrorMessage(error)}`
  } finally {
    backendLoading.value = false
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
    && material.paperQuality.trim()
    && material.specification.trim()
    && Number(material.unitsPerCarton) > 0,
  )
  const currentOrder = editingOrderRecord.value
  const selectedCustomer = selectedOrderCustomer.value
    ?? (currentOrder && currentOrder.customer_code === orderForm.customerCode ? {
      customer_code: currentOrder.customer_code,
      customer_name: currentOrder.customer_name,
    } : null)
  if (!selectedCustomer) {
    actionMessage.value = '当前厂区没有可用客户，请先由纸箱部主管在“客户资料维护”中新增或启用客户。'
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
  if (!Number.isFinite(Number(orderForm.orderQuantity)) || Number(orderForm.orderQuantity) <= 0) {
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
    actionMessage.value = '该货号尚无历史品名，请先填写产品名称；后续再用同一货号时会自动带出。'
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
      item_no: orderForm.itemNo.trim(),
      product_name: orderForm.productName.trim(),
      product_order_quantity: Number(orderForm.orderQuantity),
      order_date: orderForm.orderDate,
      customer_due_date: orderForm.customerDueDate || null,
      due_date: calculatedOrderDueDate.value,
      note: orderForm.note.trim(),
      lines: validMaterials.map((material) => ({
        packaging_type: material.packagingType.trim(),
        paper_quality: material.paperQuality.trim(),
        specification: material.specification.trim(),
        dimension_unit: material.dimensionUnit,
        usage_quantity: Number(material.unitsPerCarton),
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
    actionMessage.value = `订单 ${saved.order_no} 已确认并锁定普通编辑；尚未收料时仅主管可追加或减单。`
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
  cancelOrderReason.value = ''
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
    ORDER_CREATED: '订单创建确认',
    ORDER_SUBMITTED_SUPPLIER: '确认订单并锁定',
    ORDER_UPDATED: '订单修改',
    ORDER_APPENDED: '追加订单',
    ORDER_REDUCED: '订单减单 / 退单',
    ORDER_CANCELLED: '订单取消',
    ORDER_RETURNED: '订单退单',
    RECEIPT_CREATED: '收料单创建',
    RECEIPT_DRAFT_CREATED: '收料草稿创建',
    RECEIPT_CONFIRMED: '收料确认入库',
    RECEIPT_REVERSED: '收料作废 / 冲销',
    INVENTORY_MOVEMENT_CREATED: '库存流水登记',
    INVENTORY_PRICE_CONFIRMED: '入库单价核实',
    INVENTORY_LOCATION_CHANGED: '库存调仓',
    STOCKTAKE_CREATED: '生成盘点单',
    STOCKTAKE_SAVE: '盘点草稿保存',
    STOCKTAKE_SUBMIT: '盘点提交复核',
    STOCKTAKE_APPROVE: '盘点复核入账',
    STOCKTAKE_RETURN: '盘点退回重盘',
    STOCKTAKE_CANCEL: '盘点取消',
    INVENTORY_BULK_OUTBOUND_CREATED: '批量出库',
    INVENTORY_MOVEMENT_REVERSED: '库存流水冲销',
    HISTORY_INVENTORY_IMPORTED: '历史库存导入',
    IMPORT_BATCH_CREATED: '导入批次创建',
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
  cancelOrderReason.value = ''
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
  selectedCustomer.value = '全部客户'
  globalSearch.value = ''
  inventoryBalanceDateRange.value = { start: undefined, end: undefined }
}

function openAppendOrder(orderNo: string) {
  const order = orderRecords.value.find((item) => item.order_no === orderNo)
  if (!order || !canAppendOrder(orderNo)) {
    actionMessage.value = ['PENDING_SUPPLIER', 'PARTIALLY_RECEIVED', 'COMPLETED'].includes(order?.status ?? '')
      ? '确认锁定后的订单只有主管可以追加。'
      : '该订单当前不能追加。'
    return
  }
  appendOrderNo.value = orderNo
  appendOrderQuantity.value = 0
  appendOrderReason.value = DEFAULT_APPEND_ORDER_REASON
  appendOrderCustomerDueDate.value = order.customer_due_date ?? ''
  appendOrderDueDate.value = order.due_date
}

async function confirmAppendOrder() {
  const order = orderRecords.value.find((item) => item.order_no === appendOrderNo.value)
  if (!order || appendOrderQuantity.value <= 0) {
    actionMessage.value = '追加数量必须大于 0。'
    return
  }
  if (appendOrderCustomerDueDate.value && appendOrderCustomerDueDate.value < order.order_date) {
    actionMessage.value = '追加订单的客户交期不能早于原订单的下单日期。'
    return
  }
  appendingOrder.value = true
  try {
    const wasCompleted = order.status === 'COMPLETED'
    const saved = await cartonProcurementApi.appendOrder(
      selectedFactoryId.value,
      order,
      appendOrderQuantity.value,
      appendOrderReason.value.trim() || DEFAULT_APPEND_ORDER_REASON,
      calculatedAppendOrderDueDate.value,
      appendOrderCustomerDueDate.value,
    )
    replaceOrderState(saved)
    appendOrderNo.value = ''
    await loadBackendData()
    actionMessage.value = wasCompleted
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
      ? '只有主管可以减少未入库数量，且不能低于已入库及待确认收料数量。'
      : '当前订单状态不能减单。'
    return
  }
  reduceOrderNo.value = orderNo
  reduceOrderQuantity.value = 0
  reduceOrderReason.value = DEFAULT_REDUCE_ORDER_REASON
}

async function confirmReduceOrder() {
  const order = orderRecords.value.find((item) => item.order_no === reduceOrderNo.value)
  const maximumReduction = order ? maximumReducibleProductQuantity(order) : 0
  if (!order || reduceOrderQuantity.value <= 0 || reduceOrderQuantity.value > maximumReduction) {
    actionMessage.value = `减单数量必须大于 0，且不能超过可减数量 ${formatNumber(maximumReduction)}。`
    return
  }
  const reductionQuantity = reduceOrderQuantity.value
  reducingOrder.value = true
  try {
    const wasPartiallyReceived = order.status === 'PARTIALLY_RECEIVED'
    const saved = await cartonProcurementApi.reduceOrder(
      selectedFactoryId.value,
      order,
      reductionQuantity,
      reduceOrderReason.value.trim() || DEFAULT_REDUCE_ORDER_REASON,
    )
    replaceOrderState(saved)
    reduceOrderNo.value = ''
    await loadBackendData()
    actionMessage.value = saved.status === 'CANCELLED'
      ? `订单 ${saved.order_no} 已减至 0 并转为已取消（退单），操作记录已保存。`
      : wasPartiallyReceived && saved.status === 'COMPLETED'
        ? `订单 ${saved.order_no} 已退掉全部未入库数量，现有入库量已满足调整后订单，状态转为“全部到货”。`
        : `订单 ${saved.order_no} 已减少 ${formatNumber(reductionQuantity)} 件，纸箱需求量已重新计算并留痕。`
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

function signedQuantity(value: string | number) {
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
    downloadWorkbook(blob, `${issue.document_no}_${purchaseOrderTypeLabel(issue.document_type)}.xlsx`)
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

  importingHistoryOrders.value = true
  try {
    const result = await cartonProcurementApi.uploadHistoryOrders(selectedFactoryId.value, file)
    const orders = await cartonProcurementApi.listOrders(selectedFactoryId.value)
    orderRecords.value = orders
    localOrders.splice(0, localOrders.length, ...orders.map(mapOrder))
    apiConnected.value = true
    const skipped = result.skipped_count ? `，跳过 ${result.skipped_count} 张重复订单` : ''
    actionMessage.value = `历史订单“${result.original_filename}”导入完成：新增 ${result.imported_count} 张订单、${result.imported_line_count} 条纸品明细${skipped}。`
  } catch (error) {
    actionMessage.value = `历史订单导入失败：${getApiErrorMessage(error)}`
  } finally {
    importingHistoryOrders.value = false
  }
}

function mapInspectionPreview(row: CartonImportPreviewRow, index: number): InspectionReminderRow {
  const result = ({
    READY: '纸箱已备齐',
    UPCOMING: '待提前交货',
    DUE_SOON: '交货临近',
    OVERDUE: '交货已逾期',
    MISSING_ORDER: '疑似漏单',
    AMBIGUOUS: '待人工关联',
    INVALID_DATE: '日期待补充',
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

function triggerHistoryInventoryImport() {
  historyInventoryFileInput.value?.click()
}

async function handleHistoryInventoryFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (!/\.(xlsx|xlsm|xls)$/i.test(file.name)) {
    actionMessage.value = '历史库存仅支持 Excel 文件，请使用系统映射模板填写后再导入。'
    return
  }

  importingHistoryInventory.value = true
  try {
    const result = await cartonProcurementApi.uploadHistoryInventory(selectedFactoryId.value, file)
    const [movements, balances] = await Promise.all([
      cartonProcurementApi.listMovements(selectedFactoryId.value),
      cartonProcurementApi.listInventoryBalances(selectedFactoryId.value),
    ])
    localMovements.splice(0, localMovements.length, ...movements.map(mapMovement))
    localInventoryBalances.splice(0, localInventoryBalances.length, ...balances.map(mapInventoryBalance))
    apiConnected.value = true
    const matched = result.matched_order_line_count
      ? `，关联正式订单明细 ${result.matched_order_line_count} 行`
      : ''
    const standalone = result.standalone_count
      ? `，独立旧库存 ${result.standalone_count} 行`
      : ''
    const skipped = result.skipped_count ? `，跳过重复 ${result.skipped_count} 行` : ''
    actionMessage.value = result.duplicate
      ? `历史库存“${result.original_filename}”已导入过，本次未重复入账。`
      : `历史库存“${result.original_filename}”导入完成：新增 ${result.imported_count} 笔期初流水${matched}${standalone}${skipped}。`
  } catch (error) {
    actionMessage.value = `历史库存导入失败：${getApiErrorMessage(error)}`
  } finally {
    importingHistoryInventory.value = false
  }
}

function openInventoryRelocation(row: InventoryBalanceRow, event: Event) {
  inventoryDialogTrigger.value = event.currentTarget as HTMLElement | null
  relocationTarget.value = { ...row }
  relocationLocation.value = ''
  relocationNote.value = ''
  relocationFeedback.value = ''
  showInventoryRelocation.value = true
}

async function submitInventoryRelocation() {
  const target = relocationTarget.value
  const factoryId = selectedFactoryId.value
  if (!target || relocationBusy.value) return
  const location = relocationLocation.value.trim()
  if (!location || location === target.location) {
    relocationFeedback.value = !location ? '请填写目标仓位。' : '目标仓位与当前仓位相同。'
    return
  }
  relocationBusy.value = true
  relocationFeedback.value = ''
  try {
    const balance = await cartonProcurementApi.relocateInventory({
      factory_id: factoryId,
      reference_movement_id: target.latestMovementId,
      expected_location_revision: target.locationRevision,
      location,
      note: relocationNote.value.trim(),
    })
    if (selectedFactoryId.value !== factoryId || relocationTarget.value !== target) return
    const index = localInventoryBalances.findIndex((row) => row.id === target.id)
    if (index >= 0) localInventoryBalances[index] = mapInventoryBalance(balance)
    actionMessage.value = `调仓完成：${target.location || '未设置仓位'} → ${location}，库存数量不变。`
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

function setInventoryOperationType(type: 'OUTBOUND' | 'ADJUSTMENT') {
  inventoryOperationType.value = type
  inventoryOperationReason.value = type === 'OUTBOUND' ? '客户要货' : ''
  selectedInventoryTargetIds.value = []
  selectInventoryTarget('')
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
  const [movements, balances, audits] = await Promise.all([
    cartonProcurementApi.listMovements(factoryId),
    cartonProcurementApi.listInventoryBalances(factoryId),
    cartonProcurementApi.listAuditEvents(factoryId),
  ])
  if (selectedFactoryId.value !== factoryId) return
  localMovements.splice(0, localMovements.length, ...movements.map(mapMovement))
  localInventoryBalances.splice(0, localInventoryBalances.length, ...balances.map(mapInventoryBalance))
  inventoryReportRefreshKey.value += 1
  auditRecords.value = audits
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
      quantity: amount,
      location: inventoryOperationLocation.value.trim(),
      document_no: inventoryOperationDocumentNo.value.trim(),
      reason: inventoryOperationReason.value.trim(),
    })
    if (selectedFactoryId.value !== factoryId) return
    // A successful write stays successful even if the following read fails.
    inventoryOperationQuantity.value = 0
    inventoryOperationDocumentNo.value = ''
    inventoryOperationReason.value = inventoryOperationType.value === 'OUTBOUND' ? '客户要货' : ''
    inventoryOperationFeedback.value = `${action}已登记，系统已新增不可变流水。`
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
      items: rows.map((row) => ({
        order_line_id: row.orderLineId,
        reference_movement_id: row.orderLineId ? null : row.latestMovementId,
        quantity: Number(inventoryBulkQuantities.value[row.id]),
        location: row.location,
      })),
    })
    if (selectedFactoryId.value !== factoryId) return
    selectedInventoryTargetIds.value = []
    inventoryBulkQuantities.value = {}
    inventoryOperationDocumentNo.value = ''
    inventoryOperationReason.value = '客户要货'
    inventoryOperationFeedback.value = `已按填写数量批量出库 ${rows.length} 条记录。`
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
    && ['OUTBOUND', 'ADJUSTMENT'].includes(row.rawMovementType ?? '')
    && !localMovements.some((candidate) => candidate.reversalOfMovementId === row.id)
}

function openInventoryReversal(row: InventoryMovementViewRow) {
  reversingMovementId.value = row.id
  reversalReason.value = ''
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
  receiptCorrectionReason.value = ''
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
  showManualReceipt.value = true
  receiptBatchId.value = ''
  manualReceiptOrderNos.value = linkedOrders.map((order) => order.order_no)
  currentReceipt.value = reenter ? null : receipt
  receiptCorrectionNote.value = reenter ? `更正原收料单 ${receipt.receipt_no}；原送货单号 ${receipt.delivery_note_no}；原单已作废或冲销。` : receipt.note.startsWith('更正原收料单') ? receipt.note : ''
  // Keep the original business document immutable; a correction uses an explicit distinct registration identifier.
  const suffix = `-更正-${receipt.receipt_no}`
  receiptDeliveryNoteNo.value = reenter ? `${receipt.delivery_note_no.slice(0, 128 - suffix.length)}${suffix}` : receipt.delivery_note_no
  receiptDeliveryDate.value = receipt.delivery_date
  receiptLines.splice(0, receiptLines.length, ...receipt.lines.map((line) => ({
    id: `HISTORY-${line.id}`, orderNo: receipt.receipt_no, sourceType: line.source_type || 'FORMAL_ORDER',
    orderLineId: line.order_line_id || '', customerCode: line.customer_code, contractNo: line.contract_no,
    itemNo: line.item_no, description: `${line.packaging_type} ${line.paper_quality}`, packagingType: line.packaging_type,
    paperQuality: line.paper_quality, specification: line.specification, unit: line.unit, currency: line.currency,
    unitPrice: Number(line.unit_price), deliveryQuantity: Number(line.delivered_quantity),
    receivedQuantity: Number(line.received_quantity), damagedQuantity: Number(line.damaged_quantity),
    rejectedQuantity: Number(line.rejected_quantity), unusableQuantity: Number(line.unusable_quantity), location: line.location,
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

function openCustomerManager() {
  resetCustomerForm()
  customerSearch.value = ''
  showCustomerModal.value = true
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
  if (!customerForm.customer_name.trim()) {
    actionMessage.value = '请填写客户名称。'
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
    const current = customerRecords.value.find((customer) => customer.id === editingCustomerId.value)
    const saved = current
      ? await cartonProcurementApi.updateCustomer(current, payload)
      : await cartonProcurementApi.createCustomer(payload)
    const index = customerRecords.value.findIndex((customer) => customer.id === saved.id)
    if (index >= 0) customerRecords.value.splice(index, 1, saved)
    else customerRecords.value.push(saved)
    customerRecords.value.sort((left, right) => left.customer_name.localeCompare(right.customer_name, 'zh-CN'))
    if (!orderForm.customerCode && saved.status === 'ACTIVE') orderForm.customerCode = saved.customer_code
    actionMessage.value = current
      ? `客户 ${saved.customer_name} 的资料已更新。`
      : `客户 ${saved.customer_name} 已加入 ${activeFactory.value.shortName} 客户主数据。`
    resetCustomerForm()
  } catch (error) {
    actionMessage.value = `客户资料未保存：${getApiErrorMessage(error)}`
  } finally {
    savingCustomer.value = false
  }
}

async function removeCustomer(customer: CartonCustomerResponse) {
  if (!window.confirm(`确定删除客户“${customer.customer_name}”吗？已有订单的客户不能删除，只能停用。`)) return
  deletingCustomerId.value = customer.id
  try {
    await cartonProcurementApi.deleteCustomer(selectedFactoryId.value, customer.id)
    customerRecords.value = customerRecords.value.filter((item) => item.id !== customer.id)
    if (orderForm.customerCode === customer.customer_code) {
      orderForm.customerCode = activeCustomers.value[0]?.customer_code ?? ''
    }
    if (editingCustomerId.value === customer.id) resetCustomerForm()
    actionMessage.value = `客户 ${customer.customer_name} 已删除。`
  } catch (error) {
    actionMessage.value = `客户未删除：${getApiErrorMessage(error)}`
  } finally {
    deletingCustomerId.value = ''
  }
}

async function issueSelectedPurchaseOrders() {
  if (!selectedOrderNos.value.length || issuingSelectedPurchaseOrders.value) return
  if (!apiConnected.value) {
    combinedPurchaseOrderTone.value = 'error'
    combinedPurchaseOrderMessage.value = '后端未连接，当前演示订单不能发行供应商采购单。'
    return
  }
  const orders = selectedOrders.value
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
      cartonProcurementApi.getPurchaseOrderContext(selectedFactoryId.value, order.order_no),
    ))
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
      const confirmed = window.confirm(
        `本次选择包含 ${warningContexts.length} 张非首次或已发行采购单：${preview}${remaining > 0 ? `，另有 ${remaining} 张` : ''}。\n其中${warningSummary}；系统不会重复编号。供应商仍只按各采购单的“本次箱数变化”执行。是否继续生成？`,
      )
      if (!confirmed) {
        combinedPurchaseOrderTone.value = 'progress'
        combinedPurchaseOrderMessage.value = '已取消批量发行，没有生成新的供应商采购单。'
        return
      }
    }
    combinedPurchaseOrderMessage.value = `正在处理 ${orders.length} 张所选订单${nonInitialContexts.length ? `，其中 ${nonInitialContexts.length} 张生成非首次采购单` : ''}${reusedContexts.length ? `、${reusedContexts.length} 张重新打包历史快照` : ''}…`
    const result = await cartonProcurementApi.issuePurchaseOrders(selectedFactoryId.value, orders)
    downloadWorkbook(result.blob, `供应商采购单批次_${businessTodayIso()}.xlsx`)
    const skippedCount = Math.max(0, orders.length - result.issueCount)
    const reusedCount = Math.min(reusedContexts.length, result.issueCount)
    const createdCount = Math.max(0, result.issueCount - reusedCount)
    combinedPurchaseOrderTone.value = 'success'
    combinedPurchaseOrderMessage.value = `批次文件包含 ${result.issueCount} 份供应商采购单：新发行 ${createdCount} 份${reusedCount ? `，重新打包历史快照 ${reusedCount} 份` : ''}${skippedCount ? `；跳过 ${skippedCount} 张既无变化也无历史采购单的订单` : ''}。供应商只按“本次箱数变化”执行。`
    actionMessage.value = `已生成 ${result.issueCount} 份不可变供应商采购单的批次文件。`
  } catch (error) {
    const message = `供应商采购单批量发行失败：${await getApiErrorMessageAsync(error)}`
    combinedPurchaseOrderTone.value = 'error'
    combinedPurchaseOrderMessage.value = message
    actionMessage.value = message
  } finally {
    issuingSelectedPurchaseOrders.value = false
  }
}

function resetOrderForm() {
  const remembered = readOrderFormMemory()
  editingOrderNo.value = ''
  orderChangeReason.value = ''
  orderForm.customerCode = activeCustomers.value[0]?.customer_code ?? ''
  orderForm.supplierId = ''
  orderForm.contractNo = ''
  orderForm.itemNo = ''
  orderForm.productName = ''
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
    packagingType: remembered?.packagingType ?? '外箱',
    paperQuality: remembered?.paperQuality ?? '',
    specification: remembered?.specification ?? '',
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
    unitsPerCarton: Number(line.usage_quantity),
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
  actionMessage.value = `已复用历史货号 ${suggestion.item_no} 最近订单 ${suggestion.latest_order_no} 的客户、品名和 ${suggestion.lines.length} 条纸品资料；本次合同、数量和日期未覆盖。`
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
  orderChangeReason.value = ''
  orderForm.customerCode = order.customer_code
  orderForm.supplierId = order.supplier_id
  orderForm.contractNo = order.contract_no
  orderForm.itemNo = order.item_no
  orderForm.productName = order.product_name
  orderForm.orderQuantity = Number(order.product_order_quantity)
  orderForm.orderDate = order.order_date
  orderForm.customerDueDate = order.customer_due_date ?? ''
  orderForm.dueDate = order.due_date
  orderForm.note = order.note
  orderForm.materials.splice(0, orderForm.materials.length, ...order.lines.map((line) => ({
    id: line.id,
    packagingType: line.packaging_type,
    paperQuality: line.paper_quality,
    specification: line.specification,
    unitsPerCarton: Number(line.usage_quantity),
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
  if (alert.kind === 'QUANTITY_INCREASE' && alert.orderStatus === 'CONFIRMED') return '追加订单'
  if (alert.kind === 'QUANTITY_DECREASE' && alert.orderStatus === 'CONFIRMED') {
    return alert.scheduleQuantity <= 0 ? '取消订单' : '调整订单数量'
  }
  if (alert.kind === 'QUANTITY_DECREASE' && ['PARTIALLY_RECEIVED', 'COMPLETED'].includes(alert.orderStatus)) return '退单'
  if (alert.orderNo) return alert.orderStatus === 'PENDING_SUPPLIER' ? '查看锁定订单' : '查看订单'
  return '核对提醒'
}

function businessAlertActionDisabled(alert: BusinessOrderAlert) {
  return !apiConnected.value || ['RESOLVED', 'CLOSED'].includes(alert.exception.status)
}

function openBusinessAlertException(alert: BusinessOrderAlert) {
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
    orderStatusFilter.value = 'ALL'
    setActiveTab('orders')
    void nextTick(() => {
      actionMessage.value = `订单 ${alert.order!.order_no} 已经入库，禁止追加、减单或退单；如有差异请按库存冲销流程处理。`
    })
    return
  }

  if (alert.orderNo) {
    globalSearch.value = alert.orderNo
    orderStatusFilter.value = 'ALL'
    setActiveTab('orders')
    void nextTick(() => {
      actionMessage.value = alert.orderStatus === 'PENDING_SUPPLIER'
        ? `订单 ${alert.orderNo} 已确认锁定；仅主管可在尚未收料时追加或减单。`
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
    packagingType: '滑板纸',
    paperQuality: '',
    specification: '',
    unitsPerCarton: 1,
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
  const rows = batch.parse_summary.rows ?? []
  selectedWeeklyFileName.value = batch.original_filename
  localWeeklyChecks.splice(0, localWeeklyChecks.length, ...rows.map(mapWeeklyPreview))
  actionMessage.value = `已查看 ${batch.original_filename} 的历史核对结果：${batch.parse_summary.row_count ?? rows.length} 行。`
}

function restoreInspectionImport(batch: CartonImportBatchResponse) {
  const rows = batch.parse_summary.rows ?? []
  selectedInspectionFileName.value = batch.original_filename
  inspectionAdvanceDays.value = batch.parse_summary.advance_days ?? inspectionAdvanceDays.value
  localInspectionChecks.splice(0, localInspectionChecks.length, ...rows.map(mapInspectionPreview))
  actionMessage.value = `已查看 ${batch.original_filename} 的历史交期提醒：${batch.parse_summary.reminder_count ?? rows.length} 条。`
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
  receiptFeedbackMessage.value = ''
  if (!receiptLines.length) {
    setReceiptFeedback(receiptEntryMode.value === 'MANUAL'
      ? '当前没有可登记的订单明细，请先选择待收料订单。'
      : '当前没有已复核的送货明细；导入文件后须先完成字段匹配，才能提交正式收料反馈。')
    return
  }
  if (receiptEntryMode.value === 'IMPORT' && !receiptBatchId.value) {
    setReceiptFeedback('保存未完成：请先导入送货单并完成订单纸品匹配。')
    return
  }
  if (receiptLines.some((row) => row.sourceType === 'FORMAL_ORDER' && !row.orderLineId)) {
    setReceiptFeedback('保存未完成：正式订单收料必须先完成订单纸品匹配。')
    return
  }
  const incompleteAdHocLine = receiptLines.find((row) => row.sourceType === 'AD_HOC' && [
    row.customerCode,
    row.itemNo,
    row.packagingType,
    row.paperQuality,
    row.specification,
    row.unit,
  ].some((value) => !value.trim()))
  if (incompleteAdHocLine) {
    setReceiptFeedback('保存未完成：非正式/打板收料必须补齐客户、货号、纸品类型、纸质、规格和单位。')
    return
  }
  if (receiptUnsubmittedOrderNos.value.length) {
    setReceiptFeedback(`保存未完成：订单 ${receiptUnsubmittedOrderNos.value.join('、')} 尚未确认锁定，必须先确认订单并锁定后才能登记收料。`)
    return
  }
  if (!receiptDeliveryNoteNo.value.trim()) {
    setReceiptFeedback('保存未完成：请先填写送货单号（送货单当前显示“待识别”）。')
    focusReceiptField(manualDeliveryNoteInput.value)
    return
  }
  if (!receiptDeliveryDate.value) {
    setReceiptFeedback('保存未完成：请先填写送货日期。')
    focusReceiptField(manualDeliveryDateInput.value)
    return
  }
  if (receiptLines.some((row) => Number(row.damagedQuantity) + Number(row.rejectedQuantity) + Number(row.unusableQuantity) > Number(row.receivedQuantity))) {
    setReceiptFeedback('保存未完成：破损、拒收和其他不可用数量之和不能大于实收数量。')
    return
  }
  if (receiptLines.some((row) => Number(row.receivedQuantity) > Number(row.deliveryQuantity))) {
    setReceiptFeedback('保存未完成：实收数量不能大于送货数量。')
    return
  }
  if (receiptEntryMode.value === 'MANUAL' && receiptLines.some((row) => row.sourceType === 'FORMAL_ORDER' && receiptLineEffectiveQuantity(row) > row.remainingQuantity)) {
    setReceiptFeedback('保存未完成：人工录入的有效收料不能大于该订单明细当前待收数量。')
    return
  }
  const linesToSubmit = receiptLines.filter((row) => Number(row.deliveryQuantity) > 0 || Number(row.receivedQuantity) > 0)
  if (!linesToSubmit.length) {
    setReceiptFeedback('保存未完成：请至少填写一条大于 0 的送货或实收数量。')
    return
  }
  const invalidPriceLine = linesToSubmit.find((row) => {
    const price = String(row.unitPrice ?? '').trim()
    return price !== '' && !/^\d{1,12}(\.\d{1,6})?$/.test(price)
  })
  if (invalidPriceLine) {
    setReceiptFeedback('保存未完成：单价须为非负数字，最多 12 位整数和 6 位小数；暂不清楚价格可留空待核价。')
    return
  }
  savingReceipt.value = true
  try {
    currentReceipt.value = await cartonProcurementApi.createReceipt({
      factory_id: selectedFactoryId.value,
      delivery_note_no: receiptDeliveryNoteNo.value.trim(),
      delivery_date: receiptDeliveryDate.value,
      import_batch_id: receiptEntryMode.value === 'MANUAL' ? null : receiptBatchId.value,
      note: receiptCorrectionNote.value || (receiptEntryMode.value === 'MANUAL'
        ? `人工批量录入订单收料：${manualReceiptOrderNos.value.join('、')}`
        : `来源文件：${selectedReceiptFileName.value}；已逐行人工复核；非正式/打板明细 ${adHocReceiptLineCount.value} 行`),
      lines: linesToSubmit.map((row) => ({
        source_type: row.sourceType,
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
        unit_price: Number(row.unitPrice),
        location: row.location,
        feedback_note: row.sourceType === 'AD_HOC'
          ? '送货单未匹配正式订单，作为非正式/打板收料人工复核'
          : receiptEntryMode.value === 'MANUAL' ? '仓管人工录入收料' : '导入识别后人工复核',
      })),
    })
    setReceiptFeedback(`保存成功：待确认收料单 ${currentReceipt.value.receipt_no} 已保存；有效收料 ${formatNumber(receiptTotals.value.effective)}，尚未写入库存${hasAdHocReceiptLines.value ? '或月结' : ''}。请点击“${receiptConfirmButtonLabel.value}”。`, 'success')
  } catch (error) {
    setReceiptFeedback(`保存失败：${getApiErrorMessage(error)}`)
  } finally {
    savingReceipt.value = false
  }
}

async function confirmCurrentReceipt() {
  if (!currentReceipt.value) return
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
  closingBusyId.value = 'generate'
  try {
    const closings = await cartonProcurementApi.generateClosings(selectedFactoryId.value, closingPeriod.value)
    closingRecords.value = closings
    localClosings.splice(0, localClosings.length, ...closings.map(mapClosing))
    actionMessage.value = `已生成 ${closingPeriod.value} 月结草稿，共 ${closings.filter((row) => row.status !== 'LOCKED').length} 份待重新核对；已锁账快照保留。`
  } catch (error) {
    actionMessage.value = `月结生成失败：${getApiErrorMessage(error)}`
  } finally {
    closingBusyId.value = ''
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

function closingButtonLabel(rowId: string) {
  const closing = closingRecord(rowId)
  return closing ? closingActionLabel(closing.status) : '等待正式数据'
}

function closingButtonHint(rowId: string) {
  const closing = closingRecord(rowId)
  if (!closing) return '等待正式数据'
  if (closing.status === 'LOCKED') return '最终锁账后，本期间禁止新增和冲销流水'
  if (closing.snapshot_stale) return '收发数据已有变动，请重新生成草稿并核对'
  if (closing.status === 'CONFIRMED' && closing.period >= businessTodayIso().slice(0, 7)) return '月份尚未结束，可继续正常收发货'
  if (closing.status === 'CONFIRMED' && !canFinalizeClosing.value) return '最终锁账须由有权限的主管执行'
  return closing.status === 'CONFIRMED' ? '月份已结束，核对完成后可最终锁账' : '核对确认不限制正常收发货'
}

function closingButtonDisabled(rowId: string) {
  const closing = closingRecord(rowId)
  return !apiConnected.value || !authStore.can('carton_procurement:closing_manage')
    || !closing || closing.status === 'LOCKED' || Boolean(closingBusyId.value) || closing.snapshot_stale
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
  if ((nextStatus === 'RESOLVED' || nextStatus === 'CLOSED') && note.length < 4) {
    actionMessage.value = '标记解决或关闭异常前，请填写至少 4 个字符的处理说明。'
    return
  }
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

        <label class="relative ml-1 hidden lg:block">
          <Search class="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
          <input
            v-model="globalSearch"
            placeholder="搜索合同 / PO / 货号 / 单据..."
            class="h-8 w-72 rounded-lg border border-slate-200 bg-slate-50 pl-8 pr-3 text-[12px] outline-none transition focus:border-teal-500 focus:bg-white"
          >
        </label>

        <div class="ml-auto flex items-center gap-2">
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
          :class="activeTab === tab.id ? 'bg-teal-700 text-white' : 'text-slate-500 hover:bg-slate-50 hover:text-slate-900'"
          :aria-current="activeTab === tab.id ? 'page' : undefined"
          @click="setActiveTab(tab.id)"
        >
          <component :is="tab.icon" class="size-4" aria-hidden="true" />
          <span class="hidden xl:inline">{{ tab.label }}</span>
          <span class="xl:hidden">{{ tab.shortLabel }}</span>
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
          <label class="relative block lg:hidden">
            <Search class="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
            <input
              v-model="globalSearch"
              aria-label="全局搜索"
              placeholder="搜索单据..."
              class="h-9 w-44 rounded-lg border border-slate-200 bg-slate-50 pl-8 pr-3 text-[12px] outline-none focus:border-teal-500"
            >
          </label>
          <select
            v-if="activeTab !== 'inventory-summary' && activeTab !== 'orders' && (activeTab !== 'receipts' || !showManualReceipt) && (activeTab !== 'inventory' || showInventoryImport)"
            v-model="selectedCustomer"
            aria-label="客户筛选"
            class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-700 outline-none focus:border-teal-500"
          >
            <option v-for="customer in customerFilterOptions" :key="customer" :value="customer">{{ customer }}</option>
          </select>
          <button
            v-if="activeTab === 'orders' && canManageCustomers"
            type="button"
            :disabled="!apiConnected"
            class="inline-flex h-9 items-center gap-2 rounded-lg border border-teal-200 bg-white px-3 text-[12px] font-bold text-teal-700 transition hover:bg-teal-50 disabled:cursor-not-allowed disabled:border-slate-200 disabled:text-slate-400"
            @click="openCustomerManager"
          >
            <Users class="size-4" aria-hidden="true" />
            客户资料维护
          </button>
          <span v-else-if="activeTab === 'orders'" class="text-[10px] text-slate-500">客户资料由纸箱部主管维护</span>
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
            <div class="mt-2 text-3xl font-bold tabular-nums text-slate-950">{{ formatNumber(inventoryBalance) }}</div>
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
                <div class="mt-1 truncate text-[10px] text-slate-500">{{ alert.productName || '品名待补充' }}<template v-if="alert.orderNo"> · 纸箱订单 {{ alert.orderNo }}（{{ orderStatusLabel(alert.orderStatus) }}）</template></div>
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
            <div v-if="visibleBusinessOrderAlerts.length > 8" class="border-t border-slate-100 px-4 py-3 text-center"><button type="button" class="text-[10px] font-bold text-teal-700" @click="setActiveTab('exceptions')">还有 {{ visibleBusinessOrderAlerts.length - 8 }} 条，前往异常中心查看</button></div>
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
              <button type="button" class="text-[11px] font-bold text-teal-700" @click="setActiveTab('exceptions')">进入异常中心</button>
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
            <p class="mt-1 text-[11px] text-slate-500">待下单订单确认后整单锁定；再另行发行供应商采购单。主管可继续追加，也可减少尚未入库部分；全部到货后追加会恢复为“部分到货”。</p>
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
            <button type="button" :disabled="apiConnected && activeCustomers.length === 0" class="inline-flex h-9 items-center gap-2 rounded-lg bg-teal-700 px-3.5 text-[12px] font-bold text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:bg-slate-300" @click="openOrderModal">
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

        <div aria-label="订单筛选与批量操作" class="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
          <label class="space-y-1"><span class="block text-[10px] font-bold text-slate-500">客户</span><select v-model="selectedCustomer" aria-label="客户筛选" class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-[11px] font-semibold outline-none focus:border-teal-500"><option v-for="customer in customerFilterOptions" :key="customer" :value="customer">{{ customer }}</option></select></label>
          <label class="space-y-1"><span class="block text-[10px] font-bold text-slate-500">订单状态</span><select v-model="orderStatusFilter" aria-label="订单状态筛选" class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-[11px] font-semibold outline-none focus:border-teal-500"><option value="ALL">全部状态</option><option value="CONFIRMED">待下单</option><option value="PENDING_SUPPLIER">已确认锁定</option><option value="PARTIALLY_RECEIVED">部分收料</option><option value="COMPLETED">已完成</option><option value="CANCELLED">已取消</option></select></label>
          <label class="space-y-1"><span class="block text-[10px] font-bold text-slate-500">计划交期</span><select v-model="orderDueFilter" aria-label="订单计划交期筛选" class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-[11px] font-semibold outline-none focus:border-teal-500"><option value="ALL">全部计划交期</option><option value="OVERDUE">已逾期</option><option value="TODAY">今日交期</option><option value="DUE_SOON">3 天内</option><option value="UPCOMING">后续交期</option></select></label>
          <div class="space-y-1"><span class="block text-[10px] font-bold text-slate-500">下单日期</span><DateRangeFilter v-model="orderDateRange" label="订单下单日期筛选" /></div>
          <label class="space-y-1"><span class="block text-[10px] font-bold text-slate-500">排序</span><select v-model="orderSort" aria-label="订单排序" class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-[11px] font-semibold outline-none focus:border-teal-500"><option value="DUE_ASC">交期由近到远</option><option value="DUE_DESC">交期由远到近</option><option value="ORDER_DESC">下单日期最新</option></select></label>
          <button type="button" :disabled="!apiConnected || !selectedSubmittableOrderCount || submittingSupplierOrder" class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-teal-200 bg-teal-50 px-3 text-[11px] font-bold text-teal-700 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-white disabled:text-slate-400" @click="openBulkSubmitSupplierOrders"><ShieldCheck class="size-3.5" />{{ submittingSupplierOrder ? '正在确认…' : `确认订单并锁定（${selectedSubmittableOrderCount}）` }}</button>
          <button type="button" :disabled="!apiConnected || !selectedOrderNos.length || issuingSelectedPurchaseOrders || !canIssuePurchaseOrders" title="首次与非首次采购单均可多选发行；包含追加或减单时会先确认" class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-amber-600 px-3 text-[11px] font-bold text-white disabled:cursor-not-allowed disabled:bg-slate-300" @click="issueSelectedPurchaseOrders"><Send class="size-3.5" />{{ issuingSelectedPurchaseOrders ? '发行中…' : `发行供应商采购单（${selectedOrderNos.length}）` }}</button>
          <button type="button" :disabled="!apiConnected || !selectedOrderNos.length || exportingSelectedOrders" :title="!apiConnected ? '后端未连接，当前演示订单不能导出' : '累计对账表不代表向供应商新增下单'" class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-teal-200 px-3 text-[11px] font-bold text-teal-700 disabled:cursor-not-allowed disabled:border-slate-200 disabled:text-slate-400" @click="exportSelectedPurchaseOrders"><Download class="size-3.5" />{{ exportingSelectedOrders ? '合并生成中…' : '导出累计对账表' }}</button>
          <button type="button" :disabled="!selectedOrdersCanCancel || cancellingOrder" title="仅尚未确认锁定的待下单订单可批量取消" class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-red-200 px-3 text-[11px] font-bold text-red-700 disabled:opacity-40" @click="openBulkCancelOrders"><X class="size-3.5" />批量取消</button>
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

        <div class="rounded-xl border border-slate-200 bg-white shadow-sm">
          <div aria-label="订单批量选择" class="rounded-t-xl border-b border-slate-100 bg-slate-50 px-4 py-2.5">
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
                <div class="truncate font-mono text-[13px] font-bold leading-tight text-slate-950" :title="row.contractNo">{{ row.contractNo }}</div>
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
                <span class="inline-flex rounded-full px-2 py-0.5 text-[10px] font-bold ring-1 ring-inset" :class="toneClass(row.tone)">{{ row.status }}</span>
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
                  <div v-if="canEditConfirmedOrder(row.id) || canReceiveOrder(row.id) || canAppendOrder(row.id) || canReduceSubmittedOrder(row.id)" class="relative col-start-2 row-start-1 w-full">
                    <button type="button" class="inline-flex h-8 w-full items-center justify-center gap-1 whitespace-nowrap rounded-md border border-slate-200 bg-white px-1 text-[10px] font-bold text-slate-600 transition hover:border-slate-300 hover:bg-slate-100" :aria-label="`更多 ${row.id} 订单操作`" aria-haspopup="menu" :aria-expanded="openOrderMoreMenu === row.id" @click.stop="openOrderMoreMenu = openOrderMoreMenu === row.id ? '' : row.id">更多 <span class="text-[8px]">▾</span></button>
                    <button v-if="openOrderMoreMenu === row.id" type="button" class="fixed inset-0 z-20 cursor-default" :aria-label="`关闭 ${row.id} 更多操作`" @click="openOrderMoreMenu = ''"></button>
                    <div v-if="openOrderMoreMenu === row.id" role="menu" class="absolute right-0 top-full z-30 mt-1 w-44 overflow-hidden rounded-lg border border-slate-200 bg-white py-1 shadow-xl">
                      <button v-if="canEditConfirmedOrder(row.id)" type="button" role="menuitem" :disabled="!apiConnected" class="flex w-full items-center gap-2 px-3 py-2 text-left text-[10px] font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40" :aria-label="`修改 ${row.id} 订单`" @click="openOrderMoreMenu = ''; openEditOrderModal(row.id)"><Pencil class="size-3.5" />修改订单</button>
                      <button v-if="canEditConfirmedOrder(row.id) || canReceiveOrder(row.id)" type="button" role="menuitem" :disabled="!apiConnected" class="flex w-full items-center gap-2 px-3 py-2 text-left text-[10px] font-semibold text-teal-700 hover:bg-teal-50 disabled:opacity-40" :aria-label="`管理 ${row.id} 采购单`" @click="openOrderMoreMenu = ''; openPurchaseOrderDialog(row.id)"><Download class="size-3.5" />采购单</button>
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
                <h2 class="font-bold text-slate-950">每周排期防漏单核对</h2>
                <p class="mt-1 text-[11px] text-slate-500">按 Reference、PO、客户、货号和数量检查正式订单，发现漏下或数量不一致。</p>
              </div>
              <input ref="weeklyFileInput" type="file" accept=".xlsx,.xls" class="hidden" aria-label="选择每周排期文件" @change="handleWeeklyFile">
              <div class="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  :disabled="importingWeekly"
                  class="inline-flex h-9 items-center gap-2 rounded-lg border border-teal-200 bg-white px-3 text-[12px] font-bold text-teal-700 transition hover:bg-teal-50 disabled:cursor-not-allowed disabled:border-slate-200 disabled:text-slate-400"
                  @click="triggerWeeklyImport"
                >
                  <FileSpreadsheet class="size-4" />{{ importingWeekly ? '正在核对…' : '导入本周排期' }}
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
            <p v-if="weeklyCheckMode === 'ORDER_GAP'" class="mt-2 text-[11px] leading-5">导入排期只生成防漏核对结果和待办，<strong>不会自动创建正式纸箱订单</strong>。</p>
            <p v-else class="mt-2 text-[11px] leading-5">最迟交货日＝验货开始日－提前天数；只生成纸箱部提醒，<strong>不会修改订单或库存</strong>。</p>
          </article>
        </div>

        <article class="rounded-xl border border-slate-200 bg-white shadow-sm">
          <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
            <div>
              <h2 class="font-bold text-slate-950">核对历史</h2>
              <p class="mt-1 text-[11px] text-slate-500">每次导入及核对结果均由后端保存；点击历史批次可恢复当时的结果明细。</p>
            </div>
            <span class="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-bold text-slate-600">{{ activeWeeklyImportHistory.length }} 个批次</span>
          </div>
          <div v-if="activeWeeklyImportHistory.length" class="divide-y divide-slate-100">
            <div v-for="batch in activeWeeklyImportHistory.slice(0, 8)" :key="batch.id" class="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
              <div class="min-w-0">
                <div class="truncate text-[12px] font-semibold text-slate-900">{{ batch.original_filename }}</div>
                <div class="mt-0.5 text-[10px] text-slate-500">{{ (batch.created_at || '').replace('T', ' ').slice(0, 16) || '历史时间待补充' }} · {{ batch.imported_by_name || '历史操作人' }} · {{ batch.parse_summary.row_count ?? 0 }} 行</div>
              </div>
              <button type="button" class="h-8 rounded-lg border border-slate-200 bg-white px-3 text-[11px] font-bold text-slate-700 hover:border-teal-300 hover:text-teal-700" @click="batch.import_type === 'WEEKLY_SCHEDULE' ? restoreWeeklyImport(batch) : restoreInspectionImport(batch)">查看结果</button>
            </div>
          </div>
          <div v-else class="px-4 py-8 text-center text-[11px] text-slate-400">尚无当前类型的核对历史</div>
        </article>

        <div v-if="weeklyCheckMode === 'ORDER_GAP'" class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div class="overflow-x-auto">
            <table class="min-w-[1250px] w-full text-left">
              <thead class="bg-slate-50 text-[10px] font-bold text-slate-500">
                <tr><th class="px-4 py-3">Reference / PO.NO</th><th class="px-4 py-3">客户 / 产品</th><th class="px-4 py-3">货号</th><th class="px-4 py-3 text-right">数量</th><th class="px-4 py-3">装箱</th><th class="px-4 py-3">验货期</th><th class="px-4 py-3">核对结果</th><th class="px-4 py-3">关联订单</th><th class="px-4 py-3">处理建议</th></tr>
              </thead>
              <tbody class="divide-y divide-slate-100">
                <tr v-for="row in visibleWeeklyChecks" :key="row.id" class="hover:bg-slate-50/80">
                  <td class="px-4 py-3"><div class="font-semibold">{{ row.reference }}</div><div class="mt-0.5 text-[10px] text-slate-500">{{ row.poNumbers }}</div></td>
                  <td class="px-4 py-3"><div class="font-semibold">{{ row.customer }}</div><div class="mt-0.5 text-[10px] text-slate-500">{{ row.productName }}</div></td>
                  <td class="px-4 py-3 font-mono font-semibold">{{ row.itemNo }}</td>
                  <td class="px-4 py-3 text-right font-semibold tabular-nums">{{ formatNumber(row.quantity) }}</td>
                  <td class="px-4 py-3">{{ row.cartonRule }}</td>
                  <td class="px-4 py-3 font-semibold">{{ row.inspectionWindow }}</td>
                  <td class="px-4 py-3"><span class="rounded-full px-2 py-0.5 text-[10px] font-bold ring-1 ring-inset" :class="toneClass(row.tone)">{{ row.result }}</span></td>
                  <td class="px-4 py-3 font-mono text-[11px]">{{ row.linkedOrder }}</td>
                  <td class="max-w-[280px] px-4 py-3 text-[11px] text-slate-500">{{ row.suggestion }}</td>
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
        <article v-if="showManualReceipt" class="overflow-hidden rounded-xl border border-blue-200 bg-white shadow-sm">
          <div class="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 px-5 py-4">
            <div>
              <h2 class="flex items-center gap-2 text-lg font-bold text-slate-950"><Truck class="size-5 text-teal-700" />待收订单 <span class="text-sm font-medium text-slate-500">{{ visibleManualReceiptOrders.length }} 张</span></h2>
              <p class="mt-1 text-sm text-slate-500">选择本次送货的订单，再登记送货单及实际收料数量。</p>
            </div>
            <button type="button" class="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 px-3 text-xs font-bold text-slate-600 hover:bg-slate-50" ref="receiptDialogTrigger" @click="cancelManualReceipt"><Upload class="size-4" />切换导入模式</button>
          </div>
          <div class="flex flex-wrap items-center justify-between gap-3 bg-slate-50 px-5 py-3">
            <div class="flex flex-1 flex-wrap items-center gap-3">
              <label class="inline-flex items-center gap-2 text-xs font-semibold text-slate-600"><span>客户</span><select v-model="selectedCustomer" aria-label="待收订单客户筛选" class="h-9 min-w-28 rounded-lg border border-slate-200 bg-white px-3 text-xs text-slate-700 outline-none focus:border-teal-500"><option v-for="customer in customerFilterOptions" :key="customer" :value="customer">{{ customer }}</option></select></label>
              <div role="group" aria-label="计划交期筛选" class="flex items-center gap-2 text-xs font-semibold text-slate-600">
                <span>计划交期</span>
                <DateRangeFilter v-model="receiptDueCalendarValue" label="选择计划交期范围" />
              </div>
              <label class="inline-flex items-center gap-2 text-xs font-semibold text-slate-600"><span>排序</span><select v-model="receiptOrderSort" aria-label="待收订单排序" class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-xs text-slate-700 outline-none focus:border-teal-500"><option value="DUE_ASC">交期由近到远</option><option value="DUE_DESC">交期由远到近</option><option value="DEFAULT">下单日期最新</option></select></label>
              <button v-if="selectedCustomer !== '全部客户' || receiptPlannedDueFrom || receiptPlannedDueTo" type="button" class="h-9 px-2 text-xs font-semibold text-teal-700 hover:text-teal-900" @click="clearReceiptOrderFilters">清除筛选</button>
            </div>
            <div class="flex items-center gap-4"><span class="text-sm text-slate-600">已选 <strong class="text-teal-700">{{ selectedManualReceiptOrders.length }}</strong> 张</span><button type="button" :disabled="!selectedManualReceiptOrders.length || !apiConnected" class="inline-flex h-10 items-center gap-2 rounded-lg bg-teal-700 px-4 text-sm font-bold text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-40" @click="openManualReceipt()"><Plus class="size-4" />登记所选订单收料</button></div>
          </div>
          <div class="bg-white">
            <div class="receipt-order-ledger-grid grid min-h-11 items-center gap-x-3 border-b border-slate-100 bg-slate-50 px-4 text-[11px] font-bold tracking-wide text-slate-700" aria-label="待收订单列表表头">
              <div class="grid min-w-0 grid-cols-[1.25rem_minmax(0,1fr)] items-center gap-x-1.5">
                <label class="inline-flex cursor-pointer items-center" title="全选当前订单"><input type="checkbox" aria-label="全选待收订单" class="size-5 shrink-0 cursor-pointer accent-teal-600" :disabled="!visibleManualReceiptOrders.length" :checked="visibleManualReceiptOrders.length > 0 && visibleManualReceiptOrders.every((order) => manualReceiptOrderNos.includes(order.order_no))" @change="toggleVisibleReceiptOrders(($event.target as HTMLInputElement).checked)"><span class="sr-only">全选当前订单</span></label>
                <span class="hidden lg:inline">下单日期</span><span class="lg:hidden">全选当前订单</span>
              </div><span class="hidden lg:block">客户</span><span class="hidden lg:block">合同号</span><span class="hidden lg:block">货号 / 品名</span><span class="hidden lg:block">纸品明细</span><span class="hidden lg:block">交期（客户 / 计划）</span><span class="hidden lg:block">到货进度</span><span class="hidden lg:block">订单状态</span><span class="hidden lg:block">交期提醒</span><span class="hidden lg:block">操作</span>
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
                <div class="truncate font-mono text-[13px] font-bold leading-tight text-slate-950" :title="row.contractNo">{{ row.contractNo }}</div>
              </div>
              <div class="min-w-0 text-left"><div class="mb-1 text-[10px] font-bold text-slate-400 lg:hidden">货号 / 品名</div><div class="truncate font-mono text-[13px] font-bold text-slate-950" :title="row.itemNo">{{ row.itemNo }}</div><div v-if="row.productName" class="mt-1 truncate text-[11px] text-slate-500" :title="row.productName">{{ row.productName }}</div></div>
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
                <span class="inline-flex rounded-full px-2 py-0.5 text-[10px] font-bold ring-1 ring-inset" :class="toneClass(row.tone)">{{ row.status }}</span>
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
            </article>
            <p v-if="!visibleManualReceiptOrders.length" class="py-10 text-center text-sm text-slate-500">{{ backendLoading ? '正在加载待收订单…' : '当前没有符合条件的待收订单。只有已确认锁定或部分收料的订单会显示在这里。' }}</p>
          </div>
        </article>

        <article v-else class="rounded-xl border border-teal-200 bg-white p-5 shadow-sm">
          <div class="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 class="flex items-center gap-2 text-lg font-bold text-slate-950"><Upload class="size-5 text-teal-700" />送货单导入</h2>
              <p class="mt-1 text-sm text-slate-500">上传送货单，复核识别明细后登记收料。</p>
            </div>
            <div class="flex flex-wrap items-center gap-3">
              <button type="button" :disabled="importingReceipt" class="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 px-4 text-xs font-bold text-slate-600 hover:bg-slate-50 disabled:opacity-60" @click="returnToPendingReceiptOrders"><ArrowLeft class="size-4" />返回待收订单</button>
              <input ref="receiptFileInput" type="file" accept=".pdf,.jpg,.jpeg,.png,.heic,.heif,image/heic,image/heif,.xlsx,.xls" class="hidden" aria-label="选择送货单文件" @change="handleReceiptFile">
              <button ref="receiptDialogTrigger" type="button" :disabled="importingReceipt" class="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-teal-700 px-4 text-xs font-bold text-white transition hover:bg-teal-800 disabled:opacity-60" @click="triggerReceiptImport"><Upload class="size-4" />{{ importingReceipt ? '正在识别…' : '导入送货单' }}</button>
            </div>
          </div>
          <p v-if="selectedReceiptFileName" class="mt-3 break-all text-xs text-slate-500">已选择：<span class="font-semibold text-slate-700">{{ selectedReceiptFileName }}</span></p>
        </article>

        <div v-if="!showManualReceipt && receiptLines.length" class="flex items-center justify-between gap-3 rounded-xl border border-teal-200 bg-teal-50 p-4">
          <span class="text-sm text-teal-900">{{ receiptLines.length }} 条明细待复核</span>
          <button type="button" class="h-10 rounded-lg bg-teal-700 px-4 text-sm font-bold text-white" @click="showReceiptDialog = true">填写收料反馈</button>
        </div>

        <article v-if="receiptImportBatch" class="overflow-hidden rounded-xl border bg-white shadow-sm" :class="receiptImportNeedsReview ? 'border-amber-300' : 'border-emerald-300'">
          <div class="flex flex-wrap items-start justify-between gap-3 border-b px-4 py-3" :class="receiptImportNeedsReview ? 'border-amber-200 bg-amber-50' : 'border-emerald-200 bg-emerald-50'">
            <div>
              <div class="flex flex-wrap items-center gap-2 font-bold" :class="receiptImportNeedsReview ? 'text-amber-950' : 'text-emerald-950'">
                <CheckCircle2 class="size-4" />送货单识别完成
                <span v-if="receiptImportBatch.duplicate" class="rounded-full bg-white px-2 py-0.5 text-[9px] font-bold text-slate-600 ring-1 ring-inset ring-slate-200">重复文件 · 已恢复原结果</span>
              </div>
              <p class="mt-1 text-[11px]" :class="receiptImportNeedsReview ? 'text-amber-800' : 'text-emerald-800'">{{ receiptImportBatch.original_filename }} · {{ receiptImportBatch.parse_summary.engine || '文件解析' }} · 批次 {{ receiptImportBatch.id }}</p>
            </div>
            <div class="flex flex-wrap gap-2">
              <button v-if="receiptImportStats.issues" type="button" class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-amber-300 bg-white px-3 text-[11px] font-bold text-amber-800 hover:bg-amber-100" @click="setActiveTab('exceptions')"><AlertTriangle class="size-3.5" />前往异常中心</button>
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
            系统尚未生成收料明细或库存。确认确属非正式/打板收料时，可在下方加入待确认收料并补齐字段；只有保存后再次人工确认，才会入库并计入月结。
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
              <thead class="bg-slate-50 text-[10px] font-bold text-slate-500"><tr><th class="px-3 py-2.5">来源</th><th class="px-3 py-2.5">送货单 / 日期</th><th class="px-3 py-2.5">合同号</th><th class="px-3 py-2.5">货号</th><th class="px-3 py-2.5">品名（类型 / 纸质）</th><th class="px-3 py-2.5">规格</th><th class="px-3 py-2.5 text-right">数量</th><th class="px-3 py-2.5">匹配结果</th><th class="px-3 py-2.5">处理建议</th><th class="px-3 py-2.5">收料处理</th></tr></thead>
              <tbody class="divide-y divide-slate-100">
                <tr v-for="(row, index) in receiptImportPreviewRows" :key="`${row.source_sheet}-${row.source_row}-${index}`" class="hover:bg-slate-50/70">
                  <td class="px-3 py-2.5 text-[10px] text-slate-500">{{ row.source_sheet || '文件' }} · 第 {{ row.source_row || index + 1 }} 行</td>
                  <td class="px-3 py-2.5"><div class="font-mono text-[11px] font-semibold">{{ row.delivery_note_no || receiptImportBatch.parse_summary.document?.delivery_note_no || '待识别' }}</div><div class="text-[9px] text-slate-400">{{ row.delivery_date || receiptImportBatch.parse_summary.document?.delivery_date || '日期待复核' }}</div></td>
                  <td class="px-3 py-2.5 font-mono text-[11px] font-semibold">{{ row.contract_no || row.reference || '待识别' }}</td>
                  <td class="px-3 py-2.5 font-mono text-[11px]">{{ row.item_no || '待识别' }}</td>
                  <td class="px-3 py-2.5 text-[11px]"><div class="font-semibold">{{ row.packaging_type || '待复核' }}</div><div class="text-[9px] text-slate-400">{{ row.paper_quality || '' }}</div></td>
                  <td class="px-3 py-2.5 text-[10px] text-slate-600">{{ row.specification || '待识别' }}</td>
                  <td class="px-3 py-2.5 text-right font-semibold tabular-nums">{{ importQuantityLabel(row) }}</td>
                  <td class="px-3 py-2.5"><span class="rounded-full px-2 py-0.5 text-[9px] font-bold ring-1 ring-inset" :class="importMatchTone(row.match_status)">{{ importMatchLabel(row.match_status) }}</span></td>
                  <td class="max-w-[260px] px-3 py-2.5 text-[10px] text-slate-500">{{ row.suggestion || '请人工复核识别结果' }}</td>
                  <td class="px-3 py-2.5">
                    <span v-if="row.match_status === 'MATCHED'" class="text-[10px] font-bold text-emerald-700">已关联正式订单</span>
                    <button v-else-if="row.match_status === 'MISSING_ORDER' && !receiptImportRowAdded(row, index)" type="button" :disabled="Boolean(currentReceipt)" class="inline-flex h-8 items-center gap-1 rounded-lg border border-amber-300 bg-amber-50 px-2.5 text-[10px] font-bold text-amber-800 hover:bg-amber-100 disabled:opacity-40" @click="addAdHocReceiptLine(row, index)"><Plus class="size-3.5" />作为非正式/打板收料</button>
                    <span v-else-if="receiptImportRowAdded(row, index)" class="text-[10px] font-bold text-blue-700">已加入待确认收料</span>
                    <span v-else class="text-[10px] text-slate-400">需先解决匹配不唯一</span>
                  </td>
                </tr>
                <tr v-if="receiptImportPreviewRows.length === 0"><td colspan="10" class="px-4 py-10 text-center text-slate-400">未解析出结构化明细；请查看上方“识别诊断详情”中的 OCR 原文和警告</td></tr>
              </tbody>
            </table>
          </div>
          <div v-if="receiptImportRows.length > receiptImportPreviewRows.length" class="border-t border-slate-200 px-4 py-2 text-[10px] text-slate-500">当前显示前 {{ receiptImportPreviewRows.length }} 行，共 {{ receiptImportRows.length }} 行；全部问题行均已保存。</div>
        </article>

        <div v-if="apiConnected && receiptEntryMode === 'IMPORT' && receiptLines.length === 0 && !receiptImportBatch" class="rounded-xl border border-teal-200 bg-teal-50 p-5 text-teal-900 shadow-sm">
          <div class="flex items-center gap-2 font-bold"><Upload class="size-4" />等待导入并复核送货单</div>
          <p class="mt-1 text-[11px] leading-5 text-teal-800">选择文件后，后端先登记唯一指纹和待复核批次；字段匹配与数量确认完成前，不会创建收料单或库存流水。</p>
        </div>


        <article class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
            <div>
              <h2 class="font-bold text-slate-950">收料历史台账</h2>
              <p class="mt-1 text-[11px] text-slate-500">已保存和已确认的收料单长期保留，可按送货单、合同、货号或纸品查找。</p>
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
            <table class="min-w-[1280px] w-full text-left">
              <thead class="bg-slate-50 text-[10px] font-bold text-slate-500"><tr><th class="px-4 py-3">收料单 / 送货单</th><th class="px-4 py-3">日期</th><th class="px-4 py-3">客户 / 合同</th><th class="px-4 py-3">货号</th><th class="px-4 py-3">纸品 / 规格</th><th class="px-4 py-3 text-right">有效收料</th><th class="px-4 py-3">仓位</th><th class="px-4 py-3">状态</th><th class="px-4 py-3">经手人 / 时间</th><th class="px-4 py-3">操作</th></tr></thead>
              <tbody class="divide-y divide-slate-100">
                <tr v-for="row in receiptHistoryRows" :key="row.id" class="hover:bg-slate-50/80">
                  <td class="px-4 py-3"><div class="font-mono font-semibold">{{ row.receiptNo }}</div><div class="mt-0.5 font-mono text-[10px] text-slate-500">{{ row.deliveryNoteNo }}</div></td>
                  <td class="px-4 py-3 font-semibold">{{ row.deliveryDate }}</td>
                  <td class="px-4 py-3"><div class="font-semibold">{{ row.customer }}</div><div class="mt-0.5 font-mono text-[10px] text-slate-500">{{ row.contractNo }}</div></td>
                  <td class="px-4 py-3 font-mono font-semibold">{{ row.itemNo }}</td>
                  <td class="px-4 py-3"><div class="font-semibold">{{ row.paper }}</div><div class="mt-0.5 text-[10px] text-slate-500">{{ row.specification }}</div></td>
                  <td class="px-4 py-3 text-right font-bold tabular-nums text-teal-700">{{ formatNumber(row.effectiveQuantity) }} {{ row.unit }}</td>
                  <td class="px-4 py-3">{{ row.location || '未填写' }}</td>
                  <td class="px-4 py-3"><span class="rounded-full px-2 py-0.5 text-[10px] font-bold ring-1 ring-inset" :class="row.status === 'POSTED' ? toneClass('green') : toneClass('amber')">{{ row.status === 'REVERSED' && !row.receipt.confirmed_at ? '已作废' : receiptStatusLabel(row.status) }}</span><div v-if="row.sourceType === 'AD_HOC'" class="mt-1 text-[9px] font-bold text-amber-700">非正式/打板收料</div></td>
                  <td class="px-4 py-3"><div class="font-semibold">{{ row.operator || '—' }}</div><div class="mt-0.5 text-[10px] text-slate-500">{{ (row.confirmedAt || '').replace('T', ' ').slice(0, 16) }}</div></td>
                  <td class="px-4 py-3"><div class="flex gap-2 whitespace-nowrap">
                    <button type="button" class="inline-flex h-8 items-center justify-center rounded-md border border-slate-200 bg-white px-2 text-[11px] font-bold text-slate-600 transition hover:border-teal-300 hover:bg-teal-50 hover:text-teal-700" :aria-label="`查看收料单 ${row.receiptNo}`" title="悬停预览整单明细，单击后保持显示" aria-haspopup="dialog" @mouseenter="showReceiptDetails(row.receipt)" @mouseleave="closeReceiptDetailPreview" @focus="showReceiptDetails(row.receipt)" @blur="closeReceiptDetailPreview" @click="showReceiptDetails(row.receipt, true)">明细</button>
                    <button v-if="canCorrectReceipt && ['PENDING_CONFIRMATION', 'POSTED'].includes(row.status)" type="button" class="inline-flex h-8 items-center justify-center rounded-md border border-red-200 bg-white px-2 text-[11px] font-bold text-red-600 transition hover:bg-red-50" :aria-label="`更正收料单 ${row.receiptNo}`" :title="row.status === 'POSTED' ? '冲销整张收料单的入库，需填写原因并确认' : '作废待确认收料单，需填写原因并确认'" @click="openReceiptCorrection(row.receipt)">{{ row.status === 'POSTED' ? '冲销' : '作废' }}</button>
                    <button v-if="canCorrectReceipt && row.status === 'REVERSED'" type="button" class="inline-flex h-8 items-center justify-center rounded-md border border-teal-200 bg-white px-2 text-[11px] font-bold text-teal-700 transition hover:bg-teal-50" @click="openReceiptHistoryDocument(row.receipt, true)">重新登记</button>
                  </div></td>
                </tr>
                <tr v-if="receiptHistoryRows.length === 0"><td colspan="10" class="px-4 py-10 text-center text-slate-400">没有符合条件的收料历史</td></tr>
              </tbody>
            </table>
          </div>
        </article>
      </section>

      <section v-else-if="activeTab === 'inventory'" class="space-y-4">
        <CartonStocktakeWorkspace v-if="showStocktake" :key="selectedFactoryId" :factory-id="selectedFactoryId" @close="showStocktake = false" @posted="refreshInventoryLedger" />
        <article v-else-if="showInventoryImport" class="rounded-xl border border-teal-200 bg-white p-5 shadow-sm">
          <div class="flex flex-wrap items-center justify-between gap-4"><div><h2 class="flex items-center gap-2 text-lg font-bold text-slate-950"><Boxes class="size-5 text-teal-700" />期初库存管理</h2><p class="mt-1 text-sm text-slate-500">用于系统启用、迁移或补录已有库存，支持模板下载与历史库存导入。</p></div><button type="button" :disabled="importingHistoryInventory" class="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 px-3 text-xs font-bold text-slate-600 disabled:opacity-40" @click="showInventoryImport = false"><ArrowLeft class="size-4" />返回库存台账</button></div>
          <div class="mt-5 flex flex-wrap items-center gap-3 rounded-lg bg-slate-50 p-4">
          <a
            href="/templates/carton-history-inventory-import-template.xlsx"
            download="纸箱历史库存导入模板.xlsx"
            class="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-bold text-slate-700 transition hover:border-teal-200 hover:bg-teal-50 hover:text-teal-700"
          >
            <Download class="size-4" aria-hidden="true" />
            下载历史库存模板
          </a>
          <input
            ref="historyInventoryFileInput"
            type="file"
            accept=".xlsx,.xlsm,.xls"
            class="hidden"
            aria-label="选择历史库存文件"
            @change="handleHistoryInventoryFile"
          >
          <button
            type="button"
            :disabled="!apiConnected || importingHistoryInventory"
            class="inline-flex h-9 items-center gap-2 rounded-lg border border-teal-200 bg-white px-3 text-[12px] font-bold text-teal-700 transition hover:bg-teal-50 disabled:cursor-not-allowed disabled:border-slate-200 disabled:text-slate-400"
            @click="triggerHistoryInventoryImport"
          >
            <Upload class="size-4" aria-hidden="true" />
            {{ importingHistoryInventory ? '正在导入…' : '导入历史库存' }}
          </button>
          </div>
          <p class="mt-4 text-xs leading-5 text-slate-500">导入成功后生成期初库存流水；重复文件不会重复入账。</p>
        </article>
        <template v-else>
        <div class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div class="border-b border-slate-200 px-4 py-3">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div><h2 class="flex items-center gap-2 text-lg font-bold text-slate-950"><Boxes class="size-5 text-teal-700" />实时库存结存台账</h2><p class="mt-1 text-[11px] text-slate-500">不同合同、货号、纸品类型、纸质、规格和单位分别结存，不互相覆盖。</p></div>
              <div class="flex flex-wrap items-center gap-2"><span class="mr-2 text-xs text-slate-500">当前结存 {{ formatNumber(inventoryBalance) }} · 显示 {{ inventoryBalances.length }} / {{ localInventoryBalances.length }} 条</span><button type="button" class="h-9 rounded-lg border border-slate-200 px-3 text-xs font-bold text-slate-600" @click="setActiveTab('closing')">月结对账</button><PopoverRoot v-model:open="inventoryMoreOpen">
                <PopoverTrigger as-child><button type="button" aria-label="库存更多操作" class="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 px-3 text-xs font-bold text-slate-600 hover:bg-slate-50">更多操作<span aria-hidden="true">▾</span></button></PopoverTrigger>
                <PopoverPortal><PopoverContent align="end" :side-offset="6" :collision-padding="12" class="z-50 w-64 rounded-xl border border-slate-200 bg-white p-1.5 shadow-lg">
                  <button type="button" :disabled="!apiConnected" class="w-full rounded-lg px-3 py-2.5 text-left hover:bg-slate-50 disabled:opacity-40" @click="inventoryMoreOpen = false; openInventoryOperation('ADJUSTMENT', '', false, $event)"><span class="block text-sm font-semibold text-slate-800">库存数量调整</span><span class="mt-1 block text-xs text-slate-500">少量临时纠错；定期清点请使用库存盘点</span></button>
                  <button type="button" class="w-full rounded-lg px-3 py-2.5 text-left hover:bg-slate-50" @click="inventoryMoreOpen = false; showInventoryImport = true"><span class="block text-sm font-semibold text-slate-800">期初库存管理</span><span class="mt-1 block text-xs text-slate-500">历史库存补录、模板下载与导入</span></button>
                </PopoverContent></PopoverPortal>
              </PopoverRoot></div>
            </div>

          </div>
          <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-slate-50/70 px-4 py-3">
            <div class="flex flex-wrap items-center gap-3"><label class="inline-flex items-center gap-2"><span class="text-xs font-semibold text-slate-600">客户</span><select v-model="selectedCustomer" aria-label="库存台账客户筛选" class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-xs"><option v-for="customer in customerFilterOptions" :key="customer" :value="customer">{{ customer }}</option></select></label><div class="inline-flex items-center gap-2"><span class="text-xs font-semibold text-slate-600">入库时间</span><DateRangeFilter v-model="inventoryBalanceDateRange" label="结存台账入库时间范围" title="按最近一次入库时间筛选" /></div><button type="button" aria-label="清空结存台账筛选" :disabled="!hasInventoryBalanceFilters" class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-[11px] font-bold text-slate-600 disabled:cursor-not-allowed disabled:opacity-40" @click="clearInventoryBalanceFilters">清空筛选</button></div>
            <div class="flex flex-wrap items-center gap-2"><span class="mr-2 text-xs text-slate-600">已选 <b class="text-teal-700">{{ selectedInventoryTargetIds.length }}</b> 条</span><button type="button" :disabled="!apiConnected" class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-xs font-bold text-slate-600 disabled:opacity-40" @click="showStocktake = true">库存盘点</button><button type="button" :disabled="!apiConnected || !selectedInventoryTargetIds.length" class="inline-flex h-9 items-center gap-2 rounded-lg bg-teal-700 px-4 text-xs font-bold text-white disabled:opacity-40" @click="openInventoryOperation('OUTBOUND', '', true, $event)"><PackageCheck class="size-4" />登记所选库存出库</button></div>
          </div>
          <div class="overflow-x-auto">
            <table class="inventory-balance-table min-w-[1180px] w-full table-fixed text-left">
              <colgroup>
                <col style="width: 3.25rem">
                <col style="width: calc((100% - 12.25rem) * 0.08)">
                <col style="width: calc((100% - 12.25rem) * 0.16)">
                <col style="width: calc((100% - 12.25rem) * 0.12)">
                <col style="width: calc((100% - 12.25rem) * 0.09)">
                <col style="width: calc((100% - 12.25rem) * 0.08)">
                <col style="width: calc((100% - 12.25rem) * 0.13)">
                <col style="width: calc((100% - 12.25rem) * 0.08)">
                <col style="width: calc((100% - 12.25rem) * 0.10)">
                <col style="width: calc((100% - 12.25rem) * 0.16)">
                <col style="width: 9rem">
              </colgroup>
              <thead class="bg-slate-50 text-[10px] font-bold text-slate-500"><tr><th scope="col" class="px-4 py-3"><label class="inline-flex cursor-pointer items-center" title="全选筛选结果"><input type="checkbox" aria-label="全选库存筛选结果" class="size-5 cursor-pointer accent-teal-600" :checked="inventoryBalances.filter((row) => row.balance > 0).length > 0 && inventoryBalances.filter((row) => row.balance > 0).every((row) => selectedInventoryTargetIds.includes(row.id))" @change="toggleVisibleInventoryBalances(($event.target as HTMLInputElement).checked)"><span class="sr-only">全选筛选结果</span></label></th><th class="px-4 py-3">客户</th><th class="px-4 py-3">合同号</th><th class="px-4 py-3">货号</th><th class="px-4 py-3">纸品类型</th><th class="px-4 py-3">纸质</th><th class="px-4 py-3">规格</th><th class="px-4 py-3">仓位</th><th class="px-4 py-3 text-right">当前结存</th><th class="px-4 py-3">最近单据 / 变动</th><th class="px-4 py-3 text-right">操作</th></tr></thead>
              <tbody class="divide-y divide-slate-100">
                <tr v-for="row in inventoryBalances" :key="row.id" :data-inventory-balance="row.id" class="hover:bg-teal-50/40" :class="selectedInventoryTargetIds.includes(row.id) ? 'bg-teal-50/50' : ''">
                  <td class="px-4 py-3"><input v-model="selectedInventoryTargetIds" class="size-5 accent-teal-600" type="checkbox" :value="row.id" :disabled="row.balance <= 0" :aria-label="`选择库存 ${row.itemNo} ${row.specification}`"></td>
                  <td class="px-4 py-3 font-semibold">{{ row.customer }}</td>
                  <td class="break-all px-4 py-3 font-mono font-semibold">{{ row.poNumber || '—' }}</td>
                  <td class="break-all px-4 py-3 font-mono font-semibold">{{ row.itemNo }}</td>
                  <td class="px-4 py-3 font-semibold">{{ row.packagingType }}</td>
                  <td class="px-4 py-3 font-semibold text-teal-700">{{ row.paperQuality }}</td>
                  <td class="break-words px-4 py-3 text-slate-600">{{ row.specification }}</td>
                  <td class="break-words px-4 py-3">{{ row.location }}</td>
                  <td class="px-4 py-3 text-right text-[14px] font-bold tabular-nums text-teal-700">{{ formatNumber(row.balance) }} <span class="text-[10px] font-medium text-slate-500">{{ row.unit }}</span></td>
                  <td class="px-4 py-3"><div class="break-all font-mono text-[11px] font-semibold">{{ inventoryBalanceLatestDocumentNo(row) || '—' }}</div><div class="mt-0.5 text-[10px] text-slate-500">{{ row.date }}</div></td><td class="px-4 py-3"><div class="flex justify-end gap-2"><button type="button" :aria-label="`出库 ${row.id}`" :disabled="!apiConnected || row.balance <= 0" class="h-8 whitespace-nowrap rounded-md bg-teal-700 px-3 text-xs font-bold text-white disabled:opacity-40" @click="openInventoryOperation('OUTBOUND', row.id, false, $event)">出库</button><button type="button" :aria-label="`调仓 ${row.id}`" :disabled="!apiConnected || row.balance <= 0 || !authStore.can('carton_procurement:inventory_write')" class="h-8 whitespace-nowrap rounded-md border border-teal-200 px-2 text-xs font-bold text-teal-700 hover:bg-teal-50 disabled:opacity-40" @click="openInventoryRelocation(row, $event)">调仓</button></div></td>
                </tr>
                <tr v-if="inventoryBalances.length === 0"><td colspan="11" class="px-4 py-12 text-center text-slate-400">没有符合当前筛选条件的实时结存</td></tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div class="border-b border-slate-200 px-4 py-3">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div><h2 class="font-bold text-slate-950">逐笔交易流水</h2><p class="mt-1 text-[11px] text-slate-500">本表只追踪库存数量变化；提交、追加、退单和修改请在统一操作日志中追溯。</p></div>
              <button type="button" class="h-9 rounded-lg border border-violet-200 bg-violet-50 px-3 text-[11px] font-bold text-violet-700 hover:bg-violet-100" @click="setActiveTab('audit')"><GitBranch class="mr-1 inline size-3.5" />查看统一操作日志</button>
            </div>
            <div class="mt-3 flex flex-wrap items-end gap-3 rounded-lg bg-slate-50 p-3">
              <label class="space-y-1"><span class="block text-[10px] font-bold text-slate-500">流水类型</span><select v-model="inventoryMovementFilter" aria-label="库存流水类型" class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-[11px]"><option value="ALL">全部</option><option value="INBOUND">入库</option><option value="OUTBOUND">出库</option><option value="ADJUSTMENT">调整</option><option value="REVERSAL">冲销</option></select></label>
              <div class="space-y-1"><span class="block text-[10px] font-bold text-slate-500">流水日期</span><DateRangeFilter v-model="inventoryMovementDateRange" label="库存流水日期范围" /></div>
            </div>
          </div>
          <div class="overflow-x-auto">
            <table class="min-w-[1380px] w-full text-left">
              <thead class="bg-slate-50 text-[10px] font-bold text-slate-500"><tr><th class="px-4 py-3">时间 / 流水号</th><th class="px-4 py-3">来源单据</th><th class="px-4 py-3">客户 / PO</th><th class="px-4 py-3">货号</th><th class="px-4 py-3">纸品</th><th class="px-4 py-3">纸质</th><th class="px-4 py-3">类型</th><th class="px-4 py-3 text-right">变动数量</th><th class="px-4 py-3 text-right">结存</th><th class="px-4 py-3">仓位</th><th class="px-4 py-3">经手人</th><th class="px-4 py-3">操作</th></tr></thead>
              <tbody class="divide-y divide-slate-100">
                <tr v-for="row in visibleMovements" :key="row.id" class="hover:bg-slate-50/80">
                  <td class="px-4 py-3"><div class="font-semibold">{{ row.date }}</div><div class="mt-0.5 font-mono text-[10px] text-slate-400">{{ row.id }}</div></td>
                  <td class="px-4 py-3"><div class="font-mono font-semibold">{{ row.documentNo }}</div><div class="mt-0.5 text-[10px] text-slate-500">{{ row.source }}</div></td>
                  <td class="px-4 py-3"><div class="font-semibold">{{ row.customer }}</div><div class="mt-0.5 text-[10px] text-slate-500">{{ row.poNumber }}</div></td>
                  <td class="px-4 py-3 font-mono font-semibold">{{ row.itemNo }}</td>
                  <td class="px-4 py-3"><div class="font-semibold">{{ row.packagingType }}</div><div class="text-[10px] text-slate-500">{{ row.specification }}</div></td>
                  <td class="px-4 py-3 font-semibold text-teal-700">{{ row.paperQuality }}</td>
                  <td class="px-4 py-3"><span class="rounded-full px-2 py-0.5 text-[10px] font-bold ring-1 ring-inset" :class="row.movementType === '入库' ? toneClass('green') : row.movementType === '出库' ? toneClass('blue') : toneClass('amber')">{{ row.movementType }}</span></td>
                  <td class="px-4 py-3 text-right font-bold tabular-nums" :class="row.quantity < 0 ? 'text-red-600' : 'text-emerald-700'">{{ row.quantity > 0 ? '+' : '' }}{{ row.quantity }}</td>
                  <td class="px-4 py-3 text-right font-bold tabular-nums">{{ row.balance }}</td>
                  <td class="px-4 py-3">{{ row.location }}</td><td class="px-4 py-3">{{ row.operator }}</td>
                  <td class="px-4 py-3"><button v-if="movementCanReverse(row)" type="button" class="h-8 rounded-lg border border-red-200 bg-white px-3 text-[10px] font-bold text-red-700 hover:bg-red-50" @click="openInventoryReversal(row)">冲销</button><span v-else-if="localMovements.some((candidate) => candidate.reversalOfMovementId === row.id)" class="text-[10px] font-bold text-slate-400">已冲销</span><span v-else class="text-[10px] text-slate-300">—</span></td>
                </tr>
                <tr v-if="visibleMovements.length === 0"><td colspan="12" class="px-4 py-12 text-center text-slate-400">没有符合当前筛选条件的库存流水</td></tr>
              </tbody>
            </table>
          </div>
        </div>
        </template>
      </section>

      <CartonInventorySummary v-else-if="activeTab === 'inventory-summary'" :factory-id="selectedFactoryId" :customers="customerRecords" :search="globalSearch" :refresh-key="inventoryReportRefreshKey" :connected="apiConnected" @clear-search="globalSearch = ''" @inventory="setActiveTab('inventory')" @closing="setActiveTab('closing')" />

      <section v-else-if="activeTab === 'closing'" class="space-y-4">
        <div class="grid gap-4 xl:grid-cols-[1fr_380px]">
          <article class="rounded-xl border border-violet-200 bg-violet-50 p-4 shadow-sm"><div class="flex items-center gap-2 font-bold text-violet-950"><FileSpreadsheet class="size-4" />期间月结与供应商对账页</div><p class="mt-1 text-[11px] leading-5 text-violet-800">回答“某客户在选定期间的期初、入库、出库、调整和期末是否对平”。当月可以核对确认并继续收发货；月份结束、数据核对完成后，再由主管最终锁账。</p></article>
          <article class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div class="text-[11px] font-bold text-slate-900">与库存页面的区别</div><p class="mt-1 text-[11px] text-slate-500">要看当前余量、仓位或某一笔收发来源，应返回实时库存台账。</p><button type="button" class="mt-3 text-[11px] font-bold text-teal-700" @click="setActiveTab('inventory')">去实时库存台账 →</button></article>
        </div>
        <div class="grid gap-3 md:grid-cols-3">
          <article class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div class="text-[11px] text-slate-500">月结期间</div><div class="mt-2 flex flex-wrap items-center gap-2"><input v-model="closingPeriod" aria-label="月结期间" type="month" class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-[13px] font-bold outline-none focus:border-teal-500"><button type="button" :disabled="closingBusyId === 'generate'" class="h-9 rounded-lg bg-teal-700 px-3 text-[11px] font-bold text-white disabled:cursor-not-allowed disabled:opacity-50" @click="generateClosingSnapshot">{{ closingBusyId === 'generate' ? '生成中…' : '生成月结草稿' }}</button></div><div class="mt-1 text-[10px] text-slate-400">按所选月份形成快照，生成或更新草稿后需重新核对；已锁账客户不受影响</div></article>
          <article class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div class="text-[11px] text-slate-500">客户对账</div><div class="mt-2 text-2xl font-bold">{{ visibleClosings.length }} 家</div><div class="mt-1 text-[10px] text-slate-400">固定一家纸箱供应商，按客户核对</div></article>
          <article class="rounded-xl border border-amber-200 bg-amber-50 p-4 shadow-sm"><div class="text-[11px] font-bold text-amber-800">待处理</div><div class="mt-2 text-2xl font-bold text-amber-900">{{ visibleClosings.filter((row) => row.status !== '已锁账').length }}</div><div class="mt-1 text-[10px] text-amber-700">草稿、待核对或已核对确认的客户</div></article>
        </div>
        <div class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div class="border-b border-slate-200 px-4 py-3"><h2 class="font-bold text-slate-950">客户月结汇总快照</h2><p class="mt-1 text-[11px] text-slate-500">期末 = 期初 + 入库 − 出库 + 调整；库存金额按移动加权成本计算。缺价或计价异常处理后才能确认、锁账。</p></div>
          <div class="overflow-x-auto">
            <table class="min-w-[1220px] w-full text-left">
              <thead class="bg-slate-50 text-[10px] font-bold text-slate-500"><tr><th class="px-4 py-3">客户</th><th class="px-4 py-3">期间</th><th class="px-4 py-3 text-right">期初</th><th class="px-4 py-3 text-right">入库</th><th class="px-4 py-3 text-right">出库</th><th class="px-4 py-3 text-right">调整</th><th class="px-4 py-3 text-right">期末</th><th class="px-4 py-3 text-right">期末金额</th><th class="px-4 py-3">对账状态</th><th class="px-4 py-3">操作</th></tr></thead>
              <tbody class="divide-y divide-slate-100">
                <tr v-for="row in visibleClosings" :key="row.id" class="hover:bg-slate-50/80">
                  <td class="px-4 py-3 font-bold">{{ row.customer }}</td><td class="px-4 py-3">{{ row.period }}</td><td class="px-4 py-3 text-right tabular-nums">{{ row.openingQuantity }}</td><td class="px-4 py-3 text-right text-emerald-700 tabular-nums">+{{ row.inboundQuantity }}</td><td class="px-4 py-3 text-right text-blue-700 tabular-nums">-{{ row.outboundQuantity }}</td><td class="px-4 py-3 text-right tabular-nums">{{ row.adjustmentQuantity > 0 ? '+' : '' }}{{ row.adjustmentQuantity }}</td><td class="px-4 py-3 text-right text-[14px] font-bold tabular-nums">{{ row.endingQuantity }}</td><td class="px-4 py-3 text-right"><div class="font-semibold tabular-nums">{{ formatMoney(row.endingAmount, row.currency) }}</div><div class="mt-0.5 text-[9px] font-bold text-slate-400">{{ row.currency }}</div><div v-if="closingRecord(row.id)?.pricing_issues?.length" class="mt-1 text-xs font-semibold text-amber-700">暂估金额 · 待核价</div></td><td class="px-4 py-3"><span class="rounded-full px-2 py-0.5 text-[10px] font-bold ring-1 ring-inset" :class="toneClass(row.tone)">{{ row.status }}</span></td><td class="px-4 py-3"><button type="button" :disabled="closingButtonDisabled(row.id)" :title="closingButtonHint(row.id)" class="h-8 rounded-lg border border-teal-200 bg-white px-3 text-[11px] font-bold text-teal-700 disabled:cursor-not-allowed disabled:border-slate-200 disabled:text-slate-400" @click="advanceClosing(row.id)">{{ closingBusyId === row.id ? '处理中…' : closingButtonLabel(row.id) }}</button><button v-if="closingRecord(row.id)?.status === 'LOCKED' && canFinalizeClosing" type="button" :disabled="Boolean(closingBusyId)" class="ml-2 h-8 rounded-lg border border-amber-300 px-3 text-xs font-bold text-amber-800" @click="openClosingDecision(closingRecord(row.id)!, 'UNLOCK')">解锁重核</button><p class="mt-1 max-w-52 text-[10px] text-slate-500">{{ closingButtonHint(row.id) }}</p></td>
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
      </section>

      <section v-else-if="activeTab === 'exceptions'" class="space-y-4">
        <div class="rounded-xl border border-blue-200 bg-blue-50 p-4 text-[11px] leading-5 text-blue-800"><div class="font-bold text-blue-950">导入异常会在这里形成正式待办</div><p class="mt-1">排期疑似漏单、送货单未匹配、数量差异和匹配不唯一均需人工处理；排期导入本身不会创建订单，送货单导入本身不会增加库存。</p></div>
        <div class="grid gap-3 md:grid-cols-3"><article class="rounded-xl border border-red-200 bg-red-50 p-4"><div class="text-[11px] font-bold text-red-800">高优先级</div><div class="mt-2 text-2xl font-bold text-red-900">{{ visibleExceptions.filter((row) => row.tone === 'red' && row.status !== '已关闭').length }}</div></article><article class="rounded-xl border border-amber-200 bg-amber-50 p-4"><div class="text-[11px] font-bold text-amber-800">待处理 / 处理中</div><div class="mt-2 text-2xl font-bold text-amber-900">{{ visibleExceptions.filter((row) => row.status === '待处理' || row.status === '处理中').length }}</div></article><article class="rounded-xl border border-slate-200 bg-white p-4"><div class="text-[11px] font-bold text-slate-600">已解决 / 已关闭</div><div class="mt-2 text-2xl font-bold text-slate-900">{{ visibleExceptions.filter((row) => row.status === '已解决' || row.status === '已关闭').length }}</div></article></div>
        <div class="grid gap-3 xl:grid-cols-2">
          <article v-for="row in visibleExceptions" :key="row.id" class="rounded-xl border p-4 shadow-sm" :class="toneClass(row.tone, 'surface')">
            <div class="flex items-start gap-3"><span class="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-white/80"><AlertTriangle class="size-4" /></span><div class="min-w-0 flex-1"><div class="flex flex-wrap items-center gap-2"><span class="text-[10px] font-bold">{{ row.id }}</span><span class="rounded-full bg-white/70 px-2 py-0.5 text-[10px] font-bold">{{ row.type }}</span><span class="ml-auto rounded-full bg-white/70 px-2 py-0.5 text-[10px] font-bold">{{ row.status }}</span></div><h2 class="mt-2 text-[14px] font-bold">{{ row.title }}</h2><p class="mt-1 text-[11px] opacity-80">{{ row.detail }}</p><div class="mt-3 flex flex-wrap gap-4 text-[10px] font-semibold"><span>客户：{{ row.customer }}</span><span>责任部门：{{ row.owner }}</span><span>{{ row.deadline }}</span></div><div v-if="exceptionRecord(row.id)" class="mt-3 flex flex-col gap-2 border-t border-current/10 pt-3 sm:flex-row"><input v-model="resolutionNotes[exceptionRecordId(row.id)]" :aria-label="`${row.id} 处理说明`" :placeholder="exceptionRecord(row.id)?.status === 'IN_PROGRESS' ? '填写核对结果（解决前必填）' : '可填写处理说明'" class="h-9 min-w-0 flex-1 rounded-lg border border-white/80 bg-white/80 px-3 text-[11px] text-slate-800 outline-none focus:border-teal-500"><button type="button" :disabled="exceptionButtonDisabled(row.id)" class="h-9 rounded-lg bg-white px-3 text-[11px] font-bold text-teal-700 shadow-sm disabled:cursor-not-allowed disabled:text-slate-400" @click="advanceException(row.id)">{{ exceptionBusyId === exceptionRecord(row.id)?.id ? '处理中…' : exceptionButtonLabel(row.id) }}</button></div></div></div>
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

    <DialogRoot :open="showInventoryRelocation" @update:open="(open) => { if (!relocationBusy) showInventoryRelocation = open }">
      <DialogOverlay class="fixed inset-0 z-[70] bg-slate-950/40 backdrop-blur-sm" />
      <DialogContent class="fixed left-1/2 top-1/2 z-[71] max-h-[90vh] w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-2xl bg-white p-6 shadow-2xl" @interact-outside.prevent @escape-key-down="(event) => { if (relocationBusy) event.preventDefault() }" @close-auto-focus="restoreInventoryFocus">
        <div class="flex items-start justify-between gap-4">
          <div><DialogTitle class="text-lg font-bold text-slate-950">库存调仓</DialogTitle><DialogDescription class="mt-1 text-sm text-slate-500">将这条库存整体移至新仓位，数量保持不变。</DialogDescription></div>
          <DialogClose :disabled="relocationBusy" aria-label="关闭调仓" class="rounded-lg p-1 text-slate-500 hover:bg-slate-100 disabled:opacity-40"><X class="size-5" /></DialogClose>
        </div>
        <form v-if="relocationTarget" class="mt-5 space-y-5" @submit.prevent="submitInventoryRelocation">
          <div class="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <div class="flex items-start justify-between gap-3"><div><p class="font-bold text-slate-950">{{ relocationTarget.customer }} · {{ relocationTarget.itemNo }}</p><p class="mt-1 text-xs text-slate-500">合同号 {{ relocationTarget.poNumber || '—' }}</p></div><span class="whitespace-nowrap text-lg font-bold text-teal-700">{{ formatNumber(relocationTarget.balance) }} <span class="text-xs font-medium">{{ relocationTarget.unit }}</span></span></div>
            <p class="mt-3 text-sm text-slate-600">{{ relocationTarget.packagingType }} · {{ relocationTarget.paperQuality }} · {{ relocationTarget.specification }}</p>
          </div>
          <div class="grid gap-3 sm:grid-cols-2">
            <div><span class="block text-xs font-semibold text-slate-500">当前仓位</span><div class="mt-2 flex h-11 items-center rounded-lg bg-slate-100 px-3 font-semibold text-slate-600">{{ relocationTarget.location || '未设置仓位' }}</div></div>
            <label><span class="block text-xs font-semibold text-teal-700">目标仓位 *</span><input v-model="relocationLocation" :disabled="relocationBusy" aria-label="调仓目标仓位" maxlength="128" placeholder="例如 纸箱仓 B-02" class="mt-2 h-11 w-full rounded-lg border border-teal-300 bg-white px-3 outline-none focus:ring-2 focus:ring-teal-100"></label>
          </div>
          <label class="block"><span class="text-xs font-semibold text-slate-600">调仓备注 <span class="font-normal text-slate-400">（选填）</span></span><textarea v-model="relocationNote" :disabled="relocationBusy" aria-label="调仓备注" maxlength="2000" rows="2" placeholder="例如 库位整理，移至靠近出货区" class="mt-2 w-full resize-none rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500" /></label>
          <p class="text-xs leading-5 text-slate-500">这条结存以最新调仓仓位为准，历史收发记录保留原仓位。调仓前后仓位及经手人可在操作日志中查看。</p>
          <p v-if="relocationFeedback" role="alert" class="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">{{ relocationFeedback }}</p>
          <div class="flex justify-end gap-3 border-t border-slate-100 pt-4"><DialogClose :disabled="relocationBusy" class="h-10 rounded-lg border border-slate-200 px-4 text-sm font-semibold text-slate-600 disabled:opacity-40">取消</DialogClose><button type="submit" :disabled="!apiConnected || relocationBusy || !authStore.can('carton_procurement:inventory_write')" class="h-10 rounded-lg bg-teal-700 px-5 text-sm font-bold text-white hover:bg-teal-800 disabled:opacity-40">{{ relocationBusy ? '正在调仓…' : '确认调仓' }}</button></div>
        </form>
      </DialogContent>
    </DialogRoot>

    <DialogRoot :open="showInventoryOperation" @update:open="setInventoryDialogOpen">
      <DialogOverlay class="fixed inset-0 z-[70] bg-slate-950/40 backdrop-blur-sm" />
      <DialogContent class="fixed left-1/2 top-1/2 z-[71] max-h-[90vh] w-[calc(100%-2rem)] max-w-3xl -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-2xl bg-white p-5 shadow-2xl" @interact-outside.prevent @close-auto-focus="restoreInventoryFocus">
        <div class="mb-3 flex justify-end"><DialogClose :disabled="inventoryOperationBusy" aria-label="关闭库存作业" class="rounded-lg p-1 text-slate-500 hover:bg-slate-100 disabled:opacity-40"><X class="size-5" /></DialogClose></div>
        <form class="rounded-xl border border-teal-200 bg-white p-4 shadow-sm" @submit.prevent="inventoryBulkMode ? submitBulkInventoryOutbound() : submitInventoryOperation()">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div>
              <DialogTitle class="text-lg font-bold text-slate-950">{{ inventoryBulkMode ? '批量出库' : '登记库存作业' }}</DialogTitle>
              <DialogDescription class="mt-1 text-sm text-slate-500">{{ inventoryBulkMode ? '逐条填写本次出库数量，核对出库后结存，再确认提交。' : '核对库存、数量和来源单据后确认；每次操作都会保留流水。' }}</DialogDescription>
            </div>
            <div v-if="!inventoryBulkMode" class="flex rounded-lg border border-slate-200 bg-slate-50 p-1">
              <button type="button" class="h-8 rounded-md px-3 text-[11px] font-bold" :class="inventoryOperationType === 'OUTBOUND' ? 'bg-blue-700 text-white shadow-sm' : 'text-slate-600'" @click="setInventoryOperationType('OUTBOUND')">出库</button>
              <button type="button" class="h-8 rounded-md px-3 text-[11px] font-bold" :class="inventoryOperationType === 'ADJUSTMENT' ? 'bg-amber-600 text-white shadow-sm' : 'text-slate-600'" @click="setInventoryOperationType('ADJUSTMENT')">库存调整</button>
            </div>
          </div>
          <div v-if="inventoryBulkMode" class="mt-4 max-h-[45vh] overflow-auto rounded-lg border border-slate-200">
            <table class="w-full min-w-[760px] text-left text-xs">
              <thead class="sticky top-0 bg-slate-50 text-slate-500"><tr><th class="px-3 py-3">客户 / 合同</th><th class="px-3 py-3">货号 / 纸品</th><th class="px-3 py-3">仓位</th><th class="px-3 py-3 text-right">当前结存</th><th class="px-3 py-3 text-right">本次出库 *</th><th class="px-3 py-3 text-right">出库后结存</th></tr></thead>
              <tbody class="divide-y divide-slate-100"><tr v-for="row in selectedInventoryBalances" :key="row.id">
                <td class="px-3 py-3"><div class="font-semibold">{{ row.customer }}</div><div class="mt-1 font-mono text-slate-500">{{ row.poNumber || '无合同' }}</div></td>
                <td class="px-3 py-3"><div class="font-mono font-semibold">{{ row.itemNo }}</div><div class="mt-1 text-slate-500">{{ row.packagingType }} · {{ row.paperQuality }} · {{ row.specification }}</div></td>
                <td class="px-3 py-3">{{ row.location || '未设置' }}</td><td class="whitespace-nowrap px-3 py-3 text-right">{{ formatNumber(row.balance) }} {{ row.unit }}</td>
                <td class="px-3 py-3"><input v-model="inventoryBulkQuantities[row.id]" :aria-label="`本次出库数量 ${row.id}`" type="number" step="0.0001" min="0.0001" :max="row.balance" :disabled="inventoryOperationBusy" required class="h-10 w-28 rounded-lg border border-teal-200 bg-white px-3 text-right font-semibold outline-none focus:border-teal-500"></td>
                <td class="whitespace-nowrap px-3 py-3 text-right font-semibold text-teal-700">{{ bulkOutboundRemaining(row) }}</td>
              </tr></tbody>
            </table>
          </div>
          <div class="mt-4 grid gap-3 md:grid-cols-2">
            <label v-if="!inventoryBulkMode" class="space-y-1.5"><span class="text-[10px] font-bold text-slate-600">库存记录 *</span><select v-model="inventoryTargetId" aria-label="库存作业记录" class="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 outline-none focus:border-teal-500" @change="selectInventoryTarget(inventoryTargetId)"><option value="">请选择客户、合同、货号和纸品</option><option v-for="row in operableInventoryBalances" :key="row.id" :value="row.id">{{ row.customer }} · {{ row.poNumber || '无合同' }} · {{ row.itemNo }} · {{ row.packagingType }} {{ row.paperQuality }} · 结存 {{ row.balance }}</option></select></label>
            <label v-if="!inventoryBulkMode" class="space-y-1.5"><span class="text-[10px] font-bold text-slate-600">{{ inventoryOperationType === 'OUTBOUND' ? '出库数量' : '调整数量' }} *</span><input v-model.number="inventoryOperationQuantity" aria-label="库存作业数量" type="number" step="0.0001" :min="inventoryOperationType === 'OUTBOUND' ? 0.0001 : undefined" :placeholder="inventoryOperationType === 'OUTBOUND' ? '大于 0' : '盘盈正数 / 盘亏负数'" class="h-10 w-full rounded-lg border border-slate-200 px-3 text-right font-semibold outline-none focus:border-teal-500"></label>
            <label class="space-y-1.5"><span class="text-[10px] font-bold text-slate-600">来源单据号 *</span><input v-model="inventoryOperationDocumentNo" aria-label="库存作业单据号" placeholder="例如 OUT-260811-001" class="h-10 w-full rounded-lg border border-slate-200 px-3 font-mono outline-none focus:border-teal-500"></label>
            <label v-if="!inventoryBulkMode" class="space-y-1.5"><span class="text-[10px] font-bold text-slate-600">仓位</span><input v-model="inventoryOperationLocation" aria-label="库存作业仓位" placeholder="例如 A-01" class="h-10 w-full rounded-lg border border-slate-200 px-3 outline-none focus:border-teal-500"></label>
          </div>
          <div class="mt-3 flex flex-col gap-3 lg:flex-row lg:items-end">
            <label class="min-w-0 flex-1 space-y-1.5">
              <span class="text-[10px] font-bold text-slate-600">{{ inventoryOperationType === 'OUTBOUND' ? '出库原因' : '调整原因' }} *</span>
              <select v-if="inventoryOperationType === 'OUTBOUND'" v-model="inventoryOperationReason" aria-label="库存作业原因" class="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 outline-none focus:border-teal-500">
                <option v-for="reason in inventoryOutboundReasons" :key="reason" :value="reason">{{ reason }}</option>
              </select>
              <input v-else v-model="inventoryOperationReason" aria-label="库存作业原因" placeholder="例如月中盘点差异" class="h-10 w-full rounded-lg border border-slate-200 px-3 outline-none focus:border-teal-500">
            </label>
            <button type="submit" :disabled="!apiConnected || inventoryOperationBusy" class="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-teal-700 px-5 text-[12px] font-bold text-white disabled:cursor-not-allowed disabled:opacity-50"><CheckCircle2 class="size-4" />{{ inventoryOperationBusy ? '正在登记…' : inventoryBulkMode ? '确认批量出库' : inventoryOperationType === 'OUTBOUND' ? '确认出库' : '确认调整' }}</button>

          </div>
          <div v-if="inventoryOperationFeedback" role="status" class="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-[11px] font-semibold text-slate-700">{{ inventoryOperationFeedback }}</div>
        </form>
      </DialogContent>
    </DialogRoot>

    <DialogRoot v-model:open="showReceiptDialog">
      <DialogOverlay class="fixed inset-0 z-[70] bg-slate-950/45" />
      <DialogContent class="fixed left-1/2 top-1/2 z-[71] flex max-h-[92vh] w-[calc(100%-2rem)] max-w-[1500px] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl bg-white shadow-2xl" @interact-outside.prevent @close-auto-focus="restoreReceiptFocus">
        <div class="flex shrink-0 items-start justify-between gap-4 border-b border-slate-200 px-6 py-4">
          <div><DialogTitle class="text-lg font-bold text-slate-950">{{ receiptEntryMode === 'MANUAL' ? '人工录入订单收料' : '送货单收料反馈' }}</DialogTitle><DialogDescription class="mt-1 text-sm text-slate-500">核对本次送货信息及各项收料数量，保存后再确认入库。</DialogDescription></div>
          <DialogClose as-child><button type="button" aria-label="关闭收料录入" class="rounded-lg p-2 text-slate-500 hover:bg-slate-100"><X class="size-5" /></button></DialogClose>
        </div>
        <div class="min-h-0 space-y-4 overflow-y-auto p-4 sm:p-6">
          <div class="grid gap-4 rounded-xl border border-slate-200 bg-slate-50 p-4 sm:grid-cols-2">
            <label class="space-y-1.5"><span class="text-sm font-bold text-slate-600">送货单号 *</span><input ref="manualDeliveryNoteInput" v-model="receiptDeliveryNoteNo" :disabled="Boolean(currentReceipt)" aria-label="人工送货单号" :aria-invalid="receiptFeedbackTone === 'error' && receiptFeedbackMessage.includes('送货单号')" placeholder="例如 DN26081001" class="h-11 w-full rounded-lg border bg-white px-3 font-mono outline-none focus:border-blue-500" :class="receiptFeedbackTone === 'error' && receiptFeedbackMessage.includes('送货单号') ? 'border-red-400 ring-2 ring-red-100' : 'border-slate-200'" @input="receiptFeedbackMessage = ''"></label>
            <label class="space-y-1.5"><span class="text-sm font-bold text-slate-600">送货日期 *</span><input ref="manualDeliveryDateInput" v-model="receiptDeliveryDate" :disabled="Boolean(currentReceipt)" aria-label="人工送货日期" type="date" class="h-11 w-full rounded-lg border border-slate-200 bg-white px-3 outline-none focus:border-blue-500"></label>
          </div>
          <div class="flex flex-wrap gap-x-6 gap-y-2 text-sm text-slate-600">
            <p v-if="receiptCorrectionNote" class="w-full text-amber-700">{{ receiptCorrectionNote }} <span v-if="!currentReceipt">本次使用带“更正”后缀的新登记号，请核对后保存。</span></p>
            <span v-if="receiptEntryMode === 'MANUAL'">已选订单 <strong>{{ selectedManualReceiptOrders.length }} 张</strong></span><span>本次明细 <strong>{{ receiptLines.length }} 行</strong></span><span>有效收料<strong class="text-teal-700">{{ formatNumber(receiptTotals.effective) }}</strong></span>
            <span v-if="receiptEntryMode === 'MANUAL' && receiptLines.length" :class="manualReceiptWillCompleteOrder ? 'text-emerald-700' : 'text-amber-700'">{{ manualReceiptWillCompleteOrder ? '全部收齐，确认后自动完成' : '分批收料，确认后保持部分收料' }}</span>
          </div>
        <div class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div class="border-b border-slate-200 px-4 py-3">
            <h2 class="font-bold text-slate-950">收料反馈明细</h2>
            <p class="mt-1 text-sm text-teal-700">请按送货单填写本次入库单价，默认带出订单已有价格；留空或 0 表示待核价。</p>
            <p class="mt-1 text-sm text-slate-500">有效收料 = 实收 − 破损 − 拒收 − 其他不可用；非正式/打板明细不补建正式订单，保存后仍须人工确认才入库并进入月结。</p>
          </div>
          <div class="overflow-x-auto">
            <table class="min-w-[1440px] w-full text-left">
              <thead class="bg-slate-50 text-xs font-bold text-slate-500">
                <tr><th class="px-4 py-3">合同 / 货号</th><th class="px-4 py-3">品名 / 规格</th><th class="px-4 py-3 text-right">送货数量</th><th class="px-4 py-3 text-center">单价 / 单位</th><th class="px-3 py-3 text-right">实收</th><th class="px-3 py-3 text-right">破损</th><th class="px-3 py-3 text-right">拒收</th><th class="px-3 py-3 text-right">其他不可用</th><th class="px-4 py-3 text-right">有效收料</th><th class="px-4 py-3">仓位</th><th class="px-4 py-3">来源</th></tr>
              </thead>
              <tbody class="divide-y divide-slate-100">
                <tr v-for="row in visibleReceiptLines" :key="row.id" class="[&>td]:align-top [&>td]:py-3">
                  <td class="px-4 py-3">
                    <div v-if="row.sourceType === 'AD_HOC'" class="w-52 space-y-1.5">
                      <span class="inline-flex rounded-full bg-amber-50 px-2 py-0.5 text-[9px] font-bold text-amber-800 ring-1 ring-inset ring-amber-200">非正式 / 打板收料</span>
                      <select v-model="row.customerCode" :aria-label="`${row.id} 客户`" :disabled="Boolean(currentReceipt)" class="h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-xs outline-none focus:border-amber-500 disabled:bg-slate-50"><option value="">请选择客户 *</option><option v-for="customer in activeCustomers" :key="customer.id" :value="customer.customer_code">{{ customer.customer_name }}</option></select>
                      <input v-model="row.contractNo" :aria-label="`${row.id} 合同或来源号`" :disabled="Boolean(currentReceipt)" placeholder="合同/打板来源号（可空）" class="h-8 w-full rounded-md border border-slate-200 px-2 font-mono text-xs outline-none focus:border-amber-500 disabled:bg-slate-50">
                      <input v-model="row.itemNo" :aria-label="`${row.id} 货号`" :disabled="Boolean(currentReceipt)" placeholder="货号 *" class="h-8 w-full rounded-md border border-slate-200 px-2 font-mono text-xs outline-none focus:border-amber-500 disabled:bg-slate-50">
                    </div>
                    <div v-else class="space-y-1">
                      <div class="break-all font-mono text-sm font-semibold">{{ row.contractNo || '—' }}</div>
                      <div class="break-all font-mono text-xs text-slate-500">货号 {{ row.itemNo || '—' }}</div>
                    </div>
                  </td>
                  <td class="px-4 py-3">
                    <div v-if="row.sourceType === 'AD_HOC'" class="w-48 space-y-1.5">
                      <input v-model="row.packagingType" :aria-label="`${row.id} 纸品类型`" :disabled="Boolean(currentReceipt)" placeholder="纸品类型 *" class="h-8 w-full rounded-md border border-slate-200 px-2 text-xs outline-none focus:border-amber-500 disabled:bg-slate-50">
                      <input v-model="row.paperQuality" :aria-label="`${row.id} 纸质`" :disabled="Boolean(currentReceipt)" placeholder="纸质 *" class="h-8 w-full rounded-md border border-slate-200 px-2 text-xs outline-none focus:border-amber-500 disabled:bg-slate-50">
                      <input v-model="row.specification" :aria-label="`${row.id} 规格`" :disabled="Boolean(currentReceipt)" placeholder="规格 *" class="h-8 w-full rounded-md border border-slate-200 px-2 text-xs outline-none focus:border-amber-500 disabled:bg-slate-50">
                    </div>
                    <template v-else><div class="font-semibold">{{ row.description }}</div><div class="mt-0.5 text-xs text-slate-500">{{ row.specification }}</div></template>
                  </td>
                  <td class="px-4 py-2 text-right"><input v-if="receiptEntryMode === 'MANUAL' || row.sourceType === 'AD_HOC'" v-model.number="row.deliveryQuantity" :aria-label="`${row.id} 送货数量`" :disabled="Boolean(currentReceipt)" type="number" min="0" :max="row.sourceType === 'FORMAL_ORDER' && receiptEntryMode === 'MANUAL' ? row.remainingQuantity : undefined" class="ml-auto block h-8 w-24 rounded-md border border-slate-200 px-2 text-right font-semibold outline-none focus:border-blue-500 disabled:bg-slate-50"><div v-else class="font-semibold tabular-nums">{{ row.deliveryQuantity }}</div><div v-if="receiptEntryMode === 'MANUAL' && row.sourceType === 'FORMAL_ORDER'" class="mt-0.5 text-[9px] text-slate-400">待收 {{ formatNumber(row.remainingQuantity) }}</div></td>
                  <td class="px-4 py-2">
                    <div class="mx-auto w-28 text-center">
                      <input v-model.number="row.unitPrice" :aria-label="`${row.id} 单价`" :disabled="Boolean(currentReceipt)" type="number" min="0" step="0.000001" placeholder="送货单单价" class="block h-8 w-full rounded-md border border-slate-200 px-2 text-right text-xs outline-none focus:border-amber-500 disabled:bg-slate-50">
                      <div v-if="row.sourceType === 'AD_HOC'" class="mt-1 flex justify-center gap-1">
                        <select v-model="row.currency" :aria-label="`${row.id} 币种`" :disabled="Boolean(currentReceipt)" class="h-7 w-16 rounded border border-slate-200 bg-white px-1 text-[9px] disabled:bg-slate-50"><option value="CNY">CNY</option><option value="HKD">HKD</option><option value="USD">USD</option></select>
                        <input v-model="row.unit" :aria-label="`${row.id} 单位`" :disabled="Boolean(currentReceipt)" placeholder="单位" class="h-7 w-12 rounded border border-slate-200 px-1 text-[9px] disabled:bg-slate-50">
                      </div>
                      <div v-else class="mt-1 text-xs text-slate-500">{{ row.currency }} / {{ row.unit }}</div>
                      <div v-if="!Number(row.unitPrice)" class="mt-1 text-xs text-amber-700">待核价</div>
                    </div>
                  </td>
                  <td class="px-3 py-2"><input v-model.number="row.receivedQuantity" :aria-label="`${row.id} 实收`" :disabled="Boolean(currentReceipt)" type="number" min="0" class="ml-auto block h-8 w-20 rounded-md border border-slate-200 px-2 text-right font-semibold outline-none focus:border-teal-500 disabled:bg-slate-50"></td>
                  <td class="px-3 py-2"><input v-model.number="row.damagedQuantity" :aria-label="`${row.id} 破损`" :disabled="Boolean(currentReceipt)" type="number" min="0" class="ml-auto block h-8 w-20 rounded-md border border-slate-200 px-2 text-right outline-none focus:border-teal-500 disabled:bg-slate-50"></td>
                  <td class="px-3 py-2"><input v-model.number="row.rejectedQuantity" :aria-label="`${row.id} 拒收`" :disabled="Boolean(currentReceipt)" type="number" min="0" class="ml-auto block h-8 w-20 rounded-md border border-slate-200 px-2 text-right outline-none focus:border-teal-500 disabled:bg-slate-50"></td>
                  <td class="px-3 py-2"><input v-model.number="row.unusableQuantity" :aria-label="`${row.id} 其他不可用`" :disabled="Boolean(currentReceipt)" type="number" min="0" class="ml-auto block h-8 w-20 rounded-md border border-slate-200 px-2 text-right outline-none focus:border-teal-500 disabled:bg-slate-50"></td>
                  <td class="px-4 py-3 text-right text-[14px] font-bold text-teal-700 tabular-nums">{{ receiptLineEffectiveQuantity(row) }}</td>
                  <td class="px-4 py-2"><input v-model="row.location" :aria-label="`${row.id} 仓位`" :disabled="Boolean(currentReceipt)" placeholder="例如 A-01" class="h-8 w-24 rounded-md border border-slate-200 px-2 text-sm outline-none focus:border-teal-500 disabled:bg-slate-50"></td>
                  <td class="px-4 py-3"><span class="rounded-full px-2 py-0.5 text-xs font-bold ring-1 ring-inset" :class="row.sourceType === 'AD_HOC' ? 'bg-amber-50 text-amber-800 ring-amber-200' : 'bg-violet-50 text-violet-700 ring-violet-200'">{{ row.sourceLabel }}</span><button v-if="row.sourceType === 'AD_HOC' && !currentReceipt" type="button" class="mt-2 block text-[9px] font-bold text-red-600" @click="removeAdHocReceiptLine(row.id)">移除此行</button></td>
                </tr>
                <tr v-if="visibleReceiptLines.length === 0"><td colspan="11" class="px-4 py-12 text-center text-slate-400">没有找到匹配的送货明细</td></tr>
              </tbody>
              <tfoot class="border-t border-slate-200 bg-slate-50 font-bold">
                <tr><td colspan="2" class="px-4 py-3">本页合计</td><td class="px-4 py-3 text-right">{{ receiptTotals.delivered }}</td><td class="px-4 py-3 text-right">—</td><td class="px-3 py-3 text-right">{{ receiptTotals.received }}</td><td colspan="3" class="px-3 py-3 text-right text-red-600">不可用 {{ receiptTotals.unusable }}</td><td class="px-4 py-3 text-right text-teal-700">{{ receiptTotals.effective }}</td><td colspan="2" class="px-4 py-3">—</td></tr>
              </tfoot>
            </table>
          </div>
          <div class="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 px-4 py-3">
            <div class="min-w-0 flex-1">
              <p class="text-sm text-slate-500">只有逐行复核并正式确认后，后端才会按有效收料数量生成入库流水。</p>
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
              <button v-if="!currentReceipt" type="button" :disabled="receiptLines.length === 0 || savingReceipt" class="inline-flex h-9 items-center gap-2 rounded-lg border border-teal-300 bg-white px-4 text-[12px] font-bold text-teal-700 disabled:cursor-not-allowed disabled:opacity-50" @click="saveReceiptFeedback">
                <CheckCircle2 class="size-4" />{{ savingReceipt ? '正在保存…' : '保存待确认收料单' }}
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

    <div v-if="showCustomerModal" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4" @click.self="showCustomerModal = false">
      <div class="max-h-[92vh] w-full max-w-6xl overflow-y-auto rounded-2xl bg-white shadow-2xl">
        <div class="flex items-start justify-between border-b border-slate-200 px-5 py-4">
          <div><h2 class="text-[16px] font-bold text-slate-950">客户资料维护</h2><p class="mt-1 text-[11px] text-slate-500">仅维护 {{ activeFactory.shortName }} 客户；停用客户保留历史订单，但不能用于新建订单。</p></div>
          <button type="button" aria-label="关闭客户资料维护" class="rounded-lg p-2 text-slate-400 hover:bg-slate-100" @click="showCustomerModal = false"><X class="size-4" /></button>
        </div>
        <div class="grid gap-5 p-5 lg:grid-cols-[340px_minmax(0,1fr)]">
          <form class="space-y-4 rounded-xl border border-slate-200 bg-slate-50/70 p-4" @submit.prevent="saveCustomer">
            <div class="flex items-center justify-between"><div class="font-bold text-slate-950">{{ editingCustomerId ? '编辑客户' : '新增客户' }}</div><button v-if="editingCustomerId" type="button" class="text-[11px] font-bold text-teal-700" @click="resetCustomerForm">改为新增</button></div>
            <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
              <label class="space-y-1.5"><span class="text-[10px] font-bold text-slate-600">客户名称 *</span><input v-model="customerForm.customer_name" aria-label="客户名称" placeholder="客户正式名称" class="h-9 w-full rounded-lg border border-slate-200 bg-white px-3 outline-none focus:border-teal-500"></label>
              <label class="space-y-1.5"><span class="text-[10px] font-bold text-slate-600">国家 / 地区</span><input v-model="customerForm.country_region" aria-label="客户国家地区" placeholder="例如 德国" class="h-9 w-full rounded-lg border border-slate-200 bg-white px-3 outline-none focus:border-teal-500"></label>
              <label class="space-y-1.5"><span class="text-[10px] font-bold text-slate-600">联系人</span><input v-model="customerForm.contact_name" aria-label="客户联系人" class="h-9 w-full rounded-lg border border-slate-200 bg-white px-3 outline-none focus:border-teal-500"></label>
              <label class="space-y-1.5"><span class="text-[10px] font-bold text-slate-600">联系电话</span><input v-model="customerForm.contact_phone" aria-label="客户联系电话" class="h-9 w-full rounded-lg border border-slate-200 bg-white px-3 outline-none focus:border-teal-500"></label>
              <label class="space-y-1.5"><span class="text-[10px] font-bold text-slate-600">状态</span><select v-model="customerForm.status" aria-label="客户状态" class="h-9 w-full rounded-lg border border-slate-200 bg-white px-3 outline-none focus:border-teal-500"><option value="ACTIVE">启用</option><option value="INACTIVE">停用</option></select></label>
              <label class="space-y-1.5"><span class="text-[10px] font-bold text-slate-600">备注</span><textarea v-model="customerForm.note" aria-label="客户备注" rows="3" class="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 outline-none focus:border-teal-500"></textarea></label>
            </div>
            <button type="submit" :disabled="savingCustomer" class="h-9 w-full rounded-lg bg-teal-700 px-4 text-[12px] font-bold text-white disabled:opacity-60">{{ savingCustomer ? '正在保存…' : editingCustomerId ? '保存客户修改' : '新增客户' }}</button>
          </form>

          <section class="min-w-0">
            <div class="mb-3 flex flex-wrap items-center justify-between gap-3"><div><div class="font-bold text-slate-950">本厂客户清单 · {{ customerRecords.length }} 家</div><p class="mt-0.5 text-[10px] text-slate-500">已有订单的客户请停用，不要删除。</p></div><label class="relative"><Search class="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-slate-400" /><input v-model="customerSearch" aria-label="搜索客户资料" placeholder="搜索名称、联系人" class="h-9 w-64 rounded-lg border border-slate-200 pl-8 pr-3 text-[11px] outline-none focus:border-teal-500"></label></div>
            <div class="overflow-x-auto rounded-xl border border-slate-200">
              <table class="min-w-[720px] w-full text-left">
                <thead class="bg-slate-50 text-[10px] font-bold text-slate-500"><tr><th class="px-3 py-2.5">客户名称</th><th class="px-3 py-2.5">国家 / 地区</th><th class="px-3 py-2.5">联系人</th><th class="px-3 py-2.5">状态</th><th class="px-3 py-2.5 text-right">操作</th></tr></thead>
                <tbody class="divide-y divide-slate-100">
                  <tr v-for="customer in visibleCustomerRecords" :key="customer.id" class="hover:bg-slate-50/70">
                    <td class="px-3 py-3"><div class="font-semibold text-slate-900">{{ customer.customer_name }}</div><div v-if="customer.note" class="mt-0.5 max-w-56 truncate text-[9px] text-slate-400">{{ customer.note }}</div></td>
                    <td class="px-3 py-3 text-[11px] text-slate-600">{{ customer.country_region || '—' }}</td>
                    <td class="px-3 py-3 text-[11px] text-slate-600"><div>{{ customer.contact_name || '—' }}</div><div class="text-[9px] text-slate-400">{{ customer.contact_phone }}</div></td>
                    <td class="px-3 py-3"><span class="rounded-full px-2 py-0.5 text-[10px] font-bold ring-1 ring-inset" :class="customer.status === 'ACTIVE' ? 'bg-emerald-50 text-emerald-700 ring-emerald-200' : 'bg-slate-100 text-slate-500 ring-slate-200'">{{ customer.status === 'ACTIVE' ? '启用' : '停用' }}</span></td>
                    <td class="px-3 py-3"><div class="flex justify-end gap-1.5"><button type="button" :aria-label="`编辑客户 ${customer.customer_name}`" class="flex size-8 items-center justify-center rounded-lg border border-slate-200 text-slate-500 hover:border-teal-200 hover:text-teal-700" @click="editCustomer(customer)"><Pencil class="size-3.5" /></button><button type="button" :disabled="deletingCustomerId === customer.id" :aria-label="`删除客户 ${customer.customer_name}`" class="flex size-8 items-center justify-center rounded-lg border border-slate-200 text-slate-400 hover:border-red-200 hover:text-red-600 disabled:opacity-50" @click="removeCustomer(customer)"><Trash2 class="size-3.5" /></button></div></td>
                  </tr>
                  <tr v-if="visibleCustomerRecords.length === 0"><td colspan="5" class="px-4 py-12 text-center text-slate-400">没有符合条件的客户资料</td></tr>
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </div>
    </div>

    <div v-if="orderDetailRow" data-testid="order-detail-overlay" class="fixed inset-0 z-[62] flex items-center justify-center p-4 transition-colors" :class="orderDetailPinned ? 'pointer-events-auto bg-slate-950/45' : 'pointer-events-none bg-slate-950/25'" @click.self="closeOrderDetails">
      <div class="max-h-[88vh] w-full max-w-5xl overflow-y-auto rounded-2xl bg-white shadow-2xl" role="dialog" :aria-modal="orderDetailPinned ? 'true' : undefined" aria-labelledby="order-detail-title">
        <div class="flex items-start justify-between border-b border-slate-200 px-5 py-4">
          <div>
            <h2 id="order-detail-title" class="text-[18px] font-bold text-slate-950">订单明细 — {{ orderDetailRow.contractNo }} / {{ orderDetailRow.itemNo }}</h2>
            <p class="mt-1 text-[11px] text-slate-500">按合同查看纸品需求、实际入库和剩余待入库数量。<span class="ml-2 font-semibold text-teal-700">{{ orderDetailPinned ? '已固定显示' : '悬停预览 · 单击明细可固定' }}</span></p>
          </div>
          <button type="button" aria-label="关闭订单明细" class="rounded-lg p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700" @click="closeOrderDetails"><X class="size-4" /></button>
        </div>

        <div class="space-y-4 p-5">
          <section class="grid gap-x-5 gap-y-3 rounded-xl border border-emerald-200 bg-emerald-50/60 px-4 py-3 text-[12px] sm:grid-cols-2 lg:grid-cols-4">
            <div><span class="text-slate-500">客户</span><b class="ml-2 text-slate-900">{{ orderDetailRow.customer }}</b></div>
            <div><span class="text-slate-500">产品名称</span><b class="ml-2 text-slate-900">{{ orderDetailRecord?.product_name || '未记录' }}</b></div>
            <div><span class="text-slate-500">产品订单数量</span><b class="ml-2 tabular-nums text-slate-900">{{ formatNumber(orderDetailRow.orderQuantity) }}</b></div>
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
                    <td class="px-4 py-3 text-right font-semibold tabular-nums">{{ formatUnitsPerCarton(material.unitsPerCarton) }}</td>
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

    <div v-if="showOrderModal" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4" @click.self="showOrderModal = false">
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
              <label class="space-y-1.5"><span class="text-[11px] font-bold text-slate-600">客户</span><select v-model="orderForm.customerCode" aria-label="订单客户" :disabled="editingOrderStructureLocked" class="h-10 w-full rounded-lg border border-slate-200 px-3 outline-none focus:border-teal-500 disabled:bg-slate-50 disabled:text-slate-500"><option v-if="activeCustomers.length === 0 && !editingOrderRecord" value="">当前厂区暂无启用客户</option><option v-if="editingOrderRecord && !activeCustomers.some((customer) => customer.customer_code === editingOrderRecord?.customer_code)" :value="editingOrderRecord.customer_code">{{ editingOrderRecord.customer_name }}（已停用）</option><option v-for="customer in activeCustomers" :key="customer.id" :value="customer.customer_code">{{ customer.customer_name }}</option></select></label>
              <label class="space-y-1.5"><span class="text-[11px] font-bold text-slate-600">纸箱供应商</span><input value="河源东康纸品有限公司（系统固定）" aria-label="纸箱供应商" disabled class="h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-slate-500"></label>
              <label class="space-y-1.5"><span class="text-[11px] font-bold text-slate-600">合同号 *</span><input v-model="orderForm.contractNo" aria-label="合同号" :disabled="editingOrderStructureLocked" placeholder="例如 SC700145365" class="h-10 w-full rounded-lg border border-slate-200 px-3 outline-none focus:border-teal-500 disabled:bg-slate-50 disabled:text-slate-500"><span class="block text-[9px] text-slate-400">支持中英文、数字及 - _ . / # ( ) + &</span></label>
              <div class="relative space-y-1.5">
                <label class="block space-y-1.5"><span class="text-[11px] font-bold text-slate-600">货号 *</span><input v-model="orderForm.itemNo" aria-label="货号" :disabled="editingOrderStructureLocked" autocomplete="off" placeholder="例如 203302044" class="h-10 w-full rounded-lg border border-slate-200 px-3 outline-none focus:border-teal-500 disabled:bg-slate-50 disabled:text-slate-500" @focus="showHistoryItemSuggestions = historyItemSuggestionsLoading || historyItemSuggestions.length > 0" @keydown.esc="showHistoryItemSuggestions = false"></label>
                <div v-if="showHistoryItemSuggestions && (historyItemSuggestionsLoading || historyItemSuggestions.length > 0)" class="absolute left-0 top-[60px] z-30 max-h-80 w-[min(42rem,90vw)] overflow-y-auto rounded-xl border border-teal-200 bg-white p-1.5 shadow-2xl" aria-label="历史货号候选">
                  <div v-if="historyItemSuggestionsLoading" class="px-3 py-3 text-[11px] font-semibold text-slate-500">正在查找近似历史货号…</div>
                  <button v-for="suggestion in historyItemSuggestions" :key="`${suggestion.customer_code}-${suggestion.item_no}`" type="button" :aria-label="`复用历史货号 ${suggestion.item_no} ${suggestion.customer_name}`" class="block w-full rounded-lg px-3 py-2.5 text-left hover:bg-teal-50" @mousedown.prevent="applyHistoryItemSuggestion(suggestion)">
                    <span class="flex flex-wrap items-center gap-2"><span class="font-mono text-[12px] font-bold text-slate-950">{{ suggestion.item_no }}</span><span class="rounded-full bg-teal-50 px-2 py-0.5 text-[9px] font-bold text-teal-700">{{ historyItemMatchLabel(suggestion.match_type) }}</span><span class="text-[11px] font-semibold text-slate-700">{{ suggestion.product_name || '未记录品名' }}</span></span>
                    <span class="mt-1 block text-[10px] text-slate-500">{{ suggestion.customer_name }} · 最近 {{ suggestion.latest_order_no }} / {{ formatMonthDay(suggestion.latest_order_date) }} · {{ suggestion.lines.length }} 条纸品 · 历史 {{ suggestion.order_count }} 单</span>
                    <span class="mt-1 block truncate text-[10px] text-slate-400">{{ suggestion.lines.map((line) => `${line.packaging_type} ${line.paper_quality} ${line.specification}`).join('；') }}</span>
                  </button>
                </div>
                <span v-if="selectedHistoryItemSource" class="block text-[9px] font-semibold text-teal-700">已复用 {{ selectedHistoryItemSource.latest_order_no }}；本次合同、数量和日期仍需单独填写</span><span v-else class="block text-[9px] text-slate-400">输入 2 位以上货号，选择近似历史订单后自动带出客户、品名和纸品资料</span>
              </div>
              <label class="space-y-1.5"><span class="text-[11px] font-bold text-slate-600">产品名称 *</span><input v-model="orderForm.productName" aria-label="产品名称" :disabled="editingOrderStructureLocked" placeholder="例如 仿真消防车" class="h-10 w-full rounded-lg border border-slate-200 px-3 outline-none focus:border-teal-500 disabled:bg-slate-50 disabled:text-slate-500"></label>
              <label class="space-y-1.5"><span class="text-[11px] font-bold text-slate-600">产品订单数量 *</span><input v-model.number="orderForm.orderQuantity" aria-label="订单数量" type="number" min="1" placeholder="请填写实际数量" :disabled="editingOrderStructureLocked" class="h-10 w-full rounded-lg border border-slate-200 px-3 outline-none focus:border-teal-500 disabled:bg-slate-50 disabled:text-slate-500"></label>
              <div class="grid gap-4 sm:col-span-2 sm:grid-cols-3">
                <label class="space-y-1.5"><span class="text-[11px] font-bold text-slate-600">下单日期</span><input v-model="orderForm.orderDate" aria-label="下单日期" type="date" :disabled="editingOrderStructureLocked" class="h-10 w-full rounded-lg border border-slate-200 px-3 outline-none focus:border-teal-500 disabled:bg-slate-50 disabled:text-slate-500"></label>
                <label class="space-y-1.5"><span class="text-[11px] font-bold text-slate-600">客户交期 *</span><input v-model="orderForm.customerDueDate" aria-label="客户交期" type="date" :min="orderForm.orderDate || undefined" class="h-10 w-full rounded-lg border border-blue-200 px-3 outline-none focus:border-blue-500"><span v-if="editingOrderRecord && !editingOrderRecord.customer_due_date && !orderForm.customerDueDate" class="block text-[9px] text-slate-400">历史订单未记录，可在本次修改时补充</span></label>
                <label class="space-y-1.5"><span class="text-[11px] font-bold text-slate-600">计划交期（自动）</span><input :value="calculatedOrderDueDate" aria-label="计划交期" type="date" readonly class="h-10 w-full cursor-not-allowed rounded-lg border border-teal-200 bg-teal-50 px-3 font-semibold text-teal-800 outline-none"><span class="block text-[9px] text-slate-500">客户交期减 {{ DEFAULT_CARTON_SAFETY_LEAD_DAYS }} 个自然日</span></label>
                <p v-if="orderSafetyLeadWarning" role="alert" class="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[10px] font-semibold text-red-700 sm:col-span-3">{{ orderSafetyLeadWarning }}</p>
              </div>
            </div>
          </section>

          <section class="rounded-xl border border-slate-200">
            <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-slate-50 px-4 py-3">
              <div><div class="font-bold text-slate-950">合同内纸品明细</div><p class="mt-0.5 text-[10px] text-slate-500">每行填写每箱个数，纸箱数量自动按“产品订单数量 ÷ 每箱个数”计算，不足一箱向上取整。</p></div>
              <button type="button" :disabled="editingOrderStructureLocked" class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-teal-200 bg-white px-3 text-[11px] font-bold text-teal-700 disabled:cursor-not-allowed disabled:border-slate-200 disabled:text-slate-400" @click="addOrderMaterialLine"><Plus class="size-3.5" />新增纸品明细</button>
            </div>
            <div class="space-y-3 p-4">
              <div v-for="(material, index) in orderForm.materials" :key="material.id" class="grid gap-3 rounded-lg border border-slate-200 bg-slate-50/60 p-3 lg:grid-cols-[1fr_1fr_1.7fr_0.8fr_0.9fr_0.65fr_auto] lg:items-end">
                <label class="space-y-1.5"><span class="text-[10px] font-bold text-slate-500">纸品类型 *</span><select v-model="material.packagingType" :aria-label="`纸品类型 ${index + 1}`" :disabled="editingOrderStructureLocked" class="h-9 w-full rounded-lg border border-slate-200 bg-white px-2 outline-none focus:border-teal-500 disabled:bg-slate-100"><option>外箱</option><option>内箱</option><option>滑板纸</option><option>卡纸</option><option>展示盒</option><option>其他</option></select></label>
                <label class="space-y-1.5"><span class="text-[10px] font-bold text-slate-500">纸质 *</span><input v-model="material.paperQuality" list="carton-paper-quality-history" :aria-label="`纸质 ${index + 1}`" :disabled="editingOrderStructureLocked" placeholder="如 A33+B" class="h-9 w-full rounded-lg border border-slate-200 bg-white px-2 outline-none focus:border-teal-500 disabled:bg-slate-100"></label>
                <label class="space-y-1.5"><span class="text-[10px] font-bold text-slate-500">规格 *</span><input v-model="material.specification" list="carton-specification-history" :aria-label="`规格 ${index + 1}`" :disabled="editingOrderStructureLocked" placeholder="长 × 宽 × 高；保留单位" class="h-9 w-full rounded-lg border border-slate-200 bg-white px-2 outline-none focus:border-teal-500 disabled:bg-slate-100"></label>
                <label class="space-y-1.5"><span class="text-[10px] font-bold text-slate-500">每箱个数 *</span><input v-model.number="material.unitsPerCarton" :aria-label="`每箱个数 ${index + 1}`" type="number" min="0.00000001" step="any" :disabled="editingOrderStructureLocked" class="h-9 w-full rounded-lg border border-slate-200 bg-white px-2 text-right outline-none focus:border-teal-500 disabled:bg-slate-100"></label>
                <div class="space-y-1.5"><span class="text-[10px] font-bold text-slate-500">纸箱数量（自动）</span><output :aria-label="`纸箱数量 ${index + 1}`" class="flex h-9 w-full items-center justify-end rounded-lg border border-teal-200 bg-teal-50 px-2 font-bold text-teal-700 tabular-nums">{{ formatRequiredQuantity(material.unitsPerCarton, orderForm.orderQuantity) }}</output></div>
                <label class="space-y-1.5"><span class="text-[10px] font-bold text-slate-500">单位</span><select v-model="material.unit" :aria-label="`纸品单位 ${index + 1}`" :disabled="editingOrderStructureLocked" class="h-9 w-full rounded-lg border border-slate-200 bg-white px-2 outline-none focus:border-teal-500 disabled:bg-slate-100"><option>个</option><option>张</option><option>套</option></select></label>
                <button type="button" :disabled="editingOrderStructureLocked" :aria-label="`删除纸品明细 ${index + 1}`" class="flex size-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-400 transition hover:border-red-200 hover:text-red-600 disabled:cursor-not-allowed disabled:bg-slate-100" @click="removeOrderMaterialLine(index)"><X class="size-4" /></button>
              </div>
            </div>
          </section>
          <datalist id="carton-paper-quality-history"><option v-for="value in paperQualitySuggestions" :key="value" :value="value" /></datalist>
          <datalist id="carton-specification-history"><option v-for="value in specificationSuggestions" :key="value" :value="value" /></datalist>

          <label class="block space-y-1.5"><span class="text-[11px] font-bold text-slate-600">合同备注</span><textarea v-model="orderForm.note" aria-label="订单备注" rows="3" placeholder="历史规格来源、刀模版本或特殊交付要求" class="w-full rounded-lg border border-slate-200 px-3 py-2 outline-none focus:border-teal-500"></textarea></label>
          <label v-if="editingOrderNo" class="block space-y-1.5"><span class="text-[11px] font-bold text-slate-600">修改原因 *</span><textarea v-model="orderChangeReason" aria-label="订单修改原因" rows="2" minlength="4" maxlength="500" placeholder="说明客户通知、数量修正或交期变化原因" class="w-full rounded-lg border border-amber-200 bg-amber-50/60 px-3 py-2 outline-none focus:border-amber-500"></textarea></label>
        </div>
        <div class="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 bg-slate-50 px-5 py-4"><p class="text-[10px] text-slate-500">{{ editingOrderNo ? '保存后版本号递增并写入修改原因。' : '创建后仍可修改、追加或取消；必须另行“确认订单并锁定”后才允许入库。' }}</p><div class="flex gap-2"><button type="button" class="h-9 rounded-lg border border-slate-200 bg-white px-4 text-[12px] font-bold text-slate-600" @click="showOrderModal = false">返回</button><button type="submit" :disabled="savingOrder" class="h-9 rounded-lg bg-teal-700 px-4 text-[12px] font-bold text-white disabled:opacity-60">{{ savingOrder ? '正在保存…' : editingOrderNo ? '保存订单修订' : '创建待下单订单' }}</button></div></div>
      </form>
    </div>

    <div v-if="submitSupplierOrderNo || bulkSubmitSupplierOrderNos.length" class="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/45 p-4" @click.self="closeSubmitSupplierDialog">
      <div class="w-full max-w-lg overflow-hidden rounded-2xl bg-white shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="submit-supplier-title">
        <div class="flex items-start justify-between border-b border-slate-200 px-5 py-4">
          <div><h2 id="submit-supplier-title" class="text-[16px] font-bold text-slate-950">{{ bulkSubmitSupplierOrderNos.length ? `批量确认并锁定 ${selectedSubmittableOrderCount} 张待下单订单` : `确认订单 ${submitSupplierOrderNo} 并锁定` }}</h2><p class="mt-1 text-[11px] text-slate-500">确认后订单进入“已确认锁定”状态并开放收料；这一步不会发送文件，之后需要另行发行供应商采购单。</p></div>
          <button type="button" aria-label="关闭确认订单并锁定" class="rounded-lg p-2 text-slate-400 hover:bg-slate-100" @click="closeSubmitSupplierDialog"><X class="size-4" /></button>
        </div>
        <div class="p-5"><div class="rounded-xl border border-amber-200 bg-amber-50 p-4 text-[12px] font-semibold leading-6 text-amber-900">此操作会锁定普通编辑：确认锁定后客户、合同、货号和纸品资料不可直接修改；主管可继续追加，也可减少尚未入库且未进入待确认收料单的数量。</div></div>
        <div class="flex justify-end gap-2 border-t border-slate-200 bg-slate-50 px-5 py-4"><button type="button" class="h-9 rounded-lg border border-slate-200 bg-white px-4 text-[12px] font-bold text-slate-600" @click="closeSubmitSupplierDialog">返回检查</button><button type="button" aria-label="执行确认订单并锁定" :disabled="submittingSupplierOrder" class="h-9 rounded-lg bg-teal-700 px-4 text-[12px] font-bold text-white disabled:opacity-60" @click="confirmSubmitSupplierOrder">{{ submittingSupplierOrder ? '正在确认…' : '确认订单并锁定' }}</button></div>
      </div>
    </div>

    <div v-if="cancelOrderNo" class="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/45 p-4" @click.self="cancelOrderNo = ''">
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
          <div v-if="purchaseOrderContextRecord.historical_baseline" class="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-[11px] leading-5 text-blue-800">系统升级前的当前累计数量已登记为历史基线；后续追加或减单只导出相对该基线的净变化，避免重复下单。</div>
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
                <div><div class="flex items-center gap-2"><b class="font-mono text-[12px] text-slate-900">{{ issue.document_no }}</b><span class="rounded-full bg-teal-50 px-2 py-0.5 text-[9px] font-bold text-teal-700">{{ purchaseOrderTypeLabel(issue.document_type) }}</span></div><p class="mt-1 text-[10px] text-slate-500">产品变化 {{ signedQuantity(issue.product_quantity_delta) }} · {{ issue.generated_by_name || '—' }} · {{ issue.generated_at.slice(0, 16).replace('T', ' ') }}</p></div>
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

    <div v-if="appendOrderNo" class="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/45 p-4" @click.self="appendOrderNo = ''">
      <form data-testid="append-order-form" class="w-full max-w-2xl overflow-hidden rounded-2xl bg-white shadow-2xl" @submit.prevent="confirmAppendOrder">
        <div class="flex items-start justify-between border-b border-slate-200 px-5 py-4"><div><h2 class="text-[16px] font-bold text-slate-950">追加订单 {{ appendOrderNo }}</h2><p class="mt-1 text-[11px] text-slate-500">{{ appendOrderGuidance }}</p></div><button type="button" aria-label="关闭追加订单" class="rounded-lg p-2 text-slate-400 hover:bg-slate-100" @click="appendOrderNo = ''"><X class="size-4" /></button></div>
        <div class="grid gap-4 p-5 sm:grid-cols-3"><label class="space-y-1.5"><span class="text-[11px] font-bold text-slate-600">追加产品数量 *</span><input v-model.number="appendOrderQuantity" aria-label="追加订单数量" type="number" min="1" class="h-10 w-full rounded-lg border border-amber-200 px-3 text-right font-semibold outline-none focus:border-amber-500"></label><label class="space-y-1.5"><span class="text-[11px] font-bold text-slate-600">新客户交期</span><input v-model="appendOrderCustomerDueDate" aria-label="追加订单客户交期" type="date" :min="appendingOrderRecord?.order_date" class="h-10 w-full rounded-lg border border-blue-200 px-3 outline-none focus:border-blue-500"><span v-if="!appendingOrderRecord?.customer_due_date" class="block text-[9px] text-slate-400">历史订单可留空并沿用原计划交期</span></label><label class="space-y-1.5"><span class="text-[11px] font-bold text-slate-600">新计划交期（自动）</span><input :value="calculatedAppendOrderDueDate" aria-label="追加订单计划交期" type="date" readonly class="h-10 w-full cursor-not-allowed rounded-lg border border-teal-200 bg-teal-50 px-3 font-semibold text-teal-800 outline-none"><span class="block text-[9px] text-slate-500">客户交期减 {{ DEFAULT_CARTON_SAFETY_LEAD_DAYS }} 个自然日</span></label><p v-if="appendSafetyLeadWarning" role="alert" class="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[10px] font-semibold text-red-700 sm:col-span-3">{{ appendSafetyLeadWarning }}</p><label class="space-y-1.5 sm:col-span-3"><span class="text-[11px] font-bold text-slate-600">追加原因（默认已填写，可修改）</span><textarea v-model="appendOrderReason" aria-label="追加订单原因" rows="3" maxlength="500" placeholder="如有其他原因，可在这里修改" class="w-full rounded-lg border border-amber-200 bg-amber-50/40 px-3 py-2 outline-none focus:border-amber-500"></textarea></label></div>
        <div class="flex justify-end gap-2 border-t border-slate-200 bg-slate-50 px-5 py-4"><button type="button" class="h-9 rounded-lg border border-slate-200 bg-white px-4 text-[12px] font-bold text-slate-600" @click="appendOrderNo = ''">返回</button><button type="submit" :disabled="appendingOrder" class="h-9 rounded-lg bg-amber-600 px-4 text-[12px] font-bold text-white disabled:opacity-60">{{ appendingOrder ? '正在追加…' : '确认追加并留痕' }}</button></div>
      </form>
    </div>

    <div v-if="reduceOrderNo" class="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/45 p-4" @click.self="reduceOrderNo = ''">
      <form data-testid="reduce-order-form" class="w-full max-w-lg overflow-hidden rounded-2xl bg-white shadow-2xl" @submit.prevent="confirmReduceOrder">
        <div class="flex items-start justify-between border-b border-slate-200 px-5 py-4">
          <div><h2 class="text-[16px] font-bold text-slate-950">{{ reducingOrderRecord?.status === 'PARTIALLY_RECEIVED' ? '减少未入库量' : '减单 / 退单' }} {{ reduceOrderNo }}</h2><p class="mt-1 text-[11px] text-slate-500">{{ reducingOrderRecord?.status === 'PARTIALLY_RECEIVED' ? '仅可减少尚未入库且未进入待确认收料单的数量；减完全部余量后订单自动转为“全部到货”。' : '尚无入库时可部分减单或整单退单；待确认收料数量会预留保护。' }}</p></div>
          <button type="button" aria-label="关闭减单" class="rounded-lg p-2 text-slate-400 hover:bg-slate-100" @click="reduceOrderNo = ''"><X class="size-4" /></button>
        </div>
        <div class="space-y-4 p-5">
          <div class="grid grid-cols-3 gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3 text-[12px]"><div><span class="block text-slate-500">当前产品数量</span><b class="mt-1 block text-slate-900">{{ formatNumber(Number(reducingOrderRecord?.product_order_quantity ?? 0)) }}</b></div><div><span class="block text-slate-500">最大可减</span><b class="mt-1 block text-amber-700">{{ formatNumber(reduceOrderMaximumQuantity) }}</b></div><div><span class="block text-slate-500">调整后数量</span><b class="mt-1 block" :class="reduceOrderRemainingQuantity === 0 ? 'text-red-700' : 'text-teal-700'">{{ formatNumber(reduceOrderRemainingQuantity) }}</b></div></div>
          <label class="block space-y-1.5"><span class="text-[11px] font-bold text-slate-600">{{ reducingOrderRecord?.status === 'PARTIALLY_RECEIVED' ? '减少未入库产品数量' : '减少产品数量' }} *</span><input v-model.number="reduceOrderQuantity" aria-label="减单数量" type="number" min="1" :max="reduceOrderMaximumQuantity" class="h-10 w-full rounded-lg border border-red-200 px-3 text-right font-semibold outline-none focus:border-red-500"></label>
          <label class="block space-y-1.5"><span class="text-[11px] font-bold text-slate-600">减单 / 退单原因（默认已填写，可修改）</span><textarea v-model="reduceOrderReason" aria-label="减单原因" rows="3" maxlength="500" placeholder="如有其他原因，可在这里修改" class="w-full rounded-lg border border-red-200 bg-red-50/40 px-3 py-2 outline-none focus:border-red-500"></textarea></label>
          <div class="rounded-xl border border-amber-200 bg-amber-50 p-3 text-[11px] font-semibold leading-5 text-amber-900">最大可减数量已经按每条纸品的已入库量与待确认收料量计算；确认后只降低未入库需求，不修改任何既有收料单或库存流水。</div>
        </div>
        <div class="flex justify-end gap-2 border-t border-slate-200 bg-slate-50 px-5 py-4"><button type="button" class="h-9 rounded-lg border border-slate-200 bg-white px-4 text-[12px] font-bold text-slate-600" @click="reduceOrderNo = ''">返回</button><button type="submit" :disabled="reducingOrder" class="h-9 rounded-lg bg-red-600 px-4 text-[12px] font-bold text-white disabled:opacity-60">{{ reducingOrder ? '正在处理…' : reduceOrderRemainingQuantity === 0 ? '确认整单退单' : reducingOrderRecord?.status === 'PARTIALLY_RECEIVED' ? '确认减少未入库量' : '确认减单并留痕' }}</button></div>
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
        <label class="block text-sm font-semibold">原因 *<textarea v-model="receiptCorrectionReason" :disabled="receiptCorrectionBusy" aria-label="收料纠错原因" rows="3" maxlength="2000" class="mt-2 w-full rounded-lg border border-slate-200 p-3" placeholder="说明录错的信息及更正原因"></textarea></label>
        <p v-if="receiptCorrectionError" role="alert" class="my-3 text-sm text-red-600">{{ receiptCorrectionError }}</p>
        <div class="mt-4 flex justify-end gap-3"><button type="button" :disabled="receiptCorrectionBusy" class="h-9 rounded-lg border px-4" @click="receiptCorrectionTarget = null">取消</button><button type="submit" :disabled="receiptCorrectionBusy" class="h-9 rounded-lg bg-red-600 px-4 font-bold text-white disabled:opacity-50">{{ receiptCorrectionBusy ? '正在处理…' : receiptCorrectionTarget.status === 'POSTED' ? '确认整单冲销' : '确认作废' }}</button></div>
      </form>
    </div>
    <div v-if="reversingMovementId" class="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/45 p-4" @click.self="reversingMovementId = ''">
      <form class="w-full max-w-lg overflow-hidden rounded-2xl bg-white shadow-2xl" @submit.prevent="confirmInventoryReversal">
        <div class="flex items-start justify-between border-b border-slate-200 px-5 py-4">
          <div><h2 class="text-[16px] font-bold text-slate-950">冲销库存流水</h2><p class="mt-1 text-[11px] text-slate-500">系统将新增一笔方向相反的冲销流水，原流水不会被修改或删除。</p></div>
          <button type="button" aria-label="关闭库存冲销" class="rounded-lg p-2 text-slate-400 hover:bg-slate-100" @click="reversingMovementId = ''"><X class="size-4" /></button>
        </div>
        <div class="space-y-3 p-5">
          <div class="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 font-mono text-[11px] text-slate-700">原流水：{{ reversingMovementId }}</div>
          <label class="block space-y-1.5"><span class="text-[11px] font-bold text-slate-600">冲销原因 *</span><textarea v-model="reversalReason" aria-label="库存冲销原因" rows="4" maxlength="2000" placeholder="说明原单据错误或作废原因" class="w-full rounded-lg border border-red-200 bg-red-50/40 px-3 py-2 outline-none focus:border-red-500"></textarea></label>
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
</style>
