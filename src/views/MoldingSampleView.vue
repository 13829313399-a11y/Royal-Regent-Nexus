<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch, watchEffect } from 'vue'
import {
  ArrowLeft,
  Beaker,
  Building2,
  Check,
  CheckCheck,
  ChevronLeft,
  ChevronRight,
  Clock,
  ClipboardCheck,
  Download,
  ExternalLink,
  Factory,
  FilePlus2,
  FileText,
  Filter,
  Gavel,
  History,
  Layers,
  LayoutDashboard,
  MessageSquareText,
  PencilLine,
  Plus,
  Printer,
  RotateCcw,
  Save,
  Search,
  Send,
  Table2,
  Tag,
  Trash2,
  TriangleAlert,
  Upload,
  UserRound,
  X,
} from '@lucide/vue'
import { RouterLink, useRoute } from 'vue-router'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import {
  factoryContexts,
  isProductionFactoryContextId,
  type ProductionFactoryContextId,
} from '@/data/enterpriseMock'
import { rawMaterialDatabaseRows } from '@/data/rawMaterialDatabase'
import {
  buildCompletionGate,
  calculateExpectedMaterialAmountHkd,
  isExternalMoldingSampleOrder,
  resolveMaterialPrice,
  roundMoney,
} from '@/lib/moldingSampleBusiness'
import { getApiErrorMessage } from '@/lib/http'
import {
  MOLDING_SAMPLE_XLSX_MIME,
  moldingSampleApi,
  type MoldingSampleCreateRequest,
  type MoldingSampleDetailResponse,
  type MoldingSampleStatusRequest,
} from '@/api/moldingSample'
import {
  buildManualMoldingSampleCreateRequest,
  createManualMoldingSampleLineDraft,
  createManualMoldingSampleOrderDraft,
  deriveManualMoldingSampleOrderId,
  type ManualMoldingSampleLineDraft,
  type ManualMoldingSampleOrderDraft,
} from '@/lib/moldingSampleManualCreate'
import type {
  MoldingSampleItem,
  MoldingSampleOrder,
  MoldingSampleStatus,
  MoldingSampleWorkflowRecord,
} from '@/types/moldingSample'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

type ViewKey = 'overview' | 'create' | 'detail' | 'material-balance'
type OverviewDisplayMode = 'board' | 'list'
type MaterialBalancePeriodMode = 'day' | 'week' | 'month'
type ActionToastTone = 'success' | 'error' | 'info'
type StatusState = 'done' | 'current' | 'pending' | 'rejected'

interface KpiCard {
  label: string
  value: string
  detail: string
  icon: unknown
  className: string
}

interface BoardColumn {
  status: MoldingSampleStatus
  label: string
  detail: string
  records: MoldingSampleWorkflowRecord[]
  pagedRecords: MoldingSampleWorkflowRecord[]
  pagination: PaginationState<MoldingSampleWorkflowRecord>
  dotClass: string
}

interface PaginationState<T> {
  rows: T[]
  total: number
  page: number
  pageCount: number
  start: number
  end: number
  hasPrevious: boolean
  hasNext: boolean
}

interface MaterialBalanceItemRow {
  item: MoldingSampleItem
  expectedWeightKg: number
  actualWeightKg: number
  balanceWeightKg: number
  balanceAmountHkd: number | null
  hasActualWeight: boolean
}

interface MaterialBalanceOrderRow {
  record: MoldingSampleWorkflowRecord
  itemRows: MaterialBalanceItemRow[]
  expectedWeightKg: number
  actualWeightKg: number
  balanceWeightKg: number
  balanceAmountHkd: number | null
  missingActualCount: number
  unknownAmountCount: number
}

interface MaterialBalanceSummary {
  orderCount: number
  totalExpectedWeightKg: number
  totalActualWeightKg: number
  totalBalanceWeightKg: number
  knownBalanceAmountHkd: number
  unknownAmountCount: number
}

interface MaterialBalancePeriodOption {
  key: MaterialBalancePeriodMode
  label: string
  detail: string
}

interface MaterialBalancePeriodKey {
  key: string
  label: string
  detail: string
  startDate: string
  endDate: string
}

interface MaterialBalancePeriodRow extends MaterialBalancePeriodKey {
  orderRows: MaterialBalanceOrderRow[]
  orderCount: number
  expectedWeightKg: number
  actualWeightKg: number
  balanceWeightKg: number
  balanceAmountHkd: number | null
  missingActualCount: number
  unknownAmountCount: number
}

interface WorkflowStep {
  status: MoldingSampleStatus
  title: string
  detail: string
}

interface ApprovalActor {
  passAction: string
  rejectAction: string
  actorName: string
  permission: string
}

interface CreateSuccessToast {
  orderId: string
  detail: string
}

interface RawMaterialSelectOption {
  value: string
  label: string
  code: string
  category: string
  origin: string
  searchText: string
}

interface RawMaterialPickerPosition {
  left: number
  top: number
  width: number
}

const route = useRoute()
const appStore = useAppStore()
const authStore = useAuthStore()

function getTodayText(date = new Date()) {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')

  return `${date.getFullYear()}-${month}-${day}`
}

const today = getTodayText()
const activeView = ref<ViewKey>('overview')
const overviewDisplayMode = ref<OverviewDisplayMode>('board')
const materialBalancePeriodMode = ref<MaterialBalancePeriodMode>('day')
const selectedOrderId = ref(readQueryString(route.query.order_id))
const selectedBatchOrderIds = ref<string[]>([])
const printableRecords = ref<MoldingSampleWorkflowRecord[]>([])
const printPreviewVisible = ref(false)
const searchKeyword = ref('')
const overviewListPage = ref(1)
const boardPageByStatus = ref<Partial<Record<MoldingSampleStatus, number>>>({})
const materialBalancePeriodPage = ref(1)
const materialBalanceDetailPage = ref(1)
const apiRecords = ref<MoldingSampleDetailResponse[]>([])
const apiState = ref<'checking' | 'connected' | 'empty' | 'error'>('checking')
const actionMessage = ref('正在读取正式啤办单列表...')
const actionToastVisible = ref(true)
const currentRmbToHkdRate = ref<number | null>(null)
const createDraft = ref<ManualMoldingSampleOrderDraft>(createManualMoldingSampleOrderDraft())
const createErrors = ref<string[]>([])
const createSubmitting = ref(false)
const createSuccessToast = ref<CreateSuccessToast | null>(null)
const editingRejectedOrderId = ref('')
const approvalNote = ref('')
const approvalSubmitting = ref(false)
const withdrawSubmitting = ref(false)
const deleteSubmitting = ref(false)
const deleteConfirmingOrderId = ref('')
const excelFileInput = ref<HTMLInputElement | null>(null)
const excelImporting = ref(false)
const excelExporting = ref(false)
const excelAccept = `${MOLDING_SAMPLE_XLSX_MIME},.xlsx`
const createLineGridClass = 'grid-cols-[40px_132px_142px_150px_112px_110px_138px_190px_112px_124px_74px_96px_82px_92px_112px_118px_138px_160px_72px]'
const createDraftStoragePrefix = 'rr:molding-sample:create-draft'
const RAW_MATERIAL_PICKER_WIDTH = 360
const RAW_MATERIAL_PICKER_HEIGHT = 256
const RAW_MATERIAL_PICKER_GAP = 8
const RAW_MATERIAL_PICKER_VIEWPORT_PADDING = 12
const rawMaterialPriceList = rawMaterialDatabaseRows.flatMap((row) => {
  const unitPrice = Number(row.unitPriceHkdPerLb)

  return row.materialName.trim() && Number.isFinite(unitPrice) && unitPrice > 0
    ? [{ material: row.materialName.trim(), unit_price: unitPrice, notes: '原料资料' }]
    : []
})
const RAW_MATERIAL_PICKER_VISIBLE_LIMIT = 60
const activeRawMaterialPickerLineIndex = ref<number | null>(null)
const rawMaterialSearchByLine = ref<Record<number, string>>({})
const rawMaterialPickerPositionByLine = ref<Record<number, RawMaterialPickerPosition>>({})
let createSuccessToastTimer: ReturnType<typeof setTimeout> | null = null
let actionToastTimer: ReturnType<typeof setTimeout> | null = null

const workflowSteps: WorkflowStep[] = [
  { status: '待审核', title: '主管审核', detail: '工程提交后进入主管队列' },
  { status: '待生产', title: '待生产', detail: '主管通过后流转到啤机部' },
  { status: '生产中', title: '啤机生产', detail: '回填实际用料和啤办费' },
  { status: '已完成', title: '完成归档', detail: '生产完成后回传工程单' },
]

const boardStatuses: MoldingSampleStatus[] = [
  '待审核',
  '待生产',
  '生产中',
  '已完成',
  '已驳回',
  '已撤回',
]

const materialBalancePeriodOptions: MaterialBalancePeriodOption[] = [
  { key: 'day', label: '日结余', detail: '每日汇总' },
  { key: 'week', label: '周结余', detail: '周一至周日' },
  { key: 'month', label: '月结余', detail: '自然月汇总' },
]

const MOLDING_SAMPLE_PAGE_SIZE = 10

const statusToneClasses: Record<MoldingSampleStatus, string> = {
  待审核: 'border-amber-200 bg-amber-50 text-amber-700',
  待经理审核: 'border-blue-200 bg-blue-50 text-blue-700',
  待生产: 'border-indigo-200 bg-indigo-50 text-indigo-700',
  生产中: 'border-teal-200 bg-teal-50 text-teal-700',
  已完成: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  已驳回: 'border-red-200 bg-red-50 text-red-700',
  已撤回: 'border-slate-200 bg-slate-50 text-slate-600',
}

const statusDotClasses: Record<MoldingSampleStatus, string> = {
  待审核: 'bg-amber-400',
  待经理审核: 'bg-blue-400',
  待生产: 'bg-indigo-400',
  生产中: 'bg-teal-400',
  已完成: 'bg-emerald-400',
  已驳回: 'bg-red-400',
  已撤回: 'bg-slate-400',
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
    ?? factoryContexts.find((factory) => factory.id === 'huaxing')
    ?? factoryContexts[1],
)

const rawMaterialOptions = computed<RawMaterialSelectOption[]>(() => {
  const seenValues = new Set<string>()

  return rawMaterialDatabaseRows.flatMap((row) => {
    const value = row.materialName.trim()

    if (!value || seenValues.has(value)) {
      return []
    }

    seenValues.add(value)

    const sourceParts = [row.materialCode, row.plasticCategory].filter(Boolean)
    const label = sourceParts.length ? `${value}（${sourceParts.join(' / ')}）` : value
    const searchText = [
      value,
      label,
      row.materialCode,
      row.plasticCategory,
      row.commodityName,
      row.origin,
      row.remarks,
    ].join(' ').toLowerCase()

    return [{
      value,
      label,
      code: row.materialCode,
      category: row.plasticCategory,
      origin: row.origin,
      searchText,
    }]
  })
})

const rawMaterialOptionByValue = computed(() =>
  new Map(rawMaterialOptions.value.map((option) => [option.value, option])),
)

const rawMaterialOptionValueSet = computed(() =>
  new Set(rawMaterialOptionByValue.value.keys()),
)

const productionTaskRoute = computed(() => {
  const params = new URLSearchParams({ factory: selectedFactoryId.value })

  if (selectedRecord.value?.order.id) {
    params.set('order_id', selectedRecord.value.order.id)
  }

  return `/modules/production/molding-sample-tasks?${params.toString()}`
})

const sourceRecords = computed<MoldingSampleWorkflowRecord[]>(() => {
  return apiRecords.value.map(toWorkflowRecord)
})

const factoryRecords = computed<MoldingSampleWorkflowRecord[]>(() =>
  sourceRecords.value.filter((record) => record.factory_id === selectedFactoryId.value),
)

const visibleRecords = computed<MoldingSampleWorkflowRecord[]>(() => {
  const keyword = searchKeyword.value.trim().toLowerCase()

  if (!keyword) {
    return factoryRecords.value
  }

  return factoryRecords.value.filter((record) => [
    record.order.id,
    record.order.order_number,
    record.order.doc_number,
    record.order.product_name,
    record.order.client_name,
    record.order.supervisor,
    record.order.eng_name,
    ...record.items.flatMap((item) => [item.mold_id, item.mold_name, item.material, item.color]),
    ...record.problems.flatMap((problem) => [problem.description, problem.reported_by, problem.status]),
  ].some((value) => String(value).toLowerCase().includes(keyword)))
})

const overviewListPagination = computed(() =>
  createPaginationState(visibleRecords.value, overviewListPage.value),
)
const paginatedVisibleRecords = computed(() => overviewListPagination.value.rows)

const selectedRecord = computed<MoldingSampleWorkflowRecord | null>(() =>
  visibleRecords.value.find((record) => record.order.id === selectedOrderId.value)
    ?? factoryRecords.value.find((record) => record.order.id === selectedOrderId.value)
    ?? factoryRecords.value[0]
    ?? null,
)

const selectedBatchOrderIdSet = computed(() => new Set(selectedBatchOrderIds.value))
const selectedBatchRecords = computed(() =>
  visibleRecords.value.filter((record) => selectedBatchOrderIdSet.value.has(record.order.id)),
)
const batchActionRecords = computed(() =>
  selectedBatchRecords.value.length > 0
    ? selectedBatchRecords.value
    : selectedRecord.value
      ? [selectedRecord.value]
      : [],
)
const selectedBatchCount = computed(() => selectedBatchRecords.value.length)
const isAllVisibleOrdersSelected = computed(() =>
  visibleRecords.value.length > 0
  && visibleRecords.value.every((record) => selectedBatchOrderIdSet.value.has(record.order.id)),
)

const selectedOrder = computed<MoldingSampleOrder>(() => selectedRecord.value?.order ?? createEmptySelectedOrder())
const selectedItems = computed(() => selectedRecord.value?.items ?? [])
const selectedProblems = computed(() => selectedRecord.value?.problems ?? [])
const selectedAuditLogs = computed(() => selectedRecord.value?.audit_logs ?? [])
const selectedCompletionGate = computed(() => selectedRecord.value
  ? buildCompletionGate(selectedOrder.value, selectedItems.value)
  : { can_complete: false, missing_item_ids: [], message: '暂无正式单据' },
)
const isSelectedExternal = computed(() => selectedRecord.value ? isExternalMoldingSampleOrder(selectedOrder.value) : false)

const kpiCards = computed<KpiCard[]>(() => {
  const records = visibleRecords.value
  const reviewCount = records.filter((record) => ['待审核', '待经理审核'].includes(record.order.status)).length
  const productionCount = records.filter((record) => ['待生产', '生产中'].includes(record.order.status)).length
  const completedCount = records.filter((record) => record.order.status === '已完成').length
  const blockedCount = records.filter((record) =>
    record.order.status === '已驳回'
    || record.order.status === '已撤回'
    || record.problems.length > 0
    || buildCompletionGate(record.order, record.items).missing_item_ids.length > 0,
  ).length

  return [
    {
      label: '当前厂区单据',
      value: String(records.length),
      detail: `${activeFactory.value.shortName} · 按状态分列`,
      icon: Layers,
      className: 'border-slate-200 bg-white text-slate-700',
    },
    {
      label: '审核中',
      value: String(reviewCount),
      detail: '主管节点',
      icon: Clock,
      className: 'border-amber-200 bg-amber-50 text-amber-700',
    },
    {
      label: '待啤机处理',
      value: String(productionCount),
      detail: '待生产 / 生产中',
      icon: Factory,
      className: 'border-teal-200 bg-teal-50 text-teal-700',
    },
    {
      label: '已完成',
      value: String(completedCount),
      detail: '完成归档回传',
      icon: CheckCheck,
      className: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    },
    {
      label: '卡点 / 退回',
      value: String(blockedCount),
      detail: '需要工程跟进',
      icon: TriangleAlert,
      className: 'border-red-200 bg-red-50 text-red-700',
    },
  ]
})

const boardColumns = computed<BoardColumn[]>(() =>
  boardStatuses.map((status) => {
    const records = visibleRecords.value.filter((record) => normalizeBoardStatus(record.order.status) === status)
    const pagination = createPaginationState(records, boardPageByStatus.value[status] ?? 1)

    return {
      status,
      label: status,
      detail: getStatusColumnDetail(status),
      records,
      pagedRecords: pagination.rows,
      pagination,
      dotClass: statusDotClasses[status],
    }
  }),
)

const materialBalanceRows = computed<MaterialBalanceOrderRow[]>(() =>
  visibleRecords.value.map(buildMaterialBalanceOrderRow),
)

const materialBalanceSummary = computed<MaterialBalanceSummary>(() => {
  const rows = materialBalanceRows.value

  return {
    orderCount: rows.length,
    totalExpectedWeightKg: roundMaterialWeight(rows.reduce((sum, row) => sum + row.expectedWeightKg, 0)),
    totalActualWeightKg: roundMaterialWeight(rows.reduce((sum, row) => sum + row.actualWeightKg, 0)),
    totalBalanceWeightKg: roundMaterialWeight(rows.reduce((sum, row) => sum + row.balanceWeightKg, 0)),
    knownBalanceAmountHkd: roundMoney(rows.reduce((sum, row) => sum + (row.balanceAmountHkd ?? 0), 0)),
    unknownAmountCount: rows.reduce((sum, row) => sum + (row.balanceAmountHkd === null ? 1 : 0), 0),
  }
})

const materialBalancePeriodRows = computed<MaterialBalancePeriodRow[]>(() =>
  buildMaterialBalancePeriodRows(materialBalanceRows.value, materialBalancePeriodMode.value),
)

const materialBalancePeriodPagination = computed(() =>
  createPaginationState(materialBalancePeriodRows.value, materialBalancePeriodPage.value),
)
const paginatedMaterialBalancePeriodRows = computed(() => materialBalancePeriodPagination.value.rows)
const materialBalanceDetailPagination = computed(() =>
  createPaginationState(materialBalanceRows.value, materialBalanceDetailPage.value),
)
const paginatedMaterialBalanceRows = computed(() => materialBalanceDetailPagination.value.rows)

const actionToastTone = computed<ActionToastTone>(() => {
  if (apiState.value === 'error' || /失败|错误|未提交|不能|没有|请选择|缺失/.test(actionMessage.value)) {
    return 'error'
  }

  if (/正在|导入中|导出中/.test(actionMessage.value)) {
    return 'info'
  }

  return 'success'
})

const actionToastFrameClass = computed(() => {
  if (actionToastTone.value === 'error') {
    return 'border-red-200 bg-white text-red-700 shadow-red-100/70'
  }

  if (actionToastTone.value === 'info') {
    return 'border-sky-200 bg-white text-sky-700 shadow-sky-100/70'
  }

  return 'border-teal-200 bg-white text-teal-700 shadow-teal-100/70'
})

const actionToastIconClass = computed(() => {
  if (actionToastTone.value === 'error') {
    return 'bg-red-50 text-red-600'
  }

  if (actionToastTone.value === 'info') {
    return 'bg-sky-50 text-sky-600'
  }

  return 'bg-teal-50 text-teal-700'
})

const detailRows = computed(() => selectedItems.value.slice(0, 8))
const printPreviewItemCount = computed(() =>
  printableRecords.value.reduce((total, record) => total + record.items.length, 0),
)

function getExpectedMaterialAmountHkd(item: MoldingSampleItem) {
  return calculateExpectedMaterialAmountHkd(item, rawMaterialPriceList)
}

function getRawMaterialUnitPrice(material: string) {
  return resolveMaterialPrice(material, rawMaterialPriceList)?.unit_price ?? null
}

function getRawMaterialUnitPriceLabel(material: string) {
  const unitPrice = getRawMaterialUnitPrice(material)

  if (unitPrice !== null) {
    return formatMoney(unitPrice)
  }

  return material.trim() ? '待维护' : '待选择'
}

const isSelectedOrderDataExpanded = ref(false)
const canManageSelectedFactory = computed(() => authStore.hasFactoryScope(selectedFactoryId.value))
const canManageSelectedOrderFactory = computed(() => {
  const factoryId = selectedRecord.value?.order.factory_id || selectedFactoryId.value
  return authStore.hasFactoryScope(factoryId)
})
const isSelectedFactoryReadOnly = computed(() => !canManageSelectedFactory.value)
const canCreateOrder = computed(() => authStore.hasPermission('molding_sample:create') && canManageSelectedFactory.value)
const canEditDraftOrder = computed(() => authStore.hasPermission('molding_sample:edit_draft') && canManageSelectedOrderFactory.value)
const canDeleteDraftOrder = computed(() => authStore.hasPermission('molding_sample:delete_draft') && canManageSelectedOrderFactory.value)
const isEditingRejectedOrder = computed(() => editingRejectedOrderId.value !== '')
const editingRevisionOrderLabel = computed(() => selectedOrder.value.status === '已撤回' ? '撤回单' : '驳回单')
const canSubmitCreateForm = computed(() => isEditingRejectedOrder.value ? canEditDraftOrder.value : canCreateOrder.value)
const canExportSelectedOrder = computed(() =>
  batchActionRecords.value.length > 0
  && apiState.value === 'connected'
  && batchActionRecords.value.every((target) =>
    apiRecords.value.some((record) => record.order.id === target.order.id),
  ),
)
const canEditSelectedRejectedOrder = computed(() =>
  Boolean(selectedRecord.value)
  && ['已驳回', '已撤回'].includes(selectedOrder.value.status)
  && canEditDraftOrder.value,
)
const canWithdrawSelectedOrder = computed(() =>
  Boolean(selectedRecord.value)
  && selectedOrder.value.status === '待审核'
  && canEditDraftOrder.value,
)
const canDeleteSelectedWithdrawnOrder = computed(() =>
  Boolean(selectedRecord.value)
  && selectedOrder.value.status === '已撤回'
  && canDeleteDraftOrder.value,
)
const canDeleteSelectedOrder = computed(() =>
  Boolean(selectedRecord.value)
  && canManageSelectedOrderFactory.value
  && (
    authStore.hasPermission('system:user_manage')
    || canDeleteSelectedWithdrawnOrder.value
  ),
)
const canApproveSelectedOrder = computed(() => {
  const actor = getApprovalActor()
  return Boolean(actor && canManageSelectedOrderFactory.value && authStore.hasPermission(actor.permission))
})

