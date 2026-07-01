import { http } from '../lib/http.js'
import type {
  MoldingSampleAuditLog,
  MoldingSampleItem,
  MoldingSampleOrder,
  MoldingSampleRole,
} from '../types/moldingSample.js'
import type { MoldingSampleMaterialPrice } from '../lib/moldingSampleBusiness.js'

export interface HttpLikeClient {
  get<T = unknown>(url: string, config?: unknown): Promise<{ data: T }>
  post<T = unknown>(url: string, data?: unknown, config?: unknown): Promise<{ data: T }>
  put<T = unknown>(url: string, data?: unknown): Promise<{ data: T }>
  patch<T = unknown>(url: string, data?: unknown): Promise<{ data: T }>
  delete<T = unknown>(url: string): Promise<{ data: T }>
}

export const MOLDING_SAMPLE_XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

export type MoldingSampleOrderDraft = Partial<MoldingSampleOrder>
  & Pick<MoldingSampleOrder, 'id' | 'product_name' | 'client_name' | 'date' | 'workshop' | 'supervisor' | 'eng_name'>

export type MoldingSampleItemDraft = Partial<MoldingSampleItem> & Pick<MoldingSampleItem, 'id'>

export interface MoldingSampleCreateRequest {
  order: MoldingSampleOrderDraft
  items: MoldingSampleItemDraft[]
}

export interface MoldingSampleEditRequest extends MoldingSampleCreateRequest {
  actor_name: string
  actor_role: MoldingSampleRole
  pin?: string
}

export interface MoldingSampleDeleteRequest {
  actor_name: string
  actor_role: MoldingSampleRole
  pin?: string
}

export interface MoldingSampleExcelImportOptions {
  order_id?: string
}

export interface MoldingSampleDetailResponse {
  order: MoldingSampleOrder
  items: MoldingSampleItem[]
  audit_logs: MoldingSampleAuditLog[]
}

export interface MoldingSampleStatusRequest {
  action: string
  reviewer_name: string
  reviewer_role: MoldingSampleRole
  pin?: string
  reason?: string
  today?: string
}

export interface MoldingSampleItemsPatchRequest {
  items: MoldingSampleItemDraft[]
}

export interface MaterialPricesResponse {
  prices: MoldingSampleMaterialPrice[]
  rmb_to_hkd_rate: number
}

export interface MaterialPricesUpdateRequest extends MaterialPricesResponse {
  manager_name?: string
  manager_pin?: string
}

export interface PinVerifyRequest {
  name: string
  role: MoldingSampleRole
  pin: string
}

export interface PinChangeRequest {
  name: string
  role: MoldingSampleRole
  old_pin: string
  new_pin: string
}

export interface ResetSupervisorPinRequest {
  manager_name: string
  manager_pin: string
  supervisor_name: string
  new_pin?: string
}

export interface PinVerifyResponse {
  valid: boolean
  name: string
  role: MoldingSampleRole
  must_change: boolean
}

export interface RolesResponse {
  supervisors: Array<{ name: string, role: MoldingSampleRole, must_change: boolean }>
  managers: Array<{ name: string, role: MoldingSampleRole, must_change: boolean }>
}

export interface RequisitionCreateRequest {
  date: string
  order_id: string
  material: string
  requested_weight_kg: number
  applicant?: string
  notes?: string
}

export interface RequisitionStatusRequest {
  status: '待出库' | '已出库'
  issued_at?: string
  inventory_batch_id?: string
}

export interface RequisitionResponse {
  id: string
  req_number: string
  date: string
  order_id: string
  order_number: string
  material: string
  requested_weight_kg: number
  applicant: string
  notes: string
  inventory_batch_id: string
  inventory_batch_no: string
  status: '待出库' | '已出库'
  issued_at: string
  created_at: string
  updated_at: string
}

export interface InventoryBatchCreateRequest {
  material: string
  batch_no: string
  location?: string
  initial_weight_kg: number
}

export interface InventoryBatchResponse {
  id: string
  material: string
  batch_no: string
  location: string
  initial_weight_kg: number
  available_weight_kg: number
  created_at: string
  updated_at: string
}

export interface InventoryMovementFilters {
  batch_id?: string
  material?: string
  requisition_id?: string
}

export interface InventoryMovementResponse {
  id: number
  batch_id: string
  batch_no: string
  requisition_id: string
  req_number: string
  material: string
  movement_type: string
  quantity_kg: number
  before_weight_kg: number
  after_weight_kg: number
  actor_name: string
  reason: string
  created_at: string
}

export interface SensitiveAuditLogResponse {
  id: number
  action: string
  actor_name: string
  actor_role: string
  target_type: string
  target_name: string
  detail: string
  created_at: string
}

export interface InjectionTotalCostSummary {
  order_id: string
  order_number: string
  doc_number: string
  product_name: string
  client_name: string
  completed_date: string
  workshop: string
  send_to: string
  status: string
  total_material_cost: number
  total_injection_cost: number
  total_cost: number
  has_missing_price: boolean
  has_missing_injection_cost: boolean
  item_rows: Array<Record<string, unknown>>
}

