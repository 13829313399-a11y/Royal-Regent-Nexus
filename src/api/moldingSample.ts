import { http } from '../lib/http.js'
import type {
  MoldingSampleAuditLog,
  MoldingSampleDispatchLog,
  MoldingSampleItem,
  MoldingSampleOrder,
  MoldingSampleProblem,
  MoldingSampleStatus,
  MoldingSampleTrialReport,
  MoldingSampleTrialReportData,
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
  & Pick<MoldingSampleOrder, 'product_name' | 'client_name' | 'date' | 'workshop' | 'supervisor' | 'eng_name'>

export type MoldingSampleItemDraft = Partial<MoldingSampleItem>

export type MoldingSampleExistingOrderDraft = MoldingSampleOrderDraft & Pick<MoldingSampleOrder, 'id'>

export type MoldingSampleExistingItemDraft = MoldingSampleItemDraft & Pick<MoldingSampleItem, 'id'>

export interface MoldingSampleCreateRequest {
  order: MoldingSampleOrderDraft
  items: MoldingSampleItemDraft[]
}

export interface MoldingSampleEditRequest {
  order: MoldingSampleExistingOrderDraft
  items: MoldingSampleExistingItemDraft[]
}

export interface MoldingSampleExcelImportOptions {
  order_id?: string
  factory_id?: string
  production_factory_id?: string
}

export interface MoldingSampleDetailResponse {
  order: MoldingSampleOrder
  items: MoldingSampleItem[]
  audit_logs: MoldingSampleAuditLog[]
  dispatch_logs: MoldingSampleDispatchLog[]
  notifications: MoldingSampleNotificationResponse[]
  problems: MoldingSampleProblem[]
  trial_reports: MoldingSampleTrialReport[]
  read_source?: MoldingSampleReadSource
  can_view_cost?: boolean
  read_only?: boolean
  access?: MoldingSampleAccess
}

export interface MoldingSampleBoardPageResponse {
  rows: MoldingSampleDetailResponse[]
  total: number
  page: number
  page_size: number
  page_count: number
}

export interface MoldingSampleBoardSummaryResponse {
  total: number
  status_counts: Partial<Record<MoldingSampleStatus, number>>
  review_count: number
  production_count: number
  completed_count: number
  rejected_count: number
  withdrawn_count: number
  unresolved_problem_count: number
  production_data_pending_count: number
}

export type MoldingSampleReadSource = 'local' | 'cross' | 'cross_operate'

export interface MoldingSampleAccess {
  read_source?: MoldingSampleReadSource
  can_view_cost?: boolean
  read_only?: boolean
}

export function resolveMoldingSampleAccess(response: Pick<
  MoldingSampleDetailResponse,
  'read_source' | 'can_view_cost' | 'read_only' | 'access'
>): Required<MoldingSampleAccess> {
  const readSource = response.access?.read_source ?? response.read_source ?? 'local'
  return {
    read_source: readSource,
    can_view_cost: response.access?.can_view_cost ?? response.can_view_cost ?? true,
    read_only: response.access?.read_only ?? response.read_only ?? readSource === 'cross',
  }
}

export interface MoldingSampleStatusRequest {
  action: string
  reason?: string
}

export interface MoldingSampleProductionAssignmentRequest {
  production_factory_id: string
  reason: string
  expected_assignment_version: number
}

export interface MoldingSampleFactoryCapabilityResponse {
  factory_id: string
  has_molding_department: boolean
  allowed_production_factory_ids: string[]
  suggested_production_factory_id: string
}

export interface MoldingSampleItemsPatchRequest {
  items: MoldingSampleExistingItemDraft[]
}

export interface MoldingSampleTrialReportUpsertRequest {
  data: MoldingSampleTrialReportData
}

export interface MaterialPricesResponse {
  prices: MoldingSampleMaterialPrice[]
  rmb_to_hkd_rate: number
}

export interface MaterialPricesUpdateRequest extends MaterialPricesResponse {}

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
  factory_id: string
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
  factory_id?: string
  material: string
  batch_no: string
  location?: string
  initial_weight_kg: number
}

export interface InventoryBatchResponse {
  id: string
  factory_id: string
  material: string
  batch_no: string
  location: string
  initial_weight_kg: number
  available_weight_kg: number
  created_at: string
  updated_at: string
}

export interface InventoryMovementFilters {
  factory_id?: string
  batch_id?: string
  material?: string
  requisition_id?: string
}

