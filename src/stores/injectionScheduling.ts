import { defineStore } from 'pinia'
import { markRaw } from 'vue'
import {
  injectionSchedulingRepository,
  type InjectionSchedulingImportPreview,
  type InjectionSchedulingRepository,
} from '@/api/injectionScheduling'
import {
  calculateScheduleTiming,
  evaluateChangeover,
  evaluateMachineEligibility,
  optimizeSchedule,
} from '@/domain/injection-scheduling'
import { cloneSchedulingSnapshot } from '@/data/injectionSchedulingMock'
import type { ProductionFactoryContextId } from '@/data/enterpriseMock'
import { getApiErrorMessage } from '@/lib/http'
import type {
  BacklogOrder,
  InjectionMachine,
  MoveValidation,
  ProductionCalendar,
  ScheduleMoveRequest,
  SchedulePlanVersion,
  ScheduleFieldScheme,
  ScheduleTask,
  ScheduleWorksheetDetails,
  SchedulingDensity,
  SchedulingFilters,
  SchedulingKpi,
  SchedulingSimulationResult,
  SchedulingSnapshot,
  SchedulingViewMode,
} from '@/types/injectionScheduling'

interface SchedulingToast {
  id: number
  title: string
  detail: string
  tone: 'teal' | 'amber'
}

const defaultFilters = (): SchedulingFilters => ({
  search: '',
  machineClass: 'all',
  state: 'all',
  exceptionsOnly: false,
  incompleteOnly: false,
  idleOnly: false,
  taskScope: 'all',
  deliveryFrom: '',
  deliveryTo: '',
})

function emptyPlan(factoryId: ProductionFactoryContextId): SchedulePlanVersion {
  return {
    id: `${factoryId}-empty`,
    label: '未建立版本',
    revision: 0,
    rulesVersion: '待配置',
    status: 'draft',
    anchorAt: '2026-07-28T08:00:00+08:00',
  }
}

function emptyCalendar(): ProductionCalendar {
  return { timezone: 'Asia/Shanghai', availabilityWindows: [], downtimeWindows: [] }
}

function cloneSnapshot(snapshot: SchedulingSnapshot): SchedulingSnapshot {
  return JSON.parse(JSON.stringify(snapshot)) as SchedulingSnapshot
}

function normalizeWorksheet(value: ScheduleWorksheetDetails | null | undefined): ScheduleWorksheetDetails {
  return value && typeof value === 'object' ? value : {}
}

function isRevisionConflict(error: unknown) {
  return Boolean(
    error
    && typeof error === 'object'
    && 'response' in error
    && (error as { response?: { status?: number } }).response?.status === 409,
  )
}

function taskMatchesFilters(
  task: ScheduleTask,
  filters: SchedulingFilters,
  search: string,
  machineMatchesSearch: boolean,
) {
  if (filters.taskScope === 'current' && !task.current) return false
  if (filters.taskScope === 'future' && task.current) return false
  if (filters.incompleteOnly && task.risk !== 'incomplete') return false
  if (filters.exceptionsOnly && !['overdue', 'urgent', 'incomplete', 'warning'].includes(task.risk)) return false
  const deliveryDate = (task.worksheet.deliveryDueAt || task.timing.deliveryDueAt || '').slice(0, 10)
  if (filters.deliveryFrom && (!deliveryDate || deliveryDate < filters.deliveryFrom)) return false
  if (filters.deliveryTo && (!deliveryDate || deliveryDate > filters.deliveryTo)) return false
  if (!search || machineMatchesSearch) return true
  return [
    task.requirement.mold.moldNo,
    task.requirement.productName,
    task.requirement.orderNo,
    task.requirement.itemNo ?? '',
    task.requirement.color,
    task.requirement.material,
    task.worksheet.warehouse ?? '',
    task.worksheet.machineClassRequirement ?? '',
    task.worksheet.remark ?? '',
  ].some((value) => value.toLocaleLowerCase().includes(search))
}

