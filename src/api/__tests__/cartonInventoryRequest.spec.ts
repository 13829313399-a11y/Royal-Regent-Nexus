import { beforeEach, describe, expect, it, vi } from 'vitest'

const post = vi.hoisted(() => vi.fn())
vi.mock('@/lib/http', () => ({ http: { post } }))
const url = '/carton-procurement/inventory/movements'
const payload = { factory_id: 'huaxing', order_line_id: 'line-a', quantity: 2, document_no: 'OUT' }

describe('carton inventory submission recovery', () => {
  beforeEach(() => {
    vi.resetModules()
    post.mockReset()
    sessionStorage.clear()
  })

  it('shares concurrent submissions and reuses the same ID after timeout', async () => {
    const { postCartonInventoryRequest } = await import('../cartonInventoryRequest')
    let reject!: (error: Error) => void
    post.mockImplementationOnce(() => new Promise((_, fail) => { reject = fail }))
    const first = postCartonInventoryRequest(url, payload)
    const simultaneous = postCartonInventoryRequest(url, payload)
    expect(first).toBe(simultaneous)
    expect(post).toHaveBeenCalledTimes(1)
    const firstId = post.mock.calls[0]?.[1].request_id
    reject(new Error('network timeout'))
    await expect(first).rejects.toThrow('network timeout')
    post.mockResolvedValueOnce({ data: { id: 'movement-one' } })
    await expect(postCartonInventoryRequest(url, payload)).resolves.toEqual({ id: 'movement-one' })
    expect(post.mock.calls[1]?.[1].request_id).toBe(firstId)
    expect(sessionStorage.length).toBe(0)
    // An intentional later operation with the same document and amount remains allowed.
    post.mockResolvedValueOnce({ data: { id: 'movement-two' } })
    await postCartonInventoryRequest(url, payload)
    expect(post.mock.calls[2]?.[1].request_id).not.toBe(firstId)
  })

  it('recovers unresolved IDs after a page/module reload and keeps factories separate', async () => {
    let api = await import('../cartonInventoryRequest')
    post.mockRejectedValueOnce(new Error('lost response'))
    await expect(api.postCartonInventoryRequest(url, payload)).rejects.toThrow('lost response')
    const firstId = post.mock.calls[0]?.[1].request_id
    vi.resetModules()
    api = await import('../cartonInventoryRequest')
    post.mockResolvedValueOnce({ data: {} })
    await api.postCartonInventoryRequest(url, { ...payload, factory_id: 'huakang_a' })
    expect(post.mock.calls[1]?.[1].request_id).not.toBe(firstId)
    post.mockResolvedValueOnce({ data: {} })
    await api.postCartonInventoryRequest(url, { document_no: 'OUT', quantity: 2, order_line_id: 'line-a', factory_id: 'huaxing' })
    expect(post.mock.calls[2]?.[1].request_id).toBe(firstId)
  })
})
