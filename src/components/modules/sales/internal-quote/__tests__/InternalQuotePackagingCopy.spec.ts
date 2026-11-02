import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { internalQuoteApi, type ApiInternalQuoteBatchProduct } from '@/api/internalQuote'
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
function apiProducts(): ApiInternalQuoteBatchProduct[] {
  return products.map(row => ({
    quote_id: row.quoteId, quote_no: row.quoteNo, product_name: row.productName,
    version_label: 'A-V1', scenario_name: '原方案', archived: false,
    qty: row.quantity, position: row.position, batch_size: row.batchSize, quote_type: row.quoteType,
    region_code: row.regionCode, status: row.status, header_revision: row.headerRevision,
    is_baseline: row.isBaseline, differs_from_baseline: false, different_header_fields: [],
    different_sections: [], different_section_details: {}, main_image: null,
    packaging_copy: { material_count: 2, carton_count: 1, packaging_group_count: 2, packaging_labor_hkd: '1.6250',
      source_issue: '', assembly_issue: '', target_issue: row.status === 'exported' ? '已输出，请先复制新版本后接收包装' : '', assembly_target_issue: '' },
  }))
}
async function setup(dirty = false, rows = apiProducts(), selectSource = true) {
  const quote = { ...useInternalQuoteDeskStore().placeholderQuote, id: 'q1', versionLabel: 'A-V1' }
  const preview = vi.spyOn(internalQuoteApi, 'previewPackagingCopy').mockResolvedValue({
    preview_token: 'preview-1', source_name: '产品1', targets: [{ quote_id: 'q2', product_name: '产品2', changed: true, packaging_material_count: 2, carton_count: 1, replaces_existing: true }],
  })
  const apply = vi.spyOn(internalQuoteApi, 'applyPackagingCopy').mockResolvedValue({ targets: [] })
  const list = vi.spyOn(internalQuoteApi, 'listBatchProducts').mockResolvedValue(rows)
  const wrapper = mount(InternalQuotePackagingCopy, { props: { quote, products, hasUnsavedChanges: () => dirty } })
  await flushPromises()
  if (selectSource) await wrapper.get('select').setValue('q1')
  return { wrapper, preview, apply, list }
}
const button = (wrapper: Awaited<ReturnType<typeof setup>>['wrapper'], text: string) => wrapper.findAll('button').find(row => row.text() === text)!
beforeEach(() => setActivePinia(createPinia()))
afterEach(() => vi.restoreAllMocks())

