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
  RotateCcw,
  Save,
  Send,
  ShieldAlert,
  Table2,
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
  type MoldingSampleReportItemRow,
  type MoldingSampleReportSummary,
} from '@/lib/moldingSampleBusiness'
import {
  moldingSampleMaterialPrices,
  moldingSampleRmbToHkdRate,
} from '@/data/moldingSampleCostMock'
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

interface ItemFillbackDraft {
  actual_weight_kg: string
  injection_cost: string
  production_machine: string
}

type ProductionQueueFilter = '全部' | '待接单' | '生产中'
type ProductionTaskDisplayMode = 'board' | 'list'
type NotificationStatus = MoldingSampleNotificationResponse['status']

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
  if (!apiRecords.value.length || !apiNotifications.value.length) {
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
    .filter((record) => notificationOrderIds.value.has(record.order.id))
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
      injection_cost: parseOptionalNumber(draft.injection_cost),
      production_machine: draft.production_machine.trim(),
    }
  })
})

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

  return applyCostPreviewToItems(
    activeItems.value,
    moldingSampleMaterialPrices,
    moldingSampleRmbToHkdRate,
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

const canStartSelectedTask = computed(() => selectedTask.value?.order.status === '待生产')
const canFillbackSelectedTask = computed(() => selectedTask.value?.order.status === '生产中')
const canCompleteSelectedTask = computed(() => canFillbackSelectedTask.value && completionGate.value.can_complete)
const canMarkSelectedNotificationRead = computed(() =>
  selectedNotification.value?.status === '未读',
)
const canMarkSelectedNotificationHandled = computed(() =>
  Boolean(selectedNotification.value && selectedNotification.value.status !== '已处理'),
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

function formatGram(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) {
    return '待填写'
  }

  return `${Number(value).toFixed(2)} g`
}

function formatWeight(value: number | null | undefined) {
  const formatted = formatDecimal(value, '待填写')
  return formatted === '待填写' ? formatted : `${formatted} kg`
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
    injection_cost: item.injection_cost,
    production_machine: item.production_machine,
  }))
}

function syncItemDrafts() {
  if (!selectedTask.value) {
    itemDrafts.value = {}
    return
  }

  itemDrafts.value = selectedTask.value.items.reduce<Record<string, ItemFillbackDraft>>((acc, item) => {
    acc[item.id] = {
      actual_weight_kg: item.actual_weight_kg === null || item.actual_weight_kg === undefined ? '' : String(item.actual_weight_kg),
      injection_cost: item.injection_cost === null || item.injection_cost === undefined ? '' : String(item.injection_cost),
      production_machine: item.production_machine ?? '',
    }

    return acc
  }, {})
}

