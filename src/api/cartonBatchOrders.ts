import { http } from '@/lib/http'
import type { SpecialLine, UnifiedOrderRef } from './cartonSpecialRequests'

export interface AppendItem extends UnifiedOrderRef {
  reason: string; due_date?: string; lines: { id: string; additional_quantity: string }[]; new_lines: SpecialLine[]
}
export interface AppendBody { factory_id: string; request_id: string; items: AppendItem[] }
export interface BatchResult { batch_id: string; count: number }
export interface DemandRow {
  source_row: number; group: string; kind: string; item_no: string; packaging_type: string; paper_quality: string
  specification: string; dimension_unit: string; quantity: string; unit: string; required_date: string; note: string
}
export interface DemandPreview { fingerprint: string; rows: DemandRow[] }
export interface DemandBody { factory_id: string; request_id: string; fingerprint: string; rows: DemandRow[] }
export const cartonBatchOrdersApi = {
  async append(body: AppendBody, signal?: AbortSignal) { return (await http.post<BatchResult>('/carton-unified-orders/batch-append', body, { signal })).data },
  async template(factory: string) { return (await http.get<Blob>('/carton-unified-orders/demand-import/template', { params: { factory_id: factory }, responseType: 'blob' })).data },
  async preview(factory: string, file: File, signal?: AbortSignal) {
    const data = new FormData(); data.append('factory_id', factory); data.append('file', file)
    return (await http.post<DemandPreview>('/carton-unified-orders/demand-import/preview', data, { signal, timeout: 300000 })).data
  },
  async importDemands(body: DemandBody, file: File, signal?: AbortSignal) {
    const data = new FormData(); data.append('body', JSON.stringify(body)); data.append('file', file)
    return (await http.post<BatchResult>('/carton-unified-orders/demand-import/confirm', data, { signal, timeout: 300000 })).data
  },
}
