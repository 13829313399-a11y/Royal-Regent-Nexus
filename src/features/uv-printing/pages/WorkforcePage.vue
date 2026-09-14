<script setup lang="ts">
import { computed, inject, ref, watch } from 'vue'
import { AlertTriangle, Calculator, CalendarClock, CheckCircle2, RefreshCw, UserRound } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import type {
  BusinessDate,
  Id,
  Money,
  ShiftCode,
  UvAssignment,
  UvMachine,
  UvPayrollLine,
  UvPayrollPreview,
  UvReport,
  UvShiftTemplate,
  UvWorkerRef,
  UvWorkspaceTransport,
} from '../contracts'
import { UV_PERMISSIONS } from '../contracts'
import { UV_CONTEXT_KEY, UV_TRANSPORT_KEY } from '../composables/uvPageContext'
import { newOperationId, useUvCommand, useUvRequest } from '../composables/useUvRequest'
import { addDays, SHIFT_LABELS } from '../domain/businessTime'
import {
  currencyMinorUnits,
  decimalCompare,
  decimalRound,
  formatMoney,
  money,
  splitRemainder,
} from '../domain/decimal'
import { PAYROLL_STATE } from '../domain/status'
import { readAllPages } from '../transport/pagination'
import UvStateBlock, { type UvSurfaceState } from '../components/UvStateBlock.vue'
import UvStatusPill from '../components/UvStatusPill.vue'
import UvNumber from '../components/UvNumber.vue'
import ShiftMatrix from '../components/ShiftMatrix.vue'
import AssignmentEditorDrawer from '../components/AssignmentEditorDrawer.vue'
import WorkerPayrollDrawer, {
  type WorkerPayrollAllocationGroup,
  type WorkerPayrollDetailRow,
  type WorkerPayrollPendingItem,
} from '../components/WorkerPayrollDrawer.vue'

/**
 * 人员班次工作区（UV_PRINT_SHARED_SPEC.md 5.3 / 5.6 / 6.7）。
 *
 * - 主视图是机台×白夜班矩阵；排班写入需要 uv_printing:shift_write，
 *   工资相关读取（payrollPreview 与每名员工的金额）需要 uv_printing:payroll_read；
 * - 没有 payroll_read 时不请求、不渲染任何金额，只说明「没有查看工资的权限」——
 *   隐藏列不是权限控制，服务端才是权威；
 * - 加载 / 空 / 无结果 / 无权限 / 失败 / 过期全部由 UvStateBlock 表达，
 *   读取失败不回落到样例数据、也不显示 0；
 * - 计件工资与商业执行价严格分开：本页只出现计件口径，不显示产值。
 */

const transportRef = inject(UV_TRANSPORT_KEY)
const pageContext = inject(UV_CONTEXT_KEY)

if (!transportRef || !pageContext) {
  throw new Error('人员班次工作区必须在 UV 工作区壳内使用：缺少 UV_TRANSPORT_KEY 或 UV_CONTEXT_KEY。')
}

const transport = transportRef
const ctx = pageContext
const workspace = ctx.workspace

/* ------------------------------------------------------------------ *
 * 查询范围
 * ------------------------------------------------------------------ */

const businessDate = computed<BusinessDate>(() => workspace.business_date.value)
/** 工资明细的可读窗口：业务日期往前 30 天，避免一次拉取全部历史。 */
const payrollWindowFrom = computed<BusinessDate>(() => addDays(businessDate.value, -30))
const matrixShifts: ShiftCode[] = ['day', 'night']

function baseScope() {
  return workspace.scopeFor()
}

function canReadPayroll(): boolean {
  return workspace.can(UV_PERMISSIONS.payrollRead)
}

/* ------------------------------------------------------------------ *
 * 读取
 * ------------------------------------------------------------------ */

