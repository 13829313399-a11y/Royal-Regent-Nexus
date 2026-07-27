<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  Activity,
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  CircleGauge,
  ClockArrowDown,
  Factory,
  History,
  LoaderCircle,
  LockKeyhole,
  Moon,
  Play,
  RefreshCw,
  Route,
  Sparkles,
  Sun,
} from '@lucide/vue'
import type { InjectionOrderPriority } from '@/types/injectionSchedule'

export type Phase4ReplanTriggerType = 'urgent_order' | 'machine_downtime'
export type Phase4ShiftCode = 'day' | 'night'

export interface Phase4VersionView {
  id: string
  versionNo: number
  revision: number
  status: 'draft' | 'published' | 'superseded'
  businessDate: string
}

export interface Phase4OrderOption {
  id: string
  orderNo: string
  productName: string
  outstandingQty: number
  producedQty: number
  revision: number
  priorityCode: InjectionOrderPriority
  priorityFlag: string
  estimatedFinishAt?: string | null
}

export interface Phase4MachineOption {
  id: string
  machineCode: string
  machineName: string
  status: string
}

export interface Phase4TaskOption {
  id: string
  orderId: string
  orderNo: string
  productName: string
  machineId: string
  machineCode: string
  plannedQty: number
  plannedFinishAt: string
  locked: boolean
  protected: boolean
  executionStatus: string
}

export interface Phase4ActualView {
  id: string
  orderId: string
  orderNo: string
  machineCode: string
  shiftDate: string
  shiftCode: Phase4ShiftCode
  source: 'manual' | 'workbook'
  legacyShiftCode: '' | 'A' | 'B'
  actualQty: number
  cumulativeProducedQty: number
  outstandingQty: number
  estimatedFinishAt: string | null
  createdByName: string
  createdAt: string
  reason: string
  revision: number
  correctionCount: number
  correctedByName: string
  correctedAt: string
  canCorrect: boolean
}

export interface Phase4RunView {
  id: string
  runType: 'auto_draft' | 'local_replan'
  status: 'previewed' | 'applied'
  triggerType: string
  reason: string
  affectedMachineCount: number
  affectedTaskCount: number
  movedTaskCount: number
  createdAt: string
  createdByName: string
  explanations: string[]
}

export interface Phase4ImpactView {
  id: string
  orderNo: string
  machineCode: string
  beforeFinishAt: string
  afterFinishAt: string
  etaShiftMinutes: number
  deliverySlackBeforeHours: number | null
  deliverySlackAfterHours: number | null
  shortageQty: number
}

export interface Phase4SkippedView {
  id: string
  label: string
  status: 'unknown' | 'fail'
  reason: string
}

export interface Phase4BarrierView {
  id: string
  label: string
  reason: string
}

export interface Phase4AutoDraftRequestView {
  reason: string
  horizonEndAt: string
}

export interface Phase4ReplanRequestView {
  triggerType: Phase4ReplanTriggerType
  orderId: string
  machineId: string
  downtimeStartAt: string
  downtimeEndAt: string
  freezeBeforeAt: string
  maxAffectedMachines: number
  maxAffectedTasks: number
  reason: string
}

export interface Phase4ActualRequestView {
  taskId: string
  shiftDate: string
  shiftCode: Phase4ShiftCode
  actualQty: number
  reason: string
}

export interface Phase4ActualCorrectionRequestView extends Phase4ActualRequestView {
  actualId: string
  actualRevision: number
}

const props = defineProps<{
  version: Phase4VersionView | null
  orders: Phase4OrderOption[]
  machines: Phase4MachineOption[]
  tasks: Phase4TaskOption[]
  actuals: Phase4ActualView[]
  lastRun: Phase4RunView | null
  impacts: Phase4ImpactView[]
  skipped: Phase4SkippedView[]
  barriers: Phase4BarrierView[]
  lastActualReplay: boolean
  canAutomate: boolean
  canWriteActuals: boolean
  busy: boolean
  actualsLoading: boolean
  error?: string
}>()

const emit = defineEmits<{
  'generate-auto-draft': [input: Phase4AutoDraftRequestView]
  'run-replan': [input: Phase4ReplanRequestView]
  'write-actual': [input: Phase4ActualRequestView]
  'correct-actual': [input: Phase4ActualCorrectionRequestView]
  'reload-actuals': []
}>()

const autoDraftReason = ref('')
const autoDraftHorizonEndAt = ref('')
const urgentOrderSearch = ref('')
const replanTriggerType = ref<Phase4ReplanTriggerType>('urgent_order')
const replanOrderId = ref('')
const replanMachineId = ref('')
const downtimeStartAt = ref('')
const downtimeEndAt = ref('')
const freezeBeforeAt = ref('')
const maxAffectedMachines = ref(8)
const maxAffectedTasks = ref(120)
const replanReason = ref('')
const actualTaskId = ref('')
const actualTaskSearch = ref('')
const actualShiftDate = ref('')
const actualShiftCode = ref<Phase4ShiftCode>('day')
const actualQty = ref<number | null>(null)
const actualReason = ref('')
const correctionActualId = ref('')
const correctionActualRevision = ref(0)
const localError = ref('')

const priorityRank: Record<InjectionOrderPriority, number> = {
  P0: 0,
  P1: 1,
  P2: 2,
  P3: 3,
}

const urgentOrders = computed(() => [...props.orders]
  .filter((order) => order.outstandingQty > 0)
  .sort((left, right) => {
    return priorityRank[left.priorityCode] - priorityRank[right.priorityCode]
      || right.outstandingQty - left.outstandingQty
  }))

