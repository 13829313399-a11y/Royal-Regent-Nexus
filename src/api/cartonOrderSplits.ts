import { http } from '@/lib/http'
import type { CartonInventoryBalanceResponse } from './cartonProcurement'

export interface SplitStock { location_id: string; expected_position_revision: number; quantity: string | number }
export interface SplitLineInput { order_line_id: string; pending_quantity: string | number; stock: SplitStock[] }
export interface SplitTargetInput { contract_no: string; customer_po: string; product_quantity: string | number | null; lines: SplitLineInput[] }
export interface SplitRecord {
  id: string; factory_id: string; order_id: string; order_no: string; item_no: string; customer_code: string
  status: 'ACTIVE' | 'PENDING_WAREHOUSE' | 'CANCELLED'; revision: number; reason: string; created_at: string; created_by_name: string
  targets: Array<Omit<SplitTargetInput, 'lines'> & { lines: Array<SplitLineInput & {
    target_line_id: string; packaging_type: string; paper_quality: string; specification: string; unit: string
    received_quantity: string; pending_remaining: string
  }> }>
}
export interface SplitContext {
  factory_id: string; order_no: string; revision: number; plans: SplitRecord[]
  lines: Array<{ order_line_id: string; packaging_type: string; paper_quality: string; specification: string
    unit: string; usage_quantity: string | null; required_quantity: string; pending_available: string; positions: CartonInventoryBalanceResponse[] }>
}
export interface SplitReceiptInput { order_line_id: string; effective_quantity: string | number }
export interface SplitReceiptPreview {
  confirmation: string; blocked_plans: string[]
  allocations: Array<{ plan_id: string; target_line_id: string; order_line_id: string; contract_no: string; customer_po: string
    item_no: string; packaging_type: string; quantity: string; unit: string }>
}
const base = '/carton-procurement'
export const cartonOrderSplitsApi = {
  async context(factory_id: string, order_no: string) {
    return (await http.get<SplitContext>(`${base}/orders/${encodeURIComponent(order_no)}/splits`, { params: { factory_id } })).data
  },
  async create(factory_id: string, order_no: string, payload: { request_id: string; expected_revision: number; reason: string; targets: SplitTargetInput[] }) {
    return (await http.post<SplitRecord>(`${base}/orders/${encodeURIComponent(order_no)}/splits`, { ...payload, factory_id })).data
  },
  async act(factory_id: string, plan: SplitRecord, action: 'confirm' | 'cancel', reason: string) {
    return (await http.post<SplitRecord>(`${base}/order-splits/${encodeURIComponent(plan.id)}/${action}`,
      { factory_id, expected_revision: plan.revision, reason })).data
  },
  async receiptPreview(factory_id: string, lines: SplitReceiptInput[]) {
    return (await http.post<SplitReceiptPreview>(`${base}/order-splits/receipt-preview`, { factory_id, lines })).data
  },
}
