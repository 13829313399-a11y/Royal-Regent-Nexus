import axios from 'axios'
import { http } from '@/lib/http'

export type SpreadsheetCell = string | number | boolean | null
export type MergeResolution = 'primary' | 'secondary'
export interface SpreadsheetInspection {
  filename: string
  sheets: { name: string; rows: SpreadsheetCell[][] }[]
  warnings: string[]
}
export interface MergeTable {
  name: string
  headers: string[]
  rows: SpreadsheetCell[][]
  header_row: number
}
export type MergeTemplateId = 'carton-packaging' | 'carton-paper-options' | 'carton-locations' | 'carton-history-orders' | 'carton-opening-inventory' | 'carton-weekly-schedule'
export interface MergeTemplate {
  id: MergeTemplateId
  label: string
  description: string
  headers: string[]
  profile: 'generic' | 'carton-packaging'
  sheet_name: string
  header_row: number
}
export interface SpreadsheetMergeRequest {
  primary: MergeTable
  secondary: MergeTable
  audit_tables?: MergeTable[]
  template_id?: MergeTemplateId
  factory_id?: string
  mapping: { source: number; target: number }[]
  key_columns: number[]
  remarks_column: number | null
  extra_columns_to_remarks: number[]
  resolutions: Record<string, MergeResolution>
  profile: 'generic' | 'carton-packaging'
  batch_size: number | null
}
export interface MergeSourceRef { table: 'primary' | 'secondary'; name: string; row: number }
export interface SpreadsheetMergePreview {
  headers: string[]
  rows: SpreadsheetCell[][]
  provenance: MergeSourceRef[][]
  conflicts: { id: string; row: number; column: number; primary: SpreadsheetCell; secondary: SpreadsheetCell; resolution: MergeResolution | null }[]
  issues: { code: string; message: string; rows: number[] }[]
  warnings: string[]
  ready_for_import: boolean
  stats: { primary_rows: number; secondary_rows: number; output_rows: number; filled_cells: number; added_rows: number }
  validation_errors: string[]
}
const base = '/tools/spreadsheet-merge'
const timeout = 180_000

function filename(headers: Record<string, unknown>, fallback: string) {
  const disposition = String(headers['content-disposition'] ?? '')
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  if (encoded) { try { return decodeURIComponent(encoded) } catch { /* use fallback */ } }
  return disposition.match(/filename="([^"]+)"/)?.[1] ?? fallback
}
async function download(path: string, request?: SpreadsheetMergeRequest, signal?: AbortSignal, factoryId?: string) {
  try {
    const response = request
      ? await http.post<Blob>(path, request, { responseType: 'blob', timeout, signal })
      : await http.get<Blob>(path, { responseType: 'blob', timeout, signal, params: { factory_id: factoryId } })
    return { blob: response.data, filename: filename(response.headers, request?.batch_size ? '表格合并.zip' : '表格合并.xlsx') }
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.data instanceof Blob) {
      const raw = await error.response.data.text()
      try {
        const data = JSON.parse(raw) as { detail?: string | { message?: string }; message?: string }
        const message = typeof data.detail === 'string' ? data.detail : data.detail?.message ?? data.message
        if (message) throw new Error(message)
      } catch (parsed) { if (parsed instanceof Error && !(parsed instanceof SyntaxError)) throw parsed }
    }
    throw error
  }
}
export const spreadsheetMergeApi = {
  async inspect(file: File, preset = '', signal?: AbortSignal): Promise<SpreadsheetInspection> {
    const body = new FormData()
    body.append('file', file)
    if (preset) body.append('preset', preset)
    return (await http.post<SpreadsheetInspection>(`${base}/inspect`, body, { headers: { 'Content-Type': undefined }, timeout, signal })).data
  },
  async templates(factoryId: string, signal?: AbortSignal): Promise<MergeTemplate[]> {
    return (await http.get<MergeTemplate[]>(`${base}/templates`, { signal, params: { factory_id: factoryId } })).data
  },
  async preview(request: SpreadsheetMergeRequest, signal?: AbortSignal): Promise<SpreadsheetMergePreview> {
    return (await http.post<SpreadsheetMergePreview>(`${base}/preview`, request, { timeout, signal })).data
  },
  export: (request: SpreadsheetMergeRequest, signal?: AbortSignal) => download(`${base}/export`, request, signal),
  template: (id: MergeTemplateId, factoryId: string, signal?: AbortSignal) => download(`${base}/templates/${encodeURIComponent(id)}`, undefined, signal, factoryId),
}
