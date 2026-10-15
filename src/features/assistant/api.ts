import { dispatchAccessFailure } from '@/lib/http'
import { getAuthenticationGeneration } from '@/lib/authenticationGeneration'
import type { Artifact, DocumentFile, Capabilities, Conversation, HelpArticle, MessagePage, PageContext, SendPayload, Snapshot } from './types'

export function assistantUrl(path: string, base = import.meta.env.VITE_API_BASE_URL || '/api') {
  return `${base.replace(/\/$/, '')}/assistant${path}`
}
export class AssistantApiError extends Error {
  constructor(message: string, public status: number, public code: string, public retryable = false) { super(message) }
}
export async function request(path: string, init: RequestInit = {}) {
  const url = assistantUrl(path)
  const generation = getAuthenticationGeneration()
  const response = await fetch(url, { ...init, credentials: 'include', cache: 'no-store',
    headers: { ...(init.body && !(init.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}), ...init.headers } })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    dispatchAccessFailure(response.status, url, data, generation)
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
  sessions: (cursor = '', q = '', favorites = false) => json<{ items: Conversation[]; next_cursor: string | null }>(`/sessions?${new URLSearchParams({ cursor, q, favorites: String(favorites) })}`),
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
  attachment: async (id: string) => (await request(`/attachments/${id}/content`)).blob(),
  uploadDocument: async (sid: string, file: File) => { const body = new FormData(); body.append('file', file); return json<DocumentFile>(`/sessions/${sid}/files`, { method: 'POST', body }) },
  document: (id: string) => json<DocumentFile>(`/files/${id}`),
  documentContent: (id: string) => json<{ text: string; locator: import('./v2').FileSource['locator'] }[]>(`/files/${id}/content?extracted=true`),
  removeDocument: (id: string) => request(`/files/${id}`, { method: 'DELETE' }),
  saveArtifact: (sid: string, value: { source_run_id: string; title: string; kind: string; content: string }) => json<Artifact>(`/sessions/${sid}/artifacts`, { method: 'POST', body: JSON.stringify(value) }),
  artifacts: (cursor = '', q = '') => json<{ items: Artifact[]; next_cursor: string | null }>(`/artifacts?${new URLSearchParams({cursor, q})}`),
  artifact: (id: string, revision?: number) => json<Artifact>(`/artifacts/${id}${revision ? `?revision=${revision}` : ''}`),
  reviseArtifact: (id: string, base_revision: number, content: string) => json<Artifact>(`/artifacts/${id}/versions`, { method: 'POST', body: JSON.stringify({base_revision, content}) }),
  exportArtifact: async (id: string, format: string, revision?: number) => (await request(`/artifacts/${id}/export?format=${encodeURIComponent(format)}${revision ? `&revision=${revision}` : ''}`)).blob(),
  exportAnswer: async (id: string) => (await request(`/runs/${id}/export`)).blob(),
  favorite: (sid: string, favorite: boolean) => json<{favorite: boolean}>(`/sessions/${sid}/favorite`, { method: 'PATCH', body: JSON.stringify({favorite}) }),
  action: (run_id: string, index: number) => json<import('./v2').UIAction>('/actions/resolve', { method: 'POST', body: JSON.stringify({run_id, index}) }),
}

export function newRequestId() {
  // crypto.randomUUID requires a secure context; getRandomValues also works on intranet HTTP.
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  return Array.from(bytes, x => x.toString(16).padStart(2, '0')).join('')
}
