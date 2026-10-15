import { http } from '@/lib/http'
export interface CorrectedMaterial { packaging_type: string; paper_quality: string; specification: string; dimension_unit: string }
export interface MaterialCorrection {
  id: string; factory_id: string; order_id: string; order_no: string; contract_no: string; item_no: string; order_line_id: string
  issue_id: string; document_no: string; before: CorrectedMaterial; after: CorrectedMaterial; reason: string
  status: 'PENDING' | 'RETURNED' | 'APPROVED' | 'WITHDRAWN'; revision: number
  created_by_name: string; created_at: string; resolved_by_name: string; resolved_at: string; response_note: string; corrected_document_no: string
}
export interface CorrectionContext { order_no: string; factory_id: string; revision: number; issue_id: string; status: string; lines: (CorrectedMaterial & { id: string })[]; records: MaterialCorrection[] }
export interface CorrectionCreate { factory_id: string; request_id: string; expected_revision: number; issue_id: string; order_line_id: string; after: CorrectedMaterial; reason?: string }
export interface CorrectionAction { factory_id: string; request_id: string; expected_revision: number; action: 'APPROVE' | 'RETURN' | 'WITHDRAW'; note?: string; verified: boolean }
export const materialCorrectionApi = {
  async context(factory: string, number: string, signal?: AbortSignal) { return (await http.get<CorrectionContext>(`/carton-procurement/orders/${encodeURIComponent(number)}/material-corrections`, { params: { factory_id: factory }, signal })).data },
  async supplierList(factory: string, signal?: AbortSignal) { return (await http.get<MaterialCorrection[]>('/carton-supplier/material-corrections', { params: { factory_id: factory }, signal })).data },
  async create(number: string, body: CorrectionCreate, signal?: AbortSignal) { return (await http.post<MaterialCorrection>(`/carton-procurement/orders/${encodeURIComponent(number)}/material-corrections`, body, { signal })).data },
  async act(id: string, body: CorrectionAction, supplier: boolean, signal?: AbortSignal) { return (await http.post<MaterialCorrection>(`/${supplier ? 'carton-supplier' : 'carton-procurement'}/material-corrections/${encodeURIComponent(id)}/actions`, body, { signal })).data },
}
