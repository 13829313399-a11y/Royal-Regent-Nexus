import { describe, expect, it, vi } from 'vitest'
import { createPdfRenameApi, PDF_BATCH_RENAME_TIMEOUT_MS } from '@/api/pdfRename'

describe('Huaxing PDF rename API', () => {
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
    const api = createPdfRenameApi({ get, post })
    const files = [new File(['%PDF-a'], 'A.pdf'), new File(['%PDF-b'], 'B.pdf')]

    const signal = new AbortController().signal
    await api.getPdfRenameRules('huaxing', signal)
    const overrides = [{ source_index: 1, target_file_name: '#11011-52136+52137.pdf', confirmed: true }]
    await api.previewPdfRename(files, 'fixed-region-a', 'huaxing', signal, overrides)
    const result = await api.executePdfRename(files, 'fixed-region-a', 'preview-token', true, 'huaxing', signal, overrides)

    expect(get).toHaveBeenCalledWith('/tools/pdf-rename/rules', { params: { factory_id: 'huaxing' }, signal })
    expect(post.mock.calls[0]?.[0]).toBe('/tools/pdf-rename/preview')
    expect((post.mock.calls[0]?.[1] as FormData).getAll('pdf_files')).toEqual(files)
    expect((post.mock.calls[0]?.[1] as FormData).get('factory_id')).toBe('huaxing')
    expect(JSON.parse(String((post.mock.calls[0]?.[1] as FormData).get('manual_overrides')))).toEqual(overrides)
    expect(post.mock.calls[1]?.[0]).toBe('/tools/pdf-rename/execute')
    expect((post.mock.calls[1]?.[1] as FormData).get('preview_token')).toBe('preview-token')
    expect((post.mock.calls[1]?.[1] as FormData).get('ocr_review_confirmed')).toBe('true')
    expect((post.mock.calls[1]?.[1] as FormData).get('factory_id')).toBe('huaxing')
    expect(JSON.parse(String((post.mock.calls[1]?.[1] as FormData).get('manual_overrides')))).toEqual(overrides)
    for (const call of post.mock.calls) {
      expect(call[2]).toMatchObject({ timeout: PDF_BATCH_RENAME_TIMEOUT_MS, signal })
    }
    expect(result).toMatchObject({ fileName: 'rename.zip', fileCount: 2 })
  })


  it.each(['catalog', 'preview', 'execute'] as const)('preserves structured %s error details', async (operation) => {
    const detail = { code: 'PDF_RENAME_RULE_FACTORY_MISMATCH', message: '仅华兴可用。', action: '请选择华兴。', retryable: false }
    const responseData = operation === 'execute' ? new Blob([JSON.stringify({ detail })], { type: 'application/json' }) : { detail }
    const fail = { isAxiosError: true, message: 'Request failed', response: { status: 403, data: responseData, headers: {} } }
    const api = createPdfRenameApi({ get: vi.fn().mockRejectedValue(fail), post: vi.fn().mockRejectedValue(fail) })
    const request = operation === 'catalog' ? api.getPdfRenameRules('huadeng')
      : operation === 'preview' ? api.previewPdfRename([], 'buzzbee-inspection', 'huadeng')
      : api.executePdfRename([], 'buzzbee-inspection', 'token', true, 'huadeng')
    await expect(request).rejects.toMatchObject(detail)
  })

  it.each(['catalog', 'preview', 'execute'] as const)('keeps %s cancellation distinct from OCR failure', async (operation) => {
    const fail = { __CANCEL__: true }
    const api = createPdfRenameApi({ get: vi.fn().mockRejectedValue(fail), post: vi.fn().mockRejectedValue(fail) })
    const request = operation === 'catalog' ? api.getPdfRenameRules('huaxing')
      : operation === 'preview' ? api.previewPdfRename([], 'buzzbee-inspection', 'huaxing')
      : api.executePdfRename([], 'buzzbee-inspection', 'token', true, 'huaxing')
    await expect(request).rejects.toMatchObject({ code: 'DOCUMENT_REQUEST_CANCELLED' })
  })

  it('does not expose an HTML gateway response as the download error', async () => {
    const api = createPdfRenameApi({ post: vi.fn().mockRejectedValue({
      isAxiosError: true, message: 'Request failed',
      response: { status: 504, headers: { 'content-type': 'text/html' }, data: new Blob(['<html>upstream timeout</html>']) },
    }) })
    await expect(api.executePdfRename([], 'buzzbee-inspection', 'token', true, 'huaxing')).rejects.toThrow('最长 15 分钟')
  })
})
