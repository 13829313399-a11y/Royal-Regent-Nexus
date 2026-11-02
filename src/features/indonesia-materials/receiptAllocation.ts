import type { Data } from '@/api/indonesiaMaterials'
import { quantity } from './warehouseMatching'
import { referenceNumber } from './receiptSummary'

export const allocationKey = (plan: Data) => JSON.stringify([plan.order_id, plan.demand_id])
export function quantityText(value: bigint) {
  const text = value.toString().padStart(9, '0')
  return `${text.slice(0, -8)}.${text.slice(-8)}`.replace(/\.?0+$/, '') || '0'
}
export function dueDate(target: Data) { return target.required_date || target.delivery_date || '9999-12-31' }
export function sortedTargets(targets: Data[]) {
  return [...targets].sort((a, b) => {
    for (const key of ['priority', 'contract_no', 'po_no', 'item_no', 'order_id', 'demand_id']) {
      const left = String(key === 'priority' ? dueDate(a) : a[key] || ''), right = String(key === 'priority' ? dueDate(b) : b[key] || '')
      if (left !== right) return left < right ? -1 : 1
    }
    return 0
  })
}
export function additionalReservations(plans: Data[], originals: Data[]) {
  if (!originals.length) return plans
  return plans.map(plan => {
    const previous = originals.filter(old => allocationKey(old) === allocationKey(plan))
      .reduce((sum, old) => sum + (quantity(old.normal_quantity) || 0n) + (quantity(old.spare_quantity) || 0n), 0n)
    const normal = quantity(plan.normal_quantity), spare = quantity(plan.spare_quantity)
    if (normal === null || spare === null) return plan
    // Existing allocations are already subtracted by the server; reserve only any proposed increase.
    const increase = normal + spare - previous
    return { ...plan, normal_quantity: quantityText(increase > 0n ? increase : 0n), spare_quantity: '0' }
  })
}
/** Proposals only: the command rechecks versions, source totals and capacities under the factory lock. */
export function suggestAllocations(source: Data, targets: Data[], otherPlans: Data[], limit = 100): Data[] {
  let normal = quantity(source.normal_quantity), spare = quantity(source.spare_quantity)
  if (normal === null || spare === null) return []
  const reserved = new Map<string, bigint>(), invalid = new Set<string>()
  for (const plan of otherPlans) {
    if (!plan.order_id) continue
    const key = allocationKey(plan), n = quantity(plan.normal_quantity), s = quantity(plan.spare_quantity)
    if (n === null || s === null) invalid.add(key)
    else reserved.set(key, (reserved.get(key) || 0n) + n + s)
  }
  const plans: Data[] = []
  for (const target of sortedTargets(targets)) {
    if ((!normal && !spare) || plans.length >= Math.max(0, Math.min(100, limit))) break
    const key = allocationKey(target), reference = referenceNumber(target.remaining)
    if (reference === null || invalid.has(key)) continue
    // Receipt inputs have eight decimal places: never round capacity up.
    let capacity = reference / 100000000n - (reserved.get(key) || 0n)
    if (capacity <= 0n) continue
    const n = normal < capacity ? normal : capacity
    normal -= n; capacity -= n
    const s = spare < capacity ? spare : capacity
    spare -= s
    plans.push({ key, order_id: target.order_id, demand_id: target.demand_id, order_version: target.order_version,
      normal_quantity: quantityText(n), spare_quantity: quantityText(s) })
  }
  return plans
}
export function allocationIssue(source: Data, plans: Data[]) {
  const normal = quantity(source.normal_quantity), spare = quantity(source.spare_quantity)
  if (normal === null || spare === null) return '实收数量需核对'
  let n = 0n, s = 0n
  for (const plan of plans) {
    const pn = quantity(plan.normal_quantity), ps = quantity(plan.spare_quantity)
    if (pn === null || ps === null) return '分配数量需填写完整'
    if (!plan.order_id || !plan.demand_id) return '请选择对应合同／PO'
    n += pn; s += ps
  }
  if (n > normal || s > spare) return '分配数量超过本行实收，请调整'
  return n !== normal || s !== spare ? `待分配：正常 ${quantityText(normal - n)}／备品 ${quantityText(spare - s)}。请核对需求或拆分原单行，本行最多分配 100 份合同。` : ''
}
