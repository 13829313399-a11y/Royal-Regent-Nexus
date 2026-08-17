import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { internalQuoteApi } from '@/api/internalQuote'
import type { InternalQuoteAttachmentRecord } from '@/types/internalQuoteDesk'
import InternalQuoteDepartmentFilesPanel from '../InternalQuoteDepartmentFilesPanel.vue'

const excelAttachment: InternalQuoteAttachmentRecord = {
  id: 'excel-1', fileName: '模具映射.xlsx',
  contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  sizeBytes: 2048, sha256: 'excel-sha', uploadedBy: '工程部', uploadedAt: '2026-08-17 15:00:00',
  isImportSource: true, importBatchId: 'batch-1', importType: 'mold',
}
const wordAttachment: InternalQuoteAttachmentRecord = {
  id: 'word-1', fileName: '产品说明.docx',
  contentType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  sizeBytes: 1024, sha256: 'word-sha', uploadedBy: '业务部', uploadedAt: '2026-08-17 15:10:00',
  isImportSource: false, importBatchId: '', importType: '',
}

afterEach(() => vi.restoreAllMocks())

describe('InternalQuoteDepartmentFilesPanel', () => {
  it('previews the selected department Excel attachment and exposes its sheet tabs', async () => {
    vi.spyOn(internalQuoteApi, 'previewAttachmentContent').mockResolvedValue({
      file_name: '模具映射.xlsx', kind: 'excel', paragraphs: [], warnings: [],
      sheets: [{ name: '模具', rows: [['模号', '模价'], ['M-1', 7750]], total_rows: 2, total_columns: 2, truncated: false }],
    })
    const wrapper = mount(InternalQuoteDepartmentFilesPanel, {
      props: { quoteId: 'quote-1', sectionLabel: '工程部', attachments: [excelAttachment] },
    })
    await flushPromises()

    expect(internalQuoteApi.previewAttachmentContent).toHaveBeenCalledWith('quote-1', 'excel-1')
    expect(wrapper.text()).toContain('工程部资料')
    expect(wrapper.text()).toContain('模具映射.xlsx')
    expect(wrapper.text()).toContain('模号')
    expect(wrapper.text()).toContain('7750')
    expect(wrapper.get('.department-sheet-tabs button').text()).toBe('模具')

    await wrapper.get('button[aria-label="下载当前资料"]').trigger('click')
    expect(wrapper.emitted('download')?.[0]).toEqual([excelAttachment])
  })

  it('renders extracted Word paragraphs in the resizable side-panel content', async () => {
    vi.spyOn(internalQuoteApi, 'previewAttachmentContent').mockResolvedValue({
      file_name: '产品说明.docx', kind: 'word', sheets: [], warnings: [],
      paragraphs: ['产品规格说明', '只分配给业务部。'],
    })
    const wrapper = mount(InternalQuoteDepartmentFilesPanel, {
      props: { quoteId: 'quote-1', sectionLabel: '业务部', attachments: [wordAttachment] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('产品规格说明')
    expect(wrapper.text()).toContain('只分配给业务部。')
    expect(wrapper.find('.department-word-preview').exists()).toBe(true)
  })
})
