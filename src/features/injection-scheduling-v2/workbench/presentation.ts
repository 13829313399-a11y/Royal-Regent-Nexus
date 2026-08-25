import type { Tone } from '@/data/enterpriseMock'
import type { WorkbenchJobStatus, WorkbenchMachine } from './types'

export interface WorkbenchPresentation {
  label: string
  tone: Tone
  className: string
}

const statusMap: Record<WorkbenchJobStatus, WorkbenchPresentation> = {
  UNPLANNED: { label: '待排', tone: 'slate', className: 'unplanned' },
  PLANNED: { label: '已排', tone: 'blue', className: 'planned' },
  RUNNING: { label: '生产中', tone: 'teal', className: 'running' },
  PAUSED: { label: '暂停', tone: 'amber', className: 'paused' },
  DONE: { label: '完成', tone: 'green', className: 'done' },
}

const priorityMap: Record<string, WorkbenchPresentation> = {
  NORMAL: { label: '普通', tone: 'slate', className: 'normal' },
  URGENT: { label: '急单', tone: 'amber', className: 'urgent' },
  CRITICAL: { label: '特急', tone: 'red', className: 'critical' },
}

const machineStatusMap: Record<string, WorkbenchPresentation> = {
  ACTIVE: { label: '可用', tone: 'green', className: 'available' },
  AVAILABLE: { label: '可用', tone: 'green', className: 'available' },
  MAINTENANCE: { label: '维护', tone: 'amber', className: 'maintenance' },
  DOWN: { label: '故障', tone: 'red', className: 'down' },
  DISABLED: { label: '受限', tone: 'slate', className: 'restricted' },
  INACTIVE: { label: '受限', tone: 'slate', className: 'restricted' },
}

export function statusPresentation(status: WorkbenchJobStatus) {
  return statusMap[status]
}

export function priorityPresentation(priority: string) {
  return priorityMap[priority.toUpperCase()] ?? {
    label: priority || '普通',
    tone: 'slate' as const,
    className: 'normal',
  }
}

export function dueSlackPresentation(days: number | null): WorkbenchPresentation {
  if (days == null) return { label: '交期待补', tone: 'slate', className: 'unknown' }
  if (days < 0) return { label: `逾期 ${Math.abs(days)} 天`, tone: 'red', className: 'overdue' }
  if (days === 0) return { label: '今日到期', tone: 'amber', className: 'due-today' }
  return { label: `余 ${days} 天`, tone: days <= 3 ? 'amber' : 'teal', className: 'remaining' }
}

export function machineStatusPresentation(machine: WorkbenchMachine) {
  if (!machine.availableForAutoSchedule) {
    const mapped = machineStatusMap[machine.status.toUpperCase()]
    return mapped && mapped.className !== 'available'
      ? mapped
      : { label: '受限', tone: 'amber' as const, className: 'restricted' }
  }
  return machineStatusMap[machine.status.toUpperCase()]
    ?? { label: '可用', tone: 'green' as const, className: 'available' }
}

export function formatAClass(value: number | null) {
  return value == null ? 'A级待补' : `${Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}A`
}

export function mappingStatusLabel(value: string) {
  return ({
    MAPPED: '已映射',
    LOW_CONFIDENCE: '低置信度',
    MISSING: '缺失',
    UNMAPPED: '待映射',
    AMBIGUOUS: '需确认',
  } as Record<string, string>)[value.toUpperCase()] ?? '需确认'
}
