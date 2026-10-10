import { http } from '@/lib/http'

export interface Owner { user_id: string; employment_epoch: number }
export interface Capabilities { enabled: boolean; eligible: boolean; owner: Owner; features: Record<string, unknown> }
export interface MemberProfile {
  bio: string; help_topics: string; skill_tags: string[]; theme: 'celadon' | 'jade' | 'dusk' | 'champagne'
  availability: 'available' | 'busy' | 'leave_message'; status_text: string; status_expires_at: string | null; version: number
}
export interface Preferences {
  motion: 'rich' | 'simple' | 'off'; density: 'comfortable' | 'compact'; sound_enabled: boolean
  read_receipts_enabled: boolean; dnd_until: string | null; send_key: 'enter' | 'ctrl_enter'; module_shortcuts: string[]; version: number
}
export interface Attachment { id: string; filename: string; mime: string; size: number; state: string; url: string }
export interface Reference { resource_type: 'molding_sample' | 'internal_quote'; resource_id: string; factory_id: string }
export interface ReferenceProjection { available: boolean; label: string; title?: string; status?: string; url?: string; factory_id?: string }
export interface Message {
  id: string; conversation_id: string; message_seq: number; sender_user_id: string; client_message_id: string | null
  kind: 'text' | 'attachment' | 'business_reference'; body: string; created_at: string; retracted_at: string | null; version: number
  reply_to_id: string | null; reply: { id: string; message_seq: number; body: string; retracted: boolean } | null
  attachments: Attachment[]; reference: ReferenceProjection | null
}
export interface MessagePayload { client_message_id: string; kind: Message['kind']; body: string; reply_to_id: string | null; attachment_ids: string[]; reference: Reference | null; draft_version: number | null }
export interface Conversation {
  id: string; peer: { id: string; display_name: string; available: boolean }; last_message_seq: number; last_read_seq: number
  unread: number; revision: number; updated_at: string; mute_until: string | null; pin_order: number; archived_at: string | null
  version: number; peer_read_seq: number | null; last_message: Message | null
}
export interface Draft { text: string; reply_to_id: string | null; attachment_ids: string[]; version: number; unavailable_attachment_ids?: string[] }
export interface Page<T> { items: T[]; next_cursor: string | null }
export interface MessagePage { items: Message[]; has_more: boolean; last_read_seq: number; last_message_seq: number }
export interface Bootstrap { owner: Owner; conversations: Page<Conversation>; unread: number; preferences: Preferences; cursor: string; server_now: string }
export interface UserEvent { event_seq: number; type: string; entity_id?: string; entity_version?: number; conversation_id?: string; message?: Message; notify_receiver?: boolean }
export interface SyncBatch { owner: Owner; events: UserEvent[]; cursor: string; has_more: boolean; unread: number; server_now: string }
export interface Appreciation { id: string; sender_id: string; receiver_id: string; sender_name: string; receiver_name: string; category: string; text: string; created_at: string; version: number | null; receiver_seen_at: string | null; private_pin_order: number; hidden_at: string | null }

export const collaborationApi = {
  async get<T>(path: string, signal?: AbortSignal, params?: Record<string, unknown>) { return (await http.get<T>(`/collaboration${path}`, { signal, params })).data },
  async post<T>(path: string, body: unknown, signal?: AbortSignal) { return (await http.post<T>(`/collaboration${path}`, body, { signal })).data },
  async patch<T>(path: string, body: unknown, signal?: AbortSignal) { return (await http.patch<T>(`/collaboration${path}`, body, { signal })).data },
  async contact(id: string, add: boolean, signal?: AbortSignal) { return add ? http.put(`/collaboration/me/contacts/${encodeURIComponent(id)}`, {}, { signal }) : http.delete(`/collaboration/me/contacts/${encodeURIComponent(id)}`, { signal }) },
  async upload(cid: string, file: File, clientId: string, progress: (value: number) => void, signal?: AbortSignal) {
    const form = new FormData(); form.append('file', file); form.append('client_upload_id', clientId)
    return (await http.post<Attachment>(`/collaboration/conversations/${cid}/attachments`, form, {
      signal, timeout: 120_000, headers: { 'Content-Type': undefined }, onUploadProgress: event => progress(Math.round((event.progress ?? 0) * 100)),
    })).data
  },
}
