import { http } from '@/lib/http'

export interface SupplierSource {
  source_key: string; kind: 'RECEIPT' | 'RETURN'; document_no: string; acceptance_date: string | null;
  date_basis: string; customer_name: string; contract_no: string; item_no: string; packaging_type: string;
  paper_quality: string; specification: string; unit: string; quantity: string; unit_price: string | null;
  amount: string | null; currency: string; issues: string[];
  supplier_delivery?: { shipment_id: string; line_id: string; document_no: string; delivery_date: string;
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
  result: { issues: string[]; line_results: { id: string; source_key: string; quantity_difference: string | null; price_difference: string | null; amount_difference: string | null; issues: string[] }[]; inbound_amount: string | null; return_amount: string | null; net_amount: string | null; statement_amount: string | null; supplier_review?: SupplierReview; unsettled_shipments?: UnsettledShipment[] };
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
const base = '/carton-procurement/supplier-settlements'
export const supplierSettlementApi = {
  async workspace(factory_id: string, period: string, currency: string) { return (await http.get<SupplierWorkspace>(base + '/workspace', { params: { factory_id, period, currency } })).data },
  async save(payload: SettlementSave) { return (await http.post<SettlementDocument>(base, payload)).data },
  async confirm(id: string, factory_id: string, expected_revision: number) { return (await http.post<SettlementDocument>(`${base}/${id}/confirm`, { factory_id, expected_revision })).data },
  async reopen(id: string, factory_id: string, expected_revision: number, reason: string) { return (await http.post<SettlementDocument>(`${base}/${id}/reopen`, { factory_id, expected_revision, reason })).data },
  async acceptance(receipt_id: string, factory_id: string, expected_revision: number, acceptance_date: string, reason: string) { return (await http.post(`/carton-procurement/receipts/${receipt_id}/acceptance-date`, { factory_id, expected_revision, acceptance_date, reason })).data },
  async supplierWorkspace(factory_id: string, period: string, currency: string) { return (await http.get<SupplierSettlementWorkspace>('/carton-supplier/settlements/workspace', { params: { factory_id, period, currency } })).data },
  async supplierReview(id: string, factory_id: string, expected_revision: number, decision: 'CONFIRMED' | 'DISPUTED', reason: string) { return (await http.post<SettlementDocument>(`/carton-supplier/settlements/${id}/review`, { factory_id, expected_revision, decision, reason })).data },
}