const writableTasks = computed(() => props.tasks.filter((task) => (
  !/completed|cancelled/i.test(task.executionStatus)
)))
const visibleUrgentOrders = computed(() => {
  const query = urgentOrderSearch.value.trim().toLocaleLowerCase('zh-CN')
  return urgentOrders.value
    .filter((order) => (
      !query
      || order.orderNo.toLocaleLowerCase('zh-CN').includes(query)
      || order.productName.toLocaleLowerCase('zh-CN').includes(query)
    ))
    .slice(0, 120)
})
const visibleWritableTasks = computed(() => {
  const query = actualTaskSearch.value.trim().toLocaleLowerCase('zh-CN')
  return writableTasks.value
    .filter((task) => (
      !query
      || task.orderNo.toLocaleLowerCase('zh-CN').includes(query)
      || task.productName.toLocaleLowerCase('zh-CN').includes(query)
      || task.machineCode.toLocaleLowerCase('zh-CN').includes(query)
    ))
    .slice(0, 160)
})
const visibleActuals = computed(() => props.actuals.slice(0, 200))
const visibleBarriers = computed(() => props.barriers.slice(0, 120))
const visibleSkipped = computed(() => props.skipped.slice(0, 120))
const visibleImpacts = computed(() => props.impacts.slice(0, 160))
const selectedActualTask = computed(() => (
  props.tasks.find((task) => task.id === actualTaskId.value) ?? null
))
const selectedActualOrder = computed(() => {
  const task = selectedActualTask.value
  return task
    ? props.orders.find((order) => order.id === task.orderId) ?? null
    : null
})

const totalActualQty = computed(() => props.actuals.reduce(
  (total, actual) => total + actual.actualQty,
  0,
))
const rollingOutstandingQty = computed(() => props.orders.reduce(
  (total, order) => total + Math.max(order.outstandingQty, 0),
  0,
))
const delayedProjectionCount = computed(() => props.impacts.filter((impact) => (
  impact.deliverySlackAfterHours != null
  && impact.deliverySlackAfterHours < 0
)).length)

watch(
  () => props.version?.id,
  () => {
    localError.value = ''
    if (!actualShiftDate.value) {
      actualShiftDate.value = props.version?.businessDate ?? ''
    }
  },
  { immediate: true },
)

watch(
  () => props.actuals.find((actual) => actual.id === correctionActualId.value)?.revision,
  (revision) => {
    if (
      correctionActualId.value
      && revision != null
      && revision !== correctionActualRevision.value
    ) {
      correctionActualId.value = ''
      correctionActualRevision.value = 0
      actualQty.value = null
      actualReason.value = ''
    }
  },
)

watch(visibleUrgentOrders, (orders) => {
  if (!orders.some((order) => order.id === replanOrderId.value)) {
    replanOrderId.value = orders[0]?.id ?? ''
  }
}, { immediate: true })

watch(visibleWritableTasks, (tasks) => {
  if (!tasks.some((task) => task.id === actualTaskId.value)) {
    actualTaskId.value = tasks[0]?.id ?? ''
  }
}, { immediate: true })

watch(
  () => props.machines,
  (machines) => {
    if (!machines.some((machine) => machine.id === replanMachineId.value)) {
      replanMachineId.value = machines[0]?.id ?? ''
    }
  },
  { immediate: true },
)

function normalizedDateTime(value: string) {
  if (!value) return ''
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? '' : parsed.toISOString()
}

function requireEditableDraft() {
  if (!props.version || props.version.status !== 'draft') {
    localError.value = '请先打开可编辑的正式草稿版本。'
    return false
  }
  if (!props.canAutomate) {
    localError.value = '当前账号没有本厂区排产编辑权限。'
    return false
  }
  return true
}

function submitAutoDraft() {
  localError.value = ''
  if (!requireEditableDraft()) return
  const reason = autoDraftReason.value.trim()
  if (reason.length < 4) {
    localError.value = '自动排程原因至少填写 4 个字符。'
    return
  }
  emit('generate-auto-draft', {
    reason,
    horizonEndAt: normalizedDateTime(autoDraftHorizonEndAt.value),
  })
}

function submitReplan() {
  localError.value = ''
  if (!requireEditableDraft()) return
  const reason = replanReason.value.trim()
  if (reason.length < 4) {
    localError.value = '局部重排原因至少填写 4 个字符。'
    return
  }
  if (replanTriggerType.value === 'urgent_order' && !replanOrderId.value) {
    localError.value = '请选择需要插单或提急的订单。'
    return
  }
  if (replanTriggerType.value === 'machine_downtime') {
    const startAt = Date.parse(downtimeStartAt.value)
    const endAt = Date.parse(downtimeEndAt.value)
    if (
      !replanMachineId.value
      || !Number.isFinite(startAt)
      || !Number.isFinite(endAt)
      || endAt <= startAt
    ) {
      localError.value = '请选择停机机台，并填写有效的停机开始与结束时间。'
      return
    }
  }
  if (
    !Number.isFinite(maxAffectedMachines.value)
    || maxAffectedMachines.value < 1
    || !Number.isFinite(maxAffectedTasks.value)
    || maxAffectedTasks.value < 1
  ) {
    localError.value = '重排影响范围必须是正整数。'
    return
  }
  emit('run-replan', {
    triggerType: replanTriggerType.value,
    orderId: replanTriggerType.value === 'urgent_order' ? replanOrderId.value : '',
    machineId: replanTriggerType.value === 'machine_downtime' ? replanMachineId.value : '',
    downtimeStartAt: replanTriggerType.value === 'machine_downtime'
      ? normalizedDateTime(downtimeStartAt.value)
      : '',
    downtimeEndAt: replanTriggerType.value === 'machine_downtime'
      ? normalizedDateTime(downtimeEndAt.value)
      : '',
    freezeBeforeAt: normalizedDateTime(freezeBeforeAt.value),
    maxAffectedMachines: Math.trunc(maxAffectedMachines.value),
    maxAffectedTasks: Math.trunc(maxAffectedTasks.value),
    reason,
  })
}

