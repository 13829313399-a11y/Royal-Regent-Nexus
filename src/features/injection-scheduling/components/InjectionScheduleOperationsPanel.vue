<script setup lang="ts">
import { CalendarClock, CheckCircle2, Loader2, Lock, Play, Unlock } from '@lucide/vue'
import { computed, nextTick, ref, watch } from 'vue'
import { injectionSchedulingApi } from '@/api/injectionScheduling'
import { Button } from '@/components/ui/button'
import { getApiErrorMessage } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'
import type {
  InjectionScheduleAutoProposal,
  InjectionScheduleLine,
  InjectionScheduleMachine,
  InjectionScheduleMoveValidation,
} from '@/types/injectionScheduling'

const props = defineProps<{
  factoryId: string
  lines: InjectionScheduleLine[]
  machines: InjectionScheduleMachine[]
  scheduleRevision: number
  startDate: string
  endDate: string
  canEdit: boolean
  canSchedule: boolean
  moveDraft?: {
    nonce: number
    lineId: string
    machineId: string
    startAt: string
    finishAt: string
    reason: string
  } | null
}>()
const emit = defineEmits<{ changed: [] }>()

const lineId = ref('')
const machineId = ref('')
const startAt = ref('')
const finishAt = ref('')
const reason = ref('人工调整')
const validation = ref<InjectionScheduleMoveValidation | null>(null)
const productionDate = ref('')
const shift = ref<'DAY' | 'NIGHT'>('DAY')
const reportedShots = ref('')
const defectShots = ref('0')
const proposal = ref<InjectionScheduleAutoProposal | null>(null)
const busy = ref('')
const message = ref('')

const line = computed(() => props.lines.find(item => item.id === lineId.value) ?? null)
const availableMachines = computed(() => props.machines.filter(item => item.status === 'AVAILABLE'))

function localIso(value: string) {
  return value ? `${value.length === 16 ? `${value}:00` : value}+08:00` : ''
}

function resetValidation() {
  validation.value = null
  message.value = ''
}

async function validateMove() {
  if (!line.value || !machineId.value || !startAt.value || !finishAt.value) {
    message.value = '请选择排程行、目标机台和计划时间。'
    return
  }
  busy.value = 'validate'
  resetValidation()
  try {
    validation.value = await injectionSchedulingApi.validateMove(line.value.id, {
      factory_id: props.factoryId,
      target_machine_id: machineId.value,
      planned_start_at: localIso(startAt.value),
      planned_finish_at: localIso(finishAt.value),
      expected_line_version: line.value.version,
      expected_schedule_revision: props.scheduleRevision,
      reason: reason.value,
    })
    message.value = validation.value.valid ? '校验通过，可以确认移动。' : '存在冲突，不能移动。'
  } catch (error) {
    message.value = getApiErrorMessage(error)
  } finally {
    busy.value = ''
  }
}

async function confirmMove() {
  if (!line.value || !validation.value?.valid) return
  busy.value = 'move'
  try {
    await injectionSchedulingApi.moveLine(line.value.id, {
      factory_id: props.factoryId,
      target_machine_id: machineId.value,
      planned_start_at: localIso(startAt.value),
      planned_finish_at: localIso(finishAt.value),
      expected_line_version: line.value.version,
      expected_schedule_revision: props.scheduleRevision,
      validate_token: validation.value.validate_token,
      reason: reason.value,
    })
    message.value = '人工排程已保存。'
    validation.value = null
    emit('changed')
  } catch (error) {
    message.value = getApiErrorMessage(error)
  } finally {
    busy.value = ''
  }
}

async function lineAction(action: 'lock' | 'unlock' | 'pause' | 'resume') {
  if (!line.value) return
  busy.value = action
  try {
    await injectionSchedulingApi.lineAction(
      line.value.id,
      action,
      props.factoryId,
      line.value.version,
      props.scheduleRevision,
      reason.value,
    )
    message.value = '排程状态已更新。'
    emit('changed')
  } catch (error) {
    message.value = getApiErrorMessage(error)
  } finally {
    busy.value = ''
  }
}

async function recordOutput() {
  if (!line.value || !productionDate.value || !reportedShots.value) {
    message.value = '请选择排程行、生产日期并填写班次啤数。'
    return
  }
  busy.value = 'output'
  try {
    await injectionSchedulingApi.putShiftOutput(
      props.factoryId,
      line.value.id,
      productionDate.value,
      shift.value,
      reportedShots.value,
      defectShots.value || '0',
    )
    message.value = '班次产量已登记。'
    emit('changed')
  } catch (error) {
    message.value = getApiErrorMessage(error)
  } finally {
    busy.value = ''
  }
}

async function previewAuto() {
  busy.value = 'auto'
  proposal.value = null
  try {
    proposal.value = await injectionSchedulingApi.previewAutoSchedule(
      props.factoryId,
      createRandomUuid(),
      `${props.startDate}T08:00:00+08:00`,
      `${props.endDate}T20:00:00+08:00`,
      props.scheduleRevision,
    )
    message.value = `自动排程预览：可排 ${proposal.value.summary.scheduled_count} 条，未排 ${proposal.value.summary.unscheduled_count} 条。`
  } catch (error) {
    message.value = getApiErrorMessage(error)
  } finally {
    busy.value = ''
  }
}

async function applyAuto() {
  if (!proposal.value) return
  busy.value = 'apply-auto'
  try {
    await injectionSchedulingApi.applyAutoSchedule(
      props.factoryId,
      proposal.value.proposal_id,
      props.scheduleRevision,
    )
    message.value = '自动排程 proposal 已确认应用。'
    proposal.value = null
    emit('changed')
  } catch (error) {
    message.value = getApiErrorMessage(error)
  } finally {
    busy.value = ''
  }
}

