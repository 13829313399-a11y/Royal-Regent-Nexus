import type { CellDraft, EditableCellKey } from '../types'

const planEditKeys = new Set<EditableCellKey>([
  'status',
  'targetQuantity',
  'plannedStart',
  'plannedFinish',
])
const reportEditKeys = new Set<EditableCellKey>([
  'status',
  'targetQuantity',
  'shiftCompleted',
  'completedQuantity',
  'downtime',
  'exception',
])
const orderEditKeys = new Set<EditableCellKey>(['warehouse', 'remark'])

export function cellDraftKey(taskId: string, key: EditableCellKey) {
  return `${taskId}:${key}`
}

export function isPlanEdit(key: EditableCellKey, planStatus: string) {
  return planStatus === 'DRAFT' && planEditKeys.has(key)
}

export function isReportEdit(key: EditableCellKey, planStatus: string) {
  return planStatus === 'PUBLISHED' && reportEditKeys.has(key)
}

export function isOrderEdit(key: EditableCellKey) {
  return orderEditKeys.has(key)
}

export function normalizeCellValue(key: EditableCellKey, value: string | number) {
  if (['targetQuantity', 'shiftCompleted', 'completedQuantity', 'downtime'].includes(key)) {
    const numeric = typeof value === 'number' ? value : Number(value)
    return Number.isFinite(numeric) ? Math.max(0, numeric) : 0
  }
  return String(value).trim()
}

export function resolveReportedQuantity(
  drafts: CellDraft[],
  taskReportedQuantity: number,
  sourceCompletedQuantity: number,
) {
  const completedDraft = drafts.find((draft) => draft.key === 'completedQuantity')
  if (completedDraft) return Math.max(0, Number(completedDraft.value) - sourceCompletedQuantity)
  const taskDraft = drafts.find((draft) => draft.key === 'shiftCompleted')
  return Number(taskDraft?.value ?? taskReportedQuantity)
}
