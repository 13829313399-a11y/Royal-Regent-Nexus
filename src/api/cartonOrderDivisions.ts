import { http } from '@/lib/http'
import type { SplitContext } from './cartonOrderSplits'
import type { PrintPlan } from './cartonPrintSplits'

export interface DivisionMember { order_id: string; order_no: string; contract_no: string }
export interface OrderDivisionInfo { source_order_no?: string; source_contract_no?: string; children: DivisionMember[] }
export interface DivisionContext extends SplitContext {
  supplier_notified: boolean; can_split: boolean; block_reason: string
  order_split: OrderDivisionInfo | null; previous_proposals: PrintPlan[]
}
export interface DivisionCommand {
  request_id: string; expected_revision: number; reason: string; legacy_splits: Record<string, number>
  targets: { contract_no: string; customer_po: string; product_quantity: string | number | null; due_date: string
    lines: { order_line_id: string; quantity: string | number }[] }[]
}
export interface OrderDivision { id: string; supplier_notified: boolean; members: (DivisionMember & { role: string })[] }
export const cartonOrderDivisionsApi = {
  async context(factory_id: string, order_no: string) {
    return (await http.get<DivisionContext>(`/carton-procurement/orders/${encodeURIComponent(order_no)}/independent-splits`, { params: { factory_id } })).data
  },
  async create(factory_id: string, order_no: string, body: DivisionCommand) {
    return (await http.post<OrderDivision>(`/carton-procurement/orders/${encodeURIComponent(order_no)}/independent-splits`, { ...body, factory_id })).data
  },
}
