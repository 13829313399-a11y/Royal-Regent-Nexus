import { mount, flushPromises, shallowMount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import { internalQuoteApi, type ApiInternalQuoteAlternativeFamily } from '@/api/internalQuote'
import InternalQuoteAlternatives from '../InternalQuoteAlternatives.vue'
import InternalQuoteCollaboration from '../InternalQuoteCollaboration.vue'

vi.mock('vue-router', () => ({ useRoute: () => ({ params: { quoteId: 'q1' }, query: {} }), useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }))
function family(): ApiInternalQuoteAlternativeFamily {
  return { family_id: 'family', revision: 3, selected_quote_id: '', items: ['q1', 'q2'].map((id, index) => ({
    quote_id: id, scenario_id: id, scenario_name: index ? '开窗盒' : '普通彩盒', version_number: 1, version_label: 'V1', source_quote_id: '', change_note: '', status: index ? 'exported' : 'drafting', issued_at: '', reported_at: '', created_at: '', quote_no: 'IQ', product_name: '巴士', customer: 'Dickie', quantity: 5000, archived: false,
  })) }
}
function setup() {
  const pinia = createPinia(); setActivePinia(pinia)
  const auth = useAuthStore(); vi.spyOn(auth, 'can').mockReturnValue(true)
  const app = useAppStore(); vi.spyOn(app, 'activeFactory', 'get').mockReturnValue({ id: 'huaxing' } as typeof app.activeFactory)
  const store = useInternalQuoteDeskStore()
  const quote = { ...store.placeholderQuote, id: 'q1', quoteNo: 'IQ', factoryId: 'huaxing', moduleVersion: 'v4', headerRevision: 8 }
  store.quotes = [quote]
  vi.spyOn(store, 'loadQuote').mockResolvedValue(quote); vi.spyOn(store, 'loadBatchProducts').mockResolvedValue(undefined)
  vi.spyOn(internalQuoteApi, 'listAlternatives').mockResolvedValue(family())
  vi.spyOn(internalQuoteApi, 'get').mockResolvedValue({ sections: [] } as never)
  return { pinia, store, quote, auth }
}
beforeEach(() => { vi.stubGlobal('IntersectionObserver', class { observe() {} disconnect() {} }) })
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })
describe('independent quotation alternatives', () => {
  it('copies only saved source into a named independent scenario with both revisions', async () => {
    const { quote, pinia } = setup()
    const create = vi.spyOn(internalQuoteApi, 'createAlternative').mockResolvedValue({ id: 'q3' } as never)
    const wrapper = mount(InternalQuoteAlternatives, { props: { quote }, global: { plugins: [pinia] } })
    await flushPromises()
    await wrapper.findAll('button').find(b => b.text() === '复制为新方案')!.trigger('click')
    await wrapper.get('input[placeholder="例如：开窗盒包装"]').setValue('吸塑包装')
    await wrapper.get('input[placeholder="例如：客户要求调整包装尺寸"]').setValue('客户比较包装')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(create).toHaveBeenCalledWith('q1', { revision: 8, family_revision: 3, kind: 'scenario', name: '吸塑包装', change_note: '客户比较包装' })
    expect(wrapper.emitted('open')).toEqual([['q3']]); wrapper.unmount()
  })
  it('blocks copying and navigating while source has unsaved changes', async () => {
    const { quote, pinia } = setup()
    const wrapper = mount(InternalQuoteAlternatives, { props: { quote, hasUnsavedChanges: () => true }, global: { plugins: [pinia] } })
    await flushPromises()
    await wrapper.findAll('button').find(b => b.text() === '复制新版本')!.trigger('click')
    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.get('[role="alert"]').text()).toContain('未保存')
    await wrapper.findAll('button').find(b => b.text() === '打开' && !b.attributes('disabled'))!.trigger('click')
    expect(wrapper.emitted('open')).toBeUndefined(); wrapper.unmount()
  })
  it('requires selection reason and records exact issued version, not scenario', async () => {
    const { quote, pinia } = setup()
    const select = vi.spyOn(internalQuoteApi, 'selectAlternative').mockResolvedValue({ ...family(), selected_quote_id: 'q2' })
    const wrapper = mount(InternalQuoteAlternatives, { props: { quote }, global: { plugins: [pinia] } })
    await flushPromises()
    const choose = wrapper.findAll('button').find(b => b.text() === '客户采用此版')!
    await choose.trigger('click'); await flushPromises(); expect(select).not.toHaveBeenCalled()
    await wrapper.get('input[placeholder="例如：客户确认采用开窗盒 V2"]').setValue('客户确认开窗盒 V1')
    await choose.trigger('click'); await flushPromises()
    expect(select).toHaveBeenCalledWith('q1', { family_revision: 3, selected_quote_id: 'q2', reason: '客户确认开窗盒 V1' }); wrapper.unmount()
  })
  it('compares two chosen versions and exposes changed packaging fields', async () => {
    const { quote, pinia } = setup()
    const compare = vi.spyOn(internalQuoteApi, 'compareVersion').mockResolvedValue({ header_changes: [{ path: 'quantity', before: 3000, after: 5000 }], total_before_hkd: '1', total_after_hkd: '2', total_delta_hkd: '1', sections: [] } as never)
    const wrapper = mount(InternalQuoteAlternatives, { props: { quote }, global: { plugins: [pinia] } }); await flushPromises()
    await wrapper.findAll('button').find(b => b.text() === '比较两版')!.trigger('click'); await flushPromises()
    expect(compare).toHaveBeenCalledWith('q1', 'q2'); expect(wrapper.text()).toContain('报价数量'); wrapper.unmount()
  })
  it('shows direct issue without review controls and freezes via versioned API', async () => {
    const { pinia, store } = setup()
    const issue = vi.spyOn(store, 'directIssue').mockResolvedValue({ id: 'export1', file_name: '内部.xlsx' })
    const download = vi.spyOn(store, 'downloadExport').mockResolvedValue(undefined)
    const wrapper = shallowMount(InternalQuoteCollaboration, { global: { plugins: [pinia], stubs: { RouterLink: true, InternalQuoteSectionEditor: { template: '<div />', methods: { hasUnsavedChanges: () => false } } } } }); await flushPromises()
    expect(wrapper.findAll('button').some(b => b.text() === '提交审核')).toBe(false)
    await wrapper.findAll('button').find(b => b.text() === '直接输出并保留此版')!.trigger('click'); await flushPromises()
    expect(issue).toHaveBeenCalledWith('q1', 8); expect(download).toHaveBeenCalledWith('q1', 'export1', '内部.xlsx'); wrapper.unmount()
  })
  it('keeps the synchronization success result mounted while refreshing the family', async () => {
    const { pinia, quote } = setup()
    const wrapper = mount(InternalQuoteAlternatives, { props: { quote }, global: { plugins: [pinia], stubs: {
      InternalQuoteAlternativeSync: { data: () => ({ saved: false }), template: '<div><button @click="saved = true; $emit(\'changed\')">模拟同步保存</button><span v-if="saved">同步结果已保存</span></div>' },
    } } })
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '模拟同步保存')!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('同步结果已保存')
    wrapper.unmount()
  })
  it('hides direct issue and reference mutation after version is exported', async () => {
    const { pinia, store } = setup(); store.quotes[0]!.status = 'exported'
    const wrapper = shallowMount(InternalQuoteCollaboration, { global: { plugins: [pinia], stubs: { RouterLink: true, InternalQuoteSectionEditor: { template: '<div />', methods: { hasUnsavedChanges: () => false } } } } }); await flushPromises()
    expect(wrapper.findAll('button').some(b => b.text() === '直接输出并保留此版' || b.text() === '同步最新参考表')).toBe(false); wrapper.unmount()
  })
  it('keeps unsaved edits in place and refuses direct output until saved', async () => {
    const { pinia, store } = setup()
    const issue = vi.spyOn(store, 'directIssue')
    const wrapper = shallowMount(InternalQuoteCollaboration, { global: { plugins: [pinia], stubs: { RouterLink: true, InternalQuoteSectionEditor: { template: '<div />', methods: { hasUnsavedChanges: () => true } } } } }); await flushPromises()
    await wrapper.findAll('button').find(b => b.text() === '直接输出并保留此版')!.trigger('click'); await flushPromises()
    expect(issue).not.toHaveBeenCalled(); expect(wrapper.text()).toContain('先保存当前款'); wrapper.unmount()
  })
})
