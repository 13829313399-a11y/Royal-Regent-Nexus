<script setup lang="ts">
import { computed, ref } from 'vue'
import { CalendarClock, LockKeyhole, MoveRight, ShieldAlert } from '@lucide/vue'
import type {
  InjectionMachine,
  InjectionMold,
  InjectionOrder,
  InjectionScheduleTask,
} from '@/types/injectionSchedule'

export interface MachineCandidateState {
  state: 'recommended' | 'manual' | 'blocked' | 'neutral'
  message: string
}

const props = withDefaults(defineProps<{
  machines: InjectionMachine[]
  tasks: InjectionScheduleTask[]
  orders: InjectionOrder[]
  molds?: InjectionMold[]
  selectedOrder?: InjectionOrder | null
  candidateStateByMachine?: Record<string, MachineCandidateState>
  planBaseAt?: string
  timelineStartAt?: string
  timelineEndAt?: string
}>(), {
  selectedOrder: null,
  molds: () => [],
  candidateStateByMachine: () => ({}),
  planBaseAt: '',
  timelineStartAt: '',
  timelineEndAt: '',
})

const emit = defineEmits<{
  inspectMachine: [machineId: string]
  inspectTask: [taskId: string]
  previewAssignment: [payload: { orderId: string; machineId: string }]
  scheduleDrop: [payload: {
    taskId: string
    machineId: string
    beforeTaskId: string | null
  }]
}>()

const viewport = ref<HTMLElement | null>(null)
const scrollTop = ref(0)
const dragOverMachineId = ref('')
const draggingTaskId = ref('')
const rowHeight = 72
const headerHeight = 56
const overscan = 3
const viewportHeight = 584
const hourMilliseconds = 3_600_000
const dayMilliseconds = hourMilliseconds * 24
const timelineDayCount = 7
const factoryTimeZone = 'Asia/Shanghai'
const dayLabelFormatter = new Intl.DateTimeFormat('zh-CN', {
  month: '2-digit',
  day: '2-digit',
  timeZone: factoryTimeZone,
})
const weekdayFormatter = new Intl.DateTimeFormat('zh-CN', {
  weekday: 'short',
  timeZone: factoryTimeZone,
})
const timeFormatter = new Intl.DateTimeFormat('zh-CN', {
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
  timeZone: factoryTimeZone,
})
const dateTimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
  timeZone: factoryTimeZone,
})

function parseTimestamp(value: string | null | undefined) {
  if (!value) return null
  const timestamp = Date.parse(value)
  return Number.isFinite(timestamp) ? timestamp : null
}

const planBaseTimestamp = computed(() => (
  parseTimestamp(props.planBaseAt)
  ?? parseTimestamp(props.timelineStartAt)
  ?? props.tasks.reduce<number | null>((earliest, task) => {
    const taskStart = parseTimestamp(task.startAt)
    if (taskStart == null) return earliest
    return earliest == null ? taskStart : Math.min(earliest, taskStart)
  }, null)
))
const timelineStartTimestamp = computed(() => planBaseTimestamp.value)
const timelineEndTimestamp = computed(() => {
  const start = timelineStartTimestamp.value
  const explicitEnd = parseTimestamp(props.timelineEndAt)
  if (start == null) return null
  if (explicitEnd != null && explicitEnd > start) return explicitEnd
  return start + timelineDayCount * dayMilliseconds
})
const days = computed(() => {
  const base = planBaseTimestamp.value
  if (base == null) return []

  return Array.from({ length: timelineDayCount }, (_, index) => {
    const dayShiftStartsAt = base + index * dayMilliseconds
    const nightShiftStartsAt = dayShiftStartsAt + 12 * hourMilliseconds
    const date = new Date(dayShiftStartsAt)
    return {
      id: date.toISOString(),
      date: dayLabelFormatter.format(date),
      weekday: weekdayFormatter.format(date),
      dayShift: `白 ${timeFormatter.format(date)}`,
      nightShift: `夜 ${timeFormatter.format(new Date(nightShiftStartsAt))}`,
    }
  })
})
const shiftCount = computed(() => days.value.length * 2)
const shiftCalendarStyle = computed(() => ({
  gridTemplateColumns: `repeat(${Math.max(days.value.length, 1)}, minmax(126px, 1fr))`,
}))
const planBasePosition = computed(() => {
  const base = planBaseTimestamp.value
  const start = timelineStartTimestamp.value
  const end = timelineEndTimestamp.value
  if (base == null || start == null || end == null || end <= start) return null
  if (base < start || base > end) return null
  return Math.min(100, Math.max(0, ((base - start) / (end - start)) * 100))
})
const timelineRegionLabel = computed(() => {
  const base = planBaseTimestamp.value
  return base == null
    ? '机台七日排程时间轴'
    : `机台七日排程时间轴，计划基准 ${dateTimeFormatter.format(new Date(base))}`
})

