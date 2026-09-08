import { beforeEach, describe, expect, it, vi } from 'vitest'
import { cartonProcurementApi } from '../cartonProcurement'
const get = vi.hoisted(() => vi.fn())
const post = vi.hoisted(() => vi.fn())
vi.mock('@/lib/http', () => ({ http: { get, post } }))

describe('carton history pagination', () => {
  beforeEach(() => get.mockReset())
  it.each(['listOrders', 'listReceipts'] as const)('loads %s beyond the first 200 records', async (method) => {
    const first = Array.from({ length: 200 }, (_, index) => ({ id: `row-${index}` }))
    get.mockResolvedValueOnce({ data: { items: first, total: 201 } })
      .mockResolvedValueOnce({ data: { items: [{ id: 'old-record' }], total: 201 } })
    const result = await cartonProcurementApi[method]('huaxing')
    expect(result).toHaveLength(201)
    expect(result[200]?.id).toBe('old-record')
    expect(get.mock.calls[1]?.[1].params).toMatchObject({ factory_id: 'huaxing', offset: 200 })
  })
})

it('retries direct receipt posting with the same request identity after a lost response', async () => {
  post.mockReset()
  const payload = { factory_id: 'huaxing', post_immediately: true, delivery_note_no: 'DN-RETRY',
    delivery_date: '2026-09-08', import_batch_id: null, note: '', lines: [] }
  post.mockRejectedValueOnce(new Error('lost response'))
  await expect(cartonProcurementApi.createReceipt(payload)).rejects.toThrow('lost response')
  const requestId = post.mock.calls[0]?.[1].request_id
  expect(requestId).toBeTruthy()
  post.mockResolvedValueOnce({ data: { id: 'R-POSTED', status: 'POSTED' } })
  expect(await cartonProcurementApi.createReceipt(payload)).toMatchObject({ status: 'POSTED' })
  expect(post.mock.calls[1]).toEqual(['/carton-procurement/receipts', { ...payload, request_id: requestId }])
})
