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

afterEach(() => vi.restoreAllMocks())

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
})
