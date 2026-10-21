import { expect, it, vi } from 'vitest'
import { supplierSettlementApi as api } from '../cartonSupplierSettlement'
import { http } from '@/lib/http'

vi.mock('@/lib/http', () => ({ http: { post: vi.fn() } }))

it('preserves the exact evidence revision, idempotency key and abort signal for date correction', async () => {
  const body = { factory_id: 'huaxing', request_id: 'retry-stable-request', expected_evidence_revision: 2,
    expected_evidence_fingerprint: 'a'.repeat(64), return_date: '2026-09-30', reason: '已核对原始交接凭证' }
  const result = { movement_id: 'M/1', return_date: body.return_date, posting_date: '2026-10-01', date_basis: 'RETURN_ACTUAL' }
  const signal = new AbortController().signal
  vi.mocked(http.post).mockResolvedValue({ data: result })
  expect(await api.correctReturnDate('M/1', body, signal)).toEqual(result)
  expect(http.post).toHaveBeenCalledWith('/carton-procurement/inventory/movements/M%2F1/return-date/corrections', body, { signal })
})
