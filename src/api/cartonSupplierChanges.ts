import { http } from '@/lib/http'

export interface SupplierChangeLine {
  id: string; packaging_type: string; paper_quality: string; specification: string; dimension_unit?: string; unit: string
  quantity: string; before_quantity: string
  before_material?: Partial<Record<'packaging_type' | 'paper_quality' | 'specification' | 'dimension_unit', string>>
}
export interface SupplierChangeTask {
  publication_history?: { source_id: string; document_no: string; created_at: string; action: string; status: string; read: boolean; responded_by: string; responded_at: string; reason: string; planned_date: string; superseded: boolean; response_history?: { status: string; reason: string; promised_date: string; actor_name: string; created_at: string }[]; lines: Pick<SupplierChangeLine, 'id' | 'packaging_type' | 'paper_quality' | 'specification' | 'unit' | 'quantity'>[] }[]
  source_kind: 'REGULAR' | 'REPLENISHMENT' | 'SPECIAL'; source_id: string; factory_id: string
  order_id: string; order_no: string; document_no: string; expected_revision: number; status: string
  is_cancellation: boolean; read: boolean; read_at: string; reason: string; responded_by: string; responded_at: string
  promised_date: string; planned_date: string; before_date: string; created_at: string; age_days: number
  change_reason?: string; customer_due_date?: string; before_customer_due_date?: string
  overdue: boolean; action: string; responsibility: string; lines: SupplierChangeLine[]; material_changed: boolean
  pending: boolean; can_respond: boolean
}
export type SupplierChangeAction = 'READ' | 'ACCEPT' | 'DISPUTE' | 'ACK_CANCEL'
export interface SupplierChangeWorkspace { items: SupplierChangeTask[]; pending_count: number; overdue_count: number; disputed_count: number }
export const cartonSupplierChangesApi = {
  async list(factory: string, internal = false, signal?: AbortSignal) {
    return (await http.get<SupplierChangeWorkspace>(`/carton-supplier/${internal ? 'internal/' : ''}changes`, { params: { factory_id: factory }, signal })).data
  },
  async respond(body: { factory_id: string; source_kind: SupplierChangeTask['source_kind']; source_id: string; expected_revision: number; action: SupplierChangeAction; request_id: string; promised_date?: string; reason?: string }, signal?: AbortSignal) {
    return (await http.post<SupplierChangeTask>('/carton-supplier/changes/respond', body, { signal })).data
  },
}
