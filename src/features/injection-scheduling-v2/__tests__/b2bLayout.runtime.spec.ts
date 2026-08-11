import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ColumnPresetMenu from '../components/ColumnPresetMenu.vue'
import {
  getColumnMoveDecision,
  schedulingColumns,
  schedulingDefaultColumnOrder,
  schedulingFrozenKeysByPreset,
  schedulingPlannerColumnKeys,
  uploadedPlanFieldCount,
} from '../composables/useSchedulingColumns'
import {
  defaultSchedulingDensity,
  schedulingDensity,
  translateSchedulingScrollOffset,
} from '../config/schedulingLayout'
import { useInjectionSchedulingV2Store } from '../stores/useInjectionSchedulingV2Store'

const expectedPlannerKeys = [
  'status', 'machineCode', 'moldNo', 'productName',
  'sequence', 'moldA', 'orderNo', 'itemNo',
  'outstandingQuantity', 'progress', 'deliveryDue', 'slack',
  'plannedStart', 'plannedFinish', 'warehouse', 'remark',
]

describe('B2b planner columns, frozen partitions and density', () => {
  it('uses the approved 16-column planner order while retaining all 50 full columns', () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useInjectionSchedulingV2Store(pinia)

    expect(schedulingPlannerColumnKeys).toEqual(expectedPlannerKeys)
    expect(schedulingDefaultColumnOrder.slice(0, expectedPlannerKeys.length)).toEqual(expectedPlannerKeys)
    expect(store.visibleColumns.map((column) => column.key)).toEqual(expectedPlannerKeys)
    expect(store.visibleColumns.filter((column) => column.frozen).map((column) => column.key)).toEqual([
      'status', 'machineCode', 'moldNo', 'productName',
    ])
    expect(store.visibleColumns.slice(4).every((column) => !column.frozen)).toBe(true)
    expect(store.visibleColumns.filter((column) => column.frozen).reduce((total, column) => total + column.width, 0)).toBe(554)
    expect(554 / 1_280).toBeLessThanOrEqual(0.45)

    store.setPreset('full')
    expect(store.visibleColumns).toHaveLength(50)
    expect(schedulingColumns).toHaveLength(50)
    expect(uploadedPlanFieldCount).toBe(43)
  })

  it('keeps pinned and scrolling columns in separate movable partitions', () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useInjectionSchedulingV2Store(pinia)
    const initialOrder = [...store.columnOrder]

    expect(getColumnMoveDecision(initialOrder, 'productName', 1, 'planner')).toMatchObject({ allowed: false, reason: '冻结列不能移动到滚动区' })
    expect(getColumnMoveDecision(initialOrder, 'sequence', -1, 'planner')).toMatchObject({ allowed: false, reason: '普通列不能移动到冻结区' })
    store.moveColumn('productName', 1)
    expect(store.columnOrder).toEqual(initialOrder)

    store.moveColumn('status', 1)
    expect(store.visibleColumns.slice(0, 4).map((column) => column.key)).toEqual(['machineCode', 'status', 'moldNo', 'productName'])
    expect(store.visibleColumns.slice(0, 4).every((column) => column.frozen)).toBe(true)

    store.moveColumn('sequence', 1)
    expect(store.visibleColumns.slice(4, 6).map((column) => column.key)).toEqual(['moldA', 'sequence'])
    expect(store.visibleColumns.slice(4).every((column) => !column.frozen)).toBe(true)

    store.resetColumns()
    store.setPreset('fit')
    expect(store.visibleColumns.slice(0, schedulingFrozenKeysByPreset.fit.length).map((column) => column.key)).toEqual(schedulingFrozenKeysByPreset.fit)
  })

  it('shows the full-field distinction and explains disabled cross-boundary moves', () => {
    const wrapper = mount(ColumnPresetMenu, {
      props: {
        open: true,
        preset: 'planner',
        visibleKeys: expectedPlannerKeys,
        widths: {},
        columnOrder: schedulingDefaultColumnOrder,
      },
    })

    expect(wrapper.text()).toContain(`完整字段50 列（其中上传来源 ${uploadedPlanFieldCount} 字段）`)
    expect(wrapper.get('button[aria-label="名称后移"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('button[aria-label="名称后移"]').attributes('title')).toBe('冻结列不能移动到滚动区')
    expect(wrapper.get('button[aria-label="队列前移"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('button[aria-label="队列前移"]').attributes('title')).toBe('普通列不能移动到冻结区')
  })

  it('defines comfortable and compact geometry once and preserves the scroll anchor', () => {
    expect(defaultSchedulingDensity).toBe('comfortable')
    expect(schedulingDensity.comfortable).toEqual({ machineRow: 48, taskRow: 44, bodyFont: 13, headerFont: 12, groupFont: 11, chipFont: 11 })
    expect(schedulingDensity.compact).toEqual({ machineRow: 44, taskRow: 38, bodyFont: 12, headerFont: 11, groupFont: 10, chipFont: 10 })

    const rows = [{ rowType: 'machine' as const }, { rowType: 'task' as const }, { rowType: 'task' as const }]
    expect(translateSchedulingScrollOffset(rows, 'comfortable', 'compact', 48 + 22)).toBe(44 + 19)
    expect(translateSchedulingScrollOffset(rows, 'compact', 'comfortable', 44 + 19)).toBe(48 + 22)
  })
})
