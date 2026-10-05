import { describe, expect, it, vi } from 'vitest'
import type { InternalAxiosRequestConfig } from 'axios'
import { cartonFeedbackApi } from '../cartonFeedback'
import { http } from '@/lib/http'

describe('carton feedback HTTP contract', () => {
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