const workersRequest = useUvRequest(
  (signal) =>
    readAllPages((nextScope, nextSignal) => transport.value.workers(nextScope, nextSignal), baseScope(), signal).then((response) => {
      asOf.value = response.meta.as_of
      return response.data.items
    }),
  { immediate: false },
)
const templatesRequest = useUvRequest(
  (signal) => readAllPages((nextScope, nextSignal) => transport.value.shiftTemplates(nextScope, nextSignal), baseScope(), signal).then((response) => response.data.items),
  { immediate: false },
)
const assignmentsRequest = useUvRequest(
  (signal) =>
    readAllPages((nextScope, nextSignal) => transport.value.assignments(nextScope, nextSignal), { ...baseScope(), business_date: businessDate.value }, signal)
      .then((response) => response.data.items),
  { immediate: false },
)
const reportsRequest = useUvRequest(
  (signal) =>
    readAllPages((nextScope, nextSignal) => transport.value.reports(nextScope, nextSignal), { ...baseScope(), date_from: payrollWindowFrom.value, date_to: businessDate.value }, signal)
      .then((response) => response.data.items),
  { immediate: false },
)
const payrollRequest = useUvRequest(
  (signal) =>
    transport.value
      .payrollPreview({ ...baseScope(), date_from: payrollWindowFrom.value, date_to: businessDate.value }, signal)
      .then((response) => {
        asOf.value = response.meta.as_of
        return response.data
      }),
  { immediate: false },
)

const machinesRequest = useUvRequest(
  (signal) =>
    readAllPages((nextScope, nextSignal) => transport.value.machines(nextScope, nextSignal), baseScope(), signal).then((response) => {
      asOf.value = response.meta.as_of
      return response.data.items
    }),
  { immediate: false },
)

const workers = computed<UvWorkerRef[]>(() => workersRequest.data.value ?? [])
const templates = computed<UvShiftTemplate[]>(() => templatesRequest.data.value ?? [])
const assignments = computed<UvAssignment[]>(() => assignmentsRequest.data.value ?? [])
const reports = computed<UvReport[]>(() => reportsRequest.data.value ?? [])
const machines = computed<UvMachine[]>(() => machinesRequest.data.value ?? [])
const payroll = computed<UvPayrollPreview | null>(() => payrollRequest.data.value)

const transportError = ref('')
const loadError = computed(
  () =>
    workersRequest.error.value
    ?? templatesRequest.error.value
    ?? assignmentsRequest.error.value
    ?? reportsRequest.error.value
    ?? machinesRequest.error.value,
)

const firstSettled = computed(
  () =>
    workersRequest.settled.value
    && templatesRequest.settled.value
    && assignmentsRequest.settled.value
    && reportsRequest.settled.value
    && machinesRequest.settled.value,
)

const reading = computed(() =>
  !transportError.value
  && (!firstSettled.value
    || workersRequest.loading.value
    || templatesRequest.loading.value
    || assignmentsRequest.loading.value
    || reportsRequest.loading.value
    || machinesRequest.loading.value),
)

/** 使用服务端 as_of 判断过期；阈值 12 小时，与心跳 5 分钟阈值区分开。 */
const STALE_MINUTES = 12 * 60
const asOf = ref<string>('')

const staleMinutes = computed(() => {
  if (!asOf.value) return null
  const minutes = Math.round((Date.now() - new Date(asOf.value).getTime()) / 60_000)
  return Number.isFinite(minutes) ? minutes : null
})

/** 过期是可继续查看的告警：说明数据截止时间，但不把事实藏起来。 */
const isStale = computed(() => staleMinutes.value !== null && staleMinutes.value > STALE_MINUTES)

const pageState = computed<UvSurfaceState>(() => {
  if (ctx.workspace.violation.value) return 'forbidden'
  if (transportError.value) return 'error'
  if (reading.value) return 'loading'
  if (loadError.value) return 'error'
  if (!machines.value.length) return 'empty'
  if (!workers.value.length) return 'empty'
  if (!assignments.value.length) return 'no-result'
  return 'ready'
})

const stateMessage = computed(() => {
  const error = loadError.value
  if (!error) return '排班与人员名单没有读取成功，这里不是「0 条」，也不会回落样例数据。'
  return `${error.message}（错误码 ${error.code}${error.status ? ` · HTTP ${error.status}` : ''}）`
})

