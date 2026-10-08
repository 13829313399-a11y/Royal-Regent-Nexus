import { http } from '@/lib/http'
import type { MasterRecord } from './fabricMaster'
import type { MaterialCategory } from './fabricReceiving'

export type PurchaseScope = 'PENDING' | 'RETURNED' | 'ALL' | 'TRACKING'
export type PurchaseView = 'OUTSTANDING' | 'NOT_ARRIVED' | 'PARTIAL' | 'ARRIVAL_REVIEW' | 'CHANGED' | 'OVERDUE' | 'DUE_TODAY' | 'AWAITING_DATE' | 'QUANTITY_REVIEW'
export type TrackingSummary = Record<'outstanding' | 'not_arrived' | 'partial' | 'arrival_review' | 'changed', number> & Partial<Record<'overdue' | 'due_today' | 'awaiting_date' | 'quantity_review', number>>
export interface ChaseResolution { id: string; revision: number; starting_quantity: string; evidence: string; actor_name: string; occurred_at: string; cutoff: { first_receipt_id: string | null; receipt_count_at_confirmation: number; warehouse_received_at_confirmation: string; before_all_system_receipts: true } }
export interface PurchaseFilters { supplier?: string; unit?: string; source_category?: string; category?: string; promise_from?: string; promise_to?: string; order_no?: string; production_no?: string; material_code?: string; style_no?: string; import_batch?: string; quantity_review?: string; sort?: string }
export type ImportAction = 'ALL' | 'NEW' | 'UPDATE' | 'UNCHANGED' | 'BLOCKED'
export interface PurchaseFacts {
  source_category?: 'PURCHASE' | 'SUPPLEMENT'
  supplement_no?: string
  style_no?: string
  workshop_group?: string
  release_date?: string | null
  release_date_raw?: string
  status: 'PENDING' | 'RETURNED'
  source_line_id: string
  order_no: string
  supplier: string
  production_no: string
  plan_no: string
  material_code: string
  old_material_code: string
  material_name: string
  unit: string
  contract_no: string
  ordered_quantity: string
  reported_received_quantity: string | null
  reported_received_quantity_basis?: 'EMPTY_PENDING_DELIVERY'
  unit_price: string | null
  order_date: string | null
  order_date_raw: string
  delivery_detail: string
  delivery_note_no: string
  delivery_note_date: string | null
  delivery_note_date_raw: string
  reported_receipt_date: string | null
  reported_receipt_date_raw: string
  supplier_reply: string
  supplier_reply_date: string | null
  second_reply: string
  second_reply_date: string | null
  note: string
  warehouse_note: string
}
export interface ImportCounts { total: number; new: number; updated: number; unchanged: number; blocked: number; warnings: number; pending: number; returned: number }
export interface PurchasePreviewRow { row_key: string; sheet: string; row_number: number; facts: PurchaseFacts; previous: PurchaseFacts | null; changes: string[]; action: Exclude<ImportAction, 'ALL'>; errors: string[]; warnings: string[] }
export interface PurchasePreview { preview_token: string; revision: number; counts: ImportCounts; sheets: string[]; ignored_sheets: string[]; excluded_history?: number; filtered_total: number; offset: number; limit: number; items: PurchasePreviewRow[] }
export interface ImportWithdrawal { actor_name: string; occurred_at: string; reason: string; remove_count: number; restore_count: number }
export interface PurchaseImport { id: string; source_name: string; actor_name: string; occurred_at: string; counts: ImportCounts; scope: PurchaseScope; stock_posted: false; can_withdraw?: boolean; withdrawal?: ImportWithdrawal }
export interface PurchaseLine {
  id: string; revision: number; updated_at: string; facts: PurchaseFacts; reported_outstanding_quantity?: string | null
  unreviewed_changes?: number; tracking?: Partial<Record<keyof TrackingSummary, boolean>>; receipt_count?: number
  prior_received_quantity?: string | null; warehouse_received_quantity?: string; warehouse_outstanding_quantity?: string | null
  starting_chase_quantity?: string | null; chase_resolution?: ChaseResolution | null; receipt_reconciliation_required?: boolean
  receipt_quantity_review_required?: boolean; receipt_quantity_conflict?: boolean; receipt_identity_review_required?: boolean; promise_date?: string | null; promise_text?: string; overdue_days?: number; promise_elapsed_days?: number | null
  material_category?: MaterialCategory | null; master_material?: MasterRecord | null
}
export interface PurchaseDetail extends Omit<PurchaseLine, 'updated_at'> { can_review?: boolean; can_receive?: boolean; active?: boolean; available_locations?: { code: string; name: string; warehouse: string }[]; chase_resolution_history?: ChaseResolution[]; evidence: { id?: string; withdrawal?: ImportWithdrawal; source_name: string; sheet: string; row_number: number; actor_name: string; occurred_at: string; before: Partial<PurchaseFacts>; after: PurchaseFacts }[] }
export interface WithdrawalPreview { id: string; source_name: string; remove_count: number; restore_count: number; preview_token: string; revision: number }

