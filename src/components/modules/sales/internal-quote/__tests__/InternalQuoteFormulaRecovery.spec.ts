import { defineComponent } from 'vue'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import type { InternalQuote, InternalQuoteBatchProduct } from '@/types/internalQuoteDesk'
import InternalQuoteCollaboration from '../InternalQuoteCollaboration.vue'
import InternalQuotePackagingCopy from '../InternalQuotePackagingCopy.vue'
import InternalQuoteProductActions from '../InternalQuoteProductActions.vue'
import InternalQuoteOutputProblems from '../InternalQuoteOutputProblems.vue'

let dirty = false
const wrappers: ReturnType<typeof shallowMount>[] = []
async function setup(overrides: Partial<InternalQuote> = {}, permission = true, recovery = false) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const permissions = ['internal_quote:read', 'internal_quote:create', ...(permission ? ['internal_quote:reference_manage'] : [])]
  useAuthStore().applySession({
    id: 'owner', username: 'owner', display_name: '业务', roles: ['业务'], permissions,
    factory_scopes: ['huaxing'], department_scopes: ['sales-business'], force_password_change: false,
    grants: [{ role_id: 'sales_customer_owner', role_name: '业务', factory_id: 'huaxing', department: 'sales-business', permissions, data_scope: 'department' }],
  })
  const app = useAppStore()
  vi.spyOn(app, 'activeFactory', 'get').mockReturnValue({ id: 'huaxing' } as typeof app.activeFactory)
  const store = useInternalQuoteDeskStore()
  const source: InternalQuote = { ...store.placeholderQuote, id: 'source', quoteNo: 'IQ-1', productName: '来源款', factoryId: 'huaxing',
    moduleVersion: 'v4', status: 'drafting', headerRevision: 4, formulaVersion: 'current', currentFormulaVersion: 'current',
    formulaRecalculationRequired: true, ...overrides }
  const receiver = { ...source, id: 'receiver', productName: '接收款', formulaRecalculationRequired: false }
  store.quotes = [source, receiver]
  const products: InternalQuoteBatchProduct[] = [source, receiver].map((row, index) => ({
    quoteId: row.id, quoteNo: row.quoteNo, productName: row.productName, quantity: 5000, position: index + 1,
    batchSize: 2, quoteType: 'series', regionCode: '', status: row.status, headerRevision: row.headerRevision,
    isBaseline: index === 0, differsFromBaseline: false, differentHeaderFields: [], differentSections: [], differentSectionDetails: {}, mainImage: null,
  }))
  store.batchProductsByQuoteId = { source: products, receiver: products }
  vi.spyOn(store, 'loadQuote').mockImplementation(async id => store.getQuoteById(id))
  vi.spyOn(store, 'loadBatchProducts').mockResolvedValue(undefined)
  const recalculate = vi.spyOn(store, 'recalculateFormula').mockResolvedValue(undefined)
  const sync = vi.spyOn(store, 'syncReferenceSnapshot').mockResolvedValue(undefined)
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/modules/sales-business/internal-quote-desk/:quoteId/collaboration', component: InternalQuoteCollaboration },
  ] })
  await router.push({ path: '/modules/sales-business/internal-quote-desk/source/collaboration', query: { factory: 'huaxing', ...(recovery ? { formulaRecovery: '1' } : {}) } })
  await router.isReady()
  const wrapper = shallowMount(InternalQuoteCollaboration, { global: { plugins: [pinia, router], stubs: {
    RouterLink: true,
    InternalQuoteSectionEditor: defineComponent({ name: 'InternalQuoteSectionEditor', props: ['section'], setup(props, { expose }) { expose({ hasUnsavedChanges: () => dirty, canSaveWholeQuoteDraft: () => true, getWholeQuoteDraft: () => ({ sectionCode: props.section.code, revision: 1, payload: {} }), acceptSavedPayload: () => {} }); return () => null } }),
  } } })
  wrappers.push(wrapper)
  await flushPromises()
  return { wrapper, store, router, recalculate, sync }
}
type Wrapper = Awaited<ReturnType<typeof setup>>['wrapper']
const button = (wrapper: Wrapper, label: string) => wrapper.findAll('button').find(item => item.text() === label)!
beforeEach(() => {
  dirty = false
  vi.stubGlobal('IntersectionObserver', class { observe() {} disconnect() {} })
})
afterEach(() => {
  wrappers.splice(0).forEach(wrapper => wrapper.unmount())
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('packaging source formula recovery', () => {
  it('opens the summary recovery link without recalculating or changing the saved reference prices', async () => {
    const { wrapper, router, recalculate, sync } = await setup({}, true, true)
    expect(router.currentRoute.value.query).toEqual({ factory: 'huaxing' })
    expect(wrapper.get('.quote-snapshot-banner').text()).toContain('旧公式待重算')
    expect(wrapper.get('.quote-sync-panel').text()).toContain('沿用本报价原有汇率和参考价格')
    expect(wrapper.get('.quote-sync-panel').text()).toContain('历史输出文件仍保留')
    expect(button(wrapper, '按当前公式重算').attributes('disabled')).toBeDefined()
    expect(recalculate).not.toHaveBeenCalled()
    expect(sync).not.toHaveBeenCalled()
    await wrapper.get('textarea[aria-label="公式或参考资料变更原因"]').setValue('解冻后更新公式')
    await button(wrapper, '按当前公式重算').trigger('click')
    await flushPromises()
    expect(recalculate).toHaveBeenCalledWith('source', 4, '解冻后更新公式')
    expect(sync).not.toHaveBeenCalled()
  })

  it('offers recalculation for a stale section with a current header, requiring a reason', async () => {
    const { wrapper, recalculate, sync } = await setup()
    await button(wrapper, '处理旧公式').trigger('click')
    expect(button(wrapper, '按当前公式重算').attributes('disabled')).toBeDefined()
    expect(recalculate).not.toHaveBeenCalled()
    await wrapper.get('textarea[aria-label="公式或参考资料变更原因"]').setValue('  复制包装前更新公式  ')
    await button(wrapper, '按当前公式重算').trigger('click'); await flushPromises()
    expect(recalculate).toHaveBeenCalledWith('source', 4, '复制包装前更新公式')
    expect(sync).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('重算完成，请重新打开复制或输出窗口')
  })

  it('navigates from the receiver to the selected source and opens its formula panel without a write', async () => {
    const { wrapper, router, recalculate, sync } = await setup()
    await router.push('/modules/sales-business/internal-quote-desk/receiver/collaboration?factory=huaxing'); await flushPromises()
    wrapper.findComponent(InternalQuoteProductActions).vm.$emit('copy-packaging'); await flushPromises()
    wrapper.findComponent(InternalQuotePackagingCopy).vm.$emit('resolveFormula', 'source'); await flushPromises()
    expect(router.currentRoute.value.params.quoteId).toBe('source')
    expect(router.currentRoute.value.query).toEqual({ factory: 'huaxing' })
    expect(wrapper.find('.quote-sync-panel').exists()).toBe(true)
    expect(wrapper.text()).toContain('当前处理产品：来源款')
    expect(recalculate).not.toHaveBeenCalled()
    expect(sync).not.toHaveBeenCalled()
  })

  it('reloads the current source before opening recovery when dialog readiness is newer than the page', async () => {
    const { wrapper, store, recalculate } = await setup({ formulaRecalculationRequired: false })
    wrapper.findComponent(InternalQuoteProductActions).vm.$emit('copy-packaging'); await flushPromises()
    vi.mocked(store.loadQuote).mockImplementationOnce(async id => {
      const source = store.getQuoteById(id)!
      source.formulaRecalculationRequired = true
      return source
    })
    wrapper.findComponent(InternalQuotePackagingCopy).vm.$emit('resolveFormula', 'source'); await flushPromises()
    expect(wrapper.find('.quote-sync-panel').exists()).toBe(true)
    expect(recalculate).not.toHaveBeenCalled()
  })

  it.each([
    [{ versionArchived: true }, true, '本款已归档'],
    [{ status: 'exported' }, true, '本款已冻结'],
    [{}, false, '没有该厂区的公式重算权限'],
    [{ formulaRecalculationRequired: false }, true, '本款已使用当前公式'],
  ] as const)('explains why the source cannot be recalculated: %s', async (overrides, permission, text) => {
    const { wrapper, recalculate, sync } = await setup(overrides, permission, true)
    expect(wrapper.text()).toContain(text)
    expect(wrapper.find('.quote-sync-panel').exists()).toBe(false)
    expect(recalculate).not.toHaveBeenCalled()
    expect(sync).not.toHaveBeenCalled()
  })

  it('blocks recalculation and reference sync when an editor has unsaved changes', async () => {
    const { wrapper, recalculate, sync } = await setup({}, true, true)
    expect(wrapper.findComponent({ name: 'InternalQuoteSectionEditor' }).exists()).toBe(true)
    dirty = true
    await wrapper.get('textarea[aria-label="公式或参考资料变更原因"]').setValue('更新公式')
    await button(wrapper, '按当前公式重算').trigger('click')
    expect(wrapper.text()).toContain('请先保存当前款，再按当前公式重算')
    await button(wrapper, '同步最新参考表').trigger('click')
    expect(wrapper.text()).toContain('请先保存当前款，再同步参考资料')
    expect(recalculate).not.toHaveBeenCalled()
    expect(sync).not.toHaveBeenCalled()
  })
})


it('reports saved but incomplete pricing with the specific painting blocker and navigation', async () => {
  const blockers = [{ section_code: 'painting', section_name: '喷油部', state: 'blocked', reason: '喷油第 1 行：油漆、人工待填写' }]
  const { wrapper, store } = await setup({ formulaRecalculationRequired: false, readiness: { state: 'incomplete', ready_sections: 3, required_sections: 4, blockers } })
  vi.spyOn(store, 'saveWholeProductSections').mockResolvedValue({ sections: [], quote: store.getQuoteById('source') } as never)
  await button(wrapper, '保存').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('内容已保存，仍有 1 项待补齐或重算')
  expect(wrapper.text()).not.toContain('当前全部现有内容已保存')
  expect(wrapper.findComponent(InternalQuoteOutputProblems).props('problems')).toEqual(blockers)
})


it('keeps the formula blocker visible after saving otherwise ready content', async () => {
  const { wrapper, store } = await setup({ readiness: { state: 'ready', ready_sections: 3, required_sections: 3, blockers: [] } })
  vi.spyOn(store, 'saveWholeProductSections').mockResolvedValue({ sections: [], quote: store.getQuoteById('source') } as never)
  await button(wrapper, '保存').trigger('click'); await flushPromises()
  expect(wrapper.findComponent(InternalQuoteOutputProblems).props('problems')).toEqual([expect.objectContaining({ section_code: 'formula' })])
  expect(wrapper.text()).toContain('内容已保存，仍有 1 项待补齐或重算')
})
