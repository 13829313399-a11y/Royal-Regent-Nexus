<script setup lang="ts">
import { computed, ref, watchEffect } from 'vue'
import {
  ArrowLeft,
  Beaker,
  Building2,
  Check,
  CheckCheck,
  ChevronRight,
  Clock,
  ClipboardCheck,
  ExternalLink,
  Factory,
  FilePlus2,
  FileText,
  Filter,
  Gavel,
  History,
  Layers,
  LayoutDashboard,
  Lock,
  MessageSquareText,
  Plus,
  Search,
  Send,
  ShieldCheck,
  Table2,
  Tag,
  TriangleAlert,
  UserRound,
  X,
} from '@lucide/vue'
import { RouterLink, useRoute } from 'vue-router'
import {
  factoryContexts,
  isProductionFactoryContextId,
  type ProductionFactoryContextId,
} from '@/data/enterpriseMock'
import {
  getMoldingSampleRecord,
  moldingSampleFactoryRecords,
} from '@/data/moldingSampleWorkflowMock'
import {
  buildCompletionGate,
  isExternalMoldingSampleOrder,
} from '@/lib/moldingSampleBusiness'
import type {
  MoldingSampleItem,
  MoldingSampleStatus,
  MoldingSampleWorkflowRecord,
} from '@/types/moldingSample'
import { useAppStore } from '@/stores/app'

type ViewKey = 'overview' | 'create' | 'detail'
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
  dotClass: string
}

interface WorkflowStep {
  status: MoldingSampleStatus
  title: string
  detail: string
}

const route = useRoute()
const appStore = useAppStore()

const activeView = ref<ViewKey>('overview')
const selectedOrderId = ref(readQueryString(route.query.order_id))

const workflowSteps: WorkflowStep[] = [
  { status: '待审核', title: '主管审核', detail: '工程提交后进入主管队列' },
  { status: '待经理审核', title: '经理审核', detail: '主管通过后等待经理终审' },
  { status: '待生产', title: '待生产', detail: '内部单流转到啤机部' },
  { status: '生产中', title: '啤机生产', detail: '回填实际用料和啤办费' },
  { status: '已完成', title: '完成归档', detail: '生产完成后回传工程单' },
]

const boardStatuses: MoldingSampleStatus[] = [
  '待审核',
  '待经理审核',
  '待生产',
  '生产中',
  '已完成',
  '已驳回',
]

const statusToneClasses: Record<MoldingSampleStatus, string> = {
  待审核: 'border-amber-200 bg-amber-50 text-amber-700',
  待经理审核: 'border-blue-200 bg-blue-50 text-blue-700',
  待生产: 'border-indigo-200 bg-indigo-50 text-indigo-700',
  生产中: 'border-teal-200 bg-teal-50 text-teal-700',
  已完成: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  已驳回: 'border-red-200 bg-red-50 text-red-700',
}

const statusDotClasses: Record<MoldingSampleStatus, string> = {
  待审核: 'bg-amber-400',
  待经理审核: 'bg-blue-400',
  待生产: 'bg-indigo-400',
  生产中: 'bg-teal-400',
  已完成: 'bg-emerald-400',
  已驳回: 'bg-red-400',
}

const selectedFactoryId = computed<ProductionFactoryContextId>(() => {
  const routeFactory = route.query.factory

  if (typeof routeFactory === 'string' && isProductionFactoryContextId(routeFactory)) {
    return routeFactory
  }

  return isProductionFactoryContextId(appStore.activeProductionFactory.id)
    ? appStore.activeProductionFactory.id
    : 'huakang-a'
})

const activeFactory = computed(() =>
  factoryContexts.find((factory) => factory.id === selectedFactoryId.value) ?? factoryContexts[1],
)

const productionTaskRoute = computed(() => {
  const params = new URLSearchParams({ factory: selectedFactoryId.value })

  if (selectedRecord.value?.order.id) {
    params.set('order_id', selectedRecord.value.order.id)
  }

  return `/modules/production/molding-sample-tasks?${params.toString()}`
})

const factoryRecords = computed<MoldingSampleWorkflowRecord[]>(() =>
  Object.values(moldingSampleFactoryRecords).filter((record) => record.factory_id === selectedFactoryId.value),
)

