import type { FeedbackStatus } from '@/api/moduleFeedback'
export const feedbackStatuses: Record<FeedbackStatus, string> = {
  submitted: '已提交', needs_info: '待补充', in_progress: '处理中', awaiting_verification: '待验证', resolved: '已解决',
}
export const feedbackMaterials: Record<string, string> = {
  screenshot: '问题截图', steps: '操作步骤', expected_result: '期望结果', original_file: '原始 PO / 排期文件', order_reference: '订单参考号',
}
export const feedbackEmojis = [
  { emoji: '🐞', label: '有问题', category: 'bug' }, { emoji: '🐢', label: '太慢', category: 'bug' },
  { emoji: '😕', label: '看不懂', category: 'question' }, { emoji: '💡', label: '有建议', category: 'suggestion' },
  { emoji: '👍', label: '好用', category: 'suggestion' },
] as const
