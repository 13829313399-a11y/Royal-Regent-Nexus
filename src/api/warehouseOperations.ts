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
export const warehouseOperationsApi = {
  async saveLocation(input: { factory_id: 'huakang-c'; request_id: string; id: string; expected_revision: number; warehouse: string; code: string; status: 'ACTIVE' | 'INACTIVE' }) { return (await http.post<WarehouseLocation>('/warehouse-operations/semi/locations', input)).data },
  async bulkIssue(warehouse: WarehouseDomain, input: WarehouseBulkIssue) { return (await http.post(`/warehouse-operations/${warehouse}/issues/bulk`, input)).data },
  async workspace(warehouse: WarehouseDomain) {
    return (await http.get<WarehouseOperationsWorkspace>(`/warehouse-operations/${warehouse}`, { params: { factory_id: 'huakang-c' } })).data
  },
  async post(warehouse: WarehouseDomain, input: WarehouseDocumentInput) {
    return (await http.post<WarehouseDocument>(`/warehouse-operations/${warehouse}/documents`, input)).data
  },
}
