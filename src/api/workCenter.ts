import { http } from '@/lib/http'
import type { PersonalPatch, WorkEntry, WorkPreferences, WorkQuery, WorkSnapshot } from '@/features/work-center/types'
export const workCenterApi = {
  async snapshot(query: Partial<WorkQuery> = {}, signal?: AbortSignal) { return (await http.get<WorkSnapshot>('/work-center/snapshot', { params: query, signal })).data },
  async entry(id: string, signal?: AbortSignal) { return (await http.get<WorkEntry>(`/work-center/entries/${encodeURIComponent(id)}`, { signal })).data },
  async events(id: string, cursor?: string) { return (await http.get<{ items: { id: string; occurred_at: string; summary: string }[]; next_cursor: string | null }>(`/work-center/entries/${encodeURIComponent(id)}/events`, { params: { cursor } })).data },
  async patch(id: string, payload: PersonalPatch) { return (await http.patch<WorkEntry>(`/work-center/entries/${encodeURIComponent(id)}/user-state`, payload)).data },
  async batch(items: (PersonalPatch & { id: string })[]) { return (await http.post<{ results: { id: string; status: string; message?: string }[] }>('/work-center/user-state/batch', { items })).data },
  async preferences() { return (await http.get<WorkPreferences>('/work-center/preferences')).data },
  async savePreferences(payload: Partial<WorkPreferences>) { return (await http.patch<WorkPreferences>('/work-center/preferences', payload)).data },
}
