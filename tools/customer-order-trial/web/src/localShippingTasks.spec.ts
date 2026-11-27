import { afterEach, expect, it, vi } from 'vitest'
import { listShippingTasks } from '@/api/shippingTasks'

afterEach(() => vi.unstubAllGlobals())

it('keeps the online-only shipping integration out of standalone requests', async () => {
  const request = vi.fn()
  vi.stubGlobal('fetch', request)
  await expect(listShippingTasks('huadeng', { q: 'example' })).rejects.toThrow('本机试用包未连接服务器船务排期')
  expect(request).not.toHaveBeenCalled()
})
