<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch, watchEffect } from 'vue'
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ClipboardPenLine,
  ChevronRight,
  Flag,
  LayoutDashboard,
  ListChecks,
  Lock,
  Package,
  PencilRuler,
  Play,
  Plus,
  Printer,
  RotateCcw,
  Save,
  Search,
  Send,
  ShieldAlert,
  Table2,
  X,
} from '@lucide/vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import {
  factoryContexts,
  getFactoryScopedRoute,
  isProductionFactoryContextId,
  type ProductionFactoryContextId,
  type Tone,
} from '@/data/enterpriseMock'
import {
  applyCostPreviewToItems,
  buildCompletionGate,
  buildMoldingSampleReportSummary,
  calculateMaterialCostBreakdown,
  formatMaterialComposition,
  isExternalMoldingSampleOrder,
  resolveActualMaterialCostBreakdown,
  resolveMaterialComponents,
  type MoldingSampleMaterialPrice,
  type MoldingSampleReportItemRow,
  type MoldingSampleReportSummary,
} from '@/lib/moldingSampleBusiness'
import {
  matchesMoldingSampleSearch,
  tokenizeMoldingSampleSearchKeyword,
} from '@/lib/moldingSampleSearch'
import {
  formatBusinessDate,
  formatBusinessDateTime,
  parseBusinessTimestamp,
} from '@/lib/dateTime'
import { getApiErrorMessage } from '@/lib/http'
import {
  moldingSampleApi,
  type MoldingSampleDetailResponse,
  type MoldingSampleNotificationResponse,
  type MoldingSampleStatusRequest,
} from '@/api/moldingSample'
import type {
  MoldingSampleItem,
  MoldingSampleOrder,
  MoldingSampleProblem,
  MoldingSampleTrialReport,
  MoldingSampleTrialReportData,
  MoldingSampleStatus,
  MoldingSampleWorkflowRecord,
} from '@/types/moldingSample'
import StatusPill from '@/components/common/StatusPill.vue'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import MoldingSampleTrialReportDialog from '@/components/molding/MoldingSampleTrialReportDialog.vue'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

interface ItemFillbackDraft {
  actual_weight_kg: string
}

type ProductionQueueFilter = '全部' | '待接单' | '生产中'
type ProductionTaskDisplayMode = 'board' | 'list'
type NotificationStatus = MoldingSampleNotificationResponse['status']
type ProductionTransitionAction = '开始处理' | '撤回开始生产' | '标记完成' | '撤回完成'

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

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const authStore = useAuthStore()

const PRODUCTION_NOTIFICATION_MODULE = 'production_molding_sample_task'
const PRODUCTION_TASK_PAGE_SIZE = 10
const PRODUCTION_TASK_STATUSES = new Set<MoldingSampleStatus>(['待生产', '生产中', '已完成'])
const apiRecords = ref<MoldingSampleDetailResponse[]>([])
const apiNotifications = ref<MoldingSampleNotificationResponse[]>([])
const apiState = ref<'checking' | 'connected' | 'empty' | 'error'>('checking')
const actionMessage = ref('正在读取啤办生产任务...')
const selectedOrderId = ref('')
const queueFilter = ref<ProductionQueueFilter>('全部')
const productionSearchKeyword = ref('')
const queueDisplayMode = ref<ProductionTaskDisplayMode>('board')
const queuePage = ref(1)
const productionProblem = ref('')
const problemSubmitting = ref(false)
const notificationUpdating = ref(false)
const itemDrafts = ref<Record<string, ItemFillbackDraft>>({})
const localItemOverrides = ref<Record<string, Record<string, Partial<MoldingSampleItem>>>>({})
const isSelectedTaskDataExpanded = ref(false)
const selectedFullDataItemId = ref('')
const fullDataItemPane = ref<HTMLElement | null>(null)
const taskPrintPreviewVisible = ref(false)
const trialReportDialogVisible = ref(false)
const trialReportReadOnly = ref(false)
const trialReportInitialItemId = ref('')
const trialReportSaving = ref(false)
const protectedMaterialPrices = ref<MoldingSampleMaterialPrice[]>([])
const protectedRmbToHkdRate = ref<number | null>(null)
let apiDataRequestId = 0
let protectedMaterialPricesRequestId = 0
let trialReportSaveRequestId = 0

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

const statusTones: Record<MoldingSampleStatus, Tone> = {
  待审核: 'blue',
  待经理审核: 'blue',
  待生产: 'amber',
  生产中: 'teal',
  已完成: 'green',
  已驳回: 'red',
  已撤回: 'slate',
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
const productionDepartmentRoute = computed(() => getFactoryScopedRoute(
  '/modules/production',
  selectedFactoryId.value,
))

function isWildcardMoldingAdministrator() {
  return authStore.grants.some((grant) =>
    (grant.role_code === 'admin' || grant.role_id === 'admin')
    && grant.factory_id === '*'
    && ['*', 'system'].includes(grant.department),
  )
}

function isHomeProductionFactory(factoryId: string) {
  if (isWildcardMoldingAdministrator() || authStore.authzMode !== 'enforce') return true
  const primaryFactoryId = authStore.currentUser?.profile?.primary_factory_id?.trim()
  if (primaryFactoryId) return primaryFactoryId === factoryId
  return authStore.grants.some((grant) => grant.factory_id === factoryId)
}

function canOperateProductionFactory(factoryId: string) {
  if (isHomeProductionFactory(factoryId)) return true
  return authStore.grants.some((grant) =>
    grant.scope_mode === 'cross_factory_operate'
    && grant.factory_id !== factoryId,
  )
}

function canProductionPermission(permission: string, factoryId: string) {
  if (
    ['molding_sample:production_start', 'molding_sample:production_fillback', 'molding_sample:production_complete'].includes(permission)
    && !canOperateProductionFactory(factoryId)
  ) {
    return false
  }
  return ['production', 'molding'].some((department) =>
    authStore.can(permission, factoryId, department),
  )
}

const canReadSelectedFactory = computed(() =>
  canProductionPermission('molding_sample:production_read', selectedFactoryId.value),
)

const engineeringOrderRoute = computed(() => {
  const params = new URLSearchParams({ factory: selectedFactoryId.value })
  if (selectedTask.value?.order.id) {
    params.set('order_id', selectedTask.value.order.id)
  }

  return `/modules/molding-sample?${params.toString()}`
})

const sourceRecords = computed<MoldingSampleWorkflowRecord[]>(() => {
  if (!apiRecords.value.length || !canReadSelectedFactory.value) {
    return []
  }

  return apiRecords.value
    .map((record) => ({
      factory_id: record.order.factory_id,
      order: record.order,
      items: record.items,
      audit_logs: record.audit_logs,
      requisitions: [],
      problems: record.problems ?? [],
      trial_reports: record.trial_reports ?? [],
    }))
})

const taskRecords = computed(() =>
  sourceRecords.value.map((record) => ({
    ...record,
    items: record.items.map((item) => ({
      ...item,
      ...(localItemOverrides.value[record.order.id]?.[item.id] ?? {}),
    })),
  })),
)

const taskEntries = computed(() => taskRecords.value
  .filter((record) => record.factory_id === selectedFactoryId.value)
  .filter((record) => !isExternalMoldingSampleOrder(record.order))
  .filter((record) => PRODUCTION_TASK_STATUSES.has(record.order.status))
  .sort((left, right) => getTaskPriority(left.order.status) - getTaskPriority(right.order.status)),
)

const productionSearchTokens = computed(() =>
  tokenizeMoldingSampleSearchKeyword(productionSearchKeyword.value),
)

const searchMatchedTaskEntries = computed(() => {
  if (!productionSearchTokens.value.length) {
    return taskEntries.value
  }

  return taskEntries.value.filter((entry) => matchesMoldingSampleSearch(entry, productionSearchTokens.value))
})

const selectedTask = computed(() => {
  const queryOrderId = readQueryString(route.query.order_id)
  const targetOrderId = selectedOrderId.value || queryOrderId

  return taskEntries.value.find((entry) => entry.order.id === targetOrderId)
    ?? taskEntries.value.find((entry) => entry.factory_id === selectedFactoryId.value)
    ?? taskEntries.value[0]
    ?? null
})

const selectedNotification = computed(() =>
  selectedTask.value ? getLatestNotification(selectedTask.value.order.id) : null,
)

const selectedTaskFactoryId = computed(() => selectedTask.value?.order.factory_id || selectedFactoryId.value)
const canStartSelectedTaskFactory = computed(() =>
  canProductionPermission('molding_sample:production_start', selectedTaskFactoryId.value),
)
const canFillbackSelectedTaskFactory = computed(() =>
  canProductionPermission('molding_sample:production_fillback', selectedTaskFactoryId.value),
)
const canCompleteSelectedTaskFactory = computed(() =>
  canProductionPermission('molding_sample:production_complete', selectedTaskFactoryId.value),
)
const canUpdateSelectedNotification = computed(() =>
  canOperateProductionFactory(selectedTaskFactoryId.value)
  && canFillbackSelectedTaskFactory.value
  && canProductionPermission('molding_sample:notification_read', selectedTaskFactoryId.value),
)
const isSelectedFactoryReadOnly = computed(() => ![
  'molding_sample:production_start',
  'molding_sample:production_fillback',
  'molding_sample:production_complete',
].some((permission) => canProductionPermission(permission, selectedFactoryId.value)))

const activeItems = computed<MoldingSampleItem[]>(() => {
  if (!selectedTask.value) {
    return []
  }

  return selectedTask.value.items.map((item) => {
    const draft = itemDrafts.value[item.id]

    if (!draft) {
      return item
    }

    return {
      ...item,
      actual_weight_kg: parseOptionalNumber(draft.actual_weight_kg),
    }
  })
})

const selectedFullDataItem = computed(() =>
  activeItems.value.find((item) => item.id === selectedFullDataItemId.value)
  ?? activeItems.value[0]
  ?? null,
)

// The printed handoff is issued when molding first receives the engineering order.
// Keep it tied to the original engineering rows instead of unsaved production fillback.
const printableEngineeringItems = computed<MoldingSampleItem[]>(() => selectedTask.value?.items ?? [])
const taskPrintDensityClass = computed(() => {
  const items = printableEngineeringItems.value
  const textWeight = items.reduce((total, item) => total
    + formatMaterialComposition(resolveMaterialComponents(item)).length
    + String(item.mold_name ?? '').length
    + String(item.notes ?? '').length, String(selectedTask.value?.order.reason ?? '').length)
  const layoutWeight = items.length * 72 + textWeight

  if (items.length > 7 || layoutWeight > 1_000) {
    return 'is-dense'
  }

  if (items.length > 3 || layoutWeight > 480) {
    return 'is-compact'
  }

  return ''
})
const canPrintSelectedTask = computed(() =>
  Boolean(
    selectedTask.value
    && printableEngineeringItems.value.length
    && ['待生产', '生产中', '已完成'].includes(selectedTask.value.order.status),
  ),
)
const canSaveSelectedTrialReport = computed(() =>
  Boolean(
    selectedTask.value
    && ['待生产', '生产中'].includes(selectedTask.value.order.status)
    && canFillbackSelectedTaskFactory.value,
  ),
)
const selectedTrialReports = computed(() => selectedTask.value?.trial_reports ?? [])
const currentProductionOperatorName = computed(() =>
  authStore.currentUser?.display_name
  || authStore.currentUser?.username
  || '',
)

const completionGate = computed(() => {
  if (!selectedTask.value) {
    return {
      can_complete: false,
      missing_item_ids: [],
      message: '请选择一张啤办生产任务单。',
    }
  }

  return buildCompletionGate(selectedTask.value.order, activeItems.value)
})

const selectedProblems = computed(() => selectedTask.value?.problems ?? [])

const queueFilters: ProductionQueueFilter[] = ['全部', '待接单', '生产中']

const filteredTaskEntries = computed(() => searchMatchedTaskEntries.value.filter((entry) => {
  if (queueFilter.value === '待接单') {
    return entry.order.status === '待生产'
  }
  if (queueFilter.value === '生产中') {
    return entry.order.status === '生产中'
  }

  return true
}))

const filteredTaskPagination = computed(() =>
  createPaginationState(filteredTaskEntries.value, queuePage.value),
)

const paginatedFilteredTaskEntries = computed(() => filteredTaskPagination.value.rows)

const waitingTaskCount = computed(() =>
  taskEntries.value.filter((entry) => entry.order.status === '待生产').length,
)

const runningTaskCount = computed(() =>
  taskEntries.value.filter((entry) => entry.order.status === '生产中').length,
)

const selectedPreviewItems = computed<MoldingSampleItem[]>(() => {
  if (!selectedTask.value) {
    return []
  }

  if (protectedRmbToHkdRate.value === null) {
    return activeItems.value
  }

  if (selectedTask.value.order.status === '已完成') {
    return activeItems.value
  }

  return applyCostPreviewToItems(
    activeItems.value,
    protectedMaterialPrices.value,
    protectedRmbToHkdRate.value,
    isExternalMoldingSampleOrder(selectedTask.value.order),
    true,
  )
})

const selectedReportSummary = computed<MoldingSampleReportSummary | null>(() => {
  if (!selectedTask.value) {
    return null
  }

  return buildMoldingSampleReportSummary(
    selectedTask.value.order,
    selectedPreviewItems.value,
    protectedMaterialPrices.value,
  )
})

const selectedReportRowsByItemId = computed(() =>
  new Map<string, MoldingSampleReportItemRow>(
    selectedReportSummary.value?.item_rows.map((row) => [row.item_id, row]) ?? [],
  ),
)

const selectedMissingItems = computed(() => {
  const missingIds = new Set(completionGate.value.missing_item_ids)

  return activeItems.value.filter((item) => missingIds.has(item.id))
})

const canStartSelectedTask = computed(() => canStartSelectedTaskFactory.value && selectedTask.value?.order.status === '待生产')
const canFillbackSelectedTask = computed(() => canFillbackSelectedTaskFactory.value && selectedTask.value?.order.status === '生产中')
const canCompleteSelectedTask = computed(() =>
  canCompleteSelectedTaskFactory.value
  && selectedTask.value?.order.status === '生产中'
  && completionGate.value.can_complete,
)
const canRollbackStartedTask = computed(() => canStartSelectedTaskFactory.value && selectedTask.value?.order.status === '生产中')
const canRollbackCompletedTask = computed(() => canCompleteSelectedTaskFactory.value && selectedTask.value?.order.status === '已完成')
const canMarkSelectedNotificationRead = computed(() =>
  canUpdateSelectedNotification.value && selectedNotification.value?.status === '未读',
)
const canMarkSelectedNotificationHandled = computed(() =>
  Boolean(canUpdateSelectedNotification.value && selectedNotification.value && selectedNotification.value.status !== '已处理'),
)

function readQueryString(value: unknown) {
  if (typeof value === 'string') {
    return value.trim()
  }
  if (Array.isArray(value) && typeof value[0] === 'string') {
    return value[0].trim()
  }

  return ''
}

function getPageCount(total: number) {
  return Math.max(1, Math.ceil(total / PRODUCTION_TASK_PAGE_SIZE))
}

function createPaginationState<T>(rows: T[], page: number): PaginationState<T> {
  const total = rows.length
  const pageCount = getPageCount(total)
  const normalizedPage = Math.min(Math.max(page, 1), pageCount)
  const startIndex = (normalizedPage - 1) * PRODUCTION_TASK_PAGE_SIZE
  const pageRows = rows.slice(startIndex, startIndex + PRODUCTION_TASK_PAGE_SIZE)

  return {
    rows: pageRows,
    total,
    page: normalizedPage,
    pageCount,
    start: total ? startIndex + 1 : 0,
    end: Math.min(startIndex + pageRows.length, total),
    hasPrevious: normalizedPage > 1,
    hasNext: normalizedPage < pageCount,
  }
}

function formatPaginationRange<T>(pagination: PaginationState<T>) {
  if (!pagination.total) {
    return '0 / 0'
  }

  return `${pagination.start}-${pagination.end} / ${pagination.total}`
}

function setQueuePage(page: number) {
  queuePage.value = Math.min(Math.max(page, 1), filteredTaskPagination.value.pageCount)
}

function setQueueDisplayMode(mode: ProductionTaskDisplayMode) {
  queueDisplayMode.value = mode
  queuePage.value = 1
}

function getTaskPriority(status: MoldingSampleStatus) {
  const priorities: Record<MoldingSampleStatus, number> = {
    生产中: 0,
    待生产: 1,
    待审核: 2,
    待经理审核: 3,
    已完成: 4,
    已驳回: 5,
    已撤回: 6,
  }

  return priorities[status]
}

function getTaskStageLabel(status: MoldingSampleStatus) {
  if (status === '待审核' || status === '待经理审核') {
    return '已收到工程通知'
  }
  if (status === '待生产') {
    return '待啤机执行'
  }
  if (status === '生产中') {
    return '啤机生产中'
  }
  if (status === '已完成') {
    return '已回传工程'
  }

  return status
}

function getTaskStageDetail(order: MoldingSampleOrder) {
  if (order.status === '待审核') {
    return `等待 ${order.supervisor || '主管'} 审核后继续流转`
  }
  if (order.status === '待经理审核') {
    return '历史审核节点，处理后进入啤机可执行队列'
  }
  if (order.status === '待生产') {
    return '啤机部可以开始生产执行'
  }
  if (order.status === '生产中') {
    return completionGate.value.message
  }
  if (order.status === '已完成') {
    return `完成日期：${formatWorkflowDate(order.completed_date || order.updated_at, '已回传')}`
  }

  return '当前任务不可执行'
}

function getTaskWorkflowDateLabel(order: MoldingSampleOrder) {
  const completedDate = formatWorkflowDate(order.completed_date, '')
  if (order.status === '已完成' && completedDate) {
    return `完成 ${completedDate}`
  }
  const submittedDate = formatWorkflowDate(order.created_at, '')
  if (submittedDate) {
    return `提交 ${submittedDate}`
  }

  return `业务 ${formatWorkflowDate(order.date)}`
}

function getQueueFilterCount(filter: ProductionQueueFilter) {
  if (filter === '待接单') {
    return waitingTaskCount.value
  }
  if (filter === '生产中') {
    return runningTaskCount.value
  }

  return taskEntries.value.length
}

function getQueueStatusLabel(status: MoldingSampleStatus) {
  if (status === '待生产') {
    return '待接单'
  }
  if (status === '已完成') {
    return '已回传'
  }
  if (status === '待审核' || status === '待经理审核') {
    return '通知'
  }

  return status
}

function getReportRow(itemId: string) {
  return selectedReportRowsByItemId.value.get(itemId) ?? null
}

function selectFullDataItem(itemId: string) {
  selectedFullDataItemId.value = itemId
  void nextTick(() => {
    if (fullDataItemPane.value) {
      fullDataItemPane.value.scrollTop = 0
    }
  })
}

function getExpectedMaterialCostBreakdown(item: MoldingSampleItem) {
  return calculateMaterialCostBreakdown({
    components: resolveMaterialComponents(item),
    totalWeightKg: item.required_material_kg,
    prices: protectedMaterialPrices.value,
  })
}

function hasUnsavedActualWeightChange(item: MoldingSampleItem) {
  if (selectedTask.value?.order.status === '已完成') {
    return false
  }

  const savedItem = selectedTask.value?.items.find((candidate) => candidate.id === item.id)
  return savedItem !== undefined
    && (savedItem.actual_weight_kg ?? null) !== (item.actual_weight_kg ?? null)
}

function getActualMaterialCostBreakdown(item: MoldingSampleItem) {
  if (hasUnsavedActualWeightChange(item)) {
    return {
      ...calculateMaterialCostBreakdown({
        components: resolveMaterialComponents(item),
        totalWeightKg: item.actual_weight_kg,
        prices: protectedMaterialPrices.value,
      }),
      source: 'estimated' as const,
    }
  }

  return resolveActualMaterialCostBreakdown(item, protectedMaterialPrices.value)
}

function getActualMaterialCostTotal(item: MoldingSampleItem) {
  if (hasUnsavedActualWeightChange(item)) {
    return getActualMaterialCostBreakdown(item).total_amount_hkd
  }

  return item.actual_amount_hkd ?? getActualMaterialCostBreakdown(item).total_amount_hkd
}

function getActualMaterialCostSourceLabel(item: MoldingSampleItem) {
  if (hasUnsavedActualWeightChange(item)) {
    return '按本次实际用料预览，保存后结算'
  }
  if (getActualMaterialCostBreakdown(item).source === 'persisted') {
    return '实际结算快照'
  }

  return item.actual_amount_hkd === null || item.actual_amount_hkd === undefined
    ? '分项按当前原料价估算'
    : '分项按当前原料价估算；合计以已存实际料费为准'
}

function getMaterialSourceLabel(sourceType: 'virgin' | 'runner') {
  return sourceType === 'runner' ? '水口料' : '原料'
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

function compareCreatedAtDescending(
  left: Pick<MoldingSampleNotificationResponse, 'created_at'>,
  right: Pick<MoldingSampleNotificationResponse, 'created_at'>,
) {
  return (parseBusinessTimestamp(right.created_at) ?? 0) - (parseBusinessTimestamp(left.created_at) ?? 0)
}

function formatDecimal(value: number | null | undefined, fallback = '—') {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) {
    return fallback
  }

  return Number(value).toFixed(2)
}

function formatWeight(value: number | null | undefined) {
  const formatted = formatDecimal(value, '待填写')
  return formatted === '待填写' ? formatted : `${formatted} kg`
}

function formatMoldPresenceStatus(value: MoldingSampleItem['mold_presence_status']) {
  return value === 'in_factory' ? '在厂' : value === 'out_of_factory' ? '不在厂' : '待确认'
}

function formatCurrency(value: number | null | undefined, fallback = '—') {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) {
    return fallback
  }

  return `$ ${Number(value).toFixed(2)}`
}

