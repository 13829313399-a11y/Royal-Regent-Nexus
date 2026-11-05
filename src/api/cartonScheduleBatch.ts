import { http } from '@/lib/http'
import type { CartonOrderCreateRequest, CartonOrderResponse } from './cartonProcurement'

export interface ScheduleBatchSource { batch_id: string; source_sheet: string; source_row: number }
export interface ScheduleBatchLineOverride { line_no: number; manual_quantity?: number | null; net_weight_kg?: number | null; gross_weight_kg?: number | null }
export interface ScheduleBatchOrderOverride extends ScheduleBatchSource { lines: ScheduleBatchLineOverride[] }
export interface ScheduleBatchBody {
  factory_id: string; request_id: string; sources: ScheduleBatchSource[]; planned_due_date: string
  lines: CartonOrderCreateRequest['lines']; master_config_id: string; master_config_revision: number
  note?: string; rush?: boolean; rush_reason?: string; order_overrides?: ScheduleBatchOrderOverride[]
}
export const cartonScheduleBatchApi = {
  async create(body: ScheduleBatchBody, signal?: AbortSignal) {
    return (await http.post<CartonOrderResponse[]>('/carton-procurement/orders/from-schedule-batch', body, { signal })).data
  },
}
