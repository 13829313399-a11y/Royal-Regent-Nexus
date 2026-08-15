import { http } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'

export interface QcEntityBase {
  id: string
  factory_id: string
  revision: number
  created_at: string
  updated_at: string
}

export interface QcInspectionOrder extends QcEntityBase {
  inspection_no?: string
  week_key?: string
  customer_name: string
  sales_contract_no: string
  customer_po_no: string
  customer_item_no: string
  product_name: string
  quantity: number | string
  packing?: string | null
  carton_count?: string | null
  report_status?: string | null
  production_department?: string | null
  export_country_code: string
  shipment_date: string
  planned_inspection_date: string
  actual_inspection_date?: string | null
  inspection_result?: string | null
  inspection_agency?: string | null
  account_manager?: string | null
  source_type?: string
  sequence_no?: number
  has_problem?: boolean
  manual_has_problem?: boolean
  problem_count?: number
  problem_id?: string | null
  problem_summary?: string | null
  rejection_reason?: string | null
  resolution?: string | null
  status?: string
}

export interface QcInspectionProblem extends QcEntityBase {
  inspection_order_id: string
  inspection_no?: string
  problem_no?: string
  customer_name?: string
  sales_contract_no?: string
  customer_po_no?: string
  customer_item_no?: string
  inspection_date?: string | null
  inspection_result?: string | null
  category?: string | null
  description?: string | null
  return_reason?: string | null
  corrective_action?: string | null
  resolution?: string | null
  primary_responsible_person?: string | null
  secondary_responsible_person?: string | null
  reported_date?: string | null
  status: string
}

export interface QcScheduleChange {
  id: string
  factory_id: string
  batch_id: string
  source_row_no: number
  sales_contract_no: string
  customer_po_no: string
  customer_item_no: string
  customer_name: string
  product_name: string
  quantity: number | string
  export_country_code: string
  shipment_date: string
  planned_inspection_date: string
  inspection_agency?: string | null
  account_manager?: string | null
  match_status: 'NEW' | 'EXACT' | 'MULTIPLE_MATCHES' | 'INVALID' | string
  candidate_order_ids: string[]
  candidate_order_revisions?: Record<string, number>
  candidate_orders?: Array<{
    id: string
    inspection_no: string
    customer_po_no: string
    week_key: string
    planned_inspection_date: string
    quantity: number | string
    revision: number
  }>
  changes: Array<{
    field: string
    old_value?: string | null
    new_value?: string | null
  }>
  validation_errors: string[]
  decision_status: 'PENDING' | 'UPDATE' | 'KEEP' | 'CREATE' | 'SKIP' | 'UNCHANGED' | string
  linked_order_id?: string | null
}

export interface QcScheduleImport extends QcEntityBase {
  week_key: string
  source_file_name: string
  source_file_sha256?: string
  source_size_bytes?: number
  parser_version?: string
  status: string
  row_count: number
  blocking_count: number
  summary?: Record<string, unknown>
  rows: QcScheduleChange[]
}

export type QcReportType =
  | 'CUSTOMER_SUMMARY'
  | 'WEEKLY_STATISTICS'
  | 'HUAXING_CUSTOMER_WEEKLY_DETAIL'
  | 'HUAXING_WEEKLY_AGGREGATE'
  | 'GROUP_SUMMARY'

export interface QcGeneratedReport {
  id: string
  factory_id: string
  report_type: QcReportType | string
  week_key: string
  artifact_file_name: string
  status: string
  is_formal_snapshot: boolean
  snapshot_revision: number
  source_revision_sha256: string
  artifact_media_type: string
  artifact_sha256: string
  artifact_size_bytes: number
  generation_summary: Record<string, unknown>
  error_message: string
  requested_by: string
  requested_by_name: string
  created_at: string
}

export interface QcWorkspace {
  factory_id: string
  week: string
  summary: {
    total_orders: number
    pending_orders: number
    completed_orders: number
    problem_orders: number
  }
  orders: QcInspectionOrder[]
  problems: QcInspectionProblem[]
  imports: QcScheduleImport[]
  reports: QcGeneratedReport[]
}

