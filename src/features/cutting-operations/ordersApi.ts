import type { Planning, PlanTaskInput } from './planning'
import { http } from '@/lib/http'
import { CUTTING_FACTORY } from './navigation'
import type { Command, MasterRecord, Requirement } from './api'

export interface DemandInput { row: number; quantity: string; purchase_mode: 'purchase' | 'no_purchase'; no_purchase_reason: string }
export interface Demand extends Requirement { row: number; quantity: string; purchase_mode?: 'purchase' | 'no_purchase'; no_purchase_reason?: string; theoretical_quantity: string; replied_quantity: string; awaiting_reply_quantity: string; material: { code: string; name: string } }
export interface EtaBatch { row: number; quantity: string; expected_date: string; supplier: string; purchase_reference: string }
export interface OrderData {
  planning?: Planning
  order: Record<string, string | number | null>; dispatch_id: string; bom: MasterRecord | null
  target_sets?: number; quantity_basis?: string; bom_match_basis?: string; purchase_reconciliation_required: boolean
  requisition: { version: number; lines: Demand[]; actor_id: string; created_at: string } | null; batches: EtaBatch[]
  pending_requisition_version?: number | null
  reconciliation_request?: { kind: string; actor_id: string; reason: string } | null
  reconciliation?: { requisition_version: number; disposition: string; evidence: string; actor_id: string; created_at: string }
}
export interface OrderRevision { version: number; data: OrderData; actor_id: string; created_at: string; reason: string }
export interface CuttingOrder { planning_summary?: { states?: string[]; published_stale: boolean; draft_stale: boolean; published_version: number | null; draft_version: number | null }; line_id: string; dispatch_id: string; source_version: number; snapshot: OrderData['order']; received_at: string; needs_receipt: boolean; current: OrderRevision | null; workflow_status?: string; expected_date_passed?: boolean; pending_purchase?: Pick<OrderData, 'requisition' | 'bom' | 'order' | 'batches'> | null }
export interface Page<T> { data: T[]; total: number; page: number; page_size: number }
export type OrderAction = 'receive' | 'bom' | 'requisition' | 'eta' | 'withdraw' | 'reconcile' | 'plan' | 'plan-publish'
export type OrderCommand = Command & ({ tasks: PlanTaskInput[]; removed_task_reasons?: Record<string,string> } | { draft_version: number } | { dispatch_id: string } | { bom_id: string; bom_version: number; target_sets: number; quantity_basis: string; bom_match_basis: string } | { lines: DemandInput[] } | { requisition_version: number; batches: EtaBatch[] } | { requisition_version: number } | { requisition_version: number; disposition: 'not_ordered' | 'cancelled_or_reallocated'; evidence: string; all_handled: boolean })
const base = '/cutting-operations/orders'
const params = { factory_id: CUTTING_FACTORY }
export const ordersApi = {
  async list(page = 1, q = '', status = '', planStatus = ''): Promise<Page<CuttingOrder>> { return (await http.get(base, { params: { ...params, page, q, ...(status ? { status } : {}), ...(planStatus ? { plan_status: planStatus } : {}) } })).data },
  async history(id: string, page = 1): Promise<Page<OrderRevision>> { return (await http.get(`${base}/${encodeURIComponent(id)}/versions`, { params: { ...params, page } })).data },
  async command(id: string, action: OrderAction, body: OrderCommand): Promise<CuttingOrder> { return (await http.post(`${base}/${encodeURIComponent(id)}/${action}`, body)).data },
  async recover(id: string, action: OrderAction, command: OrderCommand): Promise<{ state: 'committed'; result: CuttingOrder } | { state: 'abandoned' }> { return (await http.post(`${base}/${encodeURIComponent(id)}/operations/recover`, { action, command })).data },
}
