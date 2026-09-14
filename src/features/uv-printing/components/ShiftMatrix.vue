<script setup lang="ts">
import { computed } from 'vue'
import { AlertTriangle, CalendarOff, UserPlus } from '@lucide/vue'
import type { BusinessDate, ShiftCode, UvAssignment, UvMachine, UvShiftTemplate, UvWorkerRef } from '../contracts'
import { EMPLOY_STATE_LABELS, WORKER_ROLE_LABELS } from '../domain/status'
import { SHIFT_LABELS } from '../domain/businessTime'

/**
 * 机台×白夜班排班矩阵（UV_PRINT_SHARED_SPEC.md 5.6 / 6.7）。
 *
 * - 行 = 机台，列 = 所选业务日期的白班/夜班；单元格展示参与人员与份额；
 *   此处使用 `.uv-matrix-scroll` / `.uv-matrix`，只有矩阵自身横向滚动。
 * - 同一班次里同一名熟练工出现在多台机台时给出可见的「冲突提示」，
 *   但默认不禁止兼岗：份额与工作批次必须在工资预览里核对，页面上明确写出这条口径。
 * - 点击/键盘等价操作是必须的：每个单元格都有一个真实的 <button>（覆盖层），
 *   聚焦名称与单元格可见内容通过 aria-describedby 关联，读屏用户听到的是同一份事实。
 * - 窄屏不挤压矩阵，改用同一份数据的纵向可读列表。
 */

const props = withDefaults(defineProps<{
  machines: UvMachine[]
  businessDate: BusinessDate
  /** 矩阵列；默认白班 + 夜班。 */
  shifts?: ShiftCode[]
  templates?: UvShiftTemplate[]
  assignments: UvAssignment[]
  workers: UvWorkerRef[]
  /** 缺少排班写权限时，单元格按钮不可用并说明原因。 */
  editable?: boolean
}>(), {
  shifts: () => ['day', 'night'] as ShiftCode[],
  templates: () => [],
  editable: true,
})

const emit = defineEmits<{
  open: [payload: { machineId: string; shift: ShiftCode }]
  'open-worker': [workerId: string]
}>()

const workerById = computed(() => {
  const map = new Map<string, UvWorkerRef>()
  for (const worker of props.workers) map.set(worker.id, worker)
  return map
})

function workerName(workerId: string): string {
  return workerById.value.get(workerId)?.display_name ?? workerId
}

export interface MatrixWorkerChip {
  workerId: string
  name: string
  roleLabel: string
  employLabel: string
  left: boolean
  /** 份额不是 1 时表示跨机兼岗，必须显示出来。 */
  shareLabel: string
  conflict: boolean
}

export interface MatrixCell {
  machineId: string
  shift: ShiftCode
  shiftLabel: string
  timeLabel: string
  workers: MatrixWorkerChip[]
  conflicts: string[]
  /** 单元格正文的可见文本，供读屏与测试读取。 */
  summaryText: string
  buttonLabel: string
}

export interface MatrixRow {
  machineId: string
  machineCode: string
  machineName: string
  /** 已停用机台不参与排产，但仍保留历史排班。 */
  disabled: boolean
  cells: MatrixCell[]
}

const dayAssignments = computed(() =>
  props.assignments.filter((assignment) => assignment.business_date === props.businessDate),
)

/** 冲突口径：同一业务日期、同一班次，同一名员工被安排到多于一台机台。 */
const conflictsByWorker = computed(() => {
  const machines = new Map<string, Set<string>>()
  for (const assignment of dayAssignments.value) {
    const key = `${assignment.shift}:${assignment.worker_id}`
    const set = machines.get(key) ?? new Set<string>()
    set.add(assignment.machine_id)
    machines.set(key, set)
  }
  const conflicts = new Map<string, string[]>()
  for (const [key, machineIds] of machines) {
    if (machineIds.size < 2) continue
    const workerId = key.slice(key.indexOf(':') + 1)
    conflicts.set(workerId, [...machineIds].sort((a, b) => a.localeCompare(b, 'en')))
  }
  return conflicts
})

function templateFor(shift: ShiftCode): UvShiftTemplate | undefined {
  return props.templates.find((template) => template.shift === shift)
}

