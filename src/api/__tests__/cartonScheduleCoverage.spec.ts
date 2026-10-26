import { beforeEach, expect, it, vi } from 'vitest'
import { http } from '@/lib/http'
import { cartonScheduleCoverageApi as api } from '../cartonScheduleCoverage'

vi.mock('@/lib/http', () => ({ http: { get: vi.fn(), post: vi.fn() } }))
beforeEach(() => { vi.resetAllMocks(); vi.mocked(http.get).mockResolvedValue({ data: {} }); vi.mocked(http.post).mockResolvedValue({ data: {} }) })
it('preserves factory/customer pagination, exact case identity and reasoned optimistic replay fields', async () => {
  const signal = new AbortController().signal
  await api.workspace('huaxing', { customer_code: 'DICKIE', status: 'ALL', keyword: 'SO0001', limit: 20, offset: 40 }, signal)
  expect(http.get).toHaveBeenLastCalledWith('/carton-procurement/schedule-coverage/workspace', { params: { factory_id: 'huaxing', customer_code: 'DICKIE', status: 'ALL', keyword: 'SO0001', limit: 20, offset: 40 }, signal })
  await api.detail('huaxing', 'M/1', signal)
  expect(http.get).toHaveBeenLastCalledWith('/carton-procurement/schedule-coverage/missing/M%2F1', { params: { factory_id: 'huaxing' }, signal })
  const body = { factory_id: 'huaxing', request_id: 'original-retry-id', expected_revision: 2, source_fingerprint: 'f'.repeat(64), decision: 'REOPEN' as const, reason: '原结论有误重新核实' }
  await api.review('M/1', body, signal)
  expect(http.post).toHaveBeenCalledWith('/carton-procurement/schedule-coverage/missing/M%2F1/review', body, { signal })
})
