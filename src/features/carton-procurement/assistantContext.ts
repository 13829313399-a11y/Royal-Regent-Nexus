import type { ContextSelection } from '@/features/assistant/v2'
import type { UnifiedOrderEntry, UnifiedOrderRef } from '@/api/cartonSpecialRequests'

export const cartonKinds = ['PURCHASE', 'SAMPLE', 'WORKSHOP_MISC', 'SUPPLIER_GIFT'] as const
export function cartonOrderRef(value: unknown): UnifiedOrderRef | null {
  if (typeof value !== 'string') return null
  const colon = value.indexOf(':'), kind = value.slice(0, colon), id = value.slice(colon + 1)
  if (colon < 0 || !cartonKinds.includes(kind as UnifiedOrderRef['kind']) || !id || id.length > 96 || id !== id.trim()) return null
  return { kind: kind as UnifiedOrderRef['kind'], id }
}
export function cartonIdentity(entry: UnifiedOrderEntry) {
  return `${entry.kind}:${entry.order?.order_no ?? entry.special?.id ?? ''}`
}
export async function cartonInventoryIdentity(key: string) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(key))
  return 'INVENTORY:' + [...new Uint8Array(digest)].map(n => n.toString(16).padStart(2, '0')).join('')
}
export const isCartonInventoryIdentity = (value: unknown): value is string => typeof value === 'string' && /^INVENTORY:[a-f0-9]{64}$/.test(value)
export function cartonDate(value: unknown) {
  if (value === undefined || value === '') return ''
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null
  const parsed = new Date(`${value}T00:00:00Z`)
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value ? value : null
}
export function cartonSelection(factory: string, ids: string[], filters: ContextSelection['filters']): ContextSelection {
  if (ids.length > 10) return { selection_id: 'carton-selection-too-large', resources: [],
    filters: { factory_id: factory, scope_error: '请将纸品选中记录减少到10条以内，再带入曜灵。' } }
  return { selection_id: ids.length ? 'carton-selected-records' : 'carton-scope', resources: ids.map(id => ({ module_id: 'carton-procurement',
    resource_type: isCartonInventoryIdentity(id) ? 'inventory' : 'order', resource_id: id })),
    filters: { factory_id: factory, ...filters } }
}