function timeLabel(shift: ShiftCode): string {
  const template = templateFor(shift)
  if (!template) return SHIFT_LABELS[shift]
  const prefix = shift === 'night' ? '次日' : ''
  return `${template.start_local}–${prefix}${template.end_local}`
}

function chipsFor(machineId: string, shift: ShiftCode): MatrixWorkerChip[] {
  return dayAssignments.value
    .filter((assignment) => assignment.machine_id === machineId && assignment.shift === shift)
    .map((assignment) => {
      const worker = workerById.value.get(assignment.worker_id)
      return {
        workerId: assignment.worker_id,
        name: worker?.display_name ?? assignment.worker_id,
        roleLabel: WORKER_ROLE_LABELS[worker?.role ?? ''] ?? '岗位待登记',
        employLabel: EMPLOY_STATE_LABELS[worker?.employ_state ?? ''] ?? '在职状态待确认',
        left: worker?.employ_state === 'left',
        shareLabel: assignment.share === 1 ? '份额 1' : `份额 ${assignment.share}`,
        conflict: (conflictsByWorker.value.get(assignment.worker_id)?.length ?? 0) > 1,
      }
    })
    .sort((a, b) => a.name.localeCompare(b.name, 'zh-Hans-CN'))
}

function cellFor(machine: UvMachine, shift: ShiftCode): MatrixCell {
  const workers = chipsFor(machine.id, shift)
  const conflictWorkers = workers.filter((chip) => chip.conflict)
  const shiftLabel = SHIFT_LABELS[shift]
  const assignmentText = workers.length
    ? workers.map((chip) => `${chip.name}（${chip.roleLabel}·${chip.shareLabel}）`).join('、')
    : '未安排人员'
  const conflictText = conflictWorkers.length
    ? `冲突提示：${conflictWorkers.map((chip) => chip.name).join('、')} 在同一${shiftLabel}同时排在多台机台，份额与工作批次必须核对。`
    : '本班次没有跨机兼岗。'

  return {
    machineId: machine.id,
    shift,
    shiftLabel,
    timeLabel: timeLabel(shift),
    workers,
    conflicts: conflictWorkers.map((chip) =>
      `${chip.name} 同时参与 ${conflictsByWorker.value.get(chip.workerId)?.length ?? 0} 台机台的${shiftLabel}`,
    ),
    summaryText: `${assignmentText}。${workers.length ? conflictText : '点击或按回车安排本班人员。'}`,
    buttonLabel: `${machine.code} ${machine.name} ${shiftLabel}（${timeLabel(shift)}）排班：${assignmentText}${conflictWorkers.length ? `。${conflictText}` : ''}`,
  }
}

const rows = computed<MatrixRow[]>(() =>
  props.machines.map((machine) => ({
    machineId: machine.id,
    machineCode: machine.code,
    machineName: machine.name,
    disabled: machine.admin_status === 'disabled',
    cells: props.shifts.map((shift) => cellFor(machine, shift)),
  })),
)

const conflictCount = computed(() => conflictsByWorker.value.size)
function hasConflict(machineId: string, shift: ShiftCode): boolean {
  return chipsFor(machineId, shift).some((chip) => chip.conflict)
}
</script>

