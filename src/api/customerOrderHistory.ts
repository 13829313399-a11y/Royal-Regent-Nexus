import { http } from '@/lib/http'

export interface CustomerOrderHistoryHttpClient {
  get<T = unknown>(url: string, config?: unknown): Promise<{ data: T }>
  post<T = unknown>(url: string, data?: unknown, config?: unknown): Promise<{ data: T }>
}

export interface CustomerOrderHistoryCustomer {
  code: string
  name: string
}

export type CustomerOrderHistorySection = 'unshipped' | 'shipped' | 'cancelled'
export type CustomerOrderHistoryStatus = 'active' | 'cancelled'

export interface CustomerOrderHistoryRow {
  id: string
  sheet: string
  row: number
  section: CustomerOrderHistorySection
  reference_no: string
  product_no: string
  quantity: string
  requested_ship_date: string
  customer_name: string
  issues: string[]
  blocked: boolean
  existing: boolean
  data: Record<string, unknown>
}

export interface CustomerOrderHistoryPreview {
  factory_id: string
  customer_code: string
  customer_name: string
  file_name: string
  fingerprint: string
  rows: CustomerOrderHistoryRow[]
  warnings: string[]
  summary: { total: number; blocked: number; existing: number }
}

export interface CustomerOrderHistorySelection {
  id: string
  status: CustomerOrderHistoryStatus
  opening_shipped_quantity: string
}

export interface CustomerOrderHistoryConfirmResult {
  created_count: number
  existing_count: number
  items: unknown[]
}

function query(params: Record<string, string | undefined>) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value) search.set(key, value)
  })
  return search.toString()
}

function basePayload(factoryId: string, customerCode: string, file: File) {
  const form = new FormData()
  form.append('factory_id', factoryId)
  form.append('customer_code', customerCode)
  form.append('schedule_file', file)
  return form
}

export function createCustomerOrderHistoryApi(client: CustomerOrderHistoryHttpClient = http) {
  const base = '/customer-order-ledger/history'
  return {
    async customers(factoryId: string) {
      return (await client.get<{ items: CustomerOrderHistoryCustomer[] }>(`${base}/customers?${query({ factory_id: factoryId })}`)).data
    },
    async preview(factoryId: string, customerCode: string, file: File) {
      return (await client.post<CustomerOrderHistoryPreview>(`${base}/preview`, basePayload(factoryId, customerCode, file), {
        headers: { 'Content-Type': 'multipart/form-data' }, timeout: 240_000,
      })).data
    },
    async confirm(
      factoryId: string,
      customerCode: string,
      file: File,
      payload: { fingerprint: string; cutoff_date: string; reason: string; selections: CustomerOrderHistorySelection[] },
    ) {
      const form = basePayload(factoryId, customerCode, file)
      form.append('fingerprint', payload.fingerprint)
      form.append('cutoff_date', payload.cutoff_date)
      form.append('reason', payload.reason)
      form.append('selections', JSON.stringify(payload.selections))
      form.append('confirmed', 'true')
      return (await client.post<CustomerOrderHistoryConfirmResult>(`${base}/confirm`, form, {
        headers: { 'Content-Type': 'multipart/form-data' }, timeout: 240_000,
      })).data
    },
    async correctOpening(id: string, factoryId: string, payload: { expected_revision: number; opening_shipped_quantity: string; reason: string }) {
      return (await client.post(`/customer-order-ledger/lines/${encodeURIComponent(id)}/history-opening?${query({ factory_id: factoryId })}`, payload)).data
    },
  }
}

export const customerOrderHistoryApi = createCustomerOrderHistoryApi()
