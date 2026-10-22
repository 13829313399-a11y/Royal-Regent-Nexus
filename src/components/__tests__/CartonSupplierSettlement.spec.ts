import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import { useMoneyPreference } from '@/features/carton-procurement/moneyPreference'
import Component from '../CartonSupplierSettlement.vue'
import { supplierSettlementApi as api, type SupplierWorkspace, type SettlementDocument } from '@/api/cartonSupplierSettlement'
import { cartonSupplierReturnsApi } from '@/api/cartonSupplierReturns'
import { row as returnFixture } from './cartonReturnFixture'

const mocks = vi.hoisted(() => ({ can: vi.fn(() => true), leave: vi.fn(), update: vi.fn() }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ can: mocks.can, currentUser: { id: 'settlement-user', identity: { employment_epoch: 1 } } }) }))
vi.mock('vue-router', () => ({ onBeforeRouteLeave: mocks.leave, onBeforeRouteUpdate: mocks.update }))
vi.mock('@/lib/http', () => ({ http: {}, getApiErrorMessage: (e: Error) => e.message }))
vi.mock('@/api/cartonSupplierSettlement', () => ({ supplierSettlementApi: { workspace: vi.fn(), save: vi.fn(), confirm: vi.fn(), reopen: vi.fn(), acceptance: vi.fn(), returnDate: vi.fn(), correctReturnDate: vi.fn() } }))
vi.mock('@/api/cartonSupplierReturns', () => ({ cartonSupplierReturnsApi: { detail: vi.fn() } }))
const workspace = (): SupplierWorkspace => ({
  factory_id: 'huaxing', supplier_id: 'S1', supplier_name: '纸箱供应商', period: '2026-10', currency: 'CNY', source_fingerprint: 'a'.repeat(64),
  sources: [{ source_key: 'RECEIPT:R1', kind: 'RECEIPT', document_no: 'DELIVERY-1', acceptance_date: '2026-10-02', date_basis: 'acceptance_date', customer_name: '客户', contract_no: 'SEP30', item_no: 'ITEM', packaging_type: '外箱', paper_quality: 'A33', specification: '30*20*15', unit: '个', quantity: '10', unit_price: '2', amount: '20.00', currency: 'CNY', issues: [] }],
  documents: [], issues: [], undated_receipts: [],
})
const document = (): SettlementDocument => ({
  id: 'D1', factory_id: 'huaxing', supplier_id: 'S1', period: '2026-10', currency: 'CNY', version: 1, revision: 1, status: 'DRAFT', source_fingerprint: 'a'.repeat(64), sources: workspace().sources,
  statement: { statement_no: 'BILL1', tax_basis: 'INCLUSIVE', same_price_basis: true, lines: [{ id: 'L1', source_key: 'RECEIPT:R1', document_no: 'DELIVERY-1', quantity: '10', unit_price: '2', amount: '20.00', approved_return_unit_price: null, credit_document_no: '', credit_date: null, note: '' }] },
  result: { issues: [], line_results: [{ id: 'L1', source_key: 'RECEIPT:R1', quantity_difference: '0', price_difference: '0', amount_difference: '0', issues: [] }], inbound_amount: '20.00', return_amount: '0.00', net_amount: '20.00', statement_amount: '20.00' },
  created_at: '', updated_at: '', confirmed_at: '', confirmed_by: '', reopen_reason: '', stale: false,
})
const button = (w: ReturnType<typeof mount>, text: string) => w.findAll('button').find(b => b.text() === text)!
function collaborativeWorkspace(): SupplierWorkspace {
  const ws = workspace(), source = { ...ws.sources[0]!, supplier_delivery: { shipment_id: 'SHIP1', line_id: 'SL1', document_no: 'DELIVERY-1', delivery_date: '2026-09-30', quantity: '10', unit_price: '2', amount: '20.00', currency: 'CNY', received_quantity: '10', damaged_quantity: '0', rejected_quantity: '0', unusable_quantity: '0', difference_reason: '', quantity_difference: '0', price_difference: '0' } }
  ws.collaboration = { sources: [source], source_fingerprint: 'c'.repeat(64), unsettled_shipments: [], lines: document().statement.lines }
  return ws
}
afterEach(() => { vi.useRealTimers(); window.localStorage.clear() })
beforeEach(() => { vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-11-01T04:00:00Z')); vi.resetAllMocks(); mocks.can.mockReturnValue(true); vi.mocked(api.workspace).mockResolvedValue(workspace()) })

describe('供应商月结对账', () => {
  it.each([false, true])('refreshes adopted supplier prices while preserving deliberate manual adjustment=%s', async manual => {
    const ws = collaborativeWorkspace(), doc = document()
    doc.statement.origin = 'COLLABORATION'; doc.stale = true
    if (manual) doc.statement.lines[0]!.unit_price = '7'
    const nextSource = { ...doc.sources[0]!, unit_price: '3', amount: '30.00', supplier_price_update: { manual_unit_price: '2', supplier_unit_price: '3', amount_difference: '10', quantity: '10', currency: 'CNY', occurred_at: '', document_no: 'DELIVERY-1' } }
    ws.documents = [doc]; ws.collaboration!.sources = [nextSource]; ws.collaboration!.lines = [{ ...doc.statement.lines[0]!, unit_price: '3', amount: '30.00' }]
    vi.mocked(api.workspace).mockResolvedValue(ws); vi.mocked(api.save).mockResolvedValue(doc)
    const w = mount(Component, { props: { factoryId: 'huaxing' } }); await flushPromises()
    await button(w, '更新来源并重新核对').trigger('click')
    await button(w, '保存并核对差异').trigger('submit'); await flushPromises()
    expect(vi.mocked(api.save).mock.calls[0]![0].lines[0]!.unit_price).toBe(manual ? '7' : '3')
    w.unmount()
  })
  it.each(['new', 'dirty', 'stale', 'clean'] as const)('shows a truthful summary for %s without claiming an unverified zero difference', async state => {
    const ws = collaborativeWorkspace(), doc = document()
    doc.statement.origin = 'COLLABORATION'; doc.stale = state === 'stale'
    if (state !== 'new') ws.documents = [doc]
    vi.mocked(api.workspace).mockResolvedValue(ws)
    const w = mount(Component, { props: { factoryId: 'huaxing' } }); await flushPromises()
    if (state === 'dirty') await w.get('[aria-label="供应商账单号"]').setValue('changed')
    const summary = w.get('[aria-label="本月核对概览"]')
    if (state === 'clean') { expect(summary.text()).toContain('核对无差异'); expect(summary.text()).toContain('等待供应商确认') }
    else { expect(summary.text()).not.toContain('核对无差异'); expect(summary.text()).toContain('待核对') }
    expect(w.find('td[data-label="供应商原送货"]').exists()).toBe(false)
    w.unmount()
  })
  it('shows adopted supplier prices with previous manual price and amount difference, without treating the notice as an unresolved difference', async () => {
    const ws = collaborativeWorkspace(), doc = document()
    doc.sources[0]!.supplier_price_update = { manual_unit_price: '1.50', supplier_unit_price: '2.00', amount_difference: '5.00', quantity: '10', currency: 'CNY', occurred_at: '2026-10-21', document_no: 'DELIVERY-1' }
    ws.documents = [doc]; vi.mocked(api.workspace).mockResolvedValue(ws)
    const w = mount(Component, { props: { factoryId: 'huaxing' } }); await flushPromises()
    expect(w.get('[aria-label="供应商价格更新记录"]').text()).toContain('手工价 1.50 → 供应商价 2.00')
    expect(w.get('[aria-label="本月核对概览"]').text()).toContain('核对无差异')
    w.unmount()
  })
  it('keeps a genuine reopened empty bill operable after explicitly removing withdrawn unmatched evidence', async () => {
    const ws = collaborativeWorkspace(), doc = document()
    doc.statement.origin = 'COLLABORATION'; doc.stale = true; doc.reopen_reason = '原实收已撤回更正重核'
    ws.documents = [doc]; ws.sources = []; ws.source_fingerprint = 'b'.repeat(64)
    ws.collaboration = { sources: [], lines: [], source_fingerprint: 'b'.repeat(64), unsettled_shipments: [] }
    const empty = { ...doc, stale: false, sources: [], statement: { ...doc.statement, lines: [] }, result: { ...doc.result, issues: [], line_results: [], inbound_amount: '0.00', return_amount: '0.00', net_amount: '0.00', statement_amount: '0.00' } }
    vi.mocked(api.workspace).mockResolvedValue(ws); vi.mocked(api.save).mockResolvedValue(empty)
    const w = mount(Component, { props: { factoryId: 'huaxing' } }); await flushPromises()
    await button(w, '更新来源并重新核对').trigger('click'); await button(w, '移除录错行').trigger('click')
    expect(button(w, '保存并核对差异').attributes('disabled')).toBeUndefined()
    await button(w, '保存并核对差异').trigger('submit'); await flushPromises()
    expect(api.save).toHaveBeenCalledWith(expect.objectContaining({ id: 'D1', expected_revision: 1, source_fingerprint: 'b'.repeat(64), lines: [] }))
    expect(w.text()).toContain('付款与独立费用在“应付与付款”查看'); w.unmount()
  })
  it.each(['refresh', 'adopt'] as const)('uses server-approved return evidence for %s while keeping legacy manual sources editable', async mode => {
    const ws = workspace(), doc = document()
    const legacySource = { ...ws.sources[0]!, source_key: 'RETURN:M1', kind: 'RETURN' as const, date_basis: 'RETURN_ACTUAL', unit_price: null, amount: null }
    const currentSource = { ...legacySource, unit_price: '2.5', amount: '25.00', return_agreement: { receipt_event_ids: ['SIGN1'], credit_event_id: 'CREDIT-CONFIRM-1', credit_document_no: 'CREDIT-NEW', credit_date: '2026-10-03' } }
    const oldLine = { ...doc.statement.lines[0]!, source_key: 'RETURN:M1', amount: null, unit_price: null, approved_return_unit_price: null }
    const suggested = { ...oldLine, amount: '25.00', unit_price: '2.5', approved_return_unit_price: '2.5', credit_document_no: 'CREDIT-NEW', credit_date: '2026-10-03' }
    doc.sources = [legacySource]; doc.statement.lines = [oldLine]; doc.statement.origin = mode === 'refresh' ? 'COLLABORATION' : 'MANUAL'; doc.stale = mode === 'refresh'
    ws.sources = [legacySource]; ws.documents = [doc]; ws.collaboration = { sources: [currentSource], lines: [suggested], source_fingerprint: 'c'.repeat(64), unsettled_shipments: [] }
    vi.mocked(api.workspace).mockResolvedValue(ws); vi.mocked(api.save).mockResolvedValue(doc)
    const w = mount(Component, { props: { factoryId: 'huaxing' } }); await flushPromises()
    expect(w.find('[aria-label="认可退货单价 L1"]').exists()).toBe(true)
    await button(w, mode === 'refresh' ? '更新来源并重新核对' : '接入双方对账').trigger('click'); await flushPromises()
    expect(w.text()).toContain('双方退货核定依据'); expect(w.text()).toContain('CREDIT-NEW')
    expect(w.find('[aria-label="认可退货单价 L1"]').exists()).toBe(false)
    await button(w, '查看退货回执').trigger('click')
    expect(w.emitted('returns')).toEqual([[]])
    await button(w, '保存并核对差异').trigger('submit'); await flushPromises()
    expect(vi.mocked(api.save).mock.calls[0]![0].lines[0]).toMatchObject({ amount: '25.00', unit_price: '2.5', approved_return_unit_price: '2.5', credit_document_no: 'CREDIT-NEW' })
    w.unmount()
  })
  it('opens recorded date correction with independent evidence and refreshes without changing stock posting or monthly statement payload', async () => {
    const ws = workspace(), doc = document(), detail = { ...returnFixture(), allowed_actions: ['CORRECT_DATE'] }
    const source = { ...ws.sources[0]!, source_key: 'RETURN:M1', kind: 'RETURN' as const, date_basis: 'RETURN_ACTUAL', acceptance_date: '2026-10-01', return_date: '2026-10-01', posting_date: '2026-10-02' }
    ws.sources = [source]; doc.sources = [source]; doc.statement.lines[0] = { ...doc.statement.lines[0]!, source_key: source.source_key }; ws.documents = [doc]
    vi.mocked(api.workspace).mockResolvedValue(ws); vi.mocked(cartonSupplierReturnsApi.detail).mockResolvedValue(detail)
    const w = mount(Component, { props: { factoryId: 'huaxing' } }); await flushPromises()
    await w.get('[aria-label="更正退货日期 RETURN:M1"]').trigger('click'); await flushPromises()
    expect(cartonSupplierReturnsApi.detail).toHaveBeenCalledWith('M1', 'huaxing', true, expect.any(AbortSignal))
    await w.get('[aria-label="更正后的实际退货日期"]').setValue('2026-09-30')
    await w.get('[aria-label="实际退货日期更正原因"]').setValue('核实原退货交接单日期')
    await w.get('form[aria-label="更正已录实际退货日期"]').trigger('submit'); await flushPromises()
    expect(api.correctReturnDate).toHaveBeenCalledWith('M1', expect.objectContaining({ expected_evidence_revision: 1, expected_evidence_fingerprint: 'd'.repeat(64), return_date: '2026-09-30' }), expect.any(AbortSignal))
    expect(w.get('[role="status"]').text()).toContain('真实到账记录保留')
    expect(api.save).not.toHaveBeenCalled(); expect(doc.sources[0]!.posting_date).toBe('2026-10-02'); w.unmount()
  })
  it('presents cash refund as verified financial evidence and adds the server cash total visibly to the net payable equation', async () => {
    const ws = workspace(), doc = document()
    const source = { ...ws.sources[0]!, source_key: 'RETURN_REFUND:M1:CASH1', kind: 'RETURN_REFUND' as const, quantity: '1', unit: '笔', amount: '6.00', unit_price: '6.00', date_basis: 'REFUND_ACTUAL', acceptance_date: '2026-10-04' }
    doc.sources = [source]; doc.statement.lines[0] = { ...doc.statement.lines[0]!, source_key: source.source_key, quantity: '1', amount: '6.00' }
    doc.result.cash_refund_amount = '6.00'; doc.result.return_amount = '20.00'; doc.result.return_deduction_amount = '14.00'; doc.result.net_amount = '6.00'; ws.documents = [doc]
    vi.mocked(api.workspace).mockResolvedValue(ws)
    const w = mount(Component, { props: { factoryId: 'huaxing' } }); await flushPromises()
    await button(w, '展开原单与验收对照').trigger('click')
    const cell = w.get('td[data-label="本厂有效验收"]')
    expect(cell.text()).toContain('资金凭证 · 现金到账'); expect(cell.text()).toContain('不计实物收料'); expect(cell.text()).not.toContain('1 笔')
    expect(w.text()).toContain('本月已确认现金退款 6.00'); expect(w.text()).toContain('退货净抵扣 14.00')
    expect(w.text()).toContain('现金退款到账日期 2026-10-04'); expect(w.text()).toContain('月结抵扣仅分配贷项，不再另减')
    w.unmount()
  })
  it('labels legacy return dates and verifies them only with supervisor evidence while preserving the source posting date', async () => {
    const ws = workspace(), doc = document()
    const source = { ...ws.sources[0]!, source_key: 'RETURN:M1', kind: 'RETURN' as const, date_basis: 'RETURN_POSTING', acceptance_date: '2026-10-02', unit_price: null, amount: null }
    ws.sources = [source]; doc.sources = [source]
    doc.statement.lines[0] = { ...doc.statement.lines[0]!, source_key: source.source_key }
    ws.documents = [doc]; vi.mocked(api.workspace).mockResolvedValue(ws); vi.mocked(api.returnDate).mockResolvedValue({})
    const w = mount(Component, { props: { factoryId: 'huaxing' } }); await flushPromises()
    expect(w.text()).toContain('历史记账日期（实际退货日期待核实） 2026-10-02')
    await w.get('[aria-label="核实退货日期 RETURN:M1"]').trigger('click')
    const form = w.get('[aria-label="核实实际退货日期"]').element.closest('form')!
    expect(form.textContent).toContain('旧归属月份 2026-10')
    await w.get('[aria-label="核实实际退货日期"]').setValue('2026-09-30')
    await w.get('[aria-label="实际退货日期核实依据"]').setValue('退货交接单和经手人核实')
    await button(w, '保存实际退货日期').trigger('submit'); await flushPromises()
    expect(api.returnDate).toHaveBeenCalledWith('M1', 'huaxing', '2026-10-02', '2026-09-30', '退货交接单和经手人核实')
    w.unmount()
  })

  it('shows explicit actual return and stock posting dates and omits the one-time legacy verification entry', async () => {
    const ws = workspace(), doc = document()
    const source = { ...ws.sources[0]!, source_key: 'RETURN:M1', kind: 'RETURN' as const, date_basis: 'RETURN_ACTUAL', acceptance_date: '2026-09-30', return_date: '2026-09-30', posting_date: '2026-10-02', unit_price: null, amount: null }
    ws.sources = [source]; doc.sources = [source]; doc.statement.lines[0] = { ...doc.statement.lines[0]!, source_key: source.source_key }
    ws.documents = [doc]; vi.mocked(api.workspace).mockResolvedValue(ws)
    const w = mount(Component, { props: { factoryId: 'huaxing' } }); await flushPromises()
    expect(w.text()).toContain('实际退货日期 2026-09-30'); expect(w.text()).toContain('库存记账 2026-10-02')
    expect(w.find('[aria-label="核实退货日期 RETURN:M1"]').exists()).toBe(false)
    w.unmount()
  })
  it('changes HKD reference display without dirtying the statement or changing the RMB save payload', async () => {
    const ws = workspace(), doc = document()
    ws.documents = [doc]
    vi.mocked(api.workspace).mockResolvedValue(ws); vi.mocked(api.save).mockResolvedValue(doc)
    let money!: ReturnType<typeof useMoneyPreference>
    const preferences = mount(defineComponent({ setup() { money = useMoneyPreference({ userId: 'settlement-user', employmentEpoch: 1 }); return () => null } }))
    const w = mount(Component, { props: { factoryId: 'huaxing' } }); await flushPromises()
    try {
      expect(w.text()).not.toContain('港币参考 HK$')
      money.setPreference('HKD', '1.1'); await flushPromises()
      expect(w.get('[aria-label="月结港币参考汇率"]').text()).toContain('1 CNY = 1.1 HKD')
      expect(w.text()).toContain('港币参考 HK$22.00')
      expect(w.text()).toContain('港币参考 HK$2.200000')
      expect(button(w, '放弃未保存内容')).toBeUndefined()
      if (w.find('[aria-label="处理结算明细 L1"]').exists()) await w.find('[aria-label="处理结算明细 L1"]').trigger('click')
      expect(w.get<HTMLInputElement>('[aria-label="账单单价 L1"]').element.value).toBe('2')
      if (w.find('[aria-label="处理结算明细 L1"]').exists()) await w.find('[aria-label="处理结算明细 L1"]').trigger('click')
      expect(w.get<HTMLInputElement>('[aria-label="账单金额 L1"]').element.value).toBe('20.00')
      money.setPreference('HKD', '1.2'); await flushPromises()
      expect(w.text()).toContain('港币参考 HK$24.00')
      expect(button(w, '放弃未保存内容')).toBeUndefined()
      await button(w, '保存并核对差异').trigger('submit'); await flushPromises()
      expect(api.save).toHaveBeenCalledWith(expect.objectContaining({ currency: 'CNY', lines: expect.arrayContaining([
        expect.objectContaining({ id: 'L1', quantity: '10', unit_price: '2', amount: '20.00' }),
      ]) }))
      expect(api.workspace).toHaveBeenCalledWith('huaxing', expect.any(String), 'CNY')
      money.setPreference('CNY', '1.2'); await flushPromises()
      expect(w.text()).not.toContain('港币参考 HK$')
      await w.get('[aria-label="供应商对账币种"]').setValue('JPY')
      await button(w, '查询 / 刷新').trigger('click'); await flushPromises()
      expect(api.workspace).toHaveBeenLastCalledWith('huaxing', expect.any(String), 'JPY')
    } finally { w.unmount(); preferences.unmount() }
  })
  it('shares header search while saving and confirming the complete version, and retains standalone search', async () => {
    const ws = workspace(), doc = document()
    doc.sources.push({ ...doc.sources[0]!, source_key: 'RECEIPT:R2', document_no: 'DELIVERY-2', item_no: 'OTHER-ITEM' })
    doc.statement.lines.push({ ...doc.statement.lines[0]!, id: 'L2', source_key: 'RECEIPT:R2', document_no: 'DELIVERY-2' })
    ws.documents = [doc]
    vi.mocked(api.workspace).mockResolvedValue(ws)
    vi.mocked(api.save).mockResolvedValue(doc)
    vi.mocked(api.confirm).mockResolvedValue({ ...doc, status: 'CONFIRMED' })
    const w = mount(Component, { props: { factoryId: 'huaxing', search: 'DELIVERY-1' } }); await flushPromises()
    expect(w.find('[aria-label="月结明细关键字"]').exists()).toBe(false)
    expect(w.get('table').text()).toContain('DELIVERY-1')
    expect(w.get('table').text()).not.toContain('DELIVERY-2')
    expect(w.emitted('update:search')).toBeUndefined()
    await button(w, '保存并核对差异').trigger('submit'); await flushPromises()
    expect(api.save).toHaveBeenCalledWith(expect.objectContaining({ lines: expect.arrayContaining([
      expect.objectContaining({ id: 'L1' }), expect.objectContaining({ id: 'L2' }),
    ]) }))
    expect(vi.mocked(api.save).mock.calls[0]![0].lines).toHaveLength(2)
    await button(w, '确认对账完成').trigger('click'); await flushPromises()
    expect(api.confirm).toHaveBeenCalledWith('D1', 'huaxing', 1)
    await button(w, '清除筛选').trigger('click')
    expect(w.emitted('update:search')).toEqual([['']])
    await w.setProps({ factoryId: 'huadeng', search: 'OTHER-ITEM' }); await flushPromises()
    expect(w.emitted('update:search')).toEqual([['']])
    expect(w.get('table').text()).toContain('DELIVERY-2')
    expect(w.get('table').text()).not.toContain('DELIVERY-1')
    w.unmount()
    const standalone = mount(Component, { props: { factoryId: 'huaxing' } }); await flushPromises()
    expect(standalone.find('[aria-label="月结明细关键字"]').exists()).toBe(true)
    standalone.unmount()
  })
  it('shows one bilateral workflow with normal data read-only and opens adjustment only on the selected line', async () => {
    vi.mocked(api.workspace).mockResolvedValue(collaborativeWorkspace())
    const w = mount(Component, { props: { factoryId: 'huaxing' } }); await flushPromises()
    expect(w.get('[aria-label="双方月结流程"]').text()).toContain('1 · 本厂核对并保存')
    expect(w.get('[aria-label="双方月结流程"]').text()).toContain('2 · 供应商核对确认')
    expect(w.get('[aria-label="双方月结流程"]').text()).toContain('3 · 本厂完成月结')
    expect(w.find('[aria-label="账单数量 L1"]').exists()).toBe(false)
    expect(w.get('[aria-label="拟结算明细 L1"]').text()).toContain('10 个')
    expect(w.get('thead').text()).not.toContain('供应商原送货')
    await button(w, '展开原单与验收对照').trigger('click')
    expect(w.get('thead').text()).toContain('供应商原送货本厂有效验收拟结算')
    await w.get('[aria-label="处理结算明细 L1"]').trigger('click')
    if (w.find('[aria-label="处理结算明细 L1"]').exists()) await w.find('[aria-label="处理结算明细 L1"]').trigger('click')
    expect(w.get<HTMLInputElement>('[aria-label="账单数量 L1"]').element.value).toBe('10')
    expect(button(w, '放弃未保存内容')).toBeUndefined()  // Opening the row does not change business data.
    if (w.find('[aria-label="处理结算明细 L1"]').exists()) await w.find('[aria-label="处理结算明细 L1"]').trigger('click')
    await w.get('[aria-label="账单金额 L1"]').setValue('18')
    expect(button(w, '放弃未保存内容')).toBeDefined()
    expect(w.get('[aria-label="双方月结流程"]').text()).toContain('修改待保存')
    expect(w.get('[aria-label="双方月结流程"]').text()).toContain('更新后须重新确认')
    w.unmount()
  })
  it('keeps a completed collaborative version read-only and shows its previous confirmation evidence', async () => {
    const ws = collaborativeWorkspace(), doc = document()
    doc.status = 'SUPERSEDED'; doc.statement.origin = 'COLLABORATION'; doc.sources = ws.collaboration!.sources
    doc.result.supplier_review = { decision: 'CONFIRMED', reason: '双方确认原凭证', by: 'VENDOR', at: '2026-11-01', fingerprint: 'x' }
    ws.documents = [doc]; vi.mocked(api.workspace).mockResolvedValue(ws)
    const w = mount(Component, { props: { factoryId: 'huaxing' } }); await flushPromises()
    expect(w.text()).toContain('历史版本 · 只读')
    expect(w.get('[aria-label="双方月结确认状态"]').text()).toContain('历史确认记录')
    expect(w.text()).toContain('供应商已确认 · 2026-11-01')
    expect(w.find('[aria-label="处理结算明细 L1"]').exists()).toBe(false)
    expect(w.find('[aria-label="账单金额 L1"]').exists()).toBe(false)
    expect(button(w, '保存并核对差异')).toBeUndefined()
    w.unmount()
  })
  it('marks a stale supplier acknowledgement as needing renewed confirmation in every current-version status', async () => {
    const ws = collaborativeWorkspace(), doc = document()
    doc.statement.origin = 'COLLABORATION'; doc.sources = ws.collaboration!.sources; doc.stale = true
    doc.result.supplier_review = { decision: 'CONFIRMED', reason: '', by: 'VENDOR', at: '2026-11-01', fingerprint: 'x' }
    ws.documents = [doc]; vi.mocked(api.workspace).mockResolvedValue(ws)
    const w = mount(Component, { props: { factoryId: 'huaxing' } }); await flushPromises()
    expect(w.get('[aria-label="双方月结流程"]').text()).toContain('更新后须重新确认')
    expect(w.get('[aria-label="双方月结确认状态"]').text()).toContain('须更新并保存后重新取得供应商确认')
    expect(w.get('[aria-label="双方月结确认状态"]').text()).not.toContain('供应商已确认')
    expect(button(w, '确认对账完成').attributes('disabled')).toBeDefined()
    w.unmount()
  })
  it('converts an existing manual draft without erasing invoice identity, return evidence or unmatched vendor rows', async () => {
    const ws = workspace(), doc = document()
    doc.statement.statement_no = 'EXTERNAL-BILL'; doc.statement.tax_basis = 'EXCLUSIVE'
    doc.statement.lines[0]!.note = '已有凭证依据'
    doc.statement.lines.push({ ...doc.statement.lines[0]!, id: 'EXTRA', source_key: '', document_no: 'EXTRA-BILL' })
    ws.documents = [doc]
    ws.collaboration = { sources: ws.sources.map(row => ({ ...row, supplier_delivery: null })),
      source_fingerprint: 'c'.repeat(64), unsettled_shipments: [], lines: doc.statement.lines.slice(0, 1).map(row => ({ ...row, quantity: null, unit_price: null, amount: null, note: '' })) }
    vi.mocked(api.workspace).mockResolvedValue(ws); vi.mocked(api.save).mockResolvedValue(doc)
    const w = mount(Component, { props: { factoryId: 'huaxing' } }); await flushPromises()
    await button(w, '接入双方对账').trigger('click')
    expect(w.get<HTMLInputElement>('[aria-label="供应商账单号"]').element.value).toBe('EXTERNAL-BILL')
    if (w.find('[aria-label="处理结算明细 L1"]').exists()) await w.find('[aria-label="处理结算明细 L1"]').trigger('click')
    expect(w.get<HTMLInputElement>('[aria-label="账单金额 L1"]').element.value).toBe('20.00')
    expect(w.get<HTMLInputElement>('[aria-label="未匹配送货单 EXTRA"]').element.value).toBe('EXTRA-BILL')
    await button(w, '保存并核对差异').trigger('submit'); await flushPromises()
    expect(api.save).toHaveBeenCalledWith(expect.objectContaining({ id: doc.id, origin: 'COLLABORATION', statement_no: 'EXTERNAL-BILL', tax_basis: 'EXCLUSIVE', source_fingerprint: 'c'.repeat(64), lines: expect.arrayContaining([expect.objectContaining({ note: '已有凭证依据', amount: '20.00' })]) }))
    w.unmount()
  })
  it('prefills independent vendor evidence and leaves unlinked historical receipts blank', async () => {
    const ws = workspace()
    const source = { ...ws.sources[0]!, quantity: '8', amount: '16', supplier_delivery: { shipment_id: 'SHIP1', line_id: 'SL1', document_no: 'DELIVERY-1', delivery_date: '2026-09-30', quantity: '10', unit_price: '2', amount: '20', currency: 'CNY', received_quantity: '8', damaged_quantity: '0', rejected_quantity: '0', unusable_quantity: '0', difference_reason: '原送货少到两件', quantity_difference: '2', price_difference: '0' } }
    ws.collaboration = { sources: [source, { ...ws.sources[0]!, source_key: 'RECEIPT:HISTORY', document_no: 'HISTORY', supplier_delivery: null }], source_fingerprint: 'c'.repeat(64), unsettled_shipments: [{ shipment_id: 'PENDING', document_no: 'PENDING-NOTE', delivery_date: '2026-10-31', acceptance_date: null, status: 'SENT', reason: '待仓库验收' }], lines: [
      { ...document().statement.lines[0]!, quantity: '10', amount: '20' },
      { ...document().statement.lines[0]!, id: 'H1', source_key: 'RECEIPT:HISTORY', document_no: 'HISTORY', quantity: null, unit_price: null, amount: null },
    ] }
    vi.mocked(api.workspace).mockResolvedValue(ws)
    const saved = document(); saved.statement.origin = 'COLLABORATION'; saved.sources = ws.collaboration.sources
    saved.statement.lines = ws.collaboration.lines; saved.source_fingerprint = 'c'.repeat(64)
    vi.mocked(api.save).mockResolvedValue(saved)
    const w = mount(Component, { props: { factoryId: 'huaxing' } }); await flushPromises()
    expect(w.find('[aria-label="账单数量 L1"]').exists()).toBe(false)
    expect(w.get('[aria-label="处理结算明细 L1"]').text()).toBe('处理差异')
    await w.get('[aria-label="处理结算明细 L1"]').trigger('click')
    if (w.find('[aria-label="处理结算明细 L1"]').exists()) await w.find('[aria-label="处理结算明细 L1"]').trigger('click')
    expect(w.get<HTMLInputElement>('[aria-label="账单数量 L1"]').element.value).toBe('10')
    if (w.find('[aria-label="处理结算明细 H1"]').exists()) await w.find('[aria-label="处理结算明细 H1"]').trigger('click')
    expect(w.get<HTMLInputElement>('[aria-label="账单数量 H1"]').element.value).toBe('')
    expect(w.text()).toContain('原送货少到两件'); expect(w.text()).toContain('PENDING-NOTE')
    await button(w, '保存并核对差异').trigger('submit'); await flushPromises()
    expect(api.save).toHaveBeenCalledWith(expect.objectContaining({ origin: 'COLLABORATION', source_fingerprint: 'c'.repeat(64) }))
    expect(button(w, '确认对账完成').attributes('disabled')).toBeDefined()
    expect(w.text()).toContain('待供应商在供应商协同')
    w.unmount()
  })
  it('requires supplier acknowledgement and invalidates the final button when an acknowledged draft is edited', async () => {
    const ws = workspace(), doc = document(); doc.statement.origin = 'COLLABORATION'
    doc.result.supplier_review = { decision: 'CONFIRMED', reason: '', by: 'VENDOR', at: '2026-11-01', fingerprint: 'x' }
    ws.documents = [doc]; vi.mocked(api.workspace).mockResolvedValue(ws)
    const w = mount(Component, { props: { factoryId: 'huaxing' } }); await flushPromises()
    expect(button(w, '确认对账完成').attributes('disabled')).toBeUndefined()
    if (w.find('[aria-label="处理结算明细 L1"]').exists()) await w.find('[aria-label="处理结算明细 L1"]').trigger('click')
    await w.get('[aria-label="账单金额 L1"]').setValue('21')
    expect(button(w, '确认对账完成').attributes('disabled')).toBeDefined()
    expect(w.text()).toContain('保存后需重新取得供应商确认')
    w.unmount()
  })
  it('leaves vendor values empty and uses acceptance month independently of the order date', async () => {
    const w = mount(Component, { props: { factoryId: 'huaxing' } }); await flushPromises()
    expect(w.text()).toContain('2026-10-02'); expect(w.text()).toContain('SEP30')
    if (w.find('[aria-label^="处理结算明细"]').exists()) await w.find('[aria-label^="处理结算明细"]').trigger('click')
    const quantity = w.get<HTMLInputElement>('input[aria-label^="账单数量"]')
    expect(quantity.element.value).toBe('')
    expect(button(w, '确认对账完成')).toBeUndefined()
    await w.get('[aria-label="供应商对账月份"]').setValue('2026-10')
    await button(w, '查询 / 刷新').trigger('click'); await flushPromises()
    expect(api.workspace).toHaveBeenLastCalledWith('huaxing', '2026-10', 'CNY')
    w.unmount()
  })
  it('sends entered statement values, preserves blanks and shows server discrepancies before confirmation', async () => {
    const doc = document(); doc.result.line_results[0]!.issues = ['账单数量不一致']; doc.result.line_results[0]!.quantity_difference = '2'
    vi.mocked(api.save).mockResolvedValue(doc)
    const w = mount(Component, { props: { factoryId: 'huaxing' } }); await flushPromises()
    await w.get('[aria-label="供应商账单号"]').setValue('ACTUAL-BILL')
    if (w.find('[aria-label^="处理结算明细"]').exists()) await w.find('[aria-label^="处理结算明细"]').trigger('click')
    await w.get('input[aria-label^="账单数量"]').setValue('12')
    await button(w, '保存并核对差异').trigger('submit'); await flushPromises()
    expect(api.save).toHaveBeenCalledWith(expect.objectContaining({ statement_no: 'ACTUAL-BILL', factory_id: 'huaxing', source_fingerprint: 'a'.repeat(64), lines: [expect.objectContaining({ quantity: 12, unit_price: null, amount: null })] }))
    expect(w.text()).toContain('账单数量不一致')
    expect(button(w, '确认对账完成').attributes('disabled')).toBeDefined()
    w.unmount()
  })
  it('retains the draft when confirmation rejects a changed source and disables confirmation after edits', async () => {
    const ws = workspace(); ws.documents = [document()]; vi.mocked(api.workspace).mockResolvedValue(ws)
    vi.mocked(api.confirm).mockRejectedValue(new Error('收料来源已变化，请重核'))
    const w = mount(Component, { props: { factoryId: 'huaxing' } }); await flushPromises()
    await button(w, '确认对账完成').trigger('click'); await flushPromises()
    expect(api.confirm).toHaveBeenCalledWith('D1', 'huaxing', 1)
    expect(w.get('[role="alert"]').text()).toContain('来源已变化')
    expect(w.get<HTMLInputElement>('[aria-label="供应商账单号"]').element.value).toBe('BILL1')
    if (w.find('[aria-label="处理结算明细 L1"]').exists()) await w.find('[aria-label="处理结算明细 L1"]').trigger('click')
    await w.get('[aria-label="账单金额 L1"]').setValue('21')
    expect(button(w, '确认对账完成').attributes('disabled')).toBeDefined()
    expect(w.text()).toContain('差异待重算')
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    expect(mocks.leave.mock.calls[0]![0]()).toBe(false); confirm.mockRestore()
    w.unmount()
  })
  it('keeps confirmed snapshots read-only and reopens with revision and a reason', async () => {
    const doc = document(); doc.status = 'CONFIRMED'; const ws = workspace(); ws.documents = [doc]
    vi.mocked(api.workspace).mockResolvedValue(ws)
    const reopened = document(); reopened.id = 'D2'; reopened.version = 2; vi.mocked(api.reopen).mockResolvedValue(reopened)
    const w = mount(Component, { props: { factoryId: 'huaxing' } }); await flushPromises()
    expect(w.find('[aria-label="账单金额 L1"]').exists()).toBe(false)
    expect(button(w, '保存并核对差异')).toBeUndefined()
    expect(w.text()).toContain('补录旧月原送货或更正来源前，请重开受影响的已确认月份')
    expect(w.text()).toContain('补证后须保存新草稿并由供应商和内部重新确认，金额不会自动调整')
    await w.get('[aria-label="供应商对账重核原因"]').setValue('更正供应商账单')
    await button(w, '建立重核版本').trigger('submit'); await flushPromises()
    expect(api.reopen).toHaveBeenCalledWith('D1', 'huaxing', 1, '更正供应商账单')
    if (w.find('[aria-label="处理结算明细 L1"]').exists()) await w.find('[aria-label="处理结算明细 L1"]').trigger('click')
    expect(w.get('[aria-label="账单金额 L1"]').attributes('disabled')).toBeUndefined()
    w.unmount()
  })
  it('does not grant date fixes or settlement writes to read-only users', async () => {
    mocks.can.mockReturnValue(false); const ws = workspace()
    ws.undated_receipts = [{ receipt_id: 'R0', revision: 3, document_no: 'OLD', confirmed_at: '2026-09-01', acceptance_date: null }]
    vi.mocked(api.workspace).mockResolvedValue(ws)
    const w = mount(Component, { props: { factoryId: 'huaxing' } }); await flushPromises()
    expect(w.text()).toContain('历史收料未记录实际验收日期')
    expect(button(w, '核实验收日期 OLD')).toBeUndefined()
    expect(button(w, '保存并核对差异')).toBeUndefined()
    expect(w.find('input[aria-label^="账单数量"]').exists()).toBe(false)
    w.unmount()
  })
  it('reports a saved acceptance date separately from its failed statement refresh', async () => {
    const ws = workspace()
    ws.undated_receipts = [{ receipt_id: 'R0', revision: 3, document_no: 'OLD', confirmed_at: '2026-09-01', acceptance_date: null }]
    vi.mocked(api.workspace).mockResolvedValue(ws)
    vi.mocked(api.acceptance).mockResolvedValue({})
    const w = mount(Component, { props: { factoryId: 'huaxing' } }); await flushPromises()
    await button(w, '核实验收日期 OLD').trigger('click')
    await w.get('[aria-label="补录实际验收日期"]').setValue('2026-10-02')
    await w.get('[aria-label="验收日期核实依据"]').setValue('已核对仓库签收单')
    vi.mocked(api.workspace).mockRejectedValueOnce(new Error('对账服务暂不可用'))
    await button(w, '保存核实日期').trigger('submit'); await flushPromises()
    expect(w.get('[role="alert"]').text()).toContain('验收日期已保存，但对账刷新失败：对账服务暂不可用')
    expect(api.acceptance).toHaveBeenCalledTimes(1)
    expect(w.find('[aria-label="补录实际验收日期"]').exists()).toBe(false)
    w.unmount()
  })
  it('ignores an old factory response arriving after switching factories', async () => {
    let resolve!: (value: SupplierWorkspace) => void
    vi.mocked(api.workspace).mockImplementationOnce(() => new Promise(r => { resolve = r }))
    const w = mount(Component, { props: { factoryId: 'huaxing' } })
    const second = workspace(); second.factory_id = 'other'; second.supplier_name = '另一厂供应商'; second.sources = []
    vi.mocked(api.workspace).mockResolvedValueOnce(second)
    await w.setProps({ factoryId: 'other' }); await flushPromises()
    resolve(workspace()); await flushPromises()
    expect(w.text()).toContain('另一厂供应商'); expect(w.text()).not.toContain('DELIVERY-1')
    w.unmount()
  })
  it('does not use inventory cost as an approved supplier return price', async () => {
    const ws = workspace(); ws.sources[0]!.kind = 'RETURN'; ws.sources[0]!.source_key = 'RETURN:M1'; ws.sources[0]!.unit_price = null; ws.sources[0]!.amount = null
    vi.mocked(api.workspace).mockResolvedValue(ws)
    const w = mount(Component, { props: { factoryId: 'huaxing' } }); await flushPromises()
    expect(w.get<HTMLInputElement>('input[aria-label^="认可退货单价"]').element.value).toBe('')
    await button(w, '展开原单与验收对照').trigger('click')
    expect(w.text()).toContain('按下方退货依据结算')
    expect(w.text()).toContain('库存平均成本不作为退货结算价')
    w.unmount()
  })
  it('refreshes stale sources without silently deleting vendor evidence and makes removed sources resolvable', async () => {
    const ws = workspace(); const doc = document(); doc.stale = true; ws.documents = [doc]
    ws.source_fingerprint = 'b'.repeat(64); ws.sources[0]!.source_key = 'RECEIPT:NEW'; ws.sources[0]!.document_no = 'NEW-DELIVERY'
    vi.mocked(api.workspace).mockResolvedValue(ws); vi.mocked(api.save).mockResolvedValue(document())
    const w = mount(Component, { props: { factoryId: 'huaxing' } }); await flushPromises()
    await button(w, '更新来源并重新核对').trigger('click')
    expect(w.get<HTMLInputElement>('[aria-label="未匹配送货单 L1"]').element.value).toBe('DELIVERY-1')
    if (w.find('[aria-label="处理结算明细 L1"]').exists()) await w.find('[aria-label="处理结算明细 L1"]').trigger('click')
    expect(w.get<HTMLInputElement>('[aria-label="账单金额 L1"]').element.value).toBe('20.00')
    expect(button(w, '移除录错行')).toBeDefined()
    expect(button(w, '确认对账完成').attributes('disabled')).toBeDefined()
    await button(w, '保存并核对差异').trigger('submit'); await flushPromises()
    expect(api.save).toHaveBeenCalledWith(expect.objectContaining({ source_fingerprint: 'b'.repeat(64), expected_revision: 1, lines: [expect.objectContaining({ source_key: 'RECEIPT:NEW', amount: null }), expect.objectContaining({ source_key: '', document_no: 'DELIVERY-1', amount: '20.00' })] }))
    w.unmount()
  })
})
