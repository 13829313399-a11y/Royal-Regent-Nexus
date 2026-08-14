import type { AITaskState, AITaskSummary } from '@/api/aiTasks'
import type { AIActionConfirmationStatus, AIBusinessResult } from '@/features/ai-assistant/types'

export interface ConversationRuntimeStatus {
  taskCount: number
  taskState: AITaskState | null
  taskLabel: string
  actionCount: number
  actionState: AIActionConfirmationStatus | null
  actionLabel: string
}

const taskPriority: AITaskState[] = [
  'FAILED', 'WAITING_APPROVAL', 'WAITING_INPUT', 'RETRY_PENDING', 'RUNNING',
  'VERIFYING', 'CANCELLING', 'PLANNED', 'UNDERSTOOD', 'CREATED',
  'COMPLETED', 'CANCELLED',
]
const taskLabels: Record<AITaskState, string> = {
  CREATED: '任务已创建', UNDERSTOOD: '任务已理解', PLANNED: '任务已规划',
  RUNNING: '任务运行中', WAITING_INPUT: '任务待补充', WAITING_APPROVAL: '任务待确认',
  VERIFYING: '任务验证中', COMPLETED: '任务已完成', CANCELLING: '任务取消中',
  CANCELLED: '任务已取消', FAILED: '任务失败', RETRY_PENDING: '任务待重试',
}
const actionPriority: AIActionConfirmationStatus[] = [
  'FAILED', 'STALE', 'PENDING', 'CONFIRMED', 'EXPIRED', 'EXECUTED', 'CANCELLED',
]
const actionLabels: Record<AIActionConfirmationStatus, string> = {
  PENDING: '待确认操作', CONFIRMED: '操作待执行', EXECUTED: '操作已执行',
  EXPIRED: '操作已过期', CANCELLED: '操作已取消', STALE: '操作已失效', FAILED: '操作失败',
}

function highestPriority<T extends string>(states: T[], priority: T[]) {
  return priority.find((state) => states.includes(state)) ?? null
}

export function summarizeConversationRuntime(
  conversationId: string,
  tasks: readonly AITaskSummary[],
  results: readonly AIBusinessResult[],
): ConversationRuntimeStatus {
  const conversationTasks = tasks.filter((task) => task.conversation_id === conversationId)
  const actions = results
    .filter((result) => result.kind === 'action_confirmation')
    .map((result) => result.actionConfirmation?.status)
    .filter((state): state is AIActionConfirmationStatus => Boolean(state))
  const taskState = highestPriority(conversationTasks.map((task) => task.state), taskPriority)
  const actionState = highestPriority(actions, actionPriority)
  return {
    taskCount: conversationTasks.length,
    taskState,
    taskLabel: taskState ? taskLabels[taskState] : '',
    actionCount: actions.length,
    actionState,
    actionLabel: actionState ? actionLabels[actionState] : '',
  }
}
