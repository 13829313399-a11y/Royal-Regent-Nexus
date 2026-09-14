<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { AlertTriangle, CopyPlus, Info, Loader2, RefreshCw } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import type { BusinessDate, ShiftCode, UvMachine, UvShiftTemplate, UvWorkerRef } from '../contracts'
import { EMPLOY_STATE_LABELS, WORKER_ROLE_LABELS } from '../domain/status'
import { SHIFT_LABELS } from '../domain/businessTime'
import UvDrawer from './UvDrawer.vue'

/**
 * 排班编辑抽屉（UV_PRINT_SHARED_SPEC.md 5.6 / 6.7）。
 *
 * - 只编辑「谁在哪个机台的哪个班次」，写入走 saveAssignments（operation_id + expected_version）；
 * - 「复制前一班」是一项显式动作：从上一班的同一机台读取计划，说明它只复制排班计划，
 *   绝不复制产量与工资；复制后仍需人工确认保存，不隐式写入；
 * - 离职员工的历史排班照常显示并标注为历史，不会被静默剔除；
 * - 复制来源读取失败时给出可重试的失败提示，绝不假装复制成功。
 */

const props = withDefaults(defineProps<{
  open: boolean
  businessDate: BusinessDate
  shift: ShiftCode
  machine: UvMachine | null
  workers: UvWorkerRef[]
  templates?: UvShiftTemplate[]
  /** 当前班次该机台已保存的人员。 */
  assignedWorkerIds: string[]
  /** 该班次全部机台的排班，用于提示跨机兼岗。 */
  machineIdsByWorker?: Record<string, string[]>
  /** 上一班的标识；不存在时说明原因。 */
  previousShift: { businessDate: BusinessDate; shift: ShiftCode } | null
  canWrite: boolean
  busy?: boolean
  errorMessage?: string
  /** 复制前一班读取失败时的可读原因。 */
  copyError?: string
  copyLoading?: boolean
}>(), {
  templates: () => [],
  machineIdsByWorker: () => ({}),
  busy: false,
  errorMessage: '',
  copyError: '',
  copyLoading: false,
})

const emit = defineEmits<{
  close: []
  save: [payload: { workerIds: string[]; note: string }]
  'copy-previous': []
}>()

const selected = ref<string[]>([])
const note = ref('')

watch(
  () => [props.open, props.assignedWorkerIds.join(','), props.businessDate, props.shift] as const,
  () => {
    if (!props.open) return
    selected.value = [...props.assignedWorkerIds]
    note.value = ''
  },
  { immediate: true },
)

const activeWorkers = computed(() => props.workers.filter((worker) => worker.employ_state === 'active'))
const leftWorkers = computed(() => props.workers.filter((worker) => worker.employ_state === 'left'))

const shiftLabel = computed(() => SHIFT_LABELS[props.shift])
const timeLabel = computed(() => {
  const template = props.templates.find((candidate) => candidate.shift === props.shift)
  if (!template) return '班次模板未配置，先登记模板再排班'
  const prefix = props.shift === 'night' ? '次日' : ''
  return `${template.start_local}–${prefix}${template.end_local}，休息 ${template.break_minutes} 分钟`
})

const previousShiftLabel = computed(() =>
  props.previousShift
    ? `${props.previousShift.businessDate} ${SHIFT_LABELS[props.previousShift.shift]}`
    : `没有更早的班次可复制`,
)

const canSave = computed(() => props.canWrite && !props.busy && Boolean(props.machine))

function isSelected(workerId: string): boolean {
  return selected.value.includes(workerId)
}

function conflictMachines(workerId: string): string[] {
  const machines = props.machineIdsByWorker[workerId] ?? []
  return machines.filter((machineId) => machineId !== props.machine?.id)
}

function toggle(workerId: string) {
  if (!props.canWrite) return
  selected.value = isSelected(workerId)
    ? selected.value.filter((candidate) => candidate !== workerId)
    : [...selected.value, workerId]
}

function submit() {
  if (!canSave.value) return
  emit('save', { workerIds: [...selected.value], note: note.value.trim() })
}

/**
 * 复制前一班：只把上一班的排班计划（人员）带入当前勾选。
 * 产量、合格数与工资不属于复制范围，调用方读到的报工数据不会被触碰。
 */
function applyCopy(workerIds: string[]) {
  const unique = [...new Set(workerIds)]
  selected.value = unique
  note.value = '由上一班排班计划复制：只复制人员安排，不含产量与工资，请核对兼岗份额。'
}

defineExpose({ applyCopy })
</script>

