import { describe, expect, it, vi } from 'vitest'
const get = vi.hoisted(() => vi.fn())
vi.mock('@/lib/http', () => ({ http: { get } }))
import { cartonProcurementApi } from '../cartonProcurement'

describe('exception history completeness', () => {
  it('includes an old stocktake exception after a full page of newer unrelated exceptions', async () => {
    const recent = Array.from({ length: 500 }, (_, i) => ({ id: `recent-${i}`, category: 'MISSING_ORDER' }))
    const old = { id: 'old-count', category: 'STOCKTAKE_REVIEW', created_at: '2026-08-01' }
    get.mockResolvedValueOnce({ data: { items: recent, total: 501 } })
      .mockResolvedValueOnce({ data: { items: [old], total: 501 } })
    const result = await cartonProcurementApi.listExceptions('huaxing')
    expect(result).toHaveLength(501)
    expect(result.at(-1)).toEqual(old)
    expect(get).toHaveBeenLastCalledWith('/carton-procurement/exceptions', { params: { factory_id: 'huaxing', limit: 500, offset: 500 } })
  })
})
