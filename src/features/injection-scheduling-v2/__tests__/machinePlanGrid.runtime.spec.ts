import { computed, nextTick, unref } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ScheduleGridRow } from '../types'
import MachinePlanGrid from '../components/MachinePlanGrid.vue'
import { schedulingColumns } from '../composables/useSchedulingColumns'
import { createBusinessSchedulingBaselineFixture } from './fixtures/schedulingBaselineFixture'
import { seedSchedulingBaselineStore } from './helpers/seedSchedulingBaselineStore'

interface CapturedVirtualizerOptions {
  count: number
  overscan: number
  estimateSize: (index: number) => number
}

function styleWidth(style: string | undefined) {
  return Number.parseFloat(style?.match(/width: ([\d.]+)px/)?.[1] ?? '0')
}

const virtualizerProbe = vi.hoisted(() => ({ options: null as CapturedVirtualizerOptions | null, measureCalls: 0 }))

vi.mock('@tanstack/vue-virtual', () => ({
  useVirtualizer: (source: unknown) => computed(() => {
    const options = unref(source) as CapturedVirtualizerOptions
    virtualizerProbe.options = options
    let start = 0
    const items = Array.from({ length: Math.min(options.count, 40) }, (_, index) => {
      const size = options.estimateSize(index)
      const item = { index, key: index, start, end: start + size, size, lane: 0 }
      start += size
      return item
    })
    let totalSize = 0
    for (let index = 0; index < options.count; index += 1) totalSize += options.estimateSize(index)
    return {
      getVirtualItems: () => items,
      getTotalSize: () => totalSize,
      measure: () => { virtualizerProbe.measureCalls += 1 },
    }
  }),
}))

afterEach(() => {
  document.body.innerHTML = ''
  virtualizerProbe.options = null
  virtualizerProbe.measureCalls = 0
})