export interface QcOrderCreatePayload {
  factory_id: string
  customer_name: string
  sales_contract_no: string
  customer_po_no: string
  customer_item_no: string
  product_name: string
  quantity: number
  packing?: string
  carton_count?: string
  production_department?: string
  export_country_code: string
  shipment_date: string
  planned_inspection_date: string
  week_key: string
  inspection_agency?: string
  account_manager?: string
  request_id: string
}

export interface QcOrderUpdatePayload {
  factory_id: string
  expected_revision: number
  request_id: string
  reason: string
  actual_inspection_date?: string | null
  inspection_result?: string | null
  inspection_agency?: string | null
  manual_has_problem?: boolean
  packing?: string | null
  carton_count?: string | null
  report_status?: string | null
  production_department?: string | null
  planned_inspection_date?: string
  shipment_date?: string
  sequence_no?: number
}

export interface QcProblemUpdatePayload {
  factory_id: string
  expected_revision: number
  request_id: string
  reason: string
  category?: string | null
  description?: string | null
  return_reason?: string | null
  corrective_action?: string | null
  resolution?: string | null
  primary_responsible_person?: string | null
  secondary_responsible_person?: string | null
  status?: string
}

export interface QcReportGeneratePayload {
  factory_id: string
  week_key: string
  report_type: QcReportType
  is_formal_snapshot?: boolean
  request_id: string
}

export interface QcListResponse<T> {
  factory_id: string
  week: string
  total: number
  items: T[]
}

export interface QcRenameGroupInput {
  group_id: string
  is_caixing: boolean
  export_country?: string
  report_number?: string
  item_number: string
  customer_po_no: string
  quantity?: string
  actual_inspection_date: string
  files: Array<{
    file_id: string
    source_file_name: string
    sequence?: number
  }>
}

export interface QcRenamePreviewFile {
  source_file_name: string
  target_file_name: string
  source_sha256: string
  size_bytes: number
}

export interface QcRenamePreviewGroup {
  group_id: string
  success: boolean
  base_name: string | null
  files: QcRenamePreviewFile[]
  issues: Array<{ code: string; message: string; source_file_name?: string | null }>
}

export interface QcRenameBatch {
  id: string
  factory_id: string
  status: string
  rule_version: string
  fingerprint: string
  group_count: number
  source_file_count: number
  source_size_bytes: number
  successful_group_count: number
  failed_group_count: number
  revision: number
  archive_file_name: string
  archive_sha256: string
  archive_size_bytes: number
  created_at: string
  executed_at: string
  groups: QcRenamePreviewGroup[]
}

export interface QcDownloadResult {
  blob: Blob
  fileName: string
}

