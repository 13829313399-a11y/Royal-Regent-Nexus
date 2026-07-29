<script setup lang="ts">
import { ArrowDown, ArrowUp, GripVertical, LockKeyhole } from '@lucide/vue'
import { computed } from 'vue'
import ScheduleCellEditor from './ScheduleCellEditor.vue'
import {
  formatScheduleCellValue,
  type ScheduleSpreadsheetColumn,
  type ScheduleSpreadsheetColumnKey,
} from './scheduleSpreadsheetColumns'
import type { InjectionMachine, ScheduleTask, SchedulingDensity } from '@/types/injectionScheduling'

const props = defineProps<{
  task: ScheduleTask
  machine: InjectionMachine
  previousTask?: ScheduleTask
  rowIndex: number
  columns: ScheduleSpreadsheetColumn[]
  widths: Record<ScheduleSpreadsheetColumnKey, number>
  frozenOffsets: Record<string, number>
  density: SchedulingDensity
  selected: boolean
  bigScreen: boolean
}>()

const emit = defineEmits<{
  select: [taskId: string]
  navigate: [taskId: string, direction: 'up' | 'down']
  nudge: [taskId: string, direction: 'up' | 'down']
  dragTask: [taskId: string]
  dropTask: [taskId: string, machineId: string, targetIndex: number]
  contextmenu: [event: MouseEvent, taskId: string]
}>()

const sameMoldAsPrevious = computed(() => (
  props.previousTask?.requirement.mold.moldNo === props.task.requirement.mold.moldNo
))

function rowTone() {
  if (props.task.risk === 'overdue') return 'bg-red-50/85'
  if (props.task.risk === 'urgent') return 'bg-orange-50/85'
  if (props.task.risk === 'warning') return 'bg-amber-50/85'
  if (props.task.risk === 'incomplete') return 'bg-violet-50/85'
  if (props.task.current) return props.bigScreen ? 'bg-teal-950/70' : 'bg-teal-50/60'
  return props.bigScreen ? 'bg-[#0e2927]' : 'bg-white'
}

function frozenBackground() {
  if (props.bigScreen) return '#0e2927'
  if (props.task.risk === 'overdue') return '#fef2f2'
  if (props.task.risk === 'urgent') return '#fff7ed'
  if (props.task.risk === 'warning') return '#fffbeb'
  if (props.task.risk === 'incomplete') return '#f5f3ff'
  if (props.task.current) return '#ecfdf5'
  return '#ffffff'
}

function cellValue(column: ScheduleSpreadsheetColumn) {
  return column.value(props.task, props.machine, props.rowIndex)
}

function onDragStart(event: DragEvent) {
  if (props.bigScreen || props.task.current || props.task.locked) {
    event.preventDefault()
    return
  }
  event.dataTransfer?.setData('application/x-injection-task', props.task.id)
  event.dataTransfer?.setData('text/plain', props.task.id)
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
  emit('dragTask', props.task.id)
}

function onDrop(event: DragEvent) {
  const taskId = event.dataTransfer?.getData('application/x-injection-task') || event.dataTransfer?.getData('text/plain')
  if (taskId && taskId !== props.task.id) emit('dropTask', taskId, props.machine.id, props.rowIndex)
}

function onKeydown(event: KeyboardEvent) {
  if (event.altKey && (event.key === 'ArrowUp' || event.key === 'ArrowDown')) {
    event.preventDefault()
    if (!props.bigScreen && !props.task.current && !props.task.locked) {
      emit('nudge', props.task.id, event.key === 'ArrowUp' ? 'up' : 'down')
    }
    return
  }
  if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
    event.preventDefault()
    emit('navigate', props.task.id, event.key === 'ArrowUp' ? 'up' : 'down')
    return
  }
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    emit('select', props.task.id)
  }
}
</script>

<template>
  <tr
    :id="`schedule-task-${task.id}`"
    tabindex="0"
    class="schedule-order-row group outline-none transition-shadow focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-teal-500"
    :class="[rowTone(), selected ? 'ring-2 ring-inset ring-teal-600' : '']"
    :data-task-id="task.id"
    :data-current="task.current"
    @click="emit('select', task.id)"
    @keydown="onKeydown"
    @contextmenu.prevent="emit('contextmenu', $event, task.id)"
    @dragover.prevent
    @drop.prevent="onDrop"
  >
    <td
      v-for="column in columns"
      :key="column.key"
      class="border-b border-r border-slate-200/80 px-2 text-[9px] text-slate-700"
      :class="[
        density === 'compact' ? 'h-[27px]' : 'h-[34px]',
        column.align === 'right' ? 'text-right tabular-nums' : column.align === 'center' ? 'text-center' : 'text-left',
        column.frozen ? 'sticky z-20 shadow-[1px_0_0_#dbe4e6]' : '',
        bigScreen ? '!border-slate-700/70 !text-slate-200' : '',
        column.key === 'moldNo' && sameMoldAsPrevious ? 'border-l-2 !border-l-teal-500' : '',
      ]"
      :style="{
        width: `${widths[column.key]}px`,
        minWidth: `${widths[column.key]}px`,
        maxWidth: `${widths[column.key]}px`,
        left: column.frozen ? `${frozenOffsets[column.key] ?? 0}px` : undefined,
        backgroundColor: column.frozen ? frozenBackground() : undefined,
      }"
      :data-column-key="column.key"
    >
      <div v-if="column.key === 'sequence'" class="flex items-center justify-center gap-0.5">
        <LockKeyhole v-if="task.current || task.locked" class="size-3 text-slate-400" aria-label="当前任务已锁定" />
        <template v-else>
          <button
            type="button"
            draggable="true"
            class="cursor-grab rounded p-0.5 text-slate-400 hover:bg-teal-50 hover:text-teal-700 active:cursor-grabbing"
            :aria-label="`拖动${task.requirement.orderNo}`"
            @dragstart="onDragStart"
            @click.stop
          ><GripVertical class="size-3.5" /></button>
          <span class="w-4 text-center text-[8px] text-slate-400">{{ rowIndex + 1 }}</span>
          <span class="hidden items-center group-hover:inline-flex">
            <button type="button" class="text-slate-400 hover:text-teal-700" aria-label="向前移动" @click.stop="emit('nudge', task.id, 'up')"><ArrowUp class="size-2.5" /></button>
            <button type="button" class="text-slate-400 hover:text-teal-700" aria-label="向后移动" @click.stop="emit('nudge', task.id, 'down')"><ArrowDown class="size-2.5" /></button>
          </span>
        </template>
      </div>
      <ScheduleCellEditor
        v-else-if="column.key === 'remark'"
        :model-value="cellValue(column)"
        :editable="false"
        :aria-label="`${task.requirement.orderNo}备注`"
      />
      <span
        v-else
        class="block truncate"
        :class="{
          'font-black text-red-700': task.risk === 'overdue' && ['deliverySlack', 'plannedEnd', 'status'].includes(column.key),
          'font-black text-orange-700': task.risk === 'urgent' && ['deliverySlack', 'plannedEnd', 'status'].includes(column.key),
          'font-black text-amber-700': task.risk === 'warning' && ['deliverySlack', 'plannedEnd', 'status'].includes(column.key),
          'font-black text-violet-700': task.risk === 'incomplete' && ['machineRequirement', 'status'].includes(column.key),
          'font-black text-teal-900': task.current && ['machine', 'orderNo'].includes(column.key) && !bigScreen,
        }"
        :title="formatScheduleCellValue(cellValue(column))"
      >{{ formatScheduleCellValue(cellValue(column)) }}</span>
    </td>
  </tr>
</template>