function parseOptionalNumber(value: string) {
  const trimmed = value.trim()
  if (!trimmed) {
    return null
  }

  const parsed = Number(trimmed)

  return Number.isFinite(parsed) ? parsed : null
}

function buildItemPatches() {
  return activeItems.value.map((item) => ({
    id: item.id,
    actual_weight_kg: item.actual_weight_kg,
  }))
}

function updateItemDraft(itemId: string, field: keyof ItemFillbackDraft, value: string) {
  itemDrafts.value = {
    ...itemDrafts.value,
    [itemId]: {
      ...(itemDrafts.value[itemId] ?? { actual_weight_kg: '' }),
      [field]: value,
    },
  }
}

function openTaskPrintPreview() {
  if (!canPrintSelectedTask.value) {
    actionMessage.value = '仅已审核下发至啤机部且包含工程明细的啤办通知单可以打印。'
    return
  }

  taskPrintPreviewVisible.value = true
}

function closeTaskPrintPreview() {
  taskPrintPreviewVisible.value = false
}

function confirmTaskPrint() {
  if (!selectedTask.value) {
    taskPrintPreviewVisible.value = false
    actionMessage.value = '未找到可打印的啤办生产任务单。'
    return
  }

  actionMessage.value = `正在打印工程部下发的啤办通知单 ${selectedTask.value.order.id}。`
  document.body.classList.add('molding-sample-task-printing')
  document.getElementById('molding-sample-active-print-page')?.remove()
  const pageStyle = document.createElement('style')
  pageStyle.id = 'molding-sample-active-print-page'
  pageStyle.textContent = '@media print { @page { size: A4 landscape; margin: 5mm; } }'
  document.head.append(pageStyle)
  let cleanedUp = false
  const cleanUp = () => {
    if (cleanedUp) {
      return
    }
    cleanedUp = true
    document.body.classList.remove('molding-sample-task-printing')
    pageStyle.remove()
  }
  window.addEventListener('afterprint', cleanUp, { once: true })
  window.print()
  window.setTimeout(cleanUp, 1000)
}

function openTrialReportDialog() {
  if (!selectedTask.value?.items.length) {
    actionMessage.value = '当前啤办单没有可填写试模报告的模具明细。'
    return
  }

  trialReportReadOnly.value = false
  trialReportInitialItemId.value = ''
  trialReportDialogVisible.value = true
}

function openTrialReportHistory(itemId: string) {
  if (!selectedTask.value?.trial_reports.some((report) => report.item_id === itemId)) {
    actionMessage.value = '当前模具尚未保存试模报告。'
    return
  }

  trialReportReadOnly.value = true
  trialReportInitialItemId.value = itemId
  trialReportDialogVisible.value = true
}

function closeTrialReportDialog() {
  trialReportDialogVisible.value = false
  trialReportReadOnly.value = !canSaveSelectedTrialReport.value
  trialReportInitialItemId.value = ''
}

function isTrialReportSaveContextCurrent(requestId: number, factoryId: string, orderId: string) {
  return requestId === trialReportSaveRequestId
    && factoryId === selectedFactoryId.value
    && selectedTask.value?.order.factory_id === factoryId
    && selectedTask.value?.order.id === orderId
}

async function saveTrialReport(payload: { itemId: string, data: MoldingSampleTrialReportData }) {
  const task = selectedTask.value
  if (!task) {
    actionMessage.value = '请先选择一张啤办生产任务单。'
    return
  }
  if (!canSaveSelectedTrialReport.value) {
    actionMessage.value = '仅待生产或生产中的任务可保存试模报告，且需具备啤机部回填权限。'
    return
  }
  if (apiState.value !== 'connected') {
    actionMessage.value = '真实任务读取失败或暂无正式任务，不能保存试模报告。'
    return
  }

  const requestedFactoryId = selectedFactoryId.value
  const requestedOrderId = task.order.id
  const requestedItemId = payload.itemId
  const requestId = ++trialReportSaveRequestId
  trialReportSaving.value = true
  try {
    const report = await moldingSampleApi.upsertTrialReport(requestedOrderId, requestedItemId, { data: payload.data })
    if (!isTrialReportSaveContextCurrent(requestId, requestedFactoryId, requestedOrderId)) {
      return
    }

    if (
      report.factory_id !== requestedFactoryId
      || report.order_id !== requestedOrderId
      || report.item_id !== requestedItemId
    ) {
      actionMessage.value = '试模报告保存响应与当前厂区或任务不一致，已忽略该响应。'
      return
    }

    replaceTrialReportForOrder(requestedOrderId, report)
    actionMessage.value = `试模报告已保存并同步至工程部：${requestedOrderId} · ${requestedItemId}。`
  }
  catch (error) {
    if (!isTrialReportSaveContextCurrent(requestId, requestedFactoryId, requestedOrderId)) {
      return
    }

    actionMessage.value = `试模报告保存失败：${getApiErrorMessage(error)}`
  }
  finally {
    if (isTrialReportSaveContextCurrent(requestId, requestedFactoryId, requestedOrderId)) {
      trialReportSaving.value = false
    }
  }
}

function applyLocalItemPatches(orderId: string) {
  const patches = buildItemPatches().reduce<Record<string, Partial<MoldingSampleItem>>>((acc, patch) => {
    acc[patch.id] = patch
    return acc
  }, {})

  localItemOverrides.value = {
    ...localItemOverrides.value,
    [orderId]: {
      ...(localItemOverrides.value[orderId] ?? {}),
      ...patches,
    },
  }
}

function replaceApiRecord(record: MoldingSampleDetailResponse) {
  const exists = apiRecords.value.some((entry) => entry.order.id === record.order.id)

  apiRecords.value = exists
    ? apiRecords.value.map((entry) => entry.order.id === record.order.id ? record : entry)
    : [record, ...apiRecords.value]

  replaceApiNotificationsForOrder(record)
}

function replaceTrialReportForOrder(orderId: string, report: MoldingSampleTrialReport) {
  apiRecords.value = apiRecords.value.map((record) => record.order.id === orderId
    ? {
        ...record,
        trial_reports: [
          report,
          ...(record.trial_reports ?? []).filter((entry) => entry.id !== report.id && entry.item_id !== report.item_id),
        ],
      }
    : record)
}

function appendProblemForOrder(orderId: string, problem: MoldingSampleProblem) {
  apiRecords.value = apiRecords.value.map((entry) => entry.order.id === orderId
    ? {
        ...entry,
        problems: [
          problem,
          ...(entry.problems ?? []).filter((existing) => existing.id !== problem.id),
        ],
      }
    : entry)
}

function replaceApiNotificationsForOrder(record: MoldingSampleDetailResponse) {
  const productionNotifications = (record.notifications ?? [])
    .filter((notification) => notification.target_module === PRODUCTION_NOTIFICATION_MODULE)
  const preservedNotifications = productionNotifications.length
    ? productionNotifications
    : apiNotifications.value.filter((notification) => notification.order_id === record.order.id)
  const otherNotifications = apiNotifications.value
    .filter((notification) => notification.order_id !== record.order.id)

  apiNotifications.value = [...preservedNotifications, ...otherNotifications]
    .sort(compareCreatedAtDescending)
}

function replaceApiNotification(notification: MoldingSampleNotificationResponse) {
  apiNotifications.value = [
    notification,
    ...apiNotifications.value.filter((entry) => entry.id !== notification.id),
  ].sort(compareCreatedAtDescending)
}

function getLatestNotification(orderId: string) {
  return apiNotifications.value.find((notification) => notification.order_id === orderId) ?? null
}