export const useInjectionSchedulingStore = defineStore('injection-scheduling', {
  state: () => ({
    repository: markRaw(injectionSchedulingRepository) as InjectionSchedulingRepository,
    factoryId: 'huaxing' as ProductionFactoryContextId,
    sourceMode: 'empty' as 'backend' | 'mock' | 'empty',
    remoteError: '',
    sourceLabel: '',
    snapshotAt: '',
    notice: '',
    plan: emptyPlan('huaxing'),
    calendar: emptyCalendar(),
    kpis: [] as SchedulingKpi[],
    machines: [] as InjectionMachine[],
    tasks: [] as ScheduleTask[],
    backlog: [] as BacklogOrder[],
    draftSnapshots: {} as Partial<Record<ProductionFactoryContextId, SchedulingSnapshot>>,
    viewMode: 'spreadsheet' as SchedulingViewMode,
    density: 'compact' as SchedulingDensity,
    fieldScheme: 'full' as ScheduleFieldScheme,
    columnChooserOpen: false,
    bigScreen: false,
    workspaceBeforeBigScreen: null as SchedulingSnapshot | null,
    filters: defaultFilters(),
    loading: true,
    selectedTaskId: '',
    selectedMachineId: '',
    selectedBacklogId: '',
    pendingMove: null as ScheduleMoveRequest | null,
    pendingMoveValidation: null as MoveValidation | null,
    alertsOpen: false,
    rulesOpen: false,
    publishOpen: false,
    backlogOpen: false,
    optimizerOpen: false,
    importOpen: false,
    importBusy: false,
    importError: '',
    importPreview: null as InjectionSchedulingImportPreview | null,
    optimizationResult: null as SchedulingSimulationResult | null,
    toast: null as SchedulingToast | null,
    toastSequence: 0,
  }),
  getters: {
    selectedTask(state) {
      return state.tasks.find((task) => task.id === state.selectedTaskId) ?? null
    },
    selectedMachine(state) {
      return state.machines.find((machine) => machine.id === state.selectedMachineId) ?? null
    },
    selectedBacklog(state) {
      return state.backlog.find((order) => order.id === state.selectedBacklogId) ?? null
    },
    taskMap(state) {
      return new Map(state.tasks.map((task) => [task.id, task]))
    },
    tasksByMachine(state) {
      const result = new Map<string, ScheduleTask[]>()
      for (const machine of state.machines) result.set(machine.id, [])
      for (const task of state.tasks) {
        const bucket = result.get(task.machineId)
        if (bucket) bucket.push(task)
      }
      for (const bucket of result.values()) bucket.sort((left, right) => left.sequence - right.sequence)
      return result
    },
    visibleTasksByMachine(state) {
      const search = this.filters.search.trim().toLocaleLowerCase()
      const result = new Map<string, ScheduleTask[]>()
      for (const machine of state.machines) {
        const machineMatchesSearch = Boolean(search) && [
          machine.name,
          machine.code,
          machine.capability.machineClass,
          machine.kind,
          machine.restriction,
        ].some((value) => value.toLocaleLowerCase().includes(search))
        const machineTasks = this.tasksByMachine.get(machine.id) ?? []
        result.set(
          machine.id,
          machineTasks.filter((task) => taskMatchesFilters(
            task,
            state.filters,
            search,
            machineMatchesSearch,
          )),
        )
      }
      return result
    },
    visibleMachines(): InjectionMachine[] {
      const search = this.filters.search.trim().toLocaleLowerCase()
      return this.machines.filter((machine) => {
        const machineTasks = this.tasksByMachine.get(machine.id) ?? []
        const visibleTasks = this.visibleTasksByMachine.get(machine.id) ?? []
        const machineMatchesSearch = !search || [
          machine.name,
          machine.code,
          machine.capability.machineClass,
          machine.kind,
          machine.restriction,
        ].some((value) => value.toLocaleLowerCase().includes(search))
        const matchesType = this.filters.machineClass === 'all'
          || machine.capability.machineClass === this.filters.machineClass
        const matchesState = this.filters.state === 'all' || machine.state === this.filters.state
        const matchesIdle = !this.filters.idleOnly || machineTasks.length === 0
        const matchesException = !this.filters.exceptionsOnly
          || ['risk', 'urgent', 'fault', 'maintenance'].includes(machine.state)
          || visibleTasks.some((task) => ['overdue', 'urgent', 'incomplete', 'warning'].includes(task.risk))
        const hasTaskMatch = visibleTasks.length > 0
        const taskFiltersActive = this.filters.taskScope !== 'all'
          || this.filters.incompleteOnly
          || Boolean(this.filters.deliveryFrom)
          || Boolean(this.filters.deliveryTo)
        const matchesSearch = machineMatchesSearch || hasTaskMatch
        const matchesTaskFilters = !taskFiltersActive || machineTasks.length === 0 || hasTaskMatch
        return matchesSearch && matchesType && matchesState && matchesIdle && matchesException && matchesTaskFilters
      })
    },
    visibleBacklog(state): BacklogOrder[] {
      const search = state.filters.search.trim().toLocaleLowerCase()
      return state.backlog.filter((order) => (
        !search
        || [
          order.requirement.mold.moldNo,
          order.requirement.productName,
          order.requirement.orderNo,
          order.requirement.color,
          order.requirement.material,
          order.requirement.itemNo ?? '',
          order.worksheet.warehouse ?? '',
        ].some((value) => value.toLocaleLowerCase().includes(search))
      ))
    },
    hasPreviewData(state) {
      return Boolean(state.machines.length || state.tasks.length || state.backlog.length)
    },
    isHuaxingPreview(state) {
      return state.factoryId === 'huaxing'
    },
    isHuakangBPreview(state) {
      return state.factoryId === 'huakang-b'
    },
    supportsWorkbookImport(state) {
      return state.factoryId === 'huaxing' || state.factoryId === 'huakang-b'
    },
  },
  actions: {
    setRepository(repository: InjectionSchedulingRepository) {
      this.repository = markRaw(repository)
    },
    applySnapshot(snapshot: SchedulingSnapshot | null, factoryId: ProductionFactoryContextId) {
      this.factoryId = factoryId
      this.sourceLabel = snapshot?.sourceLabel ?? ''
      this.snapshotAt = snapshot?.snapshotAt ?? ''
      this.notice = snapshot?.notice ?? ''
      this.plan = snapshot?.plan ?? emptyPlan(factoryId)
      this.calendar = snapshot?.calendar ?? emptyCalendar()
      this.kpis = snapshot?.kpis ?? []
      this.machines = snapshot?.machines ?? []
      this.tasks = (snapshot?.tasks ?? []).map((task) => ({
        ...task,
        worksheet: normalizeWorksheet(task.worksheet),
      }))
      this.backlog = (snapshot?.backlog ?? []).map((order) => ({
        ...order,
        worksheet: normalizeWorksheet(order.worksheet),
      }))
    },
    currentSnapshot(): SchedulingSnapshot {
      return {
        factoryId: this.factoryId,
        sourceLabel: this.sourceLabel,
        snapshotAt: this.snapshotAt,
        notice: this.notice,
        plan: this.plan,
        calendar: this.calendar,
        kpis: this.kpis,
        machines: this.machines,
        tasks: this.tasks,
        backlog: this.backlog,
      }
    },
    async load(factoryId: ProductionFactoryContextId) {
      this.loading = true
      this.selectedTaskId = ''
      this.selectedMachineId = ''
      this.selectedBacklogId = ''
      this.pendingMove = null
      this.pendingMoveValidation = null
      this.backlogOpen = false
      this.optimizerOpen = false
      this.importOpen = false
      this.bigScreen = false
      this.workspaceBeforeBigScreen = null
      this.filters = defaultFilters()
      await new Promise((resolve) => window.setTimeout(resolve, 60))

      try {
        const remoteSnapshot = await this.repository.loadSnapshot(factoryId)
        if (remoteSnapshot) {
          this.sourceMode = 'backend'
          this.remoteError = ''
          delete this.draftSnapshots[factoryId]
          this.applySnapshot(remoteSnapshot, factoryId)
          return
        }

        const mockSnapshot = this.draftSnapshots[factoryId] ?? cloneSchedulingSnapshot(factoryId)
        if (mockSnapshot) {
          this.sourceMode = 'mock'
          this.remoteError = ''
          this.draftSnapshots[factoryId] = mockSnapshot
          this.applySnapshot({
            ...mockSnapshot,
            notice: '后端暂无该厂区正式快照，当前显示只读 Mock 演示数据。',
          }, factoryId)
        } else {
          this.sourceMode = 'empty'
          this.remoteError = ''
          this.applySnapshot(null, factoryId)
        }
      } catch (error) {
        const mockSnapshot = this.draftSnapshots[factoryId] ?? cloneSchedulingSnapshot(factoryId)
        this.remoteError = getApiErrorMessage(error)
        if (mockSnapshot) {
          this.sourceMode = 'mock'
          this.draftSnapshots[factoryId] = mockSnapshot
          this.applySnapshot({
            ...mockSnapshot,
            notice: `正式后端暂不可用，当前显示 Mock：${this.remoteError}`,
          }, factoryId)
        } else {
          this.sourceMode = 'empty'
          this.applySnapshot(null, factoryId)
        }
      } finally {
        this.loading = false
      }
    },
    tasksForMachine(machineId: string) {
      return this.tasksByMachine.get(machineId) ?? []
    },
    selectTask(taskId: string) {
      this.selectedTaskId = taskId
      this.selectedMachineId = ''
    },
    selectMachine(machineId: string) {
      this.selectedMachineId = machineId
      this.selectedTaskId = ''
    },
    selectBacklog(backlogId: string) {
      this.selectedBacklogId = backlogId
      this.selectedTaskId = ''
      this.selectedMachineId = ''
      this.backlogOpen = true
    },
    openBacklog() {
      this.selectedTaskId = ''
      this.selectedMachineId = ''
      this.backlogOpen = true
    },
    openImport() {
      this.importPreview = null
      this.importError = ''
      this.importOpen = true
    },
    closeImport() {
      if (this.importBusy) return
      this.importOpen = false
      this.importPreview = null
      this.importError = ''
    },
    async previewWorkbook(file: File, businessDate: string) {
      this.importBusy = true
      this.importError = ''
      try {
        this.importPreview = await this.repository.previewImport(
          this.factoryId,
          businessDate,
          file,
        )
      } catch (error) {
        this.importPreview = null
        this.importError = getApiErrorMessage(error)
      } finally {
        this.importBusy = false
      }
    },
    async confirmWorkbook(reason: string) {
      if (!this.importPreview?.summary.canConfirm) return
      this.importBusy = true
      this.importError = ''
      try {
        const snapshot = await this.repository.confirmImport(
          this.importPreview.batch_id,
          {
            factoryId: this.factoryId,
            previewRevision: this.importPreview.preview_revision,
            reason,
          },
        )
        this.sourceMode = 'backend'
        this.remoteError = ''
        delete this.draftSnapshots[this.factoryId]
        this.applySnapshot(snapshot, this.factoryId)
        this.importOpen = false
        this.importPreview = null
        this.showToast('工作簿已确认导入', `正式后端草案 r${snapshot.plan.revision} 已建立。`, 'teal')
      } catch (error) {
        this.importError = getApiErrorMessage(error)
      } finally {
        this.importBusy = false
      }
    },
    closeTransientLayers() {
      this.selectedTaskId = ''
      this.selectedMachineId = ''
      this.pendingMove = null
      this.pendingMoveValidation = null
      this.alertsOpen = false
      this.rulesOpen = false
      this.publishOpen = false
      this.backlogOpen = false
      this.optimizerOpen = false
      this.importOpen = false
    },
    async requestMove(request: Omit<ScheduleMoveRequest, 'factoryId' | 'revision'>) {
      const task = request.taskId ? this.tasks.find((item) => item.id === request.taskId) : null
      const order = request.backlogId ? this.backlog.find((item) => item.id === request.backlogId) : null
      if (task?.locked || task?.current) {
        this.showToast('当前任务已锁定', '只能调整后续队列，正在生产的任务不能拖动。', 'amber')
        return
      }

      const target = this.machines.find((machine) => machine.id === request.targetMachineId)
      const requirement = task?.requirement ?? order?.requirement
      if (!target || !requirement) return
      const eligibility = evaluateMachineEligibility({ machine: target, requirement })
      const sameLaneReorder = task?.machineId === target.id && request.targetIndex !== undefined
      const allowed = sameLaneReorder
        || (this.sourceMode === 'backend' ? eligibility.status !== 'ineligible' : eligibility.eligible)
      this.pendingMove = {
        ...request,
        factoryId: this.factoryId,
        revision: this.plan.revision,
      }
      this.pendingMoveValidation = {
        allowed,
        eligibility,
        reasons: allowed
          ? [
              '前端硬约束预检通过',
              this.sourceMode === 'backend' ? '等待后端复核厂区与版本' : '确认后只修改当前厂区浏览器草案',
            ]
          : eligibility.checks.filter((check) => !check.passed).map((check) => check.reason),
        affectedTaskCount: sameLaneReorder ? 2 : 1,
      }
      if (this.sourceMode !== 'backend' || !allowed) return
      this.pendingMoveValidation = {
        ...this.pendingMoveValidation,
        allowed: false,
        reasons: ['正在由后端复核厂区、revision 与锁定状态…'],
      }
      try {
        this.pendingMoveValidation = await this.repository.validateMove(this.pendingMove)
      } catch (error) {
        this.pendingMoveValidation = {
          allowed: false,
          eligibility,
          reasons: [
            isRevisionConflict(error)
              ? '草案版本冲突，请刷新当前厂区快照后重试'
              : getApiErrorMessage(error),
          ],
          affectedTaskCount: 0,
        }
      }
    },
    nudgeTask(taskId: string, direction: 'up' | 'down') {
      const task = this.tasks.find((item) => item.id === taskId)
      if (!task || task.locked) return
      const ordered = this.tasksForMachine(task.machineId)
      const index = ordered.findIndex((item) => item.id === taskId)
      const targetIndex = direction === 'up' ? index - 1 : index + 1
      if (targetIndex <= 0 || targetIndex >= ordered.length) return
      this.requestMove({
        taskId,
        sourceMachineId: task.machineId,
        targetMachineId: task.machineId,
        targetIndex,
      })
    },
    cancelMove() {
      this.pendingMove = null
      this.pendingMoveValidation = null
    },
    recalculateMachine(machineId: string) {
      const machine = this.machines.find((item) => item.id === machineId)
      if (!machine) return
      let anchorAt = this.plan.anchorAt
      let previous: ScheduleTask | null = null
      machine.taskIds.forEach((taskId, index) => {
        const task = this.tasks.find((item) => item.id === taskId)
        if (!task) return
        const changeover = evaluateChangeover(
          machine.capability.machineClass,
          previous?.requirement ?? null,
          task.requirement,
        )
        const timing = calculateScheduleTiming({
          anchorAt,
          changeoverHours: changeover.totalHours,
          productionDurationHours: task.production.productionDurationHours,
          deliveryDueAt: task.timing.deliveryDueAt,
          calendar: this.calendar,
        })
        task.sequence = index + 1
        task.changeover = changeover
        task.timing = timing
        task.risk = task.requirement.priorityCode === 'P0'
          ? 'urgent'
          : changeover.status === 'missing-rule'
            ? 'incomplete'
            : timing.slackHours < 0 ? 'overdue' : timing.slackHours < 36 ? 'warning' : 'normal'
        anchorAt = timing.plannedEnd
        previous = task
      })
    },
    async confirmMove() {
      const move = this.pendingMove
      if (!move || !this.pendingMoveValidation?.allowed) return
      const before = cloneSnapshot(this.currentSnapshot())
      const baseRevision = this.plan.revision

      if (move.taskId) {
        const task = this.tasks.find((item) => item.id === move.taskId)
        if (!task) return
        const source = this.machines.find((machine) => machine.id === task.machineId)
        const target = this.machines.find((machine) => machine.id === move.targetMachineId)
        if (!source || !target) return
        source.taskIds = source.taskIds.filter((id) => id !== task.id)
        const insertionIndex = Math.max(1, Math.min(move.targetIndex ?? target.taskIds.length, target.taskIds.length))
        target.taskIds.splice(insertionIndex, 0, task.id)
        task.machineId = target.id
        this.recalculateMachine(source.id)
        if (target.id !== source.id) this.recalculateMachine(target.id)
        this.showToast('排程草案已调整', `${task.requirement.mold.moldNo} 已移至 ${target.name}，尚未发布。`, 'teal')
      }

      if (move.backlogId) {
        const order = this.backlog.find((item) => item.id === move.backlogId)
        const target = this.machines.find((machine) => machine.id === move.targetMachineId)
        if (!order || !target) return
        const previous = target.taskIds.length
          ? this.tasks.find((task) => task.id === target.taskIds[target.taskIds.length - 1])
          : null
        const changeover = evaluateChangeover(
          target.capability.machineClass,
          previous?.requirement ?? null,
          order.requirement,
        )
        const timing = calculateScheduleTiming({
          anchorAt: previous?.timing.plannedEnd ?? this.plan.anchorAt,
          changeoverHours: changeover.totalHours,
          productionDurationHours: order.production.productionDurationHours,
          deliveryDueAt: order.requiredDate,
          calendar: this.calendar,
        })
        const taskId = `draft-${order.id}-${this.plan.revision + 1}`
        target.taskIds.push(taskId)
        this.tasks.push({
          id: taskId,
          machineId: target.id,
          requirement: order.requirement,
          production: order.production,
          timing,
          changeover,
          risk: order.requirement.priorityCode === 'P0' ? 'urgent' : timing.slackHours < 0 ? 'overdue' : 'warning',
          sequence: target.taskIds.length,
          current: false,
          locked: false,
          remark: '由前端候选机台流程加入草案；正式排程须由后端按相同 factoryId 与 revision 复核。',
          worksheet: normalizeWorksheet(order.worksheet),
        })
        this.backlog = this.backlog.filter((item) => item.id !== order.id)
        this.selectedBacklogId = ''
        this.backlogOpen = false
        this.showToast('订单已加入排程草案', `${order.requirement.mold.moldNo} 已放入 ${target.name} 的后续队列。`, 'teal')
      }

      this.plan.revision += 1
      this.plan.label = `草案 v${this.plan.revision}.0`
      this.pendingMove = null
      this.pendingMoveValidation = null
      if (this.sourceMode === 'mock') {
        this.draftSnapshots[this.factoryId] = cloneSnapshot(this.currentSnapshot())
        return
      }
      if (this.sourceMode !== 'backend') return
      try {
        const saved = await this.repository.saveDraft({
          factoryId: this.factoryId,
          revision: baseRevision,
          snapshot: cloneSnapshot(this.currentSnapshot()),
          reason: move.backlogId ? '将待排订单加入后续队列' : '人工调整后续任务队列',
        })
        this.plan.revision = saved.revision
        this.snapshotAt = saved.savedAt
        this.showToast('排程草案已保存', `后端已保存 r${saved.revision}，尚未发布。`, 'teal')
      } catch (error) {
        this.applySnapshot(before, this.factoryId)
        this.showToast(
          isRevisionConflict(error) ? '草案版本冲突' : '草案保存失败',
          isRevisionConflict(error) ? '已有其他人员更新排程，请刷新当前厂区快照后再调整。' : getApiErrorMessage(error),
          'amber',
        )
      }
    },
    generateSuggestion() {
      this.optimizationResult = optimizeSchedule(this.tasks, this.machines)
      this.optimizerOpen = true
    },
    async applySuggestion() {
      if (!this.optimizationResult) return
      const before = cloneSnapshot(this.currentSnapshot())
      const baseRevision = this.plan.revision
      for (const machine of this.machines) {
        const proposal = this.optimizationResult.proposedTaskOrderByMachine[machine.id]
        if (proposal) {
          machine.taskIds = [...proposal]
          this.recalculateMachine(machine.id)
        }
      }
      this.plan.revision += 1
      this.plan.label = `建议草案 v${this.plan.revision}.0`
      this.optimizerOpen = false
      if (this.sourceMode === 'mock') {
        this.draftSnapshots[this.factoryId] = cloneSnapshot(this.currentSnapshot())
        this.showToast('建议已应用到浏览器草案', '当前任务与人工锁定保持不动，尚未写入后端。', 'teal')
        return
      }
      if (this.sourceMode !== 'backend') return
      try {
        const saved = await this.repository.saveDraft({
          factoryId: this.factoryId,
          revision: baseRevision,
          snapshot: cloneSnapshot(this.currentSnapshot()),
          reason: '应用智能排程建议',
        })
        this.plan.revision = saved.revision
        this.snapshotAt = saved.savedAt
        this.showToast('排程建议已保存', `后端已保存 r${saved.revision}，尚未发布。`, 'teal')
      } catch (error) {
        this.applySnapshot(before, this.factoryId)
        this.showToast(
          isRevisionConflict(error) ? '草案版本冲突' : '建议保存失败',
          isRevisionConflict(error) ? '已有其他人员更新排程，请刷新当前厂区快照后再应用建议。' : getApiErrorMessage(error),
          'amber',
        )
      }
    },
    async enterPublishedBigScreen() {
      if (this.sourceMode !== 'backend') {
        this.showToast('大屏仅显示正式发布版本', '请先导入正式计划并完成发布。', 'amber')
        return false
      }
      try {
        const published = await this.repository.loadPublishedSnapshot(this.factoryId)
        if (!published) {
          this.showToast('尚无已发布版本', '大屏不会展示未发布草案，请先发布当前排程。', 'amber')
          return false
        }
        this.workspaceBeforeBigScreen = cloneSnapshot(this.currentSnapshot())
        this.applySnapshot(published, this.factoryId)
        this.bigScreen = true
        return true
      } catch (error) {
        this.showToast('无法进入大屏', getApiErrorMessage(error), 'amber')
        return false
      }
    },
    exitPublishedBigScreen() {
      const workspace = this.workspaceBeforeBigScreen
      this.bigScreen = false
      this.workspaceBeforeBigScreen = null
      if (workspace) this.applySnapshot(workspace, workspace.factoryId)
    },
    async publishPreview() {
      this.publishOpen = false
      if (this.sourceMode !== 'backend') {
        this.showToast('Mock 不可发布', '请先导入并确认该厂区的正式工作簿快照。', 'amber')
        return
      }
      try {
        const published = await this.repository.publishVersion({
          factoryId: this.factoryId,
          revision: this.plan.revision,
          reason: '发布当前注塑排程到生产大屏',
        })
        this.plan.status = 'published'
        this.plan.publishedAt = published.publishedAt
        this.showToast('排程已发布', `正式版本 ${published.version} 已生成。`, 'teal')
      } catch (error) {
        this.showToast('发布失败', getApiErrorMessage(error), 'amber')
      }
    },
    markRecalculate() {
      this.machines.forEach((machine) => this.recalculateMachine(machine.id))
      this.showToast('前端草案已按固定锚点重算', `使用 ${this.plan.anchorAt}，未读取浏览器当前时间。`, 'teal')
    },
    showToast(title: string, detail: string, tone: SchedulingToast['tone']) {
      this.toastSequence += 1
      this.toast = { id: this.toastSequence, title, detail, tone }
    },
    clearToast() {
      this.toast = null
    },
  },
})
