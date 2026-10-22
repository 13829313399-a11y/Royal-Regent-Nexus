import { http } from '@/lib/http'
import type { CartonOrderResponse } from './cartonProcurement'

export type SpecialKind = 'SAMPLE' | 'WORKSHOP_MISC' | 'SUPPLIER_GIFT'
export type PricingKind = 'PENDING_QUOTE' | 'FREE' | 'CHARGEABLE'
export type AttachmentRole = 'REFERENCE' | 'DRAFT' | 'CONFIRMED'
export type MarkMode = 'EXISTING' | 'UPLOAD' | 'NONE' | 'PENDING'
export interface SpecialLine {
  mark_mode?: MarkMode; mark_attachment_id?: string; mark_asset_id?: string; mark_asset_revision?: number; mark_ready?: boolean
  id?: string; packaging_type: string; paper_quality: string; specification: string; dimension_unit: string
  quantity: string; unit: string; item_no: string; unit_price?: string; received_quantity?: string; remaining_quantity?: string; remaining_to_ship?: string
}
export interface SpecialShipment {
  closures?: { quantities: Record<string, string>; reason: string; acceptance_date: string }[]
  source_origin?: 'WAREHOUSE_MANUAL' | 'SUPPLIER'
  id: string; version_id: string; delivery_note_no: string; delivery_date: string; status?: string
  lines: { id: string; request_line_id: string; quantity: string; received_quantity: string; remaining_quantity: string; snapshot?: Partial<SpecialLine> & { pricing_kind?: PricingKind; warehouse_unit_price?: string | null; supplier_price_confirmed?: boolean; source_origin?: 'WAREHOUSE_MANUAL' | 'SUPPLIER' }; closed_quantity?: string; gross_received_quantity?: string; effective_received_quantity?: string }[]
  receipts: { id: string; receipt_no?: string; acceptance_date?: string; status?: string; lines?: { id?: string; shipment_line_id?: string; packaging_type?: string; paper_quality?: string; specification?: string; unit?: string; received_quantity?: string; damaged_quantity?: string; rejected_quantity?: string; unusable_quantity?: string; effective_quantity?: string; unit_price?: string }[] }[]
}
export interface SpecialRequest {
  replacement?: { parent_request_id: string; parent_request_no: string; responsibility: 'OWN' | 'SUPPLIER'; can_undo: boolean; blockers: string[] } | null
  mark_assets?: { id: string; file_name: string; revision: number; kind: 'pdf' | 'excel' | 'image'; line_id?: string }[]
  supplier_confirmation?: { status: string; version_id: string; promised_date: string; reason: string; responded_at: string; responded_by: string }
  deleted?: boolean
  manual_delivery_id?: string
  origin?: string; id: string; request_no: string; factory_id: string; kind: SpecialKind; title: string; requester_name: string
  status: string; revision: number; current_version_id: string; quote_version_id: string; pricing_kind: PricingKind
  promised_date: string; customer_code: string; customer_name: string; workshop_id: string; purpose: string; required_date: string; created_at?: string
  lines: SpecialLine[]; shipments: SpecialShipment[]
  attachments: { id: string; role: AttachmentRole; filename: string; created_at?: string; version_id?: string; line_id?: string; sha256?: string; version?: number }[]
  messages: { id: string; body: string; author_name?: string; actor_name?: string; created_at: string }[]
  history: { id?: string; action: string; actor_name?: string; created_at: string; note?: string }[]
  permissions: Partial<Record<'can_edit' | 'can_send' | 'can_confirm' | 'can_adjust' | 'can_append' | 'can_return_stock' | 'can_replenish' | 'can_undo_replenish' | 'can_manual_receive' | 'can_approve' | 'can_cancel' | 'can_delete' | 'can_quote' | 'can_ship' | 'can_receive' | 'can_attach' | 'can_message' | 'can_confirm_material', boolean>>
}
export interface SpecialWorkspace {
  items: SpecialRequest[]; total: number; can_create: boolean
  options?: { customers?: { customer_code: string; customer_name: string }[]; workshops?: { id: string; name: string }[]; locations?: { id: string; label: string; warehouse?: string; bin_code?: string }[] }
}
export interface SpecialSave {
  factory_id: string; request_id: string; kind: SpecialKind; title?: string; requester_name: string; purpose: string
  workshop_id: string; customer_code: string; required_date: string; lines: SpecialLine[]; expected_revision?: number
}
export interface SpecialAction { factory_id: string; request_id: string; expected_revision: number; [key: string]: unknown }
export interface SpecialManualReceipt extends SpecialAction {
  delivery_note_no: string; delivery_date: string; acceptance_date: string
  lines: { line_id: string; received_quantity: string; damaged_quantity: string; rejected_quantity: string; unusable_quantity: string; unit_price: string | null; location_allocations: { location_id: string; quantity: string | number }[] }[]
}
const prefix = (supplier: boolean) => supplier ? '/carton-supplier/special-requests' : '/carton-special-requests'
export interface UnifiedOrderEntry { kind: 'PURCHASE' | SpecialKind; order?: CartonOrderResponse; special?: SpecialRequest }
export interface UnifiedOrderRef { kind: UnifiedOrderEntry['kind']; id: string; expected_revision?: number }
export interface UnifiedOrderPage { items: UnifiedOrderEntry[]; total: number; can_create: boolean; statistics: { overdue: number; today: number; dueSoon: number; pending: number } }
export interface MarkOption { id: string; file_name: string; revision: number; contract_number?: string }
export const cartonSpecialRequestsApi = {
  async purchaseContext(factory: string, id: string, supplier = false, signal?: AbortSignal) { return (await http.get<import('./cartonProcurement').CartonPurchaseOrderContextResponse>(`${prefix(supplier)}/${encodeURIComponent(id)}/purchase-orders`, { params: { factory_id: factory }, signal })).data },
  async purchaseExport(factory: string, id: string, versionId: string, supplier = false, signal?: AbortSignal) { return (await http.get<Blob>(`${prefix(supplier)}/${encodeURIComponent(id)}/purchase-orders/${encodeURIComponent(versionId)}/export`, { params: { factory_id: factory }, signal, responseType: 'blob' })).data },
  async selected(factory: string, items: UnifiedOrderRef[], signal?: AbortSignal) { return (await http.post<UnifiedOrderEntry[]>('/carton-unified-orders/selected', { factory_id: factory, items }, { signal })).data },
  async batchAction(body: { factory_id: string; request_id: string; action: 'CONFIRM' | 'CANCEL' | 'DELETE'; reason: string; items: UnifiedOrderRef[] }, signal?: AbortSignal) { return (await http.post<{ count: number }>('/carton-unified-orders/batch-actions', body, { signal })).data },
  async ledger(factory: string, filters: Record<string, string | number>, signal?: AbortSignal) { return (await http.get<UnifiedOrderPage>('/carton-unified-orders', { params: { factory_id: factory, ...filters }, signal })).data },
  async markOptions(factory: string, signal?: AbortSignal, supplier = false, requestId?: string) { return (await http.get<MarkOption[]>(`${prefix(supplier)}/mark-options`, { params: { factory_id: factory, request_id: requestId }, signal })).data },
  async factories(signal?: AbortSignal) { return (await http.get<{ factory_id: string; supplier_name: string }[]>('/carton-supplier/special-requests/factories', { signal })).data },
  async list(factory: string, supplier = false, signal?: AbortSignal, responsibilityScope?: string) { return (await http.get<SpecialWorkspace>(prefix(supplier), { params: { factory_id: factory, ...(responsibilityScope ? { responsibility_scope: responsibilityScope } : {}) }, signal })).data },
  async detail(factory: string, id: string, supplier = false, signal?: AbortSignal) { return (await http.get<SpecialRequest>(`${prefix(supplier)}/${encodeURIComponent(id)}`, { params: { factory_id: factory }, signal })).data },
  async save(body: SpecialSave, supplier = false, id = '', signal?: AbortSignal) {
    const url = `${prefix(supplier)}${id ? `/${encodeURIComponent(id)}` : supplier ? '/gifts' : ''}`
    return (await (id ? http.put<SpecialRequest>(url, body, { signal }) : http.post<SpecialRequest>(url, body, { signal }))).data
  },
  async action(id: string, action: string, body: SpecialAction, supplier = false, signal?: AbortSignal) { return (await http.post<SpecialRequest>(`${prefix(supplier)}/${encodeURIComponent(id)}/${action}`, body, { signal })).data },
  async adjust(id: string, body: SpecialSave & { reason: string }, signal?: AbortSignal) { return (await http.post<SpecialRequest>(`${prefix(false)}/${encodeURIComponent(id)}/adjust`, body, { signal })).data },
  async manualReceive(id: string, body: SpecialManualReceipt, signal?: AbortSignal) { return (await http.post<SpecialRequest>(`${prefix(false)}/${encodeURIComponent(id)}/manual-receive`, body, { signal })).data },
  async attach(id: string, body: SpecialAction, role: AttachmentRole, file: File, supplier = false, signal?: AbortSignal) {
    const form = new FormData(); for (const [key, value] of Object.entries(body)) form.append(key, String(value))
    form.append('role', role); form.append('file', file)
    return (await http.post<SpecialRequest>(`${prefix(supplier)}/${encodeURIComponent(id)}/attachments`, form, { headers: { 'Content-Type': 'multipart/form-data' }, signal })).data
  },
  async download(factory: string, id: string, attachmentId: string, supplier = false, signal?: AbortSignal) {
    return (await http.get<Blob>(`${prefix(supplier)}/${encodeURIComponent(id)}/attachments/${encodeURIComponent(attachmentId)}`, { params: { factory_id: factory }, signal, responseType: 'blob' })).data
  },
}
