import { describe, expect, it, vi } from 'vitest'
import { readAllPages } from '../transport/pagination'
import type { UvScope } from '../contracts'

describe('UV 全量分页读取', () => {
  it('聚合和下拉选项跨过首 200 条继续读取，且保留同一筛选作用域', async () => {
    const reader = vi.fn(async (scope: UvScope) => ({
      meta: { factory_id: 'huakang-a' as const, as_of: '2026-09-13T00:00:00Z', data_mode: 'live' as const, coverage: 'complete' as const, warnings: [] },
      data: {
        items: scope.page === 1 ? Array.from({ length: 200 }, (_, index) => index) : [200, 201],
        total: 202,
        page: scope.page ?? 1,
        page_size: scope.page_size ?? 200,
      },
    }))
    const response = await readAllPages(reader, { factory_id: 'huakang-a', q: 'A-001', date_from: '2026-09-01' })
    expect(response.data.items).toHaveLength(202)
    expect(reader).toHaveBeenCalledTimes(2)
    expect(reader.mock.calls[1]?.[0]).toMatchObject({ page: 2, page_size: 200, q: 'A-001', date_from: '2026-09-01' })
  })
})
