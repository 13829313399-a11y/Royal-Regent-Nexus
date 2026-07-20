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
  RefreshCw,
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
import { RouterLink, useRoute, useRouter } from 'vue-router'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import MoldingSampleTrialReportDialog from '@/components/molding/MoldingSampleTrialReportDialog.vue'
import {
  factoryContexts,
  getFactoryScopedRoute,
  isProductionFactoryContextId,
  type ProductionFactoryContextId,
} from '@/data/enterpriseMock'
import {
  buildCompletionGate,
  calculateMaterialCostBreakdown,
  calculateExpectedMaterialAmountHkd,
  countMoldingSampleAttentionMetrics,
  formatMaterialComposition,
  isExternalMoldingSampleOrder,
  normalizeMaterialComponents,
  resolveActualMaterialCostBreakdown,
  resolveMaterialPrice,
  resolveMaterialComponents,
  roundMoney,
} from '@/lib/moldingSampleBusiness'
import {
  matchesMoldingSampleSearch,
  tokenizeMoldingSampleSearchKeyword,
} from '@/lib/moldingSampleSearch'
import {
  getAllowedMoldingSampleProductionFactoryIds,
  getMoldingSampleFactoryCapability,
  getMoldingSampleFactoryLabel,
  getSuggestedMoldingSampleProductionFactoryId,
  resolveMoldingSampleProductionFactoryId,
  validateMoldingSampleProductionAssignment,
} from '@/lib/moldingSampleFactoryCapabilities'
import { getApiErrorMessage } from '@/lib/http'
import { formatBusinessDate, formatBusinessDateTime } from '@/lib/dateTime'
import {
  MOLDING_SAMPLE_XLSX_MIME,
  moldingSampleApi,
  type MoldingSampleBoardPageResponse,
  type MoldingSampleBoardSummaryResponse,
  type MoldingSampleCreateRequest,
  type MoldingSampleDetailResponse,
  type MoldingSampleStatusRequest,
} from '@/api/moldingSample'
import { rawMaterialApi, type RawMaterialResponse } from '@/api/rawMaterial'
import {
  buildManualMoldingSampleCreateRequest,
  createManualMoldingSampleMaterialComponentDraft,
  createManualMoldingSampleLineDraft,
  createManualMoldingSampleOrderDraft,
  createSingleManualMaterialComponentDraft,
  deriveManualMoldingSampleOrderId,
  type ManualMoldingSampleMaterialComponentDraft,
  type ManualMoldingSampleLineDraft,
  type ManualMoldingSampleOrderDraft,
} from '@/lib/moldingSampleManualCreate'
import type {
  MoldingSampleItem,
  MoldingSampleMaterialComponent,
  MoldingSampleMaterialSource,
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
  key: string
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
  loading: boolean
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
  isTrial: boolean
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
  trialItemCount: number
}

