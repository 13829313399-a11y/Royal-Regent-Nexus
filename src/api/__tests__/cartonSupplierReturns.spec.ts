import { beforeEach, expect, it, vi } from 'vitest'
import { http } from '@/lib/http'
import { cartonSupplierReturnsApi as api, type ReturnActionBody } from '../cartonSupplierReturns'

vi.mock('@/lib/http', () => ({ http: { get: vi.fn(), post: vi.fn() } }))
beforeEach(() => vi.resetAllMocks())
it.each([false, true])('uses the correct scoped list/detail/action prefix (internal=%s) with no evidence rewriting', async internal => {
  const prefix = internal ? '/carton-procurement' : '/carton-supplier', signal = new AbortController().signal
  const data = { items: [], total: 0 }
  vi.mocked(http.get).mockResolvedValue({ data }); vi.mocked(http.post).mockResolvedValue({ data: { movement_id: 'M/1' } })
  expect(await api.list('huaxing', internal, { status: 'PENDING', limit: 20, offset: 40, keyword: '合同1' }, signal)).toEqual(data)
  expect(http.get).toHaveBeenLastCalledWith(prefix + '/returns/workspace', { params: { factory_id: 'huaxing', status: 'PENDING', limit: 20, offset: 40, keyword: '合同1' }, signal })
  await api.detail('M/1', 'huaxing', internal, signal)
  expect(http.get).toHaveBeenLastCalledWith(prefix + '/returns/M%2F1', { params: { factory_id: 'huaxing' }, signal })
  const body: ReturnActionBody = { factory_id: 'huaxing', request_id: 'stable-request-1', expected_revision: 4, source_fingerprint: 'f'.repeat(64), action: 'CONFIRM_REFUND', target_event_id: 'REFUND-1', confirmation_reference: 'BANK-1', reason: '银行流水已核实到账' }
  await api.act('M/1', internal, body, signal)
  expect(http.post).toHaveBeenCalledWith(prefix + '/returns/M%2F1/actions', body, { signal })
})