function normalizeBoardStatus(status: MoldingSampleStatus): MoldingSampleStatus {
  return status === '待经理审核' ? '待审核' : status
}

function toWorkflowRecord(record: MoldingSampleDetailResponse): MoldingSampleWorkflowRecord {
  const factoryId = isProductionFactoryContextId(record.order.factory_id)
    ? record.order.factory_id
    : selectedFactoryId.value

  return {
    factory_id: factoryId,
    order: {
      ...record.order,
      factory_id: factoryId,
    },
    items: record.items,
    audit_logs: record.audit_logs,
    requisitions: [],
    problems: record.problems ?? [],
  }
}

function createEmptySelectedOrder(): MoldingSampleOrder {
  return {
    id: '',
    factory_id: selectedFactoryId.value,
    order_number: '',
    doc_number: '',
    product_name: '',
    client_name: '',
    date: '',
    stage: '',
    order_type: '啤办',
    workshop: '华登车间',
    send_to: '',
    supervisor: '',
    eng_name: '',
    reason: '',
    status: '待审核',
    reject_reason: '',
    completed_date: '',
    created_at: '',
    updated_at: '',
  }
}

function createEmptyCreateDraft() {
  return createManualMoldingSampleOrderDraft({
    factory_id: selectedFactoryId.value,
    order_date: today,
    stage: 'T0',
    order_type: '啤办',
    workshop: '工程部',
    send_to: '内部',
    supervisor: '',
    eng_name: '',
    items: [
      createManualMoldingSampleLineDraft(),
    ],
  })
}

function canUseLocalStorage() {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined'
}

function createDraftStorageKey(factoryId = selectedFactoryId.value) {
  return `${createDraftStoragePrefix}:${factoryId}`
}

function clearSavedCreateDraft(factoryId = selectedFactoryId.value) {
  if (!canUseLocalStorage()) {
    return
  }

  window.localStorage.removeItem(createDraftStorageKey(factoryId))
}

function hasDraftText(value: unknown) {
  return String(value ?? '').trim() !== ''
}

function isBlankCreateLine(line: ManualMoldingSampleLineDraft) {
  return Object.values(line).every((value) => !hasDraftText(value))
}

function isBlankCreateDraft(draft: ManualMoldingSampleOrderDraft) {
  const hasHeaderValue = [
    draft.id,
    draft.product_no,
    draft.doc_number,
    draft.client_name,
    draft.product_name,
    draft.supervisor,
    draft.eng_name,
    draft.reason,
  ].some(hasDraftText)
  const hasChangedDefault = draft.order_date !== today
    || draft.stage !== 'T0'
    || draft.order_type !== '啤办'
    || draft.workshop !== '工程部'
    || draft.send_to !== '内部'
  const hasLineValue = draft.items.some((line) => !isBlankCreateLine(line))

  return !hasHeaderValue && !hasChangedDefault && !hasLineValue
}

function normalizeSavedCreateDraft(saved: Partial<ManualMoldingSampleOrderDraft>) {
  const savedItems = Array.isArray(saved.items) && saved.items.length > 0
    ? saved.items.map((item) => createManualMoldingSampleLineDraft(item as Partial<ManualMoldingSampleLineDraft>))
    : [createManualMoldingSampleLineDraft()]

  return createManualMoldingSampleOrderDraft({
    ...saved,
    factory_id: selectedFactoryId.value,
    items: savedItems,
  })
}

function persistCreateDraft() {
  if (isEditingRejectedOrder.value || !canUseLocalStorage()) {
    return
  }

  if (isBlankCreateDraft(createDraft.value)) {
    clearSavedCreateDraft()
    return
  }

  window.localStorage.setItem(
    createDraftStorageKey(),
    JSON.stringify({
      ...createDraft.value,
      factory_id: selectedFactoryId.value,
    }),
  )
}

function restoreSavedCreateDraft() {
  if (!canUseLocalStorage()) {
    createDraft.value = createEmptyCreateDraft()
    createErrors.value = []
    return
  }

  const savedDraft = window.localStorage.getItem(createDraftStorageKey())

  if (!savedDraft) {
    createDraft.value = createEmptyCreateDraft()
    createErrors.value = []
    return
  }

  try {
    createDraft.value = normalizeSavedCreateDraft(JSON.parse(savedDraft) as Partial<ManualMoldingSampleOrderDraft>)
  }
  catch {
    clearSavedCreateDraft()
    createDraft.value = createEmptyCreateDraft()
  }

  createErrors.value = []
}

function resetCreateDraft() {
  editingRejectedOrderId.value = ''
  createDraft.value = createEmptyCreateDraft()
  createErrors.value = []
}

function resetCurrentCreateDraft() {
  if (!isEditingRejectedOrder.value) {
    clearSavedCreateDraft()
    resetCreateDraft()
    actionMessage.value = '已重置新建啤办单草稿。'
    return
  }

  const record = factoryRecords.value.find((entry) => entry.order.id === editingRejectedOrderId.value)
  if (!record) {
    actionMessage.value = '未找到当前驳回单，已返回详情。'
    cancelRejectedEdit()
    return
  }

  createDraft.value = createDraftFromRecord(record)
  createErrors.value = []
  actionMessage.value = `已恢复驳回单 ${record.order.id} 的原始修改内容。`
}

function createDraftFromRecord(record: MoldingSampleWorkflowRecord) {
  return createManualMoldingSampleOrderDraft({
    id: record.order.id,
    factory_id: record.factory_id,
    product_no: record.order.order_number,
    doc_number: record.order.doc_number,
    client_name: record.order.client_name,
    product_name: record.order.product_name,
    order_date: record.order.date,
    stage: record.order.stage,
    order_type: record.order.order_type,
    workshop: record.order.workshop,
    send_to: record.order.send_to || '内部',
    supervisor: record.order.supervisor,
    eng_name: record.order.eng_name,
    reason: record.order.reason,
    items: record.items.map((item) => {
      const colorParts = splitColorPms(item.color)

      return createManualMoldingSampleLineDraft({
        customer_mold_id: item.mold_id,
        mold_name: item.mold_name,
        material: item.material,
        color: colorParts.color,
        pms: colorParts.pms,
        pigment_no: item.pigment_no,
        quantity: item.quantity,
        shoot_qty: String(item.shoot_qty || ''),
        gross_weight_g: formatDraftNumber(item.gross_weight_g),
        required_material_kg: formatDraftNumber(item.required_material_kg),
        mold_dimensions: item.mold_dimensions,
        machine_type: item.machine_type,
        mold_presence_status: normalizeDraftMoldPresenceStatus(item.mold_presence_status),
        mold_return_time: item.mold_return_time,
        required_date: item.completion_time,
        notes: item.notes,
      })
    }),
  })
}

function createDraftFromExcelPreview(payload: MoldingSampleCreateRequest) {
  const order = payload.order
  const items = payload.items.length
    ? payload.items.map((item) => {
        const colorParts = splitColorPms(item.color ?? '')

        return createManualMoldingSampleLineDraft({
          customer_mold_id: item.mold_id ?? '',
          mold_name: item.mold_name ?? '',
          material: item.material ?? '',
          color: colorParts.color,
          pms: colorParts.pms,
          pigment_no: item.pigment_no ?? '',
          quantity: item.quantity ?? '',
          shoot_qty: String(item.shoot_qty || ''),
          gross_weight_g: formatDraftNumber(item.gross_weight_g),
          required_material_kg: formatDraftNumber(item.required_material_kg),
          mold_dimensions: item.mold_dimensions ?? '',
          machine_type: item.machine_type ?? '',
          mold_presence_status: normalizeDraftMoldPresenceStatus(item.mold_presence_status),
          mold_return_time: item.mold_return_time ?? '',
          required_date: item.completion_time || '',
          notes: item.notes ?? '',
        })
      })
    : [createManualMoldingSampleLineDraft()]

  return createManualMoldingSampleOrderDraft({
    id: order.id,
    factory_id: order.factory_id || selectedFactoryId.value,
    product_no: order.order_number || order.id.replace(/^BP-/, ''),
    doc_number: order.doc_number ?? '',
    client_name: order.client_name,
    product_name: order.product_name,
    order_date: order.date,
    stage: order.stage ?? 'T0',
    order_type: order.order_type ?? '啤办',
    workshop: order.workshop || '工程部',
    send_to: order.send_to || '内部',
    supervisor: order.supervisor,
    eng_name: order.eng_name,
    reason: order.reason ?? '',
    items,
  })
}

function formatDraftNumber(value: number | null | undefined) {
  return value === null || value === undefined ? '' : String(value)
}

function normalizeDraftMoldPresenceStatus(value: unknown): '' | 'in_factory' | 'out_of_factory' {
  return value === 'in_factory' || value === 'out_of_factory' ? value : ''
}

function splitColorPms(value: string) {
  const parts = value.split('/').map((part) => part.trim()).filter(Boolean)
  const pmsIndex = parts.findIndex((part) => /^PMS\s+/i.test(part))

  if (pmsIndex === -1) {
    return { color: value, pms: '' }
  }

  const pms = parts[pmsIndex].replace(/^PMS\s*/i, '').trim()
  const color = parts.filter((_, index) => index !== pmsIndex).join(' / ')

  return { color, pms }
}

function startCreateOrder() {
  if (!canManageSelectedFactory.value) {
    actionMessage.value = '当前厂区为只读，仅可查看数据。'
    return
  }

  editingRejectedOrderId.value = ''
  restoreSavedCreateDraft()
  activeView.value = 'create'
}

function startRejectedEdit() {
  if (!selectedRecord.value) {
    actionMessage.value = '请先选择一张正式啤办单。'
    return
  }

  if (!canEditSelectedRejectedOrder.value) {
    actionMessage.value = `当前账号没有编辑${editingRevisionOrderLabel.value}权限。`
    return
  }

  editingRejectedOrderId.value = selectedOrder.value.id
  createDraft.value = createDraftFromRecord(selectedRecord.value)
  createErrors.value = []
  activeView.value = 'create'
  actionMessage.value = `已载入${editingRevisionOrderLabel.value} ${selectedOrder.value.id}，修改后可重新提交主管审核。`
}

function cancelRejectedEdit() {
  const orderId = editingRejectedOrderId.value

  editingRejectedOrderId.value = ''
  createErrors.value = []
  selectedOrderId.value = orderId || selectedOrderId.value
  activeView.value = orderId ? 'detail' : 'overview'
}

function replaceApiRecord(record: MoldingSampleDetailResponse) {
  const exists = apiRecords.value.some((entry) => entry.order.id === record.order.id)

  apiRecords.value = exists
    ? apiRecords.value.map((entry) => entry.order.id === record.order.id ? record : entry)
    : [record, ...apiRecords.value]
  apiState.value = 'connected'
}

function removeApiRecord(orderId: string) {
  apiRecords.value = apiRecords.value.filter((entry) => entry.order.id !== orderId)
  const nextFactoryRecord = factoryRecords.value.find((record) => record.order.id !== orderId)
  selectedOrderId.value = nextFactoryRecord?.order.id ?? ''
  apiState.value = apiRecords.value.length ? 'connected' : 'empty'
}

async function loadApiData() {
  apiState.value = 'checking'
  actionMessage.value = '正在读取正式啤办单列表...'

  try {
    const records = await moldingSampleApi.listOrders()
    apiRecords.value = records
    apiState.value = records.length ? 'connected' : 'empty'
    actionMessage.value = records.length
      ? `已读取正式啤办单 ${records.length} 张。`
      : '后端暂无正式啤办单，可先新建啤办单。'

    const factoryRecord = records.find((record) => record.order.factory_id === selectedFactoryId.value)
    if (!selectedOrderId.value && factoryRecord) {
      selectedOrderId.value = factoryRecord.order.id
    }
  }
  catch (error) {
    apiRecords.value = []
    apiState.value = 'error'
    actionMessage.value = `正式数据读取失败：${getApiErrorMessage(error)}。不会显示本地示例单据。`
  }
}

async function loadMaterialPricing() {
  try {
    const pricing = await moldingSampleApi.getMaterialPrices()
    currentRmbToHkdRate.value = pricing.rmb_to_hkd_rate
  }
  catch {
    currentRmbToHkdRate.value = null
  }
}

function triggerExcelImport() {
  if (!canCreateOrder.value) {
    actionMessage.value = '当前账号没有从Excel导入啤办单权限。'
    return
  }

  excelFileInput.value?.click()
}

function readWorkbookAsArrayBuffer(file: File) {
  return file.arrayBuffer()
}

async function handleExcelImportFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]

  if (!file) {
    return
  }

  if (!file.name.toLowerCase().endsWith('.xlsx')) {
    actionMessage.value = '导入失败：请选择 .xlsx 格式的啤办单文件。'
    input.value = ''
    return
  }

  excelImporting.value = true
  actionMessage.value = `正在导入Excel文件 ${file.name}...`

  try {
    const workbook = await readWorkbookAsArrayBuffer(file)
    const preview = await moldingSampleApi.previewOrderExcel(workbook, {
      factory_id: selectedFactoryId.value,
    })
    editingRejectedOrderId.value = ''
    createDraft.value = createDraftFromExcelPreview(preview)
    createErrors.value = []
    selectedOrderId.value = ''
    activeView.value = 'create'
    actionMessage.value = 'Excel已导入到新建开单草稿，请确认数据无误后提交主管审核。'
  }
  catch (error) {
    actionMessage.value = `Excel导入失败：${getApiErrorMessage(error)}`
  }
  finally {
    excelImporting.value = false
    input.value = ''
  }
}

function isOrderBatchSelected(orderId: string) {
  return selectedBatchOrderIdSet.value.has(orderId)
}

function setOrderBatchSelection(orderId: string, checked: boolean) {
  selectedBatchOrderIds.value = checked
    ? Array.from(new Set([...selectedBatchOrderIds.value, orderId]))
    : selectedBatchOrderIds.value.filter((selectedId) => selectedId !== orderId)
}

function toggleOrderBatchSelection(orderId: string, event: Event) {
  setOrderBatchSelection(orderId, (event.target as HTMLInputElement).checked)
}

function selectAllVisibleOrders() {
  selectedBatchOrderIds.value = visibleRecords.value.map((record) => record.order.id)
}

function clearBatchSelection() {
  selectedBatchOrderIds.value = []
}

async function downloadOrderExcel() {
  if (!canExportSelectedOrder.value) {
    actionMessage.value = '请先勾选或选择已从后端读取到的正式啤办单，再导出Excel。'
    return
  }

  const records = batchActionRecords.value
  excelExporting.value = true
  actionMessage.value = records.length === 1
    ? `正在导出啤办单 ${records[0].order.id} 的Excel文件...`
    : `正在合并导出 ${records.length} 张啤办单的Excel文件...`

  try {
    const orderIds = records.map((record) => record.order.id)
    const workbook = await moldingSampleApi.exportOrdersExcel(orderIds)
    const filename = records.length === 1
      ? `${records[0].order.id}-molding-sample.xlsx`
      : `molding-sample-${records.length}-orders.xlsx`
    saveWorkbookAsExcel(workbook, filename)

    actionMessage.value = records.length === 1
      ? `啤办单 ${records[0].order.id} 的Excel文件已开始下载。`
      : `已导出 ${records.length} 张啤办单到一个Excel文件。`
  }
  catch (error) {
    actionMessage.value = `Excel导出失败：${getApiErrorMessage(error)}`
  }
  finally {
    excelExporting.value = false
  }
}

async function printOverview() {
  const records = batchActionRecords.value

  if (!records.length) {
    printPreviewVisible.value = false
    actionMessage.value = '请先勾选或选择已从后端读取到的正式啤办单，再打印。'
    return
  }

  printableRecords.value = records
  printPreviewVisible.value = true
  actionMessage.value = records.length === 1
    ? `已打开啤办单 ${records[0].order.id} 的打印预览。`
    : `已打开 ${records.length} 张啤办单的打印预览。`
  await nextTick()
}

async function confirmPrintOverview() {
  if (!printableRecords.value.length) {
    printPreviewVisible.value = false
    actionMessage.value = '请先勾选或选择已从后端读取到的正式啤办单，再打印。'
    return
  }

  actionMessage.value = printableRecords.value.length === 1
    ? `正在打印啤办单 ${printableRecords.value[0].order.id} 的详细内容。`
    : `正在打印 ${printableRecords.value.length} 张啤办单的详细内容。`
  await nextTick()
  window.print()
}

function closePrintPreview() {
  printPreviewVisible.value = false
}

