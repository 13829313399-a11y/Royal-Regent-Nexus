import { describe, expect, it } from 'vitest'
import { calculateInjectionVersionDiff } from '@/lib/injection-schedule/versionDiff'
import type {
  ConstraintResult,
  DataProvenance,
  InjectionOrder,
  InjectionScheduleTask,
  InjectionScoreBreakdown,
} from '@/types/injectionSchedule'

const provenance: DataProvenance = {
  source: 'mock',
  confidence: 'verified',
  sourceId: 'phase-2-version-diff-test',
  sourceFileName: null,
  sourceFileSha256: null,
  sheetName: null,
  sourceRow: null,
  capturedAt: '2026-07-23T00:00:00Z',
  importedAt: null,
  importedBy: null,
}

const scoreBreakdown: InjectionScoreBreakdown = {
  dueUrgency: 0,
  sameMoldMaterial: 0,
  setupCost: 0,
  colorTransition: 0,
  loadBalance: 0,
  downstreamImpact: 0,
  exactMatch: 0,
  splitPenalty: 0,
  specialHandlingPenalty: 0,
}

const passingConstraint: ConstraintResult = {
  code: 'factory_match',
  label: '厂区一致',
  status: 'pass',
  blocking: false,
  autoPublishBlocked: false,
  reason: '通过',
  missingFields: [],
  actual: 'huaxing',
  expected: 'huaxing',
  originalStatus: null,
  override: null,
}

function order(
  id: string,
  moldId: string,
  dueAt = '2026-07-23T11:00:00Z',
): InjectionOrder {
  return {
    id,
    factoryId: 'huaxing',
    orderNo: id,
    itemNo: null,
    moldId,
    productName: id,
    orderShots: 2_000,
    producedShots: 0,
    outstandingShots: 2_000,
    targetShotsPerDay: 1_000,
    grossShotWeightG: 300,
    colorName: '白',
    colorCode: 'WHITE',
    colorRank: 1,
    materialCode: 'PP',
    armRequirement: 'double',
    fixtureRequirements: [],
    capabilitiesRequired: [],
    orderedAt: null,
    deliveryStartAt: null,
    deliveryDueAt: dueAt,
    warehouseBufferHours: 0,
    downstreamBufferHours: 0,
    downstreamProcess: null,
    downstreamUrgency: 0,
    priority: 'P1',
    dataQualityFlags: [],
    sourceWorkbookRow: null,
    provenance,
  }
}

function task(
  id: string,
  orderId: string,
  machineId: string,
  startAt: string,
  endAt: string,
  overrides: Partial<InjectionScheduleTask> = {},
): InjectionScheduleTask {
  return {
    id,
    planVersionId: 'version',
    factoryId: 'huaxing',
    machineId,
    orderId,
    startAt,
    endAt,
    plannedShots: 1_000,
    setupMinutesBefore: 60,
    setupReason: [],
    score: null,
    scoreBreakdown,
    constraintSnapshot: [passingConstraint],
    source: 'manual',
    locked: false,
    status: 'draft',
    provenance,
    ...overrides,
  }
}

const orders = [
  order('O1', 'MO-A'),
  order('O2', 'MO-B'),
  order('O3', 'MO-A'),
  order('O4', 'MO-C'),
]

