import { http } from '@/lib/http'
import type { Usage, WorkflowActor } from './api'
export interface PurchaseGroup extends Usage { source_key: string; purchasable: boolean; processes: string[] }
export interface PurchaseSource { id: string; version: number; item_no: string; owner_name: string; process_dates: Record<string, string>; groups: PurchaseGroup[] }
export interface PurchaseLine { source_key: string; quantity: number | null; purchase_unit: string; unit_price: string | null }
export interface PurchaseData { demand_id: string; demand_version: number; supplier_reference: string; currency: string; tax_rate: string | null; delivery_date: string | null; delivery_location: string; payment_terms: string; lines: PurchaseLine[] }
export interface PurchaseChange { kind: 'QUANTITY' | 'CANCEL'; quantities: Record<string, number>; before: Record<string, number | null>; before_status?: string; reason: string; requested_by: WorkflowActor; decision?: string; decided_by?: WorkflowActor; decision_reason?: string }
export interface PurchaseDocument { replacement_of?: { id: string; version: number; demand_version: number }; id: string; version: number; status: string; data: PurchaseData; source: PurchaseSource; occurred_at: string; reason: string; pending_change?: PurchaseChange; last_change?: PurchaseChange; created_by: WorkflowActor; approved_by?: WorkflowActor; release_gate: { can_release: false; blockers: string[] }; effective_on_order: false; released_at: null }
export interface PurchaseAccess { enabled: boolean; schema_ready: boolean; can_write: boolean; can_approve: boolean; can_release: false }
export interface DemandDifference {
  source_key: string; changes: string[]; before: Usage & { processes: string[] } | null; after: Usage & { processes: string[] } | null
  delta: Pick<Usage, 'base' | 'loss' | 'gross'>
}
export interface PreparationChecks {
  document_id: string; document_version: number; demand_id: string; bound_demand_version: number; checked_at: string
  source_current: boolean; source_issue: string | null; can_release: false; cancelled_document_count: number
  source_comparison: {
    status: 'CURRENT' | 'COMPARED' | 'UNAVAILABLE'; target_version: number | null; issue: string | null; unchanged_count: number | null
    rows: DemandDifference[]
    process_comparison?: { available: boolean; issue: string | null; rows: Array<DemandDifference & { process: string }>; unchanged_count: number | null }
    dates: Array<{ process: string; before: string | null; after: string | null }>
  }
  groups: Array<{ demand_version: number; source_key: string; code: string; name: string; attribute: string; material_version: number;
    source_unit: string; purchase_unit: string; status: string; before_status?: string | null; known_quantity: string; complete_quantity: string | null;
    missing_quantity_count: number; related_document_count: number; possible_duplicate: boolean;
    documents: Array<{ id: string; version: number; supplier_reference: string; quantity: number | null; pending_kind: string | null; proposed_quantity: number | null }> }>
}
const base = '/material-purchasing', params = { factory_id: 'huakang-c' }
export const purchaseApi = {
  async access(): Promise<PurchaseAccess> { return (await http.get(`${base}/access`, { params })).data },
  async workspace(): Promise<{ sources: PurchaseSource[]; documents: PurchaseDocument[] }> { return (await http.get(`${base}/workspace`, { params })).data },
  async command(path: string, body: unknown): Promise<PurchaseDocument> { return (await http.post(base + path, body)).data },
  async history(id: string): Promise<{ items: PurchaseDocument[] }> { return (await http.get(`${base}/documents/${encodeURIComponent(id)}/history`, { params })).data },
  async checks(id: string, version: number): Promise<PreparationChecks> { return (await http.get(`${base}/documents/${encodeURIComponent(id)}/checks`, { params: { ...params, expected_version: version } })).data },
}
export const emptyPurchase = (): PurchaseData => ({ demand_id: '', demand_version: 0, supplier_reference: '', currency: '', tax_rate: null, delivery_date: null, delivery_location: '', payment_terms: '', lines: [] })
const statuses: Record<string, string> = { DRAFT: '草稿', PENDING_APPROVAL: '待负责人审核', APPROVED_UNRELEASED: '内部已审，未下发', CHANGE_PENDING: '取消／改量待审核', CANCELLED_UNRELEASED: '已取消（未下发）' }
export const purchaseStatus = (status: string) => statuses[status] || status