function saveWorkbookAsExcel(workbook: ArrayBuffer, filename: string) {
  const blob = new Blob([workbook], { type: MOLDING_SAMPLE_XLSX_MIME })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')

  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function readQueryString(value: unknown) {
  if (typeof value === 'string') {
    return value.trim()
  }
  if (Array.isArray(value) && typeof value[0] === 'string') {
    return value[0].trim()
  }

  return ''
}

function setView(view: ViewKey) {
  activeView.value = view
  deleteConfirmingOrderId.value = ''
}

function openRecord(record: MoldingSampleWorkflowRecord) {
  selectedOrderId.value = record.order.id
  activeView.value = 'detail'
  approvalNote.value = ''
  deleteConfirmingOrderId.value = ''
}

function readInputValue(event: Event) {
  return (event.target as HTMLInputElement).value
}

function updateCreateProductNo(value: string) {
  const previousDerivedId = deriveManualMoldingSampleOrderId(createDraft.value.product_no)

  createDraft.value.product_no = value

  if (!createDraft.value.id || createDraft.value.id === previousDerivedId) {
    createDraft.value.id = deriveManualMoldingSampleOrderId(value)
  }
}

function addCreateLine() {
  createDraft.value.items.push(createManualMoldingSampleLineDraft())
}

function removeCreateLine(index: number) {
  resetRawMaterialPickerState()

  if (createDraft.value.items.length <= 1) {
    createDraft.value.items = [createManualMoldingSampleLineDraft()]
    return
  }

  createDraft.value.items.splice(index, 1)
}

function hideCreateSuccessToast() {
  if (createSuccessToastTimer) {
    clearTimeout(createSuccessToastTimer)
    createSuccessToastTimer = null
  }

  createSuccessToast.value = null
}

function clearActionToastTimer() {
  if (actionToastTimer) {
    clearTimeout(actionToastTimer)
    actionToastTimer = null
  }
}

function hideActionToast() {
  clearActionToastTimer()
  actionToastVisible.value = false
}

function getActionToastDuration(message: string) {
  if (/正在/.test(message)) {
    return 0
  }

  if (/失败|错误|未提交|不能|没有|请选择|缺失/.test(message)) {
    return 6500
  }

  return 4200
}

function showActionToast(message = actionMessage.value) {
  clearActionToastTimer()
  actionToastVisible.value = Boolean(message)

  const duration = getActionToastDuration(message)
  if (duration > 0) {
    actionToastTimer = setTimeout(() => {
      actionToastVisible.value = false
      actionToastTimer = null
    }, duration)
  }
}

function showCreateSuccessToast(orderId: string) {
  hideCreateSuccessToast()
  createSuccessToast.value = {
    orderId,
    detail: '已提交主管审核，正式列表已刷新。',
  }
  createSuccessToastTimer = setTimeout(() => {
    createSuccessToast.value = null
    createSuccessToastTimer = null
  }, 3200)
}

async function submitManualCreate() {
  if (!canSubmitCreateForm.value) {
    actionMessage.value = isSelectedFactoryReadOnly.value
      ? '当前厂区为只读，仅可查看数据。'
      : isEditingRejectedOrder.value
      ? '当前账号没有编辑驳回单权限。'
      : '当前账号没有新建啤办单权限。'
    return
  }

  createDraft.value.factory_id = selectedFactoryId.value
  createErrors.value = []
  const result = buildManualMoldingSampleCreateRequest(createDraft.value, selectedFactoryId.value)
  const revisionLabel = editingRevisionOrderLabel.value

  if (!result.payload) {
    createErrors.value = result.errors
    actionMessage.value = `${isEditingRejectedOrder.value ? `${revisionLabel}重提` : '新建啤办单'}未提交：${result.errors[0] ?? '请检查表单'}`
    return
  }

  createSubmitting.value = true
  const isRejectedResubmit = isEditingRejectedOrder.value
  actionMessage.value = isRejectedResubmit ? `正在保存${revisionLabel}修改并重提啤办单...` : '正在提交新建啤办单...'

  try {
    const created = isRejectedResubmit
      ? await resubmitRejectedOrder(result.payload)
      : await moldingSampleApi.createOrder(result.payload)

    replaceApiRecord(created)
    selectedOrderId.value = created.order.id
    activeView.value = 'detail'
    actionMessage.value = isRejectedResubmit
      ? `啤办单 ${created.order.id} 已保存${revisionLabel}修改并重提主管审核。`
      : `啤办单 ${created.order.id} 已提交主管审核，正式列表已刷新。`
    if (!isRejectedResubmit) {
      clearSavedCreateDraft()
      showCreateSuccessToast(created.order.id)
    }
    resetCreateDraft()
  }
  catch (error) {
    actionMessage.value = `${isEditingRejectedOrder.value ? `${revisionLabel}重提` : '新建啤办单'}提交失败：${getApiErrorMessage(error)}`
  }
  finally {
    createSubmitting.value = false
  }
}

async function resubmitRejectedOrder(payload: NonNullable<ReturnType<typeof buildManualMoldingSampleCreateRequest>['payload']>) {
  const orderId = editingRejectedOrderId.value
  if (!orderId || payload.order.id !== orderId) {
    throw new Error('驳回单编号不能修改，请保持原单号后重提。')
  }

  await moldingSampleApi.editOrder(orderId, payload)

  return moldingSampleApi.updateStatus(orderId, {
    action: '工程重提',
    reason: `${authStore.currentUser?.display_name ?? '工程部'}修改后重提。`,
    today,
  })
}

function getApprovalActor(): ApprovalActor | null {
  if (!selectedRecord.value) {
    return null
  }

  if (selectedOrder.value.status === '待审核') {
    return {
      passAction: '主管通过',
      rejectAction: '主管驳回',
      actorName: selectedOrder.value.supervisor,
      permission: 'molding_sample:supervisor_review',
    }
  }

  if (selectedOrder.value.status === '待经理审核') {
    return {
      passAction: '经理通过',
      rejectAction: '经理驳回',
      actorName: '经理审核',
      permission: 'molding_sample:manager_review',
    }
  }

  return null
}

async function runApprovalTransition(decision: '通过' | '驳回') {
  const actor = getApprovalActor()

  if (!actor) {
    actionMessage.value = '当前单据不在审核节点，不能执行审核动作。'
    return
  }

  if (!canManageSelectedOrderFactory.value) {
    actionMessage.value = '当前厂区为只读，仅可查看数据。'
    return
  }

  const reason = approvalNote.value.trim()
  if (decision === '驳回' && !reason) {
    actionMessage.value = '驳回必须填写审核意见。'
    return
  }

  approvalSubmitting.value = true
  actionMessage.value = `正在提交${decision}结果...`

  const payload: MoldingSampleStatusRequest = {
    action: decision === '通过' ? actor.passAction : actor.rejectAction,
    reason: reason || `${authStore.currentUser?.display_name ?? actor.actorName}${decision}`,
    today,
  }

  try {
    const updated = await moldingSampleApi.updateStatus(selectedOrder.value.id, payload)
    replaceApiRecord(updated)
    selectedOrderId.value = updated.order.id
    approvalNote.value = ''
    actionMessage.value = `啤办单 ${updated.order.id} 已${decision}，当前状态：${updated.order.status}。`
  }
  catch (error) {
    actionMessage.value = `审核${decision}失败：${getApiErrorMessage(error)}`
  }
  finally {
    approvalSubmitting.value = false
  }
}

async function withdrawSelectedOrder() {
  if (!selectedRecord.value) {
    actionMessage.value = '请先选择一张正式啤办单。'
    return
  }

  if (!canWithdrawSelectedOrder.value) {
    actionMessage.value = !canManageSelectedOrderFactory.value
      ? '当前厂区为只读，仅可查看数据。'
      : '只有开单工程师可以撤回待审核单。'
    return
  }

  const actorName = (authStore.currentUser?.display_name ?? selectedOrder.value.eng_name) || '工程部'
  withdrawSubmitting.value = true
  actionMessage.value = '正在撤回主管审核...'

  try {
    const updated = await moldingSampleApi.updateStatus(selectedOrder.value.id, {
      action: '工程撤回',
      reason: `${actorName}撤回主管审核。`,
      today,
    })
    replaceApiRecord(updated)
    selectedOrderId.value = updated.order.id
    actionMessage.value = `啤办单 ${updated.order.id} 已撤回，可修改后重新提交主管审核。`
  }
  catch (error) {
    actionMessage.value = `撤回主管审核失败：${getApiErrorMessage(error)}`
  }
  finally {
    withdrawSubmitting.value = false
  }
}

async function deleteSelectedOrder() {
  if (!selectedRecord.value) {
    actionMessage.value = '请先选择一张正式啤办单。'
    return
  }

  if (!canDeleteSelectedOrder.value) {
    actionMessage.value = !canManageSelectedOrderFactory.value
      ? '当前厂区为只读，仅可查看数据。'
      : '只有管理员或可删草稿的工程账号可以删除当前啤办单。'
    return
  }

  const orderId = selectedOrder.value.id
  if (deleteConfirmingOrderId.value !== orderId) {
    deleteConfirmingOrderId.value = orderId
    actionMessage.value = `再次点击确认删除啤办单 ${orderId}。`
    return
  }

  deleteSubmitting.value = true
  actionMessage.value = `正在删除啤办单 ${orderId}...`

  try {
    await moldingSampleApi.deleteOrder(orderId)
    removeApiRecord(orderId)
    activeView.value = 'overview'
    deleteConfirmingOrderId.value = ''
    actionMessage.value = `啤办单 ${orderId} 已删除。`
  }
  catch (error) {
    actionMessage.value = `删除啤办单失败：${getApiErrorMessage(error)}`
  }
  finally {
    deleteSubmitting.value = false
  }
}

function getStatusColumnDetail(status: MoldingSampleStatus) {
  const details: Record<MoldingSampleStatus, string> = {
    待审核: '等待主管处理',
    待经理审核: '历史经理节点',
    待生产: '已通知啤机部',
    生产中: '啤机部执行中',
    已完成: '完成后归档',
    已驳回: '退回工程处理',
    已撤回: '工程主动撤回',
  }

  return details[status]
}

function getWorkflowStepState(status: MoldingSampleStatus): StatusState {
  if (selectedOrder.value.status === '已驳回' || selectedOrder.value.status === '已撤回') {
    return status === '待审核' ? 'rejected' : 'pending'
  }

  const currentIndex = workflowSteps.findIndex((step) => step.status === normalizeBoardStatus(selectedOrder.value.status))
  const stepIndex = workflowSteps.findIndex((step) => step.status === status)

  if (stepIndex < currentIndex) {
    return 'done'
  }
  if (stepIndex === currentIndex) {
    return 'current'
  }

  return 'pending'
}

function getWorkflowCardClass(state: StatusState) {
  const classes: Record<StatusState, string> = {
    done: 'border-teal-200 bg-teal-50 text-teal-800',
    current: 'border-slate-950 bg-slate-950 text-white',
    pending: 'border-slate-200 bg-white text-slate-500',
    rejected: 'border-red-200 bg-red-50 text-red-700',
  }

  return classes[state]
}

function getWorkflowIndexClass(state: StatusState) {
  const classes: Record<StatusState, string> = {
    done: 'bg-teal-600 text-white',
    current: 'bg-white text-slate-950',
    pending: 'bg-slate-200 text-slate-500',
    rejected: 'bg-red-600 text-white',
  }

  return classes[state]
}

function getFlowSummary(record: MoldingSampleWorkflowRecord) {
  if (record.order.status === '待审核') {
    return `${record.order.eng_name} → ${record.order.supervisor}`
  }
  if (record.order.status === '待经理审核') {
    return `${record.order.supervisor} 已通过 · 历史经理节点`
  }
  if (record.order.status === '待生产') {
    return '等待啤机部开始处理'
  }
  if (record.order.status === '生产中') {
    const missingCount = buildCompletionGate(record.order, record.items).missing_item_ids.length
    return missingCount ? `待回填 ${missingCount} 项实际用料` : '生产数据已补齐'
  }
  if (record.order.status === '已完成') {
    return record.order.completed_date ? `${record.order.completed_date} 完成` : '已完成'
  }

  if (record.order.status === '已撤回') {
    return '工程已撤回，待修改重提'
  }

  return record.order.reject_reason || '退回工程处理'
}

function getPageCount(total: number) {
  return Math.max(1, Math.ceil(total / MOLDING_SAMPLE_PAGE_SIZE))
}

function clampPage(page: number, total: number) {
  return Math.min(Math.max(1, page), getPageCount(total))
}

function createPaginationState<T>(rows: T[], page: number): PaginationState<T> {
  const total = rows.length
  const pageCount = getPageCount(total)
  const normalizedPage = clampPage(page, total)
  const startIndex = (normalizedPage - 1) * MOLDING_SAMPLE_PAGE_SIZE
  const pageRows = rows.slice(startIndex, startIndex + MOLDING_SAMPLE_PAGE_SIZE)
  const start = total === 0 ? 0 : startIndex + 1
  const end = total === 0 ? 0 : startIndex + pageRows.length

  return {
    rows: pageRows,
    total,
    page: normalizedPage,
    pageCount,
    start,
    end,
    hasPrevious: normalizedPage > 1,
    hasNext: normalizedPage < pageCount,
  }
}

function formatPaginationRange<T>(pagination: PaginationState<T>) {
  return pagination.total === 0
    ? '0 / 0 条'
    : `${pagination.start}-${pagination.end} / ${pagination.total} 条`
}

function resetPagination() {
  overviewListPage.value = 1
  boardPageByStatus.value = {}
  materialBalancePeriodPage.value = 1
  materialBalanceDetailPage.value = 1
}

function setOverviewListPage(page: number) {
  overviewListPage.value = clampPage(page, visibleRecords.value.length)
}

function setBoardColumnPage(status: MoldingSampleStatus, page: number) {
  const total = visibleRecords.value.filter((record) => normalizeBoardStatus(record.order.status) === status).length
  boardPageByStatus.value = {
    ...boardPageByStatus.value,
    [status]: clampPage(page, total),
  }
}

function setMaterialBalancePeriodPage(page: number) {
  materialBalancePeriodPage.value = clampPage(page, materialBalancePeriodRows.value.length)
}

function setMaterialBalanceDetailPage(page: number) {
  materialBalanceDetailPage.value = clampPage(page, materialBalanceRows.value.length)
}

function formatBlank(value: string | number | null | undefined, fallback = '待填写') {
  return value === null || value === undefined || value === '' ? fallback : String(value)
}

function formatMoldPresenceStatus(value: string | undefined) {
  return value === 'in_factory' ? '在厂' : value === 'out_of_factory' ? '不在厂' : '待确认'
}

function formatWeight(value: number | null | undefined) {
  return value === null || value === undefined ? '待填写' : `${value.toFixed(2)} kg`
}

function formatGram(value: number | null | undefined) {
  return value === null || value === undefined ? '待填写' : `${value.toFixed(2)} g`
}

function formatMoney(value: number | null | undefined, currency = 'HKD') {
  return value === null || value === undefined ? '待计算' : `${currency} ${value.toFixed(2)}`
}

function formatExchangeRate(value: number | null | undefined) {
  const rate = value ?? currentRmbToHkdRate.value

  if (rate === null || rate === undefined || !Number.isFinite(rate)) {
    return '待读取'
  }

  return rate.toFixed(4).replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '')
}

function getExchangeRateLabel(item: Pick<MoldingSampleItem, 'exchange_rate_at_save'>) {
  return item.exchange_rate_at_save === null || item.exchange_rate_at_save === undefined
    ? '当前汇率(RMB→HKD)'
    : '保存汇率(RMB→HKD)'
}

function readMaterialWeight(value: number | null | undefined) {
  const parsed = Number(value)

  return Number.isFinite(parsed) ? parsed : 0
}

function roundMaterialWeight(value: number) {
  return Math.round(value * 100) / 100
}

function hasUnknownRawMaterialValue(value: string) {
  return value !== '' && !rawMaterialOptionValueSet.value.has(value)
}

function resetRawMaterialPickerState() {
  activeRawMaterialPickerLineIndex.value = null
  rawMaterialSearchByLine.value = {}
  rawMaterialPickerPositionByLine.value = {}
}

function getRawMaterialListboxId(index: number) {
  return `raw-material-options-${index}`
}

function getRawMaterialPickerText(index: number, selectedValue: string) {
  if (activeRawMaterialPickerLineIndex.value === index) {
    return rawMaterialSearchByLine.value[index] ?? selectedValue
  }

  return selectedValue
}

function getRawMaterialOptionTitle(value: string) {
  return rawMaterialOptionByValue.value.get(value)?.label ?? value
}

function updateRawMaterialPickerPosition(index: number, target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) {
    return
  }

  const rect = target.getBoundingClientRect()
  const maxLeft = window.innerWidth - RAW_MATERIAL_PICKER_WIDTH - RAW_MATERIAL_PICKER_VIEWPORT_PADDING
  const left = Math.min(
    Math.max(RAW_MATERIAL_PICKER_VIEWPORT_PADDING, rect.left),
    Math.max(RAW_MATERIAL_PICKER_VIEWPORT_PADDING, maxLeft),
  )
  const top = Math.max(
    RAW_MATERIAL_PICKER_VIEWPORT_PADDING,
    rect.top - RAW_MATERIAL_PICKER_HEIGHT - RAW_MATERIAL_PICKER_GAP,
  )

  rawMaterialPickerPositionByLine.value = {
    ...rawMaterialPickerPositionByLine.value,
    [index]: {
      left,
      top,
      width: RAW_MATERIAL_PICKER_WIDTH,
    },
  }
}

function getRawMaterialPickerStyle(index: number) {
  const position = rawMaterialPickerPositionByLine.value[index]

  if (!position) {
    return {
      width: `${RAW_MATERIAL_PICKER_WIDTH}px`,
    }
  }

  return {
    left: `${position.left}px`,
    top: `${position.top}px`,
    width: `${position.width}px`,
  }
}

function openRawMaterialPicker(index: number, selectedValue: string, event: FocusEvent) {
  activeRawMaterialPickerLineIndex.value = index
  rawMaterialSearchByLine.value = {
    ...rawMaterialSearchByLine.value,
    [index]: selectedValue,
  }
  updateRawMaterialPickerPosition(index, event.currentTarget)
}

function closeRawMaterialPicker(index: number) {
  if (activeRawMaterialPickerLineIndex.value === index) {
    activeRawMaterialPickerLineIndex.value = null
  }

  const nextSearchByLine = { ...rawMaterialSearchByLine.value }
  delete nextSearchByLine[index]
  rawMaterialSearchByLine.value = nextSearchByLine

  const nextPositionByLine = { ...rawMaterialPickerPositionByLine.value }
  delete nextPositionByLine[index]
  rawMaterialPickerPositionByLine.value = nextPositionByLine
}

function handleRawMaterialPickerFocusOut(index: number, event: FocusEvent) {
  const currentTarget = event.currentTarget
  const nextTarget = event.relatedTarget

  if (
    currentTarget instanceof HTMLElement
    && nextTarget instanceof Node
    && currentTarget.contains(nextTarget)
  ) {
    return
  }

  closeRawMaterialPicker(index)
}

function updateRawMaterialSearch(index: number, event: Event) {
  const input = event.target as HTMLInputElement

  activeRawMaterialPickerLineIndex.value = index
  updateRawMaterialPickerPosition(index, event.currentTarget)
  rawMaterialSearchByLine.value = {
    ...rawMaterialSearchByLine.value,
    [index]: input.value,
  }
}

function getVisibleRawMaterialOptions(index: number) {
  const query = (rawMaterialSearchByLine.value[index] ?? '').trim().toLowerCase()
  const options = query
    ? rawMaterialOptions.value.filter((option) => option.searchText.includes(query))
    : rawMaterialOptions.value

  return options.slice(0, RAW_MATERIAL_PICKER_VISIBLE_LIMIT)
}

function selectRawMaterialOption(
  line: ManualMoldingSampleLineDraft,
  index: number,
  option: RawMaterialSelectOption,
) {
  line.material = option.value
  closeRawMaterialPicker(index)
}

function selectFirstRawMaterialOption(line: ManualMoldingSampleLineDraft, index: number) {
  const option = getVisibleRawMaterialOptions(index)[0]

  if (option) {
    selectRawMaterialOption(line, index, option)
    return
  }

  closeRawMaterialPicker(index)
}

function clearRawMaterialSelection(line: ManualMoldingSampleLineDraft, index: number) {
  line.material = ''
  rawMaterialSearchByLine.value = {
    ...rawMaterialSearchByLine.value,
    [index]: '',
  }
  activeRawMaterialPickerLineIndex.value = index
}

function buildMaterialBalanceItemRow(item: MoldingSampleItem): MaterialBalanceItemRow {
  const expectedWeightKg = readMaterialWeight(item.required_material_kg)
  const actualWeightKg = readMaterialWeight(item.actual_weight_kg)
  const balanceWeightKg = roundMaterialWeight(expectedWeightKg - actualWeightKg)
  const actualAmountHkd = item.actual_amount_hkd === null || item.actual_amount_hkd === undefined
    ? null
    : Number(item.actual_amount_hkd)
  const hasActualWeight = actualWeightKg > 0
  const hasKnownAmount = actualAmountHkd !== null && Number.isFinite(actualAmountHkd)
  const unitAmountHkd = hasActualWeight && hasKnownAmount ? actualAmountHkd / actualWeightKg : null
  const balanceAmountHkd = unitAmountHkd === null
    ? (balanceWeightKg === 0 ? 0 : null)
    : roundMoney(balanceWeightKg * unitAmountHkd)

  return {
    item,
    expectedWeightKg,
    actualWeightKg,
    balanceWeightKg,
    balanceAmountHkd,
    hasActualWeight,
  }
}

function buildMaterialBalanceOrderRow(record: MoldingSampleWorkflowRecord): MaterialBalanceOrderRow {
  const itemRows = record.items.map(buildMaterialBalanceItemRow)
  const unknownAmountCount = itemRows.filter((row) => row.balanceAmountHkd === null).length

  return {
    record,
    itemRows,
    expectedWeightKg: roundMaterialWeight(itemRows.reduce((sum, row) => sum + row.expectedWeightKg, 0)),
    actualWeightKg: roundMaterialWeight(itemRows.reduce((sum, row) => sum + row.actualWeightKg, 0)),
    balanceWeightKg: roundMaterialWeight(itemRows.reduce((sum, row) => sum + row.balanceWeightKg, 0)),
    balanceAmountHkd: unknownAmountCount > 0
      ? null
      : roundMoney(itemRows.reduce((sum, row) => sum + (row.balanceAmountHkd ?? 0), 0)),
    missingActualCount: itemRows.filter((row) => !row.hasActualWeight).length,
    unknownAmountCount,
  }
}

function buildMaterialBalancePeriodRows(
  rows: MaterialBalanceOrderRow[],
  periodMode: MaterialBalancePeriodMode,
): MaterialBalancePeriodRow[] {
  const groups = new Map<string, MaterialBalancePeriodRow>()

  for (const orderRow of rows) {
    const periodKey = getMaterialBalancePeriodKey(orderRow.record, periodMode)
    const existing = groups.get(periodKey.key)
    const group = existing ?? {
      ...periodKey,
      orderRows: [],
      orderCount: 0,
      expectedWeightKg: 0,
      actualWeightKg: 0,
      balanceWeightKg: 0,
      balanceAmountHkd: 0,
      missingActualCount: 0,
      unknownAmountCount: 0,
    }

    group.orderRows.push(orderRow)
    group.orderCount += 1
    group.expectedWeightKg = roundMaterialWeight(group.expectedWeightKg + orderRow.expectedWeightKg)
    group.actualWeightKg = roundMaterialWeight(group.actualWeightKg + orderRow.actualWeightKg)
    group.balanceWeightKg = roundMaterialWeight(group.balanceWeightKg + orderRow.balanceWeightKg)
    group.missingActualCount += orderRow.missingActualCount
    group.unknownAmountCount += orderRow.unknownAmountCount
    group.balanceAmountHkd = group.balanceAmountHkd === null || orderRow.balanceAmountHkd === null
      ? null
      : roundMoney(group.balanceAmountHkd + orderRow.balanceAmountHkd)

    groups.set(periodKey.key, group)
  }

  return Array.from(groups.values()).sort((a, b) => b.startDate.localeCompare(a.startDate))
}