async function loadAll() {
  transportError.value = ''
  if (!transport.value) {
    transportError.value = '当前上下文没有可用的 transport。'
    return
  }
  const tasks: Array<Promise<unknown>> = [
    workersRequest.run(),
    templatesRequest.run(),
    machinesRequest.run(),
    assignmentsRequest.run(),
    reportsRequest.run(),
  ]
  if (canReadPayroll()) tasks.push(payrollRequest.run())
  else payrollRequest.reset()
  await Promise.all(tasks)
}

const sourceKey = computed(() => [
  ctx.revision.value,
  businessDate.value,
  workspace.shift.value,
  String(transport.value ? 'transport' : 'none'),
].join('|'))

watch(sourceKey, () => { void loadAll() }, { immediate: true })

/* ------------------------------------------------------------------ *
 * 冲突与兼岗
 * ------------------------------------------------------------------ */

const conflictsByWorker = computed(() => {
  const machineIds = new Map<string, Set<string>>()
  for (const assignment of assignments.value) {
    const key = `${assignment.shift}:${assignment.worker_id}`
    const set = machineIds.get(key) ?? new Set<string>()
    set.add(assignment.machine_id)
    machineIds.set(key, set)
  }
  const result = new Map<string, string[]>()
  for (const [key, set] of machineIds) {
    if (set.size < 2) continue
    result.set(key.slice(key.indexOf(':') + 1), [...set].sort((a, b) => a.localeCompare(b, 'en')))
  }
  return result
})

/** 传给排班抽屉的兼岗提示：当前班次里该员工已排到哪些机台。 */
const machineIdsByWorker = computed<Record<string, string[]>>(() => {
  const result: Record<string, string[]> = {}
  for (const assignment of assignments.value) {
    const list = result[assignment.worker_id] ?? []
    if (!list.includes(assignment.machine_id)) list.push(assignment.machine_id)
    result[assignment.worker_id] = list
  }
  return result
})

/** 兼岗汇总：同一班次里跨机参与的员工，供排班组标题与单元格冲突提示共用。 */
const conflictSummary = computed<Array<{ workerId: string; name: string; machineCount: number }>>(
  () =>
    [...conflictsByWorker.value.entries()]
      .map(([workerId, machineIds]) => ({
        workerId,
        name: workers.value.find((worker) => worker.id === workerId)?.display_name ?? workerId,
        machineCount: machineIds.length,
      }))
      .sort((a, b) => b.machineCount - a.machineCount || a.name.localeCompare(b.name, 'zh-Hans-CN')),
)

/* ------------------------------------------------------------------ *
 * 排班抽屉
 * ------------------------------------------------------------------ */

const editorOpen = ref(false)
const editing = ref<{ machineId: Id; shift: ShiftCode } | null>(null)
const editorRef = ref<{ applyCopy: (workerIds: string[]) => void } | null>(null)
const copyLoading = ref(false)
const copyError = ref('')

const assignmentCommand = useUvCommand<unknown>()
const editingMachine = computed<UvMachine | null>(
  () => machines.value.find((machine) => machine.id === editing.value?.machineId) ?? null,
)

const editingAssignments = computed(() =>
  assignments.value.filter(
    (assignment) =>
      assignment.machine_id === editing.value?.machineId
      && assignment.shift === editing.value?.shift
      && assignment.business_date === businessDate.value,
  ),
)

const assignedWorkerIds = computed(() => editingAssignments.value.map((assignment) => assignment.worker_id))

/** 相邻班次：白天之前是前一日夜班，夜班之前是同日白班。 */
const previousShift = computed<{ businessDate: BusinessDate; shift: ShiftCode } | null>(() => {
  if (!editing.value) return null
  return editing.value.shift === 'day'
    ? { businessDate: addDays(businessDate.value, -1), shift: 'night' }
    : { businessDate: businessDate.value, shift: 'day' }
})

const canWriteShift = computed(() => workspace.can(UV_PERMISSIONS.shiftWrite))

function openEditor(payload: { machineId: Id; shift: ShiftCode }) {
  editing.value = { machineId: payload.machineId, shift: payload.shift }
  copyError.value = ''
  editorOpen.value = true
}

function closeEditor() {
  editorOpen.value = false
  assignmentCommand.clearError()
}

