import axios from 'axios'
import { http } from '@/lib/http'
import type {
  CustomerOrderImportPreview,
  CustomerOrderManualOverride,
} from '@/types/customerOrder'

export interface CustomerOrderHttpClient {
  post<T = unknown>(
    url: string,
    data?: unknown,
    config?: unknown,
  ): Promise<{ data: T; headers?: Record<string, unknown> }>
}

export type HuaxingMappedCustomerCode =
  | 'disney'
  | 'edu'
  | '360'
  | 'yinhui'
  | 'seasons'
  | 'maxx'
  | 'shushupapa'
  | 'barter'

export type HuadengMappedCustomerCode =
  | 'casdon'
  | 'jakks'
  | 'simba'
  | 'spin'
  | 'spin-master'

export type HuakangAMappedCustomerCode =
  | '360'
  | 'green-toys'
  | 'headstart'

export type HuakangCMappedCustomerCode =
  | 'index'
  | 'jazwares'
  | 'maxx'
  | 'strottman'
  | 'jp'

export type MappedCustomerCode =
  | HuaxingMappedCustomerCode
  | HuadengMappedCustomerCode
  | HuakangAMappedCustomerCode
  | HuakangCMappedCustomerCode

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

function appendExportControls(
  payload: FormData,
  skippedIssueKeys: string[],
  previewFingerprint: string,
  confirmationReason: string,
  manualOverrides: CustomerOrderManualOverride[],
) {
  payload.append('confirmed', 'true')
  payload.append('skipped_issue_keys', JSON.stringify(skippedIssueKeys))
  payload.append('preview_fingerprint', previewFingerprint)
  payload.append('confirmation_reason', confirmationReason)
  payload.append('manual_overrides', JSON.stringify(manualOverrides))
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

function responsePasswordRequired(headers: Record<string, unknown> | undefined) {
  return String(headers?.['x-workbook-password-required'] ?? '').toLowerCase() === 'true'
}

async function postCustomerOrderBlob(
  client: CustomerOrderHttpClient,
  url: string,
  payload: FormData,
  timeout: number,
) {
  try {
    return await client.post<Blob>(url, payload, {
      headers: { 'Content-Type': 'multipart/form-data' },
      responseType: 'blob',
      timeout,
    })
  } catch (error) {
    if (!axios.isAxiosError(error) || !(error.response?.data instanceof Blob)) {
      throw error
    }
    const raw = await error.response.data.text()
    try {
      const payload = JSON.parse(raw) as { detail?: unknown; message?: unknown }
      const message = typeof payload.detail === 'string'
        ? payload.detail
        : typeof payload.message === 'string' ? payload.message : ''
      if (message) throw new Error(message)
    } catch (parseError) {
      if (parseError instanceof SyntaxError) {
        throw new Error(raw.trim() || error.message)
      }
      throw parseError
    }
    throw error
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
      previewFingerprint = '',
      confirmationReason = '',
      manualOverrides: CustomerOrderManualOverride[] = [],
    ) {
      const payload = buildFormData(poFile, scheduleFile, receivedDate, factoryId)
      appendExportControls(payload, skippedIssueKeys, previewFingerprint, confirmationReason, manualOverrides)
      const response = await postCustomerOrderBlob(
        client, '/customer-orders/buzzbee/export', payload, 120_000,
      )
      return {
        blob: response.data,
        fileName: responseFileName(response.headers, fallbackFileName),
        passwordRequired: responsePasswordRequired(response.headers),
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
      previewFingerprint = '',
      confirmationReason = '',
      manualOverrides: CustomerOrderManualOverride[] = [],
    ) {
      const payload = buildBatchFormData(poFiles, scheduleFile, receivedDate, factoryId)
      appendExportControls(payload, skippedIssueKeys, previewFingerprint, confirmationReason, manualOverrides)
      const response = await postCustomerOrderBlob(
        client, '/customer-orders/buzzbee/export-batch', payload, 180_000,
      )
      return {
        blob: response.data,
        fileName: responseFileName(response.headers, fallbackFileName),
        passwordRequired: responsePasswordRequired(response.headers),
      }
    },
    async previewDickieBatch(
      poFiles: File[],
      scheduleFile: File,
      receivedDate: string,
      factoryId = 'huaxing',
    ) {
      const response = await client.post<CustomerOrderImportPreview>(
        '/customer-orders/dickie/preview-batch',
        buildBatchFormData(poFiles, scheduleFile, receivedDate, factoryId),
        { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 180_000 },
      )
      return response.data
    },
    async exportDickieBatch(
      poFiles: File[],
      scheduleFile: File,
      receivedDate: string,
      fallbackFileName: string,
      factoryId = 'huaxing',
      skippedIssueKeys: string[] = [],
      previewFingerprint = '',
      confirmationReason = '',
      manualOverrides: CustomerOrderManualOverride[] = [],
    ) {
      const payload = buildBatchFormData(poFiles, scheduleFile, receivedDate, factoryId)
      appendExportControls(payload, skippedIssueKeys, previewFingerprint, confirmationReason, manualOverrides)
      const response = await postCustomerOrderBlob(
        client, '/customer-orders/dickie/export-batch', payload, 240_000,
      )
      return {
        blob: response.data,
        fileName: responseFileName(response.headers, fallbackFileName),
        passwordRequired: responsePasswordRequired(response.headers),
      }
    },
    async previewCaixingBatch(
      poFiles: File[],
      scheduleFile: File,
      receivedDate: string,
      factoryId = 'huaxing',
    ) {
      const response = await client.post<CustomerOrderImportPreview>(
        '/customer-orders/caixing/preview-batch',
        buildBatchFormData(poFiles, scheduleFile, receivedDate, factoryId),
        { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 180_000 },
      )
      return response.data
    },
    async exportCaixingBatch(
      poFiles: File[],
      scheduleFile: File,
      receivedDate: string,
      fallbackFileName: string,
      factoryId = 'huaxing',
      skippedIssueKeys: string[] = [],
      previewFingerprint = '',
      confirmationReason = '',
      manualOverrides: CustomerOrderManualOverride[] = [],
    ) {
      const payload = buildBatchFormData(poFiles, scheduleFile, receivedDate, factoryId)
      appendExportControls(payload, skippedIssueKeys, previewFingerprint, confirmationReason, manualOverrides)
      const response = await postCustomerOrderBlob(
        client, '/customer-orders/caixing/export-batch', payload, 240_000,
      )
      return {
        blob: response.data,
        fileName: responseFileName(response.headers, fallbackFileName),
        passwordRequired: responsePasswordRequired(response.headers),
      }
    },
    async previewHuaxingMappedBatch(
      customerCode: MappedCustomerCode,
      poFiles: File[],
      scheduleFile: File,
      receivedDate: string,
      factoryId = 'huaxing',
    ) {
      const response = await client.post<CustomerOrderImportPreview>(
        `/customer-orders/${customerCode}/preview-batch`,
        buildBatchFormData(poFiles, scheduleFile, receivedDate, factoryId),
        { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 240_000 },
      )
      return response.data
    },
    async exportHuaxingMappedBatch(
      customerCode: MappedCustomerCode,
      poFiles: File[],
      scheduleFile: File,
      receivedDate: string,
      fallbackFileName: string,
      factoryId = 'huaxing',
      skippedIssueKeys: string[] = [],
      previewFingerprint = '',
      confirmationReason = '',
      manualOverrides: CustomerOrderManualOverride[] = [],
    ) {
      const payload = buildBatchFormData(poFiles, scheduleFile, receivedDate, factoryId)
      appendExportControls(payload, skippedIssueKeys, previewFingerprint, confirmationReason, manualOverrides)
      const response = await postCustomerOrderBlob(
        client, `/customer-orders/${customerCode}/export-batch`, payload, 300_000,
      )
      return {
        blob: response.data,
        fileName: responseFileName(response.headers, fallbackFileName),
        passwordRequired: responsePasswordRequired(response.headers),
      }
    },
    async previewMappedBatch(
      customerCode: MappedCustomerCode,
      poFiles: File[],
      scheduleFile: File,
      receivedDate: string,
      factoryId: string,
    ) {
      const response = await client.post<CustomerOrderImportPreview>(
        `/customer-orders/${customerCode}/preview-batch`,
        buildBatchFormData(poFiles, scheduleFile, receivedDate, factoryId),
        { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 240_000 },
      )
      return response.data
    },
    async exportMappedBatch(
      customerCode: MappedCustomerCode,
      poFiles: File[],
      scheduleFile: File,
      receivedDate: string,
      fallbackFileName: string,
      factoryId: string,
      skippedIssueKeys: string[] = [],
      previewFingerprint = '',
      confirmationReason = '',
      manualOverrides: CustomerOrderManualOverride[] = [],
    ) {
      const payload = buildBatchFormData(poFiles, scheduleFile, receivedDate, factoryId)
      appendExportControls(payload, skippedIssueKeys, previewFingerprint, confirmationReason, manualOverrides)
      const response = await postCustomerOrderBlob(
        client, `/customer-orders/${customerCode}/export-batch`, payload, 300_000,
      )
      return {
        blob: response.data,
        fileName: responseFileName(response.headers, fallbackFileName),
        passwordRequired: responsePasswordRequired(response.headers),
      }
    },
  }
}

export const customerOrderApi = createCustomerOrderApi()
