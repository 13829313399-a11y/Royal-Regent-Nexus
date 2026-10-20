import { afterEach, describe, expect, it, vi } from 'vitest'
import { collaborativeSheetsApi as api, COLLABORATIVE_SHEET_MAX_FILE_BYTES } from '@/api/collaborativeSheets'
import { http } from '@/lib/http'

afterEach(() => vi.restoreAllMocks())

describe('collaborative sheet upload size', () => {
  it('carries cancellation and request correlation through the blob transport', async () => {
    const blob = new Blob(['xlsx']), controller = new AbortController(), response = vi.fn()
    const get = vi.spyOn(http, 'get').mockResolvedValue({ data: blob, headers: { 'x-request-id': 'opaque-id', 'server-timing': 'app;dur=12', 'x-workbook-revision': '9' } })
    expect(await api.download('huaxing', { id: 'task' }, undefined, { signal: controller.signal, requestId: 'opaque-id', onResponse: response })).toBe(blob)
    expect(get).toHaveBeenCalledWith('/tools/collaborative-sheets/task/download', expect.objectContaining({ signal: controller.signal, timeout: 300_000, responseType: 'blob', headers: { 'X-Request-ID': 'opaque-id' } }))
    expect(response).toHaveBeenCalledWith({ bytes: blob.size, requestId: 'opaque-id', serverTiming: 'app;dur=12', revision: '9' })
  })
  it('rejects files over 100 MiB without sending a request', async () => {
    const post = vi.spyOn(http, 'post').mockResolvedValue({ data: {} })
    const file = new File(['sample'], 'large.xlsx')
    Object.defineProperty(file, 'size', { value: 100 * 1024 * 1024 + 1 })
    await expect(api.create('huaxing', 'Large workbook', file)).rejects.toThrow('工作簿不能超过 100 MB')
    expect(post).not.toHaveBeenCalled()
  })

  it('accepts the 100 MiB boundary and gives only uploads a longer timeout', async () => {
    const post = vi.spyOn(http, 'post').mockResolvedValue({ data: {} })
    const get = vi.spyOn(http, 'get').mockResolvedValue({ data: { items: [] } })
    const file = new File(['sample'], 'large.xlsx')
    Object.defineProperty(file, 'size', { value: 100 * 1024 * 1024 })
    expect(COLLABORATIVE_SHEET_MAX_FILE_BYTES).toBe(file.size)
    await api.create('huaxing', 'Large workbook', file)
    expect(post).toHaveBeenCalledWith('/tools/collaborative-sheets', expect.any(FormData), expect.objectContaining({ timeout: 300_000 }))
    const body = post.mock.calls[0]![1] as FormData
    expect(body.get('factory_id')).toBe('huaxing')
    expect(body.get('file')).toBe(file)
    await api.list('huaxing')
    expect(get).toHaveBeenCalledWith('/tools/collaborative-sheets', expect.objectContaining({ timeout: 120_000 }))
  })
})
