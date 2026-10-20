import { http } from '@/lib/http'

export type JPReferenceKind = 'schedule' | 'price' | 'confirmed'
export interface JPReference { id: string; name: string; revision: number; sha256: string; actor: string; updated_at: string; options?: { currency?: string } }
export interface JPCapabilities { read: boolean; write: boolean; export: boolean; available: boolean; creator_name?: string }
export interface JPRow {
  id: string; source: string; baby_item: string; long_code: string; qty: string; customer: string; customer_po: string;
  country: string; pkg: string; ship_date: string; cutoff_date: string; price_t: string; factory_price_t: string;
  carton_t: string; note: string; exists?: boolean; price_confirm?: boolean; price_note?: string;
}
export interface JPPreview {
  factory_id: string; fingerprint: string; rows: JPRow[]; warnings: string[]; failed_sources: string[];
  quantity_selections: Array<{ source_id: string; source: string; table_index: number; columns: Array<{ index: number; sample: string }> }>;
}
export interface JPExportRecord { id: string; actor: string; created_at: string; prefix: string; first_number: number; last_number: number; row_count: number }
const base = '/huakang-b-jp'
const scope = (factory: string) => `factory_id=${encodeURIComponent(factory)}`
const fileConfig = { timeout: 270_000, headers: { 'X-JP-Intake': '1' } }

export const huakangBJPApi = {
  async clearConfirmed(data: FormData, signal?: AbortSignal) { return (await http.post<Partial<Record<JPReferenceKind, JPReference>>>(`${base}/references/confirmed/clear`, data, { ...fileConfig, ...(signal ? { signal } : {}) })).data },
  async capabilities(factory: string, signal?: AbortSignal) { return (await http.get<JPCapabilities>(`${base}/capabilities?${scope(factory)}`, signal ? { signal } : undefined)).data },
  async references(factory: string, signal?: AbortSignal) { return (await http.get<Partial<Record<JPReferenceKind, JPReference>>>(`${base}/references?${scope(factory)}`, signal ? { signal } : undefined)).data },
  async upload(kind: JPReferenceKind, data: FormData, signal?: AbortSignal) { return (await http.post<Partial<Record<JPReferenceKind, JPReference>>>(`${base}/references/${kind}`, data, { ...fileConfig, ...(signal ? { signal } : {}) })).data },
  async preview(data: FormData, signal?: AbortSignal) { return (await http.post<JPPreview>(`${base}/preview`, data, { ...fileConfig, ...(signal ? { signal } : {}) })).data },
  async export(data: FormData, signal?: AbortSignal) { return (await http.post<{ id: string; row_count: number }>(`${base}/export`, data, { ...fileConfig, ...(signal ? { signal } : {}) })).data },
  async exports(factory: string, page = 1, signal?: AbortSignal) { return (await http.get<{ items: JPExportRecord[]; total: number }>(`${base}/exports?${scope(factory)}&page=${page}`, signal ? { signal } : undefined)).data },
  async download(factory: string, id: string, signal?: AbortSignal) { return (await http.get<Blob>(`${base}/exports/${encodeURIComponent(id)}/download?${scope(factory)}`, { responseType: 'blob', ...(signal ? { signal } : {}) })).data },
}
