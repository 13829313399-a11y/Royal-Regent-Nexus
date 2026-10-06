import { http } from '@/lib/http'

export type FeedbackState = 'OPEN' | 'FIXED' | 'DECLINED'
export type UpdateAudience = 'INTERNAL' | 'SUPPLIER'
export interface Feedback {
  id: string; factory_id: string; author_id: string; author_name: string; title: string; description: string
  context_path: string; status: FeedbackState; revision: number; created_at: string; updated_at: string
}
export interface FeedbackDetail extends Feedback {
  images: string[]; replies: { id: string; author_name: string; body: string; status: FeedbackState; created_at: string }[]
}
export interface FeedbackWorkspace {
  can_manage: boolean; feedbacks: Feedback[]
  updates: { id: string; title: string; body: string; audience?: UpdateAudience; author_name: string; created_at: string }[]
  total?: number; updates_total?: number; limit?: number; offset?: number; updates_offset?: number
}
const base = '/carton-feedback'
export const cartonFeedbackApi = {
  async workspace(factory: string, all: boolean, signal?: AbortSignal, filters: Record<string, string | number> = {}) {
    return (await http.get<FeedbackWorkspace>(base, { params: { factory_id: factory, all_feedback: all, ...filters }, signal })).data
  },
  async detail(factory: string, id: string, signal?: AbortSignal, portal?: 'supplier') {
    return (await http.get<FeedbackDetail>(`${base}/${encodeURIComponent(id)}`, { params: { factory_id: factory, ...(portal ? { portal } : {}) }, signal })).data
  },
  async create(factory: string, title: string, description: string, path: string, key: string, files: File[], signal?: AbortSignal, portal?: 'supplier') {
    const form = new FormData()
    form.set('factory_id', factory); form.set('title', title); form.set('description', description)
    form.set('context_path', path); form.set('request_key', key)
    if (portal) form.set('portal', portal)
    files.forEach(file => form.append('files', file))
    return (await http.post<FeedbackDetail>(base, form, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000, signal })).data
  },
  async reply(factory: string, row: FeedbackDetail, body: string, status: FeedbackState, signal?: AbortSignal) {
    return (await http.post<FeedbackDetail>(`${base}/${encodeURIComponent(row.id)}/reply`, { revision: row.revision, body, status }, { params: { factory_id: factory }, signal })).data
  },
  async publish(factory: string, title: string, body: string, key: string, signal?: AbortSignal, audience: UpdateAudience = 'INTERNAL') {
    return (await http.post(base + '/updates/publish', { title, body, request_key: key, audience }, { params: { factory_id: factory }, signal })).data
  },
  async image(factory: string, feedback: string, image: string, signal?: AbortSignal, portal?: 'supplier') {
    return (await http.get<Blob>(`${base}/${encodeURIComponent(feedback)}/images/${encodeURIComponent(image)}`, { params: { factory_id: factory, ...(portal ? { portal } : {}) }, responseType: 'blob', signal })).data
  },
}
