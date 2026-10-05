import { http } from '@/lib/http'

export type FeedbackStatus = 'submitted' | 'needs_info' | 'in_progress' | 'awaiting_verification' | 'resolved'
export type FeedbackAction = 'reply' | 'start' | 'request_info' | 'ready' | 'resolve' | 'reopen'
export type FeedbackView = 'mine' | 'manage'
export interface FeedbackContext {
  page?: string
  section?: string
  customer_code?: string
  order_id?: string
  order_reference?: string
  product_no?: string
  batch_id?: string
  error_message?: string
  file_names?: string[]
  app_version?: string
}
export interface FeedbackCapabilities {
  can_submit: boolean
  can_manage: boolean
  can_link_order: boolean
  max_files: number
  max_file_bytes: number
  max_total_bytes: number
  allowed_extensions: string[]
  material_options: string[]
}
export interface FeedbackAttachment { id: string; file_name: string; content_type: string; size: number; sha256: string; url: string }
export interface FeedbackMessage {
  id: string
  actor_name: string
  actor_kind: string
  body: string
  action: string
  created_at: string
  revision: number
  attachments: FeedbackAttachment[]
  requested_materials: string[]
  provided_materials: string[]
  release_note: string
}
export interface FeedbackTicket {
  id: string
  factory_id: string
  module: string
  title: string
  category: 'bug' | 'suggestion' | 'question'
  emoji: string
  status: FeedbackStatus
  author_id: string
  author_name: string
  assigned_name: string
  context: FeedbackContext
  requested_materials: string[]
  provided_materials: string[]
  release_note: string
  revision: number
  created_at: string
  updated_at: string
  unread: boolean
}
export interface FeedbackDetail extends FeedbackTicket { messages: FeedbackMessage[] }
export interface FeedbackList { items: FeedbackTicket[]; total: number; unread_count: number; page: number; page_size: number }
export interface FeedbackCreate {
  factory_id: string
  module: string
  title: string
  category: FeedbackTicket['category']
  emoji: string
  body: string
  context: FeedbackContext
  client_request_id: string
}
export interface FeedbackReply {
  expected_revision: number
  client_request_id: string
  action: FeedbackAction
  body: string
  requested_materials?: string[]
  provided_materials?: string[]
  release_note?: string
}

function multipart(payload: FeedbackCreate | FeedbackReply, files: File[]) {
  const form = new FormData()
  form.append('payload', JSON.stringify(payload))
  files.forEach(file => form.append('files', file, file.name))
  return form
}
const base = '/module-feedback'
const uploadOptions = { timeout: 90000, headers: { 'Content-Type': undefined } }
export const moduleFeedbackApi = {
  async capabilities(factoryId: string, module = 'customer-order-center') {
    return (await http.get<FeedbackCapabilities>(`${base}/capabilities`, { params: { factory_id: factoryId, module } })).data
  },
  async list(factoryId: string, view: FeedbackView, options: { status?: FeedbackStatus | ''; q?: string; page?: number; page_size?: number } = {}) {
    return (await http.get<FeedbackList>(base, { params: { factory_id: factoryId, module: 'customer-order-center', view, ...options, status: options.status || undefined } })).data
  },
  async create(payload: FeedbackCreate, files: File[]) {
    return (await http.post<FeedbackDetail>(base, multipart(payload, files), uploadOptions)).data
  },
  async detail(id: string, factoryId: string) {
    return (await http.get<FeedbackDetail>(`${base}/${encodeURIComponent(id)}`, { params: { factory_id: factoryId } })).data
  },
  async reply(id: string, factoryId: string, payload: FeedbackReply, files: File[]) {
    return (await http.post<FeedbackDetail>(`${base}/${encodeURIComponent(id)}/messages`, multipart(payload, files), { ...uploadOptions, params: { factory_id: factoryId } })).data
  },
  async read(id: string, factoryId: string, throughRevision: number) {
    return (await http.post(`${base}/${encodeURIComponent(id)}/read`, { through_revision: throughRevision }, { params: { factory_id: factoryId } })).data
  },
}

// Construct links locally; never navigate to an arbitrary attachment URL from a response.
export function feedbackAttachmentUrl(ticket: FeedbackTicket, attachment: FeedbackAttachment) {
  const apiBase = String(http.defaults.baseURL ?? '/api').replace(/\/+$/, '')
  return `${apiBase}${base}/${encodeURIComponent(ticket.id)}/attachments/${encodeURIComponent(attachment.id)}?factory_id=${encodeURIComponent(ticket.factory_id)}`
}
