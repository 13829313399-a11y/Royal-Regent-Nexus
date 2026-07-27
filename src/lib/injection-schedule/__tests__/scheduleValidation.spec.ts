import { describe, expect, it } from 'vitest'
import { validateInjectionSchedule } from '@/lib/injection-schedule/scheduleValidation'
import type {
  ConstraintResult,
  DataProvenance,
  InjectionMachine,
  InjectionOrder,
  InjectionScheduleTask,
  InjectionScoreBreakdown,
} from '@/types/injectionSchedule'

const provenance: DataProvenance = {
  source: 'mock',
  confidence: 'verified',
  sourceId: 'phase-2-validation-test',
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

function constraint(
  status: ConstraintResult['status'] = 'pass',
  overrides: Partial<ConstraintResult> = {},
): ConstraintResult {
  return {
    code: 'shot_capacity',
    label: '射胶量',
    status,
    blocking: status !== 'pass' && status !== 'override',
    autoPublishBlocked: status !== 'pass',
    reason: status === 'pass' ? '通过' : '测试资料状态',
    missingFields: status === 'unknown' ? ['machine.maxShotWeightG'] : [],
    actual: null,
    expected: null,
    originalStatus: status === 'override' ? 'unknown' : null,
    override: status === 'override'
      ? {
          reason: '工程线下确认',
          actorId: 'planner-1',
          actorName: '计划员',
          createdAt: '2026-07-23T00:00:00Z',
        }
      : null,
    ...overrides,
  }
}

function machine(overrides: Partial<InjectionMachine> = {}): InjectionMachine {
  return {
    id: 'M1',
    factoryId: 'huaxing',
    workshop: 'new',
    machineNo: '新1',
    machineClass: '14A',
    tonnage: 180,
    speedType: null,
    armType: 'double',
    supportedFixtures: [],
    screwType: 'alloy',
    capabilities: [],
    materialRules: [],
    maxShotWeightG: 500,
    tieBarWidthMm: 700,
    tieBarHeightMm: 600,
    minMoldThicknessMm: 100,
    maxMoldThicknessMm: 500,
    maxOpeningStrokeMm: 600,
    maxEjectorClearanceMm: 200,
    status: 'idle',
    schedulingLocked: false,
    availableFrom: '2026-07-23T00:00:00Z',
    unavailableWindows: [],
    dataCompleteness: 1,
    dataQualityFlags: [],
    provenance,
    ...overrides,
  }
}

function order(id: string, overrides: Partial<InjectionOrder> = {}): InjectionOrder {
  return {
    id,
    factoryId: 'huaxing',
    orderNo: id,
    itemNo: null,
    moldId: 'MO-1',
    productName: id,
    orderShots: 1_000,
    producedShots: 0,
    outstandingShots: 1_000,
    targetShotsPerDay: 500,
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
    deliveryDueAt: '2026-07-30T00:00:00Z',
    warehouseBufferHours: 0,
    downstreamBufferHours: 0,
    downstreamProcess: null,
    downstreamUrgency: 0,
    priority: 'P1',
    dataQualityFlags: [],
    sourceWorkbookRow: null,
    provenance,
    ...overrides,
  }
}

function task(
  id: string,
  orderId: string,
  startAt: string,
  endAt: string,
  overrides: Partial<InjectionScheduleTask> = {},
): InjectionScheduleTask {
  return {
    id,
    planVersionId: 'draft-v1',
    factoryId: 'huaxing',
    machineId: 'M1',
    orderId,
    startAt,
    endAt,
    plannedShots: 100,
    setupMinutesBefore: 0,
    setupReason: [],
    score: null,
    scoreBreakdown,
    constraintSnapshot: [constraint()],
    source: 'manual',
    locked: false,
    status: 'draft',
    provenance,
    ...overrides,
  }
}

describe('Phase 2 injection schedule validation', () => {
  it('accepts non-overlapping compatible tasks with conserved quantities', () => {
    const result = validateInjectionSchedule({
      factoryId: 'huaxing',
      tasks: [
        task('T1', 'O1', '2026-07-23T08:00:00Z', '2026-07-23T10:00:00Z'),
        task('T2', 'O2', '2026-07-23T10:00:00Z', '2026-07-23T12:00:00Z'),
      ],
      machines: [machine()],
      orders: [order('O1'), order('O2')],
    })

    expect(result).toEqual({
      conflicts: [],
      valid: true,
      autoPublishAllowed: true,
    })
  })

  it('surfaces task overlap on the same machine', () => {
    const result = validateInjectionSchedule({
      factoryId: 'huaxing',
      tasks: [
        task('T1', 'O1', '2026-07-23T08:00:00Z', '2026-07-23T10:00:00Z'),
        task('T2', 'O2', '2026-07-23T09:00:00Z', '2026-07-23T11:00:00Z'),
      ],
      machines: [machine()],
      orders: [order('O1'), order('O2')],
    })

    expect(result.conflicts).toEqual(expect.arrayContaining([
      expect.objectContaining({
        code: 'task_overlap',
        taskIds: ['T1', 'T2'],
        blocking: true,
      }),
    ]))
    expect(result.valid).toBe(false)
  })

  it('treats setup time as occupied when checking downtime windows', () => {
    const result = validateInjectionSchedule({
      factoryId: 'huaxing',
      tasks: [
        task('T1', 'O1', '2026-07-23T09:00:00Z', '2026-07-23T10:00:00Z', {
          setupMinutesBefore: 60,
        }),
      ],
      machines: [machine({
        unavailableWindows: [{
          id: 'DOWN-1',
          startAt: '2026-07-23T08:30:00Z',
          endAt: '2026-07-23T08:45:00Z',
          reason: '计划保养',
          kind: 'maintenance',
        }],
      })],
      orders: [order('O1')],
    })

    expect(result.conflicts).toEqual(expect.arrayContaining([
      expect.objectContaining({
        code: 'unavailable_window',
        windowId: 'DOWN-1',
        taskIds: ['T1'],
      }),
    ]))
  })

  it('surfaces unknown constraints as blocking and reviewed overrides as manual-only warnings', () => {
    const unknown = validateInjectionSchedule({
      factoryId: 'huaxing',
      tasks: [
        task('T1', 'O1', '2026-07-23T08:00:00Z', '2026-07-23T10:00:00Z', {
          constraintSnapshot: [constraint('unknown')],
        }),
      ],
      machines: [machine()],
      orders: [order('O1')],
    })
    expect(unknown.conflicts).toEqual(expect.arrayContaining([
      expect.objectContaining({
        code: 'constraint_unknown',
        constraintCode: 'shot_capacity',
        blocking: true,
        autoPublishBlocked: true,
      }),
    ]))
    expect(unknown.valid).toBe(false)
    expect(unknown.autoPublishAllowed).toBe(false)

    const reviewed = validateInjectionSchedule({
      factoryId: 'huaxing',
      tasks: [
        task('T1', 'O1', '2026-07-23T08:00:00Z', '2026-07-23T10:00:00Z', {
          constraintSnapshot: [constraint('override')],
        }),
      ],
      machines: [machine()],
      orders: [order('O1')],
    })
    expect(reviewed.conflicts).toEqual([
      expect.objectContaining({
        code: 'constraint_override',
        severity: 'warning',
        blocking: false,
        autoPublishBlocked: true,
      }),
    ])
    expect(reviewed.valid).toBe(true)
    expect(reviewed.autoPublishAllowed).toBe(false)
  })

  it('blocks known constraint failures and missing constraint snapshots', () => {
    const result = validateInjectionSchedule({
      factoryId: 'huaxing',
      tasks: [
        task('T1', 'O1', '2026-07-23T08:00:00Z', '2026-07-23T10:00:00Z', {
          constraintSnapshot: [constraint('fail', {
            code: 'arm_type',
            label: '机械手',
            reason: '双臂订单不能排到单臂机',
          })],
        }),
        task('T2', 'O2', '2026-07-23T10:00:00Z', '2026-07-23T12:00:00Z', {
          constraintSnapshot: [],
        }),
      ],
      machines: [machine()],
      orders: [order('O1'), order('O2')],
    })

    expect(result.conflicts.map((entry) => entry.code)).toEqual(
      expect.arrayContaining(['constraint_failure', 'constraint_snapshot_missing']),
    )
    expect(result.valid).toBe(false)
  })

  it('blocks over-allocation and cross-factory references', () => {
    const result = validateInjectionSchedule({
      factoryId: 'huaxing',
      tasks: [
        task('T1', 'O1', '2026-07-23T08:00:00Z', '2026-07-23T10:00:00Z', {
          plannedShots: 700,
        }),
        task('T2', 'O1', '2026-07-23T10:00:00Z', '2026-07-23T12:00:00Z', {
          plannedShots: 400,
          factoryId: 'huadeng',
        }),
      ],
      machines: [machine()],
      orders: [order('O1', { outstandingShots: 1_000 })],
    })

    expect(result.conflicts.map((entry) => entry.code)).toEqual(
      expect.arrayContaining(['order_overallocated', 'factory_mismatch']),
    )
    expect(result.autoPublishAllowed).toBe(false)
  })
})
