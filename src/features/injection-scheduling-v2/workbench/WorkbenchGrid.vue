<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { createColumnHelper, getCoreRowModel, useVueTable, type ColumnDef } from '@tanstack/vue-table'
import { useVirtualizer } from '@tanstack/vue-virtual'
import { FileSpreadsheet, PencilLine, SearchX } from '@lucide/vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { buildPasteChanges, formatWorkbenchCell, normalizeWorkbenchEdit } from './columns'
import { dueSlackPresentation, formatAClass, priorityPresentation, statusPresentation } from './presentation'
import WorkbenchActionButton from './ui/WorkbenchActionButton.vue'
import type { WorkbenchCellChange, WorkbenchColumn, WorkbenchJob } from './types'

const props = defineProps<{
  jobs: WorkbenchJob[]
  columns: WorkbenchColumn[]
  selectedJobId: string | null
  editable: boolean
  pendingKeys: string[]
}>()
const emit = defineEmits<{
  select: [jobId: string]
  stage: [changes: WorkbenchCellChange[]]
  error: [message: string]
  clearFilters: []
  import: []
}>()

const scrollElement = ref<HTMLElement | null>(null)
const focused = ref({ row: 0, column: 0 })
const columnHelper = createColumnHelper<WorkbenchJob>()
const columnDefs = computed<ColumnDef<WorkbenchJob>[]>(() => props.columns.map((column) => columnHelper.accessor(column.key, {
  id: String(column.key), header: column.label, size: column.width,
})) as ColumnDef<WorkbenchJob>[])
const table = useVueTable({
  data: [],
  get columns() { return columnDefs.value },
  getCoreRowModel: getCoreRowModel(),
})
const virtualizer = useVirtualizer(computed(() => ({
  count: props.jobs.length,
  getScrollElement: () => scrollElement.value,
  estimateSize: () => 38,
  overscan: 12,
})))
const virtualRows = computed(() => virtualizer.value.getVirtualItems())
const columnWidth = (column: WorkbenchColumn) => table.getColumn(String(column.key))?.getSize() ?? column.width
const totalWidth = computed(() => table.getTotalSize())
const stickyLeft = computed(() => {
  let left = 0
  return Object.fromEntries(props.columns.map((column) => {
    const value = column.frozen ? left : undefined
    if (column.frozen) left += columnWidth(column)
    return [column.key, value]
  })) as Partial<Record<keyof WorkbenchJob, number>>
})

function pending(job: WorkbenchJob, column: WorkbenchColumn) {
  return column.editable ? props.pendingKeys.includes(`${job.id}:${column.editable}`) : false
}

function canEdit(job: WorkbenchJob, column: WorkbenchColumn) {
  if (!props.editable || !column.editable) return false
  if (column.editable === 'warehouseText' || column.editable === 'orderRemark') return true
  return Boolean(job.taskId && job.taskRevision)
}

function cellStyle(column: WorkbenchColumn) {
  const left = stickyLeft.value[column.key]
  return {
    width: `${columnWidth(column)}px`,
    minWidth: `${columnWidth(column)}px`,
    left: left === undefined ? undefined : `${left}px`,
  }
}

function stage(job: WorkbenchJob, column: WorkbenchColumn, raw: string) {
  if (!column.editable) return
  try {
    emit('stage', [{
      jobId: job.id,
      expectedTaskRevision: job.taskRevision,
      expectedOrderRevision: job.orderRevision,
      field: column.editable,
      value: normalizeWorkbenchEdit(column.editable, raw),
    }])
  } catch (cause) {
    emit('error', cause instanceof Error ? cause.message : '单元格值无效')
  }
}

function handlePaste(event: ClipboardEvent, rowIndex: number, columnIndex: number) {
  const value = event.clipboardData?.getData('text/plain') ?? ''
  if (!value) return
  event.preventDefault()
  try {
    emit('stage', buildPasteChanges(props.jobs, props.columns, rowIndex, columnIndex, value))
  } catch (cause) {
    emit('error', cause instanceof Error ? cause.message : '粘贴内容无效')
  }
}

async function focusCell(row: number, column: number) {
  const safeRow = Math.max(0, Math.min(props.jobs.length - 1, row))
  const safeColumn = Math.max(0, Math.min(props.columns.length - 1, column))
  virtualizer.value.scrollToIndex(safeRow, { align: 'auto' })
  await nextTick()
  const cell = scrollElement.value?.querySelector<HTMLElement>(`[data-grid-cell="${safeRow}:${safeColumn}"]`)
  cell?.focus()
  focused.value = { row: safeRow, column: safeColumn }
}

function handleKeydown(event: KeyboardEvent, rowIndex: number, columnIndex: number) {
  if (event.key === 'ArrowUp') { event.preventDefault(); void focusCell(rowIndex - 1, columnIndex) }
  else if (event.key === 'ArrowDown') { event.preventDefault(); void focusCell(rowIndex + 1, columnIndex) }
  else if (event.key === 'ArrowLeft' && !(event.target instanceof HTMLInputElement)) { event.preventDefault(); void focusCell(rowIndex, columnIndex - 1) }
  else if (event.key === 'ArrowRight' && !(event.target instanceof HTMLInputElement)) { event.preventDefault(); void focusCell(rowIndex, columnIndex + 1) }
  else if (event.key === 'Tab') {
    event.preventDefault()
    const delta = event.shiftKey ? -1 : 1
    const flat = rowIndex * props.columns.length + columnIndex + delta
    void focusCell(Math.floor(Math.max(0, flat) / props.columns.length), Math.max(0, flat) % props.columns.length)
  }
}

