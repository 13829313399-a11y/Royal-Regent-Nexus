import { http } from '@/lib/http'

export type Data = Record<string, any>
export type RecordKind = 'option' | 'customer' | 'material' | 'product' | 'order' | 'supply' | 'allocation' | 'shipment' | 'import'
export interface MaterialRecord { id: string; kind: RecordKind; version: number; data: Data; scope?: 'shared-options' }
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
export interface WorkspaceResponse { records: MaterialRecord[]; board: BoardOrder[]; permissions: string[]; option_defaults?: Data[] }
export type Action = 'option_save' | 'option_delete' | 'option_restore' | 'customer_delete' | 'customer_restore' | 'product_delete' | 'product_restore' | 'material_restore' | 'customer_save' | 'material_save' | 'product_save' | 'order_save' | 'order_plan_save' | 'order_recalculate' | 'demand_adjust'
  | 'supply_save' | 'supply_reply' | 'output_material_refresh' | 'receipt_confirm' | 'allocate' | 'reallocate'
  | 'shipment_save' | 'shipment_confirm' | 'import_confirm' | 'warehouse_import_confirm'
export interface Command {
  factory_id: string; operation_id: string; action: Action; entity_id: string | null
  expected_version: number; data: Data
}
export interface ReceiptTemplateRequest {
  factory_id: string; customer: string; recipient: string; warehouse: string
  selections: { order_id: string; demand_id: string }[]
}

export const indonesiaMaterialsApi = {
  async workspace(factory: string): Promise<WorkspaceResponse> {
    if (factory === 'shared-options') return (await http.get('/indonesia-materials/shared-options')).data
    return (await http.get('/indonesia-materials/workspace', { params: { factory_id: factory } })).data
  },
  async command(command: Command): Promise<{ record: MaterialRecord }> {
    return (await http.post(command.factory_id === 'shared-options' ? '/indonesia-materials/shared-options/commands' : '/indonesia-materials/commands', command)).data
  },
  async preview(factory: string, customer: string, recipient: string, file: File, warehouse?: string): Promise<{ record: MaterialRecord }> {
    const data = new FormData()
    data.append('factory_id', factory)
    data.append('customer', customer)
    data.append('recipient', recipient)
    data.append('file', file)
    if (warehouse !== undefined) data.append('warehouse', warehouse)
    return (await http.post(warehouse === undefined ? '/indonesia-materials/imports/preview' : '/indonesia-materials/warehouse-imports/preview', data, {
      headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120_000,
    })).data
  },
  async warehouseTemplate(request: ReceiptTemplateRequest) {
    try {
      return (await http.post('/indonesia-materials/warehouse-imports/template', request, { responseType: 'blob', timeout: 120_000 })).data as Blob
    } catch (cause) {
      const response = (cause as { response?: { data: unknown } }).response
      if (response?.data instanceof Blob) {
        try { response.data = JSON.parse(await response.data.text()) } catch { /* Keep the original download error. */ }
      }
      throw cause
    }
  },
  async download(factory: string, id: string, kind: 'shipment' | 'asset') {
    const path = kind === 'shipment' ? `shipments/${encodeURIComponent(id)}/export` : `assets/${encodeURIComponent(id)}`
    return (await http.get(`/indonesia-materials/${path}`, { params: { factory_id: factory }, responseType: 'blob', timeout: 120_000 })).data as Blob
  },
}
