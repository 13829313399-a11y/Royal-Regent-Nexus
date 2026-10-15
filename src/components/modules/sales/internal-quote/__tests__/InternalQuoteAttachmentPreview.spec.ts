import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { internalQuoteApi } from '@/api/internalQuote'
import { createXlsxWorkbook } from '@/lib/customerPriceConverters/xlsxLite'
import { normalizeInternalQuotePayload } from '@/lib/internalQuoteSectionPayload'
import type { InternalQuoteAttachmentRecord } from '@/types/internalQuoteDesk'
import InternalQuoteAttachmentPreview from '../InternalQuoteAttachmentPreview.vue'
import InternalQuoteSectionForm from '../InternalQuoteSectionForm.vue'

const moldAttachment: InternalQuoteAttachmentRecord = {
  id: 'attachment-mold-1',
  fileName: '模具映射.xlsx',
  contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  sizeBytes: 4096,
  sha256: 'sha256-mold',
  uploadedBy: '工程部用户',
  uploadedAt: '2026-08-17 12:00:00',
  isImportSource: true,
  importBatchId: 'batch-mold-1',
  importType: 'mold',
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('Internal quote imported Excel preview', () => {
  it('shows the preview action only for a matching imported source and emits that attachment', async () => {
    const wrapper = mount(InternalQuoteSectionForm, {
      props: {
        code: 'engineering',
        modelValue: normalizeInternalQuotePayload('engineering', {}),
        attachments: [moldAttachment],
        'onUpdate:modelValue': () => undefined,
      },
    })

    const button = wrapper.get('.engineering-molds button[title="预览本部分最近导入的 Excel 原文件"]')
    expect(button.text()).toContain('预览附件')
    expect(wrapper.find('#internal-quote-engineering-hardware button[title="预览本部分最近导入的 Excel 原文件"]').exists()).toBe(false)

    await button.trigger('click')
    expect(wrapper.emitted('preview-attachment')?.[0]).toEqual([moldAttachment])
  })

  it('renders workbook sheets and cells in a read-only dialog', async () => {
    const bytes = createXlsxWorkbook([
      { name: '模具映射', rows: [['模具名称', '价格 RMB'], ['主模', 7750]] },
      { name: '说明', rows: [['只读预览']] },
    ])
    vi.spyOn(internalQuoteApi, 'previewAttachment').mockResolvedValue(new Blob([bytes as BlobPart]))

    const wrapper = mount(InternalQuoteAttachmentPreview, {
      props: { quoteId: 'quote-1', attachment: moldAttachment },
      global: { stubs: { Teleport: true } },
    })
    await flushPromises()

    expect(internalQuoteApi.previewAttachment).toHaveBeenCalledWith('quote-1', 'attachment-mold-1')
    expect(wrapper.text()).toContain('模具映射.xlsx')
    expect(wrapper.text()).toContain('模具名称')
    expect(wrapper.text()).toContain('主模')
    expect(wrapper.text()).toContain('7750')
    expect(wrapper.findAll('.workbook-sheet-tabs button')).toHaveLength(2)

    await wrapper.findAll('.workbook-sheet-tabs button')[1].trigger('click')
    expect(wrapper.text()).toContain('只读预览')
  })

  it('previews painting image bytes through the protected attachment API instead of parsing them as Excel', async () => {
    const createObjectURL = vi.fn(() => 'blob:painting-image')
    const revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', class extends URL {
      static createObjectURL = createObjectURL
      static revokeObjectURL = revokeObjectURL
    })
    const attachment = { ...moldAttachment, id: 'image-1', fileName: '喷油图片.png', contentType: 'image/png' }
    const blob = new Blob([new Uint8Array([137, 80, 78, 71])], { type: 'image/png' })
    vi.spyOn(internalQuoteApi, 'previewAttachment').mockResolvedValue(blob)
    const wrapper = mount(InternalQuoteAttachmentPreview, {
      props: { quoteId: 'quote-1', attachment },
      global: { stubs: { Teleport: true } },
    })
    await flushPromises()
    expect(internalQuoteApi.previewAttachment).toHaveBeenCalledWith('quote-1', 'image-1')
    expect(createObjectURL).toHaveBeenCalledWith(blob)
    expect(wrapper.get('.attachment-image-preview img').attributes()).toMatchObject({ src: 'blob:painting-image', alt: '喷油图片.png' })
    expect(wrapper.find('table').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('无法显示附件')
    await wrapper.setProps({ attachment: undefined })
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:painting-image')
    wrapper.unmount()
  })

  it('discards an image response arriving after another quote is opened', async () => {
    const createObjectURL = vi.fn(() => 'blob:current-image')
    const revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', class extends URL {
      static createObjectURL = createObjectURL
      static revokeObjectURL = revokeObjectURL
    })
    let resolveOld!: (blob: Blob) => void
    const oldResponse = new Promise<Blob>((resolve) => { resolveOld = resolve })
    const current = new Blob(['current-image'], { type: 'image/png' })
    vi.spyOn(internalQuoteApi, 'previewAttachment').mockReturnValueOnce(oldResponse).mockResolvedValueOnce(current)
    const wrapper = mount(InternalQuoteAttachmentPreview, {
      props: { quoteId: 'quote-1', attachment: { ...moldAttachment, id: 'image-1', contentType: 'image/png' } },
      global: { stubs: { Teleport: true } },
    })
    await wrapper.setProps({ quoteId: 'quote-2' })
    await flushPromises()
    resolveOld(new Blob(['old-image'], { type: 'image/png' }))
    await flushPromises()
    expect(internalQuoteApi.previewAttachment).toHaveBeenLastCalledWith('quote-2', 'image-1')
    expect(createObjectURL).toHaveBeenCalledTimes(1)
    expect(createObjectURL).toHaveBeenCalledWith(current)
    wrapper.unmount()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:current-image')
  })
})
