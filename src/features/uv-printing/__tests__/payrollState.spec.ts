import { describe, expect, it } from 'vitest'
import { PAYROLL_STATE } from '../domain/status'

describe('工资调整状态', () => {
  it('adjusted 是有效的已调整工资，不显示为未定价', () => {
    expect(PAYROLL_STATE.adjusted).toEqual({ label: '已调整', tone: 'blue' })
    expect(PAYROLL_STATE.adjusted.label).not.toBe(PAYROLL_STATE.unpriced.label)
  })
})