const visibleRecords = computed<MoldingSampleWorkflowRecord[]>(() =>
  factoryRecords.value.length ? factoryRecords.value : [getMoldingSampleRecord(selectedFactoryId.value)],
)

const selectedRecord = computed<MoldingSampleWorkflowRecord>(() =>
  visibleRecords.value.find((record) => record.order.id === selectedOrderId.value)
    ?? visibleRecords.value[0]
    ?? getMoldingSampleRecord(selectedFactoryId.value),
)

const selectedOrder = computed(() => selectedRecord.value.order)
const selectedItems = computed(() => selectedRecord.value.items)
const selectedCompletionGate = computed(() => buildCompletionGate(selectedOrder.value, selectedItems.value))
const isSelectedExternal = computed(() => isExternalMoldingSampleOrder(selectedOrder.value))

const kpiCards = computed<KpiCard[]>(() => {
  const records = visibleRecords.value
  const reviewCount = records.filter((record) => ['待审核', '待经理审核'].includes(record.order.status)).length
  const productionCount = records.filter((record) => ['待生产', '生产中'].includes(record.order.status)).length
  const completedCount = records.filter((record) => record.order.status === '已完成').length
  const blockedCount = records.filter((record) =>
    record.order.status === '已驳回'
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
      detail: '主管 / 经理节点',
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
      label: '卡点 / 驳回',
      value: String(blockedCount),
      detail: '需要工程跟进',
      icon: TriangleAlert,
      className: 'border-red-200 bg-red-50 text-red-700',
    },
  ]
})

const boardColumns = computed<BoardColumn[]>(() =>
  boardStatuses.map((status) => ({
    status,
    label: status,
    detail: getStatusColumnDetail(status),
    records: visibleRecords.value.filter((record) => record.order.status === status),
    dotClass: statusDotClasses[status],
  })),
)

const detailRows = computed(() => selectedItems.value.slice(0, 8))
const createTemplateRows = computed(() => selectedItems.value.slice(0, 4))

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
}

function openRecord(record: MoldingSampleWorkflowRecord) {
  selectedOrderId.value = record.order.id
  activeView.value = 'detail'
}

function getStatusColumnDetail(status: MoldingSampleStatus) {
  const details: Record<MoldingSampleStatus, string> = {
    待审核: '等待主管处理',
    待经理审核: '等待经理终审',
    待生产: '已通知啤机部',
    生产中: '啤机部执行中',
    已完成: '完成后归档',
    已驳回: '退回工程处理',
  }

  return details[status]
}

function getWorkflowStepState(status: MoldingSampleStatus): StatusState {
  if (selectedOrder.value.status === '已驳回') {
    return status === '待审核' ? 'rejected' : 'pending'
  }

  const currentIndex = workflowSteps.findIndex((step) => step.status === selectedOrder.value.status)
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
    return `${record.order.supervisor} 已通过 → 王经理`
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

  return record.order.reject_reason || '退回工程处理'
}

function formatBlank(value: string | number | null | undefined, fallback = '待填写') {
  return value === null || value === undefined || value === '' ? fallback : String(value)
}

function formatWeight(value: number | null | undefined) {
  return value === null || value === undefined ? '待填写' : `${value.toFixed(2)} kg`
}