function getNotificationMeta(orderId: string) {
  const notification = getLatestNotification(orderId)
  if (!notification) {
    return '未找到正式通知'
  }

  return `${notification.event_type} · ${notification.status}`
}

function getNotificationStatusClass(status: NotificationStatus) {
  if (status === '未读') {
    return 'bg-amber-100 text-amber-700'
  }
  if (status === '已读') {
    return 'bg-blue-100 text-blue-700'
  }

  return 'bg-emerald-100 text-emerald-700'
}

async function loadProtectedMaterialPrices(factoryId: string) {
  const requestId = ++protectedMaterialPricesRequestId
  protectedMaterialPrices.value = []
  protectedRmbToHkdRate.value = null

  try {
    const response = await moldingSampleApi.getMaterialPrices(factoryId)
    if (
      requestId !== protectedMaterialPricesRequestId
      || factoryId !== selectedFactoryId.value
    ) {
      return
    }

    protectedMaterialPrices.value = response.prices
    protectedRmbToHkdRate.value = response.rmb_to_hkd_rate
  }
  catch {
    if (
      requestId !== protectedMaterialPricesRequestId
      || factoryId !== selectedFactoryId.value
    ) {
      return
    }

    protectedMaterialPrices.value = []
    protectedRmbToHkdRate.value = null
  }
}

async function loadApiData() {
  const requestedFactoryId = selectedFactoryId.value
  const requestId = ++apiDataRequestId
  apiState.value = 'checking'
  actionMessage.value = '正在读取啤办生产任务...'

  if (!canProductionPermission('molding_sample:production_read', requestedFactoryId)) {
    apiRecords.value = []
    apiNotifications.value = []
    apiState.value = 'empty'
    actionMessage.value = '当前账号没有该厂区的啤办生产任务查看权限。'
    return
  }

  try {
    const notificationsRequest = canProductionPermission('molding_sample:notification_read', requestedFactoryId)
      ? moldingSampleApi.listNotifications({
          target_module: PRODUCTION_NOTIFICATION_MODULE,
          factory_id: requestedFactoryId,
        })
      : Promise.resolve([])
    const [orders, notifications] = await Promise.all([
      moldingSampleApi.listOrders(requestedFactoryId),
      notificationsRequest,
    ])
    if (
      requestId !== apiDataRequestId
      || requestedFactoryId !== selectedFactoryId.value
    ) {
      return
    }

    apiRecords.value = orders
    apiNotifications.value = notifications
    const formalTaskCount = orders.filter((record) =>
      record.order.factory_id === requestedFactoryId
      && !isExternalMoldingSampleOrder(record.order)
      && PRODUCTION_TASK_STATUSES.has(record.order.status)
    ).length
    apiState.value = formalTaskCount ? 'connected' : 'empty'
    actionMessage.value = canProductionPermission('molding_sample:notification_read', requestedFactoryId)
      ? formalTaskCount
        ? `已读取 ${formalTaskCount} 张正式啤办生产任务；同步 ${notifications.length} 条任务通知。`
        : '当前厂区暂无正式啤办生产任务。'
      : formalTaskCount
        ? `已读取 ${formalTaskCount} 张正式啤办生产任务；当前账号没有通知处理权限。`
        : '当前厂区暂无正式啤办生产任务。'
  }
  catch (error) {
    if (
      requestId !== apiDataRequestId
      || requestedFactoryId !== selectedFactoryId.value
    ) {
      return
    }

    apiRecords.value = []
    apiNotifications.value = []
    apiState.value = 'error'
    actionMessage.value = `真实任务读取失败：${getApiErrorMessage(error)}。不会显示本地示例任务。`
  }
}

async function selectTask(orderId: string, factoryId: string) {
  selectedOrderId.value = orderId
  await router.replace({
    path: route.path,
    query: {
      ...route.query,
      factory: factoryId,
      order_id: orderId,
    },
  })
}

async function updateSelectedNotificationStatus(status: NotificationStatus) {
  const notification = selectedNotification.value

  if (!notification) {
    actionMessage.value = '当前任务没有可更新的正式通知。'
    return
  }
  if (notification.status === '已处理') {
    actionMessage.value = '当前通知已处理，无需重复更新。'
    return
  }
  if (status === '已读' && notification.status !== '未读') {
    actionMessage.value = '当前通知已读，无需重复标记。'
    return
  }
  if (!canUpdateSelectedNotification.value) {
    actionMessage.value = '当前账号没有处理该厂区生产通知的权限。'
    return
  }

  notificationUpdating.value = true

  try {
    const updated = await moldingSampleApi.updateNotification(notification.id, { status })
    replaceApiNotification(updated)
    actionMessage.value = status === '已读'
      ? `通知已读：${updated.order_id}。`
      : `通知已处理：${updated.order_id}。`
  }
  catch (error) {
    actionMessage.value = `通知状态更新失败：${getApiErrorMessage(error)}`
  }
  finally {
    notificationUpdating.value = false
  }
}

async function saveProductionFillback() {
  if (!selectedTask.value) {
    actionMessage.value = '请先选择一张啤办生产任务单。'
    return
  }
  if (!canFillbackSelectedTaskFactory.value) {
    actionMessage.value = '当前账号没有回填该厂区生产数据的权限。'
    return
  }

  const orderId = selectedTask.value.order.id
  applyLocalItemPatches(orderId)

  if (apiState.value !== 'connected') {
    actionMessage.value = '真实任务读取失败或暂无正式任务，不能保存回填。'
    return
  }

  try {
    const updated = await moldingSampleApi.updateItems(orderId, { items: buildItemPatches() })
    replaceApiRecord(updated)
    actionMessage.value = '啤机回填已保存，工程啤办单可以看到最新实际用料。'
  }
  catch (error) {
    actionMessage.value = `啤机回填保存失败：${getApiErrorMessage(error)}`
  }
}

function getProductionTransitionReason(action: ProductionTransitionAction) {
  if (action === '开始处理') {
    return '啤办生产任务单接收后开始执行。'
  }
  if (action === '撤回开始生产') {
    return '啤机部撤回开始生产，任务回到待生产。'
  }
  if (action === '标记完成') {
    return '啤机部完成生产并回传工程啤办单。'
  }

  return '啤机部撤回完成回传，回到生产中继续修正。'
}

async function runProductionTransition(action: ProductionTransitionAction) {
  if (!selectedTask.value) {
    actionMessage.value = '请先选择一张啤办生产任务单。'
    return
  }
  if (['开始处理', '撤回开始生产'].includes(action) && !canStartSelectedTaskFactory.value) {
    actionMessage.value = '当前账号没有开始或撤回该厂区生产任务的权限。'
    return
  }
  if (['标记完成', '撤回完成'].includes(action) && !canCompleteSelectedTaskFactory.value) {
    actionMessage.value = '当前账号没有完成或撤回该厂区生产任务的权限。'
    return
  }
  if (action === '开始处理' && !canStartSelectedTask.value) {
    actionMessage.value = '只有待生产任务可以开始执行。'
    return
  }
  if (action === '撤回开始生产' && !canRollbackStartedTask.value) {
    actionMessage.value = '只有生产中任务可以撤回开始生产。'
    return
  }
  if (action === '标记完成' && !canCompleteSelectedTask.value) {
    actionMessage.value = completionGate.value.message
    return
  }
  if (action === '撤回完成' && !canRollbackCompletedTask.value) {
    actionMessage.value = '只有已完成任务可以撤回完成回传。'
    return
  }

  const orderId = selectedTask.value.order.id

  if (action === '标记完成' && canFillbackSelectedTaskFactory.value) {
    applyLocalItemPatches(orderId)
  }

  if (apiState.value !== 'connected') {
    actionMessage.value = '真实任务读取失败或暂无正式任务，不能更新生产状态。'
    return
  }

  try {
    if (action === '标记完成' && canFillbackSelectedTaskFactory.value) {
      await moldingSampleApi.updateItems(orderId, { items: buildItemPatches() })
    }

    const payload: MoldingSampleStatusRequest = {
      action,
      reason: getProductionTransitionReason(action),
    }
    const updated = await moldingSampleApi.updateStatus(orderId, payload)
    replaceApiRecord(updated)
    if (action === '开始处理') {
      actionMessage.value = '啤办生产任务已开始执行。'
    }
    else if (action === '撤回开始生产') {
      actionMessage.value = '已撤回开始生产，任务回到待生产。'
    }
    else if (action === '标记完成') {
      actionMessage.value = '生产完成通知已回传到工程啤办单。'
    }
    else {
      actionMessage.value = '生产完成已撤回，可继续修正回填后重新完成。'
    }
  }
  catch (error) {
    actionMessage.value = `生产任务状态更新失败：${getApiErrorMessage(error)}`
  }
}

async function reportProductionProblem() {
  const problem = productionProblem.value.trim()
  if (!problem || !selectedTask.value) {
    return
  }
  if (!canFillbackSelectedTaskFactory.value) {
    actionMessage.value = '当前账号没有回填该厂区生产问题的权限。'
    return
  }

  const orderId = selectedTask.value.order.id

  if (apiState.value !== 'connected') {
    actionMessage.value = '真实任务读取失败或暂无正式任务，不能上报问题。'
    return
  }

  problemSubmitting.value = true

  try {
    const created = await moldingSampleApi.createProblem({
      order_id: orderId,
      description: problem,
    })
    appendProblemForOrder(orderId, created)
    actionMessage.value = `问题反馈已保存并同步给工程部：${problem}`
    productionProblem.value = ''
  }
  catch (error) {
    actionMessage.value = `问题反馈保存失败：${getApiErrorMessage(error)}`
  }
  finally {
    problemSubmitting.value = false
  }
}

function readInputValue(event: Event) {
  return (event.target as HTMLInputElement).value
}

onMounted(() => {
  void loadApiData()
  void loadProtectedMaterialPrices(selectedFactoryId.value)
})

watch(selectedTask, () => {
  itemDrafts.value = selectedTask.value?.items.reduce<Record<string, ItemFillbackDraft>>((acc, item) => {
    acc[item.id] = {
      actual_weight_kg: item.actual_weight_kg === null || item.actual_weight_kg === undefined ? '' : String(item.actual_weight_kg),
    }
    return acc
  }, {}) ?? {}
  isSelectedTaskDataExpanded.value = false
  selectedFullDataItemId.value = selectedTask.value?.items[0]?.id ?? ''
}, { immediate: true })

watch([queueFilter, productionSearchKeyword, selectedFactoryId], () => {
  queuePage.value = 1
})

watch(selectedFactoryId, (factoryId, previousFactoryId) => {
  if (previousFactoryId === undefined || factoryId === previousFactoryId) {
    return
  }

  trialReportSaveRequestId += 1
  trialReportSaving.value = false
  closeTrialReportDialog()
}, { flush: 'sync' })

watch(selectedFactoryId, (factoryId, previousFactoryId) => {
  if (previousFactoryId === undefined || factoryId === previousFactoryId) {
    return
  }

  void loadApiData()
  void loadProtectedMaterialPrices(factoryId)
})

onUnmounted(() => {
  apiDataRequestId += 1
  protectedMaterialPricesRequestId += 1
  trialReportSaveRequestId += 1
})

watchEffect(() => {
  appStore.setActiveFactory(selectedFactoryId.value)
})
</script>