function inputValue(job: WorkbenchJob, column: WorkbenchColumn) {
  const value = job[column.key]
  return value == null ? '' : String(value)
}

function cellTone(job: WorkbenchJob, column: WorkbenchColumn) {
  if (column.key === 'status') return statusPresentation(job.status)
  if (column.key === 'priority') return priorityPresentation(job.priority)
  if (column.key === 'deliverySlackDays') return dueSlackPresentation(job.deliverySlackDays)
  return null
}

function semanticCellClass(column: WorkbenchColumn) {
  return {
    numeric: ['orderQuantity', 'outstandingQuantity', 'shiftTargetQuantity', 'todayDayQuantity', 'todayNightQuantity', 'completedQuantity', 'reportedQuantity'].includes(String(column.key)),
    'cell-status': column.key === 'status',
    'cell-priority': column.key === 'priority',
    'cell-slack': column.key === 'deliverySlackDays',
  }
}
</script>

<template>
  <div
    ref="scrollElement"
    class="wb-grid-scroll"
    role="grid"
    aria-label="注塑排产在线表格"
    :aria-rowcount="jobs.length + 1"
    :aria-colcount="columns.length"
    data-testid="workbench-virtual-grid"
  >
    <div class="wb-grid-canvas" :style="{ width: `${totalWidth}px` }">
      <div class="wb-grid-header" role="row">
        <div
          v-for="column in columns"
          :key="column.key"
          class="wb-grid-head-cell"
          :class="{ frozen: column.frozen }"
          :style="cellStyle(column)"
          role="columnheader"
        >
          <span>{{ column.label }}</span><PencilLine v-if="column.editable" :size="11" aria-label="可编辑" />
        </div>
      </div>
      <div class="wb-grid-body" :style="{ height: `${virtualizer.getTotalSize()}px` }">
        <div
          v-for="virtualRow in virtualRows"
          :key="jobs[virtualRow.index]?.id"
          class="wb-grid-row"
          :class="{ selected: jobs[virtualRow.index]?.id === selectedJobId, overdue: (jobs[virtualRow.index]?.deliverySlackDays ?? 0) < 0 }"
          :style="{ transform: `translateY(${virtualRow.start}px)`, width: `${totalWidth}px` }"
          role="row"
          :aria-rowindex="virtualRow.index + 2"
          :aria-selected="jobs[virtualRow.index]?.id === selectedJobId"
        >
          <div
            v-for="(column, columnIndex) in columns"
            :key="column.key"
            class="wb-grid-cell"
            :class="[{ frozen: column.frozen, editable: canEdit(jobs[virtualRow.index]!, column), pending: pending(jobs[virtualRow.index]!, column) }, semanticCellClass(column)]"
            :style="cellStyle(column)"
            role="gridcell"
            tabindex="0"
            :data-grid-cell="`${virtualRow.index}:${columnIndex}`"
            :title="formatWorkbenchCell(jobs[virtualRow.index]!, column)"
            @focus="focused = { row: virtualRow.index, column: columnIndex }"
            @click="emit('select', jobs[virtualRow.index]!.id)"
            @paste="handlePaste($event, virtualRow.index, columnIndex)"
            @keydown="handleKeydown($event, virtualRow.index, columnIndex)"
          >
            <select
              v-if="canEdit(jobs[virtualRow.index]!, column) && column.editable === 'status'"
              :value="jobs[virtualRow.index]!.status"
              aria-label="任务状态"
              @change="stage(jobs[virtualRow.index]!, column, ($event.target as HTMLSelectElement).value)"
            >
              <option value="PLANNED">已排</option>
              <option value="PAUSED">暂停</option>
            </select>
            <select
              v-else-if="canEdit(jobs[virtualRow.index]!, column) && column.editable === 'locked'"
              :value="jobs[virtualRow.index]!.locked ? '是' : '否'"
              aria-label="是否锁定"
              @change="stage(jobs[virtualRow.index]!, column, ($event.target as HTMLSelectElement).value)"
            >
              <option>否</option><option>是</option>
            </select>
            <StatusPill
              v-else-if="cellTone(jobs[virtualRow.index]!, column)"
              :label="cellTone(jobs[virtualRow.index]!, column)!.label"
              :tone="cellTone(jobs[virtualRow.index]!, column)!.tone"
              compact
            />
            <span v-else-if="column.key === 'requiredMachineA'" class="wb-a-class">{{ formatAClass(jobs[virtualRow.index]!.requiredMachineA) }}</span>
            <input
              v-else-if="canEdit(jobs[virtualRow.index]!, column)"
              :value="inputValue(jobs[virtualRow.index]!, column)"
              :aria-label="`${column.label}编辑`"
              @change="stage(jobs[virtualRow.index]!, column, ($event.target as HTMLInputElement).value)"
              @paste="handlePaste($event, virtualRow.index, columnIndex)"
              @keydown="handleKeydown($event, virtualRow.index, columnIndex)"
            />
            <span v-else>{{ formatWorkbenchCell(jobs[virtualRow.index]!, column) }}</span>
          </div>
        </div>
      </div>
    </div>
    <div v-if="!jobs.length" class="wb-grid-empty">
      <span class="wb-empty-icon"><SearchX :size="24" /></span>
      <h3>没有符合当前条件的任务</h3>
      <p>可以清除筛选条件，或导入新的需求表与生产日计划表。</p>
      <div><WorkbenchActionButton variant="secondary" @click="emit('clearFilters')">清除筛选</WorkbenchActionButton><WorkbenchActionButton variant="primary" @click="emit('import')"><template #icon><FileSpreadsheet :size="15" /></template>导入 Excel</WorkbenchActionButton></div>
    </div>
  </div>
</template>