function getMaterialBalancePeriodKey(
  record: MoldingSampleWorkflowRecord,
  materialBalancePeriodMode: MaterialBalancePeriodMode,
): MaterialBalancePeriodKey {
  const date = parseMaterialBalanceDate(readMaterialBalanceDate(record)) ?? parseMaterialBalanceDate(today)
  const safeDate = date ?? new Date(Date.UTC(2026, 6, 3))

  if (materialBalancePeriodMode === 'day') {
    const dayKey = formatMaterialBalanceDate(safeDate)

    return {
      key: `day:${dayKey}`,
      label: dayKey,
      detail: '日结余',
      startDate: dayKey,
      endDate: dayKey,
    }
  }

  if (materialBalancePeriodMode === 'week') {
    const weekStart = getWeekStartDate(safeDate)
    const weekEnd = addUtcDays(weekStart, 6)
    const startDate = formatMaterialBalanceDate(weekStart)
    const endDate = formatMaterialBalanceDate(weekEnd)

    return {
      key: `week:${startDate}`,
      label: `${startDate} ~ ${endDate}`,
      detail: '周结余',
      startDate,
      endDate,
    }
  }

  if (materialBalancePeriodMode === 'month') {
    const year = safeDate.getUTCFullYear()
    const month = safeDate.getUTCMonth()
    const start = new Date(Date.UTC(year, month, 1))
    const end = new Date(Date.UTC(year, month + 1, 0))
    const startDate = formatMaterialBalanceDate(start)
    const endDate = formatMaterialBalanceDate(end)
    const label = `${year}-${String(month + 1).padStart(2, '0')}`

    return {
      key: `month:${label}`,
      label,
      detail: '月结余',
      startDate,
      endDate,
    }
  }

  return getMaterialBalancePeriodKey(record, 'day')
}

function readMaterialBalanceDate(record: MoldingSampleWorkflowRecord) {
  return record.order.completed_date
    || record.order.date
    || record.order.updated_at
    || record.order.created_at
    || today
}

function parseMaterialBalanceDate(value: string) {
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})/)

  if (!match) {
    return null
  }

  return new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])))
}

function formatMaterialBalanceDate(date: Date) {
  return [
    date.getUTCFullYear(),
    String(date.getUTCMonth() + 1).padStart(2, '0'),
    String(date.getUTCDate()).padStart(2, '0'),
  ].join('-')
}

function getWeekStartDate(date: Date) {
  const weekday = date.getUTCDay() === 0 ? 7 : date.getUTCDay()

  return addUtcDays(date, 1 - weekday)
}

function addUtcDays(date: Date, days: number) {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate() + days))
}

function formatSignedWeight(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) {
    return '待填写'
  }

  const normalized = Number(value)
  const prefix = normalized > 0 ? '+' : normalized < 0 ? '-' : ''

  return `${prefix}${Math.abs(normalized).toFixed(2)} kg`
}

function formatSignedMoney(value: number | null | undefined, currency = 'HKD') {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) {
    return '待计算'
  }

  const normalized = Number(value)
  const prefix = normalized > 0 ? '+' : normalized < 0 ? '-' : ''

  return `${prefix}${currency} ${Math.abs(normalized).toFixed(2)}`
}

function getBalanceValueClass(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) {
    return 'text-slate-400'
  }
  if (Number(value) > 0) {
    return 'text-emerald-700'
  }
  if (Number(value) < 0) {
    return 'text-red-600'
  }

  return 'text-slate-500'
}

function getColorSwatchClass(color: string) {
  const normalized = color.toLowerCase()

  if (normalized.includes('绿')) {
    return 'bg-green-700'
  }
  if (normalized.includes('蓝')) {
    return 'bg-blue-800'
  }
  if (normalized.includes('黑')) {
    return 'bg-slate-900'
  }
  if (normalized.includes('白') || normalized.includes('透明')) {
    return 'bg-white'
  }
  if (normalized.includes('紫')) {
    return 'bg-violet-500'
  }
  if (normalized.includes('橙')) {
    return 'bg-orange-500'
  }

  return 'bg-slate-300'
}

function getStatusBadgeClass(status: MoldingSampleStatus) {
  return statusToneClasses[status]
}

function getItemState(item: MoldingSampleItem) {
  return Number(item.actual_weight_kg) > 0 ? '已回填' : '待回填'
}

function getItemStateClass(item: MoldingSampleItem) {
  return Number(item.actual_weight_kg) > 0
    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
    : 'border-amber-200 bg-amber-50 text-amber-700'
}

watchEffect(() => {
  const queryOrderId = readQueryString(route.query.order_id)

  if (queryOrderId && queryOrderId !== selectedOrderId.value) {
    selectedOrderId.value = queryOrderId
  }

  appStore.setActiveFactory(selectedFactoryId.value)
})

restoreSavedCreateDraft()

watch(createDraft, () => {
  if (activeView.value === 'create') {
    persistCreateDraft()
  }
}, { deep: true })

watch(selectedFactoryId, () => {
  resetPagination()

  if (!isEditingRejectedOrder.value) {
    restoreSavedCreateDraft()
  }
})

watch(selectedOrderId, () => {
  isSelectedOrderDataExpanded.value = false
})

watch(searchKeyword, () => {
  resetPagination()
})

watch(visibleRecords, (records) => {
  const visibleOrderIds = new Set(records.map((record) => record.order.id))
  selectedBatchOrderIds.value = selectedBatchOrderIds.value.filter((orderId) => visibleOrderIds.has(orderId))
})

watch(materialBalancePeriodMode, () => {
  materialBalancePeriodPage.value = 1
})

watch(actionMessage, (message) => {
  showActionToast(message)
}, { immediate: true })

onMounted(() => {
  void loadApiData()
  void loadMaterialPricing()
})

onUnmounted(() => {
  hideActionToast()
  hideCreateSuccessToast()
})
</script>

