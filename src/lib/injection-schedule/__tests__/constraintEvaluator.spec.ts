import { describe, expect, it } from 'vitest'
import {
  canAutoPublishFromConstraints,
  evaluateInjectionConstraints,
} from '@/lib/injection-schedule/constraintEvaluator'
import type {
  DataProvenance,
  InjectionConstraintCode,
  InjectionMachine,
  InjectionMold,
  InjectionOrder,
  InjectionRuleConfig,
} from '@/types/injectionSchedule'

const provenance: DataProvenance = {
  source: 'mock',
  confidence: 'verified',
  sourceId: 'phase-1-rules-test',
  sourceFileName: null,
  sourceFileSha256: null,
  sheetName: null,
  sourceRow: null,
  capturedAt: '2026-07-21T00:00:00+08:00',
  importedAt: null,
  importedBy: null,
}

function ruleConfig(overrides: Partial<InjectionRuleConfig> = {}): InjectionRuleConfig {
  return {
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
      darkToLightColorMinutes: 40,
      unknownColorTransitionMinutes: 45,
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
    ...overrides,
  }
}

function machine(overrides: Partial<InjectionMachine> = {}): InjectionMachine {
  return {
    id: 'machine-01',
    factoryId: 'huaxing',
    workshop: 'new',
    machineNo: '新17',
    machineClass: '14A',
    tonnage: 180,
    speedType: null,
    armType: 'double',
    supportedFixtures: ['suction_cup', 'air_cutter'],
    screwType: 'alloy',
    capabilities: ['core_pull', 'double_core_pull', 'high_pressure'],
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
    availableFrom: '2026-07-22T08:00:00+08:00',
    unavailableWindows: [],
    dataCompleteness: 1,
    dataQualityFlags: [],
    provenance,
    ...overrides,
  }
}

function mold(overrides: Partial<InjectionMold> = {}): InjectionMold {
  return {
    id: 'mold-14a-01',
    factoryId: 'huaxing',
    moldNo: '14A-001',
    name: '双臂抽芯模',
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
    armRequirement: 'double',
    fixtureRequirements: ['suction_cup'],
    capabilitiesRequired: ['double_core_pull'],
    materialCode: 'PP',
    requiredScrewTypes: [],
    defaultColor: '浅蓝',
    defaultColorRank: 2,
    cavityCount: 2,
    standardCycleSeconds: 30,
    dataQualityFlags: [],
    provenance,
    ...overrides,
  }
}

function order(overrides: Partial<InjectionOrder> = {}): InjectionOrder {
  return {
    id: 'order-001',
    factoryId: 'huaxing',
    orderNo: 'SO-001',
    itemNo: 'ITEM-001',
    moldId: 'mold-14a-01',
    productName: '测试产品',
    orderShots: 10_000,
    producedShots: 1_000,
    outstandingShots: 9_000,
    targetShotsPerDay: 2_000,
    grossShotWeightG: 300,
    colorName: '浅蓝',
    colorCode: 'LIGHT-BLUE',
    colorRank: 2,
    materialCode: 'PP',
    armRequirement: null,
    fixtureRequirements: [],
    capabilitiesRequired: [],
    orderedAt: '2026-07-18T08:00:00+08:00',
    deliveryStartAt: '2026-07-24T08:00:00+08:00',
    deliveryDueAt: '2026-07-25T20:00:00+08:00',
    warehouseBufferHours: 72,
    downstreamBufferHours: 0,
    downstreamProcess: 'assembly',
    downstreamUrgency: 0.5,
    priority: 'P1',
    dataQualityFlags: [],
    sourceWorkbookRow: 20,
    provenance,
    ...overrides,
  }
}

function resultByCode(
  evaluation: ReturnType<typeof evaluateInjectionConstraints>,
  code: InjectionConstraintCode,
) {
  return evaluation.results.find((result) => result.code === code)
}

