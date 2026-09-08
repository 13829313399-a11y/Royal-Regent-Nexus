import { describe, expect, it } from 'vitest'
import { estimateMoney, moneyLabel, moneyTotals } from '../cartonInventoryMoney'

describe('inventory money display', () => {
  const cost = { cost_status: '已计价', cost_currency: 'CNY', cost_unit_price: '1.005' }
  it('rounds decimal half cents without binary floating point and supports exponents', () => {
    expect(moneyLabel(estimateMoney(cost, 1))).toBe('CNY 1.01')
    expect(moneyLabel(estimateMoney({ ...cost, cost_unit_price: '5E-3' }, 1))).toBe('CNY 0.01')
    expect(moneyLabel(estimateMoney({ ...cost, cost_unit_price: '0' }, 1))).toBe('CNY 0.00')
  })
  it('keeps currencies separate and marks partial totals', () => {
    const result = moneyTotals([{ ...cost, cost_amount: '0.10' }, { ...cost, cost_amount: '0.20' },
      { ...cost, cost_currency: 'HKD', cost_amount: '5' }, { cost_status: '待核价' }])
    expect(result).toEqual({ amounts: ['CNY 0.30', 'HKD 5.00'], pending: 1 })
    expect(moneyLabel(estimateMoney({ cost_status: '待核价' }, 5))).toBe('待核价')
  })
  it('preserves signed reversal amounts and large exact values', () => {
    expect(moneyLabel({ ...cost, cost_amount: '-1.005' })).toBe('CNY -1.01')
    expect(moneyLabel({ ...cost, cost_amount: '9007199254740993.01' })).toBe('CNY 9007199254740993.01')
    expect(moneyLabel(estimateMoney(cost, ''))).toBe('请填写数量')
  })
})
