import type { OrderData } from './ordersApi'

const beijingClock = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
})

export function orderHistoryTime(value: string): string {
  const instant = new Date(value)
  return value && Number.isFinite(instant.getTime()) ? `${beijingClock.format(instant)}（北京时间）` : '时间未记录'
}

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
