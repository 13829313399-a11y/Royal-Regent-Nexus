<script setup lang="ts">
import { computed, reactive, ref, watch, type Component } from 'vue'
import {
  AlertTriangle,
  ArrowLeft,
  Boxes,
  Building2,
  CalendarClock,
  CheckCircle2,
  ClipboardCheck,
  FileSpreadsheet,
  GitBranch,
  LayoutDashboard,
  PackageCheck,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Truck,
  Upload,
  X,
} from '@lucide/vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import {
  cartonProcurementApi,
  type CartonClosingResponse,
  type CartonExceptionResponse,
  type CartonImportBatchResponse,
  type CartonImportPreviewRow,
  type CartonInventoryMovementResponse,
  type CartonOrderResponse,
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
  type CartonOrderRow,
  type CartonTone,
  type ReceiptLineSeed,
  type WeeklyCheckRow,
} from '@/features/carton-procurement/demoData'
import { useAppStore } from '@/stores/app'
import { getApiErrorMessage } from '@/lib/http'

type CartonTab = 'dashboard' | 'orders' | 'weekly-check' | 'receipts' | 'inventory' | 'closing' | 'exceptions'

interface CartonTabItem {
  id: CartonTab
  label: string
  shortLabel: string
  icon: Component
}

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()

const tabs: CartonTabItem[] = [
  { id: 'dashboard', label: '纸箱采购协同看板', shortLabel: '协同看板', icon: LayoutDashboard },
  { id: 'orders', label: '纸箱订单管理', shortLabel: '订单管理', icon: ClipboardCheck },
  { id: 'weekly-check', label: '每周防漏核对', shortLabel: '防漏核对', icon: CalendarClock },
  { id: 'receipts', label: '收料反馈平台', shortLabel: '收料反馈', icon: PackageCheck },
  { id: 'inventory', label: '库存台账与交易流水', shortLabel: '库存流水', icon: Boxes },
  { id: 'closing', label: '库存月结与对账报表', shortLabel: '月结对账', icon: FileSpreadsheet },
  { id: 'exceptions', label: '异常中心', shortLabel: '异常中心', icon: AlertTriangle },
]

const validTabs = new Set<CartonTab>(tabs.map((tab) => tab.id))
const selectedCustomer = ref<(typeof cartonCustomers)[number]>('全部客户')
const globalSearch = ref('')
const actionMessage = ref('正在读取纸箱采购台账…')
const apiConnected = ref(false)
const backendLoading = ref(false)
const savingOrder = ref(false)
const showOrderModal = ref(false)
const receiptSaved = ref(false)
const receiptSearchInput = ref('')
const receiptSearchTerm = ref('')
const receiptFileInput = ref<HTMLInputElement | null>(null)
const selectedReceiptFileName = ref('')
const weeklyFileInput = ref<HTMLInputElement | null>(null)
const selectedWeeklyFileName = ref('')
const importingWeekly = ref(false)
const importingReceipt = ref(false)
const savingReceipt = ref(false)
const confirmingReceipt = ref(false)
const receiptBatchId = ref('')
const receiptDeliveryNoteNo = ref('DN26061301')
const receiptDeliveryDate = ref('2026-06-13')
const currentReceipt = ref<CartonReceiptResponse | null>(null)
const closingPeriod = ref(new Date(new Date().getFullYear(), new Date().getMonth() - 1, 1).toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' }).slice(0, 7))
const closingBusyId = ref('')
const exceptionBusyId = ref('')
const resolutionNotes = reactive<Record<string, string>>({})
const localOrders = reactive<CartonOrderRow[]>(cartonOrders.map((row) => ({
  ...row,
  materials: row.materials.map((material) => ({ ...material })),
})))
const localMovements = reactive(inventoryMovementDemo.map((row) => ({ ...row })))
const localClosings = reactive(cartonClosingDemo.map((row) => ({ ...row })))
const localWeeklyChecks = reactive<WeeklyCheckRow[]>(weeklyChecks.map((row) => ({ ...row })))
const localExceptions = reactive<CartonExceptionRow[]>(cartonExceptions.map((row) => ({ ...row })))
const closingRecords = ref<CartonClosingResponse[]>([])
const exceptionRecords = ref<CartonExceptionResponse[]>([])

interface ReceiptReviewLine extends ReceiptLineSeed {
  orderLineId: string
  location: string
  sourceLabel: string
}

const receiptLines = reactive<ReceiptReviewLine[]>(receiptSeed.map((line) => ({
  ...line,
  orderLineId: '',
  location: '',
  sourceLabel: '只读演示',
})))

type OrderFormMaterialLine = Omit<CartonMaterialLine, 'id'> & { id: string }

const orderForm = reactive({
  customer: 'Dickie',
  contractNo: '',
  itemNo: '',
  orderQuantity: 3600,
  dueDate: '2026-08-12',
  note: '',
  materials: [
    {
      id: 'FORM-MAT-1',
      packagingType: '外箱',
      paperQuality: 'A33+B',
      specification: '',
      usage: 1 / 120,
      unit: '个',
    },
  ] as OrderFormMaterialLine[],
})

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

const visibleOrders = computed(() => localOrders.filter((row) =>
  matchesCustomer(row.customer)
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
  ]),
))

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

const visibleMovements = computed(() => localMovements.filter((row) =>
  matchesCustomer(row.customer)
  && includesSearch([
    row.date,
    row.documentNo,
    row.customer,
    row.poNumber,
    row.itemNo,
    row.movementType,
    row.location,
  ]),
))

const visibleClosings = computed(() => localClosings.filter((row) =>
  matchesCustomer(row.customer)
  && includesSearch([row.customer, row.period, row.status]),
))

const visibleExceptions = computed(() => localExceptions.filter((row) =>
  matchesCustomer(row.customer)
  && includesSearch([row.id, row.customer, row.type, row.title, row.detail, row.status]),
))

const visibleReceiptLines = computed(() => {
  const term = receiptSearchTerm.value.trim().toLowerCase()
  if (!term) return receiptLines
  return receiptLines.filter((row) => [
    receiptDeliveryNoteNo.value,
    row.orderNo,
    row.description,
    row.specification,
  ].join(' ').toLowerCase().includes(term))
})

const pendingOrderCount = computed(() => visibleOrders.value.filter((row) => row.status !== '已完成').length)
const weeklyRiskCount = computed(() => visibleWeeklyChecks.value.filter((row) => row.result !== '已匹配').length)
const openExceptionCount = computed(() => visibleExceptions.value.filter((row) => row.status !== '已关闭').length)
const inventoryBalance = computed(() => {
  const latestByItem = new Map<string, number>()
  for (const row of visibleMovements.value) {
    const key = `${row.customer}|${row.itemNo}|${row.packagingType}`
    if (!latestByItem.has(key)) latestByItem.set(key, row.balance)
  }
  return Array.from(latestByItem.values()).reduce((sum, value) => sum + value, 0)
})

const inventoryBalances = computed(() => {
  const latestByItem = new Map<string, (typeof localMovements)[number]>()
  for (const row of visibleMovements.value) {
    const key = `${row.customer}|${row.itemNo}|${row.packagingType}`
    if (!latestByItem.has(key)) latestByItem.set(key, row)
  }
  return Array.from(latestByItem.values())
})

