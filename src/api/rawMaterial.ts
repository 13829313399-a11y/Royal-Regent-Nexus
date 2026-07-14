import { http } from '../lib/http.js'

export interface RawMaterialHttpClient {
  get<T = unknown>(url: string): Promise<{ data: T }>
  post<T = unknown>(url: string, data?: unknown): Promise<{ data: T }>
  patch<T = unknown>(url: string, data?: unknown): Promise<{ data: T }>
}

export interface RawMaterialCreateRequest {
  factory_id: string
  material_code: string
  material_name: string
  category: string
  spec?: string
  unit: string
  supplier?: string
  safety_stock_kg?: number | null
  unit_price_hkd_per_lb?: number | null
  status?: '启用' | '停用'
  notes?: string
}

export interface RawMaterialUpdateRequest {
  material_name: string
  category: string
  spec?: string
  unit: string
  supplier?: string
  safety_stock_kg?: number | null
  unit_price_hkd_per_lb?: number | null
  status?: '启用' | '停用'
  notes?: string
}

export interface RawMaterialResponse {
  id: string
  factory_id: string
  material_code: string
  material_name: string
  category: string
  spec: string
  unit: string
  supplier: string
  safety_stock_kg: number | null
  unit_price_hkd_per_lb: number | null
  status: '启用' | '停用'
  notes: string
  created_by: string
  created_at: string
  updated_at: string
}

export function createRawMaterialApi(client: RawMaterialHttpClient = http) {
  return {
    async list(factoryId: string) {
      const response = await client.get<RawMaterialResponse[]>(
        `/raw-materials?factory_id=${encodeURIComponent(factoryId)}`,
      )
      return response.data
    },
    async create(payload: RawMaterialCreateRequest) {
      const response = await client.post<RawMaterialResponse>('/raw-materials', payload)
      return response.data
    },
    async update(materialId: string, payload: RawMaterialUpdateRequest) {
      const response = await client.patch<RawMaterialResponse>(`/raw-materials/${encodeURIComponent(materialId)}`, payload)
      return response.data
    },
  }
}

export const rawMaterialApi = createRawMaterialApi()