function submitActual() {
  localError.value = ''
  if (!props.canWriteActuals) {
    localError.value = '当前账号没有本厂区实绩回写权限。'
    return
  }
  const reason = actualReason.value.trim()
  if (!selectedActualTask.value || !actualShiftDate.value) {
    localError.value = '请选择排程任务和实绩日期。'
    return
  }
  if (!Number.isFinite(actualQty.value) || Number(actualQty.value) < 0) {
    localError.value = '实际啤数必须是大于或等于 0 的整数。'
    return
  }
  if (reason.length < 4) {
    localError.value = '实绩回写原因至少填写 4 个字符。'
    return
  }
  const input = {
    taskId: selectedActualTask.value.id,
    shiftDate: actualShiftDate.value,
    shiftCode: actualShiftCode.value,
    actualQty: Math.trunc(Number(actualQty.value)),
    reason,
  }
  if (correctionActualId.value) {
    emit('correct-actual', {
      ...input,
      actualId: correctionActualId.value,
      actualRevision: correctionActualRevision.value,
    })
    return
  }
  emit('write-actual', input)
}

function startActualCorrection(actual: Phase4ActualView) {
  correctionActualId.value = actual.id
  correctionActualRevision.value = actual.revision
  actualTaskId.value = props.tasks.find((task) => task.orderId === actual.orderId)?.id ?? ''
  actualShiftDate.value = actual.shiftDate
  actualShiftCode.value = actual.shiftCode
  actualQty.value = actual.actualQty
  actualReason.value = ''
  localError.value = ''
}

function cancelActualCorrection() {
  correctionActualId.value = ''
  correctionActualRevision.value = 0
  actualQty.value = null
  actualReason.value = ''
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return '未排程'
  const date = new Date(value)
  if (Number.isNaN(date.getTime()) || date.getUTCFullYear() <= 1900) return '未排程'
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}

function runTypeLabel(run: Phase4RunView) {
  return run.runType === 'auto_draft' ? '自动排程草稿' : '局部动态重排'
}
</script>