<template>
  <main class="production-task-page app-shell min-h-screen bg-[radial-gradient(circle_at_top_left,rgba(20,184,166,0.09),transparent_32rem),linear-gradient(180deg,#f8fafc_0%,#eef4f8_100%)] px-4 pb-6 pt-16 text-[13px] leading-relaxed text-slate-900 sm:px-6 xl:px-10">
    <div class="app-page mx-auto max-w-[1720px] space-y-4">
      <RouterLink
        :to="productionDepartmentRoute"
        class="interactive-surface fixed left-4 top-4 z-50 inline-flex h-9 items-center gap-2 rounded-full border border-slate-200/80 bg-white/90 px-3 text-sm font-semibold text-slate-600 shadow-[0_8px_24px_-18px_rgba(15,23,42,0.45)] backdrop-blur-xl transition hover:border-teal-200 hover:bg-teal-50/90 hover:text-teal-800 sm:left-6 xl:left-10"
      >
        <ArrowLeft class="size-4" aria-hidden="true" />
        生产部模块
      </RouterLink>

      <div class="flex flex-wrap items-center gap-2 text-xs text-slate-400">
        <RouterLink :to="productionDepartmentRoute" class="font-medium hover:text-slate-900">
          生产部模块
        </RouterLink>
        <ChevronRight class="size-3.5" aria-hidden="true" />
        <span class="font-semibold text-slate-700">
          生产任务单 · {{ selectedTask?.order.id || '未选择' }}
        </span>
        <div class="fixed right-4 top-4 z-50 flex items-center gap-2 rounded-full border border-slate-200/80 bg-white/90 px-2 py-1 shadow-[0_8px_24px_-18px_rgba(15,23,42,0.45)] backdrop-blur-xl sm:right-6 xl:right-10">
          <span class="sr-only font-medium text-slate-500 lg:not-sr-only lg:inline" role="status" aria-live="polite">
            当前厂区：{{ activeFactory.shortName }} · {{ actionMessage }}
          </span>
          <AccountMenu />
        </div>
      </div>

      <section
        v-if="isSelectedFactoryReadOnly"
        class="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2.5 text-[12px] font-semibold text-amber-800"
      >
        <AlertTriangle class="mt-0.5 size-4 shrink-0 text-amber-600" aria-hidden="true" />
        <span>全厂只读：可查看当前厂区生产任务，不能开始、回填、完成、处理通知或上报问题</span>
      </section>

      <section class="enterprise-panel relative overflow-hidden rounded-2xl p-5">
        <span class="absolute inset-y-0 left-0 w-1 bg-gradient-to-b from-teal-500 via-teal-600 to-cyan-600" aria-hidden="true" />
        <span class="pointer-events-none absolute -right-20 -top-28 size-64 rounded-full bg-teal-100/45 blur-3xl" aria-hidden="true" />
        <div class="relative flex flex-wrap items-start justify-between gap-4">
          <div class="min-w-0">
            <p class="text-xs font-semibold uppercase tracking-[0.18em] text-teal-700">MOLDING SAMPLE PRODUCTION TASK</p>
            <h1 class="mt-1 text-2xl font-bold tracking-tight text-[#17385e]">啤机部生产任务单</h1>
            <p class="mt-1 max-w-4xl text-sm text-slate-600">
              啤办生产任务单用于接收工程啤办单通知，啤机部在这里开始执行、回填实际用料，完成后把状态回传到同一张工程啤办单。
            </p>
            <p class="mt-1 text-xs text-slate-500">
              主管审核通过后任务进入生产队列；铃铛通知独立同步，啤机部只处理生产执行字段，工程资料回到工程啤办单维护。
            </p>
          </div>

          <div class="flex flex-wrap gap-2">
            <RouterLink
              :to="engineeringOrderRoute"
              class="interactive-surface inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white/90 px-4 text-sm font-semibold text-slate-700 shadow-sm transition hover:border-teal-200 hover:bg-teal-50 hover:text-teal-800"
            >
              <Send class="size-4" aria-hidden="true" />
              工程啤办单
            </RouterLink>
            <button
              type="button"
              :disabled="apiState === 'checking'"
              :aria-busy="apiState === 'checking'"
              class="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-[#17385e] bg-[#17385e] px-4 text-sm font-semibold text-white shadow-[0_10px_24px_-16px_rgba(23,56,94,0.75)] transition hover:border-[#204b73] hover:bg-[#204b73] disabled:cursor-wait disabled:border-slate-300 disabled:bg-slate-300"
              @click="loadApiData"
            >
              <RotateCcw class="size-4" :class="apiState === 'checking' ? 'animate-spin' : ''" aria-hidden="true" />
              {{ apiState === 'checking' ? '刷新中' : '刷新任务' }}
            </button>
          </div>
        </div>
        <div v-if="apiState === 'checking'" class="absolute inset-x-0 bottom-0 h-0.5 overflow-hidden bg-teal-100" aria-hidden="true">
          <span class="production-loading-bar block h-full w-1/3 rounded-full bg-gradient-to-r from-teal-700 via-teal-500 to-cyan-400" />
        </div>
      </section>

      <div class="grid min-w-0 gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
        <aside class="min-w-0 space-y-3 xl:sticky xl:top-20 xl:self-start" aria-label="啤办生产任务队列">
          <section class="enterprise-panel rounded-2xl p-3.5">
            <div class="flex items-center justify-between gap-3">
              <div>
                <h2 class="text-[13px] font-bold text-slate-950">当前厂区生产队列</h2>
                <p class="mt-0.5 text-[11px] text-slate-400">正式生产任务 · {{ activeFactory.shortName }}</p>
              </div>
              <span class="rounded-full bg-teal-100 px-2 py-0.5 text-[11px] font-bold text-teal-700">{{ taskEntries.length }}</span>
            </div>
            <div class="relative mt-3">
              <Search class="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
              <input
                data-testid="production-task-search-input"
                v-model="productionSearchKeyword"
                type="search"
                aria-label="模糊搜索生产任务"
                autocomplete="off"
                placeholder="搜索单号 / 产品 / 客户 / 模具 / 原料..."
                class="h-9 w-full rounded-lg border border-slate-200 bg-slate-50/80 pl-8 pr-8 text-[12px] outline-none shadow-[inset_0_1px_2px_rgba(15,23,42,0.03)] transition focus:border-teal-300 focus:bg-white"
                @keydown.esc="productionSearchKeyword = ''"
              >
              <button
                v-if="productionSearchKeyword"
                type="button"
                aria-label="清除生产任务搜索"
                class="absolute right-1.5 top-1/2 flex size-6 -translate-y-1/2 items-center justify-center rounded-full text-slate-400 transition hover:bg-slate-200 hover:text-slate-700"
                @click="productionSearchKeyword = ''"
              >
                <X class="size-3.5" aria-hidden="true" />
              </button>
            </div>
            <p v-if="productionSearchTokens.length" class="mt-1.5 text-[11px] font-medium text-slate-500">
              找到 {{ searchMatchedTaskEntries.length }} 张匹配任务
            </p>
            <div class="mt-2 flex flex-wrap gap-1 text-[11px]">
              <button
                v-for="filter in queueFilters"
                :key="filter"
                type="button"
                :aria-pressed="queueFilter === filter"
                class="rounded-md px-2 py-1 font-semibold transition"
                :class="queueFilter === filter ? 'bg-[#17385e] text-white shadow-sm' : 'text-slate-500 hover:bg-teal-50 hover:text-teal-800'"
                @click="queueFilter = filter"
              >
                {{ filter }} {{ getQueueFilterCount(filter) }}
              </button>
            </div>
            <div class="surface-subtle mt-3 flex rounded-lg p-1 text-[11px] font-semibold">
              <button
                type="button"
                :aria-pressed="queueDisplayMode === 'board'"
                class="flex h-7 flex-1 items-center justify-center gap-1.5 rounded-md transition"
                :class="queueDisplayMode === 'board' ? 'bg-[#17385e] text-white shadow-sm' : 'text-slate-500 hover:bg-white hover:text-teal-800'"
                @click="setQueueDisplayMode('board')"
              >
                <LayoutDashboard class="size-3.5" aria-hidden="true" />
                看板
              </button>
              <button
                type="button"
                :aria-pressed="queueDisplayMode === 'list'"
                class="flex h-7 flex-1 items-center justify-center gap-1.5 rounded-md transition"
                :class="queueDisplayMode === 'list' ? 'bg-[#17385e] text-white shadow-sm' : 'text-slate-500 hover:bg-white hover:text-teal-800'"
                @click="setQueueDisplayMode('list')"
              >
                <Table2 class="size-3.5" aria-hidden="true" />
                列表
              </button>
            </div>
          </section>

          <div v-if="filteredTaskEntries.length" class="production-queue-list sidebar-scrollbar space-y-2 pr-0.5" @wheel="handoffWheelAtBoundary">
            <div v-if="queueDisplayMode === 'board'" class="reveal-grid space-y-2">
              <button
                v-for="entry in paginatedFilteredTaskEntries"
                :key="entry.order.id"
                type="button"
                :aria-current="selectedTask?.order.id === entry.order.id ? 'true' : undefined"
                class="interactive-surface w-full rounded-xl border bg-white p-2.5 text-left shadow-[0_1px_2px_rgba(15,23,42,0.04)] transition motion-reduce:transform-none motion-reduce:transition-none hover:border-teal-200 hover:bg-teal-50/40"
                :class="selectedTask?.order.id === entry.order.id ? 'border-teal-300 bg-gradient-to-r from-teal-50 to-white shadow-[inset_3px_0_0_rgba(13,148,136,0.75),0_8px_20px_-18px_rgba(13,148,136,0.8)] ring-1 ring-teal-100' : 'border-slate-200'"
                @click="selectTask(entry.order.id, entry.factory_id)"
              >
                <div class="flex items-start justify-between gap-2">
                  <span class="font-mono text-[12px] font-bold text-slate-800">{{ entry.order.id }}</span>
                  <StatusPill :label="getQueueStatusLabel(entry.order.status)" :tone="statusTones[entry.order.status]" compact />
                </div>
                <p class="mt-0.5 truncate text-[12px] font-semibold text-slate-950">{{ entry.order.product_name }}</p>
                <p class="truncate text-[11px] text-slate-400">
                  {{ entry.order.client_name }} · {{ entry.items.length }} 项 · 业务交期 {{ formatWorkflowDate(entry.items[0]?.completion_time || entry.order.date) }}
                </p>
                <p class="mt-0.5 truncate text-[10px] text-slate-400">{{ getTaskWorkflowDateLabel(entry.order) }}</p>
                <p class="mt-1 truncate text-[10px] font-semibold text-teal-700">任务通知 · {{ getNotificationMeta(entry.order.id) }}</p>
                <p
                  v-if="entry.order.status === '生产中' && entry.items.some((item) => !(Number(item.actual_weight_kg) > 0))"
                  class="mt-1.5 flex items-center gap-1 text-[10px] font-semibold text-red-500"
                >
                  <AlertTriangle class="size-3" aria-hidden="true" />
                  {{ entry.items.filter((item) => !(Number(item.actual_weight_kg) > 0)).length }} 项缺实际用料
                </p>
              </button>
            </div>

            <div v-else class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm" role="table" aria-label="啤办生产任务列表">
              <div class="grid grid-cols-[112px_minmax(0,1fr)_64px] gap-2 border-b border-slate-100 bg-slate-50 px-3 py-2 text-[11px] font-semibold text-slate-500" role="row">
                <div role="columnheader">单号</div>
                <div role="columnheader">产品 / 客户</div>
                <div class="text-right" role="columnheader">状态</div>
              </div>
              <button
                v-for="entry in paginatedFilteredTaskEntries"
                :key="`list-${entry.order.id}`"
                type="button"
                :aria-current="selectedTask?.order.id === entry.order.id ? 'true' : undefined"
                class="grid w-full grid-cols-[112px_minmax(0,1fr)_64px] gap-2 border-b border-slate-100 px-3 py-2 text-left text-[12px] transition last:border-b-0 hover:bg-teal-50/50"
                :class="selectedTask?.order.id === entry.order.id ? 'bg-teal-50/70' : 'bg-white'"
                role="row"
                @click="selectTask(entry.order.id, entry.factory_id)"
              >
                <span class="min-w-0 truncate font-mono font-bold text-slate-800" role="cell">{{ entry.order.id }}</span>
                <span class="min-w-0" role="cell">
                  <span class="block truncate font-semibold text-slate-950">{{ entry.order.product_name }}</span>
                  <span class="block truncate text-[11px] text-slate-400">{{ entry.order.client_name }} · {{ entry.items.length }} 项</span>
                </span>
                <span class="text-right text-[11px] font-semibold text-slate-500" role="cell">{{ getQueueStatusLabel(entry.order.status) }}</span>
              </button>
            </div>

            <div class="enterprise-panel flex items-center justify-between gap-2 rounded-xl px-3 py-2 text-[11px] text-slate-500">
              <span class="font-medium">每页 10 条</span>
              <span class="font-mono">{{ formatPaginationRange(filteredTaskPagination) }}</span>
              <div class="flex gap-1">
                <button
                  type="button"
                  :disabled="!filteredTaskPagination.hasPrevious"
                  class="h-7 rounded-md border border-slate-200 px-2 font-semibold text-slate-600 transition hover:border-slate-300 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-300"
                  @click="setQueuePage(filteredTaskPagination.page - 1)"
                >
                  上一页
                </button>
                <button
                  type="button"
                  :disabled="!filteredTaskPagination.hasNext"
                  class="h-7 rounded-md border border-slate-200 px-2 font-semibold text-slate-600 transition hover:border-slate-300 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-300"
                  @click="setQueuePage(filteredTaskPagination.page + 1)"
                >
                  下一页
                </button>
              </div>
            </div>
          </div>
          <div v-else class="rounded-xl border border-dashed border-slate-200 bg-white/70 p-5 text-center text-sm text-slate-500">
            {{ productionSearchTokens.length ? '未找到匹配的生产任务。' : '当前筛选下没有内部啤机生产任务。' }}
          </div>
        </aside>

        <section v-if="selectedTask" class="reveal-grid min-w-0 space-y-4">
          <section class="enterprise-panel rounded-2xl p-4">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <span class="font-mono text-lg font-bold text-slate-950">{{ selectedTask.order.id }}</span>
                  <StatusPill :label="selectedTask.order.status" :tone="statusTones[selectedTask.order.status]" compact />
                  <span class="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500">{{ selectedTask.order.stage || '啤办' }}</span>
                </div>
                <h2 class="mt-0.5 truncate text-[15px] font-bold text-slate-950">
                  {{ selectedTask.order.product_name }} · {{ selectedTask.order.client_name }}
                </h2>
                <div class="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-400">
                  <span>{{ selectedTask.order.workshop }}</span>
                  <span>工程 {{ selectedTask.order.eng_name }}</span>
                  <span>{{ getTaskStageDetail(selectedTask.order) }}</span>
                </div>
                <div
                  v-if="selectedNotification"
                  class="surface-subtle mt-3 flex flex-wrap items-center gap-2 rounded-lg px-3 py-2"
                >
                  <div class="min-w-0 flex-1">
                    <div class="flex flex-wrap items-center gap-2">
                      <span class="text-[11px] font-semibold text-slate-500">通知状态</span>
                      <span
                        class="rounded-full px-2 py-0.5 text-[10px] font-bold"
                        :class="getNotificationStatusClass(selectedNotification.status)"
                      >
                        {{ selectedNotification.status }}
                      </span>
                    </div>
                    <p class="mt-0.5 truncate text-[11px] text-slate-500">
                      {{ selectedNotification.title }} · {{ formatWorkflowTime(selectedNotification.created_at) }}
                    </p>
                  </div>
                  <button
                    type="button"
                    :disabled="notificationUpdating || !canMarkSelectedNotificationRead"
                    class="h-7 rounded-md border border-slate-200 bg-white px-2 text-[11px] font-semibold text-slate-600 transition hover:border-slate-300 hover:text-slate-950 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
                    @click="updateSelectedNotificationStatus('已读')"
                  >
                    标记已读
                  </button>
                  <button
                    type="button"
                    :disabled="notificationUpdating || !canMarkSelectedNotificationHandled"
                    class="h-7 rounded-md bg-[#17385e] px-2 text-[11px] font-semibold text-white transition hover:bg-[#204b73] disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
                    @click="updateSelectedNotificationStatus('已处理')"
                  >
                    标记已处理
                  </button>
                </div>
                <div
                  v-else
                  class="mt-3 rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-2 text-[11px] text-slate-500"
                >
                  当前任务未找到正式通知，刷新任务后可同步通知状态。
                </div>
              </div>
              <div class="rounded-xl border border-[#284f76] bg-gradient-to-br from-[#17385e] to-[#204b73] px-3.5 py-2.5 text-right text-white shadow-[0_12px_26px_-18px_rgba(23,56,94,0.85)]">
                <div class="text-[11px] text-slate-200">实际料费(HKD)</div>
                <div class="text-lg font-bold tabular-nums">{{ formatCurrency(selectedReportSummary?.total_material_cost, '$ 0.00') }}</div>
              </div>
              <button
                type="button"
                :disabled="!selectedTask.items.length"
                class="inline-flex h-9 items-center justify-center gap-1.5 rounded-lg border border-teal-200 bg-teal-50 px-3 text-[12px] font-semibold text-teal-800 transition hover:border-teal-300 hover:bg-teal-100 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-400"
                @click="openTrialReportDialog"
              >
                <ClipboardPenLine class="size-3.5" aria-hidden="true" />
                {{ canSaveSelectedTrialReport ? '试模报告填写 / 打印' : '试模报告查看 / 打印' }}
              </button>
              <button
                type="button"
                :disabled="!canPrintSelectedTask"
                class="inline-flex h-9 items-center justify-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400"
                @click="openTaskPrintPreview"
              >
                <Printer class="size-3.5" aria-hidden="true" />
                打印任务单
              </button>
            </div>
          </section>

          <section class="enterprise-panel rounded-2xl p-3.5" data-testid="molding-sample-trial-report-history">
            <div class="flex flex-wrap items-start justify-between gap-2">
              <div class="flex items-center gap-2">
                <ClipboardPenLine class="size-4 text-teal-700" aria-hidden="true" />
                <div>
                  <h3 class="text-[13px] font-bold text-slate-950">试模报告历史</h3>
                  <p class="mt-0.5 text-[11px] text-slate-500">已保存的报告自动同步到工程部单据详情，可随时查看和再次打印。</p>
                </div>
              </div>
              <span class="rounded-full bg-teal-50 px-2 py-0.5 text-[11px] font-semibold text-teal-700">{{ selectedTrialReports.length }} 份</span>
            </div>
            <div v-if="selectedTrialReports.length" class="mt-3 grid gap-2 md:grid-cols-2">
              <article
                v-for="report in selectedTrialReports"
                :key="report.id"
                class="interactive-surface surface-subtle flex min-w-0 items-center justify-between gap-3 rounded-lg px-3 py-2.5 motion-reduce:transform-none motion-reduce:transition-none"
              >
                <div class="min-w-0">
                  <p class="truncate text-[12px] font-semibold text-slate-900">
                    {{ selectedTask.items.find((item) => item.id === report.item_id)?.mold_id || '未填模具编号' }}
                    ·
                    {{ selectedTask.items.find((item) => item.id === report.item_id)?.mold_name || '未填模具名称' }}
                  </p>
                  <p class="mt-0.5 truncate text-[11px] text-slate-500">啤机部 {{ report.updated_by || report.created_by || '已保存' }} · {{ formatWorkflowTime(report.updated_at || report.created_at) }}</p>
                </div>
                <button
                  type="button"
                  class="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border border-teal-200 bg-white px-2.5 text-[11px] font-semibold text-teal-800 transition hover:bg-teal-50"
                  @click="openTrialReportHistory(report.item_id)"
                >
                  <Printer class="size-3.5" aria-hidden="true" />
                  查看 / 再次打印
                </button>
              </article>
            </div>
            <p v-else class="surface-subtle mt-3 rounded-lg border-dashed px-3 py-2 text-[11px] text-slate-500">
              暂无已保存报告。啤机部填写并保存后，这里会形成可查、可重印的历史记录。
            </p>
          </section>

          <div
            v-if="selectedTask.order.status === '生产中' && !completionGate.can_complete"
            class="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-red-700"
          >
            <ShieldAlert class="mt-0.5 size-5 shrink-0 text-red-500" aria-hidden="true" />
            <div class="text-[12px]">
              <b>无法标记完成：</b>{{ completionGate.message }}
              <span v-if="selectedMissingItems[0]" class="font-mono">
                {{ selectedMissingItems[0].mold_id }} {{ selectedMissingItems[0].mold_name }}
              </span>
            </div>
          </div>

          <section class="enterprise-panel min-w-0 overflow-clip rounded-2xl">
            <div class="flex flex-wrap items-center gap-2 border-b border-slate-100 bg-gradient-to-r from-slate-50/90 via-white to-teal-50/40 px-4 py-3">
              <PencilRuler class="size-4 text-slate-400" aria-hidden="true" />
              <span class="text-[13px] font-bold text-slate-950">啤机回填明细 · 实际用料回填</span>
              <span class="ml-auto text-[11px] text-slate-400">
                {{ activeItems.length }} 项<span class="hidden md:inline"> · 区域内滚动查看</span> · 单价按原料表
              </span>
              <button
                type="button"
                class="inline-flex h-7 items-center rounded-md border border-slate-200 bg-white px-2 text-[11px] font-semibold text-slate-600 transition hover:border-teal-200 hover:bg-teal-50 hover:text-teal-800"
                :aria-expanded="isSelectedTaskDataExpanded"
                aria-controls="production-complete-order-data"
                @click="isSelectedTaskDataExpanded = !isSelectedTaskDataExpanded"
              >
                {{ isSelectedTaskDataExpanded ? '收起完整数据' : '展开完整数据' }}
              </button>
            </div>
            <div data-testid="production-fillback-list" class="p-3">
              <div
                class="production-fillback-scroll sidebar-scrollbar rounded-xl bg-slate-50/60 p-1 outline-none focus-visible:ring-2 focus-visible:ring-teal-500/35 focus-visible:ring-offset-2"
                role="region"
                aria-label="啤机回填模具明细"
                tabindex="0"
                @wheel="handoffWheelAtBoundary"
              >
                <div data-testid="production-fillback-grid" class="production-fillback-grid">
                  <article
                    v-for="item in activeItems"
                    :key="item.id"
                    data-testid="production-fillback-item"
                    class="overflow-clip rounded-xl border bg-white shadow-[0_8px_24px_-22px_rgba(15,23,42,0.35)]"
                    :class="Number(item.actual_weight_kg) > 0 ? 'border-slate-200' : 'border-red-200 ring-1 ring-red-100'"
                  >
                <div class="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 bg-gradient-to-r from-slate-50 via-white to-teal-50/30 px-4 py-3">
                  <div class="flex min-w-0 items-start gap-3">
                    <span class="flex h-7 min-w-7 shrink-0 items-center justify-center rounded-lg bg-[#17385e] px-2 text-[11px] font-bold text-white shadow-sm">
                      {{ item.sort_order }}
                    </span>
                    <div class="min-w-0">
                      <div class="break-all font-mono text-[12px] font-semibold text-slate-950">{{ item.mold_id }}</div>
                      <div class="mt-0.5 break-words text-[13px] font-semibold text-slate-700">{{ item.mold_name }}</div>
                    </div>
                  </div>
                  <div class="flex flex-wrap items-center justify-end gap-2">
                    <span
                      class="rounded-full px-2.5 py-1 text-[10px] font-bold"
                      :class="item.material_usage_type === 'trial' ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'"
                    >
                      {{ item.material_usage_type === 'trial' ? '试料 · 不计结余' : '正式生产' }}
                    </span>
                    <span
                      class="inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[10px] font-bold"
                      :class="Number(item.actual_weight_kg) > 0 ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-red-200 bg-red-50 text-red-700'"
                    >
                      <AlertTriangle v-if="!(Number(item.actual_weight_kg) > 0)" class="size-3" aria-hidden="true" />
                      {{ Number(item.actual_weight_kg) > 0 ? '已回填' : '待回填' }}
                    </span>
                  </div>
                </div>

                    <div class="p-3">
                      <div class="grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(11rem,0.72fr)]">
                        <section class="surface-subtle rounded-lg p-3">
                      <h4 class="text-[11px] font-bold tracking-wide text-slate-500">原料资料</h4>
                      <dl class="mt-3 space-y-3">
                        <div>
                          <dt class="text-[11px] font-medium text-slate-500">原料配比</dt>
                          <dd class="mt-1 break-words text-[13px] font-semibold leading-5 text-slate-900">
                            {{ formatMaterialComposition(resolveMaterialComponents(item)) }}
                          </dd>
                        </div>
                        <div class="border-t border-slate-200 pt-3">
                          <dt class="text-[11px] font-medium text-slate-500">备注 / 颜色</dt>
                          <dd class="mt-1 break-words text-[12px] leading-5" :class="Number(item.actual_weight_kg) > 0 ? 'text-slate-600' : 'font-semibold text-red-600'">
                            {{ item.notes || item.color || '待啤机部补实际用料' }}
                          </dd>
                        </div>
                      </dl>
                    </section>

                        <section data-testid="production-fillback-usage-panel" class="surface-subtle rounded-lg p-3">
                      <h4 class="text-[11px] font-bold tracking-wide text-slate-500">用量回填</h4>
                      <div class="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
                        <div class="rounded-lg bg-slate-50 px-3 py-2.5">
                          <div class="text-[11px] font-medium text-slate-500">领料重量</div>
                          <div class="mt-1 text-[15px] font-bold tabular-nums text-slate-950">
                            {{ formatWeight(item.collected_weight_kg ?? item.required_material_kg) }}
                          </div>
                        </div>
                        <label class="block rounded-lg bg-slate-50 px-3 py-2.5">
                          <span class="text-[11px] font-medium" :class="Number(item.actual_weight_kg) > 0 ? 'text-slate-500' : 'text-red-600'">实际用料</span>
                          <span class="mt-1 flex items-center gap-2">
                            <input
                              data-testid="production-actual-weight-input"
                              :value="itemDrafts[item.id]?.actual_weight_kg ?? ''"
                              :disabled="!canFillbackSelectedTask"
                              :aria-label="`${item.mold_id} 实际用料`"
                              type="number"
                              min="0"
                              step="0.01"
                              class="h-9 min-w-0 flex-1 rounded-md px-2.5 text-right text-[14px] font-bold tabular-nums outline-none disabled:bg-slate-100 disabled:text-slate-400"
                              :class="Number(item.actual_weight_kg) > 0 ? 'border border-emerald-200 bg-emerald-50 focus:border-emerald-400' : 'border-2 border-red-300 bg-white placeholder:text-red-300 focus:border-red-500'"
                              :placeholder="Number(item.actual_weight_kg) > 0 ? '' : '必填'"
                              @input="updateItemDraft(item.id, 'actual_weight_kg', readInputValue($event))"
                            >
                            <span class="text-[11px] font-semibold text-slate-400">kg</span>
                          </span>
                        </label>
                      </div>
                    </section>
                  </div>

                      <section data-testid="production-fillback-cost-grid" class="mt-2 grid gap-2 sm:grid-cols-2">
                    <article data-testid="production-fillback-expected-cost-panel" class="overflow-clip rounded-xl border border-slate-200/80 bg-white/90">
                      <div class="border-b border-slate-100 bg-slate-50 px-3.5 py-2.5">
                        <h4 class="text-[11px] font-bold text-slate-600">预计料费(HKD)</h4>
                        <p class="mt-0.5 text-[11px] text-slate-500">按预计用料与当前原料价计算</p>
                      </div>
                      <div class="divide-y divide-slate-100 px-3.5">
                        <div
                          v-for="(component, componentIndex) in getExpectedMaterialCostBreakdown(item).components"
                          :key="`production-expected-${item.id}-${componentIndex}`"
                          class="flex items-start justify-between gap-3 py-3"
                        >
                          <div class="min-w-0">
                            <div class="break-words text-[12px] font-semibold leading-5 text-slate-800">{{ component.material }}</div>
                            <div class="mt-0.5 text-[11px] text-slate-500">{{ getMaterialSourceLabel(component.source_type) }}</div>
                          </div>
                          <div class="shrink-0 text-right tabular-nums">
                            <div class="text-[11px] text-slate-500">{{ formatWeight(component.weight_kg) }}</div>
                            <div class="mt-0.5 text-[12px] font-semibold text-slate-900">{{ formatCurrency(component.amount_hkd) }}</div>
                          </div>
                        </div>
                      </div>
                      <div class="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-3.5 py-2.5 text-[12px] font-bold text-slate-950">
                        <span>预计合计</span>
                        <span class="tabular-nums">{{ formatCurrency(getExpectedMaterialCostBreakdown(item).total_amount_hkd) }}</span>
                      </div>
                    </article>

                    <article data-testid="production-fillback-actual-cost-panel" class="overflow-clip rounded-xl border border-slate-200/80 bg-white/90">
                      <div class="border-b border-slate-100 bg-slate-50 px-3.5 py-2.5">
                        <h4 class="text-[11px] font-bold text-slate-600">实际料费(HKD)</h4>
                        <p
                          data-testid="production-actual-material-cost-source"
                          class="mt-0.5 text-[11px] font-semibold"
                          :class="getActualMaterialCostBreakdown(item).source === 'persisted' ? 'text-emerald-600' : 'text-amber-600'"
                        >
                          {{ getActualMaterialCostSourceLabel(item) }}
                        </p>
                      </div>
                      <div class="divide-y divide-slate-100 px-3.5">
                        <div
                          v-for="(component, componentIndex) in getActualMaterialCostBreakdown(item).components"
                          :key="`production-actual-${item.id}-${componentIndex}`"
                          class="flex items-start justify-between gap-3 py-3"
                        >
                          <div class="min-w-0">
                            <div class="break-words text-[12px] font-semibold leading-5 text-slate-800">{{ component.material }}</div>
                            <div class="mt-0.5 text-[11px] text-slate-500">{{ getMaterialSourceLabel(component.source_type) }}</div>
                          </div>
                          <div class="shrink-0 text-right tabular-nums">
                            <div class="text-[11px] text-slate-500">{{ formatWeight(component.weight_kg) }}</div>
                            <div class="mt-0.5 text-[12px] font-semibold text-slate-900">{{ formatCurrency(component.amount_hkd) }}</div>
                          </div>
                        </div>
                      </div>
                      <div class="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-3.5 py-2.5 text-[12px] font-bold text-slate-950">
                        <span>实际合计</span>
                        <span data-testid="production-fillback-actual-total" class="tabular-nums">{{ formatCurrency(getActualMaterialCostTotal(item)) }}</span>
                      </div>
                    </article>
                      </section>
                    </div>
                  </article>
                </div>
              </div>

              <div data-testid="production-fillback-summary" class="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#284f76] bg-gradient-to-r from-[#17385e] to-[#204b73] px-4 py-3 text-white shadow-[0_12px_28px_-20px_rgba(23,56,94,0.85)]">
                <div>
                  <div class="text-[11px] font-semibold text-slate-300">实际料费合计</div>
                  <div class="mt-0.5 text-[11px] text-slate-300">
                    {{ selectedReportSummary?.has_missing_actual_weight ? '仍有模具待补齐实际用料' : '全部模具已回填实际用料' }}
                  </div>
                </div>
                <div class="text-[18px] font-bold tabular-nums">{{ formatCurrency(selectedReportSummary?.total_material_cost, '$ 0.00') }}</div>
              </div>
            </div>
            <Transition
              enter-active-class="transition duration-200 ease-out motion-reduce:transition-none"
              enter-from-class="-translate-y-2 opacity-0"
              enter-to-class="translate-y-0 opacity-100"
              leave-active-class="transition duration-150 ease-in motion-reduce:transition-none"
              leave-from-class="translate-y-0 opacity-100"
              leave-to-class="-translate-y-2 opacity-0"
            >
              <div v-if="isSelectedTaskDataExpanded" id="production-complete-order-data" class="border-t border-slate-100 bg-slate-50/70 p-4">
                <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <h3 class="text-[13px] font-bold text-slate-950">完整单据数据</h3>
                    <p class="text-[11px] text-slate-500">单头资料与全部模具明细字段，供啤机回填前完整核对。</p>
                  </div>
                  <span class="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[11px] font-semibold text-slate-500">
                    {{ selectedTask.order.id }}
                  </span>
                </div>

                <div class="grid gap-2 text-[12px] md:grid-cols-3 xl:grid-cols-4">
                  <div class="rounded-lg border border-slate-200 bg-white px-3 py-2">
                    <div class="text-[10px] font-semibold text-slate-400">产品编号</div>
                    <div class="mt-0.5 font-semibold text-slate-900">{{ formatBlank(selectedTask.order.order_number) }}</div>
                  </div>
                  <div class="rounded-lg border border-slate-200 bg-white px-3 py-2">
                    <div class="text-[10px] font-semibold text-slate-400">产品 / 客户</div>
                    <div class="mt-0.5 font-semibold text-slate-900">{{ selectedTask.order.product_name }} · {{ selectedTask.order.client_name }}</div>
                  </div>
                  <div class="rounded-lg border border-slate-200 bg-white px-3 py-2">
                    <div class="text-[10px] font-semibold text-slate-400">状态 / 阶段 / 类型</div>
                    <div class="mt-0.5 font-semibold text-slate-900">{{ selectedTask.order.status }} · {{ selectedTask.order.stage || '待填写' }} · {{ selectedTask.order.order_type }}</div>
                  </div>
                  <div class="rounded-lg border border-slate-200 bg-white px-3 py-2">
                    <div class="text-[10px] font-semibold text-slate-400">填写部 / 发至</div>
                    <div class="mt-0.5 font-semibold text-slate-900">{{ formatBlank(selectedTask.order.workshop) }} / {{ formatBlank(selectedTask.order.send_to, '内部') }}</div>
                  </div>
                  <div class="rounded-lg border border-slate-200 bg-white px-3 py-2">
                    <div class="text-[10px] font-semibold text-slate-400">工程 / 主管</div>
                    <div class="mt-0.5 font-semibold text-slate-900">{{ formatBlank(selectedTask.order.eng_name) }} / {{ formatBlank(selectedTask.order.supervisor) }}</div>
                  </div>
                  <div class="rounded-lg border border-slate-200 bg-white px-3 py-2">
                    <div class="text-[10px] font-semibold text-slate-400">业务开单日期</div>
                    <div class="mt-0.5 font-semibold text-slate-900">{{ formatWorkflowDate(selectedTask.order.date) }}</div>
                  </div>
                  <div class="rounded-lg border border-slate-200 bg-white px-3 py-2">
                    <div class="text-[10px] font-semibold text-slate-400">流程完成日期</div>
                    <div class="mt-0.5 font-semibold text-slate-900">{{ formatWorkflowDate(selectedTask.order.completed_date, '未完成') }}</div>
                  </div>
                  <div class="rounded-lg border border-slate-200 bg-white px-3 py-2">
                    <div class="text-[10px] font-semibold text-slate-400">系统提交时间（北京时间）</div>
                    <div class="mt-0.5 font-semibold text-slate-900">{{ formatWorkflowTime(selectedTask.order.created_at) }}</div>
                  </div>
                  <div class="rounded-lg border border-slate-200 bg-white px-3 py-2">
                    <div class="text-[10px] font-semibold text-slate-400">系统更新时间（北京时间）</div>
                    <div class="mt-0.5 font-semibold text-slate-900">{{ formatWorkflowTime(selectedTask.order.updated_at) }}</div>
                  </div>
                </div>

                <div class="mt-3 rounded-lg border border-slate-200 bg-white px-3 py-2">
                  <div class="text-[10px] font-semibold text-slate-400">注意事项 / 开单事由</div>
                  <p class="mt-1 text-[12px] leading-5 text-slate-700">{{ formatBlank(selectedTask.order.reason) }}</p>
                  <p v-if="selectedTask.order.reject_reason" class="mt-1 text-[12px] leading-5 text-red-600">
                    驳回原因：{{ selectedTask.order.reject_reason }}
                  </p>
                </div>

                <div data-testid="production-full-item-master-detail" class="production-full-item-master mt-4">
                  <nav class="production-full-item-index enterprise-panel sidebar-scrollbar min-w-0 rounded-xl p-2" aria-label="模具明细索引" @wheel="handoffWheelAtBoundary">
                    <div class="mb-2 hidden items-center justify-between px-1 lg:flex">
                      <span class="text-[11px] font-bold text-slate-600">模具索引</span>
                      <span class="text-[10px] text-slate-400">{{ activeItems.length }} 项</span>
                    </div>
                    <div class="production-full-item-index-options" aria-label="选择要核对的模具">
                      <button
                        v-for="item in activeItems"
                        :key="`production-full-index-${item.id}`"
                        type="button"
                        data-testid="production-full-item-index-button"
                        :aria-pressed="selectedFullDataItem?.id === item.id"
                        class="min-w-[13rem] rounded-lg border px-3 py-2 text-left outline-none transition focus-visible:ring-2 focus-visible:ring-teal-500/35 focus-visible:ring-offset-2 motion-reduce:transition-none lg:min-w-0 lg:w-full"
                        :class="selectedFullDataItem?.id === item.id
                          ? 'border-teal-300 bg-teal-50 text-teal-950 shadow-sm ring-1 ring-teal-100'
                          : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50'"
                        @click="selectFullDataItem(item.id)"
                      >
                        <span class="flex items-center gap-2">
                          <span
                            class="flex h-5 min-w-5 shrink-0 items-center justify-center rounded px-1 text-[10px] font-bold"
                            :class="selectedFullDataItem?.id === item.id ? 'bg-teal-600 text-white' : 'bg-slate-100 text-slate-600'"
                          >
                            {{ item.sort_order }}
                          </span>
                          <span class="min-w-0 flex-1 truncate font-mono text-[11px] font-semibold">{{ formatBlank(item.mold_id) }}</span>
                          <span class="shrink-0 text-[9px] font-bold" :class="Number(item.actual_weight_kg) > 0 ? 'text-emerald-700' : 'text-amber-700'">
                            {{ Number(item.actual_weight_kg) > 0 ? '已回填' : '待回填' }}
                          </span>
                        </span>
                        <span class="mt-1 block truncate text-[12px] font-semibold">{{ formatBlank(item.mold_name) }}</span>
                        <span class="mt-1 flex items-center justify-between gap-2 text-[10px]" :class="selectedFullDataItem?.id === item.id ? 'text-teal-800' : 'text-slate-500'">
                          <span class="min-w-0 truncate">{{ formatMaterialComposition(resolveMaterialComponents(item)) }}</span>
                          <span class="shrink-0 tabular-nums">{{ formatWeight(item.required_material_kg) }}</span>
                        </span>
                      </button>
                    </div>
                  </nav>

                  <div
                    ref="fullDataItemPane"
                    class="production-full-item-pane sidebar-scrollbar min-w-0 rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-teal-500/35 focus-visible:ring-offset-2"
                    role="region"
                    :aria-label="`${selectedFullDataItem?.mold_id || '当前模具'}完整数据`"
                    tabindex="0"
                    @wheel="handoffWheelAtBoundary"
                  >
                    <article
                      v-for="item in selectedFullDataItem ? [selectedFullDataItem] : []"
                      :id="`production-full-panel-${item.id}`"
                      :key="`production-full-${item.id}`"
                      data-testid="production-full-item-card"
                      class="enterprise-panel overflow-clip rounded-xl"
                    >
                    <div class="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 bg-gradient-to-r from-slate-50 via-white to-teal-50/30 px-4 py-3">
                      <div class="flex min-w-0 items-start gap-3">
                        <span class="flex h-7 min-w-7 shrink-0 items-center justify-center rounded-lg bg-[#17385e] px-2 text-[11px] font-bold text-white shadow-sm">
                          {{ item.sort_order }}
                        </span>
                        <div class="min-w-0">
                          <div class="break-all font-mono text-[12px] font-semibold text-slate-950">{{ item.mold_id }}</div>
                          <div class="mt-0.5 break-words text-[13px] font-semibold text-slate-700">{{ item.mold_name }}</div>
                        </div>
                      </div>
                      <div class="flex flex-wrap items-center justify-end gap-2">
                        <span
                          class="rounded-full px-2.5 py-1 text-[10px] font-bold"
                          :class="item.material_usage_type === 'trial' ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'"
                        >
                          {{ item.material_usage_type === 'trial' ? '试料 · 不计结余' : '正式生产' }}
                        </span>
                        <span
                          class="rounded-full border px-2.5 py-1 text-[10px] font-bold"
                          :class="Number(item.actual_weight_kg) > 0 ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-amber-200 bg-amber-50 text-amber-700'"
                        >
                          {{ Number(item.actual_weight_kg) > 0 ? '已回填' : '待回填' }}
                        </span>
                      </div>
                    </div>
                    <div class="p-3">
                      <div class="grid gap-3 md:grid-cols-2">
                        <section data-testid="production-full-item-material-section" class="surface-subtle rounded-xl p-3.5">
                          <h4 class="text-[11px] font-bold tracking-wide text-slate-500">原料与颜色</h4>
                          <dl class="mt-3 space-y-3">
                            <div>
                              <dt class="text-[11px] font-medium text-slate-500">原料配比</dt>
                              <dd class="mt-1 break-words text-[13px] font-semibold leading-5 text-slate-900">
                                {{ formatMaterialComposition(resolveMaterialComponents(item)) }}
                              </dd>
                            </div>
                            <div class="border-t border-slate-200 pt-3">
                              <dt class="text-[11px] font-medium text-slate-500">颜色 / PMS</dt>
                              <dd class="mt-1 break-words text-[13px] font-semibold text-slate-900">{{ formatBlank(item.color) }} / {{ formatBlank(item.pigment_no) }}</dd>
                            </div>
                          </dl>
                        </section>

                        <section data-testid="production-full-item-timing-section" class="surface-subtle rounded-xl p-3.5">
                          <h4 class="text-[11px] font-bold tracking-wide text-slate-500">生产数量与时点</h4>
                          <dl class="mt-3 grid gap-x-4 gap-y-3 sm:grid-cols-2">
                            <div>
                              <dt class="text-[11px] font-medium text-slate-500">数量 / 啤数</dt>
                              <dd class="mt-1 text-[13px] font-semibold tabular-nums text-slate-900">{{ formatBlank(item.quantity) }} / {{ formatBlank(item.shoot_qty) }}</dd>
                            </div>
                            <div>
                              <dt class="text-[11px] font-medium text-slate-500">预计用料</dt>
                              <dd class="mt-1 text-[13px] font-semibold tabular-nums text-slate-900">{{ formatWeight(item.required_material_kg) }}</dd>
                            </div>
                            <div class="sm:col-span-2">
                              <dt class="text-[11px] font-medium text-slate-500">业务回模 / 需办日期</dt>
                              <dd class="mt-1 text-[13px] font-semibold tabular-nums text-slate-900">{{ formatWorkflowDate(item.mold_return_time) }} / {{ formatWorkflowDate(item.completion_time) }}</dd>
                            </div>
                          </dl>
                        </section>
                      </div>

                      <section data-testid="production-full-item-usage-section" class="surface-subtle mt-3 rounded-xl p-3.5">
                        <h4 class="text-[11px] font-bold tracking-wide text-slate-500">实际用量</h4>
                        <dl class="mt-3 grid gap-2 sm:grid-cols-2">
                          <div class="rounded-lg bg-slate-50 px-3 py-2.5">
                            <dt class="text-[11px] font-medium text-slate-500">领料重量</dt>
                            <dd class="mt-1 text-[15px] font-bold tabular-nums text-slate-950">{{ formatWeight(item.collected_weight_kg) }}</dd>
                          </div>
                          <div class="rounded-lg bg-gradient-to-br from-[#17385e] to-[#204b73] px-3 py-2.5 text-white shadow-sm">
                            <dt class="text-[11px] font-medium text-slate-300">实际用料</dt>
                            <dd class="mt-1 text-[15px] font-bold tabular-nums">{{ formatWeight(item.actual_weight_kg) }}</dd>
                          </div>
                        </dl>
                      </section>

                      <section data-testid="production-full-item-cost-grid" class="mt-3 grid gap-3 lg:grid-cols-2">
                        <article class="overflow-clip rounded-xl border border-slate-200">
                          <div class="border-b border-slate-100 bg-slate-50 px-3.5 py-2.5">
                            <h4 class="text-[11px] font-bold text-slate-600">预计料费(HKD)</h4>
                            <p class="mt-0.5 text-[11px] text-slate-500">按预计用料与当前原料价计算</p>
                          </div>
                          <div class="divide-y divide-slate-100 px-3.5">
                            <div
                              v-for="(component, componentIndex) in getExpectedMaterialCostBreakdown(item).components"
                              :key="`production-full-expected-${item.id}-${componentIndex}`"
                              class="flex items-start justify-between gap-3 py-3"
                            >
                              <div class="min-w-0">
                                <div class="break-words text-[12px] font-semibold leading-5 text-slate-800">{{ component.material }}</div>
                                <div class="mt-0.5 text-[11px] text-slate-500">{{ getMaterialSourceLabel(component.source_type) }}</div>
                              </div>
                              <div class="shrink-0 text-right tabular-nums">
                                <div class="text-[11px] text-slate-500">{{ formatWeight(component.weight_kg) }}</div>
                                <div class="mt-0.5 text-[12px] font-semibold text-slate-900">{{ formatCurrency(component.amount_hkd) }}</div>
                              </div>
                            </div>
                          </div>
                          <div class="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-3.5 py-2.5 text-[12px] font-bold text-slate-950">
                            <span>预计合计</span>
                            <span class="tabular-nums">{{ formatCurrency(getExpectedMaterialCostBreakdown(item).total_amount_hkd) }}</span>
                          </div>
                        </article>

                        <article class="overflow-clip rounded-xl border border-slate-200">
                          <div class="border-b border-slate-100 bg-slate-50 px-3.5 py-2.5">
                            <h4 class="text-[11px] font-bold text-slate-600">实际料费(HKD)</h4>
                            <p
                              data-testid="production-full-actual-material-cost-source"
                              class="mt-0.5 text-[11px] font-semibold"
                              :class="getActualMaterialCostBreakdown(item).source === 'persisted' ? 'text-emerald-600' : 'text-amber-600'"
                            >
                              {{ getActualMaterialCostSourceLabel(item) }}
                            </p>
                          </div>
                          <div class="divide-y divide-slate-100 px-3.5">
                            <div
                              v-for="(component, componentIndex) in getActualMaterialCostBreakdown(item).components"
                              :key="`production-full-actual-${item.id}-${componentIndex}`"
                              class="flex items-start justify-between gap-3 py-3"
                            >
                              <div class="min-w-0">
                                <div class="break-words text-[12px] font-semibold leading-5 text-slate-800">{{ component.material }}</div>
                                <div class="mt-0.5 text-[11px] text-slate-500">{{ getMaterialSourceLabel(component.source_type) }}</div>
                              </div>
                              <div class="shrink-0 text-right tabular-nums">
                                <div class="text-[11px] text-slate-500">{{ formatWeight(component.weight_kg) }}</div>
                                <div class="mt-0.5 text-[12px] font-semibold text-slate-900">{{ formatCurrency(component.amount_hkd) }}</div>
                              </div>
                            </div>
                          </div>
                          <div class="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-3.5 py-2.5 text-[12px] font-bold text-slate-950">
                            <span>实际合计</span>
                            <span class="tabular-nums">{{ formatCurrency(getActualMaterialCostTotal(item)) }}</span>
                          </div>
                        </article>
                      </section>

                      <p class="mt-3 rounded-lg border border-slate-100 bg-slate-50 px-3 py-2.5 text-[12px] leading-5 text-slate-600">
                        <span class="font-semibold text-slate-500">备注：</span>{{ formatBlank(item.notes) }}
                      </p>
                    </div>
                    </article>
                  </div>
                </div>
              </div>
            </Transition>
          </section>

          <div class="grid gap-4 md:grid-cols-2">
            <section class="enterprise-panel rounded-2xl p-4">
              <div class="mb-2 flex items-center gap-2">
                <ListChecks class="size-4 text-slate-400" aria-hidden="true" />
                <span class="text-[13px] font-bold text-slate-950">生产操作</span>
              </div>
              <div class="space-y-2">
                <button
                  type="button"
                  :disabled="!canStartSelectedTask"
                  class="flex h-10 w-full items-center justify-center gap-2 rounded-lg text-[13px] font-semibold transition disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
                  :class="canStartSelectedTask ? 'bg-[#17385e] text-white shadow-sm hover:bg-[#204b73]' : ''"
                  @click="runProductionTransition('开始处理')"
                >
                  <Play class="size-4" aria-hidden="true" />
                  开始生产
                </button>
                <button
                  v-if="canRollbackStartedTask"
                  type="button"
                  class="flex h-10 w-full items-center justify-center gap-2 rounded-lg border border-amber-200 bg-amber-50 text-[13px] font-semibold text-amber-700 transition hover:border-amber-300 hover:bg-amber-100"
                  @click="runProductionTransition('撤回开始生产')"
                >
                  <RotateCcw class="size-4" aria-hidden="true" />
                  撤回开始生产
                </button>
                <button
                  type="button"
                  :disabled="!canCompleteSelectedTask"
                  class="flex h-10 w-full items-center justify-center gap-2 rounded-lg text-[13px] font-semibold transition disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
                  :class="canCompleteSelectedTask ? 'bg-emerald-700 text-white hover:bg-emerald-800' : ''"
                  @click="runProductionTransition('标记完成')"
                >
                  <CheckCircle2 v-if="canCompleteSelectedTask || selectedTask.order.status === '已完成'" class="size-4" aria-hidden="true" />
                  <Lock v-else class="size-4" aria-hidden="true" />
                  {{ selectedTask.order.status === '已完成' ? '已完成回传' : canCompleteSelectedTask ? '完成并回传' : `标记完成（缺 ${completionGate.missing_item_ids.length} 项用料）` }}
                </button>
                <button
                  v-if="canRollbackCompletedTask"
                  type="button"
                  class="flex h-10 w-full items-center justify-center gap-2 rounded-lg border border-amber-200 bg-amber-50 text-[13px] font-semibold text-amber-700 transition hover:border-amber-300 hover:bg-amber-100"
                  @click="runProductionTransition('撤回完成')"
                >
                  <RotateCcw class="size-4" aria-hidden="true" />
                  撤回完成
                </button>
                <div class="flex gap-2">
                  <button
                    type="button"
                    :disabled="!canFillbackSelectedTask"
                    class="flex h-9 flex-1 items-center justify-center gap-1.5 rounded-lg border border-slate-200 text-[12px] font-medium text-slate-600 transition hover:border-slate-300 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400"
                    @click="saveProductionFillback"
                  >
                    <Save class="size-3.5" aria-hidden="true" />
                    保存回填
                  </button>
                  <RouterLink
                    :to="engineeringOrderRoute"
                    class="flex h-9 flex-1 items-center justify-center gap-1.5 rounded-lg border border-slate-200 text-[12px] font-medium text-slate-600 transition hover:border-slate-300 hover:text-slate-950"
                  >
                    <Package class="size-3.5" aria-hidden="true" />
                    工程啤办单
                  </RouterLink>
                </div>
              </div>
            </section>

            <section class="enterprise-panel rounded-2xl p-4">
              <div class="mb-2 flex flex-wrap items-center gap-2">
                <Flag class="size-4 text-slate-400" aria-hidden="true" />
                <span class="text-[13px] font-bold text-slate-950">问题记录</span>
                <span
                  v-if="selectedProblems.length"
                  class="rounded-full bg-red-100 px-1.5 py-0.5 text-[10px] font-bold text-red-600"
                >
                  {{ selectedProblems.length }} 待处理
                </span>
              </div>
              <div v-if="selectedProblems.length" class="space-y-2">
                <article
                  v-for="problem in selectedProblems"
                  :key="problem.id"
                  class="rounded-lg border border-red-100 bg-red-50 p-2 text-[11px] text-red-800"
                >
                  <div class="font-semibold text-red-700">{{ problem.status }} · {{ problem.description }}</div>
                  <div class="mt-0.5 text-red-400">{{ problem.reported_by }} · {{ formatWorkflowTime(problem.created_at) }}</div>
                </article>
              </div>
              <div v-else class="rounded-lg border border-slate-100 bg-slate-50 p-2 text-[11px] text-slate-500">
                暂无问题反馈。
              </div>
              <div class="mt-2 grid gap-2 sm:grid-cols-[minmax(0,1fr)_112px]">
                <input
                  v-model="productionProblem"
                  :disabled="problemSubmitting || !canFillbackSelectedTaskFactory"
                  class="h-8 rounded-lg border border-slate-200 bg-white px-2 text-[12px] outline-none focus:border-slate-400 disabled:bg-slate-50 disabled:text-slate-400"
                  placeholder="生产问题反馈，可回到工程啤办单跟进"
                >
                <button
                  type="button"
                  :disabled="problemSubmitting || !canFillbackSelectedTaskFactory || !productionProblem.trim()"
                  class="flex h-8 items-center justify-center gap-1.5 rounded-lg border border-slate-200 text-[11px] font-medium text-slate-500 transition hover:border-slate-300 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400"
                  @click="reportProductionProblem"
                >
                  <Plus class="size-3.5" aria-hidden="true" />
                  {{ problemSubmitting ? '保存中...' : '上报新问题' }}
                </button>
              </div>
            </section>
          </div>

          <section class="enterprise-panel rounded-2xl p-4">
            <div class="flex items-center gap-2">
              <CheckCircle2 class="size-4 text-slate-400" aria-hidden="true" />
              <span class="text-[13px] font-bold text-slate-950">完成通知回传</span>
              <span class="ml-auto text-[11px] text-slate-400">生产完成会写回工程啤办单状态和审核轨迹</span>
            </div>
            <div class="mt-3 grid gap-3 md:grid-cols-3">
              <div class="rounded-lg border border-slate-200 bg-slate-50 p-3">
                <p class="text-[11px] font-semibold text-slate-500">回传目标</p>
                <p class="mt-1 text-sm font-semibold text-slate-950">{{ selectedTask.order.id }} 工程啤办单</p>
                <p class="mt-0.5 text-[11px] text-slate-500">同一张单据，不复制生产数据</p>
              </div>
              <div class="rounded-lg border border-slate-200 bg-slate-50 p-3">
                <p class="text-[11px] font-semibold text-slate-500">完成状态</p>
                <p class="mt-1 text-sm font-semibold text-slate-950">{{ selectedTask.order.status === '已完成' ? '已回传' : '待回传' }}</p>
                <p class="mt-0.5 text-[11px] text-slate-500">{{ formatWorkflowDate(selectedTask.order.completed_date, '完成后写入日期') }}</p>
              </div>
              <div class="rounded-lg border border-slate-200 bg-slate-50 p-3">
                <p class="text-[11px] font-semibold text-slate-500">最近记录</p>
                <p class="mt-1 truncate text-sm font-semibold text-slate-950">{{ selectedTask.audit_logs[0]?.action || '暂无轨迹' }}</p>
                <p class="mt-0.5 text-[11px] text-slate-500">{{ formatWorkflowTime(selectedTask.audit_logs[0]?.created_at) }}</p>
              </div>
            </div>
          </section>
        </section>

        <section v-else class="rounded-xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-500">
          <p class="font-semibold text-slate-950">
            {{ apiState === 'error' ? '真实任务读取失败' : '暂无啤办生产任务单。' }}
          </p>
          <p class="mt-2">
            {{ apiState === 'error' ? '不会显示本地示例任务，请修复登录权限、接口或网络后刷新任务。' : '工程新建内部啤办单后，这里会先显示通知。' }}
          </p>
        </section>
      </div>

      <MoldingSampleTrialReportDialog
        :visible="trialReportDialogVisible"
        :order="selectedTask?.order ?? null"
        :items="selectedTask?.items ?? []"
        :reports="selectedTrialReports"
        :factory-short-name="activeFactory.shortName"
        :operator-name="currentProductionOperatorName"
        :can-save="canSaveSelectedTrialReport"
        :saving="trialReportSaving"
        :read-only="trialReportReadOnly || !canSaveSelectedTrialReport"
        :initial-item-id="trialReportInitialItemId"
        @close="closeTrialReportDialog"
        @save="saveTrialReport"
      />

      <Transition
        enter-active-class="transition duration-150 ease-out"
        enter-from-class="opacity-0"
        enter-to-class="opacity-100"
        leave-active-class="transition duration-150 ease-in"
        leave-from-class="opacity-100"
        leave-to-class="opacity-0"
      >
        <section
          v-if="taskPrintPreviewVisible && selectedTask"
          class="fixed inset-0 z-[60] bg-slate-950/45 px-4 py-5 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-label="工程啤办明细打印预览"
          data-testid="molding-sample-task-print-preview"
        >
          <div class="mx-auto flex h-full max-w-6xl flex-col overflow-hidden rounded-lg bg-white shadow-2xl shadow-slate-950/30">
            <header class="flex shrink-0 items-center gap-3 border-b border-slate-200 px-4 py-3">
              <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-teal-50 text-teal-700">
                <Printer class="size-4" aria-hidden="true" />
              </span>
              <div class="min-w-0">
                <div class="text-[15px] font-bold text-slate-950">啤办通知单 · 打印预览</div>
                <p class="mt-0.5 text-[12px] text-slate-500">工程审核通过后下发至啤机部 · {{ selectedTask.order.id }}</p>
              </div>
              <button
                type="button"
                class="ml-auto flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
                aria-label="关闭任务单打印预览"
                @click="closeTaskPrintPreview"
              >
                <X class="size-4" aria-hidden="true" />
              </button>
            </header>
            <div class="min-h-0 flex-1 overflow-y-auto bg-slate-100 p-4">
              <article class="mx-auto max-w-6xl rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                <div class="flex flex-wrap items-start justify-between gap-3 border-b-2 border-slate-900 pb-3">
                  <div>
                    <div class="text-[13px] font-bold uppercase tracking-[0.12em] text-teal-700">工程部下发 · 啤机部执行</div>
                    <div class="mt-1 text-[24px] font-bold text-slate-950">啤办通知单</div>
                    <div class="mt-1 text-[14px] text-slate-500">工程审核通过后下发；以下为工程单据填写详情。</div>
                  </div>
                  <div class="rounded-md bg-slate-900 px-3 py-2 text-right text-[14px] text-white">
                    <div class="font-mono font-bold">{{ selectedTask.order.id }}</div>
                    <div class="mt-0.5 text-slate-300">{{ selectedTask.order.status }} · {{ selectedTask.order.stage || '待填写' }}</div>
                  </div>
                </div>
                <div class="mt-3 grid gap-px overflow-hidden rounded-md border border-slate-200 bg-slate-200 text-[14px] leading-5 sm:grid-cols-3">
                  <div class="bg-white px-3 py-2"><span class="text-slate-400">产品编号</span><div class="font-semibold">{{ formatBlank(selectedTask.order.order_number) }}</div></div>
                  <div class="bg-white px-3 py-2"><span class="text-slate-400">产品 / 客户</span><div class="font-semibold">{{ formatBlank(selectedTask.order.product_name) }} / {{ formatBlank(selectedTask.order.client_name) }}</div></div>
                  <div class="bg-white px-3 py-2"><span class="text-slate-400">阶段 / 类型</span><div class="font-semibold">{{ formatBlank(selectedTask.order.stage) }} / {{ formatBlank(selectedTask.order.order_type) }}</div></div>
                  <div class="bg-white px-3 py-2"><span class="text-slate-400">填写部 / 发至</span><div class="font-semibold">工程部 / {{ formatBlank(selectedTask.order.send_to) }}</div></div>
                  <div class="bg-white px-3 py-2"><span class="text-slate-400">工程 / 审核主管</span><div class="font-semibold">{{ formatBlank(selectedTask.order.eng_name) }} / {{ formatBlank(selectedTask.order.supervisor) }}</div></div>
                  <div class="bg-white px-3 py-2"><span class="text-slate-400">业务开单日期</span><div class="font-semibold">{{ formatWorkflowDate(selectedTask.order.date) }}</div></div>
                </div>
                <div class="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[14px] leading-5 text-amber-900"><span class="mr-2 font-semibold text-amber-700">注意事项 / 开单事由</span>{{ formatBlank(selectedTask.order.reason) }}</div>
                <div class="mt-4 flex items-center justify-between border-b border-slate-200 pb-2"><div class="text-[18px] font-bold text-slate-950">工程模具明细</div><div class="text-[13px] text-slate-400">共 {{ printableEngineeringItems.length }} 项 · 不含啤机回填及费用</div></div>
                <div class="mt-2 overflow-x-auto">
                  <table class="min-w-[720px] w-full border-collapse text-left text-[14px] leading-5">
                    <thead><tr class="border-y border-slate-200 bg-slate-50 text-[13px] text-slate-500"><th class="w-10 px-2 py-2">#</th><th class="w-[24%] px-2 py-2">模具信息</th><th class="w-[18%] px-2 py-2">工程时点</th><th class="w-[24%] px-2 py-2">用料与颜色</th><th class="w-[14%] px-2 py-2 text-right">数量 / 需料</th><th class="px-2 py-2">工程备注</th></tr></thead>
                    <tbody class="divide-y divide-slate-100"><tr v-for="item in printableEngineeringItems" :key="`preview-${item.id}`"><td class="px-2 py-2 align-top text-slate-400">{{ item.sort_order }}</td><td class="px-2 py-2 align-top"><div class="font-semibold text-slate-900">{{ formatBlank(item.mold_id) }} · {{ formatBlank(item.mold_name) }}</div><div class="mt-0.5 text-[13px] text-slate-500">工模尺寸：{{ formatBlank(item.mold_dimensions) }}</div></td><td class="px-2 py-2 align-top text-[13px] text-slate-600"><div>{{ formatMoldPresenceStatus(item.mold_presence_status) }}</div><div class="mt-0.5">回模：{{ formatWorkflowDate(item.mold_return_time) }}</div><div class="mt-0.5">需办：{{ formatWorkflowDate(item.completion_time) }}</div></td><td class="px-2 py-2 align-top"><div class="font-semibold text-slate-900">{{ formatBlank(formatMaterialComposition(resolveMaterialComponents(item))) }}</div><div class="mt-1 text-[12px] font-semibold" :class="item.material_usage_type === 'trial' ? 'text-amber-700' : 'text-emerald-700'">{{ item.material_usage_type === 'trial' ? '试料 · 不计结余' : '正式生产' }}</div><div class="mt-0.5 text-[13px] text-slate-600">{{ formatBlank(item.color) }} / {{ formatBlank(item.pigment_no) }}</div></td><td class="px-2 py-2 align-top text-right"><div class="text-[13px] text-slate-600">{{ formatBlank(item.quantity) }} · {{ formatBlank(item.shoot_qty) }} 啤</div><div class="mt-0.5 font-bold tabular-nums text-slate-900">{{ formatWeight(item.required_material_kg) }}</div></td><td class="px-2 py-2 align-top text-slate-600">{{ formatBlank(item.notes) }}</td></tr></tbody>
                  </table>
                </div>
              </article>
            </div>
            <footer class="flex shrink-0 justify-end gap-2 border-t border-slate-200 px-4 py-3">
              <button type="button" class="h-8 rounded-md border border-slate-200 px-3 text-[12px] font-semibold text-slate-600 transition hover:border-slate-300" @click="closeTaskPrintPreview">关闭</button>
              <button type="button" class="inline-flex h-8 items-center gap-1.5 rounded-md bg-slate-900 px-3 text-[12px] font-semibold text-white transition hover:bg-slate-800" @click="confirmTaskPrint"><Printer class="size-3.5" aria-hidden="true" />确认打印</button>
            </footer>
          </div>
        </section>
      </Transition>

    </div>
  </main>

  <section class="molding-sample-task-print-root hidden" data-testid="molding-sample-task-print-area" aria-label="工程啤办通知单打印内容">
    <article v-if="selectedTask" class="molding-sample-task-print-page" :class="taskPrintDensityClass">
      <header class="molding-sample-task-print-header"><div><div class="molding-sample-task-print-label">工程部下发 · 啤机部执行</div><div class="molding-sample-task-print-title">啤办通知单</div><div class="molding-sample-task-print-subtitle">Engineering Molding Sample Work Notice</div></div><div class="molding-sample-task-print-id"><strong>{{ selectedTask.order.id }}</strong><span>{{ selectedTask.order.status }} · {{ selectedTask.order.stage || '待填写' }}</span></div></header>
      <section class="molding-sample-task-print-meta"><div><span>产品编号</span><strong>{{ formatBlank(selectedTask.order.order_number) }}</strong></div><div><span>产品 / 客户</span><strong>{{ formatBlank(selectedTask.order.product_name) }} / {{ formatBlank(selectedTask.order.client_name) }}</strong></div><div><span>阶段 / 类型</span><strong>{{ formatBlank(selectedTask.order.stage) }} / {{ formatBlank(selectedTask.order.order_type) }}</strong></div><div><span>填写部 / 发至</span><strong>工程部 / {{ formatBlank(selectedTask.order.send_to) }}</strong></div><div><span>工程 / 审核主管</span><strong>{{ formatBlank(selectedTask.order.eng_name) }} / {{ formatBlank(selectedTask.order.supervisor) }}</strong></div><div><span>业务开单日期</span><strong>{{ formatWorkflowDate(selectedTask.order.date) }}</strong></div></section>
      <section class="molding-sample-task-print-reason"><span>注意事项 / 开单事由</span><strong>{{ formatBlank(selectedTask.order.reason) }}</strong></section>
      <section class="molding-sample-task-print-section-heading"><strong>工程模具明细</strong><span>共 {{ printableEngineeringItems.length }} 项 · 不含啤机回填及费用</span></section>
      <table class="molding-sample-task-print-table"><colgroup><col class="molding-sample-task-print-index"><col class="molding-sample-task-print-mold"><col class="molding-sample-task-print-timing"><col class="molding-sample-task-print-material"><col class="molding-sample-task-print-quantity"><col class="molding-sample-task-print-notes"></colgroup><thead><tr><th>#</th><th>模具信息</th><th>工程时点</th><th>用料与颜色</th><th>数量 / 需料</th><th>工程备注</th></tr></thead><tbody><tr v-for="item in printableEngineeringItems" :key="`print-${item.id}`"><td>{{ item.sort_order }}</td><td><strong>{{ formatBlank(item.mold_id) }} · {{ formatBlank(item.mold_name) }}</strong><span>工模尺寸：{{ formatBlank(item.mold_dimensions) }}</span></td><td>{{ formatMoldPresenceStatus(item.mold_presence_status) }}<span>回模：{{ formatWorkflowDate(item.mold_return_time) }}</span><span>需办：{{ formatWorkflowDate(item.completion_time) }}</span></td><td><strong>{{ formatBlank(formatMaterialComposition(resolveMaterialComponents(item))) }}</strong><span class="molding-sample-task-print-usage" :class="{ 'is-trial': item.material_usage_type === 'trial' }">{{ item.material_usage_type === 'trial' ? '试料 · 不计结余' : '正式生产' }}</span><span>{{ formatBlank(item.color) }} / {{ formatBlank(item.pigment_no) }}</span></td><td class="molding-sample-task-print-quantity-value">{{ formatBlank(item.quantity) }} · {{ formatBlank(item.shoot_qty) }} 啤<strong>{{ formatWeight(item.required_material_kg) }}</strong></td><td>{{ formatBlank(item.notes) }}</td></tr></tbody></table>
    </article>
  </section>
