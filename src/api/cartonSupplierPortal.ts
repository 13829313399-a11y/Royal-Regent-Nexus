import { http } from '@/lib/http'
import { postCartonInventoryRequest } from './cartonInventoryRequest'
import type { LocationAllocation } from './cartonPositions'
export interface PortalAttachment { id: string; filename: string; version: number; size: number; sha256: string; created_at: string }
export interface PortalPaper { id: string; line_no: number; child_no: string; packaging_type: string; paper_quality: string; specification: string; dimension_unit: string; unit: string; required_quantity: string; received_quantity: string; in_transit_quantity: string; remaining_to_ship: string; accepted: boolean; shipping_blocked_reason?: string; commitment_revision: number; promised_date: string; unit_price?: string; currency?: string }
export interface PortalOrder { id: string; order_no: string; customer_name: string; contract_no: string; customer_po: string; item_no: string; product_name: string; status: string; issue_id: string; document_no: string; planned_date: string; awaiting_issue: boolean; lines: PortalPaper[]; attachments: PortalAttachment[] }
export interface ShipmentLine { id: string; order_line_id: string; order_no: string; contract_no: string; customer_po: string; item_no: string; customer_name: string; child_no: string; packaging_type: string; paper_quality: string; specification: string; unit: string; quantity: string; unit_price?: string; currency?: string }
export interface ReceiveLine { shipment_line_id: string; received_quantity: number; damaged_quantity: number; rejected_quantity: number; unusable_quantity: number; unit_price: number; paper_quality: string; specification: string; location_allocations: LocationAllocation[]; difference_reason: string }
export interface PortalShipment { id: string; delivery_note_no: string; delivery_date: string; status: string; revision: number; created_at: string; confirmed_at: string; receipt_id?: string; receipt_status?: string; acceptance_date: string | null; lines: ShipmentLine[]; acceptance_lines: Pick<ReceiveLine, 'shipment_line_id' | 'received_quantity' | 'damaged_quantity' | 'rejected_quantity' | 'unusable_quantity' | 'difference_reason'>[] }
export interface PortalWorkspace { factory_id: string; supplier_name: string; orders: PortalOrder[]; shipments: PortalShipment[] }
export interface SupplierMember { id: string; username: string; display_name: string; status: 'ACTIVE' | 'INACTIVE'; revision: number }
const base = '/carton-supplier'
export const cartonSupplierPortalApi = {
  async memberships() { return (await http.get<{ factory_id: string; supplier_name: string }[]>(base + '/memberships')).data },
  async workspace(factory_id: string, internal = false) { return (await http.get<PortalWorkspace>(base + (internal ? '/internal' : '') + '/workspace', { params: { factory_id } })).data },
  async accept(line: PortalPaper, order: PortalOrder, factory_id: string, promised_date: string) { return (await http.put<PortalOrder>(`${base}/papers/${line.id}/commitment`, { factory_id, issue_id: order.issue_id, expected_revision: line.commitment_revision, promised_date })).data },
  ship(payload: { factory_id: string; delivery_note_no: string; delivery_date: string; lines: { order_line_id: string; issue_id: string; quantity: number }[] }) { return postCartonInventoryRequest<PortalShipment>(base + '/shipments', payload) },
  receive(id: string, payload: { factory_id: string; expected_revision: number; acceptance_date: string; lines: ReceiveLine[] }) { return postCartonInventoryRequest<PortalShipment>(`${base}/internal/shipments/${id}/receive`, payload) },
  async members(factory_id: string) { return (await http.get<SupplierMember[]>(base + '/internal/members', { params: { factory_id } })).data },
  async member(payload: { factory_id: string; username: string; expected_revision: number; status: 'ACTIVE' | 'INACTIVE'; reason: string }) { return (await http.put<SupplierMember[]>(base + '/internal/members', payload)).data },
  async upload(order_id: string, factory_id: string, file: File) { const form = new FormData(); form.append('factory_id', factory_id); form.append('file', file); return (await http.post<PortalAttachment>(`${base}/internal/orders/${order_id}/attachments`, form)).data },
  async download(id: string, factory_id: string, filename: string, internal = false) { const { data } = await http.get<Blob>(`${base}${internal ? '/internal' : ''}/attachments/${id}`, { params: { factory_id }, responseType: 'blob' }); const url = URL.createObjectURL(data); const a = document.createElement('a'); a.href = url; a.download = filename; a.click(); URL.revokeObjectURL(url) },
}
