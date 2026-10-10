import type { MasterRecord } from './api'
export interface PlanTaskInput {
  task_id: string; name: string; resource_id: string; resource_version: number; target_sets: number
  prerequisite_required?: boolean; prerequisite_change_reason?: string
  date_basis?: 'estimated' | 'actual'
  preparation_workdays?: number
  resource_change_basis?: string
  actual_prerequisite_date?: string | null; actual_prerequisite_reference?: string
  materials: Array<{ row: number; expected_date: string | null }>; readiness_basis: string
  actual_issue_date: string | null; actual_issue_reference: string; prerequisite_date: string | null; prerequisite_basis: string; days: Array<{ day: string; sets: number }>
}
export interface PlanTask extends PlanTaskInput {
  estimated_supply_date?: string | null; actual_supply_date?: string | null; actual_review_pending?: boolean
  expected_issue_date?: string | null; // Historical estimate only; never promoted to actual issue evidence.
  resource: MasterRecord; planned_sets: number; unplanned_sets: number
  readiness_date?: string | null; calendar_source?: string; calendar?: import('./api').WorkCalendarData | null
  first_supply_date: string | null; completion_date: string | null; earliest_supply_date?: string | null
}
export interface ProductionPlan {
  version: number; tasks: PlanTask[]; allocated_sets: number; unallocated_sets: number
  actor_id: string; created_at: string; reason: string; adjustment_reason?: string | null
  removed_task_reasons?: Record<string, string>
}
export interface Planning { draft?: ProductionPlan | null; published?: ProductionPlan; baseline?: ProductionPlan }
export function taskInput(t: PlanTaskInput): PlanTaskInput {
  return JSON.parse(JSON.stringify({ task_id: t.task_id, name: t.name, resource_id: t.resource_id,
    resource_version: t.resource_version, target_sets: t.target_sets, date_basis: t.date_basis ?? 'estimated',
    preparation_workdays: t.preparation_workdays ?? 3,
    resource_change_basis: t.resource_change_basis ?? '',
    prerequisite_required: t.prerequisite_required ?? !!(t.prerequisite_date || t.actual_prerequisite_date), prerequisite_change_reason: t.prerequisite_change_reason ?? '',
    actual_prerequisite_date: t.actual_prerequisite_date ?? null, actual_prerequisite_reference: t.actual_prerequisite_reference ?? '', materials: t.materials.map(m => ({ ...m, expected_date: m.expected_date || null })),
    actual_issue_date: t.actual_issue_date ?? null, actual_issue_reference: t.actual_issue_reference ?? '',
    readiness_basis: t.readiness_basis, prerequisite_date: t.prerequisite_date,
    prerequisite_basis: t.prerequisite_basis, days: t.days }))
}
