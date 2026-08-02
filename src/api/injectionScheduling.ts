import { http } from '@/lib/http'

export interface InjectionSchedulingHttpClient {
  get<T = unknown>(url: string, config?: unknown): Promise<{ data: T }>
  post<T = unknown>(url: string, data?: unknown, config?: unknown): Promise<{ data: T }>
}

export interface InjectionSchedulingMachineDto {
  id: string
  factory_id: string
  machine_code: string
  area: string
  position: string
  machine_class: string
  clamping_force_tons: number | null
  injection_capacity_g: number | null
  platen_x_mm: number | null
  platen_y_mm: number | null
  machine_type: string
  robot_capabilities: string[]
  process_restrictions: string[]
  status: 'available' | 'running' | 'maintenance' | 'offline'
  revision: number
  updated_at: string
}

export interface InjectionSchedulingMoldDto {
  id: string
  factory_id: string
  mold_no: string
  name: string
  length_mm: number | null
  width_mm: number | null
  height_mm: number | null
  recommended_machine_class: string
  whole_shot_net_weight_g: number | null
  required_arm_type: string
  required_fixture_type: string
  material_code: string
  material_name: string
  color_profile: string
  data_quality_status: 'complete' | 'needs_review'
  revision: number
}

export interface InjectionSchedulingOrderDto {
  id: string
  factory_id: string
  order_no: string
  item_no: string
  product_name: string
  mold_id: string | null
  order_quantity: number
  source_completed_quantity: number
  completed_quantity: number
  outstanding_quantity: number
  delivery_slack_days: number | null
  delivery_start_date: string
  delivery_due_date: string
  priority_code: 'NORMAL' | 'URGENT' | 'CRITICAL'
  material_readiness_status: 'unknown' | 'ready' | 'partial' | 'blocked'
  warehouse_text: string
  remark: string
  lineage: Record<string, unknown>
  status: 'BACKLOG' | 'SCHEDULED' | 'COMPLETED' | 'CANCELLED'
  revision: number
  updated_at: string
}

export interface InjectionSchedulingTaskDto {
  id: string
  factory_id: string
  plan_id: string
  machine_id: string
  order_id: string
  mold_id: string | null
  sequence_no: number
  execution_status: 'QUEUED' | 'RUNNING' | 'BLOCKED' | 'COMPLETED' | 'CANCELLED'
  planned_start: string
  planned_finish: string
  shift_target_quantity: number
  reported_quantity: number
  delivery_slack_days: number | null
  manual_override_reason: string
  source_sheet_name: string
  source_row: number | null
  revision: number
  updated_at: string
}

export interface InjectionSchedulingPlanDto {
  id: string
  factory_id: string
  business_date: string
  status: 'DRAFT' | 'PUBLISHED' | 'ARCHIVED'
  revision: number
  updated_at: string
  orders: InjectionSchedulingOrderDto[]
  tasks: InjectionSchedulingTaskDto[]
}

export interface InjectionSchedulingCurrentPlanDto {
  factory_id: string
  plan: InjectionSchedulingPlanDto | null
  polling_revision: number
}

export interface InjectionSchedulingImportIssueDto {
  id: string
  severity: 'ERROR' | 'WARNING'
  code: string
  message: string
  sheet_name: string
  source_row: number | null
  field_name: string
  cell_ref: string
  raw_value: string
  formula_text: string
  blocking: boolean
}

export interface InjectionSchedulingImportTaskPreviewDto {
  machine_code: string
  sequence_no: number
  execution_status: string
  status_inferred: boolean
  legacy_marker: string
  mold_no: string
  product_name: string
  order_no: string
  item_no: string
  order_quantity: number | null
  completed_quantity: number | null
  shift_target_quantity: number
  delivery_due_date: string
  planned_start: string
  planned_finish: string
  priority_code: string
  source: Record<string, unknown>
}

export interface InjectionSchedulingImportBatchDto {
  id: string
  factory_id: string
  source_file_name: string
  source_file_hash: string
  source_size_bytes: number
  parser_version: string
  preview_schema_version: string
  normalized_sha256: string
  summary: Record<string, number | boolean>
  status: 'PREVIEW' | 'CONFIRMED'
  revision: number
  preview_request_id: string
  confirm_request_id: string | null
  confirm_mode: string
  confirmed_plan_id: string
  confirmed_plan_revision: number
  result: Record<string, number | boolean>
  issues: InjectionSchedulingImportIssueDto[]
  tasks: InjectionSchedulingImportTaskPreviewDto[]
  idempotent_replay: boolean
}

export interface InjectionSchedulingImportConfirmDto {
  factory_id: string
  expected_revision: number
  expected_plan_revision: number
  request_id: string
  confirm_mode: 'create_draft' | 'merge_draft'
  business_date: string
  acknowledged_blocking_issue_ids: string[]
}

