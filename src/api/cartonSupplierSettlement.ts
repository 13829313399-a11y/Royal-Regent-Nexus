import { http } from '@/lib/http'

export interface SupplierSource {
  source_key: string; kind: 'RECEIPT' | 'RETURN'; document_no: string; acceptance_date: string | null;
  date_basis: string; customer_name: string; contract_no: string; item_no: string; packaging_type: string;
  paper_quality: string; specification: string; unit: string; quantity: string; unit_price: string | null;
  amount: string | null; currency: string; issues: string[];
}
export interface StatementLine {
  id: string; source_key: string; document_no: string; quantity: string | null; unit_price: string | null;
  amount: string | null; approved_return_unit_price: string | null; credit_document_no: string;
  credit_date: string | null; note: string;
}
export interface SettlementDocument {
  id: string; factory_id: string; supplier_id: string; period: string; currency: string; version: number;
  revision: number; status: 'DRAFT' | 'CONFIRMED' | 'SUPERSEDED'; source_fingerprint: string; sources: SupplierSource[];
  statement: { statement_no: string; tax_basis: 'INCLUSIVE' | 'EXCLUSIVE'; same_price_basis: boolean; lines: StatementLine[] };
  result: { issues: string[]; line_results: { id: string; source_key: string; quantity_difference: string | null; price_difference: string | null; amount_difference: string | null; issues: string[] }[]; inbound_amount: string | null; return_amount: string | null; net_amount: string | null; statement_amount: string | null };
  created_at: string; updated_at: string; confirmed_at: string; confirmed_by: string; reopen_reason: string; stale: boolean;
}
export interface SupplierWorkspace {
  factory_id: string; supplier_id: string; supplier_name: string; period: string; currency: string;
  source_fingerprint: string; sources: SupplierSource[]; issues: string[]; documents: SettlementDocument[];
  undated_receipts: { receipt_id: string; revision: number; document_no: string; confirmed_at: string; acceptance_date: null }[];
}
export interface SettlementSave {
  factory_id: string; supplier_id: string; period: string; currency: string; source_fingerprint: string;
  id?: string; expected_revision?: number; statement_no: string; tax_basis: 'INCLUSIVE' | 'EXCLUSIVE'; same_price_basis: boolean; lines: StatementLine[];
}
const base = '/carton-procurement/supplier-settlements'
export const supplierSettlementApi = {
  async workspace(factory_id: string, period: string, currency: string) { return (await http.get<SupplierWorkspace>(base + '/workspace', { params: { factory_id, period, currency } })).data },
  async save(payload: SettlementSave) { return (await http.post<SettlementDocument>(base, payload)).data },
  async confirm(id: string, factory_id: string, expected_revision: number) { return (await http.post<SettlementDocument>(`${base}/${id}/confirm`, { factory_id, expected_revision })).data },
  async reopen(id: string, factory_id: string, expected_revision: number, reason: string) { return (await http.post<SettlementDocument>(`${base}/${id}/reopen`, { factory_id, expected_revision, reason })).data },
  async acceptance(receipt_id: string, factory_id: string, expected_revision: number, acceptance_date: string, reason: string) { return (await http.post(`/carton-procurement/receipts/${receipt_id}/acceptance-date`, { factory_id, expected_revision, acceptance_date, reason })).data },
}
