import { http } from '@/lib/http'

export interface ScheduleMarkRow {
  materials_folder_id?: string
  materials_status?: string
  source_sheet: string
  source_row: number
  status: 'UPLOADED' | 'MISSING' | 'REVIEW' | 'RESTRICTED'
  asset_ids: string[]
  status_label?: string
  has_materials?: boolean
  confirmed_count?: number
  pending_count?: number
  draft_count?: number
}
export interface ScheduleMarksWorkspace {
  factory_id: string
  batch_id: string
  source_policy?: 'LEGACY' | 'ASSET_V1'
  rows: ScheduleMarkRow[]
  assets: { id: string; file_name: string; usage_status: string }[]
}
export const cartonScheduleMarksApi = {
  async get(factoryId: string, batchId: string, signal?: AbortSignal) {
    return (await http.get<ScheduleMarksWorkspace>('/carton-mark/assets/schedule', {
      params: { factory_id: factoryId, batch_id: batchId }, signal,
    })).data
  },
}
