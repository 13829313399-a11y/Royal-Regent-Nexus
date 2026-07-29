<script setup lang="ts">
import { LockKeyhole } from '@lucide/vue'
import { computed } from 'vue'
import { formatScheduleTime, formatSlack } from '@/lib/injectionSchedulingPresentation'
import type { ScheduleTask } from '@/types/injectionScheduling'

const props = defineProps<{ task: ScheduleTask | null }>()
const emit = defineEmits<{ select: [taskId: string] }>()

const completion = computed(() => {
  if (!props.task) return 0
  return Math.round(props.task.production.completedQuantity / Math.max(props.task.production.orderQuantity, 1) * 100)
})
</script>

<template>
  <button
    v-if="task"
    type="button"
    class="current-task-card relative h-full w-full overflow-hidden rounded-lg bg-gradient-to-br from-[#0b4943] to-[#07322f] px-3 py-2 text-left text-white shadow-sm"
    :aria-label="`查看当前任务 ${task.requirement.mold.moldNo}`"
    @click="emit('select', task.id)"
  >
    <div class="flex items-center gap-2">
      <span class="inline-flex items-center gap-1 rounded bg-teal-400/15 px-1.5 py-0.5 text-[8px] font-black text-teal-100">
        <i class="size-1.5 rounded-full bg-teal-300 motion-safe:animate-pulse" />
        生产中
      </span>
      <strong class="min-w-0 flex-1 truncate text-[12px]">{{ task.requirement.mold.moldNo }}</strong>
      <LockKeyhole class="size-3 text-amber-200" aria-label="当前任务已锁定" />
    </div>
    <p class="mt-1 truncate text-[9px] text-teal-100">{{ task.requirement.productName }}</p>
    <div class="mt-1.5 grid grid-cols-3 gap-2 text-[8px]">
      <span class="truncate text-teal-200">单号 <b class="text-white">{{ task.requirement.orderNo }}</b></span>
      <span class="text-teal-200">欠数 <b class="text-white">{{ task.production.remainingQuantity.toLocaleString() }}</b></span>
      <span class="text-teal-200">日目标 <b class="text-white">{{ task.production.effectiveDailyTarget.toLocaleString() }}</b></span>
    </div>
    <div class="mt-2 flex items-center gap-2">
      <div class="h-1 flex-1 overflow-hidden rounded-full bg-white/12">
        <i class="block h-full rounded-full bg-teal-300 transition-[width] duration-300" :style="{ width: `${completion}%` }" />
      </div>
      <span class="text-[8px] text-teal-100">{{ completion }}%</span>
      <span class="text-[8px] font-black" :class="task.timing.slackHours < 0 ? 'text-amber-200' : 'text-teal-100'">
        {{ formatScheduleTime(task.timing.plannedEnd) }} · {{ formatSlack(task.timing.slackHours) }}
      </span>
    </div>
  </button>
  <div v-else class="grid h-full place-items-center rounded-lg border border-dashed border-slate-200 bg-white/70 text-center text-[9px] text-slate-400">
    <span>当前空闲 · 可接待排订单</span>
  </div>
</template>
