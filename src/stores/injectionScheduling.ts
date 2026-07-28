import { defineStore } from 'pinia'
import { cloneHuaxingSchedulingSnapshot } from '@/data/injectionSchedulingMock'
import type { ProductionFactoryContextId } from '@/data/enterpriseMock'
import type {
  BacklogOrder,
  InjectionMachine,
  ScheduleMoveRequest,
  ScheduleTask,
  SchedulingFilters,
  SchedulingKpi,
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
  machineType: 'all',
  state: 'all',
  exceptionsOnly: false,
})

export const useInjectionSchedulingStore = defineStore('injection-scheduling', {
  state: () => ({
    factoryId: 'huaxing' as ProductionFactoryContextId,
    sourceLabel: '',
    snapshotAt: '',
    notice: '',
    kpis: [] as SchedulingKpi[],
    machines: [] as InjectionMachine[],
    tasks: [] as ScheduleTask[],
    backlog: [] as BacklogOrder[],
    viewMode: 'board' as SchedulingViewMode,
    filters: defaultFilters(),
    loading: true,
    selectedTaskId: '',
    selectedBacklogId: '',
    pendingMove: null as ScheduleMoveRequest | null,
    detailsExpanded: false,
    alertsOpen: false,
    rulesOpen: false,
    publishOpen: false,
    version: '草案 v0.1',
    toast: null as SchedulingToast | null,
    toastSequence: 0,
  }),
  getters: {
    selectedTask(state) {
      return state.tasks.find((task) => task.id === state.selectedTaskId) ?? null
    },
    selectedBacklog(state) {
      return state.backlog.find((order) => order.id === state.selectedBacklogId) ?? null
    },
    taskMap(state) {
      return new Map(state.tasks.map((task) => [task.id, task]))
    },
    visibleMachines(state): InjectionMachine[] {
      const search = state.filters.search.trim().toLocaleLowerCase()
      return state.machines.filter((machine) => {
        const machineTasks = state.tasks.filter((task) => task.machineId === machine.id)
        const matchesSearch = !search || [
          machine.name,
          machine.machineType,
          machine.tonnage,
          ...machineTasks.flatMap((task) => [task.moldNo, task.productName, task.orderNo]),
        ].some((value) => value.toLocaleLowerCase().includes(search))
        const matchesType = state.filters.machineType === 'all'
          || machine.machineType === state.filters.machineType
        const matchesState = state.filters.state === 'all' || machine.state === state.filters.state
        const matchesException = !state.filters.exceptionsOnly
          || machine.state === 'risk'
          || machine.state === 'urgent'
          || machineTasks.some((task) => task.risk === 'overdue' || task.risk === 'urgent')
        return matchesSearch && matchesType && matchesState && matchesException
      })
    },
    visibleBacklog(state): BacklogOrder[] {
      const search = state.filters.search.trim().toLocaleLowerCase()
      return state.backlog.filter((order) => (
        !search
        || [order.moldNo, order.productName, order.orderNo, order.color]
          .some((value) => value.toLocaleLowerCase().includes(search))
      ))
    },
    isHuaxingPreview(state) {
      return state.factoryId === 'huaxing'
    },
  },
  actions: {
    async load(factoryId: ProductionFactoryContextId) {
      this.loading = true
      this.factoryId = factoryId
      this.selectedTaskId = ''
      this.selectedBacklogId = ''
      this.pendingMove = null
      this.filters = defaultFilters()
      await new Promise((resolve) => window.setTimeout(resolve, 120))

      if (factoryId !== 'huaxing') {
        this.sourceLabel = ''
        this.snapshotAt = ''
        this.notice = ''
        this.kpis = []
        this.machines = []
        this.tasks = []
        this.backlog = []
        this.loading = false
        return
      }

      const snapshot = cloneHuaxingSchedulingSnapshot()
      this.sourceLabel = snapshot.sourceLabel
      this.snapshotAt = snapshot.snapshotAt
      this.notice = snapshot.notice
      this.kpis = snapshot.kpis
      this.machines = snapshot.machines
      this.tasks = snapshot.tasks
      this.backlog = snapshot.backlog
      this.loading = false
    },
    tasksForMachine(machineId: string) {
      return this.tasks
        .filter((task) => task.machineId === machineId)
        .sort((left, right) => left.sequence - right.sequence)
    },
    selectTask(taskId: string) {
      this.selectedTaskId = taskId
    },
    selectBacklog(backlogId: string) {
      this.selectedBacklogId = backlogId
      this.viewMode = 'backlog'
    },
    requestMove(request: ScheduleMoveRequest) {
      const task = request.taskId ? this.tasks.find((item) => item.id === request.taskId) : null
      if (task?.locked) {
        this.showToast('当前任务已锁定', '只能调整后续队列，正在生产的任务不能拖动。', 'amber')
        return
      }
      this.pendingMove = request
    },
    cancelMove() {
      this.pendingMove = null
    },
    confirmMove() {
      const move = this.pendingMove
      if (!move) return

      if (move.taskId) {
        const task = this.tasks.find((item) => item.id === move.taskId)
        if (!task) return
        const source = this.machines.find((machine) => machine.id === task.machineId)
        const target = this.machines.find((machine) => machine.id === move.targetMachineId)
        if (!target || source?.id === target.id) {
          this.pendingMove = null
          return
        }
        source!.taskIds = source!.taskIds.filter((id) => id !== task.id)
        target.taskIds.push(task.id)
        task.machineId = target.id
        task.sequence = target.taskIds.length
        this.showToast('排程草案已调整', `${task.moldNo} 已移至 ${target.name}，尚未发布。`, 'teal')
      }

      if (move.backlogId) {
        const order = this.backlog.find((item) => item.id === move.backlogId)
        const target = this.machines.find((machine) => machine.id === move.targetMachineId)
        if (!order || !target) return
        const taskId = `draft-${order.id}`
        target.taskIds.push(taskId)
        this.tasks.push({
          id: taskId,
          machineId: target.id,
          moldNo: order.moldNo,
          productName: order.productName,
          orderNo: order.orderNo,
          color: order.color,
          quantity: order.quantity,
          completedQuantity: 0,
          dailyTarget: order.dailyTarget,
          startAt: '待计算',
          endAt: order.requiredDate,
          dueLabel: '待后端校验',
          risk: order.urgency === 'urgent' ? 'urgent' : 'warning',
          sequence: target.taskIds.length,
          current: false,
          locked: false,
          remark: '由前端演示分配，正式排程须后端校验。',
        })
        this.backlog = this.backlog.filter((item) => item.id !== order.id)
        this.selectedBacklogId = ''
        this.showToast('订单已加入排程草案', `${order.moldNo} 已放入 ${target.name} 的后续队列。`, 'teal')
      }

      this.pendingMove = null
    },
    generateSuggestion() {
      this.version = '建议草案 v0.2'
      this.showToast('建议草案已生成', '仅按当前 Mock 约束重新排序，未执行正式排程算法。', 'teal')
    },
    publishPreview() {
      this.publishOpen = false
      this.showToast('发布功能尚未接入', '当前只能维护前端排程草案，未写入任何后端数据。', 'amber')
    },
    markRecalculate() {
      this.showToast('已标记需要重算', '待后端接入后，将重新计算日期与资格约束。', 'teal')
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
