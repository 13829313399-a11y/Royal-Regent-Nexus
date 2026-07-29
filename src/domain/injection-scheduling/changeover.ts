import {
  colorChangeHoursByMachineClass,
  colorFamilyRank,
  moldChangeHoursByMachineClass,
} from './config'
import type {
  ChangeoverCost,
  ColorFamily,
  MachineClass,
  OrderRequirement,
} from '@/types/injectionScheduling'

export function colorPathMultiplier(from: ColorFamily, to: ColorFamily) {
  if (from === to) return 0
  if (from === 'special' || to === 'special') return 1.6
  const direction = colorFamilyRank[to] - colorFamilyRank[from]
  return direction >= 0 ? 0.75 : 1.35
}

export function evaluateChangeover(
  machineClass: MachineClass,
  previous: OrderRequirement | null,
  next: OrderRequirement,
): ChangeoverCost {
  if (!previous) {
    return {
      status: 'ok',
      moldChangeHours: 0,
      colorChangeHours: 0,
      totalHours: 0,
      pathLabel: '首项任务',
      reason: '计划起点不计算与上一任务的切换损失。',
    }
  }

  const sameMold = previous.mold.moldNo === next.mold.moldNo
  const sameColor = previous.color === next.color
  if (sameMold && sameColor) {
    return {
      status: 'ok',
      moldChangeHours: 0,
      colorChangeHours: 0,
      totalHours: 0,
      pathLabel: '同模同色',
      reason: '模具和颜色均相同，无切换损失。',
    }
  }

  const moldRule = moldChangeHoursByMachineClass[machineClass]
  const colorRule = colorChangeHoursByMachineClass[machineClass]
  if ((!sameMold && moldRule === undefined) || (!sameColor && colorRule === undefined)) {
    return {
      status: 'missing-rule',
      moldChangeHours: 0,
      colorChangeHours: 0,
      totalHours: 0,
      pathLabel: `${machineClass} 缺少规则`,
      reason: `${machineClass} 未配置完整换模/转色时间，必须人工确认，不能按 0 小时通过。`,
    }
  }

  const moldChangeHours = sameMold ? 0 : (moldRule ?? 0)
  const colorChangeHours = sameColor
    ? 0
    : (colorRule ?? 0) * colorPathMultiplier(previous.colorFamily, next.colorFamily)
  const totalHours = moldChangeHours + colorChangeHours

  return {
    status: 'ok',
    moldChangeHours,
    colorChangeHours,
    totalHours,
    pathLabel: sameMold ? '同模异色' : sameColor ? '异模同色' : '异模异色',
    reason: `换模 ${moldChangeHours.toFixed(1)}h，转色 ${colorChangeHours.toFixed(1)}h。`,
  }
}
