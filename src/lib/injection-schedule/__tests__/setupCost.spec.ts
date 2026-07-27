import { describe, expect, it } from 'vitest'
import { calculateInjectionSetupCost } from '@/lib/injection-schedule/setupCost'
import type {
  InjectionSetupProfile,
  InjectionSetupRuleConfig,
} from '@/types/injectionSchedule'

const config: InjectionSetupRuleConfig = {
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
}

function profile(overrides: Partial<InjectionSetupProfile> = {}): InjectionSetupProfile {
  return {
    moldId: 'MOLD-001',
    productName: '产品 A',
    materialCode: 'PP',
    colorCode: 'WHITE',
    colorRank: 1,
    ...overrides,
  }
}

describe('injection setup cost', () => {
  it('makes adjacent same-mold work zero-cost when material and color are unchanged', () => {
    const sameMold = calculateInjectionSetupCost({
      previous: profile(),
      next: profile({ productName: '产品 A 的另一订单' }),
      config,
    })
    const changedMold = calculateInjectionSetupCost({
      previous: profile(),
      next: profile({ moldId: 'MOLD-002' }),
      config,
    })

    expect(sameMold).toMatchObject({
      totalMinutes: 0,
      moldChangeMinutes: 0,
      materialChangeMinutes: 0,
      colorChangeMinutes: 0,
      sameMold: true,
    })
    expect(changedMold.moldChangeMinutes).toBe(60)
    expect(sameMold.totalMinutes).toBeLessThan(changedMold.totalMinutes)
  })

  it('costs light-to-dark conversion less than the reverse direction', () => {
    const lightToDark = calculateInjectionSetupCost({
      previous: profile({ colorCode: 'WHITE', colorRank: 1 }),
      next: profile({ colorCode: 'BLACK', colorRank: 9 }),
      config,
    })
    const darkToLight = calculateInjectionSetupCost({
      previous: profile({ colorCode: 'BLACK', colorRank: 9 }),
      next: profile({ colorCode: 'WHITE', colorRank: 1 }),
      config,
    })

    expect(lightToDark.colorDirection).toBe('light_to_dark')
    expect(darkToLight.colorDirection).toBe('dark_to_light')
    expect(lightToDark.colorChangeMinutes).toBe(10)
    expect(darkToLight.colorChangeMinutes).toBe(45)
    expect(lightToDark.totalMinutes).toBeLessThan(darkToLight.totalMinutes)
  })

  it('uses the factory color matrix before the generic light/dark rule', () => {
    const matrixConfig: InjectionSetupRuleConfig = {
      ...config,
      colorTransitionMatrix: [{
        fromColorCode: 'WHITE',
        toColorCode: 'BLACK',
        minutes: 6,
      }],
    }
    const result = calculateInjectionSetupCost({
      previous: profile({ colorCode: 'white', colorRank: 1 }),
      next: profile({ colorCode: 'black', colorRank: 9 }),
      config: matrixConfig,
    })

    expect(result.colorDirection).toBe('matrix')
    expect(result.colorChangeMinutes).toBe(6)
    expect(result.reasons.join(' ')).toContain('按厂区矩阵转色')
  })

  it('supports a recorded manual color exception and rejects reasonless overrides', () => {
    const result = calculateInjectionSetupCost({
      previous: profile({ colorCode: 'BLACK', colorRank: 9 }),
      next: profile({ colorCode: 'WHITE', colorRank: 1 }),
      config,
      colorOverride: {
        colorTransitionMinutes: 12,
        reason: '已安排专用洗机料',
        actorId: 'planner-1',
      },
    })

    expect(result.colorChangeMinutes).toBe(12)
    expect(result.colorOverride).toEqual({
      colorTransitionMinutes: 12,
      reason: '已安排专用洗机料',
      actorId: 'planner-1',
    })
    expect(result.reasons.join(' ')).toContain('人工例外')

    expect(() => calculateInjectionSetupCost({
      previous: profile({ colorCode: 'BLACK', colorRank: 9 }),
      next: profile({ colorCode: 'WHITE', colorRank: 1 }),
      config,
      colorOverride: {
        colorTransitionMinutes: 12,
        reason: '   ',
        actorId: 'planner-1',
      },
    })).toThrow('颜色转换人工例外必须填写原因')
  })

  it('uses adjacent material-transition matrix entries rather than a physical worksheet row', () => {
    const matrixConfig: InjectionSetupRuleConfig = {
      ...config,
      materialTransitionMatrix: [{
        fromMaterialCode: 'PP',
        toMaterialCode: 'PC',
        minutes: 75,
      }],
    }
    const result = calculateInjectionSetupCost({
      previous: profile({ materialCode: 'PP' }),
      next: profile({ materialCode: 'PC' }),
      config: matrixConfig,
    })

    expect(result.materialChangeMinutes).toBe(75)
    expect(result.reasons.join(' ')).toContain('按厂区矩阵换料')
  })
})
