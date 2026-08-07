import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { isAxiosError } from 'axios'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import {
  applyAutoSchedulePreview,
  createAutoSchedulePreview,
  fetchCurrentSchedulingPlan,
  fetchEligibility,
  fetchIncrementalEvents,
  fetchPhase5Analytics,
  fetchSchedulingWorkspace,
  mapOrder,
  mapTask,
  moveScheduleTask,
  patchScheduleOrder,
  patchScheduleTask,
  rebuildPhase5SpeedModels,
  saveShiftReportsBulk,
} from '../api/injectionSchedulingV2Api'
import { schedulingColumns } from '../composables/useSchedulingColumns'
import { cellDraftKey, isOrderEdit, isPlanEdit, isReportEdit, normalizeCellValue, resolveReportedQuantity } from '../composables/useScheduleDraftEdits'
import { demoEvents, demoMachines, demoMolds, demoOrders, demoTasks } from '../data/demo'
import type {
  AutoScheduleRunRecord,
  AutoScheduleGenerationOptions,
  AuditEvent,
  CellDraft,
  ColumnPreset,
  EditableCellKey,
  FactoryId,
  MachineRecord,
  MoldRecord,
  MovePreview,
  OrderRecord,
  Phase5AnalyticsRecord,
  PlanSliceKey,
  RevisionConflict,
  ScheduleGridRow,
  ScheduleTaskRecord,
  SchedulingPlanRecord,
  ShiftReportDraft,
  WorkspaceView,
} from '../types'

interface ExplicitPlanSlice {
  plan: SchedulingPlanRecord | null
  orders: OrderRecord[]
  tasks: ScheduleTaskRecord[]
  selectedTaskId: string | null
  search: string
  statusFilter: string
  riskFilter: string
  cellDrafts: Record<string, CellDraft>
  timelineScrollLeft: number
  timelineZoom: number
}

const emptyPlanSlice = (): ExplicitPlanSlice => ({
  plan: null, orders: [], tasks: [], selectedTaskId: null, search: '', statusFilter: 'all', riskFilter: 'all',
  cellDrafts: {}, timelineScrollLeft: 0, timelineZoom: 1,
})

const factoryNames: Record<FactoryId, string> = {
  huaxing: '华兴', 'huakang-a': '华康 A', 'huakang-b': '华康 B', 'huakang-c': '华康 C', 'huakang-d': '华康 D', huadeng: '华登',
}
const readLineage = (order: OrderRecord | undefined, key: string, fallback: unknown = '—') => order?.lineage[key] ?? fallback
const gridValue = (order: OrderRecord | undefined, key: string, fallback: string | number = '—'): string | number => {
  const value = readLineage(order, key, fallback)
  return typeof value === 'string' || typeof value === 'number' ? value : fallback
}
const formatA = (value: number | null, raw: string) => value ? `${value}A${raw && !raw.includes(String(value)) ? ` · ${raw}` : ''}` : raw || '待复核'
const balancedScheduleOptions = (): AutoScheduleGenerationOptions => ({
  solver: 'CP_SAT', scenarioName: '方案 A · 综合平衡',
  objectiveWeights: { tardinessWeight: 100, transitionWeight: 2, classGapWeight: 1.5, loadBalanceWeight: 25, existingTaskMoveCost: 40 },
})

