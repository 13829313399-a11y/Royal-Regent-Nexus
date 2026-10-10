import { http } from '@/lib/http'

export const COLLABORATIVE_SHEET_MAX_FILE_MB = 100
export const COLLABORATIVE_SHEET_MAX_FILE_BYTES = COLLABORATIVE_SHEET_MAX_FILE_MB * 1024 * 1024
export const COLLABORATIVE_SHEET_FILE_SIZE_ERROR = `工作簿不能超过 ${COLLABORATIVE_SHEET_MAX_FILE_MB} MB`

export type SheetValue = string | number | boolean | null
export interface FillCell {
  address: string
  row: number
  column: number
  value: SheetValue
  display: string
  formula: boolean
  style: Record<string, string | number>
  number_format?: string
  image?: string
}
export interface FillSheet {
  index: number
  name: string
  rows: number
  columns: number
  cells: FillCell[]
  merges: string[]
  row_heights: Record<string, number>
  column_widths: Record<string, number>
  images?: { url: string; row: number; column: number; width: number; height: number }[]
}
export interface FillGrant {
  principal_type: 'user' | 'department'
  principal_id: string
  sheet: number
  range: string
}
export interface FillTask {
  id: string
  title: string
  original_name: string
  format: string
  factory_id: string
  owner_user_id: string
  owner_name: string
  status: 'draft' | 'open' | 'closed'
  revision: number
  created_at: string
  updated_at: string
  is_owner: boolean
}
export interface FillTaskDetail extends FillTask {
  participants?: FillParticipant[]
  grants: FillGrant[]
  workbook: { sheets: FillSheet[]; warnings: string[] }
  editable_ranges: { sheet: number; range: string }[]
  submissions: { user_id: string; display_name: string; revision: number; submitted_at: string; current: boolean }[]
  activity: { id: string; actor_name: string; action: string; revision: number; created_at: string; detail: Record<string, unknown> }[]
}
export interface FillParticipant {
  user_id: string
  display_name: string
  department: string
  status: 'not_started' | 'in_progress' | 'completed' | 'needs_confirmation'
  last_saved_at: string | null
  submitted_at: string | null
}
export interface FillParticipantSnapshot {
  id: string
  revision: number
  status: FillTask['status']
  participants: FillParticipant[]
}
export interface FillRecipients {
  users: { id: string; display_name: string; department: string }[]
  departments: { id: string; name: string }[]
}
export interface FillChange { sheet: number; address: string; value: SheetValue }

const base = '/tools/collaborative-sheets'
const config = (factory_id: string) => ({ params: { factory_id }, timeout: 120_000 })
export const collaborativeSheetsApi = {
  async recipients(factoryId: string) {
    return (await http.get<FillRecipients>(`${base}/recipients`, config(factoryId))).data
  },
  async list(factoryId: string) {
    return (await http.get<{ items: FillTask[] }>(base, config(factoryId))).data
  },
  async create(factoryId: string, title: string, file: File) {
    if (file.size > COLLABORATIVE_SHEET_MAX_FILE_BYTES) throw new Error(COLLABORATIVE_SHEET_FILE_SIZE_ERROR)
    const body = new FormData()
    body.append('factory_id', factoryId)
    body.append('title', title)
    body.append('file', file)
    return (await http.post<FillTaskDetail>(base, body, {
      ...config(factoryId), timeout: 300_000, headers: { 'Content-Type': 'multipart/form-data' },
    })).data
  },
  async detail(factoryId: string, id: string) {
    return (await http.get<FillTaskDetail>(`${base}/${encodeURIComponent(id)}`, config(factoryId))).data
  },
  async participants(factoryId: string, id: string) {
    return (await http.get<FillParticipantSnapshot>(`${base}/${encodeURIComponent(id)}/participants`, config(factoryId))).data
  },
  async grants(factoryId: string, task: FillTask, grants: FillGrant[]) {
    return (await http.put<FillTaskDetail>(`${base}/${task.id}/grants`, {
      expected_revision: task.revision, grants,
    }, config(factoryId))).data
  },
  async state(factoryId: string, task: FillTask, status: 'open' | 'closed') {
    return (await http.post<FillTaskDetail>(`${base}/${task.id}/state`, {
      expected_revision: task.revision, status,
    }, config(factoryId))).data
  },
  async save(factoryId: string, task: FillTask, changes: FillChange[]) {
    return (await http.patch<FillTaskDetail>(`${base}/${task.id}/cells`, {
      expected_revision: task.revision, changes,
    }, config(factoryId))).data
  },
  async submit(factoryId: string, task: FillTask) {
    return (await http.post<FillTaskDetail>(`${base}/${task.id}/submit`, {
      expected_revision: task.revision,
    }, config(factoryId))).data
  },
  async download(factoryId: string, task: FillTask) {
    return (await http.get<Blob>(`${base}/${task.id}/download`, {
      ...config(factoryId), responseType: 'blob',
    })).data
  },
}
