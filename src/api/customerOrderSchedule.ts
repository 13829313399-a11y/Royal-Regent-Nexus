import { http } from '@/lib/http'
import type { CustomerOrderLedgerLine } from '@/api/customerOrderLedger'

export interface CustomerOrderScheduleHttpClient {
  get<T = unknown>(url: string, config?: unknown): Promise<{ data: T }>
  post?<T = unknown>(url: string, data?: unknown, config?: unknown): Promise<{ data: T; headers?: Record<string, unknown> }>
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

export type CustomerOrderScheduleLine = CustomerOrderLedgerLine & {
  schedule_inspection_date?: string
  inspection_date_warning?: string
}

export interface CustomerOrderScheduleSection {
  items: CustomerOrderScheduleLine[]
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
  inspection_grouping?: { as_of_date: string; timezone: 'Asia/Shanghai' }
  sections: {
    unshipped: CustomerOrderScheduleSection
    shipped: CustomerOrderScheduleSection
    cancelled: CustomerOrderScheduleSection
    inspection_pending?: CustomerOrderScheduleSection
    completed?: CustomerOrderScheduleSection
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
  inspectionPendingPage?: number
  completedPage?: number
  pageSize?: number
}

export interface CustomerOrderScheduleOrganizeReport {
  as_of_date: string
  sheets: Record<string, { moved_to_completed: number; moved_to_pending: number }>
  warning_count: number
  warnings: string[]
}

function organizeReport(header: unknown): CustomerOrderScheduleOrganizeReport | undefined {
  // This optional display summary must never prevent a successful download.
  if (typeof header !== 'string' || header.length > 5_000) return undefined
  const isCount = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0
  try {
    const value = JSON.parse(decodeURIComponent(header)) as Record<string, unknown> | null
    if (!value || typeof value !== 'object' || Array.isArray(value)
      || typeof value.as_of_date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value.as_of_date)
      || !value.sheets || typeof value.sheets !== 'object' || Array.isArray(value.sheets)
      || !isCount(value.warning_count) || !Array.isArray(value.warnings)
      || value.warnings.some((warning) => typeof warning !== 'string')
      || value.warning_count < value.warnings.length) return undefined
    const sheets: CustomerOrderScheduleOrganizeReport['sheets'] = {}
    for (const [name, rawStats] of Object.entries(value.sheets)) {
      if (!['ITEM表', '接单表', '正单评审表'].includes(name) || !rawStats || typeof rawStats !== 'object' || Array.isArray(rawStats)) return undefined
      const stats = rawStats as Record<string, unknown>
      if (!isCount(stats.moved_to_completed) || !isCount(stats.moved_to_pending)) return undefined
      sheets[name] = { moved_to_completed: stats.moved_to_completed, moved_to_pending: stats.moved_to_pending }
    }
    if (Object.keys(sheets).length !== 3) return undefined
    return { as_of_date: value.as_of_date, sheets, warning_count: value.warning_count,
      warnings: value.warnings.slice(0, 3).map((warning: string) => warning.slice(0, 100)) }
  } catch {
    return undefined
  }
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
        inspection_pending_page: options.inspectionPendingPage ?? 1,
        completed_page: options.completedPage ?? 1,
        page_size: options.pageSize ?? 50,
      })}`)).data
    },
    async organize360(factoryId: string, file: File) {
      if (!client.post) throw new Error('当前客户端不支持排期整理下载。')
      const payload = new FormData()
      payload.append('schedule_file', file)
      const response = await client.post<Blob>(`${base}/organize-360?${query({ factory_id: factoryId })}`, payload, {
        headers: { 'Content-Type': 'multipart/form-data' },
        responseType: 'blob',
        timeout: 300_000,
      })
      const disposition = String(response.headers?.['content-disposition'] ?? '')
      const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
      let fileName = '360_按验货日期整理.xlsx'
      if (encoded) {
        try { fileName = decodeURIComponent(encoded) } catch { /* Keep the safe fallback. */ }
      } else {
        fileName = disposition.match(/filename="([^"]+)"/i)?.[1] ?? fileName
      }
      const report = organizeReport(response.headers?.['x-schedule-organize-report'])
      return { blob: response.data, fileName, ...(report ? { report } : {}) }
    },
  }
}

export const customerOrderScheduleApi = createCustomerOrderScheduleApi()