<template>
  <main class="min-h-screen bg-slate-100 text-[13px] leading-relaxed text-slate-900">
    <header class="sticky top-0 z-40 border-b border-slate-200 bg-white/95 backdrop-blur">
      <div class="mx-auto flex max-w-[1720px] items-center gap-4 px-5 py-2.5">
        <RouterLink
          to="/modules/engineering"
          class="inline-flex h-9 shrink-0 items-center gap-2 whitespace-nowrap rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-600 transition hover:border-slate-300 hover:text-slate-950"
        >
          <ArrowLeft class="size-4" aria-hidden="true" />
          <span class="hidden sm:inline">工程部模块</span>
          <span class="sm:hidden">工程部</span>
        </RouterLink>

        <div class="flex min-w-0 items-center gap-2.5">
          <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-900 text-white">
            <Beaker class="size-5" aria-hidden="true" />
          </span>
          <div class="min-w-0">
            <div class="truncate text-[15px] font-bold leading-tight">啤办单管理</div>
            <div class="truncate text-[11px] text-slate-400">Molding Sample · 试模 / 试色 / 啤办</div>
          </div>
        </div>

        <div class="relative ml-1 hidden md:block">
          <Search class="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
          <input
            v-model="searchKeyword"
            placeholder="搜索单号 / 产品 / 客户 / 模具号..."
            class="h-8 w-72 rounded-lg border border-slate-200 bg-slate-50 pl-8 pr-3 text-[12px] outline-none transition focus:border-slate-400 focus:bg-white"
          >
        </div>

        <div class="ml-auto flex items-center gap-3">
          <span class="hidden h-8 items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 text-[12px] font-medium text-slate-600 sm:inline-flex">
            <Building2 class="size-4" aria-hidden="true" />
            {{ activeFactory.shortName }}
          </span>
          <AccountMenu />
        </div>
      </div>

      <nav class="mx-auto flex max-w-[1720px] items-center gap-1 overflow-x-auto px-5">
        <button
          type="button"
          class="tab-btn inline-flex whitespace-nowrap items-center gap-1.5 rounded-t-lg border-b-2 border-transparent px-3 py-2 text-[12.5px] font-semibold transition hover:text-slate-900"
          :class="activeView === 'overview' ? 'bg-slate-900 text-white' : 'text-slate-500'"
          @click="setView('overview')"
        >
          <LayoutDashboard class="size-4" aria-hidden="true" />
          看板总览
        </button>
        <button
          type="button"
          class="tab-btn inline-flex whitespace-nowrap items-center gap-1.5 rounded-t-lg border-b-2 border-transparent px-3 py-2 text-[12.5px] font-semibold transition hover:text-slate-900"
          :class="activeView === 'create' ? 'bg-slate-900 text-white' : 'text-slate-500'"
          :disabled="!canManageSelectedFactory"
          @click="startCreateOrder"
        >
          <FilePlus2 class="size-4" aria-hidden="true" />
          工程部 · 新建开单
        </button>
        <button
          type="button"
          class="tab-btn inline-flex whitespace-nowrap items-center gap-1.5 rounded-t-lg border-b-2 border-transparent px-3 py-2 text-[12.5px] font-semibold transition hover:text-slate-900"
          :class="activeView === 'detail' ? 'bg-slate-900 text-white' : 'text-slate-500'"
          @click="setView('detail')"
        >
          <ClipboardCheck class="size-4" aria-hidden="true" />
          单据详情 · 审核
        </button>
        <RouterLink
          :to="productionTaskRoute"
          class="ml-auto inline-flex whitespace-nowrap items-center gap-1.5 rounded-t-lg px-3 py-2 text-[12.5px] font-semibold text-slate-500 transition hover:text-slate-900"
        >
          <Factory class="size-4" aria-hidden="true" />
          啤办生产任务单
          <ExternalLink class="size-3.5" aria-hidden="true" />
        </RouterLink>
      </nav>
    </header>

    <Transition
      appear
      mode="out-in"
      enter-active-class="transition duration-300 ease-out motion-reduce:transition-none"
      enter-from-class="-translate-y-4 scale-95 opacity-0"
      enter-to-class="translate-y-0 scale-100 opacity-100"
      leave-active-class="transition duration-200 ease-in motion-reduce:transition-none"
      leave-from-class="translate-y-0 scale-100 opacity-100"
      leave-to-class="-translate-y-3 scale-95 opacity-0"
    >
      <aside
        v-if="actionToastVisible && actionMessage"
        :key="actionMessage"
        class="fixed left-1/2 top-24 z-50 w-[min(520px,calc(100vw-2rem))] -translate-x-1/2 origin-top transform-gpu"
        role="status"
        aria-live="polite"
        aria-label="操作提示"
      >
        <div
          class="rounded-lg border px-3 py-2.5 shadow-xl backdrop-blur"
          :class="actionToastFrameClass"
        >
          <div class="flex items-start gap-2.5">
            <span
              class="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg"
              :class="actionToastIconClass"
            >
              <TriangleAlert v-if="actionToastTone === 'error'" class="size-4" aria-hidden="true" />
              <Clock v-else-if="actionToastTone === 'info'" class="size-4" aria-hidden="true" />
              <Check v-else class="size-4" aria-hidden="true" />
            </span>
            <p class="min-w-0 flex-1 text-[12.5px] font-semibold leading-6 text-slate-800">
              {{ actionMessage }}
            </p>
            <button
              type="button"
              class="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
              aria-label="关闭操作提示"
              @click="hideActionToast"
            >
              <X class="size-3.5" aria-hidden="true" />
            </button>
          </div>
        </div>
      </aside>
    </Transition>

    <Transition
      enter-active-class="transition duration-200 ease-out"
      enter-from-class="-translate-y-1.5 opacity-0"
      enter-to-class="translate-y-0 opacity-100"
      leave-active-class="transition duration-150 ease-in"
      leave-from-class="translate-y-0 opacity-100"
      leave-to-class="-translate-y-1.5 opacity-0"
    >
      <aside
        v-if="createSuccessToast"
        class="fixed right-5 top-20 z-50 w-[min(360px,calc(100vw-2.5rem))]"
        role="status"
        aria-live="polite"
      >
        <div class="rounded-lg border border-teal-200 bg-white/95 p-3 shadow-lg shadow-slate-200/70 backdrop-blur">
          <div class="flex items-start gap-2.5">
            <span class="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-teal-50 text-teal-700">
              <Check class="size-4" aria-hidden="true" />
            </span>
            <div class="min-w-0 flex-1">
              <div class="text-[13px] font-bold text-slate-950">新建成功</div>
              <p class="mt-0.5 text-[12px] leading-5 text-slate-500">
                啤办单 {{ createSuccessToast.orderId }} {{ createSuccessToast.detail }}
              </p>
            </div>
            <button
              type="button"
              class="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
              aria-label="关闭新建成功提示"
              @click="hideCreateSuccessToast"
            >
              <X class="size-3.5" aria-hidden="true" />
            </button>
          </div>
        </div>
      </aside>
    </Transition>

    <Transition
      enter-active-class="transition duration-200 ease-out"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition duration-150 ease-in"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <section
        v-if="printPreviewVisible"
        class="fixed inset-0 z-[60] bg-slate-950/45 px-4 py-5 backdrop-blur-sm"
        role="dialog"
        aria-modal="true"
        aria-label="啤办单打印预览"
        data-testid="molding-sample-print-preview"
      >
        <div class="mx-auto flex h-full max-w-6xl flex-col overflow-hidden rounded-lg bg-white shadow-2xl shadow-slate-950/30">
          <header class="flex shrink-0 items-center gap-3 border-b border-slate-200 px-4 py-3">
            <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-teal-50 text-teal-700">
              <Printer class="size-4" aria-hidden="true" />
            </span>
            <div class="min-w-0">
              <div class="text-[15px] font-bold text-slate-950">打印预览</div>
              <p class="mt-0.5 text-[12px] text-slate-500">
                {{ printableRecords.length }} 张单据 · {{ printPreviewItemCount }} 条模具明细
              </p>
            </div>
            <button
              type="button"
              class="ml-auto flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
              aria-label="关闭打印预览"
              @click="closePrintPreview"
            >
              <X class="size-4" aria-hidden="true" />
            </button>
          </header>

          <div class="min-h-0 flex-1 overflow-y-auto bg-slate-100 px-4 py-4">
            <div class="mx-auto space-y-4">
              <article
                v-for="record in printableRecords"
                :key="`preview-${record.order.id}`"
                class="rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
              >
                <div class="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 pb-3">
                  <div class="min-w-0">
                    <div class="flex flex-wrap items-center gap-2">
                      <span class="rounded-full bg-teal-50 px-2 py-0.5 text-[11px] font-bold text-teal-700">{{ record.order.status }}</span>
                      <strong class="font-mono text-[14px] text-slate-950">{{ record.order.id }}</strong>
                    </div>
                    <div class="mt-1 text-[13px] font-semibold text-slate-800">
                      {{ formatBlank(record.order.product_name) }} / {{ formatBlank(record.order.client_name) }}
                    </div>
                  </div>
                  <div class="rounded-md border border-slate-200 px-3 py-2 text-right">
                    <div class="text-[11px] text-slate-400">阶段 / 类型</div>
                    <div class="text-[12px] font-bold text-slate-700">{{ record.order.stage || '待填写' }} · {{ record.order.order_type }}</div>
                  </div>
                </div>

                <div class="mt-3 grid gap-2 text-[12px] sm:grid-cols-2 xl:grid-cols-4">
                  <div class="rounded-md bg-slate-50 px-3 py-2">
                    <span class="block text-[11px] text-slate-400">订单 / 文件编号</span>
                    <strong class="font-mono text-slate-800">{{ formatBlank(record.order.order_number) }} / {{ formatBlank(record.order.doc_number) }}</strong>
                  </div>
                  <div class="rounded-md bg-slate-50 px-3 py-2">
                    <span class="block text-[11px] text-slate-400">填写部 / 发至</span>
                    <strong class="text-slate-800">{{ formatBlank(record.order.workshop) }} / {{ formatBlank(record.order.send_to, '内部') }}</strong>
                  </div>
                  <div class="rounded-md bg-slate-50 px-3 py-2">
                    <span class="block text-[11px] text-slate-400">工程 / 主管</span>
                    <strong class="text-slate-800">{{ formatBlank(record.order.eng_name) }} / {{ formatBlank(record.order.supervisor) }}</strong>
                  </div>
                  <div class="rounded-md bg-slate-50 px-3 py-2">
                    <span class="block text-[11px] text-slate-400">开单 / 更新</span>
                    <strong class="text-slate-800">{{ formatBlank(record.order.date) }} / {{ formatBlank(record.order.updated_at) }}</strong>
                  </div>
                </div>

                <div class="mt-3 rounded-md border border-slate-200">
                  <div class="flex items-center justify-between border-b border-slate-100 bg-slate-50 px-3 py-2">
                    <span class="text-[12px] font-bold text-slate-700">模具明细</span>
                    <span class="text-[11px] font-semibold text-slate-400">共 {{ record.items.length }} 条</span>
                  </div>
                  <div v-if="!record.items.length" class="px-3 py-5 text-center text-[12px] font-medium text-slate-400">
                    暂无明细
                  </div>
                  <div v-else class="overflow-x-auto">
                    <table class="w-full min-w-[860px] text-[12px]">
                      <thead>
                        <tr class="border-b border-slate-100 text-[11px] text-slate-400">
                          <th class="px-3 py-2 text-left font-medium">模号 / 名称</th>
                          <th class="px-3 py-2 text-left font-medium">原料</th>
                          <th class="px-3 py-2 text-left font-medium">颜色 / PMS</th>
                          <th class="px-3 py-2 text-right font-medium">预计用料</th>
                          <th class="px-3 py-2 text-right font-medium">实际用料</th>
                          <th class="px-3 py-2 text-right font-medium">费用</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr
                          v-for="item in record.items"
                          :key="`preview-${item.id}`"
                          class="border-b border-slate-100 last:border-0"
                        >
                          <td class="px-3 py-2">
                            <strong class="block text-slate-800">{{ formatBlank(item.mold_id) }}</strong>
                            <span class="text-slate-500">{{ formatBlank(item.mold_name) }}</span>
                          </td>
                          <td class="px-3 py-2 text-slate-700">{{ formatBlank(item.material) }}</td>
                          <td class="px-3 py-2 text-slate-700">{{ formatBlank(item.color) }} / {{ formatBlank(item.pigment_no) }}</td>
                          <td class="px-3 py-2 text-right tabular-nums text-slate-700">{{ formatWeight(item.required_material_kg) }}</td>
                          <td class="px-3 py-2 text-right tabular-nums text-slate-700">{{ formatWeight(item.actual_weight_kg) }}</td>
                          <td class="px-3 py-2 text-right tabular-nums text-slate-700">{{ formatMoney(item.actual_amount_hkd) }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              </article>
            </div>
          </div>

          <footer class="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t border-slate-200 bg-white px-4 py-3">
            <div class="text-[12px] font-medium text-slate-500">打印内容将使用正式 A4 纸面样式。</div>
            <div class="flex items-center gap-2">
              <button
                type="button"
                class="inline-flex h-9 items-center justify-center rounded-md border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-600 transition hover:border-slate-300 hover:bg-slate-50"
                @click="closePrintPreview"
              >
                关闭预览
              </button>
              <button
                type="button"
                class="inline-flex h-9 items-center justify-center gap-1.5 rounded-md bg-slate-900 px-4 text-[12px] font-semibold text-white transition hover:bg-slate-700"
                @click="confirmPrintOverview"
              >
                <Printer class="size-3.5" aria-hidden="true" />
                确认打印
              </button>
            </div>
          </footer>
        </div>
      </section>
    </Transition>

    <div class="mx-auto max-w-[1720px] px-5 py-4">
      <section
        v-if="isSelectedFactoryReadOnly"
        class="mb-3 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] font-semibold text-amber-800"
      >
        <TriangleAlert class="mt-0.5 size-4 shrink-0 text-amber-600" aria-hidden="true" />
        <span>当前厂区为只读，仅可查看数据</span>
      </section>

      <section
        class="mb-3 flex flex-wrap items-center justify-end gap-2"
        aria-label="啤办业务导出打印操作区"
        data-testid="molding-sample-export-print-toolbar"
      >
        <input
          ref="excelFileInput"
          type="file"
          class="hidden"
          :accept="excelAccept"
          @change="handleExcelImportFile"
        >
        <div class="flex min-h-9 flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 shadow-sm shadow-slate-200/60">
          <div class="mr-1 border-r border-slate-200 pr-2">
            <div class="text-[11px] font-bold uppercase tracking-[0.08em] text-slate-500">导出 / 打印</div>
            <div class="text-[11px] text-slate-400">选择单据后可打印详情或合并导出</div>
          </div>
          <span
            class="inline-flex h-7 items-center rounded-md border border-teal-100 bg-teal-50 px-2 text-[12px] font-bold text-teal-700"
          >
            {{ selectedBatchCount ? `已选 ${selectedBatchCount} 单` : '默认当前单据' }}
          </span>
        <button
          type="button"
          class="inline-flex h-7 items-center gap-1 rounded-md border border-teal-200 bg-white px-2 text-[12px] font-semibold text-teal-700 transition hover:border-teal-300 hover:bg-teal-50"
          @click="printOverview"
        >
          <Printer class="size-3.5" aria-hidden="true" />
          打印
        </button>
        <button
          type="button"
          class="inline-flex h-7 items-center gap-1 rounded-md border border-teal-200 bg-white px-2 text-[12px] font-semibold text-teal-700 transition hover:border-teal-300 hover:bg-teal-50 disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="excelImporting || !canCreateOrder"
          @click="triggerExcelImport"
        >
          <Upload class="size-3.5" aria-hidden="true" />
          {{ excelImporting ? '导入中...' : '导入Excel' }}
        </button>
        <button
          type="button"
          class="inline-flex h-7 items-center gap-1 rounded-md border border-teal-200 bg-white px-2 text-[12px] font-semibold text-teal-700 transition hover:border-teal-300 hover:bg-teal-50 disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="excelExporting || !canExportSelectedOrder"
          @click="downloadOrderExcel"
        >
          <Download class="size-3.5" aria-hidden="true" />
          {{ excelExporting ? '导出中...' : '导出Excel' }}
        </button>
        <button
          type="button"
          class="inline-flex h-7 items-center rounded-md border border-slate-200 bg-slate-50 px-2 text-[12px] font-semibold text-slate-600 transition hover:border-slate-300 hover:bg-white"
          @click="loadApiData"
        >
          刷新正式列表
        </button>
        </div>
      </section>

      <section v-if="activeView === 'overview'" class="space-y-4">
        <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
          <article
            v-for="card in kpiCards"
            :key="card.label"
            class="min-h-[94px] rounded-lg border p-3"
            :class="card.className"
          >
            <div class="flex items-center justify-between">
              <span class="text-[11px] font-medium opacity-75">{{ card.label }}</span>
              <component :is="card.icon" class="size-4 opacity-60" aria-hidden="true" />
            </div>
            <div class="mt-1 text-2xl font-bold tabular-nums text-slate-950">{{ card.value }}</div>
            <div class="text-[11px] opacity-75">{{ card.detail }}</div>
          </article>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <div class="flex items-center gap-1 rounded-lg border border-slate-200 bg-white p-0.5">
            <button
              type="button"
              class="inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-[12px] transition"
              :class="overviewDisplayMode === 'board' ? 'bg-slate-900 font-semibold text-white' : 'font-medium text-slate-500 hover:text-slate-900'"
              @click="overviewDisplayMode = 'board'"
            >
              <LayoutDashboard class="size-3.5" aria-hidden="true" />
              看板
            </button>
            <button
              type="button"
              class="inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-[12px] transition"
              :class="overviewDisplayMode === 'list' ? 'bg-slate-900 font-semibold text-white' : 'font-medium text-slate-500 hover:text-slate-900'"
              @click="overviewDisplayMode = 'list'"
            >
              <Table2 class="size-3.5" aria-hidden="true" />
              列表
            </button>
          </div>
          <span class="mx-1 h-5 w-px bg-slate-200" aria-hidden="true" />
          <button class="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[12px] font-medium text-slate-600 hover:border-slate-300">
            <Filter class="size-3.5" aria-hidden="true" />
            车间：{{ selectedOrder.workshop || '全部' }}
          </button>
          <button class="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[12px] font-medium text-slate-600 hover:border-slate-300">
            <UserRound class="size-3.5" aria-hidden="true" />
            主管：{{ selectedOrder.supervisor || '全部' }}
          </button>
          <button class="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[12px] font-medium text-slate-600 hover:border-slate-300">
            <Tag class="size-3.5" aria-hidden="true" />
            类型：啤办
          </button>
          <div class="flex flex-wrap items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-1.5 py-1 text-[12px] text-slate-600">
            <button
              type="button"
              class="inline-flex h-7 items-center rounded-md px-2 font-semibold transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
              :disabled="!visibleRecords.length || isAllVisibleOrdersSelected"
              @click="selectAllVisibleOrders"
            >
              全选当前筛选单据
            </button>
            <button
              type="button"
              class="inline-flex h-7 items-center rounded-md px-2 font-semibold transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
              :disabled="selectedBatchCount === 0"
              @click="clearBatchSelection"
            >
              清空选择
            </button>
            <span class="rounded bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-500">
              已选 {{ selectedBatchCount }} 单
            </span>
          </div>
          <button
            type="button"
            class="ml-auto inline-flex items-center gap-1.5 rounded-lg border border-teal-200 bg-teal-50 px-3 py-1.5 text-[12px] font-semibold text-teal-700 transition hover:border-teal-300 hover:bg-teal-100"
            data-testid="material-balance-button"
            @click="setView('material-balance')"
          >
            <Beaker class="size-4" aria-hidden="true" />
            物料结余
          </button>
          <button
            type="button"
            class="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-1.5 text-[12px] font-semibold text-white transition hover:bg-slate-700"
            @click="startCreateOrder"
          >
            <Plus class="size-4" aria-hidden="true" />
            新建啤办单
          </button>
        </div>

        <div v-if="overviewDisplayMode === 'board'" class="grid grid-cols-1 gap-3 overflow-x-auto pb-2 md:grid-cols-2 xl:grid-cols-6">
          <section
            v-for="column in boardColumns"
            :key="column.status"
            class="min-h-[230px] rounded-lg bg-slate-50/90 ring-1 ring-inset ring-slate-200"
          >
            <div class="flex items-center justify-between px-3 py-2.5">
              <div class="flex min-w-0 items-center gap-2">
                <span class="h-2.5 w-2.5 shrink-0 rounded-full" :class="column.dotClass" />
                <div class="min-w-0">
                  <div class="truncate text-[12.5px] font-bold">{{ column.label }}</div>
                  <div class="truncate text-[10px] text-slate-400">{{ column.detail }}</div>
                </div>
              </div>
              <span class="rounded-full bg-white px-2 py-0.5 text-[11px] font-bold text-slate-500 ring-1 ring-slate-200">
                {{ column.records.length }}
              </span>
            </div>

            <div class="space-y-2 px-2 pb-2">
              <article
                v-for="record in column.pagedRecords"
                :key="record.order.id"
                class="w-full rounded-lg border bg-white p-2.5 text-left shadow-sm transition hover:shadow"
                :class="selectedOrder.id === record.order.id ? 'border-slate-950 ring-1 ring-slate-950' : isOrderBatchSelected(record.order.id) ? 'border-teal-300 ring-1 ring-teal-200' : 'border-slate-200 hover:border-slate-300'"
              >
                <div class="flex items-start gap-2">
                  <input
                    type="checkbox"
                    class="mt-0.5 h-4 w-4 shrink-0 rounded border-slate-300 text-teal-600"
                    :checked="isOrderBatchSelected(record.order.id)"
                    :aria-label="`选择单据 ${record.order.id}`"
                    @change="toggleOrderBatchSelection(record.order.id, $event)"
                  >
                  <button
                    type="button"
                    class="min-w-0 flex-1 text-left"
                    @click="openRecord(record)"
                  >
                    <div class="flex items-center justify-between gap-2">
                      <span class="font-mono text-[12px] font-bold text-slate-800">{{ record.order.id }}</span>
                      <span class="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500">{{ record.order.stage || '啤办' }}</span>
                    </div>
                    <div class="mt-1 truncate text-[13px] font-semibold">{{ record.order.product_name }}</div>
                    <div class="truncate text-[11px] text-slate-400">{{ record.order.client_name }} · {{ record.items.length }} 项明细</div>
                    <div class="mt-2 flex items-center justify-between gap-2 border-t border-slate-100 pt-2 text-[11px]">
                      <span class="truncate text-slate-500">{{ getFlowSummary(record) }}</span>
                      <span class="shrink-0 text-slate-400">{{ record.order.date }}</span>
                    </div>
                  </button>
                </div>
              </article>

              <div
                v-if="!column.records.length"
                class="rounded-lg border border-dashed border-slate-200 bg-white/70 p-4 text-center text-[11px] font-medium text-slate-400"
              >
                暂无{{ column.label }}单据
              </div>
            </div>
            <div
              v-if="column.records.length"
              class="border-t border-slate-200 px-2 py-2 text-[11px] text-slate-500"
            >
              <div class="mb-1.5 flex items-center justify-between gap-2">
                <span class="font-medium">每页 10 条</span>
                <span class="tabular-nums">{{ formatPaginationRange(column.pagination) }}</span>
              </div>
              <div class="flex items-center justify-between gap-2">
                <button
                  type="button"
                  class="inline-flex h-7 items-center gap-1 rounded-md border border-slate-200 bg-white px-2 font-semibold text-slate-600 transition hover:border-slate-300 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-40"
                  :disabled="!column.pagination.hasPrevious"
                  :aria-label="`${column.label}上一页`"
                  @click="setBoardColumnPage(column.status, column.pagination.page - 1)"
                >
                  <ChevronLeft class="size-3.5" aria-hidden="true" />
                  上一页
                </button>
                <span class="shrink-0 tabular-nums">{{ column.pagination.page }} / {{ column.pagination.pageCount }} 页</span>
                <button
                  type="button"
                  class="inline-flex h-7 items-center gap-1 rounded-md border border-slate-200 bg-white px-2 font-semibold text-slate-600 transition hover:border-slate-300 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-40"
                  :disabled="!column.pagination.hasNext"
                  :aria-label="`${column.label}下一页`"
                  @click="setBoardColumnPage(column.status, column.pagination.page + 1)"
                >
                  下一页
                  <ChevronRight class="size-3.5" aria-hidden="true" />
                </button>
              </div>
            </div>
          </section>
        </div>
        <section v-else class="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
            <div class="flex items-center gap-2">
              <Table2 class="size-4 text-slate-400" aria-hidden="true" />
              <span class="text-[13px] font-bold text-slate-950">啤办单列表</span>
              <span class="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-500">{{ visibleRecords.length }} 单</span>
            </div>
            <div class="flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
              <span class="font-medium">每页 10 条</span>
              <span class="tabular-nums">{{ formatPaginationRange(overviewListPagination) }}</span>
              <button
                type="button"
                class="inline-flex h-7 items-center gap-1 rounded-md border border-slate-200 bg-white px-2 font-semibold text-slate-600 transition hover:border-slate-300 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-40"
                :disabled="!overviewListPagination.hasPrevious"
                aria-label="啤办单列表上一页"
                @click="setOverviewListPage(overviewListPagination.page - 1)"
              >
                <ChevronLeft class="size-3.5" aria-hidden="true" />
                上一页
              </button>
              <span class="tabular-nums">{{ overviewListPagination.page }} / {{ overviewListPagination.pageCount }} 页</span>
              <button
                type="button"
                class="inline-flex h-7 items-center gap-1 rounded-md border border-slate-200 bg-white px-2 font-semibold text-slate-600 transition hover:border-slate-300 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-40"
                :disabled="!overviewListPagination.hasNext"
                aria-label="啤办单列表下一页"
                @click="setOverviewListPage(overviewListPagination.page + 1)"
              >
                下一页
                <ChevronRight class="size-3.5" aria-hidden="true" />
              </button>
            </div>
          </div>
          <div class="overflow-x-auto">
            <table aria-label="啤办单列表" class="w-full min-w-[1040px] text-[12px]">
              <thead>
                <tr class="border-b border-slate-100 bg-slate-50 text-[11px] text-slate-500">
                  <th class="px-3 py-2 text-left font-medium">选择</th>
                  <th class="px-3 py-2 text-left font-medium">单号</th>
                  <th class="px-3 py-2 text-left font-medium">产品 / 客户</th>
                  <th class="px-3 py-2 text-left font-medium">状态</th>
                  <th class="px-3 py-2 text-left font-medium">阶段</th>
                  <th class="px-3 py-2 text-left font-medium">明细</th>
                  <th class="px-3 py-2 text-left font-medium">工程 / 主管</th>
                  <th class="px-3 py-2 text-left font-medium">进度</th>
                  <th class="px-3 py-2 text-right font-medium">日期</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-50">
                <tr
                  v-for="record in paginatedVisibleRecords"
                  :key="record.order.id"
                  class="cursor-pointer transition hover:bg-slate-50"
                  :class="selectedOrder.id === record.order.id ? 'bg-slate-50 ring-1 ring-inset ring-slate-200' : ''"
                  @click="openRecord(record)"
                >
                  <td class="px-3 py-2.5 align-top">
                    <input
                      type="checkbox"
                      class="h-4 w-4 rounded border-slate-300 text-teal-600"
                      :checked="isOrderBatchSelected(record.order.id)"
                      :aria-label="`选择单据 ${record.order.id}`"
                      @click.stop
                      @change="toggleOrderBatchSelection(record.order.id, $event)"
                    >
                  </td>
                  <td class="px-3 py-2.5 align-top">
                    <button type="button" class="font-mono text-[12px] font-bold text-slate-900">
                      {{ record.order.id }}
                    </button>
                    <div class="mt-0.5 text-[10px] text-slate-400">{{ record.order.doc_number || record.order.order_number || '未填文件号' }}</div>
                  </td>
                  <td class="px-3 py-2.5 align-top">
                    <div class="max-w-[220px] truncate font-semibold text-slate-950">{{ record.order.product_name }}</div>
                    <div class="mt-0.5 max-w-[220px] truncate text-[11px] text-slate-400">{{ record.order.client_name || '未填客户' }}</div>
                  </td>
                  <td class="px-3 py-2.5 align-top">
                    <span class="inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold" :class="getStatusBadgeClass(record.order.status)">
                      {{ record.order.status }}
                    </span>
                  </td>
                  <td class="px-3 py-2.5 align-top">
                    <div class="text-[12px] font-semibold text-slate-800">{{ record.order.stage || '未填' }}</div>
                    <div class="mt-0.5 text-[11px] text-slate-400">{{ record.order.order_type }}</div>
                  </td>
                  <td class="px-3 py-2.5 align-top">
                    <div class="font-semibold text-slate-800">{{ record.items.length }} 项明细</div>
                    <div class="mt-0.5 max-w-[180px] truncate text-[11px] text-slate-400">
                      {{ record.items[0]?.mold_id || record.items[0]?.mold_name || '暂无明细' }}
                    </div>
                  </td>
                  <td class="px-3 py-2.5 align-top">
                    <div class="text-slate-700">{{ record.order.eng_name || '未填工程' }}</div>
                    <div class="mt-0.5 text-[11px] text-slate-400">{{ record.order.supervisor || '未填主管' }}</div>
                  </td>
                  <td class="px-3 py-2.5 align-top">
                    <div class="max-w-[220px] truncate text-slate-600">{{ getFlowSummary(record) }}</div>
                    <div v-if="record.problems.length" class="mt-0.5 text-[11px] font-semibold text-red-500">{{ record.problems.length }} 个问题</div>
                  </td>
                  <td class="px-3 py-2.5 text-right align-top tabular-nums text-slate-500">
                    {{ record.order.completed_date || record.order.date || record.order.updated_at }}
                  </td>
                </tr>
                <tr v-if="!visibleRecords.length">
                  <td colspan="9" class="px-3 py-10 text-center text-[12px] font-medium text-slate-400">
                    暂无符合条件的啤办单
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </section>

      <section v-else-if="activeView === 'material-balance'" class="space-y-4">
        <div class="flex items-center gap-2 text-[12px] text-slate-400">
          <button type="button" class="hover:text-slate-900" @click="setView('overview')">看板总览</button>
          <ChevronRight class="size-3.5" aria-hidden="true" />
          <span class="font-semibold text-slate-700">物料结余</span>
        </div>

        <section class="rounded-lg border border-slate-200 bg-white p-4">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div class="flex items-center gap-2">
                <Beaker class="size-5 text-teal-600" aria-hidden="true" />
                <h2 class="text-lg font-bold text-slate-950">物料结余</h2>
              </div>
              <div class="mt-1 text-[12px] font-medium text-slate-400">预计用料 - 实际用料</div>
            </div>
            <button
              type="button"
              class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-600 hover:border-slate-300"
              @click="setView('overview')"
            >
              <LayoutDashboard class="size-4" aria-hidden="true" />
              返回看板
            </button>
          </div>
        </section>

        <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
          <article class="min-h-[86px] rounded-lg border border-slate-200 bg-white p-3">
            <div class="text-[11px] font-medium text-slate-500">单据数</div>
            <div class="mt-1 text-2xl font-bold tabular-nums text-slate-950">{{ materialBalanceSummary.orderCount }}</div>
            <div class="text-[11px] text-slate-400">{{ activeFactory.shortName }}</div>
          </article>
          <article class="min-h-[86px] rounded-lg border border-indigo-100 bg-indigo-50 p-3">
            <div class="text-[11px] font-medium text-indigo-700">预计用料</div>
            <div class="mt-1 text-2xl font-bold tabular-nums text-slate-950">{{ formatWeight(materialBalanceSummary.totalExpectedWeightKg) }}</div>
            <div class="text-[11px] text-indigo-500">开单明细汇总</div>
          </article>
          <article class="min-h-[86px] rounded-lg border border-sky-100 bg-sky-50 p-3">
            <div class="text-[11px] font-medium text-sky-700">实际用料</div>
            <div class="mt-1 text-2xl font-bold tabular-nums text-slate-950">{{ formatWeight(materialBalanceSummary.totalActualWeightKg) }}</div>
            <div class="text-[11px] text-sky-500">啤机回填汇总</div>
          </article>
          <article class="min-h-[86px] rounded-lg border border-teal-100 bg-teal-50 p-3">
            <div class="text-[11px] font-medium text-teal-700">物料结余</div>
            <div class="mt-1 text-2xl font-bold tabular-nums" :class="getBalanceValueClass(materialBalanceSummary.totalBalanceWeightKg)">
              {{ formatSignedWeight(materialBalanceSummary.totalBalanceWeightKg) }}
            </div>
            <div class="text-[11px] text-teal-500">预计减实际</div>
          </article>
          <article class="min-h-[86px] rounded-lg border border-emerald-100 bg-emerald-50 p-3">
            <div class="text-[11px] font-medium text-emerald-700">结余金额</div>
            <div class="mt-1 text-2xl font-bold tabular-nums" :class="getBalanceValueClass(materialBalanceSummary.knownBalanceAmountHkd)">
              {{ formatSignedMoney(materialBalanceSummary.knownBalanceAmountHkd) }}
            </div>
            <div class="text-[11px] text-emerald-500">
              {{ materialBalanceSummary.unknownAmountCount ? `${materialBalanceSummary.unknownAmountCount} 单待计算` : '已全部折算' }}
            </div>
          </article>
        </div>

        <section class="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
            <div class="flex items-center gap-2">
              <History class="size-4 text-teal-500" aria-hidden="true" />
              <span class="text-[13px] font-bold text-slate-950">周期结余</span>
              <span class="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-500">{{ materialBalancePeriodRows.length }} 组</span>
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <div class="flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 p-0.5">
                <button
                  v-for="option in materialBalancePeriodOptions"
                  :key="option.key"
                  type="button"
                  class="inline-flex min-w-[72px] items-center justify-center rounded-md px-2.5 py-1 text-[12px] transition"
                  :class="materialBalancePeriodMode === option.key ? 'bg-slate-900 font-semibold text-white' : 'font-medium text-slate-500 hover:text-slate-900'"
                  @click="materialBalancePeriodMode = option.key"
                >
                  {{ option.label }}
                </button>
              </div>
              <div class="flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                <span class="font-medium">每页 10 条</span>
                <span class="tabular-nums">{{ formatPaginationRange(materialBalancePeriodPagination) }}</span>
                <button
                  type="button"
                  class="inline-flex h-7 items-center gap-1 rounded-md border border-slate-200 bg-white px-2 font-semibold text-slate-600 transition hover:border-slate-300 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-40"
                  :disabled="!materialBalancePeriodPagination.hasPrevious"
                  aria-label="物料周期结余上一页"
                  @click="setMaterialBalancePeriodPage(materialBalancePeriodPagination.page - 1)"
                >
                  <ChevronLeft class="size-3.5" aria-hidden="true" />
                  上一页
                </button>
                <span class="tabular-nums">{{ materialBalancePeriodPagination.page }} / {{ materialBalancePeriodPagination.pageCount }} 页</span>
                <button
                  type="button"
                  class="inline-flex h-7 items-center gap-1 rounded-md border border-slate-200 bg-white px-2 font-semibold text-slate-600 transition hover:border-slate-300 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-40"
                  :disabled="!materialBalancePeriodPagination.hasNext"
                  aria-label="物料周期结余下一页"
                  @click="setMaterialBalancePeriodPage(materialBalancePeriodPagination.page + 1)"
                >
                  下一页
                  <ChevronRight class="size-3.5" aria-hidden="true" />
                </button>
              </div>
            </div>
          </div>
          <div class="overflow-x-auto">
            <table aria-label="物料周期结余" class="w-full min-w-[980px] text-[12px]">
              <thead>
                <tr class="border-b border-slate-100 bg-slate-50 text-[11px] text-slate-500">
                  <th class="px-3 py-2 text-left font-medium">周期</th>
                  <th class="px-3 py-2 text-left font-medium">单据</th>
                  <th class="px-3 py-2 text-right font-medium">预计用料</th>
                  <th class="px-3 py-2 text-right font-medium">实际用料</th>
                  <th class="px-3 py-2 text-right font-medium">结余</th>
                  <th class="px-3 py-2 text-right font-medium">结余金额</th>
                  <th class="px-3 py-2 text-left font-medium">折算状态</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-50">
                <tr v-for="row in paginatedMaterialBalancePeriodRows" :key="row.key" class="hover:bg-slate-50">
                  <td class="px-3 py-2.5 align-top">
                    <div class="font-semibold text-slate-950">{{ row.label }}</div>
                    <div class="mt-0.5 text-[10px] text-slate-400">{{ row.detail }} · {{ row.startDate }} 至 {{ row.endDate }}</div>
                  </td>
                  <td class="px-3 py-2.5 align-top">
                    <div class="font-semibold text-slate-800">{{ row.orderCount }} 张单</div>
                    <div class="mt-0.5 max-w-[240px] truncate text-[11px] text-slate-400">
                      {{ row.orderRows.map((orderRow) => orderRow.record.order.id).join('、') }}
                    </div>
                  </td>
                  <td class="px-3 py-2.5 text-right align-top tabular-nums text-slate-700">{{ formatWeight(row.expectedWeightKg) }}</td>
                  <td class="px-3 py-2.5 text-right align-top tabular-nums text-slate-700">{{ formatWeight(row.actualWeightKg) }}</td>
                  <td class="px-3 py-2.5 text-right align-top font-bold tabular-nums" :class="getBalanceValueClass(row.balanceWeightKg)">
                    {{ formatSignedWeight(row.balanceWeightKg) }}
                  </td>
                  <td class="px-3 py-2.5 text-right align-top font-bold tabular-nums" :class="getBalanceValueClass(row.balanceAmountHkd)">
                    {{ formatSignedMoney(row.balanceAmountHkd) }}
                  </td>
                  <td class="px-3 py-2.5 align-top">
                    <span
                      class="inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold"
                      :class="row.missingActualCount ? 'border-amber-200 bg-amber-50 text-amber-700' : row.unknownAmountCount ? 'border-slate-200 bg-slate-50 text-slate-500' : 'border-emerald-200 bg-emerald-50 text-emerald-700'"
                    >
                      {{ row.missingActualCount ? `${row.missingActualCount} 项待回填` : row.unknownAmountCount ? `${row.unknownAmountCount} 项待计价` : '已折算' }}
                    </span>
                  </td>
                </tr>
                <tr v-if="!materialBalancePeriodRows.length">
                  <td colspan="7" class="px-3 py-10 text-center text-[12px] font-medium text-slate-400">
                    暂无周期结余
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
            <div class="flex items-center gap-2">
              <Beaker class="size-4 text-teal-500" aria-hidden="true" />
              <span class="text-[13px] font-bold text-slate-950">物料结余明细</span>
              <span class="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-500">{{ materialBalanceRows.length }} 单</span>
            </div>
            <div class="flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
              <span class="font-medium">每页 10 条</span>
              <span class="tabular-nums">{{ formatPaginationRange(materialBalanceDetailPagination) }}</span>
              <button
                type="button"
                class="inline-flex h-7 items-center gap-1 rounded-md border border-slate-200 bg-white px-2 font-semibold text-slate-600 transition hover:border-slate-300 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-40"
                :disabled="!materialBalanceDetailPagination.hasPrevious"
                aria-label="物料结余明细上一页"
                @click="setMaterialBalanceDetailPage(materialBalanceDetailPagination.page - 1)"
              >
                <ChevronLeft class="size-3.5" aria-hidden="true" />
                上一页
              </button>
              <span class="tabular-nums">{{ materialBalanceDetailPagination.page }} / {{ materialBalanceDetailPagination.pageCount }} 页</span>
              <button
                type="button"
                class="inline-flex h-7 items-center gap-1 rounded-md border border-slate-200 bg-white px-2 font-semibold text-slate-600 transition hover:border-slate-300 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-40"
                :disabled="!materialBalanceDetailPagination.hasNext"
                aria-label="物料结余明细下一页"
                @click="setMaterialBalanceDetailPage(materialBalanceDetailPagination.page + 1)"
              >
                下一页
                <ChevronRight class="size-3.5" aria-hidden="true" />
              </button>
            </div>
          </div>
          <div class="overflow-x-auto">
            <table aria-label="物料结余明细" class="w-full min-w-[1120px] text-[12px]">
              <thead>
                <tr class="border-b border-slate-100 bg-slate-50 text-[11px] text-slate-500">
                  <th class="px-3 py-2 text-left font-medium">单号</th>
                  <th class="px-3 py-2 text-left font-medium">产品 / 客户</th>
                  <th class="px-3 py-2 text-left font-medium">状态</th>
                  <th class="px-3 py-2 text-left font-medium">明细</th>
                  <th class="px-3 py-2 text-right font-medium">预计用料</th>
                  <th class="px-3 py-2 text-right font-medium">实际用料</th>
                  <th class="px-3 py-2 text-right font-medium">结余</th>
                  <th class="px-3 py-2 text-right font-medium">结余金额</th>
                  <th class="px-3 py-2 text-left font-medium">折算状态</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-50">
                <tr
                  v-for="row in paginatedMaterialBalanceRows"
                  :key="row.record.order.id"
                  class="cursor-pointer transition hover:bg-slate-50"
                  @click="openRecord(row.record)"
                >
                  <td class="px-3 py-2.5 align-top">
                    <button type="button" class="font-mono text-[12px] font-bold text-slate-900">
                      {{ row.record.order.id }}
                    </button>
                    <div class="mt-0.5 text-[10px] text-slate-400">{{ row.record.order.doc_number || row.record.order.order_number || '未填文件号' }}</div>
                  </td>
                  <td class="px-3 py-2.5 align-top">
                    <div class="max-w-[220px] truncate font-semibold text-slate-950">{{ row.record.order.product_name }}</div>
                    <div class="mt-0.5 max-w-[220px] truncate text-[11px] text-slate-400">{{ row.record.order.client_name || '未填客户' }}</div>
                  </td>
                  <td class="px-3 py-2.5 align-top">
                    <span class="inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold" :class="getStatusBadgeClass(row.record.order.status)">
                      {{ row.record.order.status }}
                    </span>
                  </td>
                  <td class="px-3 py-2.5 align-top">
                    <div class="font-semibold text-slate-800">{{ row.itemRows.length }} 项明细</div>
                    <div class="mt-0.5 max-w-[180px] truncate text-[11px] text-slate-400">
                      {{ row.itemRows[0]?.item.material || row.itemRows[0]?.item.mold_name || '暂无明细' }}
                    </div>
                  </td>
                  <td class="px-3 py-2.5 text-right align-top tabular-nums text-slate-700">{{ formatWeight(row.expectedWeightKg) }}</td>
                  <td class="px-3 py-2.5 text-right align-top tabular-nums text-slate-700">{{ formatWeight(row.actualWeightKg) }}</td>
                  <td class="px-3 py-2.5 text-right align-top font-bold tabular-nums" :class="getBalanceValueClass(row.balanceWeightKg)">
                    {{ formatSignedWeight(row.balanceWeightKg) }}
                  </td>
                  <td class="px-3 py-2.5 text-right align-top font-bold tabular-nums" :class="getBalanceValueClass(row.balanceAmountHkd)">
                    {{ formatSignedMoney(row.balanceAmountHkd) }}
                  </td>
                  <td class="px-3 py-2.5 align-top">
                    <span
                      class="inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold"
                      :class="row.missingActualCount ? 'border-amber-200 bg-amber-50 text-amber-700' : row.unknownAmountCount ? 'border-slate-200 bg-slate-50 text-slate-500' : 'border-emerald-200 bg-emerald-50 text-emerald-700'"
                    >
                      {{ row.missingActualCount ? `${row.missingActualCount} 项待回填` : row.unknownAmountCount ? `${row.unknownAmountCount} 项待计价` : '已折算' }}
                    </span>
                  </td>
                </tr>
                <tr v-if="!materialBalanceRows.length">
                  <td colspan="9" class="px-3 py-10 text-center text-[12px] font-medium text-slate-400">
                    暂无符合条件的啤办单
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </section>

      <section v-else-if="activeView === 'create'" class="space-y-4">
        <div class="flex items-center gap-2 text-[12px] text-slate-400">
          <button type="button" class="hover:text-slate-900" @click="setView('overview')">看板总览</button>
          <ChevronRight class="size-3.5" aria-hidden="true" />
          <button
            v-if="isEditingRejectedOrder"
            type="button"
            class="hover:text-slate-900"
            @click="cancelRejectedEdit"
          >
            单据详情
          </button>
          <ChevronRight v-if="isEditingRejectedOrder" class="size-3.5" aria-hidden="true" />
          <span class="font-semibold text-slate-700">
            {{ isEditingRejectedOrder ? selectedOrder.status === '已撤回' ? '修改撤回单并重提' : '修改驳回单并重提' : '新建啤办单' }}
          </span>
        </div>

        <div class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
          <div class="space-y-4 xl:contents">
            <section class="rounded-lg border border-slate-200 bg-white">
              <div class="flex items-center gap-2 border-b border-slate-100 px-4 py-2.5">
                <FileText class="size-4 text-slate-400" aria-hidden="true" />
                <span class="text-[13px] font-bold">基础资料</span>
                <span class="ml-auto text-[11px] text-slate-400">
                  {{ isEditingRejectedOrder ? `${editingRevisionOrderLabel} ${editingRejectedOrderId}` : '单号自动生成 · BP-新' }}
                </span>
              </div>
              <div class="grid grid-cols-2 gap-x-4 gap-y-3 p-4 md:grid-cols-3">
                <label class="block">
                  <span class="mb-1 block text-[11px] font-medium text-slate-500">单据编号</span>
                  <input v-model="createDraft.id" data-testid="create-order-id" placeholder="BP-产品编号" class="h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-[12px] outline-none focus:border-slate-400">
                </label>
                <label class="block">
                  <span class="mb-1 block text-[11px] font-medium text-slate-500">产品编号</span>
                  <input
                    :value="createDraft.product_no"
                    data-testid="create-product-no"
                    class="h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-[12px] outline-none focus:border-slate-400"
                    @input="updateCreateProductNo(readInputValue($event))"
                  >
                </label>
                <label class="block">
                  <span class="mb-1 block text-[11px] font-medium text-slate-500">客户</span>
                  <input v-model="createDraft.client_name" data-testid="create-client-name" class="h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-[12px] outline-none focus:border-slate-400">
                </label>
                <label class="block">
                  <span class="mb-1 block text-[11px] font-medium text-slate-500">产品名称</span>
                  <input v-model="createDraft.product_name" data-testid="create-product-name" class="h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-[12px] outline-none focus:border-slate-400">
                </label>
                <label class="block">
                  <span class="mb-1 block text-[11px] font-medium text-slate-500">开单日期</span>
                  <input v-model="createDraft.order_date" type="date" class="h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-[12px] outline-none focus:border-slate-400">
                </label>
                <label class="block">
                  <span class="mb-1 block text-[11px] font-medium text-slate-500">阶段</span>
                  <select v-model="createDraft.stage" class="h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-[12px] outline-none focus:border-slate-400">
                    <option>T0</option>
                    <option>EP</option>
                    <option>FEP</option>
                    <option>PP</option>
                  </select>
                </label>
                <label class="block">
                  <span class="mb-1 block text-[11px] font-medium text-slate-500">填写部</span>
                  <select v-model="createDraft.workshop" class="h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-[12px] outline-none focus:border-slate-400">
                    <option>工程部</option>
                    <option>PMC部</option>
                    <option>生产部</option>
                    <option>QA部</option>
                    <option>业务部</option>
                  </select>
                </label>
                <label class="block">
                  <span class="mb-1 block text-[11px] font-medium text-slate-500">发至</span>
                  <input v-model="createDraft.send_to" placeholder="填写发至位置" class="h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-[12px] outline-none focus:border-slate-400">
                </label>
                <label class="block">
                  <span class="mb-1 block text-[11px] font-medium text-slate-500">审核主管</span>
                  <input v-model="createDraft.supervisor" data-testid="create-supervisor" placeholder="填写主管姓名" class="h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-[12px] outline-none focus:border-slate-400">
                </label>
                <label class="block">
                  <span class="mb-1 block text-[11px] font-medium text-slate-500">落单人</span>
                  <input v-model="createDraft.eng_name" data-testid="create-engineer" class="h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-[12px] outline-none focus:border-slate-400">
                </label>
                <label class="col-span-2 block md:col-span-3">
                  <span class="mb-1 block text-[11px] font-medium text-slate-500">注意事项 / 开单事由</span>
                  <textarea v-model="createDraft.reason" rows="3" class="w-full rounded-md border border-slate-200 bg-white px-2 py-1.5 text-[12px] outline-none focus:border-slate-400" />
                </label>
              </div>
            </section>

            <section class="rounded-lg border border-slate-200 bg-white shadow-sm xl:col-span-2">
              <div class="flex items-center gap-2 border-b border-slate-100 px-4 py-2.5">
                <Table2 class="size-4 text-slate-400" aria-hidden="true" />
                <span class="text-[13px] font-bold">模具明细</span>
                <span class="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-500">按行维护</span>
              </div>
              <div class="space-y-2 p-3">
                <div class="overflow-x-auto rounded-lg border border-slate-200 bg-white">
                  <div class="min-w-[2240px]" role="table" aria-label="模具明细录入表">
                    <div
                      class="grid items-center gap-x-2 border-b border-slate-200 bg-slate-50 px-3 py-2.5 text-[11px] font-semibold text-slate-500"
                      :class="createLineGridClass"
                      role="row"
                    >
                      <div class="min-w-0 text-center" role="columnheader">#</div>
                      <div class="min-w-0 truncate px-2" role="columnheader">客模具编号</div>
                      <div class="min-w-0 truncate px-2" role="columnheader">模具名称</div>
                      <div class="min-w-0 truncate px-2" role="columnheader">工模尺寸</div>
                      <div class="min-w-0 truncate px-2" role="columnheader">适配机型</div>
                      <div class="min-w-0 truncate px-2" role="columnheader">模具是否在厂</div>
                      <div class="min-w-0 truncate px-2" role="columnheader">模具回厂时间</div>
                      <div class="min-w-0 truncate px-2" role="columnheader">所需用料</div>
                      <div class="min-w-0 truncate px-2 text-right" role="columnheader">原料价格(HKD/磅)</div>
                      <div class="min-w-0 truncate px-2" role="columnheader">颜色</div>
                      <div class="min-w-0 truncate px-2" role="columnheader">PMS</div>
                      <div class="min-w-0 truncate px-2" role="columnheader">色粉</div>
                      <div class="min-w-0 truncate px-2 text-center" role="columnheader">啤/套</div>
                      <div class="min-w-0 truncate px-2 text-right" role="columnheader">啤数</div>
                      <div class="min-w-0 truncate px-2 text-right" role="columnheader">整啤毛重(g)</div>
                      <div class="min-w-0 truncate px-2 text-right" role="columnheader">所需用料(kg)</div>
                      <div class="min-w-0 truncate px-2" role="columnheader">需办日期</div>
                      <div class="min-w-0 truncate px-2" role="columnheader">备注</div>
                      <div class="min-w-0 truncate text-center" role="columnheader">操作</div>
                    </div>
                    <div class="divide-y divide-slate-100 bg-white">
                      <div
                        v-for="(line, index) in createDraft.items"
                        :key="`create-line-${index}`"
                        class="grid items-start gap-x-2 px-3 py-3 text-[12px] hover:bg-slate-50/70"
                        :class="createLineGridClass"
                        role="row"
                      >
                        <div class="min-w-0 pt-1.5 text-center" role="cell">
                          <span class="inline-flex size-6 items-center justify-center rounded-md bg-slate-100 font-semibold text-slate-500">{{ index + 1 }}</span>
                        </div>
                        <div class="min-w-0" role="cell">
                          <input v-model="line.customer_mold_id" data-testid="create-line-mold-id" class="h-9 w-full min-w-0 rounded-md border border-slate-200 bg-white px-2 font-mono outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-100">
                        </div>
                        <div class="min-w-0" role="cell">
                          <input v-model="line.mold_name" data-testid="create-line-mold-name" class="h-9 w-full min-w-0 rounded-md border border-slate-200 bg-white px-2 outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-100">
                        </div>
                        <div class="min-w-0" role="cell"><input v-model="line.mold_dimensions" data-testid="create-line-mold-dimensions" class="h-9 w-full min-w-0 rounded-md border border-slate-200 bg-white px-2"></div>
                        <div class="min-w-0" role="cell"><input v-model="line.machine_type" data-testid="create-line-machine-type" class="h-9 w-full min-w-0 rounded-md border border-slate-200 bg-white px-2"></div>
                        <div class="min-w-0" role="cell"><select v-model="line.mold_presence_status" data-testid="create-line-mold-presence-status" class="h-9 w-full min-w-0 rounded-md border border-slate-200 bg-white px-2"><option value="">待确认</option><option value="in_factory">在厂</option><option value="out_of_factory">不在厂</option></select></div>
                        <div class="min-w-0" role="cell"><input v-model="line.mold_return_time" data-testid="create-line-mold-return-time" type="date" class="h-9 w-full min-w-0 rounded-md border border-slate-200 bg-white px-2"></div>
                        <div
                          class="relative min-w-0"
                          role="cell"
                          @focusout="handleRawMaterialPickerFocusOut(index, $event)"
                        >
                          <div class="relative">
                            <Search class="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-slate-400" aria-hidden="true" />
                            <input
                              :value="getRawMaterialPickerText(index, line.material)"
                              data-testid="create-line-material"
                              role="combobox"
                              aria-label="选择所需用料"
                              aria-haspopup="listbox"
                              autocomplete="off"
                              :aria-expanded="activeRawMaterialPickerLineIndex === index"
                              :aria-controls="getRawMaterialListboxId(index)"
                              :title="getRawMaterialOptionTitle(line.material) || '请选择原料'"
                              placeholder="搜索原料名称/编号"
                              class="h-9 w-full min-w-0 rounded-md border border-slate-200 bg-white py-0 pl-8 pr-7 text-[12px] outline-none transition placeholder:text-slate-400 focus:border-slate-400 focus:ring-2 focus:ring-slate-100"
                              @focus="openRawMaterialPicker(index, line.material, $event)"
                              @input="updateRawMaterialSearch(index, $event)"
                              @keydown.enter.prevent="selectFirstRawMaterialOption(line, index)"
                              @keydown.esc.prevent="closeRawMaterialPicker(index)"
                            >
                            <button
                              v-if="line.material"
                              type="button"
                              class="absolute right-1.5 top-1/2 inline-flex size-6 -translate-y-1/2 items-center justify-center rounded-md text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
                              aria-label="清除所需用料"
                              @mousedown.prevent
                              @click="clearRawMaterialSelection(line, index)"
                            >
                              <X class="size-3.5" aria-hidden="true" />
                            </button>
                          </div>
                          <Teleport to="body">
                            <div
                              v-if="activeRawMaterialPickerLineIndex === index"
                              :id="getRawMaterialListboxId(index)"
                              class="fixed z-[80] overflow-hidden rounded-lg border border-slate-200 bg-white shadow-xl shadow-slate-900/10"
                              :style="getRawMaterialPickerStyle(index)"
                              role="listbox"
                            >
                              <div class="max-h-64 overflow-y-auto py-1">
                                <button
                                  v-if="hasUnknownRawMaterialValue(line.material)"
                                  type="button"
                                  class="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-[12px] text-slate-700 transition hover:bg-slate-50"
                                  role="option"
                                  :aria-selected="true"
                                  @mousedown.prevent
                                  @click="closeRawMaterialPicker(index)"
                                >
                                  <span class="min-w-0 truncate font-semibold">{{ line.material }}</span>
                                  <span class="shrink-0 rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700">当前值</span>
                                </button>
                                <button
                                  v-for="option in getVisibleRawMaterialOptions(index)"
                                  :key="option.value"
                                  type="button"
                                  class="grid w-full grid-cols-[minmax(0,1fr)_76px_72px] items-center gap-2 px-3 py-2 text-left text-[12px] text-slate-700 transition hover:bg-slate-50"
                                  :class="line.material === option.value ? 'bg-slate-50 text-slate-950' : ''"
                                  role="option"
                                  :aria-selected="line.material === option.value"
                                  :title="option.label"
                                  @mousedown.prevent
                                  @click="selectRawMaterialOption(line, index, option)"
                                >
                                  <span class="min-w-0 truncate font-semibold">{{ option.value }}</span>
                                  <span class="min-w-0 truncate font-mono text-[10px] text-slate-400">{{ option.code || '无编号' }}</span>
                                  <span class="min-w-0 truncate rounded bg-slate-100 px-1.5 py-0.5 text-center text-[10px] font-semibold text-slate-500">{{ option.category || '未分类' }}</span>
                                </button>
                                <div
                                  v-if="!getVisibleRawMaterialOptions(index).length && !hasUnknownRawMaterialValue(line.material)"
                                  class="px-3 py-3 text-[12px] font-medium text-slate-400"
                                >
                                  未找到匹配原料
                                </div>
                              </div>
                            </div>
                          </Teleport>
                        </div>
                        <div class="min-w-0" role="cell">
                          <div
                            data-testid="create-line-material-price"
                            class="flex h-9 w-full min-w-0 items-center justify-end gap-1 rounded-md border border-slate-200 bg-slate-50 px-2 text-[12px] text-slate-500"
                            :class="getRawMaterialUnitPrice(line.material) !== null ? 'font-semibold tabular-nums text-slate-700' : ''"
                            :title="line.material ? `${line.material} · ${getRawMaterialUnitPriceLabel(line.material)} / 磅` : '请选择所需用料后显示原料价格'"
                          >
                            <span>{{ getRawMaterialUnitPriceLabel(line.material) }}</span>
                            <span v-if="getRawMaterialUnitPrice(line.material) !== null" class="text-[10px] font-medium text-slate-400">/ 磅</span>
                          </div>
                        </div>
                        <div class="min-w-0" role="cell">
                          <input v-model="line.color" data-testid="create-line-color" placeholder="颜色" class="h-9 w-full min-w-0 rounded-md border border-slate-200 bg-white px-2 outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-100">
                        </div>
                        <div class="min-w-0" role="cell">
                          <input v-model="line.pms" placeholder="PMS" class="h-9 w-full min-w-0 rounded-md border border-slate-200 bg-white px-2 outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-100">
                        </div>
                        <div class="min-w-0" role="cell">
                          <input v-model="line.pigment_no" class="h-9 w-full min-w-0 rounded-md border border-slate-200 bg-white px-2 outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-100">
                        </div>
                        <div class="min-w-0" role="cell">
                          <input v-model="line.quantity" data-testid="create-line-quantity" class="h-9 w-full min-w-0 rounded-md border border-slate-200 bg-white px-2 text-center outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-100">
                        </div>
                        <div class="min-w-0" role="cell">
                          <input v-model="line.shoot_qty" data-testid="create-line-shoot-qty" class="h-9 w-full min-w-0 rounded-md border border-slate-200 bg-white px-2 text-right outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-100">
                        </div>
                        <div class="min-w-0" role="cell">
                          <input v-model="line.gross_weight_g" data-testid="create-line-gross-weight" inputmode="decimal" placeholder="g" class="h-9 w-full min-w-0 rounded-md border border-slate-200 bg-white px-2 text-right outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-100">
                        </div>
                        <div class="min-w-0" role="cell">
                          <input v-model="line.required_material_kg" data-testid="create-line-required-material" inputmode="decimal" placeholder="kg" class="h-9 w-full min-w-0 rounded-md border border-slate-200 bg-white px-2 text-right outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-100">
                        </div>
                        <div class="min-w-0" role="cell">
                          <input v-model="line.required_date" data-testid="create-line-required-date" type="date" class="h-9 w-full min-w-0 rounded-md border border-slate-200 bg-white px-2 outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-100">
                        </div>
                        <div class="min-w-0" role="cell">
                          <input v-model="line.notes" placeholder="备注提示" class="h-9 w-full min-w-0 rounded-md border border-slate-200 bg-white px-2 outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-100">
                        </div>
                        <div class="min-w-0" role="cell">
                          <button
                            type="button"
                            class="flex h-9 w-full items-center justify-center rounded-md border border-red-100 bg-white text-[11px] font-semibold text-red-500 transition hover:bg-red-50"
                            @click="removeCreateLine(index)"
                          >
                            删除
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                <button
                  type="button"
                  class="flex h-9 w-full items-center justify-center rounded-lg border border-dashed border-slate-300 bg-slate-50 text-[12px] font-semibold text-slate-600 transition hover:border-slate-400 hover:bg-white hover:text-slate-950"
                  @click="addCreateLine"
                >
                  + 继续添加明细行
                </button>
              </div>
            </section>
          </div>

          <aside class="space-y-4 xl:col-start-2 xl:row-start-1">
            <section class="rounded-lg border border-slate-200 bg-white p-4">
              <div class="mb-3 flex items-center gap-2">
                <Send class="size-4 text-slate-400" aria-hidden="true" />
                <span class="text-[13px] font-bold">提交动作</span>
              </div>
              <div class="space-y-2 text-[11px] text-slate-500">
                <div class="flex justify-between"><span>当前厂区</span><strong class="text-slate-800">{{ activeFactory.shortName }}</strong></div>
                <div class="flex justify-between"><span>提交人</span><strong class="text-slate-800">{{ authStore.currentUser?.display_name ?? createDraft.eng_name ?? '待填写' }}</strong></div>
                <div class="flex justify-between"><span>下一节点</span><strong class="text-slate-800">待审核</strong></div>
              </div>
              <div
                v-if="isEditingRejectedOrder"
                class="mt-3 rounded-lg border p-2.5 text-[11px] leading-5"
                :class="selectedOrder.status === '已撤回' ? 'border-slate-200 bg-slate-50 text-slate-600' : 'border-red-200 bg-red-50 text-red-700'"
              >
                {{ selectedOrder.status === '已撤回' ? '当前单据已由工程撤回。保存修改后会自动重提，状态回到待审核，并保留审核轨迹。' : '当前单据已被驳回。保存修改后会自动重提，状态回到待审核，并保留审核轨迹。' }}
              </div>
              <div v-if="createErrors.length" class="mt-3 rounded-lg border border-red-200 bg-red-50 p-2 text-[11px] text-red-700">
                <div v-for="error in createErrors" :key="error">{{ error }}</div>
              </div>
              <div class="mt-3 rounded-lg bg-slate-50 p-2.5 text-[11px] text-slate-500">
                {{ isEditingRejectedOrder ? '重提后回到主管审核节点，主管通过后进入下一流程。' : '开单后进入现有流程：待审核 → 待生产 → 生产中 → 已完成。' }}
              </div>
              <div
                v-if="!isEditingRejectedOrder"
                class="mt-2 rounded-lg border border-slate-200 bg-white p-2.5 text-[11px] leading-5 text-slate-500"
              >
                已填写草稿会自动保留，提交或重置后清除。
              </div>
              <button
                type="button"
                :disabled="createSubmitting || !canSubmitCreateForm"
                class="mt-3 flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-slate-900 text-[13px] font-semibold text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-300"
                @click="submitManualCreate"
              >
                <Save v-if="isEditingRejectedOrder" class="size-4" aria-hidden="true" />
                <Send v-else class="size-4" aria-hidden="true" />
                {{
                  createSubmitting
                    ? '提交中...'
                    : canSubmitCreateForm
                      ? isEditingRejectedOrder ? '保存并重提' : '提交主管审核'
                      : isEditingRejectedOrder ? '无编辑权限' : '无新建权限'
                }}
              </button>
              <button
                type="button"
                class="mt-2 flex h-9 w-full items-center justify-center gap-1.5 rounded-lg border border-slate-200 text-[12px] font-medium text-slate-600 hover:border-slate-300"
                @click="resetCurrentCreateDraft"
              >
                <RotateCcw class="size-3.5" aria-hidden="true" />
                {{ isEditingRejectedOrder ? '重置修改' : '重置草稿' }}
              </button>
              <button
                v-if="isEditingRejectedOrder"
                type="button"
                class="mt-2 flex h-9 w-full items-center justify-center gap-1.5 rounded-lg border border-slate-200 text-[12px] font-medium text-slate-600 hover:border-slate-300"
                @click="cancelRejectedEdit"
              >
                返回单据详情
              </button>
            </section>
          </aside>
        </div>
      </section>

      <section v-else-if="selectedRecord" class="space-y-4">
        <div class="flex items-center gap-2 text-[12px] text-slate-400">
          <button type="button" class="hover:text-slate-900" @click="setView('overview')">看板总览</button>
          <ChevronRight class="size-3.5" aria-hidden="true" />
          <span class="font-semibold text-slate-700">单据详情 · {{ selectedOrder.id }}</span>
        </div>

        <section class="rounded-lg border border-slate-200 bg-white p-4">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div class="flex flex-wrap items-center gap-2">
                <span class="font-mono text-lg font-bold">{{ selectedOrder.id }}</span>
                <span class="rounded-full border px-2 py-0.5 text-[11px] font-bold" :class="getStatusBadgeClass(selectedOrder.status)">
                  {{ selectedOrder.status }}
                </span>
                <span class="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500">{{ selectedOrder.stage || '啤办' }}</span>
                <span class="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500">
                  {{ isSelectedExternal ? '外厂 / 模厂路径' : '内部生产' }}
                </span>
              </div>
              <div class="mt-1 text-[15px] font-bold">{{ selectedOrder.product_name }} · {{ selectedOrder.client_name }}</div>
              <div class="mt-1 flex flex-wrap gap-x-4 text-[11px] text-slate-400">
                <span>文件 {{ selectedOrder.doc_number }}</span>
                <span>{{ selectedOrder.workshop }}</span>
                <span>工程 {{ selectedOrder.eng_name }}</span>
                <span>主管 {{ selectedOrder.supervisor }}</span>
                <span>开单 {{ selectedOrder.date }}</span>
              </div>
            </div>

            <div class="flex flex-wrap gap-2">
              <button
                type="button"
                class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-600 hover:border-slate-300"
                @click="setView('overview')"
              >
                返回看板
              </button>
              <button
                v-if="selectedOrder.status === '待审核'"
                type="button"
                :disabled="!canWithdrawSelectedOrder || withdrawSubmitting"
                class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-3 text-[12px] font-semibold text-amber-700 hover:bg-amber-100 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-400"
                @click="withdrawSelectedOrder"
              >
                <RotateCcw class="size-4" aria-hidden="true" />
                {{ withdrawSubmitting ? '撤回中...' : '撤回审核' }}
              </button>
              <button
                v-if="selectedOrder.status === '已驳回' || selectedOrder.status === '已撤回'"
                type="button"
                :disabled="!canEditSelectedRejectedOrder"
                class="inline-flex h-9 items-center gap-1.5 rounded-lg border px-3 text-[12px] font-semibold disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-400"
                :class="selectedOrder.status === '已撤回' ? 'border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100' : 'border-red-200 bg-red-50 text-red-700 hover:bg-red-100'"
                @click="startRejectedEdit"
              >
                <PencilLine class="size-4" aria-hidden="true" />
                修改后重提
              </button>
              <button
                v-if="canDeleteSelectedOrder"
                type="button"
                :disabled="deleteSubmitting"
                class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-red-200 bg-red-50 px-3 text-[12px] font-semibold text-red-700 hover:bg-red-100 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-400"
                @click="deleteSelectedOrder"
              >
                <Trash2 class="size-4" aria-hidden="true" />
                {{ deleteSubmitting ? '删除中...' : deleteConfirmingOrderId === selectedOrder.id ? '确认删除' : '删除啤办单' }}
              </button>
              <RouterLink
                :to="productionTaskRoute"
                class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-slate-900 px-3 text-[12px] font-semibold text-white hover:bg-slate-700"
              >
                <Factory class="size-4" aria-hidden="true" />
                啤办生产任务单
              </RouterLink>
            </div>
          </div>
        </section>

        <section class="rounded-lg border border-slate-200 bg-white p-4">
          <div class="mb-3 flex items-center justify-between gap-3">
            <div>
              <h2 class="text-[13px] font-bold">流程状态</h2>
              <p class="text-[11px] text-slate-400">保持现有状态机：待审核 → 待生产 → 生产中 → 已完成</p>
            </div>
            <span class="rounded-full border px-2 py-0.5 text-[11px] font-bold" :class="getStatusBadgeClass(selectedOrder.status)">
              {{ selectedCompletionGate.message }}
            </span>
          </div>

          <div class="grid gap-2 md:grid-cols-4">
            <article
              v-for="(step, index) in workflowSteps"
              :key="step.status"
              class="rounded-lg border p-2.5"
              :class="getWorkflowCardClass(getWorkflowStepState(step.status))"
            >
              <div class="flex items-center gap-1.5">
                <span
                  class="flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold"
                  :class="getWorkflowIndexClass(getWorkflowStepState(step.status))"
                >
                  {{ index + 1 }}
                </span>
                <span class="text-[12px] font-bold">{{ step.title }}</span>
              </div>
              <div class="mt-1 pl-6 text-[10px] opacity-75">{{ step.detail }}</div>
            </article>
          </div>
        </section>

        <div class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
          <div class="space-y-4">
            <section class="rounded-lg border border-slate-200 bg-white">
              <div class="flex flex-wrap items-center gap-2 border-b border-slate-100 px-4 py-2.5">
                <Table2 class="size-4 text-slate-400" aria-hidden="true" />
                <span class="text-[13px] font-bold">模具明细</span>
                <span class="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-500">{{ selectedItems.length }} 项</span>
                <button
                  type="button"
                  class="ml-auto inline-flex h-7 items-center rounded-md border border-slate-200 bg-white px-2 text-[11px] font-semibold text-slate-600 transition hover:border-slate-300 hover:text-slate-950"
                  @click="isSelectedOrderDataExpanded = !isSelectedOrderDataExpanded"
                >
                  {{ isSelectedOrderDataExpanded ? '收起完整数据' : '展开完整数据' }}
                </button>
              </div>
              <div class="overflow-x-auto">
                <table class="w-full min-w-[1120px] text-[12px]">
                  <thead>
                    <tr class="border-b border-slate-100 bg-slate-50 text-[11px] text-slate-500">
                      <th class="w-8 px-2 py-2 font-medium">#</th>
                      <th class="px-2 py-2 text-left font-medium">模具号</th>
                      <th class="px-2 py-2 text-left font-medium">名称</th>
                      <th class="px-2 py-2 text-left font-medium">原料</th>
                      <th class="px-2 py-2 text-left font-medium">颜色 / PMS</th>
                      <th class="px-2 py-2 text-right font-medium">预计用料</th>
                      <th class="px-2 py-2 text-right font-medium">预计料费</th>
                      <th class="px-2 py-2 text-right font-medium">实际用料</th>
                      <th class="px-2 py-2 text-left font-medium">啤机确认机台</th>
                      <th class="px-2 py-2 text-right font-medium">实际料费</th>
                      <th class="px-2 py-2 text-left font-medium">状态</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-slate-50">
                    <tr v-for="item in detailRows" :key="item.id" class="hover:bg-slate-50/60">
                      <td class="px-2 py-1.5 text-center text-slate-400">{{ item.sort_order }}</td>
                      <td class="px-2 py-1.5 font-mono">{{ item.mold_id }}</td>
                      <td class="px-2 py-1.5">{{ item.mold_name }}</td>
                      <td class="px-2 py-1.5">{{ item.material }}</td>
                      <td class="px-2 py-1.5">
                        <span class="inline-flex items-center gap-1">
                          <span class="h-2.5 w-2.5 rounded-full border border-slate-200" :class="getColorSwatchClass(item.color)" />
                          {{ item.color }}
                        </span>
                      </td>
                      <td class="px-2 py-1.5 text-right tabular-nums">{{ formatWeight(item.required_material_kg) }}</td>
                      <td class="px-2 py-1.5 text-right tabular-nums">{{ formatMoney(getExpectedMaterialAmountHkd(item)) }}</td>
                      <td class="px-2 py-1.5 text-right tabular-nums">{{ formatWeight(item.actual_weight_kg) }}</td>
                      <td class="px-2 py-1.5">{{ formatBlank(item.production_machine) }}</td>
                      <td class="px-2 py-1.5 text-right tabular-nums">{{ formatMoney(item.actual_amount_hkd) }}</td>
                      <td class="px-2 py-1.5">
                        <span class="rounded-full border px-2 py-0.5 text-[10px] font-bold" :class="getItemStateClass(item)">
                          {{ getItemState(item) }}
                        </span>
                      </td>
                    </tr>
                    <tr v-if="selectedItems.length > detailRows.length">
                      <td colspan="10" class="px-2 py-2 text-center text-[11px] font-medium text-slate-400">
                        还有 {{ selectedItems.length - detailRows.length }} 项明细，滚动后续详情视图继续查看
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <Transition
                enter-active-class="transition duration-200 ease-out"
                enter-from-class="-translate-y-2 opacity-0"
                enter-to-class="translate-y-0 opacity-100"
                leave-active-class="transition duration-150 ease-in"
                leave-from-class="translate-y-0 opacity-100"
                leave-to-class="-translate-y-2 opacity-0"
              >
                <div v-if="isSelectedOrderDataExpanded" class="border-t border-slate-100 bg-slate-50/70 p-4">
                  <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <h3 class="text-[13px] font-bold text-slate-950">完整单据数据</h3>
                      <p class="text-[11px] text-slate-500">单头资料与所有模具明细字段，供审核前完整核对。</p>
                    </div>
                    <span class="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[11px] font-semibold text-slate-500">
                      {{ selectedOrder.id }}
                    </span>
                  </div>

                  <div class="grid gap-2 text-[12px] md:grid-cols-3 xl:grid-cols-4">
                    <div class="rounded-lg border border-slate-200 bg-white px-3 py-2">
                      <div class="text-[10px] font-semibold text-slate-400">产品编号</div>
                      <div class="mt-0.5 font-semibold text-slate-900">{{ formatBlank(selectedOrder.order_number) }}</div>
                    </div>
                    <div class="rounded-lg border border-slate-200 bg-white px-3 py-2">
                      <div class="text-[10px] font-semibold text-slate-400">文件编号</div>
                      <div class="mt-0.5 font-semibold text-slate-900">{{ formatBlank(selectedOrder.doc_number) }}</div>
                    </div>
                    <div class="rounded-lg border border-slate-200 bg-white px-3 py-2">
                      <div class="text-[10px] font-semibold text-slate-400">产品 / 客户</div>
                      <div class="mt-0.5 font-semibold text-slate-900">{{ selectedOrder.product_name }} · {{ selectedOrder.client_name }}</div>
                    </div>
                    <div class="rounded-lg border border-slate-200 bg-white px-3 py-2">
                      <div class="text-[10px] font-semibold text-slate-400">状态 / 阶段 / 类型</div>
                      <div class="mt-0.5 font-semibold text-slate-900">{{ selectedOrder.status }} · {{ selectedOrder.stage || '待填写' }} · {{ selectedOrder.order_type }}</div>
                    </div>
                    <div class="rounded-lg border border-slate-200 bg-white px-3 py-2">
                      <div class="text-[10px] font-semibold text-slate-400">填写部 / 发至</div>
                      <div class="mt-0.5 font-semibold text-slate-900">{{ formatBlank(selectedOrder.workshop) }} / {{ formatBlank(selectedOrder.send_to, '内部') }}</div>
                    </div>
                    <div class="rounded-lg border border-slate-200 bg-white px-3 py-2">
                      <div class="text-[10px] font-semibold text-slate-400">工程 / 主管</div>
                      <div class="mt-0.5 font-semibold text-slate-900">{{ formatBlank(selectedOrder.eng_name) }} / {{ formatBlank(selectedOrder.supervisor) }}</div>
                    </div>
                    <div class="rounded-lg border border-slate-200 bg-white px-3 py-2">
                      <div class="text-[10px] font-semibold text-slate-400">开单 / 完成</div>
                      <div class="mt-0.5 font-semibold text-slate-900">{{ formatBlank(selectedOrder.date) }} / {{ formatBlank(selectedOrder.completed_date) }}</div>
                    </div>
                    <div class="rounded-lg border border-slate-200 bg-white px-3 py-2">
                      <div class="text-[10px] font-semibold text-slate-400">更新时间</div>
                      <div class="mt-0.5 font-semibold text-slate-900">{{ formatBlank(selectedOrder.updated_at) }}</div>
                    </div>
                  </div>

                  <div class="mt-3 rounded-lg border border-slate-200 bg-white px-3 py-2">
                    <div class="text-[10px] font-semibold text-slate-400">注意事项 / 开单事由</div>
                    <p class="mt-1 text-[12px] leading-5 text-slate-700">{{ formatBlank(selectedOrder.reason) }}</p>
                    <p v-if="selectedOrder.reject_reason" class="mt-1 text-[12px] leading-5 text-red-600">
                      驳回原因：{{ selectedOrder.reject_reason }}
                    </p>
                  </div>

                  <div class="mt-3 space-y-2">
                    <article
                      v-for="item in selectedItems"
                      :key="`full-${item.id}`"
                      class="rounded-lg border border-slate-200 bg-white p-3"
                    >
                      <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
                        <div class="font-semibold text-slate-950">
                          {{ item.sort_order }}. {{ item.mold_id }} · {{ item.mold_name }}
                        </div>
                        <span class="rounded-full border px-2 py-0.5 text-[10px] font-bold" :class="getItemStateClass(item)">
                          {{ getItemState(item) }}
                        </span>
                      </div>
                      <div class="grid gap-2 text-[12px] md:grid-cols-3 xl:grid-cols-4">
                        <div><span class="text-slate-400">工模尺寸</span><div class="font-semibold">{{ formatBlank(item.mold_dimensions) }}</div></div>
                        <div><span class="text-slate-400">适配机型</span><div class="font-semibold">{{ formatBlank(item.machine_type) }}</div></div>
                        <div><span class="text-slate-400">模具是否在厂</span><div class="font-semibold">{{ formatMoldPresenceStatus(item.mold_presence_status) }}</div></div>
                        <div><span class="text-slate-400">模具回厂时间</span><div class="font-semibold">{{ formatBlank(item.mold_return_time) }}</div></div>
                        <div><span class="text-slate-400">啤机确认机台</span><div class="font-semibold">{{ formatBlank(item.production_machine) }}</div></div>
                        <div><span class="text-slate-400">原料</span><div class="font-semibold">{{ formatBlank(item.material) }}</div></div>
                        <div><span class="text-slate-400">颜色 / PMS</span><div class="font-semibold">{{ formatBlank(item.color) }} / {{ formatBlank(item.pigment_no) }}</div></div>
                        <div><span class="text-slate-400">数量 / 啤数</span><div class="font-semibold">{{ formatBlank(item.quantity) }} / {{ formatBlank(item.shoot_qty) }}</div></div>
                        <div><span class="text-slate-400">整啤毛重(g)</span><div class="font-semibold">{{ formatGram(item.gross_weight_g) }}</div></div>
                        <div><span class="text-slate-400">预计用料</span><div class="font-semibold">{{ formatWeight(item.required_material_kg) }}</div></div>
                        <div><span class="text-slate-400">预计料费(HKD)</span><div class="font-semibold">{{ formatMoney(getExpectedMaterialAmountHkd(item)) }}</div></div>
                        <div><span class="text-slate-400">回模 / 完成时间</span><div class="font-semibold">{{ formatBlank(item.mold_return_time) }} / {{ formatBlank(item.completion_time) }}</div></div>
                        <div><span class="text-slate-400">领料重量</span><div class="font-semibold">{{ formatWeight(item.collected_weight_kg) }}</div></div>
                        <div><span class="text-slate-400">实际用料</span><div class="font-semibold">{{ formatWeight(item.actual_weight_kg) }}</div></div>
                        <div><span class="text-slate-400">实际料费(HKD)</span><div class="font-semibold">{{ formatMoney(item.actual_amount_hkd) }}</div></div>
                        <div><span class="text-slate-400">啤办费(RMB)</span><div class="font-semibold">{{ formatMoney(item.injection_cost, 'RMB') }}</div></div>
                        <div><span class="text-slate-400">啤办费(HKD)</span><div class="font-semibold">{{ formatMoney(item.injection_cost_hkd) }}</div></div>
                        <div><span class="text-slate-400">{{ getExchangeRateLabel(item) }}</span><div class="font-semibold">{{ formatExchangeRate(item.exchange_rate_at_save) }}</div></div>
                      </div>
                      <p class="mt-2 rounded-md bg-slate-50 px-2 py-1.5 text-[12px] leading-5 text-slate-600">
                        备注：{{ formatBlank(item.notes) }}
                      </p>
                    </article>
                  </div>
                </div>
              </Transition>
            </section>

            <section class="rounded-lg border border-slate-200 bg-white p-4">
              <div class="mb-1.5 flex items-center gap-2">
                <MessageSquareText class="size-4 text-slate-400" aria-hidden="true" />
                <span class="text-[13px] font-bold">开单事由</span>
              </div>
              <p class="text-[12.5px] text-slate-600">{{ selectedOrder.reason }}</p>
            </section>

            <section class="rounded-lg border border-slate-200 bg-white p-4">
              <div class="mb-3 flex items-center justify-between gap-3">
                <div class="flex items-center gap-2">
                  <TriangleAlert class="size-4 text-red-500" aria-hidden="true" />
                  <span class="text-[13px] font-bold">生产问题反馈</span>
                </div>
                <span class="rounded-full bg-red-50 px-2 py-0.5 text-[11px] font-semibold text-red-600">
                  {{ selectedProblems.length }} 条
                </span>
              </div>
              <div v-if="selectedProblems.length" class="space-y-2">
                <article
                  v-for="problem in selectedProblems"
                  :key="problem.id"
                  class="rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-[12px] text-red-800"
                >
                  <div class="flex flex-wrap items-center justify-between gap-2">
                    <span class="font-semibold">{{ problem.status }} · {{ problem.reported_by }}</span>
                    <span class="text-[11px] text-red-500">{{ problem.created_at }}</span>
                  </div>
                  <p class="mt-1 leading-5">{{ problem.description }}</p>
                </article>
              </div>
              <p v-else class="text-[12px] text-slate-400">
                暂无啤机部反馈问题。
              </p>
            </section>
          </div>

          <aside class="space-y-4">
            <section
              class="rounded-lg border-2 p-4"
              :class="selectedOrder.status === '待审核' || selectedOrder.status === '待经理审核' ? 'border-amber-200 bg-amber-50/50' : 'border-slate-200 bg-white'"
            >
              <form @submit.prevent="runApprovalTransition('通过')">
                <div class="flex items-center gap-2">
                <Gavel class="size-4 text-amber-600" aria-hidden="true" />
                <span class="text-[13px] font-bold" :class="selectedOrder.status === '待审核' || selectedOrder.status === '待经理审核' ? 'text-amber-800' : 'text-slate-800'">
                  {{ selectedOrder.status === '待审核' ? `${selectedOrder.supervisor} · 待审核` : selectedOrder.status === '待经理审核' ? '历史经理节点 · 待处理' : '当前无需工程审核' }}
                </span>
                </div>
                <p class="mt-1 text-[11px]" :class="selectedOrder.status === '待审核' || selectedOrder.status === '待经理审核' ? 'text-amber-700' : 'text-slate-500'">
                  {{ selectedOrder.status === '待审核' ? '核对单头、明细、交期后执行操作。内部单进入待生产，外厂 / 模厂路径直接完成。' : selectedOrder.status === '待经理审核' ? '历史单据仍保留经理终审兼容，处理后继续流转到后续节点。' : '该单据当前处于后续生产或归档节点。' }}
                </p>
                <textarea
                v-model="approvalNote"
                rows="2"
                placeholder="审核意见（驳回必填）..."
                class="mt-3 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[12px] outline-none focus:border-slate-400"
                />
                <div class="mt-2 flex gap-2">
                  <button
                  type="submit"
                  :disabled="!canApproveSelectedOrder || approvalSubmitting"
                  class="flex h-10 flex-1 items-center justify-center gap-1.5 rounded-lg bg-emerald-600 text-[13px] font-semibold text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:bg-slate-300"
                  >
                    <Check class="size-4" aria-hidden="true" />
                    {{ approvalSubmitting ? '提交中...' : '通过' }}
                  </button>
                  <button
                  type="button"
                  :disabled="!canApproveSelectedOrder || approvalSubmitting"
                  class="flex h-10 flex-1 items-center justify-center gap-1.5 rounded-lg bg-red-600 text-[13px] font-semibold text-white hover:bg-red-500 disabled:cursor-not-allowed disabled:bg-slate-300"
                  @click="runApprovalTransition('驳回')"
                  >
                    <X class="size-4" aria-hidden="true" />
                    驳回
                  </button>
                </div>
              </form>
            </section>

            <section class="rounded-lg border border-slate-200 bg-white p-4">
              <div class="mb-3 flex items-center gap-2">
                <History class="size-4 text-slate-400" aria-hidden="true" />
                <span class="text-[13px] font-bold">审核轨迹</span>
              </div>
              <ol class="relative space-y-4 border-l border-slate-200 pl-4">
                <li v-for="log in selectedAuditLogs" :key="log.id" class="relative">
                  <span class="absolute -left-[21px] top-0.5 flex h-3.5 w-3.5 rounded-full bg-teal-400 ring-4 ring-white" />
                  <div class="text-[12px] font-semibold">{{ log.action }}</div>
                  <div class="text-[11px] text-slate-400">{{ log.actor_name }} · {{ log.actor_role }} · {{ log.created_at }}</div>
                  <div class="mt-1 rounded-md bg-slate-50 px-2 py-1 text-[11px] text-slate-500">{{ log.reason }}</div>
                </li>
                <li v-if="!selectedAuditLogs.length" class="relative">
                  <span class="absolute -left-[21px] top-0.5 flex h-3.5 w-3.5 rounded-full bg-slate-200 ring-4 ring-white" />
                  <div class="text-[12px] font-semibold text-slate-400">暂无轨迹</div>
                </li>
              </ol>
            </section>
          </aside>
        </div>
      </section>

      <section v-else class="rounded-lg border border-slate-200 bg-white p-8 text-center">
        <p class="text-base font-semibold text-slate-950">
          {{ apiState === 'error' ? '正式数据读取失败' : '当前厂区暂无正式啤办单' }}
        </p>
        <p class="mt-2 text-sm text-slate-500">
          {{ apiState === 'error' ? '不会显示本地示例单据，请修复登录权限、接口或网络后刷新正式列表。' : '可以先在“工程部 · 新建开单”提交一张新啤办单，提交成功后会进入正式看板。' }}
        </p>
        <button
          type="button"
          class="mt-5 inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
          :disabled="!canManageSelectedFactory"
          @click="startCreateOrder"
        >
          <Plus class="size-4" aria-hidden="true" />
          新建啤办单
        </button>
      </section>
    </div>

    <section
      class="molding-sample-print-root hidden"
      data-testid="molding-sample-print-area"
      aria-label="啤办单打印内容"
    >
      <article
        v-for="record in printableRecords"
        :key="record.order.id"
        class="molding-sample-print-page"
      >
        <div class="molding-sample-print-statusband">
          <span class="molding-sample-print-statuspill">{{ record.order.status }}</span>
          <span>{{ record.order.stage || '待填写' }} 阶段 · {{ formatBlank(record.order.send_to, '内部') }} · {{ record.order.order_type }}</span>
          <span class="molding-sample-print-statuscount">共 {{ record.items.length }} 条模具明细</span>
        </div>

        <header class="molding-sample-print-header">
          <div class="molding-sample-print-brand">Royal Regent Nexus</div>
          <div>
            <div class="molding-sample-print-title">工程啤办通知单</div>
            <div class="molding-sample-print-subtitle">Molding Sample Order</div>
          </div>
          <div class="molding-sample-print-docno">
            <span>单据编号</span>
            <strong>{{ record.order.id }}</strong>
          </div>
        </header>

        <section class="molding-sample-print-section">
          <div class="molding-sample-print-section-title">单据资料</div>
          <table class="molding-sample-print-meta-table" aria-label="单据资料">
            <tbody>
              <tr>
                <th>订单号</th>
                <td>{{ formatBlank(record.order.order_number) }}</td>
                <th>文件编号</th>
                <td>{{ formatBlank(record.order.doc_number) }}</td>
              </tr>
              <tr>
                <th>产品 / 客户</th>
                <td>{{ formatBlank(record.order.product_name) }} / {{ formatBlank(record.order.client_name) }}</td>
                <th>状态</th>
                <td>{{ record.order.status }} · {{ record.order.stage || '待填写' }} · {{ record.order.order_type }}</td>
              </tr>
              <tr>
                <th>填写部 / 发至</th>
                <td>{{ formatBlank(record.order.workshop) }} / {{ formatBlank(record.order.send_to, '内部') }}</td>
                <th>工程 / 主管</th>
                <td>{{ formatBlank(record.order.eng_name) }} / {{ formatBlank(record.order.supervisor) }}</td>
              </tr>
              <tr>
                <th>开单 / 完成</th>
                <td>{{ formatBlank(record.order.date) }} / {{ formatBlank(record.order.completed_date) }}</td>
                <th>最近更新</th>
                <td>{{ formatBlank(record.order.updated_at) }}</td>
              </tr>
            </tbody>
          </table>
        </section>

        <section class="molding-sample-print-section">
          <div class="molding-sample-print-section-title">开单事由</div>
          <div class="molding-sample-print-reason">{{ formatBlank(record.order.reason) }}</div>
        </section>

        <section class="molding-sample-print-section">
          <div class="molding-sample-print-section-title">模具明细（一行一模具，节省纸张）</div>
          <div v-if="!record.items.length" class="molding-sample-print-empty">暂无明细</div>
          <table
            v-else
            class="molding-sample-print-detail-table"
            aria-label="模具明细"
          >
            <colgroup>
              <col class="molding-sample-print-col-index">
              <col class="molding-sample-print-col-mold">
              <col class="molding-sample-print-col-material">
              <col class="molding-sample-print-col-machine">
              <col class="molding-sample-print-col-color">
              <col class="molding-sample-print-col-pigment">
              <col class="molding-sample-print-col-shot">
              <col class="molding-sample-print-col-date">
              <col class="molding-sample-print-col-cost">
              <col class="molding-sample-print-col-notes">
            </colgroup>
            <thead>
              <tr>
                <th>#</th>
                <th>模号 / 名称</th>
                <th>原料</th>
                <th>啤机确认机台</th>
                <th>颜色 / PMS</th>
                <th>色粉</th>
                <th>啤数 / 预料</th>
                <th>回模 / 完成</th>
                <th>回填 / 费用</th>
                <th>备注</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in record.items" :key="item.id">
                <td class="molding-sample-print-index">{{ item.sort_order }}</td>
                <td>
                  <strong>{{ formatBlank(item.mold_id) }}</strong>
                  <span>{{ formatBlank(item.mold_name) }}</span>
                  <span>工模尺寸：{{ formatBlank(item.mold_dimensions) }}</span>
                  <span>适配机型：{{ formatBlank(item.machine_type) }}</span>
                  <span>模具是否在厂：{{ formatMoldPresenceStatus(item.mold_presence_status) }}</span>
                  <span>模具回厂时间：{{ formatBlank(item.mold_return_time) }}</span>
                  <em>{{ formatBlank(item.id) }}</em>
                </td>
                <td>{{ formatBlank(item.material) }}</td>
                <td>{{ formatBlank(item.production_machine) }}</td>
                <td>
                  <strong>{{ formatBlank(item.color) }}</strong>
                  <span>PMS {{ formatBlank(item.pigment_no) }}</span>
                </td>
                <td>{{ formatBlank(item.pigment_no) }}</td>
                <td>
                  <strong>{{ formatBlank(item.quantity) }} / {{ formatBlank(item.shoot_qty) }}</strong>
                  <span>{{ formatWeight(item.required_material_kg) }}</span>
                  <span>预计料费 {{ formatMoney(getExpectedMaterialAmountHkd(item)) }}</span>
                  <em>{{ formatGram(item.gross_weight_g) }}</em>
                </td>
                <td>{{ formatBlank(item.mold_return_time) }} / {{ formatBlank(item.completion_time) }}</td>
                <td>
                  <strong>{{ formatWeight(item.actual_weight_kg) }}</strong>
                  <span>{{ formatMoney(item.actual_amount_hkd) }} · {{ formatMoney(item.injection_cost, 'RMB') }}</span>
                  <em>{{ formatMoney(item.injection_cost_hkd) }} · {{ formatExchangeRate(item.exchange_rate_at_save) }}</em>
                </td>
                <td>{{ formatBlank(item.notes) }}</td>
              </tr>
            </tbody>
          </table>
        </section>

        <section class="molding-sample-print-signatures" aria-label="签核栏">
          <div class="molding-sample-print-signature-title">签核栏</div>
          <div class="molding-sample-print-signature-cell">
            <strong>经办确认</strong>
            <span>签名 / 日期</span>
          </div>
          <div class="molding-sample-print-signature-cell">
            <strong>主管审核</strong>
            <span>签名 / 日期</span>
          </div>
          <div class="molding-sample-print-signature-cell">
            <strong>啤机确认</strong>
            <span>签名 / 日期</span>
          </div>
        </section>

        <div class="molding-sample-print-footwrap">
          <footer class="molding-sample-print-footer">
            本单据由 Royal Regent Nexus 生成。打印前请核对单据资料、模具明细、用料及费用回填。
          </footer>
          <div class="molding-sample-print-qr">扫码<br>查看单据</div>
          <div class="molding-sample-print-pageno">第 1 / 1 页</div>
        </div>
      </article>
    </section>
  </main>
</template>

<style>
@media print {
  @page {
    size: A4 portrait;
    margin: 12mm 10mm;
  }

  html,
  body {
    background: #fff !important;
  }

  body * {
    visibility: hidden;
  }

  .molding-sample-print-root,
  .molding-sample-print-root * {
    visibility: visible;
  }

  .molding-sample-print-root {
    display: block !important;
    position: absolute;
    inset: 0;
    width: 100%;
    background: white;
    color: #111827;
    padding: 0;
    font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif;
    font-size: 10.5pt;
    line-height: 1.45;
  }

  .molding-sample-print-page {
    break-after: page;
    page-break-after: always;
    min-height: 266mm;
  }

  .molding-sample-print-page:last-child {
    break-after: auto;
    page-break-after: auto;
  }

  .molding-sample-print-statusband {
    display: flex;
    align-items: center;
    gap: 3mm;
    margin-bottom: 4mm;
    padding: 2.4mm 5mm;
    background: linear-gradient(90deg, #0f766e, #14b8a6) !important;
    color: #fff;
    font-size: 9pt;
  }

  .molding-sample-print-statuspill {
    display: inline-flex;
    align-items: center;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.22) !important;
    padding: 0.8mm 3mm;
    font-weight: 800;
  }

  .molding-sample-print-statuscount {
    margin-left: auto;
    white-space: nowrap;
  }

  .molding-sample-print-header {
    display: grid;
    grid-template-columns: 1fr 1.5fr 1fr;
    align-items: end;
    gap: 12mm;
    border-bottom: 2px solid #111827;
    padding-bottom: 4mm;
    margin-bottom: 5mm;
  }

  .molding-sample-print-brand {
    font-size: 10pt;
    font-weight: 700;
    letter-spacing: 0;
    text-transform: uppercase;
  }

  .molding-sample-print-title {
    text-align: center;
    font-size: 20pt;
    font-weight: 800;
    letter-spacing: 0;
  }

  .molding-sample-print-subtitle {
    margin-top: 1mm;
    text-align: center;
    font-size: 8.5pt;
    color: #4b5563;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .molding-sample-print-docno {
    text-align: right;
    font-size: 9pt;
  }

  .molding-sample-print-docno span {
    display: block;
    color: #4b5563;
  }

  .molding-sample-print-docno strong {
    display: block;
    margin-top: 1mm;
    font-size: 12pt;
    color: #111827;
  }

  .molding-sample-print-section {
    margin-top: 4mm;
    break-inside: avoid;
    page-break-inside: avoid;
  }

  .molding-sample-print-section-title {
    display: flex;
    align-items: center;
    gap: 2mm;
    margin-bottom: 1.8mm;
    font-size: 10pt;
    font-weight: 800;
    color: #111827;
  }

  .molding-sample-print-section-title::before {
    content: "";
    display: block;
    width: 3mm;
    height: 3mm;
    border: 1px solid #111827;
  }

  .molding-sample-print-meta-table,
  .molding-sample-print-detail-table {
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
  }

  .molding-sample-print-meta-table th,
  .molding-sample-print-meta-table td,
  .molding-sample-print-detail-table th,
  .molding-sample-print-detail-table td {
    border: 1px solid #9ca3af;
    padding: 2mm 2.3mm;
    vertical-align: top;
    word-break: break-word;
  }

  .molding-sample-print-meta-table th {
    width: 19mm;
    background: #f3f4f6 !important;
    color: #374151;
    font-weight: 700;
    text-align: left;
  }

  .molding-sample-print-meta-table td {
    width: 72mm;
  }

  .molding-sample-print-reason,
  .molding-sample-print-empty {
    min-height: 14mm;
    border: 1px solid #9ca3af;
    padding: 2.5mm 3mm;
    color: #111827;
  }

  .molding-sample-print-empty {
    text-align: center;
    color: #6b7280;
  }

  .molding-sample-print-detail-table {
    margin-bottom: 3mm;
    font-size: 7.8pt;
    break-inside: avoid;
    page-break-inside: avoid;
  }

  .molding-sample-print-col-index {
    width: 5%;
  }

  .molding-sample-print-col-mold {
    width: 16%;
  }

  .molding-sample-print-col-material {
    width: 10%;
  }

  .molding-sample-print-col-machine {
    width: 10%;
  }

  .molding-sample-print-col-color {
    width: 11%;
  }

  .molding-sample-print-col-pigment {
    width: 8%;
  }

  .molding-sample-print-col-shot {
    width: 9%;
  }

  .molding-sample-print-col-date {
    width: 10%;
  }

  .molding-sample-print-col-cost {
    width: 13%;
  }

  .molding-sample-print-col-notes {
    width: 8%;
  }

  .molding-sample-print-detail-table thead th {
    background: #0f172a !important;
    color: #fff;
    font-size: 7.4pt;
    font-weight: 800;
    text-align: center;
    white-space: nowrap;
  }

  .molding-sample-print-detail-table tbody td {
    color: #111827;
    padding: 1.6mm 1.7mm;
  }

  .molding-sample-print-detail-table tbody tr:nth-child(even) td {
    background: #f8fafc !important;
  }

  .molding-sample-print-detail-table strong,
  .molding-sample-print-detail-table span,
  .molding-sample-print-detail-table em {
    display: block;
    font-style: normal;
  }

  .molding-sample-print-detail-table strong {
    font-weight: 800;
  }

  .molding-sample-print-detail-table span {
    color: #475569;
  }

  .molding-sample-print-detail-table em {
    color: #64748b;
    font-size: 7.1pt;
  }

  .molding-sample-print-index {
    text-align: center;
    color: #64748b !important;
    font-variant-numeric: tabular-nums;
  }

  .molding-sample-print-signatures {
    display: grid;
    grid-template-columns: 24mm repeat(3, 1fr);
    margin-top: 6mm;
    border: 1px solid #111827;
    break-inside: avoid;
    page-break-inside: avoid;
  }

  .molding-sample-print-signature-title,
  .molding-sample-print-signature-cell {
    min-height: 18mm;
    border-right: 1px solid #111827;
    padding: 2mm 3mm;
  }

  .molding-sample-print-signature-title {
    display: flex;
    align-items: center;
    justify-content: center;
    background: #f3f4f6 !important;
    font-weight: 800;
  }

  .molding-sample-print-signature-cell {
    display: flex;
    flex-direction: column;
    justify-content: space-between;
  }

  .molding-sample-print-signature-cell:last-child {
    border-right: 0;
  }

  .molding-sample-print-signature-cell strong {
    font-size: 9.5pt;
  }

  .molding-sample-print-signature-cell span {
    color: #6b7280;
    font-size: 8.5pt;
  }

  .molding-sample-print-footwrap {
    display: flex;
    align-items: flex-end;
    gap: 4mm;
    margin-top: 4mm;
  }

  .molding-sample-print-footer {
    flex: 1;
    color: #6b7280;
    font-size: 8.5pt;
  }

  .molding-sample-print-qr {
    display: flex;
    width: 16mm;
    height: 16mm;
    align-items: center;
    justify-content: center;
    border: 1px dashed #94a3b8;
    border-radius: 1.6mm;
    color: #94a3b8;
    font-size: 7pt;
    line-height: 1.2;
    text-align: center;
  }

  .molding-sample-print-pageno {
    color: #64748b;
    font-size: 8pt;
    white-space: nowrap;
  }
}
</style>
