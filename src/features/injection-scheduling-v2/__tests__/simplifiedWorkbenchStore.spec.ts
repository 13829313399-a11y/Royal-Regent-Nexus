import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { WorkbenchJob, WorkbenchSnapshot } from '../workbench/types'

const apiMocks = vi.hoisted(() => ({
  applyHeuristicPreview: vi.fn(), createHeuristicPreview: vi.fn(), evaluateWorkbenchMove: vi.fn(),
  fetchWorkbench: vi.fn(), moveWorkbenchJob: vi.fn(), reportWorkbenchShift: vi.fn(),
  saveWorkbenchChanges: vi.fn(), withdrawWorkbenchJob: vi.fn(),
}))
vi.mock('../workbench/api', () => apiMocks)

import { useInjectionWorkbenchStore } from '../workbench/store'

function job(): WorkbenchJob {
  return {
    id: 'task-1', factoryId: 'huaxing', planId: 'plan-1', taskId: 'task-1', orderId: 'order-1',
    machineId: 'machine-1', machineCode: '12A-01', sequenceNo: 0, status: 'PLANNED', orderNo: 'SO-1',
    itemNo: '000001', productName: '脱敏产品', warehouseText: '', setQuantity: null, orderQuantity: 100,
    openingCompletedQuantity: 0, reportedQuantity: 0, completedQuantity: 0, outstandingQuantity: 100,
    completionRate: 0, moldId: null, moldNo: '', moldName: '', requiredMachineA: 12, materialName: '',
    sprueRatio: null, colorName: '', colorPowderCode: '', netWeightG: null, grossWeightG: null,
    materialWeightKg: null, unitPrice: null, sprayRequired: null, armRequirement: '', fixtureRequirement: '',
    orderDate: '', deliveryStartDate: '', deliveryDueDate: '', priority: 'NORMAL', plannedStart: '',
    plannedFinish: '', estimatedFinish: '', deliverySlackDays: null, shiftTargetQuantity: 100,
    todayDayQuantity: 0, todayNightQuantity: 0, downtimeMinutes: 0, locked: false, manualOverrideReason: '',
    orderRemark: '', machineRemark: '', parsedConstraintSummary: '', suggestionReason: '',
    materialReadinessStatus: 'ready', moldEnrichmentStatus: '', sourceBatchId: null, sourceSheetName: '',
    sourceRowNumber: null, sourceLineKey: '', taskRevision: 1, orderRevision: 1, planRevision: 1,
    updatedByName: '', updatedAt: '', lineage: {},
  }
}

function snapshot(currentJob = job()): WorkbenchSnapshot {
  return {
    factoryId: 'huaxing', businessDate: '2026-08-25', planId: 'plan-1', planRevision: currentJob.planRevision,
    ruleRevision: 1, planMode: 'PLANNING', pollingRevision: 1, machines: [], jobs: [currentJob],
    summary: { unplannedCount: 0, overdueCount: 0, conflictCount: 0, runningCount: 0,
      todayDayQuantity: 0, todayNightQuantity: 0 },
  }
}

describe('simplified workbench automatic save', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    vi.clearAllMocks()
  })
  afterEach(() => {
    vi.clearAllTimers()
    vi.useRealTimers()
  })

  it('keeps and rebases edits typed while an earlier save is in flight', async () => {
    let finishSave!: (value: WorkbenchSnapshot) => void
    apiMocks.saveWorkbenchChanges.mockReturnValue(new Promise((resolve) => { finishSave = resolve }))
    const store = useInjectionWorkbenchStore()
    store.snapshot = snapshot()
    store.stageChanges([{ jobId: 'task-1', expectedTaskRevision: 1, expectedOrderRevision: 1,
      field: 'shiftTargetQuantity', value: 200 }])
    const saving = store.savePendingChanges()
    store.stageChanges([{ jobId: 'task-1', expectedTaskRevision: 1, expectedOrderRevision: 1,
      field: 'shiftTargetQuantity', value: 300 }])
    finishSave(snapshot({ ...job(), shiftTargetQuantity: 200, taskRevision: 2, orderRevision: 1, planRevision: 2 }))
    await saving

    expect(store.pendingCount).toBe(1)
    expect(store.snapshot?.jobs[0]?.shiftTargetQuantity).toBe(300)
    expect(Object.values(store.pending)[0]?.expectedTaskRevision).toBe(2)
  })
})
