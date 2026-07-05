import type { Tone } from '@/data/enterpriseMock'

export type SchedulingEngineMode = 'frontend-mvp' | 'backend-service'

export interface SchedulingEngineOrder {
  orderNo: string
  moldCode: string
  productName?: string
  color?: string
  material?: string
  quantity?: string
  dueDate?: string
  machineAdvice?: string
  machineModel?: string
  armType?: string
  remark?: string
}

export interface SchedulingEngineMachine {
  machine: string
  tonnage: string
  robot: string
  workshop: string
  processRange: string
  colorPolicy: string
  status: string
}

export interface SchedulingEngineMoldMapping {
  moldCode: string
  recommendedMachine: string
  backupMachine: string
}

export interface SchedulingEngineInput {
  mode: SchedulingEngineMode
  orders: SchedulingEngineOrder[]
  machines: SchedulingEngineMachine[]
  moldMachineMappings: SchedulingEngineMoldMapping[]
}

export interface SchedulingEngineRecommendation {
  orderNo: string
  moldCode: string
  selectedMachine: string
  machineOptions: string[]
  reason: string
  blocker: string
  tone: Tone
}

export interface SchedulingEngineResult {
  recommendations: SchedulingEngineRecommendation[]
  warnings: string[]
}

export const schedulingEngineContractVersion = 'injection-scheduling-contract-v1'
