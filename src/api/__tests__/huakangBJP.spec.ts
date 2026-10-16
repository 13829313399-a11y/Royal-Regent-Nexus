import { describe, expect, it, vi } from 'vitest'
const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/lib/http', () => ({ http }))
import { huakangBJPApi as api } from '../huakangBJP'
describe('Huakang B JP API', () => {
  it('scopes reads/downloads and uses non-simple protection headers for multipart writes', async () => {
    http.get.mockResolvedValue({ data: {} }); http.post.mockResolvedValue({ data: {} })
    await api.references('huakang-b')
    const form = new FormData()
    await api.preview(form)
    await api.download('huakang-b', 'id/1')
    expect(http.get).toHaveBeenNthCalledWith(1, '/huakang-b-jp/references?factory_id=huakang-b', undefined)
    expect(http.post).toHaveBeenCalledWith('/huakang-b-jp/preview', form, { timeout: 270000, headers: { 'X-JP-Intake': '1' } })
    expect(http.get).toHaveBeenNthCalledWith(2, '/huakang-b-jp/exports/id%2F1/download?factory_id=huakang-b', { responseType: 'blob' })
  })
})
