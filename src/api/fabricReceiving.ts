import { http } from '@/lib/http'
import type { PurchaseFacts } from './fabricProcurement'

export type MaterialCategory = 'FABRIC' | 'ACCESSORY' | 'THREAD'
export interface ReceiptBatchInput { location_id?: string; quantity: string; location: string; dye_lot: string; roll_no: string }
export interface ReceiveRequest {
  factory_id: 'huakang-c'; request_id: string; expected_source_revision: number; expected_receipt_count: number
  receipt_date: string; delivery_reference: string; delivery_note_date: string | null
  material_category: MaterialCategory; difference_reason: string; note: string
  batches: ReceiptBatchInput[]; confirmed: boolean
}
export interface FabricReceipt {
  id: string; source_line_id: string; source_revision: number; facts: PurchaseFacts; quantity: string; unit: string
  prior_received_quantity: string | null; receipt_date: string; accounting_month: string; delivery_reference: string
  material_category: MaterialCategory; difference_reason: string; note: string; actor_name: string; occurred_at: string; stock_posted: true
  batches: (ReceiptBatchInput & { id: string; quality_status: 'PENDING_INSPECTION' })[]
}
export interface ReceiveSourcesRequest {
  factory_id: 'huakang-c'; request_id: string; receipt_date: string; delivery_reference: string
  delivery_note_date: string | null; note: string; confirmed: boolean
  items: (Pick<ReceiveRequest, 'expected_source_revision' | 'expected_receipt_count' | 'material_category' | 'difference_reason' | 'batches'> & { source_line_id: string })[]
}
export interface ReceiveSourcesResult { request_id: string; receipts: FabricReceipt[] }
export interface FabricStockBatch {
  id: string; receipt_id: string; movement_id: string; kind: 'RECEIPT'; source_line_id: string; facts: PurchaseFacts
  quantity: string; unit: string; location: string; dye_lot: string; roll_no: string; material_category: MaterialCategory
  quality_status: 'PENDING_INSPECTION'; receipt_date: string; accounting_month: string; delivery_reference: string
  actor_name: string; occurred_at: string
}
export const materialCategoryLabels: Record<MaterialCategory, string> = { FABRIC: '布料', ACCESSORY: '辅料', THREAD: '线' }
export const fabricReceivingApi = {
  async receiveBatch(payload: ReceiveSourcesRequest) {
    return (await http.post<ReceiveSourcesResult>('/fabric-warehouse/procurement/receipts/batch', payload)).data
  },
  async receive(id: string, payload: ReceiveRequest) {
    return (await http.post<FabricReceipt>(`/fabric-warehouse/procurement/lines/${encodeURIComponent(id)}/receive`, payload)).data
  },
  async receipts(search = '', offset = 0) {
    return (await http.get<{ total: number; items: FabricReceipt[] }>('/fabric-warehouse/procurement/receipts', { params: { factory_id: 'huakang-c', search, offset } })).data
  },
  async stock(search = '', offset = 0) {
    return (await http.get<{ total: number; items: FabricStockBatch[] }>('/fabric-warehouse/procurement/stock', { params: { factory_id: 'huakang-c', search, offset } })).data
  },
}
