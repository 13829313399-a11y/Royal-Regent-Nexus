import { describe, expect, it } from 'vitest'
import {
  applyInjectionScheduleMutation,
  mutateAndProjectInjectionSchedule,
  projectInjectionSchedule,
} from '@/lib/injection-schedule/scheduleProjection'
import type {
  ConstraintResult,
  DataProvenance,
  InjectionMachine,
  InjectionMold,
  InjectionOrder,
  InjectionScheduleTask,
  InjectionScoreBreakdown,
  InjectionSetupRuleConfig,
} from '@/types/injectionSchedule'

const provenance: DataProvenance = {
  source: 'mock',
  confidence: 'verified',
  sourceId: 'phase-2-projection-test',
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

const setupConfig: InjectionSetupRuleConfig = {
  firstTaskSetupMinutes: 60,
  sameMoldChangeMinutes: 0,
  differentMoldChangeMinutes: 60,
  sameMaterialChangeMinutes: 0,
  differentMaterialChangeMinutes: 0,
  sameColorChangeMinutes: 0,
  lightToDarkColorMinutes: 0,
  darkToLightColorMinutes: 0,
  unknownColorTransitionMinutes: 0,
  colorTransitionMatrix: [],
  materialTransitionMatrix: [],
}

function machine(id: string): InjectionMachine {
  return {
    id,
    factoryId: 'huaxing',
    workshop: 'new',
    machineNo: id,
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
  }
}

function mold(id: string): InjectionMold {
  return {
    id,
    factoryId: 'huaxing',
    moldNo: id,
    name: id,
    recommendedMachineClass: '14A',
    minTonnage: 160,
    grossShotWeightG: 300,
    engineeringNetWeightG: 280,
    lengthMm: 500,
    widthMm: 400,
    heightMm: 300,
    moldThicknessMm: 300,
    requiredOpeningStrokeMm: 400,
    requiredEjectorClearanceMm: 100,
    moldWeightKg: 800,
    armRequirement: 'double',
    fixtureRequirements: [],
    capabilitiesRequired: [],
    materialCode: 'PP',
    requiredScrewTypes: [],
    defaultColor: '白',
    defaultColorRank: 1,
    cavityCount: 2,
    standardCycleSeconds: 30,
    dataQualityFlags: [],
    provenance,
  }
}

function order(id: string, moldId: string): InjectionOrder {
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
    targetShotsPerDay: 240,
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
  }
}