<template>
  <UvDrawer
    :open="open"
    :title="`排班 · ${machine?.code ?? '机台'} ${shiftLabel}`"
    :subtitle="`${businessDate} · ${SHIFT_LABELS[shift]} · ${machine?.name ?? '机台待选择'} · ${timeLabel}`"
    size="lg"
    :busy="busy"
    close-hint="Esc 关闭，未保存的勾选会丢失"
    @close="emit('close')"
  >
    <div v-if="!canWrite" class="uv-state uv-state--warning uv-state--compact" role="alert">
      <div class="uv-state__icon uv-state__icon--warning" aria-hidden="true">
        <AlertTriangle class="size-5" />
      </div>
      <p class="uv-state__title">没有修改排班的权限</p>
      <p class="uv-state__message">
        当前账号在华康A生产部缺少 uv_printing:shift_write；可以查看现有排班，但不能保存或复制。
        权限由服务端判定，界面隐藏按钮不等于权限控制。
      </p>
    </div>

    <section class="uv-section">
      <h3 class="uv-section__title"><span class="uv-section__index">1</span>本班次人员计划</h3>

      <p class="uv-callout">
        <Info class="inline size-3.5" aria-hidden="true" />
        排班只决定「谁参与了哪个工作批次」。计件金额仍由报工的合格数量与计件工价快照计算，
        在这里改人员不会改写任何已确认工资。
      </p>

      <div class="uv-actions" style="margin: 10px 0">
        <Button
          variant="outline"
          size="sm"
          type="button"
          :disabled="!canWrite || !previousShift || copyLoading"
          @click="emit('copy-previous')"
        >
          <Loader2 v-if="copyLoading" class="size-3.5 motion-safe:animate-spin" aria-hidden="true" />
          <CopyPlus v-else class="size-3.5" aria-hidden="true" />
          {{ copyLoading ? '正在读取前一班…' : '复制前一班' }}
        </Button>
        <span class="uv-state__hint">
          来源：{{ previousShiftLabel }}。复制范围只有排班计划（人员与工作批次），
          <strong>不会复制产量、合格数与工资</strong>；复制后请核对兼岗份额再保存。
        </span>
      </div>

      <p v-if="copyError" class="uv-form-error" role="alert">
        <AlertTriangle class="size-3.5" aria-hidden="true" />
        复制前一班失败：{{ copyError }}。当前勾选没有改动，可重试。
        <Button variant="ghost" size="sm" type="button" @click="emit('copy-previous')">
          <RefreshCw class="size-3.5" aria-hidden="true" />
          重试复制
        </Button>
      </p>

      <fieldset class="uv-form-field" :disabled="!canWrite">
        <legend class="uv-form-label">在职人员（{{ activeWorkers.length }} 人）</legend>
        <div class="uv-check-row">
          <label
            v-for="worker in activeWorkers"
            :key="worker.id"
            class="uv-check"
            :class="isSelected(worker.id) ? 'uv-check--on' : ''"
          >
            <input
              type="checkbox"
              :checked="isSelected(worker.id)"
              :value="worker.id"
              :disabled="!canWrite"
              :data-worker-id="worker.id"
              @change="toggle(worker.id)"
            >
            <span>
              {{ worker.display_name }}
              <span class="uv-row-sub">
                {{ worker.employee_no }} · {{ WORKER_ROLE_LABELS[worker.role] ?? '岗位待登记' }} ·
                {{ EMPLOY_STATE_LABELS[worker.employ_state] ?? '在职状态待确认' }}
              </span>
              <span v-if="conflictMachines(worker.id).length" class="uv-matrix__conflict">
                <AlertTriangle class="inline size-3" aria-hidden="true" />
                本班次已排在 {{ conflictMachines(worker.id).length }} 台其他机台，保存后份额与工作批次需核对
              </span>
            </span>
          </label>
        </div>
      </fieldset>

      <fieldset v-if="leftWorkers.length" class="uv-form-field" style="margin-top: 10px" :disabled="!canWrite">
        <legend class="uv-form-label">已离职·仅历史（{{ leftWorkers.length }} 人）</legend>
        <p class="uv-form-help">
          离职员工不会出现在新的排班计划里；勾选只用于补录历史班次，历史工资快照继续保留。
        </p>
        <div class="uv-check-row">
          <label
            v-for="worker in leftWorkers"
            :key="worker.id"
            class="uv-check"
            :class="[isSelected(worker.id) ? 'uv-check--on' : '', 'uv-check--disabled']"
          >
            <input
              type="checkbox"
              :checked="isSelected(worker.id)"
              :disabled="!canWrite"
              :data-worker-id="worker.id"
              @change="toggle(worker.id)"
            >
            <span>
              {{ worker.display_name }}
              <span class="uv-row-sub">
                {{ worker.employee_no }} · 离职日期 {{ worker.left_on ?? '未登记' }} · 历史记录
              </span>
            </span>
          </label>
        </div>
      </fieldset>

      <p v-if="selected.length" class="uv-callout uv-callout--accent">
        本次将保存 {{ selected.length }} 人：{{
          workers.filter((worker) => selected.includes(worker.id)).map((worker) => worker.display_name).join('、')
        }}
      </p>
      <p v-else class="uv-callout uv-callout--warning" role="status">
        没有勾选任何人：保存会清空该机台本班次的排班名单，报工会显示为「未排班」而不是 0 工资。
      </p>
    </section>

    <section class="uv-section">
      <h3 class="uv-section__title"><span class="uv-section__index">2</span>工作批次与备注</h3>
      <label class="uv-form-field">
        <span class="uv-form-label">备注（会写入排班记录）</span>
        <textarea
          v-model="note"
          class="uv-input uv-textarea"
          rows="3"
          :disabled="!canWrite"
          placeholder="例如：跨机兼岗，按份额核对工作批次"
        />
        <span class="uv-form-help">
          份额默认 1；跨机兼岗的份额由排班记录表达，系统不从班次名单推测，也不禁止熟练工多机覆盖。
        </span>
      </label>
    </section>

    <p v-if="errorMessage" class="uv-form-error" role="alert">
      <AlertTriangle class="size-3.5" aria-hidden="true" />
      保存失败：{{ errorMessage }}。当前勾选与备注已保留，可直接重试。
    </p>

    <template #actions>
      <Button variant="outline" type="button" :disabled="busy" @click="emit('close')">取消</Button>
      <Button type="button" :disabled="!canSave" @click="submit">
        {{ busy ? '正在保存…' : '保存本班排班' }}
      </Button>
    </template>

  </UvDrawer>
</template>
