import { describe, expect, it, vi } from 'vitest'
const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/lib/http', () => ({ http }))
import { cartonSpecialRequestsApi as api } from '../cartonSpecialRequests'

describe('special order mark request contracts', () => {
  it('uses distinct internal adjustment and actual receipt routes and forwards responsibility scope', async () => {
    http.post.mockResolvedValue({ data: {} }); http.get.mockResolvedValue({ data: {} })
    const signal = new AbortController().signal
    const adjustment = { factory_id: 'huaxing', request_id: 'A', expected_revision: 4, reason: '调整需求数量', kind: 'SAMPLE' as const, requester_name: '员工', purpose: '', customer_code: '', workshop_id: '', required_date: '2026-10-20', lines: [] }
    await api.adjust('R/1', adjustment, signal)
    expect(http.post).toHaveBeenLastCalledWith('/carton-special-requests/R%2F1/adjust', adjustment, { signal })
    const receipt = { factory_id: 'huaxing', request_id: 'M', expected_revision: 4, delivery_note_no: 'REAL', delivery_date: '2026-10-20', acceptance_date: '2026-10-20', lines: [] }
    await api.manualReceive('R/1', receipt, signal)
    expect(http.post).toHaveBeenLastCalledWith('/carton-special-requests/R%2F1/manual-receive', receipt, { signal })
    await api.list('huaxing', false, signal, 'ALL')
    expect(http.get).toHaveBeenLastCalledWith('/carton-special-requests', { params: { factory_id: 'huaxing', responsibility_scope: 'ALL' }, signal })
  })
  it('sends an actual multipart upload with paper, revision and retry identity for both audiences', async () => {
    http.post.mockResolvedValue({ data: { id: 'R' } })
    const file = new File(['pdf'], '箱唛.pdf', { type: 'application/pdf' }), signal = new AbortController().signal
    for (const supplier of [false, true]) {
      await api.attach('order/a', { factory_id: 'huaxing', expected_revision: 4, request_id: 'retry-1', line_id: 'L' }, 'DRAFT', file, supplier, signal)
      const [path, body, options] = http.post.mock.lastCall!
      expect(path).toBe(`${supplier ? '/carton-supplier/special-requests' : '/carton-special-requests'}/order%2Fa/attachments`)
      expect(options).toEqual({ headers: { 'Content-Type': 'multipart/form-data' }, signal })
      expect(body).toBeInstanceOf(FormData)
      expect(Object.fromEntries(body.entries())).toEqual({ factory_id: 'huaxing', expected_revision: '4', request_id: 'retry-1', line_id: 'L', role: 'DRAFT', file })
    }
  })
  it('scopes available shared marks to the correct order and supplier API', async () => {
    http.get.mockResolvedValue({ data: [] })
    const signal = new AbortController().signal
    await api.markOptions('huaxing', signal, true, 'R1')
    expect(http.get).toHaveBeenLastCalledWith('/carton-supplier/special-requests/mark-options', { params: { factory_id: 'huaxing', request_id: 'R1' }, signal })
    await api.markOptions('huakang-a', signal, false, 'R2')
    expect(http.get).toHaveBeenLastCalledWith('/carton-special-requests/mark-options', { params: { factory_id: 'huakang-a', request_id: 'R2' }, signal })
  })
})
