import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { isAxiosError } from 'axios'
import {
  applyHeuristicPreview,
  createHeuristicPreview,
  evaluateWorkbenchMove,
  fetchWorkbench,
  moveWorkbenchJob,
  reportWorkbenchShift,
  saveWorkbenchChanges,
  withdrawWorkbenchJob,
} from './api'
import { workbenchColumnPresets } from './columns'
import type {
  SchedulePreview,
  ShiftReportInput,
  WorkbenchCellChange,
  WorkbenchColumnPreset,
  WorkbenchFactoryId,
  WorkbenchJob,
  WorkbenchJobStatus,
  WorkbenchSnapshot,
  WorkbenchView,
} from './types'

const factoryNames: Record<WorkbenchFactoryId, string> = {
  huaxing: '华兴',
  'huakang-a': '华康 A',
  'huakang-b': '华康 B',
  'huakang-c': '华康 C',
  'huakang-d': '华康 D',
  huadeng: '华登',
}

function errorMessage(error: unknown) {
  if (isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (detail && typeof detail === 'object' && 'message' in detail) return String(detail.message)
    return error.message
  }
  return error instanceof Error ? error.message : '操作失败'
}

function changeKey(change: WorkbenchCellChange) {
  return `${change.jobId}:${change.field}`
}

function optimisticValue(job: WorkbenchJob, change: WorkbenchCellChange) {
  if (change.field === 'status') job.status = change.value as WorkbenchJobStatus
  else if (change.field === 'shiftTargetQuantity') job.shiftTargetQuantity = Number(change.value)
  else if (change.field === 'locked') job.locked = Boolean(change.value)
  else job[change.field] = String(change.value)
}

