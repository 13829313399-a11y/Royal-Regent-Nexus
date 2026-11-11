<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  ClipboardList,
  Container,
  FileSpreadsheet,
  FileText,
  Gauge,
  Search,
  ShieldCheck,
  Truck,
} from '@lucide/vue'
import StatusPill from '@/components/common/StatusPill.vue'
import type { ShipmentStatus, ShippingFactoryProfile, ShipmentTask } from './contracts'
import {
  cbmText,
  documentCompletion,
  documentStageMeta,
  hoursUntil,
  isUrgentCutoff,
  qcStateMeta,
  relativeDayText,
  shipmentModeMeta,
  shipmentStatusMeta,
  shippingTotals,
  taskDocuments,
} from './contracts'

const props = defineProps<{ profile: ShippingFactoryProfile }>()
const emit = defineEmits<{ notify: [message: string] }>()

const filters: Array<{ id: 'all' | ShipmentStatus; label: string }> = [
  { id: 'all', label: '全部' },
  { id: 'review', label: '待复核' },
  { id: 'shipment', label: '待走货' },
  { id: 'waiting', label: '等待通知' },
  { id: 'completed', label: '已完成' },
]

const query = ref('')
const activeStatus = ref<'all' | ShipmentStatus>('all')
const selectedId = ref('')

const visibleTasks = computed(() => {
  const keyword = query.value.trim().toLowerCase()
  return props.profile.tasks.filter((task) => {
    if (activeStatus.value !== 'all' && task.status !== activeStatus.value) return false
    if (!keyword) return true
    return [task.batchNo, task.customer, task.so, task.containerType, task.warehouse, task.coordinator, task.port]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(keyword))
  })
})

const selectedTask = computed<ShipmentTask | null>(() => {
  const tasks = visibleTasks.value
  return tasks.find((task) => task.id === selectedId.value) ?? tasks[0] ?? null
})

watch(
  () => [props.profile.factoryId, activeStatus.value, query.value],
  () => {
    selectedId.value = visibleTasks.value[0]?.id ?? ''
  },
)

const kpis = computed(() => {
  const tasks = props.profile.tasks
  const open = tasks.filter((task) => !['completed', 'cancelled'].includes(task.status))
  return [
    {
      id: 'review',
      label: '待复核',
      value: tasks.filter((task) => task.status === 'review').length,
      hint: '核对明细与分类后进入待走货',
      icon: ClipboardList,
      tone: 'amber',
    },
    {
      id: 'shipment',
      label: '待走货',
      value: tasks.filter((task) => task.status === 'shipment').length,
      hint: '含整柜与交仓任务',
      icon: Truck,
      tone: 'blue',
    },
    {
      id: 'urgent',
      label: '48 小时内截关',
      value: open.filter((task) => isUrgentCutoff(task)).length,
      hint: '截关临近，优先核对放行',
      icon: AlertTriangle,
      tone: 'red',
    },
    {
      id: 'completed',
      label: '已完成',
      value: tasks.filter((task) => task.status === 'completed').length,
      hint: '库存回写闭环的任务',
      icon: CheckCircle2,
      tone: 'green',
    },
  ] as const
})

const gates = computed(() => {
  const task = selectedTask.value
  if (!task) return []
  const cutoffHours = hoursUntil(task.cutoff)
  return [
    {
      id: 'ship',
      label: '装船 / 出货日',
      value: task.shipDate ? `${task.shipDate}` : '待客户通知',
      hint: task.shipDate ? relativeDayText(task.shipDate) : '收到通知后补计划日',
      tone: 'teal' as const,
      icon: Container,
    },
    {
      id: 'si',
      label: 'SI 截止',
      value: task.siDeadline || '待确认',
      hint: task.siDeadline ? '截补料，早于截关' : '等待货代通知',
      tone: 'blue' as const,
      icon: CalendarClock,
    },
    {
      id: 'cutoff',
      label: '截关 / 截数期',
      value: task.cutoff || '待确认',
      hint:
        cutoffHours === null
          ? '等待船期确认'
          : cutoffHours < 0
            ? '截关已过，需确认是否已进闸'
            : `剩余约 ${Math.max(0, Math.round(cutoffHours))} 小时`,
      tone: (cutoffHours !== null && cutoffHours <= 48 ? 'amber' : 'slate') as 'amber' | 'slate',
      icon: AlertTriangle,
    },
    {
      id: 'delivery',
      label: task.mode === 'warehouse' ? '交仓日期' : '到仓 / 装柜',
      value: task.deliveryDate || (task.mode === 'warehouse' ? '待预约' : '柜内直送'),
      hint: task.warehouse || task.mainFactory,
      tone: 'slate' as const,
      icon: Truck,
    },
  ]
})

