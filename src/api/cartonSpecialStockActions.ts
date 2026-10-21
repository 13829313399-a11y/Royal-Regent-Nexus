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
