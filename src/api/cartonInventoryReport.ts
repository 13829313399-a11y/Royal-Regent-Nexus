import { http } from '@/lib/http'

export type InventoryFlowCategory = 'INBOUND' | 'OUTBOUND' | 'ADJUSTMENT'
export interface InventoryReportRow {
  business_date: string
  customer_code: string
  customer_name: string
  unit: string
  opening_quantity: string
  inbound_quantity: string
  outbound_quantity: string
  adjustment_quantity: string
  ending_quantity: string
  document_count: number
  line_count: number
}
export interface InventoryReportMovement {
  id: string
  occurred_at: string
  customer_code: string
  customer_name: string
  contract_no: string
  item_no: string
  packaging_type: string
  paper_quality: string
  specification: string
  unit: string
  document_no: string
  movement_type: string
  quantity: string
  flow_category: InventoryFlowCategory
  flow_quantity: string
  source_type: string
  reason: string
  location: string
  actor_name: string
}
export interface InventoryOrderReportRow extends Omit<InventoryReportRow, 'business_date'> {
  key: string
  order_id: string | null
  order_line_id: string | null
  order_date: string
  contract_no: string
  item_no: string
  product_name: string
  packaging_type: string
  paper_quality: string
  specification: string
  current_usage_quantity?: string
  current_usage_status?: string
  current_usage_label?: string
  current_positions?: Array<{ location: string; quantity: string }>
  last_movement_at: string
}
export interface InventoryReport {
  rows: InventoryReportRow[]
  order_rows: InventoryOrderReportRow[]
  movements: InventoryReportMovement[]
}
export const cartonInventoryReportApi = {
  async get(factoryId: string, filters: { customer_code: string; date_from: string; date_to: string; search: string }) {
    const response = await http.get<InventoryReport>('/carton-procurement/inventory/report', {
      params: { factory_id: factoryId, ...filters },
    })
    return response.data
  },
}
