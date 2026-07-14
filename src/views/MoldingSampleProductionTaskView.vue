<script setup lang="ts">
import { computed, onMounted, ref, watch, watchEffect } from 'vue'
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
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
  Send,
  ShieldAlert,
  Table2,
  X,
} from '@lucide/vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import {
  factoryContexts,
  isProductionFactoryContextId,
  type ProductionFactoryContextId,
  type Tone,
} from '@/data/enterpriseMock'
import {
  applyCostPreviewToItems,
  buildCompletionGate,
  buildMoldingSampleReportSummary,
  isExternalMoldingSampleOrder,
  type MoldingSampleMaterialPrice,
  type MoldingSampleReportItemRow,
  type MoldingSampleReportSummary,
} from '@/lib/moldingSampleBusiness'
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
  MoldingSampleStatus,
  MoldingSampleWorkflowRecord,
} from '@/types/moldingSample'
import StatusPill from '@/components/common/StatusPill.vue'
import AccountMenu from '@/components/layout/AccountMenu.vue'
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

const today = '2026-07-03'
const PRODUCTION_NOTIFICATION_MODULE = 'production_molding_sample_task'
const PRODUCTION_TASK_PAGE_SIZE = 10
const apiRecords = ref<MoldingSampleDetailResponse[]>([])
const apiNotifications = ref<MoldingSampleNotificationResponse[]>([])
const apiState = ref<'checking' | 'connected' | 'empty' | 'error'>('checking')
const actionMessage = ref('正在读取啤办生产任务...')
const selectedOrderId = ref('')
const queueFilter = ref<ProductionQueueFilter>('全部')
const queueDisplayMode = ref<ProductionTaskDisplayMode>('board')
const queuePage = ref(1)
const productionProblem = ref('')
const problemSubmitting = ref(false)
const notificationUpdating = ref(false)
const itemDrafts = ref<Record<string, ItemFillbackDraft>>({})
const localItemOverrides = ref<Record<string, Record<string, Partial<MoldingSampleItem>>>>({})
const isSelectedTaskDataExpanded = ref(false)
const taskPrintPreviewVisible = ref(false)
const protectedMaterialPrices = ref<MoldingSampleMaterialPrice[]>([])
const protectedRmbToHkdRate = ref<number | null>(null)

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

function isWildcardMoldingAdministrator() {
  return authStore.grants.some((grant) =>
    (grant.role_code === 'admin' || grant.role_id === 'admin')
    && grant.factory_id === '*'
    && ['*', 'system'].includes(grant.department),
  )
}

function isLocalProductionFactory(factoryId: string) {
  if (isWildcardMoldingAdministrator() || authStore.authzMode !== 'enforce') {
    return true
  }

  const primaryFactoryId = authStore.currentUser?.profile?.primary_factory_id?.trim()
  if (primaryFactoryId) {
    return primaryFactoryId === factoryId
  }

  return authStore.grants.some((grant) => grant.factory_id === factoryId)
}

function canProductionPermission(permission: string, factoryId: string) {
  return isLocalProductionFactory(factoryId)
    && ['production', 'molding'].some((department) =>
      authStore.can(permission, factoryId, department),
    )
}

const canReadSelectedFactory = computed(() =>
  canProductionPermission('molding_sample:production_read', selectedFactoryId.value),
)
const canReadSelectedNotifications = computed(() =>
  canProductionPermission('molding_sample:notification_read', selectedFactoryId.value),
)

