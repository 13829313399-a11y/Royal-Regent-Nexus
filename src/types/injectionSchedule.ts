export interface InjectionScheduleImportSummary {
  machine_count: number
  old_machine_count: number
  new_machine_count: number
  task_count: number
  scheduled_task_count: number
  pending_task_count: number
  relative_task_count: number
  no_plan_task_count: number
  total_shortage_qty: number
  overdue_count: number
  missing_due_count: number
  negative_or_zero_shortage_count: number
  huge_negative_gap_count: number
  external_formula_risk_count: number
  date_axis_days: number
  date_axis_shift_columns: number
  business_date: string
}

export interface InjectionScheduleMachine {
  id: string
  batch_id: string
  factory_id: string
  machine_code: string
  workshop: string
  machine_spec_label: string
  machine_process_type: string
  robot_type: string
  status: string
  constraints: Record<string, unknown>
  source_row: number
}

export interface InjectionScheduleTask {
  id: string
  batch_id: string
  factory_id: string
  source_row: number
  assigned_machine_code: string
  task_bucket: 'scheduled' | 'pending' | 'unplanned'
  mold_code: string
  product_name: string
  order_no: string
  product_code: string
  machine_model: string
  color: string
  pigment: string
  material: string
  order_qty: number | null
  produced_qty: number | null
  shortage_qty: number | null
  daily_target_qty: number | null
  delivery_due_date: string
  plan_start_at: string
  plan_finish_at: string
  warehouse_due_at: string
  delivery_gap_days: number | null
  priority_flag: string
  remark: string
  source_values: Record<string, unknown>
}

export interface InjectionScheduleImportIssue {
  id: string
  batch_id: string
  source_row: number
  severity: 'info' | 'warning' | 'error' | string
  issue_type: string
  field_name: string
  raw_value: string
  message: string
}

export interface InjectionScheduleImportPreview {
  batch_id: string
  factory_id: string
  source_file_name: string
  business_date: string
  status: string
  summary: InjectionScheduleImportSummary
  machines: InjectionScheduleMachine[]
  tasks: InjectionScheduleTask[]
  issues: InjectionScheduleImportIssue[]
}
