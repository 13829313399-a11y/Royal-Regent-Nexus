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

  it('exposes the retained uploaded-plan fields and required frozen defaults', () => {
    expect(uploadedPlanFieldCount).toBe(43)
    expect(schedulingColumns.length).toBeGreaterThanOrEqual(uploadedPlanFieldCount)
    expect(schedulingColumns.map((column) => column.key)).not.toEqual(expect.arrayContaining([
      'outsourcePrice', 'shiftEnd', 'duration', 'shiftPlan',
    ]))
    expect(schedulingColumns.filter((column) => column.frozen).map((column) => column.key)).toEqual([
      'status', 'machineCode', 'moldNo', 'productName',
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

  it('lets planners enlarge the plan grid by dragging or toggling the KPI boundary', () => {
    expect(viewSource).toContain('role="separator"')
    expect(viewSource).toContain('调整计划表高度')
    expect(viewSource).toContain('@pointerdown="startKpiResize"')
    expect(viewSource).toContain('@dblclick="toggleWorkspaceHeight"')
    expect(viewSource).toContain("event.key === 'ArrowUp'")
    expect(viewSource).toContain("event.key === 'ArrowDown'")
    expect(viewSource).toContain("workspaceExpanded ? '恢复指标' : '放大表格'")
  })

  it('projects demand-order planning facts with the agreed plan-column mapping', () => {
    expect(storeSource).toContain("readLineage(order, 'source_mold_no'")
    expect(storeSource).toContain('setQuantity: total')
    expect(storeSource).toContain("readLineage(order, 'color_name'")
    expect(storeSource).toContain("readLineage(order, 'color_powder_code'")
    expect(storeSource).toContain("readLineage(order, 'material_name'")
    expect(storeSource).toContain("gridValue(order, 'whole_shot_net_weight_g'")
    expect(storeSource).toContain("gridValue(order, 'total_gross_weight'")
    expect(storeSource).toContain("readLineage(order, 'sprue_ratio'")
    expect(storeSource).toContain("readLineage(order, 'order_date'")
  })
})