describe('injection hard-constraint evaluator', () => {
  it('accepts a complete compatible same-factory candidate and permits automatic publishing', () => {
    const evaluation = evaluateInjectionConstraints({
      machine: machine(),
      mold: mold(),
      order: order(),
      config: ruleConfig(),
    })

    expect(evaluation.eligible).toBe(true)
    expect(evaluation.autoPublishAllowed).toBe(true)
    expect(evaluation.results.every((result) => result.status === 'pass')).toBe(true)
    expect(canAutoPublishFromConstraints(evaluation.results)).toBe(true)
  })

  it('treats cross-factory placement as a non-overridable isolation failure', () => {
    const evaluation = evaluateInjectionConstraints({
      machine: machine(),
      mold: mold(),
      order: order({ factoryId: 'huadeng' }),
      config: ruleConfig(),
      overrides: {
        factory_match: {
          reason: '尝试人工跨厂',
          actorId: 'planner-1',
          actorName: '计划员',
          createdAt: '2026-07-22T08:00:00+08:00',
        },
      },
    })

    expect(resultByCode(evaluation, 'factory_match')).toMatchObject({
      status: 'fail',
      blocking: true,
      autoPublishBlocked: true,
    })
    expect(resultByCode(evaluation, 'factory_match')?.reason).toContain('禁止跨厂排程')
    expect(evaluation.eligible).toBe(false)
  })

  it('rejects maintenance, stopped, or explicitly locked machines', () => {
    for (const candidate of [
      machine({ status: 'maintenance' }),
      machine({ status: 'stopped' }),
      machine({ schedulingLocked: true }),
    ]) {
      const evaluation = evaluateInjectionConstraints({
        machine: candidate,
        mold: mold(),
        order: order(),
        config: ruleConfig(),
      })
      expect(resultByCode(evaluation, 'machine_status')?.status).toBe('fail')
      expect(evaluation.eligible).toBe(false)
    }
  })

  it('returns a specific failure for dimensions, mold thickness, and opening stroke', () => {
    const cases: Array<{
      code: 'mold_dimensions' | 'mold_thickness' | 'opening_stroke'
      mold: InjectionMold
      copy: string
    }> = [
      {
        code: 'mold_dimensions',
        mold: mold({ lengthMm: 900, widthMm: 800 }),
        copy: '超出机台拉杆内距',
      },
      {
        code: 'mold_thickness',
        mold: mold({ moldThicknessMm: 700 }),
        copy: '不在机台范围',
      },
      {
        code: 'opening_stroke',
        mold: mold({ requiredOpeningStrokeMm: 800 }),
        copy: '超过机台上限',
      },
    ]

    for (const testCase of cases) {
      const evaluation = evaluateInjectionConstraints({
        machine: machine(),
        mold: testCase.mold,
        order: order(),
        config: ruleConfig(),
      })
      expect(resultByCode(evaluation, testCase.code)).toMatchObject({
        status: 'fail',
        blocking: true,
      })
      expect(resultByCode(evaluation, testCase.code)?.reason).toContain(testCase.copy)
    }
  })

  it('prevents a double-arm order from being placed on a single-arm machine', () => {
    const evaluation = evaluateInjectionConstraints({
      machine: machine({ armType: 'single' }),
      mold: mold({ armRequirement: 'double' }),
      order: order({ armRequirement: 'double' }),
      config: ruleConfig(),
    })

    expect(resultByCode(evaluation, 'arm_type')).toMatchObject({
      status: 'fail',
      actual: 'single',
      expected: 'double',
    })
    expect(resultByCode(evaluation, 'arm_type')?.reason).toContain('订单要求双臂')
  })

  it('rejects gross shot weight above the configured safe shot capacity', () => {
    const evaluation = evaluateInjectionConstraints({
      machine: machine({ maxShotWeightG: 500 }),
      mold: mold({ grossShotWeightG: 401 }),
      order: order({ grossShotWeightG: 401 }),
      config: ruleConfig({ shotSafetyFactor: 0.8 }),
    })

    expect(resultByCode(evaluation, 'shot_capacity')).toMatchObject({
      status: 'fail',
      actual: 401,
      expected: expect.objectContaining({ maximumG: 400 }),
    })
    expect(resultByCode(evaluation, 'shot_capacity')?.reason).toContain('超过安全射胶量')
  })

  it('marks missing shot data unknown and blocks unattended publishing', () => {
    const evaluation = evaluateInjectionConstraints({
      machine: machine({ maxShotWeightG: null }),
      mold: mold({ grossShotWeightG: null }),
      order: order({ grossShotWeightG: null }),
      config: ruleConfig(),
    })

    expect(resultByCode(evaluation, 'shot_capacity')).toMatchObject({
      status: 'unknown',
      blocking: true,
      autoPublishBlocked: true,
    })
    expect(resultByCode(evaluation, 'shot_capacity')?.missingFields).toEqual(
      expect.arrayContaining(['order/mold.grossShotWeightG', 'machine.maxShotWeightG']),
    )
    expect(evaluation.hasUnknownData).toBe(true)
    expect(evaluation.autoPublishAllowed).toBe(false)
  })

  it('explains fixture, process capability, and material restriction conflicts separately', () => {
    const evaluation = evaluateInjectionConstraints({
      machine: machine({
        supportedFixtures: ['air_cutter'],
        capabilities: ['core_pull'],
        materialRules: [{
          id: 'no-pvc',
          mode: 'deny',
          materialCodes: ['PVC'],
          reason: '该机台不可啤 PVC',
        }],
      }),
      mold: mold({
        fixtureRequirements: ['suction_cup'],
        capabilitiesRequired: ['double_core_pull', 'high_pressure'],
        materialCode: 'PVC',
      }),
      order: order({ materialCode: 'PVC' }),
      config: ruleConfig(),
    })

    expect(resultByCode(evaluation, 'fixtures')?.reason).toContain('SUCTION_CUP')
    expect(resultByCode(evaluation, 'capabilities')?.reason).toContain('两边抽芯')
    expect(resultByCode(evaluation, 'material_restrictions')).toMatchObject({
      status: 'fail',
      reason: '该机台不可啤 PVC',
    })
  })

  it('allows a reviewed manual placement override but still blocks automatic publishing', () => {
    const evaluation = evaluateInjectionConstraints({
      machine: machine(),
      mold: mold({ grossShotWeightG: null }),
      order: order({ grossShotWeightG: null }),
      config: ruleConfig(),
      overrides: {
        shot_capacity: {
          reason: '工程已线下复核，等待主数据回填',
          actorId: 'planner-1',
          actorName: '计划员',
          createdAt: '2026-07-22T08:00:00+08:00',
        },
      },
    })

    expect(resultByCode(evaluation, 'shot_capacity')).toMatchObject({
      status: 'override',
      originalStatus: 'unknown',
      blocking: false,
      autoPublishBlocked: true,
    })
    expect(evaluation.eligible).toBe(true)
    expect(evaluation.hasUnknownData).toBe(true)
    expect(evaluation.autoPublishAllowed).toBe(false)
  })
})
