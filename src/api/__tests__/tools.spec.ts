import { describe, expect, it, vi } from 'vitest'
import {
  createSharedToolsApi,
  DOCUMENT_TRANSLATION_TIMEOUT_MS,
  PDF_SPLIT_TIMEOUT_MS,
  PDF_TO_EXCEL_TIMEOUT_MS,
  PDF_TO_WORD_TIMEOUT_MS,
} from '@/api/tools'


describe('shared tools api', () => {
  it('uploads one Office document with the selected translation direction', async () => {
    const blob = new Blob(['docx'], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    const post = vi.fn().mockResolvedValue({
      data: blob,
      headers: {
        'content-disposition': "attachment; filename*=UTF-8''%E8%AE%A2%E5%8D%95_%E4%B8%AD%E8%AF%91%E8%8B%B1.docx",
        'x-translation-unit-count': '18',
        'x-translation-skipped-count': '7',
        'x-translation-part-count': '3',
      },
    })
    const api = createSharedToolsApi({ post })
    const file = new File(['office'], '订单.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })

    const result = await api.translateDocument(file, 'zh_to_en')

    const [url, payload, config] = post.mock.calls[0]!
    expect(url).toBe('/tools/document-translation')
    expect((payload as FormData).get('document_file')).toBe(file)
    expect((payload as FormData).get('direction')).toBe('zh_to_en')
    expect((payload as FormData).get('mode')).toBe('local_private')
    expect((payload as FormData).get('sheet_names')).toBeNull()
    expect(config).toMatchObject({ responseType: 'blob', timeout: DOCUMENT_TRANSLATION_TIMEOUT_MS })
    expect(result).toMatchObject({
      fileName: '订单_中译英.docx',
      translatedUnitCount: 18,
      skippedUnitCount: 7,
      processedPartCount: 3,
    })
  })

  it('requires an explicit cloud mode and consent marker', async () => {
    const post = vi.fn().mockResolvedValue({ data: new Blob(['xlsx']), headers: {} })
    const api = createSharedToolsApi({ post })
    const file = new File(['office'], '订单.xlsx')

    await api.translateDocument(file, 'zh_to_en', ['订单'], 'ai_smart_cloud', true)

    const payload = post.mock.calls[0]![1] as FormData
    expect(payload.get('mode')).toBe('ai_smart_cloud')
    expect(payload.get('cloud_consent')).toBe('true')
    expect(payload.get('sheet_names')).toBe('["订单"]')
  })

  it('uploads the selected Excel worksheet names with the translation request', async () => {
    const post = vi.fn().mockResolvedValue({
      data: new Blob(['xlsx']),
      headers: {},
    })
    const api = createSharedToolsApi({ post })
    const file = new File(['office'], '订单.xlsx')

    await api.translateDocument(file, 'en_to_zh', ['报价单', '生产计划'])

    const payload = post.mock.calls[0]![1] as FormData
    expect(payload.get('direction')).toBe('en_to_zh')
    expect(payload.get('sheet_names')).toBe('["报价单","生产计划"]')
  })

  it('uploads one PDF and returns download metadata', async () => {
    const blob = new Blob(['xlsx'], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const post = vi.fn().mockResolvedValue({
      data: blob,
      headers: {
        'content-disposition': "attachment; filename*=UTF-8''%E6%B5%8B%E8%AF%95_%E8%BD%AC%E6%8D%A2%E7%BB%93%E6%9E%9C.xlsx",
        'x-pdf-page-count': '3',
        'x-pdf-table-count': '2',
        'x-pdf-text-page-count': '1',
        'x-pdf-ocr-page-count': '0',
      },
    })
    const api = createSharedToolsApi({ post })
    const file = new File(['%PDF-test'], '测试.pdf', { type: 'application/pdf' })

    const result = await api.convertPdfToExcel(file)

    expect(post).toHaveBeenCalledOnce()
    const [url, payload, config] = post.mock.calls[0]!
    expect(url).toBe('/tools/pdf-to-excel')
    expect(payload).toBeInstanceOf(FormData)
    expect((payload as FormData).get('pdf_file')).toBe(file)
    expect(config).toMatchObject({ responseType: 'blob', timeout: PDF_TO_EXCEL_TIMEOUT_MS })
    expect(result.fileName).toBe('测试_转换结果.xlsx')
    expect(result.metrics).toEqual({ pageCount: 3, tableCount: 2, textPageCount: 1, ocrPageCount: 0 })
  })

  it('reads the offline translation service status', async () => {
    const get = vi.fn().mockResolvedValue({
      data: {
        available: true,
        engine: 'offline',
        engineLabel: '服务器离线中英模型',
        directions: { zh_to_en: true, en_to_zh: true },
      },
    })
    const api = createSharedToolsApi({ post: vi.fn(), get })

    await expect(api.getDocumentTranslationStatus()).resolves.toMatchObject({ available: true })
    expect(get).toHaveBeenCalledWith('/tools/document-translation/status')
  })

  it('converts one PDF to Word with conversion metrics', async () => {
    const blob = new Blob(['docx'], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    const post = vi.fn().mockResolvedValue({
      data: blob,
      headers: {
        'content-disposition': "attachment; filename*=UTF-8''%E8%AE%A2%E5%8D%95_%E8%BD%AC%E6%8D%A2%E7%BB%93%E6%9E%9C.docx",
        'x-pdf-page-count': '4',
        'x-pdf-table-count': '1',
        'x-pdf-text-page-count': '2',
        'x-pdf-ocr-page-count': '2',
      },
    })
    const api = createSharedToolsApi({ post })
    const file = new File(['%PDF-test'], '订单.pdf', { type: 'application/pdf' })

    const result = await api.convertPdfToWord(file)

    const [url, payload, config] = post.mock.calls[0]!
    expect(url).toBe('/tools/pdf-to-word')
    expect((payload as FormData).get('pdf_file')).toBe(file)
    expect(config).toMatchObject({ responseType: 'blob', timeout: PDF_TO_WORD_TIMEOUT_MS })
    expect(result.fileName).toBe('订单_转换结果.docx')
    expect(result.metrics).toEqual({ pageCount: 4, tableCount: 1, textPageCount: 2, ocrPageCount: 2 })
  })

  it('submits split mode and page ranges then returns ZIP metadata', async () => {
    const blob = new Blob(['zip'], { type: 'application/zip' })
    const post = vi.fn().mockResolvedValue({
      data: blob,
      headers: {
        'content-disposition': "attachment; filename*=UTF-8''%E8%AE%A2%E5%8D%95_%E6%8B%86%E5%88%86%E7%BB%93%E6%9E%9C.zip",
        'x-pdf-page-count': '8',
        'x-pdf-split-file-count': '3',
      },
    })
    const api = createSharedToolsApi({ post })
    const file = new File(['%PDF-test'], '订单.pdf', { type: 'application/pdf' })

    const result = await api.splitPdf(file, { mode: 'ranges', pageRanges: '1-3, 4, 5-8' })

    const [url, payload, config] = post.mock.calls[0]!
    expect(url).toBe('/tools/pdf-split')
    expect((payload as FormData).get('pdf_file')).toBe(file)
    expect((payload as FormData).get('split_mode')).toBe('ranges')
    expect((payload as FormData).get('page_ranges')).toBe('1-3, 4, 5-8')
    expect(config).toMatchObject({ responseType: 'blob', timeout: PDF_SPLIT_TIMEOUT_MS })
    expect(result).toMatchObject({ fileName: '订单_拆分结果.zip', pageCount: 8, fileCount: 3 })
  })
})
