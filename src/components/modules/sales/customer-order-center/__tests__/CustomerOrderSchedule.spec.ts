import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import CustomerOrderSchedule from '../CustomerOrderSchedule.vue'

const api = vi.hoisted(() => ({ customers: vi.fn(), get: vi.fn() }))
vi.mock('@/api/customerOrderSchedule', () => ({ customerOrderScheduleApi: api }))
vi.mock('../CustomerOrderLedger.vue', () => ({
  default: {
    name: 'CustomerOrderLedger',
    props: ['factoryId', 'factoryName', 'detailOnly', 'focusLineId'],
    emits: ['changed', 'close-detail'],
    template: '<aside data-testid="ledger-detail"><button type="button" @click="$emit(\'changed\')">保存详情</button><button type="button" @click="$emit(\'close-detail\')">关闭详情</button></aside>',
  },
}))

const line = {
  id: 'line-1', factory_id: 'huaxing', customer_code: 'buzzbee', customer_name: 'BuzzBee', reference_no: 'REF-001', product_no: 'P-001', quantity: '100', shipped_quantity: '20', remaining_quantity: '80', status: 'active' as const, version: 2, revision: 1, dispatch_status: 'sent' as const,
  data: { contract_no: 'CT-9', po_no: 'PO-0007', product_name_zh: '小熊', product_name_en: 'Bear', requested_ship_date: '2026-10-10', packaging: '彩盒', label: true }, created_at: '', updated_at: '',
}

function result(overrides: Record<string, unknown> = {}) {
  return {
    factory_id: 'huaxing', customer_code: 'buzzbee', customer_name: 'BuzzBee',
    columns: [{ key: 'packaging', label: '包装' }, { key: 'label', label: '标签' }, { key: 'note', label: '备注' }, { key: 'carton_mark', label: '箱唛' }, { key: 'extra', label: '客户字段' }],
    summary: { order_count: 2, ordered_quantity: '200', shipped_quantity: '120', remaining_quantity: '80', unknown_quantity_count: 1, cancelled_count: 1 },
    sections: {
      unshipped: { items: [line], total: 51, page: 1, page_size: 50 },
      shipped: { items: [{ ...line, id: 'line-2', remaining_quantity: '0' }], total: 1, page: 1, page_size: 50 },
      cancelled: { items: [{ ...line, id: 'line-3', status: 'cancelled' as const, remaining_quantity: '99' }], total: 1, page: 1, page_size: 50 },
    },
    ...overrides,
  }
}

function mountSchedule() {
  api.customers.mockResolvedValue({ factory_id: 'huaxing', items: [{ code: 'buzzbee', name: 'BuzzBee' }] })
  api.get.mockResolvedValue(result())
  return mount(CustomerOrderSchedule, { props: { factoryId: 'huaxing', factoryName: '华兴厂' } })
}

async function chooseAndApply(wrapper: ReturnType<typeof mount>) {
  await flushPromises()
  await wrapper.get('select').setValue('buzzbee')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
}