const receiptTotals = computed(() => visibleReceiptLines.value.reduce((totals, row) => {
  const unusable = Number(row.damagedQuantity || 0) + Number(row.rejectedQuantity || 0) + Number(row.unusableQuantity || 0)
  const effective = Math.max(0, Number(row.receivedQuantity || 0) - unusable)
  totals.delivered += Number(row.deliveryQuantity || 0)
  totals.received += Number(row.receivedQuantity || 0)
  totals.unusable += unusable
  totals.effective += effective
  return totals
}, { delivered: 0, received: 0, unusable: 0, effective: 0 }))

const receiptAmount = computed(() => visibleReceiptLines.value.reduce(
  (total, row) => total + Number(row.deliveryQuantity || 0) * Number(row.unitPrice || 0),
  0,
))

watch(selectedFactoryId, (factoryId) => {
  appStore.setActiveFactory(factoryId)
  void loadBackendData(factoryId)
}, { immediate: true })

watch([selectedCustomer, globalSearch], () => {
  actionMessage.value = selectedCustomer.value === '全部客户'
    ? `当前显示全部客户的${apiConnected.value ? '正式台账' : '只读演示记录'}。`
    : `当前已筛选客户：${selectedCustomer.value}。`
})

function setActiveTab(tab: CartonTab) {
  receiptSaved.value = false
  void router.replace({
    query: {
      ...route.query,
      factory: selectedFactoryId.value,
      tab: tab === 'dashboard' ? undefined : tab,
    },
  })
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

function formatUsage(value: number) {
  const normalized = Number(value || 0)
  if (normalized > 0 && normalized < 1) {
    const reciprocal = 1 / normalized
    if (Math.abs(reciprocal - Math.round(reciprocal)) < 1e-8) {
      return `1/${Math.round(reciprocal)}`
    }
  }
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 6 }).format(normalized)
}

function calculateRequiredQuantity(usage: number, orderQuantity: number) {
  const result = Number(usage || 0) * Number(orderQuantity || 0)
  return Math.abs(result - Math.round(result)) < 1e-8
    ? Math.round(result)
    : Number(result.toFixed(4))
}

function formatRequiredQuantity(usage: number, orderQuantity: number) {
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 4 }).format(
    calculateRequiredQuantity(usage, orderQuantity),
  )
}

function formatMoney(value: number) {
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    minimumFractionDigits: 2,
  }).format(value)
}

function customerCode(customer: string) {
  return ({ Dickie: 'DICKIE', '360': '360', 施信: 'SHIXIN', BuzzBee: 'BUZZBEE' } as Record<string, string>)[customer]
    ?? customer.trim().toUpperCase()
}

function orderTone(status: string): CartonTone {
  if (status === 'COMPLETED' || status === 'CONFIRMED') return 'green'
  if (status === 'PARTIALLY_RECEIVED') return 'blue'
  if (status === 'CANCELLED') return 'red'
  if (status === 'DRAFT') return 'slate'
  return 'amber'
}

function orderStatusLabel(status: string) {
  return ({
    DRAFT: '草稿',
    PENDING_SUPPLIER: '待供应商确认',
    CONFIRMED: '已确认交期',
    PARTIALLY_RECEIVED: '部分收料',
    COMPLETED: '已完成',
    CANCELLED: '已取消',
  } as Record<string, string>)[status] ?? status
}

function mapOrder(row: CartonOrderResponse): CartonOrderRow {
  return {
    id: row.order_no,
    orderDate: row.order_date,
    customer: row.customer_name,
    contractNo: row.contract_no,
    itemNo: row.item_no,
    orderQuantity: Number(row.product_order_quantity),
    materials: row.lines.map((line) => ({
      id: line.id,
      packagingType: line.packaging_type,
      paperQuality: line.paper_quality,
      specification: `${line.specification}${line.dimension_unit ? ` ${line.dimension_unit}` : ''}`,
      usage: Number(line.usage_quantity),
      unit: line.unit,
    })),
    dueDate: row.due_date,
    status: orderStatusLabel(row.status),
    tone: orderTone(row.status),
    note: row.note,
  }
}

function mapMovement(row: CartonInventoryMovementResponse) {
  const movementType = row.movement_type === 'INBOUND'
    ? '入库' as const
    : row.movement_type === 'OUTBOUND'
      ? '出库' as const
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
    source: row.source_type === 'RECEIPT' ? '收料反馈' : row.reason,
  }
}

function mapClosing(row: CartonClosingResponse) {
  const status = ({ DRAFT: '草稿', PENDING: '待核对', CONFIRMED: '已确认', LOCKED: '已锁账' } as Record<string, string>)[row.status] ?? row.status
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
    type: ({ MISSING_ORDER: '疑似漏单', RECEIPT_UNMATCHED: '收料未匹配', QUANTITY_MISMATCH: '数量差异', AMBIGUOUS_MATCH: '匹配不唯一' } as Record<string, string>)[row.category] ?? row.category,
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
  const matched = rows.filter((row) => row.match_status === 'MATCHED' && row.order_line_id)
  const deliveryNumbers = [...new Set(matched.map((row) => row.delivery_note_no).filter(Boolean))] as string[]
  const selectedDeliveryNo = deliveryNumbers[0]
    ?? batch.parse_summary.document?.delivery_note_no
    ?? `IMPORT-${batch.id.slice(-8).toUpperCase()}`
  const selectedRows = matched.filter((row) => !row.delivery_note_no || row.delivery_note_no === selectedDeliveryNo)
  receiptLines.splice(0, receiptLines.length, ...selectedRows.map((row, index) => ({
    id: `${batch.id}-${row.source_row ?? index + 1}`,
    orderNo: `${row.order_no ?? ''} · ${row.contract_no ?? ''}-${row.item_no ?? ''}`,
    description: `${row.packaging_type ?? '待复核'} ${row.paper_quality ?? ''}`.trim(),
    specification: row.specification ?? '',
    deliveryQuantity: Number(row.delivered_quantity ?? 0),
    unitPrice: Number(row.unit_price ?? 0),
    receivedQuantity: Number(row.delivered_quantity ?? 0),
    damagedQuantity: 0,
    rejectedQuantity: 0,
    unusableQuantity: 0,
    orderLineId: row.order_line_id ?? '',
    location: row.location ?? '',
    sourceLabel: `${row.source_sheet ?? 'OCR'} 第 ${row.source_row ?? index + 1} 行`,
  })))
  receiptBatchId.value = batch.id
  receiptDeliveryNoteNo.value = selectedDeliveryNo
  receiptDeliveryDate.value = selectedRows.find((row) => row.delivery_date)?.delivery_date
    ?? batch.parse_summary.document?.delivery_date
    ?? new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
  currentReceipt.value = null
  receiptSaved.value = false
  const extraDocuments = Math.max(0, deliveryNumbers.length - 1)
  actionMessage.value = `已解析 ${batch.parse_summary.row_count ?? rows.length} 行，自动匹配 ${batch.parse_summary.matched_count ?? matched.length} 行，${batch.parse_summary.issue_count ?? 0} 行已进入异常中心。${extraDocuments ? `本次还包含 ${extraDocuments} 张其他送货单，请分批复核。` : ''}`
}

