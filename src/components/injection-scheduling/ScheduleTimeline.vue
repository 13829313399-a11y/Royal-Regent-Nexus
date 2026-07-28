<script setup lang="ts">
import { Clock3 } from '@lucide/vue'
import { computed } from 'vue'
import type { InjectionMachine, ScheduleTask } from '@/types/injectionScheduling'

const props = defineProps<{ machines: InjectionMachine[]; tasks: ScheduleTask[] }>()
const emit = defineEmits<{ selectTask: [taskId: string] }>()

const taskMap = computed(() => new Map(props.tasks.map((task) => [task.id, task])))

function tasksFor(machine: InjectionMachine) {
  return machine.taskIds
    .map((id) => taskMap.value.get(id))
    .filter((task): task is ScheduleTask => Boolean(task))
}
</script>

<template>
  <section class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
    <header class="flex items-center justify-between border-b border-slate-200 bg-[#dfecea] px-5 py-3">
      <strong class="inline-flex items-center gap-2 text-sm text-slate-800">
        <Clock3 class="size-4 text-teal-700" aria-hidden="true" />
        机台负荷时间轴
      </strong>
      <span class="text-[11px] text-slate-500">时间宽度按任务数量演示，正式版由后端返回精确区间</span>
    </header>

    <div class="overflow-x-auto">
      <div class="min-w-[1050px]">
        <div class="grid grid-cols-[150px_1fr] border-b border-slate-100 text-[10px] font-semibold text-slate-400">
          <span class="px-4 py-3">机台</span>
          <div class="grid grid-cols-6 px-3 py-3 text-center">
            <span>07-21</span><span>07-22</span><span>07-23</span><span>07-24</span><span>07-25</span><span>07-26+</span>
          </div>
        </div>

        <div
          v-for="machine in machines"
          :key="machine.id"
          class="grid min-h-20 grid-cols-[150px_1fr] border-b border-slate-100 last:border-b-0"
          style="content-visibility: auto; contain-intrinsic-size: 82px;"
        >
          <div class="border-r border-slate-100 px-4 py-4">
            <strong class="text-sm text-slate-900">{{ machine.name }}</strong>
            <p class="mt-1 text-[10px] text-slate-500">{{ machine.machineType }} · 负荷 {{ machine.load }}%</p>
          </div>
          <div class="relative flex items-center gap-1.5 overflow-hidden bg-[linear-gradient(90deg,transparent_16.5%,#e2e8f0_16.6%,transparent_16.8%,transparent_33.1%,#e2e8f0_33.2%,transparent_33.4%,transparent_49.8%,#e2e8f0_49.9%,transparent_50.1%,transparent_66.5%,#e2e8f0_66.6%,transparent_66.8%,transparent_83.1%,#e2e8f0_83.2%,transparent_83.4%)] px-3">
            <button
              v-for="task in tasksFor(machine)"
              :key="task.id"
              type="button"
              class="group min-w-24 flex-1 rounded-lg px-3 py-2 text-left text-[10px] font-bold shadow-sm transition hover:-translate-y-0.5"
              :class="{
                'bg-teal-900 text-white': task.current,
                'bg-red-50 text-red-800 ring-1 ring-red-200': !task.current && task.risk === 'overdue',
                'bg-amber-50 text-amber-800 ring-1 ring-amber-200': !task.current && task.risk === 'warning',
                'bg-white text-slate-700 ring-1 ring-slate-200': !task.current && task.risk === 'normal',
                'bg-orange-50 text-orange-800 ring-1 ring-orange-200': !task.current && task.risk === 'urgent',
              }"
              @click="emit('selectTask', task.id)"
            >
              <span class="block truncate">{{ task.moldNo }}</span>
              <span class="mt-0.5 block truncate font-normal opacity-70">{{ task.startAt }}</span>
            </button>
            <span v-if="!tasksFor(machine).length" class="text-xs text-slate-400">暂无任务</span>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

