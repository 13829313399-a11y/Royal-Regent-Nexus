import { http } from '@/lib/http'
import type { PortalShipment, ShipmentLine, SupplierDocumentBusinessKind } from './cartonSupplierPortal'
import type { SpecialRequest, MarkMode } from './cartonSpecialRequests'
import type { CartonReceiptResponse } from './cartonProcurement'

export interface UnifiedDeliveryLine extends Omit<ShipmentLine, 'source_type'> {
  source_type?: string; source_kind: 'FORMAL' | 'SPECIAL'
  special_request_id?: string; special_shipment_id?: string; special_request_revision?: number
  original_special_line_id?: string; origin?: string; requester_name?: string; workshop_id?: string
  free_confirmed?: boolean; mark_mode?: MarkMode; mark_attachment_id?: string
  source_origin?: string; warehouse_unit_price?: string | null
}
export interface UnifiedDelivery {
  id: string; factory_id: string; delivery_note_no: string; delivery_date: string; created_at: string
  formal: PortalShipment | null; special: SpecialRequest[]; lines: UnifiedDeliveryLine[]
  receipts: { id?: string; receipt_id?: string; receipt_no?: string; status?: string; acceptance_date?: string | null }[]
  status: string; revision: number; requires_correction: boolean; can_operate: boolean
  shortfall_reopen_history?: { reason: string; created_at: string; quantities: Record<string, string> }[]
}
export type PriceAction = 'MATCH' | 'PENDING' | 'PROPOSE' | 'FREE'
export function unifiedDeliveryLineKind(group: UnifiedDelivery, line: UnifiedDeliveryLine): SupplierDocumentBusinessKind {
  if (line.business_kind) return line.business_kind
  if (line.source_kind === 'FORMAL') return line.source_type === 'AD_HOC_REVIEW' ? 'UNKNOWN' : line.source_type === 'FORMAL_ORDER' || line.order_line_id ? 'REGULAR' : 'UNKNOWN'
  const request = group.special.find(item => item.id === line.special_request_id)
  if (!request || (request.origin === 'SUPPLIER_EXTRA' || line.origin === 'SUPPLIER_EXTRA') && !request.shipments.some(shipment => shipment.receipts?.length > 0)) return 'UNKNOWN'
  return request.kind === 'SAMPLE' ? 'SAMPLE' : request.kind === 'WORKSHOP_MISC' ? 'MISC' : 'UNKNOWN'
}
// Display/filter projection only. Mutations always use the original typed group.
export function toPortalShipment(group: UnifiedDelivery): PortalShipment {
  const history = group.receipts.map(receipt => ({ receipt_id: receipt.receipt_id || receipt.id,
    acceptance_date: receipt.acceptance_date || null, confirmed_at: '', status: receipt.status || '', lines: [] }))
  return { ...group.formal, id: group.id, delivery_note_no: group.delivery_note_no, delivery_date: group.delivery_date,
    status: group.status, revision: group.revision, created_at: group.created_at, confirmed_at: '',
    acceptance_date: history.map(row => row.acceptance_date || '').sort().at(-1) || null,
    acceptance_history: history, acceptance_lines: [], requires_correction: group.requires_correction, can_operate: group.can_operate,
    lines: group.lines.map(line => ({ ...line, business_kind: unifiedDeliveryLineKind(group, line), source_type: line.source_kind === 'FORMAL' ? line.source_type as ShipmentLine['source_type'] : undefined,
      order_line_id: line.source_kind === 'SPECIAL' && line.origin !== 'SUPPLIER_EXTRA' ? line.original_special_line_id || null : line.order_line_id,
      customer_name: line.customer_name || '', contract_no: line.contract_no || '', customer_po: line.customer_po || '', item_no: line.item_no || '' })) }
}
const prefix = (supplier: boolean) => supplier ? '/carton-supplier/unified-deliveries' : '/carton-unified-deliveries'
export const cartonUnifiedDeliveriesApi = {
  async warehouseReceive(body: Record<string, unknown>, signal?: AbortSignal) { return (await http.post<{ delivery_id: string; receipts: CartonReceiptResponse[] }>(`${prefix(false)}/warehouse-receive`, body, { signal })).data },
  async detail(factory: string, id: string, signal?: AbortSignal) { return (await http.get<UnifiedDelivery>(`${prefix(false)}/${encodeURIComponent(id)}`, { params: { factory_id: factory }, signal })).data },
  async list(factory: string, supplier = false, signal?: AbortSignal) { return (await http.get<{ items: UnifiedDelivery[]; total: number; options?: { workshops: { id: string; name: string }[] } }>(prefix(supplier), { params: { factory_id: factory }, signal })).data },
  async dispatch(body: Record<string, unknown>, signal?: AbortSignal) { return (await http.post<UnifiedDelivery>(prefix(true), body, { signal })).data },
  async receive(id: string, body: Record<string, unknown>, signal?: AbortSignal) { return (await http.post<UnifiedDelivery>(`${prefix(false)}/${encodeURIComponent(id)}/receive`, body, { signal })).data },
  async reopenShortfall(id: string, body: Record<string, unknown>, signal?: AbortSignal) { return (await http.post<UnifiedDelivery>(`${prefix(false)}/${encodeURIComponent(id)}/reopen-shortfall`, body, { signal })).data },
}
