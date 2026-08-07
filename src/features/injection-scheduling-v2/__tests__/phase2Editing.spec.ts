import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import GridEditableCell from '../components/GridEditableCell.vue'
import { resolveReportedQuantity } from '../composables/useScheduleDraftEdits'
import type { CellDraft } from '../types'

const root = join(process.cwd(), 'src/features/injection-scheduling-v2')
const apiSource = readFileSync(join(root, 'api/injectionSchedulingV2Api.ts'), 'utf8')
const storeSource = readFileSync(join(root, 'stores/useInjectionSchedulingV2Store.ts'), 'utf8')
const rowSource = readFileSync(join(root, 'components/ScheduleTaskRow.vue'), 'utf8')
const liveSource = readFileSync(join(root, 'composables/useScheduleLiveEvents.ts'), 'utf8')
const viewSource = readFileSync(join(root, 'InjectionSchedulingV2View.vue'), 'utf8')
const anchorSource = readFileSync(join(process.cwd(), 'backend/app/services/injection_scheduling_scheduler/anchor.py'), 'utf8')

function draft(key: CellDraft['key'], value: string | number): CellDraft {
  return { taskId: 'task-1', orderId: 'order-1', key, value, originalValue: 0 }
}

describe('injection scheduling V2 Phase 2 editing', () => {
  it('commits an editable grid cell with the keyboard', async () => {
    const wrapper = mount(GridEditableCell, { props: { value: 12, kind: 'number' } })

    await wrapper.get('button').trigger('dblclick')
    const input = wrapper.get('input')
    await input.setValue('18')
    await input.trigger('keydown', { key: 'Enter' })

    expect(wrapper.emitted('commit')).toEqual([[18]])
    expect(wrapper.find('input').exists()).toBe(false)
  })

  it('treats the edited order cumulative quantity as authoritative', () => {
    expect(resolveReportedQuantity([draft('shiftCompleted', 30), draft('completedQuantity', 145)], 20, 100)).toBe(45)
    expect(resolveReportedQuantity([draft('shiftCompleted', 30)], 20, 100)).toBe(30)
    expect(resolveReportedQuantity([], 20, 100)).toBe(20)
  })

  it('wires atomic reports, eligibility-checked moves, revisions, and 12-second events', () => {
    expect(apiSource).toContain('/tasks/shift-reports/bulk')
    expect(apiSource).toContain('/tasks/bulk-move')
    expect(apiSource).toContain('allow_scheduled: allowScheduled')
    expect(apiSource).toContain("'X-Request-ID'")
    expect(storeSource).toContain('savePendingEdits')
    expect(storeSource).toContain('revisionConflict')
    expect(storeSource).toContain('fetchEligibility')
    expect(storeSource).toContain('pollEvents')
    expect(liveSource).toContain('intervalMs = 12_000')
    expect(rowSource).toContain(':draggable="draggable()"')
    expect(rowSource).toContain("ArrowUp: 'up'")
    expect(rowSource).toContain("ArrowRight: 'next-machine'")
  })

  it('reads execution and planning contexts explicitly and exposes one continuation anchor contract', () => {
    expect(apiSource).toContain('/injection-scheduling/plans/context')
    expect(apiSource).toContain('execution_published_plan')
    expect(apiSource).toContain('planning_draft_plan')
    expect(apiSource).toContain('sourceTaskId')
    expect(storeSource).toContain('executionPlan')
    expect(storeSource).toContain('planningPlan')
    expect(viewSource).toContain('执行 {{ store.executionPlan')
    expect(viewSource).toContain('规划 {{ store.planningPlan')
    expect(anchorSource).toContain('def build_machine_continuation_anchors')
    expect(anchorSource).toContain('def next_feasible_start')
  })
})
