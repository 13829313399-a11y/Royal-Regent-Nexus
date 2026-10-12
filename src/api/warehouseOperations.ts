import { http } from '@/lib/http'

export type WarehouseDomain = 'fabric' | 'semi'
export type WarehouseOperationKind = 'RECEIPT' | 'REQUEST' | 'ISSUE' | 'RETURN' | 'TRANSFER' | 'QUALITY' | 'CORRECTION' | 'TASK' | 'PROCESS_SEND' | 'PROCESS_RETURN' | 'PACK_SEND' | 'PACK_RECEIVE' | 'LOCATION_BIND'
export type WarehouseQuality = 'PENDING_INSPECTION' | 'QUALIFIED' | 'REJECTED' | 'HOLD'
export interface WarehouseDocumentInput {
  factory_id: 'huakang-c'; request_id: string; expected_revision: number; kind: WarehouseOperationKind; business_date: string
  source_system: string; source_no: string; source_line: string; source_version: string
  item_code: string; item_name: string; unit: string; process_state: string; material_category: 'FABRIC' | 'ACCESSORY' | 'THREAD'
  location_id?: string; confirmed?: boolean
  location: string; lot: string; roll_no: string; quantity: string; consumed_quantity: string; counterparty: string
  production_no: string; purpose: string; due_date: string | null; batch_id: string; original_id: string; task_id: string
  quality_status: WarehouseQuality; responsible_person: string; reason: string
  allocations: { production_no: string; quantity: string }[]
  reversed_kind?: WarehouseOperationKind
}
export interface WarehouseLocation { id: string; warehouse: string; code: string; label: string; status: string; revision: number }
export interface WarehouseBulkIssue { factory_id: 'huakang-c'; request_id: string; expected_revision: number; business_date: string; counterparty: string; reason: string; items: { batch_id: string; quantity: string; counterparty: string }[] }
export interface WarehouseBatch {
  location_id?: string; location_verified?: boolean; location_status?: string; location_label?: string; warehouse_name?: string
  inbound_quantity?: string; outbound_quantity?: string; transfer_quantity?: string
  id: string; item_code: string; item_name: string; unit: string; process_state: string; material_category: string
  location: string; lot: string; roll_no: string; quantity: string; available_quantity: string; quality_status: WarehouseQuality
  source_no: string; source_document: string; received_on: string; counterparty: string; production_no: string
}
export interface WarehouseDocument {
  id: string; kind: WarehouseOperationKind; sequence: number; business_date: string; data: WarehouseDocumentInput
  actor_name: string; occurred_at: string; reversed?: boolean; batch_snapshot?: WarehouseBatch
  read_only?: boolean
  issued_quantity?: string; returned_quantity?: string; received_quantity?: string; consumed_quantity?: string
}
export interface WarehouseOperationsWorkspace {
  revision: number; stock: WarehouseBatch[]; documents: WarehouseDocument[]
  original_receipts?: WarehouseDocument[]
  locations?: WarehouseLocation[]
  permissions: Record<'read' | 'operate' | 'quality' | 'correct', boolean> & { master?: boolean }
}
export type FabricMonthlyView = 'monthly' | 'reconciliation' | 'recipients'
export interface FabricMonthlyQuery { month: string; direction: '' | 'IN' | 'OUT'; channel: '' | 'MANUAL' | 'SCAN'; party_key: string }
export interface FabricMonthlyQuantities {
  received: string; receipt_reversed: string; net_received: string; issued: string; issue_reversed: string
  returned: string; net_issued: string; net_outbound: string; stock_change: string
  manual_received: string; scan_received: string; manual_outbound: string; scan_outbound: string
}
export interface FabricMonthlyDetail {
  id: string; date: string; direction: 'IN' | 'OUT'; kind: 'RECEIPT' | 'ISSUE' | 'RETURN'; correction: boolean
  original_id: string; channel: 'MANUAL' | 'SCAN'; channel_label: string; origin: string; source_no: string; source_line: string
  document_id: string; party_key: string; party_name: string; recorded_party: string; supplier_id: string; identity_basis: string
  item_code: string; item_name: string; unit: string; quantity: string; actor_name: string
  unit_price: string; price_unit: string; currency: string; price_note: string
  amount?: string
}
export interface FabricMonthlyReport extends FabricMonthlyQuery {
  parties: { key: string; name: string; direction: 'IN' | 'OUT' }[]
  summary: (FabricMonthlyQuantities & { direction: 'IN' | 'OUT'; party_key: string; party_name: string; item_code: string; item_name: string; unit: string; document_count: number })[]
  totals: (FabricMonthlyQuantities & { unit: string })[]; details: FabricMonthlyDetail[]
  version: string; cutting_interface: 'PENDING'; basis: string; live: boolean; closed: boolean; amounts_calculated: boolean
}
export interface FabricOrderSummaryQuery { date_from: string; date_to: string; search: string; supplier: string }
export interface FabricOrderQuantities { opening: string; inbound: string; outbound: string; adjustment: string; balance: string }
export interface FabricOrderIdentity {
  key: string; source_line_id: string; order_no: string; production_no: string; style_no: string; supplier: string
  item_code: string; item_name: string; unit: string; linked: boolean
}
export interface FabricOrderRow extends FabricOrderIdentity, FabricOrderQuantities { document_count: number }
export interface FabricOrderDetail extends FabricOrderIdentity {
  id: string; date: string; mode: 'INBOUND' | 'OUTBOUND' | 'ADJUSTMENT'; label: string; quantity: string; stock_change: string
  moved_quantity: string; source_no: string; original_id: string; recipient: string; location: string; channel: 'MANUAL' | 'SCAN'
  actor_name: string; reason: string; sequence: number
}
export interface FabricOrderReport extends FabricOrderSummaryQuery {
  rows: FabricOrderRow[]; details: FabricOrderDetail[]; totals: (FabricOrderQuantities & { unit: string })[]
  suppliers: string[]; basis: string; version: string
}
export const warehouseOperationsApi = {
  async orderSummary(query: FabricOrderSummaryQuery) { return (await http.get<FabricOrderReport>('/warehouse-operations/fabric/order-summary', { params: { factory_id: 'huakang-c', ...query } })).data },
  async monthly(query: FabricMonthlyQuery) { return (await http.get<FabricMonthlyReport>('/warehouse-operations/fabric/monthly', { params: { factory_id: 'huakang-c', ...query } })).data },
  async exportMonthly(query: FabricMonthlyQuery, version: string) { return (await http.get<Blob>('/warehouse-operations/fabric/monthly/export', { params: { factory_id: 'huakang-c', ...query, version }, responseType: 'blob' })).data },
  async saveLocation(input: { factory_id: 'huakang-c'; request_id: string; id: string; expected_revision: number; warehouse: string; code: string; status: 'ACTIVE' | 'INACTIVE' }) { return (await http.post<WarehouseLocation>('/warehouse-operations/semi/locations', input)).data },
  async bulkIssue(warehouse: WarehouseDomain, input: WarehouseBulkIssue) { return (await http.post(`/warehouse-operations/${warehouse}/issues/bulk`, input)).data },
  async workspace(warehouse: WarehouseDomain) {
    return (await http.get<WarehouseOperationsWorkspace>(`/warehouse-operations/${warehouse}`, { params: { factory_id: 'huakang-c' } })).data
  },
  async post(warehouse: WarehouseDomain, input: WarehouseDocumentInput) {
    return (await http.post<WarehouseDocument>(`/warehouse-operations/${warehouse}/documents`, input)).data
  },
}
