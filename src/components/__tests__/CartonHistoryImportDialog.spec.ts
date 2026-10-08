import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Dialog from '../CartonHistoryImportDialog.vue'
const api = vi.hoisted(() => ({ previewHistoryOrders: vi.fn(), uploadHistoryOrders: vi.fn() }))
vi.mock('@/api/cartonProcurement', () => ({ cartonProcurementApi: api }))
const file = new File(['xlsx'], '历史订单.xlsx')
function preview() {
  return { factory_id: 'huaxing', original_filename: file.name, source_fingerprint: 'reviewed-file',
    row_count: 1, group_count: 1, line_count: 1, ready_count: 0, draft_count: 1, skipped_count: 0, errors: [] as string[], warnings: [],
    orders: [{ source_rows: ['历史订单:3'], order_no: 'H1', customer_name: '客户', contract_no: '001', item_no: '002', product_name: '',
      product_order_quantity: null, order_date: '2026-09-01', due_date: '2026-09-10', customer_due_date: null,
      status: 'CONFIRMED', quantity_basis: 'EXPLICIT', duplicate: false, ready: false, warnings: [],
      lines: [{ packaging_type: '外箱', paper_quality: '', specification: '', dimension_unit: 'cm', usage_quantity: null, required_quantity: '100', unit: '个', unit_price: '0', currency: 'CNY', note: '' }] }] }
}
describe('historical order review', () => {
  beforeEach(() => { vi.resetAllMocks(); api.previewHistoryOrders.mockResolvedValue(preview()) })
  it('keeps unknown quantities visible and writes only after explicit review', async () => {
    const result = { imported_count: 1 }
    api.uploadHistoryOrders.mockResolvedValue(result)
    const wrapper = mount(Dialog, { props: { file, factoryId: 'huaxing' } })
    await flushPromises()
    expect(wrapper.text()).toContain('产品数量 未记录')
    expect(wrapper.text()).toContain('100 个')
    expect(wrapper.text()).toContain('待补齐')
    expect(api.uploadHistoryOrders).not.toHaveBeenCalled()
    await wrapper.trigger('click')
    expect(wrapper.emitted('close')).toBeUndefined()
    await wrapper.findAll('button').find(b => b.text() === '确认历史已下单并导入')!.trigger('click')
    await flushPromises()
    expect(api.uploadHistoryOrders).toHaveBeenCalledWith('huaxing', file, 'reviewed-file')
    expect(wrapper.emitted('imported')).toEqual([[result]])
  })
  it('blocks the whole import when any row has an error', async () => {
    const data = preview(); data.errors.push('第 4 行计划交期缺少年份')
    api.previewHistoryOrders.mockResolvedValue(data)
    const wrapper = mount(Dialog, { props: { file, factoryId: 'huaxing' } })
    await flushPromises()
    expect(wrapper.findAll('button').find(b => b.text() === '确认历史已下单并导入')!.attributes('disabled')).toBeDefined()
    expect(api.uploadHistoryOrders).not.toHaveBeenCalled()
  })
  it('ignores a preview from the previous factory', async () => {
    let finish!: (value: ReturnType<typeof preview>) => void
    api.previewHistoryOrders.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const wrapper = mount(Dialog, { props: { file, factoryId: 'huaxing' } })
    const current = preview(); current.source_fingerprint = 'other-factory'; current.orders[0]!.customer_name = '当前工厂'
    api.previewHistoryOrders.mockResolvedValue(current)
    await wrapper.setProps({ factoryId: 'other' }); await flushPromises()
    finish(preview()); await flushPromises()
    expect(wrapper.text()).toContain('当前工厂')
    expect(wrapper.text()).not.toContain('客户 · 001')
  })
})

describe('historical order packed-goods weights', () => {
  beforeEach(() => vi.clearAllMocks())
  it('shows both weights before confirmation and distinguishes zero from unknown', async () => {
    api.previewHistoryOrders.mockResolvedValue({ errors: [], warnings: [], orders: [{
      customer_name: '迪奇', contract_no: 'C1', item_no: 'ITEM1', source_rows: ['第3行'], warnings: [],
      lines: [
        { packaging_type: '外箱', net_weight_kg: '8.125', gross_weight_kg: '9.25', unit_price: '1' },
        { packaging_type: '内箱', net_weight_kg: '0', gross_weight_kg: '0', unit_price: '1' },
        { packaging_type: '卡纸', net_weight_kg: null, gross_weight_kg: null, unit_price: '1' },
      ],
    }] })
    const wrapper = mount(Dialog, { props: { file: new File(['xlsx'], 'history.xlsx'), factoryId: 'huaxing' } })
    await flushPromises()
    expect(wrapper.text()).toContain('净重不含纸箱、配卡等包装')
    expect(wrapper.findAll('th').map(cell => cell.text())).toContain('每箱净重 kg')
    expect(wrapper.findAll('th').map(cell => cell.text())).toContain('每箱毛重 kg')
    const rows = wrapper.findAll('tbody tr')
    expect(rows[0]!.findAll('td').slice(5, 7).map(cell => cell.text())).toEqual(['8.125', '9.25'])
    expect(rows[1]!.findAll('td').slice(5, 7).map(cell => cell.text())).toEqual(['0', '0'])
    expect(rows[2]!.findAll('td').slice(5, 7).map(cell => cell.text())).toEqual(['未记录', '未记录'])
    expect(api.uploadHistoryOrders).not.toHaveBeenCalled()
  })
})
