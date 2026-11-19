import { http } from '@/lib/http'

export type SpecialStockAction = 'RETURN' | 'REPLENISH' | 'UNDO'
export interface SpecialStockLine {
  receipt_line_id: string; movement_id: string; location_id: string; location_label: string; receipt_no: string
  request_line_id: string; item_no: string; packaging_type: string; paper_quality: string; specification: string
  dimension_unit: string; unit: string; currency: string; received_quantity: string; safe_quantity: string
  inventory_unit_price: string | null; inventory_amount: string | null; blockers: string[]
}
export interface SpecialStockSource { id: string; request_no: string; revision: number; status: string; kind?: string; supplier_name?: string }
export interface SpecialStockPreview {
  source_request: SpecialStockSource; source_fingerprint: string; can_return: boolean; can_replenish: boolean
  blockers: string[]; lines: SpecialStockLine[]
  replacement: null | { parent_request_id: string; parent_request_no: string; responsibility: 'OWN' | 'SUPPLIER'; can_undo: boolean; blockers: string[] }
}
export interface SpecialStockCommand {
  factory_id: string; request_id: string; expected_revision: number; source_fingerprint: string
  action: 'RETURN' | 'REPLENISH'; reason: string; return_date?: string; required_date?: string; responsibility?: 'OWN' | 'SUPPLIER'
  lines: { receipt_line_id: string; movement_id: string; location_id: string; quantity: string }[]
}
export interface SpecialStockUndo { factory_id: string; request_id: string; expected_revision: number; reason: string }
export interface SpecialStockResult {
  action: SpecialStockAction; movement_ids: string[]; source_request: SpecialStockSource; replenishment_request: SpecialStockSource | null
}
const path = (id: string) => `/carton-special-requests/${encodeURIComponent(id)}/stock-actions`
export const cartonSpecialStockActionsApi = {
  async preview(factory: string, id: string, signal?: AbortSignal) {
    return (await http.get<SpecialStockPreview>(path(id), { params: { factory_id: factory }, signal })).data
  },
  async submit(id: string, body: SpecialStockCommand, signal?: AbortSignal) {
    return (await http.post<SpecialStockResult>(path(id), body, { signal })).data
  },
  async undo(id: string, body: SpecialStockUndo, signal?: AbortSignal) {
    return (await http.post<SpecialStockResult>(`${path(id)}/undo`, body, { signal })).data
  },
}

export interface OrderStockReturnLine extends Pick<SpecialStockLine, 'location_id' | 'location_label' | 'packaging_type' | 'paper_quality' | 'specification' | 'dimension_unit' | 'unit' | 'safe_quantity' | 'blockers'> {
  order_line_id: string
}
export interface OrderStockReturnCommand extends SpecialStockUndo {
  action: 'RETURN'
  source_fingerprint: string
  return_date: string
  lines: (Pick<OrderStockReturnLine, 'order_line_id' | 'location_id'> & { quantity: string })[]
}
interface OrderStockReturnPreview {
  order_no: string
  revision: number
  status: string
  source_fingerprint: string
  blockers: string[]
  lines: OrderStockReturnLine[]
}

const orderReturnPath = (orderNo: string) => `/carton-procurement/orders/${encodeURIComponent(orderNo)}/return-stock`
export const cartonOrderStockReturnApi = {
  async preview(factory: string, orderNo: string, signal?: AbortSignal) {
    const { data } = await http.get<OrderStockReturnPreview>(orderReturnPath(orderNo), { params: { factory_id: factory }, signal })
    return {
      source_request: { id: data.order_no, request_no: data.order_no, revision: data.revision, status: data.status },
      source_fingerprint: data.source_fingerprint,
      can_return: data.lines.some(line => Number(line.safe_quantity) > 0 && !line.blockers.length),
      can_replenish: false, blockers: data.blockers, lines: data.lines, replacement: null,
    }
  },
  async submit(orderNo: string, body: OrderStockReturnCommand, signal?: AbortSignal) {
    const { action, ...payload } = body
    await http.post(orderReturnPath(orderNo), payload, { signal })
    return { action, replenishment_request: null }
  },
}
