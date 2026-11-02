import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Component from '../CartonIndependentSplitPanel.vue'
import type { CartonOrderResponse } from '@/api/cartonProcurement'
import type { SplitContext } from '@/api/cartonOrderSplits'
import type { DivisionContext } from '@/api/cartonOrderDivisions'
const api = vi.hoisted(() => ({ create: vi.fn() }))
vi.mock('@/api/cartonOrderDivisions', () => ({ cartonOrderDivisionsApi: api }))

const order: CartonOrderResponse = {
  id: 'ORDER1', factory_id: 'huaxing', order_no: 'CT-1', customer_code: 'BUZZ', customer_name: 'BUZZ', supplier_id: 'SUP1',
  supplier_name: '供应商', contract_no: 'OLD', customer_po: 'OLD-PO', item_no: '001', product_name: '产品', quantity_basis: 'CALCULATED',
  product_order_quantity: '100', order_date: '2026-09-01', due_date: '2026-09-30', status: 'PARTIALLY_RECEIVED', note: '', revision: 4,
  created_by: 'u1', created_by_name: '用户', updated_by: 'u1', updated_by_name: '用户', created_at: '', updated_at: '',
  lines: [{ id: 'PAPER1', line_no: 1, packaging_type: '外箱', paper_quality: 'A33', specification: '18*12*10', dimension_unit: 'cm',
    usage_quantity: '10', required_quantity: '10', received_quantity: '3', remaining_quantity: '7', unit: '个', unit_price: '1',
    currency: 'CNY', price_source: 'manual', note: '' }],
}
const context: SplitContext = {
  factory_id: 'huaxing', order_no: 'CT-1', revision: 4, plans: [],
  lines: [{ order_line_id: 'PAPER1', packaging_type: '外箱', paper_quality: 'A33', specification: '18*12*10', unit: '个',
    usage_quantity: '10', required_quantity: '10', pending_available: '7', positions: [{ inventory_key: 'PAPER1', factory_id: 'huaxing',
      customer_code: 'BUZZ', customer_name: 'BUZZ', contract_no: 'OLD', item_no: '001', order_line_id: 'PAPER1', packaging_type: '外箱',
      paper_quality: 'A33', specification: '18*12*10', unit: '个', balance: '3', location_id: 'A1', position_revision: 6,
      latest_location: 'A车间／A1', location_revision: 0, latest_movement_id: 'IN1', latest_document_no: 'DN1', latest_movement_at: '',
      latest_inbound_at: '', position_key: '["PAPER1","A1"]' }] }],
}

const divisionContext: DivisionContext = { ...context, supplier_notified: false, can_split: true, block_reason: '', order_split: null, previous_proposals: [] }
beforeEach(() => { vi.clearAllMocks(); api.create.mockResolvedValue({ id: 'COS-1', supplier_notified: false, members: [] }) })
async function setup(sent = false) {
  const wrapper = mount(Component, { props: { order, context: { ...divisionContext, supplier_notified: sent }, canCreate: true } })
  await wrapper.get('[aria-label="子单 1 合同"]').setValue('NEW')
  await wrapper.get('[aria-label="子单 1 产品数量"]').setValue('40')
  return wrapper
}
describe('普通独立订单拆分', () => {
  it('一次确认完成未发送订单拆分，没有资料或印刷选择', async () => {
    const wrapper = await setup()
    expect(wrapper.find('select').exists()).toBe(false)
    expect(wrapper.find('[aria-label="子单印刷不同"]').exists()).toBe(false)
    expect(wrapper.get('[aria-label="拆分数量核对"]').text()).toContain('6')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.create.mock.calls[0]![2]).toMatchObject({ expected_revision: 4, targets: [{ contract_no: 'NEW', lines: [{ order_line_id: 'PAPER1', quantity: '4' }] }] })
    expect(api.create.mock.calls[0]![2]).not.toHaveProperty('original_asset_ids')
    expect(wrapper.emitted('completed')).toHaveLength(1)
    wrapper.unmount()
  })
  it('已发送订单明确提示普通变更通知，仍一次生成独立订单', async () => {
    const wrapper = await setup(true)
    expect(wrapper.get('[type="submit"]').text()).toBe('确认拆分并通知供应商')
    expect(wrapper.text()).toContain('现有订单变更待办')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.create).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
  it('结果未知时保留并重试同一请求，验证错误允许修改', async () => {
    const wrapper = await setup()
    api.create.mockRejectedValueOnce(new Error('连接中断'))
    await wrapper.get('form').trigger('submit'); await flushPromises()
    const command = api.create.mock.calls[0]![2]
    api.create.mockRejectedValueOnce({ response: { status: 422 } })
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.create.mock.calls[1]![2]).toEqual(command)
    expect(wrapper.get('fieldset').attributes('disabled')).toBeUndefined()
    await wrapper.get('[aria-label="子单 1 合同"]').setValue('CHANGED')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.create.mock.calls[2]![2].request_id).not.toBe(command.request_id)
    wrapper.unmount()
  })
  it('手工需求允许只拆一种纸品，空白和零不会生成虚假子行', async () => {
    const explicit = { ...order, quantity_basis: 'EXPLICIT' as const, product_order_quantity: null,
      lines: [order.lines[0]!, { ...order.lines[0]!, id: 'PAPER2', line_no: 2, packaging_type: '内箱' }] }
    const ctx = { ...divisionContext, lines: [context.lines[0]!, { ...context.lines[0]!, order_line_id: 'PAPER2', packaging_type: '内箱' }] }
    const wrapper = mount(Component, { props: { order: explicit, context: ctx, canCreate: true } })
    await wrapper.get('[aria-label="子单 1 合同"]').setValue('PARTIAL')
    await wrapper.get('[aria-label="子单 1 内箱拆出数量"]').setValue('3')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.create.mock.calls[0]![2].targets[0].lines).toEqual([{ order_line_id: 'PAPER2', quantity: '3' }])
    expect(api.create.mock.calls[0]![2].targets[0].product_quantity).toBeNull()
    wrapper.unmount()
  })
  it('完成单只读，不显示可提交的拆单表单', () => {
    const wrapper = mount(Component, { props: { order: { ...order, status: 'COMPLETED' }, context: { ...divisionContext, can_split: false, block_reason: '没有可拆需求' }, canCreate: true } })
    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.text()).toContain('没有可拆需求')
    wrapper.unmount()
  })
})
