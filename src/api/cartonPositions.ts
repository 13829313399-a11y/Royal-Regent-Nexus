import { http } from '@/lib/http'
import { postCartonInventoryRequest } from './cartonInventoryRequest'

export interface CartonLocation { id: string; factory_id: string; warehouse: string; bin_code: string; label: string; status?: string; revision?: number }
export interface LocationAllocation { location_id: string; quantity: string | number }
export const cartonPositionsApi = {
  async locations(factory_id: string) {
    return (await http.get<CartonLocation[]>('/carton-procurement/inventory/locations', { params: { factory_id } })).data
  },
  async create(factory_id: string, warehouse: string, bin_code: string, reason = '新增仓库仓位') {
    return (await http.post<CartonLocation>('/carton-procurement/inventory/locations', { factory_id, warehouse, bin_code, reason })).data
  },
  async transfer(payload: { factory_id: string; position_key: string; expected_position_revision: number; location_id: string; quantity: number; note: string }) {
    return postCartonInventoryRequest<{ id: string; quantity: string; from_location: string; to_location: string }>(
      '/carton-procurement/inventory/transfers', payload)
  },
}
