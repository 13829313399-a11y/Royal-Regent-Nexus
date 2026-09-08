import { beforeEach, describe, expect, it, vi } from 'vitest'
import { cartonProcurementApi } from '../cartonProcurement'
const get = vi.hoisted(() => vi.fn())
vi.mock('@/lib/http', () => ({ http: { get } }))

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
