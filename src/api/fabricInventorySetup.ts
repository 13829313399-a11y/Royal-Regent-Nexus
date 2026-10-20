import { http } from '@/lib/http'
import type { WarehouseBatch, WarehouseOperationsWorkspace } from './warehouseOperations'

export interface OpeningRow {
  style_no?: string; customer_name?: string; material_detail?: string
  row_number: number; source_line: string; item_code: string; item_name: string; material_category: string
  unit: string; location: string; warehouse: string; location_code: string; lot: string; roll_no: string
  quantity: string; counterparty: string; reason: string; action: 'NEW' | 'SKIP' | 'ERROR'; errors: string[]
}
export interface OpeningPreview { filename: string; rows: OpeningRow[]; token: string; totals: Record<string,string>; new_count: number; skip_count: number; error_count: number }
export interface OpeningRecord { id: string; business_date: string; source_no: string; filename: string; actor_name: string; posted_count: number; skipped_count: number; totals: Record<string,string>; rows: OpeningRow[] }
export interface CountLine { batch_id: string; snapshot: WarehouseBatch; actual: string; reason: string; difference?: string }
export interface CountDocument { id: string; revision: number; status: 'DRAFT' | 'POSTED' | 'CANCELLED'; actor_name: string; business_date: string; posted_on?: string; reason: string; lines: CountLine[]; stale?: boolean; changed_batch_ids?: string[]; legacy_scope?: boolean; events: { action: string; actor_name: string; at: string; reason?: string }[] }
export interface SetupWorkspace { openings: OpeningRecord[]; counts: CountDocument[]; permissions: WarehouseOperationsWorkspace['permissions'] }
export interface CountCreate { factory_id: 'huakang-c'; request_id: string; batch_ids: string[]; reason: string }
export interface CountAction { factory_id: 'huakang-c'; request_id: string; expected_revision: number; action: 'SAVE' | 'REFRESH' | 'POST' | 'CANCEL'; business_date: string; confirmed: boolean; reason: string; lines: {batch_id:string; actual:string; reason:string}[] }
const base = '/warehouse-operations/fabric/inventory-setup'
export const fabricInventorySetupApi = {
  async workspace() { return (await http.get<SetupWorkspace>(base, { params: {factory_id:'huakang-c'} })).data },
  async template() { return (await http.get<Blob>(`${base}/template`, {params:{factory_id:'huakang-c'},responseType:'blob'})).data },
  async preview(input:FormData) { return (await http.post<OpeningPreview>(`${base}/preview`,input)).data },
  async apply(input:FormData) { return (await http.post<OpeningRecord>(`${base}/import`,input)).data },
  async create(input:CountCreate) { return (await http.post<CountDocument>(`${base}/counts`,input)).data },
  async act(id:string,input:CountAction) { return (await http.post<CountDocument>(`${base}/counts/${encodeURIComponent(id)}`,input)).data },
}
