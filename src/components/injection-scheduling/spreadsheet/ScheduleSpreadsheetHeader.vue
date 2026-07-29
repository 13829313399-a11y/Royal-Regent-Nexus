<script setup lang="ts">
import { onBeforeUnmount } from 'vue'
import type {
  ScheduleSpreadsheetColumn,
  ScheduleSpreadsheetColumnKey,
} from './scheduleSpreadsheetColumns'

const props = defineProps<{
  columns: ScheduleSpreadsheetColumn[]
  widths: Record<ScheduleSpreadsheetColumnKey, number>
  frozenOffsets: Record<string, number>
}>()

const emit = defineEmits<{
  resize: [key: ScheduleSpreadsheetColumnKey, width: number]
}>()

interface ColumnGroup {
  label: string
  span: number
}

function groups() {
  const result: ColumnGroup[] = []
  for (const column of props.columns) {
    const last = result.at(-1)
    if (last?.label === column.group) last.span += 1
    else result.push({ label: column.group, span: 1 })
  }
  return result
}

let resizing:
  | { key: ScheduleSpreadsheetColumnKey; startX: number; startWidth: number; min: number; max: number }
  | undefined

function handleResizeMove(event: MouseEvent) {
  if (!resizing) return
  const width = Math.max(resizing.min, Math.min(resizing.max, resizing.startWidth + event.clientX - resizing.startX))
  emit('resize', resizing.key, width)
}

function stopResize() {
  resizing = undefined
  document.removeEventListener('mousemove', handleResizeMove)
  document.removeEventListener('mouseup', stopResize)
}

function startResize(event: MouseEvent, column: ScheduleSpreadsheetColumn) {
  event.preventDefault()
  event.stopPropagation()
  resizing = {
    key: column.key,
    startX: event.clientX,
    startWidth: props.widths[column.key],
    min: column.minWidth,
    max: column.maxWidth,
  }
  document.addEventListener('mousemove', handleResizeMove)
  document.addEventListener('mouseup', stopResize)
}

onBeforeUnmount(stopResize)
</script>

<template>
  <thead class="text-[9px] font-black">
    <tr>
      <th
        v-for="group in groups()"
        :key="group.label"
        :colspan="group.span"
        scope="colgroup"
        class="sticky top-0 z-30 h-[25px] border-b border-r border-teal-900/40 bg-[#0d4d47] px-2 text-left text-[8px] uppercase tracking-[0.08em] text-teal-100"
      >
        {{ group.label }}
      </th>
    </tr>
    <tr>
      <th
        v-for="column in columns"
        :key="column.key"
        scope="col"
        class="sticky top-[25px] z-30 h-[31px] select-none border-b border-r border-slate-200 bg-[#e2eeec] px-2 text-slate-700"
        :class="[
          column.align === 'right' ? 'text-right' : column.align === 'center' ? 'text-center' : 'text-left',
          column.frozen ? '!z-40 shadow-[1px_0_0_#cbd5e1]' : '',
        ]"
        :style="{
          width: `${widths[column.key]}px`,
          minWidth: `${widths[column.key]}px`,
          maxWidth: `${widths[column.key]}px`,
          left: column.frozen ? `${frozenOffsets[column.key] ?? 0}px` : undefined,
        }"
        :data-column-key="column.key"
      >
        <span class="block truncate" :title="column.label">{{ column.label }}</span>
        <span
          class="absolute inset-y-0 right-[-3px] z-10 w-1.5 cursor-col-resize hover:bg-teal-500/40"
          role="separator"
          :aria-label="`调整${column.label}列宽`"
          @mousedown="startResize($event, column)"
        />
      </th>
    </tr>
  </thead>
</template>