function task(
  id: string,
  orderId: string,
  machineId: string,
  overrides: Partial<InjectionScheduleTask> = {},
): InjectionScheduleTask {
  return {
    id,
    planVersionId: 'draft-v1',
    factoryId: 'huaxing',
    machineId,
    orderId,
    startAt: '2026-07-23T01:00:00Z',
    endAt: '2026-07-23T02:00:00Z',
    plannedShots: 100,
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

const machines = [machine('M1'), machine('M2'), machine('M3')]
const molds = [mold('MO-A'), mold('MO-B')]
const orders = [
  order('O-A', 'MO-A'),
  order('O-B', 'MO-B'),
  order('O-C', 'MO-A'),
  order('O-D', 'MO-B'),
]

describe('Phase 2 injection schedule mutation and projection', () => {
  it('assigns a new task at a deterministic machine position and projects only that machine', () => {
    const originalA = task('T-A', 'O-A', 'M1')
    const untouched = task('T-D', 'O-D', 'M3', {
      startAt: '2026-07-25T01:00:00Z',
      endAt: '2026-07-25T02:00:00Z',
    })
    const assigned = task('T-B', 'O-B', 'unassigned')
    const mutation = applyInjectionScheduleMutation([originalA, untouched], {
      type: 'assign',
      task: assigned,
      machineId: 'M1',
      index: 1,
    })
    const projection = projectInjectionSchedule({
      tasks: mutation.tasks,
      affectedMachineIds: mutation.affectedMachineIds,
      machines,
      molds,
      orders,
      setupConfig,
      planBaseAt: '2026-07-23T00:00:00Z',
      productionMinutesByTaskId: {
        'T-A': 60,
        'T-B': 60,
      },
    })

    expect(mutation.tasks.filter((entry) => entry.machineId === 'M1').map((entry) => entry.id))
      .toEqual(['T-A', 'T-B'])
    expect(projection.affectedMachineIds).toEqual(['M1'])
    expect(projection.projectedTaskIds).toEqual(['T-A', 'T-B'])
    expect(projection.tasks.find((entry) => entry.id === 'T-D')).toBe(untouched)
    expect(projection.tasks.find((entry) => entry.id === 'T-D')?.startAt)
      .toBe('2026-07-25T01:00:00Z')
  })

  it('reorders within one machine and recomputes setup from the new adjacent tasks', () => {
    const result = mutateAndProjectInjectionSchedule({
      tasks: [
        task('T-A', 'O-A', 'M1'),
        task('T-B', 'O-B', 'M1'),
        task('T-C', 'O-C', 'M1'),
      ],
      mutation: {
        type: 'reorder',
        taskId: 'T-C',
        index: 1,
      },
      machines,
      molds,
      orders,
      setupConfig,
      planBaseAt: '2026-07-23T00:00:00Z',
      productionMinutesByTaskId: {
        'T-A': 60,
        'T-B': 60,
        'T-C': 60,
      },
    })
    const sequence = result.tasks.filter((entry) => entry.machineId === 'M1')

    expect(sequence.map((entry) => entry.id)).toEqual(['T-A', 'T-C', 'T-B'])
    expect(sequence.map((entry) => entry.setupMinutesBefore)).toEqual([60, 0, 60])
    expect(sequence[1]?.setupReason.join(' ')).toContain('同模相邻任务')
    expect(result.affectedMachineIds).toEqual(['M1'])
  })

  it('moves across machines and leaves a third machine byte-for-byte untouched', () => {
    const untouched = task('T-D', 'O-D', 'M3', {
      startAt: '2026-07-26T04:00:00Z',
      endAt: '2026-07-26T05:00:00Z',
    })
    const result = mutateAndProjectInjectionSchedule({
      tasks: [
        task('T-A', 'O-A', 'M1'),
        task('T-B', 'O-B', 'M1'),
        task('T-C', 'O-C', 'M2'),
        untouched,
      ],
      mutation: {
        type: 'move',
        taskId: 'T-B',
        machineId: 'M2',
        index: 1,
      },
      machines,
      molds,
      orders,
      setupConfig,
      planBaseAt: '2026-07-23T00:00:00Z',
      productionMinutesByTaskId: {
        'T-A': 60,
        'T-B': 60,
        'T-C': 60,
      },
    })

    expect(result.affectedMachineIds).toEqual(['M1', 'M2'])
    expect(result.tasks.filter((entry) => entry.machineId === 'M1').map((entry) => entry.id))
      .toEqual(['T-A'])
    expect(result.tasks.filter((entry) => entry.machineId === 'M2').map((entry) => entry.id))
      .toEqual(['T-C', 'T-B'])
    expect(result.tasks.find((entry) => entry.id === 'T-D')).toBe(untouched)
  })

  it('protects locked tasks from move, reorder, split, and indirect time movement', () => {
    const locked = task('T-A', 'O-A', 'M1', { locked: true })

    expect(() => applyInjectionScheduleMutation([locked], {
      type: 'move',
      taskId: 'T-A',
      machineId: 'M2',
    })).toThrow('已锁定')
    expect(() => applyInjectionScheduleMutation([locked], {
      type: 'reorder',
      taskId: 'T-A',
      index: 0,
    })).toThrow('已锁定')
    expect(() => applyInjectionScheduleMutation([locked], {
      type: 'split',
      taskId: 'T-A',
      newTaskId: 'T-A-2',
      splitPlannedShots: 20,
    })).toThrow('已锁定')

    const protectedDownstream = task('T-B', 'O-B', 'M1', {
      locked: true,
      startAt: '2026-07-23T03:00:00Z',
      endAt: '2026-07-23T04:00:00Z',
    })
    expect(() => mutateAndProjectInjectionSchedule({
      tasks: [
        task('T-A', 'O-A', 'M1', {
          startAt: '2026-07-23T01:00:00Z',
          endAt: '2026-07-23T02:00:00Z',
        }),
        protectedDownstream,
      ],
      mutation: {
        type: 'reorder',
        taskId: 'T-A',
        index: 1,
      },
      machines,
      molds,
      orders,
      setupConfig,
      planBaseAt: '2026-07-23T00:00:00Z',
      productionMinutesByTaskId: {
        'T-A': 60,
        'T-B': 60,
      },
    })).toThrow('会移动受保护任务 T-B')
  })

  it('splits quantity without creating or losing planned shots', () => {
    const original = task('T-A', 'O-A', 'M1', { plannedShots: 1_000 })
    const mutation = applyInjectionScheduleMutation([original], {
      type: 'split',
      taskId: 'T-A',
      newTaskId: 'T-A-SPLIT',
      splitPlannedShots: 400,
      machineId: 'M2',
      index: 0,
    })
    const splitTasks = mutation.tasks.filter((entry) => entry.orderId === 'O-A')

    expect(splitTasks).toHaveLength(2)
    expect(splitTasks.map((entry) => entry.plannedShots).sort((a, b) => a - b))
      .toEqual([400, 600])
    expect(splitTasks.reduce((sum, entry) => sum + entry.plannedShots, 0)).toBe(1_000)
    expect(mutation.affectedMachineIds).toEqual(['M1', 'M2'])
    expect(original.plannedShots).toBe(1_000)
  })

  it('is deterministic and does not mutate caller-owned tasks', () => {
    const inputTasks = [
      task('T-A', 'O-A', 'M1'),
      task('T-B', 'O-B', 'M1'),
    ]
    const before = structuredClone(inputTasks)
    const input = {
      tasks: inputTasks,
      mutation: {
        type: 'reorder' as const,
        taskId: 'T-B',
        index: 0,
      },
      machines,
      molds,
      orders,
      setupConfig,
      planBaseAt: '2026-07-23T00:00:00Z',
      productionMinutesByTaskId: {
        'T-A': 60,
        'T-B': 60,
      },
    }

    expect(mutateAndProjectInjectionSchedule(input))
      .toEqual(mutateAndProjectInjectionSchedule(input))
    expect(inputTasks).toEqual(before)
  })
})
