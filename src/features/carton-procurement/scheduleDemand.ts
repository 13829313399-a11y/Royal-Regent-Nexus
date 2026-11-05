import type { CartonImportPreviewRow, CartonScheduleDemandSnapshot, CartonScheduleOrderMark, CartonScheduleOrder } from '@/api/cartonProcurement'

const normalized = (value?: string) => (value || '').normalize('NFKC').trim().toLowerCase()
export const effectiveSchedulePo = (row: CartonImportPreviewRow) => normalized(row.source_reference) || normalized(row.customer_po)
// SO identifies the schedule; only the source P/O# fills the order's PO field.
export const scheduleCustomerPo = (row: CartonImportPreviewRow) => row.customer_po || ''
export const scheduleLinkedPoMatches = (row: CartonImportPreviewRow, po?: string) =>
  !effectiveSchedulePo(row) || normalized(po) === normalized(row.customer_po) || Boolean(normalized(row.source_reference) && normalized(po) === normalized(row.source_reference))
export const scheduleQuantityMatchBasis = 'CONTRACT_ITEM_QUANTITY_PACKING'

function packingKey(value?: string) {
  const text = normalized(value).replace(/\s+/g, '')
  if (!/^\d+(?:\.\d+)?(?:\/\d+(?:\.\d+)?)?$/.test(text)) return ''
  const values = text.split('/').map(Number)
  const inner = values.length === 1 ? 0 : values[0]!, outer = values.at(-1)!
  return outer > 0 && inner >= 0 && inner <= outer ? `${inner}/${outer}` : ''
}

/** Consume current server evidence; paper lines and uniqueness are never guessed here. */
export function scheduleQuantityCandidates(row: CartonImportPreviewRow, orders: CartonScheduleOrder[], factory: string, ambiguous = false) {
  const quantity = Number(row.quantity), packing = packingKey(row.carton_rule)
  if (!row.schedule_identity || !packing || !(quantity > 0)) return []
  return orders.filter(order => order.factory_id === factory && order.status !== 'CANCELLED' && !normalized(order.customer_po)
    && normalized(order.customer_code) === normalized(row.schedule_customer_code)
    && normalized(order.contract_no) === normalized(row.contract_no || row.reference) && normalized(order.item_no) === normalized(row.item_no)
    && Number(order.product_order_quantity) === quantity
    && order.schedule_quantity_matches?.some(proof => proof.version === 1 && proof.basis === scheduleQuantityMatchBasis
      && proof.factory_id === factory && proof.schedule_identity === row.schedule_identity && proof.ambiguous === ambiguous
      && proof.customer_code === normalized(row.schedule_customer_code) && proof.contract_no === normalized(row.contract_no || row.reference)
      && proof.item_no === normalized(row.item_no) && Number(proof.quantity) === quantity && proof.carton_rule === packing))
}

export function scheduleDemandSnapshot(row: CartonImportPreviewRow): CartonScheduleDemandSnapshot {
  let packing = normalized(row.carton_rule).replace(/\s+/g, '')
  if (/^\d+(?:\.\d+)?(?:\/\d+(?:\.\d+)?)?$/.test(packing)) packing = packing.split('/').map(value => String(Number(value))).join('/')
  return { quantity: row.quantity == null ? '' : String(Number(row.quantity)), carton_rule: packing,
    inspection_window: normalized(row.inspection_window || row.source_inspection_window),
    customer_due_date: normalized(row.customer_due_date || row.source_customer_due_date) }
}

export function scheduleMarkChanges(row: CartonImportPreviewRow, mark?: Partial<CartonScheduleOrderMark>): string[] {
  if (mark?.review_required) return ['原下单依据待核实']
  if (!(mark?.marked ?? row.manual_ordered)) return []
  const frozen = mark?.demand_snapshot
  if (!frozen || Object.keys(frozen).length !== 4) return ['原下单依据待核实']
  const labels: Record<keyof CartonScheduleDemandSnapshot, string> = { quantity: '数量', carton_rule: '装箱', inspection_window: '验货日期', customer_due_date: '客户交期' }
  const current = scheduleDemandSnapshot(row)
  return (Object.keys(labels) as Array<keyof CartonScheduleDemandSnapshot>).filter(key => frozen[key] !== current[key]).map(key => labels[key])
}

export function scheduleMarkState(row: CartonImportPreviewRow, marks: Record<string, Partial<CartonScheduleOrderMark>>) {
  const current = marks[row.schedule_identity || '']
  if (current) return current
  if (row.schedule_identity_aliases?.some(key => marks[key]?.marked || marks[key]?.review_required))
    return { marked: false, review_required: true, demand_snapshot: null }
  return { marked: row.manual_ordered ?? false }
}
