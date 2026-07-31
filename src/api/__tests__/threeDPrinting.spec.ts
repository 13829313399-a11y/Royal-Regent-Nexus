import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get, post, put, deleteRequest } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  deleteRequest: vi.fn(),
}))

vi.mock('@/lib/http', () => ({
  http: {
    get,
    post,
    put,
    delete: deleteRequest,
  },
}))

import { threeDPrintingApi } from '@/api/threeDPrinting'

describe('threeDPrintingApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('locks dashboard and export reads to Huakang A', async () => {
    get
      .mockResolvedValueOnce({ data: { factory_id: 'huakang-a' } })
      .mockResolvedValueOnce({ data: new Blob(['xlsx']) })

    await threeDPrintingApi.dashboard('2026-07-01', '2026-07-29')
    await threeDPrintingApi.exportWorkbook()

    expect(get).toHaveBeenNthCalledWith(
      1,
      '/three-d-printing/dashboard',
      {
        params: {
          factory_id: 'huakang-a',
          date_from: '2026-07-01',
          date_to: '2026-07-29',
        },
      },
    )
    expect(get).toHaveBeenNthCalledWith(
      2,
      '/three-d-printing/export.xlsx',
      expect.objectContaining({
        params: { factory_id: 'huakang-a' },
        responseType: 'blob',
      }),
    )
  })

  it('uploads an image as multipart data and waits for the saved product response', async () => {
    const saved = { id: 'product-1', image_url: '/saved.jpg' }
    post.mockResolvedValueOnce({ data: saved })
    const file = new File(['jpeg'], 'product.jpg', { type: 'image/jpeg' })

    await expect(threeDPrintingApi.uploadProductImage('product-1', file)).resolves.toEqual(saved)

    expect(post).toHaveBeenCalledWith(
      '/three-d-printing/products/product-1/image',
      expect.any(FormData),
      expect.objectContaining({
        params: { factory_id: 'huakang-a' },
        headers: { 'Content-Type': 'multipart/form-data' },
      }),
    )
    const form = post.mock.calls[0]?.[1] as FormData
    expect(form.get('file')).toBe(file)
  })

  it('creates only pause or resume commands with Huakang A scope and idempotency', async () => {
    post.mockResolvedValueOnce({ data: { id: 'command-1' } })
    const printer = { id: 'printer-1' } as Parameters<typeof threeDPrintingApi.command>[0]

    await threeDPrintingApi.command(printer, 'pause', '现场异常')

    expect(post).toHaveBeenCalledWith(
      '/three-d-printing/printers/printer-1/commands',
      expect.objectContaining({
        factory_id: 'huakang-a',
        action: 'pause',
        reason: '现场异常',
        idempotency_key: expect.stringMatching(/^pause-printer-1-\d+$/),
      }),
    )
  })
})
