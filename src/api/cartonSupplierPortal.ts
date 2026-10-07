import { http } from '@/lib/http'
import { postCartonInventoryRequest } from './cartonInventoryRequest'
import type { LocationAllocation } from './cartonPositions'
import type { SplitRecord } from './cartonOrderSplits'
import type { CartonSupplierAcceptanceResponse } from './cartonProcurement'
export interface PortalAttachment { id: string; filename: string; version: number; size: number; sha256: string; created_at: string }
export interface PortalPaper { id: string; line_no: number; child_no: string; packaging_type: string; paper_quality: string; specification: string; dimension_unit: string; unit: string; required_quantity: string; received_quantity: string; in_transit_quantity: string; remaining_to_ship: string; accepted: boolean; shipping_blocked_reason?: string; commitment_revision: number; promised_date: string; unit_price?: string; currency?: string }
export interface PortalOrder { split_records?: SplitRecord[]; id: string; order_no: string; customer_code?: string; revision?: number; customer_name: string; contract_no: string; customer_po: string; item_no: string; product_name: string; status: string; issue_id: string; document_no: string; order_date: string; planned_date: string; awaiting_issue: boolean; lines: PortalPaper[]; attachments: PortalAttachment[] }
export interface ShipmentLine { id: string; order_line_id: string | null; source_type?: 'FORMAL_ORDER' | 'AD_HOC_REVIEW'; order_no: string; contract_no: string; customer_po: string; item_no: string; customer_name: string; child_no: string; packaging_type: string; paper_quality: string; specification: string; unit: string; quantity: string; unit_price?: string; delivery_unit_price?: string | null; currency?: string }
export interface ReceiveLine { shipment_line_id: string; received_quantity: number; damaged_quantity: number; rejected_quantity: number; unusable_quantity: number; unit_price: number; paper_quality: string; specification: string; location_allocations: LocationAllocation[]; difference_reason: string; no_order_decision?: '' | 'SAMPLE' | 'WRONG_DELIVERY'; customer_code?: string; sample_purpose?: string; requested_by?: string; unit?: string }
export interface SampleReceipt { receipt_line_id: string; customer_code: string; customer_name: string; contract_no: string; item_no: string; packaging_type: string; paper_quality: string; specification: string; unit: string; quantity: string; linked_order_line_id: string }
export interface PortalShipment { requires_receipt_link?: boolean; linked_existing_receipt?: boolean; id: string; delivery_note_no: string; delivery_date: string; status: string; revision: number; created_at: string; confirmed_at: string; source_filename?: string; source_sha256?: string; receipt_id?: string; receipt_status?: string; requires_correction?: boolean; acceptance_history?: { confirmed_at: string; acceptance_date: string | null; status: string; lines: PortalShipment['acceptance_lines'] }[]; sample_receipts?: SampleReceipt[]; acceptance_date: string | null; lines: ShipmentLine[]; acceptance_lines: Pick<ReceiveLine, 'shipment_line_id' | 'received_quantity' | 'damaged_quantity' | 'rejected_quantity' | 'unusable_quantity' | 'difference_reason' | 'no_order_decision'>[] }
export interface PortalWorkspace { factory_id: string; supplier_name: string; orders: PortalOrder[]; shipments: PortalShipment[] }
export interface PendingSupplierShipment { id: string; delivery_note_no: string; delivery_date: string; requires_correction: boolean }
export interface PendingSupplierShipments { factory_id: string; total: number; items: PendingSupplierShipment[] }
export interface DeliveryImportRow { source_sheet: string; source_row: number; contract_no: string; item_no: string; packaging_type: string; paper_quality: string; specification: string; delivered_quantity: number; unit_price?: number; order_no: string; child_no: string; order_line_id: string; issue_id: string; status: 'READY' | 'AD_HOC_REVIEW' | 'BLOCKED'; reason: string }
export interface DeliveryImportGroup { factory_id: string; destination: string; delivery_note_no: string; delivery_date: string; ready: boolean; receipt_link_ready?: boolean; existing_receipt_count?: number; issues: string[]; rows: DeliveryImportRow[] }
export type DeliveryRegistrationMode = 'SHIPMENT' | 'EXISTING_RECEIPT'
export interface ShipmentReceiptOption { already_linked?: boolean; id: string; revision: number; status: 'POSTED' | 'REVERSED'; receipt_no: string; delivery_note_no: string; delivery_date: string; acceptance_date: string | null; lines: { order_line_id: string; contract_no: string; item_no: string; packaging_type: string; paper_quality: string; specification: string; received_quantity: string; damaged_quantity: string; rejected_quantity: string; unusable_quantity: string; effective_quantity: string; unit: string; unit_price: string; currency: string }[] }
export interface DeliveryImportPreview { filename: string; sha256: string; row_count: number; groups: DeliveryImportGroup[] }
export interface SupplierMarkTemplate { id: string; customer_name: string; po: string; item: string; contract_number: string; version: number; check_status: string; manual_released: boolean; excel_file_name: string; pdf_file_name: string; created_at: string }
export interface SupplierDocumentOrder { order_no: string; customer_name: string; contract_no: string; customer_po: string; item_no: string; product_name: string; order_date: string; planned_date: string }
export interface SupplierDocumentLine { order_no: string; child_no: string; contract_no?: string; item_no?: string; customer_name?: string; source_document_no?: string; packaging_type: string; paper_quality: string; specification: string; unit: string; quantity: string; before_quantity?: string; change_quantity?: string; received_quantity?: string }
export interface SupplierDocument { supplier_acceptance?: Omit<CartonSupplierAcceptanceResponse, 'status' | 'issue_id' | 'document_no' | 'accepted_at'> & { status: string }; id: string; kind: 'PURCHASE' | 'DELIVERY'; factory_id: string; document_no: string; document_type: string; date: string; created_at: string; status: string; replenishment: boolean; export_count: number; is_batch?: boolean; source_documents?: { id: string; document_no: string; order_no: string }[]; unmatched_line_count?: number; source_filename?: string; source_sha256?: string; orders: SupplierDocumentOrder[]; lines: SupplierDocumentLine[] }
export interface SupplierActivity { id: string; created_at: string; action: string; reference_no: string; actor_name: string; factory_id: string }
export interface SupplierMarkAsset {
  photo_group_id?: string | null
  id: string; file_name: string; kind: 'pdf' | 'excel' | 'image'; size_bytes: number; contract_number: string; created_at: string
  orders: { id: string; customer_name: string; contract_no: string; customer_po: string; item_no: string }[]
}
const base = '/carton-supplier'
export const cartonSupplierPortalApi = {
  async memberships() { return (await http.get<{ factory_id: string; supplier_name: string }[]>(base + '/memberships')).data },
  async workspace(factory_id: string, internal = false) { return (await http.get<PortalWorkspace>(base + (internal ? '/internal' : '') + '/workspace', { params: { factory_id } })).data },
  async pendingShipments(factory_id: string, limit = 3) { return (await http.get<PendingSupplierShipments>(base + '/internal/shipments/pending', { params: { factory_id, limit } })).data },
  async documents(factory_id: string) { return (await http.get<SupplierDocument[]>(base + '/documents', { params: { factory_id } })).data },
  async activity(factory_id: string) { return (await http.get<SupplierActivity[]>(base + '/activity', { params: { factory_id } })).data },
  async activityPage(filters: Record<string, string | number>) { return (await http.get<{ items: SupplierActivity[]; total: number; limit: number; offset: number }>(base + '/activity-page', { params: filters })).data },
  async exportDocuments(documents: Pick<SupplierDocument, 'factory_id' | 'kind' | 'id'>[]) {
    const selections = documents.map(({ factory_id, kind, id }) => ({ factory_id, kind, id }))
    const { data } = await http.post<Blob>(base + '/documents/export.xlsx', { documents: selections }, { responseType: 'blob' })
    const url = URL.createObjectURL(data)
    const a = document.createElement('a')
    a.href = url
    a.download = '供应商单据.xlsx'
    a.click()
    URL.revokeObjectURL(url)
  },
  async exportOrderImport(documents: Pick<SupplierDocument, 'factory_id' | 'kind' | 'id'>[], acknowledgeUnaccepted = false) {
    const selections = documents.map(({ factory_id, kind, id }) => ({ factory_id, kind, id }))
    const { data } = await http.post<Blob>(base + '/documents/order-import.xlsx', { documents: selections, acknowledge_unaccepted: acknowledgeUnaccepted }, { responseType: 'blob' })
    const url = URL.createObjectURL(data)
    const a = document.createElement('a')
    a.href = url
    a.download = '东康订单导入模板.xlsx'
    a.click()
    URL.revokeObjectURL(url)
  },
  async markTemplates(factory_id: string) { return (await http.get<SupplierMarkTemplate[]>(base + '/carton-mark/templates', { params: { factory_id } })).data },
  async markAssets(factory_id: string, signal?: AbortSignal) { return (await http.get<SupplierMarkAsset[]>(base + '/carton-mark/assets', { params: { factory_id }, signal })).data },
  previewMarkAssetUrl(id: string, factory_id: string) { return http.getUri({ url: `${base}/carton-mark/assets/${encodeURIComponent(id)}/document`, params: { factory_id, preview: true } }) },
  async downloadMarkAsset(id: string, factory_id: string, signal?: AbortSignal) { return (await http.get<Blob>(`${base}/carton-mark/assets/${encodeURIComponent(id)}/document`, { params: { factory_id }, responseType: 'blob', signal })).data },
  previewMarkPdfUrl(template_id: string, factory_id: string) { return http.getUri({ url: `${base}/carton-mark/templates/${encodeURIComponent(template_id)}/documents/print_pdf`, params: { factory_id, preview: true } }) },
  async downloadMarkDocument(template_id: string, kind: 'source_excel' | 'print_pdf', factory_id: string, filename: string) { const { data } = await http.get<Blob>(`${base}/carton-mark/templates/${template_id}/documents/${kind}`, { params: { factory_id }, responseType: 'blob' }); const url = URL.createObjectURL(data); const a = document.createElement('a'); a.href = url; a.download = filename; a.click(); URL.revokeObjectURL(url) },
  async accept(line: PortalPaper, order: PortalOrder, factory_id: string, promised_date: string) { return (await http.put<PortalOrder>(`${base}/papers/${line.id}/commitment`, { factory_id, issue_id: order.issue_id, expected_revision: line.commitment_revision, promised_date })).data },
  async acceptBatch(factory_id: string, lines: { order_line_id: string; issue_id: string; expected_revision: number; promised_date: string }[]) {
    return (await http.put<{ order_ids: string[] }>(base + '/commitments/batch', { factory_id, lines })).data
  },
  ship(payload: { factory_id: string; delivery_note_no: string; delivery_date: string; lines: { order_line_id: string; issue_id: string; quantity: number }[] }) { return postCartonInventoryRequest<PortalShipment>(base + '/shipments', payload) },
  async previewDeliveryImport(file: File) {
    const form = new FormData(); form.append('file', file)
    return (await http.post<DeliveryImportPreview>(base + '/shipments/import-preview', form, { timeout: 120000 })).data
  },
  async confirmDeliveryImport(file: File, preview: DeliveryImportPreview, selections: { factory_id: string; delivery_note_no: string; registration_mode?: DeliveryRegistrationMode }[]) {
    const form = new FormData(); form.append('file', file); form.append('sha256', preview.sha256)
    form.append('selections', JSON.stringify(selections))
    return (await http.post<{ shipments: PortalShipment[] }>(base + '/shipments/import-confirm', form, { timeout: 120000 })).data
  },
  async receiptOptions(factory_id: string, id: string) {
    return (await http.get<ShipmentReceiptOption[]>(`${base}/internal/shipments/${encodeURIComponent(id)}/receipt-options`, { params: { factory_id } })).data
  },
  linkReceipt(id: string, payload: { factory_id: string; expected_revision: number; receipt_id: string; expected_receipt_revision: number; reason: string }) {
    return postCartonInventoryRequest<PortalShipment>(`${base}/internal/shipments/${encodeURIComponent(id)}/link-receipt`, payload)
  },
  receive(id: string, payload: { new_delivery_confirmation?: boolean; correction_reason?: string; split_confirmation?: string; factory_id: string; expected_revision: number; acceptance_date: string; lines: ReceiveLine[] }) { return postCartonInventoryRequest<PortalShipment>(`${base}/internal/shipments/${id}/receive`, payload) },
  async linkShipmentLine(id: string, lineId: string, payload: { factory_id: string; customer_code: string; order_line_id: string; expected_revision: number; expected_order_revision: number; reason: string }) {
    return (await http.post<PortalShipment>(`${base}/internal/shipments/${encodeURIComponent(id)}/lines/${encodeURIComponent(lineId)}/link-order`, payload)).data
  },
  async linkSampleReceipt(receiptLineId: string, payload: { factory_id: string; order_line_id: string; expected_order_revision: number; reason: string }) {
    return (await http.post<{ receipt_line_id: string; order_line_id: string; order_no: string; quantity: string }>(`${base}/internal/receipt-lines/${encodeURIComponent(receiptLineId)}/link-order`, payload)).data
  },
  async upload(order_id: string, factory_id: string, file: File) { const form = new FormData(); form.append('factory_id', factory_id); form.append('file', file); return (await http.post<PortalAttachment>(`${base}/internal/orders/${order_id}/attachments`, form)).data },
  async download(id: string, factory_id: string, filename: string, internal = false) { const { data } = await http.get<Blob>(`${base}${internal ? '/internal' : ''}/attachments/${id}`, { params: { factory_id }, responseType: 'blob' }); const url = URL.createObjectURL(data); const a = document.createElement('a'); a.href = url; a.download = filename; a.click(); URL.revokeObjectURL(url) },
}
