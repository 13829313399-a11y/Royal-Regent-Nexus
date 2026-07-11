import type { PricingContext, RebateResult } from '@/types/pricing'
import { roundMoney } from './rounding'

export function calcRebate(subtotal: number, context: PricingContext): RebateResult {
  const tier = [...context.rebateTiers]
    .sort((left, right) => left.threshold - right.threshold)
    .filter((candidate) => candidate.threshold <= subtotal)
    .at(-1)

  return {
    amount: tier ? roundMoney(subtotal * (tier.rate / 100)) : 0,
    ...(tier ? { tier: { ...tier } } : {}),
  }
}
