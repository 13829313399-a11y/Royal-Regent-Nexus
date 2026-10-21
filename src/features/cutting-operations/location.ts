import { computed, inject, watch } from 'vue'
import { onBeforeRouteUpdate, routeLocationKey, type LocationQuery } from 'vue-router'
import { CUTTING_BASE, CUTTING_FACTORY } from './navigation'

export type FocusKind = 'task' | 'issue' | 'report' | 'usage' | 'warehouse' | 'cost_event'
export interface CuttingLocation { lineId: string; month?: string; day?: string; kind?: FocusKind; id?: string; costView?: 'history'|'allocation'; reportingView?: 'records'|'external' }
const kinds: FocusKind[] = ['task', 'issue', 'report', 'usage', 'warehouse', 'cost_event']
const scalar = (value: unknown) => typeof value === 'string' && value.length <= 200 && !/[\x00-\x1f]/.test(value) ? value : ''
export function readCuttingLocation(query: LocationQuery): CuttingLocation | undefined {
  const lineId = scalar(query.line_id)
  if (query.factory !== CUTTING_FACTORY || !lineId) return
  const kind = scalar(query.focus_kind) as FocusKind, id = scalar(query.focus_id)
  const month = typeof query.month === 'string' && /^\d{4}-(0[1-9]|1[0-2])$/.test(query.month) ? query.month : undefined
  const rawDay=scalar(query.day)
  const day=/^\d{4}-\d{2}-\d{2}$/.test(rawDay)&&!Number.isNaN(Date.parse(rawDay))&&new Date(rawDay).toISOString().slice(0,10)===rawDay?rawDay:undefined
  const costView=query.cost_view==='history'||query.cost_view==='allocation'?query.cost_view:undefined
  const reportingView=query.reporting_view==='records'||query.reporting_view==='external'?query.reporting_view:undefined
  return { lineId, month, ...(day?{day}:{}), ...(costView?{costView}:{}), ...(reportingView?{reportingView}:{}), ...(kinds.includes(kind) && id ? { kind, id } : {}) }
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