describe('Phase 2 injection schedule version diff', () => {
  it('reports cross-machine moves, same-machine index changes, and lock changes', () => {
    const before = [
      task('T1', 'O1', 'M1', '2026-07-23T08:00:00Z', '2026-07-23T09:00:00Z'),
      task('T2', 'O2', 'M1', '2026-07-23T09:00:00Z', '2026-07-23T10:00:00Z'),
      task('T3', 'O3', 'M1', '2026-07-23T10:00:00Z', '2026-07-23T11:00:00Z'),
      task('T4', 'O4', 'M2', '2026-07-23T08:00:00Z', '2026-07-23T09:00:00Z'),
    ]
    const after = [
      task('T3', 'O3', 'M1', '2026-07-23T08:00:00Z', '2026-07-23T09:00:00Z'),
      task('T1', 'O1', 'M1', '2026-07-23T09:00:00Z', '2026-07-23T10:00:00Z'),
      task('T4', 'O4', 'M2', '2026-07-23T08:00:00Z', '2026-07-23T09:00:00Z'),
      task('T2', 'O2', 'M2', '2026-07-23T09:00:00Z', '2026-07-23T10:00:00Z', {
        locked: true,
      }),
    ]
    const diff = calculateInjectionVersionDiff({
      beforeTasks: before,
      afterTasks: after,
      orders,
    })

    expect(diff.movedTasks).toEqual([{
      taskId: 'T2',
      orderId: 'O2',
      fromMachineId: 'M1',
      toMachineId: 'M2',
    }])
    expect(diff.reorderedTasks).toEqual(expect.arrayContaining([
      expect.objectContaining({ taskId: 'T1', fromIndex: 0, toIndex: 1 }),
      expect.objectContaining({ taskId: 'T3', fromIndex: 2, toIndex: 0 }),
    ]))
    expect(diff.lockChanges).toEqual([{
      taskId: 'T2',
      orderId: 'O2',
      beforeLocked: false,
      afterLocked: true,
    }])
    expect(diff.counts).toMatchObject({
      moved: 1,
      reordered: 2,
      lockChanges: 1,
    })
  })

  it('recognizes a quantity-conserving split and records the new task', () => {
    const before = [
      task('T1', 'O1', 'M1', '2026-07-23T08:00:00Z', '2026-07-23T10:00:00Z', {
        plannedShots: 1_000,
      }),
    ]
    const after = [
      task('T1', 'O1', 'M1', '2026-07-23T08:00:00Z', '2026-07-23T09:00:00Z', {
        plannedShots: 600,
      }),
      task('T1-SPLIT', 'O1', 'M2', '2026-07-23T08:00:00Z', '2026-07-23T09:00:00Z', {
        plannedShots: 400,
      }),
    ]
    const diff = calculateInjectionVersionDiff({
      beforeTasks: before,
      afterTasks: after,
      orders,
    })

    expect(diff.addedTaskIds).toEqual(['T1-SPLIT'])
    expect(diff.splitOrders).toEqual([{
      orderId: 'O1',
      beforeTaskCount: 1,
      afterTaskCount: 2,
      beforePlannedShots: 1_000,
      afterPlannedShots: 1_000,
      addedTaskIds: ['T1-SPLIT'],
      quantityConserved: true,
    }])
  })

  it('shows delivery slack and risk changes for affected orders', () => {
    const before = [
      task('T1', 'O1', 'M1', '2026-07-23T08:00:00Z', '2026-07-23T10:00:00Z'),
    ]
    const after = [
      task('T1', 'O1', 'M1', '2026-07-23T10:00:00Z', '2026-07-23T12:00:00Z'),
    ]
    const diff = calculateInjectionVersionDiff({
      beforeTasks: before,
      afterTasks: after,
      orders,
    })

    expect(diff.deliveryImpacts).toEqual([expect.objectContaining({
      orderId: 'O1',
      beforeSlackHours: 1,
      afterSlackHours: -1,
      slackDeltaHours: -2,
      beforeRisk: 'on_time',
      afterRisk: 'late',
    })])
    expect(diff.affectedOrderIds).toContain('O1')
  })

  it('counts adjacent mold changes and setup-minute deltas', () => {
    const before = [
      task('T1', 'O1', 'M1', '2026-07-23T08:00:00Z', '2026-07-23T09:00:00Z', {
        setupMinutesBefore: 60,
      }),
      task('T2', 'O2', 'M1', '2026-07-23T09:00:00Z', '2026-07-23T10:00:00Z', {
        setupMinutesBefore: 60,
      }),
      task('T3', 'O3', 'M1', '2026-07-23T10:00:00Z', '2026-07-23T11:00:00Z', {
        setupMinutesBefore: 60,
      }),
    ]
    const after = [
      task('T1', 'O1', 'M1', '2026-07-23T08:00:00Z', '2026-07-23T09:00:00Z', {
        setupMinutesBefore: 60,
      }),
      task('T3', 'O3', 'M1', '2026-07-23T09:00:00Z', '2026-07-23T10:00:00Z', {
        setupMinutesBefore: 0,
      }),
      task('T2', 'O2', 'M1', '2026-07-23T10:00:00Z', '2026-07-23T11:00:00Z', {
        setupMinutesBefore: 60,
      }),
    ]
    const diff = calculateInjectionVersionDiff({
      beforeTasks: before,
      afterTasks: after,
      orders,
    })

    expect(diff.changeovers).toEqual({
      beforeCount: 2,
      afterCount: 1,
      deltaCount: -1,
      beforeSetupMinutes: 180,
      afterSetupMinutes: 120,
      deltaSetupMinutes: -60,
    })
  })

  it('is deterministic and does not mutate version snapshots', () => {
    const before = [
      task('T1', 'O1', 'M1', '2026-07-23T08:00:00Z', '2026-07-23T09:00:00Z'),
      task('T2', 'O2', 'M1', '2026-07-23T09:00:00Z', '2026-07-23T10:00:00Z'),
    ]
    const after = [
      task('T2', 'O2', 'M1', '2026-07-23T08:00:00Z', '2026-07-23T09:00:00Z'),
      task('T1', 'O1', 'M1', '2026-07-23T09:00:00Z', '2026-07-23T10:00:00Z'),
    ]
    const beforeSnapshot = structuredClone(before)
    const afterSnapshot = structuredClone(after)
    const input = { beforeTasks: before, afterTasks: after, orders }

    expect(calculateInjectionVersionDiff(input)).toEqual(calculateInjectionVersionDiff(input))
    expect(before).toEqual(beforeSnapshot)
    expect(after).toEqual(afterSnapshot)
  })
})