watch(() => props.lines, (value) => {
  if (!value.some(item => item.id === lineId.value)) lineId.value = value[0]?.id ?? ''
}, { immediate: true })
watch(lineId, () => {
  const current = line.value
  machineId.value = current?.machine_id ?? availableMachines.value[0]?.id ?? ''
  startAt.value = current?.planned_start_at?.slice(0, 16) ?? ''
  finishAt.value = current?.planned_finish_at?.slice(0, 16) ?? ''
  productionDate.value = props.startDate
  resetValidation()
})
watch(() => props.moveDraft?.nonce, async () => {
  if (!props.moveDraft) return
  lineId.value = props.moveDraft.lineId
  await nextTick()
  machineId.value = props.moveDraft.machineId
  startAt.value = props.moveDraft.startAt
  finishAt.value = props.moveDraft.finishAt
  reason.value = props.moveDraft.reason
  validation.value = null
  message.value = '已接收时间轴拖放草案；请点击“校验移动”。'
})
</script>

<template>
  <section class="rounded-xl border border-slate-200/80 bg-white/90 p-4 shadow-sm">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div><h2 class="flex items-center gap-2 font-bold"><CalendarClock class="size-5 text-teal-700" aria-hidden="true" />人工排产与班次执行</h2><p class="mt-1 text-xs text-slate-500">每次写入都校验当前排程 revision 和记录 version。</p></div>
      <div class="flex gap-2"><Button variant="outline" size="sm" :disabled="!canSchedule || Boolean(busy)" @click="previewAuto"><Loader2 v-if="busy === 'auto'" class="animate-spin" aria-hidden="true" /><Play v-else aria-hidden="true" />自动排程预览</Button><Button v-if="proposal" size="sm" :disabled="Boolean(busy) || proposal.summary.scheduled_count === 0" @click="applyAuto"><CheckCircle2 aria-hidden="true" />确认应用 {{ proposal.summary.scheduled_count }} 条</Button></div>
    </div>
    <div class="mt-4 grid gap-2 xl:grid-cols-[220px_180px_190px_190px_minmax(160px,1fr)_auto]">
      <select v-model="lineId" class="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm"><option value="">选择订单排程行</option><option v-for="item in lines" :key="item.id" :value="item.id">{{ item.machine_code }} · {{ item.order_no }} · {{ item.product_code }}</option></select>
      <select v-model="machineId" class="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm" @change="resetValidation"><option v-for="machine in availableMachines" :key="machine.id" :value="machine.id">{{ machine.machine_code }} · {{ machine.machine_a_label }}</option></select>
      <input v-model="startAt" type="datetime-local" class="h-10 rounded-lg border border-slate-200 px-3 text-sm" @input="resetValidation">
      <input v-model="finishAt" type="datetime-local" class="h-10 rounded-lg border border-slate-200 px-3 text-sm" @input="resetValidation">
      <input v-model="reason" class="h-10 rounded-lg border border-slate-200 px-3 text-sm" maxlength="500" placeholder="调整原因">
      <div class="flex gap-2"><Button variant="outline" :disabled="!canEdit || !line || Boolean(busy)" @click="validateMove">校验移动</Button><Button :disabled="!validation?.valid || Boolean(busy)" @click="confirmMove">确认移动</Button></div>
    </div>
    <div v-if="line" class="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
      <Button variant="outline" size="sm" :disabled="!canEdit || Boolean(busy)" @click="lineAction(line.is_locked ? 'unlock' : 'lock')"><Unlock v-if="line.is_locked" aria-hidden="true" /><Lock v-else aria-hidden="true" />{{ line.is_locked ? '解锁' : '锁定' }}</Button>
      <Button v-if="line.status === 'IN_PRODUCTION'" variant="outline" size="sm" :disabled="Boolean(busy)" @click="lineAction('pause')">暂停</Button><Button v-if="line.status === 'PAUSED'" variant="outline" size="sm" :disabled="Boolean(busy)" @click="lineAction('resume')">恢复</Button>
      <span class="ml-2 text-xs font-semibold text-slate-600">班次登记</span><input v-model="productionDate" type="date" class="h-9 rounded-lg border border-slate-200 px-2 text-sm"><select v-model="shift" class="h-9 rounded-lg border border-slate-200 bg-white px-2 text-sm"><option value="DAY">白班</option><option value="NIGHT">夜班</option></select><input v-model="reportedShots" type="number" min="0" step="0.001" class="h-9 w-28 rounded-lg border border-slate-200 px-2 text-sm" placeholder="总啤数"><input v-model="defectShots" type="number" min="0" step="0.001" class="h-9 w-28 rounded-lg border border-slate-200 px-2 text-sm" placeholder="不良数"><Button size="sm" :disabled="!canEdit || Boolean(busy)" @click="recordOutput">登记</Button>
    </div>
    <div v-if="validation?.conflicts.length" class="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700"><p v-for="item in validation.conflicts" :key="item.code">{{ item.code }}：{{ item.message }}</p></div>
    <p v-if="message" class="mt-3 text-xs text-slate-600">{{ message }}</p>
    <div v-if="proposal?.unscheduled.length" class="mt-3 max-h-28 overflow-auto rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800"><p v-for="item in proposal.unscheduled.slice(0, 20)" :key="item.line_id">{{ item.reason_code }} · {{ item.message }}</p></div>
  </section>
</template>
