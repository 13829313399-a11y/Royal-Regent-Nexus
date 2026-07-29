import { describe, expect, it } from 'vitest'
import { evaluateMachineEligibility } from '@/domain/injection-scheduling'
import type { InjectionMachine, OrderRequirement } from '@/types/injectionScheduling'

function machine(overrides: Partial<InjectionMachine['capability']> = {}): InjectionMachine {
  return {
    id: 'm-1',
    name: '测试机',
    code: 'T01',
    workshop: '测试区',
    kind: '高速机',
    restriction: '标准机台',
    load: 70,
    state: 'running',
    resourceState: 'available',
    taskIds: [],
    capability: {
      machineClass: '12A',
      tonnage: 150,
      shotCapacityGrams: 300,
      safetyUtilization: 0.8,
      tieBarWidthMm: 450,
      tieBarHeightMm: 450,
      minMoldThicknessMm: 120,
      maxMoldThicknessMm: 420,
      openingStrokeMm: 380,
      ejectionStrokeMm: 120,
      armType: 'multi-arm',
      supportsCorePull: true,
      supportsUnscrewing: true,
      compatibleMaterials: ['ABS', 'PP', 'PC', 'PVC'],
      screwType: 'standard',
      ...overrides,
    },
  }
}

function requirement(overrides: Partial<OrderRequirement['mold']> = {}): OrderRequirement {
  return {
    productName: '测试产品',
    orderNo: 'ORDER-1',
    color: '本白',
    colorFamily: 'natural',
    material: 'ABS 750NSW',
    priorityCode: 'P2',
    mold: {
      moldNo: 'MOLD-1',
      widthMm: 300,
      heightMm: 280,
      thicknessMm: 220,
      openingStrokeMm: 240,
      ejectionStrokeMm: 80,
      shotWeightGrams: 180,
      material: 'ABS 750NSW',
      armRequirement: 'single-arm',
      requiresCorePull: false,
      requiresUnscrewing: false,
      state: 'available',
      ...overrides,
    },
  }
}

describe('injection scheduling hard eligibility', () => {
  it('rejects a mold when shot weight exceeds effective shot capacity', () => {
    const result = evaluateMachineEligibility({
      machine: machine(),
      requirement: requirement({ shotWeightGrams: 260 }),
    })
    expect(result.status).toBe('ineligible')
    expect(result.checks.find((check) => check.code === 'shot-capacity')).toMatchObject({ passed: false, severity: 'hard' })
  })

  it('does not allow a multi-arm requirement on a single-arm machine', () => {
    const result = evaluateMachineEligibility({
      machine: machine({ armType: 'single-arm' }),
      requirement: requirement({ armRequirement: 'multi-arm' }),
    })
    expect(result.eligible).toBe(false)
    expect(result.checks.find((check) => check.code === 'robot-arm')?.reason).toContain('能力不足')
  })

  it('enforces PVC, PC and transparent-only material/color restrictions', () => {
    const pcOnPvc = evaluateMachineEligibility({
      machine: machine({ compatibleMaterials: ['PVC'], screwType: 'PVC' }),
      requirement: { ...requirement(), material: 'PC 透明料' },
    })
    const darkOnTransparent = evaluateMachineEligibility({
      machine: machine({ transparentOnly: true, screwType: 'transparent' }),
      requirement: { ...requirement(), color: '黑色', colorFamily: 'black' },
    })
    expect(pcOnPvc.checks.find((check) => check.code === 'material-screw')?.passed).toBe(false)
    expect(darkOnTransparent.checks.find((check) => check.code === 'transparent-only')?.passed).toBe(false)
  })

  it('rejects core-pull work on a machine without core-pull support', () => {
    const result = evaluateMachineEligibility({
      machine: machine({ supportsCorePull: false }),
      requirement: requirement({ requiresCorePull: true }),
    })
    expect(result.checks.find((check) => check.code === 'core-pull')).toMatchObject({ passed: false })
  })

  it('returns incomplete when critical mold dimensions or shot weight are missing', () => {
    const result = evaluateMachineEligibility({
      machine: machine(),
      requirement: requirement({ widthMm: undefined, heightMm: undefined, shotWeightGrams: undefined }),
    })
    expect(result.status).toBe('incomplete')
    expect(result.complete).toBe(false)
    expect(result.eligible).toBe(false)
  })
})
