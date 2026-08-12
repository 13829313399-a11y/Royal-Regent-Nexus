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

const MOLDING_SAMPLE_PROMPTS = [
  '请列出最近更新的啤办任务摘要。',
  '请查找当前厂区待处理的啤办任务。',
  '请按任务编号、产品或客户查找啤办任务。',
]

const CARTON_PROCUREMENT_PROMPTS = [
  '请列出最近更新的纸箱采购订单摘要。',
  '当前有哪些纸箱采购订单临近交期？',
  '请按订单号、客户、合同或货号查找纸箱采购订单。',
]

const RAW_MATERIAL_PROMPTS = [
  '请查找原料主数据摘要。',
  '请列出当前厂区有库存的原料批次。',
  '哪些原料批次的可用重量较低？',
]

const CUSTOMER_ORDER_PROMPTS = [
  '当前厂区支持哪些客户订单预览与导出能力？',
  '请列出最近的客户订单导出审计摘要。',
  '这里能否提供官方订单总数？',
]

export function suggestedPrompts(context: AIPageContext | null) {
  if (context?.module_id === 'injection-scheduling') return SCHEDULING_PROMPTS
  if (context?.module_id === 'internal-quote') return INTERNAL_QUOTE_PROMPTS
  if (context?.module_id === 'molding-sample') return MOLDING_SAMPLE_PROMPTS
  if (context?.module_id === 'carton-procurement') return CARTON_PROCUREMENT_PROMPTS
  if (context?.module_id === 'raw-material') return RAW_MATERIAL_PROMPTS
  if (context?.module_id === 'customer-order') return CUSTOMER_ORDER_PROMPTS
  return GENERAL_PROMPTS
}
