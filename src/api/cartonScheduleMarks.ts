import { http } from '@/lib/http'

export interface ScheduleMarkRow {
  source_sheet: string
  source_row: number
  status: 'UPLOADED' | 'MISSING' | 'REVIEW' | 'RESTRICTED'
  asset_ids: string[]
}
export interface ScheduleMarksWorkspace {
  factory_id: string
  batch_id: string
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
