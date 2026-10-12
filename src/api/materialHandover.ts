import axios from 'axios'
import { http } from '@/lib/http'
import type { WarehouseOperationsWorkspace } from './warehouseOperations'
import type { MasterRecord } from './fabricMaster'

export const HANDOVER_FACTORY = 'huakang-c' as const
export interface HandoverLine {
  id: string; source_line: string; item_code: string; item_name: string; specification: string; color: string
  quantity: string; unit: string; material_category: 'FABRIC' | 'ACCESSORY' | 'THREAD'; lot: string; roll_no: string
  roll_quantities: string; contract_no: string; production_no: string; product_no: string; note: string
  unit_price?: string; price_unit?: string; currency?: '' | 'CNY' | 'HKD' | 'USD' | 'EUR'; price_note?: string
}
export interface HandoverData {
  kind: 'DELIVERY' | 'ISSUE'; source_no: string; document_date: string | null; counterparty: string
  contract_no: string; production_no: string; product_no: string; note: string; lines: HandoverLine[]
  supplier_id?: string
}
export interface HandoverDocument {
  id: string; factory_id: string; issuer_id: string | null; status: 'DRAFT' | 'CONFIRMED' | 'VOID'; revision: number
  code_version: number; code: string; data: HandoverData; warnings: string[]; evidence: Record<string, unknown>
  engine: string; raw_text: string; file_name: string; source_sha256: string; confirmed_at: string; created_at: string
  progress: Record<string, { processed: string; remaining: string }>; processing_status: 'PENDING' | 'PARTIAL' | 'COMPLETE'
  movements: { operation_id: string; line_id: string; quantity: string; business_date: string; reversed: boolean }[]
}
export interface HandoverSummary { id: string; status: HandoverDocument['status']; revision: number; data: Omit<HandoverData, 'lines'>; line_count: number; created_at: string }
export interface HandoverIssuer { id: string; name: string; kind: 'SUPPLIER' | 'REQUESTOR'; active: number; revision: number; expires_at: string; created_at: string; token?: string; supplier_id?: string; supplier_code?: string; replayed?: boolean }
export interface HandoverWorkspace { factory_id: string; inventory: WarehouseOperationsWorkspace; can_operate: boolean; can_manage: boolean; materials: { id: string; code: string; name: string }[]; suppliers?: MasterRecord[] }
export interface HandoverPosting { factory_id: 'huakang-c'; request_id: string; expected_revision: number; expected_inventory_revision: number; code_version: number; business_date: string; lines: { line_id: string; quantity: string; batch_id: string; location_id: string; lot: string; roll_no: string }[] }
export interface HandoverSave { request_id: string; expected_revision: number; data: HandoverData }
export interface HandoverAction { request_id: string; expected_revision: number; acknowledge_warnings: boolean; reason: string; data?: HandoverData }
export interface HandoverMonthlyRow { document_id: string; line_id: string; source_no: string; document_date: string; supplier_id: string; supplier_name: string; item_code: string; item_name: string; unit: string; declared: string; prior_received: string; month_received: string; month_reversed: string; month_net_received: string; cumulative_received: string; outstanding: string; unit_price: string; price_unit: string; currency: string; price_note: string; notes: string[] }
export interface HandoverMonthly { month: string; basis: string; version: string; closed: false; amounts_calculated: false; live: true; details: HandoverMonthlyRow[]; summary: { supplier_id: string; supplier_name: string; item_code: string; item_name: string; unit: string; month_received: string; month_reversed: string; month_net_received: string; outstanding: string; document_count: number }[]; totals: { unit: string; month_received: string; month_reversed: string; month_net_received: string }[]; unlinked_receipts: { id: string; source_no: string; date: string; counterparty: string; item_code: string; quantity: string; unit: string; reason: string }[] }
export interface HandoverLinkInput { request_id: string; name: string; kind: HandoverIssuer['kind']; supplier_id: string; valid_days: number }
export interface HandoverLinkAction { request_id: string; expected_revision: number; valid_days?: number; supplier_id?: string }

export function handoverApi(key = '') {
  const external = Boolean(key)
  const client = external ? axios.create({ baseURL: '/api/material-handover/external', withCredentials: false, headers: { 'X-Handover-Key': key }, timeout: 240_000 }) : http
  const base = external ? '' : '/material-handover'
  const config = external ? {} : { params: { factory_id: HANDOVER_FACTORY } }
  return {
    async context() { return (await client.get<HandoverIssuer>(base + '/context')).data },
    async workspace() { return (await http.get<HandoverWorkspace>('/material-handover/workspace', config)).data },
    async list(offset = 0) { return (await client.get<{ items: HandoverSummary[]; limit: number; offset: number }>(base + '/documents', { ...config, params: { ...(external ? {} : { factory_id: HANDOVER_FACTORY }), limit: 50, offset } })).data },
    async detail(id: string) { return (await client.get<HandoverDocument>(base + '/documents/' + encodeURIComponent(id), config)).data },
    async upload(file: File, requestId: string) {
      const body = new FormData(); body.append('file', file); body.append('request_id', requestId)
      if (!external) body.append('factory_id', HANDOVER_FACTORY)
      return (await client.post<HandoverDocument>(base + '/documents/upload', body, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 240_000 })).data
    },
    async save(id: string, body: HandoverSave) { return (await client.put<HandoverDocument>(base + '/documents/' + encodeURIComponent(id), body, config)).data },
    async action(id: string, action: 'confirm' | 'void', body: HandoverAction) { return (await client.post<HandoverDocument>(base + '/documents/' + encodeURIComponent(id) + (external ? '/' : '/actions/') + action, body, config)).data },
    async file(id: string, kind: 'source' | 'qr') { return (await client.get<Blob>(base + '/documents/' + encodeURIComponent(id) + '/' + kind, { ...config, responseType: 'blob' })).data },
    async printFile(id: string, expected_revision: number, corner: 'left' | 'right') { return (await client.get<Blob>(base + '/documents/' + encodeURIComponent(id) + '/print', { ...config, params: { ...(external ? {} : { factory_id: HANDOVER_FACTORY }), expected_revision, corner }, responseType: 'blob', timeout: 240_000 })).data },
    async scan(code: string) { return (await http.post<HandoverDocument>('/material-handover/scan', { factory_id: HANDOVER_FACTORY, code })).data },
    async post(id: string, body: HandoverPosting) { return (await http.post<HandoverDocument>('/material-handover/documents/' + encodeURIComponent(id) + '/post', body)).data },
    async issuers() { return (await http.get<HandoverIssuer[]>('/material-handover/issuers', config)).data },
    async createIssuer(body: HandoverLinkInput) { return (await http.post<HandoverIssuer>('/material-handover/issuers', { factory_id: HANDOVER_FACTORY, ...body })).data },
    async linkAction(id: string, action: 'renew' | 'bind' | 'revoke', body: HandoverLinkAction) { return (await http.post<HandoverIssuer>('/material-handover/issuers/' + id + '/' + action, { factory_id: HANDOVER_FACTORY, ...body })).data },
    async monthly(month: string, supplier_id = '') { return (await client.get<HandoverMonthly>(base + '/monthly', { ...config, params: { ...(external ? {} : { factory_id: HANDOVER_FACTORY }), month, supplier_id } })).data },
    async exportMonthly(month: string, supplier_id = '') { return (await client.get<Blob>(base + '/monthly/export', { responseType: 'blob', params: { ...(external ? {} : { factory_id: HANDOVER_FACTORY }), month, supplier_id } })).data },
  }
}