const orderById = computed(() => new Map(props.orders.map((order) => [order.id, order])))
const moldById = computed(() => new Map(props.molds.map((mold) => [mold.id, mold])))
const machineById = computed(() => new Map(
  props.machines.map((machine) => [machine.id, machine]),
))
const tasksByMachine = computed(() => {
  const groups = new Map<string, InjectionScheduleTask[]>()
  for (const task of props.tasks) {
    const current = groups.get(task.machineId) ?? []
    current.push(task)
    groups.set(task.machineId, current)
  }
  for (const tasks of groups.values()) {
    tasks.sort((left, right) => left.startAt.localeCompare(right.startAt))
  }
  return groups
})

const firstVisibleIndex = computed(() => Math.max(
  0,
  Math.floor(Math.max(0, scrollTop.value - headerHeight) / rowHeight) - overscan,
))
const visibleCount = computed(() => Math.ceil(viewportHeight / rowHeight) + overscan * 2)
const visibleMachines = computed(() => props.machines
  .slice(firstVisibleIndex.value, firstVisibleIndex.value + visibleCount.value)
  .map((machine, localIndex) => ({
    machine,
    index: firstVisibleIndex.value + localIndex,
  })))
const boardHeight = computed(() => headerHeight + props.machines.length * rowHeight)

function handleScroll(event: Event) {
  scrollTop.value = (event.currentTarget as HTMLElement).scrollTop
}

function candidateState(machineId: string) {
  return props.candidateStateByMachine[machineId] ?? {
    state: 'neutral' as const,
    message: '选择待排订单后可校验',
  }
}

function assignmentButtonLabel(machine: InjectionMachine) {
  const selected = props.selectedOrder
  if (!selected) return `查看${machine.machineNo}机台`
  const state = candidateState(machine.id).state
  return state === 'blocked'
    ? `查看${selected.orderNo}不能排到${machine.machineNo}的原因`
    : state === 'manual'
      ? `查看${selected.orderNo}排到${machine.machineNo}前需要确认的资料`
      : `将${selected.orderNo}预排到${machine.machineNo}`
}

function previewSelectedOrder(machineId: string) {
  if (!props.selectedOrder) {
    emit('inspectMachine', machineId)
    return
  }

  emit('previewAssignment', {
    orderId: props.selectedOrder.id,
    machineId,
  })
}

function beginDragOver(machineId: string) {
  dragOverMachineId.value = machineId
}

function endDragOver(machineId: string) {
  if (dragOverMachineId.value === machineId) {
    dragOverMachineId.value = ''
  }
}

function handleDrop(event: DragEvent, machineId: string) {
  dragOverMachineId.value = ''
  const taskId = event.dataTransfer?.getData('application/x-injection-schedule-task')
  if (taskId) {
    emit('scheduleDrop', {
      taskId,
      machineId,
      beforeTaskId: taskBeforeDrop(event, machineId, taskId),
    })
    draggingTaskId.value = ''
    return
  }
  const orderId = event.dataTransfer?.getData('application/x-injection-order')
    || event.dataTransfer?.getData('text/plain')
    || props.selectedOrder?.id
  if (!orderId) return
  emit('previewAssignment', { orderId, machineId })
}

function taskBeforeDrop(
  event: DragEvent,
  machineId: string,
  draggedTaskId: string,
) {
  const row = event.currentTarget as HTMLElement | null
  const track = row?.querySelector<HTMLElement>('.timeline-track')
  if (!track) return null
  const rect = track.getBoundingClientRect()
  if (rect.width <= 0) return null
  const pointerPosition = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width))
  const orderedTasks = (tasksByMachine.value.get(machineId) ?? [])
    .filter((task) => task.id !== draggedTaskId)
    .map((task) => ({
      task,
      geometry: taskGeometry(task),
    }))
    .filter((entry): entry is {
      task: InjectionScheduleTask
      geometry: { left: number; width: number }
    } => entry.geometry != null)
    .sort((left, right) => left.geometry.left - right.geometry.left)

  return orderedTasks.find((entry) => (
    pointerPosition * 100 < entry.geometry.left + entry.geometry.width / 2
  ))?.task.id ?? null
}

