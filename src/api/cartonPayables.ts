import { http } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'

export type PayableKind = 'OPENING' | 'FEE' | 'PAYMENT' | 'PAYMENT_RETURN'
export type PayableActionName = 'PROPOSE_OPENING' | 'REVIEW_OPENING' | 'CONFIRM_OPENING' | 'PROPOSE_FEE' | 'REVISE_FEE' | 'VOID_FEE' | 'REVIEW_FEE' | 'CONFIRM_FEE' | 'RECORD_PAYMENT' | 'RECEIVE_PAYMENT' | 'DECLARE_PAYMENT_RETURN' | 'CONFIRM_PAYMENT_RETURN' | 'REQUEST_VOID' | 'REVIEW_VOID' | 'CONFIRM_VOID' | 'ALLOCATE' | 'DEALLOCATE'
export interface PayableReview { decision: 'CONFIRMED' | 'DISPUTED'; by: string; at: string; reason: string }
export interface PayableVersion {
  event_id: string; version: number; status: string; direction: string; amount: string; signed_amount: string; date: string;
  document_no: string; reason: string; cutoff_date?: string; category?: string; related_settlement_id?: string;
  baseline_fingerprint?: string; acknowledge_unknown_sources?: boolean; supplier_review?: PayableReview; confirmed_by?: string; confirmed_at?: string;
}
export interface PayableEvent { id: string; action: string; actor_name: string; created_at: string; reason: string; target_id?: string; data: Record<string, unknown> }
export interface PayableEntry {
  id: string; kind: PayableKind; status: string; revision: number; currency: string; amount: string; signed_amount?: string; date: string;
  document_no: string; reason: string; direction?: string; category?: string; related_settlement_id?: string;
  bank_reference?: string; parent_payment_id?: string; confirmation_reference?: string; receipt_status?: string; receipt_review?: PayableReview;
  void_request?: { supplier_review?: PayableReview; correction_reference?: string; reason?: string } | null;
  active: PayableVersion | null; proposal: PayableVersion | null; versions?: PayableVersion[]; parent_payment_document_no?: string; needs_reconfirmation?: boolean; unknown_sources?: unknown[];
  allowed_actions: string[]; history: PayableEvent[];
}
export interface PayableObligation {
  id: string; kind: 'OPENING' | 'SETTLEMENT' | 'FEE'; record_id: string; version: number; period?: string; document_no: string; date: string;
  currency: string; signed_amount: string; direction: 'DEBIT' | 'CREDIT'; allocated_amount: string; remaining_amount: string;
  can_allocate: boolean; status: 'CURRENT' | 'REOPENED_HOLD' | 'STALE'; source_fingerprint: string;
}
export interface PayableAllocationSource {
  id: string; source_kind: 'PAYMENT' | 'CREDIT'; record_id: string; document_no: string; date: string; currency: string;
  amount: string; allocated_amount: string; reserved_return_amount: string; available_amount: string; can_allocate: boolean;
  returnable_amount?: string; can_declare_payment_return?: boolean;
}
export interface PayableAllocation {
  id: string; source_kind: 'PAYMENT' | 'CREDIT'; source_id: string; target_kind: 'OPENING' | 'SETTLEMENT' | 'FEE'; target_id: string;
  amount: string; status: 'ACTIVE' | 'RELEASED'; actor_name: string; created_at: string; reason: string; released_at?: string; released_by?: string;
  source_document_no?: string; target_document_no?: string; target_version?: number; target_period?: string | null; source_date?: string; target_date?: string;
}
export interface PayablesSummary {
  opening_signed: string; confirmed_settlements: string; fees_signed: string; internal_paid: string; supplier_received: string;
  paid_awaiting_receipt: string; payment_returns_confirmed: string; allocated: string; unapplied_payment: string; unapplied_credit: string;
  balance_due_signed: string; needs_reconfirmation: boolean;
}
export interface PayablesWorkspace {
  factory_id: string; supplier_id: string; supplier_name: string; currency: string; revision: number; source_fingerprint: string; allowed_actions: string[];
  opening: PayableEntry | null; records: { items: PayableEntry[]; total: number; limit: number; offset: number };
  obligations: PayableObligation[]; allocation_sources: PayableAllocationSource[]; allocations: PayableAllocation[];
  summary: PayablesSummary; issues: string[]; changed_record_id?: string; replayed?: boolean;
}
export interface PayableDetail extends PayableEntry { account_revision: number; source_fingerprint: string }
export interface PayableAction {
  factory_id: string; supplier_id?: string; currency: string; request_id: string; expected_revision: number; source_fingerprint: string;
  action: PayableActionName; target_id?: string; reason: string; cutoff_date?: string; direction?: 'PAYABLE' | 'CREDIT' | 'ADD_PAYABLE' | 'DEDUCT_PAYABLE';
  amount?: string; document_no?: string; acknowledge_unknown_sources?: boolean; fee_date?: string;
  category?: 'FREIGHT' | 'DISCOUNT' | 'TAX' | 'ROUNDING' | 'OTHER'; related_settlement_id?: string; payment_date?: string; bank_reference?: string;
  decision?: 'CONFIRMED' | 'DISPUTED'; parent_payment_id?: string; return_date?: string; confirmation_reference?: string; correction_reference?: string;
  source_kind?: 'PAYMENT' | 'CREDIT'; source_id?: string; targets?: { target_kind: 'OPENING' | 'SETTLEMENT' | 'FEE'; target_id: string; amount: string }[];
  allocation_ids?: string[];
}
export interface PayablesQuery { factory_id: string; supplier_id?: string; currency: string; kind: 'ALL' | PayableKind; status: 'ALL' | 'PENDING'; keyword: string; limit: number; offset: number }
const base = (internal: boolean) => `${internal ? '/carton-procurement' : '/carton-supplier'}/payables`
const prefix = 'carton-payables-pending:v1:'
const pending = new Map<string, PayableAction>(), flights = new Map<string, Promise<PayablesWorkspace>>()
const key = (internal: boolean, factory: string, currency: string, viewer: string) => prefix + JSON.stringify([internal, factory, currency, viewer])
const canonical = (value: unknown): unknown => Array.isArray(value) ? value.map(canonical) : value && typeof value === 'object' ? Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([name, item]) => [name, canonical(item)])) : value
export function pendingPayableAction(internal: boolean, factory: string, currency: string, viewer: string): PayableAction | null {
  const id = key(internal, factory, currency, viewer)
  if (pending.has(id)) return pending.get(id)!
  try {
    const saved = JSON.parse(sessionStorage.getItem(id) || 'null') as PayableAction | null
    if (saved && saved.factory_id === factory && saved.currency === currency && typeof saved.request_id === 'string' && /^[\w-]{16,96}$/.test(saved.request_id)) { pending.set(id, saved); return saved }
  } catch { /* A disabled or unavailable tab store does not affect in-memory retries. */ }
  return null
}
export function clearPendingPayableAction(internal: boolean, factory: string, currency: string, viewer: string) {
  const id = key(internal, factory, currency, viewer); pending.delete(id)
  try { sessionStorage.removeItem(id) } catch { /* The current tab may disable storage. */ }
}
export const cartonPayablesApi = {
  async workspace(internal: boolean, query: PayablesQuery, signal?: AbortSignal) { return (await http.get<PayablesWorkspace>(base(internal) + '/workspace', { params: query, signal })).data },
  async detail(internal: boolean, id: string, query: { factory_id: string; supplier_id?: string; currency: string }, signal?: AbortSignal) { return (await http.get<PayableDetail>(`${base(internal)}/records/${encodeURIComponent(id)}`, { params: query, signal })).data },
  async export(internal: boolean, query: { factory_id: string; supplier_id?: string; currency: string }, signal?: AbortSignal) { return (await http.get<Blob>(base(internal) + '/export', { params: query, signal, responseType: 'blob' })).data },
  act(internal: boolean, body: Omit<PayableAction, 'request_id'>, viewer: string, signal?: AbortSignal): Promise<PayablesWorkspace> {
    const saved = pendingPayableAction(internal, body.factory_id, body.currency, viewer)
    if (saved) {
      const { request_id: ignored, ...before } = saved
      if (JSON.stringify(canonical(before)) !== JSON.stringify(canonical(body))) return Promise.reject(new Error('尚有结果待核实的原请求。请先核对凭证或重试原请求。'))
    }
    const id = key(internal, body.factory_id, body.currency, viewer), current = flights.get(id)
    if (current) return current
    const payload: PayableAction = saved || { ...body, request_id: createRandomUuid() }
    pending.set(id, payload)
    try { sessionStorage.setItem(id, JSON.stringify(payload)) } catch { /* In-memory recovery still retains the exact request. */ }
    const request = http.post<PayablesWorkspace>(base(internal) + '/actions', payload, { signal }).then(({ data }) => {
      clearPendingPayableAction(internal, body.factory_id, body.currency, viewer); return data
    }).catch((cause: unknown) => {
      const status = (cause as { response?: { status?: number } })?.response?.status
      if (status && status >= 400 && status < 500) clearPendingPayableAction(internal, body.factory_id, body.currency, viewer)
      throw cause
    }).finally(() => { flights.delete(id) })
    flights.set(id, request); return request
  },
}
