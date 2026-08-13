import type { AIBusinessResult, AIMoldingSampleSummary } from '../types'
import { productionFactoryContextIds } from '@/data/enterpriseMock'
import { boundedInteger, boundedText, bool, hasExactKeys, localId, record, safeLinks, text } from './contracts'


export function isMoldingSampleResultCandidate(source: Record<string, unknown>) {
  const resultType = typeof source.result_type === 'string' ? source.result_type : ''
  const schemaVersion = typeof source.schema_version === 'string' ? source.schema_version : ''
  return resultType === 'molding_sample'
    || resultType.startsWith('molding_sample.')
    || schemaVersion === 'molding-sample'
    || schemaVersion.startsWith('molding-sample-')
}

export function extractMoldingSampleResult(
  source: Record<string, unknown>,
): AIBusinessResult | null {
  if (!hasExactKeys(source, [
    'schema_version',
    'result_type',
    'source_type',
    'factory_id',
    'as_of',
    'total',
    'limit',
    'offset',
    'returned',
    'truncated',
    'orders',
  ])) return null
  if (
    source.result_type !== 'molding_sample.summary_list'
    || source.schema_version !== 'molding-sample-summary-v1'
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

  const orders: AIMoldingSampleSummary[] = []
  for (const rawOrder of rawOrders) {
    const order = record(rawOrder)
    if (!order || !hasExactKeys(order, [
      'order_id',
      'order_number',
      'product_name',
      'client_name',
      'status',
      'stage',
      'order_date',
      'production_factory_id',
      'updated_at',
    ])) return null
    const orderId = boundedText(order.order_id, 1, 64)
    const orderNumber = boundedText(order.order_number, 0, 128)
    const productName = boundedText(order.product_name, 0, 255)
    const clientName = boundedText(order.client_name, 0, 255)
    const status = boundedText(order.status, 0, 32)
    const stage = boundedText(order.stage, 0, 20)
    const orderDate = boundedText(order.order_date, 0, 20)
    const updatedAt = boundedText(order.updated_at, 0, 32)
    const rawProductionFactoryId = order.production_factory_id
    const productionFactoryId = rawProductionFactoryId === null
      ? null
      : boundedText(rawProductionFactoryId, 1, 64)
    if (
      !orderId
      || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(orderId)
      || orderNumber === null
      || productName === null
      || clientName === null
      || status === null
      || stage === null
      || orderDate === null
      || updatedAt === null
      || (rawProductionFactoryId !== null && productionFactoryId === null)
      || (productionFactoryId !== null
        && !productionFactoryContextIds.includes(productionFactoryId as (typeof productionFactoryContextIds)[number]))
    ) return null
    orders.push({
      orderId,
      orderNumber,
      productName,
      clientName,
      status,
      stage,
      orderDate,
      productionFactoryId,
      updatedAt,
    })
  }
  return {
    id: localId('result'),
    kind: 'molding_sample_list',
    title: '啤办任务摘要',
    summary: `本次返回 ${returned} 条，共 ${total} 条。`,
    sourceType: 'FORMAL',
    factoryId,
    asOf,
    truncated: source.truncated,
    links: [],
    moldingSample: { total, returned, limit, offset, orders },
  }
}
