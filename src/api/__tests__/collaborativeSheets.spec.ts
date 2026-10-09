import { afterEach, describe, expect, it, vi } from 'vitest'
import { collaborativeSheetsApi as api, COLLABORATIVE_SHEET_MAX_FILE_BYTES } from '@/api/collaborativeSheets'
import { http } from '@/lib/http'

afterEach(() => vi.restoreAllMocks())

describe('collaborative sheet upload size', () => {
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
