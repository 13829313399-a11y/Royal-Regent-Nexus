import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { internalQuoteApi } from '@/api/internalQuote'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import InternalQuoteFreezeDialog from '../InternalQuoteFreezeDialog.vue'

function setup(frozen = false) {
  const pinia = createPinia(); setActivePinia(pinia)
  const store = useInternalQuoteDeskStore()
  const read = vi.spyOn(internalQuoteApi, 'getFreezeOptions').mockResolvedValue({ products: [
    { product_root_id: 'p1', product_name: '第一款', family_revision: 2, options: [
      { quote_id: 'p1', scenario_name: '原方案', version_label: 'A-V1', header_revision: 4, final_release_status: frozen ? 'issued' : 'output' },
      { quote_id: 'p1-v2', scenario_name: '新方案', version_label: 'B-V1', header_revision: 9, final_release_status: 'output' },
    ] },
    { product_root_id: 'p2', product_name: '第二款', family_revision: 3, options: [
      { quote_id: 'p2', scenario_name: '原方案', version_label: 'A-V1', header_revision: 5, final_release_status: frozen ? 'issued' : '' },
    ] },
  ] } as never)
  const save = vi.spyOn(internalQuoteApi, 'setDocumentFrozen').mockResolvedValue([])
  const wrapper = mount(InternalQuoteFreezeDialog, { props: { quote: { ...store.placeholderQuote, id: 'p1', factoryId: 'huaxing' } },
    global: { plugins: [pinia], stubs: { Teleport: true } } })
  return { wrapper, read, save }
}
afterEach(() => vi.restoreAllMocks())
describe('document freeze', () => {
  it('requires a reason and sends all products atomically with the reviewed version revisions', async () => {
    const { wrapper, save } = setup()
    await flushPromises()
    expect(wrapper.findAll('input[type=checkbox]')).toHaveLength(0)
    expect(wrapper.get('button[type=submit]').attributes('disabled')).toBeDefined()
    await wrapper.get('select[aria-label="第一款 当前版本"]').setValue('p1-v2')
    await wrapper.get('textarea').setValue('确认整单')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(save).toHaveBeenCalledWith('p1', { frozen: true, reason: '确认整单', products: [
      { quote_id: 'p1-v2', revision: 9, family_revision: 2 }, { quote_id: 'p2', revision: 5, family_revision: 3 },
    ] })
    expect(wrapper.emitted('completed')).toHaveLength(1)
    wrapper.unmount()
  })
  it('allows old frozen versions to be unlocked together and retains scope on conflict', async () => {
    const { wrapper, save } = setup(true)
    await flushPromises()
    expect(wrapper.get('button[type=submit]').text()).toBe('解除全部 2 款冻结')
    save.mockRejectedValueOnce(new Error('报价已更新，请重新读取'))
    await wrapper.get('textarea').setValue('客户微调')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(save).toHaveBeenCalledWith('p1', expect.objectContaining({ frozen: false, products: [
      { quote_id: 'p1', revision: 4, family_revision: 2 }, { quote_id: 'p2', revision: 5, family_revision: 3 },
    ] }))
    expect(wrapper.get('[role=alert]').text()).toContain('重新读取')
    expect(wrapper.emitted('completed')).toBeUndefined()
    expect(wrapper.get('textarea').element.value).toBe('客户微调')
    wrapper.unmount()
  })
  it('prevents duplicate submissions and closing during an outstanding operation', async () => {
    const { wrapper, save } = setup()
    await flushPromises()
    let finish!: () => void
    save.mockImplementationOnce(() => new Promise(resolve => { finish = () => resolve([]) }))
    await wrapper.get('textarea').setValue('核对完成')
    await wrapper.get('form').trigger('submit')
    await wrapper.get('form').trigger('submit')
    await wrapper.get('button[aria-label="关闭冻结管理"]').trigger('click')
    expect(save).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('close')).toBeUndefined()
    finish(); await flushPromises()
    expect(wrapper.emitted('completed')).toHaveLength(1)
    wrapper.unmount()
  })
})
