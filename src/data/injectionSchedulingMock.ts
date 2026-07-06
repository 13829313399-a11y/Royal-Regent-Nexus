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
  productCode?: string
  color: string
  colorPowder?: string
  material: string
  quantity: string
  orderQuantity?: string
  producedQuantity?: string
  shortageQuantity?: string
  planTarget?: string
  dueDate: string
  cavity: string
  unitWeight: string
  netWeight?: string
  remainingMaterialKg?: string
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
    label: '驾驶舱',
    summary: '总览待排、结转、机台负载、交期风险和重点异常。',
  },
  {
    id: 'smart-scheduling',
    label: '排机工作台',
    summary: '导入订单、查看智能待排明细、人工确认机台并提交主管审核。',
  },
  {
    id: 'daily-report',
    label: '日报回报',
    summary: '啤机部文员按已排机模号填写产量、停机、欠数和结转交接。',
  },
  {
    id: 'inbound-orders',
    label: '入库回写',
    summary: '确认入库数量，刷新欠数、ERP 状态和订单池。',
  },
  {
    id: 'master-data',
    label: '基础资料',
    summary: '查看机台档案、工艺范围、保养和当前状态。',
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
