<script setup lang="ts">
import { ChevronDown, ChevronUp, CircleOff, Gauge, Info, TriangleAlert, Zap } from '@lucide/vue'
import { ref } from 'vue'
import ScheduleTaskCard from './ScheduleTaskCard.vue'
import type { InjectionMachine, ScheduleTask } from '@/types/injectionScheduling'

const props = defineProps<{
  machine: InjectionMachine
  tasks: ScheduleTask[]
  detailsExpanded: boolean
}>()

const emit = defineEmits<{
  selectTask: [taskId: string]
  requestMove: [taskId: string, targetMachineId: string]
}>()

const laneExpanded = ref(false)

function startDrag(event: DragEvent, taskId: string) {
  event.dataTransfer?.setData('text/schedule-task-id', taskId)
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
}

function dropTask(event: DragEvent) {
  const taskId = event.dataTransfer?.getData('text/schedule-task-id')
  if (taskId) emit('requestMove', taskId, props.machine.id)
}

const stateCopy = {
  running: '生产中',
  risk: '交期异常',
  urgent: '特急任务',
  idle: '空闲',
}
</script>

<template>
  <article
    class="grid min-w-[1050px] grid-cols-[250px_minmax(0,1fr)] border-b border-slate-200 last:border-b-0"
    style="content-visibility: auto; contain-intrinsic-size: 250px;"
  >
    <section class="border-r border-slate-200 bg-white p-4">
      <div class="flex items-start justify-between gap-3">
        <div>
          <h3 class="text-lg font-black text-slate-950">{{ machine.name }}</h3>
          <p class="mt-2 text-sm font-black text-slate-800">{{ machine.machineType }} {{ machine.tonnage }}</p>
        </div>
        <span
          class="rounded-full px-2 py-1 text-[10px] font-black"
          :class="{
            'bg-teal-50 text-teal-700': machine.state === 'running',
            'bg-red-50 text-red-700': machine.state === 'risk',
            'bg-orange-50 text-orange-700': machine.state === 'urgent',
            'bg-slate-100 text-slate-500': machine.state === 'idle',
          }"
        >{{ stateCopy[machine.state] }}</span>
      </div>

      <div class="mt-3 flex flex-wrap gap-1.5 text-[10px] font-semibold text-slate-600">
        <span class="rounded border border-slate-200 px-2 py-1">{{ machine.capability }}</span>
        <span class="rounded border border-slate-200 px-2 py-1">{{ machine.armType }}</span>
        <span class="rounded border border-slate-200 px-2 py-1">{{ tasks.length }} 项任务</span>
      </div>

      <p class="mt-3 rounded-lg bg-slate-50 px-2.5 py-2 text-[10px] leading-5 text-slate-600">
        限制：{{ machine.restriction }}
      </p>

      <div class="mt-3 flex items-center justify-between text-[10px] text-slate-500">
        <span class="inline-flex items-center gap-1"><Gauge class="size-3.5" aria-hidden="true" />当前负荷 {{ machine.load }}%</span>
        <button
          type="button"
          class="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2 py-1 font-bold text-slate-700 hover:bg-slate-50"
          @click="laneExpanded = !laneExpanded"
        >
          明细
          <ChevronUp v-if="laneExpanded" class="size-3" aria-hidden="true" />
          <ChevronDown v-else class="size-3" aria-hidden="true" />
        </button>
      </div>

      <div v-if="detailsExpanded || laneExpanded" class="mt-3 space-y-1 border-t border-slate-100 pt-3 text-[10px] text-slate-500">
        <p class="flex items-center gap-1.5"><Info class="size-3" aria-hidden="true" />机台编号 {{ machine.id }}</p>
        <p class="flex items-center gap-1.5"><Zap class="size-3" aria-hidden="true" />计划利用率 {{ machine.load }}%</p>
        <p v-if="machine.state === 'risk'" class="flex items-center gap-1.5 text-red-600"><TriangleAlert class="size-3" aria-hidden="true" />存在交期异常</p>
      </div>
    </section>

    <section
      class="min-h-[220px] overflow-x-auto bg-slate-50/70 p-3"
      :aria-label="`${machine.name}任务队列`"
      @dragover.prevent
      @drop.prevent="dropTask"
    >
      <div v-if="tasks.length" class="flex min-w-max gap-3">
        <ScheduleTaskCard
          v-for="task in tasks"
          :key="task.id"
          :task="task"
          @select="emit('selectTask', $event)"
          @dragstart="startDrag"
        />
      </div>
      <div v-else class="flex h-full min-h-[190px] items-center justify-center rounded-xl border border-dashed border-slate-300 bg-white/60 text-center">
        <div>
          <CircleOff class="mx-auto size-5 text-slate-400" aria-hidden="true" />
          <strong class="mt-2 block text-sm text-slate-600">当前无排程</strong>
          <p class="mt-1 text-xs text-slate-400">可从待排订单池选择合适任务</p>
        </div>
      </div>
    </section>
  </article>
</template>

