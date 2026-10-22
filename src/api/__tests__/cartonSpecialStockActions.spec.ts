import { describe, expect, it, vi } from 'vitest'
import { cartonSpecialStockActionsApi as api } from '../cartonSpecialStockActions'
const client = vi.hoisted(() => ({ get: vi.fn().mockResolvedValue({ data: {} }), post: vi.fn().mockResolvedValue({ data: {} }) }))
vi.mock('@/lib/http', () => ({ http: client }))

describe('SPECIAL stock action transport', () => {
  it('keeps the typed request identity, factory, selected receipt and bin on their own API', async () => {
    const signal = new AbortController().signal
    await api.preview('huaxing', 'SP/1', signal)
    expect(client.get).toHaveBeenCalledWith('/carton-special-requests/SP%2F1/stock-actions', { params: { factory_id: 'huaxing' }, signal })
    const body = { factory_id: 'huaxing', request_id: 'request-id-0000001', expected_revision: 3, source_fingerprint: 'basis', action: 'RETURN' as const, reason: '实际退回供应商', return_date: '2026-10-21', lines: [{ receipt_line_id: 'RL1', movement_id: 'M1', location_id: 'L1', quantity: '2' }] }
    await api.submit('SP/1', body, signal)
    expect(client.post).toHaveBeenCalledWith('/carton-special-requests/SP%2F1/stock-actions', body, { signal })
    const undo = { factory_id: 'huaxing', request_id: 'request-id-0000002', expected_revision: 4, reason: '未发货补单撤销' }
    await api.undo('SP/1', undo, signal)
    expect(client.post).toHaveBeenCalledWith('/carton-special-requests/SP%2F1/stock-actions/undo', undo, { signal })
  })
})
