<script setup lang="ts">
import { Gauge, MoveHorizontal, TriangleAlert } from '@lucide/vue'
import { computed, ref } from 'vue'
import CurrentTaskCell from './CurrentTaskCell.vue'
import MachineCapabilityPopover from './MachineCapabilityPopover.vue'
import QueueTaskChip from './QueueTaskChip.vue'
import {
  armLabels,
  formatScheduleTime,
  machineStateMeta,
} from '@/lib/injectionSchedulingPresentation'
import type { InjectionMachine, ScheduleTask, SchedulingDensity } from '@/types/injectionScheduling'

const props = defineProps<{
  machine: InjectionMachine
  tasks: ScheduleTask[]
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

const dragTarget = ref(false)
const currentTask = computed(() => props.tasks.find((task) => task.current) ?? null)
const futureTasks = computed(() => props.tasks.filter((task) => !task.current))
const riskCount = computed(() => props.tasks.filter((task) => ['overdue', 'urgent', 'incomplete'].includes(task.risk)).length)
const finalTask = computed(() => props.tasks[props.tasks.length - 1] ?? null)

function startDrag(event: DragEvent, taskId: string) {
  event.dataTransfer?.setData('text/schedule-task-id', taskId)
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
}

function dropTask(event: DragEvent) {
  dragTarget.value = false
  const taskId = event.dataTransfer?.getData('text/schedule-task-id')
  if (taskId) emit('requestMove', taskId, props.machine.id)
}
</script>

<template>
  <article
    class="compact-machine-lane grid min-w-[1020px] grid-cols-[170px_286px_minmax(0,1fr)_138px] border-b border-slate-200 bg-white last:border-b-0 hover:bg-teal-50/20"
    :class="[
      density === 'compact' ? 'h-24' : 'h-28',
      bigScreen ? '!h-[84px] border-slate-800 !bg-[#0a201e] text-white' : '',
      dragTarget ? 'outline outline-2 -outline-offset-2 outline-teal-500' : '',
    ]"
    style="content-visibility: auto; contain: layout paint style; contain-intrinsic-size: 96px;"
  >
    <section
      class="relative flex min-w-0 gap-2.5 border-r border-slate-200 bg-gradient-to-r from-white to-slate-50 px-2.5 py-2"
      :class="bigScreen ? '!border-slate-800 !from-[#0e2b28] !to-[#0b211f]' : ''"
    >
      <button
        type="button"
        class="grid size-10 shrink-0 place-items-center self-center rounded-xl bg-teal-950 text-xs font-black text-white shadow-sm"
        :aria-label="`查看${machine.name}机台能力`"
        @click="emit('selectMachine', machine.id)"
      >{{ machine.code }}</button>
      <div class="min-w-0 flex-1">
        <div class="flex items-center gap-1">
          <strong class="truncate text-[12px]" :class="bigScreen ? 'text-white' : 'text-slate-900'">{{ machine.name }}</strong>
          <span class="rounded bg-slate-100 px-1 py-0.5 text-[8px] font-black text-slate-600">{{ machine.capability.machineClass }}</span>
          <MachineCapabilityPopover :machine="machine" @open="emit('selectMachine', $event)" />
        </div>
        <p class="mt-1 truncate text-[8px]" :class="bigScreen ? 'text-slate-400' : 'text-slate-500'">
          {{ machine.capability.tonnage }}T · {{ machine.kind }} · {{ machine.capability.shotCapacityGrams }}g
        </p>
        <div class="mt-1 flex min-w-0 gap-1">
          <span class="truncate rounded border border-slate-200 px-1 text-[7px] text-slate-500">{{ armLabels[machine.capability.armType] }}</span>
          <span class="truncate rounded border border-slate-200 px-1 text-[7px] text-slate-500">{{ machine.restriction }}</span>
        </div>
        <div class="mt-1.5 flex items-center gap-1">
          <div class="h-0.5 flex-1 overflow-hidden rounded-full bg-slate-200"><i class="block h-full bg-teal-600" :style="{ width: `${machine.load}%` }" /></div>
          <span class="text-[7px] text-slate-400">{{ machine.load }}%</span>
        </div>
      </div>
      <i class="absolute inset-y-0 left-0 w-[3px]" :class="machine.state === 'risk' || machine.state === 'fault' ? 'bg-red-500' : machine.state === 'urgent' ? 'bg-orange-500' : 'bg-teal-500'" />
    </section>

    <section class="border-r border-slate-200 p-1.5" :class="bigScreen ? '!border-slate-800' : ''">
      <CurrentTaskCell :task="currentTask" @select="emit('selectTask', $event)" />
    </section>

    <section
      class="min-w-0 overflow-x-auto border-r border-slate-200 bg-slate-50/50 p-1.5 [scrollbar-width:thin]"
      :class="bigScreen ? '!border-slate-800 !bg-[#081d1b]' : ''"
      :aria-label="`${machine.name}后续任务队列`"
      @dragenter.prevent="dragTarget = true"
      @dragleave.self="dragTarget = false"
      @dragover.prevent
      @drop.prevent="dropTask"
    >
      <div v-if="futureTasks.length" class="flex h-full min-w-max gap-1.5">
        <QueueTaskChip
          v-for="(task, index) in futureTasks"
          :key="task.id"
          :task="task"
          :same-mold="(index === 0 ? currentTask?.requirement.mold.moldNo : futureTasks[index - 1]?.requirement.mold.moldNo) === task.requirement.mold.moldNo"
          @select="emit('selectTask', $event)"
          @dragstart="startDrag"
          @nudge="(taskId, direction) => emit('nudgeTask', taskId, direction)"
        />
      </div>
      <button
        v-else
        type="button"
        class="grid h-full w-full place-items-center rounded-lg border border-dashed border-slate-200 bg-white/50 text-[9px] text-slate-400"
        @click="emit('openBacklog', machine.id)"
      >拖入后续任务或从待排池分配</button>
    </section>

    <section class="flex flex-col items-center justify-center gap-1 px-2 text-center" :class="bigScreen ? 'bg-[#0b2321]' : 'bg-white'">
      <span class="text-[8px] text-slate-400">队列预计完成</span>
      <strong class="text-[11px]" :class="bigScreen ? 'text-white' : 'text-slate-800'">{{ finalTask ? formatScheduleTime(finalTask.timing.plannedEnd) : '—' }}</strong>
      <span
        class="rounded px-2 py-0.5 text-[8px] font-black"
        :class="riskCount ? 'bg-red-50 text-red-700' : machineStateMeta[machine.state].className"
      >
        {{ riskCount ? `${riskCount} 项逾期/特急` : machineStateMeta[machine.state].label }}
      </span>
      <div v-if="!bigScreen" class="mt-0.5 flex gap-1">
        <button type="button" class="grid size-6 place-items-center rounded border border-slate-200 text-slate-500" title="机台能力" @click="emit('selectMachine', machine.id)"><Gauge class="size-3" /></button>
        <button type="button" class="grid size-6 place-items-center rounded border border-slate-200 text-slate-500" title="从待排池分配" @click="emit('openBacklog', machine.id)"><MoveHorizontal class="size-3" /></button>
        <TriangleAlert v-if="riskCount" class="mt-1 size-3 text-red-500" aria-label="存在交期风险" />
      </div>
    </section>
  </article>
</template>