async function copyPreviousShift() {
  const target = editing.value
  const source = previousShift.value
  if (!target || !source) return
  copyLoading.value = true
  copyError.value = ''
  try {
    const response = await readAllPages((nextScope, nextSignal) => transport.value.assignments(nextScope, nextSignal),
      { ...baseScope(), business_date: source.businessDate, shift: source.shift },
      new AbortController().signal,
    )
    const sourceAssignments = response.data.items.filter(
      (assignment) => assignment.business_date === source.businessDate
        && assignment.shift === source.shift
        && assignment.machine_id === target.machineId,
    )
    if (!sourceAssignments.length) {
      copyError.value = `${source.businessDate} ${SHIFT_LABELS[source.shift]} 该机台没有可复制的排班计划`
      return
    }
    editorRef.value?.applyCopy(sourceAssignments.map((assignment) => assignment.worker_id))
  } catch (error) {
    copyError.value = error instanceof Error ? error.message : String(error)
  } finally {
    copyLoading.value = false
  }
}

async function saveAssignments(payload: { workerIds: Id[]; note: string }) {
  const target = editing.value
  if (!target) return
  const operationId = newOperationId()
  const result = await assignmentCommand.execute(operationId, () =>
    transport.value.saveAssignments({
      factory_id: baseScope().factory_id,
      operation_id: operationId,
      expected_version: 0,
      business_date: businessDate.value,
      shift: target.shift,
      machine_id: target.machineId,
      worker_ids: payload.workerIds,
      note: payload.note,
    }),
  )
  if (!result) return
  ctx.markDirty()
  closeEditor()
}

/* ------------------------------------------------------------------ *
 * 工资预览（需要 payroll_read）
 * ------------------------------------------------------------------ */

const payrollAllowed = computed(() => canReadPayroll())
const payrollLineById = computed(() => {
  const map = new Map<string, UvPayrollLine>()
  for (const line of payroll.value?.lines ?? []) map.set(line.worker_id, line)
  return map
})

const payrollPending = computed<WorkerPayrollPendingItem[]>(() => {
  const snapshot = payroll.value
  if (!snapshot) return []
  const items: WorkerPayrollPendingItem[] = []
  if (snapshot.unpriced_reports > 0) {
    items.push({
      key: 'unpriced',
      label: '未定价',
      count: snapshot.unpriced_reports,
      reason: '该产品/工艺在此机台没有生效的计件工价，金额保持未定价，不用 0 代替。',
    })
  }
  if (snapshot.unassigned_reports > 0) {
    items.push({
      key: 'unassigned',
      label: '未排班',
      count: snapshot.unassigned_reports,
      reason: '报工没有参与人员，无法拆分工资；先补齐排班再复核这笔报工。',
    })
  }
  if (snapshot.quality_pending_reports > 0) {
    items.push({
      key: 'quality',
      label: '待核',
      count: snapshot.quality_pending_reports,
      reason: '质量尚未判清，按已判合格量暂算；待判数量判定后金额会变化。',
    })
  }
  return items
})

const payrollProvisional = computed(() => {
  const snapshot = payroll.value
  if (!snapshot) return true
  return snapshot.coverage !== 'complete' || snapshot.lines.some((line) => line.state !== 'confirmed' && line.state !== 'adjusted')
})

/** 未定价优先级最高：任何一条未定价报工都会把整体口径标成未定价，而不是暂算。 */
const payrollState = computed(() => {
  const unpriced = (payroll.value?.lines ?? []).some((line) => line.state === 'unpriced')
  if (unpriced || payrollPending.value.some((item) => item.key === 'unpriced')) return 'unpriced'
  const settled = (payroll.value?.lines ?? []).every((line) => line.state === 'confirmed' || line.state === 'adjusted')
  if (!settled || !(payroll.value?.lines.length ?? 0)) return 'provisional'
  return (payroll.value?.lines ?? []).some((line) => line.state === 'adjusted') ? 'adjusted' : 'confirmed'
})
const payrollStateView = computed(() => PAYROLL_STATE[payrollState.value])
const payrollPanelState = computed<UvSurfaceState>(() => {
  if (!payrollAllowed.value) return 'forbidden'
  if (payrollRequest.loading.value && !payroll.value) return 'loading'
  if (payrollRequest.error.value) return 'error'
  if (!payroll.value) return 'idle'
  if (!payroll.value.lines.length) return payroll.value.unassigned_reports > 0 ? 'no-result' : 'empty'
  return 'ready'
})

