import { http } from '@/lib/http'
import type { BatchResult } from './cartonBatchOrders'

export type ImportMode = 'REGULAR' | 'SPECIAL'
export interface ImportOptions { factory_id: string; mode: ImportMode; sheet?: string; header_row?: number; mapping?: Record<string, number> }
export interface ImportRow { source_row: number; data: Record<string, string> }
export interface ImportField { key: string; label: string; requirement?: 'required' | 'optional' | 'conditional'; hint?: string }
export interface ImportFile {
  fingerprint: string; sheets: string[]; sheet: string; header_row: number; mapping: Record<string, number>; rows: ImportRow[]
  fields: ImportField[]; columns: { index: number; label: string; sample: string }[]; ignored_demo_rows?: number[]
}
export interface ImportPreviewBody extends ImportOptions { fingerprint: string; rows: ImportRow[] }
export interface ImportGroup { id: string; source_rows: number[]; label: string; errors: string[]; warnings: string[]; quantities: string[]; due_date: string; status: 'READY' | 'INVALID' | 'IMPORTED' }
export interface ImportPreview { groups: ImportGroup[]; preview_fingerprint: string }
export interface ImportConfirm extends ImportPreviewBody { request_id: string; selected_groups: string[]; preview_fingerprint: string }
async function upload<T>(action: string, body: unknown, file: File, signal?: AbortSignal) {
  const data = new FormData(); data.append('body', JSON.stringify(body)); data.append('file', file)
  return (await http.post<T>(`/carton-unified-orders/order-import/${action}`, data, { signal, timeout: 300000, headers: { 'Content-Type': 'multipart/form-data' } })).data
}
export const cartonOrderImportApi = {
  read: (body: ImportOptions, file: File, signal?: AbortSignal) => upload<ImportFile>('read', body, file, signal),
  preview: (body: ImportPreviewBody, file: File, signal?: AbortSignal) => upload<ImportPreview>('preview', body, file, signal),
  confirm: (body: ImportConfirm, file: File, signal?: AbortSignal) => upload<BatchResult>('confirm', body, file, signal),
  async template(factory: string, mode: ImportMode) { return (await http.get<Blob>('/carton-unified-orders/order-import/template', { params: { factory_id: factory, mode }, responseType: 'blob' })).data },
}
