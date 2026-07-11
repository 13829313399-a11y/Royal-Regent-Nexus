import { http } from '@/lib/http'
import type {
  DiscountRule,
  PricingContext,
  PricingInput,
  PricingLine,
  PricingResult,
  RebateTier,
  SavedPricingQuote,
} from '@/types/pricing'

interface ApiPricingLine {
  sku: string
  description: string
  qty: number
  unit_price: number
  product_line: string
}

interface ApiPricingContext {
  customer_id: string
  customer_name: string
  currency: string
  rules: Array<{
    id: string
    label: string
    product_line: string
    kind: DiscountRule['kind']
    value: number
    min_qty: number | null
  }>
  rebate_tiers: Array<{ threshold: number; rate: number }>
  tax_rate: number
}

interface ApiPricingResult {
  lines: Array<ApiPricingLine & {
    gross: number
    after_discount: number
    applied_rules: string[]
  }>
  subtotal: number
  rebate: { amount: number; tier: RebateTier | null }
  tax: { amount: number; rate: number }
  total: number
  currency: string
}

interface ApiPricingQuote {
  id: string
  factory_id: string
  customer_id: string
  customer_name: string
  project_name: string
  status: string
  input: { customer_id: string; lines: ApiPricingLine[] }
  context: ApiPricingContext
  result: ApiPricingResult
  created_by: string
  created_at: string
}

function toLine(line: ApiPricingLine): PricingLine {
  return {
    sku: line.sku,
    description: line.description,
    qty: line.qty,
    unitPrice: line.unit_price,
    ...(line.product_line ? { productLine: line.product_line } : {}),
  }
}

function fromLine(line: PricingLine): ApiPricingLine {
  return {
    sku: line.sku,
    description: line.description,
    qty: line.qty,
    unit_price: line.unitPrice,
    product_line: line.productLine ?? '',
  }
}

function toContext(context: ApiPricingContext): PricingContext {
  return {
    customerId: context.customer_id,
    customerName: context.customer_name,
    currency: context.currency,
    rules: context.rules.map((rule) => ({
      id: rule.id,
      label: rule.label,
      kind: rule.kind,
      value: rule.value,
      ...(rule.product_line ? { productLine: rule.product_line } : {}),
      ...(rule.min_qty !== null ? { minQty: rule.min_qty } : {}),
    })),
    rebateTiers: context.rebate_tiers,
    taxRate: context.tax_rate,
  }
}

function toResult(result: ApiPricingResult): PricingResult {
  return {
    lines: result.lines.map((line) => ({
      ...toLine(line),
      gross: line.gross,
      afterDiscount: line.after_discount,
      appliedRules: line.applied_rules,
    })),
    subtotal: result.subtotal,
    rebate: {
      amount: result.rebate.amount,
      ...(result.rebate.tier ? { tier: result.rebate.tier } : {}),
    },
    tax: result.tax,
    total: result.total,
    currency: result.currency,
  }
}

function fromResult(result: PricingResult): ApiPricingResult {
  return {
    lines: result.lines.map((line) => ({
      ...fromLine(line),
      gross: line.gross,
      after_discount: line.afterDiscount,
      applied_rules: line.appliedRules,
    })),
    subtotal: result.subtotal,
    rebate: { amount: result.rebate.amount, tier: result.rebate.tier ?? null },
    tax: result.tax,
    total: result.total,
    currency: result.currency,
  }
}

function toQuote(quote: ApiPricingQuote): SavedPricingQuote {
  return {
    id: quote.id,
    factoryId: quote.factory_id,
    customerId: quote.customer_id,
    customerName: quote.customer_name,
    projectName: quote.project_name,
    status: quote.status,
    input: { customerId: quote.input.customer_id, lines: quote.input.lines.map(toLine) },
    context: toContext(quote.context),
    result: toResult(quote.result),
    createdBy: quote.created_by,
    createdAt: quote.created_at,
  }
}

export const pricingApi = {
  async getContext(customerId: string, factoryId: string) {
    const response = await http.get<ApiPricingContext>('/pricing/context', {
      params: { customer_id: customerId, factory_id: factoryId },
    })
    return toContext(response.data)
  },
  async listQuotes(factoryId: string, customerId?: string) {
    const response = await http.get<ApiPricingQuote[]>('/pricing/quotes', {
      params: { factory_id: factoryId, ...(customerId ? { customer_id: customerId } : {}) },
    })
    return response.data.map(toQuote)
  },
  async createQuote(payload: {
    factoryId: string
    projectName: string
    input: PricingInput
    localResult: PricingResult
  }) {
    const response = await http.post<ApiPricingQuote>('/pricing/quotes', {
      factory_id: payload.factoryId,
      customer_id: payload.input.customerId,
      project_name: payload.projectName,
      lines: payload.input.lines.map(fromLine),
      local_result: fromResult(payload.localResult),
    })
    return toQuote(response.data)
  },
}
