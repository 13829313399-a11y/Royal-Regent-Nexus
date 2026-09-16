import { http } from '@/lib/http'
import type { CustomerOrderLedgerLine } from '@/api/customerOrderLedger'

export interface CustomerOrderScheduleHttpClient {
  get<T = unknown>(url: string, config?: unknown): Promise<{ data: T }>
}

export interface CustomerOrderScheduleCustomer {
  code: string
  name: string
}

export interface CustomerOrderScheduleColumn {
  key: string
  label: string
}

export interface CustomerOrderScheduleSummary {
  order_count: number
  ordered_quantity: string
  shipped_quantity: string
  remaining_quantity: string
  unknown_quantity_count: number
  cancelled_count: number
}

export interface CustomerOrderScheduleSection {
  items: CustomerOrderLedgerLine[]
  total: number
  page: number
  page_size: number
}

export interface CustomerOrderScheduleResult {
  factory_id: string
  customer_code: string
  customer_name: string
  columns: CustomerOrderScheduleColumn[]
  summary: CustomerOrderScheduleSummary
  sections: {
    unshipped: CustomerOrderScheduleSection
    shipped: CustomerOrderScheduleSection
    cancelled: CustomerOrderScheduleSection
  }
}

export interface CustomerOrderScheduleOptions {
  customerCode: string
  q?: string
  dateFrom?: string
  dateTo?: string
  unshippedPage?: number
  shippedPage?: number
  cancelledPage?: number
  pageSize?: number
}

function query(params: Record<string, string | number | undefined>) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') search.set(key, String(value))
  })
  return search.toString()
}

export function createCustomerOrderScheduleApi(client: CustomerOrderScheduleHttpClient = http) {
  const base = '/customer-order-ledger/schedule'
  return {
    async customers(factoryId: string) {
      return (await client.get<{ factory_id: string; items: CustomerOrderScheduleCustomer[] }>(
        `${base}/customers?${query({ factory_id: factoryId })}`,
      )).data
    },
    async get(factoryId: string, options: CustomerOrderScheduleOptions) {
      return (await client.get<CustomerOrderScheduleResult>(`${base}?${query({
        factory_id: factoryId,
        customer_code: options.customerCode,
        q: options.q,
        date_from: options.dateFrom,
        date_to: options.dateTo,
        unshipped_page: options.unshippedPage ?? 1,
        shipped_page: options.shippedPage ?? 1,
        cancelled_page: options.cancelledPage ?? 1,
        page_size: options.pageSize ?? 50,
      })}`)).data
    },
  }
}

export const customerOrderScheduleApi = createCustomerOrderScheduleApi()