const totals = computed(() => (selectedTask.value ? shippingTotals(selectedTask.value) : null))
const documentStats = computed(() => documentCompletion(props.profile.tasks))
const selectedDocuments = computed(() => (selectedTask.value ? taskDocuments(selectedTask.value) : null))

/**
 * 船务日常的四类单据作业：按 SO 出货表、补料（SI）、舱单和通关一体化资料。
 * 当前是界面预览，点击只给出明确提示，不生成文件、不写业务库。
 */
const quickActions = [
  { id: 'so-export', title: 'SO排出货表', hint: '按 SO 汇总待出运明细', icon: FileSpreadsheet },
  { id: 'si-supplement', title: '补料', hint: 'SI 截止前补料与截补料提醒', icon: CalendarClock },
  { id: 'manifest', title: '舱单', hint: '舱单资料与发送记录', icon: FileText },
  { id: 'customs-pack', title: '通关一体化资料', hint: '报关单 / 装箱单 / 发票', icon: ShieldCheck },
]

function runQuickAction(action: (typeof quickActions)[number]) {
  const so = selectedTask.value?.so
  preview(`${action.title}${so ? `（当前 SO ${so}）` : ''}`)
}

function selectTask(id: string) {
  selectedId.value = id
}

function statusMeta(task: ShipmentTask) {
  return shipmentStatusMeta[task.status]
}

function modeMeta(task: ShipmentTask) {
  return shipmentModeMeta[task.mode]
}

function shortDate(value: string) {
  if (!value) return '待定'
  return value.slice(5, 10).replace('-', '/')
}

function cutHint(task: ShipmentTask) {
  const hours = hoursUntil(task.cutoff)
  if (hours === null) return '待确认截关'
  if (hours < 0) return '截关已过'
  if (hours <= 48) return `${Math.max(0, Math.round(hours))} 小时后截关`
  return relativeDayText(task.cutoff)
}

function preview(message: string) {
  emit('notify', `界面预览：${message}尚未接入后端接口。`)
}
</script>

