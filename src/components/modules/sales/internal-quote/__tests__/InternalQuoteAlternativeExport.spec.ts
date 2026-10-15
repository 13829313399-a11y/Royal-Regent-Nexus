import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { internalQuoteApi } from '@/api/internalQuote'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import InternalQuoteAlternativeExport from '../InternalQuoteAlternativeExport.vue'

function setup(dirty = () => false) {
  const pinia = createPinia(); setActivePinia(pinia)
  const store = useInternalQuoteDeskStore()
  const quote = { ...store.placeholderQuote, id: 'original', quoteNo: 'IQ-TEST' }
  vi.spyOn(internalQuoteApi, 'listAlternatives').mockResolvedValue({ items: [
    { quote_id: 'original', scenario_name: '普通彩盒', version_label: 'A-V1', status: 'exported', archived: false },
    { quote_id: 'window', scenario_name: '开窗彩盒', version_label: 'B-V1', status: 'drafting', archived: false },
    { quote_id: 'archived', scenario_name: '旧包装', version_label: 'C-V1', archived: true },
  ] } as never)
  const read = vi.spyOn(internalQuoteApi, 'get').mockImplementation(async id => ({ id, header_revision: id === 'original' ? 8 : 3 }) as never)
  const output = vi.spyOn(store, 'exportAlternatives').mockResolvedValue(undefined)
  const wrapper = mount(InternalQuoteAlternativeExport, { props: { quote, hasUnsavedChanges: dirty }, global: {
    plugins: [pinia], stubs: { DialogPortal: { template: '<div><slot /></div>' } },
  } })
  return { wrapper, output, read }
}
afterEach(() => vi.restoreAllMocks())
describe('multi-alternative export', () => {
  it('requires an explicit selection and exports only selected unarchived versions with current revisions', async () => {
    const { wrapper, output } = setup()
    await flushPromises()
    expect(wrapper.findAll('input[type=checkbox]')).toHaveLength(2)
    const submit = wrapper.get('button.primary')
    expect(submit.attributes('disabled')).toBeDefined()
    for (const checkbox of wrapper.findAll('input[type=checkbox]')) await checkbox.setValue(true)
    expect(wrapper.text()).toContain('已选 2 个版本')
    expect(wrapper.text()).toContain('已输出版本沿用原文件')
    await submit.trigger('click'); await flushPromises()
    expect(output).toHaveBeenCalledWith('original', [{ quote_id: 'original', revision: 8 }, { quote_id: 'window', revision: 3 }], 'IQ-TEST-多方案报价.xlsx')
    expect(wrapper.emitted('completed')).toHaveLength(1)
    wrapper.unmount()
  })
  it('blocks unsaved edits and leaves failed selections available for retry', async () => {
    let dirty = true
    const { wrapper, output } = setup(() => dirty)
    await flushPromises()
    for (const checkbox of wrapper.findAll('input[type=checkbox]')) await checkbox.setValue(true)
    await wrapper.get('button.primary').trigger('click'); await flushPromises()
    expect(output).not.toHaveBeenCalled()
    expect(wrapper.get('[role=alert]').text()).toContain('请先保存')
    dirty = false
    output.mockRejectedValueOnce(new Error('开窗彩盒：啤机成本尚未完整'))
    await wrapper.get('button.primary').trigger('click'); await flushPromises()
    expect(wrapper.get('[role=alert]').text()).toContain('啤机成本尚未完整')
    expect(wrapper.emitted('completed')).toBeUndefined()
    expect(wrapper.text()).toContain('已选 2 个版本')
    wrapper.unmount()
  })
  it('does not issue when the user edits while selected revisions are loading', async () => {
    let dirty = false
    const { wrapper, output, read } = setup(() => dirty)
    await flushPromises()
    for (const checkbox of wrapper.findAll('input[type=checkbox]')) await checkbox.setValue(true)
    read.mockImplementation(async () => { dirty = true; return { header_revision: 1 } as never })
    await wrapper.get('button.primary').trigger('click'); await flushPromises()
    expect(output).not.toHaveBeenCalled()
    expect(wrapper.get('[role=alert]').text()).toContain('请先保存')
    wrapper.unmount()
  })
})
