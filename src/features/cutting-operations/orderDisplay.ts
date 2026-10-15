import type { OrderData } from './ordersApi'

/** Display only the product name frozen in this order snapshot. */
export function orderProductName(order: OrderData['order']): string {
  for (const key of ['product_name_zh', 'product_name_en']) {
    const value = order[key]
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return '未填写'
}

// The business dispatch contract currently has no ordinary/rare classification.
export const unclassifiedStyle = '未分类'
export const unclassifiedStyleHint = '业务订单尚未提供普通款／稀有款分类'
