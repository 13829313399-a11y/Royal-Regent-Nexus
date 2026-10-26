import { http } from '@/lib/http'

export interface SupplierPriceUpdate {
  manual_unit_price: string | null; supplier_unit_price: string; amount_difference: string | null;
  quantity: string; currency: string; occurred_at: string; document_no: string;
}
export interface SupplierSource {
  supplier_price_update?: SupplierPriceUpdate;
  return_movement_id?: string;
  return_agreement?: { receipt_event_ids: string[]; credit_event_id: string | null; credit_document_no: string; credit_date: string | null; pending_credit_id?: string | null; supplier_date_confirmation?: string | null; internal_date_confirmation?: string | null };
  refund_evidence?: { id: string; confirmation_id: string; credit_event_id: string; confirmation_reference: string };
  return_date?: string | null; posting_date?: string;
  special_request_id?: string; special_request_no?: string; receipt_id?: string; delivery_id?: string;
  special_request_kind?: 'SAMPLE' | 'WORKSHOP_MISC' | 'SUPPLIER_GIFT';
  source_key: string; kind: 'RECEIPT' | 'RETURN' | 'RETURN_REFUND'; document_no: string; acceptance_date: string | null;
  date_basis: string; customer_name: string; contract_no: string; item_no: string; packaging_type: string;
  paper_quality: string; specification: string; dimension_unit?: string; unit: string; quantity: string; unit_price: string | null;
  amount: string | null; currency: string; issues: string[];
  price_review?: { id: string; status: 'PENDING' | 'PROPOSED' | 'CONFIRMED'; revision: number };
  supplier_delivery?: { original_quantity?: string; shipment_id: string; line_id: string; document_no: string; delivery_date: string;
    quantity: string; unit_price: string | null; amount: string | null; currency: string;
    received_quantity: string; damaged_quantity: string; rejected_quantity: string; unusable_quantity: string;
    original_unit_price?: string | null; price_warning?: string;
    difference_reason: string; quantity_difference: string; price_difference: string | null } | null;
}
export interface UnsettledShipment { shipment_id: string; document_no: string; delivery_date: string; acceptance_date: string | null; status: string; reason: string; line_id?: string; item_no?: string; specification?: string; unit?: string; quantity?: string; original_unit_price?: string | null; difference_reason?: string }
export interface SupplierReview { decision: 'CONFIRMED' | 'DISPUTED'; reason: string; by: string; at: string; fingerprint: string }
export interface StatementLine {
  id: string; source_key: string; document_no: string; quantity: string | null; unit_price: string | null;
  amount: string | null; approved_return_unit_price: string | null; credit_document_no: string;
  credit_date: string | null; note: string;
}
export interface SettlementDocument {
  id: string; factory_id: string; supplier_id: string; period: string; currency: string; version: number;
  revision: number; status: 'DRAFT' | 'CONFIRMED' | 'SUPERSEDED'; source_fingerprint: string; sources: SupplierSource[];
  statement: { origin?: 'MANUAL' | 'COLLABORATION'; statement_no: string; tax_basis: 'INCLUSIVE' | 'EXCLUSIVE'; same_price_basis: boolean; lines: StatementLine[] };
  result: { issues: string[]; line_results: { id: string; source_key: string; quantity_difference: string | null; price_difference: string | null; amount_difference: string | null; issues: string[] }[]; inbound_amount: string | null; return_amount: string | null; cash_refund_amount?: string | null; return_deduction_amount?: string | null; net_amount: string | null; statement_amount: string | null; supplier_review?: SupplierReview; unsettled_shipments?: UnsettledShipment[] };
  created_at: string; updated_at: string; confirmed_at: string; confirmed_by: string; reopen_reason: string; stale: boolean;
}
export interface SupplierWorkspace {
  factory_id: string; supplier_id: string; supplier_name: string; period: string; currency: string;
  source_fingerprint: string; sources: SupplierSource[]; issues: string[]; documents: SettlementDocument[];
  undated_receipts: { receipt_id: string; revision: number; document_no: string; confirmed_at: string; acceptance_date: null }[];
  collaboration?: { sources: SupplierSource[]; lines: StatementLine[]; source_fingerprint: string; unsettled_shipments: UnsettledShipment[] } | null;
}
export interface SettlementSave {
  origin?: 'MANUAL' | 'COLLABORATION';
  factory_id: string; supplier_id: string; period: string; currency: string; source_fingerprint: string;
  id?: string; expected_revision?: number; statement_no: string; tax_basis: 'INCLUSIVE' | 'EXCLUSIVE'; same_price_basis: boolean; lines: StatementLine[];
}
export interface SupplierSettlementWorkspace { factory_id: string; supplier_name: string; period: string; currency: string; documents: SettlementDocument[] }
export interface ReturnDateEvidence {
  return_date: string; revision: number; event_id: string; fingerprint: string;
  date_basis: 'RETURN_ACTUAL'; posting_date: string;
}
export interface ReturnDateCorrection {
  factory_id: string; request_id: string; expected_evidence_revision: number;
  expected_evidence_fingerprint: string; return_date: string; reason: string;
}
export interface ReturnDateCorrectionResult {
  movement_id: string; return_date: string; posting_date: string;
  date_basis: 'RETURN_ACTUAL'; date_evidence: ReturnDateEvidence;
}
export interface MonthlySettlementLine {
  source_key: string; kind: 'RECEIPT' | 'RETURN' | 'RETURN_REFUND'; document_no: string; acceptance_date: string | null;
  date_basis: string; customer_name?: string; contract_no?: string; item_no?: string; packaging_type?: string;
  paper_quality?: string; specification?: string; unit?: string; quantity: string; unit_price: string | null;
  amount: string | null; currency: string; issues: string[]; price_basis?: string;
}
export type MonthlySettlementStatus = 'OPEN' | 'SUBMITTED' | 'CONFIRMED' | 'DISPUTED' | 'STALE' | 'LOCKED'
export interface MonthlySettlement {
  factory_id: string; supplier_id: string; supplier_name: string; period: string; currency: string;
  source_fingerprint: string; status: MonthlySettlementStatus; locked_at: string | null; locked_by: string | null;
  locked_totals: Record<string, string | number> | null; stale: boolean;
  submitted_at: string | null; submitted_by: string | null;
  supplier_confirmed_at: string | null; supplier_confirmed_by: string | null;
  disputed_reason: string; unlocked_reason: string;
  can_submit: boolean; can_lock: boolean;
  totals: { inbound: string | null; returns: string | null; refunds: string | null; net: string | null;
    documents: number; receipt_lines: number; return_lines: number; refund_lines: number };
  blockers: string[]; lines: MonthlySettlementLine[];
}
export interface SupplierMonthlySummary {
  factory_id: string; supplier_name: string; period: string; currency: string;
  status: MonthlySettlementStatus; stale: boolean; locked_at: string | null;
  submitted_at: string | null; supplier_confirmed_at: string | null; disputed_reason: string;
  can_confirm: boolean; can_dispute: boolean;
  totals: MonthlySettlement['totals']; lines: MonthlySettlementLine[];
}
export const supplierSettlementApi = {
  async supplierMonthlyWorkspace(factory_id: string, period: string, currency: string) { return (await http.get<SupplierMonthlySummary>('/carton-supplier/monthly-settlements/workspace', { params: { factory_id, period, currency } })).data },
  async monthlyWorkspace(factory_id: string, period: string, currency: string) { return (await http.get<MonthlySettlement>('/carton-procurement/monthly-settlements/workspace', { params: { factory_id, period, currency } })).data },
  async acceptance(receipt_id: string, factory_id: string, expected_revision: number, acceptance_date: string, reason: string) { return (await http.post(`/carton-procurement/receipts/${receipt_id}/acceptance-date`, { factory_id, expected_revision, acceptance_date, reason })).data },
  async returnDate(movement_id: string, factory_id: string, expected_posting_date: string, return_date: string, reason: string) { return (await http.post(`/carton-procurement/inventory/movements/${encodeURIComponent(movement_id)}/return-date`, { factory_id, expected_posting_date, expected_date_basis: 'RETURN_POSTING', return_date, reason })).data },
  async correctReturnDate(movement_id: string, body: ReturnDateCorrection, signal?: AbortSignal) { return (await http.post<ReturnDateCorrectionResult>(`/carton-procurement/inventory/movements/${encodeURIComponent(movement_id)}/return-date/corrections`, body, { signal })).data },
}
