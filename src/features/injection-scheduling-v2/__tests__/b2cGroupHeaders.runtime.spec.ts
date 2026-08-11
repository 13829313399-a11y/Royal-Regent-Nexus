import { createPinia, setActivePinia } from 'pinia'
import { describe, expect, it } from 'vitest'
import { buildSchedulingGroupHeaderSegments } from '../presentation/schedulingGroupSegments'
import type { SchedulingColumnDefinition } from '../types'
import { useInjectionSchedulingV2Store } from '../stores/useInjectionSchedulingV2Store'

function leafWidth(columns: SchedulingColumnDefinition[], widths: Record<string, number> = {}) {
  return columns.reduce((total, column) => total + (widths[String(column.key)] ?? column.width), 0)
}

describe('B2c scheduling group-header segments', () => {
  it('merges the planner header into continuous group segments without crossing the frozen boundary', () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useInjectionSchedulingV2Store(pinia)
    const segments = buildSchedulingGroupHeaderSegments(store.visibleColumns, {})

    expect(segments).toEqual([
      { id: 'frozen:执行:status', group: '执行', frozen: true, columnKeys: ['status'], width: 92, left: 0 },
      { id: 'frozen:机台与排程:machineCode', group: '机台与排程', frozen: true, columnKeys: ['machineCode', 'moldNo', 'productName'], width: 462, left: 92 },
      { id: 'scroll:执行:sequence', group: '执行', frozen: false, columnKeys: ['sequence'], width: 54 },
      { id: 'scroll:机台与排程:moldA', group: '机台与排程', frozen: false, columnKeys: ['moldA', 'orderNo', 'itemNo'], width: 358 },
      { id: 'scroll:数量与进度:outstandingQuantity', group: '数量与进度', frozen: false, columnKeys: ['outstandingQuantity', 'progress'], width: 204 },
      { id: 'scroll:货期与计划:deliveryDue', group: '货期与计划', frozen: false, columnKeys: ['deliveryDue', 'slack', 'plannedStart', 'plannedFinish'], width: 456 },
      { id: 'scroll:生产辅助:warehouse', group: '生产辅助', frozen: false, columnKeys: ['warehouse', 'remark'], width: 304 },
    ])
    expect(segments.reduce((total, segment) => total + segment.width, 0)).toBe(leafWidth(store.visibleColumns))
  })

  it('never merges identical adjacent labels across frozen and scrolling partitions', () => {
    const columns: SchedulingColumnDefinition[] = [
      { key: 'status', title: '状态', group: '执行', width: 92, frozen: true, presets: ['planner'] },
      { key: 'sequence', title: '队列', group: '执行', width: 54, presets: ['planner'] },
    ]

    expect(buildSchedulingGroupHeaderSegments(columns, {})).toEqual([
      { id: 'frozen:执行:status', group: '执行', frozen: true, columnKeys: ['status'], width: 92, left: 0 },
      { id: 'scroll:执行:sequence', group: '执行', frozen: false, columnKeys: ['sequence'], width: 54 },
    ])
  })

  it('recomputes segment membership and width after a column is hidden or resized', () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useInjectionSchedulingV2Store(pinia)
    const visible = store.visibleColumns.filter((column) => column.key !== 'orderNo')
    const widths = { machineCode: 100, productName: 240, progress: 140 }
    const segments = buildSchedulingGroupHeaderSegments(visible, widths)

    expect(segments.find((segment) => segment.id === 'frozen:机台与排程:machineCode')).toMatchObject({
      columnKeys: ['machineCode', 'moldNo', 'productName'],
      width: 500,
      left: 92,
    })
    expect(segments.find((segment) => segment.id === 'scroll:机台与排程:moldA')).toMatchObject({
      columnKeys: ['moldA', 'itemNo'],
      width: 230,
    })
    expect(segments.find((segment) => segment.id === 'scroll:数量与进度:outstandingQuantity')).toMatchObject({ width: 232 })
    expect(segments.reduce((total, segment) => total + segment.width, 0)).toBe(leafWidth(visible, widths))
  })

  it('preserves the width invariant across every preset', () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useInjectionSchedulingV2Store(pinia)

    for (const preset of ['planner', 'production', 'fit', 'full'] as const) {
      store.setPreset(preset)
      const columns = store.visibleColumns
      const segments = buildSchedulingGroupHeaderSegments(columns, {})
      expect(segments.reduce((total, segment) => total + segment.width, 0), preset).toBe(leafWidth(columns))
      expect(segments.some((segment, index) => index > 0
        && segment.group === segments[index - 1]!.group
        && segment.frozen === segments[index - 1]!.frozen), preset).toBe(false)
      expect(segments.findIndex((segment) => !segment.frozen), preset).toBeGreaterThan(0)
      expect(segments.slice(0, segments.findIndex((segment) => !segment.frozen)).every((segment) => segment.frozen), preset).toBe(true)
    }
  })
})
