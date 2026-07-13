import type { PricingContext, TaxResult } from '@/types/pricing'
import { roundMoney } from './rounding'

export function calcTax(taxable: number, context: PricingContext): TaxResult {
  return {
    amount: roundMoney(Math.max(0, taxable) * (context.taxRate / 100)),
    rate: context.taxRate,
  }
}