export const useInjectionWorkbenchStore = defineStore('injection-scheduling-workbench', () => {
  let autoSaveTimer: ReturnType<typeof setTimeout> | null = null
  const factoryId = ref<WorkbenchFactoryId>('huaxing')
  const snapshot = ref<WorkbenchSnapshot | null>(null)
  const loading = ref(false)
  const saving = ref(false)
  const message = ref('')
  const error = ref('')
  const lastSavedAt = ref('')
  const view = ref<WorkbenchView>('sheet')
  const preset = ref<WorkbenchColumnPreset>('scheduler')
  const search = ref('')
  const statusFilter = ref<WorkbenchJobStatus | 'ALL'>('ALL')
  const machineFilter = ref('ALL')
  const selectedJobId = ref<string | null>(null)
  const pending = ref<Record<string, WorkbenchCellChange>>({})
  const schedulePreview = ref<SchedulePreview | null>(null)
  const scheduling = ref(false)

  const factoryName = computed(() => factoryNames[factoryId.value])
  const columns = computed(() => workbenchColumnPresets[preset.value])
  const pendingCount = computed(() => Object.keys(pending.value).length)
  const filteredJobs = computed(() => {
    const needle = search.value.trim().toLocaleLowerCase()
    return (snapshot.value?.jobs ?? []).filter((job) => {
      if (statusFilter.value !== 'ALL' && job.status !== statusFilter.value) return false
      if (machineFilter.value !== 'ALL' && (machineFilter.value === 'UNPLANNED' ? job.machineId !== null : job.machineId !== machineFilter.value)) return false
      if (!needle) return true
      return [job.machineCode, job.orderNo, job.itemNo, job.productName, job.moldNo, job.moldName, job.warehouseText]
        .join(' ').toLocaleLowerCase().includes(needle)
    })
  })
  const selectedJob = computed(() => snapshot.value?.jobs.find((job) => job.id === selectedJobId.value) ?? null)
  const jobsByMachine = computed(() => {
    const groups = new Map<string, WorkbenchJob[]>()
    for (const job of filteredJobs.value) {
      const key = job.machineId ?? 'UNPLANNED'
      const current = groups.get(key) ?? []
      current.push(job)
      groups.set(key, current)
    }
    return groups
  })

  async function load(options: { quiet?: boolean } = {}) {
    if (!options.quiet) loading.value = true
    error.value = ''
    try {
      snapshot.value = await fetchWorkbench(factoryId.value)
      lastSavedAt.value = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    } catch (cause) {
      error.value = errorMessage(cause)
    } finally {
      loading.value = false
    }
  }

  async function setFactory(value: WorkbenchFactoryId) {
    if (factoryId.value === value) return true
    if (pendingCount.value) await savePendingChanges()
    if (pendingCount.value) {
      error.value = error.value || '当前修改尚未保存，已保留在原厂区'
      return false
    }
    factoryId.value = value
    search.value = ''
    statusFilter.value = 'ALL'
    machineFilter.value = 'ALL'
    selectedJobId.value = null
    schedulePreview.value = null
    await load()
    return true
  }

  function stageChanges(changes: WorkbenchCellChange[]) {
    if (!snapshot.value || snapshot.value.planMode === 'EXECUTION') throw new Error('当前是执行快照，请先创建或接管为可编辑规划')
    const next = { ...pending.value }
    for (const change of changes) {
      const job = snapshot.value.jobs.find((item) => item.id === change.jobId)
      if (!job) continue
      optimisticValue(job, change)
      next[changeKey(change)] = change
    }
    pending.value = next
    message.value = `已暂存 ${pendingCount.value} 处修改`
    error.value = ''
    if (autoSaveTimer) clearTimeout(autoSaveTimer)
    autoSaveTimer = setTimeout(() => void savePendingChanges(), 600)
  }

  async function savePendingChanges() {
    if (saving.value || !snapshot.value || !pendingCount.value) return
    if (autoSaveTimer) clearTimeout(autoSaveTimer)
    autoSaveTimer = null
    saving.value = true
    error.value = ''
    const submitted = { ...pending.value }
    const changes = Object.values(submitted)
    try {
      const savedSnapshot = await saveWorkbenchChanges(factoryId.value, snapshot.value.planRevision, changes)
      const remaining = Object.fromEntries(
        Object.entries(pending.value).filter(([key, change]) => submitted[key] !== change),
      ) as Record<string, WorkbenchCellChange>
      for (const change of Object.values(remaining)) {
        const job = savedSnapshot.jobs.find((item) => item.id === change.jobId)
        if (!job) continue
        change.expectedTaskRevision = job.taskRevision
        change.expectedOrderRevision = job.orderRevision
        optimisticValue(job, change)
      }
      snapshot.value = savedSnapshot
      pending.value = remaining
      lastSavedAt.value = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
      message.value = pendingCount.value
        ? `已自动保存 ${changes.length} 处修改，另有 ${pendingCount.value} 处新修改待保存`
        : `已自动保存 ${changes.length} 处修改`
      if (pendingCount.value) autoSaveTimer = setTimeout(() => void savePendingChanges(), 600)
    } catch (cause) {
      error.value = errorMessage(cause)
      message.value = '自动保存未完成，修改仍保留在表格中'
    } finally {
      saving.value = false
    }
  }

  function discardPendingChanges() {
    pending.value = {}
    if (autoSaveTimer) clearTimeout(autoSaveTimer)
    autoSaveTimer = null
    void load({ quiet: true })
  }

  async function reportShift(job: WorkbenchJob, input: ShiftReportInput) {
    if (!snapshot.value) return false
    error.value = ''
    try {
      await reportWorkbenchShift(factoryId.value, snapshot.value.businessDate || new Date().toISOString().slice(0, 10), job, input)
      await load({ quiet: true })
      message.value = `已回报${input.shiftCode === 'DAY' ? '白班' : '夜班'} ${input.quantity.toLocaleString('zh-CN')} 件`
      return true
    } catch (cause) {
      error.value = errorMessage(cause)
      return false
    }
  }

  async function moveJob(job: WorkbenchJob, targetMachineId: string, targetSequence?: number) {
    if (!snapshot.value || snapshot.value.planMode !== 'PLANNING') return
    error.value = ''
    try {
      if (pendingCount.value) await savePendingChanges()
      let overrideReason = ''
      if (job.machineId !== targetMachineId) {
        const evaluation = await evaluateWorkbenchMove(factoryId.value, job, targetMachineId)
        const result = Array.isArray(evaluation.results) ? evaluation.results[0] as Record<string, unknown> | undefined : undefined
        const failures = Array.isArray(result?.hard_failures) ? result.hard_failures as Array<Record<string, unknown>> : []
        const warnings = Array.isArray(result?.warnings) ? result.warnings as Array<Record<string, unknown>> : []
        if (result?.decision === 'FAIL') throw new Error(failures.map((item) => String(item.detail ?? item.label ?? '')).filter(Boolean).join('；') || '机台硬约束不匹配')
        if (result?.decision === 'REVIEW_REQUIRED') {
          const warningText = warnings.map((item) => String(item.detail ?? item.label ?? '')).filter(Boolean).join('；')
          if (!window.confirm(`${warningText || '该移动需要人工确认'}\n\n是否继续？`)) return
          overrideReason = `调度员确认：${warningText || '机台适配警告'}`
        }
      }
      const queueLength = jobsByMachine.value.get(targetMachineId)?.length ?? 0
      const sequence = Math.max(0, Math.min(targetSequence ?? queueLength, queueLength))
      await moveWorkbenchJob(snapshot.value, job, targetMachineId, sequence, overrideReason)
      await load({ quiet: true })
      message.value = job.machineId === targetMachineId ? '已调整机台队列顺序' : '任务已移入目标机台队列'
    } catch (cause) {
      error.value = errorMessage(cause)
    }
  }

  async function withdrawJob(job: WorkbenchJob) {
    if (!snapshot.value) return
    const reason = window.prompt('请填写撤回待排池的原因：', '调度调整')?.trim()
    if (!reason) return
    try {
      await withdrawWorkbenchJob(snapshot.value, job, reason)
      await load({ quiet: true })
      message.value = '任务已撤回待排池'
    } catch (cause) {
      error.value = errorMessage(cause)
    }
  }

  async function previewSchedule() {
    if (!snapshot.value) return
    scheduling.value = true
    error.value = ''
    try {
      schedulePreview.value = await createHeuristicPreview(snapshot.value)
    } catch (cause) {
      error.value = errorMessage(cause)
    } finally {
      scheduling.value = false
    }
  }

  async function applySchedule() {
    if (!snapshot.value || !schedulePreview.value) return
    scheduling.value = true
    try {
      await applyHeuristicPreview(snapshot.value, schedulePreview.value)
      schedulePreview.value = null
      await load({ quiet: true })
      message.value = '已应用排期建议'
    } catch (cause) {
      error.value = errorMessage(cause)
    } finally {
      scheduling.value = false
    }
  }

  return {
    factoryId, factoryName, snapshot, loading, saving, message, error, lastSavedAt,
    view, preset, search, statusFilter, machineFilter, selectedJobId, pending,
    schedulePreview, scheduling, columns, pendingCount, filteredJobs, selectedJob,
    jobsByMachine, load, setFactory, stageChanges, savePendingChanges,
    discardPendingChanges, reportShift, moveJob, withdrawJob, previewSchedule, applySchedule,
  }
})
