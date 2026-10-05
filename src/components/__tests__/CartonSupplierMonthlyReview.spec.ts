import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import Component from '../CartonSupplierMonthlyReview.vue'
import { supplierSettlementApi as api, type SettlementDocument, type SupplierSettlementWorkspace } from '@/api/cartonSupplierSettlement'

const mocks = vi.hoisted(() => ({ can: vi.fn(() => true) }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ can: mocks.can }) }))
vi.mock('@/lib/http', () => ({ http: {}, getApiErrorMessage: (err: Error) => err.message }))
vi.mock('@/api/cartonSupplierSettlement', () => ({ supplierSettlementApi: { supplierWorkspace: vi.fn(), supplierReview: vi.fn() } }))
const factories = [{ factory_id: 'huaxing', supplier_name: '东康' }]
function fixture(): SupplierSettlementWorkspace {
  const doc: SettlementDocument = { id: 'D1', factory_id: 'huaxing', supplier_id: 'S1', period: '2026-10', currency: 'CNY', version: 1, revision: 4, status: 'DRAFT', source_fingerprint: 'a', created_at: '', updated_at: '', confirmed_at: '', confirmed_by: '', reopen_reason: '', stale: false,
    sources: [{ source_key: 'RECEIPT:R1', kind: 'RECEIPT', document_no: 'DN1', acceptance_date: '2026-10-02', date_basis: 'ACCEPTANCE', customer_name: '客户', contract_no: '合同', item_no: '货号', packaging_type: '外箱', paper_quality: 'A33', specification: '10*20', unit: '个', quantity: '8', unit_price: '2', amount: '16', currency: 'CNY', issues: [] }],
    statement: { origin: 'COLLABORATION', statement_no: '月结1', tax_basis: 'INCLUSIVE', same_price_basis: true, lines: [{ id: 'L1', source_key: 'RECEIPT:R1', document_no: 'DN1', quantity: '8', unit_price: '2', amount: '16', approved_return_unit_price: null, credit_document_no: '', credit_date: null, note: '双方核对按实收结算' }] },
    result: { issues: [], line_results: [], inbound_amount: '16', return_amount: '0', net_amount: '16', statement_amount: '16' } }
  return { factory_id: 'huaxing', supplier_name: '东康', period: '2026-10', currency: 'CNY', documents: [doc] }
}
const button = (w: ReturnType<typeof mount>, text: string) => w.findAll('button').find(row => row.text() === text)!
beforeEach(() => { vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-11-01T04:00:00Z')); vi.resetAllMocks(); mocks.can.mockReturnValue(true); vi.mocked(api.supplierWorkspace).mockResolvedValue(fixture()) })
afterEach(() => vi.useRealTimers())
describe('供应商月结确认', () => {
  it('keeps rejected vendor papers and original unsupported prices visible without adding payable rows', async () => {
    const ws = fixture(), doc = ws.documents[0]!
    doc.result.unsettled_shipments = [{ shipment_id: 'SHIP', line_id: 'REJECTED', document_no: 'DN-REJECTED',
      delivery_date: '2026-10-02', acceptance_date: '2026-10-02', status: 'RECEIVED', item_no: 'REJECTED-BOX',
      quantity: '10', unit: '个', original_unit_price: '2.1234567', reason: '有效验收为零，不计应结', difference_reason: '全部破损拒收不结款' }]
    vi.mocked(api.supplierWorkspace).mockResolvedValue(ws)
    const w = mount(Component, { props: { factories } }); await flushPromises()
    expect(w.text()).toContain('REJECTED-BOX'); expect(w.text()).toContain('2.1234567')
    expect(w.text()).toContain('全部破损拒收不结款')
    expect(w.get('table[aria-label="双方月结明细"]').findAll('tbody tr')).toHaveLength(1)
    expect(w.text()).toContain('本厂应结 16 · 拟结算 16 CNY')
    w.unmount()
  })
  it('shows immutable settlement evidence and acknowledges exactly the displayed revision', async () => {
    const doc = fixture().documents[0]!
    doc.revision = 5; doc.result.supplier_review = { decision: 'CONFIRMED', reason: '', by: 'vendor', at: '2026-11-01', fingerprint: 'a' }
    vi.mocked(api.supplierReview).mockResolvedValue(doc)
    const w = mount(Component, { props: { factories } }); await flushPromises()
    expect(w.text()).toContain('双方核对按实收结算')
    expect(w.find('input[aria-label^="账单数量"]').exists()).toBe(false)
    await button(w, '确认本月结算明细').trigger('click'); await flushPromises()
    expect(api.supplierReview).toHaveBeenCalledWith('D1', 'huaxing', 4, 'CONFIRMED', '')
    expect(w.get('[role="status"]').text()).toContain('等待本厂完成确认')
    w.unmount()
  })
  it('blocks confirmation for differences but allows a reasoned dispute and preserves the draft on failure', async () => {
    const ws = fixture(); ws.documents[0]!.result.issues = ['数量差两件']; vi.mocked(api.supplierWorkspace).mockResolvedValue(ws)
    vi.mocked(api.supplierReview).mockRejectedValue(new Error('月结版本已变化'))
    const w = mount(Component, { props: { factories } }); await flushPromises()
    expect(button(w, '确认本月结算明细').attributes('disabled')).toBeDefined()
    await w.get('[aria-label="供应商月结反馈"]').setValue('请核对少收两件')
    await button(w, '提出对账异议').trigger('click'); await flushPromises()
    expect(api.supplierReview).toHaveBeenCalledWith('D1', 'huaxing', 4, 'DISPUTED', '请核对少收两件')
    expect(w.get('[role="alert"]').text()).toContain('版本已变化')
    expect(w.get<HTMLInputElement>('[aria-label="供应商月结反馈"]').element.value).toBe('请核对少收两件')
    w.unmount()
  })
  it.each(['stale', 'permission', 'current-month'] as const)('prevents review when the displayed document is unavailable: %s', async mode => {
    const ws = fixture()
    if (mode === 'stale') ws.documents[0]!.stale = true
    if (mode === 'permission') mocks.can.mockReturnValue(false)
    if (mode === 'current-month') ws.documents[0]!.period = '2026-11'
    vi.mocked(api.supplierWorkspace).mockResolvedValue(ws)
    const w = mount(Component, { props: { factories } }); await flushPromises()
    expect(button(w, '确认本月结算明细').attributes('disabled')).toBeDefined()
    w.unmount()
  })
  it('discards a retired factory response without revealing its monthly statement', async () => {
    let resolve!: (value: SupplierSettlementWorkspace) => void
    vi.mocked(api.supplierWorkspace).mockImplementationOnce(() => new Promise(r => { resolve = r }))
    const w = mount(Component, { props: { factories } }); await flushPromises()
    vi.mocked(api.supplierWorkspace).mockResolvedValueOnce({ ...fixture(), factory_id: 'huakang-a', documents: [] })
    await w.setProps({ factories: [{ factory_id: 'huakang-a', supplier_name: '东康' }] }); await flushPromises()
    resolve(fixture()); await flushPromises()
    expect(w.text()).not.toContain('DN1')
    expect(w.text()).toContain('本期暂无')
    w.unmount()
  })
})
