import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { internalQuoteApi, type ApiInternalQuote, type ApiInternalQuoteAlternativeFamily } from '@/api/internalQuote'
import { useAuthStore } from '@/stores/auth'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import { readWorkingVersions, rememberWorkingVersion } from '@/lib/internalQuoteWorkingVersions'
import type { InternalQuoteBatchProduct } from '@/types/internalQuoteDesk'
import InternalQuoteGroupCopy from '../InternalQuoteGroupCopy.vue'
import InternalQuoteSeriesExport from '../InternalQuoteSeriesExport.vue'

beforeEach(() => localStorage.clear())
afterEach(() => vi.restoreAllMocks())
function setup() {
  const pinia = createPinia(); setActivePinia(pinia)
  const auth = useAuthStore(); auth.currentUser = { id: 'user' } as never
  const store = useInternalQuoteDeskStore()
  const quote = { ...store.placeholderQuote, id: 'p1-v2', documentQuoteId: 'p1', productRootId: 'p1', factoryId: 'huakang-b', status: 'drafting' as const }
  const products = ['p1', 'p2', 'p3'].map(id => ({ quoteId: id, productName: id })) as InternalQuoteBatchProduct[]
  vi.spyOn(internalQuoteApi, 'getAlternativeGroup').mockResolvedValue(null)
  vi.spyOn(internalQuoteApi, 'listBatchProducts').mockResolvedValue(products.map(p => ({ quote_id: p.quoteId, product_name: p.productName })) as never)
  vi.spyOn(internalQuoteApi, 'listAlternatives').mockImplementation(async id => ({ family_id: id, revision: 3, selected_quote_id: '', items: [id, `${id}-v2`, `${id}-newest`].map((q, index) => ({
    quote_id: q, scenario_name: index ? '调价方案' : '原方案', version_label: `V${index + 1}`, archived: false, status: 'drafting',
  })) } as ApiInternalQuoteAlternativeFamily))
  vi.spyOn(internalQuoteApi, 'get').mockImplementation(async id => ({ id, factory_id: 'huakang-b', document_quote_id: 'p1', product_root_id: id.split('-')[0], header_revision: 8, status: 'drafting' } as ApiInternalQuote))
  return { pinia, store, quote, products }
}

it('copies exactly one chosen version per product and remembers the resulting group', async () => {
  const { quote, pinia } = setup()
  rememberWorkingVersion('user', { ...quote, id: 'p2-v2', productRootId: 'p2' })
  const copy = vi.spyOn(internalQuoteApi, 'copyAlternativeGroup').mockResolvedValue({
    group: { group_id: 'g', document_quote_id: 'p1', kind: 'scenario', name: '调价', products: ['p1', 'p2', 'p3'].map(p => ({ product_root_id: p, source_quote_id: p, quote_id: `${p}-copy` })) },
    quotes: ['p1', 'p2', 'p3'].map(p => ({ id: `${p}-copy`, factory_id: 'huakang-b', document_quote_id: 'p1', product_root_id: p, status: 'drafting' })) as ApiInternalQuote[],
  })
  const wrapper = mount(InternalQuoteGroupCopy, { props: { quote, kind: 'scenario', hasUnsavedChanges: () => false }, global: { plugins: [pinia] } })
  try {
    await flushPromises()
    expect(wrapper.findAll('select').map(s => (s.element as HTMLSelectElement).value)).toEqual(['p1-v2', 'p2-v2', 'p3'])
    await wrapper.get('input').setValue('调价'); await wrapper.get('textarea').setValue('客户目标价调整')
    await wrapper.findAll('button').find(b => b.text() === '确认复制全部 3 款')!.trigger('click'); await flushPromises()
    expect(copy).toHaveBeenCalledWith('p1-v2', { kind: 'scenario', name: '调价', change_note: '客户目标价调整', products: ['p1-v2', 'p2-v2', 'p3'].map(quote_id => ({ quote_id, revision: 8, family_revision: 3 })) })
    expect(wrapper.emitted('open')).toEqual([['p1-copy']])
    expect(readWorkingVersions('user', 'huakang-b', 'p1').products).toEqual({ p1: 'p1-copy', p2: 'p2-copy', p3: 'p3-copy' })
  } finally { wrapper.unmount() }
})

