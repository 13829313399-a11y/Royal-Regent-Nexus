import { http } from '../lib/http.js'
import type {
  MoldingSampleAuditLog,
  MoldingSampleItem,
  MoldingSampleOrder,
  MoldingSampleRole,
} from '../types/moldingSample.js'
import type { MoldingSampleMaterialPrice } from '../lib/moldingSampleBusiness.js'

export interface HttpLikeClient {
  get<T = unknown>(url: string): Promise<{ data: T }>
  post<T = unknown>(url: string, data?: unknown): Promise<{ data: T }>
  put<T = unknown>(url: string, data?: unknown): Promise<{ data: T }>
  patch<T = unknown>(url: string, data?: unknown): Promise<{ data: T }>
  delete<T = unknown>(url: string): Promise<{ data: T }>
}

export type MoldingSampleOrderDraft = Partial<MoldingSampleOrder>
  & Pick<MoldingSampleOrder, 'id' | 'product_name' | 'client_name' | 'date' | 'workshop' | 'supervisor' | 'eng_name'>

export type MoldingSampleItemDraft = Partial<MoldingSampleItem> & Pick<MoldingSampleItem, 'id'>

export interface MoldingSampleCreateRequest {
  order: MoldingSampleOrderDraft
  items: MoldingSampleItemDraft[]
}

export interface MoldingSampleEditRequest extends MoldingSampleCreateRequest {
  actor_name: string
  actor_role: MoldingSampleRole
  pin?: string
}

export interface MoldingSampleDeleteRequest {
  actor_name: string
  actor_role: MoldingSampleRole
  pin?: string
}

export interface MoldingSampleDetailResponse {
  order: MoldingSampleOrder
  items: MoldingSampleItem[]
  audit_logs: MoldingSampleAuditLog[]
}

export interface MoldingSampleStatusRequest {
  action: string
  reviewer_name: string
  reviewer_role: MoldingSampleRole
  pin?: string
  reason?: string
  today?: string
}

export interface MoldingSampleItemsPatchRequest {
  items: MoldingSampleItemDraft[]
}

export interface MaterialPricesResponse {
  prices: MoldingSampleMaterialPrice[]
  rmb_to_hkd_rate: number
}

export interface MaterialPricesUpdateRequest extends MaterialPricesResponse {
  manager_name?: string
  manager_pin?: string
}

export interface PinVerifyRequest {
  name: string
  role: MoldingSampleRole
  pin: string
}

export interface PinChangeRequest {
  name: string
  role: MoldingSampleRole
  old_pin: string
  new_pin: string
}

export interface PinVerifyResponse {
  valid: boolean
  name: string
  role: MoldingSampleRole
  must_change: boolean
}

export interface RolesResponse {
  supervisors: Array<{ name: string, role: MoldingSampleRole, must_change: boolean }>
  managers: Array<{ name: string, role: MoldingSampleRole, must_change: boolean }>
}

export interface InjectionTotalCostSummary {
  order_id: string
  order_number: string
  doc_number: string
  product_name: string
  client_name: string
  completed_date: string
  workshop: string
  send_to: string
  status: string
  total_material_cost: number
  total_injection_cost: number
  total_cost: number
  has_missing_price: boolean
  has_missing_injection_cost: boolean
  item_rows: Array<Record<string, unknown>>
}

export function createMoldingSampleApi(client: HttpLikeClient = http) {
  return {
    async listOrders() {
      const response = await client.get<MoldingSampleDetailResponse[]>('/injection')
      return response.data
    },
    async getOrder(orderId: string) {
      const response = await client.get<MoldingSampleDetailResponse>(`/injection/${orderId}`)
      return response.data
    },
    async getRoles() {
      const response = await client.get<RolesResponse>('/roles')
      return response.data
    },
    async createOrder(payload: MoldingSampleCreateRequest) {
      const response = await client.post<MoldingSampleDetailResponse>('/injection', payload)
      return response.data
    },
    async editOrder(orderId: string, payload: MoldingSampleEditRequest) {
      const response = await client.put<MoldingSampleDetailResponse>(`/injection/${orderId}`, payload)
      return response.data
    },
    async deleteOrder(orderId: string, payload: MoldingSampleDeleteRequest) {
      const params = new URLSearchParams({
        actor_name: payload.actor_name,
        actor_role: payload.actor_role,
      })
      if (payload.pin) {
        params.set('pin', payload.pin)
      }
      const response = await client.delete(`/injection/${orderId}?${params.toString()}`)
      return response.data
    },
    async updateStatus(orderId: string, payload: MoldingSampleStatusRequest) {
      const response = await client.patch<MoldingSampleDetailResponse>(`/injection/${orderId}/status`, payload)
      return response.data
    },
    async updateItems(orderId: string, payload: MoldingSampleItemsPatchRequest) {
      const response = await client.patch<MoldingSampleDetailResponse>(`/injection/${orderId}/items`, payload)
      return response.data
    },
    async getMaterialPrices() {
      const response = await client.get<MaterialPricesResponse>('/material-prices')
      return response.data
    },
    async updateMaterialPrices(payload: MaterialPricesUpdateRequest) {
      const response = await client.post<MaterialPricesResponse>('/manager-update-prices', payload)
      return response.data
    },
    async verifyPin(payload: PinVerifyRequest) {
      const response = await client.post<PinVerifyResponse>('/verify-pin', payload)
      return response.data
    },
    async changePin(payload: PinChangeRequest) {
      const response = await client.post<PinVerifyResponse>('/change-pin', payload)
      return response.data
    },
    async getTotalCosts() {
      const response = await client.get<InjectionTotalCostSummary[]>('/injection-total-costs')
      return response.data
    },
  }
}

export const moldingSampleApi = createMoldingSampleApi()
