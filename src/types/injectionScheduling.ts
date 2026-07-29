import type { ProductionFactoryContextId } from '@/data/enterpriseMock'

export type SchedulingViewMode = 'board' | 'timeline'
export type SchedulingDensity = 'compact' | 'comfortable'
export type MachineState = 'running' | 'risk' | 'urgent' | 'idle' | 'maintenance' | 'fault'
export type TaskRisk = 'normal' | 'warning' | 'overdue' | 'urgent' | 'incomplete'
export type MachineClass =
  | '4A'
  | '5A'
  | '7A'
  | '10A'
  | '12A'
  | '14A'
  | '18A'
  | '24A'
  | '32A'
  | '50A'
  | '60A'
  | '80A'
  | '104A'
  | '120A'
export type RobotArmType = 'none' | 'single-arm' | 'multi-arm'
export type ResourceState = 'available' | 'warning' | 'blocked'
export type PriorityCode = 'P0' | 'P1' | 'P2' | 'P3'
export type ColorFamily = 'natural' | 'light' | 'medium' | 'dark' | 'black' | 'special'

export interface SchedulingKpi {
  label: string
  value: string
  detail: string
  tone: 'default' | 'teal' | 'amber' | 'red' | 'violet'
  action?: 'backlog' | 'alerts'
}

export interface MachineCapability {
  machineClass: MachineClass
  tonnage: number
  shotCapacityGrams: number
  safetyUtilization: number
  tieBarWidthMm: number
  tieBarHeightMm: number
  minMoldThicknessMm: number
  maxMoldThicknessMm: number
  openingStrokeMm: number
  ejectionStrokeMm: number
  armType: RobotArmType
  supportsCorePull: boolean
  supportsUnscrewing: boolean
  compatibleMaterials: string[]
  screwType: 'standard' | 'PVC' | 'PC' | 'transparent'
  transparentOnly?: boolean
}

export interface MoldSpecification {
  moldNo: string
  widthMm?: number
  heightMm?: number
  thicknessMm?: number
  openingStrokeMm?: number
  ejectionStrokeMm?: number
  shotWeightGrams?: number
  material?: string
  armRequirement?: RobotArmType
  requiresCorePull?: boolean
  requiresUnscrewing?: boolean
  state: ResourceState
}

export interface OrderRequirement {
  productName: string
  orderNo: string
  itemNo?: string
  color: string
  colorFamily: ColorFamily
  material: string
  mold: MoldSpecification
  priorityCode: PriorityCode
  priorityFlag?: string
}

export interface ProductionProgress {
  orderQuantity: number
  completedQuantity: number
  remainingQuantity: number
  effectiveDailyTarget: number
  productionDurationHours: number
}

export interface ScheduleTiming {
  plannedStart: string
  plannedEnd: string
  inboundAt: string
  deliveryDueAt: string
  slackHours: number
}

export interface ChangeoverCost {
  status: 'ok' | 'missing-rule'
  moldChangeHours: number
  colorChangeHours: number
  totalHours: number
  pathLabel: string
  reason: string
}

export interface ScheduleTask {
  id: string
  machineId: string
  requirement: OrderRequirement
  production: ProductionProgress
  timing: ScheduleTiming
  changeover: ChangeoverCost
  sequence: number
  current: boolean
  locked: boolean
  risk: TaskRisk
  remark?: string
}

export interface InjectionMachine {
  id: string
  name: string
  code: string
  workshop: string
  kind: '普通机' | '高速机' | '全电动'
  capability: MachineCapability
  restriction: string
  load: number
  state: MachineState
  resourceState: ResourceState
  taskIds: string[]
}

export interface EligibilityCheck {
  code: string
  label: string
  passed: boolean
  severity: 'hard' | 'warning'
  expected?: string
  actual?: string
  reason: string
}

export interface EligibilityResult {
  eligible: boolean
  complete: boolean
  status: 'eligible' | 'ineligible' | 'incomplete'
  checks: EligibilityCheck[]
}

export interface CandidateScoreBreakdown {
  key: string
  label: string
  score: number
  reason: string
}

export interface CandidateMachine {
  machineId: string
  score: number
  title: string
  eligibility: EligibilityResult
  breakdown: CandidateScoreBreakdown[]
  insertionLabel: string
  projectedEndAt: string
  affectedTaskCount: number
  warning?: string
}

export interface BacklogOrder {
  id: string
  requirement: OrderRequirement
  production: ProductionProgress
  requiredDate: string
  candidates: CandidateMachine[]
  noMatchReason?: string
}

export interface ProductionWindow {
  startAt: string
  endAt: string
  label: string
}

export interface ProductionCalendar {
  timezone: string
  availabilityWindows: ProductionWindow[]
  downtimeWindows: ProductionWindow[]
}

export interface SchedulePlanVersion {
  id: string
  label: string
  revision: number
  rulesVersion: string
  status: 'draft' | 'published'
  anchorAt: string
  publishedAt?: string
}

export interface SchedulingMetrics {
  overdueTaskCount: number
  totalOverdueHours: number
  moldChangeCount: number
  colorChangeCount: number
  utilizationPercent: number
  movedTaskCount: number
  manualReviewCount: number
}

export interface SchedulingSimulationResult {
  before: SchedulingMetrics
  after: SchedulingMetrics
  steps: Array<{ code: string; label: string; detail: string }>
  proposedTaskOrderByMachine: Record<string, string[]>
}

export interface SchedulingSnapshot {
  factoryId: ProductionFactoryContextId
  sourceLabel: string
  snapshotAt: string
  notice: string
  plan: SchedulePlanVersion
  calendar: ProductionCalendar
  kpis: SchedulingKpi[]
  machines: InjectionMachine[]
  tasks: ScheduleTask[]
  backlog: BacklogOrder[]
}

export interface ScheduleMoveRequest {
  factoryId: ProductionFactoryContextId
  revision: number
  taskId?: string
  backlogId?: string
  sourceMachineId?: string
  targetMachineId: string
  targetIndex?: number
}

export interface MoveValidation {
  allowed: boolean
  eligibility?: EligibilityResult
  reasons: string[]
  affectedTaskCount: number
}

export interface SchedulingFilters {
  search: string
  machineClass: string
  state: string
  exceptionsOnly: boolean
}
