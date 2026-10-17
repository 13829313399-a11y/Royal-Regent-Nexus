import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import HuakangBJPIntake from '../HuakangBJPIntake.vue'

const api = vi.hoisted(() => ({
  capabilities: vi.fn(), references: vi.fn(), upload: vi.fn(), clearConfirmed: vi.fn(), preview: vi.fn(), export: vi.fn(), exports: vi.fn(), download: vi.fn(),
}))
vi.mock('@/api/huakangBJP', () => ({ huakangBJPApi: api }))
const row = { id: 'a'.repeat(64), source: 'test.eml', baby_item: '67053', long_code: '67053-000-2B-003-WB0',
  qty: '648', customer: 'WMUS', customer_po: '0117978388', country: '美国', pkg: '3L', carton_t: '3',
  ship_date: '2026/12/24', cutoff_date: '2026/12/31', price_t: '12.5', factory_price_t: '10', note: '', exists: false }
const preview = { factory_id: 'huakang-b', fingerprint: 'fingerprint', rows: [row], warnings: [], failed_sources: [], quantity_selections: [] }
const refs = { schedule: { id: 's', name: 'B排期.xlsx', revision: 1 }, price: { id: 'p', name: 'B货价.xlsx', revision: 1 } }
function button(wrapper: ReturnType<typeof mount>, text: string) { return wrapper.findAll('button').find(b => b.text() === text)! }
async function open() {
  const wrapper = mount(HuakangBJPIntake, { props: { factoryId: 'huakang-b' } })
  await flushPromises()
  await wrapper.get('input[aria-label="业务跟单"]').setValue('测试跟单')
  return wrapper
}
beforeEach(() => {
  vi.resetAllMocks()
  api.capabilities.mockResolvedValue({ read: true, write: true, export: true, available: true })
  api.references.mockResolvedValue(refs)
  api.exports.mockResolvedValue({ items: [], total: 0 })
  api.preview.mockResolvedValue(JSON.parse(JSON.stringify(preview)))
})

