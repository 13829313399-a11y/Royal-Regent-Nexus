import { describe, expect, it, vi } from 'vitest'
import { createCartonQuickAssetsApi, type QuickUploadBody } from '../cartonQuickAssets'
import { quickAsset } from '@/components/__tests__/cartonQuickAssetFixtures'

describe('quick upload existing backend transport', () => {
  it('sends the chosen department, explicit empty contract and exact request in multipart', async () => {
    const post = vi.fn().mockResolvedValue({ data: quickAsset() }), client = { post }
    const api = createCartonQuickAssetsApi(client as never), file = new File(['合同号在正文中'], 'photo.png')
    const body: QuickUploadBody = { request_id: 'same-request', owner_department: 'sales-business', text: '', contract_number: '', association: 'NONE', status: 'PENDING' }
    await api.upload('huaxing', body, file)
    const form = post.mock.calls[0]![1] as FormData
    expect(JSON.parse(String(form.get('metadata')))).toEqual(body)
    expect(form.get('file')).toBe(file)
    expect(post.mock.calls[0]![0]).toBe('/carton-mark/assets/quick')
    expect(post.mock.calls[0]![2]).toMatchObject({ params: { factory_id: 'huaxing' }, headers: { 'Content-Type': 'multipart/form-data' } })
  })
  it('accepts same-factory cross-department documents but rejects an unshared foreign factory', async () => {
    const get = vi.fn().mockResolvedValue({ data: { items: [quickAsset({ owner_department: 'pmc-warehouse' })], total: 1 } })
    const api = createCartonQuickAssetsApi({ get } as never)
    expect((await api.list('huaxing', 'sales-business')).items).toHaveLength(1)
    get.mockResolvedValue({ data: { items: [quickAsset({ factory_id: 'huakang-a' })], total: 1 } })
    await expect(api.list('huaxing', 'sales-business')).rejects.toThrow('厂区')
  })
  it('uses the quick confirmation and supplier document routes, without contract-module calls', async () => {
    const post = vi.fn().mockResolvedValue({ data: quickAsset() }), get = vi.fn().mockResolvedValue({ data: new Blob(['text']) })
    const api = createCartonQuickAssetsApi({ post, get } as never)
    await api.confirm('huaxing', quickAsset(), 'confirmation-id')
    expect(post).toHaveBeenCalledWith('/carton-mark/assets/quick/asset-one/classification', { revision: 1, request_id: 'confirmation-id', status: 'READY' }, expect.anything())
    await api.document('huaxing', 'asset-one', true)
    expect(get).toHaveBeenCalledWith('/carton-mark/assets/quick/asset-one/document', expect.objectContaining({ params: { factory_id: 'huaxing', supplier_view: true } }))
  })
})
