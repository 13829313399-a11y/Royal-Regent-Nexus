import { http } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'

export type PriceCorrectionAction = 'PROPOSE' | 'SUPPLIER_CONFIRM' | 'SUPPLIER_DISPUTE' | 'FINAL_CONFIRM' | 'WITHDRAW'
export type PriceCorrectionStatus = 'NONE' | 'PENDING_SUPPLIER' | 'SUPPLIER_CONFIRMED' | 'DISPUTED' | 'WITHDRAWN' | 'APPLIED' | 'STALE'
export interface PriceCorrectionBlocker { code: string; message: string; kind: 'INVENTORY_CLOSING' | 'SUPPLIER_SETTLEMENT' | 'ALLOCATION' | 'SOURCE' | 'VALUATION'; id?: string; period?: string }
export interface PriceCorrectionProposal {
  id: string; version: number; status: string; proposed_unit_price: string; free_confirmed: boolean; document_no: string; document_date: string;
  reason: string; source_fingerprint: string; created_at: string; created_by: string;
  supplier_review?: { decision: string; by: string; at: string; reason: string }; applied_at?: string; applied_by?: string;
}
export interface PriceCorrectionEvent { id: string; action: string; actor_name: string; created_at: string; reason: string; proposal_id?: string; data: Record<string, unknown> }
export interface PriceCorrectionImpact {
  impact_fingerprint: string; can_apply: boolean; blockers: PriceCorrectionBlocker[];
  summary: { currency: string; source_cost_difference: string; inbound_cost_difference: string; outbound_cost_difference: string; other_cost_difference: string; ending_cost_difference: string; bridge_difference: string; payable_difference: string | null };
  movements: { movement_id: string; document_no: string; movement_type: string; issue_kind: string; source_type: string; occurred_at: string; quantity: string; unit: string; currency: string; customer_name: string; contract_no: string; item_no: string; old_cost_amount: string; new_cost_amount: string; cost_difference: string }[];
  pools: { id: string; customer_code: string; currency: string; unit: string; quantity: string; old_amount: string; new_amount: string; difference: string }[];
  closings: { id: string; period: string; customer_code: string; currency: string; status: string; revision: number; old_ending_amount: string; new_ending_amount: string; amount_difference: string }[];
}
export interface PriceCorrectionDetail {
  receipt_line_id: string; receipt_id: string; movement_id: string | null; factory_id: string; supplier_id: string; currency: string; quantity: string; unit: string;
  document_no: string; acceptance_date: string | null; customer_name: string; contract_no: string; item_no: string; packaging_type: string; paper_quality: string; specification: string;
  revision: number; source_fingerprint: string; status: PriceCorrectionStatus; can_propose: boolean; allowed_actions: string[];
  raw_unit_price?: string | null; current_cost_unit_price?: string | null; current_unit_price: string | null; original_supplier_unit_price: string | null;
  proposed_unit_price: string | null; proposal: PriceCorrectionProposal | null; versions?: PriceCorrectionProposal[]; history: PriceCorrectionEvent[]; blockers: PriceCorrectionBlocker[];
  impact?: PriceCorrectionImpact; replayed?: boolean;
}
export interface PriceCorrectionsWorkspace { items: PriceCorrectionDetail[]; total: number; limit: number; offset: number; pending_count: number }
export interface PriceCorrectionActionBody {
  factory_id: string; request_id: string; expected_revision: number; source_fingerprint: string; action: PriceCorrectionAction; reason: string;
  proposed_unit_price?: string; free_confirmed?: boolean; document_no?: string; document_date?: string; impact_fingerprint?: string;
}
export interface PriceCorrectionPreviewBody { factory_id: string; expected_revision: number; source_fingerprint: string; proposed_unit_price?: string; free_confirmed?: boolean }
export interface PendingPriceCorrection { receipt_line_id: string; body: PriceCorrectionActionBody }
const base = (internal: boolean) => `${internal ? '/carton-procurement' : '/carton-supplier'}/price-corrections`
const prefix = 'carton-price-correction-pending:v1:'
const pending = new Map<string, PendingPriceCorrection>(), flights = new Map<string, Promise<PriceCorrectionDetail>>()
const key = (internal: boolean, factory: string, viewer: string) => prefix + JSON.stringify([internal, factory, viewer])
const canonical = (value: unknown): unknown => Array.isArray(value) ? value.map(canonical) : value && typeof value === 'object' ? Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([name, item]) => [name, canonical(item)])) : value
export function pendingPriceCorrection(internal: boolean, factory: string, viewer: string): PendingPriceCorrection | null {
  const id = key(internal, factory, viewer)
  if (pending.has(id)) return pending.get(id)!
  try {
    const saved = JSON.parse(sessionStorage.getItem(id) || 'null') as PendingPriceCorrection | null
    if (saved && saved.body?.factory_id === factory && typeof saved.receipt_line_id === 'string' && typeof saved.body.request_id === 'string' && /^[\w-]{8,96}$/.test(saved.body.request_id)) { pending.set(id, saved); return saved }
  } catch { /* Retain in-memory recovery when browser storage is unavailable. */ }
  return null
}
export function clearPendingPriceCorrection(internal: boolean, factory: string, viewer: string) {
  const id = key(internal, factory, viewer); pending.delete(id)
  try { sessionStorage.removeItem(id) } catch { /* Storage may be unavailable. */ }
}
export const cartonPriceCorrectionsApi = {
  async workspace(internal: boolean, query: { factory_id: string; status: 'PENDING' | 'ALL'; keyword: string; limit: number; offset: number }, signal?: AbortSignal) { return (await http.get<PriceCorrectionsWorkspace>(base(internal) + '/workspace', { params: query, signal })).data },
  async detail(internal: boolean, line: string, factory_id: string, signal?: AbortSignal) { return (await http.get<PriceCorrectionDetail>(`${base(internal)}/${encodeURIComponent(line)}`, { params: { factory_id }, signal })).data },
  async preview(line: string, body: PriceCorrectionPreviewBody, signal?: AbortSignal) { return (await http.post<PriceCorrectionDetail>(`${base(true)}/${encodeURIComponent(line)}/preview`, body, { signal })).data },
  act(internal: boolean, line: string, body: Omit<PriceCorrectionActionBody, 'request_id'>, viewer: string, signal?: AbortSignal): Promise<PriceCorrectionDetail> {
    const saved = pendingPriceCorrection(internal, body.factory_id, viewer)
    if (saved) {
      const { request_id: ignored, ...before } = saved.body
      if (saved.receipt_line_id !== line || JSON.stringify(canonical(before)) !== JSON.stringify(canonical(body))) return Promise.reject(new Error('尚有结果待核实的原更正请求，请先核对记录或重试原请求。'))
    }
    const id = key(internal, body.factory_id, viewer), flight = flights.get(id)
    if (flight) return flight
    const request = saved || { receipt_line_id: line, body: { ...body, request_id: createRandomUuid() } }
    pending.set(id, request)
    try { sessionStorage.setItem(id, JSON.stringify(request)) } catch { /* Exact request remains in memory. */ }
    const promise = http.post<PriceCorrectionDetail>(`${base(internal)}/${encodeURIComponent(line)}/actions`, request.body, { signal }).then(({ data }) => {
      clearPendingPriceCorrection(internal, body.factory_id, viewer); return data
    }).catch((cause: unknown) => {
      const status = (cause as { response?: { status?: number } })?.response?.status
      if (status && status >= 400 && status < 500) clearPendingPriceCorrection(internal, body.factory_id, viewer)
      throw cause
    }).finally(() => { flights.delete(id) })
    flights.set(id, promise); return promise
  },
}