export interface QcInspectionHttpClient {
  get<T = unknown>(url: string, config?: unknown): Promise<{ data: T; headers?: Record<string, unknown> }>
  post<T = unknown>(url: string, data?: unknown, config?: unknown): Promise<{ data: T; headers?: Record<string, unknown> }>
  patch<T = unknown>(url: string, data?: unknown, config?: unknown): Promise<{ data: T; headers?: Record<string, unknown> }>
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

export function createQcRequestId() {
  return createRandomUuid()
}

export function createQcInspectionApi(client: QcInspectionHttpClient = http) {
  return {
    async getWorkspace(factoryId: string, week: string) {
      const response = await client.get<QcWorkspace>('/qc-inspections/workspace', {
        params: { factory_id: factoryId, week },
      })
      return response.data
    },

    async previewScheduleImport(file: File, factoryId: string, week: string) {
      const payload = new FormData()
      payload.append('file', file)
      payload.append('factory_id', factoryId)
      payload.append('week_key', week)
      payload.append('request_id', createQcRequestId())
      const response = await client.post<QcScheduleImport>(
        '/qc-inspections/schedule-imports/preview',
        payload,
        { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120_000 },
      )
      return response.data
    },

    async confirmScheduleImport(
      batchId: string,
      factoryId: string,
      expectedRevision: number,
      decisions: Array<{
        row_id: string
        action: 'UPDATE' | 'KEEP' | 'CREATE' | 'SKIP'
        target_order_id?: string
        reason?: string
      }>,
    ) {
      const response = await client.post<QcScheduleImport>(
        `/qc-inspections/schedule-imports/${encodeURIComponent(batchId)}/confirm`,
        {
          factory_id: factoryId,
          expected_revision: expectedRevision,
          request_id: createQcRequestId(),
          decisions,
        },
      )
      return response.data
    },

    async listOrders(factoryId: string, week?: string) {
      const response = await client.get<QcListResponse<QcInspectionOrder>>('/qc-inspections/orders', {
        params: { factory_id: factoryId, week },
      })
      return response.data.items
    },

    async createOrder(payload: Omit<QcOrderCreatePayload, 'request_id'>) {
      const response = await client.post<QcInspectionOrder>('/qc-inspections/orders', {
        ...payload,
        request_id: createQcRequestId(),
      })
      return response.data
    },

    async getOrder(orderId: string, factoryId: string) {
      const response = await client.get<QcInspectionOrder>(
        `/qc-inspections/orders/${encodeURIComponent(orderId)}`,
        { params: { factory_id: factoryId } },
      )
      return response.data
    },

    async updateOrder(orderId: string, payload: Omit<QcOrderUpdatePayload, 'request_id'>) {
      const response = await client.patch<QcInspectionOrder>(
        `/qc-inspections/orders/${encodeURIComponent(orderId)}`,
        { ...payload, request_id: createQcRequestId() },
      )
      return response.data
    },

    async listProblems(factoryId: string, week?: string) {
      const response = await client.get<QcListResponse<QcInspectionProblem>>('/qc-inspections/problems', {
        params: { factory_id: factoryId, week },
      })
      return response.data.items
    },

    async updateProblem(problemId: string, payload: Omit<QcProblemUpdatePayload, 'request_id'>) {
      const response = await client.patch<QcInspectionProblem>(
        `/qc-inspections/problems/${encodeURIComponent(problemId)}`,
        { ...payload, request_id: createQcRequestId() },
      )
      return response.data
    },

    async listReports(factoryId: string, week?: string) {
      const response = await client.get<QcListResponse<QcGeneratedReport>>('/qc-inspections/reports', {
        params: { factory_id: factoryId, week },
      })
      return response.data.items
    },

    async generateReport(payload: Omit<QcReportGeneratePayload, 'request_id'>) {
      const response = await client.post<QcGeneratedReport>('/qc-inspections/reports/generate', {
        ...payload,
        request_id: createQcRequestId(),
      })
      return response.data
    },

    async downloadReport(reportId: string, fallbackFileName: string, factoryId: string) {
      const response = await client.get<Blob>(
        `/qc-inspections/reports/${encodeURIComponent(reportId)}/download`,
        { responseType: 'blob', timeout: 120_000, params: { factory_id: factoryId } },
      )
      return {
        blob: response.data,
        fileName: responseFileName(response.headers, fallbackFileName),
      }
    },

    async previewRenameBatch(files: Array<{ fileId: string; file: File }>, groups: QcRenameGroupInput[], factoryId: string) {
      const payload = new FormData()
      files.forEach(({ fileId, file }) => {
        payload.append('files', file)
        payload.append('file_ids', fileId)
      })
      payload.append('metadata_json', JSON.stringify({
        factory_id: factoryId,
        groups,
        request_id: createQcRequestId(),
      }))
      const response = await client.post<QcRenameBatch>(
        '/qc-inspections/rename-batches/preview',
        payload,
        { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 180_000 },
      )
      return response.data
    },

    async executeRenameBatch(batchId: string, factoryId: string, expectedRevision: number) {
      const response = await client.post<Blob>(
        `/qc-inspections/rename-batches/${encodeURIComponent(batchId)}/execute`,
        { factory_id: factoryId, expected_revision: expectedRevision, request_id: createQcRequestId() },
        { responseType: 'blob', timeout: 180_000 },
      )
      return {
        blob: response.data,
        fileName: responseFileName(response.headers, `qc-report-renamed-${batchId}.zip`),
      }
    },
  }
}

export const qcInspectionApi = createQcInspectionApi()
