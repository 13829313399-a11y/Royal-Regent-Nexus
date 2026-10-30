import type { BoardOrder, MaterialRecord } from '@/api/indonesiaMaterials'

// Recipe multiplication may produce 16 places; these are reference figures, not editable receipts.
export function referenceNumber(value: unknown): bigint | null {
  const match = /^(\d+)(?:\.(\d{0,16}))?$/.exec(String(value ?? '').trim())
  return match ? BigInt(match[1]! + (match[2] || '').padEnd(16, '0')) : null
}
export function referenceText(value: bigint) {
  const text = value.toString().padStart(17, '0')
  return `${text.slice(0, -16)}.${text.slice(-16)}`.replace(/\.?0+$/, '') || '0'
}
export function receiptSummary(orders: BoardOrder[], records: MaterialRecord[]) {
  const materials = new Map(records.filter(row => row.kind === 'material').map(row => [row.id, row]))
  const groups = new Map<string, { key: string; material?: MaterialRecord; orders: Set<string>; items: Set<string>; quantity: bigint; coverage: bigint; remaining: bigint; valid: boolean }>()
  for (const order of orders) for (const demand of order.demands) {
    const requested = referenceNumber(demand.quantity), received = referenceNumber(demand.coverage)
    const valid = requested !== null && received !== null
    const remaining = valid && requested > received ? requested - received : 0n
    if (valid && !remaining) continue
    const group = groups.get(demand.material_id) || { key: demand.material_id, material: materials.get(demand.material_id), orders: new Set<string>(), items: new Set<string>(), quantity: 0n, coverage: 0n, remaining: 0n, valid: true }
    group.orders.add(order.id); group.items.add(order.item_no)
    group.quantity += requested ?? 0n; group.coverage += received ?? 0n; group.remaining += remaining
    group.valid = group.valid && valid && !!group.material && !group.material.data.deleted
      && String(group.material.data.unit).trim().toLowerCase() === demand.unit.trim().toLowerCase()
    groups.set(group.key, group)
  }
  return [...groups.values()].map(group => ({ ...group, quantity: referenceText(group.quantity), coverage: referenceText(group.coverage), remaining: referenceText(group.remaining) }))
}
