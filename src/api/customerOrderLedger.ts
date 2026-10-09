import { http } from '@/lib/http'

export interface CustomerOrderLedgerHttpClient {
  get<T = unknown>(url: string, config?: unknown): Promise<{ data: T }>
  post<T = unknown>(url: string, data?: unknown, config?: unknown): Promise<{ data: T }>
}

export interface CustomerOrderLedgerCapabilities {
  cutting_dispatch_enabled?: boolean
  read: boolean
  write: boolean
  dispatch: boolean
  shipment_confirm: boolean
  inbox_read: boolean
  inbox_receive: boolean
}

export interface CustomerOrderLedgerLine {
  id: string
  factory_id: string
  customer_code: string
  customer_name: string
  reference_no: string
  product_no: string
  quantity: string
  shipped_quantity: string
  remaining_quantity: string
  status: 'active' | 'cancelled'
  version: number
  revision: number
  dispatch_status: 'unsent' | 'sent' | 'changed'
  data: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface CustomerOrderLedgerList {
  items: CustomerOrderLedgerLine[]
  total: number
  page: number
  page_size: number
  customers: Array<{ code: string; name: string }>
}

export interface CustomerOrderLedgerDetail {
  line: CustomerOrderLedgerLine
  versions: Array<{ version: number; data: Record<string, unknown>; reason: string; actor: string; created_at: string }>
  dispatches: Array<{ id: string; recipient: string; version: number; status: 'sent' | 'received'; created_at: string; received_at: string | null; received_by: string | null }>
  shipments: Array<{ id: string; quantity: string; ship_date: string; document_no: string; note: string; actor: string; created_at: string; reversed: boolean; reversal_reason: string }>
  sources: Array<{ id: string; file_name: string; kind: string }>
}

export type CustomerOrderLedgerView = 'all' | 'unshipped' | 'shipped' | 'cancelled'

function query(params: Record<string, string | number | undefined>) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') search.set(key, String(value))
  })
  return search.toString()
}

export function customerOrderLedgerSourceUrl(sourceId: string, factoryId: string) {
  const base = String(import.meta.env?.VITE_API_BASE_URL ?? '/api').replace(/\/+$/, '')
  return `${base}/customer-order-ledger/sources/${encodeURIComponent(sourceId)}?${query({ factory_id: factoryId })}`
}

export function createCustomerOrderLedgerApi(client: CustomerOrderLedgerHttpClient = http) {
  const base = '/customer-order-ledger'
  return {
    async capabilities(factoryId: string) {
      return (await client.get<CustomerOrderLedgerCapabilities>(`${base}/capabilities?${query({ factory_id: factoryId })}`)).data
    },
    async list(factoryId: string, options: { customerCode?: string; view?: CustomerOrderLedgerView; q?: string; page?: number; pageSize?: number } = {}) {
      return (await client.get<CustomerOrderLedgerList>(`${base}/lines?${query({
        factory_id: factoryId,
        customer_code: options.customerCode,
        view: options.view ?? 'all',
        q: options.q,
        page: options.page ?? 1,
        page_size: options.pageSize ?? 50,
      })}`)).data
    },
    async detail(id: string, factoryId: string) {
      return (await client.get<CustomerOrderLedgerDetail>(`${base}/lines/${encodeURIComponent(id)}?${query({ factory_id: factoryId })}`)).data
    },
    async amend(id: string, factoryId: string, payload: { expected_revision: number; quantity: string; requested_ship_date: string; note: string; reason: string }) {
      return (await client.post<CustomerOrderLedgerLine>(`${base}/lines/${encodeURIComponent(id)}/amend?${query({ factory_id: factoryId })}`, payload)).data
    },
    async cancel(id: string, factoryId: string, payload: { expected_revision: number; reason: string }) {
      return (await client.post<CustomerOrderLedgerLine>(`${base}/lines/${encodeURIComponent(id)}/cancel?${query({ factory_id: factoryId })}`, payload)).data
    },
    async dispatch(id: string, factoryId: string, payload: { expected_revision: number; recipients: Array<'pmc' | 'warehouse' | 'injection' | 'cutting'> }) {
      return (await client.post<CustomerOrderLedgerLine>(`${base}/lines/${encodeURIComponent(id)}/dispatch?${query({ factory_id: factoryId })}`, payload)).data
    },
    async confirmShipment(id: string, factoryId: string, payload: { expected_revision: number; idempotency_key: string; quantity: string; ship_date: string; document_no: string; note: string }) {
      return (await client.post<CustomerOrderLedgerLine>(`${base}/lines/${encodeURIComponent(id)}/shipments?${query({ factory_id: factoryId })}`, payload)).data
    },
    async reverseShipment(id: string, factoryId: string, payload: { expected_revision: number; reason: string }) {
      return (await client.post<CustomerOrderLedgerLine>(`${base}/shipments/${encodeURIComponent(id)}/reverse?${query({ factory_id: factoryId })}`, payload)).data
    },
    async importConfirmed(customerCode: string, payload: FormData) {
      return (await client.post<{ items: CustomerOrderLedgerLine[]; created_count: number; existing_count: number; reconciled_count: number }>(
        `${base}/imports/${encodeURIComponent(customerCode)}`,
        payload,
        { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 240_000 },
      )).data
    },
  }
}

export const customerOrderLedgerApi = createCustomerOrderLedgerApi()