function beginTaskDrag(event: DragEvent, task: InjectionScheduleTask) {
  if (task.locked || task.status !== 'draft') {
    event.preventDefault()
    return
  }
  draggingTaskId.value = task.id
  event.dataTransfer?.setData('application/x-injection-schedule-task', task.id)
  event.dataTransfer?.setData('text/plain', task.id)
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
}

function endTaskDrag() {
  draggingTaskId.value = ''
  dragOverMachineId.value = ''
}

function taskGeometry(task: InjectionScheduleTask) {
  const timelineStart = timelineStartTimestamp.value
  const timelineEnd = timelineEndTimestamp.value
  const taskStart = parseTimestamp(task.startAt)
  const taskEnd = parseTimestamp(task.endAt)
  if (
    timelineStart == null
    || timelineEnd == null
    || taskStart == null
    || taskEnd == null
    || timelineEnd <= timelineStart
    || taskEnd <= taskStart
    || taskEnd <= timelineStart
    || taskStart >= timelineEnd
  ) {
    return null
  }

  const span = timelineEnd - timelineStart
  const visibleStart = Math.max(taskStart, timelineStart)
  const visibleEnd = Math.min(taskEnd, timelineEnd)
  const left = ((visibleStart - timelineStart) / span) * 100
  const right = ((visibleEnd - timelineStart) / span) * 100
  return {
    left,
    width: Math.max(0, right - left),
  }
}

function taskPosition(task: InjectionScheduleTask) {
  const geometry = taskGeometry(task)
  if (!geometry) return { display: 'none' }
  return {
    left: `${geometry.left}%`,
    width: `${Math.max(2.8, geometry.width)}%`,
  }
}

function taskDensity(task: InjectionScheduleTask) {
  const width = taskGeometry(task)?.width ?? 0
  if (width < 9) return 'compact'
  if (width < 20) return 'standard'
  return 'roomy'
}

function taskTone(task: InjectionScheduleTask) {
  const order = orderById.value.get(task.orderId)
  const palette = ['blue', 'violet', 'teal', 'amber', 'sky', 'green', 'orange']
  const seed = [...(order?.moldId ?? task.id)]
    .reduce((total, character) => total + character.charCodeAt(0), 0)
  return palette[seed % palette.length]
}

function formatTaskDateTime(value: string | null | undefined) {
  const timestamp = parseTimestamp(value)
  return timestamp == null ? '待确认' : dateTimeFormatter.format(new Date(timestamp))
}

function taskDueRisk(task: InjectionScheduleTask) {
  const order = orderById.value.get(task.orderId)
  const dueAt = parseTimestamp(order?.deliveryDueAt)
  const completedAt = parseTimestamp(task.endAt)
  if (dueAt == null || completedAt == null || !order) {
    return {
      short: '交期待确认',
      full: '交期风险待确认',
    }
  }

  const bufferHours = Math.max(order.warehouseBufferHours, 0)
    + Math.max(order.downstreamBufferHours, 0)
  const slackHours = (dueAt - completedAt) / hourMilliseconds - bufferHours
  const absoluteHours = Math.abs(slackHours)
  const duration = absoluteHours >= 48
    ? `${(absoluteHours / 24).toFixed(1)} 天`
    : `${absoluteHours.toFixed(1)} 小时`

  if (slackHours < 0) {
    return {
      short: `超期 ${duration}`,
      full: `计入仓库及下游缓冲后，预计超期 ${duration}`,
    }
  }
  if (slackHours <= 24) {
    return {
      short: `高风险 · 余 ${duration}`,
      full: `交期高风险，计入仓库及下游缓冲后仅余 ${duration}`,
    }
  }
  if (slackHours <= 72) {
    return {
      short: `临期 · 余 ${duration}`,
      full: `交期临近，计入仓库及下游缓冲后余 ${duration}`,
    }
  }
  return {
    short: `余 ${duration}`,
    full: `交期余量 ${duration}`,
  }
}

