import { beforeEach, expect, it, vi } from 'vitest'
const transport = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/lib/http', () => ({ http: transport }))
const body = { factory_id: 'huaxing', supplier_id: 'SUP1', currency: 'CNY', expected_revision: 7, source_fingerprint: 'f'.repeat(64), action: 'RECORD_PAYMENT' as const, payment_date: '2026-10-15', amount: '12.30', document_no: 'BANK1', bank_reference: 'OUT1', reason: '核实真实付款流水' }
beforeEach(() => { vi.resetModules(); vi.resetAllMocks(); sessionStorage.clear() })
it('uses the exact internal/supplier URLs, current account query, encoded record ID and complete CSV scope', async () => {
  const { cartonPayablesApi: api } = await import('../cartonPayables'), signal = new AbortController().signal
  transport.get.mockResolvedValue({ data: { id: 'ok' } })
  const query = { factory_id: 'huaxing', currency: 'CNY', kind: 'ALL' as const, status: 'PENDING' as const, keyword: '银行单据', limit: 25, offset: 50 }
  await api.workspace(true, query, signal); expect(transport.get).toHaveBeenLastCalledWith('/carton-procurement/payables/workspace', { params: query, signal })
  await api.detail(false, 'record/a', { factory_id: 'huaxing', currency: 'CNY' }, signal); expect(transport.get).toHaveBeenLastCalledWith('/carton-supplier/payables/records/record%2Fa', { params: { factory_id: 'huaxing', currency: 'CNY' }, signal })
  await api.export(false, { factory_id: 'huaxing', currency: 'CNY' }, signal); expect(transport.get).toHaveBeenLastCalledWith('/carton-supplier/payables/export', { params: { factory_id: 'huaxing', currency: 'CNY' }, signal, responseType: 'blob' })
})
it('shares identical money submissions, preserves the original evidence after timeout/reload and does not reuse another actor or currency request', async () => {
  let module = await import('../cartonPayables'), reject!: (error: Error) => void
  transport.post.mockImplementationOnce(() => new Promise((_, fail) => { reject = fail }))
  const first = module.cartonPayablesApi.act(true, body, 'actor:1'), same = module.cartonPayablesApi.act(true, { ...body }, 'actor:1')
  expect(first).toBe(same); expect(transport.post).toHaveBeenCalledTimes(1)
  const original = transport.post.mock.calls[0]![1]; expect(original.request_id).toMatch(/^[\w-]{16,96}$/)
  reject(new Error('响应未知')); await expect(first).rejects.toThrow('响应未知')
  await expect(module.cartonPayablesApi.act(true, { ...body, amount: '13.00' }, 'actor:1')).rejects.toThrow('原请求')
  vi.resetModules(); module = await import('../cartonPayables')
  expect(module.pendingPayableAction(true, 'huaxing', 'CNY', 'actor:1')).toEqual(original)
  transport.post.mockResolvedValue({ data: { revision: 8 } })
  await module.cartonPayablesApi.act(true, body, 'actor:2'); expect(transport.post.mock.calls[1]![1].request_id).not.toBe(original.request_id)
  await module.cartonPayablesApi.act(true, { ...body, currency: 'HKD' }, 'actor:1'); expect(transport.post.mock.calls[2]![1].request_id).not.toBe(original.request_id)
  await module.cartonPayablesApi.act(true, body, 'actor:1'); expect(transport.post.mock.calls[3]![1]).toEqual(original)
  expect(module.pendingPayableAction(true, 'huaxing', 'CNY', 'actor:1')).toBeNull()
  await module.cartonPayablesApi.act(true, body, 'actor:1'); expect(transport.post.mock.calls[4]![1].request_id).not.toBe(original.request_id)
})
it('retains uncertain 5xx evidence but allows correction after a definitive validation rejection, including HTTP without randomUUID', async () => {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis.crypto, 'randomUUID'); Object.defineProperty(globalThis.crypto, 'randomUUID', { configurable: true, value: undefined })
  try {
    const { cartonPayablesApi: api, pendingPayableAction: pending } = await import('../cartonPayables')
    transport.post.mockRejectedValueOnce({ response: { status: 503 } })
    await expect(api.act(true, body, 'actor:1')).rejects.toMatchObject({ response: { status: 503 } })
    const id = pending(true, 'huaxing', 'CNY', 'actor:1')!.request_id
    transport.post.mockRejectedValueOnce({ response: { status: 422 } })
    await expect(api.act(true, body, 'actor:1')).rejects.toMatchObject({ response: { status: 422 } })
    expect(transport.post.mock.calls[1]![1].request_id).toBe(id); expect(pending(true, 'huaxing', 'CNY', 'actor:1')).toBeNull()
    transport.post.mockResolvedValue({ data: {} }); await api.act(true, { ...body, amount: '1.00' }, 'actor:1'); expect(transport.post.mock.calls[2]![1].request_id).not.toBe(id)
  } finally { if (descriptor) Object.defineProperty(globalThis.crypto, 'randomUUID', descriptor); else delete (globalThis.crypto as Partial<Crypto>).randomUUID }
})
