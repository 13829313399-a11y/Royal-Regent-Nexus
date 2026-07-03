<script setup lang="ts">
import { computed, onMounted, ref, watch, watchEffect } from 'vue'
import { AlertTriangle, ArrowLeft, CheckCircle2, ClipboardCheck, Play, RotateCcw, Save, Send } from '@lucide/vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import {
  factoryContexts,
  isProductionFactoryContextId,
  type ProductionFactoryContextId,
  type Tone,
} from '@/data/enterpriseMock'
import { moldingSampleFactoryRecords } from '@/data/moldingSampleWorkflowMock'
import {
  buildCompletionGate,
  isExternalMoldingSampleOrder,
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
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { useAppStore } from '@/stores/app'

interface TaskSummaryCard {
  label: string
  value: string
  detail: string
  tone: Tone
}

interface ItemFillbackDraft {
  actual_weight_kg: string
  injection_cost: string
}

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()

const today = '2026-07-03'
const PRODUCTION_NOTIFICATION_MODULE = 'production_molding_sample_task'
const apiRecords = ref<MoldingSampleDetailResponse[]>([])
const apiNotifications = ref<MoldingSampleNotificationResponse[]>([])
const apiState = ref<'checking' | 'connected' | 'empty' | 'fallback'>('checking')
const actionMessage = ref('正在读取啤办生产任务...')
const selectedOrderId = ref('')
const productionProblem = ref('')
const problemSubmitting = ref(false)
const itemDrafts = ref<Record<string, ItemFillbackDraft>>({})
const localOrderOverrides = ref<Record<string, Partial<MoldingSampleOrder>>>({})
const localItemOverrides = ref<Record<string, Record<string, Partial<MoldingSampleItem>>>>({})
const localProblemOverrides = ref<Record<string, MoldingSampleProblem[]>>({})

const statusTones: Record<MoldingSampleStatus, Tone> = {
  待审核: 'blue',
  待经理审核: 'blue',
  待生产: 'amber',
  生产中: 'teal',
  已完成: 'green',
  已驳回: 'red',
}

const toneClasses: Record<Tone, string> = {
  teal: 'border-teal-100 bg-teal-50 text-teal-800',
  blue: 'border-blue-100 bg-blue-50 text-blue-800',
  amber: 'border-amber-100 bg-amber-50 text-amber-800',
  red: 'border-red-100 bg-red-50 text-red-800',
  slate: 'border-slate-200 bg-slate-50 text-slate-700',
  green: 'border-emerald-100 bg-emerald-50 text-emerald-800',
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
  if (apiRecords.value.length) {
    const records = apiRecords.value.map((record) => ({
      factory_id: record.order.factory_id,
      order: record.order,
      items: record.items,
      audit_logs: record.audit_logs,
      requisitions: [],
      problems: record.problems ?? [],
    }))

    if (apiNotifications.value.length) {
      return records.filter((record) => notificationOrderIds.value.has(record.order.id))
    }

    return []
  }

  return Object.values(moldingSampleFactoryRecords)
})

