import { describe, expect, it, vi } from 'vitest'
import type { InternalAxiosRequestConfig } from 'axios'
import { createCartonMarkApi, type CartonMarkAsset } from '@/api/cartonMark'
import { http } from '@/lib/http'

describe('carton-mark repository API', () => {
  it.each([false, true])('directly replaces three-kind associations with exact source revisions (supplier=%s)', async supplier => {
    const client = { put: vi.fn().mockResolvedValue({ data: { id: 'asset' } }) }
    const api = createCartonMarkApi(client as never), file = { id: 'asset', revision: 4 }
    const targets = [
      { order_kind: 'REGULAR' as const, order_id: 'regular', expected_revision: 2, issue_id: 'purchase-v2', line_id: '' },
      { order_kind: 'SAMPLE' as const, order_id: 'sample', expected_revision: 3, issue_id: 'sample-v3', line_id: '' },
      { order_kind: 'MISC' as const, order_id: 'misc', expected_revision: 5, issue_id: 'misc-v5', line_id: 'paper-2' },
    ]
    await api.associateAsset('huaxing', file, targets, 'request-123', supplier)
    expect(client.put).toHaveBeenLastCalledWith(`${supplier ? '/carton-supplier/carton-mark' : '/carton-mark'}/assets/asset/associations`, { revision: 4, request_id: 'request-123', targets }, { params: { factory_id: 'huaxing' }, signal: undefined })
    await api.associateAsset('huaxing', file, [], 'detach-123', supplier)
    expect(client.put.mock.calls[1]![1]).toEqual({ revision: 4, request_id: 'detach-123', targets: [] })
  })
  it('keeps sharing, supplier proposals and special paper binding as separate revisioned commands', async () => {
    const client = { get: vi.fn().mockResolvedValue({ data: [] }), post: vi.fn().mockResolvedValue({ data: {} }), put: vi.fn().mockResolvedValue({ data: {} }) }
    const api = createCartonMarkApi(client as never), file = { id: 'asset', revision: 4 }
    await api.setAssetSharing('huaxing', file, 'SUPPLIER', 'supplier-a')
    expect(client.put).toHaveBeenLastCalledWith('/carton-mark/assets/asset/sharing', { revision: 4, sharing_mode: 'SUPPLIER', supplier_id: 'supplier-a' }, { params: { factory_id: 'huaxing' }, signal: undefined })
    await api.proposeAssetBindings('huaxing', file, ['order'])
    expect(client.put).toHaveBeenLastCalledWith('/carton-supplier/carton-mark/assets/asset/binding', { revision: 4, order_ids: ['order'] }, { params: { factory_id: 'huaxing' }, signal: undefined })
    await api.bindSpecialAsset('huaxing', { order_id: 'sample', order_kind: 'SAMPLE', order_no: 'SP', contract_no: '', customer_name: '', item_no: 'I', revision: 2, lines: [] }, 'line', file, 'request', true)
    expect(client.post).toHaveBeenLastCalledWith('/carton-supplier/special-requests/sample/lines/line/mark', { factory_id: 'huaxing', expected_revision: 2, request_id: 'request', mark_mode: 'EXISTING', asset_id: 'asset', asset_revision: 4 }, { signal: undefined })
  })
  it('sends file classification and original revision with upload and status changes', async () => {
    const client = { post: vi.fn().mockResolvedValue({ data: [] }), put: vi.fn().mockResolvedValue({ data: {} }) }
    const api = createCartonMarkApi(client as never)
    const options = [{ status: 'PENDING' as const, note: '修改稿', previous_asset_id: 'original', previous_revision: 4 }]
    await api.uploadAssets('huaxing', [new File(['pdf'], '新版.pdf')], undefined, options)
    expect(JSON.parse((client.post.mock.calls[0]![1] as FormData).get('options_json') as string)).toEqual(options)
    await api.classifyAsset('huaxing', { id: 'new', revision: 1 } as CartonMarkAsset, 'READY', '已确认')
    expect(client.put).toHaveBeenCalledWith('/carton-mark/assets/new/classification', { status: 'READY', note: '已确认', revision: 1 }, { params: { factory_id: 'huaxing' }, signal: undefined })
  })
  it('sends complete member revisions for group creation, binding and dissolving', async () => {
    const client = { get: vi.fn().mockResolvedValue({ data: [] }), post: vi.fn().mockResolvedValue({ data: [] }), put: vi.fn().mockResolvedValue({ data: [] }) }
    const api = createCartonMarkApi(client as never)
    const photos = [{ id: 'photo-a', revision: 2 }, { id: 'photo-b', revision: 3 }] as CartonMarkAsset[]
    const signal = new AbortController().signal
    await api.bindingOrders('huaxing', signal)
    expect(client.get).toHaveBeenCalledWith('/carton-mark/assets/binding-orders', { params: { factory_id: 'huaxing' }, signal })
    await api.savePhotoGroup('huaxing', photos, '', '', undefined, signal)
    expect(client.post).toHaveBeenCalledWith('/carton-mark/assets/photo-groups', { assets: photos, contract_number: '', order_id: null }, { params: { factory_id: 'huaxing' }, signal })
    await api.savePhotoGroup('huaxing', photos, '4500222793', 'order-a', 'group-a', signal)
    expect(client.put).toHaveBeenCalledWith('/carton-mark/assets/photo-groups/group-a/binding', { assets: photos, contract_number: '4500222793', order_id: 'order-a' }, { params: { factory_id: 'huaxing' }, signal })
    await api.ungroupPhotos('huaxing', 'group-a', photos, signal)
    expect(client.post).toHaveBeenLastCalledWith('/carton-mark/assets/photo-groups/group-a/ungroup', { assets: photos }, { params: { factory_id: 'huaxing' }, signal })
  })
  it('keeps factory and document fields as multipart through the shared Axios request pipeline', async () => {
    const files = [new File(['pdf'], '4500222793.pdf'), new File(['excel'], '4500222793_Shipping Mark.xlsx'),
      new File(['photo'], '4500222793_正唛.jpg', { type: 'image/jpeg' })]
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
