import { http } from '@/lib/http'

export interface CartonCustomerResponsibilities {
  can_manage: boolean
  unrestricted: boolean
  own_customer_codes: string[]
  users: { id: string; name: string }[]
  customers: { id: string; code: string; name: string; revision: number; status: string; users: { id: string; name: string }[] }[]
}
export const emptyResponsibilities = (): CartonCustomerResponsibilities => ({ can_manage: false, unrestricted: false, own_customer_codes: [], users: [], customers: [] })
export const cartonCustomerResponsibilitiesApi = {
  async get(factory_id: string, signal?: AbortSignal, summary = false) {
    return (await http.get<CartonCustomerResponsibilities>('/carton-procurement/customer-responsibilities', { params: { factory_id, ...(summary ? { summary: true } : {}) }, signal })).data
  },
  async save(factory_id: string, customer_id: string, user_ids: string[], expected_revision: number, reason: string, signal?: AbortSignal) {
    return (await http.put<CartonCustomerResponsibilities>(`/carton-procurement/customers/${encodeURIComponent(customer_id)}/responsibilities`, { factory_id, user_ids, expected_revision, reason }, { signal })).data
  },
}
