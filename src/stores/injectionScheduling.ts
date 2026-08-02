import { computed, reactive, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  injectionSchedulingRepository,
  OptimisticConflictError,
} from '@/repositories/injectionSchedulingRepository'
import type { InjectionSchedulingImportBatchDto } from '@/api/injectionScheduling'
import type {
  BacklogOrder,
  InjectionFactoryId,
  InjectionMachine,
  InjectionSchedulingSnapshot,
  SchedulingTask,
  TaskReportDraft,
  WorkspaceDataQualityFilter,
  WorkspaceStatusFilter,
  WorkspaceView,
} from '@/types/injectionScheduling'

interface TaskGroup {
  machine: InjectionMachine
  tasks: SchedulingTask[]
}

interface ConflictState {
  taskId: string
  currentRevision: number
  message: string
}

export const useInjectionSchedulingStore = defineStore('injectionScheduling', () => {
  const factoryId = ref<InjectionFactoryId>('huaxing')
  const snapshot = ref<InjectionSchedulingSnapshot | null>(null)
  const loading = ref(false)
  const error = ref('')
  const search = ref('')
  const statusFilter = ref<WorkspaceStatusFilter>('all')
  const machineClass = ref('all')
  const armType = ref('all')
  const dataQuality = ref<WorkspaceDataQualityFilter>('all')
  const view = ref<WorkspaceView>('board')
  const collapsedMachines = reactive(new Set<string>())
  const reportDrafts = reactive<Record<string, TaskReportDraft>>({})
  const selectedTaskId = ref('')
  const selectedBacklogId = ref('backlog-gt')
  const detailTab = ref<'order' | 'fit' | 'report' | 'history'>('order')
  const detailDrawerOpen = ref(false)
  const backlogDrawerOpen = ref(false)
  const saving = ref(false)
  const toast = ref('')
  const conflict = ref<ConflictState | null>(null)
  const importDrawerOpen = ref(false)
  const importBatch = ref<InjectionSchedulingImportBatchDto | null>(null)
  const importFileName = ref('')
  const importBusinessDate = ref('')
  const importLoading = ref(false)
  const importError = ref('')
  const acknowledgedBlockingIssueIds = reactive(new Set<string>())
  const candidateLoading = ref(false)
  const candidateError = ref('')
  const candidateReasons = reactive<Record<string, string>>({})

  const machinesById = computed(() => new Map(
    (snapshot.value?.machines ?? []).map((entry) => [entry.id, entry]),
  ))

  const selectedTask = computed(() => snapshot.value?.tasks.find((entry) => entry.id === selectedTaskId.value) ?? null)
  const selectedMachine = computed(() => selectedTask.value ? machinesById.value.get(selectedTask.value.machineId) ?? null : null)
  const selectedBacklog = computed(() => snapshot.value?.backlogOrders.find((entry) => entry.id === selectedBacklogId.value) ?? null)
  const isDirty = computed(() => Object.keys(reportDrafts).length > 0)
  const canSubmitReports = computed(() => snapshot.value?.planStatus === 'PUBLISHED')
  const blockingImportIssues = computed(() => importBatch.value?.issues.filter((issue) => issue.blocking) ?? [])
  const allBlockingIssuesAcknowledged = computed(() => blockingImportIssues.value.every(
    (issue) => acknowledgedBlockingIssueIds.has(issue.id),
  ))

  const filteredGroups = computed<TaskGroup[]>(() => {
    const currentSnapshot = snapshot.value
    if (!currentSnapshot) return []
    const query = search.value.trim().toLocaleLowerCase()

    return currentSnapshot.machines.flatMap((machine) => {
      if (machineClass.value !== 'all' && machine.machineClass !== machineClass.value) return []
      if (armType.value !== 'all' && machine.armCapability !== armType.value) return []

      const tasks = currentSnapshot.tasks
        .filter((entry) => entry.machineId === machine.id)
        .filter((entry) => {
          if (statusFilter.value === 'running' && entry.status !== 'RUNNING') return false
          if (statusFilter.value === 'overdue' && !(entry.slackDays < 0 && entry.status !== 'DONE')) return false
          if (statusFilter.value === 'dueSoon' && !(entry.slackDays >= 0 && entry.slackDays <= 3 && entry.status !== 'DONE')) return false
          if (statusFilter.value === 'review' && entry.fitDecision !== 'REVIEW_REQUIRED') return false
          if (dataQuality.value === 'complete' && !entry.moldDimensions) return false
          if (dataQuality.value === 'missing' && entry.moldDimensions) return false
          if (!query) return true
          return [
            machine.code,
            machine.machineClass,
            entry.moldCode,
            entry.productName,
            entry.orderNo,
            entry.itemNo,
            entry.material,
            entry.color,
            entry.warehouseOwner,
            entry.note,
          ].some((value) => value.toLocaleLowerCase().includes(query))
        })
        .sort((left, right) => left.sequence - right.sequence)

      return tasks.length ? [{ machine, tasks }] : []
    })
  })

  const filteredTaskCount = computed(() => filteredGroups.value.reduce((total, group) => total + group.tasks.length, 0))
  const machineClasses = computed(() => Array.from(new Set((snapshot.value?.machines ?? []).map((entry) => entry.machineClass))))

  async function load(nextFactoryId: InjectionFactoryId) {
    const factoryChanged = nextFactoryId !== factoryId.value
    factoryId.value = nextFactoryId
    loading.value = true
    error.value = ''
    conflict.value = null
    try {
      snapshot.value = await injectionSchedulingRepository.getSnapshot(nextFactoryId)
      if (factoryChanged) resetImport()
      candidateError.value = ''
      for (const machineId of Object.keys(candidateReasons)) delete candidateReasons[machineId]
      if (!snapshot.value.backlogOrders.some((entry) => entry.id === selectedBacklogId.value)) {
        selectedBacklogId.value = snapshot.value.backlogOrders[0]?.id ?? ''
      }
      clearDrafts()
    } catch (loadError) {
      snapshot.value = null
      error.value = loadError instanceof Error ? loadError.message : '排程数据加载失败'
    } finally {
      loading.value = false
    }
  }

  function toggleMachine(machineId: string) {
    if (collapsedMachines.has(machineId)) collapsedMachines.delete(machineId)
    else collapsedMachines.add(machineId)
  }

  function openTask(taskId: string, tab: typeof detailTab.value = 'order') {
    selectedTaskId.value = taskId
    detailTab.value = tab
    detailDrawerOpen.value = true
  }

  async function openBacklog(backlogId?: string) {
    if (backlogId) selectedBacklogId.value = backlogId
    backlogDrawerOpen.value = true
    if (selectedBacklogId.value) await loadCandidates(selectedBacklogId.value)
  }

  async function loadCandidates(backlogId: string) {
    const currentSnapshot = snapshot.value
    if (!currentSnapshot) return
    candidateLoading.value = true
    candidateError.value = ''
    try {
      const refreshed = await injectionSchedulingRepository.evaluateBacklogOrder(factoryId.value, backlogId)
      const index = currentSnapshot.backlogOrders.findIndex((entry) => entry.id === backlogId)
      if (index >= 0) currentSnapshot.backlogOrders[index] = refreshed
      for (const machineId of Object.keys(candidateReasons)) delete candidateReasons[machineId]
    } catch (loadError) {
      candidateError.value = loadError instanceof Error ? loadError.message : '候选机台加载失败'
    } finally {
      candidateLoading.value = false
    }
  }

  function ensureDraft(taskEntry: SchedulingTask): TaskReportDraft {
    const existing = reportDrafts[taskEntry.id]
    if (existing) return existing
    const draft: TaskReportDraft = {
      taskId: taskEntry.id,
      expectedRevision: taskEntry.revision,
      shiftCompleted: taskEntry.shiftCompleted,
      cumulativeCompleted: taskEntry.completedQuantity,
      shiftTarget: taskEntry.shiftTarget,
      downtimeHours: taskEntry.downtimeHours,
      exceptionType: taskEntry.exceptionType,
      status: taskEntry.status,
      remark: taskEntry.note,
    }
    reportDrafts[taskEntry.id] = draft
    return draft
  }

  function updateShiftCompleted(taskEntry: SchedulingTask, value: number) {
    const draft = ensureDraft(taskEntry)
    const safeValue = Math.max(0, Math.round(Number.isFinite(value) ? value : 0))
    const delta = safeValue - taskEntry.shiftCompleted
    draft.shiftCompleted = safeValue
    draft.cumulativeCompleted = Math.max(0, Math.min(taskEntry.orderQuantity, taskEntry.completedQuantity + delta))
  }

  function updateDraft(taskEntry: SchedulingTask, patch: Partial<TaskReportDraft>) {
    Object.assign(ensureDraft(taskEntry), patch)
    const draft = reportDrafts[taskEntry.id]
    draft.shiftCompleted = Math.max(0, Math.round(draft.shiftCompleted))
    draft.cumulativeCompleted = Math.max(0, Math.min(taskEntry.orderQuantity, Math.round(draft.cumulativeCompleted)))
    draft.shiftTarget = Math.max(1, Math.round(draft.shiftTarget))
    draft.downtimeHours = Math.max(0, Number(draft.downtimeHours || 0))
  }

  function displayValues(taskEntry: SchedulingTask) {
    const draft = reportDrafts[taskEntry.id]
    const cumulativeCompleted = draft?.cumulativeCompleted ?? taskEntry.completedQuantity
    const shiftCompleted = draft?.shiftCompleted ?? taskEntry.shiftCompleted
    const shiftTarget = draft?.shiftTarget ?? taskEntry.shiftTarget
    const remaining = Math.max(0, taskEntry.orderQuantity - cumulativeCompleted)
    const progress = taskEntry.orderQuantity > 0 ? cumulativeCompleted / taskEntry.orderQuantity * 100 : 0
    const remainingShifts = remaining / Math.max(1, shiftTarget)
    return { cumulativeCompleted, shiftCompleted, shiftTarget, remaining, progress, remainingShifts }
  }

  async function saveDraft(taskId: string) {
    const taskEntry = snapshot.value?.tasks.find((entry) => entry.id === taskId)
    const draft = reportDrafts[taskId]
    if (!snapshot.value || !taskEntry || !draft) return
    if (!canSubmitReports.value) {
      error.value = '只有已发布计划可以提交生产回报；当前计划仍是草案或尚未建立。'
      return
    }

    saving.value = true
    error.value = ''
    conflict.value = null
    try {
      const result = await injectionSchedulingRepository.saveShiftReport(
        factoryId.value,
        taskId,
        draft.expectedRevision,
        draft,
      )
      const index = snapshot.value.tasks.findIndex((entry) => entry.id === taskId)
      snapshot.value.tasks[index] = result.task
      delete reportDrafts[taskId]
      toast.value = result.auditMessage
      window.setTimeout(() => { toast.value = '' }, 2800)
    } catch (saveError) {
      if (saveError instanceof OptimisticConflictError) {
        conflict.value = {
          taskId,
          currentRevision: saveError.currentRevision,
          message: '其他人员已更新这条任务。你的输入仍保留，请重新基于最新版本保存。',
        }
      } else {
        error.value = saveError instanceof Error ? saveError.message : '保存失败'
      }
    } finally {
      saving.value = false
    }
  }

  async function saveAllDrafts() {
    for (const taskId of Object.keys(reportDrafts)) {
      await saveDraft(taskId)
      if (conflict.value || error.value) break
    }
  }

  async function retryConflict() {
    const currentConflict = conflict.value
    if (!currentConflict) return
    const draft = reportDrafts[currentConflict.taskId]
    if (!draft) return
    draft.expectedRevision = currentConflict.currentRevision
    conflict.value = null
    await saveDraft(currentConflict.taskId)
  }

  async function simulateConflict(taskId: string) {
    await injectionSchedulingRepository.simulateExternalTaskUpdate(factoryId.value, taskId)
    toast.value = '已模拟另一位计划员更新；下次保存将触发版本冲突'
    window.setTimeout(() => { toast.value = '' }, 3200)
  }

  function resetImport() {
    importBatch.value = null
    importFileName.value = ''
    importBusinessDate.value = snapshot.value?.businessDate ?? new Date().toISOString().slice(0, 10)
    importError.value = ''
    acknowledgedBlockingIssueIds.clear()
  }

  function openImport() {
    resetImport()
    importDrawerOpen.value = true
  }

  async function previewImport(file: File) {
    if (!file.name.toLocaleLowerCase().endsWith('.xlsx')) {
      importError.value = '请选择 .xlsx 格式的注塑排产工作簿。'
      return
    }
    importLoading.value = true
    importError.value = ''
    importBatch.value = null
    importFileName.value = file.name
    acknowledgedBlockingIssueIds.clear()
    try {
      importBatch.value = await injectionSchedulingRepository.previewImport(factoryId.value, file)
      importBusinessDate.value = snapshot.value?.businessDate ?? new Date().toISOString().slice(0, 10)
    } catch (previewError) {
      importError.value = previewError instanceof Error ? previewError.message : 'Excel 导入预览失败'
    } finally {
      importLoading.value = false
    }
  }

  function toggleBlockingIssue(issueId: string, acknowledged: boolean) {
    if (acknowledged) acknowledgedBlockingIssueIds.add(issueId)
    else acknowledgedBlockingIssueIds.delete(issueId)
  }

  function toggleAllBlockingIssues(acknowledged: boolean) {
    acknowledgedBlockingIssueIds.clear()
    if (acknowledged) {
      for (const issue of blockingImportIssues.value) acknowledgedBlockingIssueIds.add(issue.id)
    }
  }

  async function confirmImport() {
    const batch = importBatch.value
    const currentSnapshot = snapshot.value
    if (!batch || !currentSnapshot || batch.status !== 'PREVIEW') return
    if (!allBlockingIssuesAcknowledged.value) {
      importError.value = '必须逐条确认全部阻断问题后才能正式导入。'
      return
    }
    importLoading.value = true
    importError.value = ''
    try {
      importBatch.value = await injectionSchedulingRepository.confirmImport(
        factoryId.value,
        batch,
        {
          businessDate: importBusinessDate.value,
          planStatus: currentSnapshot.planStatus,
          planRevision: currentSnapshot.planRevision,
          acknowledgedBlockingIssueIds: Array.from(acknowledgedBlockingIssueIds),
        },
      )
      toast.value = 'Excel 导入已确认，正式数据库计划已刷新'
      window.setTimeout(() => { toast.value = '' }, 3200)
      await load(factoryId.value)
    } catch (confirmError) {
      importError.value = confirmError instanceof Error ? confirmError.message : 'Excel 导入确认失败'
    } finally {
      importLoading.value = false
    }
  }

  async function assignBacklog(backlog: BacklogOrder, machineId: string, overrideReason = '') {
    saving.value = true
    error.value = ''
    candidateError.value = ''
    try {
      const result = await injectionSchedulingRepository.assignBacklogOrder(
        factoryId.value,
        backlog.id,
        machineId,
        backlog.revision,
        overrideReason,
      )
      toast.value = result.auditMessage
      window.setTimeout(() => { toast.value = '' }, 3000)
      backlogDrawerOpen.value = false
      await load(factoryId.value)
    } catch (assignError) {
      const message = assignError instanceof Error ? assignError.message : '确认候选机台失败'
      candidateError.value = message
      if (assignError instanceof OptimisticConflictError) {
        error.value = '计划或规则已被其他人员更新，请重新加载候选机台后再确认。'
      }
    } finally {
      saving.value = false
    }
  }

  function clearDrafts() {
    for (const taskId of Object.keys(reportDrafts)) delete reportDrafts[taskId]
  }

  function clearError() {
    error.value = ''
  }

  return {
    factoryId,
    snapshot,
    loading,
    error,
    search,
    statusFilter,
    machineClass,
    armType,
    dataQuality,
    view,
    collapsedMachines,
    reportDrafts,
    selectedTaskId,
    selectedBacklogId,
    detailTab,
    detailDrawerOpen,
    backlogDrawerOpen,
    saving,
    toast,
    conflict,
    importDrawerOpen,
    importBatch,
    importFileName,
    importBusinessDate,
    importLoading,
    importError,
    acknowledgedBlockingIssueIds,
    candidateLoading,
    candidateError,
    candidateReasons,
    filteredGroups,
    filteredTaskCount,
    machineClasses,
    selectedTask,
    selectedMachine,
    selectedBacklog,
    isDirty,
    canSubmitReports,
    blockingImportIssues,
    allBlockingIssuesAcknowledged,
    load,
    toggleMachine,
    openTask,
    openBacklog,
    loadCandidates,
    updateShiftCompleted,
    updateDraft,
    displayValues,
    saveDraft,
    saveAllDrafts,
    retryConflict,
    simulateConflict,
    assignBacklog,
    openImport,
    previewImport,
    toggleBlockingIssue,
    toggleAllBlockingIssues,
    confirmImport,
    resetImport,
    clearDrafts,
    clearError,
  }
})
