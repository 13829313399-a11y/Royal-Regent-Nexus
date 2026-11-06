import { http } from '@/lib/http'
export interface Material { actor_id?: string; occurred_at?: string; reason?: string; id: string; code: string; name: string; version: number; status: string; data: { unit: string; spec?: string; color?: string; old_code?: string; category?: string; engineering?: { group: string; department: string; attribute: string; approval: string } } }
export interface Node { key: string; parent: string; material_id: string; material_version: number; source_code: string; source_name: string; unit: string; numerator: string; denominator: string; process: string; exempt_loss: boolean; note: string; source: Record<string, string>; review_required: boolean; review_note: string }
export interface BomData { item_no: string; name: string; specification: string; source_reference: string; source_sha256?: string; nodes: Node[] }
export interface Bom { id: string; version: number; effective_version: number | null; status: string; data: BomData; materials: Record<string, Material>; actor_id?: string; occurred_at?: string; reason?: string }
export interface Access { enabled: boolean; schema_ready: boolean; permissions: string[] }
export type BomEvidence = Record<string, string | number | boolean | string[]>
export interface MaterialBomUsage {
  material_id: string; material_version: number; code: string; name: string; checked_at: string; bom_count: number
  items: Array<{ bom_id: string; bom_version: number; item_no: string; bom_name: string; status: string
    roles: Array<'LATEST' | 'EFFECTIVE'>; row: number; key: string; material_version: number; code: string; name: string
    attribute: string; process: string; unit: string; numerator: string; denominator: string }>
}
export interface BomApprovalCheck {
  id: string; version: number; status: string; effective_version: number | null; checked_at: string
  checked_rows: number; ready_for_approval: boolean; can_release: false
  issues: Array<{ row: number | null; key: string; code: string; name: string; attribute: string; message: string }>
}
export interface BomComparison {
  id: string; from_version: number; to_version: number; from_status: string; to_status: string; unchanged_count: number
  header: Array<{ field: string; label: string; before: string; after: string }>
  rows: Array<{ key: string; kind: 'ADDED' | 'REMOVED' | 'CHANGED'; before: BomEvidence | null; after: BomEvidence | null; changes: Array<{ field: string; label: string }> }>
}
export interface ImportPreview { filename: string; sha256: string; row_count: number; material_count: number; can_save: boolean; data: BomData; issues: Array<{ row: number; message: string; blocking: boolean }> }
const base = '/engineering-bom'
const params = { factory_id: 'huakang-c' }
export const engineeringApi = {
  async access(): Promise<Access> { return (await http.get(`${base}/access`, { params })).data },
  async workspace(): Promise<{ materials: Material[]; boms: Bom[] }> { return (await http.get(`${base}/workspace`, { params })).data },
  async history(id: string): Promise<{ items: Array<Bom | Material> }> { return (await http.get(`${base}/history/${encodeURIComponent(id)}`, { params })).data },
  async compare(id: string, from: number, to: number): Promise<BomComparison> { return (await http.get(`${base}/boms/${encodeURIComponent(id)}/comparison`, { params: { ...params, from_version: from, to_version: to } })).data },
  async approvalCheck(id: string, version: number): Promise<BomApprovalCheck> { return (await http.get(`${base}/boms/${encodeURIComponent(id)}/approval-check`, { params: { ...params, expected_version: version } })).data },
  async materialUsage(id: string, version: number): Promise<MaterialBomUsage> { return (await http.get(`${base}/materials/${encodeURIComponent(id)}/bom-usage`, { params: { ...params, expected_version: version } })).data },
  async post(path: string, body: unknown): Promise<Material | Bom> { return (await http.post(base + path, body)).data },
  async preview(body: unknown): Promise<{ items: Array<{ key: string; process: string; quantity: string; unit: string }> }> { return (await http.post(`${base}/preview`, body)).data },
  async importPreview(file: File): Promise<ImportPreview> { const form = new FormData(); form.append('factory_id', 'huakang-c'); form.append('file', file); return (await http.post(`${base}/import-preview`, form)).data },
}
export function newNode(): Node { return { key: crypto.randomUUID(), parent: '', material_id: '', material_version: 0, source_code: '', source_name: '', unit: '', numerator: '1', denominator: '1', process: '', exempt_loss: false, note: '', source: {}, review_required: false, review_note: '' } }
export function emptyBom(): BomData { return { item_no: '', name: '', specification: '', source_reference: '', nodes: [newNode()] } }
