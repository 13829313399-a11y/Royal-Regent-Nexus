import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import CartonInventorySummary from '../CartonInventorySummary.vue'
import type { InventoryReport } from '@/api/cartonInventoryReport'
import type { CartonCustomerResponse } from '@/api/cartonProcurement'

const api = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/api/cartonInventoryReport', () => ({ cartonInventoryReportApi: api }))
const customer = { factory_id: 'huaxing', customer_code: 'C1', customer_name: '360' } as CartonCustomerResponse
function data(): InventoryReport {
  const base = { business_date: '2026-09-07', customer_code: 'C1', customer_name: '360', opening_quantity: '0', inbound_quantity: '10', outbound_quantity: '4', adjustment_quantity: '0', ending_quantity: '6', document_count: 3, line_count: 3 }
  const order = { ...base, key: 'LINE-1', order_id: 'ORDER-1', order_line_id: 'LINE-1', order_date: '2026-09-01', contract_no: 'CONTRACT-1', item_no: 'ITEM-1', product_name: '消防车', packaging_type: '外箱', paper_quality: 'A33', specification: '1*1*1', last_movement_at: '2026-09-07T09:00:00+08:00', unit: '个' }
  return {
    order_rows: [order, { ...order, key: 'LINE-2', order_line_id: 'LINE-2', unit: '张', packaging_type: '滑板纸', inbound_quantity: '1000', outbound_quantity: '0', ending_quantity: '1000' }],
    rows: [{ ...base, unit: '个' }, { ...base, unit: '张', inbound_quantity: '1000', outbound_quantity: '0', ending_quantity: '1000' }],
    movements: [{ id: 'R1', occurred_at: '2026-09-07T09:00:00+08:00', customer_code: 'C1', customer_name: '360', contract_no: 'CONTRACT-1', item_no: 'ITEM-1', packaging_type: '外箱', paper_quality: 'A33', specification: '1*1*1', unit: '个', document_no: 'REVERSE-OUT-1', movement_type: 'REVERSAL', quantity: '2', flow_category: 'OUTBOUND', flow_quantity: '-2', source_type: 'REVERSAL', reason: '错误出库冲销', location: 'A01', actor_name: '仓管' }],
  }
}
function open() {
  return mount(CartonInventorySummary, { props: { factoryId: 'huaxing', customers: [customer], search: '', refreshKey: 0, connected: true } })
}
beforeEach(() => { vi.clearAllMocks(); api.get.mockResolvedValue(data()) })
describe('库存汇总工作台', () => {
  it('keeps unlike units separate and preserves contract and negative reversal in detail', async () => {
    const wrapper = open(); await flushPromises()
    expect(api.get).toHaveBeenCalledWith('huaxing', { customer_code: '', date_from: '', date_to: '', search: '' })
    const table = wrapper.get('[aria-label="收发汇总表"]')
    expect(table.findAll('tbody tr')).toHaveLength(2)
    expect(table.text()).toContain('CONTRACT-1')
    expect(table.text()).toContain('消防车')
    expect(wrapper.text()).toContain('1 张订单 · 2 项纸品')
    expect(wrapper.text()).not.toContain('1,010')
    await wrapper.findAll('[role="tab"]').find(tab => tab.text() === '出库明细')!.trigger('click')
    const details = wrapper.get('[aria-label="库存汇总明细表"]')
    expect(details.text()).toContain('CONTRACT-1')
    expect(details.text()).toContain('冲销')
    expect(details.text()).toContain('-2')
    expect(details.findAll('button')).toHaveLength(0)
  })
  it('sends the customer code and inclusive dates to the same report source', async () => {
    const wrapper = open(); await flushPromises()
    await wrapper.get('[aria-label="库存汇总客户"]').setValue('C1'); await flushPromises()
    expect(api.get.mock.lastCall?.[1].customer_code).toBe('C1')
    wrapper.findComponent({ name: 'DateRangeFilter' }).vm.$emit('update:modelValue', { start: { toString: () => '2026-09-01' }, end: { toString: () => '2026-09-07' } })
    await flushPromises()
    expect(api.get.mock.lastCall?.[1]).toMatchObject({ customer_code: 'C1', date_from: '2026-09-01', date_to: '2026-09-07' })
    await wrapper.findAll('button').find(button => button.text() === '清空筛选')!.trigger('click'); await flushPromises()
    expect(wrapper.emitted('clearSearch')).toHaveLength(1)
    expect(api.get.mock.lastCall?.[1]).toMatchObject({ customer_code: '', date_from: '', date_to: '' })
  })
  it('rejects a late response from the previous factory', async () => {
    let finishOld!: (result: InventoryReport) => void
    api.get.mockImplementationOnce(() => new Promise(resolve => { finishOld = resolve }))
    const wrapper = open(); await flushPromises()
    api.get.mockResolvedValue({ rows: [], order_rows: [], movements: [] })
    await wrapper.setProps({ factoryId: 'huakang_a' }); await flushPromises()
    finishOld(data()); await flushPromises()
    expect(wrapper.text()).not.toContain('1,000')
    expect(wrapper.text()).toContain('所选条件下没有订单或库存记录')
  })
  it('removes stale totals on a refresh failure and can retry without writing data', async () => {
    const wrapper = open(); await flushPromises()
    api.get.mockRejectedValueOnce(new Error('report unavailable'))
    await wrapper.setProps({ refreshKey: 1 }); await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="收发汇总表"]').exists()).toBe(false)
    await wrapper.findAll('button').find(button => button.text() === '重新读取')!.trigger('click'); await flushPromises()
    expect(wrapper.find('[aria-label="收发汇总表"]').exists()).toBe(true)
  })
  it('does not restore old data while a shared search is waiting to run', async () => {
    vi.useFakeTimers()
    try {
      let finishOld!: (result: InventoryReport) => void
      api.get.mockImplementationOnce(() => new Promise(resolve => { finishOld = resolve }))
      const wrapper = open(); await flushPromises()
      await wrapper.setProps({ search: 'CONTRACT-2' })
      finishOld(data()); await flushPromises()
      expect(wrapper.find('[aria-label="收发汇总表"]').exists()).toBe(false)
      api.get.mockResolvedValue({ rows: [], order_rows: [], movements: [] })
      await vi.advanceTimersByTimeAsync(250); await flushPromises()
      expect(api.get.mock.lastCall?.[1].search).toBe('CONTRACT-2')
      expect(wrapper.text()).toContain('所选条件下没有订单或库存记录')
      wrapper.unmount()
    } finally { vi.useRealTimers() }
  })
  it('retains four-decimal totals beyond the safe floating point range', async () => {
    const report = data()
    report.order_rows = [
      { ...report.order_rows[0]!, inbound_quantity: '99999999999999.0001' },
      { ...report.order_rows[0]!, key: 'SECOND', inbound_quantity: '0.0002' },
    ]
    api.get.mockResolvedValue(report)
    const wrapper = open(); await flushPromises()
    expect(wrapper.text()).toContain('99,999,999,999,999.0003')
  })
  it('lists separate orders, zero-receipt lines and standalone stock without merging identities', async () => {
    const report = data()
    report.order_rows.push(
      { ...report.order_rows[0]!, key: 'L3', order_id: 'O2', order_line_id: 'L3', contract_no: 'CONTRACT-2', inbound_quantity: '0', outbound_quantity: '0', ending_quantity: '0', line_count: 0 },
      { ...report.order_rows[0]!, key: 'HIST', order_id: null, order_line_id: null, contract_no: '', order_date: '' },
    )
    api.get.mockResolvedValue(report)
    const wrapper = open(); await flushPromises()
    const rows = wrapper.get('[aria-label="收发汇总表"]').findAll('tbody tr')
    expect(rows).toHaveLength(4)
    expect(rows[2]!.text()).toContain('CONTRACT-2')
    expect(rows[2]!.text()).toContain('暂无收发')
    expect(rows[3]!.text()).toContain('无单库存')
    expect(wrapper.text()).toContain('2 张订单 · 4 项纸品（含 1 项无单库存）')
  })
  it('opens only the current order on click and closes on scope change', async () => {
    const wrapper = mount(CartonInventorySummary, {
      props: { factoryId: 'huaxing', customers: [customer], search: '', refreshKey: 0, connected: true },
      global: { stubs: { CartonOrderTimeline: true } },
    })
    await flushPromises()
    expect(wrapper.findAll('[role="tab"]').map(tab => tab.text())).not.toContain('订单流水明细')
    const button = wrapper.get('tbody button')
    await button.trigger('mouseenter')
    expect(wrapper.find('[data-testid="order-timeline-overlay"]').exists()).toBe(false)
    await button.trigger('mouseleave')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    await button.trigger('focus')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    await button.trigger('blur')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    await button.trigger('mouseenter')
    await button.trigger('click')
    await button.trigger('mouseleave')
    expect(wrapper.get('[role="dialog"]').attributes('aria-modal')).toBe('true')
    expect(wrapper.get('[aria-label="收发汇总表"]').exists()).toBe(true)
    const timeline = wrapper.findComponent({ name: 'CartonOrderTimeline' })
    expect(timeline.props('orderId')).toBe('ORDER-1')
    expect(timeline.props('inventoryKey')).toBe('')
    expect(timeline.props('dateFrom')).toBe('')
    expect(timeline.props('search')).toBe('')
    await wrapper.get('[aria-label="关闭订单流水"]').trigger('click')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    await button.trigger('click')
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    await button.trigger('click')
    await wrapper.get('[aria-label="库存汇总客户"]').setValue('C1'); await flushPromises()
    expect(wrapper.findComponent({ name: 'CartonOrderTimeline' }).exists()).toBe(false)
    wrapper.unmount()
  })
})
