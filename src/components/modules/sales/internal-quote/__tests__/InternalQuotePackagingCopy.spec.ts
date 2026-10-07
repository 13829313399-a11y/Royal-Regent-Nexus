import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { internalQuoteApi } from '@/api/internalQuote'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import type { InternalQuoteBatchProduct } from '@/types/internalQuoteDesk'
import InternalQuotePackagingCopy from '../InternalQuotePackagingCopy.vue'
import InternalQuoteProductActions from '../InternalQuoteProductActions.vue'

const products: InternalQuoteBatchProduct[] = ['q1', 'q2', 'q3'].map((quoteId, index) => ({
  quoteId, quoteNo: 'IQ', productName: `产品${index + 1}`, quantity: 5000,
  position: index + 1, batchSize: 3, quoteType: 'series', regionCode: '', status: index === 2 ? 'exported' : 'drafting',
  headerRevision: index + 4, isBaseline: index === 0, differsFromBaseline: false,
  differentHeaderFields: [], differentSections: [], differentSectionDetails: {}, mainImage: null,
}))
function setup(dirty = false) {
  const quote = { ...useInternalQuoteDeskStore().placeholderQuote, id: 'q1', versionLabel: 'A-V1' }
  const preview = vi.spyOn(internalQuoteApi, 'previewPackagingCopy').mockResolvedValue({
    preview_token: 'preview-1', source_name: '产品1', targets: [{ quote_id: 'q2', product_name: '产品2', changed: true, packaging_material_count: 2, carton_count: 1, replaces_existing: true }],
  })
  const apply = vi.spyOn(internalQuoteApi, 'applyPackagingCopy').mockResolvedValue({ targets: [] })
  const wrapper = mount(InternalQuotePackagingCopy, { props: { quote, products, hasUnsavedChanges: () => dirty } })
  return { wrapper, preview, apply }
}
const button = (wrapper: ReturnType<typeof setup>['wrapper'], text: string) => wrapper.findAll('button').find(row => row.text() === text)!
beforeEach(() => setActivePinia(createPinia()))
afterEach(() => vi.restoreAllMocks())

describe('copy only packaging inside a quotation', () => {
  it('previews selected products and confirms with the returned token; issued targets are disabled', async () => {
    const { wrapper, preview, apply } = setup()
    const boxes = wrapper.findAll('fieldset input')
    expect(boxes[1]!.attributes('disabled')).toBeDefined()
    await boxes[0]!.setValue(true)
    await button(wrapper, '预览复制').trigger('click'); await flushPromises()
    expect(preview).toHaveBeenCalledWith('q1', { revision: 4, targets: [{ quote_id: 'q2', revision: 5 }], include_assembly: false, reason: '同一报价单多款产品共用包装' })
    expect(apply).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('将替换已有包装资料')
    await button(wrapper, '确认仅复制包装').trigger('click'); await flushPromises()
    expect(apply).toHaveBeenCalledWith('q1', expect.objectContaining({ preview_token: 'preview-1' }))
    expect(wrapper.emitted('copied')).toHaveLength(1)
    wrapper.unmount()
  })

  it('invalidates the preview when copy options change', async () => {
    const { wrapper, apply } = setup()
    await wrapper.findAll('fieldset input')[0]!.setValue(true)
    await button(wrapper, '预览复制').trigger('click'); await flushPromises()
    await wrapper.get('input[aria-label="包装复制说明"]').setValue('调整包装')
    expect(wrapper.text()).not.toContain('复制预览：')
    expect(button(wrapper, '预览复制')).toBeDefined()
    expect(apply).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('keeps unsaved product edits and refuses preview', async () => {
    const { wrapper, preview } = setup(true)
    await wrapper.findAll('fieldset input')[0]!.setValue(true)
    await button(wrapper, '预览复制').trigger('click'); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('先保存当前款')
    expect(preview).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('requires a new preview after a rejected confirmation', async () => {
    const { wrapper, apply } = setup()
    apply.mockRejectedValue(new Error('复制预览已失效，请重新预览后确认'))
    await wrapper.findAll('fieldset input')[0]!.setValue(true)
    await button(wrapper, '预览复制').trigger('click'); await flushPromises()
    await button(wrapper, '确认仅复制包装').trigger('click'); await flushPromises()
    expect(wrapper.emitted('copied')).toBeUndefined()
    expect(wrapper.text()).toContain('复制预览已失效')
    expect(button(wrapper, '预览复制')).toBeDefined()
    wrapper.unmount()
  })

  it('offers packaging reuse separately from full baseline overwrite', async () => {
    const wrapper = mount(InternalQuoteProductActions, { props: { products, currentQuoteId: 'q2', canManage: true, copyBusyQuoteId: '' } })
    expect(wrapper.text()).toContain('复制整份基准款')
    await wrapper.findAll('button').find(row => row.text() === '仅复制包装')!.trigger('click')
    expect(wrapper.emitted('copyPackaging')).toHaveLength(1)
    expect(wrapper.emitted('copyBaseline')).toBeUndefined()
    wrapper.unmount()
  })
})
