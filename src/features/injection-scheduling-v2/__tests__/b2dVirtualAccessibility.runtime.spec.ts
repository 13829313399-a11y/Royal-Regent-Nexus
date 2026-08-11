import { computed, nextTick, unref } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import MachinePlanGrid from '../components/MachinePlanGrid.vue'
import type { ScheduleGridRow } from '../types'
import { createBusinessSchedulingBaselineFixture } from './fixtures/schedulingBaselineFixture'
import { seedSchedulingBaselineStore } from './helpers/seedSchedulingBaselineStore'

interface VirtualizerOptions {
  count: number
  estimateSize: (index: number) => number
}

vi.mock('@tanstack/vue-virtual', () => ({
  useVirtualizer: (source: unknown) => computed(() => {
    const options = unref(source) as VirtualizerOptions
    let start = 0
    const items = Array.from({ length: Math.min(options.count, 40) }, (_, index) => {
      const size = options.estimateSize(index)
      const item = { index, key: index, start, end: start + size, size, lane: 0 }
      start += size
      return item
    })
    let totalSize = 0
    for (let index = 0; index < options.count; index += 1) totalSize += options.estimateSize(index)
    return { getVirtualItems: () => items, getTotalSize: () => totalSize, measure: () => undefined }
  }),
}))

function mountGrid(rows: ScheduleGridRow[], options: { draft?: boolean } = {}) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = seedSchedulingBaselineStore(pinia, createBusinessSchedulingBaselineFixture())
  const wrapper = mount(MachinePlanGrid, {
    attachTo: document.body,
    props: {
      rows,
      machineSummaryById: store.machineSummaryById,
      columns: store.visibleColumns,
      collapsedMachineIds: [],
      widths: {},
      sort: null,
      selectedTaskId: null,
      planStatus: options.draft ? 'DRAFT' : 'PUBLISHED',
      canEdit: Boolean(options.draft),
      canReport: !options.draft,
      pendingEdits: {},
    },
  })
  return { wrapper, store }
}

afterEach(() => {
  document.body.innerHTML = ''
})

describe('B2d keyboard and virtual table accessibility', () => {
  it('names the virtual table and exposes sortable headers and keyboard resizers', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = seedSchedulingBaselineStore(pinia, createBusinessSchedulingBaselineFixture())
    const rows = store.gridRows as ScheduleGridRow[]
    const { wrapper } = mountGrid(rows)
    await nextTick()

    const table = wrapper.get('table')
    expect(table.attributes('aria-label')).toBe('注塑排产任务表')
    expect(table.attributes('aria-rowcount')).toBe(String(rows.length + 2))
    expect(table.attributes('aria-colcount')).toBe('16')

    const statusHeader = wrapper.get('.column-title-row th[data-column-id="status"]')
    expect(statusHeader.attributes('aria-sort')).toBe('none')
    const sortButton = statusHeader.get('button')
    expect(sortButton.attributes('aria-label')).toContain('状态')
    await sortButton.trigger('keydown', { key: 'Enter' })
    await sortButton.trigger('keydown', { key: ' ' })
    expect(wrapper.emitted('sort')).toEqual([['status'], ['status']])

    await wrapper.setProps({ sort: { key: 'status', desc: false } })
    expect(statusHeader.attributes('aria-sort')).toBe('ascending')
    await wrapper.setProps({ sort: { key: 'status', desc: true } })
    expect(statusHeader.attributes('aria-sort')).toBe('descending')

    const resizer = statusHeader.get('[role="separator"]')
    expect(resizer.attributes('tabindex')).toBe('0')
    expect(resizer.attributes('aria-orientation')).toBe('vertical')
    expect(resizer.attributes('aria-valuemin')).toBe('54')
    expect(resizer.attributes('aria-valuemax')).toBe('420')
    expect(resizer.attributes('aria-valuenow')).toBe('92')
    await resizer.trigger('keydown', { key: 'ArrowRight' })
    expect(wrapper.emitted('resize')?.at(-1)).toEqual(['status', 100])

    wrapper.unmount()
  })

  it('publishes virtual row indices, column indices and visible keyboard guidance', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = seedSchedulingBaselineStore(pinia, createBusinessSchedulingBaselineFixture())
    const rows = store.gridRows as ScheduleGridRow[]
    const { wrapper } = mountGrid(rows)
    await nextTick()

    expect(wrapper.get('.machine-group-row').attributes('aria-rowindex')).toBe('3')
    const firstTask = wrapper.get('.schedule-task-row')
    expect(firstTask.attributes('aria-rowindex')).toBe('4')
    expect(firstTask.attributes('aria-label')).toContain('正在生产')
    expect(firstTask.findAll('td').map((cell) => cell.attributes('aria-colindex')).slice(0, 4)).toEqual(['1', '2', '3', '4'])
    expect(wrapper.get('.grid-keyboard-help').text()).toContain('Alt + 方向键移动')
    expect(wrapper.get('.grid-keyboard-help').text()).toContain('左右方向键调列宽')

    wrapper.unmount()
  })

  it('announces drag and keyboard movement and restores focus when a virtual row unloads', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = seedSchedulingBaselineStore(pinia, createBusinessSchedulingBaselineFixture())
    const allRows = store.gridRows as ScheduleGridRow[]
    const sourceTaskRow = allRows.find((row) => row.rowType === 'task' && row.task)
    if (!sourceTaskRow || sourceTaskRow.rowType !== 'task' || !sourceTaskRow.task) throw new Error('Fixture must include a task row')
    const machineRow = allRows.find((row) => row.rowType === 'machine' && row.machine.id === sourceTaskRow.machine.id)
    if (!machineRow) throw new Error('Fixture must include the task machine row')
    const movableRow: ScheduleGridRow = {
      ...sourceTaskRow,
      status: 'QUEUED',
      task: {
        ...sourceTaskRow.task,
        status: 'QUEUED',
        locked: false,
        activeExecution: false,
      },
    }
    const { wrapper } = mountGrid([machineRow, movableRow], { draft: true })
    await nextTick()
    const taskRow = wrapper.get('.schedule-task-row')

    await taskRow.trigger('keydown', { key: 'ArrowDown', altKey: true })
    await nextTick()
    expect(wrapper.emitted('keyboardMove')).toEqual([[movableRow.id, 'down']])
    expect(wrapper.get('[data-testid="grid-live-announcement"]').text()).toContain('下移移动预览')

    await taskRow.trigger('dragstart')
    await nextTick()
    expect(wrapper.get('[data-testid="grid-live-announcement"]').text()).toContain('已拾取')
    await wrapper.get('.machine-group-row').trigger('drop')
    await nextTick()
    expect(wrapper.emitted('moveRequest')).toEqual([[movableRow.id, machineRow.machine.id, store.machineSummaryById.get(machineRow.machine.id)?.taskCount]])
    expect(wrapper.get('[data-testid="grid-live-announcement"]').text()).toContain('已请求将')

    await taskRow.trigger('dragstart')
    await taskRow.trigger('dragend')
    await nextTick()
    expect(wrapper.get('[data-testid="grid-live-announcement"]').text()).toContain('已取消拖拽')

    ;(taskRow.element as HTMLElement).focus()
    await nextTick()
    expect(document.activeElement).toBe(taskRow.element)
    await wrapper.setProps({ rows: [machineRow] })
    await nextTick()
    await nextTick()
    expect(document.activeElement).toBe(wrapper.get('[data-testid="machine-plan-virtual-scroll"]').element)
    expect(wrapper.get('[data-testid="grid-live-announcement"]').text()).toContain('焦点已返回排产表')

    wrapper.unmount()
  })
})
