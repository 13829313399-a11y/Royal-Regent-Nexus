<script setup lang="ts">
import { computed, nextTick, ref, watch, type CSSProperties } from 'vue'
import { createColumnHelper, getCoreRowModel, useVueTable, type ColumnDef, type ColumnSizingState } from '@tanstack/vue-table'
import { useVirtualizer } from '@tanstack/vue-virtual'
import { ArrowDown, ArrowUp, ChevronsUpDown } from '@lucide/vue'
import MachineGroupRow from './MachineGroupRow.vue'
import ScheduleTaskRow from './ScheduleTaskRow.vue'
import { useScheduleDragDrop } from '../composables/useScheduleDragDrop'
import {
  defaultSchedulingDensity,
  schedulingDensity,
  schedulingDensityCssVariables,
  translateSchedulingScrollOffset,
  type SchedulingDensityMode,
} from '../config/schedulingLayout'
import { buildSchedulingGroupHeaderSegments } from '../presentation/schedulingGroupSegments'
import type { CellDraft, EditableCellKey, MachineScheduleSummary, ScheduleGridRow, SchedulingColumnDefinition } from '../types'

const props = withDefaults(defineProps<{
  rows: ScheduleGridRow[]
  machineSummaryById: ReadonlyMap<string, MachineScheduleSummary>
  columns: SchedulingColumnDefinition[]
  collapsedMachineIds: string[]
  widths: Record<string, number>
  sort: { key: string; desc: boolean } | null
  selectedTaskId: string | null
  planStatus: string
  canEdit: boolean
  canReport: boolean
  pendingEdits: Record<string, CellDraft>
  density?: SchedulingDensityMode
}>(), { density: defaultSchedulingDensity })
const emit = defineEmits<{
  toggleMachine: [id: string]
  select: [id: string]
  sort: [key: string]
  resize: [key: string, width: number]
  edit: [taskId: string, key: EditableCellKey, value: string | number]
  moveRequest: [taskId: string, machineId: string, sequence: number]
  keyboardMove: [taskId: string, direction: 'up' | 'down' | 'previous-machine' | 'next-machine']
}>()
const drag = useScheduleDragDrop((taskId, machineId, sequence) => emit('moveRequest', taskId, machineId, sequence))
const scrollElement = ref<HTMLElement | null>(null)
const focusedRowId = ref<string | null>(null)
const liveAnnouncement = ref('')
const densityLayout = computed(() => schedulingDensity[props.density])
const densityStyle = computed<CSSProperties>(() => schedulingDensityCssVariables(props.density) as CSSProperties)
const helper = createColumnHelper<ScheduleGridRow>()
const columnDefs = computed<ColumnDef<ScheduleGridRow>[]>(() => props.columns.map((column) => helper.accessor(column.key, {
  id: String(column.key), header: column.title, size: props.widths[String(column.key)] ?? column.width,
  minSize: 54, maxSize: 420, cell: (info) => String(info.getValue() ?? '—'), meta: { align: column.align ?? 'left', group: column.group, frozen: column.frozen },
})) as ColumnDef<ScheduleGridRow>[])
const sizing = ref<ColumnSizingState>({})
const virtualizer = useVirtualizer(computed(() => ({
  count: props.rows.length,
  getScrollElement: () => scrollElement.value,
  estimateSize: (index: number) => props.rows[index]?.rowType === 'machine' ? densityLayout.value.machineRow : densityLayout.value.taskRow,
  overscan: 12,
})))
watch(() => props.density, async (density, previousDensity) => {
  const element = scrollElement.value
  const translatedOffset = element
    ? translateSchedulingScrollOffset(props.rows, previousDensity, density, element.scrollTop)
    : 0
  await nextTick()
  virtualizer.value.measure()
  if (element) element.scrollTop = translatedOffset
})
const virtualRows = computed(() => virtualizer.value.getVirtualItems())
const table = useVueTable({
  data: [], get columns() { return columnDefs.value }, getCoreRowModel: getCoreRowModel(), columnResizeMode: 'onChange',
  state: { get columnSizing() { return sizing.value } },
  onColumnSizingChange: (updater) => {
    sizing.value = typeof updater === 'function' ? updater(sizing.value) : updater
    Object.entries(sizing.value).forEach(([key, value]) => emit('resize', key, value))
  },
})
const renderRows = computed(() => virtualRows.value.flatMap((virtualRow) => {
  const original = props.rows[virtualRow.index]
  if (!original) return []
  return [{ virtualRow, original }]
}))
const renderedRowIds = computed(() => renderRows.value.map((item) => item.original.id))
const totalWidth = computed(() => table.getTotalSize())
const columnSizes = computed(() => Object.fromEntries(props.columns.map((column) => [String(column.key), table.getColumn(String(column.key))?.getSize() ?? column.width])))
const groupSegments = computed(() => buildSchedulingGroupHeaderSegments(props.columns, columnSizes.value))
const stickyLeft = computed(() => {
  let left = 0
  const offsets: Record<string, number> = {}
  for (const column of props.columns) {
    if (!column.frozen) continue
    offsets[String(column.key)] = left
    left += table.getColumn(String(column.key))?.getSize() ?? column.width
  }
  return offsets
})
const emptyMachineSummary: MachineScheduleSummary = { taskCount: 0, currentLabel: '', releaseAt: '' }
const moveDirectionLabels = { up: '上移', down: '下移', 'previous-machine': '移至上一机台', 'next-machine': '移至下一机台' } as const
function summaryFor(machineId: string) { return props.machineSummaryById.get(machineId) ?? emptyMachineSummary }
function announce(message: string) { liveAnnouncement.value = message }
function taskLabel(taskId: string) {
  const row = props.rows.find((item) => item.rowType === 'task' && item.id === taskId)
  return row ? `${row.machine.code} ${row.productName}` : '当前任务'
}
function machineLabel(machineId: string) { return props.rows.find((item) => item.machine.id === machineId)?.machine.code ?? '目标机台' }
function startDrag(taskId: string, event: DragEvent) {
  drag.start(taskId, event)
  announce(`已拾取 ${taskLabel(taskId)}，可拖放到目标机台，或使用 Alt + 方向键移动`)
}
function endDrag() {
  const taskId = drag.draggedTaskId.value
  drag.end()
  if (taskId) announce(`已取消拖拽 ${taskLabel(taskId)}`)
}
function dropAtEnd(machineId: string, event: DragEvent) {
  const taskId = drag.draggedTaskId.value
  drag.drop(machineId, summaryFor(machineId).taskCount, event)
  if (taskId) announce(`已请求将 ${taskLabel(taskId)} 移至 ${machineLabel(machineId)} 队列末尾`)
}
function dropAtTask(machineId: string, sequence: number, event: DragEvent) {
  const taskId = drag.draggedTaskId.value
  drag.drop(machineId, sequence, event)
  if (taskId) announce(`已请求将 ${taskLabel(taskId)} 移至 ${machineLabel(machineId)} 队列 ${sequence}`)
}
function forwardEdit(taskId: string, key: EditableCellKey, value: string | number) { emit('edit', taskId, key, value) }
function forwardKeyboard(taskId: string, direction: 'up' | 'down' | 'previous-machine' | 'next-machine') {
  emit('keyboardMove', taskId, direction)
  announce(`正在打开 ${taskLabel(taskId)} 的${moveDirectionLabels[direction]}移动预览`)
}
function sortState(columnId: string) { return props.sort?.key === columnId ? (props.sort.desc ? 'descending' : 'ascending') : 'none' }
function sortLabel(columnId: string, title: string) {
  const state = sortState(columnId)
  return `按${title}排序，当前${state === 'ascending' ? '升序' : state === 'descending' ? '降序' : '未排序'}`
}
function requestSort(columnId: string) { emit('sort', columnId) }
function sortWithKeyboard(event: KeyboardEvent, columnId: string) {
  if (!['Enter', ' '].includes(event.key)) return
  event.preventDefault()
  requestSort(columnId)
}
function resizeWithKeyboard(event: KeyboardEvent, columnId: string, title: string) {
  if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return
  event.preventDefault()
  const current = table.getColumn(columnId)?.getSize() ?? 0
  const delta = (event.shiftKey ? 24 : 8) * (event.key === 'ArrowRight' ? 1 : -1)
  const width = Math.max(54, Math.min(420, current + delta))
  sizing.value = { ...sizing.value, [columnId]: width }
  emit('resize', columnId, width)
  announce(`${title}列宽已调整为 ${width} 像素`)
}
function groupColumnIndex(firstKey: string) { return props.columns.findIndex((column) => String(column.key) === firstKey) + 1 }
function recordRowFocus(rowId: string) { focusedRowId.value = rowId }
watch(renderedRowIds, async (rowIds) => {
  const rowId = focusedRowId.value
  if (!rowId || rowIds.includes(rowId)) return
  await nextTick()
  scrollElement.value?.focus()
  focusedRowId.value = null
  announce('原焦点任务已离开虚拟可见区，焦点已返回排产表')
})
</script>