export function createMoldingSampleApi(client: HttpLikeClient = http) {
  return {
    async listOrders() {
      const response = await client.get<MoldingSampleDetailResponse[]>('/injection')
      return response.data
    },
    async getOrder(orderId: string) {
      const response = await client.get<MoldingSampleDetailResponse>(`/injection/${orderId}`)
      return response.data
    },
    async getRoles() {
      const response = await client.get<RolesResponse>('/roles')
      return response.data
    },
    async createOrder(payload: MoldingSampleCreateRequest) {
      const response = await client.post<MoldingSampleDetailResponse>('/injection', payload)
      return response.data
    },
    async editOrder(orderId: string, payload: MoldingSampleEditRequest) {
      const response = await client.put<MoldingSampleDetailResponse>(`/injection/${orderId}`, payload)
      return response.data
    },
    async deleteOrder(orderId: string, payload: MoldingSampleDeleteRequest) {
      const params = new URLSearchParams({
        actor_name: payload.actor_name,
        actor_role: payload.actor_role,
      })
      if (payload.pin) {
        params.set('pin', payload.pin)
      }
      const response = await client.delete(`/injection/${orderId}?${params.toString()}`)
      return response.data
    },
    async exportOrderExcel(orderId: string) {
      const response = await client.get<ArrayBuffer>(`/injection/${orderId}/export-excel`, {
        responseType: 'arraybuffer',
      })
      return response.data
    },
    async importOrderExcel(workbook: ArrayBuffer, options: MoldingSampleExcelImportOptions = {}) {
      const params = new URLSearchParams()
      if (options.order_id) {
        params.set('order_id', options.order_id)
      }
      const query = params.toString()
      const response = await client.post<MoldingSampleDetailResponse>(
        query ? `/injection/import-excel?${query}` : '/injection/import-excel',
        workbook,
        {
          headers: {
            'content-type': MOLDING_SAMPLE_XLSX_MIME,
          },
        },
      )
      return response.data
    },
    async updateStatus(orderId: string, payload: MoldingSampleStatusRequest) {
      const response = await client.patch<MoldingSampleDetailResponse>(`/injection/${orderId}/status`, payload)
      return response.data
    },
    async updateItems(orderId: string, payload: MoldingSampleItemsPatchRequest) {
      const response = await client.patch<MoldingSampleDetailResponse>(`/injection/${orderId}/items`, payload)
      return response.data
    },
    async getMaterialPrices() {
      const response = await client.get<MaterialPricesResponse>('/material-prices')
      return response.data
    },
    async updateMaterialPrices(payload: MaterialPricesUpdateRequest) {
      const response = await client.post<MaterialPricesResponse>('/manager-update-prices', payload)
      return response.data
    },
    async listRequisitions(orderId?: string) {
      const url = orderId ? `/requisitions?${new URLSearchParams({ order_id: orderId }).toString()}` : '/requisitions'
      const response = await client.get<RequisitionResponse[]>(url)
      return response.data
    },
    async listInventoryBatches(material?: string) {
      const url = material ? `/inventory-batches?${new URLSearchParams({ material }).toString()}` : '/inventory-batches'
      const response = await client.get<InventoryBatchResponse[]>(url)
      return response.data
    },
    async listInventoryMovements(filters: InventoryMovementFilters = {}) {
      const params = new URLSearchParams()
      if (filters.batch_id) {
        params.set('batch_id', filters.batch_id)
      }
      if (filters.material) {
        params.set('material', filters.material)
      }
      if (filters.requisition_id) {
        params.set('requisition_id', filters.requisition_id)
      }
      const query = params.toString()
      const response = await client.get<InventoryMovementResponse[]>(query ? `/inventory-movements?${query}` : '/inventory-movements')
      return response.data
    },
    async createInventoryBatch(payload: InventoryBatchCreateRequest) {
      const response = await client.post<InventoryBatchResponse>('/inventory-batches', payload)
      return response.data
    },
    async createRequisition(payload: RequisitionCreateRequest) {
      const response = await client.post<RequisitionResponse>('/requisitions', payload)
      return response.data
    },
    async updateRequisitionStatus(requisitionId: string, payload: RequisitionStatusRequest) {
      const response = await client.patch<RequisitionResponse>(`/requisitions/${requisitionId}/status`, payload)
      return response.data
    },
    async deleteRequisition(requisitionId: string) {
      const response = await client.delete(`/requisitions/${requisitionId}`)
      return response.data
    },
    async verifyPin(payload: PinVerifyRequest) {
      const response = await client.post<PinVerifyResponse>('/verify-pin', payload)
      return response.data
    },
    async changePin(payload: PinChangeRequest) {
      const response = await client.post<PinVerifyResponse>('/change-pin', payload)
      return response.data
    },
    async resetSupervisorPin(payload: ResetSupervisorPinRequest) {
      const response = await client.post<{ name: string, role: MoldingSampleRole, must_change: boolean }>('/reset-supervisor-pin', payload)
      return response.data
    },
    async listSensitiveAuditLogs() {
      const response = await client.get<SensitiveAuditLogResponse[]>('/sensitive-audit-logs')
      return response.data
    },
    async getTotalCosts() {
      const response = await client.get<InjectionTotalCostSummary[]>('/injection-total-costs')
      return response.data
    },
  }
}

export const moldingSampleApi = createMoldingSampleApi()
