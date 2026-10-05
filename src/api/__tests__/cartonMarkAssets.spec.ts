import { describe, expect, it, vi } from 'vitest'
import type { InternalAxiosRequestConfig } from 'axios'
import { createCartonMarkApi } from '@/api/cartonMark'
import { http } from '@/lib/http'

describe('carton-mark repository API', () => {
  it('keeps factory and document fields as multipart through the shared Axios request pipeline', async () => {
    const files = [new File(['pdf'], '4500222793.pdf'), new File(['excel'], '4500222793_Shipping Mark.xlsx')]
    const transport = vi.fn(async (config: InternalAxiosRequestConfig) => {
      expect(config.data).toBeInstanceOf(FormData)
      expect(config.data.get('factory_id')).toBe('huaxing')
      expect(config.data.getAll('files')).toEqual(files)
      expect(config.headers.get('Content-Type')).toBe('multipart/form-data')
      return { data: [], status: 200, statusText: 'OK', headers: {}, config }
    })
    const interceptor = http.interceptors.request.use(config => {
      if (config.url === '/carton-mark/assets/batch') config.adapter = transport
      return config
    })
    try {
      await createCartonMarkApi().uploadAssets('huaxing', files)
      expect(transport).toHaveBeenCalledOnce()
    } finally {
      http.interceptors.request.eject(interceptor)
    }
  })
  it('passes factory and order scope and uses repeated multipart fields for batch upload', async () => {
    const client = { get: vi.fn().mockResolvedValue({ data: [] }), post: vi.fn().mockResolvedValue({ data: [] }) }
    const api = createCartonMarkApi(client as never)
    await api.listAssets('huaxing', 'order-a')
    expect(client.get).toHaveBeenCalledWith('/carton-mark/assets', { params: { factory_id: 'huaxing', order_id: 'order-a' }, signal: undefined })
    const files = [new File(['x'], 'contract.xlsx'), new File(['p'], 'print.pdf')]
    await api.uploadAssets('huaxing', files)
    const form = client.post.mock.calls[0]![1] as FormData
    expect(form.get('factory_id')).toBe('huaxing')
    expect(form.getAll('files')).toEqual(files)
  })
  it('submits saved source IDs without uploading the same document bytes again', async () => {
    const client = { post: vi.fn().mockResolvedValue({ data: {} }) }
    const api = createCartonMarkApi(client as never)
    await api.createTemplate({ factoryId: 'huaxing', customerName: 'ZURU', item: '100369', contractNumber: '4500222793',
      excelContract: new Blob(['x']), printPdf: new Blob(['p']), excelAssetId: 'excel-a', pdfAssetId: 'pdf-a' })
    const form = client.post.mock.calls[0]![1] as FormData
    expect(form.get('excel_asset_id')).toBe('excel-a')
    expect(form.get('pdf_asset_id')).toBe('pdf-a')
    expect(form.has('excel_contract')).toBe(false)
    expect(form.has('print_pdf')).toBe(false)
  })
})