function updateItemDraft(itemId: string, field: keyof ItemFillbackDraft, value: string) {
  itemDrafts.value = {
    ...itemDrafts.value,
    [itemId]: {
      ...(itemDrafts.value[itemId] ?? { actual_weight_kg: '', injection_cost: '', production_machine: '' }),
      [field]: value,
    },
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

async function loadApiData() {
  apiState.value = 'checking'
  actionMessage.value = '正在读取啤办生产任务...'

  try {
    const [orders, notifications] = await Promise.all([
      moldingSampleApi.listOrders(),
      moldingSampleApi.listNotifications({
        target_module: PRODUCTION_NOTIFICATION_MODULE,
        factory_id: selectedFactoryId.value,
      }),
    ])
    apiRecords.value = orders
    apiNotifications.value = notifications
    const formalTaskCount = orders.filter((record) =>
      record.order.factory_id === selectedFactoryId.value
      && notificationOrderIds.value.has(record.order.id)
      && !isExternalMoldingSampleOrder(record.order),
    ).length
    apiState.value = formalTaskCount ? 'connected' : 'empty'
    actionMessage.value = formalTaskCount
      ? `已从独立通知表同步 ${notifications.length} 条生产通知。`
      : '当前独立通知表没有待生产任务通知。'
  }
  catch (error) {
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

  const orderId = selectedTask.value.order.id
  applyLocalItemPatches(orderId)

  if (apiState.value !== 'connected') {
    actionMessage.value = '真实任务读取失败或暂无正式任务，不能保存回填。'
    return
  }

  try {
    const updated = await moldingSampleApi.updateItems(orderId, { items: buildItemPatches() })
    replaceApiRecord(updated)
    actionMessage.value = '啤机回填已保存，工程啤办单可以看到最新实际用料、啤办机台和啤办费。'
  }
  catch (error) {
    actionMessage.value = `啤机回填保存失败：${getApiErrorMessage(error)}`
  }
}

async function runProductionTransition(action: '开始处理' | '标记完成') {
  if (!selectedTask.value) {
    actionMessage.value = '请先选择一张啤办生产任务单。'
    return
  }
  if (action === '开始处理' && !canStartSelectedTask.value) {
    actionMessage.value = '只有待生产任务可以开始执行。'
    return
  }
  if (action === '标记完成' && !canCompleteSelectedTask.value) {
    actionMessage.value = completionGate.value.message
    return
  }

  const orderId = selectedTask.value.order.id

  if (action === '标记完成') {
    applyLocalItemPatches(orderId)
  }

  if (apiState.value !== 'connected') {
    actionMessage.value = '真实任务读取失败或暂无正式任务，不能更新生产状态。'
    return
  }

  try {
    if (action === '标记完成') {
      await moldingSampleApi.updateItems(orderId, { items: buildItemPatches() })
    }

    const payload: MoldingSampleStatusRequest = {
      action,
      reason: action === '开始处理'
        ? '啤办生产任务单接收后开始执行。'
        : '啤机部完成生产并回传工程啤办单。',
      today,
    }
    const updated = await moldingSampleApi.updateStatus(orderId, payload)
    replaceApiRecord(updated)
    actionMessage.value = action === '开始处理'
      ? '啤办生产任务已开始执行。'
      : '生产完成通知已回传到工程啤办单。'
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
})

watch(selectedTask, () => {
  syncItemDrafts()
  isSelectedTaskDataExpanded.value = false
}, { immediate: true })

watch([queueFilter, selectedFactoryId], () => {
  queuePage.value = 1
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

      <section class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div class="min-w-0">
            <p class="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">MOLDING SAMPLE PRODUCTION TASK</p>
            <h1 class="mt-1 text-2xl font-bold tracking-tight text-slate-950">啤机部生产任务单</h1>
            <p class="mt-1 max-w-4xl text-sm text-slate-600">
              啤办生产任务单用于接收工程啤办单通知，啤机部在这里开始执行、回填实际用料和啤办费，完成后把状态回传到同一张工程啤办单。
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
                <div class="text-[10px] text-slate-300">预估费用 (HKD)</div>
                <div class="text-lg font-bold tabular-nums">{{ formatCurrency(selectedReportSummary?.total_cost, '$ 0.00') }}</div>
              </div>
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
              <span class="ml-auto text-[11px] text-slate-400">汇率 RMB→HKD {{ moldingSampleRmbToHkdRate }} · 单价按原料表</span>
              <button
                type="button"
                class="inline-flex h-7 items-center rounded-md border border-slate-200 bg-white px-2 text-[11px] font-semibold text-slate-600 transition hover:border-slate-300 hover:text-slate-950"
                @click="isSelectedTaskDataExpanded = !isSelectedTaskDataExpanded"
              >
                {{ isSelectedTaskDataExpanded ? '收起完整数据' : '展开完整数据' }}
              </button>
            </div>
            <div class="overflow-x-auto">
              <table class="w-full min-w-[1040px] text-[12px]">
                <thead>
                  <tr class="border-b border-slate-100 bg-slate-50 text-[11px] text-slate-500">
                    <th class="px-2 py-2 text-left font-medium">模具 / 原料</th>
                    <th class="px-2 py-2 text-right font-medium">领料(kg)</th>
                    <th class="px-2 py-2 text-right font-medium">实际用料(kg)</th>
                    <th class="px-2 py-2 text-left font-medium">啤办机台</th>
                    <th class="px-2 py-2 text-right font-medium">料费(HKD)</th>
                    <th class="px-2 py-2 text-right font-medium">啤办费(RMB)</th>
                    <th class="px-2 py-2 text-right font-medium">啤办费(HKD)</th>
                    <th class="px-2 py-2 text-right font-medium">小计</th>
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
                    <td class="px-2 py-1 text-left">
                      <input
                        :value="itemDrafts[item.id]?.production_machine ?? ''"
                        :disabled="!canFillbackSelectedTask"
                        aria-label="啤办机台"
                        type="text"
                        class="h-8 w-28 rounded-md border border-slate-200 px-2 text-left outline-none focus:border-slate-400 disabled:bg-slate-50 disabled:text-slate-400"
                        placeholder="机台号"
                        @input="updateItemDraft(item.id, 'production_machine', readInputValue($event))"
                      >
                    </td>
                    <td class="px-2 py-2 text-right font-semibold tabular-nums" :class="getReportRow(item.id)?.actual_amount_hkd ? 'text-slate-900' : 'text-slate-300'">
                      {{ formatCurrency(getReportRow(item.id)?.actual_amount_hkd) }}
                    </td>
                    <td class="px-2 py-1 text-right">
                      <input
                        :value="itemDrafts[item.id]?.injection_cost ?? ''"
                        :disabled="!canFillbackSelectedTask"
                        aria-label="啤办费"
                        type="number"
                        min="0"
                        step="0.01"
                        class="h-8 w-16 rounded-md border border-slate-200 px-2 text-right tabular-nums outline-none focus:border-slate-400 disabled:bg-slate-50 disabled:text-slate-400"
                        placeholder="—"
                        @input="updateItemDraft(item.id, 'injection_cost', readInputValue($event))"
                      >
                    </td>
                    <td class="px-2 py-2 text-right tabular-nums" :class="getReportRow(item.id)?.injection_cost_hkd ? 'text-slate-900' : 'text-slate-300'">
                      {{ formatCurrency(getReportRow(item.id)?.injection_cost_hkd) }}
                    </td>
                    <td class="px-2 py-2 text-right font-bold tabular-nums" :class="getReportRow(item.id)?.total_cost ? 'text-slate-950' : 'text-slate-300'">
                      {{ formatCurrency(getReportRow(item.id)?.total_cost) }}
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
                    <td />
                    <td class="px-2 py-2 text-right tabular-nums">{{ formatCurrency(selectedReportSummary?.total_injection_cost, '$ 0.00') }}</td>
                    <td class="px-2 py-2 text-right tabular-nums">{{ formatCurrency(selectedReportSummary?.total_cost, '$ 0.00') }}</td>
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
                    <div class="text-[10px] font-semibold text-slate-400">文件编号</div>
                    <div class="mt-0.5 font-semibold text-slate-900">{{ formatBlank(selectedTask.order.doc_number) }}</div>
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
                      <div><span class="text-slate-400">机型</span><div class="font-semibold">{{ formatBlank(item.machine_type) }}</div></div>
                      <div><span class="text-slate-400">啤办机台</span><div class="font-semibold">{{ formatBlank(item.production_machine) }}</div></div>
                      <div><span class="text-slate-400">原料</span><div class="font-semibold">{{ formatBlank(item.material) }}</div></div>
                      <div><span class="text-slate-400">颜色 / PMS</span><div class="font-semibold">{{ formatBlank(item.color) }} / {{ formatBlank(item.pigment_no) }}</div></div>
                      <div><span class="text-slate-400">数量 / 啤数</span><div class="font-semibold">{{ formatBlank(item.quantity) }} / {{ formatBlank(item.shoot_qty) }}</div></div>
                      <div><span class="text-slate-400">整啤毛重(g)</span><div class="font-semibold">{{ formatGram(item.gross_weight_g) }}</div></div>
                      <div><span class="text-slate-400">预计用料</span><div class="font-semibold">{{ formatWeight(item.required_material_kg) }}</div></div>
                      <div><span class="text-slate-400">回模 / 完成时间</span><div class="font-semibold">{{ formatBlank(item.mold_return_time) }} / {{ formatBlank(item.completion_time) }}</div></div>
                      <div><span class="text-slate-400">收据编号</span><div class="font-semibold">{{ formatBlank(item.receipt_no) }}</div></div>
                      <div><span class="text-slate-400">领料重量</span><div class="font-semibold">{{ formatWeight(item.collected_weight_kg) }}</div></div>
                      <div><span class="text-slate-400">实际用料</span><div class="font-semibold">{{ formatWeight(item.actual_weight_kg) }}</div></div>
                      <div><span class="text-slate-400">实际料费(HKD)</span><div class="font-semibold">{{ formatCurrency(getReportRow(item.id)?.actual_amount_hkd ?? item.actual_amount_hkd) }}</div></div>
                      <div><span class="text-slate-400">啤办费(RMB)</span><div class="font-semibold">{{ formatCurrency(item.injection_cost) }}</div></div>
                      <div><span class="text-slate-400">啤办费(HKD)</span><div class="font-semibold">{{ formatCurrency(getReportRow(item.id)?.injection_cost_hkd ?? item.injection_cost_hkd) }}</div></div>
                      <div><span class="text-slate-400">汇率</span><div class="font-semibold">{{ formatBlank(item.exchange_rate_at_save) }}</div></div>
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
                  type="button"
                  :disabled="!canCompleteSelectedTask"
                  class="flex h-10 w-full items-center justify-center gap-2 rounded-lg text-[13px] font-semibold transition disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
                  :class="canCompleteSelectedTask ? 'bg-emerald-700 text-white hover:bg-emerald-800' : ''"
                  @click="runProductionTransition('标记完成')"
                >
                  <CheckCircle2 v-if="canCompleteSelectedTask" class="size-4" aria-hidden="true" />
                  <Lock v-else class="size-4" aria-hidden="true" />
                  {{ canCompleteSelectedTask ? '完成并回传' : `标记完成（缺 ${completionGate.missing_item_ids.length} 项用料）` }}
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
                  :disabled="problemSubmitting"
                  class="h-8 rounded-lg border border-slate-200 bg-white px-2 text-[12px] outline-none focus:border-slate-400 disabled:bg-slate-50 disabled:text-slate-400"
                  placeholder="生产问题反馈，可回到工程啤办单跟进"
                >
                <button
                  type="button"
                  :disabled="problemSubmitting || !productionProblem.trim()"
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
    </div>
  </main>
</template>
