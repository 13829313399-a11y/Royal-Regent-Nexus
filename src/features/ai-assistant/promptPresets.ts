import type { AIPageContext } from './types'

const GENERAL_PROMPTS = [
  '这个页面怎么用？',
  '请解释当前页面的主要操作。',
]

const SCHEDULING_PROMPTS = [
  '这个注塑排产页面怎么用？',
  '执行计划和规划草案有什么区别？',
  '如何查看当前页面的待排订单？',
]

const INTERNAL_QUOTE_PROMPTS = [
  '请列出最近更新的内部报价摘要。',
  '有哪些内部报价正在等待最终放行？',
  '请按报价编号或客户查找内部报价。',
]

export function suggestedPrompts(context: AIPageContext | null) {
  if (context?.module_id === 'injection-scheduling') return SCHEDULING_PROMPTS
  if (context?.module_id === 'internal-quote') return INTERNAL_QUOTE_PROMPTS
  return GENERAL_PROMPTS
}
