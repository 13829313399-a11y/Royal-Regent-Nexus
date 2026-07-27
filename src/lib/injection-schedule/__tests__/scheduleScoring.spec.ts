import { describe, expect, it } from 'vitest'
import { scoreInjectionRecommendation } from '@/lib/injection-schedule/scheduleScoring'
import type {
  ConstraintResult,
  DataProvenance,
  InjectionConstraintEvaluation,
  InjectionMachine,
  InjectionMold,
  InjectionOrder,
  InjectionRuleConfig,
  InjectionSetupCost,
  InjectionSetupProfile,
} from '@/types/injectionSchedule'

const provenance: DataProvenance = {
  source: 'mock',
  confidence: 'verified',
  sourceId: 'scoring-test',
  sourceFileName: null,
  sourceFileSha256: null,
  sheetName: null,
  sourceRow: null,
  capturedAt: '2026-07-21T00:00:00+08:00',
  importedAt: null,
  importedBy: null,
}

const machine: InjectionMachine = {
  id: 'machine-01',
  factoryId: 'huaxing',
  workshop: 'new',
  machineNo: '新17',
  machineClass: '14A',
  tonnage: 180,
  speedType: null,
  armType: 'double',
  supportedFixtures: [],
  screwType: 'standard',
  capabilities: [],
  materialRules: [],
  maxShotWeightG: 500,
  tieBarWidthMm: 700,
  tieBarHeightMm: 600,
  minMoldThicknessMm: 180,
  maxMoldThicknessMm: 500,
  maxOpeningStrokeMm: 650,
  maxEjectorClearanceMm: 180,
  status: 'idle',
  schedulingLocked: false,
  availableFrom: null,
  unavailableWindows: [],
  dataCompleteness: 1,
  dataQualityFlags: [],
  provenance,
}

const mold: InjectionMold = {
  id: 'mold-001',
  factoryId: 'huaxing',
  moldNo: 'MOLD-001',
  name: '产品 A 模具',
  recommendedMachineClass: '14A',
  minTonnage: 160,
  grossShotWeightG: 300,
  engineeringNetWeightG: 280,
  lengthMm: 600,
  widthMm: 500,
  heightMm: 350,
  moldThicknessMm: 350,
  requiredOpeningStrokeMm: 500,
  requiredEjectorClearanceMm: 100,
  moldWeightKg: 900,
  armRequirement: 'none',
  fixtureRequirements: [],
  capabilitiesRequired: [],
  materialCode: 'PP',
  requiredScrewTypes: [],
  defaultColor: '白色',
  defaultColorRank: 1,
  cavityCount: 2,
  standardCycleSeconds: 30,
  dataQualityFlags: [],
  provenance,
}

function order(overrides: Partial<InjectionOrder> = {}): InjectionOrder {
  return {
    id: 'order-001',
    factoryId: 'huaxing',
    orderNo: 'SO-001',
    itemNo: 'ITEM-001',
    moldId: mold.id,
    productName: '产品 A',
    orderShots: 10_000,
    producedShots: 1_000,
    outstandingShots: 9_000,
    targetShotsPerDay: 2_000,
    grossShotWeightG: 300,
    colorName: '白色',
    colorCode: 'WHITE',
    colorRank: 1,
    materialCode: 'PP',
    armRequirement: null,
    fixtureRequirements: [],
    capabilitiesRequired: [],
    orderedAt: '2026-07-18T08:00:00+08:00',
    deliveryStartAt: null,
    deliveryDueAt: '2026-07-26T08:00:00+08:00',
    warehouseBufferHours: 0,
    downstreamBufferHours: 0,
    downstreamProcess: 'assembly',
    downstreamUrgency: 0.5,
    priority: 'P3',
    dataQualityFlags: [],
    sourceWorkbookRow: 20,
    provenance,
    ...overrides,
  }
}

const config: InjectionRuleConfig = {
  factoryId: 'huaxing',
  shotSafetyFactor: 0.8,
  lossRate: 0.01,
  schedulableMachineStatuses: ['idle', 'running', 'setup'],
  setup: {
    firstTaskSetupMinutes: 60,
    sameMoldChangeMinutes: 0,
    differentMoldChangeMinutes: 60,
    sameMaterialChangeMinutes: 0,
    differentMaterialChangeMinutes: 30,
    sameColorChangeMinutes: 0,
    lightToDarkColorMinutes: 10,
    darkToLightColorMinutes: 45,
    unknownColorTransitionMinutes: 50,
    colorTransitionMatrix: [],
    materialTransitionMatrix: [],
  },
  scoring: {
    weights: {
      dueUrgency: 35,
      sameMoldMaterial: 15,
      setupCost: 15,
      colorTransition: 10,
      loadBalance: 10,
      downstreamImpact: 10,
      exactMatch: 5,
      splitPenalty: -12,
      specialHandlingPenalty: -8,
    },
    dueUrgencyHorizonHours: 168,
    setupCostCeilingMinutes: 120,
    colorTransitionCeilingMinutes: 60,
  },
}

const zeroSetup: InjectionSetupCost = {
  totalMinutes: 0,
  moldChangeMinutes: 0,
  materialChangeMinutes: 0,
  colorChangeMinutes: 0,
  sameMold: true,
  sameMaterial: true,
  colorDirection: 'same',
  reasons: ['同模同料同色'],
  dataQualityFlags: [],
  colorOverride: null,
}

