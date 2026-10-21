import { http } from '@/lib/http'
import type { ReturnDateEvidence } from './cartonSupplierSettlement'

export type ReturnAction = 'ENROLL' | 'RECEIVE' | 'DISPUTE' | 'PROPOSE_CREDIT' | 'CONFIRM_CREDIT'
  | 'DECLARE_REFUND' | 'CONFIRM_REFUND' | 'VOID' | 'RECONFIRM_DATE' | 'CONFIRM_DATE'
export interface ReturnCredit { id: string; confirmation_id?: string; unit_price: string; amount: string; document_no: string; credit_date: string; status: string; reason?: string; actor_name?: string; created_at?: string; confirmed_by?: string; confirmed_at?: string }
export interface ReturnReceipt { id: string; decision: 'RECEIVE' | 'DISPUTE'; quantity: string; receipt_date: string; document_no: string; status: 'ACTIVE' | 'VOID'; reason: string; actor_name: string; created_at: string }
export interface ReturnRefund { id: string; kind: 'CASH' | 'OFFSET'; amount: string; refund_date: string; document_no: string; status: 'PROPOSED' | 'CONFIRMED' | 'VOID'; reason: string; actor_name: string; created_at: string; credit_event_id: string; confirmation_id?: string; confirmation_reference?: string; confirmed_by?: string; confirmed_at?: string }
export interface ReturnHistory { id: string; action: string; actor_name: string; created_at: string; reason: string; target_event_id?: string }
export interface ReturnDateHistory { id: string; event_type: string; created_at: string; actor_name: string; return_date: string; before_date?: string; revision?: number; reason?: string }
export type ReturnDateState = ReturnDateEvidence | { return_date: null; revision: 0; event_id: null; fingerprint: string; date_basis: 'RETURN_POSTING'; posting_date: string }
export interface SupplierReturn {
  movement_id: string; factory_id: string; document_no: string; customer_name: string; contract_no: string;
  item_no: string; packaging_type: string; paper_quality: string; specification: string; unit: string; currency: string;
  quantity: string; return_date: string | null; posting_date: string; date_evidence: ReturnDateState | null; date_history?: ReturnDateHistory[];
  revision: number; source_fingerprint: string; enabled: boolean; legacy: boolean; source_active: boolean; pending: boolean;
  receipt_status: string; received_quantity: string; disputed_quantity: string; remaining_quantity: string;
  credit_status: string; credit: ReturnCredit | null; credits?: ReturnCredit[]; cash_confirmed_amount: string; offset_confirmed_amount: string;
  deduction_amount: string | null; receipts: ReturnReceipt[]; refunds: ReturnRefund[]; history: ReturnHistory[];
  date_reconfirmation_required: boolean; allowed_actions: string[]; can_correct_date?: boolean; voidable_event_ids?: string[]; void_confirmation_required_event_ids?: string[];
}
export interface ReturnWorkspace { items: SupplierReturn[]; total: number; limit: number; offset: number; pending_count: number; legacy_count: number }
export interface ReturnActionBody {
  factory_id: string; request_id: string; expected_revision: number; source_fingerprint: string; action: ReturnAction;
  target_event_id?: string; reason: string; quantity?: string; receipt_date?: string; document_no?: string;
  unit_price?: string; credit_date?: string; kind?: 'CASH' | 'OFFSET'; amount?: string; refund_date?: string;
  confirmation_reference?: string;
}
const base = (internal: boolean) => `${internal ? '/carton-procurement' : '/carton-supplier'}/returns`
export const cartonSupplierReturnsApi = {
  async list(factory: string, internal: boolean, query: { limit: number; offset: number; status?: string; keyword?: string }, signal?: AbortSignal) {
    return (await http.get<ReturnWorkspace>(base(internal) + '/workspace', { params: { factory_id: factory, ...query }, signal })).data
  },
  async detail(id: string, factory: string, internal: boolean, signal?: AbortSignal) {
    return (await http.get<SupplierReturn>(`${base(internal)}/${encodeURIComponent(id)}`, { params: { factory_id: factory }, signal })).data
  },
  async act(id: string, internal: boolean, body: ReturnActionBody, signal?: AbortSignal) {
    return (await http.post<SupplierReturn>(`${base(internal)}/${encodeURIComponent(id)}/actions`, body, { signal })).data
  },
}