<template>
  <section class="phase4-workspace" aria-label="Phase 4 自动排程与动态重排">
    <header class="phase4-hero">
      <div>
        <span class="phase4-hero__eyebrow">
          <Activity aria-hidden="true" />
          Phase 4 · 可审计的动态排程
        </span>
        <h2>自动草稿、局部重排与白夜班实绩</h2>
        <p>
          每次动作都绑定厂区、版本 revision 和操作原因；已锁任务不会被自动移动，
          实绩回写后滚动更新已啤数、欠数与预计完成时间。
        </p>
      </div>
      <dl class="phase4-version-card">
        <div><dt>当前版本</dt><dd>{{ version ? `V${version.versionNo}` : '未建立' }}</dd></div>
        <div><dt>Revision</dt><dd>{{ version?.revision ?? '—' }}</dd></div>
        <div>
          <dt>状态</dt>
          <dd :class="{ 'is-ready': version?.status === 'draft' }">
            {{ version?.status === 'draft'
              ? '可编辑草稿'
              : version?.status === 'published'
                ? '已发布 · 实绩生成滚动草稿'
                : '不可编辑' }}
          </dd>
        </div>
      </dl>
    </header>

    <div class="phase4-kpis" aria-label="动态排程摘要">
      <article>
        <Sparkles aria-hidden="true" />
        <div><span>待排 / 待补</span><strong>{{ orders.length }} 单</strong></div>
        <small>总欠数 {{ rollingOutstandingQty.toLocaleString('zh-CN') }}</small>
      </article>
      <article>
        <CircleGauge aria-hidden="true" />
        <div><span>当前任务</span><strong>{{ tasks.length }} 条</strong></div>
        <small>锁定 / 运行 / 完成保护 {{ barriers.length }} 条不移动</small>
      </article>
      <article>
        <ClockArrowDown aria-hidden="true" />
        <div><span>本次读取实绩</span><strong>{{ totalActualQty.toLocaleString('zh-CN') }} 啤</strong></div>
        <small>{{ actuals.length }} 条白夜班记录</small>
      </article>
      <article>
        <AlertTriangle aria-hidden="true" />
        <div><span>滚动 ETA 风险</span><strong>{{ delayedProjectionCount }} 单</strong></div>
        <small>以服务端回算结果为准</small>
      </article>
    </div>

    <div class="phase4-grid">
      <article class="phase4-card phase4-card--auto">
        <header>
          <span class="phase4-card__icon"><Sparkles aria-hidden="true" /></span>
          <div>
            <h3>生成自动排程草稿</h3>
            <p>从当前草稿生成新草稿，不自动发布；锁定任务与资料不全阻断项保持原状。</p>
          </div>
        </header>
        <label>
          <span>计划窗口结束（可选）</span>
          <input
            v-model="autoDraftHorizonEndAt"
            type="datetime-local"
            :disabled="busy || !canAutomate"
            aria-label="自动排程计划窗口结束"
          >
        </label>
        <label>
          <span>生成原因</span>
          <textarea
            v-model="autoDraftReason"
            rows="3"
            maxlength="2000"
            placeholder="例如：按当前欠数和交期生成本周自动排程草稿"
            :disabled="busy || !canAutomate"
          />
        </label>
        <button
          type="button"
          class="phase4-primary"
          :disabled="busy || !canAutomate || version?.status !== 'draft'"
          @click="submitAutoDraft"
        >
          <LoaderCircle v-if="busy" class="is-spinning" aria-hidden="true" />
          <Play v-else aria-hidden="true" />
          预览自动排程影响
        </button>
      </article>

      <article class="phase4-card phase4-card--replan">
        <header>
          <span class="phase4-card__icon"><Route aria-hidden="true" /></span>
          <div>
            <h3>插单 / 停机局部重排</h3>
            <p>只重算受影响机台的后序任务，范围上限由计划员明确控制。</p>
          </div>
        </header>
        <div class="phase4-segmented" role="group" aria-label="局部重排触发类型">
          <button
            type="button"
            :class="{ active: replanTriggerType === 'urgent_order' }"
            :aria-pressed="replanTriggerType === 'urgent_order'"
            @click="replanTriggerType = 'urgent_order'"
          >
            急单 / 插单
          </button>
          <button
            type="button"
            :class="{ active: replanTriggerType === 'machine_downtime' }"
            :aria-pressed="replanTriggerType === 'machine_downtime'"
            @click="replanTriggerType = 'machine_downtime'"
          >
            临时停机
          </button>
        </div>

        <label v-if="replanTriggerType === 'urgent_order'">
          <span>搜索提急订单（最多显示 120 条）</span>
          <input
            v-model.trim="urgentOrderSearch"
            type="search"
            placeholder="输入单号或产品名称"
            :disabled="busy || !canAutomate"
          >
        </label>
        <label v-if="replanTriggerType === 'urgent_order'">
          <span>提急订单</span>
          <select v-model="replanOrderId" :disabled="busy || !canAutomate">
            <option v-for="order in visibleUrgentOrders" :key="order.id" :value="order.id">
              {{ order.priorityCode }} · {{ order.orderNo }} · 欠 {{ order.outstandingQty }}
            </option>
          </select>
        </label>
        <template v-else>
          <label>
            <span>停机机台</span>
            <select v-model="replanMachineId" :disabled="busy || !canAutomate">
              <option v-for="machine in machines" :key="machine.id" :value="machine.id">
                {{ machine.machineCode }} · {{ machine.machineName }}
              </option>
            </select>
          </label>
          <div class="phase4-two-column">
            <label>
              <span>停机开始</span>
              <input v-model="downtimeStartAt" type="datetime-local" :disabled="busy || !canAutomate">
            </label>
            <label>
              <span>预计恢复</span>
              <input v-model="downtimeEndAt" type="datetime-local" :disabled="busy || !canAutomate">
            </label>
          </div>
        </template>
        <div class="phase4-two-column phase4-scope-row">
          <label>
            <span>最多影响机台</span>
            <input v-model.number="maxAffectedMachines" type="number" min="1" max="76" :disabled="busy || !canAutomate">
          </label>
          <label>
            <span>最多影响任务</span>
            <input v-model.number="maxAffectedTasks" type="number" min="1" max="1500" :disabled="busy || !canAutomate">
          </label>
        </div>
        <label>
          <span>冻结此时间之前的任务（可选）</span>
          <input v-model="freezeBeforeAt" type="datetime-local" :disabled="busy || !canAutomate">
        </label>
        <label>
          <span>重排原因</span>
          <textarea
            v-model="replanReason"
            rows="3"
            maxlength="2000"
            placeholder="例如：New23 临时停机，局部顺延未锁定后序任务"
            :disabled="busy || !canAutomate"
          />
        </label>
        <button
          type="button"
          class="phase4-primary"
          :disabled="busy || !canAutomate || version?.status !== 'draft'"
          @click="submitReplan"
        >
          <LoaderCircle v-if="busy" class="is-spinning" aria-hidden="true" />
          <RefreshCw v-else aria-hidden="true" />
          预览局部重排影响
        </button>
      </article>

      <article class="phase4-card phase4-card--actual">
        <header>
          <span class="phase4-card__icon"><Factory aria-hidden="true" /></span>
          <div>
            <h3>白班（A）/ 夜班（B）实绩回写</h3>
            <p>人工或接口录入，不代表 IoT 自动采集；重复请求和更正均由服务端审计。</p>
          </div>
        </header>
        <label>
          <span>搜索排程任务（最多显示 160 条）</span>
          <input
            v-model.trim="actualTaskSearch"
            type="search"
            placeholder="输入机台、单号或产品"
            :disabled="busy || !canWriteActuals"
          >
        </label>
        <label>
          <span>排程任务</span>
          <select v-model="actualTaskId" :disabled="busy || !canWriteActuals">
            <option v-for="task in visibleWritableTasks" :key="task.id" :value="task.id">
              {{ task.machineCode }} · {{ task.orderNo }} · 计划 {{ task.plannedQty }}
            </option>
          </select>
        </label>
        <div v-if="selectedActualTask" class="phase4-task-context">
          <span>{{ selectedActualTask.productName }}</span>
          <span>原计划完成 {{ formatDateTime(selectedActualTask.plannedFinishAt) }}</span>
          <span>当前订单欠数 {{ selectedActualOrder?.outstandingQty.toLocaleString('zh-CN') ?? '—' }}</span>
        </div>
        <div class="phase4-two-column">
          <label>
            <span>实绩日期</span>
            <input v-model="actualShiftDate" type="date" :disabled="busy || !canWriteActuals">
          </label>
          <fieldset class="phase4-shift">
            <legend>班次</legend>
            <label>
              <input v-model="actualShiftCode" type="radio" value="day" :disabled="busy || !canWriteActuals">
              <Sun aria-hidden="true" />
              白班（A）
            </label>
            <label>
              <input v-model="actualShiftCode" type="radio" value="night" :disabled="busy || !canWriteActuals">
              <Moon aria-hidden="true" />
              夜班（B）
            </label>
          </fieldset>
        </div>
        <label>
          <span>实际啤数</span>
          <input
            v-model.number="actualQty"
            type="number"
            min="0"
            step="1"
            placeholder="例如：12500"
            :disabled="busy || !canWriteActuals"
          >
        </label>
        <label>
          <span>{{ correctionActualId ? '更正原因' : '回写原因' }}</span>
          <textarea
            v-model="actualReason"
            rows="3"
            maxlength="2000"
            :placeholder="correctionActualId
              ? '例如：班组复核后更正白班实绩'
              : '例如：录入 7 月 25 日白班生产实绩'"
            :disabled="busy || !canWriteActuals"
          />
        </label>
        <div class="phase4-actual-actions">
          <button
            v-if="correctionActualId"
            type="button"
            class="phase4-secondary"
            :disabled="busy"
            @click="cancelActualCorrection"
          >
            取消更正
          </button>
          <button
            type="button"
            class="phase4-primary"
            :disabled="busy || !canWriteActuals || !actualTaskId"
            @click="submitActual"
          >
            <LoaderCircle v-if="busy" class="is-spinning" aria-hidden="true" />
            <CheckCircle2 v-else aria-hidden="true" />
            {{ correctionActualId ? '提交审计更正' : '回写并滚动计算' }}
          </button>
        </div>
      </article>
    </div>

    <p v-if="localError || error" class="phase4-error" role="alert">
      <AlertTriangle aria-hidden="true" />
      {{ localError || error }}
    </p>
    <p v-if="lastActualReplay" class="phase4-replay" role="status">
      <CheckCircle2 aria-hidden="true" />
      本次 requestId 命中幂等回放，服务端返回原实绩记录，没有重复累计产量。
    </p>

    <section v-if="barriers.length || skipped.length || impacts.length" class="phase4-evidence">
      <article>
        <header>
          <LockKeyhole aria-hidden="true" />
          <div>
            <h3>自动移动屏障</h3>
            <p>锁定、运行中、已完成和受保护任务保持原位。</p>
          </div>
        </header>
        <ul v-if="barriers.length">
          <li v-for="barrier in visibleBarriers" :key="barrier.id">
            <strong>{{ barrier.label }}</strong>
            <span>{{ barrier.reason }}</span>
          </li>
        </ul>
        <p v-else class="phase4-evidence__empty">当前服务端结果没有返回受保护任务。</p>
      </article>
      <article>
        <header>
          <AlertTriangle aria-hidden="true" />
          <div>
            <h3>未自动排入</h3>
            <p>只有硬约束 PASS 会以 source=auto 写入草稿。</p>
          </div>
        </header>
        <ul v-if="skipped.length">
          <li v-for="row in visibleSkipped" :key="row.id">
            <strong>{{ row.status === 'fail' ? 'FAIL' : 'UNKNOWN' }} · {{ row.label }}</strong>
            <span>{{ row.reason }}</span>
          </li>
        </ul>
        <p v-else class="phase4-evidence__empty">
          服务端本次没有返回逐单约束原因；UNKNOWN / FAIL 数量仍以右侧自动动作摘要为准。
        </p>
      </article>
      <article class="phase4-impact-card">
        <header>
          <Route aria-hidden="true" />
          <div>
            <h3>重排影响预览</h3>
            <p>服务端返回重排前后 ETA；交期余量只由订单交期与这两个 ETA 推导。</p>
          </div>
        </header>
        <div v-if="impacts.length" class="phase4-impact-list">
          <div v-for="impact in visibleImpacts" :key="impact.id">
            <strong>{{ impact.machineCode }} · {{ impact.orderNo }}</strong>
            <span>
              {{ formatDateTime(impact.beforeFinishAt) }} → {{ formatDateTime(impact.afterFinishAt) }}
            </span>
            <span :class="{ 'is-delayed': impact.etaShiftMinutes > 0 }">
              ETA {{ impact.etaShiftMinutes > 0 ? '+' : '' }}{{ impact.etaShiftMinutes }} 分钟 ·
              余量
              {{ impact.deliverySlackBeforeHours == null ? '—' : `${impact.deliverySlackBeforeHours.toFixed(1)}h` }}
              →
              {{ impact.deliverySlackAfterHours == null ? '—' : `${impact.deliverySlackAfterHours.toFixed(1)}h` }}
            </span>
          </div>
        </div>
        <p v-else class="phase4-evidence__empty">最近一次动作没有返回任务 ETA 变化。</p>
      </article>
    </section>

    <section class="phase4-results">
      <article class="phase4-ledger">
        <header>
          <div>
            <span class="phase4-card__icon"><CalendarClock aria-hidden="true" /></span>
            <div>
              <h3>滚动欠数与预计完成</h3>
              <p>只展示当前厂区服务端返回的白夜班实绩和滚动预测。</p>
            </div>
          </div>
          <button
            type="button"
            :disabled="actualsLoading || !canWriteActuals"
            @click="emit('reload-actuals')"
          >
            <LoaderCircle v-if="actualsLoading" class="is-spinning" aria-hidden="true" />
            <RefreshCw v-else aria-hidden="true" />
            重新读取
          </button>
        </header>
        <div v-if="actualsLoading && actuals.length === 0" class="phase4-empty" role="status">
          <LoaderCircle class="is-spinning" aria-hidden="true" />
          正在读取实绩与滚动预测…
        </div>
        <div v-else-if="actuals.length === 0" class="phase4-empty">
          <CalendarClock aria-hidden="true" />
          当前版本还没有白班 / 夜班实绩记录。
        </div>
        <div v-else class="phase4-table-scroll">
          <table>
            <thead>
              <tr>
                <th scope="col">日期 / 班次</th>
                <th scope="col">机台 / 订单</th>
                <th scope="col">本班实绩</th>
                <th scope="col">累计已啤</th>
                <th scope="col">滚动欠数</th>
                <th scope="col">预计完成</th>
                <th scope="col">状态 / 登记</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="actual in visibleActuals" :key="actual.id">
                <td>
                  <strong>{{ actual.shiftDate }}</strong>
                  <span>
                    {{ actual.shiftCode === 'day' ? '白班' : '夜班' }}
                    （{{ actual.legacyShiftCode || (actual.shiftCode === 'day' ? 'A' : 'B') }}）
                    · {{ actual.source === 'workbook' ? '工作簿' : '人工' }}
                  </span>
                </td>
                <td>
                  <strong>{{ actual.machineCode }}</strong>
                  <span>{{ actual.orderNo }}</span>
                </td>
                <td class="phase4-number">{{ actual.actualQty.toLocaleString('zh-CN') }}</td>
                <td class="phase4-number">{{ actual.cumulativeProducedQty.toLocaleString('zh-CN') }}</td>
                <td class="phase4-number" :class="{ 'is-cleared': actual.outstandingQty === 0 }">
                  {{ actual.outstandingQty.toLocaleString('zh-CN') }}
                </td>
                <td>{{ formatDateTime(actual.estimatedFinishAt) }}</td>
                <td>
                  <span class="phase4-actual-status" :class="{ corrected: actual.correctionCount > 0 }">
                    {{ actual.correctionCount > 0 ? `已更正 ${actual.correctionCount} 次` : '原始记录' }}
                  </span>
                  <strong>{{ actual.createdByName || '系统用户' }}</strong>
                  <span :title="actual.reason">{{ formatDateTime(actual.createdAt) }}</span>
                  <button
                    v-if="canWriteActuals && actual.canCorrect"
                    type="button"
                    class="phase4-inline-action"
                    @click="startActualCorrection(actual)"
                  >
                    更正
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-if="actuals.length > visibleActuals.length" class="phase4-ledger-limit">
          当前仅渲染最近 {{ visibleActuals.length }} 条；使用日期筛选重新读取可缩小范围。
        </p>
      </article>

      <aside class="phase4-audit">
        <header>
          <History aria-hidden="true" />
          <div>
            <h3>最近一次自动动作</h3>
            <p>版本、范围和理由都进入服务端审计。</p>
          </div>
        </header>
        <template v-if="lastRun">
          <span class="phase4-run-status" :class="`is-${lastRun.status}`">
            {{ lastRun.status === 'applied' ? '已应用' : '仅预览' }}
          </span>
          <h4>{{ runTypeLabel(lastRun) }}</h4>
          <p>{{ lastRun.reason }}</p>
          <dl>
            <div><dt>受影响机台</dt><dd>{{ lastRun.affectedMachineCount }}</dd></div>
            <div><dt>受影响任务</dt><dd>{{ lastRun.affectedTaskCount }}</dd></div>
            <div><dt>移动任务</dt><dd>{{ lastRun.movedTaskCount }}</dd></div>
          </dl>
          <ul>
            <li v-for="(explanation, index) in lastRun.explanations" :key="`${lastRun.id}-${index}`">
              <CheckCircle2 aria-hidden="true" />
              {{ explanation }}
            </li>
          </ul>
          <footer>
            {{ lastRun.createdByName || '系统用户' }} · {{ formatDateTime(lastRun.createdAt) }}
          </footer>
        </template>
        <div v-else class="phase4-empty phase4-empty--audit">
          <History aria-hidden="true" />
          尚未执行自动草稿或局部重排。
        </div>
      </aside>
    </section>
  </section>