function constraint(
  status: ConstraintResult['status'] = 'pass',
): InjectionConstraintEvaluation {
  const blocking = status === 'fail' || status === 'unknown'
  const result: ConstraintResult = {
    code: 'factory_match',
    label: '厂区一致',
    status,
    blocking,
    autoPublishBlocked: status !== 'pass',
    reason: status === 'pass' ? '厂区一致' : '禁止跨厂排程',
    missingFields: [],
    actual: 'huaxing',
    expected: 'huaxing',
    originalStatus: status === 'override' ? 'unknown' : null,
    override: null,
  }
  return {
    results: [result],
    eligible: !blocking,
    autoPublishAllowed: status === 'pass',
    hasUnknownData: status === 'unknown' || status === 'override',
    failureReasons: blocking ? [result.reason] : [],
  }
}

function previous(overrides: Partial<InjectionSetupProfile> = {}): InjectionSetupProfile {
  return {
    moldId: mold.id,
    productName: '产品 A',
    materialCode: 'PP',
    colorCode: 'WHITE',
    colorRank: 1,
    ...overrides,
  }
}

function scoreCandidate(
  candidateOrder: InjectionOrder,
  previousTask: InjectionSetupProfile | null,
) {
  return scoreInjectionRecommendation({
    machine,
    mold,
    order: candidateOrder,
    constraints: constraint(),
    setupCost: zeroSetup,
    config,
    previous: previousTask,
    referenceAt: '2026-07-22T08:00:00+08:00',
    estimatedStartAt: '2026-07-22T08:00:00+08:00',
    estimatedEndAt: '2026-07-23T08:00:00+08:00',
    machineLoadRatio: 0.5,
    exactMatch: true,
  })
}

describe('injection recommendation scoring', () => {
  it('scores an overdue order above an otherwise equal later-due order', () => {
    const overdue = scoreCandidate(order({
      deliveryDueAt: '2026-07-22T20:00:00+08:00',
    }), previous())
    const laterDue = scoreCandidate(order({
      deliveryDueAt: '2026-08-10T08:00:00+08:00',
    }), previous())

    expect(overdue.deliverySlackHours).toBeLessThan(0)
    expect(overdue.scoreBreakdown.dueUrgency).toBe(35)
    expect(overdue.scoreBreakdown.dueUrgency).toBeGreaterThan(
      laterDue.scoreBreakdown.dueUrgency,
    )
    expect(overdue.score).toBeGreaterThan(laterDue.score!)
  })

  it('rewards an adjacent same-mold sequence over a different mold', () => {
    const sameMold = scoreCandidate(order(), previous({ moldId: mold.id }))
    const differentMold = scoreCandidate(order(), previous({ moldId: 'mold-other' }))

    expect(sameMold.scoreBreakdown.sameMoldMaterial).toBe(15)
    expect(differentMold.scoreBreakdown.sameMoldMaterial).toBeLessThan(
      sameMold.scoreBreakdown.sameMoldMaterial,
    )
    expect(sameMold.score).toBeGreaterThan(differentMold.score!)
    expect(sameMold.reasons).toContain('与前序任务同模，适合连续生产')
  })

  it('returns no recommendation score when a hard constraint fails', () => {
    const result = scoreInjectionRecommendation({
      machine,
      mold,
      order: order(),
      constraints: constraint('fail'),
      setupCost: zeroSetup,
      config,
      previous: previous(),
      referenceAt: '2026-07-22T08:00:00+08:00',
      estimatedStartAt: '2026-07-22T08:00:00+08:00',
      estimatedEndAt: '2026-07-23T08:00:00+08:00',
      machineLoadRatio: 0.5,
    })

    expect(result.eligible).toBe(false)
    expect(result.autoPublishAllowed).toBe(false)
    expect(result.score).toBeNull()
    expect(result.reasons).toContain('禁止跨厂排程')
  })

  it('keeps weights configurable and applies split and special-handling penalties', () => {
    const result = scoreInjectionRecommendation({
      machine,
      mold,
      order: order(),
      constraints: constraint(),
      setupCost: zeroSetup,
      config: {
        ...config,
        scoring: {
          ...config.scoring,
          weights: {
            ...config.scoring.weights,
            splitPenalty: -20,
            specialHandlingPenalty: -11,
          },
        },
      },
      previous: previous(),
      referenceAt: '2026-07-22T08:00:00+08:00',
      estimatedStartAt: '2026-07-22T08:00:00+08:00',
      estimatedEndAt: '2026-07-23T08:00:00+08:00',
      machineLoadRatio: 0.5,
      splitAcrossMachines: true,
      specialHandling: true,
    })

    expect(result.scoreBreakdown.splitPenalty).toBe(-20)
    expect(result.scoreBreakdown.specialHandlingPenalty).toBe(-11)
  })

  it('rejects Date.now-style implicit scoring by requiring an explicit valid base time', () => {
    expect(() => scoreInjectionRecommendation({
      machine,
      mold,
      order: order(),
      constraints: constraint(),
      setupCost: zeroSetup,
      config,
      previous: previous(),
      referenceAt: 'not-a-date',
      estimatedStartAt: null,
      estimatedEndAt: null,
      machineLoadRatio: 0,
    })).toThrow('排程评分必须提供有效的版本基准时间')
  })
})
