import type { Tone } from '@/data/enterpriseMock'

export type InjectionSectionId =
  | 'monthly-plan'
  | 'order-import'
  | 'smart-scheduling'
  | 'scheduling-results'
  | 'daily-report'
  | 'inbound-orders'
  | 'master-data'

export interface InjectionMetric {
  label: string
  value: string
  detail: string
  tone: Tone
}

export interface ShiftSummary {
  shift: string
  date: string
  completion: number
  machineRunning: string
  carryOver: string
  alert: string
}

export interface MachineLoad {
  machine: string
  utilization: number
  mold: string
  material: string
  tone: Tone
  queueDepth: string
}

export interface ColorTransitionRisk {
  machine: string
  route: string[]
  risk: string
  tone: Tone
}

export interface DataSourceStatus {
  name: string
  freshness: string
  status: string
  statusTone: Tone
  summary: string
}

export interface ExecutionTask {
  title: string
  meta: string
  tone: Tone
}

export interface InjectionStage {
  title: string
  owner: string
  detail: string
  state: 'done' | 'active' | 'pending'
}

export interface InjectionNavItem {
  id: InjectionSectionId
  label: string
  summary: string
}

export interface DataCenterDataset {
  name: string
  owner: string
  freshness: string
  completeness: number
  status: string
  statusTone: Tone
  summary: string
  issues: string[]
}

export interface OrderSnapshotRow {
  orderNo: string
  productCode: string
  moldName: string
  color: string
  material: string
  quantity: string
  due: string
  state: string
  tone: Tone
}

export interface MachineProfileRow {
  machine: string
  tonnage: string
  armType: string
  workshop: string
  status: string
  tone: Tone
  fit: string
}

export interface MoldTargetRow {
  moldCode: string
  target24h: string
  target11h: string
  source: string
  health: string
  tone: Tone
}

export interface ExecutionOrderRow {
  machine: string
  orderNo: string
  moldName: string
  color: string
  target24h: string
  shortage: string
  priority: string
  tone: Tone
}

export interface ExecutionRuleMetric {
  label: string
  value: string
  detail: string
  tone: Tone
}

export interface ExecutionConstraintRow {
  machine: string
  workshop: string
  tonnage: string
  robot: string
  limit: string
  action: string
  tone: Tone
}

export interface ExecutionCandidateRow {
  orderNo: string
  moldCode: string
  recommendedMachine: string
  backupMachine: string
  reason: string
  blocker: string
  tone: Tone
}

export interface ExecutionScheduleRow {
  orderNo: string
  machine: string
  startWindow: string
  endWindow: string
  shiftPlan: string
  expectedOutput: string
  dependency: string
  tone: Tone
}

export interface ManualActionRow {
  title: string
  reason: string
  owner: string
  action: string
  tone: Tone
}

export interface ReportingMetric {
  label: string
  value: string
  detail: string
  tone: Tone
}

export interface ShiftReportRow {
  machine: string
  worker: string
  target11h: string
  actual: string
  variance: string
  downtime: string
  tone: Tone
}

export interface ShiftReportTemplateField {
  label: string
  required: boolean
  source: string
  summary: string
}

export interface ShiftReportTemplateGroup {
  title: string
  owner: string
  fields: ShiftReportTemplateField[]
}

export interface ShiftReportImportMappingRow {
  sourceColumn: string
  targetField: string
  required: boolean
  sample: string
  rule: string
  tone: Tone
}

export interface WarehouseInboundRow {
  deliveryCode: string
  orderNo: string
  shots: string
  materialKg: string
  pmc: string
  status: string
  tone: Tone
}

export interface WritebackRuleCard {
  title: string
  owner: string
  trigger: string
  summary: string
  status: string
  tone: Tone
  items: string[]
}

export interface WritebackKeyMatchRow {
  stage: string
  businessKey: string
  sourceKey: string
  targetRecord: string
  status: string
  blocker: string
  tone: Tone
}

export interface ConfigRuleCard {
  title: string
  owner: string
  summary: string
  status: string
  tone: Tone
  items: string[]
}

export interface PendingOrderField {
  label: string
  required: boolean
  source: string
  summary: string
}

export interface PendingOrderFieldGroup {
  title: string
  owner: string
  fields: PendingOrderField[]
}

export interface PendingOrderValidationRule {
  label: string
  hit: string
  detail: string
  tone: Tone
}

export interface OrderImportTask {
  step: string
  owner: string
  status: string
  detail: string
  tone: Tone
}

export interface PendingOrderDetailRow {
  orderNo: string
  customer: string
  productName: string
  moldCode: string
  color: string
  material: string
  quantity: string
  dueDate: string
  cavity: string
  unitWeight: string
  source: string
  planner: string
  machineAdvice: string
  machineModel?: string
  armType?: string
  remark?: string
  moldSize?: string
  issue: string
  tone: Tone
}

export interface MachineMasterRow {
  machine: string
  tonnage: string
  screw: string
  robot: string
  workshop: string
  processRange: string
  colorPolicy: string
  activeMolds: string
  maintenance: string
  status: string
  tone: Tone
}

export interface MoldTargetDetailRow {
  customer: string
  catalogStatus: string
  moldCode: string
  productName: string
  cavity: string
  cycleTime: string
  target24h: string
  target11h: string
  preferredMachine: string
  source: string
  lastVerified: string
  health: string
  tone: Tone
}

export interface MoldMachineMappingRow {
  moldCode: string
  customer: string
  productName: string
  candidatePool: string
  recommendedMachine: string
  backupMachine: string
  status: string
  detail: string
  tone: Tone
}

