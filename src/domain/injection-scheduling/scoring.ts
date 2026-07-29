import { colorPathMultiplier, evaluateChangeover } from './changeover'
import { schedulingScoreWeights } from './config'
import { evaluateMachineEligibility } from './eligibility'
import type {
  CandidateMachine,
  InjectionMachine,
  OrderRequirement,
  ScheduleTask,
} from '@/types/injectionScheduling'

export function scoreCandidateMachine(input: {
  machine: InjectionMachine
  requirement: OrderRequirement
  dueAt: string
  previousTask?: ScheduleTask
  projectedEndAt: string
}): CandidateMachine | null {
  const eligibility = evaluateMachineEligibility({
    machine: input.machine,
    requirement: input.requirement,
  })
  if (!eligibility.eligible) return null

  const previous = input.previousTask?.requirement ?? null
  const changeover = evaluateChangeover(input.machine.capability.machineClass, previous, input.requirement)
  const hoursToDue = (new Date(input.dueAt).getTime() - new Date(input.projectedEndAt).getTime()) / 3_600_000
  const sameMold = previous?.mold.moldNo === input.requirement.mold.moldNo
  const sameMaterial = previous?.material === input.requirement.material
  const colorMultiplier = previous
    ? colorPathMultiplier(previous.colorFamily, input.requirement.colorFamily)
    : 0
  const breakdown = [
    {
      key: 'urgency',
      label: '人工优先级',
      score: input.requirement.priorityCode === 'P0'
        ? schedulingScoreWeights.urgency
        : input.requirement.priorityCode === 'P1' ? 18 : 8,
      reason: `${input.requirement.priorityCode} 优先级。`,
    },
    {
      key: 'due',
      label: '交期风险',
      score: hoursToDue < 0 ? schedulingScoreWeights.overdueRisk : Math.max(8, 22 - hoursToDue / 24),
      reason: hoursToDue < 0 ? `预计逾期 ${Math.abs(hoursToDue).toFixed(1)}h。` : `预计余量 ${hoursToDue.toFixed(1)}h。`,
    },
    {
      key: 'mold',
      label: '同模连续',
      score: sameMold ? schedulingScoreWeights.sameMold : 4,
      reason: sameMold ? '与队尾任务同模，可减少换模。' : '需要换模。',
    },
    {
      key: 'color',
      label: '颜色路径',
      score: colorMultiplier === 0
        ? schedulingScoreWeights.colorPath
        : Math.max(1, schedulingScoreWeights.colorPath - colorMultiplier * 4),
      reason: changeover.pathLabel,
    },
    {
      key: 'material',
      label: '材料连续',
      score: sameMaterial ? schedulingScoreWeights.sameMaterial : 2,
      reason: sameMaterial ? '材料连续，减少清机。' : '需要转料确认。',
    },
    {
      key: 'right-size',
      label: '机型适配',
      score: Math.max(1, schedulingScoreWeights.rightSizedMachine - Math.max(0, input.machine.load - 80) / 10),
      reason: `${input.machine.capability.machineClass} · 当前负荷 ${input.machine.load}%`,
    },
    {
      key: 'balance',
      label: '负荷均衡',
      score: Math.max(0, schedulingScoreWeights.loadBalance * (1 - input.machine.load / 100)),
      reason: `当前负荷 ${input.machine.load}%`,
    },
  ]
  const score = Math.max(0, Math.min(100, Math.round(
    breakdown.reduce((total, item) => total + item.score, 0),
  )))

  return {
    machineId: input.machine.id,
    score,
    title: sameMold ? '同模优先 · 低切换损失' : '硬约束全部通过',
    eligibility,
    breakdown,
    insertionLabel: `插入 ${input.machine.name} 队尾`,
    projectedEndAt: input.projectedEndAt,
    affectedTaskCount: 1,
    warning: changeover.status === 'missing-rule' ? changeover.reason : undefined,
  }
}
