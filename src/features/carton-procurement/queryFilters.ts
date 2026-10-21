import { awaitsWarehouseReceipt } from './supplierWork'
import { isCardPaper } from './paperCatalog'
import type { PortalShipment, ShipmentLine, SupplierDocumentBusinessKind } from '@/api/cartonSupplierPortal'
import type { SettlementDocument, StatementLine, SupplierSource } from '@/api/cartonSupplierSettlement'

export interface ShipmentFilters {
  search: string; customer: string; status: string; association: string
  businessKind?: SupplierDocumentBusinessKind | ''
  dateField: 'DELIVERY' | 'ACCEPTANCE'; from: string; to: string; sort: 'DESC' | 'ASC'
}
export const emptyShipmentFilters = (): ShipmentFilters => ({ search: '', customer: '', status: '', association: '', businessKind: '', dateField: 'DELIVERY', from: '', to: '', sort: 'DESC' })
export function shipmentLineBusinessKind(line: ShipmentLine): SupplierDocumentBusinessKind {
  if (line.business_kind) return line.business_kind
  if (line.source_type === 'AD_HOC_REVIEW') return 'UNKNOWN'
  return line.source_type === 'FORMAL_ORDER' || line.order_line_id ? 'REGULAR' : 'UNKNOWN'
}
export function filterShipments<T extends PortalShipment>(rows: T[], filters: ShipmentFilters): T[] {
  const term = filters.search.trim().toLocaleLowerCase()
  const dateOf = (row: T) => (filters.dateField === 'ACCEPTANCE' ? row.acceptance_date : row.delivery_date) || ''
  return rows.filter(row => {
    const dates = filters.dateField === 'ACCEPTANCE'
      ? [row.acceptance_date, ...(row.acceptance_history ?? []).map(batch => batch.acceptance_date)].filter((day): day is string => !!day)
      : [dateOf(row)]
    return (!filters.status || (filters.status === 'PENDING_RECEIPT' ? awaitsWarehouseReceipt(row) : filters.status === 'RECEIPT_REVERSED' ? Boolean(row.requires_correction || row.receipt_status === 'REVERSED' || row.status === 'RECEIPT_REVERSED') : row.status === filters.status))
      && (!filters.customer || row.lines.some(line => line.customer_name === filters.customer))
      && (!filters.businessKind || row.lines.some(line => shipmentLineBusinessKind(line) === filters.businessKind))
      && (!filters.association || (filters.association === 'UNMATCHED' ? row.lines.some(line => !line.order_line_id) : row.lines.every(line => !!line.order_line_id)))
      && ((!filters.from && !filters.to) || dates.some(date => !!date && (!filters.from || date >= filters.from) && (!filters.to || date <= filters.to)))
      && (!term || [row.delivery_note_no, row.source_filename, ...row.lines.flatMap(line => [line.customer_name, line.order_no, line.contract_no, line.customer_po, line.item_no, line.child_no])].join(' ').toLocaleLowerCase().includes(term))
  }).sort((a, b) => {
    const left = dateOf(a), right = dateOf(b)
    return (left ? 0 : 1) - (right ? 0 : 1) || (filters.sort === 'ASC' ? left.localeCompare(right) : right.localeCompare(left)) || b.created_at.localeCompare(a.created_at) || a.id.localeCompare(b.id)
  })
}

export type SettlementLineFilter = 'ALL' | 'DIFFERENCE' | 'UNMATCHED' | 'CARD' | 'NON_CARD'
export type SettlementBusinessKind = '' | 'SAMPLE' | 'MISC' | 'OTHER'
export function matchesSettlementLine(line: StatementLine, source: SupplierSource | undefined, result: SettlementDocument['result']['line_results'][number] | undefined, search: string, filter: SettlementLineFilter, businessKind: SettlementBusinessKind = '') {
  const matches = [line.document_no, line.note, source?.special_request_no, source?.customer_name, source?.contract_no, source?.item_no, source?.packaging_type, source?.specification].join(' ').toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())
  const difference = !!source?.issues.length || !!result?.issues.length || [result?.quantity_difference, result?.price_difference, result?.amount_difference, source?.supplier_delivery?.quantity_difference, source?.supplier_delivery?.price_difference].some(value => value != null && Number(value) !== 0)
  const kind = source?.special_request_kind === 'SAMPLE' ? 'SAMPLE' : source?.special_request_kind === 'WORKSHOP_MISC' ? 'MISC' : 'OTHER'
  return matches && (!businessKind || kind === businessKind) && (filter === 'CARD' ? !!source && isCardPaper(source.packaging_type) : filter === 'NON_CARD' ? !!source?.packaging_type && !isCardPaper(source.packaging_type) : (filter === 'ALL' || (filter === 'UNMATCHED' ? !source || !source.supplier_delivery && source.kind === 'RECEIPT' : difference)))
}
export function settlementStage(doc: SettlementDocument) {
  if (doc.status === 'SUPERSEDED') return 'HISTORY'
  if (doc.stale) return 'STALE'
  if (doc.status === 'CONFIRMED') return 'CONFIRMED'
  if (doc.result.supplier_review?.decision === 'DISPUTED') return 'DISPUTED'
  return doc.result.supplier_review?.decision === 'CONFIRMED' ? 'INTERNAL_PENDING' : 'SUPPLIER_PENDING'
}