</template>

<style scoped>
.phase4-workspace {
  display: grid;
  gap: 16px;
  min-width: 0;
}

.phase4-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 24px;
  align-items: center;
  padding: 22px 24px;
  border: 1px solid #dbe7e7;
  border-radius: 16px;
  background:
    linear-gradient(110deg, rgb(15 118 110 / 8%), transparent 48%),
    #fff;
  box-shadow: 0 12px 35px -30px rgb(15 23 42 / 45%);
}

.phase4-hero__eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 7px;
  color: #0f766e;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: .06em;
  text-transform: uppercase;
}

.phase4-hero__eyebrow svg {
  width: 15px;
}

.phase4-hero h2,
.phase4-hero p,
.phase4-card h3,
.phase4-card p,
.phase4-ledger h3,
.phase4-ledger p,
.phase4-audit h3,
.phase4-audit p {
  margin: 0;
}

.phase4-hero h2 {
  color: #0f172a;
  font-size: clamp(1.35rem, 2vw, 1.75rem);
  letter-spacing: -.035em;
}

.phase4-hero p {
  max-width: 820px;
  margin-top: 5px;
  color: #64748b;
  font-size: 13px;
  line-height: 1.7;
}

.phase4-version-card {
  display: grid;
  grid-template-columns: repeat(3, minmax(92px, 1fr));
  gap: 1px;
  margin: 0;
  overflow: hidden;
  border: 1px solid #dbe4e8;
  border-radius: 12px;
  background: #dbe4e8;
}

