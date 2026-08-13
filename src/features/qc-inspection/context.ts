import type { ComputedRef, InjectionKey, Ref } from 'vue'
import { inject } from 'vue'
import type { QcWorkspace } from '@/api/qcInspection'

export type QcWorkspaceState = 'loading' | 'ready' | 'error' | 'forbidden'

export interface QcInspectionWorkspaceContext {
  factoryId: ComputedRef<string>
  factoryName: ComputedRef<string>
  weekKey: ComputedRef<string>
  workspace: Ref<QcWorkspace | null>
  state: Ref<QcWorkspaceState>
  errorMessage: Ref<string>
  canScheduleWrite: ComputedRef<boolean>
  canOrderWrite: ComputedRef<boolean>
  canResultWrite: ComputedRef<boolean>
  canProblemWrite: ComputedRef<boolean>
  canReportExport: ComputedRef<boolean>
  canRenamePreview: ComputedRef<boolean>
  canRenameExecute: ComputedRef<boolean>
  canGroupSummary: ComputedRef<boolean>
  canFactorySummary: ComputedRef<boolean>
  refresh: () => Promise<void>
  setWeek: (week: string) => Promise<void>
}

export const qcInspectionWorkspaceKey: InjectionKey<QcInspectionWorkspaceContext> = Symbol('qc-inspection-workspace')

export function useQcInspectionWorkspace() {
  const context = inject(qcInspectionWorkspaceKey)
  if (!context) {
    throw new Error('QC inspection workspace context is unavailable')
  }
  return context
}
