import type { FactoryId } from '../types'

export type WorkbenchFactoryId = FactoryId
export type WorkbenchJobStatus = 'UNPLANNED' | 'PLANNED' | 'RUNNING' | 'PAUSED' | 'DONE'
export type WorkbenchView = 'sheet' | 'queue'
export type WorkbenchColumnPreset = 'scheduler' | 'reporter' | 'full'
export type WorkbenchEditableField =
  | 'status'
  | 'shiftTargetQuantity'
  | 'plannedStart'
  | 'plannedFinish'
  | 'locked'
  | 'manualOverrideReason'
  | 'warehouseText'
  | 'orderRemark'

export interface WorkbenchMachine {
  id: string
  factoryId: string
  code: string
  position: string
  area: string
  aClass: number | null
  tonnage: number | null
  armCapabilities: string[]
  fixtureCapabilities: string[]
  processRestrictions: string[]
  status: string
  availableForAutoSchedule: boolean
  remark: string
  parsedConstraintSummary: string
  revision: number
}

export interface WorkbenchJob {
  id: string
  factoryId: string
  planId: string | null
  taskId: string | null
  orderId: string
  machineId: string | null
  machineCode: string
  sequenceNo: number | null
  status: WorkbenchJobStatus
  orderNo: string
  itemNo: string
  productName: string
  warehouseText: string
  setQuantity: number | null
  orderQuantity: number
  openingCompletedQuantity: number
  reportedQuantity: number
  completedQuantity: number
  outstandingQuantity: number
  completionRate: number
  moldId: string | null
  moldNo: string
  moldName: string
  requiredMachineA: number | null
  materialName: string
  sprueRatio: number | null
  colorName: string
  colorPowderCode: string
  netWeightG: number | null
  grossWeightG: number | null
  materialWeightKg: number | null
  unitPrice: number | null
  sprayRequired: boolean | null
  armRequirement: string
  fixtureRequirement: string
  orderDate: string
  deliveryStartDate: string
  deliveryDueDate: string
  priority: string
  plannedStart: string
  plannedFinish: string
  estimatedFinish: string
  deliverySlackDays: number | null
  shiftTargetQuantity: number
  todayDayQuantity: number
  todayNightQuantity: number
  downtimeMinutes: number
  locked: boolean
  manualOverrideReason: string
  orderRemark: string
  machineRemark: string
  parsedConstraintSummary: string
  suggestionReason: string
  materialReadinessStatus: string
  moldEnrichmentStatus: string
  sourceBatchId: string | null
  sourceSheetName: string
  sourceRowNumber: number | null
  sourceLineKey: string
  taskRevision: number | null
  orderRevision: number
  planRevision: number | null
  updatedByName: string
  updatedAt: string
  lineage: Record<string, unknown>
}

export interface WorkbenchSummary {
  unplannedCount: number
  overdueCount: number
  conflictCount: number
  runningCount: number
  todayDayQuantity: number
  todayNightQuantity: number
}

export interface WorkbenchSnapshot {
  factoryId: string
  businessDate: string
  planId: string | null
  planRevision: number | null
  ruleRevision: number | null
  planMode: 'PLANNING' | 'EXECUTION' | 'EMPTY'
  pollingRevision: number
  machines: WorkbenchMachine[]
  jobs: WorkbenchJob[]
  summary: WorkbenchSummary
}

export interface WorkbenchCellChange {
  jobId: string
  expectedTaskRevision: number | null
  expectedOrderRevision: number
  field: WorkbenchEditableField
  value: string | number | boolean
}

export interface WorkbenchColumn {
  key: keyof WorkbenchJob
  label: string
  width: number
  editable?: WorkbenchEditableField
  format?: 'number' | 'decimal' | 'percent' | 'date' | 'datetime' | 'status' | 'boolean'
  frozen?: boolean
}

export interface ShiftReportInput {
  shiftCode: 'DAY' | 'NIGHT'
  quantity: number
  targetQuantity: number
  downtimeMinutes: number
  exceptionCode: string
  exceptionDetail: string
  reportedStatus: 'QUEUED' | 'RUNNING' | 'BLOCKED' | 'COMPLETED'
}

export interface SchedulePreview {
  id: string
  solverType: string
  assignmentCount: number
  unscheduledCount: number
  warningCount: number
  objectiveScore: number
  raw: Record<string, unknown>
}
