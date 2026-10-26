import { mount, flushPromises, shallowMount } from '@vue/test-utils'
import { reactive } from 'vue'
import type { RouteLocationNormalized } from 'vue-router'
import { clearQuoteNavigationGuards, guardQuoteNavigation } from '@/features/internal-quote/navigationGuard'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import { internalQuoteApi, type ApiInternalQuoteAlternativeFamily } from '@/api/internalQuote'
import InternalQuoteAlternatives from '../InternalQuoteAlternatives.vue'
import InternalQuoteCollaboration from '../InternalQuoteCollaboration.vue'
import InternalQuoteLeaveDialog from '../InternalQuoteLeaveDialog.vue'
import InternalQuoteExportSummary from '../InternalQuoteExportSummary.vue'
import InternalQuoteSummary from '../InternalQuoteSummary.vue'

const routeState = reactive({ params: { quoteId: 'q1' }, query: {} })
vi.mock('vue-router', () => ({ onBeforeRouteLeave: vi.fn(), onBeforeRouteUpdate: vi.fn(), useRoute: () => routeState, useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }))
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
beforeEach(() => { clearQuoteNavigationGuards(); routeState.params.quoteId = 'q1'; vi.stubGlobal('IntersectionObserver', class { observe() {} disconnect() {} }) })
afterEach(() => { clearQuoteNavigationGuards(); vi.restoreAllMocks(); vi.unstubAllGlobals() })
describe('independent quotation alternatives', () => {
  it.each([
    ['collaboration', InternalQuoteCollaboration], ['summary', InternalQuoteSummary], ['export', InternalQuoteExportSummary],
  ] as const)('keeps the active factory in the %s unavailable-record return link', async (_name, component) => {
    const { pinia, store } = setup()
    vi.spyOn(useAppStore(), 'activeFactory', 'get').mockReturnValue({ id: 'huakang-a' } as ReturnType<typeof useAppStore>['activeFactory'])
    store.quotes = []
    vi.mocked(store.loadQuote).mockResolvedValue(undefined)
    vi.spyOn(store, 'loadVersionCandidates').mockResolvedValue([])
    const wrapper = shallowMount(component, { global: { plugins: [pinia], stubs: {
      RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
    } } })
    await flushPromises()
    expect(wrapper.text()).toContain('原报价暂不可用')
    expect(wrapper.get('a').attributes('href')).toBe('/modules/sales-business/internal-quote-desk?factory=huakang-a')
    wrapper.unmount()
  })

  it('hides unverified financial contents on a failed refresh without destroying local department drafts', async () => {
    const { pinia, store } = setup()
    const wrapper = shallowMount(InternalQuoteCollaboration, { global: { plugins: [pinia], stubs: {
      RouterLink: true,
      InternalQuoteSectionEditor: { template: '<input data-local-draft v-model="draft">', data: () => ({ draft: '原输入' }), methods: { hasUnsavedChanges: () => true } },
    } } })
    await flushPromises()
    const input = wrapper.findAll('input[data-local-draft]')[0]!
    await input.setValue('仍须保留的本地草稿')
    store.quoteDetailFailedId = 'q1'; store.errorMessage = '权威汇总暂不可读'
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('权威汇总暂不可读')
    expect((wrapper.get('.quote-verified-content').element as HTMLElement).style.display).toBe('none')
    expect((input.element as HTMLInputElement).value).toBe('仍须保留的本地草稿')
    store.quoteDetailFailedId = ''; store.quoteDetailVerifiedId = 'q1'; store.errorMessage = ''
    await flushPromises()
    expect(wrapper.findAll('input[data-local-draft]')[0]!.element).toBe(input.element)
    expect((wrapper.get('.quote-verified-content').element as HTMLElement).style.display).not.toBe('none')
    expect((input.element as HTMLInputElement).value).toBe('仍须保留的本地草稿')
    wrapper.unmount()
  })

  it('confirms discard without a premature dialog-close cancellation', async () => {
    const wrapper = mount(InternalQuoteLeaveDialog, { props: { open: true }, global: { stubs: { AlertDialogPortal: { template: '<div><slot /></div>' } } } })
    await flushPromises()
    await wrapper.get('button.discard').trigger('click')
    expect(wrapper.emitted('discard')).toHaveLength(1)
    expect(wrapper.emitted('cancel')).toBeUndefined()
    wrapper.unmount()
  })

  it('lets clean quotes leave and offers cancel or discard for actual sidebar edits without saving or clearing them early', async () => {
    const { pinia, store } = setup()
    let dirty = false
    const save = vi.spyOn(store, 'saveWholeProductSections')
    const wrapper = shallowMount(InternalQuoteCollaboration, { global: { plugins: [pinia], stubs: {
      RouterLink: true,
      InternalQuoteActivityPanel: { template: '<div />', methods: { hasUnsavedChanges: () => dirty } },
    } } })
    await flushPromises()
    const from = { fullPath: '/quotes/q1?factory=huaxing', params: { quoteId: 'q1' } } as unknown as RouteLocationNormalized
    const leave = (path = '/quotes/q2?factory=huaxing') => guardQuoteNavigation({ fullPath: path } as RouteLocationNormalized, from)
    expect(await leave()).toBe(true)
    dirty = true
    const pending = leave()
    const repeated = leave()
    await flushPromises()
    expect(wrapper.getComponent(InternalQuoteLeaveDialog).props('open')).toBe(true)
    wrapper.getComponent(InternalQuoteLeaveDialog).vm.$emit('cancel')
    expect(await pending).toBe(false)
    expect(await repeated).toBe(false)
    expect(dirty).toBe(true)
    expect(await leave(from.fullPath)).toBe(true)
    const switching = leave('/quotes/q1?factory=huakang-a')
    await flushPromises()
    wrapper.getComponent(InternalQuoteLeaveDialog).vm.$emit('discard')
    expect(await switching).toBe(true)
    expect(dirty).toBe(true) // A later department guard may still cancel navigation.
    expect(save).not.toHaveBeenCalled()
    const abandoned = leave()
    wrapper.unmount()
    expect(await abandoned).toBe(false)
  })

  it.each(['document', 'version'])('blocks new output from the summary/export pages for a %s archive', async scope => {
    const { pinia, quote, store } = setup()
    store.quotes = [{ ...quote, status: 'exported', versionArchived: scope === 'version',
      documentArchive: scope === 'document' ? { quote_id: 'q1', revision: 8, reason: '暂停' } : null }]
    vi.spyOn(store, 'loadVersionCandidates').mockResolvedValue([])
    const output = shallowMount(InternalQuoteExportSummary, { global: { plugins: [pinia], stubs: { RouterLink: true } } })
    await flushPromises()
    expect(output.text()).toContain('报价已归档')
    expect(output.findAll('button').find(b => b.text() === '生成内部报价 XLSX')!.attributes('disabled')).toBeDefined()
    output.unmount()
    const summary = shallowMount(InternalQuoteSummary, { global: { plugins: [pinia], stubs: { RouterLink: true } } })
    await flushPromises()
    expect(summary.text()).toContain('报价已归档，暂停业务操作')
    expect(summary.findAll('button').some(b => b.text() === '返回协作页查看归档状态')).toBe(true)
    summary.unmount()
  })
  it('ignores an old family response arriving after whole-document restoration', async () => {
    const { pinia, quote } = setup()
    const context = { quote_id: 'q1', revision: 8, reason: '暂停' }
    let finishOld!: (value: ApiInternalQuoteAlternativeFamily) => void
    vi.mocked(internalQuoteApi.listAlternatives).mockImplementationOnce(() => new Promise(resolve => { finishOld = resolve }))
    vi.spyOn(internalQuoteApi, 'restoreQuote').mockResolvedValue({} as never)
    const wrapper = mount(InternalQuoteAlternatives, { props: { quote: { ...quote, status: 'archived', documentArchive: context } }, global: { plugins: [pinia] } })
    await flushPromises()
    await wrapper.findAll('button').find(b => b.text() === '恢复整单报价')!.trigger('click')
    await wrapper.get('input[aria-label="恢复整单原因"]').setValue('继续')
    await wrapper.get('form[aria-label="恢复整单报价"]').trigger('submit'); await flushPromises()
    await wrapper.setProps({ quote: { ...quote, documentArchive: null } }); await flushPromises()
    finishOld({ ...family(), document_archive: context }); await flushPromises()
    expect(wrapper.text()).not.toContain('整单报价已归档')
    expect(wrapper.emitted('archiveState')?.at(-1)).toEqual([false])
    expect(wrapper.findAll('button').some(b => b.text() === '归档此版')).toBe(true)
    wrapper.unmount()
  })
  it('shows whole-document archive immediately and never offers per-version archive', async () => {
    const { pinia, quote } = setup()
    const context = { quote_id: 'q1', revision: 8, reason: '项目暂停' }
    quote.status = 'archived'
    const archived = { ...family(), document_archive: context }
    vi.mocked(internalQuoteApi.listAlternatives).mockResolvedValue(archived)
    const wrapper = mount(InternalQuoteAlternatives, { props: { quote, hasUnsavedChanges: () => true }, global: { plugins: [pinia] } })
    await flushPromises()
    expect(wrapper.text()).toContain('整单报价已归档')
    expect(wrapper.findAll('button').some(b => ['归档此版', '恢复显示', '复制新版本', '客户采用此版'].includes(b.text()))).toBe(false)
    const restore = vi.spyOn(internalQuoteApi, 'restoreQuote').mockResolvedValue({} as never)
    await wrapper.findAll('button').find(b => b.text() === '恢复整单报价')!.trigger('click')
    const form = wrapper.get('form[aria-label="恢复整单报价"]')
    await form.trigger('submit'); await flushPromises()
    expect(restore).not.toHaveBeenCalled()
    await form.get('input').setValue('客户继续项目')
    vi.mocked(internalQuoteApi.listAlternatives).mockResolvedValue(family())
    await form.trigger('submit'); await flushPromises()
    expect(restore).toHaveBeenCalledWith('q1', 8, '客户继续项目')
    expect(wrapper.emitted('changed')).toHaveLength(1)
    wrapper.unmount()
  })
  it('requires document archive permission even when the user may manage versions', async () => {
    const { pinia, quote, auth } = setup()
    vi.mocked(auth.can).mockImplementation(permission => permission !== 'internal_quote:archive')
    quote.status = 'archived'
    const wrapper = mount(InternalQuoteAlternatives, { props: { quote }, global: { plugins: [pinia] } })
    await flushPromises()
    expect(wrapper.text()).toContain('业务主管恢复整单')
    expect(wrapper.findAll('button').some(b => ['恢复整单报价', '归档此版', '恢复显示'].includes(b.text()))).toBe(false)
    wrapper.unmount()
  })
  it('locks an archived quote before the alternatives request completes', async () => {
    const { pinia, quote, store } = setup()
    store.quotes = [{ ...quote, status: 'archived' }]
    const wrapper = shallowMount(InternalQuoteCollaboration, { global: { plugins: [pinia], stubs: { RouterLink: true } } })
    await flushPromises()
    expect(wrapper.get('#quote-page-actions').text()).toContain('恢复整单报价')
    expect(wrapper.findAll('button').find(b => b.text() === '保存')!.attributes('disabled')).toBeDefined()
    expect(wrapper.findAll('button').some(b => b.text() === '修改报价资料')).toBe(false)
    wrapper.unmount()
  })
  it('does not discard a new draft after leaving and returning while an old reload is pending', async () => {
    const { pinia, store, quote } = setup()
    store.quotes.push({ ...quote, id: 'q2' })
    let mounted = 0
    const wrapper = shallowMount(InternalQuoteCollaboration, { global: { plugins: [pinia], stubs: { RouterLink: true, InternalQuoteSectionEditor: { template: '<div />', mounted() { mounted++ }, methods: { hasUnsavedChanges: () => true } } } } })
    await flushPromises()
    let resolveBatch!: () => void
    vi.mocked(store.loadBatchProducts).mockImplementationOnce(() => new Promise<void>(resolve => { resolveBatch = resolve }))
    store.conflictMessage = '版本冲突'; await flushPromises()
    await wrapper.findAll('button').find(b => b.text() === '放弃本地表单并重新读取')!.trigger('click'); await flushPromises()
    routeState.params.quoteId = 'q2'; await flushPromises()
    routeState.params.quoteId = 'q1'; await flushPromises()
    const afterReturn = mounted
    resolveBatch(); await flushPromises()
    expect(mounted).toBe(afterReturn)
    wrapper.unmount()
  })
  it('disables archived editing and output, then unlocks on restoration without rebuilding editors', async () => {
    const { pinia } = setup()
    let mounted = 0
    const wrapper = shallowMount(InternalQuoteCollaboration, { global: { plugins: [pinia], stubs: { RouterLink: true, InternalQuoteSectionEditor: { template: '<div />', mounted() { mounted++ }, methods: { hasUnsavedChanges: () => true } } } } })
    await flushPromises()
    const original = mounted
    wrapper.findComponent(InternalQuoteAlternatives).vm.$emit('archiveState', true); await flushPromises()
    expect(wrapper.findAll('button').find(b => b.text() === '直接输出并保留此版')!.attributes('disabled')).toBeDefined()
    expect(wrapper.findAll('button').some(b => b.text() === '修改报价资料' || b.text() === '本报价专用料价')).toBe(false)
    expect(wrapper.get('#quote-page-actions').text()).toContain('填写说明并确认恢复')
    wrapper.findComponent(InternalQuoteAlternatives).vm.$emit('archiveState', false); await flushPromises()
    expect(wrapper.findAll('button').find(b => b.text() === '直接输出并保留此版')!.attributes('disabled')).toBeUndefined()
    expect(mounted).toBe(original)
    wrapper.unmount()
  })
  it('restores the visible current archived version with its own reason while preserving local drafts', async () => {
    const { pinia, quote } = setup()
    const archived = family(); archived.items[0]!.archived = true
    vi.spyOn(internalQuoteApi, 'listAlternatives').mockResolvedValue(archived)
    const restore = vi.spyOn(internalQuoteApi, 'archiveAlternative').mockResolvedValue(family())
    const wrapper = mount(InternalQuoteAlternatives, { props: { quote, hasUnsavedChanges: () => true }, global: { plugins: [pinia] } })
    await flushPromises()
    expect(wrapper.emitted('archiveState')).toEqual([[true]])
    await wrapper.findAll('button').find(b => b.text() === '恢复显示')!.trigger('click')
    const form = wrapper.get('form[aria-label="归档或恢复版本"]')
    await form.trigger('submit'); await flushPromises()
    expect(restore).not.toHaveBeenCalled()
    expect(form.get('[role="alert"]').text()).toContain('填写')
    await form.get('input').setValue('继续报价')
    await form.trigger('submit'); await flushPromises()
    expect(restore).toHaveBeenCalledWith('q1', { family_revision: 3, archived: false, reason: '继续报价' })
    expect(wrapper.emitted('archiveState')).toEqual([[true], [false]])
    expect(wrapper.emitted('changed')).toBeUndefined()
    expect(wrapper.text()).toContain('本地未保存内容仍保留')
    wrapper.unmount()
  })
  it('does not archive an unsaved current draft or send a request on cancellation', async () => {
    const { pinia, quote } = setup()
    const archive = vi.spyOn(internalQuoteApi, 'archiveAlternative')
    const wrapper = mount(InternalQuoteAlternatives, { props: { quote, hasUnsavedChanges: () => true }, global: { plugins: [pinia] } })
    await flushPromises()
    await wrapper.findAll('button').find(b => b.text() === '归档此版')!.trigger('click')
    const form = wrapper.get('form[aria-label="归档或恢复版本"]')
    await form.get('input').setValue('暂不采用')
    await form.trigger('submit'); await flushPromises()
    expect(archive).not.toHaveBeenCalled()
    expect(form.get('[role="alert"]').text()).toContain('先保存')
    await form.findAll('button').find(b => b.text() === '取消')!.trigger('click')
    expect(wrapper.find('form').exists()).toBe(false)
    wrapper.unmount()
  })
  it('shows direct output failures beside the clicked footer controls', async () => {
    const { pinia, store } = setup()
    vi.spyOn(store, 'directIssue').mockRejectedValue(new Error('啤机部须完成填写、保存及有效计算'))
    const wrapper = shallowMount(InternalQuoteCollaboration, { global: { plugins: [pinia], stubs: { RouterLink: true, InternalQuoteSectionEditor: { template: '<div />', methods: { hasUnsavedChanges: () => false } } } } })
    await flushPromises()
    await wrapper.findAll('button').find(b => b.text() === '直接输出并保留此版')!.trigger('click'); await flushPromises()
    expect(wrapper.get('#quote-page-actions [role="alert"]').text()).toContain('啤机部')
    expect(wrapper.text()).not.toContain('放弃本地表单并重新读取')
    wrapper.unmount()
  })
  it('discards local editors only after an explicit successful reload', async () => {
    const { pinia, store, quote } = setup()
    let mounted = 0
    const wrapper = shallowMount(InternalQuoteCollaboration, { global: { plugins: [pinia], stubs: { RouterLink: true, InternalQuoteSectionEditor: { template: '<div />', mounted() { mounted++ }, methods: { hasUnsavedChanges: () => true } } } } })
    await flushPromises()
    const original = mounted
    store.conflictMessage = '版本冲突'
    await flushPromises()
    vi.mocked(store.loadQuote).mockResolvedValueOnce(undefined)
    await wrapper.findAll('button').find(b => b.text() === '放弃本地表单并重新读取')!.trigger('click'); await flushPromises()
    expect(mounted).toBe(original)
    expect(store.conflictMessage).toBe('版本冲突')
    vi.mocked(store.loadQuote).mockResolvedValueOnce(quote)
    await wrapper.findAll('button').find(b => b.text() === '放弃本地表单并重新读取')!.trigger('click'); await flushPromises()
    expect(mounted).toBeGreaterThan(original)
    expect(store.conflictMessage).toBe('')
    wrapper.unmount()
  })
  it('deletes an unused active draft only after confirmation and returns to its product', async () => {
    const { pinia, quote } = setup()
    const rows = family()
    rows.family_id = 'q1'
    rows.items[1]!.can_delete = true
    rows.items[1]!.status = 'drafting'
    vi.spyOn(internalQuoteApi, 'listAlternatives').mockResolvedValue(rows)
    vi.spyOn(internalQuoteApi, 'get').mockResolvedValue({ header_revision: 9 } as never)
    const remove = vi.spyOn(internalQuoteApi, 'deleteQuote').mockResolvedValue(undefined)
    const wrapper = mount(InternalQuoteAlternatives, { props: { quote: { ...quote, id: 'q2' } }, global: { plugins: [pinia] } })
    await flushPromises()
    await wrapper.findAll('button').find(row => row.text() === '删除未使用草稿')!.trigger('click')
    expect(remove).not.toHaveBeenCalled()
    await wrapper.findAll('button').find(row => row.text() === '确认删除草稿')!.trigger('click')
    await flushPromises()
    expect(remove).toHaveBeenCalledWith('q2', 9)
    expect(wrapper.emitted('open')).toEqual([['q1']])
    wrapper.unmount()
  })
  it('copies only saved source into a named independent scenario with both revisions', async () => {
    const { quote, pinia } = setup()
    const create = vi.spyOn(internalQuoteApi, 'createAlternative').mockResolvedValue({ id: 'q3' } as never)
    const wrapper = mount(InternalQuoteAlternatives, { props: { quote }, global: { plugins: [pinia] } })
    await flushPromises()
    await wrapper.findAll('button').find(b => b.text() === '复制为新方案')!.trigger('click')
    await wrapper.get('input[placeholder="例如：开窗盒包装"]').setValue('吸塑包装')
    await wrapper.get('input[placeholder="例如：客户要求调整包装尺寸"]').setValue('客户比较包装')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(create).toHaveBeenCalledWith('q1', { revision: 8, family_revision: 3, kind: 'scenario', name: '吸塑包装', change_note: '客户比较包装', copy_departments: quote.sections.filter(section => section.isRequired).map(section => section.code) })
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


describe('copy selected departments', () => {
  it('defaults to all, submits one or two departments and resets selection on reopening', async () => {
    const { pinia, quote } = setup()
    quote.sections = quote.sections.map(section => ({ ...section, isRequired: ['engineering', 'assembly', 'sales'].includes(section.code) }))
    const create = vi.spyOn(internalQuoteApi, 'createAlternative').mockResolvedValue({ id: 'copied' } as never)
    const wrapper = shallowMount(InternalQuoteAlternatives, { props: { quote }, global: { plugins: [pinia] } })
    await flushPromises()
    const button = (text: string) => wrapper.findAll('button').find(b => b.text() === text)!
    await button('复制为新方案').trigger('click')
    expect(wrapper.findAll('.department-options input:checked')).toHaveLength(3)
    await button('清空选择').trigger('click')
    expect(button('确认复制').attributes('disabled')).toBeDefined()
    await wrapper.get('input[value="engineering"]').setValue(true)
    await wrapper.get('input[placeholder="例如：开窗盒包装"]').setValue('工程方案')
    await wrapper.get('input[placeholder="例如：客户要求调整包装尺寸"]').setValue('仅复用工程')
    await wrapper.get('form.copy-form').trigger('submit')
    await flushPromises()
    expect(create).toHaveBeenLastCalledWith('q1', expect.objectContaining({ copy_departments: ['engineering'] }))
    expect(wrapper.emitted('open')).toEqual([['copied']])
    await button('复制新版本').trigger('click')
    expect(wrapper.findAll('.department-options input:checked')).toHaveLength(3)
    await wrapper.get('input[value="sales"]').setValue(false)
    await wrapper.get('form.copy-form').trigger('submit')
    await flushPromises()
    expect(create).toHaveBeenLastCalledWith('q1', expect.objectContaining({ kind: 'version', copy_departments: ['engineering', 'assembly'] }))
    wrapper.unmount()
  })
  it('closes the selection on quote changes and ignores an obsolete copy response', async () => {
    const { pinia, quote } = setup()
    let resolve!: (value: never) => void
    vi.spyOn(internalQuoteApi, 'createAlternative').mockImplementation(() => new Promise(done => { resolve = done }))
    const wrapper = shallowMount(InternalQuoteAlternatives, { props: { quote }, global: { plugins: [pinia] } })
    await flushPromises()
    await wrapper.findAll('button').find(b => b.text() === '复制新版本')!.trigger('click')
    await wrapper.get('form.copy-form').trigger('submit')
    await flushPromises()
    await wrapper.setProps({ quote: { ...quote, id: 'q2' } })
    resolve({ id: 'copied' } as never)
    await flushPromises()
    expect(wrapper.find('form.copy-form').exists()).toBe(false)
    expect(wrapper.emitted('open')).toBeUndefined()
    wrapper.unmount()
  })
})
