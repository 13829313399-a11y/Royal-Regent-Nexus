<script setup lang="ts">
import type { CSSProperties } from 'vue'
import { GripVertical, LockKeyhole } from '@lucide/vue'
import GridEditableCell from './GridEditableCell.vue'
import type { CellDraft, EditableCellKey, ScheduleGridRow, SchedulingColumnDefinition } from '../types'
import { formatBusinessDateTime } from '@/lib/dateTime'
import { fitDecisionMeta, taskStatusMeta } from '../presentation/schedulingLabels'

const props = defineProps<{ row: ScheduleGridRow; columns: SchedulingColumnDefinition[]; columnSizes: Record<string, number>; top: number; width: number; rowIndex: number; stickyLeft: Record<string, number>; selected: boolean; dragging: boolean; dropTarget: boolean; planStatus: string; canEdit: boolean; canReport: boolean; pendingEdits: Record<string, CellDraft> }>()
const emit = defineEmits<{
  select: [taskId: string]
  edit: [taskId: string, key: EditableCellKey, value: string | number]
  dragStart: [taskId: string, event: DragEvent]
  dragEnd: []
  dragHover: [machineId: string]
  dragLeave: [machineId: string]
  dropTask: [machineId: string, sequence: number, event: DragEvent]
  keyboardMove: [taskId: string, direction: 'up' | 'down' | 'previous-machine' | 'next-machine']
  focusRow: [taskId: string]
}>()
const number = new Intl.NumberFormat('zh-CN')
function display(value: unknown) { return typeof value === 'number' ? number.format(value) : value || '—' }
function isPlanTimeColumn(columnId: string) { return columnId === 'plannedStart' || columnId === 'plannedFinish' }
function planTime(value: unknown) { return formatBusinessDateTime(typeof value === 'string' ? value : '', { fallback: '—' }) }
function planTimeTitle(value: unknown) {
  const formatted = planTime(value)
  return formatted === '—' ? '暂无有效计划时间' : `北京时间：${formatted}`
}
function columnId(column: SchedulingColumnDefinition) { return String(column.key) }
function cellValue(column: SchedulingColumnDefinition) { return props.row[column.key] }
function cellStyle(column: SchedulingColumnDefinition): CSSProperties {
  const id = columnId(column)
  return { width: `${props.columnSizes[id] ?? column.width}px`, left: stickyLeftValue(id), textAlign: column.align ?? 'left' }
}
function stickyLeftValue(columnId: string) { return props.stickyLeft[columnId] !== undefined ? `${props.stickyLeft[columnId]}px` : undefined }
const editableKeys = new Set<EditableCellKey>(['status', 'targetQuantity', 'shiftCompleted', 'completedQuantity', 'downtime', 'exception', 'plannedStart', 'plannedFinish', 'warehouse', 'remark'])
const draftPlanKeys = new Set<EditableCellKey>(['status', 'targetQuantity', 'plannedStart', 'plannedFinish', 'warehouse', 'remark'])
const reportKeys = new Set<EditableCellKey>(['status', 'targetQuantity', 'shiftCompleted', 'completedQuantity', 'downtime', 'exception'])
function keyFor(columnId: string) { return editableKeys.has(columnId as EditableCellKey) ? columnId as EditableCellKey : null }
function canEditCell(columnId: string) {
  const key = keyFor(columnId)
  const task = props.row.task
  if (!key || !task) return false
  if (['warehouse', 'remark'].includes(key)) return props.canEdit
  if (props.planStatus === 'DRAFT') return props.canEdit && draftPlanKeys.has(key)
  return props.planStatus === 'PUBLISHED' && props.canReport && task.activeExecution && reportKeys.has(key)
}
function pending(columnId: string) { return Boolean(props.pendingEdits[`${props.row.id}:${columnId}`]) }
function editValue(columnId: string, fallback: unknown) { return props.pendingEdits[`${props.row.id}:${columnId}`]?.value ?? (fallback as string | number) }
function kind(columnId: string): 'text' | 'number' | 'datetime' | 'select' {
  if (columnId === 'status') return 'select'
  if (['targetQuantity', 'shiftCompleted', 'completedQuantity', 'downtime'].includes(columnId)) return 'number'
  if (['plannedStart', 'plannedFinish'].includes(columnId)) return 'datetime'
  return 'text'
}
function statusLabel(value: unknown) {
  return taskStatusMeta(value).label
}
function statusOptions() {
  return props.planStatus === 'DRAFT'
    ? [{ value: 'QUEUED', label: '排队中' }, { value: 'BLOCKED', label: '异常/待料' }]
    : [{ value: 'QUEUED', label: '排队中' }, { value: 'RUNNING', label: '正在生产' }, { value: 'BLOCKED', label: '异常/待料' }, { value: 'COMPLETED', label: '已完成' }]
}
function commitEdit(columnId: string, value: string | number) {
  const key = keyFor(columnId)
  if (key) emit('edit', props.row.id, key, value)
}
function draggable() { const task = props.row.task; return Boolean(props.planStatus === 'DRAFT' && props.canEdit && task && !task.locked && !task.activeExecution && task.status !== 'RUNNING') }
function keyboard(event: KeyboardEvent) {
  if (!event.altKey || !draggable()) return
  const directions: Record<string, 'up' | 'down' | 'previous-machine' | 'next-machine'> = { ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'previous-machine', ArrowRight: 'next-machine' }
  const direction = directions[event.key]
  if (direction) { event.preventDefault(); emit('keyboardMove', props.row.id, direction) }
}
function rowLabel() {
  return `${props.row.machine.code}，${props.row.productName}，${statusLabel(props.row.status)}，队列 ${props.row.sequence}${props.selected ? '，已选中' : ''}${Number(props.row.slack) < 0 ? '，已逾期' : ''}${props.row.materialReadiness === 'blocked' ? '，物料受阻' : ''}`
}
</script>