export interface ShiftReportChecklistItem {
  title: string
  owner: string
  status: string
  detail: string
  tone: Tone
}

export interface ShiftHandoverRow {
  shift: string
  machine: string
  orderNo: string
  carryOverQty: string
  nextOwner: string
  note: string
  tone: Tone
}

export interface InboundWritebackRow {
  deliveryCode: string
  orderNo: string
  inboundQty: string
  shortageAfter: string
  warehouseStatus: string
  erpStatus: string
  schedulerStatus: string
  owner: string
  tone: Tone
}

export interface InjectionModuleData {
  sectionNav: InjectionNavItem[]
  overviewMetrics: InjectionMetric[]
  shiftSummaries: ShiftSummary[]
  machineLoad: MachineLoad[]
  colorTransitionRisks: ColorTransitionRisk[]
  dataSourceStatus: DataSourceStatus[]
  executionTasks: ExecutionTask[]
  workflowStages: InjectionStage[]
  dataCenterDatasets: DataCenterDataset[]
  orderSnapshotRows: OrderSnapshotRow[]
  machineProfileRows: MachineProfileRow[]
  moldTargetRows: MoldTargetRow[]
  executionQueueRows: ExecutionOrderRow[]
  executionRuleMetrics: ExecutionRuleMetric[]
  executionConstraintRows: ExecutionConstraintRow[]
  executionCandidateRows: ExecutionCandidateRow[]
  executionScheduleRows: ExecutionScheduleRow[]
  manualActionRows: ManualActionRow[]
  reportingMetrics: ReportingMetric[]
  shiftReportRows: ShiftReportRow[]
  shiftReportTemplateGroups: ShiftReportTemplateGroup[]
  shiftReportImportMappingRows: ShiftReportImportMappingRow[]
  warehouseInboundRows: WarehouseInboundRow[]
  writebackRuleCards: WritebackRuleCard[]
  writebackKeyMatchRows: WritebackKeyMatchRow[]
  configRuleCards: ConfigRuleCard[]
  pendingOrderFieldGroups: PendingOrderFieldGroup[]
  pendingOrderValidationRules: PendingOrderValidationRule[]
  orderImportTasks: OrderImportTask[]
  pendingOrderDetailRows: PendingOrderDetailRow[]
  machineMasterRows: MachineMasterRow[]
  moldTargetDetailRows: MoldTargetDetailRow[]
  moldMachineMappingRows: MoldMachineMappingRow[]
  shiftReportChecklistItems: ShiftReportChecklistItem[]
  shiftHandoverRows: ShiftHandoverRow[]
  inboundWritebackRows: InboundWritebackRow[]
}

export const injectionSectionNav: InjectionNavItem[] = [
  {
    id: 'monthly-plan',
    label: '月计划',
    summary: '先看本月待排、交期风险、班次节奏和重点异常。',
  },
  {
    id: 'order-import',
    label: '订单导入',
    summary: '把真实待排订单导入、校验并放进订单池。',
  },
  {
    id: 'smart-scheduling',
    label: '智能排机',
    summary: '看规则、候选机台和智能排机建议。',
  },
  {
    id: 'scheduling-results',
    label: '排机结果',
    summary: '查看开机时段、机台负载和颜色切换风险。',
  },
  {
    id: 'daily-report',
    label: '日报表',
    summary: '承接班次日报、交接和停机闭环。',
  },
  {
    id: 'inbound-orders',
    label: '入库单',
    summary: '跟踪送货单、入库状态和回写结果。',
  },
  {
    id: 'master-data',
    label: '基础资料',
    summary: '统一机台档案、模具目标、映射关系和历史数据健康度。',
  },
]

export const injectionPendingOrderFieldGroups: PendingOrderFieldGroup[] = [
  {
    title: '订单识别字段',
    owner: '文员 / 计划',
    fields: [
      { label: '单号', required: true, source: 'PDF / Excel', summary: '排产、入库、回写三端统一主键。' },
      { label: '客户 / 款号', required: true, source: '订单主表', summary: '区分业务优先级和同款合并。' },
      { label: '产品编码', required: true, source: 'ERP', summary: '关联模具、BOM 与历史命中。' },
      { label: '交期', required: true, source: '业务下单', summary: '决定待排优先级和插单判断。' },
    ],
  },
  {
    title: '工艺匹配字段',
    owner: '工程 / 生产',
    fields: [
      { label: '模具编码', required: true, source: '模具台账', summary: '用于同模同机和目标产能计算。' },
      { label: '穴数', required: true, source: '模具台账', summary: '影响单班产出和欠数折算。' },
      { label: '单位啤重', required: true, source: '历史数据库', summary: '用于机台适配和材料损耗估算。' },
      { label: '颜色 / 色粉号', required: true, source: '生产单', summary: '用于颜色切换顺序判断。' },
      { label: '料型', required: true, source: 'BOM', summary: '用于工艺限制和特殊机台筛选。' },
    ],
  },
  {
    title: '排程执行字段',
    owner: '计划员',
    fields: [
      { label: '待排数量', required: true, source: '业务欠数', summary: '决定本轮排机欠数。' },
      { label: '结转标记', required: true, source: '上一班回报', summary: '是否锁原机台延续。' },
      { label: '建议机台', required: false, source: '历史学习', summary: '给智能排机初步命中。' },
      { label: '插单等级', required: false, source: 'PMC / 业务', summary: '重点插单可提高优先级。' },
    ],
  },
]
