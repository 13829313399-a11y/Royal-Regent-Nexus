import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { schedulingColumns, uploadedPlanFieldCount } from '../composables/useSchedulingColumns'

const root = join(process.cwd(), 'src/features/injection-scheduling-v2')
const viewSource = readFileSync(join(root, 'InjectionSchedulingV2View.vue'), 'utf8')
const gridSource = readFileSync(join(root, 'components/MachinePlanGrid.vue'), 'utf8')
const storeSource = readFileSync(join(root, 'stores/useInjectionSchedulingV2Store.ts'), 'utf8')

describe('injection scheduling V2 workspace foundation', () => {
  it('keeps the feature split into the required bounded components', () => {
    for (const name of [
      'SchedulingCommandBar', 'SchedulingKpiStrip', 'MachinePlanGrid', 'MachineGroupRow', 'ScheduleTaskRow',
      'ScheduleTimeline', 'BacklogDock', 'TaskInspectorDrawer', 'EligibilityChecks', 'AutoSchedulePreviewDialog', 'ColumnPresetMenu',
    ]) {
      expect(readFileSync(join(root, 'components', `${name}.vue`), 'utf8')).toBeTruthy()
    }
    expect(viewSource).not.toContain('InjectionSchedulingWorkspaceView')
  })

  it('exposes all uploaded-plan fields and required frozen defaults', () => {
    expect(uploadedPlanFieldCount).toBe(47)
    expect(schedulingColumns.length).toBeGreaterThanOrEqual(uploadedPlanFieldCount)
    expect(schedulingColumns.filter((column) => column.frozen).map((column) => column.key)).toEqual([
      'status', 'sequence', 'machineCode', 'moldA', 'moldNo', 'productName', 'orderNo', 'itemNo',
    ])
    expect(schedulingColumns.filter((column) => column.presets.includes('full')).length).toBe(schedulingColumns.length)
  })

  it('keeps TanStack virtualization while Phase 2 adds bounded editing', () => {
    expect(gridSource).toContain("from '@tanstack/vue-table'")
    expect(gridSource).toContain("from '@tanstack/vue-virtual'")
    expect(gridSource).toContain('overscan: 12')
    expect(viewSource).toContain('ManualMoveDialog')
    expect(viewSource).toContain('RevisionConflictDialog')
    expect(viewSource).toContain('store.savePendingEdits')
    expect(viewSource).not.toContain('confirmSuggestion')
    expect(storeSource).not.toContain('http.patch')
    expect(storeSource).not.toContain('http.put')
    expect(storeSource).toContain("a.status === 'RUNNING'")
    expect(storeSource).toContain("b.status === 'RUNNING'")
    expect(storeSource).toContain('function moveColumn')
  })
})