/** 员工姓名只来自名册；找不到就说明名册缺失，不猜姓名。 */
function workerName(workerId: Id): string {
  return workers.value.find((worker) => worker.id === workerId)?.display_name ?? `员工名册缺失（${workerId}）`
}

const payrollRows = computed(() =>
  (payroll.value?.lines ?? []).map((line) => ({
    ...line,
    worker: workers.value.find((worker) => worker.id === line.worker_id) ?? null,
  })),
)

const payrollReadNote = computed(() =>
  payroll.value?.warnings.map((warning) => warning.message).join('；') ?? '',
)

/* ------------------------------------------------------------------ *
 * 员工工资抽屉
 * ------------------------------------------------------------------ */

const selectedWorkerId = ref<Id | null>(null)
const selectedWorker = computed<UvWorkerRef | null>(
  () => workers.value.find((worker) => worker.id === selectedWorkerId.value) ?? null,
)
const selectedLine = computed<UvPayrollLine | null>(
  () => (selectedWorkerId.value ? payrollLineById.value.get(selectedWorkerId.value) ?? null : null),
)

const selectedReports = computed(() => {
  const workerId = selectedWorkerId.value
  if (!workerId) return []
  return reports.value.filter((report) => report.worker_ids.includes(workerId))
})

const currency = computed(() => payroll.value?.currency ?? payroll.value?.batch_total?.currency ?? '')

function machineLabel(machineId: Id): string {
  const machine = machines.value.find((candidate) => candidate.id === machineId)
  return machine ? `${machine.code} ${machine.name}` : `机台名册缺失（${machineId}）`
}

/** 报工金额快照来自服务端的 worker_shares；缺失时按同机同班同批次分摊规则现算。 */
function amountFor(workerId: Id, report: UvReport): Money | null {
  const share = report.worker_shares?.find((candidate) => candidate.worker_id === workerId)
  if (share) return share.amount
  const staffCurrency = currency.value
  if (!staffCurrency || !report.payroll?.amount) return null
  const participantIds = [...report.worker_ids].sort((a, b) => a.localeCompare(b))
  const index = participantIds.indexOf(workerId)
  if (index < 0) return null
  const shares = splitRemainder(report.payroll.amount.amount, participantIds.length, staffCurrency)
  return money(staffCurrency, shares[index] ?? '0')
}

const detailRows = computed<WorkerPayrollDetailRow[]>(() =>
  selectedReports.value.map((report) => {
    const payrollStateForReport = report.payroll?.state ?? 'unpriced'
    const pieceWage = report.payroll?.piece_wage ?? null
    const amount = amountFor(selectedWorkerId.value ?? '', report)
    return {
      key: report.id,
      reportId: report.id,
      businessDate: report.business_date,
      shiftLabel: SHIFT_LABELS[report.shift],
      machineLabel: machineLabel(report.machine_id),
      productLabel: `${report.product_no} ${report.product_name}`,
      goodQty: report.good_qty,
      pieceWage,
      rateVersionId: report.payroll?.rate_version_id ?? null,
      amount,
      state: payrollStateForReport,
      reason: amount ? '' : pieceWage === null ? '该产品/工艺在此机台没有生效的计件工价' : '没有已确认合格数量或未安排人员，暂不计薪',
      qualityPending: report.quality_status !== 'complete',
    }
  }),
)