const taskRecords = computed(() =>
  sourceRecords.value.map((record) => ({
    ...record,
    order: {
      ...record.order,
      ...(localOrderOverrides.value[record.order.id] ?? {}),
    },
    items: record.items.map((item) => ({
      ...item,
      ...(localItemOverrides.value[record.order.id]?.[item.id] ?? {}),
    })),
    problems: [
      ...record.problems,
      ...(localProblemOverrides.value[record.order.id] ?? []),
    ],
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

const taskSummaryCards = computed<TaskSummaryCard[]>(() => {
  const notifiedCount = taskEntries.value.filter((entry) => ['待审核', '待经理审核'].includes(entry.order.status)).length
  const readyCount = taskEntries.value.filter((entry) => entry.order.status === '待生产').length
  const runningCount = taskEntries.value.filter((entry) => entry.order.status === '生产中').length
  const completedCount = taskEntries.value.filter((entry) => entry.order.status === '已完成').length

  return [
    {
      label: '工程通知',
      value: String(notifiedCount),
      detail: '经理审核完成后进入通知区',
      tone: notifiedCount ? 'blue' : 'slate',
    },
    {
      label: '待执行',
      value: String(readyCount),
      detail: '已到啤机部可开始节点',
      tone: readyCount ? 'amber' : 'slate',
    },
    {
      label: '生产中',
      value: String(runningCount),
      detail: '需要回填实际用料和啤办费',
      tone: runningCount ? 'teal' : 'slate',
    },
    {
      label: '已回传',
      value: String(completedCount),
      detail: '完成后状态回写工程啤办单',
      tone: completedCount ? 'green' : 'slate',
    },
  ]
})

const canStartSelectedTask = computed(() => selectedTask.value?.order.status === '待生产')
const canFillbackSelectedTask = computed(() => selectedTask.value?.order.status === '生产中')
const canCompleteSelectedTask = computed(() => canFillbackSelectedTask.value && completionGate.value.can_complete)

function readQueryString(value: unknown) {
  if (typeof value === 'string') {
    return value.trim()
  }
  if (Array.isArray(value) && typeof value[0] === 'string') {
    return value[0].trim()
  }

  return ''
}

function getTaskPriority(status: MoldingSampleStatus) {
  const priorities: Record<MoldingSampleStatus, number> = {
    生产中: 0,
    待生产: 1,
    待审核: 2,
    待经理审核: 3,
    已完成: 4,
    已驳回: 5,
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
    return '等待经理终审，终审通过后进入啤机可执行队列'
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

function formatBlank(value: string | number | null | undefined, fallback = '待填写') {
  return value === null || value === undefined || value === '' ? fallback : String(value)
}

function formatWeight(value: number | null | undefined) {
  return value === null || value === undefined ? '待填写' : `${value} KG`
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
    }

    return acc
  }, {})
}

function updateItemDraft(itemId: string, field: keyof ItemFillbackDraft, value: string) {
  itemDrafts.value = {
    ...itemDrafts.value,
    [itemId]: {
      ...(itemDrafts.value[itemId] ?? { actual_weight_kg: '', injection_cost: '' }),
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
  if (apiState.value === 'connected' || apiState.value === 'empty') {
    apiRecords.value = apiRecords.value.map((entry) => entry.order.id === orderId
      ? {
          ...entry,
          problems: [
            problem,
            ...(entry.problems ?? []).filter((existing) => existing.id !== problem.id),
          ],
        }
      : entry)
    return
  }

  localProblemOverrides.value = {
    ...localProblemOverrides.value,
    [orderId]: [
      problem,
      ...(localProblemOverrides.value[orderId] ?? []).filter((existing) => existing.id !== problem.id),
    ],
  }
}

function replaceApiNotificationsForOrder(record: MoldingSampleDetailResponse) {
  const productionNotifications = (record.notifications ?? [])
    .filter((notification) => notification.target_module === PRODUCTION_NOTIFICATION_MODULE)
  const otherNotifications = apiNotifications.value
    .filter((notification) => notification.order_id !== record.order.id)

  apiNotifications.value = [...productionNotifications, ...otherNotifications]
    .sort((left, right) => right.created_at.localeCompare(left.created_at))
}

function getLatestNotification(orderId: string) {
  return apiNotifications.value.find((notification) => notification.order_id === orderId) ?? null
}

function getNotificationMeta(orderId: string) {
  const notification = getLatestNotification(orderId)
  if (!notification) {
    return '本地示例通知'
  }

  return `${notification.event_type} · ${notification.status}`
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
    apiState.value = 'fallback'
    actionMessage.value = `当前网络异常，暂以本地示例单据展示生产任务。${getApiErrorMessage(error)}`
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

async function saveProductionFillback() {
  if (!selectedTask.value) {
    actionMessage.value = '请先选择一张啤办生产任务单。'
    return
  }

  const orderId = selectedTask.value.order.id
  applyLocalItemPatches(orderId)

  if (apiState.value === 'fallback') {
    actionMessage.value = '当前为离线示例，啤机回填已暂存在本页。'
    return
  }

  try {
    const updated = await moldingSampleApi.updateItems(orderId, { items: buildItemPatches() })
    replaceApiRecord(updated)
    actionMessage.value = '啤机回填已保存，工程啤办单可以看到最新实际用料和啤办费。'
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
  const nextStatus: MoldingSampleStatus = action === '开始处理' ? '生产中' : '已完成'

  if (action === '标记完成') {
    applyLocalItemPatches(orderId)
  }

  if (apiState.value === 'fallback') {
    localOrderOverrides.value = {
      ...localOrderOverrides.value,
      [orderId]: {
        ...(localOrderOverrides.value[orderId] ?? {}),
        status: nextStatus,
        completed_date: action === '标记完成' ? today : selectedTask.value.order.completed_date,
        updated_at: `${today} 16:30`,
      },
    }
    actionMessage.value = action === '开始处理'
      ? '离线示例已切换到生产中。'
      : '离线示例已完成并回传到工程啤办单状态。'
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
  problemSubmitting.value = true

  if (apiState.value === 'fallback') {
    appendProblemForOrder(orderId, {
      id: `${orderId}-local-problem-${Date.now()}`,
      factory_id: selectedTask.value.factory_id,
      order_type: 'injection',
      order_id: orderId,
      order_number: selectedTask.value.order.order_number,
      description: problem,
      reported_by: '啤机部',
      status: '待处理',
      created_at: `${today} 16:30`,
      resolved_at: '',
    })
    actionMessage.value = `离线示例已暂存问题反馈：${problem}`
    productionProblem.value = ''
    problemSubmitting.value = false
    return
  }

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
}, { immediate: true })

watchEffect(() => {
  appStore.setActiveFactory(selectedFactoryId.value)
})
</script>

<template>
  <main class="min-h-screen bg-slate-100 px-4 pb-6 pt-16 text-slate-950 sm:px-6 xl:px-10">
    <div class="mx-auto max-w-[1520px] space-y-5">
      <RouterLink
        to="/modules/production"
        class="fixed left-4 top-4 z-50 inline-flex h-9 items-center gap-2 rounded-full border border-slate-200 bg-white/95 px-3 text-sm font-semibold text-slate-600 shadow-sm backdrop-blur transition hover:border-slate-300 hover:text-slate-950 sm:left-6 xl:left-10"
      >
        <ArrowLeft class="size-4" aria-hidden="true" />
        生产部模块
      </RouterLink>

      <section class="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <div class="grid gap-5 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-start">
          <div class="flex min-w-0 gap-4">
            <div class="flex h-14 w-14 shrink-0 items-center justify-center rounded-lg border border-teal-100 bg-teal-50 text-teal-700">
              <ClipboardCheck class="size-7" aria-hidden="true" />
            </div>
            <div class="min-w-0">
              <p class="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">MOLDING SAMPLE PRODUCTION TASK</p>
              <h1 class="mt-2 text-2xl font-semibold tracking-tight text-slate-950 sm:text-3xl">啤办生产任务单</h1>
              <p class="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
                接收工程啤办单通知，啤机部在这里开始执行、回填实际用料和啤办费，完成后把状态回传到同一张工程啤办单。
              </p>
              <p class="mt-2 text-sm font-medium text-slate-500">当前厂区：{{ activeFactory.shortName }} · {{ actionMessage }}</p>
            </div>
          </div>

          <div class="flex flex-wrap gap-2 xl:justify-end">
            <RouterLink
              :to="engineeringOrderRoute"
              class="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-slate-300 hover:text-slate-950"
            >
              <Send class="size-4" aria-hidden="true" />
              工程啤办单
            </RouterLink>
            <button
              type="button"
              class="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-950 bg-slate-950 px-4 text-sm font-semibold text-white"
              @click="loadApiData"
            >
              <RotateCcw class="size-4" aria-hidden="true" />
              刷新任务
            </button>
          </div>
        </div>
      </section>

      <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <article
          v-for="card in taskSummaryCards"
          :key="card.label"
          class="min-h-[92px] rounded-lg border p-4"
          :class="toneClasses[card.tone]"
        >
          <p class="text-xs font-medium opacity-80">{{ card.label }}</p>
          <p class="mt-1 text-2xl font-semibold text-slate-950">{{ card.value }}</p>
          <p class="mt-1 text-xs opacity-75">{{ card.detail }}</p>
        </article>
      </div>

      <div class="grid gap-5 xl:grid-cols-[380px_minmax(0,1fr)]">
        <aside class="xl:sticky xl:top-24 xl:self-start">
          <SectionPanel title="任务通知队列" subtitle="独立通知表接收工程新建通知，待审核完成后转入可执行任务">
            <div v-if="taskEntries.length" class="space-y-3">
              <button
                v-for="entry in taskEntries"
                :key="entry.order.id"
                type="button"
                class="w-full rounded-lg border bg-white p-3 text-left transition hover:border-slate-300 hover:bg-slate-50"
                :class="selectedTask?.order.id === entry.order.id ? 'border-slate-950 ring-1 ring-slate-950' : 'border-slate-200'"
                @click="selectTask(entry.order.id, entry.factory_id)"
              >
                <div class="flex items-start justify-between gap-3">
                  <div class="min-w-0">
                    <p class="truncate text-sm font-semibold text-slate-950">{{ entry.order.id }} · {{ entry.order.product_name }}</p>
                    <p class="mt-1 truncate text-xs text-slate-500">{{ entry.order.client_name }} · {{ entry.order.eng_name }}</p>
                    <p class="mt-1 truncate text-xs font-semibold text-blue-700">独立通知表 · {{ getNotificationMeta(entry.order.id) }}</p>
                  </div>
                  <StatusPill :label="getTaskStageLabel(entry.order.status)" :tone="statusTones[entry.order.status]" compact />
                </div>
                <div class="mt-3 grid grid-cols-3 gap-2 text-xs">
                  <div class="rounded-md bg-slate-50 px-2 py-1">
                    <p class="text-slate-500">明细</p>
                    <p class="font-semibold text-slate-900">{{ entry.items.length }}</p>
                  </div>
                  <div class="rounded-md bg-slate-50 px-2 py-1">
                    <p class="text-slate-500">啤数</p>
                    <p class="font-semibold text-slate-900">{{ entry.items.reduce((sum, item) => sum + item.shoot_qty, 0) }}</p>
                  </div>
                  <div class="rounded-md bg-slate-50 px-2 py-1">
                    <p class="text-slate-500">需办</p>
                    <p class="truncate font-semibold text-slate-900">{{ entry.items[0]?.completion_time || entry.order.date }}</p>
                  </div>
                </div>
              </button>
            </div>
            <div v-else class="rounded-lg border border-slate-200 bg-slate-50 p-5 text-sm text-slate-500">
              当前没有内部啤机生产任务。外厂 / 模厂路径不会进入这里。
            </div>
          </SectionPanel>
        </aside>

        <section v-if="selectedTask" class="space-y-5">
          <SectionPanel title="任务执行" subtitle="啤机部只处理生产执行字段，工程资料回到工程啤办单维护">
            <div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
              <div class="space-y-4">
                <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                  <div class="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                    <p class="text-xs font-semibold text-slate-500">啤办单号</p>
                    <p class="mt-1 truncate text-sm font-semibold text-slate-950">{{ selectedTask.order.id }}</p>
                  </div>
                  <div class="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                    <p class="text-xs font-semibold text-slate-500">产品</p>
                    <p class="mt-1 truncate text-sm font-semibold text-slate-950">{{ selectedTask.order.product_name }}</p>
                  </div>
                  <div class="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                    <p class="text-xs font-semibold text-slate-500">工程落单人</p>
                    <p class="mt-1 truncate text-sm font-semibold text-slate-950">{{ selectedTask.order.eng_name }}</p>
                  </div>
                  <div class="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                    <p class="text-xs font-semibold text-slate-500">要求日期</p>
                    <p class="mt-1 truncate text-sm font-semibold text-slate-950">{{ activeItems[0]?.completion_time || selectedTask.order.date }}</p>
                  </div>
                </div>

                <div
                  class="rounded-lg border p-4 text-sm"
                  :class="toneClasses[selectedTask.order.status === '生产中' ? 'teal' : selectedTask.order.status === '已完成' ? 'green' : selectedTask.order.status === '待生产' ? 'amber' : 'blue']"
                >
                  <div class="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p class="font-semibold">{{ getTaskStageLabel(selectedTask.order.status) }}</p>
                      <p class="mt-1 opacity-80">{{ getTaskStageDetail(selectedTask.order) }}</p>
                    </div>
                    <StatusPill :label="selectedTask.order.status" :tone="statusTones[selectedTask.order.status]" />
                  </div>
                </div>
              </div>

              <div class="grid gap-2">
                <button
                  type="button"
                  :disabled="!canStartSelectedTask"
                  class="inline-flex h-11 items-center justify-center gap-2 rounded-lg border px-3 text-sm font-semibold disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-400"
                  :class="canStartSelectedTask ? 'border-slate-950 bg-slate-950 text-white' : ''"
                  @click="runProductionTransition('开始处理')"
                >
                  <Play class="size-4" aria-hidden="true" />
                  开始生产
                </button>
                <button
                  type="button"
                  :disabled="!canFillbackSelectedTask"
                  class="inline-flex h-11 items-center justify-center gap-2 rounded-lg border px-3 text-sm font-semibold disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-400"
                  :class="canFillbackSelectedTask ? 'border-blue-700 bg-blue-700 text-white' : ''"
                  @click="saveProductionFillback"
                >
                  <Save class="size-4" aria-hidden="true" />
                  保存回填
                </button>
                <button
                  type="button"
                  :disabled="!canCompleteSelectedTask"
                  class="inline-flex h-11 items-center justify-center gap-2 rounded-lg border px-3 text-sm font-semibold disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-400"
                  :class="canCompleteSelectedTask ? 'border-emerald-700 bg-emerald-700 text-white' : ''"
                  @click="runProductionTransition('标记完成')"
                >
                  <CheckCircle2 class="size-4" aria-hidden="true" />
                  完成并回传
                </button>
              </div>
            </div>
          </SectionPanel>

          <SectionPanel title="啤机回填明细" subtitle="生产中任务可填写实际用料和啤办费；完成前必须补齐实际用料">
            <div
              v-if="!completionGate.can_complete"
              class="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
            >
              <div class="flex items-start gap-2">
                <AlertTriangle class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                <p>{{ completionGate.message }}</p>
              </div>
            </div>

            <div class="overflow-x-auto rounded-lg border border-slate-200 bg-white">
              <table class="min-w-[980px] divide-y divide-slate-200 text-sm">
                <thead class="bg-slate-50 text-left text-xs font-semibold text-slate-500">
                  <tr>
                    <th class="px-4 py-3">明细</th>
                    <th class="px-4 py-3">原料</th>
                    <th class="px-4 py-3">颜色</th>
                    <th class="px-4 py-3 text-right">啤数</th>
                    <th class="px-4 py-3 text-right">预计KG</th>
                    <th class="px-4 py-3 text-right">实际KG</th>
                    <th class="px-4 py-3 text-right">啤办费RMB</th>
                    <th class="px-4 py-3">状态</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                  <tr v-for="item in activeItems" :key="item.id">
                    <td class="px-4 py-3">
                      <p class="font-medium text-slate-950">{{ item.mold_id }}</p>
                      <p class="mt-1 text-xs text-slate-500">{{ item.mold_name }}</p>
                    </td>
                    <td class="px-4 py-3">{{ item.material }}</td>
                    <td class="px-4 py-3">{{ item.color }}</td>
                    <td class="px-4 py-3 text-right">{{ item.shoot_qty }}</td>
                    <td class="px-4 py-3 text-right">{{ formatWeight(item.required_material_kg) }}</td>
                    <td class="px-4 py-3 text-right">
                      <input
                        :value="itemDrafts[item.id]?.actual_weight_kg ?? ''"
                        :disabled="!canFillbackSelectedTask"
                        type="number"
                        min="0"
                        step="0.01"
                        class="h-9 w-28 rounded-md border border-slate-200 px-2 text-right disabled:bg-slate-50 disabled:text-slate-400"
                        @input="updateItemDraft(item.id, 'actual_weight_kg', readInputValue($event))"
                      >
                    </td>
                    <td class="px-4 py-3 text-right">
                      <input
                        :value="itemDrafts[item.id]?.injection_cost ?? ''"
                        :disabled="!canFillbackSelectedTask"
                        type="number"
                        min="0"
                        step="0.01"
                        class="h-9 w-28 rounded-md border border-slate-200 px-2 text-right disabled:bg-slate-50 disabled:text-slate-400"
                        @input="updateItemDraft(item.id, 'injection_cost', readInputValue($event))"
                      >
                    </td>
                    <td class="px-4 py-3">
                      <StatusPill
                        :label="Number(item.actual_weight_kg) > 0 ? '已回填' : '待回填'"
                        :tone="Number(item.actual_weight_kg) > 0 ? 'green' : 'amber'"
                        compact
                      />
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div class="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_180px]">
              <input
                v-model="productionProblem"
                :disabled="problemSubmitting"
                class="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm"
                placeholder="生产问题反馈，可回到工程啤办单跟进"
              >
              <button
                type="button"
                :disabled="problemSubmitting || !productionProblem.trim()"
                class="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-200 px-3 text-sm font-semibold text-slate-700"
                @click="reportProductionProblem"
              >
                <AlertTriangle class="size-4" aria-hidden="true" />
                {{ problemSubmitting ? '保存中...' : '反馈问题' }}
              </button>
            </div>
            <div v-if="selectedProblems.length" class="mt-3 space-y-2">
              <article
                v-for="problem in selectedProblems"
                :key="problem.id"
                class="rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-xs text-red-800"
              >
                <div class="flex flex-wrap items-center justify-between gap-2">
                  <span class="font-semibold">{{ problem.status }} · {{ problem.reported_by }}</span>
                  <span class="text-red-500">{{ problem.created_at }}</span>
                </div>
                <p class="mt-1 leading-5">{{ problem.description }}</p>
              </article>
            </div>
          </SectionPanel>

          <SectionPanel title="完成通知回传" subtitle="生产完成会写回工程啤办单状态和审核轨迹">
            <div class="grid gap-3 md:grid-cols-3">
              <article class="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <p class="text-xs font-semibold text-slate-500">回传目标</p>
                <p class="mt-2 text-sm font-semibold text-slate-950">{{ selectedTask.order.id }} 工程啤办单</p>
                <p class="mt-1 text-xs text-slate-500">同一张单据，不复制一份生产数据</p>
              </article>
              <article class="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <p class="text-xs font-semibold text-slate-500">完成状态</p>
                <p class="mt-2 text-sm font-semibold text-slate-950">{{ selectedTask.order.status === '已完成' ? '已回传' : '待回传' }}</p>
                <p class="mt-1 text-xs text-slate-500">{{ selectedTask.order.completed_date || '完成后写入日期' }}</p>
              </article>
              <article class="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <p class="text-xs font-semibold text-slate-500">最近记录</p>
                <p class="mt-2 line-clamp-1 text-sm font-semibold text-slate-950">{{ selectedTask.audit_logs[0]?.action || '暂无轨迹' }}</p>
                <p class="mt-1 text-xs text-slate-500">{{ formatBlank(selectedTask.audit_logs[0]?.created_at, '待生成') }}</p>
              </article>
            </div>
          </SectionPanel>
        </section>

        <section v-else class="rounded-lg border border-slate-200 bg-white p-8 text-center text-sm text-slate-500">
          暂无啤办生产任务单。工程新建内部啤办单后，这里会先显示通知。
        </section>
      </div>
    </div>
  </main>
</template>