<template>
  <div class="space-y-4">
    <section aria-label="船务任务概览" class="grid grid-cols-2 gap-3 xl:grid-cols-4">
      <article
        v-for="item in kpis"
        :key="item.id"
        class="rounded-xl border border-slate-200 bg-white p-3 sm:p-4 shadow-[0_1px_2px_rgba(15,23,42,0.03)]"
      >
        <div class="flex items-start justify-between gap-3">
          <div>
            <p class="text-[11px] font-semibold tracking-wide text-slate-500">{{ item.label }}</p>
            <p class="mt-2 text-2xl font-semibold leading-none text-slate-950 tabular-nums sm:text-3xl">{{ item.value }}</p>
          </div>
          <span
            class="flex size-9 shrink-0 items-center justify-center rounded-xl"
            :class="{
              'bg-amber-50 text-amber-700': item.tone === 'amber',
              'bg-blue-50 text-blue-700': item.tone === 'blue',
              'bg-red-50 text-red-700': item.tone === 'red',
              'bg-emerald-50 text-emerald-700': item.tone === 'green',
            }"
            aria-hidden="true"
          >
            <component :is="item.icon" class="size-4" />
          </span>
        </div>
        <div v-if="item.id === 'completed'" class="mt-2 flex flex-wrap gap-1" aria-label="单据完成情况">
          <span class="rounded-full bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700 ring-1 ring-inset ring-emerald-200/70">
            SO已完成 {{ documentStats.so }}
          </span>
          <span class="rounded-full bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700 ring-1 ring-inset ring-emerald-200/70">
            补料已完成 {{ documentStats.supplement }}
          </span>
          <span class="rounded-full bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700 ring-1 ring-inset ring-emerald-200/70">
            舱单已完成 {{ documentStats.manifest }}
          </span>
        </div>
        <p v-else class="mt-2 text-[11px] leading-4 text-slate-400">{{ item.hint }}</p>
      </article>
    </section>

    <section
      class="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2.5 shadow-[0_1px_2px_rgba(15,23,42,0.03)]"
      aria-label="船务快捷作业"
    >
      <p class="mr-1 text-[11px] font-semibold text-slate-500">快捷作业</p>
      <button
        v-for="action in quickActions"
        :key="action.id"
        type="button"
        class="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-left transition hover:border-teal-200 hover:bg-teal-50/45 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-500"
        @click="runQuickAction(action)"
      >
        <span class="flex size-7 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-600" aria-hidden="true">
          <component :is="action.icon" class="size-3.5" />
        </span>
        <span class="min-w-0">
          <span class="block text-[12px] font-semibold leading-4 text-slate-800">{{ action.title }}</span>
          <span class="block text-[10.5px] leading-4 text-slate-500">{{ action.hint }}</span>
        </span>
      </button>
      <span class="ml-auto hidden text-[10.5px] text-slate-400 sm:inline">
        当前 SO：<b class="tabular-nums text-slate-600">{{ selectedTask?.so || '未选择任务' }}</b>
      </span>
    </section>

    <div class="grid gap-4 lg:grid-cols-[minmax(0,360px)_minmax(0,1fr)]">
      <section class="enterprise-panel flex min-w-0 flex-col rounded-xl" aria-label="走柜任务列表">
        <div class="space-y-3 border-b border-slate-100 px-4 py-4">
          <label class="relative block">
            <span class="sr-only">搜索任务</span>
            <Search class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
            <input
              v-model="query"
              type="search"
              placeholder="批次号、客户、SO、柜型…"
              class="h-9 w-full rounded-lg border border-slate-200 bg-slate-50 pl-9 pr-3 text-[13px] text-slate-800 outline-none transition focus:border-teal-500 focus:bg-white focus:ring-3 focus:ring-teal-500/15"
            >
          </label>
          <div class="flex flex-wrap gap-1.5" role="group" aria-label="按状态筛选">
            <button
              v-for="filter in filters"
              :key="filter.id"
              type="button"
              class="rounded-full border px-2.5 py-1 text-[11px] font-semibold transition"
              :class="activeStatus === filter.id
                ? 'border-teal-600 bg-teal-700 text-white'
                : 'border-slate-200 bg-white text-slate-600 hover:border-teal-200 hover:text-teal-800'"
              :aria-pressed="activeStatus === filter.id"
              @click="activeStatus = filter.id"
            >
              {{ filter.label }}
            </button>
          </div>
          <p class="text-[11px] text-slate-400" role="status" aria-live="polite">
            共 {{ visibleTasks.length }} 个任务 · {{ profile.label }}船务目录
          </p>
        </div>

        <div class="max-h-[720px] flex-1 space-y-2 overflow-y-auto p-3">
          <button
            v-for="task in visibleTasks"
            :key="task.id"
            type="button"
            class="w-full rounded-xl border p-3 text-left transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-500"
            :class="selectedTask?.id === task.id
              ? 'border-teal-300 bg-teal-50/45 shadow-[0_8px_24px_-22px_rgba(13,148,136,0.65)]'
              : 'border-slate-200 bg-white hover:border-teal-200 hover:bg-slate-50/70'"
            :aria-pressed="selectedTask?.id === task.id"
            @click="selectTask(task.id)"
          >
            <div class="flex items-start justify-between gap-2">
              <div class="min-w-0">
                <p class="flex items-center gap-1.5 text-[13px] font-bold text-slate-950">
                  <span class="tabular-nums">{{ task.batchNo }}</span>
                  <span class="truncate font-medium text-slate-600">{{ task.customer }}</span>
                </p>
                <p class="mt-1 truncate text-[11px] text-slate-500">
                  {{ task.so || '待定 SO' }} · {{ task.containerType || task.warehouse }}
                </p>
              </div>
              <StatusPill :label="statusMeta(task).label" :tone="statusMeta(task).tone" compact />
            </div>
            <div class="mt-2 flex items-center justify-between gap-2 text-[11px] text-slate-500">
              <span class="inline-flex items-center gap-1">
                <component
                  :is="task.mode === 'container' ? Container : Truck"
                  class="size-3.5 text-slate-400"
                  aria-hidden="true"
                />
                {{ modeMeta(task).label }} · {{ task.port }}
              </span>
              <span
                class="tabular-nums"
                :class="isUrgentCutoff(task) ? 'font-semibold text-amber-700' : ''"
              >
                {{ shortDate(task.shipDate) }} → {{ cutHint(task) }}
              </span>
            </div>
            <p v-if="isUrgentCutoff(task)" class="mt-1.5 inline-flex items-center gap-1 text-[11px] font-semibold text-amber-700">
              <AlertTriangle class="size-3.5" aria-hidden="true" />截关临近，优先处理
            </p>
          </button>

          <p v-if="!visibleTasks.length" class="rounded-xl border border-dashed border-slate-200 px-4 py-10 text-center text-[12px] text-slate-500" role="status">
            没有匹配的任务。调整状态或搜索条件后再试。
          </p>
        </div>
      </section>

      <section v-if="selectedTask" class="enterprise-panel min-w-0 rounded-xl" aria-label="任务详情">
        <header class="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
          <div class="min-w-0">
            <p class="flex flex-wrap items-center gap-2">
              <span class="text-[11px] font-bold uppercase tracking-[0.16em] text-teal-700">Shipment Task</span>
              <StatusPill :label="statusMeta(selectedTask).label" :tone="statusMeta(selectedTask).tone" compact />
              <StatusPill :label="modeMeta(selectedTask).label" :tone="modeMeta(selectedTask).tone" compact />
            </p>
            <h2 class="mt-1.5 flex flex-wrap items-baseline gap-2 text-lg font-semibold tracking-[-0.02em] text-slate-950">
              <span class="tabular-nums">{{ selectedTask.batchNo }}</span>
              <span>{{ selectedTask.customer }}</span>
              <span class="text-sm font-medium text-slate-500">{{ selectedTask.so || '待定 SO' }}</span>
            </h2>
            <p class="mt-1 text-[12px] text-slate-500">
              {{ selectedTask.mainFactory }} · {{ selectedTask.containerType || selectedTask.warehouse }}
              · 负责人 {{ selectedTask.coordinator }} · 更新 {{ selectedTask.updatedAt }}
            </p>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <button
              type="button"
              class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-700 transition hover:border-teal-200 hover:text-teal-800"
              @click="preview('导出走柜表')"
            >
              <FileSpreadsheet class="size-4" aria-hidden="true" />导出走柜表
            </button>
            <button
              type="button"
              class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-700 transition hover:border-teal-200 hover:text-teal-800"
              @click="preview('库存回写')"
            >
              <Gauge class="size-4" aria-hidden="true" />库存回写
            </button>
            <button
              type="button"
              class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-teal-700 px-3.5 text-[12px] font-semibold text-white shadow-sm transition hover:bg-teal-800"
              @click="preview('推进任务状态')"
            >
              <ArrowRight class="size-4" aria-hidden="true" />推进状态
            </button>
          </div>
        </header>

        <div class="space-y-5 p-5">
          <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <article
              v-for="gate in gates"
              :key="gate.id"
              class="surface-subtle rounded-xl px-3.5 py-3"
            >
              <p class="flex items-center gap-1.5 text-[11px] font-semibold text-slate-500">
                <component :is="gate.icon" class="size-3.5 text-slate-400" aria-hidden="true" />
                {{ gate.label }}
              </p>
              <p class="mt-1.5 text-[13px] font-bold tabular-nums text-slate-950">{{ gate.value }}</p>
              <p
                class="mt-1 text-[11px] leading-4"
                :class="gate.tone === 'amber' ? 'font-semibold text-amber-700' : 'text-slate-500'"
              >
                {{ gate.hint }}
              </p>
            </article>
          </div>

          <div class="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-slate-50/60 px-3.5 py-2.5">
            <span class="text-[11px] font-semibold text-slate-500">就绪检查</span>
            <StatusPill :label="qcStateMeta[selectedTask.readiness.qc].label" :tone="qcStateMeta[selectedTask.readiness.qc].tone" compact />
            <StatusPill
              :label="selectedTask.readiness.inventory === 'confirmed' ? '库存已确认' : '库存待确认'"
              :tone="selectedTask.readiness.inventory === 'confirmed' ? 'green' : 'amber'"
              compact
            />
            <StatusPill
              :label="selectedTask.readiness.missingWeights ? `缺重量 ${selectedTask.readiness.missingWeights} 行` : '重量齐全'"
              :tone="selectedTask.readiness.missingWeights ? 'red' : 'green'"
              compact
            />
            <span class="ml-auto text-[11px] text-slate-400">就绪提示不阻塞建任务与制表</span>
          </div>

          <div
            v-if="selectedDocuments"
            class="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2.5"
            aria-label="单据进度"
          >
            <span class="text-[11px] font-semibold text-slate-500">单据进度</span>
            <span class="inline-flex items-center gap-1.5 text-[11px] text-slate-600">
              SO排出货表
              <StatusPill :label="documentStageMeta[selectedDocuments.so].label" :tone="documentStageMeta[selectedDocuments.so].tone" compact />
            </span>
            <span class="inline-flex items-center gap-1.5 text-[11px] text-slate-600">
              补料
              <StatusPill :label="documentStageMeta[selectedDocuments.supplement].label" :tone="documentStageMeta[selectedDocuments.supplement].tone" compact />
            </span>
            <span class="inline-flex items-center gap-1.5 text-[11px] text-slate-600">
              舱单
              <StatusPill :label="documentStageMeta[selectedDocuments.manifest].label" :tone="documentStageMeta[selectedDocuments.manifest].tone" compact />
            </span>
          </div>

          <div class="min-w-0">
            <div class="mb-2 flex items-center justify-between gap-3">
              <h3 class="text-[13px] font-semibold text-slate-950">出货明细</h3>
              <span class="text-[11px] text-slate-500">共 {{ selectedTask.items.length }} 行</span>
            </div>
            <div class="overflow-x-auto rounded-xl border border-slate-200">
              <table class="w-full min-w-[820px] border-collapse text-left text-[12px]">
                <thead class="bg-slate-50 text-[11px] font-semibold text-slate-500">
                  <tr>
                    <th scope="col" class="px-3 py-2">货号 / 品名</th>
                    <th scope="col" class="px-3 py-2">合同号</th>
                    <th scope="col" class="px-3 py-2">客 PO</th>
                    <th scope="col" class="px-3 py-2 text-right">件数</th>
                    <th scope="col" class="px-3 py-2 text-right">数量</th>
                    <th scope="col" class="px-3 py-2 text-right">CBM</th>
                    <th scope="col" class="px-3 py-2 text-right">卡板</th>
                    <th scope="col" class="px-3 py-2">验货</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                  <tr v-for="item in selectedTask.items" :key="item.id" class="bg-white">
                    <td class="px-3 py-2">
                      <p class="font-semibold text-slate-900 tabular-nums">{{ item.productCode }}</p>
                      <p class="text-[11px] text-slate-500">{{ item.productName }}</p>
                    </td>
                    <td class="px-3 py-2 tabular-nums text-slate-600">{{ item.contractNo }}</td>
                    <td class="px-3 py-2 tabular-nums text-slate-600">{{ item.customerPo }}</td>
                    <td class="px-3 py-2 text-right tabular-nums text-slate-800">{{ item.pieces }}</td>
                    <td class="px-3 py-2 text-right tabular-nums text-slate-800">{{ item.quantity }}</td>
                    <td class="px-3 py-2 text-right tabular-nums text-slate-800">{{ cbmText(item.cbm) }}</td>
                    <td class="px-3 py-2 text-right tabular-nums text-slate-800">{{ item.pallets }}</td>
                    <td class="px-3 py-2">
                      <StatusPill
                        :label="item.weightMissing ? '缺每箱毛重' : qcStateMeta[item.qc].label"
                        :tone="item.weightMissing ? 'red' : qcStateMeta[item.qc].tone"
                        compact
                      />
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div class="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
            <div class="surface-subtle rounded-xl px-4 py-3">
              <p class="text-[11px] font-semibold text-slate-500">特殊要求</p>
              <p class="mt-1 text-[12px] leading-5 text-slate-700">{{ selectedTask.special }}</p>
            </div>
            <dl class="grid grid-cols-2 gap-x-4 gap-y-1 text-[12px] sm:grid-cols-4" aria-label="任务合计">
              <div>
                <dt class="text-[11px] text-slate-500">合计件数</dt>
                <dd class="font-semibold tabular-nums text-slate-900">{{ totals?.pieces ?? 0 }}</dd>
              </div>
              <div>
                <dt class="text-[11px] text-slate-500">合计数量</dt>
                <dd class="font-semibold tabular-nums text-slate-900">{{ totals?.quantity ?? 0 }}</dd>
              </div>
              <div>
                <dt class="text-[11px] text-slate-500">合计 CBM</dt>
                <dd class="font-semibold tabular-nums text-slate-900">{{ cbmText(totals?.cbm ?? 0) }}</dd>
              </div>
              <div>
                <dt class="text-[11px] text-slate-500">合计卡板</dt>
                <dd class="font-semibold tabular-nums text-slate-900">{{ totals?.pallets ?? 0 }}</dd>
              </div>
            </dl>
          </div>
        </div>
      </section>

      <section v-else class="grid min-h-[320px] place-items-center rounded-xl border border-dashed border-slate-200 bg-white p-8 text-center">
        <div>
          <p class="text-[13px] font-semibold text-slate-800">选择左侧任务查看时间闸门与出货明细</p>
          <p class="mt-1 text-[12px] text-slate-500">当前筛选下没有可展示的任务。</p>
        </div>
      </section>
    </div>
  </div>
</template>
