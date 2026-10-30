import type { CartonOrderResponse } from '@/api/cartonProcurement'
import type { SplitContext, SplitTargetInput } from '@/api/cartonOrderSplits'
import { paperDemands } from './paperQuantity'

export interface SplitDraftTarget {
  contract_no: string
  customer_po: string
  product_quantity: string | number | null
  lines: Array<{ order_line_id: string; quantity: string | number }>
}
const scale = 10000n
const countUnits = new Set(['张', '个', '件', '只', '箱'])
function decimal(value: string | number | null, places = 4): bigint | null {
  const raw = String(value ?? '').trim()
  const match = /^(\d+)(?:\.(\d*))?$/.exec(raw)
  if (!match || (match[2]?.length ?? 0) > places || match[1]!.length > 14) return null
  return BigInt(match[1]!) * 10n ** BigInt(places) + BigInt((match[2] ?? '').padEnd(places, '0'))
}
function text(value: bigint) {
  const fraction = String(value % scale).padStart(4, '0').replace(/0+$/, '')
  return `${value / scale}${fraction ? `.${fraction}` : ''}`
}
const min = (left: bigint, right: bigint) => left < right ? left : right
const nonnegative = (value: bigint) => value > 0n ? value : 0n
export function conversionPending(context: SplitContext, lineId: string, pending: string) {
  const quantities = [pending, ...context.plans.filter(p => p.status !== 'CANCELLED').flatMap(p => p.targets.flatMap(t => t.lines.filter(l => l.order_line_id === lineId).map(l => l.pending_remaining)))]
  const values = quantities.map(value => decimal(value))
  return values.some(value => value === null) ? '0' : text(values.reduce<bigint>((sum, value) => sum + (value ?? 0n), 0n))
}
export function splitQuantityEditable(order: CartonOrderResponse, lineId: string) {
  return order.quantity_basis === 'EXPLICIT' || order.lines.find(line => line.id === lineId)?.quantity_rule?.manual_quantity != null
}

export function splitRemaining(required: string, quantities: string[]) {
  const total = decimal(required)
  const parts = quantities.map(value => decimal(value))
  if (total == null || parts.some(value => value == null)) return '—'
  const remaining = total - parts.reduce<bigint>((sum, value) => sum + (value ?? 0n), 0n)
  return remaining < 0n ? '超出需求' : text(remaining)
}

/** Context already subtracts reserved pending arrivals. Only pending warehouse plans reserve physical stock. */
export function allocateSplitTargets(order: CartonOrderResponse, context: SplitContext, drafts: SplitDraftTarget[]) {
  const remaining = new Map(context.lines.map(line => [line.order_line_id, {
    pending: decimal(line.pending_available) ?? 0n,
    positions: line.positions.map(position => ({ ...position, available: decimal(position.balance) ?? 0n })),
  }]))
  for (const plan of context.plans.filter(plan => plan.status === 'PENDING_WAREHOUSE')) {
    for (const target of plan.targets) for (const line of target.lines) for (const part of line.stock) {
      const position = remaining.get(line.order_line_id)?.positions.find(row => row.location_id === part.location_id)
      if (position) position.available = nonnegative(position.available - (decimal(part.quantity) ?? 0n))
    }
  }
  const errors: string[] = []
  let productTotal = context.plans.filter(plan => plan.status !== 'CANCELLED').reduce((sum, plan) =>
    sum + plan.targets.reduce((total, target) => total + (decimal(target.product_quantity, 6) ?? 0n), 0n), 0n)
  const details: Array<Array<{ quantity: string; pending: string; stock: string; available: string; error: string }>> = []
  const targets: SplitTargetInput[] = drafts.map((draft, targetIndex) => {
    const products = decimal(draft.product_quantity, 6)
    const hasProducts = draft.product_quantity != null && String(draft.product_quantity).trim() !== ''
    if ((order.quantity_basis !== 'EXPLICIT' || hasProducts) && (products == null || products <= 0n)) {
      errors.push(`拆分 ${targetIndex + 1}：请填写有效产品数量，最多六位小数`)
    }
    productTotal += products ?? 0n
    const demands = paperDemands(draft.product_quantity, order.lines.map(paper => ({ ...paper,
      quantity_rule: paper.quantity_rule?.manual_quantity != null ? { ...paper.quantity_rule,
        manual_quantity: draft.lines.find(line => line.order_line_id === paper.id)?.quantity ?? '' } : paper.quantity_rule,
    })))
    details[targetIndex] = []
    const lines = draft.lines.map((draftLine, lineIndex) => {
      const paperIndex = order.lines.findIndex(paper => paper.id === draftLine.order_line_id)
      const source = context.lines.find(line => line.order_line_id === draftLine.order_line_id)
      const capacity = remaining.get(draftLine.order_line_id)
      const manual = splitQuantityEditable(order, draftLine.order_line_id)
      const demand = demands[paperIndex]
      const quantity = manual ? draftLine.quantity : demand?.actual ?? ''
      const amount = decimal(quantity)
      const available = capacity ? capacity.pending + capacity.positions.reduce((sum, position) => sum + position.available, 0n) : 0n
      let error = !source || !capacity || paperIndex < 0 ? '原纸品已变化，请重新打开拆单' :
        !manual && demand?.error ? demand.error :
          amount == null ? '请填写有效拆分数量，最多四位小数' :
            countUnits.has(source.unit) && amount % scale !== 0n ? '该纸品单位的拆分数量必须为整数' :
              amount > available ? `拆分数量超过剩余可分配 ${text(available)} ${source.unit}` : ''
      const pending = capacity ? min(amount ?? 0n, capacity.pending) : 0n
      let stockNeeded = nonnegative((amount ?? 0n) - pending)
      if (capacity) capacity.pending -= pending
      const stock = (capacity?.positions ?? []).flatMap(position => {
        const allocated = min(stockNeeded, position.available)
        if (!allocated) return []
        if (!position.location_id || position.position_revision == null) {
          error ||= '仓位信息不完整，请刷新后重新核对'
          return []
        }
        position.available -= allocated
        stockNeeded -= allocated
        return [{ location_id: position.location_id, expected_position_revision: position.position_revision, quantity: text(allocated) }]
      })
      if (error) errors.push(`拆分 ${targetIndex + 1} · 纸品 ${lineIndex + 1}：${error}`)
      details[targetIndex]!.push({ quantity: amount == null ? String(quantity) : text(amount), pending: text(pending),
        stock: text(stock.reduce((sum, part) => sum + (decimal(part.quantity) ?? 0n), 0n)), available: text(available), error })
      return { order_line_id: draftLine.order_line_id, pending_quantity: text(pending), stock }
    })
    if (!lines.some(line => (decimal(line.pending_quantity) ?? 0n) > 0n || line.stock.length)) errors.push(`拆分 ${targetIndex + 1}：请填写大于零的拆分数量`)
    return { contract_no: draft.contract_no, customer_po: draft.customer_po,
      product_quantity: hasProducts ? draft.product_quantity : null, lines }
  })
  const productCapacity = decimal(order.product_order_quantity, 6)
  if (productCapacity != null && productTotal > productCapacity) errors.push('拆分产品数量超过原订单剩余可分配数量')
  return { targets, details, errors }
}
