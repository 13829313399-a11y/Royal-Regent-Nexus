import { computed, inject, watch } from 'vue'
import { onBeforeRouteUpdate, routeLocationKey, type LocationQuery } from 'vue-router'
import { CUTTING_BASE, CUTTING_FACTORY } from './navigation'

export type FocusKind = 'task' | 'issue' | 'report' | 'usage' | 'warehouse' | 'cost_event'
export type ReportingView = 'tasks' | 'records' | 'parts' | 'external' | 'handover'
export interface CuttingLocation { lineId: string; month?: string; day?: string; taskDay?: string; kind?: FocusKind; id?: string; costView?: 'history'|'allocation'; reportingView?: ReportingView }
const kinds: FocusKind[] = ['task', 'issue', 'report', 'usage', 'warehouse', 'cost_event']
const scalar = (value: unknown) => typeof value === 'string' && value.length <= 200 && !/[\x00-\x1f]/.test(value) ? value : ''
export function cuttingQueryDay(value: unknown) {
  const day = scalar(value)
  return /^\d{4}-\d{2}-\d{2}$/.test(day) && Number.isFinite(Date.parse(day)) && new Date(day).toISOString().slice(0,10) === day ? day : undefined
}
export interface TaskFilters { day: string; q: string; execution: string; scope: string }
export function reportingTaskFilters(query: LocationQuery, defaultDay: string): TaskFilters {
  const keyword = scalar(query.task_q)
  const execution = query.task_execution
  const scope = query.task_scope
  return {
    day: cuttingQueryDay(query.task_query_day) ?? cuttingQueryDay(query.task_day) ?? cuttingQueryDay(query.day) ?? defaultDay,
    q: keyword.length <= 80 ? keyword : '',
    execution: execution === 'internal' || execution === 'outsourced' ? execution : '',
    scope: scope === 'reported' || scope === 'unreported' || scope === 'history' || scope === 'abnormal' ? scope : 'daily',
  }
}
export function sameTaskFilters(left: TaskFilters, right: TaskFilters) {
  return left.day === right.day && left.q === right.q && left.execution === right.execution && left.scope === right.scope
}
export function readCuttingLocation(query: LocationQuery): CuttingLocation | undefined {
  const lineId = scalar(query.line_id)
  if (query.factory !== CUTTING_FACTORY || !lineId) return
  const kind = scalar(query.focus_kind) as FocusKind, id = scalar(query.focus_id)
  const month = typeof query.month === 'string' && /^\d{4}-(0[1-9]|1[0-2])$/.test(query.month) ? query.month : undefined
  const day=cuttingQueryDay(query.day), taskDay=cuttingQueryDay(query.task_day)
  const costView=query.cost_view==='history'||query.cost_view==='allocation'?query.cost_view:undefined
  const view = query.reporting_view
  const reportingView = view === 'tasks' || view === 'records' || view === 'parts' || view === 'external' || view === 'handover' ? view : undefined
  return { lineId, month, ...(day?{day}:{}), ...(taskDay?{taskDay}:{}), ...(costView?{costView}:{}), ...(reportingView?{reportingView}:{}), ...(kinds.includes(kind) && id ? { kind, id } : {}) }
}
export function cuttingDestination(lineId: string, month: string, workspace: string, kind?: FocusKind, id?: string) {
  const path = ['planning', 'reporting', 'materials', 'costs', 'closing'].includes(workspace) ? workspace : 'closing'
  return { path: `${CUTTING_BASE}/${path}`, query: { factory: CUTTING_FACTORY, line_id: lineId, month,
    ...(kind && id ? { focus_kind: kind, focus_id: id } : {}) } }
}
export function useCuttingLocation(discard: () => boolean, reload: () => void, presentationOnly?: (path: string) => boolean) {
  const route = inject(routeLocationKey, undefined)
  const location = computed(() => route ? readCuttingLocation(route.query) : undefined)
  if (route) {
    const path = route.path
    onBeforeRouteUpdate((to, from) => to.fullPath === from.fullPath || presentationOnly?.(to.fullPath) || discard())
    watch(() => route.fullPath, () => { if (route.path === path) reload() })
  }
  return location
}
