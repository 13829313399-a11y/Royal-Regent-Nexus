import type { AIBusinessResult, AICartonProcurementSummary } from '../types'
import { productionFactoryContextIds } from '@/data/enterpriseMock'
import { boundedInteger, boundedText, bool, hasExactKeys, localId, record, safeLinks, text } from './contracts'


export function isCartonProcurementResultCandidate(source: Record<string, unknown>) {
  const resultType = typeof source.result_type === 'string' ? source.result_type : ''
  const schemaVersion = typeof source.schema_version === 'string' ? source.schema_version : ''
  return resultType === 'carton_procurement'
    || resultType.startsWith('carton_procurement.')
    || schemaVersion === 'carton-procurement'
    || schemaVersion.startsWith('carton-procurement-')
}

export function extractCartonProcurementResult(
  source: Record<string, unknown>,
): AIBusinessResult | null {
  if (!hasExactKeys(source, [
    'schema_version', 'result_type', 'source_type', 'factory_id', 'as_of',
    'total', 'limit', 'offset', 'returned', 'truncated', 'orders',
  ])) return null
  if (
    source.result_type !== 'carton_procurement.summary_list'
    || source.schema_version !== 'carton-procurement-summary-v1'
    || source.source_type !== 'FORMAL'
  ) return null
  const factoryId = boundedText(source.factory_id, 1, 64)
  const asOf = boundedText(source.as_of, 1, 40)
  const total = boundedInteger(source.total, 0, Number.MAX_SAFE_INTEGER)
  const returned = boundedInteger(source.returned, 0, 20)
  const limit = boundedInteger(source.limit, 1, 20)
  const offset = boundedInteger(source.offset, 0, 10_000)
  const rawOrders = Array.isArray(source.orders) ? source.orders : null
  if (
    !factoryId
    || !productionFactoryContextIds.includes(factoryId as (typeof productionFactoryContextIds)[number])
    || !asOf
    || total === null
    || returned === null
    || limit === null
    || offset === null
    || rawOrders === null
    || rawOrders.length > 20
    || returned !== rawOrders.length
    || total < returned
    || typeof source.truncated !== 'boolean'
    || source.truncated !== (offset + returned < total)
  ) return null

  const orders: AICartonProcurementSummary[] = []
  for (const rawOrder of rawOrders) {
    const order = record(rawOrder)
    if (!order || !hasExactKeys(order, [
      'order_id', 'order_no', 'customer_name', 'contract_no', 'item_no',
      'product_name', 'order_date', 'due_date', 'status', 'revision', 'updated_at',
    ])) return null
    const orderId = boundedText(order.order_id, 1, 96)
    const orderNo = boundedText(order.order_no, 1, 64)
    const customerName = boundedText(order.customer_name, 0, 255)
    const contractNo = boundedText(order.contract_no, 0, 128)
    const itemNo = boundedText(order.item_no, 0, 128)
    const productName = boundedText(order.product_name, 0, 255)
    const orderDate = boundedText(order.order_date, 0, 10)
    const dueDate = boundedText(order.due_date, 0, 10)
    const status = boundedText(order.status, 1, 32)
    const revision = boundedInteger(order.revision, 1, Number.MAX_SAFE_INTEGER)
    const updatedAt = boundedText(order.updated_at, 0, 40)
    if (
      !orderId
      || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$/.test(orderId)
      || !orderNo
      || customerName === null
      || contractNo === null
      || itemNo === null
      || productName === null
      || orderDate === null
      || dueDate === null
      || !status
      || revision === null
      || updatedAt === null
    ) return null
    orders.push({
      orderId, orderNo, customerName, contractNo, itemNo, productName,
      orderDate, dueDate, status, revision, updatedAt,
    })
  }
  return {
    id: localId('result'),
    kind: 'carton_procurement_list',
    title: '纸箱采购摘要',
    summary: `本次返回 ${returned} 条，共 ${total} 条。`,
    sourceType: 'FORMAL',
    factoryId,
    asOf,
    truncated: source.truncated,
    links: [],
    cartonProcurement: { total, returned, limit, offset, orders },
  }
}