function taskAccessibleLabel(task: InjectionScheduleTask) {
  const order = orderById.value.get(task.orderId)
  const outstandingShots = order?.outstandingShots ?? task.plannedShots
  return [
    `机台 ${taskMachineCode(task)}`,
    `模号 ${taskMoldNo(task)}`,
    `订单号 ${taskOrderNo(task)}`,
    `产品 ${taskProductName(task)}`,
    `欠数 ${outstandingShots.toLocaleString('zh-CN')}`,
    `颜色 ${order?.colorName ?? '待确认'}`,
    `预计完成 ${formatTaskDateTime(task.endAt)}`,
    taskDueRisk(task).full,
  ].join('，')
}

function immutableSnapshotLabel(
  snapshot: string | undefined,
  current: string | null | undefined,
  fallback: string,
) {
  if (snapshot !== undefined) return snapshot.trim() || '未记录'
  return current?.trim() || fallback
}

function taskMachineCode(task: InjectionScheduleTask) {
  return immutableSnapshotLabel(
    task.machineCodeSnapshot,
    machineById.value.get(task.machineId)?.machineNo,
    task.machineId,
  )
}

function taskOrderNo(task: InjectionScheduleTask) {
  return immutableSnapshotLabel(
    task.orderNoSnapshot,
    orderById.value.get(task.orderId)?.orderNo,
    task.orderId,
  )
}

function taskProductName(task: InjectionScheduleTask) {
  return immutableSnapshotLabel(
    task.productNameSnapshot,
    orderById.value.get(task.orderId)?.productName,
    '排程任务',
  )
}

function taskMoldNo(task: InjectionScheduleTask) {
  const order = orderById.value.get(task.orderId)
  const current = order
    ? moldById.value.get(order.moldId)?.moldNo ?? order.moldId
    : null
  return immutableSnapshotLabel(task.moldCodeSnapshot, current, task.orderId)
}

function taskTooltip(task: InjectionScheduleTask) {
  return taskAccessibleLabel(task).replaceAll('，', '\n')
}

function machineArmLabel(machine: InjectionMachine) {
  if (machine.armType === 'double') return '双臂'
  if (machine.armType === 'single') return '单臂'
  return '无机械手'
}

function machineStatusLabel(machine: InjectionMachine) {
  const labels: Record<InjectionMachine['status'], string> = {
    idle: '空闲',
    running: '运行',
    setup: '换模',
    maintenance: '保养',
    stopped: '停机',
    locked: '锁定',
  }
  return labels[machine.status]
}
</script>

