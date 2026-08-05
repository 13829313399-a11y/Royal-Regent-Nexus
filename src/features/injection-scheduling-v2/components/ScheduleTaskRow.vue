<script setup lang="ts">
import { FlexRender, type Row } from '@tanstack/vue-table'
import type { CSSProperties } from 'vue'
import { GripVertical, LockKeyhole } from '@lucide/vue'
import GridEditableCell from './GridEditableCell.vue'
import type { CellDraft, EditableCellKey, ScheduleGridRow } from '../types'

const props = defineProps<{ row: Row<ScheduleGridRow>; top: number; width: number; stickyLeft: Record<string, number>; selected: boolean; dragging: boolean; dropTarget: boolean; planStatus: string; canEdit: boolean; canReport: boolean; pendingEdits: Record<string, CellDraft> }>()
const emit = defineEmits<{
  select: [taskId: string]
  edit: [taskId: string, key: EditableCellKey, value: string | number]
  dragStart: [taskId: string, event: DragEvent]
  dragEnd: []
  dragHover: [machineId: string]
  dragLeave: [machineId: string]
  dropTask: [machineId: string, sequence: number, event: DragEvent]
  keyboardMove: [taskId: string, direction: 'up' | 'down' | 'previous-machine' | 'next-machine']
}>()
const number = new Intl.NumberFormat('zh-CN')
function display(value: unknown) { return typeof value === 'number' ? number.format(value) : value || '—' }
function cellStyle(cell: ReturnType<Row<ScheduleGridRow>['getVisibleCells']>[number]): CSSProperties {
  const align = (cell.column.columnDef.meta as { align?: CSSProperties['textAlign'] } | undefined)?.align ?? 'left'
  return { width: `${cell.column.getSize()}px`, left: stickyLeftValue(cell.column.id), textAlign: align }
}
function stickyLeftValue(columnId: string) { return props.stickyLeft[columnId] !== undefined ? `${props.stickyLeft[columnId]}px` : undefined }
const editableKeys = new Set<EditableCellKey>(['status', 'targetQuantity', 'shiftCompleted', 'completedQuantity', 'downtime', 'exception', 'plannedStart', 'plannedFinish', 'warehouse', 'remark'])
const draftPlanKeys = new Set<EditableCellKey>(['status', 'targetQuantity', 'plannedStart', 'plannedFinish', 'warehouse', 'remark'])
const reportKeys = new Set<EditableCellKey>(['status', 'targetQuantity', 'shiftCompleted', 'completedQuantity', 'downtime', 'exception'])
function keyFor(columnId: string) { return editableKeys.has(columnId as EditableCellKey) ? columnId as EditableCellKey : null }
function canEditCell(columnId: string) {
  const key = keyFor(columnId)
  const task = props.row.original.task
  if (!key || !task) return false
  if (['warehouse', 'remark'].includes(key)) return props.canEdit
  if (props.planStatus === 'DRAFT') return props.canEdit && draftPlanKeys.has(key)
  return props.planStatus === 'PUBLISHED' && props.canReport && task.activeExecution && reportKeys.has(key)
}
function pending(columnId: string) { return Boolean(props.pendingEdits[`${props.row.original.id}:${columnId}`]) }
function editValue(columnId: string, fallback: unknown) { return props.pendingEdits[`${props.row.original.id}:${columnId}`]?.value ?? (fallback as string | number) }
function kind(columnId: string): 'text' | 'number' | 'datetime' | 'select' {
  if (columnId === 'status') return 'select'
  if (['targetQuantity', 'shiftCompleted', 'completedQuantity', 'downtime'].includes(columnId)) return 'number'
  if (['plannedStart', 'plannedFinish'].includes(columnId)) return 'datetime'
  return 'text'
}
function statusLabel(value: unknown) {
  return value === 'RUNNING' ? '正在生产' : value === 'QUEUED' ? '排队中' : value === 'BLOCKED' ? '异常/待料' : value === 'COMPLETED' ? '已完成' : String(value)
}
function statusOptions() {
  return props.planStatus === 'DRAFT'
    ? [{ value: 'QUEUED', label: '排队中' }, { value: 'BLOCKED', label: '异常/待料' }]
    : [{ value: 'QUEUED', label: '排队中' }, { value: 'RUNNING', label: '正在生产' }, { value: 'BLOCKED', label: '异常/待料' }, { value: 'COMPLETED', label: '已完成' }]
}
function commitEdit(columnId: string, value: string | number) {
  const key = keyFor(columnId)
  if (key) emit('edit', props.row.original.id, key, value)
}
function draggable() { const task = props.row.original.task; return Boolean(props.planStatus === 'DRAFT' && props.canEdit && task && !task.locked && !task.activeExecution && task.status !== 'RUNNING') }
function keyboard(event: KeyboardEvent) {
  if (!event.altKey || !draggable()) return
  const directions: Record<string, 'up' | 'down' | 'previous-machine' | 'next-machine'> = { ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'previous-machine', ArrowRight: 'next-machine' }
  const direction = directions[event.key]
  if (direction) { event.preventDefault(); emit('keyboardMove', props.row.original.id, direction) }
}
</script>