export interface InjectionSchedulingShiftReportDto {
  factory_id: string
  expected_revision: number
  request_id: string
  business_date: string
  shift_code: 'DAY' | 'NIGHT'
  quantity_mode: 'CUMULATIVE'
  reported_quantity: number
  shift_target_quantity: number
  downtime_minutes: number
  exception_code: string
  exception_detail: string
  reported_status: 'QUEUED' | 'RUNNING' | 'BLOCKED' | 'COMPLETED'
}

export interface InjectionSchedulingShiftReportResultDto {
  task: InjectionSchedulingTaskDto
  order: InjectionSchedulingOrderDto
  audit_sequence: number
  idempotent_replay: boolean
}

export interface InjectionSchedulingMatchReasonDto {
  rule_code: string
  label: string
  detail: string
}

export interface InjectionSchedulingScoreBreakdownDto {
  rule_code: string
  label: string
  delta: number
  explanation: string
}

export interface InjectionSchedulingMachineMatchDto {
  machine_id: string
  machine_code: string
  decision: 'PASS' | 'REVIEW_REQUIRED' | 'FAIL'
  score: number | null
  hard_failures: InjectionSchedulingMatchReasonDto[]
  warnings: InjectionSchedulingMatchReasonDto[]
  score_breakdown: InjectionSchedulingScoreBreakdownDto[]
  explanation: string
  rule_set_id: string
  rule_set_revision: number
}

export interface InjectionSchedulingMatchEvaluationDto {
  factory_id: string
  order_id: string
  mold_id: string
  rule_set_id: string
  rule_set_revision: number
  results: InjectionSchedulingMachineMatchDto[]
}

export interface InjectionSchedulingSuggestionDto {
  plan: InjectionSchedulingPlanDto
  match: InjectionSchedulingMachineMatchDto
  audit_sequence: number
}

export function createInjectionSchedulingApi(client: InjectionSchedulingHttpClient = http) {
  return {
    async listMachines(factoryId: string) {
      const response = await client.get<{ factory_id: string; items: InjectionSchedulingMachineDto[] }>(
        '/injection-scheduling/machines',
        { params: { factory_id: factoryId } },
      )
      return response.data
    },
    async listMolds(factoryId: string) {
      const response = await client.get<{ factory_id: string; items: InjectionSchedulingMoldDto[] }>(
        '/injection-scheduling/molds',
        { params: { factory_id: factoryId } },
      )
      return response.data
    },
    async getBacklog(factoryId: string) {
      const response = await client.get<{ factory_id: string; items: InjectionSchedulingOrderDto[] }>(
        '/injection-scheduling/backlog',
        { params: { factory_id: factoryId } },
      )
      return response.data
    },
    async getCurrentPlan(factoryId: string) {
      const response = await client.get<InjectionSchedulingCurrentPlanDto>(
        '/injection-scheduling/plans/current',
        { params: { factory_id: factoryId } },
      )
      return response.data
    },
    async saveShiftReport(taskId: string, payload: InjectionSchedulingShiftReportDto) {
      const response = await client.post<InjectionSchedulingShiftReportResultDto>(
        `/injection-scheduling/tasks/${encodeURIComponent(taskId)}/shift-reports`,
        payload,
      )
      return response.data
    },
    async evaluateMatches(factoryId: string, orderId: string, machineIds: string[] = []) {
      const response = await client.post<InjectionSchedulingMatchEvaluationDto>(
        '/injection-scheduling/matches/evaluate',
        { factory_id: factoryId, order_id: orderId, machine_ids: machineIds },
      )
      return response.data
    },
    async confirmSuggestion(planId: string, payload: {
      factory_id: string
      order_id: string
      machine_id: string
      expected_plan_revision: number
      expected_rule_revision: number
      request_id: string
      override_reason: string
    }) {
      const response = await client.post<InjectionSchedulingSuggestionDto>(
        `/injection-scheduling/plans/${encodeURIComponent(planId)}/suggest`,
        payload,
      )
      return response.data
    },
    async previewImport(factoryId: string, file: File, expectedRevision: number, requestId: string) {
      const payload = new FormData()
      payload.append('factory_id', factoryId)
      payload.append('expected_revision', String(expectedRevision))
      payload.append('file', file)
      const response = await client.post<InjectionSchedulingImportBatchDto>(
        '/injection-scheduling/imports/preview',
        payload,
        {
          headers: {
            'Content-Type': 'multipart/form-data',
            'X-Request-ID': requestId,
          },
          timeout: 120_000,
        },
      )
      return response.data
    },
    async confirmImport(batchId: string, payload: InjectionSchedulingImportConfirmDto) {
      const response = await client.post<InjectionSchedulingImportBatchDto>(
        `/injection-scheduling/imports/${encodeURIComponent(batchId)}/confirm`,
        payload,
        { timeout: 120_000 },
      )
      return response.data
    },
  }
}

export type InjectionSchedulingApi = ReturnType<typeof createInjectionSchedulingApi>
export const injectionSchedulingApi = createInjectionSchedulingApi()
