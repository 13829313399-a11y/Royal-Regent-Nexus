import { computed, inject, watch } from 'vue'
import { onBeforeRouteUpdate, routeLocationKey, type LocationQuery } from 'vue-router'
import { CUTTING_BASE, CUTTING_FACTORY } from './navigation'

export type FocusKind = 'task' | 'issue' | 'report' | 'usage' | 'warehouse'
export interface CuttingLocation { lineId: string; month?: string; kind?: FocusKind; id?: string }
const kinds: FocusKind[] = ['task', 'issue', 'report', 'usage', 'warehouse']
const scalar = (value: unknown) => typeof value === 'string' && value.length <= 200 && !/[\x00-\x1f]/.test(value) ? value : ''
export function readCuttingLocation(query: LocationQuery): CuttingLocation | undefined {
  const lineId = scalar(query.line_id)
  if (query.factory !== CUTTING_FACTORY || !lineId) return
  const kind = scalar(query.focus_kind) as FocusKind, id = scalar(query.focus_id)
  const month = typeof query.month === 'string' && /^\d{4}-(0[1-9]|1[0-2])$/.test(query.month) ? query.month : undefined
  return { lineId, month, ...(kinds.includes(kind) && id ? { kind, id } : {}) }
}
export function cuttingDestination(lineId: string, month: string, workspace: string, kind?: FocusKind, id?: string) {
  const path = ['planning', 'reporting', 'materials', 'costs', 'closing'].includes(workspace) ? workspace : 'closing'
  return { path: `${CUTTING_BASE}/${path}`, query: { factory: CUTTING_FACTORY, line_id: lineId, month,
    ...(kind && id ? { focus_kind: kind, focus_id: id } : {}) } }
}
export function useCuttingLocation(discard: () => boolean, reload: () => void) {
  const route = inject(routeLocationKey, undefined)
  const location = computed(() => route ? readCuttingLocation(route.query) : undefined)
  if (route) {
    const path = route.path
    onBeforeRouteUpdate((to, from) => to.fullPath === from.fullPath || discard())
    watch(() => route.fullPath, () => { if (route.path === path) reload() })
  }
  return location
}