<template>
  <tr class="schedule-task-row" :class="[`status-${row.status.toLowerCase()}`, { overdue: Number(row.slack) < 0, shortage: row.materialReadiness === 'blocked', 'is-selected': selected, 'is-dragging': dragging, 'drop-target': dropTarget, 'has-pending-edit': Object.keys(pendingEdits).some((key) => key.startsWith(`${row.id}:`)), draggable: draggable() }]" :style="{ transform: `translateY(${top}px)`, width: `${width}px` }" :draggable="draggable()" :aria-selected="selected" :aria-rowindex="rowIndex" :aria-label="rowLabel()" aria-keyshortcuts="Alt+ArrowUp Alt+ArrowDown Alt+ArrowLeft Alt+ArrowRight" tabindex="0" @click="emit('select', row.id)" @focusin="emit('focusRow', row.id)" @dragstart="emit('dragStart', row.id, $event)" @dragend="emit('dragEnd')" @dragenter.prevent="emit('dragHover', row.machine.id)" @dragover.prevent="emit('dragHover', row.machine.id)" @dragleave="emit('dragLeave', row.machine.id)" @drop="emit('dropTask', row.machine.id, Number(row.sequence), $event)" @keydown="keyboard">
    <td v-for="(column, columnIndex) in columns" :key="columnId(column)" :class="['grid-cell', { frozen: stickyLeft[columnId(column)] !== undefined }]" :style="cellStyle(column)" :aria-colindex="columnIndex + 1">
      <GridEditableCell v-if="canEditCell(columnId(column))" :value="editValue(columnId(column), cellValue(column))" :kind="kind(columnId(column))" :options="columnId(column) === 'status' ? statusOptions() : []" :pending="pending(columnId(column))" @commit="commitEdit(columnId(column), $event)"><span v-if="columnId(column) === 'status'" class="status-chip" :class="String(editValue(columnId(column), cellValue(column))).toLowerCase()">{{ statusLabel(editValue(columnId(column), cellValue(column))) }}</span><time v-else-if="isPlanTimeColumn(columnId(column))" class="schedule-time-cell" :datetime="String(editValue(columnId(column), cellValue(column)))" :title="planTimeTitle(editValue(columnId(column), cellValue(column)))">{{ planTime(editValue(columnId(column), cellValue(column))) }}</time><span v-else>{{ display(editValue(columnId(column), cellValue(column))) }}</span></GridEditableCell>
      <span v-else-if="columnId(column) === 'status'" class="status-chip" :class="row.status.toLowerCase()">{{ statusLabel(row.status) }}</span>
      <time v-else-if="isPlanTimeColumn(columnId(column))" class="schedule-time-cell" :datetime="String(cellValue(column) ?? '')" :title="planTimeTitle(cellValue(column))">{{ planTime(cellValue(column)) }}</time>
      <span v-else-if="columnId(column) === 'progress'" class="progress-cell"><i><b :style="{ width: `${row.progress}%` }"></b></i><em>{{ row.progress }}%</em></span>
      <span v-else-if="columnId(column) === 'fit'" class="fit-chip" :class="row.fit.toLowerCase()">{{ fitDecisionMeta(row.fit).label }}</span>
      <span v-else-if="columnId(column) === 'slack'" :class="{ negative: Number(row.slack) < 0, warning: Number(row.slack) >= 0 && Number(row.slack) <= 3 }">{{ display(cellValue(column)) }}</span>
      <span v-else-if="columnId(column) === 'marker'" class="marker-cell"><GripVertical v-if="draggable()" :size="12" /><LockKeyhole v-if="row.task?.locked" :size="12" />{{ display(cellValue(column)) }}</span>
      <span v-else>{{ String(cellValue(column) ?? '—') }}</span>
    </td>
  </tr>
</template>
