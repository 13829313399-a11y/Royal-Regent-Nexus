import type { DiscountRule, PricingContext, PricingLine } from '@/types/pricing'

const RULE_ORDER: Record<DiscountRule['kind'], number> = {
  markup: 0,
  percent: 1,
  fixed: 2,
}

function matchesRule(rule: DiscountRule, line: PricingLine) {
  if (rule.productLine && rule.productLine !== line.productLine) {
    return false
  }

  return rule.minQty === undefined || line.qty >= rule.minQty
}

export function applyRules(gross: number, line: PricingLine, context: PricingContext) {
  let amount = gross
  const appliedRules: string[] = []
  const orderedRules = context.rules
    .map((rule, index) => ({ rule, index }))
    .sort((left, right) => RULE_ORDER[left.rule.kind] - RULE_ORDER[right.rule.kind] || left.index - right.index)
    .map(({ rule }) => rule)

  orderedRules.forEach((rule) => {
    if (!matchesRule(rule, line)) {
      return
    }

    if (rule.kind === 'markup') {
      amount += rule.value
    } else if (rule.kind === 'percent') {
      amount -= amount * (rule.value / 100)
    } else {
      amount -= rule.value
    }
    appliedRules.push(rule.id)
  })

  return { amount: Math.max(0, amount), appliedRules }
}
