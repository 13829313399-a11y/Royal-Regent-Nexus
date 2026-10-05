import type { CartonExceptionResponse, CartonImportBatchResponse, CartonImportPreviewRow, CartonScheduleOrder } from '@/api/cartonProcurement'
import type { ScheduleOrderReminder } from '@/lib/cartonScheduleDeadline'
import { weeklyExceptionLookup } from '@/lib/cartonAlertIndex'
const identifier = (value?: string) => (value ?? '').normalize('NFKC').trim().toLocaleLowerCase()
export type BusinessOrderAlertKind = 'MISSING_ORDER' | 'NEW_ORDER' | 'QUANTITY_INCREASE' | 'QUANTITY_DECREASE' | 'QUANTITY_REVIEW' | 'SCHEDULE_CANCELLED' | 'CANCELLED_AFTER_ORDER'

export interface BusinessOrderAlert {
  id: string
  alertNo: string
  kind: BusinessOrderAlertKind
  customerCode: string
  customerName: string
  contractNo: string
  itemNo: string
  productName: string
  scheduleQuantity: number
  orderQuantity: number
  differenceQuantity: number
  orderNo: string
  orderStatus: string
  sourceFilename: string
  sourceOperatorName: string
  sourceCreatedAt: string
  suggestion: string
  exception: CartonExceptionResponse | null
  batchId: string
  status: CartonExceptionResponse['status']
  reminder: ScheduleOrderReminder | null
  sourceRow: CartonImportPreviewRow | null
  order: CartonScheduleOrder | null
}

