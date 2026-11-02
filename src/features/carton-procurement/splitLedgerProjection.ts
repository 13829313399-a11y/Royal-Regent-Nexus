import type { CartonOrderResponse } from '@/api/cartonProcurement'

export interface SplitLedgerLine {
  orderLineId: string
  targetLineId?: string
  packagingType: string
  paperQuality: string
  specification: string
  unit: string
  quantity: string
  received: string
  remaining: string
}
export interface SplitLedgerMetrics { productQuantity: string | null; lines: SplitLedgerLine[] }
export interface SplitLedgerChild extends SplitLedgerMetrics {
  key: string
  planId: string
  targetIndex: number
  contractNo: string
  customerPo: string
  status: 'ACTIVE' | 'PENDING_WAREHOUSE'
}
export interface SplitLedgerProjection {
  valid: boolean
  errors: string[]
  original: SplitLedgerMetrics
  parent: SplitLedgerMetrics
  children: SplitLedgerChild[]
}

function amount(value: unknown, places = 4): bigint {
  const match = /^(\d+)(?:\.(\d*))?$/.exec(String(value ?? '').trim())
  // Persisted Decimal values may have insignificant trailing zeroes.
  const fraction = (match?.[2] || '').replace(/0+$/, '')
  if (!match || fraction.length > places || match[1]!.length > 18) throw new Error('数量无效或精度超出范围')
  return BigInt(match[1]!) * 10n ** BigInt(places) + BigInt(fraction.padEnd(places, '0'))
}
function text(value: bigint, places = 4): string {
  const scale = 10n ** BigInt(places)
  const fraction = String(value % scale).padStart(places, '0').replace(/0+$/, '')
  return `${value / scale}${fraction ? `.${fraction}` : ''}`
}
const positiveRemainder = (quantity: bigint, received: bigint) => text(quantity > received ? quantity - received : 0n)
const optionalProduct = (value: unknown) => value == null || value === '' ? null : amount(value, 6)

/** Read-only allocation rows; they never represent additional procurement or receipt documents. */
export function projectSplitLedger(order: CartonOrderResponse): SplitLedgerProjection {
  const original: SplitLedgerMetrics = { productQuantity: null, lines: [] }
  const failure = (message: string): SplitLedgerProjection => ({ valid: false,
    errors: [`拆单数量待核实：${message}`], original, parent: original, children: [] })
  try {
    const product = optionalProduct(order.product_order_quantity)
    const lineIds = new Set<string>()
    const originalLines = order.lines.map(line => {
      if (!line.id || lineIds.has(line.id)) throw new Error('原订单纸品身份不唯一')
      lineIds.add(line.id)
      const quantity = amount(line.required_quantity), received = amount(line.received_quantity)
      return { orderLineId: line.id, packagingType: line.packaging_type, paperQuality: line.paper_quality,
        specification: line.specification, unit: line.unit, quantity: text(quantity), received: text(received),
        remaining: positiveRemainder(quantity, received) }
    })
    original.productQuantity = product == null ? null : text(product, 6)
    original.lines = originalLines
    const parent = { productQuantity: original.productQuantity, lines: originalLines.map(line => ({ ...line })) }
    const balances = new Map(originalLines.map(line => [line.orderLineId,
      { quantity: amount(line.quantity), received: amount(line.received), reserved: 0n, source: line }]))
    const children: SplitLedgerChild[] = []
    const planIds = new Set<string>(), targetLineIds = new Set<string>()
    let activeProducts = 0n, reservedProducts = 0n, unknownActiveProducts = false
    for (const plan of order.split_records || []) {
      if (plan.order_id !== order.id || plan.factory_id !== order.factory_id ||
          plan.customer_code !== order.customer_code || plan.item_no !== order.item_no || plan.status === 'CANCELLED') continue
      if (!plan.id || planIds.has(plan.id)) throw new Error('拆单记录身份重复')
      if (plan.status !== 'ACTIVE' && plan.status !== 'PENDING_WAREHOUSE') throw new Error('拆单状态未知')
      planIds.add(plan.id)
      if (!plan.targets.length) throw new Error('拆单缺少去向')
      for (const [targetIndex, target] of plan.targets.entries()) {
        if (!target.contract_no.trim() || !target.lines.length) throw new Error('拆单去向或纸品不完整')
        const childProduct = optionalProduct(target.product_quantity)
        if (childProduct != null && childProduct <= 0n) throw new Error('拆分产品数量必须大于零')
        reservedProducts += childProduct ?? 0n
        const ownLines = new Set<string>()
        const child: SplitLedgerChild = { key: JSON.stringify([order.id, plan.id, targetIndex]), planId: plan.id,
          targetIndex, contractNo: target.contract_no, customerPo: target.customer_po,
          status: plan.status, productQuantity: childProduct == null ? null : text(childProduct, 6), lines: [] }
        for (const line of target.lines) {
          const balance = balances.get(line.order_line_id)
          if (!balance || ownLines.has(line.order_line_id) || !line.target_line_id || targetLineIds.has(line.target_line_id)) {
            throw new Error('拆单纸品身份缺失或重复')
          }
          ownLines.add(line.order_line_id)
          targetLineIds.add(line.target_line_id)
          if (line.unit !== balance.source.unit || line.packaging_type !== balance.source.packagingType ||
              line.paper_quality !== balance.source.paperQuality || line.specification !== balance.source.specification) {
            throw new Error('拆单纸品与原单不一致')
          }
          const pending = amount(line.pending_quantity)
          const stock = line.stock.reduce((sum, part) => sum + amount(part.quantity), 0n)
          const arrived = amount(line.received_quantity)
          if (['张', '个', '件', '只', '箱'].includes(line.unit) &&
              [pending, arrived, ...line.stock.map(part => amount(part.quantity))].some(value => value % 10000n !== 0n)) {
            throw new Error('计件纸品的拆分数量必须为整数')
          }
          if (arrived > pending) throw new Error('拆单待到分配超过计划数量')
          const quantity = pending + stock
          const received = plan.status === 'ACTIVE' ? arrived + stock : 0n
          balance.reserved += quantity
          if (balance.reserved > amount(balance.source.quantity)) throw new Error('拆单分配数量超过原单数量')
          child.lines.push({ ...balance.source, targetLineId: line.target_line_id,
            quantity: text(quantity), received: text(received), remaining: positiveRemainder(quantity, received) })
          if (plan.status === 'ACTIVE') {
            balance.quantity -= quantity
            balance.received -= received
            if (balance.quantity < 0n || balance.received < 0n) throw new Error('生效拆单数量超过原单数量或到货数量')
          }
        }
        if (!child.lines.some(line => amount(line.quantity) > 0n)) throw new Error('拆单数量必须大于零')
        if (plan.status === 'ACTIVE') {
          activeProducts += childProduct ?? 0n
          unknownActiveProducts ||= childProduct == null
        }
        children.push(child)
      }
    }
    if (product != null && reservedProducts > product) throw new Error('拆分产品数量超过原单')
    parent.productQuantity = product == null || unknownActiveProducts ? null : text(product - activeProducts, 6)
    parent.lines = originalLines.map(line => {
      const balance = balances.get(line.orderLineId)!
      return { ...line, quantity: text(balance.quantity), received: text(balance.received),
        remaining: positiveRemainder(balance.quantity, balance.received) }
    })
    return { valid: true, errors: [], original, parent, children }
  } catch (error) {
    return failure(error instanceof Error ? error.message : '记录格式无效')
  }
}