function form(file: File, scope: PurchaseScope) {
  const body = new FormData()
  body.append('factory_id', 'huakang-c'); body.append('scope', scope); body.append('file', file)
  return body
}
const uploadOptions = { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120_000 }
export const fabricProcurementApi = {
  async preview(file: File, scope: PurchaseScope, offset = 0, action: ImportAction = 'ALL') {
    const body = form(file, scope); body.append('offset', String(offset)); body.append('action', action)
    return (await http.post<PurchasePreview>('/fabric-warehouse/procurement/imports/preview', body, uploadOptions)).data
  },
  async apply(file: File, scope: PurchaseScope, previewToken: string, requestId: string, acknowledgeExcluded: boolean) {
    const body = form(file, scope)
    body.append('preview_token', previewToken); body.append('request_id', requestId)
    body.append('confirmed', 'true'); body.append('acknowledge_excluded', String(acknowledgeExcluded))
    return (await http.post<PurchaseImport>('/fabric-warehouse/procurement/imports/apply', body, uploadOptions)).data
  },
  async lines(status: Exclude<PurchaseScope, 'TRACKING'>, search = '', offset = 0, view?: PurchaseView, filters: PurchaseFilters = {}) {
    const cleanFilters = Object.fromEntries(Object.entries(filters).filter(([, value]) => value))
    return (await http.get<{ total: number; items: PurchaseLine[]; offset: number; limit: number; summary: TrackingSummary; options?: { suppliers: string[]; units: string[]; imports?: { id: string; name: string }[] }; can_receive?: boolean }>('/fabric-warehouse/procurement/lines', { params: { factory_id: 'huakang-c', status, search, offset, view, ...cleanFilters } })).data
  },
  async detail(id: string) {
    return (await http.get<PurchaseDetail>(`/fabric-warehouse/procurement/lines/${encodeURIComponent(id)}`, { params: { factory_id: 'huakang-c' } })).data
  },
  async imports(offset = 0) {
    return (await http.get<{ items: PurchaseImport[] }>('/fabric-warehouse/procurement/imports', { params: { factory_id: 'huakang-c', offset } })).data.items
  },
  async withdrawalPreview(id: string) {
    return (await http.get<WithdrawalPreview>(`/fabric-warehouse/procurement/imports/${encodeURIComponent(id)}/withdraw-preview`, { params: { factory_id: 'huakang-c' } })).data
  },
  async withdraw(id: string, previewToken: string, reason: string) {
    return (await http.post<PurchaseImport>(`/fabric-warehouse/procurement/imports/${encodeURIComponent(id)}/withdraw`, { factory_id: 'huakang-c', preview_token: previewToken, reason, confirmed: true })).data
  },
  async reviewChanges(id: string, expectedRevision: number) {
    return (await http.post(`/fabric-warehouse/procurement/lines/${encodeURIComponent(id)}/review-changes`, { factory_id: 'huakang-c', expected_revision: expectedRevision })).data
  },
  async resolveChase(id: string, payload: { request_id: string; expected_source_revision: number; expected_receipt_count: number; expected_resolution_revision: number; starting_quantity: string; evidence: string; confirmed_start: boolean }) {
    return (await http.post(`/fabric-warehouse/procurement/lines/${encodeURIComponent(id)}/resolve-chase`, { factory_id: 'huakang-c', ...payload })).data
  },
}
