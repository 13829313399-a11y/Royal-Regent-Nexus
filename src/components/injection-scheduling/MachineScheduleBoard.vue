<script setup lang="ts">
import { Circle } from '@lucide/vue'
import { computed } from 'vue'
import MachineLane from './MachineLane.vue'
import type { InjectionMachine, ScheduleTask } from '@/types/injectionScheduling'

const props = defineProps<{
  machines: InjectionMachine[]
  tasks: ScheduleTask[]
  detailsExpanded: boolean
}>()

const emit = defineEmits<{
  selectTask: [taskId: string]
  requestMove: [taskId: string, targetMachineId: string]
}>()

const taskMap = computed(() => {
  const map = new Map<string, ScheduleTask>()
  props.tasks.forEach((task) => map.set(task.id, task))
  return map
})

function tasksForMachine(machine: InjectionMachine) {
  return machine.taskIds
    .map((id) => taskMap.value.get(id))
    .filter((task): task is ScheduleTask => Boolean(task))
}

function forwardMove(taskId: string, targetMachineId: string) {
  emit('requestMove', taskId, targetMachineId)
}
</script>

<template>
  <section class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
    <header class="grid min-w-[1050px] grid-cols-[250px_minmax(0,1fr)] border-b border-slate-200 bg-[#dfecea] text-[11px] font-black text-slate-600">
      <div class="border-r border-slate-300/70 px-4 py-3">机台 / 能力约束</div>
      <div class="flex items-center justify-between gap-4 px-4 py-3">
        <span>当前任务 → 后续模具排队</span>
        <span class="flex gap-3 font-semibold">
          <span class="inline-flex items-center gap-1 text-teal-700"><Circle class="size-2 fill-current" aria-hidden="true" />生产中</span>
          <span class="inline-flex items-center gap-1 text-red-600"><Circle class="size-2 fill-current" aria-hidden="true" />超期</span>
          <span class="inline-flex items-center gap-1 text-amber-600"><Circle class="size-2 fill-current" aria-hidden="true" />风险</span>
          <span class="inline-flex items-center gap-1 text-slate-500"><Circle class="size-2 fill-current" aria-hidden="true" />空闲</span>
        </span>
      </div>
    </header>
    <div class="overflow-x-auto">
      <MachineLane
        v-for="machine in machines"
        :key="machine.id"
        :machine="machine"
        :tasks="tasksForMachine(machine)"
        :details-expanded="detailsExpanded"
        @select-task="emit('selectTask', $event)"
        @request-move="forwardMove"
      />
    </div>
    <div v-if="!machines.length" class="p-16 text-center text-sm text-slate-500">没有匹配当前筛选条件的机台。</div>
  </section>
</template>
