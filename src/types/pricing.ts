export type PricingRuleKind = 'percent' | 'fixed' | 'markup'

export interface PricingLine {
  sku: string
  description: string
  qty: number
  unitPrice: number
  productLine?: string
}

export interface PricingInput {
  customerId: string
  lines: PricingLine[]
}

export interface DiscountRule {
  id: string
  label?: string
  productLine?: string
  kind: PricingRuleKind
  value: number
  minQty?: number
}

export interface RebateTier {
  threshold: number
  rate: number
}

export interface PricingContext {
  customerId: string
  customerName: string
  currency: string
  rules: DiscountRule[]
  rebateTiers: RebateTier[]
  taxRate: number
}

export interface LineItemResult extends PricingLine {
  gross: number
  afterDiscount: number
  appliedRules: string[]
}

export interface RebateResult {
  amount: number
  tier?: RebateTier
}

export interface TaxResult {
  amount: number
  rate: number
}

export interface PricingResult {
  lines: LineItemResult[]
  subtotal: number
  rebate: RebateResult
  tax: TaxResult
  total: number
  currency: string
}

export interface SavedPricingQuote {
  id: string
  factoryId: string
  customerId: string
  customerName: string
  projectName: string
  status: string
  input: PricingInput
  context: PricingContext
  result: PricingResult
  createdBy: string
  createdAt: string
}