<template>
  <section class="timeline-panel" aria-labelledby="machine-timeline-title">
    <header class="timeline-panel__heading">
      <div class="timeline-panel__title-wrap">
        <h2 id="machine-timeline-title">机台排程时间轴</h2>
        <span class="timeline-panel__badge">
          <CalendarClock aria-hidden="true" />
          拖放预览
        </span>
        <p>浅色优先 · 同模连排 · 交期越近优先级越高</p>
      </div>
      <span class="timeline-panel__count">已载入 {{ machines.length }} 台机</span>
    </header>
    <p id="machine-timeline-instructions" class="sr-only">
      可将待排订单拖放到机台；键盘用户可先选择订单，再使用机台按钮完成预排。
    </p>

    <div
      ref="viewport"
      class="timeline-viewport"
      role="region"
      :aria-label="timelineRegionLabel"
      aria-describedby="machine-timeline-instructions"
      tabindex="0"
      @scroll="handleScroll"
    >
      <div class="timeline-canvas" :style="{ height: `${boardHeight}px` }">
        <div class="timeline-header">
          <div class="machine-column machine-column--header">
            机台 / 机型 / 机械手
          </div>
          <div class="shift-calendar" :style="shiftCalendarStyle">
            <div
              v-for="day in days"
              :key="day.id"
              class="day-cell"
            >
              <strong>{{ day.date }}</strong>
              <span>{{ day.weekday }}</span>
              <small>{{ day.dayShift }}</small>
              <small>{{ day.nightShift }}</small>
            </div>
            <span
              v-if="planBasePosition != null"
              class="today-line"
              :class="{ 'today-line--start': planBasePosition <= 1 }"
              :style="{ left: `${planBasePosition}%` }"
              aria-hidden="true"
            >
              <span>基准</span>
            </span>
          </div>
        </div>

        <div
          v-for="{ machine, index } in visibleMachines"
          :key="machine.id"
          class="machine-row"
          :class="[
            {
              [`machine-row--${candidateState(machine.id).state}`]: dragOverMachineId === machine.id,
              'machine-row--drag-over': dragOverMachineId === machine.id,
              'machine-row--new-workshop': machine.workshop === 'new',
            },
          ]"
          :style="{ top: `${headerHeight + index * rowHeight}px` }"
          @dragenter.prevent="beginDragOver(machine.id)"
          @dragover.prevent="beginDragOver(machine.id)"
          @dragleave="endDragOver(machine.id)"
          @drop.prevent="handleDrop($event, machine.id)"
        >
          <button
            type="button"
            class="machine-column machine-cell"
            :aria-label="assignmentButtonLabel(machine)"
            :title="candidateState(machine.id).message"
            @click="previewSelectedOrder(machine.id)"
          >
            <span class="machine-chip">{{ machine.machineNo }}</span>
            <span class="machine-summary">
              <strong>{{ machine.machineClass }}</strong>
              <small>{{ machineArmLabel(machine) }} · {{ machineStatusLabel(machine) }}</small>
            </span>
            <span
              class="machine-state-dot"
              :class="`machine-state-dot--${machine.status}`"
              aria-hidden="true"
            />
            <ShieldAlert
              v-if="candidateState(machine.id).state === 'blocked'
                || candidateState(machine.id).state === 'manual'"
              class="machine-warning-icon"
              aria-hidden="true"
            />
            <MoveRight
              v-else-if="selectedOrder"
              class="machine-action-icon"
              aria-hidden="true"
            />
          </button>

          <div class="timeline-track">
            <span
              v-for="shiftIndex in shiftCount"
              :key="shiftIndex"
              class="shift-grid-line"
              :style="{ left: `${((shiftIndex - 1) / shiftCount) * 100}%` }"
              aria-hidden="true"
            />

            <button
              v-for="(task, taskIndex) in tasksByMachine.get(machine.id) ?? []"
              :key="task.id"
              type="button"
              class="schedule-task"
              :class="[
                `schedule-task--${taskTone(task)}`,
                `schedule-task--${taskDensity(task)}`,
                {
                  'schedule-task--locked': task.locked,
                  'schedule-task--dragging': draggingTaskId === task.id,
                },
              ]"
              :style="{ ...taskPosition(task), top: taskIndex % 2 === 0 ? '10px' : '38px' }"
              :aria-label="taskAccessibleLabel(task)"
              :title="taskTooltip(task)"
              :draggable="task.status === 'draft' && !task.locked"
              @dragstart="beginTaskDrag($event, task)"
              @dragend="endTaskDrag"
              @click="emit('inspectTask', task.id)"
            >
              <span class="schedule-task__identity">
                <strong>{{ taskMoldNo(task) }}</strong>
                <span class="schedule-task__order">
                  {{ taskOrderNo(task) }}
                </span>
              </span>
              <span class="schedule-task__product">
                {{ taskProductName(task) }}
              </span>
              <span class="schedule-task__meta">
                <span>{{ orderById.get(task.orderId)?.colorName ?? '待定色' }}</span>
                <small>
                  欠 {{ orderById.get(task.orderId)?.outstandingShots.toLocaleString('zh-CN')
                    ?? task.plannedShots.toLocaleString('zh-CN') }}
                </small>
              </span>
              <small class="schedule-task__completion">
                完成 {{ formatTaskDateTime(task.endAt) }}
              </small>
              <small class="schedule-task__risk">{{ taskDueRisk(task).short }}</small>
              <LockKeyhole v-if="task.locked" class="schedule-task__lock" aria-hidden="true" />
            </button>

            <span
              v-if="selectedOrder
                && dragOverMachineId === machine.id
                && (tasksByMachine.get(machine.id)?.length ?? 0) === 0"
              class="assignment-hint"
              :class="`assignment-hint--${candidateState(machine.id).state}`"
            >
              {{ candidateState(machine.id).message }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.timeline-panel {
  display: flex;
  height: 100%;
  min-width: 0;
  flex-direction: column;
  overflow: hidden;
  border-right: 1px solid #dde5e8;
  background: #fff;
}

.timeline-panel__heading {
  display: flex;
  min-height: 51px;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  border-bottom: 1px solid #dde5e8;
  padding: 0 18px;
}

.timeline-panel__title-wrap {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 14px;
}

.timeline-panel__title-wrap h2 {
  flex: none;
  color: #0f172a;
  font-size: 18px;
  font-weight: 800;
}

.timeline-panel__title-wrap p,
.timeline-panel__count {
  overflow: hidden;
  color: #64748b;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.timeline-panel__badge {
  display: inline-flex;
  height: 24px;
  align-items: center;
  gap: 5px;
  border-radius: 999px;
  background: #e6f7f4;
  padding: 0 9px;
  color: #0f766e;
  font-size: 11px;
  font-weight: 700;
}

.timeline-panel__badge svg {
  width: 13px;
  height: 13px;
}

.timeline-viewport {
  height: auto;
  min-height: 0;
  flex: 1;
  overflow: auto;
  outline: none;
  scrollbar-color: #94a3b8 #f8fafc;
  scrollbar-width: thin;
}

.timeline-viewport:focus-visible {
  box-shadow: inset 0 0 0 3px rgb(20 184 166 / 24%);
}

.timeline-canvas {
  position: relative;
  min-width: 1128px;
  background: #fff;
}

.timeline-header,
.machine-row {
  display: grid;
  grid-template-columns: 246px minmax(882px, 1fr);
}

.timeline-header {
  position: sticky;
  z-index: 20;
  top: 0;
  height: 56px;
  border-bottom: 1px solid #dbe5e8;
  background: #f7fafa;
}

.machine-column {
  position: sticky;
  z-index: 12;
  left: 0;
  border-right: 1px solid #dde5e8;
  background: inherit;
}

.machine-column--header {
  display: flex;
  align-items: center;
  padding: 0 16px;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
}

.shift-calendar {
  position: relative;
  display: grid;
}

.day-cell {
  position: relative;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  align-content: center;
  border-right: 1px solid #e8eef0;
  color: #334155;
  text-align: center;
}

.day-cell strong {
  font-size: 11px;
}

.day-cell span {
  font-size: 10px;
}

.day-cell small {
  margin-top: 5px;
  color: #94a3b8;
  font-size: 9px;
}

.today-line {
  position: absolute;
  z-index: 4;
  top: 0;
  bottom: -528px;
  width: 1px;
  background: #ef4444;
  pointer-events: none;
}

.today-line span {
  position: absolute;
  top: 3px;
  left: 50%;
  border-radius: 999px;
  background: #dc2626;
  padding: 2px 7px;
  color: #fff;
  font-size: 9px;
  font-weight: 700;
  transform: translateX(-50%);
  white-space: nowrap;
}

.today-line--start span {
  left: 6px;
  transform: none;
}

.machine-row {
  position: absolute;
  right: 0;
  left: 0;
  height: 72px;
  border-bottom: 1px solid #eef2f3;
  background: #fff;
}

.machine-row:nth-child(even) {
  background: #fbfcfc;
}

.machine-row--recommended .machine-cell {
  box-shadow: inset 3px 0 0 #14b8a6;
}

.machine-row--blocked .machine-cell {
  box-shadow: inset 3px 0 0 #ef4444;
}

.machine-row--manual .machine-cell {
  box-shadow: inset 3px 0 0 #d97706;
}

.machine-row--drag-over {
  background: #eefbf8;
  box-shadow: inset 0 0 0 2px #14b8a6;
}

.machine-row--blocked.machine-row--drag-over {
  background: #fff1f2;
  box-shadow: inset 0 0 0 2px #ef4444;
}

.machine-row--manual.machine-row--drag-over {
  background: #fffbeb;
  box-shadow: inset 0 0 0 2px #f59e0b;
}

.machine-cell {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 10px;
  border: 0;
  padding: 0 14px;
  color: #0f172a;
  text-align: left;
}

.machine-cell:hover {
  background: #f0fdfa;
}

.machine-cell:focus-visible {
  box-shadow: inset 0 0 0 2px #0f766e;
  outline: none;
}

.machine-chip {
  display: inline-flex;
  width: 46px;
  height: 36px;
  flex: none;
  align-items: center;
  justify-content: center;
  border-radius: 9px;
  background: #e6f7f4;
  color: #0f766e;
  font-size: 13px;
  font-weight: 800;
}

.machine-summary {
  display: grid;
  min-width: 0;
  flex: 1;
  gap: 4px;
}

.machine-summary strong {
  overflow: hidden;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.machine-summary small {
  overflow: hidden;
  color: #64748b;
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.machine-state-dot {
  width: 8px;
  height: 8px;
  flex: none;
  border-radius: 50%;
  background: #94a3b8;
}

.machine-state-dot--running,
.machine-state-dot--idle {
  background: #16a34a;
}

.machine-state-dot--setup {
  background: #d97706;
}

.machine-state-dot--maintenance,
.machine-state-dot--stopped,
.machine-state-dot--locked {
  background: #dc2626;
}

.machine-action-icon,
.machine-warning-icon {
  width: 15px;
  height: 15px;
  flex: none;
}

.machine-action-icon {
  color: #0f766e;
}

.machine-warning-icon {
  color: #dc2626;
}

.timeline-track {
  position: relative;
  min-width: 0;
  overflow: hidden;
}

.shift-grid-line {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 1px;
  background: #edf2f3;
}

.schedule-task {
  position: absolute;
  z-index: 3;
  display: flex;
  height: 25px;
  min-width: 74px;
  align-items: center;
  gap: 6px;
  overflow: hidden;
  border: 0;
  border-radius: 4px;
  padding: 0 7px;
  color: #fff;
  font-size: 10px;
  white-space: nowrap;
}

.schedule-task:hover,
.schedule-task:focus-visible {
  filter: brightness(0.95);
  outline: 2px solid #0f172a;
  outline-offset: 1px;
}

.schedule-task__lock {
  width: 12px;
  height: 12px;
  flex: none;
}

.schedule-task__identity,
.schedule-task__meta {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 5px;
}

.schedule-task__identity,
.schedule-task__product,
.schedule-task__meta,
.schedule-task__completion,
.schedule-task__risk,
.schedule-task strong,
.schedule-task span {
  overflow: hidden;
  text-overflow: ellipsis;
}

.schedule-task__identity {
  flex: none;
}

.schedule-task__product {
  min-width: 48px;
  flex: 1;
}

.schedule-task__meta,
.schedule-task__completion,
.schedule-task__risk {
  flex: none;
}

.schedule-task__meta small,
.schedule-task__completion,
.schedule-task__risk {
  font-size: 9px;
}

.schedule-task__risk {
  margin-left: auto;
  font-weight: 800;
}

.schedule-task--compact .schedule-task__order,
.schedule-task--compact .schedule-task__product,
.schedule-task--compact .schedule-task__meta,
.schedule-task--compact .schedule-task__completion,
.schedule-task--compact .schedule-task__risk,
.schedule-task--standard .schedule-task__product,
.schedule-task--standard .schedule-task__completion,
.schedule-task--standard .schedule-task__risk {
  display: none;
}

.schedule-task--roomy .schedule-task__order {
  opacity: 0.82;
}

.schedule-task--blue { background: #2563eb; }
.schedule-task--violet { background: #7c3aed; }
.schedule-task--teal { background: #0f766e; }
.schedule-task--amber { background: #d97706; }
.schedule-task--sky { background: #0284c7; }
.schedule-task--green { background: #16a34a; }
.schedule-task--orange { background: #ea580c; }
.schedule-task--locked { box-shadow: inset 0 0 0 2px rgb(255 255 255 / 50%); }
.schedule-task--dragging {
  opacity: 0.42;
  outline: 2px dashed #0f766e;
  outline-offset: 2px;
}

.schedule-task[draggable="true"] {
  cursor: grab;
}

.schedule-task[draggable="true"]:active {
  cursor: grabbing;
}

.assignment-hint {
  position: absolute;
  top: 21px;
  right: 16px;
  left: 16px;
  display: flex;
  height: 29px;
  align-items: center;
  justify-content: center;
  border: 1px dashed #b6c8cc;
  border-radius: 6px;
  color: #64748b;
  font-size: 10px;
  font-weight: 700;
}

.assignment-hint--recommended {
  border-color: #5eead4;
  background: #ecfdf8;
  color: #0f766e;
}

.assignment-hint--blocked {
  border-color: #fca5a5;
  background: #fff1f2;
  color: #b91c1c;
}

.assignment-hint--manual {
  border-color: #fbbf24;
  background: #fffbeb;
  color: #92400e;
}

@media (max-width: 1279px) {
  .timeline-panel__title-wrap p {
    display: none;
  }
}
</style>
