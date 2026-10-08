import { http } from '@/lib/http'
import type { MaterialCategory } from './fabricReceiving'

export type MasterKind = 'MATERIAL' | 'SUPPLIER' | 'LOCATION' | 'UNIT'
export type MasterStatus = 'DRAFT' | 'ACTIVE' | 'INACTIVE'
export interface MasterFields {
  category?: MaterialCategory | ''; unit?: string; old_code?: string; spec?: string; color?: string; composition?: string
  contact?: string; phone?: string; warehouse?: string; material_code?: string; price_unit?: string; ratio?: string
  evidence?: string; conditions?: string; effective_date?: string | null; note?: string
}
export interface MasterRecord { id: string; kind: MasterKind; code: string; name: string; status: MasterStatus; revision: number; data: MasterFields; updated_at: string }
export interface MasterCandidate extends Omit<MasterRecord, 'id' | 'updated_at'> { key: string; variants: { name: string; unit: string }[]; conflict: boolean; source_line_ids: string[]; source_count: number }
export interface SaveMasterRequest { factory_id: 'huakang-c'; request_id: string; id: string | null; expected_revision: number; kind: MasterKind; code: string; name: string; status: MasterStatus; data: MasterFields }
export interface LocationInput { warehouse: string; bins: string }
export interface LocationPreview { items: { warehouse: string; code: string; action: 'NEW' | 'UNCHANGED'; status: MasterStatus }[]; errors: string[]; new: number; unchanged: number; preview_token: string; stock_posted: false; rows?: LocationInput[] }
export interface LocationApply { factory_id: 'huakang-c'; request_id: string; rows: LocationInput[]; preview_token: string }
export interface WarehouseRename { factory_id: 'huakang-c'; request_id: string; warehouse: string; name: string; expected_group_token: string }
export const fabricMasterApi = {
  async list(kind: MasterKind, search = '', status = 'ALL', sort = 'CODE') { return (await http.get<{ items: MasterRecord[]; total: number; can_manage: boolean; warehouse_tokens: Record<string, string> }>('/fabric-warehouse/master', { params: { factory_id: 'huakang-c', kind, search, status, sort } })).data },
  async candidates(kind: MasterKind) { return (await http.get<{ items: MasterCandidate[] }>('/fabric-warehouse/master/candidates', { params: { factory_id: 'huakang-c', kind } })).data.items },
  async save(payload: SaveMasterRequest) { return (await http.post<MasterRecord>('/fabric-warehouse/master', payload)).data },
  async history(id: string) { return (await http.get<{ items: { before: Partial<MasterRecord>; after: MasterRecord; actor_name: string; occurred_at: string }[] }>(`/fabric-warehouse/master/${encodeURIComponent(id)}/history`, { params: { factory_id: 'huakang-c' } })).data.items },
  async locationTemplate() { return (await http.get<Blob>('/fabric-warehouse/master/locations/template', { params: { factory_id: 'huakang-c' }, responseType: 'blob' })).data },
  async previewLocations(rows: LocationInput[]) { return (await http.post<LocationPreview>('/fabric-warehouse/master/locations/preview', { factory_id: 'huakang-c', rows })).data },
  async previewLocationFile(file: File) { const body = new FormData(); body.append('factory_id', 'huakang-c'); body.append('file', file); return (await http.post<LocationPreview>('/fabric-warehouse/master/locations/file-preview', body)).data },
  async applyLocations(body: LocationApply) { return (await http.post<{ new: number; unchanged: number; stock_posted: false }>('/fabric-warehouse/master/locations/apply', body)).data },
  async renameWarehouse(body: WarehouseRename) { return (await http.post<{ warehouse: string; updated: number; stock_posted: false }>('/fabric-warehouse/master/locations/rename-warehouse', body)).data },
}
