<script setup lang="ts">
import { ChevronDown, ChevronUp, GripVertical } from '@lucide/vue'
import ScheduleImpactBadge from './ScheduleImpactBadge.vue'
import { formatScheduleTime, formatSlack, taskRiskMeta } from '@/lib/injectionSchedulingPresentation'
import type { ScheduleTask } from '@/types/injectionScheduling'

defineProps<{ task: ScheduleTask; sameMold: boolean }>()
const emit = defineEmits<{
  select: [taskId: string]
  dragstart: [event: DragEvent, taskId: string]
  nudge: [taskId: string, direction: 'up' | 'down']
}>()
</script>

<template>
  <article
    class="queue-task-chip group relative h-full w-[174px] shrink-0 rounded-lg border bg-white px-2.5 py-2 text-left shadow-[0_8px_20px_-19px_rgba(15,23,42,.7)] transition hover:-translate-y-px"
    :class="[
      task.risk === 'overdue' ? 'border-l-[3px] border-l-red-500' : '',
      task.risk === 'warning' ? 'border-l-[3px] border-l-amber-500' : '',
      task.risk === 'urgent' ? 'border-l-[3px] border-l-orange-500' : '',
      task.risk === 'incomplete' ? 'border-l-[3px] border-l-violet-500' : '',
      sameMold ? 'ring-1 ring-inset ring-teal-200' : 'border-slate-200',
    ]"
    draggable="true"
    :aria-label="`${task.requirement.mold.moldNo}，可拖动，Alt 加上下方向键可调整顺序`"
    tabindex="0"
    @click="emit('select', task.id)"
    @dragstart="emit('dragstart', $event, task.id)"
    @keydown.alt.up.prevent="emit('nudge', task.id, 'up')"
    @keydown.alt.down.prevent="emit('nudge', task.id, 'down')"
  >
    <div class="flex items-center gap-1.5">
      <span class="grid size-4 place-items-center rounded bg-slate-100 text-[8px] font-black text-slate-500">{{ task.sequence }}</span>
      <strong class="min-w-0 flex-1 truncate text-[10px] text-slate-900">{{ task.requirement.mold.moldNo }}</strong>
      <i class="size-1.5 rounded-full" :class="taskRiskMeta[task.risk].className.split(' ')[0].replace('text-', 'bg-')" />
      <GripVertical class="size-3 cursor-grab text-slate-300" aria-hidden="true" />
    </div>
    <p class="mt-1 truncate text-[8px] text-slate-500">{{ task.requirement.productName }}</p>
    <div class="mt-1.5 grid grid-cols-2 gap-x-2 gap-y-1 text-[8px] text-slate-400">
      <span>颜色 <b class="text-slate-700">{{ task.requirement.color }}</b></span>
      <span>欠数 <b class="text-slate-700">{{ task.production.remainingQuantity.toLocaleString() }}</b></span>
      <span>材料 <b class="text-slate-700">{{ task.requirement.material.split(' ')[0] }}</b></span>
      <ScheduleImpactBadge :changeover="task.changeover" />
    </div>
    <div class="mt-1.5 flex items-center justify-between border-t border-slate-100 pt-1.5 text-[8px]">
      <span class="text-slate-500">{{ formatScheduleTime(task.timing.plannedEnd) }}</span>
      <strong :class="task.timing.slackHours < 0 ? 'text-red-600' : 'text-teal-700'">{{ formatSlack(task.timing.slackHours) }}</strong>
    </div>
    <span v-if="sameMold" class="absolute bottom-1 right-1 rounded bg-teal-50 px-1 text-[7px] font-black text-teal-700">同模</span>
    <span class="sr-only">
      <button type="button" @click.stop="emit('nudge', task.id, 'up')"><ChevronUp />上移</button>
      <button type="button" @click.stop="emit('nudge', task.id, 'down')"><ChevronDown />下移</button>
    </span>
  </article>
</template>