export interface InventoryMovementResponse {
  id: number
  factory_id: string
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
  actor_user_id: string
  actor_name: string
  actor_role: string
  actor_roles: string
  factory_scope: string
  target_type: string
  target_name: string
  detail: string
  created_at: string
}

export interface MoldingSampleNotificationResponse {
  id: string
  order_id: string
  factory_id: string
  target_module: string
  target_role: string
  target_department?: string
  event_type: string
  title: string
  message: string
  from_status: string
  to_status: string
  status: '未读' | '已读' | '已处理'
  actor_name: string
  read_at: string
  handled_at: string
  created_at: string
}

export interface MoldingSampleNotificationFilters {
  target_module?: string
  target_role?: string
  factory_id?: string
  order_id?: string
  status?: string
}

export interface MoldingSampleNotificationUpdateRequest {
  status: '未读' | '已读' | '已处理'
}

export interface MoldingSampleProblemCreateRequest {
  order_id: string
  description: string
  reported_by?: string
}

export interface MoldingSampleProblemStatusRequest {
  status: '待处理' | '已解决'
}

export interface MoldingSampleProblemFilters {
  order_id?: string
  status?: string
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
    async listOrders(factoryId?: string) {
      const query = factoryId ? `?factory_id=${encodeURIComponent(factoryId)}` : ''
      const response = await client.get<MoldingSampleDetailResponse[]>(`/injection${query}`)
      return response.data
    },
    async listProductionTasks(executionFactoryId: string) {
      const params = new URLSearchParams({ production_factory_id: executionFactoryId })
      const response = await client.get<MoldingSampleDetailResponse[]>(
        `/injection/production-tasks?${params.toString()}`,
      )
      return response.data
    },
    async listFactoryCapabilities() {
      const response = await client.get<MoldingSampleFactoryCapabilityResponse[]>(
        '/injection/factory-capabilities',
      )
      return response.data
    },
    async getBoardSummary(factoryId: string, query?: string) {
      const params = new URLSearchParams({ factory_id: factoryId })
      const normalizedQuery = query?.trim()
      if (normalizedQuery) {
        params.set('q', normalizedQuery)
      }
      const response = await client.get<MoldingSampleBoardSummaryResponse>(
        `/injection/board/summary?${params.toString()}`,
      )
      return response.data
    },
    async listBoardPage({
      factoryId,
      status,
      query,
      page,
      pageSize,
    }: {
      factoryId: string
      status: MoldingSampleStatus
      query?: string
      page: number
      pageSize: number
    }) {
      const params = new URLSearchParams({
        factory_id: factoryId,
        status,
      })
      const normalizedQuery = query?.trim()
      if (normalizedQuery) {
        params.set('q', normalizedQuery)
      }
      params.set('page', String(page))
      params.set('page_size', String(pageSize))
      const response = await client.get<MoldingSampleBoardPageResponse>(
        `/injection/board/page?${params.toString()}`,
      )
      return response.data
    },
    async getOrder(orderId: string) {
      const response = await client.get<MoldingSampleDetailResponse>(`/injection/${orderId}`)
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
    async deleteOrder(orderId: string) {
      const response = await client.delete(`/injection/${orderId}`)
      return response.data
    },
    async exportOrderExcel(orderId: string) {
      const response = await client.get<ArrayBuffer>(`/injection/${orderId}/export-excel`, {
        responseType: 'arraybuffer',
      })
      return response.data
    },
    async exportOrdersExcel(orderIds: string[]) {
      const params = new URLSearchParams()
      for (const orderId of orderIds) {
        params.append('order_ids', orderId)
      }
      const response = await client.get<ArrayBuffer>(`/injection/export-excel?${params.toString()}`, {
        responseType: 'arraybuffer',
      })
      return response.data
    },
    async downloadEngineeringImportTemplate(factoryId?: string) {
      const query = factoryId ? `?factory_id=${encodeURIComponent(factoryId)}` : ''
      const response = await client.get<ArrayBuffer>(`/injection/import-excel-template${query}`, {
        responseType: 'arraybuffer',
      })
      return response.data
    },
    async importOrderExcel(workbook: ArrayBuffer, options: MoldingSampleExcelImportOptions = {}) {
      const params = new URLSearchParams()
      if (options.order_id) {
        params.set('order_id', options.order_id)
      }
      if (options.factory_id) {
        params.set('factory_id', options.factory_id)
      }
      if (options.production_factory_id) {
        params.set('production_factory_id', options.production_factory_id)
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
    async previewOrderExcel(workbook: ArrayBuffer, options: MoldingSampleExcelImportOptions = {}) {
      const params = new URLSearchParams()
      if (options.order_id) {
        params.set('order_id', options.order_id)
      }
      if (options.factory_id) {
        params.set('factory_id', options.factory_id)
      }
      if (options.production_factory_id) {
        params.set('production_factory_id', options.production_factory_id)
      }
      const query = params.toString()
      const response = await client.post<MoldingSampleCreateRequest>(
        query ? `/injection/import-excel-preview?${query}` : '/injection/import-excel-preview',
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
    async updateProductionAssignment(orderId: string, payload: MoldingSampleProductionAssignmentRequest) {
      const response = await client.patch<MoldingSampleDetailResponse>(
        `/injection/${orderId}/production-assignment`,
        payload,
      )
      return response.data
    },
    async updateItems(orderId: string, payload: MoldingSampleItemsPatchRequest) {
      const response = await client.patch<MoldingSampleDetailResponse>(`/injection/${orderId}/items`, payload)
      return response.data
    },
    async upsertTrialReport(orderId: string, itemId: string, payload: MoldingSampleTrialReportUpsertRequest) {
      const response = await client.put<MoldingSampleTrialReport>(
        `/injection/${orderId}/trial-reports/${itemId}`,
        payload,
      )
      return response.data
    },
    async getMaterialPrices(factoryId?: string) {
      const query = factoryId ? `?factory_id=${encodeURIComponent(factoryId)}` : ''
      const response = await client.get<MaterialPricesResponse>(`/material-prices${query}`)
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
    async listInventoryBatches(material?: string, factoryId?: string) {
      const params = new URLSearchParams()
      if (factoryId) {
        params.set('factory_id', factoryId)
      }
      if (material) {
        params.set('material', material)
      }
      const query = params.toString()
      const url = query ? `/inventory-batches?${query}` : '/inventory-batches'
      const response = await client.get<InventoryBatchResponse[]>(url)
      return response.data
    },
    async listInventoryMovements(filters: InventoryMovementFilters = {}) {
      const params = new URLSearchParams()
      if (filters.factory_id) {
        params.set('factory_id', filters.factory_id)
      }
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
    async listSensitiveAuditLogs() {
      const response = await client.get<SensitiveAuditLogResponse[]>('/sensitive-audit-logs')
      return response.data
    },
    async listNotifications(filters: MoldingSampleNotificationFilters = {}) {
      const params = new URLSearchParams()
      if (filters.target_module) {
        params.set('target_module', filters.target_module)
      }
      if (filters.target_role) {
        params.set('target_role', filters.target_role)
      }
      if (filters.factory_id) {
        params.set('factory_id', filters.factory_id)
      }
      if (filters.order_id) {
        params.set('order_id', filters.order_id)
      }
      if (filters.status) {
        params.set('status', filters.status)
      }
      const query = params.toString()
      const response = await client.get<MoldingSampleNotificationResponse[]>(
        query ? `/molding-sample-notifications?${query}` : '/molding-sample-notifications',
      )
      return response.data
    },
    async updateNotification(notificationId: string, payload: MoldingSampleNotificationUpdateRequest) {
      const response = await client.patch<MoldingSampleNotificationResponse>(
        `/molding-sample-notifications/${notificationId}`,
        payload,
      )
      return response.data
    },
    async listProblems(filters: MoldingSampleProblemFilters = {}) {
      const params = new URLSearchParams()
      if (filters.order_id) {
        params.set('order_id', filters.order_id)
      }
      if (filters.status) {
        params.set('status', filters.status)
      }
      const query = params.toString()
      const response = await client.get<MoldingSampleProblem[]>(query ? `/problems?${query}` : '/problems')
      return response.data
    },
    async createProblem(payload: MoldingSampleProblemCreateRequest) {
      const response = await client.post<MoldingSampleProblem>('/problems', payload)
      return response.data
    },
    async updateProblemStatus(problemId: string, payload: MoldingSampleProblemStatusRequest) {
      const response = await client.patch<MoldingSampleProblem>(`/problems/${problemId}`, payload)
      return response.data
    },
    async getTotalCosts() {
      const response = await client.get<InjectionTotalCostSummary[]>('/injection-total-costs')
      return response.data
    },
  }
}

export const moldingSampleApi = createMoldingSampleApi()
