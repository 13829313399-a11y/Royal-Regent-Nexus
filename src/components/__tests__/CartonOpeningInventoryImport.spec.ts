import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Component from '../CartonOpeningInventoryImport.vue'
const api = vi.hoisted(() => ({ previewHistoryInventory: vi.fn(), uploadHistoryInventory: vi.fn() }))
vi.mock('@/api/cartonProcurement', () => ({ cartonProcurementApi: api }))
const file = new File(['xlsx'], '期初库存.xlsx')
const options = { customer_name: '迪奇', warehouse: 'A', dimension_unit: 'in', currency: 'CNY' }
const props = { factoryId: 'huaxing', connected: true, canImport: true,
  customers: [{ customer_name: '迪奇', customer_code: 'D', status: 'ACTIVE' }],
  locations: [{ id: 'L1', factory_id: 'huaxing', warehouse: 'A', bin_code: 'A1', label: 'A／A1', status: 'ACTIVE' }] }
function preview() {
  return { factory_id: 'huaxing', original_filename: file.name, source_fingerprint: 'checked-evidence', row_count: 2, skipped_count: 1, missing_price_count: 1, warnings: [], errors: [] as string[],
    rows: [{ source: '第3行', customer_name: '迪奇', contract_no: 'SC1', item_no: '001', packaging_type: '平卡', paper_quality: 'H5A', specification: '7.5*13.625*0 in', unit: '张', opening_quantity: '30', unit_price: null, amount: null, currency: 'CNY', location: 'A／A1', status: 'READY', warnings: [] },
      { source: '第4行', customer_name: '迪奇', contract_no: 'SC2', item_no: '002', packaging_type: '内箱', paper_quality: 'B3B', specification: '15*10*6 in', unit: '个', opening_quantity: '0', unit_price: '0.96', amount: '0.00', currency: 'CNY', location: 'A／A1', status: 'ZERO', warnings: [] }],
    totals: [{ unit: '张', currency: 'CNY', quantity: '30', amount: null, missing_price_count: 1 }] }
}
async function configure(wrapper: VueWrapper) {
  await wrapper.get('[aria-label="期初库存客户"]').setValue('迪奇')
  await wrapper.get('[aria-label="期初库存仓库"]').setValue('A')
  await wrapper.get('[aria-label="期初尺寸单位"]').setValue('in')
}
async function choose(wrapper: VueWrapper) {
  const input = wrapper.get('[aria-label="选择历史库存文件"]')
  Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
  await input.trigger('change'); await flushPromises()
}
function button(wrapper: VueWrapper, text: string) { return wrapper.findAll('button').find(item => item.text() === text)! }
describe('opening inventory import', () => {
  beforeEach(() => { vi.resetAllMocks(); api.previewHistoryInventory.mockResolvedValue(preview()) })
  it('keeps the selected file while the user fills required settings', async () => {
    const wrapper = mount(Component, { props })
    expect(button(wrapper, '导入期初库存').attributes('disabled')).toBeUndefined()
    await choose(wrapper)
    expect(api.previewHistoryInventory).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('文件已选择，请补填尺寸单位')
    await button(wrapper, '重新预览').trigger('click')
    expect(api.previewHistoryInventory).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('文件已选择，请补填尺寸单位')
    await wrapper.get('[aria-label="期初尺寸单位"]').setValue('in')
    await button(wrapper, '重新预览').trigger('click'); await flushPromises()
    expect(api.previewHistoryInventory).toHaveBeenCalledWith('huaxing', file, { ...options, customer_name: '', warehouse: '' })
    expect(api.uploadHistoryInventory).not.toHaveBeenCalled()
  })
  it('allows row-specific customers and warehouses without batch defaults', async () => {
    const wrapper = mount(Component, { props })
    await wrapper.get('[aria-label="期初尺寸单位"]').setValue('in')
    expect(button(wrapper, '导入期初库存').attributes('disabled')).toBeUndefined()
    await choose(wrapper)
    expect(api.previewHistoryInventory).toHaveBeenCalledWith('huaxing', file, { ...options, customer_name: '', warehouse: '' })
  })
  it('previews batch conditions and remaining quantities before explicit posting', async () => {
    const wrapper = mount(Component, { props })
    expect(button(wrapper, '导入期初库存').attributes('disabled')).toBeUndefined()
    expect(wrapper.find('[aria-label="期初基准日期"]').exists()).toBe(false)
    await configure(wrapper); await choose(wrapper)
    expect(api.previewHistoryInventory).toHaveBeenCalledWith('huaxing', file, options)
    expect(wrapper.text()).toContain('待核价')
    expect(wrapper.text()).toContain('零结余，跳过')
    expect(api.uploadHistoryInventory).not.toHaveBeenCalled()
    expect(button(wrapper, '确认导入期初库存').attributes('disabled')).toBeDefined()
    api.uploadHistoryInventory.mockResolvedValue({ imported_count: 1, skipped_count: 1 })
    await wrapper.get('[aria-label="已核对期初库存"]').setValue(true)
    await button(wrapper, '确认导入期初库存').trigger('click'); await flushPromises()
    expect(api.uploadHistoryInventory).toHaveBeenCalledWith('huaxing', file, options, 'checked-evidence')
    expect(wrapper.emitted('imported')).toHaveLength(1)
    expect(wrapper.find('[aria-label="期初库存导入预览"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('已入账 1 行')
  })
  it('invalidates review when dimension unit changes and ignores its late preview', async () => {
    let finish!: (value: ReturnType<typeof preview>) => void
    api.previewHistoryInventory.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const wrapper = mount(Component, { props }); await configure(wrapper); await choose(wrapper)
    await wrapper.get('[aria-label="期初尺寸单位"]').setValue('cm')
    finish(preview()); await flushPromises()
    expect(wrapper.find('[aria-label="期初库存导入预览"]').exists()).toBe(false)
    await button(wrapper, '重新预览').trigger('click'); await flushPromises()
    expect(api.previewHistoryInventory).toHaveBeenLastCalledWith('huaxing', file, { ...options, dimension_unit: 'cm' })
  })
  it('blocks the whole batch when the preview contains amount or location errors', async () => {
    const data = preview(); data.errors.push('第5行金额不一致')
    api.previewHistoryInventory.mockResolvedValue(data)
    const wrapper = mount(Component, { props }); await configure(wrapper); await choose(wrapper)
    expect(wrapper.text()).toContain('本批尚未入账')
    expect(button(wrapper, '确认导入期初库存').attributes('disabled')).toBeDefined()
    expect(api.uploadHistoryInventory).not.toHaveBeenCalled()
  })
  it('keeps the file after a stale/uncertain save so it can be rechecked instead of blindly retried', async () => {
    api.uploadHistoryInventory.mockRejectedValue(new Error('来源已变化'))
    const wrapper = mount(Component, { props }); await configure(wrapper); await choose(wrapper)
    await wrapper.get('[aria-label="已核对期初库存"]').setValue(true)
    await button(wrapper, '确认导入期初库存').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('请重新预览')
    expect(wrapper.find('[aria-label="期初库存导入预览"]').exists()).toBe(false)
    expect(button(wrapper, '重新预览').exists()).toBe(true)
    expect(wrapper.emitted('imported')).toBeUndefined()
  })
  it('discards a confirmation response after changing factory', async () => {
    let finish!: (value: unknown) => void
    api.uploadHistoryInventory.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const wrapper = mount(Component, { props }); await configure(wrapper); await choose(wrapper)
    await wrapper.get('[aria-label="已核对期初库存"]').setValue(true)
    await button(wrapper, '确认导入期初库存').trigger('click')
    await wrapper.setProps({ factoryId: 'huadeng' })
    finish({ imported_count: 1, skipped_count: 0 }); await flushPromises()
    expect(wrapper.emitted('imported')).toBeUndefined()
    expect(wrapper.text()).not.toContain('已入账 1 行')
  })
})
