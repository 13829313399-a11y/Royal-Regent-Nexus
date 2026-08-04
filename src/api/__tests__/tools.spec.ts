import { describe, expect, it, vi } from 'vitest'
import { createSharedToolsApi, PDF_TO_EXCEL_TIMEOUT_MS } from '@/api/tools'


describe('shared tools api', () => {
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
})
