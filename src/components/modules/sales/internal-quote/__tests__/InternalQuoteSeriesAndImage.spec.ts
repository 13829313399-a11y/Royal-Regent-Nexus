import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { internalQuoteApi } from '@/api/internalQuote'
import { useAuthStore } from '@/stores/auth'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import type { InternalQuoteBatchProduct } from '@/types/internalQuoteDesk'
import InternalQuoteProductImageUpload from '../InternalQuoteProductImageUpload.vue'
import InternalQuoteSeriesExport from '../InternalQuoteSeriesExport.vue'

afterEach(() => vi.restoreAllMocks())
function setup() {
  const pinia = createPinia(); setActivePinia(pinia)
  const auth = useAuthStore(); vi.spyOn(auth, 'can').mockReturnValue(true)
  const store = useInternalQuoteDeskStore()
  const quote = { ...store.placeholderQuote, id: 'q1', quoteNo: 'IQ-1', batchQuoteNo: 'IQ-1', factoryId: 'huakang-b', moduleVersion: 'v4', headerRevision: 8, status: 'drafting' as const }
  return { pinia, auth, store, quote }
}
async function chooseFile(wrapper: ReturnType<typeof mount>) {
  const input = wrapper.get('input[type=file]')
  Object.defineProperty(input.element, 'files', { configurable: true, value: [new File(['image'], 'main.png', { type: 'image/png' })] })
  await input.trigger('change'); await flushPromises()
}

describe('quotation main image upload', () => {
  it('uploads an editable quote image with its revision and blocks unsaved changes', async () => {
    const { pinia, store, quote } = setup()
    const upload = vi.spyOn(store, 'uploadProductImage').mockResolvedValue({ id: 'picture' } as never)
    const dirty = vi.fn(() => true)
    const wrapper = mount(InternalQuoteProductImageUpload, { props: { quote, hasImage: false, hasUnsavedChanges: dirty }, global: { plugins: [pinia] } })
    expect(wrapper.text()).toContain('上传主图')
    await chooseFile(wrapper)
    expect(upload).not.toHaveBeenCalled()
    expect(wrapper.get('[role=alert]').text()).toContain('请先保存')
    dirty.mockReturnValue(false)
    await chooseFile(wrapper)
    expect(upload).toHaveBeenCalledWith('q1', expect.any(File), 8)
    expect(wrapper.get('[role=status]').text()).toContain('已上传')
    wrapper.unmount()
  })
  it('copies an issued version before uploading and opens the new version', async () => {
    const { pinia, store, quote } = setup()
    vi.spyOn(internalQuoteApi, 'listAlternatives').mockResolvedValue({ revision: 4, items: [{ quote_id: 'q1', scenario_name: '原方案' }] } as never)
    const copy = vi.spyOn(internalQuoteApi, 'createAlternative').mockResolvedValue({ id: 'new-version', header_revision: 1 } as never)
    const upload = vi.spyOn(store, 'uploadProductImage').mockResolvedValue({ id: 'picture' } as never)
    const wrapper = mount(InternalQuoteProductImageUpload, { props: { quote: { ...quote, status: 'exported' }, hasImage: false, hasUnsavedChanges: () => false }, global: { plugins: [pinia] } })
    expect(wrapper.text()).toContain('复制新版本并上传主图')
    await chooseFile(wrapper)
    expect(copy).toHaveBeenCalledWith('q1', { revision: 8, family_revision: 4, kind: 'version', name: '原方案', change_note: '补充或更新产品主图' })
    expect(upload).toHaveBeenCalledWith('new-version', expect.any(File), 1)
    expect(wrapper.emitted('open')).toEqual([['new-version']])
    wrapper.unmount()
  })
  it('keeps a created draft accessible when upload fails and never uploads to the frozen source', async () => {
    const { pinia, store, quote } = setup()
    vi.spyOn(internalQuoteApi, 'listAlternatives').mockResolvedValue({ revision: 4, items: [] } as never)
    vi.spyOn(internalQuoteApi, 'createAlternative').mockResolvedValue({ id: 'new-version', header_revision: 1 } as never)
    vi.spyOn(store, 'uploadProductImage').mockRejectedValue(new Error('图片无法读取'))
    const wrapper = mount(InternalQuoteProductImageUpload, { props: { quote: { ...quote, status: 'exported' }, hasImage: true, hasUnsavedChanges: () => false }, global: { plugins: [pinia] } })
    await chooseFile(wrapper)
    expect(wrapper.get('[role=alert]').text()).toContain('图片无法读取')
    await wrapper.findAll('button').find(button => button.text() === '打开新版本重试上传')!.trigger('click')
    expect(wrapper.emitted('open')).toEqual([['new-version']])
    wrapper.unmount()
  })
  it('hides upload from users without access and hides copy without clone permission', async () => {
    const { pinia, auth, quote } = setup()
    vi.mocked(auth.can).mockReturnValue(false)
    const wrapper = mount(InternalQuoteProductImageUpload, { props: { quote, hasImage: false, hasUnsavedChanges: () => false }, global: { plugins: [pinia] } })
    expect(wrapper.find('button').exists()).toBe(false)
    vi.mocked(auth.can).mockImplementation(permission => permission === 'internal_quote:create')
    await wrapper.setProps({ quote: { ...quote, status: 'exported' } })
    expect(wrapper.find('button').exists()).toBe(false)
    wrapper.unmount()
  })
})

describe('series quote export', () => {
  it('submits exactly one selected version per product with captured revisions in one request', async () => {
    const { pinia, store, quote } = setup()
    const products = ['q1', 'q2', 'q3'].map((id, index) => ({ quoteId: id, productName: `兔子${index + 1}` })) as InternalQuoteBatchProduct[]
    vi.spyOn(internalQuoteApi, 'listAlternatives').mockImplementation(async id => ({ items: [
      { quote_id: id, scenario_name: '原方案', version_label: 'V1', status: 'drafting' },
      { quote_id: `${id}-v2`, scenario_name: '原方案', version_label: 'V2', status: 'exported' },
    ] } as never))
    vi.spyOn(internalQuoteApi, 'get').mockImplementation(async id => ({ header_revision: id.endsWith('v2') ? 12 : 8 } as never))
    const output = vi.spyOn(store, 'exportSeries').mockResolvedValue(undefined)
    const dirty = vi.fn(() => false)
    const wrapper = mount(InternalQuoteSeriesExport, { props: { quote, products, hasUnsavedChanges: dirty }, global: { plugins: [pinia] } })
    await flushPromises()
    expect(wrapper.findAll('select')).toHaveLength(3)
    await wrapper.get('[aria-label="兔子2 输出版本"]').setValue('q2-v2'); await flushPromises()
    dirty.mockReturnValue(true)
    await wrapper.findAll('button').find(button => button.text() === '确认输出全部 3 款')!.trigger('click')
    expect(output).not.toHaveBeenCalled()
    dirty.mockReturnValue(false)
    await wrapper.findAll('button').find(button => button.text() === '确认输出全部 3 款')!.trigger('click'); await flushPromises()
    expect(output).toHaveBeenCalledWith('q1', [{ quote_id: 'q1', revision: 8 }, { quote_id: 'q2-v2', revision: 12 }, { quote_id: 'q3', revision: 8 }], 'IQ-1-系列报价.xlsx')
    expect(wrapper.emitted('completed')).toHaveLength(1)
    wrapper.unmount()
  })
})