<template>
  <div ref="scrollElement" class="machine-plan-scroll" data-testid="machine-plan-virtual-scroll" :style="densityStyle" tabindex="0" aria-describedby="grid-keyboard-help">
    <table class="machine-plan-table" :style="{ width: `${totalWidth}px` }" aria-label="注塑排产任务表" :aria-rowcount="rows.length + 2" :aria-colcount="columns.length">
      <thead :style="{ width: `${totalWidth}px` }">
        <tr class="column-group-row">
          <th
            v-for="segment in groupSegments"
            :key="segment.id"
            :class="{ frozen: segment.frozen }"
            :colspan="segment.columnKeys.length"
            :data-column-keys="segment.columnKeys.join(',')"
            :style="{ width: `${segment.width}px`, left: segment.left !== undefined ? `${segment.left}px` : undefined }"
            scope="colgroup"
            :aria-colindex="groupColumnIndex(segment.columnKeys[0]!)"
          >{{ segment.group }}</th>
        </tr>
        <tr class="column-title-row">
          <th v-for="(header, columnIndex) in table.getFlatHeaders()" :key="header.id" :data-column-id="header.column.id" :class="{ frozen: stickyLeft[header.column.id] !== undefined }" :style="{ width: `${header.getSize()}px`, left: stickyLeft[header.column.id] !== undefined ? `${stickyLeft[header.column.id]}px` : undefined }" scope="col" :aria-colindex="columnIndex + 1" :aria-sort="sortState(header.column.id)">
            <button type="button" class="column-sort-button" :aria-label="sortLabel(header.column.id, header.column.columnDef.header as string)" @click="requestSort(header.column.id)" @keydown="sortWithKeyboard($event, header.column.id)">
              <span>{{ header.column.columnDef.header as string }}</span><ArrowDown v-if="sort?.key === header.column.id && sort.desc" :size="12" aria-hidden="true" /><ArrowUp v-else-if="sort?.key === header.column.id" :size="12" aria-hidden="true" /><ChevronsUpDown v-else :size="12" class="sort-muted" aria-hidden="true" />
            </button>
            <span class="column-resizer" :class="{ resizing: header.column.getIsResizing() }" role="separator" tabindex="0" aria-orientation="vertical" aria-valuemin="54" aria-valuemax="420" :aria-valuenow="header.getSize()" :aria-label="`${header.column.columnDef.header as string}列宽`" title="左右方向键调整列宽；按住 Shift 每次调整 24 像素" @click.stop @mousedown="header.getResizeHandler()($event)" @touchstart="header.getResizeHandler()($event)" @keydown="resizeWithKeyboard($event, header.column.id, header.column.columnDef.header as string)"></span>
          </th>
        </tr>
      </thead>
      <tbody :style="{ height: `${virtualizer.getTotalSize()}px`, width: `${totalWidth}px` }">
        <template v-for="item in renderRows" :key="item.original.id">
          <MachineGroupRow v-if="item.original.rowType === 'machine'" :row="item.original" :collapsed="collapsedMachineIds.includes(item.original.machine.id)" :top="item.virtualRow.start" :width="totalWidth" :row-index="item.virtualRow.index + 3" :column-count="columns.length" :task-count="summaryFor(item.original.machine.id).taskCount" :current-label="summaryFor(item.original.machine.id).currentLabel" :release-at="summaryFor(item.original.machine.id).releaseAt" :drop-enabled="planStatus === 'DRAFT' && canEdit && Boolean(drag.draggedTaskId.value)" :drop-target="drag.dropTargetMachineId.value === item.original.machine.id" @toggle="emit('toggleMachine', $event)" @drop-task="dropAtEnd" @drag-hover="drag.hover" @drag-leave="drag.leave" />
          <ScheduleTaskRow v-else :row="item.original" :columns="columns" :column-sizes="columnSizes" :top="item.virtualRow.start" :width="totalWidth" :row-index="item.virtualRow.index + 3" :sticky-left="stickyLeft" :selected="selectedTaskId === item.original.id" :dragging="drag.draggedTaskId.value === item.original.id" :drop-target="drag.dropTargetMachineId.value === item.original.machine.id" :plan-status="planStatus" :can-edit="canEdit" :can-report="canReport" :pending-edits="pendingEdits" @select="emit('select', $event)" @edit="forwardEdit" @drag-start="startDrag" @drag-end="endDrag" @drag-hover="drag.hover" @drag-leave="drag.leave" @drop-task="dropAtTask" @keyboard-move="forwardKeyboard" @focus-row="recordRowFocus" />
        </template>
      </tbody>
    </table>
    <p id="grid-keyboard-help" class="grid-keyboard-help">键盘：Enter/空格排序 · 左右方向键调列宽 · 草案任务可用 Alt + 方向键移动</p>
    <div class="scheduling-sr-only" role="status" aria-live="polite" aria-atomic="true" data-testid="grid-live-announcement">{{ liveAnnouncement }}</div>
    <div v-if="!rows.length" class="grid-empty">没有符合当前筛选条件的计划任务</div>
  </div>
</template>
