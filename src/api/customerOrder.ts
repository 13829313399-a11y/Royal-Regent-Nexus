import { http } from '@/lib/http'
import type { CustomerOrderImportPreview } from '@/types/customerOrder'

export interface CustomerOrderHttpClient {
  post<T = unknown>(
    url: string,
    data?: unknown,
    config?: unknown,
  ): Promise<{ data: T; headers?: Record<string, unknown> }>
}

function buildFormData(
  poFile: File,
  scheduleFile: File,
  receivedDate: string,
  factoryId: string,
) {
  const payload = new FormData()
  payload.append('factory_id', factoryId)
  payload.append('received_date', receivedDate)
  payload.append('po_file', poFile)
  payload.append('schedule_file', scheduleFile)
  return payload
}

function buildBatchFormData(
  poFiles: File[],
  scheduleFile: File,
  receivedDate: string,
  factoryId: string,
) {
  const payload = new FormData()
  payload.append('factory_id', factoryId)
  payload.append('received_date', receivedDate)
  poFiles.forEach((poFile) => payload.append('po_files', poFile))
  payload.append('schedule_file', scheduleFile)
  return payload
}

function responseFileName(headers: Record<string, unknown> | undefined, fallback: string) {
  const disposition = String(headers?.['content-disposition'] ?? '')
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  if (!encoded) return fallback
  try {
    return decodeURIComponent(encoded)
  } catch {
    return fallback
  }
}

export function createCustomerOrderApi(client: CustomerOrderHttpClient = http) {
  return {
    async previewBuzzbee(
      poFile: File,
      scheduleFile: File,
      receivedDate: string,
      factoryId = 'huaxing',
    ) {
      const response = await client.post<CustomerOrderImportPreview>(
        '/customer-orders/buzzbee/preview',
        buildFormData(poFile, scheduleFile, receivedDate, factoryId),
        { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 60_000 },
      )
      return response.data
    },
    async exportBuzzbee(
      poFile: File,
      scheduleFile: File,
      receivedDate: string,
      fallbackFileName: string,
      factoryId = 'huaxing',
      skippedIssueKeys: string[] = [],
    ) {
      const payload = buildFormData(poFile, scheduleFile, receivedDate, factoryId)
      payload.append('confirmed', 'true')
      payload.append('skipped_issue_keys', JSON.stringify(skippedIssueKeys))
      const response = await client.post<Blob>(
        '/customer-orders/buzzbee/export',
        payload,
        {
          headers: { 'Content-Type': 'multipart/form-data' },
          responseType: 'blob',
          timeout: 120_000,
        },
      )
      return {
        blob: response.data,
        fileName: responseFileName(response.headers, fallbackFileName),
      }
    },
    async previewBuzzbeeBatch(
      poFiles: File[],
      scheduleFile: File,
      receivedDate: string,
      factoryId = 'huaxing',
    ) {
      const response = await client.post<CustomerOrderImportPreview>(
        '/customer-orders/buzzbee/preview-batch',
        buildBatchFormData(poFiles, scheduleFile, receivedDate, factoryId),
        { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120_000 },
      )
      return response.data
    },
    async exportBuzzbeeBatch(
      poFiles: File[],
      scheduleFile: File,
      receivedDate: string,
      fallbackFileName: string,
      factoryId = 'huaxing',
      skippedIssueKeys: string[] = [],
    ) {
      const payload = buildBatchFormData(poFiles, scheduleFile, receivedDate, factoryId)
      payload.append('confirmed', 'true')
      payload.append('skipped_issue_keys', JSON.stringify(skippedIssueKeys))
      const response = await client.post<Blob>(
        '/customer-orders/buzzbee/export-batch',
        payload,
        {
          headers: { 'Content-Type': 'multipart/form-data' },
          responseType: 'blob',
          timeout: 180_000,
        },
      )
      return {
        blob: response.data,
        fileName: responseFileName(response.headers, fallbackFileName),
      }
    },
  }
}

export const customerOrderApi = createCustomerOrderApi()
