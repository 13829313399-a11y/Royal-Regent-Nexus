import type { ProductionFactoryContextId } from '@/data/enterpriseMock'

export type SchedulingViewMode = 'board' | 'timeline' | 'backlog'
export type MachineState = 'running' | 'risk' | 'urgent' | 'idle'
export type TaskRisk = 'normal' | 'warning' | 'overdue' | 'urgent'

export interface SchedulingKpi {
  label: string
  value: string
  detail: string
  tone: 'default' | 'teal' | 'amber' | 'red'
}

export interface ScheduleTask {
  id: string
  machineId: string
  moldNo: string
  productName: string
  orderNo: string
  color: string
  quantity: number
  completedQuantity: number
  dailyTarget: number
  startAt: string
  endAt: string
  dueLabel: string
  risk: TaskRisk
  sequence: number
  current: boolean
  locked: boolean
  remark?: string
}

export interface InjectionMachine {
  id: string
  name: string
  machineType: string
  tonnage: string
  capability: string
  armType: string
  restriction: string
  load: number
  state: MachineState
  taskIds: string[]
}

export interface CandidateMachine {
  machineId: string
  score: number
  title: string
  reasons: string[]
  warning?: string
}

export interface BacklogOrder {
  id: string
  moldNo: string
  productName: string
  orderNo: string
  color: string
  quantity: number
  dailyTarget: number
  requiredDate: string
  urgency: 'normal' | 'urgent'
  machineType: string
  candidates: CandidateMachine[]
}

export interface SchedulingSnapshot {
  factoryId: ProductionFactoryContextId
  sourceLabel: string
  snapshotAt: string
  notice: string
  kpis: SchedulingKpi[]
  machines: InjectionMachine[]
  tasks: ScheduleTask[]
  backlog: BacklogOrder[]
}

export interface ScheduleMoveRequest {
  taskId?: string
  backlogId?: string
  sourceMachineId?: string
  targetMachineId: string
}

export interface SchedulingFilters {
  search: string
  machineType: string
  state: string
  exceptionsOnly: boolean
}