.phase4-version-card div {
  display: grid;
  gap: 3px;
  min-width: 96px;
  padding: 11px 14px;
  background: #fbfdfd;
}

.phase4-version-card dt {
  color: #64748b;
  font-size: 11px;
}

.phase4-version-card dd {
  margin: 0;
  color: #0f172a;
  font-size: 13px;
  font-weight: 800;
}

.phase4-version-card dd.is-ready {
  color: #0f766e;
}

.phase4-kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.phase4-kpis article {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 4px 11px;
  padding: 14px 16px;
  border: 1px solid #e1e8eb;
  border-radius: 13px;
  background: #fff;
}

.phase4-kpis svg {
  grid-row: 1 / span 2;
  width: 21px;
  color: #0f766e;
}

.phase4-kpis div {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.phase4-kpis span,
.phase4-kpis small {
  color: #64748b;
  font-size: 11px;
}

.phase4-kpis strong {
  color: #0f172a;
  font-size: 15px;
}

.phase4-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  align-items: start;
}

.phase4-card {
  display: grid;
  gap: 13px;
  min-width: 0;
  padding: 18px;
  border: 1px solid #dfe8eb;
  border-radius: 15px;
  background: #fff;
  box-shadow: 0 14px 38px -34px rgb(15 23 42 / 55%);
}

