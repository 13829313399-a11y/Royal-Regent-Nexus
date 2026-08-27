export type WorkbenchPlanMode = 'PLANNING' | 'EXECUTION' | 'EMPTY'
export type WorkbenchJobStatus = 'UNPLANNED' | 'PLANNED' | 'RUNNING' | 'PAUSED' | 'DONE'

export interface SchedulingMachine {
  id: string
  factory_id: string
  code: string
  position: string
  area: string
  a_class: number | null
  tonnage: number | null
  arm_capabilities: string[]
  fixture_capabilities: string[]
  process_restrictions: string[]
  status: string
  available_for_auto_schedule: boolean
  remark: string
  parsed_constraint_summary: string
  revision: number
}

export interface SchedulingJob {
  id: string
  factory_id: string
  plan_id: string | null
  task_id: string | null
  order_id: string
  machine_id: string | null
  machine_code: string
  sequence_no: number | null
  status: WorkbenchJobStatus
  order_no: string
  item_no: string
  product_name: string
  warehouse_text: string
  order_quantity: number
  completed_quantity: number
  outstanding_quantity: number
  completion_rate: number
  mold_id: string | null
  mold_no: string
  mold_name: string
  required_machine_a: number | null
  material_name: string
  color_name: string
  net_weight_g: number | null
  gross_weight_g: number | null
  arm_requirement: string
  fixture_requirement: string
  delivery_due_date: string
  priority: string
  planned_start: string
  planned_finish: string
  estimated_finish: string
  delivery_slack_days: number | null
  shift_target_quantity: number
  locked: boolean
  order_remark: string
  suggestion_reason: string
  material_readiness_status: string
  mold_enrichment_status: string
  source_batch_id: string | null
  source_sheet_name: string
  source_row_number: number | null
  task_revision: number | null
  order_revision: number
  plan_revision: number | null
  lineage: Record<string, unknown>
}

export interface SchedulingWorkbench {
  factory_id: string
  business_date: string
  plan_id: string | null
  plan_revision: number | null
  rule_revision: number | null
  plan_mode: WorkbenchPlanMode
  polling_revision: number
  machines: SchedulingMachine[]
  jobs: SchedulingJob[]
  summary: {
    unplanned_count: number
    overdue_count: number
    conflict_count: number
    running_count: number
    today_day_quantity: number
    today_night_quantity: number
  }
}

export interface ImportIssue {
  id: string
  severity: 'ERROR' | 'WARNING'
  code: string
  message: string
  sheet_name: string
  source_row: number | null
  field_name: string
  cell_ref: string
  raw_value: string
  blocking: boolean
}

export interface ImportPreviewRow {
  classification: string
  order_no: string
  mold_no: string
  product_name: string
  order_quantity: number
  completed_quantity: number
  delivery_due_date: string
  priority_code: string
  machine_code: string
  execution_status: string
  locked?: boolean
  source: { source_row?: number; sheet_name?: string }
}

export interface ImportBatch {
  id: string
  factory_id: string
  source_file_name: string
  source_file_hash: string
  batch_state: string
  preview_generation: number
  document_kind: string
  profile: { profile_code?: string; name?: string } | null
  scheduled_baseline_tasks: ImportPreviewRow[]
  backlog_orders: ImportPreviewRow[]
  invalid_rows: ImportPreviewRow[]
  plan_context: Record<string, string | number>
  action_fingerprint: string
  resolution_digest: string
  summary: Record<string, number | boolean | string>
  status: string
  revision: number
  issues: ImportIssue[]
}

export interface ScheduleAssignment {
  id: string
  order_id: string
  existing_task_id: string | null
  machine_id: string | null
  sequence_no: number | null
  planned_start: string
  planned_finish: string
  decision: 'PASS' | 'REVIEW_REQUIRED' | 'UNASSIGNED'
  score: number | null
  explanation: Record<string, unknown>
  unassigned_reason_code: string
}

export interface ScheduleRun {
  id: string
  factory_id: string
  plan_id: string
  expected_plan_revision: number
  rule_revision: number
  status: string
  solver_type: 'HEURISTIC' | 'CP_SAT'
  summary: Record<string, number | string | boolean>
  assignments: ScheduleAssignment[]
}

export interface MatchReason {
  rule_code: string
  label: string
  detail: string
}

export interface MachineMatch {
  machine_id: string
  machine_code: string
  decision: 'PASS' | 'REVIEW_REQUIRED' | 'FAIL'
  score: number | null
  hard_failures: MatchReason[]
  warnings: MatchReason[]
  advisories: MatchReason[]
  explanation: string
}

export interface MatchEvaluation {
  factory_id: string
  order_id: string
  rule_set_revision: number
  results: MachineMatch[]
}

export interface ManualAppendPreview {
  factory_id: string
  plan_id: string
  plan_revision: number
  order_id: string
  order_revision: number
  machine_id: string
  sequence_no: number
  decision: 'PASS' | 'REVIEW_REQUIRED' | 'FAIL'
  hard_failures: MatchReason[]
  warnings: MatchReason[]
  planned_start: string
  planned_finish: string
  rule_revision: number
  input_fingerprint: string
}
