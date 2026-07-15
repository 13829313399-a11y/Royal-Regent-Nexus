export type MoldingSampleStatus =
  | '待审核'
  | '待经理审核'
  | '待生产'
  | '生产中'
  | '已完成'
  | '已驳回'
  | '已撤回'

export type MoldingSampleOrderType = '试模' | '试色' | '啤办'

export type MoldingSampleStage = 'T0' | 'EP' | 'FEP' | 'PP' | ''

export type MoldingSampleWorkshop = 'A车间' | 'B车间' | '华登车间' | '模厂'

export type MoldingSampleSendTo = '' | '发至湖南' | '发至模厂'

export type MoldingSampleRole =
  | '工程部'
  | '主管'
  | '经理'
  | '仓库'
  | '啤机部'
  | '工程师'
  | '工程主管'
  | '仓管员'
  | '啤机操作员'
  | '啤机主管'
  | '系统管理员'

export type MoldingSampleAuditDecision = '提交' | '通过' | '驳回' | '重提' | '撤回' | '开始处理' | '撤回开始生产' | '完成' | '改价' | '重算'

export type MoldingSampleTone = 'teal' | 'blue' | 'amber' | 'red' | 'slate' | 'green'
export type MoldPresenceStatus = 'unknown' | 'in_factory' | 'out_of_factory'

export type MoldingSampleMaterialSource = 'virgin' | 'runner'

export type MoldingSampleMaterialUsageType = 'production' | 'trial'

export interface MoldingSampleMaterialComponent {
  material: string
  source_type: MoldingSampleMaterialSource
  ratio_percent: number
}

export interface MoldingSampleActualMaterialCostComponent extends MoldingSampleMaterialComponent {
  weight_kg: number
  unit_price: number
  amount_hkd: number
}

export interface MoldingSampleOrder {
  id: string
  factory_id: string
  order_number: string
  doc_number: string
  product_name: string
  client_name: string
  date: string
  stage: MoldingSampleStage
  order_type: MoldingSampleOrderType
  workshop: MoldingSampleWorkshop
  send_to: MoldingSampleSendTo
  supervisor: string
  eng_name: string
  reason: string
  status: MoldingSampleStatus
  reject_reason: string
  completed_date: string
  created_at: string
  updated_at: string
}

export interface MoldingSampleItem {
  id: string
  order_id: string
  sort_order: number
  mold_id: string
  mold_name: string
  mold_dimensions: string
  mold_presence_status: MoldPresenceStatus
  machine_type: string
  production_machine: string
  material: string
  material_components?: MoldingSampleMaterialComponent[]
  material_usage_type?: MoldingSampleMaterialUsageType
  color: string
  pigment_no: string
  quantity: string
  shoot_qty: number
  gross_weight_g: number | null
  required_material_kg: number | null
  mold_return_time: string
  completion_time: string
  notes: string
  receipt_no: string
  collected_weight_kg: number | null
  actual_weight_kg: number | null
  actual_amount_hkd: number | null
  actual_material_cost_components?: MoldingSampleActualMaterialCostComponent[]
  injection_cost: number | null
  injection_cost_hkd: number | null
  exchange_rate_at_save: number | null
}

export interface MoldingSampleAuditLog {
  id: string
  order_id: string
  action: string
  actor_user_id?: string
  actor_name: string
  actor_role: MoldingSampleRole
  actor_roles?: string
  factory_scope?: string
  decision: MoldingSampleAuditDecision
  from_status: MoldingSampleStatus
  to_status: MoldingSampleStatus
  reason: string
  created_at: string
  tone: MoldingSampleTone
}

export type MoldingSampleRequisitionStatus = '待出库' | '已出库'

export interface MoldingSampleRequisition {
  id: string
  req_number: string
  date: string
  order_id: string
  order_number: string
  material: string
  requested_weight_kg: number | null
  applicant: string
  notes: string
  inventory_batch_id: string
  inventory_batch_no: string
  status: MoldingSampleRequisitionStatus
  issued_at: string
  created_at: string
  updated_at: string
}

export type MoldingSampleProblemStatus = '待处理' | '已解决'

export interface MoldingSampleProblem {
  id: string
  factory_id: string
  order_type: 'injection'
  order_id: string
  order_number: string
  description: string
  reported_by: string
  status: MoldingSampleProblemStatus
  created_at: string
  resolved_at: string
}

export interface MoldingSampleTrialReportData {
  mold_supplier: string
  sample_category: string
  material_name: string
  material_shots: string
  material_weight: string
  color: string
  color_code: string
  color_shots: string
  color_weight: string
  virgin_material_shots: string
  virgin_material_weight: string
  runner_material_shots: string
  runner_material_weight: string
  water_ratio: string
  water_shots: string
  water_material_weight: string
  water_weight: string
  special_requirements: string
  front_mold_water: string
  rear_mold_water: string
  other_trial_requirement: string
  other_trial_requirement_note: string
  baking_time_hours: string
  mold_condition: string
  expected_return_time: string
  gross_weight: string
  net_weight: string
  plastic_model: string
  machine_model: string
  machine_no: string
  cooling_time: string
  holding_time: string
  cycle_time: string
  injection_speed: string
  ejector_count: string
  cushion_pressure: string
  clamping_force: string
  high_pressure: string
  low_pressure: string
  pressure_stage_1: string
  pressure_stage_2: string
  pressure_stage_3: string
  pressure_stage_4: string
  barrel_temperature_head: string
  barrel_temperature_middle: string
  barrel_temperature_end: string
  molding_mode: string
  mold_issues: string[]
  part_issues: string[]
  issue_notes: string
  trial_summary: string
  trial_round: string
  verdict: string
  tester_name: string
  tester_date: string
  molding_supervisor_name: string
  molding_supervisor_date: string
  engineer_name: string
  engineer_date: string
}

export interface MoldingSampleTrialReport {
  id: string
  factory_id: string
  order_id: string
  item_id: string
  data: MoldingSampleTrialReportData
  created_by: string
  created_at: string
  updated_by: string
  updated_at: string
}

export interface MoldingSampleWorkflowRecord {
  factory_id: string
  order: MoldingSampleOrder
  items: MoldingSampleItem[]
  audit_logs: MoldingSampleAuditLog[]
  requisitions: MoldingSampleRequisition[]
  problems: MoldingSampleProblem[]
  trial_reports: MoldingSampleTrialReport[]
  access?: {
    read_source: 'local' | 'cross'
    can_view_cost: boolean
    read_only: boolean
  }
}
