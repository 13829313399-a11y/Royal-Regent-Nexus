import axios from 'axios'
import type { CustomerOrderImportPreview } from '@/types/customerOrder'
export interface CustomerProfile { code: string; name: string; po_extensions: string[]; schedule_extensions: string[] }
export interface TrialConfig { factory_id: string; factory_name: string; customers: CustomerProfile[]; scope: string; capabilities?: { history_import?: boolean; ledger_schedule?: boolean; workbook_tools?: boolean };
  limits: { po_files: number; po_bytes: number; batch_po_bytes: number; schedule_bytes: number } }
export interface ExportRecord { id: string; customer_code: string; file_name: string; created_at: string; row_count: number; output_sha256: string }
export interface DownloadResult { blob: Blob; fileName: string; exportId: string; passwordRequired: boolean }
export const http = axios.create({ baseURL: '/api', timeout: 15_000, withCredentials: false, headers: { 'X-Order-Trial': '1' } })
const files = { timeout: 300_000, headers: { 'X-Order-Trial': '1' } }
function downloadResult(response: { data: Blob; headers: Record<string, unknown> }): DownloadResult {
  const disposition = String(response.headers['content-disposition'] ?? '')
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition)?.[1]
  let name = '客户排期.xlsx'
  if (encoded) { try { name = decodeURIComponent(encoded) } catch { /* Keep a usable fallback filename. */ } }
  return { blob: response.data, fileName: name.replace(/[\\/\u0000-\u001f]/g, '_'),
    exportId: String(response.headers['x-export-id'] ?? ''), passwordRequired: response.headers['x-workbook-password-required'] === 'true' }
}
export const api = {
  async config(signal?: AbortSignal) { return (await http.get<TrialConfig>('/config', { signal })).data },
  async preview(body: FormData, signal?: AbortSignal) { return (await http.post<CustomerOrderImportPreview>('/orders/preview', body, { ...files, signal })).data },
  async export(body: FormData, signal?: AbortSignal) { return downloadResult(await http.post<Blob>('/orders/export', body, { ...files, signal, responseType: 'blob' })) },
  async history(page: number, signal?: AbortSignal) { return (await http.get<{ total: number; items: ExportRecord[] }>('/orders/exports', { params: { page }, signal })).data },
  async download(id: string, signal?: AbortSignal) { return downloadResult(await http.get<Blob>(`/orders/exports/${encodeURIComponent(id)}/download`, { signal, responseType: 'blob' })) },
}
export async function errorMessage(error: unknown): Promise<string> {
  if (axios.isAxiosError(error)) {
    let payload: unknown = error.response?.data
    if (payload instanceof Blob) { try { payload = JSON.parse(await payload.text()) } catch { payload = null } }
    if (payload && typeof payload === 'object') {
      const detail = (payload as { detail?: unknown }).detail
      if (typeof detail === 'string') return detail
      if (Array.isArray(detail)) return detail.map(value => typeof value?.msg === 'string' ? value.msg : '').filter(Boolean).join('；') || '提交信息未通过校验，请核对文件与填写内容。'
    }
    if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT' || (error.response?.status ?? 0) >= 500) return '未收到完整处理结果，请先核对本机台账与排期文件历史，再决定是否重新提交。'
    if (!error.response) return '无法连接本机服务，请确认启动窗口仍在运行，再重新加载。'
    return `操作未完成，请核对后重试（HTTP ${error.response.status}）。`
  }
  return error instanceof Error ? error.message : '操作未完成，请检查输入后重试。'
}

// Original ledger UI uses this synchronous adapter for JSON errors.
export function getApiErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return detail.map(item => item?.msg || '').filter(Boolean).join('；')
    if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT' || (error.response?.status ?? 0) >= 500) return '未收到完整处理结果，请先刷新本机台账和记录核对，不要连续重复提交。'
    if (!error.response) return '无法连接本机服务，请确认启动窗口仍在运行。'
  }
  return error instanceof Error ? error.message : '操作未完成，请重试。'
}
export const getApiErrorMessageAsync = errorMessage
export type Recipient = 'pmc' | 'warehouse' | 'injection'
export interface InboxItem { id: string; line_id: string; factory_id: string; recipient: Recipient; version: number; latest_version: number; snapshot: Record<string, unknown>; actor: string; created_at: string; received_at: string | null; received_by: string | null; status: 'sent' | 'received' }
export const inboxApi = {
  async list(factoryId: string, recipient: Recipient, page: number) { return (await http.get<{ items: InboxItem[]; total: number }>('/customer-order-ledger/inbox', { params: { factory_id: factoryId, recipient, page, page_size: 50 } })).data },
  async receive(factoryId: string, recipient: Recipient, id: string) { return (await http.post<InboxItem>(`/customer-order-ledger/inbox/${encodeURIComponent(id)}/receive`, null, { params: { factory_id: factoryId, recipient } })).data },
}