const detailAllocations = computed<WorkerPayrollAllocationGroup[]>(() => {
  const workerId = selectedWorkerId.value
  const staffCurrency = currency.value
  if (!workerId || !staffCurrency) return []
  const groups: WorkerPayrollAllocationGroup[] = []
  for (const report of selectedReports.value) {
    const batch = report.payroll?.amount ?? null
    if (!batch || !report.worker_ids.length) continue
    const participants = [...report.worker_ids].sort((a, b) => a.localeCompare(b))
    const minor = currencyMinorUnits(staffCurrency)
    const shares = splitRemainder(batch.amount, participants.length, staffCurrency)
    const roundedShares = shares.map((share) => decimalRound(share, minor))
    const plainShare = roundedShares.reduce(
      (smallest, share) => (decimalCompare(share, smallest) < 0 ? share : smallest),
      roundedShares[0] ?? '0',
    )
    groups.push({
      key: report.id,
      label: `${report.business_date} ${SHIFT_LABELS[report.shift]} · ${machineLabel(report.machine_id)} · 报工 ${report.id}`,
      currency: staffCurrency,
      batchTotal: batch,
      participantCount: participants.length,
      baseShare: money(staffCurrency, plainShare),
      participants: participants.map((participantId, index) => ({
        workerId: participantId,
        workerName: workerName(participantId),
        employeeNo: workers.value.find((worker) => worker.id === participantId)?.employee_no ?? '工号待登记',
        amount: money(staffCurrency, shares[index] ?? '0'),
        remainderAdjusted: decimalCompare(roundedShares[index] ?? '0', plainShare) > 0,
      })),
    })
  }
  return groups
})
</script>