describe('MachinePlanGrid B0 runtime baseline', () => {
  it('mounts the current planner layout and records frozen offsets and virtual row sizing', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = seedSchedulingBaselineStore(pinia, createBusinessSchedulingBaselineFixture())
    const rows = store.gridRows as ScheduleGridRow[]
    const plannerColumns = store.visibleColumns
    const startedAt = performance.now()
    const wrapper = mount(MachinePlanGrid, {
      attachTo: document.body,
      props: {
        rows,
        machineSummaryById: store.machineSummaryById,
        columns: plannerColumns,
        collapsedMachineIds: [],
        widths: {},
        sort: null,
        selectedTaskId: null,
        planStatus: 'PUBLISHED',
        canEdit: false,
        canReport: true,
        pendingEdits: {},
      },
    })
    await nextTick()
    const mountDurationMs = performance.now() - startedAt

    expect(rows).toHaveLength(1_576)
    expect(plannerColumns).toHaveLength(16)
    expect(wrapper.findAll('.column-title-row th')).toHaveLength(16)
    expect(wrapper.findAll('.column-title-row th.frozen')).toHaveLength(4)
    expect(wrapper.findAll('.column-title-row th.frozen').map((header) => header.attributes('style'))).toEqual([
      'width: 92px; left: 0px;',
      'width: 82px; left: 92px;',
      'width: 160px; left: 174px;',
      'width: 220px; left: 334px;',
    ])
    expect(wrapper.findAll('.column-group-row th').map((header) => ({
      text: header.text(),
      frozen: header.classes().includes('frozen'),
      colspan: header.attributes('colspan'),
      columns: header.attributes('data-column-keys'),
      style: header.attributes('style'),
    }))).toEqual([
      { text: '执行', frozen: true, colspan: '1', columns: 'status', style: 'width: 92px; left: 0px;' },
      { text: '机台与排程', frozen: true, colspan: '3', columns: 'machineCode,moldNo,productName', style: 'width: 462px; left: 92px;' },
      { text: '执行', frozen: false, colspan: '1', columns: 'sequence', style: 'width: 54px;' },
      { text: '机台与排程', frozen: false, colspan: '3', columns: 'moldA,orderNo,itemNo', style: 'width: 358px;' },
      { text: '数量与进度', frozen: false, colspan: '2', columns: 'outstandingQuantity,progress', style: 'width: 204px;' },
      { text: '货期与计划', frozen: false, colspan: '4', columns: 'deliveryDue,slack,plannedStart,plannedFinish', style: 'width: 456px;' },
      { text: '生产辅助', frozen: false, colspan: '2', columns: 'warehouse,remark', style: 'width: 304px;' },
    ])
    expect(plannerColumns.filter((column) => column.frozen).reduce((total, column) => total + column.width, 0)).toBe(554)
    expect(wrapper.find('table').attributes('style')).toContain('width: 1930px')
    expect(wrapper.find('tbody').attributes('style')).toContain('height: 69648px')
    expect(wrapper.get('[data-testid="machine-plan-virtual-scroll"]').attributes('style')).toContain('--scheduling-machine-row: 48px')
    expect(wrapper.get('[data-testid="machine-plan-virtual-scroll"]').attributes('style')).toContain('--scheduling-task-row: 44px')
    expect(wrapper.findAll('tbody tr').length).toBeGreaterThan(0)
    expect(wrapper.findAll('tbody tr').length).toBeLessThanOrEqual(40)
    expect(virtualizerProbe.options?.overscan).toBe(12)
    expect(virtualizerProbe.options?.estimateSize(0)).toBe(48)
    expect(virtualizerProbe.options?.estimateSize(1)).toBe(44)
    expect(mountDurationMs).toBeGreaterThanOrEqual(0)

    wrapper.unmount()
  })

  it('remeasures a density change while retaining the same logical scroll anchor', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = seedSchedulingBaselineStore(pinia, createBusinessSchedulingBaselineFixture())
    const wrapper = mount(MachinePlanGrid, {
      attachTo: document.body,
      props: {
        rows: store.gridRows as ScheduleGridRow[],
        machineSummaryById: store.machineSummaryById,
        columns: store.visibleColumns,
        collapsedMachineIds: [],
        widths: {},
        sort: null,
        selectedTaskId: null,
        planStatus: 'PUBLISHED',
        canEdit: false,
        canReport: true,
        pendingEdits: {},
        density: 'comfortable',
      },
    })
    await nextTick()
    const scrollElement = wrapper.get('[data-testid="machine-plan-virtual-scroll"]').element as HTMLElement
    scrollElement.scrollTop = 70

    await wrapper.setProps({ density: 'compact' })
    await nextTick()

    expect(virtualizerProbe.measureCalls).toBe(1)
    expect(virtualizerProbe.options?.estimateSize(0)).toBe(44)
    expect(virtualizerProbe.options?.estimateSize(1)).toBe(38)
    expect(wrapper.find('tbody').attributes('style')).toContain('height: 60344px')
    expect(wrapper.get('[data-testid="machine-plan-virtual-scroll"]').attributes('style')).toContain('--scheduling-machine-row: 44px')
    expect(wrapper.get('[data-testid="machine-plan-virtual-scroll"]').attributes('style')).toContain('--scheduling-task-row: 38px')
    expect(scrollElement.scrollTop).toBe(63)

    wrapper.unmount()
  })

  it('recomputes rendered group segments after visibility, width and preset changes', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = seedSchedulingBaselineStore(pinia, createBusinessSchedulingBaselineFixture())
    const wrapper = mount(MachinePlanGrid, {
      props: {
        rows: store.gridRows as ScheduleGridRow[],
        machineSummaryById: store.machineSummaryById,
        columns: store.visibleColumns,
        collapsedMachineIds: [],
        widths: {},
        sort: null,
        selectedTaskId: null,
        planStatus: 'PUBLISHED',
        canEdit: false,
        canReport: true,
        pendingEdits: {},
      },
    })

    const withoutOrderNo = store.visibleColumns.filter((column) => column.key !== 'orderNo')
    await wrapper.setProps({
      columns: withoutOrderNo,
      widths: { machineCode: 100, productName: 240, progress: 140 },
    })
    await nextTick()
    expect(wrapper.get('.column-group-row th[data-column-keys="machineCode,moldNo,productName"]').attributes('style')).toBe('width: 500px; left: 92px;')
    expect(wrapper.get('.column-group-row th[data-column-keys="moldA,itemNo"]').attributes('style')).toBe('width: 230px;')
    expect(wrapper.get('.column-group-row th[data-column-keys="outstandingQuantity,progress"]').attributes('style')).toBe('width: 232px;')
    const resizedSegmentWidth = wrapper.findAll('.column-group-row th').reduce((total, header) => total + styleWidth(header.attributes('style')), 0)
    expect(resizedSegmentWidth).toBe(styleWidth(wrapper.get('table').attributes('style')))

    store.setPreset('fit')
    await wrapper.setProps({ columns: store.visibleColumns, widths: {} })
    await nextTick()
    expect(wrapper.findAll('.column-group-row th')).toHaveLength(6)
    expect(wrapper.findAll('.column-group-row th').map((header) => header.text())).toEqual([
      '执行', '机台与排程', '执行', '机台与排程', '颜色与物料', '生产辅助',
    ])
    expect(wrapper.findAll('.column-group-row th.frozen')).toHaveLength(2)

    wrapper.unmount()
  })

  it('keeps all current full columns available through the runtime store preset', () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = seedSchedulingBaselineStore(pinia, createBusinessSchedulingBaselineFixture())

    expect(schedulingColumns).toHaveLength(50)
    store.setPreset('full')
    expect(store.visibleColumns).toHaveLength(50)
  })
})
