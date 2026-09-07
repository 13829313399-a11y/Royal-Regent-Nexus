import { http } from '@/lib/http'
import type { CartonInventoryBalanceResponse } from './cartonProcurement'

export type StocktakeStatus = 'DRAFT' | 'SUBMITTED' | 'POSTED' | 'CANCELLED'
export interface StocktakeHeader {
  id: string; factory_id: string; status: StocktakeStatus; revision: number
  created_by: string; created_by_name: string; created_at: string
  submitted_by: string; submitted_by_name: string; submitted_at: string
  reviewed_by: string; reviewed_by_name: string; reviewed_at: string; note: string
}
export interface StocktakeLine extends CartonInventoryBalanceResponse {
  id: string; initial_quantity: string; count_book_quantity: string; current_quantity: string
  actual_quantity: string | null; difference: string | null; reason: string
  location_changed: boolean; movement_id: string
}
export interface StocktakeDetail extends StocktakeHeader {
  ledger_token: string; cutoff_at: string; basis_changed: boolean; lines: StocktakeLine[]
  events: { action: string; actor: string; at: string; detail: { reason?: string } }[]
}
export type StocktakeAction = 'SAVE' | 'SUBMIT' | 'APPROVE' | 'RETURN' | 'CANCEL'
export const cartonStocktakeApi = {
  async list(factory_id: string, offset = 0) {
    return (await http.get<StocktakeHeader[]>('/carton-procurement/stocktakes', { params: { factory_id, offset, limit: 100 } })).data
  },
  async detail(factory_id: string, id: string) {
    return (await http.get<StocktakeDetail>(`/carton-procurement/stocktakes/${id}`, { params: { factory_id } })).data
  },
  async create(factory_id: string, reference_movement_ids: string[]) {
    return (await http.post<StocktakeDetail>('/carton-procurement/stocktakes', { factory_id, reference_movement_ids })).data
  },
  async act(id: string, payload: {
    factory_id: string; expected_revision: number; action: StocktakeAction; ledger_token: string
    cutoff_acknowledged: boolean; reason: string
    lines: { id: string; actual_quantity: string | null; reason: string }[]
  }) {
    return (await http.post<StocktakeDetail>(`/carton-procurement/stocktakes/${id}/actions`, payload)).data
  },
}