async function loadBackendData(factoryId = selectedFactoryId.value) {
  if (backendLoading.value) return
  backendLoading.value = true
  try {
    const [orders, movements, closings, exceptions] = await Promise.all([
      cartonProcurementApi.listOrders(factoryId),
      cartonProcurementApi.listMovements(factoryId),
      cartonProcurementApi.listClosings(factoryId),
      cartonProcurementApi.listExceptions(factoryId),
    ])
    localOrders.splice(0, localOrders.length, ...orders.map(mapOrder))
    localMovements.splice(0, localMovements.length, ...movements.map(mapMovement))
    localClosings.splice(0, localClosings.length, ...closings.map(mapClosing))
    closingRecords.value = closings
    exceptionRecords.value = exceptions
    localExceptions.splice(0, localExceptions.length, ...exceptions.map(mapException))
    if (!selectedWeeklyFileName.value) localWeeklyChecks.splice(0)
    if (!receiptBatchId.value) {
      receiptLines.splice(0)
      receiptDeliveryNoteNo.value = ''
      receiptDeliveryDate.value = ''
    }
    apiConnected.value = true
    actionMessage.value = `已连接 ${activeFactory.value.shortName} 正式台账；订单、收料导入、库存流水和月结均由后端保存。`
  } catch (error) {
    apiConnected.value = false
    actionMessage.value = `后端暂不可用，当前显示只读演示数据：${getApiErrorMessage(error)}`
  } finally {
    backendLoading.value = false
  }
}

async function createLocalOrder() {
  const validMaterials = orderForm.materials.filter((material) =>
    material.packagingType.trim()
    && material.paperQuality.trim()
    && material.specification.trim()
    && Number(material.usage) > 0,
  )
  if (!orderForm.contractNo.trim() || !orderForm.itemNo.trim() || validMaterials.length !== orderForm.materials.length) {
    actionMessage.value = '请填写合同号、货号，并补齐每条纸品明细的类型、纸质、规格和单件用量。'
    return
  }

  savingOrder.value = true
  try {
    const created = await cartonProcurementApi.createOrder({
      factory_id: selectedFactoryId.value,
      customer_code: customerCode(orderForm.customer),
      customer_name: orderForm.customer,
      contract_no: orderForm.contractNo.trim(),
      item_no: orderForm.itemNo.trim(),
      product_order_quantity: Number(orderForm.orderQuantity),
      order_date: new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' }),
      due_date: orderForm.dueDate,
      status: 'PENDING_SUPPLIER',
      note: orderForm.note.trim(),
      lines: validMaterials.map((material) => ({
        packaging_type: material.packagingType.trim(),
        paper_quality: material.paperQuality.trim(),
        specification: material.specification.trim(),
        dimension_unit: '',
        usage_quantity: Number(material.usage),
        unit: material.unit,
      })),
    })
    localOrders.unshift(mapOrder(created))
    apiConnected.value = true
    showOrderModal.value = false
    actionMessage.value = `正式纸箱订单 ${created.order_no} 已保存，含 ${created.lines.length} 条纸品明细；需求数量由后端重新计算。`
  } catch (error) {
    actionMessage.value = `订单未保存：${getApiErrorMessage(error)}`
  } finally {
    savingOrder.value = false
  }
}

