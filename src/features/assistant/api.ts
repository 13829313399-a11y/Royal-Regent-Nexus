import { dispatchAccessFailure } from '@/lib/http'
import type { Capabilities, Conversation, HelpArticle, MessagePage, PageContext, SendPayload, Snapshot } from './types'

export function assistantUrl(path: string, base = import.meta.env.VITE_API_BASE_URL || '/api') {
  return `${base.replace(/\/$/, '')}/assistant${path}`
}
export class AssistantApiError extends Error {
  constructor(message: string, public status: number, public code: string, public retryable = false) { super(message) }
}
export async function request(path: string, init: RequestInit = {}) {
  const url = assistantUrl(path)
  const response = await fetch(url, { ...init, credentials: 'include', cache: 'no-store',
    headers: { ...(init.body && !(init.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}), ...init.headers } })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    dispatchAccessFailure(response.status, url, data)
    const detail = data.detail || data
    throw new AssistantApiError(typeof detail === 'string' ? detail : detail.message || '请求未完成，请稍后重试。', response.status, detail.code || 'request_failed', detail.retryable)
  }
  return response
}
async function json<T>(path: string, init: RequestInit = {}): Promise<T> { return (await request(path, init)).json() }
export const assistantApi = {
  capabilities: () => json<Capabilities>('/capabilities'),
  help: (page: PageContext) => json<{ items: HelpArticle[]; status: string }>(`/help/context?${new URLSearchParams({ module_id: page.module_id, route_name: page.route_name, ...(page.factory_id ? { factory_id: page.factory_id } : {}) })}`),
  article: (id: string) => json<HelpArticle>(`/help/articles/${encodeURIComponent(id)}`),
  create: (client_request_id: string) => json<Conversation>('/sessions', { method: 'POST', body: JSON.stringify({ client_request_id }) }),
  sessions: (cursor = '') => json<{ items: Conversation[]; next_cursor: string | null }>(`/sessions?cursor=${encodeURIComponent(cursor)}`),
  messages: (id: string, cursor = 0) => json<MessagePage>(`/sessions/${id}/messages?cursor=${cursor}`),
  rename: (row: Conversation, title: string) => json<Conversation>(`/sessions/${row.id}`, { method: 'PATCH', body: JSON.stringify({ title, revision: row.revision }) }),
  remove: (id: string) => json<{ deletion_state: string }>(`/sessions/${id}`, { method: 'DELETE' }),
  send: (id: string, payload: SendPayload, signal: AbortSignal) => request(`/sessions/${id}/messages`, { method: 'POST', body: JSON.stringify(payload), signal }),
  lookup: (id: string, key: string) => json<Snapshot>(`/sessions/${id}/runs/lookup?client_request_id=${encodeURIComponent(key)}`),
  snapshot: (id: string) => json<Snapshot>(`/runs/${id}`),
  cancel: (id: string) => json<{ state: string }>(`/runs/${id}/cancel`, { method: 'POST' }),
  export: async (id: string) => (await request(`/sessions/${id}/export`)).blob(),
  upload: async (id: string, file: File) => { const body = new FormData(); body.append('file', file); return json<{ id: string }>(`/sessions/${id}/attachments`, { method: 'POST', body }) },
  removeAttachment: (id: string) => request(`/attachments/${id}`, { method: 'DELETE' }),
}

export function newRequestId() {
  // crypto.randomUUID requires a secure context; getRandomValues also works on intranet HTTP.
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  return Array.from(bytes, x => x.toString(16).padStart(2, '0')).join('')
}
