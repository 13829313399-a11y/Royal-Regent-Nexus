import { afterEach, describe, expect, it } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { ref } from 'vue'
import { CalendarDate } from '@internationalized/date'
import StockLedger from '../WarehouseStockLedger.vue'
import { inventorySearchKey } from '../inventorySearch'
import { sortStockRows } from '../stockLedger'
import type { WarehouseBatch } from '@/api/warehouseOperations'

const batch = (id: string, values: Partial<WarehouseBatch> = {}): WarehouseBatch => ({
  id, item_code: id, item_name: '布料' + id, unit: '码', process_state: '', material_category: 'FABRIC',
  warehouse_name: 'A', location: 'A1', location_id: 'A1', location_label: 'A / A1', location_verified: true, location_status: 'ACTIVE',
  lot: 'LOT-1', roll_no: 'R1', quantity: '0.1', available_quantity: '0.1', quality_status: 'PENDING_INSPECTION',
  received_on: '2026-10-01', source_no: 'DN-' + id, source_document: 'RECEIPT-' + id, counterparty: '纺织厂', production_no: 'PO-1', ...values,
})
let wrapper: VueWrapper | undefined
const search = ref('')
function open(rows: WarehouseBatch[], canOperate = true) {
  search.value = ''
  wrapper = mount(StockLedger, { props: { rows, warehouse: 'fabric', canOperate, loading: false }, global: {
    provide: { [inventorySearchKey as symbol]: { search, submitted: ref(0), active: ref(true) } },
    stubs: { RouterLink: { template: '<a><slot /></a>' }, DateRangeFilter: { name: 'DateRangeFilter', props: ['modelValue'], emits: ['update:modelValue'], template: '<button>日期</button>' } },
  } })
  return wrapper
}
afterEach(() => { wrapper?.unmount(); wrapper = undefined })

