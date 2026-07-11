import type { PricingContext, PricingInput, PricingResult } from '@/types/pricing'
import { calcRebate } from './rebate'
import { roundMoney } from './rounding'
import { applyRules } from './rules'
import { calcTax } from './tax'

export function runPricing(input: PricingInput, context: PricingContext): PricingResult {
  const lines = input.lines.map((line) => {
    const normalizedLine = { ...line }
    const gross = normalizedLine.qty * normalizedLine.unitPrice
    const ruleResult = applyRules(gross, normalizedLine, context)

    return {
      ...normalizedLine,
      gross: roundMoney(gross),
      afterDiscount: roundMoney(ruleResult.amount),
      appliedRules: ruleResult.appliedRules,
    }
  })
  const subtotal = roundMoney(lines.reduce((sum, line) => sum + line.afterDiscount, 0))
  const rebate = calcRebate(subtotal, context)
  const taxable = roundMoney(subtotal - rebate.amount)
  const tax = calcTax(taxable, context)

  return {
    lines,
    subtotal,
    rebate,
    tax,
    total: roundMoney(taxable + tax.amount),
    currency: context.currency,
  }
}
