export type DecimalValue = number | string

export interface InjectionScheduleSettings {
  factory_id: string
  factory_name: string
  timezone: string
  business_date: string
  current_shift: string
  day_shift_start: string
  day_shift_end: string
  night_shift_start: string
  night_shift_end: string
  warehouse_buffer_days: number
  fallback_water_ratio: DecimalValue
  auto_schedule_mode: string
  ai_enabled: boolean
  template_family: string
  template_version: string
  schedule_revision: number
  schedule_horizon_days: number
  freeze_hours: number
  effective_hours_per_day: DecimalValue
}

export interface InjectionScheduleCapabilities {
  can_read: boolean
  can_edit: boolean
  can_schedule: boolean
  can_admin: boolean
  phase: 'LOCAL_ACCEPTANCE' | string
}

export interface InjectionScheduleBootstrap {
  factory_id: string
  settings: InjectionScheduleSettings
  capabilities: InjectionScheduleCapabilities
  supported_import_profiles: string[]
}

export interface InjectionScheduleKpis {
  active_order_count: number
  scheduled_order_count: number
  unscheduled_order_count: number
  in_production_order_count: number
  overdue_order_count: number
}

export interface InjectionScheduleLine {
  id: string
  factory_id: string
  order_demand_id: string
  machine_id: string | null
  machine_code: string
  mold_id: string | null
  mold_code: string
  order_no: string
  product_code: string
  product_name: string
  color: string
  material_name: string
  sequence_no: DecimalValue | null
  status: string
  is_locked: boolean
  priority: string
  planned_start_at: string
  planned_finish_at: string
  qualified_shots: DecimalValue
  remaining_shots: DecimalValue
  completion_percent: DecimalValue
  effective_daily_target: DecimalValue | null
  warehouse_date: string
  delivery_gap_days: DecimalValue | null
  schedule_revision: number
  schedule_source: string
  version: number
}

export interface InjectionScheduleBoard {
  factory_id: string
  start_date: string
  end_date: string
  schedule_revision: number
  kpis: InjectionScheduleKpis
  lines: InjectionScheduleLine[]
}

export interface InjectionScheduleOrder {
  id: string
  factory_id: string
  order_no: string
  product_code: string
  product_name: string
  mold_code: string
  quantity_sets: DecimalValue
  total_sets: DecimalValue | null
  order_shots: DecimalValue
  qualified_shots: DecimalValue
  remaining_shots: DecimalValue
  completion_percent: DecimalValue
  priority: string
  status: string
  delivery_due_date: string
  warehouse: string
  color: string
  pigment_code: string
  material_name: string
  material_status: string
  required_machine_a_label: string
  required_machine_a_value: DecimalValue | null
  daily_target: DecimalValue | null
  material_weight_kg: DecimalValue | null
  data_completeness_status: string
  remark: string
  version: number
}

export interface InjectionScheduleMachine {
  id: string
  factory_id: string
  machine_code: string
  position: string
  machine_name: string
  machine_a_label: string
  machine_ounce_capacity: DecimalValue | null
  tonnage: DecimalValue | null
  is_automatic: boolean
  is_high_speed: boolean
  robot_arm_type: string
  supports_core_pull: boolean
  status: string
  available_from: string
  raw_remark: string
  version: number
}

export interface InjectionScheduleMold {
  id: string
  factory_id: string
  scope_type: 'COMPANY_SHARED'
  mold_code: string
  product_code: string
  product_name: string
  required_machine_a_label: string
  mold_ounce_requirement: DecimalValue | null
  min_machine_ounce: DecimalValue | null
  max_machine_ounce: DecimalValue | null
  cavity_count: number | null
  pieces_per_shot: number | null
  shot_weight_g: DecimalValue | null
  recommended_tonnage: DecimalValue | null
  required_robot_arm: string
  status: string
  daily_target: DecimalValue | null
  remark: string
  version: number
}

export interface InjectionScheduleList<T> {
  factory_id: string
  total: number
  items: T[]
}

export interface InjectionScheduleImportIssue {
  source_row: number | null
  field_name: string
  raw_value: string
  severity: string
  error_type: string
  message: string
  blocking: boolean
}

export interface InjectionScheduleImportRow {
  source_row: number
  business_key: string
  change_action: 'CREATE' | 'UPDATE' | 'UNCHANGED'
  machine_code: string
  order_no: string
  product_code: string
  mold_code: string
  product_name: string
  quantity_sets: DecimalValue
  order_shots: DecimalValue
  delivery_due_date: string
  required_machine_a_label: string
  material_name: string
  data_completeness_status: string
  remark: string
}

export interface InjectionScheduleImportPreview {
  batch_id: string
  factory_id: string
  status: string
  profile_code: string
  document_type: string
  source_file_name: string
  source_file_sha256: string
  source_size_bytes: number
  source_sheet: string
  header_row: number
  header: Record<string, string>
  column_mapping: Record<string, string>
  machines: Array<Record<string, unknown>>
  rows: InjectionScheduleImportRow[]
  history_outputs: Array<{
    business_key: string
    source_row: number
    production_date: string
    shift: 'DAY' | 'NIGHT'
    reported_shots: DecimalValue
  }>
  issues: InjectionScheduleImportIssue[]
  summary: {
    row_count: number
    machine_count: number
    history_output_count: number
    blocking_issue_count: number
    warning_count: number
    create_count?: number
    update_count?: number
    unchanged_count?: number
  }
}

export interface InjectionScheduleImportCommitResult {
  batch_id: string
  factory_id: string
  status: 'CONFIRMED'
  created_count: number
  updated_count: number
  skipped_count: number
  history_created_count: number
  history_updated_count: number
  history_unchanged_count: number
}

export interface InjectionScheduleSavedView {
  id: string
  factory_id: string
  user_id: string
  name: string
  scope: 'PERSONAL' | 'FACTORY_SHARED'
  config: {
    view_mode?: 'table' | 'board'
    columns?: string[]
    filters?: Record<string, string>
  }
  is_default: boolean
  version: number
}

export interface InjectionScheduleMovePayload {
  factory_id: string
  target_machine_id: string
  planned_start_at: string
  planned_finish_at: string
  sequence_no?: DecimalValue | null
  expected_line_version: number
  expected_schedule_revision: number
  validate_token?: string
  reason?: string
}

export interface InjectionScheduleMoveValidation {
  valid: boolean
  validate_token: string
  conflicts: Array<{ code: string; message: string }>
  machine_code: string
}

export interface InjectionScheduleAutoProposal {
  proposal_id: string
  factory_id: string
  status: string
  algorithm_version: string
  input_version_digest: string
  summary: {
    scheduled_count: number
    unscheduled_count: number
    machine_count: number
    deterministic: boolean
  }
  changes: Array<Record<string, unknown>>
  unscheduled: Array<{ order_id: string; line_id: string; reason_code: string; message: string }>
  expires_at: string
  version: number
}