<template>
  <tr class="schedule-task-row" :class="[`status-${row.original.status.toLowerCase()}`, { overdue: Number(row.original.slack) < 0, shortage: row.original.materialReadiness === 'blocked', 'is-selected': selected, 'is-dragging': dragging, 'drop-target': dropTarget, 'has-pending-edit': Object.keys(pendingEdits).some((key) => key.startsWith(`${row.original.id}:`)), draggable: draggable() }]" :style="{ transform: `translateY(${top}px)`, width: `${width}px` }" :draggable="draggable()" :aria-selected="selected" tabindex="0" @click="emit('select', row.original.id)" @dragstart="emit('dragStart', row.original.id, $event)" @dragend="emit('dragEnd')" @dragenter.prevent="emit('dragHover', row.original.machine.id)" @dragover.prevent="emit('dragHover', row.original.machine.id)" @dragleave="emit('dragLeave', row.original.machine.id)" @drop="emit('dropTask', row.original.machine.id, Number(row.original.sequence), $event)" @keydown="keyboard">
    <td v-for="cell in row.getVisibleCells()" :key="cell.id" :class="['grid-cell', { frozen: stickyLeft[cell.column.id] !== undefined }]" :style="cellStyle(cell)">
      <GridEditableCell v-if="canEditCell(cell.column.id)" :value="editValue(cell.column.id, cell.getValue())" :kind="kind(cell.column.id)" :options="cell.column.id === 'status' ? statusOptions() : []" :pending="pending(cell.column.id)" @commit="commitEdit(cell.column.id, $event)"><span v-if="cell.column.id === 'status'" class="status-chip" :class="String(editValue(cell.column.id, cell.getValue())).toLowerCase()">{{ statusLabel(editValue(cell.column.id, cell.getValue())) }}</span><span v-else>{{ display(editValue(cell.column.id, cell.getValue())) }}</span></GridEditableCell>
      <span v-else-if="cell.column.id === 'status'" class="status-chip" :class="row.original.status.toLowerCase()">{{ statusLabel(row.original.status) }}</span>
      <span v-else-if="cell.column.id === 'progress'" class="progress-cell"><i><b :style="{ width: `${row.original.progress}%` }"></b></i><em>{{ row.original.progress }}%</em></span>
      <span v-else-if="cell.column.id === 'fit'" class="fit-chip" :class="row.original.fit.toLowerCase()">{{ row.original.fit === 'PASS' ? '通过' : row.original.fit === 'FAIL' ? '不适配' : '待复核' }}</span>
      <span v-else-if="cell.column.id === 'slack'" :class="{ negative: Number(row.original.slack) < 0, warning: Number(row.original.slack) >= 0 && Number(row.original.slack) <= 3 }">{{ display(cell.getValue()) }}</span>
      <span v-else-if="cell.column.id === 'marker'" class="marker-cell"><GripVertical v-if="draggable()" :size="12" /><LockKeyhole v-if="row.original.task?.locked" :size="12" />{{ display(cell.getValue()) }}</span>
      <FlexRender v-else :render="cell.column.columnDef.cell" :props="cell.getContext()" />
    </td>
  </tr>
</template>
