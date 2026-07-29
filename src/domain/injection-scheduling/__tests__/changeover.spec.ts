import { describe, expect, it } from 'vitest'
import { colorPathMultiplier, evaluateChangeover } from '@/domain/injection-scheduling'
import type { OrderRequirement } from '@/types/injectionScheduling'

function requirement(moldNo: string, color: string, colorFamily: OrderRequirement['colorFamily']): OrderRequirement {
  return {
    productName: '测试产品',
    orderNo: 'ORDER-1',
    color,
    colorFamily,
    material: 'ABS 750NSW',
    priorityCode: 'P2',
    mold: {
      moldNo,
      widthMm: 200,
      heightMm: 200,
      thicknessMm: 180,
      openingStrokeMm: 180,
      ejectionStrokeMm: 60,
      shotWeightGrams: 80,
      material: 'ABS 750NSW',
      armRequirement: 'single-arm',
      state: 'available',
    },
  }
}

describe('injection scheduling changeover rules', () => {
  it('returns zero for same mold and same color', () => {
    const same = requirement('M-1', '本白', 'natural')
    expect(evaluateChangeover('12A', same, same)).toMatchObject({
      status: 'ok',
      moldChangeHours: 0,
      colorChangeHours: 0,
      totalHours: 0,
    })
  })

  it('charges only color change for same mold and different color', () => {
    const result = evaluateChangeover(
      '12A',
      requirement('M-1', '本白', 'natural'),
      requirement('M-1', '黑色', 'black'),
    )
    expect(result.moldChangeHours).toBe(0)
    expect(result.colorChangeHours).toBeGreaterThan(0)
    expect(result.totalHours).toBe(result.colorChangeHours)
  })

  it('charges only mold change for different mold and same color', () => {
    const result = evaluateChangeover(
      '12A',
      requirement('M-1', '本白', 'natural'),
      requirement('M-2', '本白', 'natural'),
    )
    expect(result.moldChangeHours).toBe(1.08)
    expect(result.colorChangeHours).toBe(0)
    expect(result.totalHours).toBe(1.08)
  })

  it('returns missing-rule for an uncovered machine class instead of zero', () => {
    const result = evaluateChangeover(
      '4A',
      requirement('M-1', '本白', 'natural'),
      requirement('M-2', '黑色', 'black'),
    )
    expect(result.status).toBe('missing-rule')
    expect(result.reason).toContain('不能按 0 小时通过')
  })

  it('makes light-to-dark cheaper than dark-to-light', () => {
    expect(colorPathMultiplier('light', 'dark')).toBeLessThan(colorPathMultiplier('dark', 'light'))
  })
})