interface MaterialBalanceSummary {
  orderCount: number
  totalExpectedWeightKg: number
  totalActualWeightKg: number
  totalBalanceWeightKg: number
  knownBalanceAmountHkd: number
  unknownAmountCount: number
  trialItemCount: number
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
  trialItemCount: number
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
const router = useRouter()
const appStore = useAppStore()
const authStore = useAuthStore()

function getTodayText(date = new Date()) {
  return formatBusinessDate(date.toISOString(), '')
}

const activeView = ref<ViewKey>('overview')
const overviewDisplayMode = ref<OverviewDisplayMode>('board')
const materialBalancePeriodMode = ref<MaterialBalancePeriodMode>('day')
const selectedOrderId = ref(readQueryString(route.query.order_id))
const selectedBatchOrderIds = ref<string[]>([])
const printableRecords = ref<MoldingSampleWorkflowRecord[]>([])
const printPreviewVisible = ref(false)
const engineeringTrialReportHistoryVisible = ref(false)
const engineeringTrialReportItemId = ref('')
const searchKeyword = ref('')
const effectiveSearchKeyword = ref('')
const overviewListPage = ref(1)
const boardPageByStatus = ref<Partial<Record<MoldingSampleStatus, number>>>({})
const boardSummary = ref<MoldingSampleBoardSummaryResponse | null>(null)
const boardPagesByStatus = ref<Partial<Record<MoldingSampleStatus, MoldingSampleBoardPageResponse>>>({})
const boardLoadingByStatus = ref<Partial<Record<MoldingSampleStatus, boolean>>>({})
const serverBoardEnabled = ref(false)
const legacyOrdersLoaded = ref(false)
const legacyOrdersLoading = ref(false)
const materialBalancePeriodPage = ref(1)
const materialBalanceDetailPage = ref(1)
const apiRecords = ref<MoldingSampleDetailResponse[]>([])
const apiState = ref<'checking' | 'connected' | 'empty' | 'error'>('checking')
const actionMessage = ref('正在读取正式啤办单列表...')
const actionToastVisible = ref(true)
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
const dispatchProductionFactoryId = ref('')
const dispatchReason = ref('')
const dispatchSubmitting = ref(false)
const excelFileInput = ref<HTMLInputElement | null>(null)
const excelImporting = ref(false)
const excelExporting = ref(false)
const excelTemplateDownloading = ref(false)
const excelAccept = `${MOLDING_SAMPLE_XLSX_MIME},.xlsx`
const createLineGridClass = 'grid-cols-[40px_132px_142px_210px_120px_124px_74px_96px_82px_92px_118px_138px_150px_130px_118px_160px_72px]'
const createDraftStoragePrefix = 'rr:molding-sample:create-draft'
const RAW_MATERIAL_PICKER_WIDTH = 360
const RAW_MATERIAL_PICKER_HEIGHT = 256
const RAW_MATERIAL_PICKER_GAP = 8
const RAW_MATERIAL_PICKER_VIEWPORT_PADDING = 12
const rawMaterialPriceList = ref<Awaited<ReturnType<typeof moldingSampleApi.getMaterialPrices>>['prices']>([])
const rawMaterialMasterList = ref<RawMaterialResponse[]>([])
const RAW_MATERIAL_PICKER_VISIBLE_LIMIT = 60
const activeRawMaterialPickerLineIndex = ref<number | null>(null)
const rawMaterialSearchByLine = ref<Record<number, string>>({})
const rawMaterialPickerPositionByLine = ref<Record<number, RawMaterialPickerPosition>>({})
const materialCompositionLineIndex = ref<number | null>(null)
const materialCompositionDraftRows = ref<ManualMoldingSampleMaterialComponentDraft[]>([])
const materialCompositionError = ref('')
let createSuccessToastTimer: ReturnType<typeof setTimeout> | null = null
let actionToastTimer: ReturnType<typeof setTimeout> | null = null
let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null
let legacyOrdersLoadPromise: Promise<void> | null = null
let boardOverviewRequestId = 0
let legacyOrdersRequestId = 0
let deepLinkedOrderRequestId = 0
let protectedMaterialPricesRequestId = 0
let rawMaterialOptionsRequestId = 0
let excelImportRequestId = 0
let manualCreateMutationRequestId = 0
let productionAssignmentRequestId = 0
const boardPageRequestIds: Partial<Record<MoldingSampleStatus, number>> = {}

const materialCompositionPercentageTotal = computed(() => roundMaterialWeight(
  materialCompositionDraftRows.value.reduce((total, row) => total + (Number(row.ratio_percent) || 0), 0),
))

const workflowSteps: WorkflowStep[] = [
  { status: '待审核', title: '主管审核', detail: '工程提交后进入主管队列' },
  { status: '待生产', title: '待生产', detail: '主管通过后流转到啤机部' },
  { status: '生产中', title: '啤机生产', detail: '回填实际用料和确认机台' },
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

const MOLDING_SAMPLE_BOARD_PAGE_SIZE = 5
const MOLDING_SAMPLE_PAGE_SIZE = 10
const MOLDING_SAMPLE_SEARCH_DEBOUNCE_MS = 275
const MOLDING_SAMPLE_DISPATCHABLE_STATUSES = new Set<MoldingSampleStatus>([
  '待审核',
  '待经理审核',
  '已驳回',
  '已撤回',
  '待生产',
])

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
const activeFactoryCapability = computed(() =>
  getMoldingSampleFactoryCapability(selectedFactoryId.value),
)
const createDraftIsExternal = computed(() => isExternalCreateDraft(createDraft.value))
const allowedCreateProductionFactoryIds = computed(() =>
  getAllowedMoldingSampleProductionFactoryIds(selectedFactoryId.value),
)
const engineeringDepartmentRoute = computed(() => getFactoryScopedRoute(
  '/modules/engineering',
  selectedFactoryId.value,
))

const rawMaterialOptions = computed<RawMaterialSelectOption[]>(() => {
  const seenValues = new Set<string>()

  return rawMaterialMasterList.value.flatMap((row) => {
    const value = row.material_name.trim()

    if (!value || row.status !== '启用' || seenValues.has(value)) {
      return []
    }

    seenValues.add(value)

    const sourceParts = [row.material_code, row.category].filter(Boolean)
    const label = sourceParts.length ? `${value}（${sourceParts.join(' / ')}）` : value
    const searchText = [
      value,
      label,
      row.material_code,
      row.category,
      row.spec,
      row.supplier,
      row.notes,
    ].join(' ').toLowerCase()

    return [{
      value,
      label,
      code: row.material_code,
      category: row.category,
      origin: row.supplier,
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
  const productionFactoryId = selectedRecord.value
    ? resolveMoldingSampleProductionFactoryId(selectedRecord.value.order)
    : selectedFactoryId.value
  const params = new URLSearchParams({ factory: productionFactoryId ?? selectedFactoryId.value })

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
  const searchTokens = tokenizeMoldingSampleSearchKeyword(effectiveSearchKeyword.value)

  if (!searchTokens.length) {
    return factoryRecords.value
  }

  return factoryRecords.value.filter((record) => matchesMoldingSampleSearch(record, searchTokens))
})

const overviewOperationRecordCount = computed(() =>
  serverBoardEnabled.value && overviewDisplayMode.value === 'board'
    ? boardSummary.value?.total ?? visibleRecords.value.length
    : visibleRecords.value.length,
)

const overviewListPagination = computed(() =>
  createPaginationState(visibleRecords.value, overviewListPage.value),
)
const paginatedVisibleRecords = computed(() => overviewListPagination.value.rows)

const selectedRecord = computed<MoldingSampleWorkflowRecord | null>(() => {
  const selected = visibleRecords.value.find((record) => record.order.id === selectedOrderId.value)
    ?? factoryRecords.value.find((record) => record.order.id === selectedOrderId.value)

  if (selectedOrderId.value) {
    return selected ?? null
  }

  return factoryRecords.value[0] ?? null
})

const selectedBatchOrderIdSet = computed(() => new Set(selectedBatchOrderIds.value))
const batchSelectableRecords = computed(() => {
  if (serverBoardEnabled.value && overviewDisplayMode.value === 'board') {
    return Object.values(boardPagesByStatus.value)
      .flatMap((page) => page?.rows ?? [])
      .map(toWorkflowRecord)
  }

  return visibleRecords.value
})
const selectedBatchRecords = computed(() =>
  batchSelectableRecords.value.filter((record) => selectedBatchOrderIdSet.value.has(record.order.id)),
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
  batchSelectableRecords.value.length > 0
  && batchSelectableRecords.value.every((record) => selectedBatchOrderIdSet.value.has(record.order.id)),
)

const selectedOrder = computed<MoldingSampleOrder>(() => selectedRecord.value?.order ?? createEmptySelectedOrder())
const selectedItems = computed(() => selectedRecord.value?.items ?? [])
const selectedProblems = computed(() => selectedRecord.value?.problems ?? [])
const selectedAuditLogs = computed(() => selectedRecord.value?.audit_logs ?? [])
const selectedDispatchLogs = computed(() => selectedRecord.value?.dispatch_logs ?? [])
const selectedApiRecord = computed(() =>
  apiRecords.value.find((record) => record.order.id === selectedOrderId.value) ?? null,
)
const selectedProductionStartAudit = computed(() => {
  if (!['生产中', '已完成'].includes(selectedOrder.value.status)) return null
  return getLatestAuditLog('开始处理')
})
const selectedProductionCompleteAudit = computed(() => {
  if (selectedOrder.value.status !== '已完成') return null
  return getLatestAuditLog('标记完成')
})
const selectedLatestNotification = computed(() => {
  const notifications = selectedApiRecord.value?.notifications ?? []
  return [...notifications].sort((left, right) => right.created_at.localeCompare(left.created_at))[0] ?? null
})
const selectedTrialReports = computed(() => selectedRecord.value?.trial_reports ?? [])
const selectedCompletionGate = computed(() => selectedRecord.value
  ? buildCompletionGate(selectedOrder.value, selectedItems.value)
  : { can_complete: false, missing_item_ids: [], message: '暂无正式单据' },
)
const isSelectedExternal = computed(() => selectedRecord.value ? isExternalMoldingSampleOrder(selectedOrder.value) : false)
const selectedFactoryCapability = computed(() =>
  getMoldingSampleFactoryCapability(selectedOrder.value.factory_id),
)
const selectedProductionFactoryId = computed(() =>
  resolveMoldingSampleProductionFactoryId(selectedOrder.value),
)
const selectedProductionRouteLabel = computed(() => getProductionRouteLabel(selectedOrder.value))
const isSelectedOrderCrossFactoryDispatch = computed(() =>
  selectedFactoryCapability.value?.dispatchMode === 'cross-factory' && !isSelectedExternal.value,
)
const isSelectedOrderDispatchable = computed(() =>
  MOLDING_SAMPLE_DISPATCHABLE_STATUSES.has(selectedOrder.value.status),
)

const kpiCards = computed<KpiCard[]>(() => {
  const records = visibleRecords.value
  const useServerSummary = serverBoardEnabled.value
    && overviewDisplayMode.value === 'board'
    && boardSummary.value !== null
  const summary = useServerSummary ? boardSummary.value : null
  const reviewCount = summary?.review_count
    ?? records.filter((record) => ['待审核', '待经理审核'].includes(record.order.status)).length
  const productionCount = summary?.production_count
    ?? records.filter((record) => ['待生产', '生产中'].includes(record.order.status)).length
  const completedCount = summary?.completed_count
    ?? records.filter((record) => record.order.status === '已完成').length
  const localAttentionMetrics = countMoldingSampleAttentionMetrics(records)
  const attentionMetrics = {
    rejectedCount: summary?.rejected_count ?? localAttentionMetrics.rejectedCount,
    withdrawnCount: summary?.withdrawn_count ?? localAttentionMetrics.withdrawnCount,
    unresolvedProblemCount: summary?.unresolved_problem_count ?? localAttentionMetrics.unresolvedProblemCount,
    productionDataPendingCount: summary?.production_data_pending_count ?? localAttentionMetrics.productionDataPendingCount,
  }

  return [
    {
      key: 'factory-orders',
      label: '当前厂区单据',
      value: String(summary?.total ?? records.length),
      detail: `${activeFactory.value.shortName} · 按状态分列`,
      icon: Layers,
      className: 'border-slate-200 text-slate-700',
    },
    {
      key: 'in-review',
      label: '审核中',
      value: String(reviewCount),
      detail: '主管节点',
      icon: Clock,
      className: 'border-amber-200/80 text-amber-700',
    },
    {
      key: 'production-queue',
      label: '待啤机处理',
      value: String(productionCount),
      detail: '待生产 / 生产中',
      icon: Factory,
      className: 'border-teal-200/80 text-teal-700',
    },
    {
      key: 'completed',
      label: '已完成',
      value: String(completedCount),
      detail: '完成归档回传',
      icon: CheckCheck,
      className: 'border-emerald-200/80 text-emerald-700',
    },
    {
      key: 'returned-withdrawn',
      label: '退回 / 撤回',
      value: String(attentionMetrics.rejectedCount + attentionMetrics.withdrawnCount),
      detail: `已驳回 ${attentionMetrics.rejectedCount} · 已撤回 ${attentionMetrics.withdrawnCount}`,
      icon: RotateCcw,
      className: 'border-rose-200/80 text-rose-700',
    },
    {
      key: 'unresolved-problems',
      label: '未解决异常',
      value: String(attentionMetrics.unresolvedProblemCount),
      detail: '存在待处理问题',
      icon: TriangleAlert,
      className: 'border-orange-200/80 text-orange-700',
    },
    {
      key: 'production-data-pending',
      label: '生产数据待补',
      value: String(attentionMetrics.productionDataPendingCount),
      detail: '生产中缺实际用料',
      icon: ClipboardCheck,
      className: 'border-sky-200/80 text-sky-700',
    },
  ]
})

const boardColumns = computed<BoardColumn[]>(() =>
  boardStatuses.map((status) => {
    if (serverBoardEnabled.value) {
      const response = boardPagesByStatus.value[status]
      const records = (response?.rows ?? []).map(toWorkflowRecord)
      const pagination = createServerPaginationState(
        records,
        response?.total ?? getBoardSummaryStatusTotal(status),
        response?.page ?? boardPageByStatus.value[status] ?? 1,
        response?.page_count,
      )

      return {
        status,
        label: status,
        detail: getStatusColumnDetail(status),
        records,
        pagedRecords: records,
        pagination,
        dotClass: statusDotClasses[status],
        loading: Boolean(boardLoadingByStatus.value[status]),
      }
    }

    const records = visibleRecords.value.filter((record) => normalizeBoardStatus(record.order.status) === status)
    const pagination = createPaginationState(
      records,
      boardPageByStatus.value[status] ?? 1,
      MOLDING_SAMPLE_BOARD_PAGE_SIZE,
    )

    return {
      status,
      label: status,
      detail: getStatusColumnDetail(status),
      records,
      pagedRecords: pagination.rows,
      pagination,
      dotClass: statusDotClasses[status],
      loading: false,
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
    trialItemCount: rows.reduce((sum, row) => sum + row.trialItemCount, 0),
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

const printPreviewItemCount = computed(() =>
  printableRecords.value.reduce((total, record) => total + record.items.length, 0),
)

function getExpectedMaterialAmountHkd(item: MoldingSampleItem) {
  return calculateExpectedMaterialAmountHkd(item, rawMaterialPriceList.value)
}

function getMaterialCompositionLabel(item: MoldingSampleItem) {
  const components = resolveMaterialComponents(item)
  return components.length ? formatMaterialComposition(components) : formatBlank(item.material)
}

function getExpectedMaterialCostBreakdown(item: MoldingSampleItem) {
  return calculateMaterialCostBreakdown({
    components: resolveMaterialComponents(item),
    totalWeightKg: item.required_material_kg,
    prices: rawMaterialPriceList.value,
  })
}

function getActualMaterialCostBreakdown(item: MoldingSampleItem) {
  return resolveActualMaterialCostBreakdown(item, rawMaterialPriceList.value)
}

function getActualMaterialCostTotal(item: MoldingSampleItem) {
  return item.actual_amount_hkd ?? getActualMaterialCostBreakdown(item).total_amount_hkd
}

function getActualMaterialCostSourceLabel(item: MoldingSampleItem) {
  if (getActualMaterialCostBreakdown(item).source === 'persisted') {
    return '实际结算快照'
  }

  return item.actual_amount_hkd === null || item.actual_amount_hkd === undefined
    ? '分项按当前原料价估算'
    : '分项按当前原料价估算；合计以已存实际料费为准'
}

function getDraftMaterialComponents(line: ManualMoldingSampleLineDraft): MoldingSampleMaterialComponent[] {
  const components = line.material_components.map((component) => ({
    material: component.material,
    source_type: component.source_type,
    ratio_percent: Number(component.ratio_percent),
  }))
  return normalizeMaterialComponents(line.material, components)
}

function getDraftMaterialPriceBreakdown(line: ManualMoldingSampleLineDraft) {
  return calculateMaterialCostBreakdown({
    components: getDraftMaterialComponents(line),
    totalWeightKg: 1,
    prices: rawMaterialPriceList.value,
  })
}

function getDraftWeightedUnitPrice(line: ManualMoldingSampleLineDraft) {
  return getDraftMaterialPriceBreakdown(line).weighted_unit_price
}

function getDraftWeightedUnitPriceLabel(line: ManualMoldingSampleLineDraft) {
  const unitPrice = getDraftWeightedUnitPrice(line)
  return unitPrice === null ? (line.material.trim() ? '待维护' : '待选择') : formatMoney(unitPrice)
}

function getMaterialSourceLabel(sourceType: MoldingSampleMaterialSource) {
  return sourceType === 'runner' ? '水口料' : '原料'
}

function getRawMaterialUnitPrice(material: string) {
  return resolveMaterialPrice(material, rawMaterialPriceList.value)?.unit_price ?? null
}

function getRawMaterialUnitPriceLabel(material: string) {
  const unitPrice = getRawMaterialUnitPrice(material)

  if (unitPrice !== null) {
    return formatMoney(unitPrice)
  }

  return material.trim() ? '待维护' : '待选择'
}

const isSelectedOrderDataExpanded = ref(false)
const selectedFullItemId = ref('')
const selectedFullItemDetailPane = ref<HTMLElement | null>(null)
const selectedFullItem = computed(() => (
  selectedItems.value.find((item) => item.id === selectedFullItemId.value)
  ?? selectedItems.value[0]
  ?? null
))

function handoffWheelAtBoundary(event: WheelEvent) {
  const region = event.currentTarget as HTMLElement | null
  if (
    !region
    || event.deltaY === 0
    || event.ctrlKey
    || event.metaKey
    || event.shiftKey
    || Math.abs(event.deltaX) > Math.abs(event.deltaY)
  ) return

  const multiplier = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? window.innerHeight : 1
  const scrollDistance = event.deltaY * multiplier
  const edgeTolerance = 1.5
  const reachedTop = region.scrollTop <= edgeTolerance
  const reachedBottom = region.scrollTop + region.clientHeight >= region.scrollHeight - edgeTolerance

  if ((scrollDistance < 0 && reachedTop) || (scrollDistance > 0 && reachedBottom)) {
    event.preventDefault()
    window.scrollBy({ top: scrollDistance, behavior: 'auto' })
  }
}

function toggleSelectedOrderData() {
  const nextExpanded = !isSelectedOrderDataExpanded.value
  isSelectedOrderDataExpanded.value = nextExpanded

  if (nextExpanded && !selectedItems.value.some((item) => item.id === selectedFullItemId.value)) {
    selectedFullItemId.value = selectedItems.value[0]?.id ?? ''
  }
}

async function selectFullItem(itemId: string) {
  selectedFullItemId.value = itemId
  await nextTick()

  if (selectedFullItemDetailPane.value) {
    selectedFullItemDetailPane.value.scrollTop = 0
  }
}

const ENGINEERING_DEPARTMENT = 'engineering'
const SHARED_MOLDING_DEPARTMENTS = [
  'engineering',
  'production',
  'molding',
  'pmc-warehouse',
  'warehouse',
  'management',
] as const
const MOLDING_SAMPLE_PERMISSION_DEPARTMENTS: Record<string, readonly string[]> = {
  'molding_sample:read': SHARED_MOLDING_DEPARTMENTS,
  'molding_sample:production_read': ['production', 'molding'],
  'molding_sample:create': ['engineering'],
  'molding_sample:supervisor_review': ['engineering'],
  'molding_sample:edit_draft': ['engineering', 'management'],
  'molding_sample:delete_draft': ['engineering', 'management'],
  'molding_sample:manager_review': ['management'],
  'molding_sample:dispatch': ['engineering', 'management'],
  'molding_sample:price_update': ['management'],
  'molding_sample:export': [
    'engineering',
    'management',
    'pmc-warehouse',
    'warehouse',
    'production',
    'molding',
  ],
  'system:user_manage': ['management'],
}
const MOLDING_SAMPLE_WRITE_PERMISSIONS = [
  'molding_sample:create',
  'molding_sample:edit_draft',
  'molding_sample:delete_draft',
  'molding_sample:supervisor_review',
  'molding_sample:manager_review',
  'molding_sample:dispatch',
  'molding_sample:export',
]
const MOLDING_SAMPLE_OPERATE_PERMISSIONS = new Set([
  ...MOLDING_SAMPLE_WRITE_PERMISSIONS,
  'molding_sample:price_update',
  'molding_sample:raw_material_write',
  'molding_sample:warehouse_requisition',
  'molding_sample:inventory_issue',
  'molding_sample:production_start',
  'molding_sample:production_fillback',
  'molding_sample:production_complete',
  'system:user_manage',
])

function isWildcardMoldingAdministrator() {
  return authStore.grants.some((grant) =>
    (grant.role_code === 'admin' || grant.role_id === 'admin')
    && grant.factory_id === '*'
    && ['*', 'system'].includes(grant.department),
  )
}

function isHomeMoldingFactory(factoryId: string) {
  if (isWildcardMoldingAdministrator() || authStore.authzMode !== 'enforce') {
    return true
  }

  const primaryFactoryId = authStore.currentUser?.profile?.primary_factory_id?.trim()
  if (primaryFactoryId) {
    return primaryFactoryId === factoryId
  }

  return authStore.grants.some((grant) => grant.factory_id === factoryId)
}

function canOperateMoldingFactory(factoryId: string) {
  if (isHomeMoldingFactory(factoryId)) return true
  return authStore.grants.some((grant) =>
    grant.scope_mode === 'cross_factory_operate'
    && grant.factory_id !== factoryId,
  )
}

function canMoldingSamplePermission(permission: string, factoryId: string) {
  if (MOLDING_SAMPLE_OPERATE_PERMISSIONS.has(permission) && !canOperateMoldingFactory(factoryId)) {
    return false
  }
  const departments = MOLDING_SAMPLE_PERMISSION_DEPARTMENTS[permission] ?? [ENGINEERING_DEPARTMENT]
  return departments.some((department) => authStore.can(permission, factoryId, department))
}

function canCrossFactoryPermission(permission: string, factoryId: string) {
  return authStore.can(permission, factoryId)
}

function isRecordReadOnly(record: MoldingSampleWorkflowRecord) {
  if (record.access?.read_only === true) {
    return true
  }
  if (record.access?.read_source === 'cross' && record.access?.read_only !== false) {
    return true
  }

  return !MOLDING_SAMPLE_WRITE_PERMISSIONS.some((permission) =>
    canMoldingSamplePermission(permission, record.order.factory_id),
  )
}

function canViewRecordCost(record: MoldingSampleWorkflowRecord) {
  return record.access?.can_view_cost ?? true
}

const canManageSelectedOrderFactory = computed(() =>
  selectedRecord.value ? !isRecordReadOnly(selectedRecord.value) : false,
)
const isSelectedFactoryReadOnly = computed(() => {
  if (selectedRecord.value) {
    return isRecordReadOnly(selectedRecord.value)
  }

  return !MOLDING_SAMPLE_WRITE_PERMISSIONS.some((permission) =>
    canMoldingSamplePermission(permission, selectedFactoryId.value),
  )
})
const canManageSelectedFactory = computed(() => !isSelectedFactoryReadOnly.value)
const canViewSelectedOrderCost = computed(() =>
  selectedRecord.value ? canViewRecordCost(selectedRecord.value) : true,
)
const canViewActiveFactoryCosts = computed(() => {
  if (factoryRecords.value.length > 0) {
    return factoryRecords.value.every(canViewRecordCost)
  }

  if (
    isHomeMoldingFactory(selectedFactoryId.value)
    && (
      canMoldingSamplePermission('molding_sample:read', selectedFactoryId.value)
      || canMoldingSamplePermission('molding_sample:production_read', selectedFactoryId.value)
    )
  ) {
    return true
  }

  return canCrossFactoryPermission('molding_sample:cross_factory_cost_read', selectedFactoryId.value)
})
const isFixedMoldingClerkPosition = computed(() =>
  authStore.grants.some((grant) =>
    grant.role_id === 'position_molding_clerk'
    || grant.role_code === 'position_molding_clerk',
  ),
)
const isCrossFactoryReadOnly = computed(() =>
  selectedRecord.value?.access?.read_source === 'cross'
  && selectedRecord.value?.access?.read_only !== false,
)
const canCreateOrder = computed(() =>
  canManageSelectedFactory.value
  && canMoldingSamplePermission('molding_sample:create', selectedFactoryId.value),
)
const canEditDraftOrder = computed(() =>
  canManageSelectedOrderFactory.value
  && canMoldingSamplePermission('molding_sample:edit_draft', selectedOrder.value.factory_id),
)
const canDeleteDraftOrder = computed(() =>
  canManageSelectedOrderFactory.value
  && canMoldingSamplePermission('molding_sample:delete_draft', selectedOrder.value.factory_id),
)
const isEditingRejectedOrder = computed(() => editingRejectedOrderId.value !== '')
const editingRevisionOrderLabel = computed(() => selectedOrder.value.status === '已撤回' ? '撤回单' : '驳回单')
const canSubmitCreateForm = computed(() => isEditingRejectedOrder.value ? canEditDraftOrder.value : canCreateOrder.value)
function canExportRecords(records: MoldingSampleWorkflowRecord[]) {
  return records.length > 0
  && apiState.value === 'connected'
  && records.every((target) =>
    !isRecordReadOnly(target)
    && canMoldingSamplePermission('molding_sample:export', target.order.factory_id),
  )
  && records.every((target) =>
    apiRecords.value.some((record) => record.order.id === target.order.id),
  )
}
const canExportSelectedOrder = computed(() => canExportRecords(batchActionRecords.value))
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
    canMoldingSamplePermission('system:user_manage', selectedOrder.value.factory_id)
    || canDeleteSelectedWithdrawnOrder.value
  ),
)
const canApproveSelectedOrder = computed(() => {
  const actor = getApprovalActor()
  return Boolean(
    actor
    && canManageSelectedOrderFactory.value
    && canMoldingSamplePermission(actor.permission, selectedOrder.value.factory_id),
  )
})
const canDispatchSelectedOrder = computed(() => Boolean(
  selectedRecord.value
  && isSelectedOrderCrossFactoryDispatch.value
  && isSelectedOrderDispatchable.value
  && !isRecordReadOnly(selectedRecord.value)
  && (
    authStore.can('molding_sample:dispatch', selectedOrder.value.factory_id, 'engineering')
    || authStore.can('molding_sample:dispatch', selectedOrder.value.factory_id, 'management')
  ),
))
const selectedDispatchUnavailableReason = computed(() => {
  if (isSelectedExternal.value) return '外发湖南或模厂的单据不分配内部承接生产厂。'
  if (selectedFactoryCapability.value?.dispatchMode !== 'cross-factory') return '该厂设有啤机部，生产任务固定由本厂承接。'
  if (!isSelectedOrderDispatchable.value) return '生产已经开始或完成，不能再改派承接生产厂。'
  if (!canDispatchSelectedOrder.value) return '当前账号仅可查看派厂信息，没有改派权限。'
  return ''
})

function normalizeBoardStatus(status: MoldingSampleStatus): MoldingSampleStatus {
  return status === '待经理审核' ? '待审核' : status
}

function toWorkflowRecord(record: MoldingSampleDetailResponse): MoldingSampleWorkflowRecord {
  const factoryId = isProductionFactoryContextId(record.order.factory_id)
    ? record.order.factory_id
    : selectedFactoryId.value
  const readSource = record.access?.read_source ?? record.read_source ?? 'local'
  const factoryCapability = getMoldingSampleFactoryCapability(factoryId)
  const productionFactoryId = record.order.production_factory_id
    ?? (factoryCapability?.hasMoldingDepartment ? factoryId : null)

  return {
    factory_id: factoryId,
    order: {
      ...record.order,
      factory_id: factoryId,
      production_factory_id: productionFactoryId,
      production_assigned_at: record.order.production_assigned_at ?? '',
      production_assigned_by: record.order.production_assigned_by ?? '',
      production_assignment_version: record.order.production_assignment_version ?? 0,
    },
    items: record.items,
    audit_logs: record.audit_logs,
    dispatch_logs: record.dispatch_logs ?? [],
    requisitions: [],
    problems: record.problems ?? [],
    trial_reports: record.trial_reports ?? [],
    access: {
      read_source: readSource,
      can_view_cost: record.access?.can_view_cost ?? record.can_view_cost ?? true,
      read_only: record.access?.read_only ?? record.read_only ?? readSource === 'cross',
    },
  }
}

function createEmptySelectedOrder(): MoldingSampleOrder {
  return {
    id: '',
    factory_id: selectedFactoryId.value,
    production_factory_id: getSuggestedMoldingSampleProductionFactoryId(selectedFactoryId.value),
    production_assigned_at: '',
    production_assigned_by: '',
    production_assignment_version: 0,
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
    order_date: getTodayText(),
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
  return [
    line.customer_mold_id,
    line.mold_name,
    line.mold_dimensions,
    line.mold_presence_status,
    line.mold_return_time,
    line.material,
    line.color,
    line.pms,
    line.pigment_no,
    line.quantity,
    line.shoot_qty,
    line.required_material_kg,
    line.required_date,
    line.notes,
  ].every((value) => !hasDraftText(value))
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
  const hasChangedDefault = draft.order_date !== getTodayText()
    || draft.stage !== 'T0'
    || draft.order_type !== '啤办'
    || draft.workshop !== '工程部'
    || draft.send_to !== '内部'
    || draft.production_factory_id !== getSuggestedMoldingSampleProductionFactoryId(draft.factory_id)
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
    production_factory_id: record.order.production_factory_id,
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
        material_components: resolveMaterialComponents(item).map((component) =>
          createManualMoldingSampleMaterialComponentDraft({
            ...component,
            ratio_percent: String(component.ratio_percent),
          }),
        ),
        material_usage_type: item.material_usage_type ?? 'production',
        color: colorParts.color,
        pms: colorParts.pms,
        pigment_no: item.pigment_no,
        quantity: item.quantity,
        shoot_qty: String(item.shoot_qty || ''),
        required_material_kg: formatDraftNumber(item.required_material_kg),
        mold_dimensions: item.mold_dimensions,
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
          material_components: resolveMaterialComponents({
            material: item.material ?? '',
            material_components: item.material_components,
          }).map((component) =>
            createManualMoldingSampleMaterialComponentDraft({
              ...component,
              ratio_percent: String(component.ratio_percent),
            }),
          ),
          material_usage_type: item.material_usage_type ?? 'production',
          color: colorParts.color,
          pms: colorParts.pms,
          pigment_no: item.pigment_no ?? '',
          quantity: item.quantity ?? '',
          shoot_qty: String(item.shoot_qty || ''),
          required_material_kg: formatDraftNumber(item.required_material_kg),
          mold_dimensions: item.mold_dimensions ?? '',
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
    production_factory_id: order.production_factory_id ?? null,
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
  setView('create')
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
  setView('create')
  actionMessage.value = `已载入${editingRevisionOrderLabel.value} ${selectedOrder.value.id}，修改后可重新提交主管审核。`
}

function cancelRejectedEdit() {
  const orderId = editingRejectedOrderId.value

  editingRejectedOrderId.value = ''
  createErrors.value = []
  selectedOrderId.value = orderId || selectedOrderId.value
  setView(orderId ? 'detail' : 'overview')
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

async function loadProtectedMaterialPrices(requestedFactoryId: string) {
  const requestId = ++protectedMaterialPricesRequestId
  rawMaterialPriceList.value = []

  try {
    const response = await moldingSampleApi.getMaterialPrices(requestedFactoryId)
    if (
      requestId !== protectedMaterialPricesRequestId
      || requestedFactoryId !== selectedFactoryId.value
    ) {
      return
    }
    rawMaterialPriceList.value = response.prices
  }
  catch {
    if (
      requestId !== protectedMaterialPricesRequestId
      || requestedFactoryId !== selectedFactoryId.value
    ) {
      return
    }

    rawMaterialPriceList.value = []
  }
}

async function loadRawMaterialOptions(requestedFactoryId: string) {
  const requestId = ++rawMaterialOptionsRequestId
  rawMaterialMasterList.value = []

  try {
    const rows = await rawMaterialApi.list(requestedFactoryId)
    if (
      requestId !== rawMaterialOptionsRequestId
      || requestedFactoryId !== selectedFactoryId.value
    ) {
      return
    }
    rawMaterialMasterList.value = rows
  }
  catch {
    if (
      requestId !== rawMaterialOptionsRequestId
      || requestedFactoryId !== selectedFactoryId.value
    ) {
      return
    }

    rawMaterialMasterList.value = []
  }
}

function supportsServerBoardApi() {
  return typeof moldingSampleApi.getBoardSummary === 'function'
    && typeof moldingSampleApi.listBoardPage === 'function'
}

function isServerBoardContextActive() {
  return activeView.value === 'overview' && overviewDisplayMode.value === 'board'
}

function isLegacyOrdersContextActive() {
  return !serverBoardEnabled.value
    || activeView.value === 'material-balance'
    || (activeView.value === 'overview' && overviewDisplayMode.value === 'list')
}

function invalidateServerBoardRequests() {
  boardOverviewRequestId += 1
  boardStatuses.forEach((status) => {
    boardPageRequestIds[status] = (boardPageRequestIds[status] ?? 0) + 1
  })
  setAllBoardColumnsLoading(false)
}

function invalidateLegacyOrdersRequest() {
  legacyOrdersRequestId += 1
  legacyOrdersLoadPromise = null
  legacyOrdersLoading.value = false
}

function mergeCachedApiRecords(records: MoldingSampleDetailResponse[]) {
  const merged = new Map(apiRecords.value.map((record) => [record.order.id, record]))
  records.forEach((record) => merged.set(record.order.id, record))
  apiRecords.value = Array.from(merged.values())
}

function replaceBoardPageCache(pages: MoldingSampleBoardPageResponse[]) {
  const selectedCachedRecord = apiRecords.value.find((record) => record.order.id === selectedOrderId.value)
  const nextRecords = pages.flatMap((page) => page.rows)

  if (selectedCachedRecord && !nextRecords.some((record) => record.order.id === selectedCachedRecord.order.id)) {
    nextRecords.push(selectedCachedRecord)
  }

  apiRecords.value = Array.from(new Map(nextRecords.map((record) => [record.order.id, record])).values())
  legacyOrdersLoaded.value = false
}

function setAllBoardColumnsLoading(loading: boolean) {
  boardLoadingByStatus.value = Object.fromEntries(
    boardStatuses.map((status) => [status, loading]),
  ) as Partial<Record<MoldingSampleStatus, boolean>>
}

function requestBoardSummary(factoryId: string, query: string) {
  return query
    ? moldingSampleApi.getBoardSummary(factoryId, query)
    : moldingSampleApi.getBoardSummary(factoryId)
}

function requestBoardPage(factoryId: string, status: MoldingSampleStatus, query: string, page: number) {
  return moldingSampleApi.listBoardPage({
    factoryId,
    status,
    ...(query ? { query } : {}),
    page,
    pageSize: MOLDING_SAMPLE_BOARD_PAGE_SIZE,
  })
}

function isExternalCreateDraft(draft: Pick<ManualMoldingSampleOrderDraft, 'send_to' | 'workshop'>) {
  return draft.send_to === '发至湖南'
    || draft.send_to === '发至模厂'
    || draft.workshop === '模厂'
}

function getProductionRouteLabel(order: Pick<MoldingSampleOrder, 'factory_id' | 'production_factory_id' | 'send_to' | 'workshop'>) {
  const originLabel = getMoldingSampleFactoryLabel(order.factory_id)
  if (isExternalMoldingSampleOrder(order)) {
    return `${originLabel} → 外发（不派生产厂）`
  }

  return `${originLabel} → ${getMoldingSampleFactoryLabel(resolveMoldingSampleProductionFactoryId(order))}`
}

function getLatestAuditLog(action: string) {
  return [...selectedAuditLogs.value]
    .filter((log) => log.action === action)
    .sort((left, right) => right.created_at.localeCompare(left.created_at))[0] ?? null
}

function getCreateDraftProductionFactoryLabel() {
  if (createDraftIsExternal.value) return '外发（不派生产厂）'
  return getMoldingSampleFactoryLabel(createDraft.value.production_factory_id)
}

function syncCreateDraftProductionAssignment() {
  const capability = activeFactoryCapability.value
  if (!capability) {
    createDraft.value.production_factory_id = null
    return
  }
  if (createDraftIsExternal.value) {
    createDraft.value.production_factory_id = null
    return
  }
  if (capability.dispatchMode === 'self-only') {
    createDraft.value.production_factory_id = capability.factoryId
    return
  }

  const validation = validateMoldingSampleProductionAssignment(
    selectedFactoryId.value,
    createDraft.value.production_factory_id,
  )
  if (!validation.valid) {
    createDraft.value.production_factory_id = capability.suggestedProductionFactoryId
  }
}

function isOrderRoutingResponseExpected(
  record: MoldingSampleDetailResponse,
  expectedOriginFactoryId: string,
  expectedProductionFactoryId: string | null,
) {
  return record.order.factory_id === expectedOriginFactoryId
    && resolveMoldingSampleProductionFactoryId(record.order) === expectedProductionFactoryId
    && (!isExternalMoldingSampleOrder(record.order) || !record.order.production_factory_id)
}

function hasAllowedOrderRouting(record: MoldingSampleDetailResponse, expectedOriginFactoryId: string) {
  if (record.order.factory_id !== expectedOriginFactoryId) return false
  if (isExternalMoldingSampleOrder(record.order)) return !record.order.production_factory_id
  if (!record.order.production_factory_id) {
    return getMoldingSampleFactoryCapability(expectedOriginFactoryId) !== null
  }

  return validateMoldingSampleProductionAssignment(
    expectedOriginFactoryId,
    record.order.production_factory_id,
  ).valid
}

async function loadDeepLinkedOrderIfNeeded(requestedFactoryId: string) {
  const deepLinkedOrderId = readQueryString(route.query.order_id)

  if (!deepLinkedOrderId) {
    deepLinkedOrderRequestId += 1
    return
  }

  const cachedRecord = apiRecords.value.find((record) =>
    record.order.id === deepLinkedOrderId && record.order.factory_id === requestedFactoryId,
  )
  if (cachedRecord) {
    selectedOrderId.value = cachedRecord.order.id
    return
  }

  const requestId = ++deepLinkedOrderRequestId
  try {
    const record = await moldingSampleApi.getOrder(deepLinkedOrderId)
    if (
      requestId !== deepLinkedOrderRequestId
      || requestedFactoryId !== selectedFactoryId.value
      || deepLinkedOrderId !== readQueryString(route.query.order_id)
    ) {
      return
    }
    if (!hasAllowedOrderRouting(record, requestedFactoryId)) {
      return
    }

    mergeCachedApiRecords([record])
    selectedOrderId.value = record.order.id
  }
  catch {
    // A stale or unauthorized deep link must not hide the otherwise usable board.
  }
}

async function loadServerBoardOverview(options: { includeSupportingData?: boolean } = {}) {
  const requestedFactoryId = selectedFactoryId.value
  const requestedFactoryName = factoryContexts.find((factory) => factory.id === requestedFactoryId)?.shortName
    ?? requestedFactoryId
  const requestedQuery = effectiveSearchKeyword.value.trim()
  const requestId = ++boardOverviewRequestId
  const pageRequestIds = Object.fromEntries(boardStatuses.map((status) => {
    const nextRequestId = (boardPageRequestIds[status] ?? 0) + 1
    boardPageRequestIds[status] = nextRequestId
    return [status, nextRequestId]
  })) as Partial<Record<MoldingSampleStatus, number>>

  apiState.value = 'checking'
  setAllBoardColumnsLoading(true)
  actionMessage.value = requestedQuery
    ? `正在搜索${requestedFactoryName}啤办单...`
    : `正在读取${requestedFactoryName}啤办看板...`

  try {
    const [summary, pages] = await Promise.all([
      requestBoardSummary(requestedFactoryId, requestedQuery),
      Promise.all(boardStatuses.map((status) =>
        requestBoardPage(requestedFactoryId, status, requestedQuery, 1),
      )),
      options.includeSupportingData
        ? Promise.all([
            loadProtectedMaterialPrices(requestedFactoryId),
            loadRawMaterialOptions(requestedFactoryId),
          ])
        : Promise.resolve(),
    ])

    if (
      requestId !== boardOverviewRequestId
      || requestedFactoryId !== selectedFactoryId.value
      || requestedQuery !== effectiveSearchKeyword.value.trim()
      || !isServerBoardContextActive()
    ) {
      return
    }
    if (pages.some((page) => page.rows.some((record) => !hasAllowedOrderRouting(record, requestedFactoryId)))) {
      throw new Error('看板响应包含不属于当前来源厂或无效承接生产厂的单据')
    }

    boardSummary.value = summary
    const nextPages = { ...boardPagesByStatus.value }
    pages.forEach((page, index) => {
      const status = boardStatuses[index]!
      if (boardPageRequestIds[status] === pageRequestIds[status]) {
        nextPages[status] = page
        boardPageByStatus.value = {
          ...boardPageByStatus.value,
          [status]: page.page,
        }
      }
    })
    boardPagesByStatus.value = nextPages
    replaceBoardPageCache(pages)
    apiState.value = summary.total ? 'connected' : 'empty'
    actionMessage.value = summary.total
      ? `已读取${requestedFactoryName}啤办看板 ${summary.total} 张。`
      : `${requestedFactoryName}暂无正式啤办单，可先新建啤办单。`

    selectedOrderId.value = apiRecords.value.some((record) => record.order.id === selectedOrderId.value)
      ? selectedOrderId.value
      : pages.flatMap((page) => page.rows)[0]?.order.id ?? ''

    await loadDeepLinkedOrderIfNeeded(requestedFactoryId)
  }
  catch (error) {
    if (
      requestId !== boardOverviewRequestId
      || requestedFactoryId !== selectedFactoryId.value
      || !isServerBoardContextActive()
    ) {
      return
    }

    apiRecords.value = []
    boardSummary.value = null
    boardPagesByStatus.value = {}
    apiState.value = 'error'
    actionMessage.value = `正式数据读取失败：${getApiErrorMessage(error)}。不会显示本地示例单据。`
  }
  finally {
    boardStatuses.forEach((status) => {
      if (boardPageRequestIds[status] === pageRequestIds[status]) {
        boardLoadingByStatus.value = {
          ...boardLoadingByStatus.value,
          [status]: false,
        }
      }
    })
  }
}

async function loadServerBoardColumn(status: MoldingSampleStatus, page: number) {
  const requestedFactoryId = selectedFactoryId.value
  const requestedQuery = effectiveSearchKeyword.value.trim()
  const requestId = (boardPageRequestIds[status] ?? 0) + 1
  boardPageRequestIds[status] = requestId
  boardLoadingByStatus.value = {
    ...boardLoadingByStatus.value,
    [status]: true,
  }

  try {
    const response = await requestBoardPage(requestedFactoryId, status, requestedQuery, page)
    if (
      boardPageRequestIds[status] !== requestId
      || requestedFactoryId !== selectedFactoryId.value
      || requestedQuery !== effectiveSearchKeyword.value.trim()
      || !isServerBoardContextActive()
    ) {
      return
    }
    if (response.rows.some((record) => !hasAllowedOrderRouting(record, requestedFactoryId))) {
      throw new Error('看板分页响应包含不属于当前来源厂或无效承接生产厂的单据')
    }

    boardPagesByStatus.value = {
      ...boardPagesByStatus.value,
      [status]: response,
    }
    boardPageByStatus.value = {
      ...boardPageByStatus.value,
      [status]: response.page,
    }
    mergeCachedApiRecords(response.rows)
  }
  catch (error) {
    if (boardPageRequestIds[status] === requestId && isServerBoardContextActive()) {
      actionMessage.value = `${status}分页读取失败：${getApiErrorMessage(error)}`
    }
  }
  finally {
    if (boardPageRequestIds[status] === requestId) {
      boardLoadingByStatus.value = {
        ...boardLoadingByStatus.value,
        [status]: false,
      }
    }
  }
}

async function loadLegacyApiData(options: { force?: boolean; includeSupportingData?: boolean } = {}) {
  if (legacyOrdersLoaded.value && !options.force) {
    legacyOrdersLoading.value = false
    apiState.value = apiRecords.value.length ? 'connected' : 'empty'
    return
  }
  if (legacyOrdersLoadPromise && !options.force) {
    return legacyOrdersLoadPromise
  }

  const requestedFactoryId = selectedFactoryId.value
  const requestedFactoryName = factoryContexts.find((factory) => factory.id === requestedFactoryId)?.shortName
    ?? requestedFactoryId
  const requestId = ++legacyOrdersRequestId
  legacyOrdersLoading.value = true
  apiState.value = 'checking'
  actionMessage.value = `正在读取${requestedFactoryName}完整啤办单列表...`

  const loadPromise = (async () => {
    try {
      const [records] = await Promise.all([
        moldingSampleApi.listOrders(requestedFactoryId),
        options.includeSupportingData
          ? Promise.all([
              loadProtectedMaterialPrices(requestedFactoryId),
              loadRawMaterialOptions(requestedFactoryId),
            ])
          : Promise.resolve(),
      ])
      if (
        requestId !== legacyOrdersRequestId
        || requestedFactoryId !== selectedFactoryId.value
        || !isLegacyOrdersContextActive()
      ) {
        return
      }
      if (records.some((record) => !hasAllowedOrderRouting(record, requestedFactoryId))) {
        throw new Error('完整列表响应包含不属于当前来源厂或无效承接生产厂的单据')
      }

      apiRecords.value = records
      legacyOrdersLoaded.value = true
      apiState.value = records.length ? 'connected' : 'empty'
      actionMessage.value = records.length
        ? `已读取${requestedFactoryName}正式啤办单 ${records.length} 张。`
        : `${requestedFactoryName}暂无正式啤办单，可先新建啤办单。`
      selectedOrderId.value = records.some((record) => record.order.id === selectedOrderId.value)
        ? selectedOrderId.value
        : records[0]?.order.id ?? ''
    }
    catch (error) {
      if (
        requestId !== legacyOrdersRequestId
        || requestedFactoryId !== selectedFactoryId.value
        || !isLegacyOrdersContextActive()
      ) {
        return
      }

      if (!serverBoardEnabled.value) {
        apiRecords.value = []
        rawMaterialPriceList.value = []
        rawMaterialMasterList.value = []
        apiState.value = 'error'
        actionMessage.value = `正式数据读取失败：${getApiErrorMessage(error)}。不会显示本地示例单据。`
      }
      else {
        apiState.value = boardSummary.value?.total ? 'connected' : 'empty'
        actionMessage.value = `完整单据列表读取失败：${getApiErrorMessage(error)}`
      }
    }
    finally {
      if (requestId === legacyOrdersRequestId && requestedFactoryId === selectedFactoryId.value) {
        legacyOrdersLoading.value = false
      }
    }
  })()

  legacyOrdersLoadPromise = loadPromise
  try {
    await loadPromise
  }
  finally {
    if (legacyOrdersLoadPromise === loadPromise) {
      legacyOrdersLoadPromise = null
    }
  }
}

async function loadApiData() {
  invalidateServerBoardRequests()
  invalidateLegacyOrdersRequest()
  deepLinkedOrderRequestId += 1
  serverBoardEnabled.value = supportsServerBoardApi()
  legacyOrdersLoaded.value = false

  if (serverBoardEnabled.value) {
    boardSummary.value = null
    boardPagesByStatus.value = {}
    boardPageByStatus.value = {}
    apiRecords.value = []

    if (isServerBoardContextActive()) {
      await loadServerBoardOverview({ includeSupportingData: true })
    }
    else if (isLegacyOrdersContextActive()) {
      await loadLegacyApiData({ force: true, includeSupportingData: true })
    }
    else {
      const requestedFactoryId = selectedFactoryId.value
      await Promise.all([
        loadProtectedMaterialPrices(requestedFactoryId),
        loadRawMaterialOptions(requestedFactoryId),
        loadDeepLinkedOrderIfNeeded(requestedFactoryId),
      ])
      apiState.value = apiRecords.value.length ? 'connected' : 'empty'
    }
    return
  }

  boardSummary.value = null
  boardPagesByStatus.value = {}
  boardLoadingByStatus.value = {}
  await loadLegacyApiData({ force: true, includeSupportingData: true })
}

async function refreshBoardAfterMutation() {
  if (!serverBoardEnabled.value) {
    return
  }

  legacyOrdersLoaded.value = false
  if (isServerBoardContextActive()) {
    await loadServerBoardOverview()
  }
  else {
    boardSummary.value = null
    boardPagesByStatus.value = {}
  }
}

function triggerExcelImport() {
  if (!canCreateOrder.value) {
    actionMessage.value = '当前账号没有从Excel导入啤办单权限。'
    return
  }

  excelFileInput.value?.click()
}

async function downloadEngineeringImportTemplate() {
  if (!canCreateOrder.value) {
    actionMessage.value = '当前账号没有下载工程部导入模板权限。'
    return
  }

  excelTemplateDownloading.value = true
  actionMessage.value = '正在下载工程部啤办单导入模板...'

  try {
    const workbook = await moldingSampleApi.downloadEngineeringImportTemplate(selectedFactoryId.value)
    saveWorkbookAsExcel(workbook, '工程部啤办单_基础资料与模具明细导入模板.xlsx')
    actionMessage.value = '工程部啤办单导入模板已开始下载。'
  }
  catch (error) {
    actionMessage.value = `导入模板下载失败：${getApiErrorMessage(error)}`
  }
  finally {
    excelTemplateDownloading.value = false
  }
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

  const requestedFactoryId = selectedFactoryId.value
  const requestId = ++excelImportRequestId
  excelImporting.value = true
  actionMessage.value = `正在导入Excel文件 ${file.name}...`

  try {
    const workbook = await readWorkbookAsArrayBuffer(file)
    if (
      requestId !== excelImportRequestId
      || requestedFactoryId !== selectedFactoryId.value
    ) return

    const preview = await moldingSampleApi.previewOrderExcel(workbook, {
      factory_id: requestedFactoryId,
    })
    if (
      requestId !== excelImportRequestId
      || requestedFactoryId !== selectedFactoryId.value
    ) return
    if (preview.order.factory_id !== requestedFactoryId) {
      actionMessage.value = 'Excel预览响应与当前来源厂不一致，已忽略该响应。'
      return
    }
    if (!isExternalCreateDraft({
      send_to: preview.order.send_to ?? '',
      workshop: preview.order.workshop ?? '',
    }) && preview.order.production_factory_id) {
      const assignmentValidation = validateMoldingSampleProductionAssignment(
        requestedFactoryId,
        preview.order.production_factory_id,
      )
      if (!assignmentValidation.valid) {
        actionMessage.value = `Excel预览中的承接生产厂无效：${assignmentValidation.error}`
        return
      }
    }

    editingRejectedOrderId.value = ''
    createDraft.value = createDraftFromExcelPreview(preview)
    createErrors.value = []
    selectedOrderId.value = ''
    setView('create')
    actionMessage.value = 'Excel已导入到新建开单草稿，请确认数据无误后提交主管审核。'
  }
  catch (error) {
    if (
      requestId === excelImportRequestId
      && requestedFactoryId === selectedFactoryId.value
    ) {
      actionMessage.value = `Excel导入失败：${getApiErrorMessage(error)}`
    }
  }
  finally {
    if (
      requestId === excelImportRequestId
      && requestedFactoryId === selectedFactoryId.value
    ) {
      excelImporting.value = false
    }
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
  selectedBatchOrderIds.value = batchSelectableRecords.value.map((record) => record.order.id)
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

  if (!canExportSelectedOrder.value) {
    printPreviewVisible.value = false
    printableRecords.value = []
    actionMessage.value = '当前账号没有所选啤办单的导出或打印权限。'
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
  if (!canExportRecords(printableRecords.value)) {
    printPreviewVisible.value = false
    printableRecords.value = []
    actionMessage.value = '当前账号没有所选啤办单的导出或打印权限。'
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

function openEngineeringTrialReportHistory(itemId: string) {
  if (!selectedTrialReports.value.some((report) => report.item_id === itemId)) {
    actionMessage.value = '该模具尚未收到啤机部保存的试模报告。'
    return
  }

  engineeringTrialReportItemId.value = itemId
  engineeringTrialReportHistoryVisible.value = true
}

function closeEngineeringTrialReportHistory() {
  engineeringTrialReportHistoryVisible.value = false
  engineeringTrialReportItemId.value = ''
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

function replaceRouteOrderId(orderId: string) {
  if (readQueryString(route.query.order_id) === orderId) {
    return
  }

  deepLinkedOrderRequestId += 1
  const nextQuery = { ...route.query }
  if (orderId) {
    nextQuery.order_id = orderId
  }
  else {
    delete nextQuery.order_id
  }
  void router.replace({ query: nextQuery })
}

function setView(view: ViewKey) {
  activeView.value = view
  deleteConfirmingOrderId.value = ''

  if (!serverBoardEnabled.value) {
    return
  }

  if (view === 'overview' && overviewDisplayMode.value === 'board') {
    invalidateLegacyOrdersRequest()
    void loadServerBoardOverview()
  }
  else if (view === 'material-balance' || (view === 'overview' && overviewDisplayMode.value === 'list')) {
    invalidateServerBoardRequests()
    void loadLegacyApiData()
  }
  else {
    invalidateServerBoardRequests()
    invalidateLegacyOrdersRequest()
    apiState.value = apiRecords.value.length ? 'connected' : 'empty'

    if (
      view === 'detail'
      && selectedOrderId.value
      && !apiRecords.value.some((record) => record.order.id === selectedOrderId.value)
    ) {
      const requestedFactoryId = selectedFactoryId.value
      apiState.value = 'checking'
      void loadDeepLinkedOrderIfNeeded(requestedFactoryId).finally(() => {
        if (activeView.value === 'detail' && requestedFactoryId === selectedFactoryId.value) {
          apiState.value = apiRecords.value.some((record) => record.order.id === selectedOrderId.value)
            ? 'connected'
            : 'empty'
        }
      })
    }
  }
}

function setOverviewDisplayMode(mode: OverviewDisplayMode) {
  overviewDisplayMode.value = mode

  if (serverBoardEnabled.value && mode === 'list') {
    invalidateServerBoardRequests()
    void loadLegacyApiData()
  }
  else if (serverBoardEnabled.value && mode === 'board') {
    invalidateLegacyOrdersRequest()
    void loadServerBoardOverview()
  }
}

function openRecord(record: MoldingSampleWorkflowRecord) {
  selectedOrderId.value = record.order.id
  replaceRouteOrderId(record.order.id)
  setView('detail')
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

function isManualCreateMutationRequestCurrent(requestId: number, factoryId: string) {
  return requestId === manualCreateMutationRequestId
    && factoryId === selectedFactoryId.value
}

function isManualCreateFormContextCurrent(requestId: number, factoryId: string, rejectedOrderId: string) {
  return isManualCreateMutationRequestCurrent(requestId, factoryId)
    && editingRejectedOrderId.value === rejectedOrderId
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

  const requestedFactoryId = selectedFactoryId.value
  const requestedRejectedOrderId = editingRejectedOrderId.value
  const isRejectedResubmit = requestedRejectedOrderId !== ''
  const revisionLabel = editingRevisionOrderLabel.value
  createDraft.value.factory_id = requestedFactoryId
  createErrors.value = []
  const result = buildManualMoldingSampleCreateRequest(createDraft.value, requestedFactoryId)

  if (!result.payload) {
    createErrors.value = result.errors
    actionMessage.value = `${isRejectedResubmit ? `${revisionLabel}重提` : '新建啤办单'}未提交：${result.errors[0] ?? '请检查表单'}`
    return
  }

  const requestId = ++manualCreateMutationRequestId
  const requestedProductionFactoryId = resolveMoldingSampleProductionFactoryId({
    factory_id: requestedFactoryId,
    production_factory_id: result.payload.order.production_factory_id ?? null,
    send_to: result.payload.order.send_to,
    workshop: result.payload.order.workshop,
  })
  createSubmitting.value = true
  actionMessage.value = isRejectedResubmit ? `正在保存${revisionLabel}修改并重提啤办单...` : '正在提交新建啤办单...'

  try {
    const created = isRejectedResubmit
      ? await resubmitRejectedOrder(requestedRejectedOrderId, result.payload)
      : await moldingSampleApi.createOrder(result.payload)

    if (!isManualCreateFormContextCurrent(requestId, requestedFactoryId, requestedRejectedOrderId)) {
      return
    }
    if (
      !isOrderRoutingResponseExpected(created, requestedFactoryId, requestedProductionFactoryId)
      || (isRejectedResubmit && created.order.id !== requestedRejectedOrderId)
    ) {
      actionMessage.value = '啤办单提交响应与当前来源厂、承接生产厂或原单不一致，已忽略该响应。'
      return
    }

    replaceApiRecord(created)
    selectedOrderId.value = created.order.id
    setView('detail')
    await refreshBoardAfterMutation()
    if (!isManualCreateFormContextCurrent(requestId, requestedFactoryId, requestedRejectedOrderId)) {
      return
    }

    selectedOrderId.value = created.order.id
    actionMessage.value = isRejectedResubmit
      ? `啤办单 ${created.order.id} 已保存${revisionLabel}修改并重提主管审核。`
      : `啤办单 ${created.order.id} 已提交主管审核，正式列表已刷新。`
    if (!isRejectedResubmit) {
      clearSavedCreateDraft(requestedFactoryId)
      showCreateSuccessToast(created.order.id)
    }
    resetCreateDraft()
  }
  catch (error) {
    if (isManualCreateFormContextCurrent(requestId, requestedFactoryId, requestedRejectedOrderId)) {
      actionMessage.value = `${isRejectedResubmit ? `${revisionLabel}重提` : '新建啤办单'}提交失败：${getApiErrorMessage(error)}`
    }
  }
  finally {
    if (isManualCreateMutationRequestCurrent(requestId, requestedFactoryId)) {
      createSubmitting.value = false
    }
  }
}

async function resubmitRejectedOrder(
  orderId: string,
  payload: NonNullable<ReturnType<typeof buildManualMoldingSampleCreateRequest>['payload']>,
) {
  if (!orderId || payload.order.id !== orderId) {
    throw new Error('驳回单编号不能修改，请保持原单号后重提。')
  }

  await moldingSampleApi.editOrder(orderId, payload)

  return moldingSampleApi.updateStatus(orderId, {
    action: '工程重提',
    reason: `${authStore.currentUser?.display_name ?? '工程部'}修改后重提。`,
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
  const requestedOrderId = selectedOrder.value.id
  const requestedOriginFactoryId = selectedOrder.value.factory_id
  const requestedProductionFactoryId = resolveMoldingSampleProductionFactoryId(selectedOrder.value)

  const payload: MoldingSampleStatusRequest = {
    action: decision === '通过' ? actor.passAction : actor.rejectAction,
    reason: reason || `${authStore.currentUser?.display_name ?? actor.actorName}${decision}`,
  }

  try {
    const updated = await moldingSampleApi.updateStatus(requestedOrderId, payload)
    if (
      selectedOrder.value.id !== requestedOrderId
      || !isOrderRoutingResponseExpected(updated, requestedOriginFactoryId, requestedProductionFactoryId)
    ) {
      actionMessage.value = '审核响应与当前单据的来源厂或承接生产厂不一致，已忽略该响应。'
      return
    }
    replaceApiRecord(updated)
    selectedOrderId.value = updated.order.id
    await refreshBoardAfterMutation()
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
  const requestedOrderId = selectedOrder.value.id
  const requestedOriginFactoryId = selectedOrder.value.factory_id
  const requestedProductionFactoryId = resolveMoldingSampleProductionFactoryId(selectedOrder.value)
  withdrawSubmitting.value = true
  actionMessage.value = '正在撤回主管审核...'

  try {
    const updated = await moldingSampleApi.updateStatus(requestedOrderId, {
      action: '工程撤回',
      reason: `${actorName}撤回主管审核。`,
    })
    if (
      selectedOrder.value.id !== requestedOrderId
      || !isOrderRoutingResponseExpected(updated, requestedOriginFactoryId, requestedProductionFactoryId)
    ) {
      actionMessage.value = '撤回响应与当前单据的来源厂或承接生产厂不一致，已忽略该响应。'
      return
    }
    replaceApiRecord(updated)
    selectedOrderId.value = updated.order.id
    await refreshBoardAfterMutation()
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

async function updateSelectedProductionAssignment() {
  if (!selectedRecord.value) {
    actionMessage.value = '请先选择一张正式啤办单。'
    return
  }
  if (!canDispatchSelectedOrder.value) {
    actionMessage.value = selectedDispatchUnavailableReason.value || '当前账号没有改派承接生产厂权限。'
    return
  }

  const reason = dispatchReason.value.trim()
  if (!reason) {
    actionMessage.value = '改派承接生产厂必须填写原因。'
    return
  }

  const assignmentValidation = validateMoldingSampleProductionAssignment(
    selectedOrder.value.factory_id,
    dispatchProductionFactoryId.value,
  )
  if (!assignmentValidation.valid || !assignmentValidation.productionFactoryId) {
    actionMessage.value = assignmentValidation.error || '请选择有效的承接生产厂。'
    return
  }
  if (assignmentValidation.productionFactoryId === selectedProductionFactoryId.value) {
    actionMessage.value = '请选择与当前不同的承接生产厂。'
    return
  }

  const requestId = ++productionAssignmentRequestId
  const requestedOrderId = selectedOrder.value.id
  const requestedOriginFactoryId = selectedOrder.value.factory_id
  const requestedProductionFactoryId = assignmentValidation.productionFactoryId
  const expectedAssignmentVersion = selectedOrder.value.production_assignment_version
  dispatchSubmitting.value = true
  actionMessage.value = `正在将 ${requestedOrderId} 改派至${getMoldingSampleFactoryLabel(requestedProductionFactoryId)}...`

  try {
    const updated = await moldingSampleApi.updateProductionAssignment(requestedOrderId, {
      production_factory_id: requestedProductionFactoryId,
      reason,
      expected_assignment_version: expectedAssignmentVersion,
    })
    if (
      requestId !== productionAssignmentRequestId
      || selectedFactoryId.value !== requestedOriginFactoryId
      || selectedOrder.value.id !== requestedOrderId
    ) return
    if (
      !isOrderRoutingResponseExpected(updated, requestedOriginFactoryId, requestedProductionFactoryId)
      || updated.order.production_assignment_version !== expectedAssignmentVersion + 1
    ) {
      actionMessage.value = '改派响应与当前来源厂、承接生产厂或版本不一致，已忽略该响应。'
      return
    }

    replaceApiRecord(updated)
    selectedOrderId.value = updated.order.id
    dispatchReason.value = ''
    dispatchProductionFactoryId.value = requestedProductionFactoryId
    await refreshBoardAfterMutation()
    if (
      requestId !== productionAssignmentRequestId
      || selectedFactoryId.value !== requestedOriginFactoryId
    ) return
    selectedOrderId.value = updated.order.id
    actionMessage.value = `啤办单 ${updated.order.id} 已改派至${getMoldingSampleFactoryLabel(requestedProductionFactoryId)}。`
  }
  catch (error) {
    if (
      requestId === productionAssignmentRequestId
      && selectedFactoryId.value === requestedOriginFactoryId
      && selectedOrder.value.id === requestedOrderId
    ) {
      actionMessage.value = `改派承接生产厂失败：${getApiErrorMessage(error)}`
    }
  }
  finally {
    if (requestId === productionAssignmentRequestId) {
      dispatchSubmitting.value = false
    }
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
    await refreshBoardAfterMutation()
    if (readQueryString(route.query.order_id) === orderId) {
      replaceRouteOrderId('')
    }
    setView('overview')
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
    current: 'border-teal-700 bg-gradient-to-r from-slate-800 to-teal-800 text-white shadow-sm shadow-teal-950/10',
    pending: 'border-slate-200 bg-white text-slate-500',
    rejected: 'border-red-200 bg-red-50 text-red-700',
  }

  return classes[state]
}

function getWorkflowIndexClass(state: StatusState) {
  const classes: Record<StatusState, string> = {
    done: 'bg-teal-600 text-white',
    current: 'bg-white text-teal-800',
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
    return record.order.completed_date ? `${formatWorkflowDate(record.order.completed_date)} 完成` : '已完成'
  }

  if (record.order.status === '已撤回') {
    return '工程已撤回，待修改重提'
  }

  return record.order.reject_reason || '退回工程处理'
}

function getBoardSummaryStatusTotal(status: MoldingSampleStatus) {
  const counts = boardSummary.value?.status_counts ?? {}

  if (status === '待审核') {
    return (counts['待审核'] ?? 0) + (counts['待经理审核'] ?? 0)
  }

  return counts[status] ?? 0
}

function getPageCount(total: number, pageSize = MOLDING_SAMPLE_PAGE_SIZE) {
  return Math.max(1, Math.ceil(total / pageSize))
}

function clampPage(page: number, total: number, pageSize = MOLDING_SAMPLE_PAGE_SIZE) {
  return Math.min(Math.max(1, page), getPageCount(total, pageSize))
}

function createPaginationState<T>(rows: T[], page: number, pageSize = MOLDING_SAMPLE_PAGE_SIZE): PaginationState<T> {
  const total = rows.length
  const pageCount = getPageCount(total, pageSize)
  const normalizedPage = clampPage(page, total, pageSize)
  const startIndex = (normalizedPage - 1) * pageSize
  const pageRows = rows.slice(startIndex, startIndex + pageSize)
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

function createServerPaginationState<T>(
  rows: T[],
  total: number,
  page: number,
  pageCount = getPageCount(total, MOLDING_SAMPLE_BOARD_PAGE_SIZE),
): PaginationState<T> {
  const normalizedPageCount = Math.max(1, pageCount)
  const normalizedPage = Math.min(Math.max(1, page), normalizedPageCount)
  const startIndex = (normalizedPage - 1) * MOLDING_SAMPLE_BOARD_PAGE_SIZE

  return {
    rows,
    total,
    page: normalizedPage,
    pageCount: normalizedPageCount,
    start: total === 0 ? 0 : startIndex + 1,
    end: total === 0 ? 0 : Math.min(total, startIndex + rows.length),
    hasPrevious: normalizedPage > 1,
    hasNext: normalizedPage < normalizedPageCount,
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
  if (serverBoardEnabled.value) {
    void loadServerBoardColumn(status, page)
    return
  }

  const total = visibleRecords.value.filter((record) => normalizeBoardStatus(record.order.status) === status).length
  boardPageByStatus.value = {
    ...boardPageByStatus.value,
    [status]: clampPage(page, total, MOLDING_SAMPLE_BOARD_PAGE_SIZE),
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

function formatWorkflowDate(value: string | null | undefined, fallback = '待填写') {
  return formatBusinessDate(value, fallback)
}

function formatWorkflowTime(value: string | null | undefined, fallback = '待生成') {
  return formatBusinessDateTime(value, { includeSeconds: true, fallback })
}

function getWorkflowDateLabel(record: MoldingSampleWorkflowRecord) {
  const completedDate = formatWorkflowDate(record.order.completed_date, '')
  if (record.order.status === '已完成' && completedDate) {
    return `完成 ${completedDate}`
  }
  const submittedDate = formatWorkflowDate(record.order.created_at, '')
  if (submittedDate) {
    return `提交 ${submittedDate}`
  }

  return `业务 ${formatWorkflowDate(record.order.date)}`
}

function formatMoldPresenceStatus(value: string | undefined) {
  return value === 'in_factory' ? '在厂' : value === 'out_of_factory' ? '不在厂' : '待确认'
}

function formatWeight(value: number | null | undefined) {
  return value === null || value === undefined ? '待填写' : `${value.toFixed(2)} kg`
}

function formatMoney(value: number | null | undefined, currency = 'HKD') {
  return value === null || value === undefined ? '待计算' : `${currency} ${value.toFixed(2)}`
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
  line.material_components = [createSingleManualMaterialComponentDraft(option.value)]
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
  line.material_components = []
  rawMaterialSearchByLine.value = {
    ...rawMaterialSearchByLine.value,
    [index]: '',
  }
  activeRawMaterialPickerLineIndex.value = index
}

function openMaterialCompositionEditor(line: ManualMoldingSampleLineDraft, index: number) {
  const existingRows = line.material_components.length
    ? line.material_components
    : [createSingleManualMaterialComponentDraft(line.material)]

  materialCompositionLineIndex.value = index
  materialCompositionDraftRows.value = existingRows.map((row) =>
    createManualMoldingSampleMaterialComponentDraft(row),
  )
  materialCompositionError.value = ''
  closeRawMaterialPicker(index)
}

function closeMaterialCompositionEditor() {
  materialCompositionLineIndex.value = null
  materialCompositionDraftRows.value = []
  materialCompositionError.value = ''
}

function addMaterialCompositionRow() {
  materialCompositionDraftRows.value.push({
    material: '',
    source_type: 'virgin',
    ratio_percent: '',
  })
}

function removeMaterialCompositionRow(index: number) {
  if (materialCompositionDraftRows.value.length <= 1) {
    materialCompositionDraftRows.value = [{ material: '', source_type: 'virgin', ratio_percent: '100' }]
    return
  }

  materialCompositionDraftRows.value.splice(index, 1)
}

function findEnabledRawMaterialOption(material: string) {
  const normalized = material.trim().toLowerCase()
  return rawMaterialOptions.value.find((option) => option.value.trim().toLowerCase() === normalized) ?? null
}

function saveMaterialComposition() {
  const lineIndex = materialCompositionLineIndex.value
  const line = lineIndex === null ? null : createDraft.value.items[lineIndex]
  if (!line) {
    closeMaterialCompositionEditor()
    return
  }

  const components = materialCompositionDraftRows.value.map((row) => {
    const enabledOption = findEnabledRawMaterialOption(row.material)
    return {
      material: enabledOption?.value ?? row.material.trim(),
      source_type: row.source_type,
      ratio_percent: Number(row.ratio_percent),
      enabledOption,
    }
  })
  if (components.some((component) => !component.material)) {
    materialCompositionError.value = '请为每个配比组分选择原料。'
    return
  }
  const disabledComponentIndex = components.findIndex((component) => !component.enabledOption)
  if (disabledComponentIndex >= 0) {
    materialCompositionError.value = `第 ${disabledComponentIndex + 1} 个组分“${components[disabledComponentIndex]?.material}”不是已启用的原料，请从原料列表选择。`
    return
  }
  const componentKeys = components.map((component) => `${component.material.trim().toLowerCase()}::${component.source_type}`)
  const duplicateComponentIndex = componentKeys.findIndex((key, index) => componentKeys.indexOf(key) !== index)
  if (duplicateComponentIndex >= 0) {
    materialCompositionError.value = `第 ${duplicateComponentIndex + 1} 个组分与前面的“原料 + 来源类型”重复，请合并百分比。`
    return
  }
  if (components.some((component) => !Number.isFinite(component.ratio_percent) || component.ratio_percent <= 0)) {
    materialCompositionError.value = '每个组分的百分比都必须大于 0。'
    return
  }
  const percentageTotal = components.reduce((total, component) => total + component.ratio_percent, 0)
  if (Math.abs(percentageTotal - 100) > 0.001) {
    materialCompositionError.value = `当前配比合计 ${roundMaterialWeight(percentageTotal)}%，必须等于 100%。`
    return
  }

  line.material_components = components.map((component) =>
    createManualMoldingSampleMaterialComponentDraft({
      material: component.material,
      source_type: component.source_type,
      ratio_percent: String(component.ratio_percent),
    }),
  )
  line.material = formatMaterialComposition(components)
  closeMaterialCompositionEditor()
}

function getMaterialUsageType(line: ManualMoldingSampleLineDraft) {
  return line.material_usage_type
}

function updateMaterialUsageType(line: ManualMoldingSampleLineDraft, event: Event) {
  const input = event.target as HTMLSelectElement
  line.material_usage_type = input.value === 'trial' ? 'trial' : 'production'
}

function buildMaterialBalanceItemRow(item: MoldingSampleItem, canViewCost = true): MaterialBalanceItemRow {
  const expectedWeightKg = readMaterialWeight(item.required_material_kg)
  const actualWeightKg = readMaterialWeight(item.actual_weight_kg)
  const balanceWeightKg = roundMaterialWeight(expectedWeightKg - actualWeightKg)
  const isTrial = item.material_usage_type === 'trial'
  const actualAmountHkd = !canViewCost || item.actual_amount_hkd === null || item.actual_amount_hkd === undefined
    ? null
    : Number(item.actual_amount_hkd)
  const hasActualWeight = actualWeightKg > 0
  const hasKnownAmount = actualAmountHkd !== null && Number.isFinite(actualAmountHkd)
  const unitAmountHkd = hasActualWeight && hasKnownAmount ? actualAmountHkd / actualWeightKg : null
  const balanceAmountHkd = isTrial
    ? 0
    : unitAmountHkd === null
    ? (balanceWeightKg === 0 ? 0 : null)
    : roundMoney(balanceWeightKg * unitAmountHkd)

  return {
    item,
    expectedWeightKg,
    actualWeightKg,
    balanceWeightKg,
    balanceAmountHkd,
    hasActualWeight,
    isTrial,
  }
}

function buildMaterialBalanceOrderRow(record: MoldingSampleWorkflowRecord): MaterialBalanceOrderRow {
  const itemRows = record.items.map((item) => buildMaterialBalanceItemRow(item, canViewRecordCost(record)))
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
    trialItemCount: itemRows.filter((row) => row.isTrial).length,
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
      trialItemCount: 0,
    }

    group.orderRows.push(orderRow)
    group.orderCount += 1
    group.expectedWeightKg = roundMaterialWeight(group.expectedWeightKg + orderRow.expectedWeightKg)
    group.actualWeightKg = roundMaterialWeight(group.actualWeightKg + orderRow.actualWeightKg)
    group.balanceWeightKg = roundMaterialWeight(group.balanceWeightKg + orderRow.balanceWeightKg)
    group.missingActualCount += orderRow.missingActualCount
    group.unknownAmountCount += orderRow.unknownAmountCount
    group.trialItemCount += orderRow.trialItemCount
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
  const date = parseMaterialBalanceDate(readMaterialBalanceDate(record))
    ?? parseMaterialBalanceDate(getTodayText())
  const safeDate = date ?? new Date()

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
    || getTodayText()
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
  appStore.setActiveFactory(selectedFactoryId.value)
})

watch(() => readQueryString(route.query.order_id), (queryOrderId) => {
  if (!queryOrderId) {
    deepLinkedOrderRequestId += 1
    return
  }

  selectedOrderId.value = queryOrderId
  const requestedFactoryId = selectedFactoryId.value
  const shouldTrackDetailLoad = activeView.value === 'detail'
    && !apiRecords.value.some((record) => record.order.id === queryOrderId)
  if (shouldTrackDetailLoad) {
    apiState.value = 'checking'
  }

  void loadDeepLinkedOrderIfNeeded(requestedFactoryId).finally(() => {
    if (
      shouldTrackDetailLoad
      && activeView.value === 'detail'
      && requestedFactoryId === selectedFactoryId.value
      && queryOrderId === readQueryString(route.query.order_id)
    ) {
      apiState.value = apiRecords.value.some((record) => record.order.id === queryOrderId)
        ? 'connected'
        : 'empty'
    }
  })
})

restoreSavedCreateDraft()

watch(createDraft, () => {
  if (activeView.value === 'create') {
    persistCreateDraft()
  }
}, { deep: true })

watch(selectedFactoryId, () => {
  const shouldRestoreCreateDraft = activeView.value === 'create'
  excelImportRequestId += 1
  excelImporting.value = false
  if (excelFileInput.value) excelFileInput.value.value = ''
  manualCreateMutationRequestId += 1
  productionAssignmentRequestId += 1
  dispatchSubmitting.value = false
  dispatchReason.value = ''
  editingRejectedOrderId.value = ''
  createErrors.value = []
  if (shouldRestoreCreateDraft) {
    restoreSavedCreateDraft()
  }
  if (createSubmitting.value) {
    createSubmitting.value = false
    actionMessage.value = '厂区已切换，之前的啤办单提交结果不会应用到当前页面。'
  }
}, { flush: 'sync' })

watch(selectedFactoryId, () => {
  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer)
    searchDebounceTimer = null
  }
  effectiveSearchKeyword.value = searchKeyword.value.trim()
  resetPagination()
  selectedOrderId.value = readQueryString(route.query.order_id)
  void loadApiData()

  if (!isEditingRejectedOrder.value) {
    restoreSavedCreateDraft()
  }
})

watch(selectedOrderId, () => {
  productionAssignmentRequestId += 1
  dispatchSubmitting.value = false
  dispatchReason.value = ''
  dispatchProductionFactoryId.value = selectedProductionFactoryId.value
    ?? getSuggestedMoldingSampleProductionFactoryId(selectedOrder.value.factory_id)
    ?? ''
  isSelectedOrderDataExpanded.value = false
  selectedFullItemId.value = ''
})

watch(() => selectedOrder.value.production_factory_id, () => {
  if (dispatchSubmitting.value) return
  dispatchProductionFactoryId.value = selectedProductionFactoryId.value
    ?? getSuggestedMoldingSampleProductionFactoryId(selectedOrder.value.factory_id)
    ?? ''
})

watch(selectedItems, (items) => {
  if (!items.some((item) => item.id === selectedFullItemId.value)) {
    selectedFullItemId.value = items[0]?.id ?? ''
  }
}, {
  immediate: true,
})

watch(searchKeyword, (keyword) => {
  if (!serverBoardEnabled.value) {
    effectiveSearchKeyword.value = keyword
    resetPagination()
    return
  }

  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer)
  }

  searchDebounceTimer = setTimeout(() => {
    searchDebounceTimer = null
    effectiveSearchKeyword.value = keyword.trim()
    resetPagination()

    if (activeView.value === 'overview' && overviewDisplayMode.value === 'board') {
      void loadServerBoardOverview()
    }
  }, MOLDING_SAMPLE_SEARCH_DEBOUNCE_MS)
})

watch(batchSelectableRecords, (records) => {
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
})

onUnmounted(() => {
  invalidateServerBoardRequests()
  invalidateLegacyOrdersRequest()
  deepLinkedOrderRequestId += 1
  protectedMaterialPricesRequestId += 1
  rawMaterialOptionsRequestId += 1
  excelImportRequestId += 1
  manualCreateMutationRequestId += 1
  productionAssignmentRequestId += 1
  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer)
    searchDebounceTimer = null
  }
  hideActionToast()
  hideCreateSuccessToast()
})
</script>

<template>
  <main
    class="app-shell min-h-screen bg-transparent text-[13px] leading-relaxed text-slate-900"
    :aria-busy="apiState === 'checking'"
  >
    <header class="sticky top-0 z-40 border-b border-slate-200/80 bg-white/90 shadow-[0_1px_2px_rgba(15,23,42,0.04)] backdrop-blur-xl">
      <div class="app-page flex items-center gap-4 px-5 py-2.5">
        <RouterLink
          :to="engineeringDepartmentRoute"
          class="inline-flex min-h-9 shrink-0 items-center gap-2 whitespace-nowrap rounded-lg border border-slate-200 bg-white/85 px-3 text-[12px] font-semibold text-slate-600 shadow-sm transition hover:border-teal-200 hover:bg-teal-50/60 hover:text-teal-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30"
        >
          <ArrowLeft class="size-4" aria-hidden="true" />
          <span class="hidden sm:inline">工程部模块</span>
          <span class="sm:hidden">工程部</span>
        </RouterLink>

        <div class="flex min-w-0 items-center gap-2.5">
          <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-slate-800 to-teal-700 text-white shadow-[0_6px_18px_-12px_rgba(13,148,136,0.9)]">
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
            data-testid="molding-sample-search-input"
            v-model="searchKeyword"
            type="search"
            aria-label="模糊搜索啤办单"
            autocomplete="off"
            placeholder="搜索单号 / 产品 / 客户 / 模具 / 原料..."
            class="h-9 w-72 rounded-lg border border-slate-200 bg-slate-50/80 pl-8 pr-8 text-[12px] shadow-[inset_0_1px_2px_rgba(15,23,42,0.03)] outline-none transition hover:border-slate-300 hover:bg-white focus:border-teal-400 focus:bg-white focus:ring-2 focus:ring-teal-500/15"
            @keydown.esc="searchKeyword = ''"
          >
          <button
            v-if="searchKeyword"
            type="button"
            aria-label="清除搜索"
            class="absolute right-1.5 top-1/2 flex size-6 -translate-y-1/2 items-center justify-center rounded-full text-slate-400 transition hover:bg-slate-200 hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30"
            @click="searchKeyword = ''"
          >
            <X class="size-3.5" aria-hidden="true" />
          </button>
        </div>

        <div class="ml-auto flex items-center gap-3">
          <span class="hidden h-8 items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 text-[12px] font-medium text-slate-600 sm:inline-flex">
            <Building2 class="size-4" aria-hidden="true" />
            {{ activeFactory.shortName }}
          </span>
          <AccountMenu />
        </div>
      </div>

      <nav class="app-page flex items-center gap-1 overflow-x-auto px-5" aria-label="啤办业务导航">
        <button
          type="button"
          class="tab-btn inline-flex min-h-9 whitespace-nowrap items-center gap-1.5 rounded-t-lg border-b-2 border-transparent px-3 py-2 text-[12.5px] font-semibold transition hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-teal-500/35"
          :class="activeView === 'overview' ? 'border-teal-600 bg-gradient-to-r from-slate-800 to-teal-800 text-white shadow-sm' : 'text-slate-500 hover:bg-slate-50'"
          @click="setView('overview')"
        >
          <LayoutDashboard class="size-4" aria-hidden="true" />
          看板总览
        </button>
        <button
          v-if="!isSelectedFactoryReadOnly"
          type="button"
          class="tab-btn inline-flex min-h-9 whitespace-nowrap items-center gap-1.5 rounded-t-lg border-b-2 border-transparent px-3 py-2 text-[12.5px] font-semibold transition hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-teal-500/35"
          :class="activeView === 'create' ? 'border-teal-600 bg-gradient-to-r from-slate-800 to-teal-800 text-white shadow-sm' : 'text-slate-500 hover:bg-slate-50'"
          @click="startCreateOrder"
        >
          <FilePlus2 class="size-4" aria-hidden="true" />
          工程部 · 新建开单
        </button>
        <button
          type="button"
          class="tab-btn inline-flex min-h-9 whitespace-nowrap items-center gap-1.5 rounded-t-lg border-b-2 border-transparent px-3 py-2 text-[12.5px] font-semibold transition hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-teal-500/35"
          :class="activeView === 'detail' ? 'border-teal-600 bg-gradient-to-r from-slate-800 to-teal-800 text-white shadow-sm' : 'text-slate-500 hover:bg-slate-50'"
          @click="setView('detail')"
        >
          <ClipboardCheck class="size-4" aria-hidden="true" />
          单据详情 · 审核
        </button>
        <RouterLink
          :to="productionTaskRoute"
          class="ml-auto inline-flex min-h-9 whitespace-nowrap items-center gap-1.5 rounded-t-lg px-3 py-2 text-[12.5px] font-semibold text-slate-500 transition hover:bg-teal-50/60 hover:text-teal-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-teal-500/35"
        >
          <Factory class="size-4" aria-hidden="true" />
          啤办生产任务单
          <ExternalLink class="size-3.5" aria-hidden="true" />
        </RouterLink>
      </nav>
      <div
        v-if="apiState === 'checking'"
        class="h-0.5 overflow-hidden bg-teal-950/[0.05]"
        role="progressbar"
        aria-label="正在刷新啤办业务数据"
      >
        <span class="block h-full w-2/3 rounded-r-full bg-gradient-to-r from-slate-800 via-teal-600 to-cyan-400 shadow-[0_0_8px_rgba(13,148,136,0.28)] animate-pulse motion-reduce:animate-none" />
      </div>
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
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition duration-150 ease-in"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <section
        v-if="materialCompositionLineIndex !== null"
        class="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/45 p-4 backdrop-blur-sm"
        role="dialog"
        aria-modal="true"
        aria-label="配置原料配比"
        data-testid="material-composition-dialog"
        @click.self="closeMaterialCompositionEditor"
      >
        <div class="flex max-h-[min(720px,calc(100vh-2rem))] w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl shadow-slate-950/30">
          <header class="flex shrink-0 items-center gap-3 border-b border-slate-200 px-5 py-4">
            <span class="flex size-9 shrink-0 items-center justify-center rounded-lg bg-teal-50 text-teal-700">
              <Layers class="size-4" aria-hidden="true" />
            </span>
            <div class="min-w-0">
              <h2 class="text-[15px] font-bold text-slate-950">配置原料配比</h2>
              <p class="mt-0.5 text-[11px] text-slate-500">选择每个原料或水口料组分，配比合计必须为 100%。</p>
            </div>
            <button
              type="button"
              class="ml-auto flex size-8 items-center justify-center rounded-md text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
              aria-label="关闭原料配比弹窗"
              @click="closeMaterialCompositionEditor"
            >
              <X class="size-4" aria-hidden="true" />
            </button>
          </header>

          <div class="min-h-0 flex-1 overflow-y-auto p-5">
            <datalist id="molding-sample-material-composition-options">
              <option v-for="option in rawMaterialOptions" :key="`composition-${option.value}`" :value="option.value">{{ option.label }}</option>
            </datalist>

            <div class="space-y-2">
              <div class="grid grid-cols-[minmax(0,1fr)_128px_112px_36px] gap-2 px-2 text-[11px] font-semibold text-slate-500">
                <span>原料</span>
                <span>来源类型</span>
                <span class="text-right">百分比</span>
                <span class="sr-only">操作</span>
              </div>
              <div
                v-for="(component, componentIndex) in materialCompositionDraftRows"
                :key="`composition-row-${componentIndex}`"
                class="grid grid-cols-[minmax(0,1fr)_128px_112px_36px] items-center gap-2 rounded-lg border border-slate-200 bg-slate-50/70 p-2"
              >
                <input
                  v-model.trim="component.material"
                  list="molding-sample-material-composition-options"
                  :aria-label="`第 ${componentIndex + 1} 个配比原料`"
                  :data-testid="`material-component-name-${componentIndex}`"
                  placeholder="搜索原料名称或编号"
                  class="h-9 min-w-0 rounded-md border border-slate-200 bg-white px-3 text-[12px] outline-none transition focus:border-teal-400 focus:ring-2 focus:ring-teal-100"
                >
                <select
                  v-model="component.source_type"
                  :aria-label="`第 ${componentIndex + 1} 个来源类型`"
                  :data-testid="`material-component-source-${componentIndex}`"
                  class="h-9 rounded-md border border-slate-200 bg-white px-2 text-[12px] font-semibold text-slate-700 outline-none focus:border-teal-400"
                >
                  <option value="virgin">原料</option>
                  <option value="runner">水口料</option>
                </select>
                <label class="relative block">
                  <input
                    v-model="component.ratio_percent"
                    type="number"
                    min="0.01"
                    max="100"
                    step="0.01"
                    :aria-label="`第 ${componentIndex + 1} 个配比百分比`"
                    :data-testid="`material-component-percentage-${componentIndex}`"
                    class="h-9 w-full rounded-md border border-slate-200 bg-white pl-2 pr-7 text-right text-[12px] font-semibold tabular-nums outline-none focus:border-teal-400"
                  >
                  <span class="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-[11px] text-slate-400">%</span>
                </label>
                <button
                  type="button"
                  class="flex size-9 items-center justify-center rounded-md text-slate-400 transition hover:bg-red-50 hover:text-red-600"
                  :aria-label="`删除第 ${componentIndex + 1} 个配比组分`"
                  @click="removeMaterialCompositionRow(componentIndex)"
                >
                  <Trash2 class="size-4" aria-hidden="true" />
                </button>
              </div>
            </div>

            <div class="mt-3 flex flex-wrap items-center gap-2">
              <button
                type="button"
                class="inline-flex h-8 items-center gap-1.5 rounded-md border border-dashed border-slate-300 bg-white px-3 text-[11px] font-semibold text-slate-600 transition hover:border-teal-300 hover:text-teal-700"
                @click="addMaterialCompositionRow"
              >
                <Plus class="size-3.5" aria-hidden="true" />
                添加组分
              </button>
              <span
                class="ml-auto rounded-full border px-2.5 py-1 text-[11px] font-bold tabular-nums"
                :class="Math.abs(materialCompositionPercentageTotal - 100) <= 0.001 ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-amber-200 bg-amber-50 text-amber-700'"
              >
                合计 {{ materialCompositionPercentageTotal.toFixed(2) }}%
              </span>
            </div>

            <p v-if="materialCompositionError" class="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[12px] font-semibold text-red-700" role="alert">
              {{ materialCompositionError }}
            </p>
            <p class="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-[11px] leading-5 text-slate-500">
              单一原料可保持 100% 原料；水口料会参与用量拆分，其计价口径由业务规则自动处理。
            </p>
          </div>

          <footer class="flex shrink-0 items-center justify-end gap-2 border-t border-slate-200 px-5 py-3">
            <button type="button" class="h-9 rounded-md border border-slate-200 bg-white px-4 text-[12px] font-semibold text-slate-600 hover:border-slate-300" @click="closeMaterialCompositionEditor">取消</button>
            <button type="button" class="h-9 rounded-md bg-slate-950 px-5 text-[12px] font-semibold text-white transition hover:bg-slate-800" data-testid="save-material-composition" @click="saveMaterialComposition">保存配比</button>
          </footer>
        </div>
      </section>
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

                <div class="mt-3 grid gap-2 text-[12px] sm:grid-cols-2 xl:grid-cols-5">
                  <div class="rounded-md bg-slate-50 px-3 py-2">
                    <span class="block text-[11px] text-slate-400">订单号</span>
                    <strong class="font-mono text-slate-800">{{ formatBlank(record.order.order_number) }}</strong>
                  </div>
                  <div class="rounded-md bg-slate-50 px-3 py-2">
                    <span class="block text-[11px] text-slate-400">填写部 / 发至</span>
                    <strong class="text-slate-800">{{ formatBlank(record.order.workshop) }} / {{ formatBlank(record.order.send_to, '内部') }}</strong>
                  </div>
                  <div class="rounded-md bg-slate-50 px-3 py-2">
                    <span class="block text-[11px] text-slate-400">工程 / 主管</span>
                    <strong class="text-slate-800">{{ formatBlank(record.order.eng_name) }} / {{ formatBlank(record.order.supervisor) }}</strong>
                  </div>
                  <div class="rounded-md bg-teal-50 px-3 py-2">
                    <span class="block text-[11px] text-teal-600">来源厂 → 承接生产厂</span>
                    <strong class="text-teal-900">{{ getProductionRouteLabel(record.order) }}</strong>
                  </div>
                  <div class="rounded-md bg-slate-50 px-3 py-2">
                    <span class="block text-[11px] text-slate-400">业务开单 / 系统更新</span>
                    <strong class="text-slate-800">{{ formatWorkflowDate(record.order.date) }} / {{ formatWorkflowTime(record.order.updated_at) }}</strong>
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
                          <th v-if="canViewRecordCost(record)" class="px-3 py-2 text-right font-medium">费用</th>
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
                          <td v-if="canViewRecordCost(record)" class="px-3 py-2 text-right tabular-nums text-slate-700">{{ formatMoney(item.actual_amount_hkd) }}</td>
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

    <div class="app-page px-5 py-4">
      <section
        v-if="isSelectedFactoryReadOnly"
        class="mb-3 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] font-semibold text-amber-800"
      >
        <TriangleAlert class="mt-0.5 size-4 shrink-0 text-amber-600" aria-hidden="true" />
        <span
          v-if="isFixedMoldingClerkPosition"
          data-testid="molding-clerk-engineering-readonly-banner"
        >
          工程啤办看板只读：可切换查看所有厂区正式单据，但不能新建、编辑、审核、驳回、删除或导出；生产操作请前往“啤办生产任务单”。
        </span>
        <span v-else-if="isCrossFactoryReadOnly">
          跨厂只读：仅可查看啤办单，不能修改、审批、删除或导出；{{ canViewSelectedOrderCost ? '已额外授权查看成本' : '成本信息已隐藏' }}
        </span>
        <span v-else>当前厂区为只读，仅可查看数据</span>
      </section>

      <section
        class="enterprise-panel mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl px-3.5 py-3"
        aria-label="啤办业务导出打印操作区"
        data-testid="molding-sample-export-print-toolbar"
        :aria-busy="apiState === 'checking'"
      >
        <input
          ref="excelFileInput"
          type="file"
          class="hidden"
          :accept="excelAccept"
          @change="handleExcelImportFile"
        >
        <div class="min-w-[220px] flex-1">
          <div class="text-[10px] font-bold uppercase tracking-[0.16em] text-teal-700">Molding Sample Operations</div>
          <div class="mt-0.5 flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <h1 class="text-[14px] font-bold text-slate-950">{{ activeFactory.shortName }}啤办业务</h1>
            <span class="text-[11px] text-slate-500">当前共 {{ overviewOperationRecordCount }} 单 · 导出 / 打印</span>
          </div>
          <div class="mt-0.5 text-[11px] text-slate-400">选择单据后可打印详情或合并导出</div>
        </div>
        <div class="flex min-h-9 flex-wrap items-center justify-end gap-2">
          <span
            class="inline-flex min-h-8 items-center rounded-lg border border-teal-100 bg-teal-50 px-2.5 text-[12px] font-bold text-teal-700"
          >
            {{ selectedBatchCount ? `已选 ${selectedBatchCount} 单` : '默认当前单据' }}
          </span>
          <button
            v-if="canExportSelectedOrder"
            type="button"
            class="inline-flex min-h-8 items-center gap-1.5 rounded-lg border border-teal-200 bg-white px-2.5 text-[12px] font-semibold text-teal-700 transition hover:border-teal-300 hover:bg-teal-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30"
            @click="printOverview"
          >
            <Printer class="size-3.5" aria-hidden="true" />
            打印
          </button>
          <button
            v-if="!isSelectedFactoryReadOnly"
            type="button"
            class="inline-flex min-h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 text-[12px] font-semibold text-slate-600 transition hover:border-teal-200 hover:bg-teal-50/60 hover:text-teal-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30 disabled:cursor-not-allowed disabled:opacity-40"
            :disabled="excelImporting || !canCreateOrder"
            @click="triggerExcelImport"
          >
            <Upload class="size-3.5" aria-hidden="true" />
            {{ excelImporting ? '导入中...' : '导入Excel' }}
          </button>
          <button
            v-if="!isSelectedFactoryReadOnly"
            type="button"
            class="inline-flex min-h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 text-[12px] font-semibold text-slate-600 transition hover:border-teal-200 hover:bg-teal-50/60 hover:text-teal-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30 disabled:cursor-not-allowed disabled:opacity-40"
            :disabled="excelTemplateDownloading || !canCreateOrder"
            @click="downloadEngineeringImportTemplate"
          >
            <Download class="size-3.5" aria-hidden="true" />
            {{ excelTemplateDownloading ? '模板下载中...' : '下载导入模板' }}
          </button>
          <button
            v-if="!isSelectedFactoryReadOnly"
            type="button"
            class="inline-flex min-h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 text-[12px] font-semibold text-slate-600 transition hover:border-teal-200 hover:bg-teal-50/60 hover:text-teal-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30 disabled:cursor-not-allowed disabled:opacity-40"
            :disabled="excelExporting || !canExportSelectedOrder"
            @click="downloadOrderExcel"
          >
            <Download class="size-3.5" aria-hidden="true" />
            {{ excelExporting ? '导出中...' : '导出Excel' }}
          </button>
          <button
            type="button"
            class="inline-flex min-h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-2.5 text-[12px] font-semibold text-slate-600 transition hover:border-teal-200 hover:bg-white hover:text-teal-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30 disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="apiState === 'checking'"
            :aria-busy="apiState === 'checking'"
            @click="loadApiData"
          >
            <RefreshCw
              class="size-3.5"
              :class="apiState === 'checking' ? 'animate-spin motion-reduce:animate-none' : ''"
              aria-hidden="true"
            />
            {{ apiState === 'checking' ? '刷新中...' : '刷新正式列表' }}
          </button>
        </div>
      </section>

      <section v-if="activeView === 'overview'" class="space-y-4">
        <div
          data-testid="molding-kpi-grid"
          class="grid gap-3 xl:grid-cols-[minmax(0,4fr)_minmax(0,3fr)]"
        >
          <section class="reveal-grid grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="啤办流程概览">
            <article
              v-for="card in kpiCards.slice(0, 4)"
              :key="card.label"
              :data-testid="`molding-kpi-${card.key}`"
              class="enterprise-panel group relative min-h-[104px] min-w-0 overflow-clip rounded-xl border p-3.5"
              :class="card.className"
            >
              <span class="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-teal-500/55 to-transparent" aria-hidden="true" />
              <div class="flex items-center justify-between gap-3">
                <span class="truncate text-[11px] font-semibold opacity-80">{{ card.label }}</span>
                <span class="surface-subtle flex size-8 shrink-0 items-center justify-center rounded-lg transition-transform duration-200 group-hover:scale-105 motion-reduce:transition-none">
                  <component :is="card.icon" class="size-4 opacity-70" aria-hidden="true" />
                </span>
              </div>
              <div :data-testid="`molding-kpi-${card.key}-value`" class="mt-1.5 text-[26px] font-semibold leading-none tabular-nums tracking-[-0.035em] text-slate-950">{{ card.value }}</div>
              <div class="mt-1.5 break-words text-[11px] leading-4 opacity-75">{{ card.detail }}</div>
            </article>
          </section>
          <section class="reveal-grid grid grid-cols-1 gap-3 sm:grid-cols-3" aria-label="啤办风险提醒">
            <article
              v-for="card in kpiCards.slice(4)"
              :key="card.label"
              :data-testid="`molding-kpi-${card.key}`"
              class="enterprise-panel group relative min-h-[104px] min-w-0 overflow-clip rounded-xl border p-3.5"
              :class="card.className"
            >
              <span class="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-teal-500/40 to-transparent" aria-hidden="true" />
              <div class="flex items-center justify-between gap-3">
                <span class="truncate text-[11px] font-semibold opacity-80">{{ card.label }}</span>
                <span class="surface-subtle flex size-8 shrink-0 items-center justify-center rounded-lg transition-transform duration-200 group-hover:scale-105 motion-reduce:transition-none">
                  <component :is="card.icon" class="size-4 opacity-70" aria-hidden="true" />
                </span>
              </div>
              <div :data-testid="`molding-kpi-${card.key}-value`" class="mt-1.5 text-[26px] font-semibold leading-none tabular-nums tracking-[-0.035em] text-slate-950">{{ card.value }}</div>
              <div class="mt-1.5 break-words text-[11px] leading-4 opacity-75">{{ card.detail }}</div>
            </article>
          </section>
        </div>

        <div class="enterprise-panel flex flex-wrap items-center gap-2 rounded-xl p-2.5">
          <div class="surface-subtle flex items-center gap-1 rounded-lg p-0.5" role="group" aria-label="总览显示方式">
            <button
              type="button"
              class="inline-flex min-h-8 items-center gap-1 rounded-md px-2.5 text-[12px] transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30"
              :class="overviewDisplayMode === 'board' ? 'bg-teal-700 font-semibold text-white shadow-sm' : 'font-medium text-slate-500 hover:bg-white hover:text-slate-900'"
              :aria-pressed="overviewDisplayMode === 'board'"
              @click="setOverviewDisplayMode('board')"
            >
              <LayoutDashboard class="size-3.5" aria-hidden="true" />
              看板
            </button>
            <button
              type="button"
              class="inline-flex min-h-8 items-center gap-1 rounded-md px-2.5 text-[12px] transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30"
              :class="overviewDisplayMode === 'list' ? 'bg-teal-700 font-semibold text-white shadow-sm' : 'font-medium text-slate-500 hover:bg-white hover:text-slate-900'"
              :aria-pressed="overviewDisplayMode === 'list'"
              @click="setOverviewDisplayMode('list')"
            >
              <Table2 class="size-3.5" aria-hidden="true" />
              列表
            </button>
          </div>
          <span class="mx-1 h-5 w-px bg-slate-200" aria-hidden="true" />
          <span class="inline-flex min-h-8 items-center gap-1 rounded-lg border border-slate-200 bg-slate-50/80 px-2.5 text-[12px] font-medium text-slate-600">
            <Filter class="size-3.5" aria-hidden="true" />
            车间：{{ selectedOrder.workshop || '全部' }}
          </span>
          <span class="inline-flex min-h-8 items-center gap-1 rounded-lg border border-slate-200 bg-slate-50/80 px-2.5 text-[12px] font-medium text-slate-600">
            <UserRound class="size-3.5" aria-hidden="true" />
            主管：{{ selectedOrder.supervisor || '全部' }}
          </span>
          <span class="inline-flex min-h-8 items-center gap-1 rounded-lg border border-slate-200 bg-slate-50/80 px-2.5 text-[12px] font-medium text-slate-600">
            <Tag class="size-3.5" aria-hidden="true" />
            类型：啤办
          </span>
          <div class="surface-subtle flex min-h-9 flex-wrap items-center gap-1.5 rounded-lg px-1.5 py-0.5 text-[12px] text-slate-600">
            <button
              type="button"
              class="inline-flex min-h-8 items-center rounded-md px-2 font-semibold transition hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30 disabled:cursor-not-allowed disabled:opacity-40"
              :disabled="!batchSelectableRecords.length || isAllVisibleOrdersSelected"
              @click="selectAllVisibleOrders"
            >
              {{ serverBoardEnabled && overviewDisplayMode === 'board' ? '全选当前页' : '全选当前筛选单据' }}
            </button>
            <button
              type="button"
              class="inline-flex min-h-8 items-center rounded-md px-2 font-semibold transition hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30 disabled:cursor-not-allowed disabled:opacity-40"
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
            class="ml-auto inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-teal-200 bg-teal-50 px-3 text-[12px] font-semibold text-teal-700 transition hover:border-teal-300 hover:bg-teal-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30"
            data-testid="material-balance-button"
            @click="setView('material-balance')"
          >
            <Beaker class="size-4" aria-hidden="true" />
            物料结余
          </button>
          <button
            v-if="!isSelectedFactoryReadOnly"
            type="button"
            class="inline-flex min-h-9 items-center gap-1.5 rounded-lg bg-gradient-to-r from-slate-800 to-teal-800 px-3 text-[12px] font-semibold text-white shadow-sm transition hover:from-slate-700 hover:to-teal-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/40"
            @click="startCreateOrder"
          >
            <Plus class="size-4" aria-hidden="true" />
            新建啤办单
          </button>
        </div>

        <div
          v-if="overviewDisplayMode === 'board'"
          class="reveal-grid grid grid-cols-1 gap-3 overflow-x-auto overscroll-x-contain pb-2 md:grid-cols-2 xl:grid-flow-col xl:auto-cols-[minmax(260px,1fr)] xl:grid-cols-none"
        >
          <section
            v-for="column in boardColumns"
            :key="column.status"
            class="surface-subtle min-h-[244px] overflow-hidden rounded-xl"
            role="region"
            :aria-label="`${column.label}看板列`"
            :aria-busy="column.loading"
            :data-testid="`molding-board-column-${column.status}`"
          >
            <div class="flex items-center justify-between border-b border-slate-200/70 bg-white/60 px-3 py-2.5 backdrop-blur-sm">
              <div class="flex min-w-0 items-center gap-2">
                <span class="h-2.5 w-2.5 shrink-0 rounded-full" :class="column.dotClass" />
                <div class="min-w-0">
                  <div class="truncate text-[12.5px] font-bold">{{ column.label }}</div>
                  <div class="truncate text-[10px] text-slate-400">{{ column.detail }}</div>
                </div>
              </div>
              <div class="flex shrink-0 items-center gap-1.5">
                <RefreshCw
                  v-if="column.loading"
                  class="size-3.5 animate-spin text-teal-600 motion-reduce:animate-none"
                  aria-hidden="true"
                />
                <span class="rounded-full bg-white px-2 py-0.5 text-[11px] font-bold text-slate-600 shadow-sm ring-1 ring-slate-200">
                  {{ column.pagination.total }}
                </span>
              </div>
            </div>

            <div class="space-y-2 px-2 pb-2">
              <article
                v-for="record in column.pagedRecords"
                :key="record.order.id"
                class="enterprise-panel interactive-surface relative w-full overflow-hidden rounded-xl border p-3 text-left"
                :class="selectedOrder.id === record.order.id ? 'border-teal-300 bg-teal-50/70 shadow-[0_12px_28px_-24px_rgba(13,148,136,0.85)] ring-1 ring-teal-200' : isOrderBatchSelected(record.order.id) ? 'border-teal-300 bg-teal-50/35 ring-1 ring-teal-100' : 'border-slate-200 hover:border-teal-200'"
              >
                <span
                  v-if="selectedOrder.id === record.order.id"
                  class="absolute inset-y-2 left-0 w-0.5 rounded-r-full bg-teal-500"
                  aria-hidden="true"
                />
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
                    class="min-h-8 min-w-0 flex-1 rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30"
                    :aria-current="selectedOrder.id === record.order.id ? 'true' : undefined"
                    @click="openRecord(record)"
                  >
                    <div class="flex items-center justify-between gap-2">
                      <span class="font-mono text-[12px] font-bold text-slate-800">{{ record.order.id }}</span>
                      <span class="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500">{{ record.order.stage || '啤办' }}</span>
                    </div>
                    <div class="mt-1.5 truncate text-[13px] font-semibold text-slate-950">{{ record.order.product_name }}</div>
                    <div class="mt-0.5 truncate text-[11px] text-slate-500">{{ record.order.client_name }} · {{ record.items.length }} 项明细</div>
                    <div class="mt-1 truncate text-[10px] font-semibold text-teal-700" :title="getProductionRouteLabel(record.order)">
                      {{ getProductionRouteLabel(record.order) }}
                    </div>
                    <div class="mt-2 flex items-center justify-between gap-2 border-t border-slate-100 pt-2 text-[11px]">
                      <span class="truncate text-slate-500">{{ getFlowSummary(record) }}</span>
                      <span class="shrink-0 text-slate-400">{{ getWorkflowDateLabel(record) }}</span>
                    </div>
                  </button>
                </div>
              </article>

              <div
                v-if="column.loading && !column.pagedRecords.length"
                class="rounded-xl border border-dashed border-teal-200 bg-teal-50/60 p-5 text-center text-[11px] font-medium text-teal-700"
                role="status"
              >
                正在加载{{ column.label }}单据...
              </div>
              <div
                v-else-if="!column.pagination.total"
                class="rounded-xl border border-dashed border-slate-200 bg-white/70 p-5 text-center text-[11px] font-medium text-slate-400"
              >
                暂无{{ column.label }}单据
              </div>
            </div>
            <div
              v-if="column.pagination.total"
              class="border-t border-slate-200/80 bg-white/45 px-2 py-2 text-[11px] text-slate-500"
            >
              <div class="mb-1.5 flex items-center justify-between gap-2">
                <span class="font-medium">每页 5 条</span>
                <span class="tabular-nums">{{ formatPaginationRange(column.pagination) }}</span>
              </div>
              <div class="flex items-center justify-between gap-2">
                <button
                  type="button"
                  class="inline-flex min-h-8 items-center gap-1 rounded-md border border-slate-200 bg-white px-2 font-semibold text-slate-600 transition hover:border-teal-200 hover:text-teal-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30 disabled:cursor-not-allowed disabled:opacity-40"
                  :disabled="column.loading || !column.pagination.hasPrevious"
                  :aria-label="`${column.label}上一页`"
                  @click="setBoardColumnPage(column.status, column.pagination.page - 1)"
                >
                  <ChevronLeft class="size-3.5" aria-hidden="true" />
                  上一页
                </button>
                <span class="shrink-0 tabular-nums">{{ column.pagination.page }} / {{ column.pagination.pageCount }} 页</span>
                <button
                  type="button"
                  class="inline-flex min-h-8 items-center gap-1 rounded-md border border-slate-200 bg-white px-2 font-semibold text-slate-600 transition hover:border-teal-200 hover:text-teal-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30 disabled:cursor-not-allowed disabled:opacity-40"
                  :disabled="column.loading || !column.pagination.hasNext"
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
        <section v-else class="enterprise-panel overflow-hidden rounded-xl">
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
                class="inline-flex min-h-8 items-center gap-1 rounded-md border border-slate-200 bg-white px-2 font-semibold text-slate-600 transition hover:border-teal-200 hover:text-teal-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30 disabled:cursor-not-allowed disabled:opacity-40"
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
                class="inline-flex min-h-8 items-center gap-1 rounded-md border border-slate-200 bg-white px-2 font-semibold text-slate-600 transition hover:border-teal-200 hover:text-teal-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30 disabled:cursor-not-allowed disabled:opacity-40"
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
            <table aria-label="啤办单列表" class="w-full min-w-[1160px] text-[12px]">
              <thead>
                <tr class="border-b border-slate-100 bg-slate-50 text-[11px] text-slate-500">
                  <th class="px-3 py-2 text-left font-medium">选择</th>
                  <th class="px-3 py-2 text-left font-medium">单号</th>
                  <th class="px-3 py-2 text-left font-medium">产品 / 客户</th>
                  <th class="px-3 py-2 text-left font-medium">状态</th>
                  <th class="px-3 py-2 text-left font-medium">阶段</th>
                  <th class="px-3 py-2 text-left font-medium">明细</th>
                  <th class="px-3 py-2 text-left font-medium">工程 / 主管</th>
                  <th class="px-3 py-2 text-left font-medium">来源 / 承接生产</th>
                  <th class="px-3 py-2 text-left font-medium">进度</th>
                  <th class="px-3 py-2 text-right font-medium">流程日期</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-50">
                <tr
                  v-for="record in paginatedVisibleRecords"
                  :key="record.order.id"
                  class="cursor-pointer transition hover:bg-slate-50"
                  :class="selectedOrder.id === record.order.id ? 'bg-teal-50/70 ring-1 ring-inset ring-teal-200' : ''"
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
                    <button type="button" class="min-h-8 rounded-md font-mono text-[12px] font-bold text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30">
                      {{ record.order.id }}
                    </button>
                    <div class="mt-0.5 text-[10px] text-slate-400">{{ record.order.order_number || '未填产品号' }}</div>
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
                    <div class="whitespace-nowrap font-semibold text-teal-700">{{ getProductionRouteLabel(record.order) }}</div>
                    <div class="mt-0.5 text-[10px] text-slate-400">整单承接 · 不拆分明细</div>
                  </td>
                  <td class="px-3 py-2.5 align-top">
                    <div class="max-w-[220px] truncate text-slate-600">{{ getFlowSummary(record) }}</div>
                    <div v-if="record.problems.length" class="mt-0.5 text-[11px] font-semibold text-red-500">{{ record.problems.length }} 个问题</div>
                  </td>
                  <td class="px-3 py-2.5 text-right align-top tabular-nums text-slate-500">
                    {{ getWorkflowDateLabel(record) }}
                  </td>
                </tr>
                <tr v-if="!visibleRecords.length">
                    <td colspan="10" class="px-3 py-10 text-center text-[12px] font-medium text-slate-400">
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
              <div v-if="materialBalanceSummary.trialItemCount" class="mt-2 inline-flex rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-[11px] font-semibold text-amber-700">
                {{ materialBalanceSummary.trialItemCount }} 项试料金额不计结余；用料重量仍保留
              </div>
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

        <div
          class="grid grid-cols-2 gap-3 sm:grid-cols-3"
          :class="canViewActiveFactoryCosts ? 'xl:grid-cols-5' : 'xl:grid-cols-4'"
        >
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
          <article v-if="canViewActiveFactoryCosts" class="min-h-[86px] rounded-lg border border-emerald-100 bg-emerald-50 p-3">
            <div class="text-[11px] font-medium text-emerald-700">结余金额</div>
            <div class="mt-1 text-2xl font-bold tabular-nums" :class="getBalanceValueClass(materialBalanceSummary.knownBalanceAmountHkd)">
              {{ formatSignedMoney(materialBalanceSummary.knownBalanceAmountHkd) }}
            </div>
            <div class="text-[11px] text-emerald-500">
              {{ materialBalanceSummary.unknownAmountCount ? `${materialBalanceSummary.unknownAmountCount} 单待计算` : materialBalanceSummary.trialItemCount ? `${materialBalanceSummary.trialItemCount} 项试料已排除金额` : '已全部折算' }}
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
                  <th v-if="canViewActiveFactoryCosts" class="px-3 py-2 text-right font-medium">结余金额</th>
                  <th v-if="canViewActiveFactoryCosts" class="px-3 py-2 text-left font-medium">折算状态</th>
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
                  <td v-if="canViewActiveFactoryCosts" class="px-3 py-2.5 text-right align-top font-bold tabular-nums" :class="getBalanceValueClass(row.balanceAmountHkd)">
                    {{ formatSignedMoney(row.balanceAmountHkd) }}
                  </td>
                  <td v-if="canViewActiveFactoryCosts" class="px-3 py-2.5 align-top">
                    <div class="flex flex-col items-start gap-1">
                      <span
                        class="inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold"
                        :class="row.missingActualCount ? 'border-amber-200 bg-amber-50 text-amber-700' : row.unknownAmountCount ? 'border-slate-200 bg-slate-50 text-slate-500' : 'border-emerald-200 bg-emerald-50 text-emerald-700'"
                      >
                        {{ row.missingActualCount ? `${row.missingActualCount} 项待回填` : row.unknownAmountCount ? `${row.unknownAmountCount} 项待计价` : '已折算' }}
                      </span>
                      <span v-if="row.trialItemCount" class="inline-flex rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-bold text-amber-700">
                        {{ row.trialItemCount }} 项试料金额不计结余
                      </span>
                    </div>
                  </td>
                </tr>
                <tr v-if="!materialBalancePeriodRows.length">
                    <td :colspan="canViewActiveFactoryCosts ? 7 : 5" class="px-3 py-10 text-center text-[12px] font-medium text-slate-400">
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
                  <th v-if="canViewActiveFactoryCosts" class="px-3 py-2 text-right font-medium">结余金额</th>
                  <th v-if="canViewActiveFactoryCosts" class="px-3 py-2 text-left font-medium">折算状态</th>
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
                    <div class="mt-0.5 text-[10px] text-slate-400">{{ row.record.order.order_number || '未填产品号' }}</div>
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
                    <div v-if="row.trialItemCount" class="mt-1 text-[10px] font-semibold text-amber-700">
                      {{ row.trialItemCount }} 项试料金额不计结余
                    </div>
                  </td>
                  <td class="px-3 py-2.5 text-right align-top tabular-nums text-slate-700">{{ formatWeight(row.expectedWeightKg) }}</td>
                  <td class="px-3 py-2.5 text-right align-top tabular-nums text-slate-700">{{ formatWeight(row.actualWeightKg) }}</td>
                  <td class="px-3 py-2.5 text-right align-top font-bold tabular-nums" :class="getBalanceValueClass(row.balanceWeightKg)">
                    {{ formatSignedWeight(row.balanceWeightKg) }}
                  </td>
                  <td v-if="canViewActiveFactoryCosts" class="px-3 py-2.5 text-right align-top font-bold tabular-nums" :class="getBalanceValueClass(row.balanceAmountHkd)">
                    {{ formatSignedMoney(row.balanceAmountHkd) }}
                  </td>
                  <td v-if="canViewActiveFactoryCosts" class="px-3 py-2.5 align-top">
                    <span
                      class="inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold"
                      :class="row.missingActualCount ? 'border-amber-200 bg-amber-50 text-amber-700' : row.unknownAmountCount ? 'border-slate-200 bg-slate-50 text-slate-500' : 'border-emerald-200 bg-emerald-50 text-emerald-700'"
                    >
                      {{ row.missingActualCount ? `${row.missingActualCount} 项待回填` : row.unknownAmountCount ? `${row.unknownAmountCount} 项待计价` : '已折算' }}
                    </span>
                  </td>
                </tr>
                <tr v-if="!materialBalanceRows.length">
                  <td :colspan="canViewActiveFactoryCosts ? 9 : 7" class="px-3 py-10 text-center text-[12px] font-medium text-slate-400">
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
                  <span class="mb-1 block text-[11px] font-medium text-slate-500">客户</span>
                  <input v-model="createDraft.client_name" data-testid="create-client-name" class="h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-[12px] outline-none focus:border-slate-400">
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
                  <select v-model="createDraft.workshop" class="h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-[12px] outline-none focus:border-slate-400" @change="syncCreateDraftProductionAssignment">
                    <option>工程部</option>
                    <option>PMC部</option>
                    <option>生产部</option>
                    <option>QA部</option>
                    <option>业务部</option>
                  </select>
                </label>
                <label class="block">
                  <span class="mb-1 block text-[11px] font-medium text-slate-500">发至</span>
                  <input
                    v-model="createDraft.send_to"
                    data-testid="create-send-to"
                    placeholder="填写发至位置"
                    class="h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-[12px] outline-none focus:border-slate-400"
                    @change="syncCreateDraftProductionAssignment"
                  >
                </label>
                <label class="block">
                  <span class="mb-1 block text-[11px] font-medium text-slate-500">承接生产厂</span>
                  <select
                    v-if="activeFactoryCapability?.dispatchMode === 'cross-factory' && !createDraftIsExternal"
                    v-model="createDraft.production_factory_id"
                    data-testid="create-production-factory"
                    :disabled="isEditingRejectedOrder"
                    class="h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-[12px] font-semibold text-slate-700 outline-none focus:border-teal-400 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
                  >
                    <option :value="null" disabled>请选择承接生产厂</option>
                    <option
                      v-for="factoryId in allowedCreateProductionFactoryIds"
                      :key="factoryId"
                      :value="factoryId"
                    >
                      {{ getMoldingSampleFactoryLabel(factoryId) }}
                    </option>
                  </select>
                  <div
                    v-else
                    data-testid="create-production-factory-readonly"
                    class="flex h-8 items-center rounded-md border border-slate-200 bg-slate-50 px-2 text-[12px] font-semibold text-slate-600"
                  >
                    {{ getCreateDraftProductionFactoryLabel() }}
                  </div>
                  <span
                    v-if="activeFactoryCapability?.dispatchMode === 'cross-factory' && !createDraftIsExternal"
                    class="mt-1 block text-[10px] text-slate-400"
                  >
                    {{ isEditingRejectedOrder ? '修改承接厂请先返回详情页使用“确认改派”，改派原因会单独留痕。' : `${activeFactory.shortName}没有啤机部，内部单必须由华康A或华康B整单承接；审核通过后，任务将进入所选厂区的啤机生产队列。` }}
                  </span>
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
                  <div class="min-w-[2180px]" role="table" aria-label="模具明细录入表">
                    <div
                      class="grid items-center gap-x-2 border-b border-slate-200 bg-slate-50 px-3 py-2.5 text-[11px] font-semibold text-slate-500"
                      :class="createLineGridClass"
                      role="row"
                    >
                      <div class="min-w-0 text-center" role="columnheader">#</div>
                      <div class="min-w-0 truncate px-2" role="columnheader">模具编号</div>
                      <div class="min-w-0 truncate px-2" role="columnheader">模具名称</div>
                      <div class="min-w-0 truncate px-2" role="columnheader">所需用料</div>
                      <div class="min-w-0 truncate px-2 text-right" role="columnheader">原料价格(HKD/磅)</div>
                      <div class="min-w-0 truncate px-2" role="columnheader">颜色</div>
                      <div class="min-w-0 truncate px-2" role="columnheader">PMS</div>
                      <div class="min-w-0 truncate px-2" role="columnheader">色粉</div>
                      <div class="min-w-0 truncate px-2 text-center" role="columnheader">啤/套</div>
                      <div class="min-w-0 truncate px-2 text-right" role="columnheader">啤数</div>
                      <div class="min-w-0 truncate px-2 text-right" role="columnheader">所需用料(kg)</div>
                      <div class="min-w-0 truncate px-2" role="columnheader">需办日期</div>
                      <div class="min-w-0 truncate px-2" role="columnheader">工模尺寸</div>
                      <div class="min-w-0 truncate px-2" role="columnheader">模具状态（是否在厂）</div>
                      <div class="min-w-0 truncate px-2" role="columnheader">用料用途</div>
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
                          <button
                            type="button"
                            class="mt-1 inline-flex h-6 items-center gap-1 rounded-md border border-teal-200 bg-teal-50 px-2 text-[10px] font-semibold text-teal-700 transition hover:border-teal-300 hover:bg-teal-100"
                            :data-testid="`create-line-material-composition-${index}`"
                            @click="openMaterialCompositionEditor(line, index)"
                          >
                            <Layers class="size-3" aria-hidden="true" />
                            配置配比
                          </button>
                        </div>
                        <div class="min-w-0" role="cell">
                          <div
                            data-testid="create-line-material-price"
                            class="flex h-9 w-full min-w-0 items-center justify-end gap-1 rounded-md border border-slate-200 bg-slate-50 px-2 text-[12px] text-slate-500"
                            :class="getDraftWeightedUnitPrice(line) !== null ? 'font-semibold tabular-nums text-slate-700' : ''"
                            :title="line.material ? `${line.material} · 加权价 ${getDraftWeightedUnitPriceLabel(line)} / 磅` : '请选择所需用料后显示原料价格'"
                          >
                            <span>{{ getDraftWeightedUnitPriceLabel(line) }}</span>
                            <span v-if="getDraftWeightedUnitPrice(line) !== null" class="text-[10px] font-medium text-slate-400">/ 磅</span>
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
                          <input v-model="line.required_material_kg" data-testid="create-line-required-material" inputmode="decimal" placeholder="kg" class="h-9 w-full min-w-0 rounded-md border border-slate-200 bg-white px-2 text-right outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-100">
                        </div>
                        <div class="min-w-0" role="cell">
                          <input v-model="line.required_date" data-testid="create-line-required-date" type="date" class="h-9 w-full min-w-0 rounded-md border border-slate-200 bg-white px-2 outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-100">
                        </div>
                        <div class="min-w-0" role="cell"><input v-model="line.mold_dimensions" data-testid="create-line-mold-dimensions" class="h-9 w-full min-w-0 rounded-md border border-slate-200 bg-white px-2"></div>
                        <div class="min-w-0" role="cell"><select v-model="line.mold_presence_status" data-testid="create-line-mold-presence-status" class="h-9 w-full min-w-0 rounded-md border border-slate-200 bg-white px-2"><option value="">待确认</option><option value="in_factory">在厂</option><option value="out_of_factory">不在厂</option></select></div>
                        <div class="min-w-0" role="cell">
                          <select
                            :value="getMaterialUsageType(line)"
                            data-testid="create-line-material-usage-type"
                            aria-label="用料用途"
                            class="h-9 w-full min-w-0 rounded-md border border-slate-200 bg-white px-2 text-[11px] font-semibold text-slate-700"
                            @change="updateMaterialUsageType(line, $event)"
                          >
                            <option value="production">正式生产</option>
                            <option value="trial">试料</option>
                          </select>
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
                <div class="flex justify-between gap-3"><span>生产承接</span><strong class="text-right text-slate-800">{{ getMoldingSampleFactoryLabel(selectedFactoryId) }} → {{ getCreateDraftProductionFactoryLabel() }}</strong></div>
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
                <span class="rounded bg-teal-50 px-1.5 py-0.5 text-[10px] font-bold text-teal-700">
                  {{ selectedProductionRouteLabel }}
                </span>
              </div>
              <div class="mt-1 text-[15px] font-bold">{{ selectedOrder.product_name }} · {{ selectedOrder.client_name }}</div>
              <div class="mt-1 flex flex-wrap gap-x-4 text-[11px] text-slate-400">
                <span>{{ selectedOrder.workshop }}</span>
                <span>工程 {{ selectedOrder.eng_name }}</span>
                <span>主管 {{ selectedOrder.supervisor }}</span>
                <span>业务开单 {{ formatWorkflowDate(selectedOrder.date) }}</span>
                <span v-if="selectedOrder.production_assigned_at">派厂 {{ formatWorkflowTime(selectedOrder.production_assigned_at) }}</span>
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
                v-if="!isSelectedFactoryReadOnly && selectedOrder.status === '待审核'"
                type="button"
                :disabled="!canWithdrawSelectedOrder || withdrawSubmitting"
                class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-3 text-[12px] font-semibold text-amber-700 hover:bg-amber-100 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-400"
                @click="withdrawSelectedOrder"
              >
                <RotateCcw class="size-4" aria-hidden="true" />
                {{ withdrawSubmitting ? '撤回中...' : '撤回审核' }}
              </button>
              <button
                v-if="!isSelectedFactoryReadOnly && (selectedOrder.status === '已驳回' || selectedOrder.status === '已撤回')"
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
                v-if="!isSelectedFactoryReadOnly"
                :to="productionTaskRoute"
                class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-slate-900 px-3 text-[12px] font-semibold text-white hover:bg-slate-700"
              >
                <Factory class="size-4" aria-hidden="true" />
                啤办生产任务单
              </RouterLink>
            </div>
          </div>
        </section>

        <section
          class="rounded-lg border border-teal-200 bg-gradient-to-br from-white to-teal-50/50 p-4"
          data-testid="molding-sample-dispatch-panel"
        >
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div class="flex items-center gap-2">
                <Factory class="size-4 text-teal-700" aria-hidden="true" />
                <h2 class="text-[13px] font-bold text-slate-950">生产承接与派厂记录</h2>
                <span class="rounded-full bg-teal-100 px-2 py-0.5 text-[10px] font-bold text-teal-800">{{ selectedProductionRouteLabel }}</span>
              </div>
              <p class="mt-1 text-[11px] text-slate-500">
                来源厂负责工程审核；承接生产厂负责啤机任务。每次派厂都会形成不可变记录。
              </p>
            </div>
            <div class="text-right text-[10px] text-slate-400">
              <div>派厂版本 {{ selectedOrder.production_assignment_version }}</div>
              <div v-if="selectedOrder.production_assigned_by" class="mt-0.5">
                {{ selectedOrder.production_assigned_by }} · {{ formatWorkflowTime(selectedOrder.production_assigned_at) }}
              </div>
            </div>
          </div>

          <div class="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-5" data-testid="molding-sample-production-collaboration-summary">
            <div class="rounded-lg border border-slate-200 bg-white px-3 py-2">
              <div class="text-[10px] font-semibold text-slate-400">当前生产状态</div>
              <div class="mt-0.5 text-[12px] font-bold text-slate-800">{{ selectedOrder.status }}</div>
            </div>
            <div class="rounded-lg border border-slate-200 bg-white px-3 py-2">
              <div class="text-[10px] font-semibold text-slate-400">开始人 / 时间</div>
              <div class="mt-0.5 text-[12px] font-bold text-slate-800">{{ selectedProductionStartAudit?.actor_name || '未开始' }}</div>
              <div v-if="selectedProductionStartAudit" class="mt-0.5 text-[10px] text-slate-400">{{ formatWorkflowTime(selectedProductionStartAudit.created_at) }}</div>
            </div>
            <div class="rounded-lg border border-slate-200 bg-white px-3 py-2">
              <div class="text-[10px] font-semibold text-slate-400">完成人 / 时间</div>
              <div class="mt-0.5 text-[12px] font-bold text-slate-800">{{ selectedProductionCompleteAudit?.actor_name || '未完成' }}</div>
              <div v-if="selectedProductionCompleteAudit" class="mt-0.5 text-[10px] text-slate-400">{{ formatWorkflowTime(selectedProductionCompleteAudit.created_at) }}</div>
            </div>
            <div class="rounded-lg border border-slate-200 bg-white px-3 py-2">
              <div class="text-[10px] font-semibold text-slate-400">派厂人 / 时间</div>
              <div class="mt-0.5 text-[12px] font-bold text-slate-800">{{ selectedOrder.production_assigned_by || '未记录' }}</div>
              <div v-if="selectedOrder.production_assigned_at" class="mt-0.5 text-[10px] text-slate-400">{{ formatWorkflowTime(selectedOrder.production_assigned_at) }}</div>
            </div>
            <div class="rounded-lg border border-slate-200 bg-white px-3 py-2">
              <div class="text-[10px] font-semibold text-slate-400">最近通知状态</div>
              <div class="mt-0.5 text-[12px] font-bold text-slate-800">
                {{ selectedLatestNotification ? `${selectedLatestNotification.event_type} · ${selectedLatestNotification.status}` : '暂无通知' }}
              </div>
              <div v-if="selectedLatestNotification" class="mt-0.5 text-[10px] text-slate-400">
                {{ formatWorkflowTime(selectedLatestNotification.created_at) }}
              </div>
            </div>
          </div>

          <form
            v-if="canDispatchSelectedOrder"
            data-testid="molding-sample-dispatch-form"
            class="mt-3 grid gap-2 rounded-lg border border-teal-200 bg-white p-3 md:grid-cols-[180px_minmax(240px,1fr)_auto]"
            @submit.prevent="updateSelectedProductionAssignment"
          >
            <label class="block">
              <span class="mb-1 block text-[10px] font-semibold text-slate-500">改派至承接生产厂</span>
              <select
                v-model="dispatchProductionFactoryId"
                data-testid="dispatch-production-factory"
                class="h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-[12px] font-semibold text-slate-700 outline-none focus:border-teal-400"
              >
                <option
                  v-for="factoryId in selectedFactoryCapability?.allowedProductionFactoryIds ?? []"
                  :key="factoryId"
                  :value="factoryId"
                >
                  {{ getMoldingSampleFactoryLabel(factoryId) }}
                </option>
              </select>
            </label>
            <label class="block">
              <span class="mb-1 block text-[10px] font-semibold text-slate-500">改派原因（必填）</span>
              <input
                v-model="dispatchReason"
                data-testid="dispatch-reason"
                maxlength="1000"
                placeholder="例如：A厂机台排期冲突，改由B厂整单承接"
                class="h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-[12px] outline-none focus:border-teal-400"
              >
            </label>
            <button
              type="submit"
              :disabled="dispatchSubmitting"
              class="mt-auto inline-flex h-9 items-center justify-center gap-1.5 rounded-md bg-teal-700 px-3 text-[12px] font-semibold text-white transition hover:bg-teal-600 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              <RefreshCw :class="dispatchSubmitting ? 'animate-spin' : ''" class="size-3.5" aria-hidden="true" />
              {{ dispatchSubmitting ? '改派中...' : '确认改派' }}
            </button>
          </form>
          <p
            v-else
            class="mt-3 rounded-lg border border-slate-200 bg-white px-3 py-2 text-[11px] text-slate-500"
          >
            {{ selectedDispatchUnavailableReason }}
          </p>

          <ol v-if="selectedDispatchLogs.length" class="mt-3 grid gap-2 lg:grid-cols-2">
            <li
              v-for="log in selectedDispatchLogs"
              :key="log.id"
              class="rounded-lg border border-slate-200 bg-white px-3 py-2 text-[11px]"
            >
              <div class="flex flex-wrap items-center justify-between gap-2">
                <strong class="text-slate-800">{{ log.action }} · {{ getMoldingSampleFactoryLabel(log.from_production_factory_id) }} → {{ getMoldingSampleFactoryLabel(log.to_production_factory_id) }}</strong>
                <span class="text-slate-400">{{ formatWorkflowTime(log.created_at) }}</span>
              </div>
              <p class="mt-1 leading-5 text-slate-600">{{ log.reason }}</p>
              <p class="mt-1 text-[10px] text-slate-400">{{ log.actor_name }} · 来源 {{ getMoldingSampleFactoryLabel(log.origin_factory_id) }}</p>
            </li>
          </ol>
          <p v-else class="mt-3 text-[11px] text-slate-400">暂无派厂变更记录。</p>
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

        <div class="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
          <div class="min-w-0 space-y-4">
            <section class="min-w-0 rounded-lg border border-slate-200 bg-white">
              <div class="flex flex-wrap items-center gap-2 border-b border-slate-100 px-4 py-2.5">
                <Table2 class="size-4 text-slate-400" aria-hidden="true" />
                <span class="text-[13px] font-bold">模具明细</span>
                <span class="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-500">{{ selectedItems.length }} 项</span>
                <button
                  type="button"
                  class="ml-auto inline-flex h-7 items-center rounded-md border border-slate-200 bg-white px-2 text-[11px] font-semibold text-slate-600 transition hover:border-slate-300 hover:text-slate-950"
                  :aria-expanded="isSelectedOrderDataExpanded"
                  aria-controls="molding-sample-full-data"
                  @click="toggleSelectedOrderData"
                >
                  {{ isSelectedOrderDataExpanded ? '收起完整数据' : '展开完整数据' }}
                </button>
              </div>
              <div
                data-testid="molding-sample-detail-scroll-region"
                class="sidebar-scrollbar overflow-x-auto focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-teal-500 md:max-h-[min(62vh,640px)] md:overflow-auto"
                role="region"
                :aria-label="`模具明细，共 ${selectedItems.length} 项`"
                tabindex="0"
                @wheel="handoffWheelAtBoundary"
              >
                <table data-testid="molding-sample-detail-table" class="w-full min-w-[920px] table-fixed text-[12px]">
                  <colgroup>
                    <col class="w-[24%]" />
                    <col class="w-[24%]" />
                    <col class="w-[21%]" />
                    <col class="w-[23%]" />
                    <col class="w-[8%]" />
                  </colgroup>
                  <thead class="sticky top-0 z-10 shadow-[0_1px_0_0_rgba(226,232,240,1)]">
                    <tr class="border-b border-slate-200 bg-slate-50/80 text-[11px] text-slate-500">
                      <th scope="col" class="px-4 py-2.5 text-left font-semibold">模具资料</th>
                      <th scope="col" class="border-l border-slate-200/80 px-4 py-2.5 text-left font-semibold">原料 / 颜色</th>
                      <th scope="col" class="border-l border-slate-200/80 px-4 py-2.5 text-left font-semibold">
                        {{ canViewSelectedOrderCost ? '预计用料 / 料费' : '预计用料' }}
                      </th>
                      <th scope="col" class="border-l border-slate-200/80 px-4 py-2.5 text-left font-semibold">
                        {{ canViewSelectedOrderCost ? '实际用料 / 料费' : '实际用料' }}
                      </th>
                      <th scope="col" class="border-l border-slate-200/80 px-3 py-2.5 text-left font-semibold">状态</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-slate-100">
                    <tr
                      v-for="item in selectedItems"
                      :key="item.id"
                      data-testid="molding-sample-detail-row"
                      class="align-top transition-colors hover:bg-slate-50/40"
                    >
                      <td class="px-4 py-4">
                        <div class="flex items-start gap-3">
                          <span class="flex h-6 min-w-6 items-center justify-center rounded-md bg-slate-100 px-1.5 text-[10px] font-bold text-slate-500">
                            {{ item.sort_order }}
                          </span>
                          <div class="min-w-0">
                            <div class="break-all font-mono text-[12px] font-semibold text-slate-900">{{ item.mold_id }}</div>
                            <div class="mt-0.5 break-words text-[12px] text-slate-600">{{ item.mold_name }}</div>
                          </div>
                        </div>
                        <dl class="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 rounded-lg bg-slate-50 px-3 py-2">
                          <div class="min-w-0">
                            <dt class="text-[9px] font-semibold text-slate-400">工模尺寸</dt>
                            <dd class="mt-0.5 break-words font-medium text-slate-700">{{ formatBlank(item.mold_dimensions) }}</dd>
                          </div>
                          <div class="min-w-0">
                            <dt class="text-[9px] font-semibold text-slate-400">模具在厂</dt>
                            <dd class="mt-0.5 font-medium text-slate-700">{{ formatMoldPresenceStatus(item.mold_presence_status) }}</dd>
                          </div>
                          <div class="col-span-2 flex min-w-0 items-baseline justify-between gap-2 border-t border-slate-200/70 pt-2">
                            <dt class="text-[9px] font-semibold text-slate-400">需办日期</dt>
                            <dd class="mt-0.5 whitespace-nowrap font-medium text-slate-700">{{ formatWorkflowDate(item.completion_time) }}</dd>
                          </div>
                        </dl>
                      </td>
                      <td class="border-l border-slate-100 px-4 py-4">
                        <div class="break-words font-semibold leading-5 text-slate-800">
                          {{ getMaterialCompositionLabel(item) }}
                        </div>
                        <span
                          class="mt-2 inline-flex rounded-full px-2 py-0.5 text-[9px] font-bold"
                          :class="item.material_usage_type === 'trial' ? 'bg-amber-50 text-amber-700' : 'bg-emerald-50 text-emerald-700'"
                        >
                          {{ item.material_usage_type === 'trial' ? '试料 · 金额不计结余' : '正式生产' }}
                        </span>
                        <div class="mt-3 flex items-start gap-2 border-t border-slate-100 pt-2.5 text-slate-600">
                          <span class="mt-0.5 h-2.5 w-2.5 shrink-0 rounded-full border border-slate-200" :class="getColorSwatchClass(item.color)" />
                          <div class="min-w-0">
                            <div class="text-[9px] font-semibold text-slate-400">颜色 / PMS</div>
                            <div class="mt-0.5 break-words font-medium text-slate-700">{{ formatBlank(item.color) }}</div>
                          </div>
                        </div>
                      </td>
                      <td class="border-l border-slate-100 px-4 py-4 tabular-nums">
                        <div class="flex items-center justify-between gap-3">
                          <span class="text-[10px] font-semibold text-slate-400">预计用料</span>
                          <span class="whitespace-nowrap text-[13px] font-bold text-slate-900">{{ formatWeight(item.required_material_kg) }}</span>
                        </div>
                        <div
                          v-if="canViewSelectedOrderCost"
                          data-testid="expected-material-cost-panel"
                          class="mt-3 overflow-clip rounded-lg border border-slate-200 bg-slate-50/70"
                        >
                          <div class="border-b border-slate-200 px-2.5 py-1.5 text-[9px] font-semibold text-slate-400">预计料费明细</div>
                          <div class="divide-y divide-slate-200/70 px-2.5">
                            <div
                              v-for="(component, componentIndex) in getExpectedMaterialCostBreakdown(item).components"
                              :key="`expected-${item.id}-${component.material}-${component.source_type}-${componentIndex}`"
                              class="grid grid-cols-[minmax(0,1fr)_auto] gap-x-2 py-2"
                            >
                              <div class="min-w-0">
                                <div class="break-words text-[10px] font-medium leading-4 text-slate-700">{{ component.material }}</div>
                                <div class="mt-0.5 text-[9px] text-slate-400">
                                  {{ getMaterialSourceLabel(component.source_type) }} · {{ formatWeight(component.weight_kg) }}
                                </div>
                              </div>
                              <span class="whitespace-nowrap text-[10px] font-semibold text-slate-700">{{ formatMoney(component.amount_hkd) }}</span>
                            </div>
                          </div>
                          <div class="flex items-center justify-end border-t border-slate-200 bg-white px-2.5 py-2 font-semibold text-slate-900">
                            <span class="whitespace-nowrap">合计 {{ formatMoney(getExpectedMaterialCostBreakdown(item).total_amount_hkd) }}</span>
                          </div>
                        </div>
                      </td>
                      <td class="border-l border-slate-100 px-4 py-4 tabular-nums">
                        <div class="flex items-center justify-between gap-3">
                          <span class="text-[10px] font-semibold text-slate-400">实际用料</span>
                          <span class="whitespace-nowrap text-[13px] font-bold text-slate-900">{{ formatWeight(item.actual_weight_kg) }}</span>
                        </div>
                        <div
                          v-if="canViewSelectedOrderCost"
                          data-testid="actual-material-cost-panel"
                          class="mt-3 overflow-clip rounded-lg border border-slate-200 bg-slate-50/70"
                        >
                          <div
                            data-testid="actual-material-cost-source"
                            class="border-b border-slate-200 px-2.5 py-1.5 text-[9px] font-semibold leading-4"
                            :class="getActualMaterialCostBreakdown(item).source === 'persisted' ? 'text-emerald-600' : 'text-amber-600'"
                          >
                            {{ getActualMaterialCostSourceLabel(item) }}
                          </div>
                          <div class="divide-y divide-slate-200/70 px-2.5">
                            <div
                              v-for="(component, componentIndex) in getActualMaterialCostBreakdown(item).components"
                              :key="`actual-${item.id}-${component.material}-${component.source_type}-${componentIndex}`"
                              class="grid grid-cols-[minmax(0,1fr)_auto] gap-x-2 py-2"
                            >
                              <div class="min-w-0">
                                <div class="break-words text-[10px] font-medium leading-4 text-slate-700">{{ component.material }}</div>
                                <div class="mt-0.5 text-[9px] text-slate-400">
                                  {{ getMaterialSourceLabel(component.source_type) }} · {{ formatWeight(component.weight_kg) }}
                                </div>
                              </div>
                              <span class="whitespace-nowrap text-[10px] font-semibold text-slate-700">{{ formatMoney(component.amount_hkd) }}</span>
                            </div>
                          </div>
                          <div class="flex items-center justify-end border-t border-slate-200 bg-white px-2.5 py-2 font-semibold text-slate-900">
                            <span class="whitespace-nowrap">合计 {{ formatMoney(getActualMaterialCostTotal(item)) }}</span>
                          </div>
                        </div>
                      </td>
                      <td class="border-l border-slate-100 px-3 py-4">
                        <span class="inline-flex whitespace-nowrap rounded-full border px-2 py-0.5 text-[10px] font-bold" :class="getItemStateClass(item)">
                          {{ getItemState(item) }}
                        </span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div
                v-if="selectedItems.length > 3"
                class="hidden items-center justify-between gap-3 border-t border-slate-100 bg-slate-50/80 px-4 py-2 text-[10px] text-slate-500 md:flex"
              >
                <span>明细区域固定高度，可在区域内滚动查看全部模具。</span>
                <span class="shrink-0 font-semibold tabular-nums">共 {{ selectedItems.length }} 项</span>
              </div>
              <Transition
                enter-active-class="transition duration-200 ease-out motion-reduce:transition-none"
                enter-from-class="-translate-y-2 opacity-0"
                enter-to-class="translate-y-0 opacity-100"
                leave-active-class="transition duration-150 ease-in motion-reduce:transition-none"
                leave-from-class="translate-y-0 opacity-100"
                leave-to-class="-translate-y-2 opacity-0"
              >
                <div
                  v-if="isSelectedOrderDataExpanded"
                  id="molding-sample-full-data"
                  class="border-t border-slate-100 bg-slate-50/70 p-3 sm:p-4"
                >
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
                    <div class="rounded-lg border border-teal-200 bg-teal-50 px-3 py-2">
                      <div class="text-[10px] font-semibold text-teal-600">来源厂 → 承接生产厂</div>
                      <div class="mt-0.5 font-semibold text-teal-900">{{ selectedProductionRouteLabel }}</div>
                    </div>
                    <div class="rounded-lg border border-slate-200 bg-white px-3 py-2">
                      <div class="text-[10px] font-semibold text-slate-400">工程 / 主管</div>
                      <div class="mt-0.5 font-semibold text-slate-900">{{ formatBlank(selectedOrder.eng_name) }} / {{ formatBlank(selectedOrder.supervisor) }}</div>
                    </div>
                    <div class="rounded-lg border border-slate-200 bg-white px-3 py-2">
                      <div class="text-[10px] font-semibold text-slate-400">业务开单日期</div>
                      <div class="mt-0.5 font-semibold text-slate-900">{{ formatWorkflowDate(selectedOrder.date) }}</div>
                    </div>
                    <div class="rounded-lg border border-slate-200 bg-white px-3 py-2">
                      <div class="text-[10px] font-semibold text-slate-400">流程完成日期</div>
                      <div class="mt-0.5 font-semibold text-slate-900">{{ formatWorkflowDate(selectedOrder.completed_date, '未完成') }}</div>
                    </div>
                    <div class="rounded-lg border border-slate-200 bg-white px-3 py-2">
                      <div class="text-[10px] font-semibold text-slate-400">系统提交时间（北京时间）</div>
                      <div class="mt-0.5 font-semibold text-slate-900">{{ formatWorkflowTime(selectedOrder.created_at) }}</div>
                    </div>
                    <div class="rounded-lg border border-slate-200 bg-white px-3 py-2">
                      <div class="text-[10px] font-semibold text-slate-400">系统更新时间（北京时间）</div>
                      <div class="mt-0.5 font-semibold text-slate-900">{{ formatWorkflowTime(selectedOrder.updated_at) }}</div>
                    </div>
                  </div>

                  <div class="mt-3 rounded-lg border border-slate-200 bg-white px-3 py-2">
                    <div class="text-[10px] font-semibold text-slate-400">注意事项 / 开单事由</div>
                    <p class="mt-1 text-[12px] leading-5 text-slate-700">{{ formatBlank(selectedOrder.reason) }}</p>
                    <p v-if="selectedOrder.reject_reason" class="mt-1 text-[12px] leading-5 text-red-600">
                      驳回原因：{{ selectedOrder.reject_reason }}
                    </p>
                  </div>

                  <div
                    v-if="selectedFullItem"
                    data-testid="molding-full-data-workspace"
                    class="mt-4 grid min-h-0 gap-3 lg:h-[min(70vh,680px)] lg:min-h-[480px] lg:grid-cols-[240px_minmax(0,1fr)]"
                  >
                    <nav
                      class="min-h-0 overflow-clip rounded-xl border border-slate-200 bg-white lg:flex lg:flex-col"
                      aria-label="模具明细索引"
                    >
                      <div class="flex items-center justify-between border-b border-slate-100 px-3 py-2.5">
                        <div>
                          <h4 class="text-[11px] font-bold text-slate-700">模具索引</h4>
                          <p class="text-[10px] text-slate-400">选择一项查看完整资料</p>
                        </div>
                        <span class="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-500">{{ selectedItems.length }} 项</span>
                      </div>
                      <div
                        data-testid="molding-full-item-index"
                        class="sidebar-scrollbar flex gap-1.5 overflow-x-auto overscroll-x-contain p-2 lg:grid lg:min-h-0 lg:flex-1 lg:auto-rows-max lg:content-start lg:grid-cols-1 lg:overflow-x-hidden lg:overflow-y-auto"
                        @wheel="handoffWheelAtBoundary"
                      >
                        <button
                          v-for="item in selectedItems"
                          :key="`full-index-${item.id}`"
                          type="button"
                          data-testid="molding-full-item-selector"
                          class="min-w-[210px] rounded-lg border px-2.5 py-2 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 lg:min-w-0"
                          :class="selectedFullItem.id === item.id ? 'border-teal-300 bg-teal-50 text-teal-950 shadow-sm ring-1 ring-teal-100' : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50'"
                          :aria-pressed="selectedFullItem.id === item.id"
                          :aria-label="`查看第 ${item.sort_order} 项模具 ${item.mold_id} ${item.mold_name} 的完整资料`"
                          @click="selectFullItem(item.id)"
                        >
                          <span class="flex items-start gap-2">
                            <span
                              class="flex h-5 min-w-5 shrink-0 items-center justify-center rounded-md px-1 text-[9px] font-bold"
                              :class="selectedFullItem.id === item.id ? 'bg-teal-600 text-white' : 'bg-slate-100 text-slate-500'"
                            >
                              {{ item.sort_order }}
                            </span>
                            <span class="min-w-0 flex-1">
                              <span class="block break-all font-mono text-[11px] font-semibold">{{ item.mold_id }}</span>
                              <span class="mt-0.5 block truncate text-[11px] opacity-80" :title="item.mold_name">{{ item.mold_name }}</span>
                            </span>
                            <ChevronRight
                              class="mt-0.5 size-3.5 shrink-0"
                              :class="selectedFullItem.id === item.id ? 'text-teal-600' : 'text-slate-400'"
                              aria-hidden="true"
                            />
                          </span>
                          <span class="mt-2 block truncate text-[10px] opacity-75" :title="getMaterialCompositionLabel(item)">
                            {{ getMaterialCompositionLabel(item) }}
                          </span>
                          <span class="mt-1.5 flex items-center justify-between gap-2 text-[9px] tabular-nums opacity-75">
                            <span>{{ formatBlank(item.quantity) }} / {{ formatBlank(item.shoot_qty) }} 啤</span>
                            <span>{{ formatWeight(item.required_material_kg) }} → {{ formatWeight(item.actual_weight_kg) }}</span>
                          </span>
                        </button>
                      </div>
                    </nav>

                    <article
                      data-testid="molding-full-item-card"
                      class="min-h-0 min-w-0 overflow-clip rounded-xl border border-slate-200 bg-white shadow-sm lg:flex lg:flex-col"
                    >
                      <div class="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 bg-slate-50/80 px-3 py-2.5 lg:shrink-0">
                        <div class="flex min-w-0 items-start gap-2.5">
                          <span class="flex h-6 min-w-6 shrink-0 items-center justify-center rounded-lg bg-slate-900 px-1.5 text-[10px] font-bold text-white">
                            {{ selectedFullItem.sort_order }}
                          </span>
                          <div class="min-w-0">
                            <div class="break-all font-mono text-[12px] font-semibold text-slate-950">{{ selectedFullItem.mold_id }}</div>
                            <div class="mt-0.5 break-words text-[12px] font-semibold text-slate-700">{{ selectedFullItem.mold_name }}</div>
                          </div>
                        </div>
                        <div class="flex flex-wrap items-center justify-end gap-1.5">
                          <span
                            class="rounded-full px-2 py-0.5 text-[9px] font-bold"
                            :class="selectedFullItem.material_usage_type === 'trial' ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'"
                          >
                            {{ selectedFullItem.material_usage_type === 'trial' ? '试料 · 不计结余' : '正式生产' }}
                          </span>
                          <span class="rounded-full border px-2 py-0.5 text-[9px] font-bold" :class="getItemStateClass(selectedFullItem)">
                            {{ getItemState(selectedFullItem) }}
                          </span>
                        </div>
                      </div>
                      <div
                        ref="selectedFullItemDetailPane"
                        data-testid="molding-full-item-detail-pane"
                        class="sidebar-scrollbar p-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-teal-500 lg:min-h-0 lg:flex-1 lg:overflow-y-auto"
                        role="region"
                        :aria-label="`${selectedFullItem.mold_id} ${selectedFullItem.mold_name} 完整资料`"
                        tabindex="0"
                        @wheel="handoffWheelAtBoundary"
                      >
                        <div class="grid gap-3 md:grid-cols-2">
                          <section data-testid="molding-full-item-metadata-section" class="rounded-lg border border-slate-200 bg-slate-50/60 p-3">
                            <h4 class="text-[11px] font-bold tracking-wide text-slate-500">模具资料</h4>
                            <dl class="mt-2.5 grid gap-x-4 gap-y-2.5 sm:grid-cols-2">
                              <div>
                                <dt class="text-[10px] font-medium text-slate-500">工模尺寸</dt>
                                <dd class="mt-0.5 break-words text-[12px] font-semibold text-slate-900">{{ formatBlank(selectedFullItem.mold_dimensions) }}</dd>
                              </div>
                              <div>
                                <dt class="text-[10px] font-medium text-slate-500">模具是否在厂</dt>
                                <dd class="mt-0.5 text-[12px] font-semibold text-slate-900">{{ formatMoldPresenceStatus(selectedFullItem.mold_presence_status) }}</dd>
                              </div>
                              <div>
                                <dt class="text-[10px] font-medium text-slate-500">需办日期</dt>
                                <dd class="mt-0.5 text-[12px] font-semibold tabular-nums text-slate-900">{{ formatWorkflowDate(selectedFullItem.completion_time) }}</dd>
                              </div>
                              <div>
                                <dt class="text-[10px] font-medium text-slate-500">数量 / 啤数</dt>
                                <dd class="mt-0.5 text-[12px] font-semibold tabular-nums text-slate-900">{{ formatBlank(selectedFullItem.quantity) }} / {{ formatBlank(selectedFullItem.shoot_qty) }}</dd>
                              </div>
                            </dl>
                          </section>

                          <section data-testid="molding-full-item-material-section" class="rounded-lg border border-slate-200 bg-slate-50/60 p-3">
                            <h4 class="text-[11px] font-bold tracking-wide text-slate-500">原料与颜色</h4>
                            <dl class="mt-2.5 space-y-2.5">
                              <div>
                                <dt class="text-[10px] font-medium text-slate-500">原料配比</dt>
                                <dd class="mt-0.5 break-words text-[12px] font-semibold leading-5 text-slate-900">{{ getMaterialCompositionLabel(selectedFullItem) }}</dd>
                              </div>
                              <div class="border-t border-slate-200 pt-2.5">
                                <dt class="text-[10px] font-medium text-slate-500">颜色 / PMS</dt>
                                <dd class="mt-0.5 break-words text-[12px] font-semibold text-slate-900">{{ formatBlank(selectedFullItem.color) }} / {{ formatBlank(selectedFullItem.pigment_no) }}</dd>
                              </div>
                            </dl>
                          </section>
                        </div>

                        <section data-testid="molding-full-item-usage-section" class="mt-3 rounded-lg border border-slate-200 p-3">
                          <h4 class="text-[11px] font-bold tracking-wide text-slate-500">用量概览</h4>
                          <dl class="mt-2.5 grid gap-2 sm:grid-cols-3">
                            <div class="rounded-lg bg-slate-50 px-3 py-2">
                              <dt class="text-[10px] font-medium text-slate-500">预计用料</dt>
                              <dd class="mt-0.5 text-[14px] font-bold tabular-nums text-slate-950">{{ formatWeight(selectedFullItem.required_material_kg) }}</dd>
                            </div>
                            <div class="rounded-lg bg-slate-50 px-3 py-2">
                              <dt class="text-[10px] font-medium text-slate-500">领料重量</dt>
                              <dd class="mt-0.5 text-[14px] font-bold tabular-nums text-slate-950">{{ formatWeight(selectedFullItem.collected_weight_kg) }}</dd>
                            </div>
                            <div class="rounded-lg bg-slate-900 px-3 py-2 text-white">
                              <dt class="text-[10px] font-medium text-slate-300">实际用料</dt>
                              <dd class="mt-0.5 text-[14px] font-bold tabular-nums">{{ formatWeight(selectedFullItem.actual_weight_kg) }}</dd>
                            </div>
                          </dl>
                        </section>

                        <section
                          v-if="canViewSelectedOrderCost"
                          data-testid="molding-full-item-cost-grid"
                          class="mt-3 grid gap-3 lg:grid-cols-2"
                        >
                          <article data-testid="molding-full-item-expected-cost-panel" class="overflow-clip rounded-lg border border-slate-200">
                            <div class="border-b border-slate-100 bg-slate-50 px-3 py-2">
                              <h4 class="text-[11px] font-bold text-slate-600">预计料费(HKD)</h4>
                              <p class="mt-0.5 text-[10px] text-slate-500">按预计用料与当前原料价计算</p>
                            </div>
                            <div class="divide-y divide-slate-100 px-3">
                              <div
                                v-for="(component, componentIndex) in getExpectedMaterialCostBreakdown(selectedFullItem).components"
                                :key="`full-expected-${selectedFullItem.id}-${componentIndex}`"
                                class="flex items-start justify-between gap-3 py-2"
                              >
                                <div class="min-w-0">
                                  <div class="break-words text-[11px] font-semibold leading-4 text-slate-800">{{ component.material }}</div>
                                  <div class="mt-0.5 text-[10px] text-slate-500">{{ getMaterialSourceLabel(component.source_type) }}</div>
                                </div>
                                <div class="shrink-0 text-right tabular-nums">
                                  <div class="text-[10px] text-slate-500">{{ formatWeight(component.weight_kg) }}</div>
                                  <div class="mt-0.5 text-[11px] font-semibold text-slate-900">{{ formatMoney(component.amount_hkd) }}</div>
                                </div>
                              </div>
                            </div>
                            <div class="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-3 py-2 text-[11px] font-bold text-slate-950">
                              <span>预计合计</span>
                              <span class="tabular-nums">{{ formatMoney(getExpectedMaterialCostBreakdown(selectedFullItem).total_amount_hkd) }}</span>
                            </div>
                          </article>

                          <article data-testid="molding-full-item-actual-cost-panel" class="overflow-clip rounded-lg border border-slate-200">
                            <div class="border-b border-slate-100 bg-slate-50 px-3 py-2">
                              <h4 class="text-[11px] font-bold text-slate-600">实际料费(HKD)</h4>
                              <p
                                data-testid="actual-material-cost-source"
                                class="mt-0.5 text-[10px] font-semibold"
                                :class="getActualMaterialCostBreakdown(selectedFullItem).source === 'persisted' ? 'text-emerald-600' : 'text-amber-600'"
                              >
                                {{ getActualMaterialCostSourceLabel(selectedFullItem) }}
                              </p>
                            </div>
                            <div class="divide-y divide-slate-100 px-3">
                              <div
                                v-for="(component, componentIndex) in getActualMaterialCostBreakdown(selectedFullItem).components"
                                :key="`full-actual-${selectedFullItem.id}-${componentIndex}`"
                                class="flex items-start justify-between gap-3 py-2"
                              >
                                <div class="min-w-0">
                                  <div class="break-words text-[11px] font-semibold leading-4 text-slate-800">{{ component.material }}</div>
                                  <div class="mt-0.5 text-[10px] text-slate-500">{{ getMaterialSourceLabel(component.source_type) }}</div>
                                </div>
                                <div class="shrink-0 text-right tabular-nums">
                                  <div class="text-[10px] text-slate-500">{{ formatWeight(component.weight_kg) }}</div>
                                  <div class="mt-0.5 text-[11px] font-semibold text-slate-900">{{ formatMoney(component.amount_hkd) }}</div>
                                </div>
                              </div>
                            </div>
                            <div class="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-3 py-2 text-[11px] font-bold text-slate-950">
                              <span>实际合计</span>
                              <span class="tabular-nums">{{ formatMoney(getActualMaterialCostTotal(selectedFullItem)) }}</span>
                            </div>
                          </article>
                        </section>

                        <p class="mt-3 rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 text-[11px] leading-5 text-slate-600">
                          <span class="font-semibold text-slate-500">备注：</span>{{ formatBlank(selectedFullItem.notes) }}
                        </p>
                      </div>
                    </article>
                  </div>
                </div>
              </Transition>
            </section>

            <section class="rounded-lg border border-slate-200 bg-white p-4" data-testid="engineering-trial-report-history">
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div class="flex items-center gap-2">
                  <History class="size-4 text-teal-700" aria-hidden="true" />
                  <div>
                    <h2 class="text-[13px] font-bold text-slate-950">试模报告历史</h2>
                    <p class="mt-0.5 text-[11px] text-slate-500">啤机部保存后自动同步到此单据；工程部可查看原表并再次打印。</p>
                  </div>
                </div>
                <span class="rounded-full bg-teal-50 px-2 py-0.5 text-[11px] font-semibold text-teal-700">{{ selectedTrialReports.length }} 份已同步</span>
              </div>
              <div v-if="selectedTrialReports.length" class="mt-3 space-y-2">
                <article
                  v-for="report in selectedTrialReports"
                  :key="report.id"
                  class="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5"
                >
                  <div class="min-w-0">
                    <p class="truncate text-[12px] font-semibold text-slate-900">
                      {{ selectedItems.find((item) => item.id === report.item_id)?.mold_id || '未填模具编号' }}
                      ·
                      {{ selectedItems.find((item) => item.id === report.item_id)?.mold_name || '未填模具名称' }}
                    </p>
                    <p class="mt-0.5 text-[11px] text-slate-500">啤机部 {{ report.updated_by || report.created_by || '已保存' }} · {{ formatWorkflowTime(report.updated_at || report.created_at) }}</p>
                  </div>
                  <button
                    type="button"
                    class="inline-flex h-8 items-center gap-1.5 rounded-md border border-teal-200 bg-white px-2.5 text-[11px] font-semibold text-teal-800 transition hover:bg-teal-50"
                    @click="openEngineeringTrialReportHistory(report.item_id)"
                  >
                    <Printer class="size-3.5" aria-hidden="true" />
                    查看 / 再次打印
                  </button>
                </article>
              </div>
              <p v-else class="mt-3 rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-2 text-[11px] text-slate-500">
                暂未收到啤机部保存的试模报告。保存后会自动在此形成历史记录。
              </p>
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
                    <span class="text-[11px] text-red-500">{{ formatWorkflowTime(problem.created_at) }}</span>
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
              v-if="!isSelectedFactoryReadOnly"
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
                  <div class="text-[11px] text-slate-400">{{ log.actor_name }} · {{ log.actor_role }} · {{ formatWorkflowTime(log.created_at) }}</div>
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
          v-if="!isSelectedFactoryReadOnly"
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

    <MoldingSampleTrialReportDialog
      :visible="engineeringTrialReportHistoryVisible"
      :order="selectedRecord?.order ?? null"
      :items="selectedItems"
      :reports="selectedTrialReports"
      :factory-short-name="activeFactory.shortName"
      operator-name=""
      :can-save="false"
      :saving="false"
      read-only
      :initial-item-id="engineeringTrialReportItemId"
      @close="closeEngineeringTrialReportHistory"
    />

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
                <th>状态</th>
                <td>{{ record.order.status }} · {{ record.order.stage || '待填写' }} · {{ record.order.order_type }}</td>
              </tr>
              <tr>
                <th>产品 / 客户</th>
                <td>{{ formatBlank(record.order.product_name) }} / {{ formatBlank(record.order.client_name) }}</td>
                <th>填写部 / 发至</th>
                <td>{{ formatBlank(record.order.workshop) }} / {{ formatBlank(record.order.send_to, '内部') }}</td>
              </tr>
              <tr>
                <th>工程 / 主管</th>
                <td>{{ formatBlank(record.order.eng_name) }} / {{ formatBlank(record.order.supervisor) }}</td>
                <th>业务开单 / 流程完成</th>
                <td>{{ formatWorkflowDate(record.order.date) }} / {{ formatWorkflowDate(record.order.completed_date, '未完成') }}</td>
              </tr>
              <tr>
                <th>来源厂 → 承接生产厂</th>
                <td colspan="3">{{ getProductionRouteLabel(record.order) }}</td>
              </tr>
              <tr>
                <th>系统更新时间（北京时间）</th>
                <td colspan="3">{{ formatWorkflowTime(record.order.updated_at) }}</td>
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
                <th>颜色 / PMS</th>
                <th>色粉</th>
                <th>啤数 / 预料</th>
                <th>需办日期</th>
                <th>实际回填</th>
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
                  <span>模具是否在厂：{{ formatMoldPresenceStatus(item.mold_presence_status) }}</span>
                  <em>{{ formatBlank(item.id) }}</em>
                </td>
                <td>{{ formatBlank(item.material) }}</td>
                <td>
                  <strong>{{ formatBlank(item.color) }}</strong>
                  <span>PMS {{ formatBlank(item.pigment_no) }}</span>
                </td>
                <td>{{ formatBlank(item.pigment_no) }}</td>
                <td>
                  <strong>{{ formatBlank(item.quantity) }} / {{ formatBlank(item.shoot_qty) }}</strong>
                  <span>{{ formatWeight(item.required_material_kg) }}</span>
                  <span v-if="canViewRecordCost(record)">预计料费 {{ formatMoney(getExpectedMaterialAmountHkd(item)) }}</span>
                </td>
                <td>{{ formatWorkflowDate(item.completion_time) }}</td>
                <td>
                  <strong>{{ formatWeight(item.actual_weight_kg) }}</strong>
                  <span v-if="canViewRecordCost(record)">实际料费 {{ formatMoney(item.actual_amount_hkd) }}</span>
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
            本单据由 Royal Regent Nexus 生成。打印前请核对单据资料、模具明细、用料及实际回填。
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
