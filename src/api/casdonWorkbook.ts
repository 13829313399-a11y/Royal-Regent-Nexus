import { http } from '@/lib/http'

export interface CasdonWorkbookRow {
  id: string; row: number; section: 'active' | 'shipped'
  contract: string; reference: string; product: string; customer: string; quantity: string
}
export interface CasdonWorkbookPreview {
  factory_id: 'huadeng'; customer_code: 'casdon'; fingerprint: string; rows: CasdonWorkbookRow[]
}
export type CasdonWorkbookAction = 'prepare' | 'ship' | 'restore'
const base = '/customer-order-ledger/schedule/casdon'
const config = { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 300_000 }
export const casdonWorkbookApi = {
  async preview(factory: string, file: File) {
    const data = new FormData(); data.append('schedule_file', file)
    return (await http.post<CasdonWorkbookPreview>(`${base}/preview?factory_id=${encodeURIComponent(factory)}`, data, config)).data
  },
  async export(factory: string, file: File, fingerprint: string, action: CasdonWorkbookAction, ids: string[], reason: string) {
    const data = new FormData()
    data.append('schedule_file', file); data.append('fingerprint', fingerprint); data.append('action', action)
    data.append('selections', JSON.stringify(ids)); data.append('reason', reason); data.append('confirmed', String(action !== 'prepare'))
    const response = await http.post<Blob>(`${base}/export?factory_id=${encodeURIComponent(factory)}`, data, { ...config, responseType: 'blob' })
    let name = 'Casdon整理.xlsx'
    const encoded = String(response.headers['content-disposition'] ?? '').match(/filename\*=UTF-8''([^;]+)/i)?.[1]
    if (encoded) { try { name = decodeURIComponent(encoded).replace(/[\\/]/g, '_') } catch { /* safe fallback */ } }
    let warningCount = 0
    try {
      const report = JSON.parse(decodeURIComponent(String(response.headers['x-casdon-report'] ?? '')))
      if (Number.isSafeInteger(report.warning_count) && report.warning_count >= 0) warningCount = report.warning_count
    } catch { /* Optional summary cannot prevent download. */ }
    return { blob: response.data, name, auditId: String(response.headers['x-export-audit-id'] ?? ''), warningCount }
  },
}
