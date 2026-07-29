<script setup lang="ts">
import { Circle } from '@lucide/vue'
import CompactMachineLane from './CompactMachineLane.vue'
import type { InjectionMachine, ScheduleTask, SchedulingDensity } from '@/types/injectionScheduling'

const props = defineProps<{
  machines: InjectionMachine[]
  tasksByMachine: Map<string, ScheduleTask[]>
  density: SchedulingDensity
  bigScreen: boolean
}>()

const emit = defineEmits<{
  selectTask: [taskId: string]
  selectMachine: [machineId: string]
  requestMove: [taskId: string, targetMachineId: string]
  nudgeTask: [taskId: string, direction: 'up' | 'down']
  openBacklog: [machineId: string]
}>()
</script>

<template>
  <section class="machine-board-shell grid min-h-0 grid-rows-[34px_minmax(0,1fr)] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm" :class="bigScreen ? 'border-slate-800 bg-[#0b2321]' : ''">
    <header class="grid min-w-[1020px] grid-cols-[170px_286px_minmax(0,1fr)_138px] bg-[#104f49] text-[9px] font-black text-white">
      <div class="flex items-center border-r border-white/10 px-3">机台 / 能力约束</div>
      <div class="flex items-center border-r border-white/10 px-3">当前生产任务</div>
      <div class="flex items-center justify-between border-r border-white/10 px-3">
        <span>后续模具队列</span>
        <span class="flex items-center gap-3 text-[8px] font-semibold text-teal-100">
          <i class="inline-flex items-center gap-1"><Circle class="size-1.5 fill-red-400 text-red-400" />逾期</i>
          <i class="inline-flex items-center gap-1"><Circle class="size-1.5 fill-amber-300 text-amber-300" />风险</i>
          <i class="inline-flex items-center gap-1"><Circle class="size-1.5 fill-teal-300 text-teal-300" />正常</i>
        </span>
      </div>
      <div class="flex items-center justify-center">完成 / 操作</div>
    </header>

    <div class="min-h-0 overflow-auto [scrollbar-gutter:stable] [scrollbar-width:thin]" data-testid="machine-board-scroll">
      <CompactMachineLane
        v-for="machine in machines"
        :key="machine.id"
        :machine="machine"
        :tasks="props.tasksByMachine.get(machine.id) ?? []"
        :density="density"
        :big-screen="bigScreen"
        @select-task="emit('selectTask', $event)"
        @select-machine="emit('selectMachine', $event)"
        @request-move="(taskId, machineId) => emit('requestMove', taskId, machineId)"
        @nudge-task="(taskId, direction) => emit('nudgeTask', taskId, direction)"
        @open-backlog="emit('openBacklog', $event)"
      />
      <div v-if="!machines.length" class="grid h-full min-h-72 place-items-center p-8 text-center text-sm text-slate-500">
        没有匹配当前筛选条件的机台。
      </div>
    </div>
  </section>
</template>
