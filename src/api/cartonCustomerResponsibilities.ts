import { http } from '@/lib/http'

export interface CartonCustomerResponsibilities {
  can_manage: boolean
  unrestricted: boolean
  own_customer_codes: string[]
  blocked_customer_codes?: string[]
  users: { id: string; name: string }[]
  customers: { id: string; code: string; name: string; revision: number; status: string; users: { id: string; name: string }[];
    owner?: { id: string; name: string } | null; can_manage?: boolean; can_claim?: boolean }[]
}
export const emptyResponsibilities = (): CartonCustomerResponsibilities => ({ can_manage: false, unrestricted: false, own_customer_codes: [], users: [], customers: [] })
export const cartonCustomerResponsibilitiesApi = {
  async get(factory_id: string, signal?: AbortSignal, summary = false) {
    return (await http.get<CartonCustomerResponsibilities>('/carton-procurement/customer-responsibilities', { params: { factory_id, ...(summary ? { summary: true } : {}) }, signal })).data
  },
  async claim(factory_id: string, customer_id: string, expected_revision: number, signal?: AbortSignal) {
    return (await http.post<CartonCustomerResponsibilities>(`/carton-procurement/customers/${encodeURIComponent(customer_id)}/claim`, { factory_id, expected_revision }, { signal })).data
  },
  async save(factory_id: string, customer_id: string, user_ids: string[], expected_revision: number, reason: string, signal?: AbortSignal, owner_user_id?: string | null) {
    return (await http.put<CartonCustomerResponsibilities>(`/carton-procurement/customers/${encodeURIComponent(customer_id)}/responsibilities`, { factory_id, user_ids, expected_revision, reason, ...(owner_user_id !== undefined ? { owner_user_id } : {}) }, { signal })).data
  },
}
