import { beforeEach, expect, it, vi } from 'vitest'
const transport = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/lib/http', () => ({ http: transport }))
const body = { factory_id: 'huaxing', expected_revision: 2, source_fingerprint: 's'.repeat(64), action: 'FINAL_CONFIRM' as const, impact_fingerprint: 'i'.repeat(64), reason: '核对最新成本影响' }
beforeEach(() => { vi.resetModules(); vi.resetAllMocks(); sessionStorage.clear() })
it('uses the exact internal and supplier endpoints with encoded receipt-line identity and separate preview evidence', async () => {
  const { cartonPriceCorrectionsApi: api } = await import('../cartonPriceCorrections'), signal = new AbortController().signal
  transport.get.mockResolvedValue({ data: { receipt_line_id: 'ok' } }); transport.post.mockResolvedValue({ data: {} })
  const query = { factory_id: 'huaxing', status: 'ALL' as const, keyword: '送货', limit: 25, offset: 50 }
  await api.workspace(true, query, signal); expect(transport.get).toHaveBeenLastCalledWith('/carton-procurement/price-corrections/workspace', { params: query, signal })
  await api.detail(false, 'line/a', 'huaxing', signal); expect(transport.get).toHaveBeenLastCalledWith('/carton-supplier/price-corrections/line%2Fa', { params: { factory_id: 'huaxing' }, signal })
  const preview = { factory_id: 'huaxing', expected_revision: 2, source_fingerprint: body.source_fingerprint }
  await api.preview('line/a', preview, signal); expect(transport.post).toHaveBeenLastCalledWith('/carton-procurement/price-corrections/line%2Fa/preview', preview, { signal })
  await api.act(false, 'line/a', { ...body, action: 'SUPPLIER_CONFIRM' }, 'supplier:1', signal); expect(transport.post).toHaveBeenLastCalledWith('/carton-supplier/price-corrections/line%2Fa/actions', expect.objectContaining({ action: 'SUPPLIER_CONFIRM', expected_revision: 2 }), { signal })
})
it('shares one in-flight request and restores the entire uncertain original payload after reload', async () => {
  let module = await import('../cartonPriceCorrections'), reject!: (cause: Error) => void
  transport.post.mockImplementationOnce(() => new Promise((_, fail) => { reject = fail }))
  const first = module.cartonPriceCorrectionsApi.act(true, 'LINE1', body, 'actor1'), same = module.cartonPriceCorrectionsApi.act(true, 'LINE1', { ...body }, 'actor1')
  expect(first).toBe(same); expect(transport.post).toHaveBeenCalledTimes(1)
  const original = transport.post.mock.calls[0]![1]
  reject(new Error('结果不明')); await expect(first).rejects.toThrow('结果不明')
  await expect(module.cartonPriceCorrectionsApi.act(true, 'LINE2', body, 'actor1')).rejects.toThrow('原更正请求')
  await expect(module.cartonPriceCorrectionsApi.act(true, 'LINE1', { ...body, expected_revision: 3 }, 'actor1')).rejects.toThrow('原更正请求')
  vi.resetModules(); module = await import('../cartonPriceCorrections')
  expect(module.pendingPriceCorrection(true, 'huaxing', 'actor1')).toEqual({ receipt_line_id: 'LINE1', body: original })
  transport.post.mockResolvedValue({ data: { revision: 3 } }); await module.cartonPriceCorrectionsApi.act(true, 'LINE1', body, 'actor1')
  expect(transport.post.mock.calls[1]![1]).toEqual(original); expect(module.pendingPriceCorrection(true, 'huaxing', 'actor1')).toBeNull()
})
it('isolates actor/factory/mode and clears definitive rejection while retaining 5xx, including HTTP UUID fallback', async () => {
  const descriptor = Object.getOwnPropertyDescriptor(crypto, 'randomUUID'); Object.defineProperty(crypto, 'randomUUID', { configurable: true, value: undefined })
  try {
    const { cartonPriceCorrectionsApi: api, pendingPriceCorrection: pending } = await import('../cartonPriceCorrections')
    transport.post.mockRejectedValueOnce({ response: { status: 503 } }); await expect(api.act(true, 'LINE1', body, 'actor1')).rejects.toMatchObject({ response: { status: 503 } })
    const old = pending(true, 'huaxing', 'actor1')!.body.request_id; expect(old).toMatch(/^[\w-]{8,96}$/)
    expect(pending(true, 'huaxing', 'actor2')).toBeNull(); expect(pending(false, 'huaxing', 'actor1')).toBeNull(); expect(pending(true, 'huadeng', 'actor1')).toBeNull()
    transport.post.mockRejectedValueOnce({ response: { status: 409 } }); await expect(api.act(true, 'LINE1', body, 'actor1')).rejects.toMatchObject({ response: { status: 409 } }); expect(transport.post.mock.calls[1]![1].request_id).toBe(old); expect(pending(true, 'huaxing', 'actor1')).toBeNull()
    transport.post.mockResolvedValue({ data: {} }); await api.act(true, 'LINE1', { ...body, impact_fingerprint: 'new' }, 'actor1'); expect(transport.post.mock.calls[2]![1].request_id).not.toBe(old)
  } finally { if (descriptor) Object.defineProperty(crypto, 'randomUUID', descriptor) }
})