describe('HuakangBJPIntake', () => {
  it('requires a new currency choice for each confirmation file and retains version checks', async () => {
    const wrapper = await open()
    const input = wrapper.get('input[aria-label="文员已确认货价表（可选）"]')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [new File(['test'], 'confirmed.xlsx')] })
    await input.trigger('change')
    await wrapper.get('select').setValue('USD')
    api.upload.mockResolvedValue({ ...refs, confirmed: { id: 'c', name: 'confirmed.xlsx', revision: 1, options: { currency: 'USD' } } })
    await wrapper.findAll('button').filter(b => b.text() === '验证并更新').at(2)!.trigger('click'); await flushPromises()
    const data = api.upload.mock.calls[0]![1] as FormData
    expect(data.get('currency')).toBe('USD')
    expect(data.get('expected_revision')).toBe('0')
    await input.trigger('change')
    expect((wrapper.get('select').element as HTMLSelectElement).value).toBe('')
    vi.spyOn(window, 'confirm').mockReturnValueOnce(true)
    api.clearConfirmed.mockResolvedValue({ ...refs, confirmed: { id: 'cleared', name: 'JP-confirmed-cleared.xlsx', revision: 2 } })
    await button(wrapper, '停用当前确认价').trigger('click'); await flushPromises()
    expect((api.clearConfirmed.mock.calls[0]![0] as FormData).get('expected_revision')).toBe('1')
    expect(wrapper.text()).toContain('历史版本仍保留')
    vi.restoreAllMocks(); wrapper.unmount()
  })
  it('is factory isolated and never loads another factory', async () => {
    const wrapper = mount(HuakangBJPIntake, { props: { factoryId: 'huakang-a' } })
    await flushPromises()
    expect(api.capabilities).not.toHaveBeenCalled()
    expect(api.references).not.toHaveBeenCalled()
    expect(wrapper.text()).not.toContain('B货价.xlsx')
    wrapper.unmount()
  })
  it('shows current references and requires explicit review before export', async () => {
    const wrapper = await open()
    expect(api.references).toHaveBeenCalledWith('huakang-b', expect.any(AbortSignal))
    await button(wrapper, '解析并核对').trigger('click'); await flushPromises()
    expect(button(wrapper, '确认并生成问单 Excel').attributes('disabled')).toBeDefined()
    await wrapper.findAll('textarea').at(-1)!.setValue('逐项核对正确')
    await wrapper.findAll('input[type=checkbox]').at(-1)!.setValue(true)
    expect(button(wrapper, '确认并生成问单 Excel').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })
  it('keeps edited PO text and sends only explicit field overrides with source fingerprint', async () => {
    const wrapper = await open()
    await button(wrapper, '解析并核对').trigger('click'); await flushPromises()
    await wrapper.get('input[aria-label="客PO"]').setValue('00001234')
    await wrapper.findAll('textarea').at(-1)!.setValue('客户确认修改')
    await wrapper.findAll('input[type=checkbox]').at(-1)!.setValue(true)
    let finish: ((v: { id: string; row_count: number }) => void) | undefined
    api.export.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    await button(wrapper, '确认并生成问单 Excel').trigger('click')
    await button(wrapper, '确认并生成问单 Excel').trigger('click')
    expect(api.export).toHaveBeenCalledTimes(1)
    const data = api.export.mock.calls[0]![0] as FormData
    expect(data.get('factory_id')).toBe('huakang-b')
    expect(data.get('fingerprint')).toBe('fingerprint')
    expect(JSON.parse(String(data.get('overrides')))).toEqual([{ id: row.id, field: 'customer_po', value: '00001234' }])
    finish?.({ id: 'record-1', row_count: 1 }); await flushPromises()
    expect(wrapper.text()).toContain('未写入正式订单或下发生产')
    wrapper.unmount()
  })
  it('does not allow unresolved quantity columns to be exported', async () => {
    api.preview.mockResolvedValue({ ...preview, quantity_selections: [{ source_id: 'a'.repeat(64), source: 'test.eml', table_index: 0, columns: [{ index: 1, sample: '25' }, { index: 2, sample: '648' }] }] })
    const wrapper = await open()
    await button(wrapper, '解析并核对').trigger('click'); await flushPromises()
    await wrapper.get('select[aria-label="数量列"]').setValue('2')
    await button(wrapper, '按所选数量列重新解析').trigger('click'); await flushPromises()
    const data = api.preview.mock.calls.at(-1)![0] as FormData
    expect(JSON.parse(String(data.get('quantity_selections')))).toEqual([{ source_id: 'a'.repeat(64), table_index: 0, column_index: 2 }])
    expect(button(wrapper, '确认并生成问单 Excel').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
  it('clears stale prices after customer/packing edits and submits explicit price review', async () => {
    const wrapper = await open()
    await button(wrapper, '解析并核对').trigger('click'); await flushPromises()
    await wrapper.get('input[aria-label="客名"]').setValue('Amazon US')
    expect((wrapper.get('input[aria-label="货价HKD"]').element as HTMLInputElement).value).toBe('')
    expect(wrapper.text()).toContain('旧价格已清空')
    await wrapper.get('input[aria-label="货价HKD"]').setValue('12.5') // Deliberately reaffirm the same value.
    await wrapper.findAll('textarea').at(-1)!.setValue('按新客名核对货价')
    await wrapper.findAll('input[type=checkbox]').at(-1)!.setValue(true)
    api.export.mockResolvedValue({ id: 'test', row_count: 1 })
    await button(wrapper, '确认并生成问单 Excel').trigger('click'); await flushPromises()
    const changes = JSON.parse(String((api.export.mock.calls[0]![0] as FormData).get('overrides')))
    expect(changes).toEqual(expect.arrayContaining([
      { id: row.id, field: 'price_t', value: '12.5' },
      { id: row.id, field: 'factory_price_t', value: '' },
    ]))
    wrapper.unmount()
  })
  it('rejects a response belonging to another factory', async () => {
    api.preview.mockResolvedValue({ ...preview, factory_id: 'huakang-a' })
    const wrapper = await open()
    await button(wrapper, '解析并核对').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('厂区不一致')
    expect(wrapper.find('input[aria-label="客PO"]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('ignores an obsolete preview and clears protected results when factory changes', async () => {
    let finish: ((v: typeof preview) => void) | undefined
    api.preview.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const wrapper = await open()
    await button(wrapper, '解析并核对').trigger('click')
    await wrapper.setProps({ factoryId: 'huakang-a' })
    expect((api.preview.mock.calls[0]![1] as AbortSignal).aborted).toBe(true)
    finish?.(preview); await flushPromises()
    expect(wrapper.text()).not.toContain('B货价.xlsx')
    expect(wrapper.find('input[aria-label="客PO"]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('keeps old reference metadata on failed upload, clears it on revoked access', async () => {
    const wrapper = await open()
    const input = wrapper.get('input[aria-label="排期参照"]')
    Object.defineProperty(input.element, 'files', { value: [new File(['bad'], 'invalid.xlsx')], configurable: true })
    await input.trigger('change')
    api.upload.mockRejectedValueOnce({ response: { status: 400, data: { detail: '排期格式错误' } } })
    await button(wrapper, '验证并更新').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('B排期.xlsx')
    api.upload.mockRejectedValueOnce({ response: { status: 403, data: { detail: '权限已撤销' } } })
    await button(wrapper, '验证并更新').trigger('click'); await flushPromises()
    expect(wrapper.text()).not.toContain('B排期.xlsx')
    wrapper.unmount()
  })
  it('hides write controls and disables export for a read-only account', async () => {
    api.capabilities.mockResolvedValue({ read: true, write: false, export: false, available: true })
    const wrapper = await open()
    expect(wrapper.find('input[aria-label="排期参照"]').exists()).toBe(false)
    await button(wrapper, '解析并核对').trigger('click'); await flushPromises()
    await wrapper.findAll('textarea').at(-1)!.setValue('逐项核对正确')
    await wrapper.findAll('input[type=checkbox]').at(-1)!.setValue(true)
    expect(button(wrapper, '确认并生成问单 Excel').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
})
