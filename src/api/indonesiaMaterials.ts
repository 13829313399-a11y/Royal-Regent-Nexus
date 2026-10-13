import { http } from '@/lib/http'

export type Data = Record<string, any>
export type RecordKind = 'material' | 'product' | 'order' | 'supply' | 'allocation' | 'shipment' | 'import'
export interface MaterialRecord { id: string; kind: RecordKind; version: number; data: Data }
export interface Demand {
  id: string; material_id: string; code: string; name: string; unit: string
  computed_quantity: string; quantity: string; procurement_days: number | null
  purchase_start: string | null; coverage: string; shortage: string; allocated: string; shipped: string
  promised_date: string | null; risk: string | boolean
  actual_date?: string | null
}
export interface BoardOrder {
  id: string; customer: string; recipient: string; contract_no: string; po_no: string; item_no: string
  batch: string; quantity: string; unit: string; delivery_date: string
  plan: { production_days: number; start_date: string; dispatch_date: string; required_date: string; transport_days: number; preparation_days: number } | null
  demands: Demand[]; status: 'missing_master' | 'missing_parameters' | 'shortage' | 'complete'
  planning_status?: 'ready' | 'missing_master' | 'missing_parameters'
}
export interface WorkspaceResponse { records: MaterialRecord[]; board: BoardOrder[]; permissions: string[] }
export type Action = 'material_save' | 'product_save' | 'order_save' | 'order_recalculate' | 'demand_adjust'
  | 'supply_save' | 'supply_reply' | 'output_material_refresh' | 'receipt_confirm' | 'allocate' | 'reallocate'
  | 'shipment_save' | 'shipment_confirm' | 'import_confirm'
export interface Command {
  factory_id: string; operation_id: string; action: Action; entity_id: string | null
  expected_version: number; data: Data
}

export const indonesiaMaterialsApi = {
  async workspace(factory: string): Promise<WorkspaceResponse> {
    return (await http.get('/indonesia-materials/workspace', { params: { factory_id: factory } })).data
  },
  async command(command: Command): Promise<{ record: MaterialRecord }> {
    return (await http.post('/indonesia-materials/commands', command)).data
  },
  async preview(factory: string, customer: string, recipient: string, file: File): Promise<{ record: MaterialRecord }> {
    const data = new FormData()
    data.append('factory_id', factory)
    data.append('customer', customer)
    data.append('recipient', recipient)
    data.append('file', file)
    return (await http.post('/indonesia-materials/imports/preview', data, {
      headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120_000,
    })).data
  },
  async download(factory: string, id: string, kind: 'shipment' | 'asset') {
    const path = kind === 'shipment' ? `shipments/${encodeURIComponent(id)}/export` : `assets/${encodeURIComponent(id)}`
    return (await http.get(`/indonesia-materials/${path}`, { params: { factory_id: factory }, responseType: 'blob', timeout: 120_000 })).data as Blob
  },
}