.phase4-card > header,
.phase4-ledger > header > div,
.phase4-audit > header {
  display: flex;
  gap: 11px;
  align-items: flex-start;
}

.phase4-card__icon {
  display: inline-flex;
  width: 35px;
  height: 35px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: #e6f7f4;
  color: #0f766e;
}

.phase4-card__icon svg {
  width: 18px;
}

.phase4-card h3,
.phase4-ledger h3,
.phase4-audit h3 {
  color: #0f172a;
  font-size: 15px;
}

.phase4-card p,
.phase4-ledger p,
.phase4-audit p {
  margin-top: 3px;
  color: #64748b;
  font-size: 11px;
  line-height: 1.55;
}

.phase4-card label {
  display: grid;
  gap: 5px;
  color: #475569;
  font-size: 11px;
  font-weight: 700;
}

.phase4-card input,
.phase4-card select,
.phase4-card textarea {
  width: 100%;
  min-height: 38px;
  padding: 8px 10px;
  border: 1px solid #cbd5e1;
  border-radius: 9px;
  background: #fff;
  color: #0f172a;
  font: inherit;
  font-size: 12px;
  font-weight: 500;
  outline: none;
}

.phase4-card textarea {
  resize: vertical;
}

.phase4-card input:focus,
.phase4-card select:focus,
.phase4-card textarea:focus {
  border-color: #14b8a6;
  box-shadow: 0 0 0 3px rgb(20 184 166 / 13%);
}

.phase4-card input:disabled,
.phase4-card select:disabled,
.phase4-card textarea:disabled {
  cursor: not-allowed;
  background: #f1f5f9;
  color: #94a3b8;
}

.phase4-primary {
  display: inline-flex;
  min-height: 41px;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: 0;
  border-radius: 10px;
  background: #0f766e;
  color: #fff;
  font-size: 12px;
  font-weight: 800;
  cursor: pointer;
}

.phase4-actual-actions {
  display: flex;
  gap: 8px;
}

.phase4-actual-actions .phase4-primary {
  flex: 1;
}

.phase4-secondary {
  min-height: 41px;
  padding: 0 13px;
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  background: #fff;
  color: #475569;
  font-size: 12px;
  font-weight: 800;
  cursor: pointer;
}

.phase4-primary:hover:not(:disabled) {
  background: #115e59;
}

.phase4-primary:disabled {
  cursor: not-allowed;
  background: #cbd5e1;
}

.phase4-primary svg,
.phase4-ledger button svg {
  width: 16px;
}

.phase4-segmented {
  display: grid;
  grid-template-columns: 1fr 1fr;
  padding: 3px;
  border: 1px solid #dbe4e8;
  border-radius: 10px;
  background: #f1f5f9;
}

