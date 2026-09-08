import { describe, expect, it, vi } from 'vitest'
import {
  createSharedToolsApi,
  DOCUMENT_TRANSLATION_TIMEOUT_MS,
  PDF_TRANSLATION_TIMEOUT_MS,
  PDF_SPLIT_TIMEOUT_MS,
  PDF_TO_EXCEL_TIMEOUT_MS,
  PDF_TO_WORD_TIMEOUT_MS,
  PDF_BATCH_RENAME_TIMEOUT_MS,
  WORD_TO_PDF_TIMEOUT_MS,
} from '@/api/tools'


describe('shared tools api', () => {
  it('allows document translation requests to wait for 30 minutes', () => {
    expect(DOCUMENT_TRANSLATION_TIMEOUT_MS).toBe(30 * 60 * 1000)
    expect(PDF_TRANSLATION_TIMEOUT_MS).toBe(30 * 60 * 1000)
    expect(PDF_TO_EXCEL_TIMEOUT_MS).toBe(15 * 60 * 1000)
    expect(PDF_TO_WORD_TIMEOUT_MS).toBe(15 * 60 * 1000)
    expect(WORD_TO_PDF_TIMEOUT_MS).toBe(5 * 60 * 1000)
    expect(PDF_SPLIT_TIMEOUT_MS).toBe(5 * 60 * 1000)
    expect(PDF_BATCH_RENAME_TIMEOUT_MS).toBe(15 * 60 * 1000)
  })

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

  it('turns an HTML gateway timeout into a safe Chinese message', async () => {
    const post = vi.fn().mockRejectedValue({
      isAxiosError: true,
      message: 'Request failed with status code 504',
      response: {
        status: 504,
        headers: { 'content-type': 'text/html' },
        data: new Blob([
          '<html><head><title>504 Gateway Time-out</title></head><body>nginx</body></html>',
        ], { type: 'text/html' }),
      },
    })
    const api = createSharedToolsApi({ post })
    const file = new File(['office'], '订单.docx')

    await expect(api.translateDocument(file, 'zh_to_en')).rejects.toThrow(
      '文档处理超过网关等待时间（最长 30 分钟）',
    )
  })

  it('does not expose an upstream HTML error page', async () => {
    const post = vi.fn().mockRejectedValue({
      isAxiosError: true,
      message: 'Request failed with status code 502',
      response: {
        status: 502,
        headers: { 'content-type': 'text/html' },
        data: new Blob(['<html><body>upstream details</body></html>'], { type: 'text/html' }),
      },
    })
    const api = createSharedToolsApi({ post })
    const file = new File(['office'], '订单.docx')

    await expect(api.translateDocument(file, 'zh_to_en')).rejects.toThrow(
      '服务器暂时无法完成文档处理，请稍后重试。',
    )
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
    expect((payload as FormData).get('processing_mode')).toBe('AUTO')
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
        'x-pdf-image-count': '3',
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
    expect((payload as FormData).get('processing_mode')).toBe('AUTO')
    expect((payload as FormData).get('output_mode')).toBe('EDITABLE')
    expect(config).toMatchObject({ responseType: 'blob', timeout: PDF_TO_WORD_TIMEOUT_MS })
    expect(result.fileName).toBe('订单_转换结果.docx')
    expect(result.metrics).toEqual({ pageCount: 4, tableCount: 1, imageCount: 3, textPageCount: 2, ocrPageCount: 2 })
  })

  it('converts one Word document to PDF without the Document Job runtime', async () => {
    const blob = new Blob(['pdf'], { type: 'application/pdf' })
    const post = vi.fn().mockResolvedValue({
      data: blob,
      headers: {
        'content-disposition': "attachment; filename*=UTF-8''%E8%AE%A2%E5%8D%95_%E8%BD%AC%E6%8D%A2%E7%BB%93%E6%9E%9C.pdf",
        'x-word-page-count': '3',
        'x-word-blank-page-count': '1',
      },
    })
    const api = createSharedToolsApi({ post })
    const file = new File(['docx'], '订单.docx')

    const result = await api.convertWordToPdf(file)

    const [url, payload, config] = post.mock.calls[0]!
    expect(url).toBe('/tools/word-to-pdf')
    expect((payload as FormData).get('document_file')).toBe(file)
    expect((payload as FormData).get('processing_mode')).toBe('AUTO')
    expect(config).toMatchObject({ responseType: 'blob', timeout: WORD_TO_PDF_TIMEOUT_MS })
    expect(result).toMatchObject({ fileName: '订单_转换结果.pdf', pageCount: 3, blankPageCount: 1 })
  })

  it('translates one PDF locally with layout and protected-token options', async () => {
    const blob = new Blob(['translated'], { type: 'application/pdf' })
    const post = vi.fn().mockResolvedValue({
      data: blob,
      headers: {
        'content-disposition': "attachment; filename*=UTF-8''order_translated.pdf",
        'x-pdf-page-count': '2',
        'x-translation-unit-count': '18',
        'x-pdf-ocr-page-count': '1',
      },
    })
    const api = createSharedToolsApi({ post })
    const file = new File(['%PDF-test'], 'order.pdf', { type: 'application/pdf' })

    const result = await api.translatePdf(file, {
      direction: 'ZH_TO_EN',
      layout: 'SIDE_BY_SIDE',
      protectedTokens: ['PO-001', '0012'],
      includeEditableDocx: false,
    })

    const [url, payload, config] = post.mock.calls[0]!
    expect(url).toBe('/tools/pdf-translation')
    expect((payload as FormData).get('pdf_file')).toBe(file)
    expect((payload as FormData).get('direction')).toBe('ZH_TO_EN')
    expect((payload as FormData).get('layout')).toBe('SIDE_BY_SIDE')
    expect((payload as FormData).get('protected_tokens')).toBe('["PO-001","0012"]')
    expect((payload as FormData).get('processing_mode')).toBe('AUTO')
    expect(config).toMatchObject({ responseType: 'blob', timeout: PDF_TRANSLATION_TIMEOUT_MS })
    expect(result).toMatchObject({
      fileName: 'order_translated.pdf',
      pageCount: 2,
      translatedUnitCount: 18,
      ocrPageCount: 1,
    })
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
    expect((payload as FormData).get('processing_mode')).toBe('AUTO')
    expect(config).toMatchObject({ responseType: 'blob', timeout: PDF_SPLIT_TIMEOUT_MS })
    expect(result).toMatchObject({ fileName: '订单_拆分结果.zip', pageCount: 8, fileCount: 3 })
  })

  it('reads runtime capabilities instead of inventing frontend availability', async () => {
    const get = vi.fn().mockResolvedValue({
      data: {
        enabled: true,
        default_mode: 'AUTO',
        tools: { 'word-to-pdf': { available: false, reason_code: 'LIBREOFFICE_NOT_INSTALLED' } },
      },
    })
    const api = createSharedToolsApi({ post: vi.fn(), get })

    const result = await api.getCapabilities()

    expect(result.tools['word-to-pdf']?.available).toBe(false)
    expect(get).toHaveBeenCalledWith('/tools/capabilities', undefined)
  })

  it('loads rename rules and keeps preview separate from execution', async () => {
    const get = vi.fn().mockResolvedValue({
      data: {
        rules: [{ id: 'fixed-region-a', available: true }],
        limits: { max_files: 50, max_batch_bytes: 200, max_file_bytes: 20 },
      },
    })
    const post = vi.fn()
      .mockResolvedValueOnce({
        data: {
          rule: { id: 'fixed-region-a' },
          items: [],
          preview_token: 'preview-token',
          summary: { total: 0, ready: 0, review: 0, error: 0 },
        },
        headers: {},
      })
      .mockResolvedValueOnce({
        data: new Blob(['zip']),
        headers: {
          'content-disposition': "attachment; filename*=UTF-8''rename.zip",
          'x-pdf-rename-file-count': '2',
        },
      })
    const api = createSharedToolsApi({ get, post })
    const files = [new File(['%PDF-a'], 'A.pdf'), new File(['%PDF-b'], 'B.pdf')]

    await api.getPdfRenameRules('huaxing')
    const overrides = [{ source_index: 1, target_file_name: '#11011-52136+52137.pdf', confirmed: true }]
    await api.previewPdfRename(files, 'fixed-region-a', 'huaxing', undefined, overrides)
    const result = await api.executePdfRename(files, 'fixed-region-a', 'preview-token', true, 'huaxing', undefined, overrides)

    expect(get).toHaveBeenCalledWith('/tools/pdf-rename/rules', { params: { factory_id: 'huaxing' }, signal: undefined })
    expect(post.mock.calls[0]?.[0]).toBe('/tools/pdf-rename/preview')
    expect((post.mock.calls[0]?.[1] as FormData).getAll('pdf_files')).toEqual(files)
    expect((post.mock.calls[0]?.[1] as FormData).get('factory_id')).toBe('huaxing')
    expect(JSON.parse(String((post.mock.calls[0]?.[1] as FormData).get('manual_overrides')))).toEqual(overrides)
    expect(post.mock.calls[1]?.[0]).toBe('/tools/pdf-rename/execute')
    expect((post.mock.calls[1]?.[1] as FormData).get('preview_token')).toBe('preview-token')
    expect((post.mock.calls[1]?.[1] as FormData).get('ocr_review_confirmed')).toBe('true')
    expect((post.mock.calls[1]?.[1] as FormData).get('factory_id')).toBe('huaxing')
    expect(JSON.parse(String((post.mock.calls[1]?.[1] as FormData).get('manual_overrides')))).toEqual(overrides)
    expect(result).toMatchObject({ fileName: 'rename.zip', fileCount: 2 })
  })

  it('exposes stable document error code and actionable advice', async () => {
    const post = vi.fn().mockRejectedValue({
      isAxiosError: true,
      message: 'Request failed',
      response: {
        status: 503,
        headers: { 'content-type': 'application/json' },
        data: new Blob([JSON.stringify({
          detail: {
            code: 'LIBREOFFICE_NOT_INSTALLED',
            message: '服务器未安装 LibreOffice。',
            action: '请管理员安装 LibreOffice。',
            retryable: false,
          },
        })], { type: 'application/json' }),
      },
    })
    const api = createSharedToolsApi({ post })

    await expect(api.convertWordToPdf(new File(['docx'], '订单.docx'))).rejects.toMatchObject({
      code: 'LIBREOFFICE_NOT_INSTALLED',
      action: '请管理员安装 LibreOffice。',
    })
  })
})
