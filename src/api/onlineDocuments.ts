import { http } from '@/lib/http'

export interface DocumentGrant { user_id: string; name?: string; access: 'view' | 'edit'; epoch: number }
export interface OnlineDocument {
  id: string; title: string; format: 'docx' | 'xlsx'; owner_name: string; revision: number
  byte_size: number; updated_at: string; created_at: string; access: 'owner' | 'edit' | 'view'
  editing: boolean; grants?: DocumentGrant[]; pending_save: string; saved_request: string; save_error: string
  share_version?: string
  state_version: number; deleted_at: string; protected: boolean
  operation_notice?: string
  title_sync_pending?: boolean
  folder_id?: string | null; placement_version?: number
}
export interface DocumentFolder { id: string; name: string; version: number }
export interface CopyDocument { request_id: string; expected_revision: number; title: string; folder_id: string | null }
export type DocumentSort = 'updated' | 'name' | 'name_desc' | 'recent'
export interface MoveDocuments { request_id: string; folder_id: string | null; documents: { id: string; expected_version: number }[] }
export interface DocumentRevision { revision: number; created_at: string; byte_size: number; actor_id: string; current: boolean }
export interface DocumentEvent { id: string; kind: string; actor_name: string; revision: number; created_at: string; details: Record<string, unknown> }
export interface ProtectionRule { sheet: string; ranges: string[] }
export interface DocumentCommand { request_id: string; expected_version: number; revision?: number; enabled?: boolean; rules?: ProtectionRule[] }
export interface EditorResponse { config: Record<string, unknown>; script_url: string; document: OnlineDocument }
const root = '/tools/online-documents'
const params = (factory: string) => ({ factory_id: factory })
export const onlineDocuments = {
  list: async (factory: string, folder?: string, order?: { sort: DocumentSort; recent_ids?: string }) => (await http.get<{ items: OnlineDocument[] }>(root, { params: { ...params(factory), ...(folder ? { folder_id: folder } : {}), ...order } })).data.items,
  folders: async (factory: string) => (await http.get<{ items: DocumentFolder[] }>(`${root}/folders`, { params: params(factory) })).data.items,
  createFolder: async (factory: string, payload: { id: string; name: string }) => (await http.post<DocumentFolder>(`${root}/folders`, payload, { params: params(factory) })).data,
  removeFolder: async (factory: string, id: string) => (await http.delete(`${root}/folders/${id}`, { params: params(factory) })).data,
  renameFolder: async (factory: string, id: string, name: string, expectedName: string, expectedVersion: number) => (await http.patch<DocumentFolder>(`${root}/folders/${id}`, { name, expected_name: expectedName, expected_version: expectedVersion }, { params: params(factory) })).data,
  copy: async (factory: string, id: string, payload: CopyDocument) => (await http.post<OnlineDocument>(`${root}/${id}/copy`, payload, { params: params(factory), timeout: 300_000 })).data,
  move: async (factory: string, payload: MoveDocuments) => (await http.post(`${root}/move`, payload, { params: params(factory) })).data,
  trash: async (factory: string) => (await http.get<{ items: OnlineDocument[] }>(root, { params: { ...params(factory), deleted: true } })).data.items,
  history: async (factory: string, id: string, before = 0) => (await http.get<{ items: DocumentRevision[]; next_before: number | null }>(`${root}/${id}/history`, { params: { ...params(factory), before } })).data,
  events: async (factory: string, id: string, before = '') => (await http.get<{ items: DocumentEvent[]; next_before: string | null }>(`${root}/${id}/events`, { params: { ...params(factory), before } })).data,
  protection: async (factory: string, id: string) => (await http.get<{ document: OnlineDocument; sheets: { name: string; formula_count: number; used_cells: number }[]; rules: ProtectionRule[] }>(`${root}/${id}/protection`, { params: params(factory) })).data,
  command: async (factory: string, id: string, kind: 'restore' | 'trash' | 'recover' | 'protection', payload: DocumentCommand) => (await http.request<OnlineDocument>({ url: `${root}/${id}/${kind}`, method: kind === 'protection' ? 'PUT' : 'POST', data: payload, params: params(factory), timeout: 300_000 })).data,
  downloadRevision: async (factory: string, id: string, revision: number) => (await http.get<Blob>(`${root}/${id}/history/${revision}/download`, { params: params(factory), responseType: 'blob', timeout: 300_000 })).data,
  detail: async (factory: string, id: string) => (await http.get<OnlineDocument>(`${root}/${id}`, { params: params(factory) })).data,
  rename: async (factory: string, id: string, title: string, expectedTitle: string, expectedVersion: number) => (await http.patch<OnlineDocument>(`${root}/${id}/title`, { title, expected_title: expectedTitle, expected_version: expectedVersion }, { params: params(factory) })).data,
  create: async (factory: string, title: string, format: 'docx' | 'xlsx', folder?: string) => (await http.post<OnlineDocument>(root, { title, format, ...(folder ? { folder_id: folder } : {}) }, { params: params(factory) })).data,
  upload: async (factory: string, file: File, folder?: string) => {
    const data = new FormData(); data.append('factory_id', factory); data.append('file', file)
    if (folder) data.append('folder_id', folder)
    return (await http.post<OnlineDocument>(`${root}/upload`, data, { headers: { 'Content-Type': undefined }, timeout: 300_000 })).data
  },
  editor: async (factory: string, id: string) => (await http.post<EditorResponse>(`${root}/${id}/editor`, {}, { params: params(factory) })).data,
  save: async (factory: string, id: string) => (await http.post<{ request_id: string; revision: number }>(`${root}/${id}/save`, {}, { params: params(factory), timeout: 30_000 })).data,
  releaseUnopened: async (factory: string, id: string) => (await http.post(`${root}/${id}/release-unopened`, {}, { params: params(factory) })).data,
  recipients: async (factory: string) => (await http.get<{ users: { id: string; display_name: string; department: string; organization?: string; epoch: number }[] }>(`${root}/recipients`, { params: params(factory) })).data.users,
  share: async (factory: string, id: string, grants: DocumentGrant[], version: string) => (await http.put<OnlineDocument>(`${root}/${id}/grants`, { grants, version }, { params: params(factory) })).data,
  download: async (factory: string, id: string) => (await http.get<Blob>(`${root}/${id}/download`, { params: params(factory), responseType: 'blob', timeout: 300_000 })).data,
}