</template>

<style>
.production-task-page :where(button, a, input, textarea, select):focus-visible {
  outline: 2px solid rgb(13 148 136 / 42%);
  outline-offset: 2px;
}

.production-loading-bar {
  animation: production-loading 1.1s ease-in-out infinite;
}

@keyframes production-loading {
  0% { transform: translateX(-105%); }
  50% { transform: translateX(105%); }
  100% { transform: translateX(305%); }
}

.production-fillback-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 25rem), 1fr));
  gap: .75rem;
}

.production-full-item-master {
  display: grid;
  gap: .75rem;
}

.production-full-item-index-options {
  display: flex;
  gap: .5rem;
  overflow-x: auto;
  padding-bottom: .25rem;
  scrollbar-gutter: stable;
}

@media (min-width: 768px) {
  .production-fillback-scroll {
    max-height: min(72vh, 52rem);
    overflow-y: auto;
    overscroll-behavior-y: auto;
    scrollbar-gutter: stable;
  }
}

@media (min-width: 1024px) {
  .production-full-item-master {
    grid-template-columns: 14rem minmax(0, 1fr);
    height: min(76vh, 52rem);
    overflow: clip;
  }

  .production-full-item-index,
  .production-full-item-pane {
    min-height: 0;
    overflow-y: auto;
    overscroll-behavior-y: auto;
    scrollbar-gutter: stable;
  }

  .production-full-item-index-options {
    display: grid;
    align-content: start;
    grid-auto-rows: max-content;
    overflow: visible;
    padding-bottom: 0;
  }
}