function formatMoney(value: number | null | undefined, currency = 'HKD') {
  return value === null || value === undefined ? '待计算' : `${currency} ${value.toFixed(2)}`
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
            placeholder="搜索单号 / 产品 / 客户 / 模具号..."
            class="h-8 w-72 rounded-lg border border-slate-200 bg-slate-50 pl-8 pr-3 text-[12px] outline-none transition focus:border-slate-400 focus:bg-white"
          >
        </div>

        <div class="ml-auto flex items-center gap-3">
          <span class="hidden h-8 items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 text-[12px] font-medium text-slate-600 sm:inline-flex">
            <Building2 class="size-4" aria-hidden="true" />
            {{ activeFactory.shortName }}
          </span>
          <span class="flex items-center gap-2 rounded-lg border border-slate-200 px-2.5 py-1">
            <span class="flex h-6 w-6 items-center justify-center rounded-full bg-teal-100 text-[11px] font-bold text-teal-700">工</span>
            <span class="leading-tight">
              <span class="block text-[12px] font-semibold">工程部</span>
              <span class="block text-[10px] text-slate-400">开单 / 审核跟进</span>
            </span>
          </span>
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
          @click="setView('create')"
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

    <div class="mx-auto max-w-[1720px] px-5 py-4">
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
            <button class="rounded-md bg-slate-900 px-2.5 py-1 text-[12px] font-semibold text-white">看板</button>
            <button class="rounded-md px-2.5 py-1 text-[12px] font-medium text-slate-500 hover:text-slate-900">列表</button>
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
          <button
            type="button"
            class="ml-auto inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-1.5 text-[12px] font-semibold text-white transition hover:bg-slate-700"
            @click="setView('create')"
          >
            <Plus class="size-4" aria-hidden="true" />
            新建啤办单
          </button>
        </div>

        <div class="grid grid-cols-1 gap-3 overflow-x-auto pb-2 md:grid-cols-2 xl:grid-cols-6">
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
              <button
                v-for="record in column.records"
                :key="record.order.id"
                type="button"
                class="w-full rounded-lg border bg-white p-2.5 text-left shadow-sm transition hover:shadow"
                :class="selectedOrder.id === record.order.id ? 'border-slate-950 ring-1 ring-slate-950' : 'border-slate-200 hover:border-slate-300'"
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

              <div
                v-if="!column.records.length"
                class="rounded-lg border border-dashed border-slate-200 bg-white/70 p-4 text-center text-[11px] font-medium text-slate-400"
              >
                暂无{{ column.label }}单据
              </div>
            </div>
          </section>
        </div>
      </section>

      <section v-else-if="activeView === 'create'" class="space-y-4">
        <div class="flex items-center gap-2 text-[12px] text-slate-400">
          <button type="button" class="hover:text-slate-900" @click="setView('overview')">看板总览</button>
          <ChevronRight class="size-3.5" aria-hidden="true" />
          <span class="font-semibold text-slate-700">新建啤办单</span>
        </div>

        <div class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
          <div class="space-y-4">
            <section class="rounded-lg border border-slate-200 bg-white">
              <div class="flex items-center gap-2 border-b border-slate-100 px-4 py-2.5">
                <FileText class="size-4 text-slate-400" aria-hidden="true" />
                <span class="text-[13px] font-bold">基础资料</span>
                <span class="ml-auto text-[11px] text-slate-400">单号自动生成 · BP-新</span>
              </div>
              <div class="grid grid-cols-2 gap-x-4 gap-y-3 p-4 md:grid-cols-3">
                <label class="block">
                  <span class="mb-1 block text-[11px] font-medium text-slate-500">产品编号</span>
                  <input :value="selectedOrder.order_number" class="h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-[12px] outline-none focus:border-slate-400">
                </label>
                <label class="block">
                  <span class="mb-1 block text-[11px] font-medium text-slate-500">文件编号</span>
                  <input :value="selectedOrder.doc_number" class="h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-[12px] outline-none focus:border-slate-400">
                </label>
                <label class="block">
                  <span class="mb-1 block text-[11px] font-medium text-slate-500">客户</span>
                  <input :value="selectedOrder.client_name" class="h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-[12px] outline-none focus:border-slate-400">
                </label>
                <label class="block">
                  <span class="mb-1 block text-[11px] font-medium text-slate-500">产品名称</span>
                  <input :value="selectedOrder.product_name" class="h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-[12px] outline-none focus:border-slate-400">
                </label>
                <label class="block">
                  <span class="mb-1 block text-[11px] font-medium text-slate-500">开单日期</span>
                  <input :value="selectedOrder.date" class="h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-[12px] outline-none focus:border-slate-400">
                </label>
                <label class="block">
                  <span class="mb-1 block text-[11px] font-medium text-slate-500">阶段</span>
                  <select class="h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-[12px] outline-none focus:border-slate-400">
                    <option>{{ selectedOrder.stage || '啤办' }}</option>
                    <option>T0</option>
                    <option>EP</option>
                    <option>FEP</option>
                    <option>PP</option>
                  </select>
                </label>
                <label class="block">
                  <span class="mb-1 block text-[11px] font-medium text-slate-500">车间</span>
                  <select class="h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-[12px] outline-none focus:border-slate-400">
                    <option>{{ selectedOrder.workshop }}</option>
                    <option>A车间</option>
                    <option>B车间</option>
                    <option>模厂</option>
                  </select>
                </label>
                <label class="block">
                  <span class="mb-1 block text-[11px] font-medium text-slate-500">发至</span>
                  <select class="h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-[12px] outline-none focus:border-slate-400">
                    <option>{{ selectedOrder.send_to || '内部生产' }}</option>
                    <option>发至湖南</option>
                    <option>发至模厂</option>
                  </select>
                </label>
                <label class="block">
                  <span class="mb-1 block text-[11px] font-medium text-slate-500">审核主管</span>
                  <select class="h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-[12px] outline-none focus:border-slate-400">
                    <option>{{ selectedOrder.supervisor }}</option>
                    <option>李主管</option>
                    <option>陈主管</option>
                    <option>黄主管</option>
                  </select>
                </label>
                <label class="col-span-2 block md:col-span-3">
                  <span class="mb-1 block text-[11px] font-medium text-slate-500">注意事项 / 开单事由</span>
                  <textarea :value="selectedOrder.reason" rows="3" class="w-full rounded-md border border-slate-200 bg-white px-2 py-1.5 text-[12px] outline-none focus:border-slate-400" />
                </label>
              </div>
            </section>

            <section class="rounded-lg border border-slate-200 bg-white">
              <div class="flex items-center gap-2 border-b border-slate-100 px-4 py-2.5">
                <Table2 class="size-4 text-slate-400" aria-hidden="true" />
                <span class="text-[13px] font-bold">模具明细</span>
                <span class="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-500">按行维护</span>
              </div>
              <div class="overflow-x-auto">
                <table class="w-full min-w-[900px] text-[12px]">
                  <thead>
                    <tr class="border-b border-slate-100 bg-slate-50 text-[11px] text-slate-500">
                      <th class="w-10 px-2 py-2 font-medium">#</th>
                      <th class="px-2 py-2 text-left font-medium">客模具编号</th>
                      <th class="px-2 py-2 text-left font-medium">模具名称</th>
                      <th class="px-2 py-2 text-left font-medium">所需用料</th>
                      <th class="px-2 py-2 text-left font-medium">颜色 / PMS</th>
                      <th class="px-2 py-2 text-left font-medium">色粉</th>
                      <th class="px-2 py-2 text-right font-medium">啤数</th>
                      <th class="px-2 py-2 text-left font-medium">需办日期</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-slate-50">
                    <tr v-for="item in createTemplateRows" :key="item.id" class="hover:bg-slate-50/60">
                      <td class="px-2 py-2 text-center text-slate-400">{{ item.sort_order }}</td>
                      <td class="px-2 py-2 font-mono">{{ item.mold_id }}</td>
                      <td class="px-2 py-2">{{ item.mold_name }}</td>
                      <td class="px-2 py-2">{{ item.material }}</td>
                      <td class="px-2 py-2">
                        <span class="inline-flex items-center gap-1">
                          <span class="h-2.5 w-2.5 rounded-full border border-slate-200" :class="getColorSwatchClass(item.color)" />
                          {{ item.color }}
                        </span>
                      </td>
                      <td class="px-2 py-2">{{ formatBlank(item.pigment_no) }}</td>
                      <td class="px-2 py-2 text-right tabular-nums">{{ item.shoot_qty }}</td>
                      <td class="px-2 py-2 tabular-nums">{{ formatBlank(item.completion_time) }}</td>
                    </tr>
                    <tr>
                      <td colspan="8" class="px-2 py-2 text-center text-[11px] font-medium text-slate-400">
                        + 继续添加明细行
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>
          </div>

          <aside class="space-y-4">
            <section class="rounded-lg border border-slate-200 bg-white p-4">
              <div class="mb-3 flex items-center gap-2">
                <Send class="size-4 text-slate-400" aria-hidden="true" />
                <span class="text-[13px] font-bold">提交动作</span>
              </div>
              <div class="space-y-2 text-[11px] text-slate-500">
                <div class="flex justify-between"><span>当前厂区</span><strong class="text-slate-800">{{ activeFactory.shortName }}</strong></div>
                <div class="flex justify-between"><span>提交人</span><strong class="text-slate-800">{{ selectedOrder.eng_name }}</strong></div>
                <div class="flex justify-between"><span>下一节点</span><strong class="text-slate-800">待审核</strong></div>
              </div>
              <div class="mt-3 rounded-lg bg-slate-50 p-2.5 text-[11px] text-slate-500">
                开单后进入现有流程：待审核 → 待经理审核 → 待生产 → 生产中 → 已完成。
              </div>
              <button class="mt-3 flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-slate-900 text-[13px] font-semibold text-white hover:bg-slate-700">
                <Send class="size-4" aria-hidden="true" />
                提交主管审核
              </button>
              <button class="mt-2 flex h-9 w-full items-center justify-center gap-1.5 rounded-lg border border-slate-200 text-[12px] font-medium text-slate-600 hover:border-slate-300">
                保存草稿
              </button>
            </section>

            <section class="rounded-lg border border-teal-200 bg-teal-50 p-4">
              <div class="flex items-center gap-2 text-teal-800">
                <Factory class="size-4" aria-hidden="true" />
                <span class="text-[13px] font-bold">啤机部通知</span>
              </div>
              <p class="mt-2 text-[11px] leading-5 text-teal-700">
                内部生产单提交后会在“啤办生产任务单”收到通知；审核走完后，啤机部才能开始执行并回传完成。
              </p>
              <RouterLink
                :to="productionTaskRoute"
                class="mt-3 inline-flex h-8 items-center gap-1.5 rounded-lg border border-teal-200 bg-white px-2.5 text-[12px] font-semibold text-teal-700"
              >
                打开生产任务单
                <ExternalLink class="size-3.5" aria-hidden="true" />
              </RouterLink>
            </section>
          </aside>
        </div>
      </section>

      <section v-else class="space-y-4">
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
              <p class="text-[11px] text-slate-400">保持现有状态机：待审核 → 待经理审核 → 待生产 → 生产中 → 已完成</p>
            </div>
            <span class="rounded-full border px-2 py-0.5 text-[11px] font-bold" :class="getStatusBadgeClass(selectedOrder.status)">
              {{ selectedCompletionGate.message }}
            </span>
          </div>

          <div class="grid gap-2 md:grid-cols-5">
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
              <div class="flex items-center gap-2 border-b border-slate-100 px-4 py-2.5">
                <Table2 class="size-4 text-slate-400" aria-hidden="true" />
                <span class="text-[13px] font-bold">模具明细</span>
                <span class="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-500">{{ selectedItems.length }} 项</span>
              </div>
              <div class="overflow-x-auto">
                <table class="w-full min-w-[920px] text-[12px]">
                  <thead>
                    <tr class="border-b border-slate-100 bg-slate-50 text-[11px] text-slate-500">
                      <th class="w-8 px-2 py-2 font-medium">#</th>
                      <th class="px-2 py-2 text-left font-medium">模具号</th>
                      <th class="px-2 py-2 text-left font-medium">名称</th>
                      <th class="px-2 py-2 text-left font-medium">原料</th>
                      <th class="px-2 py-2 text-left font-medium">颜色 / PMS</th>
                      <th class="px-2 py-2 text-right font-medium">预计用料</th>
                      <th class="px-2 py-2 text-right font-medium">实际用料</th>
                      <th class="px-2 py-2 text-right font-medium">费用</th>
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
                      <td class="px-2 py-1.5 text-right tabular-nums">{{ formatWeight(item.actual_weight_kg) }}</td>
                      <td class="px-2 py-1.5 text-right tabular-nums">{{ formatMoney(item.actual_amount_hkd) }}</td>
                      <td class="px-2 py-1.5">
                        <span class="rounded-full border px-2 py-0.5 text-[10px] font-bold" :class="getItemStateClass(item)">
                          {{ getItemState(item) }}
                        </span>
                      </td>
                    </tr>
                    <tr v-if="selectedItems.length > detailRows.length">
                      <td colspan="9" class="px-2 py-2 text-center text-[11px] font-medium text-slate-400">
                        还有 {{ selectedItems.length - detailRows.length }} 项明细，滚动后续详情视图继续查看
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>

            <section class="rounded-lg border border-slate-200 bg-white p-4">
              <div class="mb-1.5 flex items-center gap-2">
                <MessageSquareText class="size-4 text-slate-400" aria-hidden="true" />
                <span class="text-[13px] font-bold">开单事由</span>
              </div>
              <p class="text-[12.5px] text-slate-600">{{ selectedOrder.reason }}</p>
            </section>
          </div>

          <aside class="space-y-4">
            <section
              class="rounded-lg border-2 p-4"
              :class="selectedOrder.status === '待审核' || selectedOrder.status === '待经理审核' ? 'border-amber-200 bg-amber-50/50' : 'border-slate-200 bg-white'"
            >
              <div class="flex items-center gap-2">
                <Gavel class="size-4 text-amber-600" aria-hidden="true" />
                <span class="text-[13px] font-bold" :class="selectedOrder.status === '待审核' || selectedOrder.status === '待经理审核' ? 'text-amber-800' : 'text-slate-800'">
                  {{ selectedOrder.status === '待审核' ? `${selectedOrder.supervisor} · 待审核` : selectedOrder.status === '待经理审核' ? '王经理 · 待审核' : '当前无需工程审核' }}
                </span>
              </div>
              <p class="mt-1 text-[11px]" :class="selectedOrder.status === '待审核' || selectedOrder.status === '待经理审核' ? 'text-amber-700' : 'text-slate-500'">
                {{ selectedOrder.status === '待审核' ? '核对单头、明细、交期后执行操作。通过后进入待经理审核。' : selectedOrder.status === '待经理审核' ? '经理终审通过后，内部单进入待生产；外厂 / 模厂路径直接完成。' : '该单据当前处于后续生产或归档节点。' }}
              </p>
              <textarea rows="2" placeholder="审核意见（驳回必填）..." class="mt-3 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[12px] outline-none focus:border-slate-400" />
              <div class="mt-2 flex gap-2">
                <button class="flex h-10 flex-1 items-center justify-center gap-1.5 rounded-lg bg-emerald-600 text-[13px] font-semibold text-white hover:bg-emerald-500">
                  <Check class="size-4" aria-hidden="true" />
                  通过
                </button>
                <button class="flex h-10 flex-1 items-center justify-center gap-1.5 rounded-lg bg-red-600 text-[13px] font-semibold text-white hover:bg-red-500">
                  <X class="size-4" aria-hidden="true" />
                  驳回
                </button>
              </div>
              <div class="mt-2 flex items-center gap-1.5 text-[10px] text-slate-500">
                <Lock class="size-3" aria-hidden="true" />
                审核仍沿用现有 PIN 与审计规则。
              </div>
            </section>

            <section class="rounded-lg border border-slate-200 bg-white p-4">
              <div class="mb-3 flex items-center gap-2">
                <History class="size-4 text-slate-400" aria-hidden="true" />
                <span class="text-[13px] font-bold">审核轨迹</span>
              </div>
              <ol class="relative space-y-4 border-l border-slate-200 pl-4">
                <li v-for="log in selectedRecord.audit_logs" :key="log.id" class="relative">
                  <span class="absolute -left-[21px] top-0.5 flex h-3.5 w-3.5 rounded-full bg-teal-400 ring-4 ring-white" />
                  <div class="text-[12px] font-semibold">{{ log.action }}</div>
                  <div class="text-[11px] text-slate-400">{{ log.actor_name }} · {{ log.actor_role }} · {{ log.created_at }}</div>
                  <div class="mt-1 rounded-md bg-slate-50 px-2 py-1 text-[11px] text-slate-500">{{ log.reason }}</div>
                </li>
                <li v-if="!selectedRecord.audit_logs.length" class="relative">
                  <span class="absolute -left-[21px] top-0.5 flex h-3.5 w-3.5 rounded-full bg-slate-200 ring-4 ring-white" />
                  <div class="text-[12px] font-semibold text-slate-400">暂无轨迹</div>
                </li>
              </ol>
            </section>
          </aside>
        </div>
      </section>
    </div>
  </main>
</template>