<template>
  <div class="uv-workforce">
    <header class="uv-page-head">
      <div class="uv-page-head__titles">
        <p class="uv-page-head__eyebrow">Workforce &amp; Payroll</p>
        <h1>人员班次</h1>
        <p class="uv-page-head__desc">
          以机台×白夜班查看排班事实，并按同机同班同工作批次核对计件工资分摊。
          排班写入与工资读取分别需要 uv_printing:shift_write 与 uv_printing:payroll_read；
          本页只呈现计件口径，商业执行价与产值不在本页换算。
        </p>
      </div>
      <div class="uv-page-head__actions">
        <label class="uv-filter">
          <span class="uv-filter__label">业务日期</span>
          <input
            class="uv-input"
            type="date"
            data-uv="business-date"
            :value="businessDate"
            @change="workspace.setBusinessDate(($event.target as HTMLInputElement).value)"
          >
        </label>
        <label class="uv-filter">
          <span class="uv-filter__label">班次</span>
          <select
            class="uv-input uv-select"
            data-uv="shift"
            :value="workspace.shift.value"
            @change="workspace.setShift(($event.target as HTMLSelectElement).value as 'day' | 'night' | 'all')"
          >
            <option value="all">全天</option>
            <option value="day">白班</option>
            <option value="night">夜班</option>
          </select>
        </label>
        <Button variant="outline" size="sm" type="button" :disabled="reading" @click="loadAll">
          <RefreshCw class="size-3.5" :class="reading ? 'motion-safe:animate-spin' : ''" aria-hidden="true" />
          {{ reading ? '刷新中…' : '刷新排班' }}
        </Button>
      </div>
    </header>

    <UvStateBlock
      :state="pageState"
      subject="人员班次与工资预览"
      :message="stateMessage"
      :retryable="pageState === 'error'"
      :hint="ctx.isPreview.value ? '样例预览同样遵守这条口径：失败不回落、不用 0 代替。' : '可放宽业务日期或先补齐排班与人员名册。'"
      @retry="loadAll"
    >
      <UvStateBlock
        v-if="isStale"
        state="stale"
        subject="排班事实"
        :message="`服务端数据截止 ${asOf}，已超过 ${STALE_MINUTES / 60} 小时；下方事实仍按该时间点显示，请先刷新再用于工资确认。`"
        retryable
        compact
        @retry="loadAll"
      />

      <div class="uv-grid">
        <section class="uv-panel">
          <header class="uv-panel__head">
            <div>
              <h2 class="uv-panel__title">机台×白夜班矩阵</h2>
              <p class="uv-panel__subtitle">
                {{ businessDate }} 的行=机台、列=白班/夜班。单元格里是参与人员与份额；
                兼岗不阻断排班，但份额与工作批次必须在工资预览里逐条核对。
              </p>
            </div>
            <div class="uv-actions">
              <span class="uv-readonly-note">
                <CalendarClock class="size-3.5" aria-hidden="true" />
                {{ asOf ? `数据截止 ${asOf}` : '数据截止时间由服务端提供' }}
              </span>
              <span v-if="!canWriteShift" class="uv-readonly-note">只读：没有排班写权限</span>
            </div>
          </header>
          <div class="uv-panel__body uv-panel__body--flush">
            <p v-if="!canWriteShift" class="uv-callout uv-callout--warning" role="status">
              当前账号缺少 uv_printing:shift_write：可以查看排班矩阵，但单元格不可编辑，
              「复制前一班」与保存都会被服务端拒绝。
            </p>
            <div class="uv-matrix-block">
              <p v-if="conflictSummary.length" class="uv-callout uv-callout--warning">
                <AlertTriangle class="inline size-3.5" aria-hidden="true" />
                本班次有 {{ conflictSummary.length }} 名熟练工同时排在多台机台（{{
                  conflictSummary.map((item) => `${item.name}·${item.machineCount} 台`).join('，')
                }}）。兼岗默认不阻断排班，但<strong>份额与对应工作批次必须逐条核对</strong>，
                否则工资预览会把同一份计件金额重复分摊。矩阵单元格内另有逐格冲突提示。
              </p>
              <p v-else class="uv-callout">
                本班次没有跨机兼岗：每位员工只出现在一台机台。
              </p>
            </div>
            <ShiftMatrix
              :machines="machines"
              :business-date="businessDate"
              :shifts="matrixShifts"
              :templates="templates"
              :assignments="assignments"
              :workers="workers"
              :editable="canWriteShift"
              @open="openEditor"
              @open-worker="selectedWorkerId = $event"
            />
          </div>
        </section>

        <section class="uv-panel">
          <header class="uv-panel__head">
            <div>
              <h2 class="uv-panel__title">班组计件工资预览</h2>
              <p class="uv-panel__subtitle">
                {{ payrollWindowFrom }} ~ {{ businessDate }} · 口径：可计薪合格数量 × 计件工价快照。
                与商业执行价严格分开。
              </p>
            </div>
            <UvStatusPill v-if="payrollAllowed && payroll" :status="payrollStateView" compact />
          </header>

          <div class="uv-panel__body">
            <UvStateBlock
              :state="payrollPanelState"
              subject="工资预览"
              :message="payrollRequest.error.value ? `${payrollRequest.error.value.message}（错误码 ${payrollRequest.error.value.code}）` : '工资预览没有读取成功；这里不是 0，也不会用样例数据补齐。'"
              :retryable="payrollPanelState === 'error'"
              hint="工资相关读取需要 uv_printing:payroll_read；没有该权限时服务端会省略金额字段。"
              @retry="payrollRequest.run"
            >
              <p
                v-if="payrollProvisional"
                class="uv-callout uv-callout--warning"
                role="status"
              >
                <AlertTriangle class="inline size-3.5" aria-hidden="true" />
                暂算：{{ payrollReadNote || '存在未定价 / 未排班 / 质量未判清的报工，确认后金额会变化。' }}
              </p>

              <div class="uv-detail-grid">
                <div class="uv-field uv-field--emphasis">
                  <dt class="uv-field__label">分摊合计（全体参与员工）</dt>
                  <dd class="uv-field__value">
                    <UvNumber
                      v-if="payroll?.batch_total"
                      :money="payroll.batch_total"
                      size="lg"
                      align="left"
                      emphasis
                      :state="payrollState === 'confirmed' ? 'normal' : 'provisional'"
                    />
                    <UvNumber v-else :state="payrollState === 'unpriced' ? 'unpriced' : 'pending'" size="lg" align="left" emphasis />
                    <span class="uv-field__hint">
                      各员工分摊额之和与批次金额完全一致：余数按稳定员工顺序补最小币种单位（1.00 给三人 = 0.34 + 0.33 + 0.33）。
                    </span>
                  </dd>
                </div>
                <div class="uv-field">
                  <dt class="uv-field__label">待核报工</dt>
                  <dd class="uv-field__value">
                    未定价 {{ payroll?.unpriced_reports ?? 0 }} · 未排班 {{ payroll?.unassigned_reports ?? 0 }} ·
                    待核 {{ payroll?.quality_pending_reports ?? 0 }}
                    <span class="uv-field__hint">三类分别计数，不合并成一个「异常」数字。</span>
                  </dd>
                </div>
              </div>

              <ul v-if="payrollPending.length" class="uv-list" data-uv="payroll-pending">
                <li v-for="item in payrollPending" :key="item.key">
                  <AlertTriangle class="size-3.5" style="margin-top: 2px" aria-hidden="true" />
                  <span>
                    <strong>{{ item.label }}</strong> · {{ item.count }} 条：{{ item.reason }}
                  </span>
                </li>
              </ul>
              <p v-else class="uv-callout">
                <CheckCircle2 class="inline size-3.5" aria-hidden="true" />
                本范围没有未定价、未排班或质量未判清的报工，可以进入工资确认流程。
              </p>

              <div class="uv-matrix-scroll">
                <table class="uv-table uv-table--dense" data-uv="payroll-lines">
                  <caption class="uv-table-caption">按员工列出分摊结果；点击员工可查看工资构成与分摊依据。</caption>
                  <thead>
                    <tr>
                      <th scope="col">员工</th>
                      <th scope="col">计入报工</th>
                      <th scope="col">合格数</th>
                      <th scope="col">分摊金额</th>
                      <th scope="col">状态</th>
                      <th scope="col">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="row in payrollRows" :key="row.worker_id" :data-worker-id="row.worker_id">
                      <td>
                        <span class="uv-row-primary">{{ row.worker_name }}</span>
                        <span class="uv-row-sub">
                          {{ row.employee_no || '工号待登记' }}
                          <template v-if="row.worker?.employ_state === 'left'">
                            · 已离职（历史，离职日期 {{ row.worker.left_on ?? '未登记' }}）
                          </template>
                        </span>
                      </td>
                      <td class="uv-table-cell--right"><UvNumber :qty="row.report_count" unit="条" /></td>
                      <td class="uv-table-cell--right"><UvNumber :qty="row.good_qty" unit="件" /></td>
                      <td class="uv-table-cell--right">
                        <UvNumber
                          v-if="row.amount"
                          :money="row.amount"
                          :state="row.state === 'confirmed' ? 'normal' : 'provisional'"
                        />
                        <UvNumber v-else :state="row.state === 'unpriced' ? 'unpriced' : 'pending'" />
                        <span class="uv-row-sub">{{ row.allocation_basis }}</span>
                        <span v-if="row.remainder_adjusted" class="uv-chip">余数补足</span>
                      </td>
                      <td><UvStatusPill :status="PAYROLL_STATE[row.state]" compact /></td>
                      <td>
                        <Button variant="ghost" size="sm" type="button" @click="selectedWorkerId = row.worker_id">
                          <UserRound class="size-3.5" aria-hidden="true" />
                          工资构成
                        </Button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <p class="uv-callout">
                <Calculator class="inline size-3.5" aria-hidden="true" />
                离职员工的历史排班与工资快照照常保留并标注为历史；修改当前排班不会改写已确认的历史工资。
              </p>
            </UvStateBlock>
          </div>
        </section>
      </div>
    </UvStateBlock>

    <AssignmentEditorDrawer
      ref="editorRef"
      :open="editorOpen"
      :business-date="businessDate"
      :shift="editing?.shift ?? 'day'"
      :machine="editingMachine"
      :workers="workers"
      :templates="templates"
      :assigned-worker-ids="assignedWorkerIds"
      :machine-ids-by-worker="machineIdsByWorker"
      :previous-shift="previousShift"
      :can-write="canWriteShift"
      :busy="assignmentCommand.pending.value"
      :error-message="assignmentCommand.error.value?.message ?? ''"
      :copy-error="copyError"
      :copy-loading="copyLoading"
      @close="closeEditor"
      @save="saveAssignments"
      @copy-previous="copyPreviousShift"
    />

    <WorkerPayrollDrawer
      :open="selectedWorkerId !== null"
      :worker="selectedWorker"
      :business-date="businessDate"
      :date-from="payrollWindowFrom"
      :date-to="businessDate"
      :currency="currency"
      :line="selectedLine"
      :preview-total="payroll?.batch_total ?? null"
      :preview-state="payrollState"
      :rows="detailRows"
      :allocations="detailAllocations"
      :pending="payrollPending"
      :provisional="payrollProvisional"
      :can-read-payroll="payrollAllowed"
      @close="selectedWorkerId = null"
    />
  </div>
</template>
