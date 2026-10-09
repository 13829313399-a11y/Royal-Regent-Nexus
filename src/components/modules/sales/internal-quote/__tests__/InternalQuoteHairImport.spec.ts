import { flushPromises, shallowMount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ApiInternalQuoteImportPreview } from '@/api/internalQuote'
import type { InternalQuoteSection } from '@/types/internalQuoteDesk'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import InternalQuoteSectionEditor from '../InternalQuoteSectionEditor.vue'

vi.mock('vue-router', () => ({ onBeforeRouteLeave: vi.fn(), onBeforeRouteUpdate: vi.fn() }))

function setup(canEdit = true, status: InternalQuoteSection['status'] = 'draft') {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useInternalQuoteDeskStore()
  const quote = { ...store.placeholderQuote, id: 'hair-quote', factoryId: 'huaxing' }
  const section: InternalQuoteSection = {
    ...quote.sections.find((item) => item.code === 'hair')!,
    code: 'hair', label: '车发部', status, revision: 3,
    payload: {}, dependencies: [], warnings: [], attachments: [], lines: [],
  }
  const preview: ApiInternalQuoteImportPreview = {
    batch_id: 'hair-preview', quote_id: quote.id, import_type: 'hair', target_department: 'hair',
    source_file_name: '车发部报价单.xls', source_sha256: 'sha256', source_size_bytes: 100,
    preview_schema_version: 'v1', target_revision: 3, sheet_name: '明细', header_row: 9,
    row_count: 1, payload_fragment: { lines: [{ name: '产品', unit_price_hkd: '2.3870229885057475', weight_g: '15.0000' }] },
    diff_summary: { existing_rows: 0, imported_rows: 1, replace_result_rows: 1 }, warnings: [],
    status: 'previewed', created_by_name: '', created_at: '', confirm_mode: '',
    confirmed_revision: 0, confirmed_by_name: '', confirmed_at: '',
  }
  const download = vi.spyOn(store, 'downloadImportTemplate').mockResolvedValue(undefined)
  const previewImport = vi.spyOn(store, 'previewImport').mockResolvedValue(preview)
  const confirm = vi.spyOn(store, 'confirmImport').mockResolvedValue(undefined)
  const upload = vi.spyOn(store, 'uploadAttachment').mockResolvedValue(undefined)
  const wrapper = shallowMount(InternalQuoteSectionEditor, {
    props: { quote, section, canEdit, canReview: false, canRemove: false, wholeQuoteReview: true },
    global: { plugins: [pinia] },
  })
  return { wrapper, download, previewImport, confirm, upload }
}

afterEach(() => vi.restoreAllMocks())

describe('hair template download and import', () => {
  it('downloads the original XLS and explains which sheet to fill', async () => {
    const { wrapper, download } = setup()
    await wrapper.get('button.template-download').trigger('click')
    await flushPromises()
    expect(download).toHaveBeenCalledWith('hair-quote', 'hair', '车发部报价单.xls')
    expect(wrapper.text()).toContain('填写“明细”页的单价和重量')
    expect(wrapper.text()).not.toContain('绿色表头')
    wrapper.unmount()
  })

  it.each(['xls', 'xlsx', 'xlsm'])('previews a %s workbook and only writes after confirmation', async (extension) => {
    const { wrapper, previewImport, confirm, upload } = setup()
    const file = new File(['workbook'], `车发报价.${extension}`)
    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
    await flushPromises()
    expect(previewImport).toHaveBeenCalledWith('hair-quote', 'hair', file)
    expect(upload).not.toHaveBeenCalled()
    expect(confirm).not.toHaveBeenCalled()
    expect(wrapper.get('.quote-import-preview').text()).toContain('明细 · 表头第 9 行')
    await wrapper.get('.quote-import-preview button.primary').trigger('click')
    await flushPromises()
    expect(confirm).toHaveBeenCalledOnce()
    expect(confirm).toHaveBeenCalledWith('hair-quote', 'hair-preview', 3, undefined, undefined)
    expect(wrapper.find('.quote-import-preview').exists()).toBe(false)
    wrapper.unmount()
  })

  it.each([[false, 'draft'], [true, 'pending_review']] as const)('blocks uploads when canEdit=%s, status=%s', async (canEdit, status) => {
    const { wrapper, previewImport, upload } = setup(canEdit, status)
    expect(wrapper.get('button.primary-upload').attributes('disabled')).toBeDefined()
    expect(wrapper.get('button.template-download').attributes('disabled')).toBeUndefined()
    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [new File(['xls'], '车发.xls')] })
    await input.trigger('change')
    await flushPromises()
    expect(previewImport).not.toHaveBeenCalled()
    expect(upload).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('shows a permission error without saving the workbook as an ordinary attachment', async () => {
    const { wrapper, previewImport, upload } = setup()
    previewImport.mockRejectedValue(Object.assign(new Error('没有车发部权限'), { status: 403 }))
    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [new File(['xls'], '车发.xls')] })
    await input.trigger('change')
    await flushPromises()
    expect(wrapper.text()).toContain('没有车发部权限')
    expect(upload).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
