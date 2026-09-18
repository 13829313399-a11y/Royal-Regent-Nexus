import { http } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'

export const QC_SCHEDULE_IMPORT_MAX_FILE_MEGABYTES = 35
export const QC_SCHEDULE_IMPORT_MAX_FILE_BYTES = QC_SCHEDULE_IMPORT_MAX_FILE_MEGABYTES * 1024 * 1024

export function validateQcScheduleImportFile(file: Pick<File, 'size'>): string {
  return file.size > QC_SCHEDULE_IMPORT_MAX_FILE_BYTES
    ? `排期文件不能超过 ${QC_SCHEDULE_IMPORT_MAX_FILE_MEGABYTES} MB`
    : ''
}

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
  source_sheet_name?: string
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
  | 'WEEKLY_INSPECTION_SCHEDULE'
  | 'DAILY_INSPECTION_LEDGER'
  | 'WEEKLY_PROBLEM_DETAIL'
  | 'WEEKLY_RETURN_SUMMARY'
  | 'INSPECTION_PASS_RATE'
  | 'ANNUAL_INSPECTION_STATISTICS'
  | 'PRODUCT_QUALITY_LEDGER'
  | 'INSPECTION_DOCUMENT_INDEX'
  | 'ORDER_INSPECTION_REPORT'

export type QcReportPeriodMode = 'WEEK' | 'MONTH' | 'YEAR' | 'EVENT'

export interface QcInspectionLine {
  id?: string
  line_no?: number
  customer_po_no: string
  release_no: string
  customer_item_no: string
  internal_item_no: string
  batch_no: string
  date_code: string
  product_name: string
  order_quantity: number | string | null
  inspected_quantity: number | string | null
  packing: string
  carton_count: string
  upc_ean: string
}

export interface QcInspectionDefect {
  id?: string
  event_line_id: string
  category: string
  severity: 'CRITICAL' | 'MAJOR' | 'MINOR' | 'OBSERVATION'
  quantity: number
  defect_location: string
  description: string
  production_department: string
  photo_reference: string
}

export interface QcInspectionTestRecord {
  id?: string
  test_item: string
  method_standard: string
  specification: string
  measured_value: string
  unit: string
  sample_size: number
  result: 'PENDING' | 'PASS' | 'FAIL' | 'NA'
  operator_name: string
  reviewer_name: string
}

export interface QcInspectionDisposition {
  id?: string
  disposition_type: 'RETURN' | 'REWORK' | 'AOD' | 'CONCESSION_ACCEPTED' | 'ON_HOLD' | 'NO_ACTION'
  return_quantity: number | string | null
  rework_quantity: number | string | null
  reason: string
  approved_by: string
  approved_date: string
  verification_result: string
}

export interface QcInspectionEvent extends QcEntityBase {
  inspection_order_id: string
  attempt_no: number
  event_type: 'CUSTOMER' | 'THIRD_PARTY' | 'LINE' | 'SELF' | 'REINSPECTION' | 'SAMPLE'
  actual_inspection_date: string
  inspector_name: string
  inspection_agency: string
  inspection_location: string
  sampling_standard: string
  inspection_level: string
  aql_critical: string
  aql_major: string
  aql_minor: string
  lot_size: number
  sample_size: number
  critical_defect_count: number
  major_defect_count: number
  minor_defect_count: number
  inspection_result: string
  document_status: 'DRAFT' | 'FINAL' | 'REVISED'
  manual_has_problem: boolean
  report_number: string
  note: string
  lines: QcInspectionLine[]
  defects: QcInspectionDefect[]
  tests: QcInspectionTestRecord[]
  dispositions: QcInspectionDisposition[]
  created_by: string
  created_by_name: string
  updated_by: string
  updated_by_name: string
}

export type QcInspectionEventPayload = Omit<
  QcInspectionEvent,
  'id' | 'revision' | 'created_at' | 'updated_at' | 'attempt_no' | 'created_by' | 'created_by_name' | 'updated_by' | 'updated_by_name'
> & { expected_pending_order_revision?: number }

export interface QcGeneratedReport {
  id: string
  factory_id: string
  report_type: QcReportType | string
  week_key: string
  period_mode: QcReportPeriodMode
  period_key: string
  metric_version: string
  inspection_order_id: string
  inspection_event_id: string
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
  quantity: number | string
  packing?: string
  carton_count?: string
  production_department?: string
  export_country_code: string
  shipment_date: string
  planned_inspection_date: string
  week_key: string
  inspection_agency?: string
  account_manager?: string
  note?: string
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
  period_mode?: QcReportPeriodMode
  period_key?: string
  request_id: string
}

export interface QcListResponse<T> {
  factory_id: string
  week: string
  total: number
  items: T[]
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
    async getScheduleImport(batchId: string, factoryId: string) {
      const response = await client.get<QcScheduleImport>(`/qc-inspections/schedule-imports/${encodeURIComponent(batchId)}`, {
        params: { factory_id: factoryId },
      })
      return response.data
    },
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

    async createOrder(payload: Omit<QcOrderCreatePayload, 'request_id'>, requestId = createQcRequestId()) {
      const response = await client.post<QcInspectionOrder>('/qc-inspections/orders', {
        ...payload,
        request_id: requestId,
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

    async listInspectionEvents(orderId: string, factoryId: string) {
      const response = await client.get<{ items: QcInspectionEvent[] }>(
        `/qc-inspections/orders/${encodeURIComponent(orderId)}/events`,
        { params: { factory_id: factoryId } },
      )
      return response.data.items
    },

    async createInspectionEvent(orderId: string, payload: QcInspectionEventPayload, requestId = createQcRequestId()) {
      const response = await client.post<QcInspectionEvent>(
        `/qc-inspections/orders/${encodeURIComponent(orderId)}/events`,
        { ...payload, request_id: requestId },
      )
      return response.data
    },

    async updateInspectionEvent(
      orderId: string,
      eventId: string,
      payload: QcInspectionEventPayload & { expected_revision: number; reason: string },
      requestId = createQcRequestId(),
    ) {
      const response = await client.patch<QcInspectionEvent>(
        `/qc-inspections/orders/${encodeURIComponent(orderId)}/events/${encodeURIComponent(eventId)}`,
        { ...payload, request_id: requestId },
      )
      return response.data
    },

    async generateOrderReport(orderId: string, eventId: string, factoryId: string) {
      const response = await client.post<QcGeneratedReport>(
        `/qc-inspections/orders/${encodeURIComponent(orderId)}/reports/generate`,
        { factory_id: factoryId, inspection_event_id: eventId, request_id: createQcRequestId() },
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


  }
}

export const qcInspectionApi = createQcInspectionApi()