describe('copy only packaging inside a quotation', () => {
  it('opens the selected stale source without copying or recalculating it', async () => {
    const rows = apiProducts()
    rows[1]!.packaging_copy!.formula_recalculation_required = true
    rows[1]!.packaging_copy!.source_issue = '来源部门仍使用旧公式'
    const { wrapper, preview, apply, list } = await setup(false, rows)
    expect(button(wrapper, '前往来源款处理')).toBeUndefined()
    await wrapper.get('select').setValue('q2')
    await button(wrapper, '前往来源款处理').trigger('click')
    expect(wrapper.emitted('resolveFormula')).toEqual([['q2']])
    expect(preview).not.toHaveBeenCalled()
    expect(apply).not.toHaveBeenCalled()
    list.mockResolvedValue(apiProducts())
    await button(wrapper, '刷新状态').trigger('click'); await flushPromises()
    expect(button(wrapper, '前往来源款处理')).toBeUndefined()
    wrapper.unmount()
  })

  it('does not leave unsaved edits to resolve a source formula', async () => {
    const rows = apiProducts()
    rows[0]!.packaging_copy!.formula_recalculation_required = true
    const { wrapper } = await setup(true, rows)
    await button(wrapper, '前往来源款处理').trigger('click')
    expect(wrapper.emitted('resolveFormula')).toBeUndefined()
    expect(wrapper.text()).toContain('请先保存当前款')
    wrapper.unmount()
  })

  it('previews selected products and confirms with the returned token; issued targets are disabled', async () => {
    const { wrapper, preview, apply } = await setup()
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
    const { wrapper, apply } = await setup()
    await wrapper.findAll('fieldset input')[0]!.setValue(true)
    await button(wrapper, '预览复制').trigger('click'); await flushPromises()
    await wrapper.get('input[aria-label="包装复制说明"]').setValue('调整包装')
    expect(wrapper.text()).not.toContain('复制预览：')
    expect(button(wrapper, '预览复制')).toBeDefined()
    expect(apply).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('keeps unsaved product edits and refuses preview', async () => {
    const { wrapper, preview } = await setup(true)
    await wrapper.findAll('fieldset input')[0]!.setValue(true)
    await button(wrapper, '预览复制').trigger('click'); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('先保存当前款')
    expect(preview).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('requires a new preview after a rejected confirmation', async () => {
    const { wrapper, apply } = await setup()
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

  it('requires an explicit source and displays the actual direction and packaging cost', async () => {
    const { wrapper, preview } = await setup(false, apiProducts(), false)
    expect((wrapper.get('select').element as HTMLSelectElement).value).toBe('')
    expect(button(wrapper, '预览复制').attributes('disabled')).toBeDefined()
    await wrapper.get('select').setValue('q1')
    await wrapper.findAll('fieldset input')[0]!.setValue(true)
    expect(wrapper.get('[aria-label="包装复制方向"]').text()).toBe('产品1 · 原方案 · A-V1→产品2 · 原方案 · A-V1')
    expect(wrapper.get('[aria-label="来源包装资料"]').text()).toContain('HKD 1.6250')
    expect(wrapper.text()).toContain('不会复制装配部包装工序或包装人工')
    expect(preview).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('explains saved empty source assembly and blocks preview only when assembly is included', async () => {
    const rows = apiProducts()
    rows[0]!.packaging_copy!.assembly_issue = '来源产品 产品1 的装配部已保存，但核算未通过：没有可计算明细'
    rows[0]!.packaging_copy!.packaging_group_count = 0
    rows[0]!.packaging_copy!.packaging_labor_hkd = null
    const { wrapper, preview } = await setup(false, rows)
    await wrapper.findAll('fieldset input')[0]!.setValue(true)
    expect(button(wrapper, '预览复制').attributes('disabled')).toBeUndefined()
    await wrapper.get('.packaging-assembly input').setValue(true)
    expect(wrapper.get('[role="alert"]').text()).toContain('装配部已保存，但核算未通过')
    expect(button(wrapper, '预览复制').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('待核算')
    expect(preview).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('keeps archived product identities visible but refuses them as source or receiver', async () => {
    const rows = apiProducts()
    rows[0]!.archived = true
    rows[0]!.packaging_copy!.source_issue = '来源产品 产品1 此方案版本已归档，请先恢复'
    rows[0]!.packaging_copy!.target_issue = '接收产品 产品1 此方案版本已归档，请先恢复'
    const { wrapper } = await setup(false, rows)
    expect(wrapper.text()).toContain('此方案版本已归档，请先恢复')
    expect(button(wrapper, '预览复制').attributes('disabled')).toBeDefined()
    await wrapper.get('select').setValue('q2')
    expect(wrapper.get('fieldset input[value="q1"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('refreshes revisions, discards old previews and fails closed when status loading fails', async () => {
    const { wrapper, preview, list } = await setup()
    await wrapper.findAll('fieldset input')[0]!.setValue(true)
    await button(wrapper, '预览复制').trigger('click'); await flushPromises()
    const rows = apiProducts(); rows[0]!.header_revision = 22
    list.mockResolvedValue(rows)
    await button(wrapper, '刷新状态').trigger('click'); await flushPromises()
    expect(wrapper.text()).not.toContain('复制预览：')
    await button(wrapper, '预览复制').trigger('click'); await flushPromises()
    expect(preview).toHaveBeenLastCalledWith('q1', expect.objectContaining({ revision: 22 }))
    list.mockRejectedValue(new Error('网络断开'))
    await button(wrapper, '刷新状态').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('读取包装状态失败')
    expect(button(wrapper, '预览复制').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('ignores an older product-list response after changing quote context', async () => {
    const { wrapper, list } = await setup()
    let finish!: (rows: ApiInternalQuoteBatchProduct[]) => void
    list.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    await button(wrapper, '刷新状态').trigger('click')
    list.mockResolvedValue([])
    await wrapper.setProps({ quote: { ...wrapper.props('quote'), id: 'another-document' } })
    await flushPromises()
    finish(apiProducts()); await flushPromises()
    expect(wrapper.findAll('option')).toHaveLength(1)
    expect(button(wrapper, '预览复制').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
})