<template>
  <div class="uv-matrix-block-inner">
    <!-- 桌面与平板：机台×班次矩阵，只有矩阵容器横向滚动。 -->
    <div class="uv-matrix-scroll uv-matrix-view" role="region" tabindex="0" aria-label="机台与白夜班排班矩阵">
      <table class="uv-matrix">
        <caption class="uv-table-caption">
          {{ businessDate }} 机台×白夜班排班：行为机台，列为白班与夜班。点击或按回车打开排班编辑。
        </caption>
        <thead>
          <tr>
            <th scope="col">机台</th>
            <th v-for="shift in shifts" :key="shift" scope="col">
              {{ SHIFT_LABELS[shift] }}
              <span class="uv-table-th-hint">{{ timeLabel(shift) }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.machineId">
            <th scope="row">
              <span class="uv-matrix__machine">{{ row.machineCode }}</span>
              <span class="uv-row-sub">{{ row.machineName }}</span>
              <span v-if="row.disabled" class="uv-matrix__flag">已停用·保留历史排班</span>
            </th>
            <td v-for="cell in row.cells" :key="cell.shift">
              <div
                class="uv-matrix__cell-wrap"
                :class="hasConflict(cell.machineId, cell.shift) ? 'uv-matrix__cell--conflict' : ''"
              >
                <div :id="`uv-cell-${cell.machineId}-${cell.shift}`" class="uv-matrix__cell">
                  <div v-if="cell.workers.length" class="uv-matrix__names">
                    <span
                      v-for="chip in cell.workers"
                      :key="chip.workerId"
                      class="uv-matrix__name"
                      :class="chip.left ? 'uv-matrix__name--left' : ''"
                    >
                      {{ chip.name }}
                      <span class="uv-matrix__share">{{ chip.roleLabel }} · {{ chip.shareLabel }}</span>
                    </span>
                  </div>
                  <span v-else class="uv-matrix__cell--empty">
                    <CalendarOff class="inline size-3.5" aria-hidden="true" />
                    未安排人员，点击安排
                  </span>
                  <span v-if="cell.conflicts.length" class="uv-matrix__conflict" role="status">
                    <AlertTriangle class="inline size-3" aria-hidden="true" />
                    冲突提示：{{ cell.conflicts.join('；') }}
                  </span>
                </div>
                <button
                  type="button"
                  class="uv-matrix__cell-hit"
                  :disabled="!editable"
                  :aria-describedby="`uv-cell-${cell.machineId}-${cell.shift}`"
                  :aria-label="cell.buttonLabel"
                  :data-machine-id="cell.machineId"
                  :data-shift="cell.shift"
                  @click="emit('open', { machineId: cell.machineId, shift: cell.shift })"
                />
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 窄屏：同一份数据的纵向列表，不挤压矩阵。 -->
    <div class="uv-matrix-cards uv-matrix-cards-view">
      <p class="uv-callout">
        窄屏使用机台卡片列出同一份排班；桌面宽度可切回完整矩阵，两者数据完全一致。
        矩阵只呈现排班事实，不呈现任何计件金额。
      </p>
      <article
        v-for="row in rows"
        :key="`card-${row.machineId}`"
        class="uv-matrix-card"
        :data-machine-id="row.machineId"
      >
        <header class="uv-matrix-card__head">
          <p class="uv-machine-card__code">{{ row.machineCode }}</p>
          <p class="uv-machine-card__name">{{ row.machineName }}</p>
          <p v-if="row.disabled" class="uv-matrix__flag">已停用·保留历史排班</p>
        </header>
        <div v-for="cell in row.cells" :key="`card-cell-${cell.shift}`" class="uv-matrix-card__cell">
          <p class="uv-machine-card__label">{{ cell.shiftLabel }} · {{ cell.timeLabel }}</p>
          <div v-if="cell.workers.length" class="uv-matrix__names">
            <span
              v-for="chip in cell.workers"
              :key="chip.workerId"
              class="uv-matrix__name"
              :class="chip.left ? 'uv-matrix__name--left' : ''"
            >
              {{ chip.name }}
              <span class="uv-matrix__share">{{ chip.roleLabel }} · {{ chip.shareLabel }}</span>
            </span>
          </div>
          <span v-else class="uv-matrix__cell--empty">未安排人员</span>
          <p v-if="cell.conflicts.length" class="uv-matrix__conflict" role="status">
            <AlertTriangle class="inline size-3" aria-hidden="true" />
            冲突提示：{{ cell.conflicts.join('；') }}
          </p>
          <div class="uv-actions">
            <button
              type="button"
              class="uv-chip"
              :disabled="!editable"
              :data-machine-id="cell.machineId"
              :data-shift="cell.shift"
              @click="emit('open', { machineId: cell.machineId, shift: cell.shift })"
            >
              <UserPlus class="size-3" aria-hidden="true" />
              {{ cell.workers.length ? '调整本班人员' : '安排本班人员' }}
            </button>
            <button
              v-for="chip in cell.workers"
              :key="`card-pay-${chip.workerId}`"
              type="button"
              class="uv-chip"
              @click="emit('open-worker', chip.workerId)"
            >
              查看 {{ chip.name }} 的工资构成
            </button>
          </div>
        </div>
      </article>
    </div>
  </div>
</template>
