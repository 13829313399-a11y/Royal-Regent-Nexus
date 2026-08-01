export type InjectionFactoryId =
  | 'huaxing'
  | 'huakang-a'
  | 'huakang-b'
  | 'huakang-c'
  | 'huakang-d'
  | 'huadeng'

export type SchedulingSourceMode = 'mock'
export type SchedulingTaskStatus = 'RUNNING' | 'QUEUED' | 'BLOCKED' | 'DONE'
export type SchedulingPriority = 'NORMAL' | 'URGENT' | 'CRITICAL'
export type FitDecision = 'PASS' | 'REVIEW_REQUIRED' | 'FAIL'
export type MachineArmCapability = '单臂' | '双臂'
export type WorkspaceView = 'board' | 'timeline'
export type WorkspaceStatusFilter = 'all' | 'running' | 'overdue' | 'dueSoon' | 'review'
export type WorkspaceDataQualityFilter = 'all' | 'complete' | 'missing'

export interface MachineDimensions {
  width: number
  height: number
}

export interface MoldDimensions {
  length: number
  width: number
  height: number
}

export interface InjectionMachine {
  id: string
  factoryId: InjectionFactoryId
  code: string
  zone: string
  machineClass: string
  tonnage: number
  shotCapacityGrams: number
  platen: MachineDimensions
  armCapability: MachineArmCapability
  machineType: string
  processNote: string
  loadPercent: number
}

export interface SchedulingTask {
  id: string
  factoryId: InjectionFactoryId
  machineId: string
  sequence: number
  status: SchedulingTaskStatus
  priority: SchedulingPriority
  originalMarker: string
  moldCode: string
  productName: string
  orderNo: string
  itemNo: string
  orderQuantity: number
  completedQuantity: number
  shiftTarget: number
  shiftCompleted: number
  downtimeHours: number
  exceptionType: string
  color: string
  colorHex: string
  material: string
  shotNetWeightGrams: number
  deliveryDate: string
  plannedStart: string
  plannedEnd: string
  slackDays: number
  armRequirement: MachineArmCapability
  fixtureRequirement: string
  moldDimensions: MoldDimensions | null
  warehouseOwner: string
  note: string
  fitDecision: FitDecision
  fitScore: number
  sourceRow: number | null
  revision: number
  updatedAt: string
}

export interface ConstraintCheck {
  key: 'mold-size' | 'shot-capacity' | 'robot-arm' | 'fixture' | 'process'
  label: string
  decision: FitDecision
  detail: string
}

export interface MachineCandidate {
  machineId: string
  machineCode: string
  rank: number
  score: number
  decision: FitDecision
  resultLabel: string
  explanation: string
  warning: string
  constraints: ConstraintCheck[]
}

export interface BacklogOrder {
  id: string
  factoryId: InjectionFactoryId
  orderNo: string
  itemNo: string
  moldCode: string
  productName: string
  quantity: number
  deliveryDate: string
  color: string
  material: string
  shotNetWeightGrams: number
  armRequirement: MachineArmCapability
  fixtureRequirement: string
  moldDimensions: MoldDimensions | null
  note: string
  candidates: MachineCandidate[]
  revision: number
}

export interface SchedulingSummary {
  availableMachines: number
  totalMachines: number
  scheduledTasks: number
  overdueTasks: number
  dueSoonTasks: number
  remainingQuantity: number
  moldDimensionCompleteness: number
  backlogOrders: number
}

export interface InjectionSchedulingSnapshot {
  factoryId: InjectionFactoryId
  factoryName: string
  sourceMode: SchedulingSourceMode
  sourceLabel: string
  planVersion: string
  generatedAt: string
  machines: InjectionMachine[]
  tasks: SchedulingTask[]
  backlogOrders: BacklogOrder[]
  summary: SchedulingSummary
}

export interface ShiftReportInput {
  shiftCompleted: number
  cumulativeCompleted: number
  shiftTarget: number
  downtimeHours: number
  exceptionType: string
  status: SchedulingTaskStatus
  remark: string
}

export interface TaskReportDraft extends ShiftReportInput {
  taskId: string
  expectedRevision: number
}

export interface SaveShiftReportResult {
  task: SchedulingTask
  auditMessage: string
}

export interface AssignBacklogResult {
  backlogOrder: BacklogOrder
  auditMessage: string
}