describe('fabric stock queries and selection', () => {
  it('keeps restricted batches transferable without offering issue actions, and filters their restriction', async () => {
    const view = open([batch('HOLD', { quality_status: 'HOLD' }), batch('BAD', { quality_status: 'REJECTED' })])
    await view.setProps({ restrictedOnly: true })
    expect(view.find('.stock-check').exists()).toBe(false)
    expect(view.findAll('tbody button').map(button => button.text())).toEqual(['调仓', '详情', '调仓', '详情'])
    await view.get('[aria-label="库存限制类型"]').setValue('REJECTED')
    expect(view.findAll('tbody tr')).toHaveLength(1)
    expect(view.get('tbody').text()).toContain('布料BAD')
    await view.findAll('tbody button').find(button => button.text() === '调仓')!.trigger('click')
    expect(view.emitted('action')).toEqual([['TRANSFER', 'BAD']])
    expect(view.emitted('bulk')).toBeUndefined()
  })
  it('searches all batches before paging and computes exact filtered totals per unit', async () => {
    const view = open(Array.from({ length: 32 }, (_, i) => batch(String(i), { item_name: i >= 30 ? '目标布料' : '其他布料', quantity: i === 31 ? '0.2' : '0.1' })))
    expect(view.findAll('tbody tr')).toHaveLength(30)
    expect(view.find('.stock-search').exists()).toBe(false)
    search.value = '目标布料'; await flushPromises()
    expect(view.findAll('tbody tr')).toHaveLength(2)
    expect(view.get('.stock-total-quantity').text()).toContain('0.3码')
    expect(view.get('.stock-footer').text()).toContain('显示 1–2')
    await view.get('[aria-label="库存原单位"]').setValue('码')
    expect(view.findAll('tbody tr')).toHaveLength(2)
  })
  it('filters warehouse, location, category, source, unit and inclusive original receipt dates', async () => {
    const view = open([batch('A'), batch('B', { warehouse_name: 'B', location_id: 'B1', location_label: 'B / B1', material_category: 'THREAD', unit: '筒', counterparty: '线厂', received_on: '2026-10-12' })])
    await view.get('[aria-label="库存仓位"]').setValue('A1')
    await view.get('[aria-label="库存仓库"]').setValue('B')
    expect(view.get<HTMLSelectElement>('[aria-label="库存仓位"]').element.value).toBe('')
    await view.get('[aria-label="库存物料分类"]').setValue('THREAD')
    await view.get('[aria-label="库存来源单位"]').setValue('线厂')
    await view.get('[aria-label="库存原单位"]').setValue('筒')
    view.findComponent({ name: 'DateRangeFilter' }).vm.$emit('update:modelValue', { start: new CalendarDate(2026, 10, 12), end: new CalendarDate(2026, 10, 12) })
    await flushPromises()
    expect(view.findAll('tbody tr')).toHaveLength(1)
    expect(view.get('tbody').text()).toContain('布料B')
    expect(view.get('.stock-total-quantity').text()).toContain('0.1筒')
    view.findComponent({ name: 'DateRangeFilter' }).vm.$emit('update:modelValue', { start: new CalendarDate(2026, 10, 13), end: undefined })
    await flushPromises(); expect(view.findAll('tbody tr')).toHaveLength(0)
    await view.findAll('button').find(button => button.text() === '重置筛选')!.trigger('click')
    expect(view.findAll('tbody tr')).toHaveLength(2)
    expect(search.value).toBe('')
  })
  it('separates available, unverified, restricted and zero stock without treating pending inspection as blocked', async () => {
    const view = open([batch('READY'), batch('OLD', { location_verified: false }), batch('HOLD', { quality_status: 'HOLD' }), batch('ZERO', { quantity: '0' })], false)
    for (const [state, name] of [['AVAILABLE', 'READY'], ['UNVERIFIED', 'OLD'], ['RESTRICTED', 'HOLD'], ['EMPTY', 'ZERO']]) {
      await view.get('[aria-label="库存状态"]').setValue(state)
      expect(view.findAll('tbody tr')).toHaveLength(1)
      expect(view.get('tbody').text()).toContain('布料' + name)
    }
    expect(view.text()).toContain('只读查看')
    expect(view.emitted('action')).toBeUndefined()
  })
  it('keeps stable selected batches across sorting, flags hidden choices, and removes unavailable choices after refresh', async () => {
    const a = batch('A'), b = batch('B', { quantity: '10' })
    const view = open([a, b])
    await view.get('[aria-label="选择库存 A"]').setValue(true)
    expect(view.get<HTMLInputElement>('[aria-label="选择当前页可出库库存"]').element.indeterminate).toBe(true)
    await view.get('[aria-label="库存排序"]').setValue('QUANTITY_DESC')
    expect(view.get('tbody tr').text()).toContain('布料B')
    search.value = '布料B'; await flushPromises()
    expect(view.text()).toContain('其中 1 项不在当前页')
    await view.findAll('button').find(button => button.text() === '仅保留当前页选择')!.trigger('click')
    expect(view.text()).not.toContain('其中 1 项不在当前页')
    await view.get('[aria-label="选择库存 B"]').setValue(true)
    await view.setProps({ loading: true })
    expect(view.text()).toContain('已选 1 项库存')
    await view.setProps({ rows: [a, { ...b, quantity: '0' }], loading: false })
    expect(view.text()).not.toContain('已选 1 项库存')
    expect(view.emitted('bulk')).toBeUndefined()
  })
  it('sorts numeric codes, exact six-place quantities and unknown dates predictably without mutating rows', () => {
    const rows = [batch('B10', { quantity: '9007199254.100002', received_on: '' }), batch('B2', { quantity: '9007199254.100001' }), batch('M', { unit: '米', quantity: '1', received_on: '2026-09-01' })]
    expect(sortStockRows(rows, 'ITEM').map(row => row.id)).toEqual(['B2', 'B10', 'M'])
    expect(sortStockRows(rows, 'QUANTITY_ASC').filter(row => row.unit === '码').map(row => row.id)).toEqual(['B2', 'B10'])
    expect(sortStockRows(rows, 'DATE_DESC').map(row => row.id)).toEqual(['B2', 'M', 'B10'])
    expect(sortStockRows(rows, 'DATE_ASC').map(row => row.id)).toEqual(['M', 'B2', 'B10'])
    expect(rows.map(row => row.id)).toEqual(['B10', 'B2', 'M'])
  })
})
