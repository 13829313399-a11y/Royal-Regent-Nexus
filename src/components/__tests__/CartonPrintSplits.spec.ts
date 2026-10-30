import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Component from '../CartonPrintSplitPanel.vue'
import type { CartonOrderResponse } from '@/api/cartonProcurement'
import type { SplitContext } from '@/api/cartonOrderSplits'
const api = vi.hoisted(() => ({ context: vi.fn(), create: vi.fn(), act: vi.fn() }))
vi.mock('@/api/cartonPrintSplits', () => ({ cartonPrintSplitsApi: api, printStatus: { DRAFT: '草稿 · 未发送' } }))
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

beforeEach(() => {
  vi.clearAllMocks()
  api.context.mockResolvedValue({ revision: 4, plans: [], files: [{ id: 'F1', file_name: '印刷.pdf', revision: 1 }] })
  api.create.mockResolvedValue({})
})
async function setup() {
  const wrapper = mount(Component, { props: { order, context, canCreate: true } })
  await flushPromises()
  await wrapper.get('[aria-label="印刷子单 1 合同"]').setValue('NEW')
  await wrapper.get('[aria-label="印刷子单 1 产品数量"]').setValue('40')
  await wrapper.get('[aria-label="子单印刷不同"]').setValue(true)
  await wrapper.get('[aria-label="原单印刷资料"]').setValue(['F1'])
  await wrapper.get('[aria-label="印刷子单 1 资料"]').setValue(['F1'])
  return wrapper
}
describe('不同印刷拆单草稿', () => {
  it('saves quantities and exact files without sending to supplier', async () => {
    const wrapper = await setup()
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.create.mock.calls[0]![2]).toMatchObject({ original_asset_ids: ['F1'], targets: [{ contract_no: 'NEW', asset_ids: ['F1'], lines: [{ order_line_id: 'PAPER1', quantity: '4' }] }] })
    expect(api.act).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('草稿已保存')
    wrapper.unmount()
  })
  it('retries the same frozen command after transport failure but allows correcting validation errors', async () => {
    const wrapper = await setup()
    api.create.mockRejectedValueOnce(new Error('连接中断'))
    await wrapper.get('form').trigger('submit'); await flushPromises()
    const command = api.create.mock.calls[0]![2]
    api.create.mockRejectedValueOnce({ response: { status: 422, data: { detail: '请核对数量' } } })
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.create.mock.calls[1]![2]).toEqual(command)
    expect(wrapper.get('fieldset').attributes('disabled')).toBeUndefined()
    await wrapper.get('[aria-label="印刷子单 1 合同"]').setValue('CORRECTED')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.create.mock.calls[2]![2].request_id).not.toBe(command.request_id)
    wrapper.unmount()
  })
})

describe('统一独立订单拆分', () => {
  it('默认沿用原印刷、无电子文件也可保存真实订单提案', async () => {
    const wrapper = mount(Component, { props: { order, context, canCreate: true } })
    await flushPromises()
    expect(wrapper.find('[aria-label="印刷子单 1 资料"]').exists()).toBe(false)
    await wrapper.get('[aria-label="印刷子单 1 合同"]').setValue('NEW')
    await wrapper.get('[aria-label="印刷子单 1 产品数量"]').setValue('40')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.create.mock.calls[0]![2]).toMatchObject({ print_changed: false, legacy_splits: {}, original_asset_ids: [], targets: [{ asset_ids: [], lines: [{ quantity: '4' }] }] })
    wrapper.unmount()
  })
  it('转换旧分配时只恢复该预占一次，并提交旧记录修订以便原子转换', async () => {
    const old = { id: 'CS-1', factory_id: 'huaxing', order_id: 'ORDER1', order_no: 'CT-1', item_no: '001', customer_code: 'BUZZ', status: 'ACTIVE' as const, revision: 2, reason: '', created_at: '', created_by_name: '', targets: [{ contract_no: 'NEW', customer_po: 'P', product_quantity: '60', lines: [{ order_line_id: 'PAPER1', target_line_id: 'CSL-1', pending_quantity: '6', pending_remaining: '6', received_quantity: '0', packaging_type: '外箱', paper_quality: 'A33', specification: '', unit: '个', stock: [] }] }] }
    const wrapper = mount(Component, { props: { order, context: { ...context, plans: [old], lines: [{ ...context.lines[0]!, pending_available: '1' }] }, canCreate: true } })
    await flushPromises()
    expect(wrapper.get('[aria-label="印刷子单 1 合同"]').element).toHaveProperty('value', 'NEW')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.create.mock.calls[0]![2]).toMatchObject({ legacy_splits: { 'CS-1': 2 }, targets: [{ product_quantity: '60', lines: [{ quantity: '6' }] }] })
    wrapper.unmount()
  })
})