it('requires an explicit replacement for a deleted group member and keeps failed copies open', async () => {
  const { quote, pinia } = setup()
  vi.mocked(internalQuoteApi.getAlternativeGroup).mockResolvedValue({ group_id: 'g', document_quote_id: 'p1', kind: 'version', name: '', products: [{ product_root_id: 'p2', source_quote_id: 'p2', quote_id: 'deleted' }] })
  const copy = vi.spyOn(internalQuoteApi, 'copyAlternativeGroup').mockRejectedValue(new Error('第三款资料已变化'))
  const wrapper = mount(InternalQuoteGroupCopy, { props: { quote, kind: 'version' }, global: { plugins: [pinia] } })
  try {
    await flushPromises()
    const confirm = () => wrapper.findAll('button').find(b => b.text() === '确认复制全部 3 款')!
    expect(confirm().attributes('disabled')).toBeDefined()
    await wrapper.get('[aria-label="p2 来源版本"]').setValue('p2-v2'); await flushPromises()
    await wrapper.get('textarea').setValue('复制后调整')
    await confirm().trigger('click'); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('第三款资料已变化')
    expect(wrapper.emitted('open')).toBeUndefined()
    expect(readWorkingVersions('user', 'huakang-b', 'p1').lastQuoteId).toBe('')
  } finally { wrapper.unmount() }
})

it('preselects the active group for output and submits exactly the displayed versions', async () => {
  const { quote, pinia, store, products } = setup()
  vi.mocked(internalQuoteApi.getAlternativeGroup).mockResolvedValue({ group_id: 'g', document_quote_id: 'p1', kind: 'version', name: '', products: products.map(p => ({ product_root_id: p.quoteId, source_quote_id: p.quoteId, quote_id: `${p.quoteId}-v2` })) })
  const output = vi.spyOn(store, 'exportSeries').mockResolvedValue(undefined)
  const wrapper = mount(InternalQuoteSeriesExport, { props: { quote, products, hasUnsavedChanges: () => false }, global: { plugins: [pinia] } })
  try {
    await flushPromises()
    expect(wrapper.findAll('select').map(s => (s.element as HTMLSelectElement).value)).toEqual(['p1-v2', 'p2-v2', 'p3-v2'])
    await wrapper.findAll('button').find(b => b.text() === '确认输出全部 3 款')!.trigger('click'); await flushPromises()
    expect(output.mock.calls[0]![1]).toEqual(['p1-v2', 'p2-v2', 'p3-v2'].map(quote_id => ({ quote_id, revision: 8 })))
  } finally { wrapper.unmount() }
})

it('discards a late copy response after the component has closed', async () => {
  const { quote, pinia } = setup()
  let finish!: (value: Awaited<ReturnType<typeof internalQuoteApi.copyAlternativeGroup>>) => void
  vi.spyOn(internalQuoteApi, 'copyAlternativeGroup').mockImplementation(() => new Promise(resolve => { finish = resolve }))
  const wrapper = mount(InternalQuoteGroupCopy, { props: { quote, kind: 'version' }, global: { plugins: [pinia] } })
  await flushPromises(); await wrapper.get('textarea').setValue('复制')
  await wrapper.findAll('button').find(b => b.text() === '确认复制全部 3 款')!.trigger('click')
  wrapper.unmount(); finish({ group: {} as never, quotes: [] }); await flushPromises()
  expect(wrapper.emitted('open')).toBeUndefined()
  expect(readWorkingVersions('user', 'huakang-b', 'p1').lastQuoteId).toBe('')
})
