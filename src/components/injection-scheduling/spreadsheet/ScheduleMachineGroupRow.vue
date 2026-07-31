<script setup lang="ts">
import { ChevronDown, ChevronRight, CircleDot, Wrench } from '@lucide/vue'
import { computed, ref } from 'vue'
import type { InjectionMachine, ScheduleTask } from '@/types/injectionScheduling'

const props = defineProps<{
  machine: InjectionMachine
  tasks: ScheduleTask[]
  columnCount: number
  collapsed: boolean
  bigScreen: boolean
}>()

const emit = defineEmits<{
  toggle: [machineId: string]
  select: [machineId: string]
  dropTask: [taskId: string, machineId: string]
}>()

const dragOver = ref(false)
const currentTask = computed(() => props.tasks.find((task) => task.current))
const exceptionCount = computed(() => props.tasks.filter((task) => task.risk !== 'normal').length)
const stateLabel = computed(() => ({
  running: '生产中',
  risk: '交期风险',
  urgent: '特急',
  idle: '空闲',
  maintenance: '保养',
  fault: '故障',
}[props.machine.state]))

function onDrop(event: DragEvent) {
  dragOver.value = false
  const taskId = event.dataTransfer?.getData('application/x-injection-task') || event.dataTransfer?.getData('text/plain')
  if (taskId) emit('dropTask', taskId, props.machine.id)
}
</script>

<template>
  <tr
    class="machine-group-row"
    :class="[
      bigScreen ? 'bg-[#123936] text-slate-100' : 'bg-[#edf6f4] text-slate-800',
      dragOver ? '!bg-teal-100 ring-2 ring-inset ring-teal-500' : '',
    ]"
    :data-machine-id="machine.id"
    @dragover.prevent="dragOver = true"
    @dragleave="dragOver = false"
    @drop.prevent="onDrop"
  >
    <th
      :colspan="columnCount"
      scope="rowgroup"
      class="h-[30px] border-b border-r border-slate-200 p-0 text-left"
    >
      <div class="sticky left-0 flex h-[30px] w-[min(1040px,calc(100vw-36px))] items-center gap-2 px-2">
        <button
          type="button"
          class="grid size-5 shrink-0 place-items-center rounded text-slate-500 hover:bg-white/60"
          :aria-label="collapsed ? `展开${machine.name}` : `收起${machine.name}`"
          @click="emit('toggle', machine.id)"
        >
          <ChevronRight v-if="collapsed" class="size-3.5" />
          <ChevronDown v-else class="size-3.5" />
        </button>
        <button type="button" class="inline-flex min-w-0 items-center gap-2 text-left" @click="emit('select', machine.id)">
          <strong class="text-[11px] font-black">{{ machine.name }}</strong>
          <span class="rounded bg-white/70 px-1.5 py-0.5 text-[8px] font-black text-teal-800">{{ machine.capability.machineClass }}</span>
          <span class="text-[8px] text-slate-500">{{ machine.kind }} · {{ machine.workshop }}</span>
        </button>
        <span class="inline-flex items-center gap-1 text-[8px] font-bold" :class="machine.state === 'running' ? 'text-teal-700' : machine.state === 'idle' ? 'text-slate-500' : 'text-amber-700'">
          <CircleDot class="size-2.5" />{{ stateLabel }}
        </span>
        <span class="text-[8px] text-slate-500">负荷 {{ machine.load }}%</span>
        <span v-if="currentTask" class="min-w-0 truncate text-[8px] text-slate-500">
          当前：{{ currentTask.requirement.mold.moldNo }} · {{ currentTask.requirement.productName }}
        </span>
        <span v-else class="text-[8px] font-bold text-slate-400">当前无生产任务</span>
        <span v-if="exceptionCount" class="rounded-full bg-amber-100 px-1.5 py-0.5 text-[8px] font-black text-amber-800">{{ exceptionCount }} 项异常</span>
        <span v-if="machine.resourceState !== 'available'" class="inline-flex items-center gap-1 rounded-full bg-red-100 px-1.5 py-0.5 text-[8px] font-black text-red-700"><Wrench class="size-2.5" />资源受限</span>
        <span class="ml-auto text-[8px] text-slate-400">{{ tasks.length }} 项任务</span>
      </div>
    </th>
  </tr>
</template>