export function buildBusinessOrderAlerts(context: {
  factoryId: string; batches: CartonImportBatchResponse[]; exceptions: CartonExceptionResponse[]
  reminder: (row: CartonImportPreviewRow) => ScheduleOrderReminder | null
  ordersForSource: (row: CartonImportPreviewRow) => CartonScheduleOrder[]
}): BusinessOrderAlert[] {
  function orderForBusinessAlert(row: CartonImportPreviewRow | null, exception: CartonExceptionResponse) {
    const candidates = context.ordersForSource({ ...row,
      contract_no: exception.contract_no || row?.contract_no || row?.reference,
      item_no: exception.item_no || row?.item_no,
      customer_code: exception.customer_code || row?.customer_code,
      customer_name: exception.customer_name || row?.customer_name,
    })
    return candidates.length === 1 ? candidates[0] ?? null : null
  }

  const batches = new Map(context.batches.filter(batch => batch.status !== 'REJECTED').map(batch => [batch.id, batch]))
  const batchRank = new Map(context.batches.map((batch, index) => [batch.id, index]))
  const alerts = new Map<string, BusinessOrderAlert>()
  const lookups = new Map([...batches].map(([id, batch]) => [id, weeklyExceptionLookup(batch.parse_summary.rows ?? [])]))
  const timingExceptions = new Map<CartonImportPreviewRow, CartonExceptionResponse>()
  for (const exception of context.exceptions) {
    if (exception.factory_id !== context.factoryId || exception.source_type !== 'WEEKLY_SCHEDULE'
      || !['MISSING_ORDER', 'SCHEDULE_NEW_ORDER'].includes(exception.category)) continue
    const source = lookups.get(exception.source_id)?.(exception)
    if (source && !timingExceptions.has(source)) timingExceptions.set(source, exception)
  }
  const sourceKey = (row: CartonImportPreviewRow) => row.schedule_identity || JSON.stringify([
    row.schedule_customer_code || row.customer_code || identifier(row.customer_name),
    identifier(row.contract_no || row.reference), identifier(row.item_no), identifier(row.source_reference),
  ])
  const candidates = context.exceptions.filter(exception => exception.factory_id === context.factoryId
    && exception.source_type === 'WEEKLY_SCHEDULE'
    && ['QUANTITY_MISMATCH', 'SCHEDULE_CANCELLED', 'SCHEDULE_CANCELLED_AFTER_ORDER'].includes(exception.category))
    .sort((left, right) => (batchRank.get(left.source_id) ?? Number.MAX_SAFE_INTEGER) - (batchRank.get(right.source_id) ?? Number.MAX_SAFE_INTEGER)
      || right.created_at.localeCompare(left.created_at))
  for (const exception of candidates) {
    const batch = batches.get(exception.source_id)
    if (!batch) continue
    const sourceRow = lookups.get(batch.id)?.(exception) ?? null
    if (sourceRow?.legacy_match_stale && exception.category === 'QUANTITY_MISMATCH') continue
    const order = orderForBusinessAlert(sourceRow, exception)
    const scheduleQuantity = Number(sourceRow?.quantity ?? 0)
    const orderQuantity = Number(order?.product_order_quantity ?? 0)
    const differenceQuantity = scheduleQuantity - orderQuantity
    const kind: BusinessOrderAlertKind = exception.category === 'SCHEDULE_CANCELLED_AFTER_ORDER' ? 'CANCELLED_AFTER_ORDER'
      : exception.category === 'SCHEDULE_CANCELLED' ? 'SCHEDULE_CANCELLED'
        : !sourceRow ? 'QUANTITY_REVIEW' : differenceQuantity > 0 ? 'QUANTITY_INCREASE'
          : differenceQuantity < 0 ? 'QUANTITY_DECREASE' : 'QUANTITY_REVIEW'
    const businessKey = sourceRow ? sourceKey(sourceRow) : JSON.stringify([exception.customer_code || exception.customer_name, exception.contract_no, exception.item_no])
    if (alerts.has(businessKey)) continue
    alerts.set(businessKey, {
      id: exception.id, alertNo: exception.exception_no, kind,
      customerCode: exception.customer_code || sourceRow?.schedule_customer_code || order?.customer_code || '',
      customerName: sourceRow?.schedule_customer_name || exception.customer_name || order?.customer_name || '待识别客户',
      contractNo: exception.contract_no || sourceRow?.contract_no || sourceRow?.reference || '',
      itemNo: exception.item_no || sourceRow?.item_no || '', productName: sourceRow?.product_name || order?.product_name || '',
      scheduleQuantity, orderQuantity, differenceQuantity,
      orderNo: order?.order_no || sourceRow?.order_no || '', orderStatus: order?.status || '',
      sourceFilename: batch.original_filename, sourceOperatorName: batch.imported_by_name || '业务接单员',
      sourceCreatedAt: batch.created_at, suggestion: sourceRow?.suggestion || exception.description,
      exception, batchId: batch.id, status: exception.status, reminder: null, sourceRow, order,
    })
  }
  // Generate timing from the latest effective evidence even when the import only produced a type-review item (e.g. 加单).
  const seen = new Set<string>()
  for (const batch of batches.values()) {
    if (batch.factory_id && batch.factory_id !== context.factoryId) continue
    for (const sourceRow of batch.parse_summary.rows ?? []) {
      const key = sourceKey(sourceRow)
      if (seen.has(key)) continue
      seen.add(key)
      const reminder = context.reminder(sourceRow)
      if (!reminder || reminder.state === 'ORDERED' || reminder.state === 'REVIEW') continue
      const exception = timingExceptions.get(sourceRow) ?? null
      const orders = context.ordersForSource(sourceRow)
      const order = orders.length === 1 ? orders[0] || null : null
      const alertNo = exception?.exception_no || `排期-${sourceRow.source_sheet || 'ITEM'}-${sourceRow.source_row || 1}`
      alerts.set(`TIMING:${key}`, {
        id: `TIMING:${batch.id}:${key}`, alertNo,
        kind: sourceRow.schedule_change === 'NEW' ? 'NEW_ORDER' : 'MISSING_ORDER',
        customerCode: sourceRow.schedule_customer_code || sourceRow.customer_code || '',
        customerName: sourceRow.schedule_customer_name || sourceRow.customer_name || '未绑定客户',
        contractNo: sourceRow.contract_no || sourceRow.reference || '', itemNo: sourceRow.item_no || '',
        productName: sourceRow.product_name || '', scheduleQuantity: Number(sourceRow.quantity || 0),
        orderQuantity: Number(order?.product_order_quantity || 0), differenceQuantity: 0,
        orderNo: order?.order_no || '', orderStatus: order?.status || '',
        sourceFilename: batch.original_filename, sourceOperatorName: batch.imported_by_name || '业务接单员',
        sourceCreatedAt: batch.created_at, suggestion: reminder.detail,
        // Closing an import mismatch is not evidence of placing an order; current procurement state owns this reminder.
        exception, batchId: batch.id, status: 'OPEN', reminder, sourceRow, order,
      })
    }
  }
  return [...alerts.values()].sort((left, right) => {
    const rank = (alert: BusinessOrderAlert) => alert.kind === 'CANCELLED_AFTER_ORDER' ? 0
      : alert.reminder?.state === 'OVERDUE' ? 1 : alert.reminder?.state === 'DUE_TODAY' ? 2
        : alert.reminder?.state === 'DUE_SOON' ? 3 : alert.reminder?.state === 'WAIT' ? 6 : 4
    return rank(left) - rank(right) || (left.reminder?.deadline || '').localeCompare(right.reminder?.deadline || '')
  })
}
