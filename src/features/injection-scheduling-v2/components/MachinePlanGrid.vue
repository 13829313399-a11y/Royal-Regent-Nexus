<script setup lang="ts">
import { computed, ref } from 'vue'
import { createColumnHelper, getCoreRowModel, useVueTable, type ColumnDef, type ColumnSizingState } from '@tanstack/vue-table'
import { useVirtualizer } from '@tanstack/vue-virtual'
import { ArrowDown, ArrowUp, ChevronsUpDown } from '@lucide/vue'
import MachineGroupRow from './MachineGroupRow.vue'
import ScheduleTaskRow from './ScheduleTaskRow.vue'
import { useScheduleDragDrop } from '../composables/useScheduleDragDrop'
import type { CellDraft, EditableCellKey, ScheduleGridRow, SchedulingColumnDefinition } from '../types'
import { formatBusinessDateTime } from '@/lib/dateTime'

const props = defineProps<{ rows: ScheduleGridRow[]; columns: SchedulingColumnDefinition[]; collapsedMachineIds: string[]; widths: Record<string, number>; sort: { key: string; desc: boolean } | null; selectedTaskId: string | null; planStatus: string; canEdit: boolean; canReport: boolean; pendingEdits: Record<string, CellDraft> }>()
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
const helper = createColumnHelper<ScheduleGridRow>()
const columnDefs = computed<ColumnDef<ScheduleGridRow>[]>(() => props.columns.map((column) => helper.accessor(column.key, {
  id: String(column.key), header: column.title, size: props.widths[String(column.key)] ?? column.width,
  minSize: 54, maxSize: 420, cell: (info) => String(info.getValue() ?? '—'), meta: { align: column.align ?? 'left', group: column.group, frozen: column.frozen },
})) as ColumnDef<ScheduleGridRow>[])
const sizing = ref<ColumnSizingState>({})
const table = useVueTable({
  get data() { return props.rows }, get columns() { return columnDefs.value }, getCoreRowModel: getCoreRowModel(), columnResizeMode: 'onChange',
  state: { get columnSizing() { return sizing.value } },
  onColumnSizingChange: (updater) => {
    sizing.value = typeof updater === 'function' ? updater(sizing.value) : updater
    Object.entries(sizing.value).forEach(([key, value]) => emit('resize', key, value))
  },
})
const tableRows = computed(() => table.getRowModel().rows)
const virtualizer = useVirtualizer(computed(() => ({ count: tableRows.value.length, getScrollElement: () => scrollElement.value, estimateSize: (index) => tableRows.value[index]?.original.rowType === 'machine' ? 44 : 38, overscan: 12 })))
const virtualRows = computed(() => virtualizer.value.getVirtualItems())
const totalWidth = computed(() => table.getTotalSize())
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
function groupCount(machineId: string) { return props.rows.filter((row) => row.rowType === 'task' && row.machine.id === machineId).length }
function currentLabel(machineId: string) { const row = props.rows.find((item) => item.rowType === 'task' && item.machine.id === machineId && item.status === 'RUNNING'); return row ? `${row.moldNo} · ${row.productName}` : '' }
function releaseAt(machineId: string) {
  const value = props.rows.filter((row) => row.rowType === 'task' && row.machine.id === machineId).at(-1)?.plannedFinish
  const formatted = formatBusinessDateTime(value, { fallback: '' })
  return formatted ? formatted.slice(5) : ''
}
function dropAtEnd(machineId: string, event: DragEvent) { drag.drop(machineId, groupCount(machineId), event) }
function dropAtTask(machineId: string, sequence: number, event: DragEvent) { drag.drop(machineId, sequence, event) }
function forwardEdit(taskId: string, key: EditableCellKey, value: string | number) { emit('edit', taskId, key, value) }
function forwardKeyboard(taskId: string, direction: 'up' | 'down' | 'previous-machine' | 'next-machine') { emit('keyboardMove', taskId, direction) }
</script>

<template>
  <div ref="scrollElement" class="machine-plan-scroll" data-testid="machine-plan-virtual-scroll">
    <table class="machine-plan-table" :style="{ width: `${totalWidth}px` }">
      <thead :style="{ width: `${totalWidth}px` }">
        <tr class="column-group-row"><th v-for="column in table.getVisibleLeafColumns()" :key="`group-${column.id}`" :style="{ width: `${column.getSize()}px` }">{{ (column.columnDef.meta as { group?: string } | undefined)?.group }}</th></tr>
        <tr class="column-title-row">
          <th v-for="header in table.getFlatHeaders()" :key="header.id" :class="{ frozen: stickyLeft[header.column.id] !== undefined }" :style="{ width: `${header.getSize()}px`, left: stickyLeft[header.column.id] !== undefined ? `${stickyLeft[header.column.id]}px` : undefined }" @click="emit('sort', header.column.id)">
            <span>{{ header.column.columnDef.header as string }}</span><ArrowDown v-if="sort?.key === header.column.id && sort.desc" :size="12" /><ArrowUp v-else-if="sort?.key === header.column.id" :size="12" /><ChevronsUpDown v-else :size="12" class="sort-muted" />
            <i class="column-resizer" :class="{ resizing: header.column.getIsResizing() }" @click.stop @mousedown="header.getResizeHandler()($event)" @touchstart="header.getResizeHandler()($event)"></i>
          </th>
        </tr>
      </thead>
      <tbody :style="{ height: `${virtualizer.getTotalSize()}px`, width: `${totalWidth}px` }">
        <template v-for="virtualRow in virtualRows" :key="tableRows[virtualRow.index]!.id">
          <MachineGroupRow v-if="tableRows[virtualRow.index]!.original.rowType === 'machine'" :row="tableRows[virtualRow.index]!.original" :collapsed="collapsedMachineIds.includes(tableRows[virtualRow.index]!.original.machine.id)" :top="virtualRow.start" :width="totalWidth" :task-count="groupCount(tableRows[virtualRow.index]!.original.machine.id)" :current-label="currentLabel(tableRows[virtualRow.index]!.original.machine.id)" :release-at="releaseAt(tableRows[virtualRow.index]!.original.machine.id)" :drop-enabled="planStatus === 'DRAFT' && canEdit && Boolean(drag.draggedTaskId.value)" :drop-target="drag.dropTargetMachineId.value === tableRows[virtualRow.index]!.original.machine.id" @toggle="emit('toggleMachine', $event)" @drop-task="dropAtEnd" @drag-hover="drag.hover" @drag-leave="drag.leave" />
          <ScheduleTaskRow v-else :row="tableRows[virtualRow.index]!" :top="virtualRow.start" :width="totalWidth" :sticky-left="stickyLeft" :selected="selectedTaskId === tableRows[virtualRow.index]!.original.id" :dragging="drag.draggedTaskId.value === tableRows[virtualRow.index]!.original.id" :drop-target="drag.dropTargetMachineId.value === tableRows[virtualRow.index]!.original.machine.id" :plan-status="planStatus" :can-edit="canEdit" :can-report="canReport" :pending-edits="pendingEdits" @select="emit('select', $event)" @edit="forwardEdit" @drag-start="drag.start" @drag-end="drag.end" @drag-hover="drag.hover" @drag-leave="drag.leave" @drop-task="dropAtTask" @keyboard-move="forwardKeyboard" />
        </template>
      </tbody>
    </table>
    <div v-if="!rows.length" class="grid-empty">没有符合当前筛选条件的计划任务</div>
  </div>
</template>
