import type { MachineState, RobotArmType, TaskRisk } from '@/types/injectionScheduling'

export function formatScheduleTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Asia/Shanghai',
  }).format(date).replace('/', '-')
}

export function formatSlack(slackHours: number) {
  if (slackHours < 0) return `逾期 ${Math.abs(slackHours / 24).toFixed(1)}天`
  return `余量 +${(slackHours / 24).toFixed(1)}天`
}

export const armLabels: Record<RobotArmType, string> = {
  none: '无机械手',
  'single-arm': '单臂三轴',
  'multi-arm': '双臂五轴',
}

export const taskRiskMeta: Record<TaskRisk, { label: string; className: string }> = {
  normal: { label: '正常', className: 'text-teal-700 bg-teal-50' },
  warning: { label: '风险', className: 'text-amber-700 bg-amber-50' },
  overdue: { label: '逾期', className: 'text-red-700 bg-red-50' },
  urgent: { label: '特急', className: 'text-orange-700 bg-orange-50' },
  incomplete: { label: '资料不全', className: 'text-violet-700 bg-violet-50' },
}

export const machineStateMeta: Record<MachineState, { label: string; className: string }> = {
  running: { label: '生产中', className: 'text-teal-700 bg-teal-50' },
  risk: { label: '交期异常', className: 'text-red-700 bg-red-50' },
  urgent: { label: '特急任务', className: 'text-orange-700 bg-orange-50' },
  idle: { label: '空闲', className: 'text-slate-600 bg-slate-100' },
  maintenance: { label: '保养', className: 'text-amber-700 bg-amber-50' },
  fault: { label: '机故', className: 'text-red-700 bg-red-50' },
}