describe('CustomerOrderSchedule', () => {
  it('requires a customer, shows persisted section totals, mapped fields and cancellation rules', async () => {
    const wrapper = mountSchedule()
    await flushPromises()
    await wrapper.get('form').trigger('submit')
    expect(api.get).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('请先选择客户')

    await chooseAndApply(wrapper)
    expect(api.get).toHaveBeenCalledWith('huaxing', expect.objectContaining({ customerCode: 'buzzbee', unshippedPage: 1, shippedPage: 1, cancelledPage: 1, pageSize: 50 }))
    expect(wrapper.text()).toContain('订单数')
    expect(wrapper.text()).toContain('数量汇总按订单只计算一次')
    expect(wrapper.text()).toContain('有 1 条订单数量无法汇总')
    expect(wrapper.text()).toContain('REF-001')
    expect(wrapper.text()).toContain('PO-0007')
    expect(wrapper.text()).toContain('部分走货的订单仍会在这里显示剩余数量')
    expect(wrapper.text()).toContain('已取消订单的未走货数量为 0')
    expect(wrapper.text()).toContain('包装')
    expect(wrapper.findAll('th').map((header) => header.text())).not.toContain('客户字段')
  })

  it('keeps applied filters while paging each section independently', async () => {
    const wrapper = mountSchedule()
    await chooseAndApply(wrapper)
    await wrapper.get('input[type="search"]').setValue('draft-only')
    api.get.mockResolvedValue(result({ sections: { ...result().sections, unshipped: { items: [], total: 51, page: 2, page_size: 50 } } }))
    const sections = wrapper.findAll('.customer-schedule__section')
    await sections[0]!.findAll('button').find((button) => button.text() === '下一页')!.trigger('click')
    await flushPromises()
    expect(api.get).toHaveBeenLastCalledWith('huaxing', expect.objectContaining({ q: '', unshippedPage: 2, shippedPage: 1, cancelledPage: 1 }))
  })

  it('does not apply an old response and clears rows if the returned scope is wrong', async () => {
    let resolveFirst: ((value: ReturnType<typeof result>) => void) | undefined
    api.get.mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve }))
    const wrapper = mountSchedule()
    await flushPromises()
    await wrapper.get('select').setValue('buzzbee')
    await wrapper.get('form').trigger('submit')
    await wrapper.get('input[type="search"]').setValue('new')
    api.get.mockResolvedValueOnce(result({ customer_code: 'other' }))
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('返回数据与当前厂区或客户不一致')
    expect(wrapper.text()).not.toContain('REF-001')
    resolveFirst?.(result())
    await flushPromises()
    expect(wrapper.text()).not.toContain('REF-001')
  })

  it('refreshes all schedule sections after a saved detail and closes its detail view', async () => {
    const wrapper = mountSchedule()
    await chooseAndApply(wrapper)
    await wrapper.findAll('.customer-schedule__link')[0]!.trigger('click')
    expect(wrapper.get('[data-testid="ledger-detail"]').exists()).toBe(true)
    await wrapper.get('[data-testid="ledger-detail"] button').trigger('click')
    await flushPromises()
    expect(api.get).toHaveBeenLastCalledWith('huaxing', expect.objectContaining({ unshippedPage: 1, shippedPage: 1, cancelledPage: 1 }))
    await wrapper.get('[data-testid="ledger-detail"] button:last-child').trigger('click')
    expect(wrapper.find('[data-testid="ledger-detail"]').exists()).toBe(false)
  })

  it('rejects a cross-customer row even when the response envelope matches', async () => {
    const wrapper = mountSchedule()
    api.get.mockResolvedValueOnce(result({ sections: { ...result().sections, shipped: { items: [{ ...line, customer_code: 'disney' }], total: 1, page: 1, page_size: 50 } } }))
    await chooseAndApply(wrapper)
    expect(wrapper.text()).toContain('返回数据与当前厂区或客户不一致')
    expect(wrapper.text()).not.toContain('REF-001')
  })

  it('uses the returned page after a page is clamped by the server', async () => {
    const wrapper = mountSchedule()
    await chooseAndApply(wrapper)
    api.get.mockResolvedValueOnce(result({ sections: { ...result().sections, unshipped: { items: [line], total: 1, page: 1, page_size: 50 } } }))
    await wrapper.findAll('.customer-schedule__section')[0]!.findAll('button').find((button) => button.text() === '下一页')!.trigger('click')
    await flushPromises()
    await wrapper.findAll('.customer-schedule__link')[0]!.trigger('click')
    await wrapper.get('[data-testid="ledger-detail"] button').trigger('click')
    await flushPromises()
    expect(api.get).toHaveBeenLastCalledWith('huaxing', expect.objectContaining({ unshippedPage: 1 }))
  })
})