export const useInjectionSchedulingV2Store = defineStore('injection-scheduling-v2', () => {
  const authStore = useAuthStore()
  const factoryId = ref<FactoryId>('huaxing')
  const machines = ref<MachineRecord[]>([])
  const molds = ref<MoldRecord[]>([])
  const orders = ref<OrderRecord[]>([])
  const tasks = ref<ScheduleTaskRecord[]>([])
  const backlogRecords = ref<OrderRecord[]>([])
  const backlogOrderIds = ref<string[]>([])
  const events = ref<AuditEvent[]>([])
  const autoScheduleRuns = ref<AutoScheduleRunRecord[]>([])
  const autoScheduleRun = ref<AutoScheduleRunRecord | null>(null)
  const autoScheduleComparisonRuns = ref<AutoScheduleRunRecord[]>([])
  const autoScheduleLoading = ref(false)
  const autoScheduleError = ref('')
  const plan = ref<SchedulingPlanRecord | null>(null)
  const executionPlan = ref<SchedulingPlanRecord | null>(null)
  const planningPlan = ref<SchedulingPlanRecord | null>(null)
  const executionPublishedPlan = ref<ExplicitPlanSlice>(emptyPlanSlice())
  const planningDraftPlan = ref<ExplicitPlanSlice>(emptyPlanSlice())
  const activePlanSlice = ref<PlanSliceKey>('execution')
  const pollingRevision = ref(0)
  const sourceMode = ref<'live' | 'fallback'>('live')
  const sourceMessage = ref('正式数据库')
  const loading = ref(false)
  const refreshing = ref(false)
  const lastSyncedAt = ref('')
  const activeView = ref<WorkspaceView>('plan')
  const activePreset = ref<ColumnPreset>('planner')
  const search = ref('')
  const statusFilter = ref('all')
  const riskFilter = ref('all')
  const selectedTaskId = ref<string | null>(null)
  const inspectorTab = ref<'order' | 'eligibility' | 'report' | 'history'>('order')
  const backlogDockOpen = ref(true)
  const autoScheduleDialogOpen = ref(false)
  const columnMenuOpen = ref(false)
  const collapsedMachineIds = ref<string[]>([])
  const customVisibleColumns = ref<Record<string, boolean>>({})
  const columnWidths = ref<Record<string, number>>({})
  const columnOrder = ref(schedulingColumns.map((column) => String(column.key)))
  const sort = ref<{ key: string; desc: boolean } | null>(null)
  const cellDrafts = ref<Record<string, CellDraft>>({})
  const savingEdits = ref(false)
  const saveMessage = ref('')
  const revisionConflict = ref<RevisionConflict | null>(null)
  const movePreview = ref<MovePreview | null>(null)
  const moveLoading = ref(false)
  const pollingEvents = ref(false)
  const phase5Analytics = ref<Phase5AnalyticsRecord | null>(null)
  const phase5AnalyticsLoading = ref(false)
  const phase5AnalyticsError = ref('')

  const schedulingDepartments = ['production', 'molding', 'pmc-warehouse', 'warehouse', 'management']
  const hasScopedPermission = (permission: string) => schedulingDepartments.some((department) => authStore.can(permission, factoryId.value, department))
  const canEdit = computed(() => sourceMode.value === 'live' && activePlanSlice.value === 'planning' && plan.value?.status === 'DRAFT' && hasScopedPermission('injection_scheduling:edit'))
  const canReport = computed(() => sourceMode.value === 'live' && activePlanSlice.value === 'execution' && plan.value?.status === 'PUBLISHED' && hasScopedPermission('injection_scheduling:report'))
  const canOverride = computed(() => sourceMode.value === 'live' && hasScopedPermission('injection_scheduling:publish'))
  const canManageRules = computed(() => sourceMode.value === 'live' && hasScopedPermission('injection_scheduling:manage_rules'))
  const canImport = computed(() => sourceMode.value === 'live' && hasScopedPermission('injection_scheduling:import'))
  const canExport = computed(() => sourceMode.value === 'live' && hasScopedPermission('injection_scheduling:export'))
  const canManageMaster = computed(() => sourceMode.value === 'live' && hasScopedPermission('injection_scheduling:manage_master'))
  const pendingEditCount = computed(() => Object.keys(cellDrafts.value).length)
  const timelineScrollLeft = computed({
    get: () => (activePlanSlice.value === 'execution' ? executionPublishedPlan.value : planningDraftPlan.value).timelineScrollLeft,
    set: (value: number) => {
      const target = activePlanSlice.value === 'execution' ? executionPublishedPlan : planningDraftPlan
      target.value = { ...target.value, timelineScrollLeft: value }
    },
  })
  const timelineZoom = computed({
    get: () => (activePlanSlice.value === 'execution' ? executionPublishedPlan.value : planningDraftPlan.value).timelineZoom,
    set: (value: number) => {
      const target = activePlanSlice.value === 'execution' ? executionPublishedPlan : planningDraftPlan
      target.value = { ...target.value, timelineZoom: Math.max(.5, Math.min(3, value)) }
    },
  })

  const factoryName = computed(() => factoryNames[factoryId.value])
  const orderMap = computed(() => new Map(orders.value.map((item) => [item.id, item])))
  const moldMap = computed(() => new Map(molds.value.map((item) => [item.id, item])))
  const machineMap = computed(() => new Map(machines.value.map((item) => [item.id, item])))
  const taskMap = computed(() => new Map(tasks.value.map((item) => [item.id, item])))
  const selectedTask = computed(() => selectedTaskId.value ? taskMap.value.get(selectedTaskId.value) ?? null : null)
  const selectedOrder = computed(() => selectedTask.value ? orderMap.value.get(selectedTask.value.orderId) ?? null : null)
  const selectedMold = computed(() => selectedTask.value?.moldId ? moldMap.value.get(selectedTask.value.moldId) ?? null : null)
  const selectedMachine = computed(() => selectedTask.value ? machineMap.value.get(selectedTask.value.machineId) ?? null : null)
  const backlogOrders = computed(() => backlogOrderIds.value.map((id) => orderMap.value.get(id)).filter((item): item is OrderRecord => Boolean(item)))

  const visibleColumns = computed(() => columnOrder.value
    .map((key) => schedulingColumns.find((column) => column.key === key))
    .filter((column): column is typeof schedulingColumns[number] => Boolean(column))
    .filter((column) => customVisibleColumns.value[String(column.key)] ?? column.presets.includes(activePreset.value)))

  const summary = computed(() => {
    const overdue = tasks.value.filter((task) => (orderMap.value.get(task.orderId)?.deliverySlackDays ?? 0) < 0).length
    const dueSoon = tasks.value.filter((task) => {
      const slack = orderMap.value.get(task.orderId)?.deliverySlackDays
      return slack != null && slack >= 0 && slack <= 3
    }).length
    const remaining = orders.value.reduce((total, order) => total + order.outstandingQuantity, 0)
    const completeMolds = molds.value.filter((mold) => mold.normalizationStatus === 'COMPLETE').length
    return {
      availableMachines: machines.value.filter((machine) => !['maintenance', 'offline'].includes(machine.status)).length,
      totalMachines: machines.value.length,
      scheduledTasks: tasks.value.length,
      runningTasks: tasks.value.filter((task) => task.status === 'RUNNING').length,
      overdue, dueSoon, remaining,
      completeness: molds.value.length ? completeMolds / molds.value.length * 100 : 0,
      backlog: backlogOrders.value.length,
      review: molds.value.filter((mold) => mold.normalizationStatus === 'REVIEW_REQUIRED').length,
    }
  })

  const alerts = computed(() => [
    { tone: 'danger', title: `${summary.value.overdue} 条计划已超期`, description: '交期差小于 0，建议优先检查锁定任务与当前生产队列。' },
    { tone: 'warning', title: `${summary.value.review} 套模具数据待复核`, description: '原始安数或结构化资格数据不完整；人工移动前必须复核，不会静默放行。' },
    { tone: 'warning', title: `${machines.value.filter((m) => ['maintenance', 'offline'].includes(m.status)).length} 台机停机或维修`, description: '机台状态会进入资格判断和后续 Phase 3 排期输入。' },
    { tone: 'info', title: '适配口径已切换为 V2', description: '默认只采用安数、射胶量、机械手、夹具、工艺限制和机台状态。' },
  ])

  function toGridRow(machine: MachineRecord, task: ScheduleTaskRecord): ScheduleGridRow {
    const order = orderMap.value.get(task.orderId)
    const mold = task.moldId ? moldMap.value.get(task.moldId) : undefined
    const fit = mold?.normalizationStatus === 'REVIEW_REQUIRED' || machine.normalizationStatus === 'REVIEW_REQUIRED' ? 'REVIEW_REQUIRED' : 'PASS'
    const completed = order?.completedQuantity ?? 0
    const total = order?.orderQuantity ?? 0
    return {
      rowType: 'task', id: task.id, machine, task, order, mold, status: task.status, sequence: task.sequence,
      position: machine.position, machineCode: machine.code, automation: readLineage(order, 'automation', '全自动') as string,
      marker: task.locked ? '锁定' : String(readLineage(order, 'marker', '')), moldA: mold ? formatA(mold.aClass, mold.aClassRaw) : '待补充',
      moldNo: mold?.moldNo ?? '未关联', productName: order?.productName ?? '', orderNo: order?.orderNo ?? '', itemNo: order?.itemNo ?? '',
      setQuantity: gridValue(order, 'set_quantity'), orderQuantity: total, completedQuantity: completed,
      outstandingQuantity: order?.outstandingQuantity ?? 0, progress: total ? Math.round(completed / total * 100) : 0,
      targetQuantity: task.targetQuantity, shiftCompleted: task.reportedQuantity, sprueRatio: String(readLineage(order, 'sprue_ratio')),
      color: mold?.colorProfile || String(readLineage(order, 'color')), powder: String(readLineage(order, 'powder')),
      material: mold?.materialName || String(readLineage(order, 'material')), netWeightG: mold?.netWeightG ?? '—', grossWeightG: mold?.grossWeightG ?? '—',
      materialKg: gridValue(order, 'material_kg'), unitPrice: gridValue(order, 'unit_price'), outsourcePrice: gridValue(order, 'outsource_price'),
      ratio: String(readLineage(order, 'ratio')), orderDate: String(readLineage(order, 'order_date')), deliveryStart: order?.deliveryStartDate || '—',
      deliveryDue: order?.deliveryDueDate || '—', moldChangeRef: String(readLineage(order, 'mold_change_ref', '0.6h')),
      colorChangeRef: String(readLineage(order, 'color_change_ref', '0.4h')), setupTime: String(readLineage(order, 'setup_time', '0h')),
      downtime: readLineage(order, 'downtime_minutes', 0) as number, exception: String(readLineage(order, 'exception_code', '')),
      plannedStart: task.plannedStart, plannedFinish: task.plannedFinish,
      planMonth: task.plannedFinish ? task.plannedFinish.slice(0, 7) : '—', warehouseDate: String(readLineage(order, 'warehouse_date')),
      slack: order?.deliverySlackDays ?? '—', spray: String(readLineage(order, 'spray', '否')), productionDays: gridValue(order, 'production_days'),
      shiftEnd: String(readLineage(order, 'shift_end', task.plannedFinish.slice(11, 16) || '—')), duration: String(readLineage(order, 'duration', '—')),
      shiftPlan: task.targetQuantity, machineA: formatA(machine.aClass, machine.aClassRaw), shotCapacity: machine.injectionCapacityG ?? '—', fit,
      warehouse: order?.warehouseText ?? '', remark: order?.remark ?? '', shipDate: String(readLineage(order, 'ship_date')),
      arm: mold?.requiredArmType || '待补充', fixture: mold?.requiredFixtureType || '待补充', priority: order?.priorityCode ?? 'NORMAL',
      materialReadiness: order?.materialReadinessStatus ?? 'unknown',
    }
  }

  const gridRows = computed(() => {
    const query = search.value.trim().toLowerCase()
    const result: ScheduleGridRow[] = []
    for (const machine of machines.value) {
      let machineTasks = tasks.value.filter((task) => task.machineId === machine.id).map((task) => toGridRow(machine, task))
      machineTasks = machineTasks.filter((row) => {
        if (statusFilter.value !== 'all' && row.status !== statusFilter.value) return false
        if (riskFilter.value === 'overdue' && !(Number(row.slack) < 0)) return false
        if (riskFilter.value === 'soon' && !(Number(row.slack) >= 0 && Number(row.slack) <= 3)) return false
        if (riskFilter.value === 'review' && row.fit !== 'REVIEW_REQUIRED') return false
        if (!query) return true
        return [row.machineCode, row.moldNo, row.productName, row.orderNo, row.itemNo, row.material, row.warehouse].join(' ').toLowerCase().includes(query)
      })
      machineTasks.sort((a, b) => {
        if (a.status === 'RUNNING' && b.status !== 'RUNNING') return -1
        if (b.status === 'RUNNING' && a.status !== 'RUNNING') return 1
        if (!sort.value) return Number(a.sequence) - Number(b.sequence)
        const { key, desc } = sort.value
        return String(a[key as keyof ScheduleGridRow] ?? '').localeCompare(String(b[key as keyof ScheduleGridRow] ?? ''), 'zh-CN', { numeric: true }) * (desc ? -1 : 1)
      })
      if (!machineTasks.length && (query || statusFilter.value !== 'all' || riskFilter.value !== 'all')) continue
      result.push({ ...toGridRow(machine, machineTasks[0]?.task ?? ({ id: '', planId: '', machineId: machine.id, orderId: '', moldId: null, sequence: 0, status: 'QUEUED', plannedStart: '', plannedFinish: '', targetQuantity: 0, reportedQuantity: 0, sourceSheetName: '', sourceRow: null, locked: false, manualOverrideReason: '', activeExecution: false, estimatedStart: '', estimatedFinish: '', estimatedRemainingShifts: 0, deliverySlackDays: null, revision: 0 })), rowType: 'machine', id: `machine:${machine.id}` })
      if (!collapsedMachineIds.value.includes(machine.id)) result.push(...machineTasks)
    }
    return result
  })

  function syncActivePlanSlice() {
    const target = activePlanSlice.value === 'execution' ? executionPublishedPlan : planningDraftPlan
    target.value = {
      ...target.value,
      plan: plan.value,
      orders: orders.value.filter((item) => !backlogOrderIds.value.includes(item.id)),
      tasks: [...tasks.value],
      selectedTaskId: selectedTaskId.value,
      search: search.value,
      statusFilter: statusFilter.value,
      riskFilter: riskFilter.value,
      cellDrafts: { ...cellDrafts.value },
    }
  }

  function activatePlanSlice(targetKey: PlanSliceKey, force = false) {
    if (!force && targetKey !== activePlanSlice.value && pendingEditCount.value) {
      saveMessage.value = '当前规划切片有未保存修改，请先保存或放弃后再切换。'
      return false
    }
    if (!force) syncActivePlanSlice()
    activePlanSlice.value = targetKey
    const target = targetKey === 'execution' ? executionPublishedPlan.value : planningDraftPlan.value
    plan.value = target.plan
    const merged = new Map<string, OrderRecord>()
    ;[...target.orders, ...backlogRecords.value].forEach((item) => merged.set(item.id, item))
    orders.value = [...merged.values()]
    tasks.value = [...target.tasks]
    selectedTaskId.value = target.selectedTaskId && target.tasks.some((item) => item.id === target.selectedTaskId)
      ? target.selectedTaskId
      : target.tasks[0]?.id ?? null
    search.value = target.search
    statusFilter.value = target.statusFilter
    riskFilter.value = target.riskFilter
    cellDrafts.value = { ...target.cellDrafts }
    revisionConflict.value = null
    return true
  }

  function applyData(data: Awaited<ReturnType<typeof fetchSchedulingWorkspace>>) {
    machines.value = data.machines; molds.value = data.molds
    backlogOrderIds.value = data.backlogOrderIds; events.value = data.events; pollingRevision.value = data.pollingRevision
    executionPlan.value = data.executionPlan; planningPlan.value = data.planningPlan
    backlogRecords.value = data.backlogOrders
    executionPublishedPlan.value = {
      ...executionPublishedPlan.value,
      plan: data.executionPlan,
      orders: data.executionOrders,
      tasks: data.executionTasks,
    }
    planningDraftPlan.value = {
      ...planningDraftPlan.value,
      plan: data.planningPlan,
      orders: data.planningOrders,
      tasks: data.planningTasks,
    }
    const target: PlanSliceKey = activePlanSlice.value === 'execution' && !data.executionPlan && data.planningPlan ? 'planning' : activePlanSlice.value
    activatePlanSlice(target, true)
    autoScheduleRuns.value = data.autoScheduleRuns
    if (autoScheduleRun.value) autoScheduleRun.value = data.autoScheduleRuns.find((item) => item.id === autoScheduleRun.value?.id) ?? autoScheduleRun.value
    if (autoScheduleRun.value) autoScheduleComparisonRuns.value = data.autoScheduleRuns.filter((item) => item.scenarioGroupId === autoScheduleRun.value?.scenarioGroupId)
  }

  function applyFallback(reason: string) {
    machines.value = demoMachines; molds.value = demoMolds; orders.value = demoOrders; tasks.value = demoTasks
    backlogRecords.value = demoOrders.filter((order) => order.status === 'BACKLOG')
    backlogOrderIds.value = demoOrders.filter((order) => order.status === 'BACKLOG').map((order) => order.id)
    events.value = demoEvents; plan.value = { id: 'DEMO-PLAN', status: 'PUBLISHED', revision: 7, ruleRevision: 1, businessDate: '2026-08-04', basedOnPlanId: '', basedOnEventSequence: 0, basedOnReportWatermark: 0 }; pollingRevision.value = 4
    executionPlan.value = plan.value; planningPlan.value = null
    executionPublishedPlan.value = { ...emptyPlanSlice(), plan: plan.value, orders: demoOrders, tasks: demoTasks, selectedTaskId: demoTasks[0]?.id ?? null }
    planningDraftPlan.value = emptyPlanSlice(); activePlanSlice.value = 'execution'
    autoScheduleRuns.value = []; autoScheduleRun.value = null; autoScheduleComparisonRuns.value = []; autoScheduleError.value = ''
    sourceMode.value = 'fallback'; sourceMessage.value = `后端暂不可用，当前显示只读演示数据 · ${reason}`; selectedTaskId.value = demoTasks[0]?.id ?? null
  }

  async function load(options: { quiet?: boolean } = {}) {
    options.quiet ? refreshing.value = true : loading.value = true
    try {
      applyData(await fetchSchedulingWorkspace(factoryId.value))
      sourceMode.value = 'live'; sourceMessage.value = '正式数据库'; lastSyncedAt.value = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    } catch (error) {
      if (!options.quiet || sourceMode.value !== 'fallback') applyFallback(error instanceof Error ? error.message : '网络错误')
    } finally {
      loading.value = false; refreshing.value = false
    }
  }

  async function loadPhase5Analytics() {
    if (sourceMode.value !== 'live' || phase5AnalyticsLoading.value) return
    phase5AnalyticsLoading.value = true
    phase5AnalyticsError.value = ''
    try {
      phase5Analytics.value = await fetchPhase5Analytics(factoryId.value)
    } catch (error) {
      phase5AnalyticsError.value = `运营分析读取失败：${getApiErrorMessage(error)}`
    } finally {
      phase5AnalyticsLoading.value = false
    }
  }

  async function calibratePhase5SpeedModels() {
    if (!canManageRules.value || phase5AnalyticsLoading.value) return
    phase5AnalyticsLoading.value = true
    phase5AnalyticsError.value = ''
    try {
      phase5Analytics.value = await rebuildPhase5SpeedModels(factoryId.value)
      saveMessage.value = '速度模型已根据历史周期重新校准'
    } catch (error) {
      phase5AnalyticsError.value = `速度模型校准失败：${getApiErrorMessage(error)}`
    } finally {
      phase5AnalyticsLoading.value = false
    }
  }

  function mergeTask(task: ScheduleTaskRecord) {
    const index = tasks.value.findIndex((item) => item.id === task.id)
    if (index >= 0) tasks.value.splice(index, 1, task)
    else tasks.value.push(task)
    syncActivePlanSlice()
  }

  function mergeOrder(order: OrderRecord) {
    const index = orders.value.findIndex((item) => item.id === order.id)
    if (index >= 0) orders.value.splice(index, 1, order)
    else orders.value.push(order)
    if (order.status === 'BACKLOG' && !backlogOrderIds.value.includes(order.id)) backlogOrderIds.value.push(order.id)
    if (order.status !== 'BACKLOG') backlogOrderIds.value = backlogOrderIds.value.filter((id) => id !== order.id)
    syncActivePlanSlice()
  }

  function mergePlanResult(data: { plan: SchedulingPlanRecord | null; tasks: ScheduleTaskRecord[]; orders: OrderRecord[] }) {
    if (data.plan) {
      plan.value = data.plan
      if (data.plan.status === 'DRAFT') planningPlan.value = data.plan
      if (data.plan.status === 'PUBLISHED') executionPlan.value = data.plan
    }
    tasks.value = data.tasks
    data.orders.forEach(mergeOrder)
    syncActivePlanSlice()
  }

  function draftValue(taskId: string, key: EditableCellKey, fallback: string | number) {
    return cellDrafts.value[cellDraftKey(taskId, key)]?.value ?? fallback
  }

  function stageCellEdit(taskId: string, key: EditableCellKey, rawValue: string | number) {
    const task = taskMap.value.get(taskId)
    const row = gridRows.value.find((item) => item.id === taskId)
    if (!task || !row || !plan.value || sourceMode.value !== 'live') return
    const allowed = isOrderEdit(key)
      ? canEdit.value
      : isPlanEdit(key, plan.value.status)
        ? canEdit.value
        : isReportEdit(key, plan.value.status) && canReport.value && task.activeExecution
    if (!allowed) {
      saveMessage.value = plan.value.status === 'DRAFT' ? '当前账号没有计划编辑权限' : '当前任务不可回报或账号没有回报权限'
      return
    }
    const value = normalizeCellValue(key, rawValue)
    const originalValue = row[key] as string | number
    const keyValue = cellDraftKey(taskId, key)
    if (String(value) === String(originalValue)) {
      const next = { ...cellDrafts.value }
      delete next[keyValue]
      cellDrafts.value = next
      return
    }
    cellDrafts.value = {
      ...cellDrafts.value,
      [keyValue]: { taskId, orderId: task.orderId, key, value, originalValue },
    }
    saveMessage.value = `${pendingEditCount.value} 个修改待保存`
  }

  function clearDrafts(drafts: CellDraft[]) {
    const next = { ...cellDrafts.value }
    drafts.forEach((draft) => delete next[cellDraftKey(draft.taskId, draft.key)])
    cellDrafts.value = next
  }

  async function refreshPlanForConflict() {
    const latest = await fetchCurrentSchedulingPlan(factoryId.value)
    mergePlanResult(latest)
    executionPlan.value = latest.executionPlan
    planningPlan.value = latest.planningPlan
    pollingRevision.value = Math.max(pollingRevision.value, latest.pollingRevision)
  }

  async function savePendingEdits() {
    if (!plan.value || !pendingEditCount.value || savingEdits.value) return
    savingEdits.value = true
    revisionConflict.value = null
    const pending = Object.values(cellDrafts.value)
    const localValues = Object.fromEntries(pending.map((draft) => [`${draft.taskId}.${draft.key}`, draft.value]))
    try {
      const planDrafts = pending.filter((draft) => isPlanEdit(draft.key, plan.value!.status))
      const taskGroups = new Map<string, CellDraft[]>()
      planDrafts.forEach((draft) => taskGroups.set(draft.taskId, [...(taskGroups.get(draft.taskId) ?? []), draft]))
      for (const [taskId, drafts] of taskGroups) {
        const task = taskMap.value.get(taskId)
        if (!task || !plan.value) continue
        const changes: Record<string, unknown> = {}
        drafts.forEach((draft) => {
          if (draft.key === 'status') changes.execution_status = draft.value
          if (draft.key === 'targetQuantity') changes.shift_target_quantity = draft.value
          if (draft.key === 'plannedStart') changes.planned_start = draft.value
          if (draft.key === 'plannedFinish') changes.planned_finish = draft.value
        })
        mergePlanResult(await patchScheduleTask(factoryId.value, plan.value, task, changes))
        clearDrafts(drafts)
      }

      const orderDrafts = pending.filter((draft) => isOrderEdit(draft.key))
      const orderGroups = new Map<string, CellDraft[]>()
      orderDrafts.forEach((draft) => orderGroups.set(draft.orderId, [...(orderGroups.get(draft.orderId) ?? []), draft]))
      for (const [orderId, drafts] of orderGroups) {
        const order = orderMap.value.get(orderId)
        if (!order) continue
        const changes: { warehouse_text?: string; remark?: string } = {}
        drafts.forEach((draft) => {
          if (draft.key === 'warehouse') changes.warehouse_text = String(draft.value)
          if (draft.key === 'remark') changes.remark = String(draft.value)
        })
        mergeOrder(await patchScheduleOrder(factoryId.value, order, changes))
        clearDrafts(drafts)
      }

      const reportDrafts = pending.filter((draft) => isReportEdit(draft.key, plan.value!.status))
      const reportGroups = new Map<string, CellDraft[]>()
      reportDrafts.forEach((draft) => reportGroups.set(draft.taskId, [...(reportGroups.get(draft.taskId) ?? []), draft]))
      const reports: ShiftReportDraft[] = []
      for (const [taskId, drafts] of reportGroups) {
        const task = taskMap.value.get(taskId)
        const order = task ? orderMap.value.get(task.orderId) : undefined
        if (!task || !order || !task.activeExecution) continue
        const value = (key: EditableCellKey) => drafts.find((draft) => draft.key === key)?.value
        const reportedQuantity = resolveReportedQuantity(drafts, task.reportedQuantity, order.sourceCompletedQuantity)
        const statusValue = String(value('status') ?? task.status)
        reports.push({
          taskId,
          expectedRevision: task.revision,
          reportedQuantity,
          shiftTargetQuantity: Number(value('targetQuantity') ?? task.targetQuantity),
          downtimeMinutes: Number(value('downtime') ?? 0),
          exceptionCode: String(value('exception') ?? ''),
          exceptionDetail: '',
          reportedStatus: (['QUEUED', 'RUNNING', 'BLOCKED', 'COMPLETED'].includes(statusValue) ? statusValue : 'RUNNING') as ShiftReportDraft['reportedStatus'],
        })
      }
      if (reports.length) {
        const saved = await saveShiftReportsBulk(factoryId.value, plan.value.businessDate, reports)
        saved.results.forEach((result) => { mergeTask(result.task); mergeOrder(result.order) })
        pollingRevision.value = Math.max(pollingRevision.value, saved.latestSequence)
        clearDrafts(reportDrafts)
      }
      saveMessage.value = '所有修改已由服务器确认保存'
      lastSyncedAt.value = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    } catch (error) {
      if (isAxiosError(error) && error.response?.status === 409) {
        const detail = error.response.data?.detail as { message?: string; diff?: Record<string, unknown> } | string | undefined
        await refreshPlanForConflict()
        revisionConflict.value = {
          title: '检测到 revision 冲突',
          message: typeof detail === 'string' ? detail : detail?.message ?? '服务器数据已被其他人更新，请对比后重新应用。',
          localValues,
          serverValues: typeof detail === 'object' ? detail.diff ?? {} : {},
          retry: async () => { revisionConflict.value = null; await savePendingEdits() },
        }
        saveMessage.value = '保存已暂停：请处理 revision 冲突'
      } else {
        saveMessage.value = `保存失败：${getApiErrorMessage(error)}`
      }
    } finally {
      savingEdits.value = false
    }
  }

  function discardPendingEdits() {
    cellDrafts.value = {}
    revisionConflict.value = null
    saveMessage.value = '已采用服务器数据'
  }

  function addDays(dateText: string, days: number) {
    const [year, month, day] = dateText.split('-').map(Number)
    const value = new Date(Date.UTC(year!, month! - 1, day! + days))
    return value.toISOString().slice(0, 10)
  }

  function scheduleHorizon() {
    const baseDate = plan.value?.businessDate || new Date().toISOString().slice(0, 10)
    return [`${baseDate}T08:00:00+08:00`, `${addDays(baseDate, 14)}T20:00:00+08:00`] as const
  }

  function rememberAutoScheduleRun(run: AutoScheduleRunRecord) {
    autoScheduleRun.value = run
    autoScheduleRuns.value = [run, ...autoScheduleRuns.value.filter((item) => item.id !== run.id)]
    autoScheduleComparisonRuns.value = autoScheduleRuns.value.filter((item) => item.scenarioGroupId === run.scenarioGroupId)
  }

  async function generateAutoSchedulePreview(options: AutoScheduleGenerationOptions = balancedScheduleOptions()) {
    if (!plan.value || plan.value.status !== 'DRAFT' || !canEdit.value || autoScheduleLoading.value) return
    if (pendingEditCount.value) {
      autoScheduleError.value = '请先保存或放弃当前单元格修改，再生成自动排期预览。'
      return
    }
    autoScheduleLoading.value = true
    autoScheduleError.value = ''
    try {
      const [horizonStart, horizonEnd] = scheduleHorizon()
      const run = await createAutoSchedulePreview(
        factoryId.value,
        plan.value,
        horizonStart,
        horizonEnd,
        options,
      )
      rememberAutoScheduleRun(run)
    } catch (error) {
      autoScheduleError.value = `自动排期预览生成失败：${getApiErrorMessage(error)}`
    } finally {
      autoScheduleLoading.value = false
    }
  }

  async function generateAutoScheduleAlternatives() {
    if (!plan.value || plan.value.status !== 'DRAFT' || !canEdit.value || autoScheduleLoading.value) return
    if (pendingEditCount.value) {
      autoScheduleError.value = '请先保存或放弃当前单元格修改，再生成多方案。'
      return
    }
    autoScheduleLoading.value = true
    autoScheduleError.value = ''
    const groupId = `isscenario-ui-${Date.now()}-${Math.random().toString(16).slice(2)}`
    const alternatives: AutoScheduleGenerationOptions[] = [
      { ...balancedScheduleOptions(), scenarioGroupId: groupId, alternativeNo: 1 },
      { solver: 'CP_SAT', scenarioGroupId: groupId, scenarioName: '方案 B · 交期优先', alternativeNo: 2, objectiveWeights: { tardinessWeight: 220, transitionWeight: 1, classGapWeight: 1, loadBalanceWeight: 10, existingTaskMoveCost: 30 } },
      { solver: 'CP_SAT', scenarioGroupId: groupId, scenarioName: '方案 C · 少换模均衡', alternativeNo: 3, objectiveWeights: { tardinessWeight: 80, transitionWeight: 8, classGapWeight: 2, loadBalanceWeight: 60, existingTaskMoveCost: 60 } },
    ]
    try {
      const [horizonStart, horizonEnd] = scheduleHorizon()
      const generated: AutoScheduleRunRecord[] = []
      for (const option of alternatives) {
        generated.push(await createAutoSchedulePreview(factoryId.value, plan.value, horizonStart, horizonEnd, option))
      }
      generated.forEach((run) => {
        autoScheduleRuns.value = [run, ...autoScheduleRuns.value.filter((item) => item.id !== run.id)]
      })
      autoScheduleComparisonRuns.value = generated
      autoScheduleRun.value = generated[0] ?? null
    } catch (error) {
      autoScheduleError.value = `多方案生成失败：${getApiErrorMessage(error)}`
    } finally {
      autoScheduleLoading.value = false
    }
  }

  async function replayAutoScheduleRun(run: AutoScheduleRunRecord) {
    await generateAutoSchedulePreview({
      solver: run.requestedSolver,
      scenarioGroupId: run.scenarioGroupId,
      scenarioName: `${run.scenarioName} · 回放`,
      alternativeNo: run.alternativeNo,
      replayOfRunId: run.id,
      objectiveWeights: { ...run.objectiveWeights },
    })
  }

  function selectAutoScheduleRun(run: AutoScheduleRunRecord) {
    autoScheduleRun.value = run
    autoScheduleComparisonRuns.value = autoScheduleRuns.value.filter((item) => item.scenarioGroupId === run.scenarioGroupId)
  }

  async function applyAutoScheduleRun(reviewOverrideReason: string) {
    if (!plan.value || !autoScheduleRun.value || autoScheduleLoading.value) return
    autoScheduleLoading.value = true
    autoScheduleError.value = ''
    try {
      const result = await applyAutoSchedulePreview(
        factoryId.value,
        plan.value,
        autoScheduleRun.value,
        reviewOverrideReason.trim(),
      )
      autoScheduleRun.value = result.run
      autoScheduleRuns.value = [result.run, ...autoScheduleRuns.value.filter((item) => item.id !== result.run.id)]
      mergePlanResult(result)
      pollingRevision.value = Math.max(pollingRevision.value, result.auditSequence)
      saveMessage.value = `自动方案已应用 · 计划 r${result.plan?.revision ?? plan.value?.revision}`
      await load({ quiet: true })
    } catch (error) {
      autoScheduleError.value = `自动方案应用失败：${getApiErrorMessage(error)}`
    } finally {
      autoScheduleLoading.value = false
    }
  }

  async function prepareMove(taskId: string, targetMachineId: string, targetSequence: number) {
    const task = taskMap.value.get(taskId)
    if (!task || !plan.value || plan.value.status !== 'DRAFT' || !canEdit.value) {
      saveMessage.value = '只有可编辑草案中的未锁定任务可以人工移动'
      return
    }
    if (task.locked || task.activeExecution || task.status === 'RUNNING') {
      saveMessage.value = '运行中或已锁定任务不能移动'
      return
    }
    moveLoading.value = true
    try {
      const evaluation = await fetchEligibility(factoryId.value, task.orderId, [targetMachineId], true)
      const results = Array.isArray(evaluation.results) ? evaluation.results as Array<Record<string, unknown>> : []
      const match = results[0]
      if (!match) throw new Error('目标机台没有返回资格结果')
      const reasons = (value: unknown) => Array.isArray(value) ? value.map((item) => ({
        label: String((item as Record<string, unknown>).label ?? ''),
        detail: String((item as Record<string, unknown>).detail ?? ''),
      })) : []
      const decision = String(match.decision) as MovePreview['decision']
      movePreview.value = {
        taskId,
        targetMachineId,
        targetSequence,
        plannedStart: task.plannedStart,
        plannedFinish: task.plannedFinish,
        decision,
        explanation: String(match.explanation ?? ''),
        hardFailures: reasons(match.hard_failures),
        warnings: reasons(match.warnings),
        setupReview: task.machineId === targetMachineId ? '同机重排：复核前后任务的换模与转色变化' : '跨机移动：复核两台机相邻任务的换模与转色变化',
        overrideReason: '',
      }
    } catch (error) {
      saveMessage.value = `资格评估失败：${getApiErrorMessage(error)}`
    } finally {
      moveLoading.value = false
    }
  }

  function updateMovePreview(changes: Partial<MovePreview>) {
    if (movePreview.value) movePreview.value = { ...movePreview.value, ...changes }
  }

  async function confirmMove() {
    const preview = movePreview.value
    const task = preview ? taskMap.value.get(preview.taskId) : undefined
    if (!preview || !task || !plan.value || moveLoading.value) return
    if (preview.decision === 'FAIL') return
    if (preview.decision === 'REVIEW_REQUIRED' && (!canOverride.value || !preview.overrideReason.trim())) {
      saveMessage.value = '待复核移动需要覆盖权限并填写原因'
      return
    }
    moveLoading.value = true
    try {
      const result = await moveScheduleTask(factoryId.value, plan.value, task, {
        machineId: preview.targetMachineId,
        sequence: preview.targetSequence,
        plannedStart: preview.plannedStart,
        plannedFinish: preview.plannedFinish,
        overrideReason: preview.overrideReason.trim(),
      })
      mergePlanResult(result)
      pollingRevision.value = Math.max(pollingRevision.value, result.auditSequence)
      movePreview.value = null
      saveMessage.value = '人工移动已通过资格复核并保存'
    } catch (error) {
      const detail = isAxiosError(error) ? error.response?.data?.detail as Record<string, unknown> | string | undefined : undefined
      if (typeof detail === 'object' && detail.match && typeof detail.match === 'object') {
        const match = detail.match as Record<string, unknown>
        updateMovePreview({ decision: String(match.decision) as MovePreview['decision'], explanation: String(match.explanation ?? '') })
      }
      if (isAxiosError(error) && error.response?.status === 409 && typeof detail === 'object' && detail.current_revision) {
        await refreshPlanForConflict()
        revisionConflict.value = {
          title: '移动未保存：计划版本已变化',
          message: String(detail.message ?? '请对比最新队列后重新应用移动。'),
          localValues: { machineId: preview.targetMachineId, sequence: preview.targetSequence, plannedStart: preview.plannedStart, plannedFinish: preview.plannedFinish },
          serverValues: (detail.diff as Record<string, unknown> | undefined) ?? {},
          retry: async () => { revisionConflict.value = null; await prepareMove(preview.taskId, preview.targetMachineId, preview.targetSequence) },
        }
      }
      saveMessage.value = `移动失败：${getApiErrorMessage(error)}`
    } finally {
      moveLoading.value = false
    }
  }

  function moveByKeyboard(taskId: string, direction: 'up' | 'down' | 'previous-machine' | 'next-machine') {
    const task = taskMap.value.get(taskId)
    if (!task) return
    if (direction === 'up' || direction === 'down') {
      const queue = tasks.value.filter((item) => item.machineId === task.machineId).sort((a, b) => a.sequence - b.sequence)
      const index = queue.findIndex((item) => item.id === taskId)
      const target = Math.max(0, Math.min(queue.length - 1, index + (direction === 'up' ? -1 : 1)))
      if (target !== index) void prepareMove(taskId, task.machineId, target)
      return
    }
    const machineIndex = machines.value.findIndex((machine) => machine.id === task.machineId)
    const targetIndex = machineIndex + (direction === 'previous-machine' ? -1 : 1)
    const machine = machines.value[targetIndex]
    if (!machine) return
    const queueLength = tasks.value.filter((item) => item.machineId === machine.id).length
    void prepareMove(taskId, machine.id, queueLength)
  }

  async function pollEvents() {
    if (sourceMode.value !== 'live' || pollingEvents.value) return
    pollingEvents.value = true
    try {
      const response = await fetchIncrementalEvents(factoryId.value, pollingRevision.value)
      let needsPlanRefresh = false
      for (const event of response.events) {
        const detail = event.detail
        const taskSnapshots = [detail.task, ...(Array.isArray(detail.tasks) ? detail.tasks : [])]
          .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && typeof (item as Record<string, unknown>).id === 'string' && Boolean((item as Record<string, unknown>).id))
        const orderSnapshots = [detail.order]
          .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && typeof (item as Record<string, unknown>).id === 'string' && Boolean((item as Record<string, unknown>).id))
        taskSnapshots.forEach((snapshot) => mergeTask(mapTask(snapshot)))
        orderSnapshots.forEach((snapshot) => mergeOrder(mapOrder(snapshot)))
        if (typeof detail.plan_revision === 'number' && plan.value) plan.value = { ...plan.value, revision: detail.plan_revision }
        if (!taskSnapshots.length && !orderSnapshots.length && (['task', 'order', 'plan'].includes(event.entityType) || event.eventType === 'import_confirmed')) needsPlanRefresh = true
        if (Object.values(cellDrafts.value).some((draft) => draft.taskId === event.entityId || draft.orderId === event.entityId)) {
          saveMessage.value = '检测到其他用户更新了正在编辑的实体；本地草稿未覆盖，请保存时处理 revision 对比。'
        }
      }
      if (needsPlanRefresh) {
        const latest = await fetchCurrentSchedulingPlan(factoryId.value)
        mergePlanResult(latest)
        executionPlan.value = latest.executionPlan
        planningPlan.value = latest.planningPlan
      }
      const merged = new Map(events.value.map((event) => [event.id, event]))
      response.events.forEach((event) => merged.set(event.id, event))
      events.value = [...merged.values()].sort((a, b) => b.sequence - a.sequence).slice(0, 200)
      pollingRevision.value = Math.max(pollingRevision.value, response.latestSequence)
      if (response.events.length) lastSyncedAt.value = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    } catch (error) {
      saveMessage.value = `增量同步暂时失败：${getApiErrorMessage(error)}`
    } finally {
      pollingEvents.value = false
    }
  }

  function setFactory(value: string) {
    if (!(value in factoryNames)) return false
    if (pendingEditCount.value) {
      saveMessage.value = '存在未保存的规划修改，切换厂区前请先保存或放弃。'
      return false
    }
    factoryId.value = value as FactoryId
    cellDrafts.value = {}
    revisionConflict.value = null
    movePreview.value = null
    autoScheduleRun.value = null
    autoScheduleComparisonRuns.value = []
    autoScheduleRuns.value = []
    autoScheduleError.value = ''
    saveMessage.value = ''
    phase5Analytics.value = null
    phase5AnalyticsError.value = ''
    executionPublishedPlan.value = emptyPlanSlice()
    planningDraftPlan.value = emptyPlanSlice()
    activePlanSlice.value = 'execution'
    return true
  }
  function setPreset(preset: ColumnPreset) { activePreset.value = preset; customVisibleColumns.value = {} }
  function toggleMachine(machineId: string) { collapsedMachineIds.value = collapsedMachineIds.value.includes(machineId) ? collapsedMachineIds.value.filter((id) => id !== machineId) : [...collapsedMachineIds.value, machineId] }
  function toggleColumn(key: string) { customVisibleColumns.value = { ...customVisibleColumns.value, [key]: !(customVisibleColumns.value[key] ?? visibleColumns.value.some((column) => column.key === key)) } }
  function moveColumn(key: string, direction: -1 | 1) {
    const currentIndex = columnOrder.value.indexOf(key)
    const targetIndex = currentIndex + direction
    if (currentIndex < 0 || targetIndex < 0 || targetIndex >= columnOrder.value.length) return
    const next = [...columnOrder.value]
    ;[next[currentIndex], next[targetIndex]] = [next[targetIndex]!, next[currentIndex]!]
    columnOrder.value = next
  }
  function resetColumns() { customVisibleColumns.value = {}; columnWidths.value = {}; columnOrder.value = schedulingColumns.map((column) => String(column.key)) }
  function selectTask(taskId: string) { selectedTaskId.value = taskId }
  function cycleSort(key: string) { sort.value = sort.value?.key === key ? (sort.value.desc ? null : { key, desc: true }) : { key, desc: false } }

  return { factoryId, factoryName, machines, molds, orders, tasks, backlogOrders, events, autoScheduleRuns, autoScheduleRun, autoScheduleComparisonRuns, autoScheduleLoading, autoScheduleError, plan, executionPlan, planningPlan, executionPublishedPlan, planningDraftPlan, activePlanSlice, pollingRevision, sourceMode, sourceMessage, loading, refreshing, lastSyncedAt,
    activeView, activePreset, search, statusFilter, riskFilter, selectedTaskId, selectedTask, selectedOrder, selectedMold, selectedMachine, inspectorTab,
    backlogDockOpen, autoScheduleDialogOpen, columnMenuOpen, collapsedMachineIds, customVisibleColumns, columnWidths, columnOrder, sort, visibleColumns, summary, alerts, gridRows,
    cellDrafts, pendingEditCount, timelineScrollLeft, timelineZoom, savingEdits, saveMessage, revisionConflict, movePreview, moveLoading, pollingEvents, canEdit, canReport, canOverride, canManageRules, canImport, canExport, canManageMaster,
    phase5Analytics, phase5AnalyticsLoading, phase5AnalyticsError,
    load, setFactory, activatePlanSlice, setPreset, toggleMachine, toggleColumn, moveColumn, resetColumns, selectTask, cycleSort,
    draftValue, stageCellEdit, savePendingEdits, discardPendingEdits, prepareMove, updateMovePreview, confirmMove, moveByKeyboard, pollEvents,
    generateAutoSchedulePreview, generateAutoScheduleAlternatives, replayAutoScheduleRun, selectAutoScheduleRun, applyAutoScheduleRun,
    loadPhase5Analytics, calibratePhase5SpeedModels }
})