function addOrderMaterialLine() {
  orderForm.materials.push({
    id: `FORM-MAT-${orderForm.materials.length + 1}`,
    packagingType: '滑板纸',
    paperQuality: '',
    specification: '',
    usage: 1,
    unit: '张',
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
    if (batch.duplicate) {
      actionMessage.value = `送货单“${file.name}”已导入过，已恢复原复核批次 ${batch.id}；没有重复创建收料或库存。`
    }
  } catch (error) {
    actionMessage.value = `送货单导入失败：${getApiErrorMessage(error)}`
  } finally {
    importingReceipt.value = false
  }
}

function triggerWeeklyImport() {
  weeklyFileInput.value?.click()
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
    localWeeklyChecks.splice(0, localWeeklyChecks.length, ...rows.map(mapWeeklyPreview))
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

function searchReceipts() {
  receiptSearchTerm.value = receiptSearchInput.value.trim()
  actionMessage.value = receiptSearchTerm.value
    ? `已查找“${receiptSearchTerm.value}”，找到 ${visibleReceiptLines.value.length} 条送货明细。`
    : '已清除送货单查找条件，显示当前送货单全部明细。'
}

async function saveReceiptFeedback() {
  if (!receiptLines.length) {
    actionMessage.value = '当前没有已复核的送货明细；导入文件后须先完成字段匹配，才能提交正式收料反馈。'
    return
  }
  if (!receiptBatchId.value || receiptLines.some((row) => !row.orderLineId)) {
    actionMessage.value = '请先导入送货单并完成订单纸品匹配。'
    return
  }
  if (receiptLines.some((row) => Number(row.damagedQuantity) + Number(row.rejectedQuantity) + Number(row.unusableQuantity) > Number(row.receivedQuantity))) {
    actionMessage.value = '破损、拒收和其他不可用数量之和不能大于实收数量。'
    return
  }
  savingReceipt.value = true
  try {
    currentReceipt.value = await cartonProcurementApi.createReceipt({
      factory_id: selectedFactoryId.value,
      delivery_note_no: receiptDeliveryNoteNo.value,
      delivery_date: receiptDeliveryDate.value,
      import_batch_id: receiptBatchId.value,
      note: `来源文件：${selectedReceiptFileName.value}；已逐行人工复核`,
      lines: receiptLines.map((row) => ({
        order_line_id: row.orderLineId,
        delivered_quantity: Number(row.deliveryQuantity),
        received_quantity: Number(row.receivedQuantity),
        damaged_quantity: Number(row.damagedQuantity),
        rejected_quantity: Number(row.rejectedQuantity),
        unusable_quantity: Number(row.unusableQuantity),
        unit_price: Number(row.unitPrice),
        location: row.location,
        feedback_note: '导入识别后人工复核',
      })),
    })
    receiptSaved.value = true
    actionMessage.value = `待确认收料单 ${currentReceipt.value.receipt_no} 已保存；有效收料 ${formatNumber(receiptTotals.value.effective)}，尚未写入库存。`
  } catch (error) {
    actionMessage.value = `收料单未保存：${getApiErrorMessage(error)}`
  } finally {
    savingReceipt.value = false
  }
}

async function confirmCurrentReceipt() {
  if (!currentReceipt.value) return
  confirmingReceipt.value = true
  try {
    currentReceipt.value = await cartonProcurementApi.confirmReceipt(
      selectedFactoryId.value,
      currentReceipt.value.id,
      currentReceipt.value.revision,
    )
    actionMessage.value = `收料单 ${currentReceipt.value.receipt_no} 已由人工确认，后端已按有效收料生成入库流水。`
    await loadBackendData()
  } catch (error) {
    actionMessage.value = `确认入库失败：${getApiErrorMessage(error)}`
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
    actionMessage.value = `已生成 ${closingPeriod.value} 月结草稿，共 ${closings.length} 个客户；尚未确认或锁账。`
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
  return ({ DRAFT: '提交核对', PENDING: '确认对平', CONFIRMED: '锁账', LOCKED: '已锁账' } as const)[status]
}

function closingRecord(rowId: string) {
  return closingRecords.value.find((row) => row.id === rowId)
}

function closingButtonLabel(rowId: string) {
  const closing = closingRecord(rowId)
  return closing ? closingActionLabel(closing.status) : '等待正式数据'
}

function closingButtonDisabled(rowId: string) {
  const closing = closingRecord(rowId)
  return !closing || closing.status === 'LOCKED' || Boolean(closingBusyId.value)
}

async function advanceClosing(rowId: string) {
  const closing = closingRecords.value.find((row) => row.id === rowId)
  if (!closing || closing.status === 'LOCKED') return
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
            v-model="selectedCustomer"
            aria-label="客户筛选"
            class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-700 outline-none focus:border-teal-500"
          >
            <option v-for="customer in cartonCustomers" :key="customer" :value="customer">{{ customer }}</option>
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
              本周核对风险
              <CalendarClock class="size-4 text-amber-600" aria-hidden="true" />
            </div>
            <div class="mt-2 text-3xl font-bold tabular-nums text-slate-950">{{ weeklyRiskCount }}</div>
            <p class="mt-1 text-[11px] text-slate-400">仅提示漏单、数量和交期差异</p>
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
              <li class="flex gap-2"><CheckCircle2 class="mt-0.5 size-4 shrink-0 text-teal-300" />周排期只用于防漏核对，不会自动创建正式订单</li>
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
                  <div class="mt-0.5 truncate text-[10px] text-slate-500">{{ row.customer }} · {{ row.materials.length }} 项纸品 · 交期 {{ row.dueDate }}</div>
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
            <p class="mt-1 text-[11px] text-slate-500">一张合同作为一条主记录，外箱、内箱、滑板纸、卡纸等纸品集中列在合同内；纸品类型、纸质和规格分别保存。</p>
          </div>
          <button type="button" class="inline-flex h-9 items-center gap-2 rounded-lg bg-teal-700 px-3.5 text-[12px] font-bold text-white transition hover:bg-teal-800" @click="showOrderModal = true">
            <Plus class="size-4" aria-hidden="true" />
            新建纸箱订单
          </button>
        </div>

        <div class="space-y-3">
          <article v-for="row in visibleOrders" :key="row.id" class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <div class="grid gap-3 border-b border-slate-200 bg-slate-50/70 px-4 py-3 md:grid-cols-[1.05fr_1fr_0.8fr_0.75fr_0.85fr_auto] md:items-center">
              <div><div class="text-[10px] font-bold text-slate-400">合同订单</div><div class="mt-1 font-semibold text-slate-950">{{ row.id }}</div><div class="text-[10px] text-slate-500">{{ row.orderDate }}</div></div>
              <div><div class="text-[10px] font-bold text-slate-400">客户 / 合同号</div><div class="mt-1 font-semibold">{{ row.customer }}</div><div class="font-mono text-[10px] text-slate-500">{{ row.contractNo }}</div></div>
              <div><div class="text-[10px] font-bold text-slate-400">货号</div><div class="mt-1 font-mono font-semibold">{{ row.itemNo }}</div></div>
              <div><div class="text-[10px] font-bold text-slate-400">产品数量</div><div class="mt-1 font-semibold tabular-nums">{{ formatNumber(row.orderQuantity) }}</div></div>
              <div><div class="text-[10px] font-bold text-slate-400">计划交期</div><div class="mt-1 font-semibold">{{ row.dueDate }}</div></div>
              <span class="w-fit rounded-full px-2.5 py-1 text-[10px] font-bold ring-1 ring-inset" :class="toneClass(row.tone)">{{ row.status }}</span>
            </div>

            <div class="px-4 py-3">
              <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
                <div class="font-bold text-slate-900">合同内纸品明细 · {{ row.materials.length }} 行</div>
                <div class="text-[10px] text-slate-500">同一货号的多种纸品统一归在本合同下</div>
              </div>
              <div class="overflow-x-auto rounded-lg border border-slate-200">
                <table class="min-w-[900px] w-full text-left">
                  <thead class="bg-slate-50 text-[10px] font-bold text-slate-500"><tr><th class="px-3 py-2.5">纸品类型</th><th class="px-3 py-2.5">纸质</th><th class="px-3 py-2.5">规格</th><th class="px-3 py-2.5 text-right">单件用量</th><th class="px-3 py-2.5 text-right">需求数量（自动）</th><th class="px-3 py-2.5">单位</th></tr></thead>
                  <tbody class="divide-y divide-slate-100">
                    <tr v-for="material in row.materials" :key="material.id">
                      <td class="px-3 py-2.5 font-semibold text-slate-900">{{ material.packagingType }}</td>
                      <td class="px-3 py-2.5 font-semibold text-teal-700">{{ material.paperQuality }}</td>
                      <td class="px-3 py-2.5 text-slate-600">{{ material.specification }}</td>
                      <td class="px-3 py-2.5 text-right font-semibold tabular-nums">{{ formatUsage(material.usage) }}</td>
                      <td class="px-3 py-2.5 text-right"><div class="font-bold text-teal-700 tabular-nums">{{ formatRequiredQuantity(material.usage, row.orderQuantity) }}</div><div class="text-[9px] text-slate-400">用量 × {{ formatNumber(row.orderQuantity) }}</div></td>
                      <td class="px-3 py-2.5 text-slate-500">{{ material.unit }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p class="mt-2 text-[10px] text-slate-500">备注：{{ row.note }}</p>
            </div>
          </article>
          <div v-if="visibleOrders.length === 0" class="rounded-xl border border-slate-200 bg-white px-4 py-12 text-center text-slate-400">没有符合当前筛选条件的合同订单</div>
        </div>
      </section>

      <section v-else-if="activeTab === 'weekly-check'" class="space-y-4">
        <div class="grid gap-4 xl:grid-cols-[1fr_360px]">
          <article class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 class="font-bold text-slate-950">每周客户查货排期核对</h2>
                <p class="mt-1 text-[11px] text-slate-500">按 Reference、PO、客户、货号、数量和验货期与纸箱订单做人工复核。</p>
              </div>
              <input ref="weeklyFileInput" type="file" accept=".xlsx,.xls" class="hidden" aria-label="选择每周排期文件" @change="handleWeeklyFile">
              <button
                type="button"
                :disabled="importingWeekly"
                class="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-bold text-slate-700"
                @click="triggerWeeklyImport"
              >
                <FileSpreadsheet class="size-4 text-emerald-600" />{{ importingWeekly ? '正在核对…' : '导入本周排期' }}
              </button>
            </div>
            <p v-if="selectedWeeklyFileName" class="mt-2 text-[10px] text-slate-500">当前文件：<span class="font-semibold text-slate-700">{{ selectedWeeklyFileName }}</span></p>
          </article>
          <article class="rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-900 shadow-sm">
            <div class="flex gap-2 font-bold"><ShieldCheck class="size-4 shrink-0" />防误建规则</div>
            <p class="mt-2 text-[11px] leading-5">导入排期只生成核对结果和待办，<strong>不会自动创建正式纸箱订单</strong>。</p>
          </article>
        </div>

        <div class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
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
      </section>

      <section v-else-if="activeTab === 'receipts'" class="space-y-4">
        <form class="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm lg:flex-row lg:items-end" @submit.prevent="searchReceipts">
          <label class="min-w-0 flex-1 space-y-1.5">
            <span class="text-[11px] font-bold text-slate-600">查找送货单或明细</span>
            <span class="relative block">
              <Search class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
              <input v-model="receiptSearchInput" aria-label="查找送货单" placeholder="送货单号 / 合同号 / 货号 / 品名" class="h-10 w-full rounded-lg border border-slate-200 bg-slate-50 pl-9 pr-3 outline-none transition focus:border-teal-500 focus:bg-white">
            </span>
          </label>
          <button type="submit" class="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-[12px] font-bold text-slate-700 transition hover:border-teal-300 hover:text-teal-700">
            <Search class="size-4" aria-hidden="true" />查找
          </button>
          <input ref="receiptFileInput" type="file" accept=".pdf,.jpg,.jpeg,.png,.xlsx,.xls" class="hidden" aria-label="选择送货单文件" @change="handleReceiptFile">
          <button type="button" :disabled="importingReceipt" class="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-teal-700 px-4 text-[12px] font-bold text-white transition hover:bg-teal-800 disabled:opacity-60" @click="triggerReceiptImport">
            <Upload class="size-4" aria-hidden="true" />{{ importingReceipt ? '正在识别…' : '导入送货单' }}
          </button>
          <div v-if="selectedReceiptFileName" class="text-[10px] text-slate-500 lg:max-w-52">已选择：<span class="font-semibold text-slate-700">{{ selectedReceiptFileName }}</span></div>
        </form>

        <div v-if="apiConnected && receiptLines.length === 0" class="rounded-xl border border-teal-200 bg-teal-50 p-5 text-teal-900 shadow-sm">
          <div class="flex items-center gap-2 font-bold"><Upload class="size-4" />等待导入并复核送货单</div>
          <p class="mt-1 text-[11px] leading-5 text-teal-800">选择文件后，后端先登记唯一指纹和待复核批次；字段匹配与数量确认完成前，不会创建收料单或库存流水。</p>
        </div>

        <div v-else class="grid gap-4 xl:grid-cols-[1.25fr_0.75fr]">
          <article class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div class="flex items-center gap-2"><Truck class="size-5 text-teal-700" /><h2 class="text-[15px] font-bold text-slate-950">送货单 {{ receiptDeliveryNoteNo || '待识别' }}</h2></div>
                <p class="mt-1 text-[11px] text-slate-500">河源东康纸品有限公司 · 单据日期 {{ receiptDeliveryDate || '待复核' }} · 来源：{{ selectedReceiptFileName || '只读演示' }}</p>
              </div>
              <span class="rounded-full bg-blue-50 px-2.5 py-1 text-[10px] font-bold text-blue-700 ring-1 ring-inset ring-blue-200">待逐行人工反馈</span>
            </div>
            <div class="mt-4 grid gap-3 sm:grid-cols-3">
              <div class="rounded-lg border border-slate-200 bg-slate-50 p-3"><div class="text-[10px] text-slate-500">已匹配明细</div><div class="mt-1 text-lg font-bold">{{ receiptLines.length }} 行</div></div>
              <div class="rounded-lg border border-slate-200 bg-slate-50 p-3"><div class="text-[10px] text-slate-500">识别金额复算</div><div class="mt-1 text-lg font-bold">{{ formatMoney(receiptAmount) }}</div></div>
              <div class="rounded-lg border border-slate-200 bg-slate-50 p-3"><div class="text-[10px] text-slate-500">有效收料</div><div class="mt-1 text-lg font-bold">{{ formatNumber(receiptTotals.effective) }}</div></div>
            </div>
          </article>
          <article class="rounded-xl border border-slate-200 bg-slate-950 p-5 text-white shadow-sm">
            <h2 class="flex items-center gap-2 font-bold"><GitBranch class="size-4 text-teal-300" />证据与录入边界</h2>
            <div class="mt-4 space-y-2.5 text-[11px] text-slate-300">
              <div class="rounded-lg bg-white/5 px-3 py-2"><span class="font-bold text-white">文件证据</span>：后端保留文件名、大小和唯一指纹，防止重复导入</div>
              <div class="rounded-lg bg-white/5 px-3 py-2"><span class="font-bold text-white">识别值</span>：Excel 表头或图片/PDF OCR 结果必须人工复核</div>
              <div class="rounded-lg bg-white/5 px-3 py-2"><span class="font-bold text-white">人工反馈</span>：实收、破损、拒收、其他不可用逐行填写</div>
            </div>
          </article>
        </div>

        <div class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div class="border-b border-slate-200 px-4 py-3">
            <h2 class="font-bold text-slate-950">收料反馈明细</h2>
            <p class="mt-1 text-[11px] text-slate-500">有效收料 = 实收 − 破损 − 拒收 − 其他不可用；分批收料后订单仍保持未齐状态。</p>
          </div>
          <div class="overflow-x-auto">
            <table class="min-w-[1320px] w-full text-left">
              <thead class="bg-slate-50 text-[10px] font-bold text-slate-500">
                <tr><th class="px-4 py-3">订单编号</th><th class="px-4 py-3">品名 / 规格</th><th class="px-4 py-3 text-right">送货数量</th><th class="px-4 py-3 text-right">单价</th><th class="px-3 py-3 text-right">实收</th><th class="px-3 py-3 text-right">破损</th><th class="px-3 py-3 text-right">拒收</th><th class="px-3 py-3 text-right">其他不可用</th><th class="px-4 py-3 text-right">有效收料</th><th class="px-4 py-3">来源</th></tr>
              </thead>
              <tbody class="divide-y divide-slate-100">
                <tr v-for="row in visibleReceiptLines" :key="row.id">
                  <td class="px-4 py-3 font-mono text-[11px] font-semibold">{{ row.orderNo }}</td>
                  <td class="px-4 py-3"><div class="font-semibold">{{ row.description }}</div><div class="mt-0.5 text-[10px] text-slate-500">{{ row.specification }}</div></td>
                  <td class="px-4 py-3 text-right font-semibold tabular-nums">{{ row.deliveryQuantity }}</td>
                  <td class="px-4 py-3 text-right tabular-nums">{{ row.unitPrice.toFixed(2) }}</td>
                  <td class="px-3 py-2"><input v-model.number="row.receivedQuantity" :aria-label="`${row.id} 实收`" type="number" min="0" class="ml-auto block h-8 w-20 rounded-md border border-slate-200 px-2 text-right font-semibold outline-none focus:border-teal-500"></td>
                  <td class="px-3 py-2"><input v-model.number="row.damagedQuantity" :aria-label="`${row.id} 破损`" type="number" min="0" class="ml-auto block h-8 w-20 rounded-md border border-slate-200 px-2 text-right outline-none focus:border-teal-500"></td>
                  <td class="px-3 py-2"><input v-model.number="row.rejectedQuantity" :aria-label="`${row.id} 拒收`" type="number" min="0" class="ml-auto block h-8 w-20 rounded-md border border-slate-200 px-2 text-right outline-none focus:border-teal-500"></td>
                  <td class="px-3 py-2"><input v-model.number="row.unusableQuantity" :aria-label="`${row.id} 其他不可用`" type="number" min="0" class="ml-auto block h-8 w-20 rounded-md border border-slate-200 px-2 text-right outline-none focus:border-teal-500"></td>
                  <td class="px-4 py-3 text-right text-[14px] font-bold text-teal-700 tabular-nums">{{ Math.max(0, Number(row.receivedQuantity || 0) - Number(row.damagedQuantity || 0) - Number(row.rejectedQuantity || 0) - Number(row.unusableQuantity || 0)) }}</td>
                  <td class="px-4 py-3"><span class="rounded-full bg-violet-50 px-2 py-0.5 text-[10px] font-bold text-violet-700 ring-1 ring-inset ring-violet-200">{{ row.sourceLabel }}</span></td>
                </tr>
                <tr v-if="visibleReceiptLines.length === 0"><td colspan="10" class="px-4 py-12 text-center text-slate-400">没有找到匹配的送货明细</td></tr>
              </tbody>
              <tfoot class="border-t border-slate-200 bg-slate-50 font-bold">
                <tr><td colspan="2" class="px-4 py-3">本页合计</td><td class="px-4 py-3 text-right">{{ receiptTotals.delivered }}</td><td class="px-4 py-3 text-right">—</td><td class="px-3 py-3 text-right">{{ receiptTotals.received }}</td><td colspan="3" class="px-3 py-3 text-right text-red-600">不可用 {{ receiptTotals.unusable }}</td><td class="px-4 py-3 text-right text-teal-700">{{ receiptTotals.effective }}</td><td class="px-4 py-3">—</td></tr>
              </tfoot>
            </table>
          </div>
          <div class="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 px-4 py-3">
            <p class="text-[11px] text-slate-500">只有逐行复核并正式确认后，后端才会按有效收料数量生成入库流水。</p>
            <div class="flex flex-wrap gap-2">
              <button v-if="!currentReceipt" type="button" :disabled="receiptLines.length === 0 || savingReceipt" class="inline-flex h-9 items-center gap-2 rounded-lg border border-teal-300 bg-white px-4 text-[12px] font-bold text-teal-700 disabled:cursor-not-allowed disabled:opacity-50" @click="saveReceiptFeedback">
                <CheckCircle2 class="size-4" />{{ savingReceipt ? '正在保存…' : '保存待确认收料单' }}
              </button>
              <button v-else type="button" :disabled="currentReceipt.status === 'POSTED' || confirmingReceipt" class="inline-flex h-9 items-center gap-2 rounded-lg bg-teal-700 px-4 text-[12px] font-bold text-white disabled:cursor-not-allowed disabled:opacity-50" @click="confirmCurrentReceipt">
                <ShieldCheck class="size-4" />{{ currentReceipt.status === 'POSTED' ? '已确认入库' : confirmingReceipt ? '正在入库…' : '人工确认并入库' }}
              </button>
            </div>
          </div>
        </div>
      </section>

      <section v-else-if="activeTab === 'inventory'" class="space-y-4">
        <div class="grid gap-4 xl:grid-cols-[1fr_380px]">
          <article class="rounded-xl border border-teal-200 bg-teal-50 p-4 shadow-sm">
            <div class="flex items-center gap-2 font-bold text-teal-950"><Boxes class="size-4" />实时库存作业页</div>
            <p class="mt-1 text-[11px] leading-5 text-teal-800">回答“现在每个客户、货号、纸品还剩多少，以及每一次入库、出库和调整是怎样发生的”。用于日常仓管作业，数据随业务发生持续变化。</p>
          </article>
          <article class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div class="text-[11px] font-bold text-slate-900">与月结页面的区别</div>
            <p class="mt-1 text-[11px] text-slate-500">月结只保留某一期间的客户汇总快照，用来对账，不展示每笔实时流水。</p>
            <button type="button" class="mt-3 text-[11px] font-bold text-teal-700" @click="setActiveTab('closing')">去月结对账 →</button>
          </article>
        </div>
        <div class="grid gap-3 md:grid-cols-3">
          <article class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div class="text-[11px] text-slate-500">当前筛选结存</div><div class="mt-2 text-2xl font-bold tabular-nums">{{ formatNumber(inventoryBalance) }} 箱</div><div class="mt-1 text-[10px] text-slate-400">取每个货号最新一笔流水结存</div></article>
          <article class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div class="text-[11px] text-slate-500">流水记录</div><div class="mt-2 text-2xl font-bold tabular-nums">{{ visibleMovements.length }}</div><div class="mt-1 text-[10px] text-slate-400">入库、出库与调整均保留来源单据</div></article>
          <article class="rounded-xl border border-blue-200 bg-blue-50 p-4 shadow-sm"><div class="flex items-center gap-2 text-[11px] font-bold text-blue-800"><ShieldCheck class="size-4" />不可变流水原则</div><p class="mt-2 text-[11px] leading-5 text-blue-700">发现错误时新增冲销或调整记录，不直接覆盖历史数量。</p></article>
        </div>
        <div class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div class="border-b border-slate-200 px-4 py-3"><h2 class="font-bold text-slate-950">实时库存结存台账</h2><p class="mt-1 text-[11px] text-slate-500">一行代表一个客户 + 货号 + 纸品类型的当前结存，纸质和规格分别显示。</p></div>
          <div class="overflow-x-auto">
            <table class="min-w-[1100px] w-full text-left">
              <thead class="bg-slate-50 text-[10px] font-bold text-slate-500"><tr><th class="px-4 py-3">客户 / 合同</th><th class="px-4 py-3">货号</th><th class="px-4 py-3">纸品类型</th><th class="px-4 py-3">纸质</th><th class="px-4 py-3">规格</th><th class="px-4 py-3">仓位</th><th class="px-4 py-3 text-right">当前结存</th><th class="px-4 py-3">最近变动</th></tr></thead>
              <tbody class="divide-y divide-slate-100">
                <tr v-for="row in inventoryBalances" :key="`${row.customer}-${row.itemNo}-${row.packagingType}`">
                  <td class="px-4 py-3"><div class="font-semibold">{{ row.customer }}</div><div class="text-[10px] text-slate-500">{{ row.poNumber }}</div></td>
                  <td class="px-4 py-3 font-mono font-semibold">{{ row.itemNo }}</td>
                  <td class="px-4 py-3 font-semibold">{{ row.packagingType }}</td>
                  <td class="px-4 py-3 font-semibold text-teal-700">{{ row.paperQuality }}</td>
                  <td class="px-4 py-3 text-slate-600">{{ row.specification }}</td>
                  <td class="px-4 py-3">{{ row.location }}</td>
                  <td class="px-4 py-3 text-right text-[14px] font-bold tabular-nums">{{ row.balance }}</td>
                  <td class="px-4 py-3 text-[11px] text-slate-500">{{ row.date }}</td>
                </tr>
                <tr v-if="inventoryBalances.length === 0"><td colspan="8" class="px-4 py-12 text-center text-slate-400">没有符合当前筛选条件的实时结存</td></tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div class="border-b border-slate-200 px-4 py-3"><h2 class="font-bold text-slate-950">逐笔交易流水</h2><p class="mt-1 text-[11px] text-slate-500">每笔业务独立留痕并指向来源单据，用于追溯结存是怎样形成的。</p></div>
          <div class="overflow-x-auto">
            <table class="min-w-[1380px] w-full text-left">
              <thead class="bg-slate-50 text-[10px] font-bold text-slate-500"><tr><th class="px-4 py-3">时间 / 流水号</th><th class="px-4 py-3">来源单据</th><th class="px-4 py-3">客户 / PO</th><th class="px-4 py-3">货号</th><th class="px-4 py-3">纸品</th><th class="px-4 py-3">纸质</th><th class="px-4 py-3">类型</th><th class="px-4 py-3 text-right">变动数量</th><th class="px-4 py-3 text-right">结存</th><th class="px-4 py-3">仓位</th><th class="px-4 py-3">经手人</th></tr></thead>
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
                </tr>
                <tr v-if="visibleMovements.length === 0"><td colspan="11" class="px-4 py-12 text-center text-slate-400">没有符合当前筛选条件的库存流水</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section v-else-if="activeTab === 'closing'" class="space-y-4">
        <div class="grid gap-4 xl:grid-cols-[1fr_380px]">
          <article class="rounded-xl border border-violet-200 bg-violet-50 p-4 shadow-sm"><div class="flex items-center gap-2 font-bold text-violet-950"><FileSpreadsheet class="size-4" />期间月结与供应商对账页</div><p class="mt-1 text-[11px] leading-5 text-violet-800">回答“某客户在选定期间的期初、入库、出库、调整和期末是否对平”。这是按月冻结的汇总快照，不承担日常收发记录。</p></article>
          <article class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div class="text-[11px] font-bold text-slate-900">与库存页面的区别</div><p class="mt-1 text-[11px] text-slate-500">要看当前余量、仓位或某一笔收发来源，应返回实时库存台账。</p><button type="button" class="mt-3 text-[11px] font-bold text-teal-700" @click="setActiveTab('inventory')">去实时库存台账 →</button></article>
        </div>
        <div class="grid gap-3 md:grid-cols-3">
          <article class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div class="text-[11px] text-slate-500">月结期间</div><div class="mt-2 flex flex-wrap items-center gap-2"><input v-model="closingPeriod" aria-label="月结期间" type="month" class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-[13px] font-bold outline-none focus:border-teal-500"><button type="button" :disabled="closingBusyId === 'generate'" class="h-9 rounded-lg bg-teal-700 px-3 text-[11px] font-bold text-white disabled:cursor-not-allowed disabled:opacity-50" @click="generateClosingSnapshot">{{ closingBusyId === 'generate' ? '生成中…' : '生成月结草稿' }}</button></div><div class="mt-1 text-[10px] text-slate-400">按所选月份形成快照，生成后仍需核对、确认和锁账</div></article>
          <article class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div class="text-[11px] text-slate-500">客户对账</div><div class="mt-2 text-2xl font-bold">{{ visibleClosings.length }} 家</div><div class="mt-1 text-[10px] text-slate-400">固定一家纸箱供应商，按客户核对</div></article>
          <article class="rounded-xl border border-amber-200 bg-amber-50 p-4 shadow-sm"><div class="text-[11px] font-bold text-amber-800">待处理</div><div class="mt-2 text-2xl font-bold text-amber-900">{{ visibleClosings.filter((row) => row.status !== '已锁账').length }}</div><div class="mt-1 text-[10px] text-amber-700">草稿、待核对或已确认待锁账的客户</div></article>
        </div>
        <div class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div class="border-b border-slate-200 px-4 py-3"><h2 class="font-bold text-slate-950">客户月结汇总快照</h2><p class="mt-1 text-[11px] text-slate-500">期末 = 期初 + 入库 − 出库 + 调整；对账确认后才进入后端锁定流程。</p></div>
          <div class="overflow-x-auto">
            <table class="min-w-[1220px] w-full text-left">
              <thead class="bg-slate-50 text-[10px] font-bold text-slate-500"><tr><th class="px-4 py-3">客户</th><th class="px-4 py-3">期间</th><th class="px-4 py-3 text-right">期初</th><th class="px-4 py-3 text-right">入库</th><th class="px-4 py-3 text-right">出库</th><th class="px-4 py-3 text-right">调整</th><th class="px-4 py-3 text-right">期末</th><th class="px-4 py-3 text-right">期末金额</th><th class="px-4 py-3">对账状态</th><th class="px-4 py-3">操作</th></tr></thead>
              <tbody class="divide-y divide-slate-100">
                <tr v-for="row in visibleClosings" :key="row.id" class="hover:bg-slate-50/80">
                  <td class="px-4 py-3 font-bold">{{ row.customer }}</td><td class="px-4 py-3">{{ row.period }}</td><td class="px-4 py-3 text-right tabular-nums">{{ row.openingQuantity }}</td><td class="px-4 py-3 text-right text-emerald-700 tabular-nums">+{{ row.inboundQuantity }}</td><td class="px-4 py-3 text-right text-blue-700 tabular-nums">-{{ row.outboundQuantity }}</td><td class="px-4 py-3 text-right tabular-nums">{{ row.adjustmentQuantity > 0 ? '+' : '' }}{{ row.adjustmentQuantity }}</td><td class="px-4 py-3 text-right text-[14px] font-bold tabular-nums">{{ row.endingQuantity }}</td><td class="px-4 py-3 text-right font-semibold tabular-nums">{{ formatMoney(row.endingAmount) }}</td><td class="px-4 py-3"><span class="rounded-full px-2 py-0.5 text-[10px] font-bold ring-1 ring-inset" :class="toneClass(row.tone)">{{ row.status }}</span></td><td class="px-4 py-3"><button type="button" :disabled="closingButtonDisabled(row.id)" class="h-8 rounded-lg border border-teal-200 bg-white px-3 text-[11px] font-bold text-teal-700 disabled:cursor-not-allowed disabled:border-slate-200 disabled:text-slate-400" @click="advanceClosing(row.id)">{{ closingBusyId === row.id ? '处理中…' : closingButtonLabel(row.id) }}</button></td>
                </tr>
                <tr v-if="visibleClosings.length === 0"><td colspan="10" class="px-4 py-12 text-center text-slate-400">没有符合当前筛选条件的月结记录；可先选择期间生成草稿</td></tr>
              </tbody>
            </table>
          </div>
          <div class="border-t border-slate-200 px-4 py-3"><p class="text-[11px] text-slate-500">状态依次为“草稿 → 待核对 → 已确认 → 已锁账”。锁账后禁止修改，需通过后续调整单处理差异。</p></div>
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
    </div>

    <div v-if="showOrderModal" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4" @click.self="showOrderModal = false">
      <form class="max-h-[92vh] w-full max-w-5xl overflow-y-auto rounded-2xl bg-white shadow-2xl" @submit.prevent="createLocalOrder">
        <div class="flex items-start justify-between border-b border-slate-200 px-5 py-4">
          <div><h2 class="text-[16px] font-bold text-slate-950">新建纸箱合同订单</h2><p class="mt-1 text-[11px] text-slate-500">先填写合同主信息，再在同一张合同内增加外箱、滑板纸、卡纸等多条纸品明细。</p></div>
          <button type="button" aria-label="关闭新建订单" class="rounded-lg p-2 text-slate-400 hover:bg-slate-100" @click="showOrderModal = false"><X class="size-4" /></button>
        </div>
        <div class="space-y-5 p-5">
          <section>
            <div class="mb-3 text-[11px] font-bold text-slate-900">合同主信息</div>
            <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              <label class="space-y-1.5"><span class="text-[11px] font-bold text-slate-600">客户</span><select v-model="orderForm.customer" aria-label="订单客户" class="h-10 w-full rounded-lg border border-slate-200 px-3 outline-none focus:border-teal-500"><option v-for="customer in cartonCustomers.filter((item) => item !== '全部客户')" :key="customer" :value="customer">{{ customer }}</option></select></label>
              <label class="space-y-1.5"><span class="text-[11px] font-bold text-slate-600">纸箱供应商</span><input value="河源东康纸品有限公司（系统固定）" aria-label="纸箱供应商" disabled class="h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-slate-500"></label>
              <label class="space-y-1.5"><span class="text-[11px] font-bold text-slate-600">合同号 *</span><input v-model="orderForm.contractNo" aria-label="合同号" placeholder="例如 SC700145365" class="h-10 w-full rounded-lg border border-slate-200 px-3 outline-none focus:border-teal-500"></label>
              <label class="space-y-1.5"><span class="text-[11px] font-bold text-slate-600">货号 *</span><input v-model="orderForm.itemNo" aria-label="货号" placeholder="例如 203302044" class="h-10 w-full rounded-lg border border-slate-200 px-3 outline-none focus:border-teal-500"></label>
              <label class="space-y-1.5"><span class="text-[11px] font-bold text-slate-600">产品订单数量</span><input v-model.number="orderForm.orderQuantity" aria-label="订单数量" type="number" min="1" class="h-10 w-full rounded-lg border border-slate-200 px-3 outline-none focus:border-teal-500"></label>
              <label class="space-y-1.5"><span class="text-[11px] font-bold text-slate-600">计划交期</span><input v-model="orderForm.dueDate" aria-label="计划交期" type="date" class="h-10 w-full rounded-lg border border-slate-200 px-3 outline-none focus:border-teal-500"></label>
            </div>
          </section>

          <section class="rounded-xl border border-slate-200">
            <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-slate-50 px-4 py-3">
              <div><div class="font-bold text-slate-950">合同内纸品明细</div><p class="mt-0.5 text-[10px] text-slate-500">每行填写单件用量，需求数量自动按“用量 × 产品订单数量”计算。</p></div>
              <button type="button" class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-teal-200 bg-white px-3 text-[11px] font-bold text-teal-700" @click="addOrderMaterialLine"><Plus class="size-3.5" />新增纸品明细</button>
            </div>
            <div class="space-y-3 p-4">
              <div v-for="(material, index) in orderForm.materials" :key="material.id" class="grid gap-3 rounded-lg border border-slate-200 bg-slate-50/60 p-3 lg:grid-cols-[1fr_1fr_1.7fr_0.8fr_0.9fr_0.65fr_auto] lg:items-end">
                <label class="space-y-1.5"><span class="text-[10px] font-bold text-slate-500">纸品类型 *</span><select v-model="material.packagingType" :aria-label="`纸品类型 ${index + 1}`" class="h-9 w-full rounded-lg border border-slate-200 bg-white px-2 outline-none focus:border-teal-500"><option>外箱</option><option>内箱</option><option>滑板纸</option><option>卡纸</option><option>展示盒</option><option>其他</option></select></label>
                <label class="space-y-1.5"><span class="text-[10px] font-bold text-slate-500">纸质 *</span><input v-model="material.paperQuality" :aria-label="`纸质 ${index + 1}`" placeholder="如 A33+B" class="h-9 w-full rounded-lg border border-slate-200 bg-white px-2 outline-none focus:border-teal-500"></label>
                <label class="space-y-1.5"><span class="text-[10px] font-bold text-slate-500">规格 *</span><input v-model="material.specification" :aria-label="`规格 ${index + 1}`" placeholder="长 × 宽 × 高；保留单位" class="h-9 w-full rounded-lg border border-slate-200 bg-white px-2 outline-none focus:border-teal-500"></label>
                <label class="space-y-1.5"><span class="text-[10px] font-bold text-slate-500">单件用量 *</span><input v-model.number="material.usage" :aria-label="`单件用量 ${index + 1}`" type="number" min="0.000001" step="0.000001" class="h-9 w-full rounded-lg border border-slate-200 bg-white px-2 text-right outline-none focus:border-teal-500"></label>
                <div class="space-y-1.5"><span class="text-[10px] font-bold text-slate-500">需求数量（自动）</span><output :aria-label="`需求数量 ${index + 1}`" class="flex h-9 w-full items-center justify-end rounded-lg border border-teal-200 bg-teal-50 px-2 font-bold text-teal-700 tabular-nums">{{ formatRequiredQuantity(material.usage, orderForm.orderQuantity) }}</output></div>
                <label class="space-y-1.5"><span class="text-[10px] font-bold text-slate-500">单位</span><select v-model="material.unit" :aria-label="`纸品单位 ${index + 1}`" class="h-9 w-full rounded-lg border border-slate-200 bg-white px-2 outline-none focus:border-teal-500"><option>个</option><option>张</option><option>套</option></select></label>
                <button type="button" :aria-label="`删除纸品明细 ${index + 1}`" class="flex size-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-400 transition hover:border-red-200 hover:text-red-600" @click="removeOrderMaterialLine(index)"><X class="size-4" /></button>
              </div>
            </div>
          </section>

          <label class="block space-y-1.5"><span class="text-[11px] font-bold text-slate-600">合同备注</span><textarea v-model="orderForm.note" aria-label="订单备注" rows="3" placeholder="历史规格来源、刀模版本或特殊交付要求" class="w-full rounded-lg border border-slate-200 px-3 py-2 outline-none focus:border-teal-500"></textarea></label>
        </div>
        <div class="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 bg-slate-50 px-5 py-4"><p class="text-[10px] text-slate-500">提交后写入正式台账，需求数量由后端按用量重新计算。</p><div class="flex gap-2"><button type="button" class="h-9 rounded-lg border border-slate-200 bg-white px-4 text-[12px] font-bold text-slate-600" @click="showOrderModal = false">取消</button><button type="submit" :disabled="savingOrder" class="h-9 rounded-lg bg-teal-700 px-4 text-[12px] font-bold text-white disabled:opacity-60">{{ savingOrder ? '正在保存…' : '建立正式订单' }}</button></div></div>
      </form>
    </div>
  </main>
</template>