@media (min-width: 1280px) {
  .production-queue-list {
    max-height: calc(100vh - 18.5rem);
    overflow-y: auto;
    overscroll-behavior-y: auto;
    scrollbar-gutter: stable;
  }
}

@media (prefers-reduced-motion: reduce) {
  .production-task-page .interactive-surface,
  .production-task-page .reveal-grid > *,
  .production-task-page .animate-spin,
  .production-loading-bar {
    animation: none !important;
    transition: none !important;
    transform: none !important;
  }

  .production-loading-bar {
    width: 100%;
    opacity: .65;
  }
}

@media print {
  @page { size: A4 landscape; margin: 5mm; }
  html, body, body.molding-sample-task-printing #app { min-height: 0 !important; height: auto !important; max-width: none !important; margin: 0 !important; padding: 0 !important; overflow: visible !important; background: #fff !important; print-color-adjust: exact; -webkit-print-color-adjust: exact; }
  body.molding-sample-task-printing * { visibility: hidden; }
  body.molding-sample-task-printing #app > :not(.molding-sample-task-print-root) { display: none !important; }
  body.molding-sample-task-printing .molding-sample-task-print-root, body.molding-sample-task-printing .molding-sample-task-print-root * { visibility: visible; }
  body.molding-sample-task-printing #app > .molding-sample-task-print-root { display: block !important; position: static !important; inset: auto !important; box-sizing: border-box; width: calc(297mm - 10mm) !important; max-width: none !important; min-height: 0 !important; height: auto !important; margin: 0 !important; color: #0f172a; font-family: Arial, "Microsoft YaHei", sans-serif; font-size: 10pt; line-height: 1.35; break-after: auto; }
  .molding-sample-task-print-page { box-sizing: border-box; width: 100%; min-height: 0; height: auto; margin: 0; break-inside: auto; page-break-inside: auto; break-after: auto; }
  .molding-sample-task-print-header { display: flex; justify-content: space-between; gap: 20px; border-bottom: 2px solid #0f172a; padding-bottom: 8px; }
  .molding-sample-task-print-label { color: #0f766e; font-size: 9pt; font-weight: 700; letter-spacing: .12em; }
  .molding-sample-task-print-title { margin-top: 2px; font-size: 20pt; font-weight: 700; }
  .molding-sample-task-print-subtitle { margin-top: 2px; color: #64748b; font-size: 8.5pt; letter-spacing: .08em; }
  .molding-sample-task-print-id { min-width: 178px; padding: 8px 10px; align-self: flex-start; background: #0f172a; color: #fff; text-align: right; font-size: 10pt; }
  .molding-sample-task-print-id strong { display: block; font-size: 11pt; }
  .molding-sample-task-print-id span { display: block; margin-top: 3px; color: #cbd5e1; }
  .molding-sample-task-print-meta { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; margin: 10px 0; border: 1px solid #cbd5e1; background: #cbd5e1; font-size: 10pt; }
  .molding-sample-task-print-meta div { display: grid; grid-template-columns: 82px minmax(0, 1fr); gap: 6px; min-height: 28px; padding: 6px 7px; background: #fff; }
  .molding-sample-task-print-meta span { color: #64748b; }
  .molding-sample-task-print-reason { display: grid; grid-template-columns: 138px minmax(0, 1fr); gap: 8px; margin: 0 0 10px; padding: 7px 9px; background: #fffbeb; border: 1px solid #fde68a; font-size: 10pt; }
  .molding-sample-task-print-reason span { color: #92400e; font-weight: 700; }
  .molding-sample-task-print-section-heading { display: flex; align-items: center; justify-content: space-between; padding-bottom: 6px; border-bottom: 1px solid #94a3b8; font-size: 11pt; }
  .molding-sample-task-print-section-heading span { color: #64748b; font-size: 9pt; }
  .molding-sample-task-print-table { width: 100%; margin-top: 7px; border-collapse: collapse; table-layout: fixed; font-size: 10pt; line-height: 1.35; }
  .molding-sample-task-print-index { width: 3%; }
  .molding-sample-task-print-mold { width: 25%; }
  .molding-sample-task-print-timing { width: 17%; }
  .molding-sample-task-print-material { width: 27%; }
  .molding-sample-task-print-quantity { width: 12%; }
  .molding-sample-task-print-notes { width: 16%; }
  .molding-sample-task-print-table th, .molding-sample-task-print-table td { border: 1px solid #cbd5e1; padding: 6px 7px; vertical-align: top; overflow-wrap: anywhere; }
  .molding-sample-task-print-table th { background: #f1f5f9; color: #334155; text-align: left; font-size: 9.5pt; }
  .molding-sample-task-print-table td > span { display: block; margin-top: 3px; color: #64748b; font-size: 9pt; font-weight: 400; }
  .molding-sample-task-print-table .molding-sample-task-print-usage { color: #047857; font-weight: 700; }
  .molding-sample-task-print-table .molding-sample-task-print-usage.is-trial { color: #b45309; }
  .molding-sample-task-print-quantity-value { text-align: right; }
  .molding-sample-task-print-quantity-value strong { display: block; margin-top: 3px; font-size: 10pt; }
  .molding-sample-task-print-table thead { display: table-header-group; }
  .molding-sample-task-print-table tr { break-inside: avoid-page; page-break-inside: avoid; }
  .molding-sample-task-print-page.is-compact .molding-sample-task-print-meta { margin: 7px 0; }
  .molding-sample-task-print-page.is-compact .molding-sample-task-print-meta div { min-height: 21px; padding: 4px 5px; }
  .molding-sample-task-print-page.is-compact .molding-sample-task-print-reason { margin-bottom: 7px; padding: 5px 6px; }
  .molding-sample-task-print-page.is-compact .molding-sample-task-print-table { margin-top: 4px; font-size: 9.25pt; }
  .molding-sample-task-print-page.is-compact .molding-sample-task-print-table th, .molding-sample-task-print-page.is-compact .molding-sample-task-print-table td { padding: 4px 5px; }
  .molding-sample-task-print-page.is-compact .molding-sample-task-print-table td > span { font-size: 8.5pt; }
  .molding-sample-task-print-page.is-dense .molding-sample-task-print-header { padding-bottom: 5px; }
  .molding-sample-task-print-page.is-dense .molding-sample-task-print-title { font-size: 17pt; }
  .molding-sample-task-print-page.is-dense .molding-sample-task-print-id { padding: 6px 8px; }
  .molding-sample-task-print-page.is-dense .molding-sample-task-print-meta { margin: 5px 0; font-size: 8.5pt; }
  .molding-sample-task-print-page.is-dense .molding-sample-task-print-meta div { min-height: 19px; padding: 3px 4px; }
  .molding-sample-task-print-page.is-dense .molding-sample-task-print-reason { margin-bottom: 5px; padding: 4px 5px; font-size: 8.5pt; }
  .molding-sample-task-print-page.is-dense .molding-sample-task-print-table { margin-top: 3px; font-size: 8.5pt; }
  .molding-sample-task-print-page.is-dense .molding-sample-task-print-table th, .molding-sample-task-print-page.is-dense .molding-sample-task-print-table td { padding: 3px 4px; }
  .molding-sample-task-print-page.is-dense .molding-sample-task-print-table td > span { font-size: 8pt; }
}
</style>
