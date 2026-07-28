<script setup lang="ts">
import { AlertTriangle, GripVertical, LockKeyhole, Play, Timer } from '@lucide/vue'
import { computed } from 'vue'
import type { ScheduleTask } from '@/types/injectionScheduling'

const props = defineProps<{ task: ScheduleTask; compact?: boolean }>()
const emit = defineEmits<{ select: [taskId: string]; dragstart: [event: DragEvent, taskId: string] }>()

const completion = computed(() => Math.min(100, Math.round(
  props.task.completedQuantity / Math.max(props.task.quantity, 1) * 100,
)))
</script>

<template>
  <article
    class="group relative min-w-[260px] rounded-xl border p-3.5 text-left shadow-[0_9px_24px_-20px_rgba(15,23,42,.55)] transition hover:-translate-y-0.5 hover:shadow-md"
    :class="[
      task.current
        ? 'min-w-[300px] border-teal-800 bg-teal-950 text-white'
        : 'border-slate-200 bg-white text-slate-900',
      task.risk === 'overdue' && !task.current ? 'border-l-4 border-l-red-500' : '',
      task.risk === 'warning' && !task.current ? 'border-l-4 border-l-amber-500' : '',
      task.risk === 'urgent' && !task.current ? 'border-l-4 border-l-orange-500' : '',
    ]"
    :draggable="!task.locked"
    :aria-label="`${task.moldNo} ${task.productName}`"
    @click="emit('select', task.id)"
    @dragstart="emit('dragstart', $event, task.id)"
  >
    <div class="flex items-center justify-between gap-2">
      <span
        class="inline-flex size-6 items-center justify-center rounded-full text-[11px] font-black"
        :class="task.current ? 'bg-white/12 text-white' : 'bg-slate-100 text-slate-600'"
      >
        <Play v-if="task.current" class="size-3" fill="currentColor" aria-hidden="true" />
        <template v-else>{{ task.sequence }}</template>
      </span>
      <span class="flex items-center gap-1.5">
        <AlertTriangle
          v-if="task.risk === 'overdue' || task.risk === 'urgent'"
          class="size-3.5"
          :class="task.current ? 'text-amber-300' : 'text-red-500'"
          aria-hidden="true"
        />
        <LockKeyhole v-if="task.locked" class="size-3.5 text-amber-300" aria-label="任务已锁定" />
        <GripVertical v-else class="size-4 cursor-grab text-slate-400" aria-label="可拖动任务" />
      </span>
    </div>

    <h3 class="mt-3 truncate text-sm font-black tracking-wide">{{ task.moldNo }}</h3>
    <p class="mt-1 truncate text-[11px]" :class="task.current ? 'text-teal-100' : 'text-slate-500'">
      {{ task.productName }}
    </p>

    <div v-if="!compact" class="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-[10px]">
      <div><span :class="task.current ? 'text-teal-200' : 'text-slate-400'">单号</span><strong class="ml-1">{{ task.orderNo }}</strong></div>
      <div><span :class="task.current ? 'text-teal-200' : 'text-slate-400'">欠数</span><strong class="ml-1">{{ (task.quantity - task.completedQuantity).toLocaleString() }}</strong></div>
      <div><span :class="task.current ? 'text-teal-200' : 'text-slate-400'">颜色</span><strong class="ml-1">{{ task.color }}</strong></div>
      <div><span :class="task.current ? 'text-teal-200' : 'text-slate-400'">目标/日</span><strong class="ml-1">{{ task.dailyTarget.toLocaleString() }}</strong></div>
    </div>

    <div v-if="task.current && !compact" class="mt-3">
      <div class="flex justify-between text-[10px] text-teal-100">
        <span>完成 {{ completion }}%</span>
        <span>{{ task.completedQuantity.toLocaleString() }} / {{ task.quantity.toLocaleString() }}</span>
      </div>
      <div class="mt-1.5 h-1.5 rounded-full bg-white/15">
        <div class="h-full rounded-full bg-teal-300" :style="{ width: `${completion}%` }" />
      </div>
    </div>

    <div class="mt-3 flex items-center justify-between gap-3 border-t pt-2 text-[10px]" :class="task.current ? 'border-white/10 text-teal-100' : 'border-slate-100 text-slate-500'">
      <span class="inline-flex items-center gap-1"><Timer class="size-3" aria-hidden="true" />{{ task.startAt }} → {{ task.endAt }}</span>
      <strong :class="task.risk === 'overdue' ? (task.current ? 'text-amber-300' : 'text-red-600') : ''">{{ task.dueLabel }}</strong>
    </div>
  </article>
</template>