.phase4-segmented button {
  min-height: 34px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.phase4-segmented button.active {
  background: #fff;
  color: #0f766e;
  box-shadow: 0 2px 8px rgb(15 23 42 / 8%);
}

.phase4-two-column {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.phase4-scope-row {
  padding: 10px;
  border: 1px dashed #cbd5e1;
  border-radius: 10px;
  background: #f8fafc;
}

.phase4-task-context {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.phase4-task-context span {
  padding: 4px 7px;
  border-radius: 7px;
  background: #f1f5f9;
  color: #475569;
  font-size: 10px;
}

.phase4-shift {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 5px;
  margin: 0;
  padding: 0;
  border: 0;
}

.phase4-shift legend {
  grid-column: 1 / -1;
  margin-bottom: 5px;
  color: #475569;
  font-size: 11px;
  font-weight: 700;
}

.phase4-shift label {
  display: flex;
  min-height: 38px;
  flex-direction: row;
  align-items: center;
  justify-content: center;
  gap: 5px;
  border: 1px solid #cbd5e1;
  border-radius: 9px;
  cursor: pointer;
}

.phase4-shift input {
  width: 13px;
  min-height: 0;
  padding: 0;
}

.phase4-shift svg {
  width: 14px;
}

.phase4-error {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  padding: 10px 13px;
  border: 1px solid #fecaca;
  border-radius: 10px;
  background: #fff1f2;
  color: #b91c1c;
  font-size: 12px;
  font-weight: 700;
}

.phase4-error svg {
  width: 16px;
}

.phase4-replay {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  padding: 10px 13px;
  border: 1px solid #99f6e4;
  border-radius: 10px;
  background: #f0fdfa;
  color: #0f766e;
  font-size: 12px;
  font-weight: 700;
}

.phase4-replay svg {
  width: 16px;
}

.phase4-evidence {
  display: grid;
  grid-template-columns: .8fr .9fr 1.3fr;
  gap: 12px;
}

.phase4-evidence > article {
  min-width: 0;
  padding: 15px;
  border: 1px solid #dfe8eb;
  border-radius: 13px;
  background: #fff;
}

.phase4-evidence header {
  display: flex;
  gap: 9px;
  align-items: flex-start;
  margin-bottom: 10px;
}

.phase4-evidence header > svg {
  width: 18px;
  flex: 0 0 auto;
  color: #0f766e;
}

.phase4-evidence h3,
.phase4-evidence p {
  margin: 0;
}

.phase4-evidence h3 {
  color: #0f172a;
  font-size: 13px;
}

.phase4-evidence header p,
.phase4-evidence__empty {
  margin-top: 2px;
  color: #64748b;
  font-size: 10px;
  line-height: 1.5;
}

.phase4-evidence ul,
.phase4-impact-list {
  display: grid;
  gap: 7px;
  max-height: 180px;
  margin: 0;
  padding: 0;
  overflow-y: auto;
  list-style: none;
}

.phase4-evidence li,
.phase4-impact-list > div {
  display: grid;
  gap: 2px;
  padding: 8px 9px;
  border-radius: 8px;
  background: #f8fafc;
}

.phase4-evidence li strong,
.phase4-impact-list strong {
  color: #334155;
  font-size: 10px;
}

.phase4-evidence li span,
.phase4-impact-list span {
  color: #64748b;
  font-size: 9px;
  line-height: 1.45;
}

.phase4-impact-list span.is-delayed {
  color: #b45309;
  font-weight: 700;
}

.phase4-results {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 14px;
  align-items: stretch;
}

.phase4-ledger,
.phase4-audit {
  min-width: 0;
  padding: 18px;
  border: 1px solid #dfe8eb;
  border-radius: 15px;
  background: #fff;
}

.phase4-ledger > header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 13px;
}

.phase4-ledger button {
  display: inline-flex;
  min-height: 35px;
  align-items: center;
  gap: 6px;
  padding: 0 11px;
  border: 1px solid #cbd5e1;
  border-radius: 9px;
  background: #fff;
  color: #475569;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
}

.phase4-table-scroll {
  overflow: auto;
  border: 1px solid #e2e8f0;
  border-radius: 11px;
}

.phase4-ledger-limit {
  margin: 8px 0 0;
  color: #64748b;
  font-size: 10px;
  text-align: right;
}

.phase4-table-scroll table {
  width: 100%;
  min-width: 820px;
  border-collapse: collapse;
  font-size: 11px;
}

.phase4-table-scroll th {
  padding: 9px 11px;
  border-bottom: 1px solid #e2e8f0;
  background: #f8fafc;
  color: #64748b;
  text-align: left;
  font-weight: 800;
  white-space: nowrap;
}

.phase4-table-scroll td {
  padding: 10px 11px;
  border-bottom: 1px solid #eef2f6;
  color: #334155;
  vertical-align: top;
}

.phase4-table-scroll tbody tr:last-child td {
  border-bottom: 0;
}

.phase4-table-scroll td strong,
.phase4-table-scroll td span {
  display: block;
}

.phase4-table-scroll .phase4-actual-status {
  display: inline-flex;
  margin: 0 0 5px;
  padding: 2px 6px;
  border-radius: 999px;
  background: #f1f5f9;
  color: #64748b;
  font-size: 9px;
  font-weight: 800;
}

.phase4-table-scroll .phase4-actual-status.corrected {
  background: #fff7ed;
  color: #c2410c;
}

.phase4-inline-action {
  margin-top: 5px;
  padding: 3px 7px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: #fff;
  color: #0f766e;
  font-size: 9px;
  font-weight: 800;
  cursor: pointer;
}

.phase4-table-scroll td span {
  margin-top: 2px;
  color: #64748b;
  font-size: 10px;
}

.phase4-number {
  font-variant-numeric: tabular-nums;
  font-weight: 800;
}

.phase4-number.is-cleared {
  color: #0f766e;
}

.phase4-audit {
  position: relative;
  background:
    linear-gradient(155deg, rgb(15 118 110 / 7%), transparent 55%),
    #fff;
}

.phase4-audit > header {
  margin-bottom: 13px;
}

.phase4-audit > header > svg {
  width: 21px;
  color: #0f766e;
}

.phase4-run-status {
  display: inline-flex;
  padding: 4px 8px;
  border-radius: 999px;
  background: #e6f7f4;
  color: #0f766e;
  font-size: 10px;
  font-weight: 800;
}

.phase4-run-status.is-blocked,
.phase4-run-status.is-failed {
  background: #fff1f2;
  color: #be123c;
}

.phase4-audit h4 {
  margin: 12px 0 4px;
  color: #0f172a;
  font-size: 15px;
}

.phase4-audit dl {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 7px;
  margin: 13px 0;
}

.phase4-audit dl div {
  padding: 9px;
  border: 1px solid #dfe8eb;
  border-radius: 9px;
  background: rgb(255 255 255 / 75%);
}

.phase4-audit dt {
  color: #64748b;
  font-size: 9px;
}

.phase4-audit dd {
  margin: 3px 0 0;
  color: #0f172a;
  font-size: 15px;
  font-weight: 800;
}

.phase4-audit ul {
  display: grid;
  gap: 7px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.phase4-audit li {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  color: #475569;
  font-size: 11px;
  line-height: 1.45;
}

.phase4-audit li svg {
  width: 13px;
  flex: 0 0 auto;
  color: #0f766e;
}

.phase4-audit footer {
  margin-top: 14px;
  color: #94a3b8;
  font-size: 10px;
}

.phase4-empty {
  display: flex;
  min-height: 130px;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #64748b;
  font-size: 12px;
}

.phase4-empty > svg {
  width: 18px;
}

.phase4-empty--audit {
  min-height: 210px;
  flex-direction: column;
  text-align: center;
}

.is-spinning {
  animation: phase4-spin 900ms linear infinite;
}

@keyframes phase4-spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 1180px) {
  .phase4-grid {
    grid-template-columns: 1fr 1fr;
  }

  .phase4-card--actual {
    grid-column: 1 / -1;
  }

  .phase4-results {
    grid-template-columns: 1fr;
  }

  .phase4-evidence {
    grid-template-columns: 1fr 1fr;
  }

  .phase4-impact-card {
    grid-column: 1 / -1;
  }
}

@media (max-width: 900px) {
  .phase4-hero {
    grid-template-columns: 1fr;
  }

  .phase4-kpis {
    grid-template-columns: 1fr 1fr;
  }

  .phase4-evidence {
    grid-template-columns: 1fr;
  }

  .phase4-impact-card {
    grid-column: auto;
  }
}

@media (max-width: 700px) {
  .phase4-grid,
  .phase4-kpis,
  .phase4-two-column {
    grid-template-columns: 1fr;
  }

  .phase4-card--actual {
    grid-column: auto;
  }

  .phase4-version-card {
    grid-template-columns: 1fr;
  }
}
</style>
