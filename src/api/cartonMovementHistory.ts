import { http } from '@/lib/http'
import type { CartonInventoryMovementResponse } from './cartonProcurement'

export interface CartonHistoryMovement extends CartonInventoryMovementResponse {
  is_reversed: boolean
}

export interface CartonMovementHistoryQuery {
  factory_id: string
  customer_code?: string
  customer_name?: string
  search?: string
  movement_type?: '' | CartonInventoryMovementResponse['movement_type']
  date_from?: string
  date_to?: string
  limit?: number
  offset?: number
}

export interface CartonMovementHistoryPage {
  factory_id: string
  total: number
  limit: number
  offset: number
  items: CartonHistoryMovement[]
}

export const cartonMovementHistoryApi = {
  async list(query: CartonMovementHistoryQuery) {
    const response = await http.get<CartonMovementHistoryPage>(
      '/carton-procurement/inventory/movement-history',
      { params: { ...query, date_from: query.date_from || undefined, date_to: query.date_to || undefined } },
    )
    return response.data
  },
}
