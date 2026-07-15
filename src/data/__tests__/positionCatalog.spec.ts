import { describe, expect, it } from 'vitest'
import { getPositionSuggestions, positionSuggestionsByDepartment } from '../positionCatalog'

describe('position catalog', () => {
  it('offers multiple department-specific suggestions without restricting free-text positions', () => {
    expect(getPositionSuggestions('engineering')).toContain('工程部技术员')
    expect(getPositionSuggestions('engineering')).toContain('工程师')
    expect(getPositionSuggestions('production')).toContain('啤机技术员')
    expect(getPositionSuggestions('qa')).toContain('QA 检验员')
    expect(getPositionSuggestions('sales-business')).toContain('车间业务跟客')
    expect(getPositionSuggestions('accounting')).toContain('会计主管')
    expect(Object.values(positionSuggestionsByDepartment).every((items) => items.length >= 8)).toBe(true)
  })

  it('returns no suggestions for an unknown department', () => {
    expect(getPositionSuggestions('unknown-department')).toEqual([])
  })
})
