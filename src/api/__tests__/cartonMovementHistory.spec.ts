import { beforeEach, describe, expect, it, vi } from 'vitest'
import { cartonMovementHistoryApi } from '../cartonMovementHistory'

const http = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/lib/http', () => ({ http }))

describe('carton movement history transport', () => {
  beforeEach(() => { http.get.mockResolvedValue({ data: { items: [], total: 0 } }) })
  it('omits empty date inputs so the typed API can load unfiltered and one-sided history', async () => {
    await cartonMovementHistoryApi.list({ factory_id: 'huaxing', date_from: '', date_to: '', offset: 0 })
    expect(http.get.mock.lastCall?.[1].params).toEqual({ factory_id: 'huaxing', date_from: undefined, date_to: undefined, offset: 0 })
    await cartonMovementHistoryApi.list({ factory_id: 'huaxing', date_from: '2026-10-01', date_to: '' })
    expect(http.get.mock.lastCall?.[1].params).toEqual({ factory_id: 'huaxing', date_from: '2026-10-01', date_to: undefined })
  })
  it('retains the inclusive date boundaries and server paging and search filters', async () => {
    const query = { factory_id: 'huaxing', customer_code: 'C1', customer_name: '同名客户', search: 'OLD', date_from: '2026-09-01', date_to: '2026-09-30', limit: 100, offset: 500 }
    await cartonMovementHistoryApi.list(query)
    expect(http.get.mock.lastCall?.[1].params).toEqual(query)
  })
})
