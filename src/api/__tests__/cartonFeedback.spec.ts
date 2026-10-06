import { describe, expect, it, vi } from 'vitest'
import type { InternalAxiosRequestConfig } from 'axios'
import { cartonFeedbackApi } from '../cartonFeedback'
import { http } from '@/lib/http'

describe('carton feedback HTTP contract', () => {
  it('sends the supplier context for private reads and uploads, and a publication audience', async () => {
    const get = vi.spyOn(http, 'get').mockResolvedValue({ data: {} })
    const post = vi.spyOn(http, 'post').mockResolvedValue({ data: {} })
    try {
      await cartonFeedbackApi.detail('huaxing', 'id', undefined, 'supplier')
      await cartonFeedbackApi.image('huaxing', 'id', 'img', undefined, 'supplier')
      expect(get.mock.calls.every(call => call[1]?.params.portal === 'supplier')).toBe(true)
      await cartonFeedbackApi.create('huaxing', '标题', '说明', '/carton-supplier', 'key', [], undefined, 'supplier')
      expect((post.mock.calls[0]![1] as FormData).get('portal')).toBe('supplier')
      await cartonFeedbackApi.publish('huaxing', '更新', '内容', 'pub', undefined, 'SUPPLIER')
      expect(post.mock.calls[1]![1]).toMatchObject({ audience: 'SUPPLIER' })
    } finally { get.mockRestore(); post.mockRestore() }
  })
  it('preserves factory, idempotency and repeated screenshot fields through the real Axios pipeline', async () => {
    const files = [new File(['image'], 'one.png'), new File(['image2'], 'two.png')]
    const transport = vi.fn(async (config: InternalAxiosRequestConfig) => {
      expect(config.data).toBeInstanceOf(FormData)
      expect(config.data.get('factory_id')).toBe('huaxing')
      expect(config.data.get('request_key')).toBe('retry-key')
      expect(config.data.getAll('files')).toEqual(files)
      expect(config.headers.get('Content-Type')).toBe('multipart/form-data')
      return { data: {}, status: 200, statusText: 'OK', headers: {}, config }
    })
    const interceptor = http.interceptors.request.use(config => { if (config.url === '/carton-feedback') config.adapter = transport; return config })
    try { await cartonFeedbackApi.create('huaxing', '问题', '说明', '/module', 'retry-key', files); expect(transport).toHaveBeenCalledOnce() }
    finally { http.interceptors.request.eject(interceptor) }
  })
})
