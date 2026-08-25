<script setup lang="ts">
import { computed, ref } from 'vue'
import { CircleDashed, GripVertical, RotateCcw, TriangleAlert } from '@lucide/vue'
import ProgressMeter from '@/components/common/ProgressMeter.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { dueSlackPresentation, formatAClass, machineStatusPresentation, priorityPresentation, statusPresentation } from './presentation'
import type { WorkbenchJob, WorkbenchMachine } from './types'

const props = defineProps<{
  machines: WorkbenchMachine[]
  jobsByMachine: Map<string, WorkbenchJob[]>
  selectedJobId: string | null
  editable: boolean
}>()
const emit = defineEmits<{
  select: [jobId: string]
  move: [job: WorkbenchJob, machineId: string, sequenceNo: number]
  withdraw: [job: WorkbenchJob]
}>()
const draggedJobId = ref<string | null>(null)
const activeTarget = ref<string | null>(null)

const unplanned = computed(() => props.jobsByMachine.get('UNPLANNED') ?? [])
function jobs(machineId: string) { return props.jobsByMachine.get(machineId) ?? [] }
function draggedJob() {
  return [...props.jobsByMachine.values()].flat().find((job) => job.id === draggedJobId.value) ?? null
}
function dragStart(job: WorkbenchJob, event: DragEvent) {
  if (!props.editable || !job.taskId) return
  draggedJobId.value = job.id
  event.dataTransfer?.setData('text/plain', job.id)
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
}
function drop(machineId: string, sequenceNo = jobs(machineId).length) {
  const job = draggedJob()
  if (job && (job.machineId !== machineId || job.sequenceNo !== sequenceNo)) emit('move', job, machineId, sequenceNo)
  draggedJobId.value = null
  activeTarget.value = null
}
function dropUnplanned() {
  const job = draggedJob()
  if (job?.taskId) emit('withdraw', job)
  draggedJobId.value = null
  activeTarget.value = null
}
</script>

<template>
  <div class="wb-queue-board" aria-label="机台生产队列">
    <section
      class="wb-queue-lane unplanned"
      :class="{ 'drop-target': activeTarget === 'UNPLANNED' }"
      @dragover.prevent="activeTarget = 'UNPLANNED'"
      @dragleave="activeTarget = null"
      @drop.prevent="dropUnplanned"
    >
      <header>
        <div><strong>待排池</strong><small>需求订单不预设机台</small></div>
        <span>{{ unplanned.length }}</span>
      </header>
      <div class="wb-queue-cards">
        <button
          v-for="job in unplanned"
          :key="job.id"
          type="button"
          class="wb-queue-card"
          :class="{ selected: selectedJobId === job.id }"
          @click="emit('select', job.id)"
        >
          <div class="wb-card-heading"><b>{{ job.itemNo || job.orderNo }}</b><StatusPill :label="priorityPresentation(job.priority).label" :tone="priorityPresentation(job.priority).tone" compact /></div>
          <span>{{ job.productName }}</span>
          <small><CircleDashed :size="12" />{{ job.moldNo || '模具待补' }} · 未完 {{ job.outstandingQuantity.toLocaleString('zh-CN') }}</small>
          <StatusPill :label="dueSlackPresentation(job.deliverySlackDays).label" :tone="dueSlackPresentation(job.deliverySlackDays).tone" compact />
        </button>
      </div>
    </section>

    <section
      v-for="machine in machines"
      :key="machine.id"
      class="wb-queue-lane"
      :class="{ 'drop-target': activeTarget === machine.id, unavailable: !machine.availableForAutoSchedule }"
      @dragover.prevent="activeTarget = machine.id"
      @dragleave="activeTarget = null"
      @drop.prevent="drop(machine.id)"
    >
      <header>
        <div>
          <span class="wb-lane-title"><strong>{{ machine.code }}</strong><StatusPill :label="machineStatusPresentation(machine).label" :tone="machineStatusPresentation(machine).tone" compact /></span>
          <small>{{ formatAClass(machine.aClass) }} · {{ machine.position || machine.area || '位置待补' }}</small>
        </div>
        <span>{{ jobs(machine.id).length }}</span>
      </header>
      <p v-if="machine.parsedConstraintSummary" class="wb-machine-rule"><TriangleAlert :size="13" />{{ machine.parsedConstraintSummary }}</p>
      <div class="wb-queue-cards">
        <article
          v-for="(job, index) in jobs(machine.id)"
          :key="job.id"
          class="wb-queue-card"
          :class="{ selected: selectedJobId === job.id, running: job.status === 'RUNNING', dragging: draggedJobId === job.id, 'drop-before': activeTarget === `${machine.id}:${index}` }"
          :draggable="editable && Boolean(job.taskId)"
          tabindex="0"
          @click="emit('select', job.id)"
          @keydown.enter="emit('select', job.id)"
          @dragstart="dragStart(job, $event)"
          @dragover.prevent.stop="activeTarget = `${machine.id}:${index}`"
          @drop.prevent.stop="drop(machine.id, index)"
          @dragend="draggedJobId = null; activeTarget = null"
        >
          <GripVertical :size="15" aria-hidden="true" />
          <div>
            <div class="wb-card-heading"><b>{{ job.itemNo || job.orderNo }}</b><StatusPill :label="statusPresentation(job.status).label" :tone="statusPresentation(job.status).tone" compact /></div>
            <span>{{ job.productName }}</span>
            <small>{{ job.moldNo || '模具待补' }} · 未完 {{ job.outstandingQuantity.toLocaleString('zh-CN') }}</small>
            <ProgressMeter :value="Math.round(job.completionRate * 100)" :tone="job.status === 'PAUSED' ? 'amber' : 'teal'" />
            <div class="wb-card-meta"><StatusPill :label="priorityPresentation(job.priority).label" :tone="priorityPresentation(job.priority).tone" compact /><StatusPill :label="dueSlackPresentation(job.deliverySlackDays).label" :tone="dueSlackPresentation(job.deliverySlackDays).tone" compact /></div>
          </div>
          <button type="button" class="wb-icon-button" title="撤回待排池" :disabled="!editable" @click.stop="emit('withdraw', job)"><RotateCcw :size="14" /></button>
        </article>
        <p v-if="!jobs(machine.id).length" class="wb-lane-empty">拖入任务到此机台</p>
      </div>
    </section>
  </div>
</template>
