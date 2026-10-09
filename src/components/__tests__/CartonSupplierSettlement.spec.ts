import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Component from '../CartonSupplierSettlement.vue'
import { supplierSettlementApi as api, type SupplierWorkspace, type SettlementDocument } from '@/api/cartonSupplierSettlement'

const mocks = vi.hoisted(() => ({ can: vi.fn(() => true), leave: vi.fn(), update: vi.fn() }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ can: mocks.can }) }))
vi.mock('vue-router', () => ({ onBeforeRouteLeave: mocks.leave, onBeforeRouteUpdate: mocks.update }))
vi.mock('@/lib/http', () => ({ http: {}, getApiErrorMessage: (e: Error) => e.message }))
vi.mock('@/api/cartonSupplierSettlement', () => ({ supplierSettlementApi: { workspace: vi.fn(), save: vi.fn(), confirm: vi.fn(), reopen: vi.fn(), acceptance: vi.fn() } }))
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
afterEach(() => vi.useRealTimers())
beforeEach(() => { vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-11-01T04:00:00Z')); vi.resetAllMocks(); mocks.can.mockReturnValue(true); vi.mocked(api.workspace).mockResolvedValue(workspace()) })

describe('供应商月结对账', () => {
  it('shows one bilateral workflow with normal data read-only and opens adjustment only on the selected line', async () => {
    vi.mocked(api.workspace).mockResolvedValue(collaborativeWorkspace())
    const w = mount(Component, { props: { factoryId: 'huaxing' } }); await flushPromises()
    expect(w.get('[aria-label="双方月结流程"]').text()).toContain('1 · 本厂核对并保存')
    expect(w.get('[aria-label="双方月结流程"]').text()).toContain('2 · 供应商核对确认')
    expect(w.get('[aria-label="双方月结流程"]').text()).toContain('3 · 本厂完成月结')
    expect(w.find('[aria-label="账单数量 L1"]').exists()).toBe(false)
    expect(w.get('[aria-label="拟结算明细 L1"]').text()).toContain('10 个')
    expect(w.get('thead').text()).toContain('供应商原送货本厂有效验收拟结算')
    await w.get('[aria-label="处理结算明细 L1"]').trigger('click')
    expect(w.get<HTMLInputElement>('[aria-label="账单数量 L1"]').element.value).toBe('10')
    expect(button(w, '放弃未保存内容')).toBeUndefined()  // Opening the row does not change business data.
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
    expect(w.get<HTMLInputElement>('[aria-label="账单数量 L1"]').element.value).toBe('10')
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
    await w.get('[aria-label="账单金额 L1"]').setValue('21')
    expect(button(w, '确认对账完成').attributes('disabled')).toBeDefined()
    expect(w.text()).toContain('保存后需重新取得供应商确认')
    w.unmount()
  })
  it('leaves vendor values empty and uses acceptance month independently of the order date', async () => {
    const w = mount(Component, { props: { factoryId: 'huaxing' } }); await flushPromises()
    expect(w.text()).toContain('2026-10-02'); expect(w.text()).toContain('SEP30')
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
    expect(w.get('[aria-label="账单金额 L1"]').attributes('disabled')).toBeDefined()
    expect(button(w, '保存并核对差异')).toBeUndefined()
    await w.get('[aria-label="供应商对账重核原因"]').setValue('更正供应商账单')
    await button(w, '建立重核版本').trigger('submit'); await flushPromises()
    expect(api.reopen).toHaveBeenCalledWith('D1', 'huaxing', 1, '更正供应商账单')
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
    expect(w.get('input[aria-label^="账单数量"]').attributes('disabled')).toBeDefined()
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
    expect(w.get<HTMLInputElement>('[aria-label="账单金额 L1"]').element.value).toBe('20.00')
    expect(button(w, '移除录错行')).toBeDefined()
    expect(button(w, '确认对账完成').attributes('disabled')).toBeDefined()
    await button(w, '保存并核对差异').trigger('submit'); await flushPromises()
    expect(api.save).toHaveBeenCalledWith(expect.objectContaining({ source_fingerprint: 'b'.repeat(64), expected_revision: 1, lines: [expect.objectContaining({ source_key: 'RECEIPT:NEW', amount: null }), expect.objectContaining({ source_key: '', document_no: 'DELIVERY-1', amount: '20.00' })] }))
    w.unmount()
  })
})
