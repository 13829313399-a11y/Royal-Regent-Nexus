<script setup lang="ts">
import { Clock3 } from '@lucide/vue'
import { formatScheduleTime } from '@/lib/injectionSchedulingPresentation'
import type { InjectionMachine, ScheduleTask } from '@/types/injectionScheduling'

defineProps<{
  machines: InjectionMachine[]
  tasksByMachine: Map<string, ScheduleTask[]>
}>()
const emit = defineEmits<{ selectTask: [taskId: string] }>()
</script>

<template>
  <section class="grid min-h-0 grid-rows-[38px_30px_minmax(0,1fr)] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
    <header class="flex items-center justify-between border-b border-slate-200 bg-[#dfecea] px-4">
      <strong class="inline-flex items-center gap-2 text-[11px] text-slate-800">
        <Clock3 class="size-3.5 text-teal-700" aria-hidden="true" />
        未来 7 天机台负荷时间轴
      </strong>
      <span class="text-[9px] text-slate-500">固定 anchorAt + 生产日历演示</span>
    </header>
    <div class="grid min-w-[960px] grid-cols-[150px_1fr] border-b border-slate-100 text-[8px] font-semibold text-slate-400">
      <span class="px-4 py-2">机台</span>
      <div class="grid grid-cols-7 px-3 py-2 text-center">
        <span v-for="day in ['07-28', '07-29', '07-30', '07-31', '08-01', '08-02', '08-03+']" :key="day">{{ day }}</span>
      </div>
    </div>
    <div class="min-h-0 overflow-auto">
      <div class="min-w-[960px]">
        <div
          v-for="machine in machines"
          :key="machine.id"
          class="grid h-[62px] grid-cols-[150px_1fr] border-b border-slate-100 last:border-b-0"
          style="content-visibility:auto; contain-intrinsic-size:62px;"
        >
          <div class="border-r border-slate-100 px-4 py-2">
            <strong class="text-[11px] text-slate-900">{{ machine.name }}</strong>
            <p class="mt-1 text-[8px] text-slate-500">{{ machine.capability.machineClass }} · 负荷 {{ machine.load }}%</p>
          </div>
          <div class="flex items-center gap-1.5 overflow-hidden bg-[linear-gradient(90deg,transparent_14.1%,#e2e8f0_14.2%,transparent_14.4%,transparent_28.4%,#e2e8f0_28.5%,transparent_28.7%,transparent_42.7%,#e2e8f0_42.8%,transparent_43%,transparent_57%,#e2e8f0_57.1%,transparent_57.3%,transparent_71.3%,#e2e8f0_71.4%,transparent_71.6%,transparent_85.6%,#e2e8f0_85.7%,transparent_85.9%)] px-3">
            <button
              v-for="task in tasksByMachine.get(machine.id) ?? []"
              :key="task.id"
              type="button"
              class="min-w-24 flex-1 rounded-md px-2 py-1.5 text-left text-[8px] font-bold shadow-sm"
              :class="{
                'bg-teal-900 text-white': task.current,
                'bg-red-50 text-red-800 ring-1 ring-red-200': !task.current && task.risk === 'overdue',
                'bg-amber-50 text-amber-800 ring-1 ring-amber-200': !task.current && task.risk === 'warning',
                'bg-orange-50 text-orange-800 ring-1 ring-orange-200': !task.current && task.risk === 'urgent',
                'bg-violet-50 text-violet-800 ring-1 ring-violet-200': !task.current && task.risk === 'incomplete',
                'bg-white text-slate-700 ring-1 ring-slate-200': !task.current && task.risk === 'normal',
              }"
              @click="emit('selectTask', task.id)"
            >
              <span class="block truncate">{{ task.requirement.mold.moldNo }}</span>
              <span class="mt-0.5 block truncate font-normal opacity-70">{{ formatScheduleTime(task.timing.plannedEnd) }}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