const notificationOrderIds = computed(() =>
  new Set(apiNotifications.value.map((notification) => notification.order_id)),
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
    }))
    .filter((record) =>
      !canReadSelectedNotifications.value || notificationOrderIds.value.has(record.order.id),
    )
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
  .filter((record) => ['待审核', '待经理审核', '待生产', '生产中', '已完成'].includes(record.order.status))
  .sort((left, right) => getTaskPriority(left.order.status) - getTaskPriority(right.order.status)),
)

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
  canProductionPermission('molding_sample:notification_read', selectedTaskFactoryId.value),
)
const isSelectedFactoryReadOnly = computed(() => ![
  'molding_sample:production_start',
  'molding_sample:production_fillback',
  'molding_sample:production_complete',
  'molding_sample:notification_read',
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

// The printed handoff is issued when molding first receives the engineering order.
// Keep it tied to the original engineering rows instead of unsaved production fillback.
const printableEngineeringItems = computed<MoldingSampleItem[]>(() => selectedTask.value?.items ?? [])
const canPrintSelectedTask = computed(() =>
  Boolean(
    selectedTask.value
    && printableEngineeringItems.value.length
    && ['待生产', '生产中', '已完成'].includes(selectedTask.value.order.status),
  ),
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

const filteredTaskEntries = computed(() => taskEntries.value.filter((entry) => {
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

  return buildMoldingSampleReportSummary(selectedTask.value.order, selectedPreviewItems.value)
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
    return `完成日期：${order.completed_date || order.updated_at || '已回传'}`
  }

  return '当前任务不可执行'
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

function formatBlank(value: string | number | null | undefined, fallback = '待填写') {
  return value === null || value === undefined || value === '' ? fallback : String(value)
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
  window.print()
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
    .sort((left, right) => right.created_at.localeCompare(left.created_at))
}

function replaceApiNotification(notification: MoldingSampleNotificationResponse) {
  apiNotifications.value = [
    notification,
    ...apiNotifications.value.filter((entry) => entry.id !== notification.id),
  ].sort((left, right) => right.created_at.localeCompare(left.created_at))
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
  protectedMaterialPrices.value = []
  protectedRmbToHkdRate.value = null

  try {
    const response = await moldingSampleApi.getMaterialPrices(factoryId)
    if (factoryId !== selectedFactoryId.value) {
      return
    }

    protectedMaterialPrices.value = response.prices
    protectedRmbToHkdRate.value = response.rmb_to_hkd_rate
  }
  catch {
    if (factoryId !== selectedFactoryId.value) {
      return
    }

    protectedMaterialPrices.value = []
    protectedRmbToHkdRate.value = null
  }
}

async function loadApiData() {
  const requestedFactoryId = selectedFactoryId.value
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
    if (requestedFactoryId !== selectedFactoryId.value) {
      return
    }

    apiRecords.value = orders
    apiNotifications.value = notifications
    const formalTaskCount = orders.filter((record) =>
      record.order.factory_id === requestedFactoryId
      && (
        !canProductionPermission('molding_sample:notification_read', requestedFactoryId)
        || notificationOrderIds.value.has(record.order.id)
      )
      && !isExternalMoldingSampleOrder(record.order),
    ).length
    apiState.value = formalTaskCount ? 'connected' : 'empty'
    actionMessage.value = canProductionPermission('molding_sample:notification_read', requestedFactoryId)
      ? formalTaskCount
        ? `已从独立通知表同步 ${notifications.length} 条生产通知。`
        : '当前独立通知表没有待生产任务通知。'
      : formalTaskCount
        ? `已读取 ${formalTaskCount} 张正式啤办生产任务；当前账号没有通知处理权限。`
        : '当前厂区暂无正式啤办生产任务。'
  }
  catch (error) {
    if (requestedFactoryId !== selectedFactoryId.value) {
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
      today,
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
}, { immediate: true })

watch([queueFilter, selectedFactoryId], () => {
  queuePage.value = 1
})

watch(selectedFactoryId, (factoryId, previousFactoryId) => {
  if (previousFactoryId === undefined || factoryId === previousFactoryId) {
    return
  }

  void loadApiData()
  void loadProtectedMaterialPrices(factoryId)
})

watchEffect(() => {
  appStore.setActiveFactory(selectedFactoryId.value)
})
</script>

<template>
  <main class="min-h-screen bg-slate-100 px-4 pb-6 pt-16 text-[13px] leading-relaxed text-slate-900 sm:px-6 xl:px-10">
    <div class="mx-auto max-w-[1720px] space-y-4">
      <RouterLink
        to="/modules/production"
        class="fixed left-4 top-4 z-50 inline-flex h-9 items-center gap-2 rounded-full border border-slate-200 bg-white/95 px-3 text-sm font-semibold text-slate-600 shadow-sm backdrop-blur transition hover:border-slate-300 hover:text-slate-950 sm:left-6 xl:left-10"
      >
        <ArrowLeft class="size-4" aria-hidden="true" />
        生产部模块
      </RouterLink>

      <div class="flex flex-wrap items-center gap-2 text-xs text-slate-400">
        <RouterLink to="/modules/production" class="font-medium hover:text-slate-900">
          生产部模块
        </RouterLink>
        <ChevronRight class="size-3.5" aria-hidden="true" />
        <span class="font-semibold text-slate-700">
          生产任务单 · {{ selectedTask?.order.id || '未选择' }}
        </span>
        <div class="fixed right-4 top-4 z-50 flex items-center gap-2 rounded-full border border-slate-200 bg-white/95 px-2 py-1 shadow-sm backdrop-blur sm:right-6 xl:right-10">
          <span class="hidden font-medium text-slate-500 lg:inline">
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
        <span>当前厂区为只读，仅可查看数据</span>
      </section>

      <section class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div class="min-w-0">
            <p class="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">MOLDING SAMPLE PRODUCTION TASK</p>
            <h1 class="mt-1 text-2xl font-bold tracking-tight text-slate-950">啤机部生产任务单</h1>
            <p class="mt-1 max-w-4xl text-sm text-slate-600">
              啤办生产任务单用于接收工程啤办单通知，啤机部在这里开始执行、回填实际用料，完成后把状态回传到同一张工程啤办单。
            </p>
            <p class="mt-1 text-xs text-slate-500">
              任务通知队列来自独立通知表，主管审核通过后进入通知区；啤机部只处理生产执行字段，工程资料回到工程啤办单维护。
            </p>
          </div>

          <div class="flex flex-wrap gap-2">
            <RouterLink
              :to="engineeringOrderRoute"
              class="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-slate-300 hover:text-slate-950"
            >
              <Send class="size-4" aria-hidden="true" />
              工程啤办单
            </RouterLink>
            <button
              type="button"
              class="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-950 bg-slate-950 px-4 text-sm font-semibold text-white transition hover:bg-slate-800"
              @click="loadApiData"
            >
              <RotateCcw class="size-4" aria-hidden="true" />
              刷新任务
            </button>
          </div>
        </div>
      </section>

      <div class="grid min-w-0 gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
        <aside class="min-w-0 space-y-3 xl:sticky xl:top-20 xl:self-start" aria-label="啤办生产任务队列">
          <section class="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
            <div class="flex items-center justify-between gap-3">
              <div>
                <h2 class="text-[13px] font-bold text-slate-950">我的生产队列</h2>
                <p class="mt-0.5 text-[11px] text-slate-400">独立通知表 · {{ activeFactory.shortName }}</p>
              </div>
              <span class="rounded-full bg-teal-100 px-2 py-0.5 text-[11px] font-bold text-teal-700">{{ taskEntries.length }}</span>
            </div>
            <div class="mt-2 flex flex-wrap gap-1 text-[11px]">
              <button
                v-for="filter in queueFilters"
                :key="filter"
                type="button"
                class="rounded-md px-2 py-0.5 font-semibold transition"
                :class="queueFilter === filter ? 'bg-slate-900 text-white' : 'text-slate-500 hover:bg-slate-100 hover:text-slate-900'"
                @click="queueFilter = filter"
              >
                {{ filter }} {{ getQueueFilterCount(filter) }}
              </button>
            </div>
            <div class="mt-3 flex rounded-lg border border-slate-200 bg-slate-50 p-1 text-[11px] font-semibold">
              <button
                type="button"
                class="flex h-7 flex-1 items-center justify-center gap-1.5 rounded-md transition"
                :class="queueDisplayMode === 'board' ? 'bg-slate-900 text-white shadow-sm' : 'text-slate-500 hover:bg-white hover:text-slate-900'"
                @click="setQueueDisplayMode('board')"
              >
                <LayoutDashboard class="size-3.5" aria-hidden="true" />
                看板
              </button>
              <button
                type="button"
                class="flex h-7 flex-1 items-center justify-center gap-1.5 rounded-md transition"
                :class="queueDisplayMode === 'list' ? 'bg-slate-900 text-white shadow-sm' : 'text-slate-500 hover:bg-white hover:text-slate-900'"
                @click="setQueueDisplayMode('list')"
              >
                <Table2 class="size-3.5" aria-hidden="true" />
                列表
              </button>
            </div>
          </section>

          <div v-if="filteredTaskEntries.length" class="space-y-2">
            <div v-if="queueDisplayMode === 'board'" class="space-y-2">
              <button
                v-for="entry in paginatedFilteredTaskEntries"
                :key="entry.order.id"
                type="button"
                class="w-full rounded-lg border bg-white p-2.5 text-left shadow-sm transition hover:border-indigo-300 hover:bg-slate-50"
                :class="selectedTask?.order.id === entry.order.id ? 'border-2 border-teal-300 bg-teal-50/60' : 'border-slate-200'"
                @click="selectTask(entry.order.id, entry.factory_id)"
              >
                <div class="flex items-start justify-between gap-2">
                  <span class="font-mono text-[12px] font-bold text-slate-800">{{ entry.order.id }}</span>
                  <StatusPill :label="getQueueStatusLabel(entry.order.status)" :tone="statusTones[entry.order.status]" compact />
                </div>
                <p class="mt-0.5 truncate text-[12px] font-semibold text-slate-950">{{ entry.order.product_name }}</p>
                <p class="truncate text-[11px] text-slate-400">
                  {{ entry.order.client_name }} · {{ entry.items.length }} 项 · 交期 {{ entry.items[0]?.completion_time || entry.order.date }}
                </p>
                <p class="mt-1 truncate text-[10px] font-semibold text-blue-700">独立通知表 · {{ getNotificationMeta(entry.order.id) }}</p>
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
                class="grid w-full grid-cols-[112px_minmax(0,1fr)_64px] gap-2 border-b border-slate-100 px-3 py-2 text-left text-[12px] transition last:border-b-0 hover:bg-slate-50"
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

            <div class="flex items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-[11px] text-slate-500 shadow-sm">
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
            当前筛选下没有内部啤机生产任务。
          </div>
        </aside>

        <section v-if="selectedTask" class="min-w-0 space-y-4">
          <section class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
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
                  class="mt-3 flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2"
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
                      {{ selectedNotification.title }} · {{ selectedNotification.created_at }}
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
                    class="h-7 rounded-md bg-slate-900 px-2 text-[11px] font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
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
              <div class="rounded-lg bg-slate-900 px-3 py-2 text-right text-white">
                <div class="text-[11px] text-slate-400">实际料费(HKD)</div>
                <div class="text-lg font-bold tabular-nums">{{ formatCurrency(selectedReportSummary?.total_material_cost, '$ 0.00') }}</div>
              </div>
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

          <section class="min-w-0 rounded-xl border border-slate-200 bg-white shadow-sm">
            <div class="flex flex-wrap items-center gap-2 border-b border-slate-100 px-4 py-2.5">
              <PencilRuler class="size-4 text-slate-400" aria-hidden="true" />
              <span class="text-[13px] font-bold text-slate-950">啤机回填明细 · 实际用料回填</span>
              <span class="ml-auto text-[11px] text-slate-400">单价按原料表</span>
              <button
                type="button"
                class="inline-flex h-7 items-center rounded-md border border-slate-200 bg-white px-2 text-[11px] font-semibold text-slate-600 transition hover:border-slate-300 hover:text-slate-950"
                @click="isSelectedTaskDataExpanded = !isSelectedTaskDataExpanded"
              >
                {{ isSelectedTaskDataExpanded ? '收起完整数据' : '展开完整数据' }}
              </button>
            </div>
            <div class="overflow-x-auto">
              <table class="w-full min-w-[860px] text-[12px]">
                <thead>
                  <tr class="border-b border-slate-100 bg-slate-50 text-[11px] text-slate-500">
                    <th class="px-2 py-2 text-left font-medium">模具 / 原料</th>
                    <th class="px-2 py-2 text-right font-medium">领料(kg)</th>
                    <th class="px-2 py-2 text-right font-medium">实际用料(kg)</th>
                    <th class="px-2 py-2 text-right font-medium">料费(HKD)</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-50">
                  <tr
                    v-for="item in activeItems"
                    :key="item.id"
                    class="hover:bg-slate-50/60"
                    :class="Number(item.actual_weight_kg) > 0 ? '' : 'bg-red-50/40 hover:bg-red-50'"
                  >
                    <td class="px-2 py-2">
                      <div class="flex items-center gap-1">
                        <span class="font-mono text-[11px]">{{ item.mold_id }}</span>
                        <AlertTriangle
                          v-if="!(Number(item.actual_weight_kg) > 0)"
                          class="size-3 text-red-500"
                          aria-hidden="true"
                        />
                      </div>
                      <div class="text-[12px] font-semibold text-slate-950">{{ item.mold_name }} · {{ item.material }}</div>
                      <div class="text-[10px]" :class="Number(item.actual_weight_kg) > 0 ? 'text-slate-400' : 'text-red-500'">
                        {{ item.notes || item.color || '待啤机部补实际用料' }}
                      </div>
                    </td>
                    <td class="px-2 py-2 text-right tabular-nums text-slate-400">
                      {{ formatDecimal(item.collected_weight_kg ?? item.required_material_kg) }}
                    </td>
                    <td class="px-2 py-1 text-right">
                      <input
                        :value="itemDrafts[item.id]?.actual_weight_kg ?? ''"
                        :disabled="!canFillbackSelectedTask"
                        aria-label="实际用料"
                        type="number"
                        min="0"
                        step="0.01"
                        class="h-8 w-20 rounded-md px-2 text-right font-semibold tabular-nums outline-none disabled:bg-slate-50 disabled:text-slate-400"
                        :class="Number(item.actual_weight_kg) > 0 ? 'border border-emerald-200 bg-emerald-50 focus:border-emerald-400' : 'border-2 border-red-300 bg-white placeholder:text-red-300 focus:border-red-500'"
                        :placeholder="Number(item.actual_weight_kg) > 0 ? '' : '必填'"
                        @input="updateItemDraft(item.id, 'actual_weight_kg', readInputValue($event))"
                      >
                    </td>
                    <td class="px-2 py-2 text-right font-semibold tabular-nums" :class="getReportRow(item.id)?.actual_amount_hkd ? 'text-slate-900' : 'text-slate-300'">
                      {{ formatCurrency(getReportRow(item.id)?.actual_amount_hkd) }}
                    </td>
                  </tr>
                </tbody>
                <tfoot>
                  <tr class="border-t border-slate-200 bg-slate-50 text-[12px] font-bold">
                    <td class="px-2 py-2">
                      合计{{ selectedReportSummary?.archive_ready ? '' : '（待补齐）' }}
                    </td>
                    <td />
                    <td />
                    <td />
                    <td class="px-2 py-2 text-right tabular-nums">{{ formatCurrency(selectedReportSummary?.total_material_cost, '$ 0.00') }}</td>
                  </tr>
                </tfoot>
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
              <div v-if="isSelectedTaskDataExpanded" class="border-t border-slate-100 bg-slate-50/70 p-4">
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
                    <div class="text-[10px] font-semibold text-slate-400">开单 / 完成</div>
                    <div class="mt-0.5 font-semibold text-slate-900">{{ formatBlank(selectedTask.order.date) }} / {{ formatBlank(selectedTask.order.completed_date) }}</div>
                  </div>
                  <div class="rounded-lg border border-slate-200 bg-white px-3 py-2">
                    <div class="text-[10px] font-semibold text-slate-400">更新时间</div>
                    <div class="mt-0.5 font-semibold text-slate-900">{{ formatBlank(selectedTask.order.updated_at) }}</div>
                  </div>
                </div>

                <div class="mt-3 rounded-lg border border-slate-200 bg-white px-3 py-2">
                  <div class="text-[10px] font-semibold text-slate-400">注意事项 / 开单事由</div>
                  <p class="mt-1 text-[12px] leading-5 text-slate-700">{{ formatBlank(selectedTask.order.reason) }}</p>
                  <p v-if="selectedTask.order.reject_reason" class="mt-1 text-[12px] leading-5 text-red-600">
                    驳回原因：{{ selectedTask.order.reject_reason }}
                  </p>
                </div>

                <div class="mt-3 space-y-2">
                  <article
                    v-for="item in activeItems"
                    :key="`production-full-${item.id}`"
                    class="rounded-lg border border-slate-200 bg-white p-3"
                  >
                    <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
                      <div class="font-semibold text-slate-950">
                        {{ item.sort_order }}. {{ item.mold_id }} · {{ item.mold_name }}
                      </div>
                      <span
                        class="rounded-full border px-2 py-0.5 text-[10px] font-bold"
                        :class="Number(item.actual_weight_kg) > 0 ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-amber-200 bg-amber-50 text-amber-700'"
                      >
                        {{ Number(item.actual_weight_kg) > 0 ? '已回填' : '待回填' }}
                      </span>
                    </div>
                    <div class="grid gap-2 text-[12px] md:grid-cols-3 xl:grid-cols-4">
                      <div><span class="text-slate-400">原料</span><div class="font-semibold">{{ formatBlank(item.material) }}</div></div>
                      <div><span class="text-slate-400">颜色 / PMS</span><div class="font-semibold">{{ formatBlank(item.color) }} / {{ formatBlank(item.pigment_no) }}</div></div>
                      <div><span class="text-slate-400">数量 / 啤数</span><div class="font-semibold">{{ formatBlank(item.quantity) }} / {{ formatBlank(item.shoot_qty) }}</div></div>
                      <div><span class="text-slate-400">预计用料</span><div class="font-semibold">{{ formatWeight(item.required_material_kg) }}</div></div>
                      <div><span class="text-slate-400">回模 / 完成时间</span><div class="font-semibold">{{ formatBlank(item.mold_return_time) }} / {{ formatBlank(item.completion_time) }}</div></div>
                      <div><span class="text-slate-400">领料重量</span><div class="font-semibold">{{ formatWeight(item.collected_weight_kg) }}</div></div>
                      <div><span class="text-slate-400">实际用料</span><div class="font-semibold">{{ formatWeight(item.actual_weight_kg) }}</div></div>
                      <div><span class="text-slate-400">实际料费(HKD)</span><div class="font-semibold">{{ formatCurrency(getReportRow(item.id)?.actual_amount_hkd ?? item.actual_amount_hkd) }}</div></div>
                    </div>
                    <p class="mt-2 rounded-md bg-slate-50 px-2 py-1.5 text-[12px] leading-5 text-slate-600">
                      备注：{{ formatBlank(item.notes) }}
                    </p>
                  </article>
                </div>
              </div>
            </Transition>
          </section>

          <div class="grid gap-4 md:grid-cols-2">
            <section class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <div class="mb-2 flex items-center gap-2">
                <ListChecks class="size-4 text-slate-400" aria-hidden="true" />
                <span class="text-[13px] font-bold text-slate-950">生产操作</span>
              </div>
              <div class="space-y-2">
                <button
                  type="button"
                  :disabled="!canStartSelectedTask"
                  class="flex h-10 w-full items-center justify-center gap-2 rounded-lg text-[13px] font-semibold transition disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
                  :class="canStartSelectedTask ? 'bg-slate-950 text-white hover:bg-slate-800' : ''"
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

            <section class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
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
                  <div class="mt-0.5 text-red-400">{{ problem.reported_by }} · {{ problem.created_at }}</div>
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

          <section class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
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
                <p class="mt-0.5 text-[11px] text-slate-500">{{ selectedTask.order.completed_date || '完成后写入日期' }}</p>
              </div>
              <div class="rounded-lg border border-slate-200 bg-slate-50 p-3">
                <p class="text-[11px] font-semibold text-slate-500">最近记录</p>
                <p class="mt-1 truncate text-sm font-semibold text-slate-950">{{ selectedTask.audit_logs[0]?.action || '暂无轨迹' }}</p>
                <p class="mt-0.5 text-[11px] text-slate-500">{{ formatBlank(selectedTask.audit_logs[0]?.created_at, '待生成') }}</p>
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
                    <div class="text-[11px] font-bold uppercase tracking-[0.12em] text-teal-700">工程部下发 · 啤机部执行</div>
                    <div class="mt-1 text-xl font-bold text-slate-950">啤办通知单</div>
                    <div class="mt-1 text-[12px] text-slate-500">工程审核通过后下发；以下为工程单据填写详情。</div>
                  </div>
                  <div class="rounded-md bg-slate-900 px-3 py-2 text-right text-[12px] text-white">
                    <div class="font-mono font-bold">{{ selectedTask.order.id }}</div>
                    <div class="mt-0.5 text-slate-300">{{ selectedTask.order.status }} · {{ selectedTask.order.stage || '待填写' }}</div>
                  </div>
                </div>
                <div class="mt-3 grid gap-px overflow-hidden rounded-md border border-slate-200 bg-slate-200 text-[12px] sm:grid-cols-3">
                  <div class="bg-white px-3 py-2"><span class="text-slate-400">产品编号</span><div class="font-semibold">{{ formatBlank(selectedTask.order.order_number) }}</div></div>
                  <div class="bg-white px-3 py-2"><span class="text-slate-400">产品 / 客户</span><div class="font-semibold">{{ formatBlank(selectedTask.order.product_name) }} / {{ formatBlank(selectedTask.order.client_name) }}</div></div>
                  <div class="bg-white px-3 py-2"><span class="text-slate-400">阶段 / 类型</span><div class="font-semibold">{{ formatBlank(selectedTask.order.stage) }} / {{ formatBlank(selectedTask.order.order_type) }}</div></div>
                  <div class="bg-white px-3 py-2"><span class="text-slate-400">填写部 / 发至</span><div class="font-semibold">工程部 / {{ formatBlank(selectedTask.order.send_to) }}</div></div>
                  <div class="bg-white px-3 py-2"><span class="text-slate-400">工程 / 审核主管</span><div class="font-semibold">{{ formatBlank(selectedTask.order.eng_name) }} / {{ formatBlank(selectedTask.order.supervisor) }}</div></div>
                  <div class="bg-white px-3 py-2"><span class="text-slate-400">开单日期</span><div class="font-semibold">{{ formatBlank(selectedTask.order.date) }}</div></div>
                </div>
                <div class="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-900"><span class="mr-2 font-semibold text-amber-700">注意事项 / 开单事由</span>{{ formatBlank(selectedTask.order.reason) }}</div>
                <div class="mt-4 flex items-center justify-between border-b border-slate-200 pb-2"><div class="font-bold text-slate-950">工程模具明细</div><div class="text-[11px] text-slate-400">共 {{ printableEngineeringItems.length }} 项 · 不含啤机回填及费用</div></div>
                <div class="mt-2 overflow-x-auto">
                  <table class="min-w-[720px] w-full border-collapse text-left text-[12px]">
                    <thead><tr class="border-y border-slate-200 bg-slate-50 text-[11px] text-slate-500"><th class="w-10 px-2 py-2">#</th><th class="w-[24%] px-2 py-2">模具信息</th><th class="w-[18%] px-2 py-2">工程时点</th><th class="w-[24%] px-2 py-2">用料与颜色</th><th class="w-[14%] px-2 py-2 text-right">数量 / 需料</th><th class="px-2 py-2">工程备注</th></tr></thead>
                    <tbody class="divide-y divide-slate-100"><tr v-for="item in printableEngineeringItems" :key="`preview-${item.id}`"><td class="px-2 py-2 align-top text-slate-400">{{ item.sort_order }}</td><td class="px-2 py-2 align-top"><div class="font-semibold text-slate-900">{{ formatBlank(item.mold_id) }} · {{ formatBlank(item.mold_name) }}</div><div class="mt-0.5 text-[11px] text-slate-500">工模尺寸：{{ formatBlank(item.mold_dimensions) }}</div></td><td class="px-2 py-2 align-top text-[11px] text-slate-600"><div>{{ formatMoldPresenceStatus(item.mold_presence_status) }}</div><div class="mt-0.5">回模：{{ formatBlank(item.mold_return_time) }}</div><div class="mt-0.5">需办：{{ formatBlank(item.completion_time) }}</div></td><td class="px-2 py-2 align-top"><div class="font-semibold text-slate-900">{{ formatBlank(item.material) }}</div><div class="mt-0.5 text-[11px] text-slate-600">{{ formatBlank(item.color) }} / {{ formatBlank(item.pigment_no) }}</div></td><td class="px-2 py-2 align-top text-right"><div class="text-[11px] text-slate-600">{{ formatBlank(item.quantity) }} · {{ formatBlank(item.shoot_qty) }} 啤</div><div class="mt-0.5 font-bold tabular-nums text-slate-900">{{ formatWeight(item.required_material_kg) }}</div></td><td class="px-2 py-2 align-top text-slate-600">{{ formatBlank(item.notes) }}</td></tr></tbody>
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
    <article v-if="selectedTask" class="molding-sample-task-print-page" :class="{ 'is-dense': printableEngineeringItems.length > 6 }">
      <header class="molding-sample-task-print-header"><div><div class="molding-sample-task-print-label">工程部下发 · 啤机部执行</div><div class="molding-sample-task-print-title">啤办通知单</div><div class="molding-sample-task-print-subtitle">Engineering Molding Sample Work Notice</div></div><div class="molding-sample-task-print-id"><strong>{{ selectedTask.order.id }}</strong><span>{{ selectedTask.order.status }} · {{ selectedTask.order.stage || '待填写' }}</span></div></header>
      <section class="molding-sample-task-print-meta"><div><span>产品编号</span><strong>{{ formatBlank(selectedTask.order.order_number) }}</strong></div><div><span>产品 / 客户</span><strong>{{ formatBlank(selectedTask.order.product_name) }} / {{ formatBlank(selectedTask.order.client_name) }}</strong></div><div><span>阶段 / 类型</span><strong>{{ formatBlank(selectedTask.order.stage) }} / {{ formatBlank(selectedTask.order.order_type) }}</strong></div><div><span>填写部 / 发至</span><strong>工程部 / {{ formatBlank(selectedTask.order.send_to) }}</strong></div><div><span>工程 / 审核主管</span><strong>{{ formatBlank(selectedTask.order.eng_name) }} / {{ formatBlank(selectedTask.order.supervisor) }}</strong></div><div><span>开单日期</span><strong>{{ formatBlank(selectedTask.order.date) }}</strong></div></section>
      <section class="molding-sample-task-print-reason"><span>注意事项 / 开单事由</span><strong>{{ formatBlank(selectedTask.order.reason) }}</strong></section>
      <section class="molding-sample-task-print-section-heading"><strong>工程模具明细</strong><span>共 {{ printableEngineeringItems.length }} 项 · 不含啤机回填及费用</span></section>
      <table class="molding-sample-task-print-table"><colgroup><col class="molding-sample-task-print-index"><col class="molding-sample-task-print-mold"><col class="molding-sample-task-print-timing"><col class="molding-sample-task-print-material"><col class="molding-sample-task-print-quantity"><col class="molding-sample-task-print-notes"></colgroup><thead><tr><th>#</th><th>模具信息</th><th>工程时点</th><th>用料与颜色</th><th>数量 / 需料</th><th>工程备注</th></tr></thead><tbody><tr v-for="item in printableEngineeringItems" :key="`print-${item.id}`"><td>{{ item.sort_order }}</td><td><strong>{{ formatBlank(item.mold_id) }} · {{ formatBlank(item.mold_name) }}</strong><span>工模尺寸：{{ formatBlank(item.mold_dimensions) }}</span></td><td>{{ formatMoldPresenceStatus(item.mold_presence_status) }}<span>回模：{{ formatBlank(item.mold_return_time) }}</span><span>需办：{{ formatBlank(item.completion_time) }}</span></td><td><strong>{{ formatBlank(item.material) }}</strong><span>{{ formatBlank(item.color) }} / {{ formatBlank(item.pigment_no) }}</span></td><td class="molding-sample-task-print-quantity-value">{{ formatBlank(item.quantity) }} · {{ formatBlank(item.shoot_qty) }} 啤<strong>{{ formatWeight(item.required_material_kg) }}</strong></td><td>{{ formatBlank(item.notes) }}</td></tr></tbody></table>
      <footer class="molding-sample-task-print-footer"><span>工程单据填写详情 · 啤机部执行依据</span><span>本通知单不含实际用料、成本及其他啤机回填数据。</span></footer>
    </article>
  </section>
</template>

<style>
@media print {
  @page { size: A4 landscape; margin: 7mm; }
  html, body { min-height: 0 !important; margin: 0 !important; padding: 0 !important; overflow: visible !important; background: #fff !important; print-color-adjust: exact; -webkit-print-color-adjust: exact; }
  body * { visibility: hidden; }
  #app > main { display: none !important; }
  .molding-sample-task-print-root, .molding-sample-task-print-root * { visibility: visible; }
  #app > .molding-sample-task-print-root { display: block !important; position: static !important; inset: auto !important; box-sizing: border-box; width: 100% !important; min-height: 0 !important; margin: 0 !important; color: #0f172a; font-family: Arial, "Microsoft YaHei", sans-serif; break-after: avoid-page; }
  .molding-sample-task-print-page { box-sizing: border-box; width: 100%; min-height: 196mm; margin: 0; break-inside: avoid-page; page-break-inside: avoid; }
  .molding-sample-task-print-header { display: flex; justify-content: space-between; gap: 20px; border-bottom: 2px solid #0f172a; padding-bottom: 8px; }
  .molding-sample-task-print-label { color: #0f766e; font-size: 9px; font-weight: 700; letter-spacing: .12em; }
  .molding-sample-task-print-title { margin-top: 2px; font-size: 21px; font-weight: 700; }
  .molding-sample-task-print-subtitle { margin-top: 2px; color: #64748b; font-size: 8.5px; letter-spacing: .08em; }
  .molding-sample-task-print-id { min-width: 178px; padding: 8px 10px; align-self: flex-start; background: #0f172a; color: #fff; text-align: right; font-size: 10px; }
  .molding-sample-task-print-id strong { display: block; font-size: 12px; }
  .molding-sample-task-print-id span { display: block; margin-top: 3px; color: #cbd5e1; }
  .molding-sample-task-print-meta { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; margin: 10px 0; border: 1px solid #cbd5e1; background: #cbd5e1; font-size: 9px; }
  .molding-sample-task-print-meta div { display: grid; grid-template-columns: 68px minmax(0, 1fr); gap: 6px; min-height: 23px; padding: 5px 6px; background: #fff; }
  .molding-sample-task-print-meta span { color: #64748b; }
  .molding-sample-task-print-reason { display: grid; grid-template-columns: 112px minmax(0, 1fr); gap: 8px; margin: 0 0 10px; padding: 6px 8px; background: #fffbeb; border: 1px solid #fde68a; font-size: 9px; }
  .molding-sample-task-print-reason span { color: #92400e; font-weight: 700; }
  .molding-sample-task-print-section-heading { display: flex; align-items: center; justify-content: space-between; padding-bottom: 5px; border-bottom: 1px solid #94a3b8; font-size: 10px; }
  .molding-sample-task-print-section-heading span { color: #64748b; font-size: 8.5px; }
  .molding-sample-task-print-table { width: 100%; margin-top: 6px; border-collapse: collapse; table-layout: fixed; font-size: 8.5px; }
  .molding-sample-task-print-index { width: 4%; }
  .molding-sample-task-print-mold { width: 25%; }
  .molding-sample-task-print-timing { width: 18%; }
  .molding-sample-task-print-material { width: 23%; }
  .molding-sample-task-print-quantity { width: 13%; }
  .molding-sample-task-print-notes { width: 17%; }
  .molding-sample-task-print-table th, .molding-sample-task-print-table td { border: 1px solid #cbd5e1; padding: 4px 5px; vertical-align: top; overflow-wrap: anywhere; }
  .molding-sample-task-print-table th { background: #f1f5f9; color: #334155; text-align: left; font-size: 8px; }
  .molding-sample-task-print-table td > span { display: block; margin-top: 2px; color: #64748b; font-size: 8px; font-weight: 400; }
  .molding-sample-task-print-quantity-value { text-align: right; }
  .molding-sample-task-print-quantity-value strong { display: block; margin-top: 2px; font-size: 9px; }
  .molding-sample-task-print-table thead { display: table-header-group; }
  .molding-sample-task-print-table tr { break-inside: avoid; }
  .molding-sample-task-print-footer { display: flex; justify-content: space-between; gap: 16px; margin-top: 8px; padding-top: 5px; border-top: 1px solid #cbd5e1; color: #64748b; font-size: 8px; }
  .molding-sample-task-print-page.is-dense .molding-sample-task-print-meta { margin: 7px 0; }
  .molding-sample-task-print-page.is-dense .molding-sample-task-print-table { font-size: 7.5px; }
  .molding-sample-task-print-page.is-dense .molding-sample-task-print-table th, .molding-sample-task-print-page.is-dense .molding-sample-task-print-table td { padding: 3px 4px; }
  .molding-sample-task-print-page.is-dense .molding-sample-task-print-table td > span { font-size: 7px; }
}
</style>
