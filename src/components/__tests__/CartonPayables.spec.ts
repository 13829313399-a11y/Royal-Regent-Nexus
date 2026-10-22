import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import Component from '../CartonPayables.vue'
import { cartonPayablesApi as api, pendingPayableAction, type PayableAction } from '@/api/cartonPayables'
import { payableEntry, payableVersion, payableWorkspace } from './cartonPayablesFixture'
vi.mock('@/lib/http', () => ({ http: {}, getApiErrorMessage: (cause: Error) => cause.message, getApiErrorMessageAsync: async (cause: Error) => cause.message }))
vi.mock('@/api/cartonPayables', () => ({ cartonPayablesApi: { workspace: vi.fn(), detail: vi.fn(), act: vi.fn(), export: vi.fn() }, pendingPayableAction: vi.fn(), clearPendingPayableAction: vi.fn() }))
const props = { factoryId: 'huaxing', internal: true, viewerKey: 'finance-actor:1' }
const button = (w: ReturnType<typeof mount>, text: string) => w.findAll('button').find(row => row.text() === text)!
beforeEach(() => {
  vi.resetAllMocks(); vi.useFakeTimers({ toFake: ['Date', 'setTimeout', 'clearTimeout'] }); vi.setSystemTime(new Date('2026-10-21T03:00:00Z'))
  vi.mocked(api.workspace).mockResolvedValue(payableWorkspace()); vi.mocked(api.detail).mockResolvedValue({ ...payableEntry(), account_revision: 7, source_fingerprint: 'f'.repeat(64) }); vi.mocked(api.act).mockResolvedValue({ ...payableWorkspace(), revision: 8 }); vi.mocked(pendingPayableAction).mockReturnValue(null)
})
afterEach(() => vi.useRealTimers())
async function fillMoney(w: ReturnType<typeof mount>, amount = '12.30') { await w.get('[aria-label="应付业务日期"]').setValue('2026-10-15'); await w.get('[aria-label="应付凭证号"]').setValue('VOUCHER1'); await w.get('[aria-label="应付原金额"]').setValue(amount); await w.get('[aria-label="应付处理原因"]').setValue('核对真实业务凭证') }
async function openPayment(w: ReturnType<typeof mount>) { await button(w, '期初、费用与资金凭证').trigger('click'); await w.get('[aria-label="查看往来凭证 BANK-OUT1"]').trigger('click'); await flushPromises() }
it('uses full server totals and separates actual payments, receipts, allocations and both refund kinds', async () => {
  const w = mount(Component, { props }); await flushPromises()
  expect(api.workspace).toHaveBeenCalledWith(true, { factory_id: 'huaxing', currency: 'CNY', kind: 'ALL', status: 'ALL', keyword: '', limit: 25, offset: 0 }, expect.any(AbortSignal))
  expect(w.get('[aria-label="应付余额汇总"]').text()).toContain('410.00 CNY'); expect(w.text()).toContain('供应商尚未确认收款（待回执／异议）'); expect(w.text()).toContain('已扣记录余额，尚不能核销')
  expect(w.text()).toContain('− 本厂实际付款 200.00 + 已确认预付款退回 20.00'); expect(w.text()).toContain('退货现金已在货款月结净额内，不重复计账')
  expect(w.text()).toContain('核销不改变上述公式'); expect(w.text()).not.toMatch(/库存成本|仓位|内部用途/); w.unmount()
})
it('never presents zero placeholders as a cleared account before bilateral opening activation', async () => {
  vi.mocked(api.workspace).mockResolvedValue({ ...payableWorkspace(), opening: null, allowed_actions: ['PROPOSE_OPENING'] })
  const w = mount(Component, { props }); await flushPromises()
  expect(w.get('[aria-label="应付账户尚未启用"]').text()).toContain('不代表零欠款或已经结清')
  expect(w.find('[aria-label="应付余额汇总"]').exists()).toBe(false); expect(button(w, '登记实际付款')).toBeUndefined(); w.unmount()
})
it('records a real payment with exact decimal evidence and preserves inputs after a definitive error', async () => {
  vi.mocked(api.act).mockRejectedValue(new Error('凭证号已经登记'))
  const w = mount(Component, { props }); await flushPromises(); await button(w, '登记实际付款').trigger('click'); await fillMoney(w, '12.30'); await w.get('[aria-label="往来资金凭证"]').setValue('BANK-REAL1')
  await w.get('form').trigger('submit'); await flushPromises()
  expect(api.act).toHaveBeenCalledWith(true, expect.objectContaining({ factory_id: 'huaxing', supplier_id: 'SUP1', currency: 'CNY', expected_revision: 7, source_fingerprint: 'f'.repeat(64), action: 'RECORD_PAYMENT', payment_date: '2026-10-15', amount: '12.30', document_no: 'VOUCHER1', bank_reference: 'BANK-REAL1' }), 'finance-actor:1', expect.any(AbortSignal))
  expect(w.get<HTMLInputElement>('[aria-label="应付原金额"]').element.value).toBe('12.30'); expect(w.get('[role="alert"]').text()).toContain('凭证号已经登记'); w.unmount()
})
it('keeps a completed money action distinct from a later balance-refresh failure', async () => {
  const w = mount(Component, { props }); await flushPromises(); await button(w, '登记实际付款').trigger('click'); await fillMoney(w); await w.get('[aria-label="往来资金凭证"]').setValue('BANK-REAL1')
  vi.mocked(api.workspace).mockRejectedValueOnce(new Error('余额读取暂不可用'))
  await w.get('form').trigger('submit'); await flushPromises()
  expect(w.get('[role="status"]').text()).toContain('登记实际付款已保存'); expect(w.get('[role="alert"]').text()).toContain('操作已保存，但往来余额刷新失败')
  expect(w.find('form').exists()).toBe(false); expect(api.act).toHaveBeenCalledTimes(1); w.unmount()
})
it('retains and retries the original uncertain action including its old account evidence after refresh', async () => {
  const pending: PayableAction = { request_id: 'original-request-123456', factory_id: 'huaxing', supplier_id: 'SUP1', currency: 'CNY', expected_revision: 4, source_fingerprint: 'old-source', action: 'RECORD_PAYMENT', payment_date: '2026-10-15', amount: '12.30', document_no: 'VOUCHER1', bank_reference: 'BANK-REAL1', reason: '核对真实业务凭证' }
  vi.mocked(pendingPayableAction).mockReturnValue(pending)
  const w = mount(Component, { props }); await flushPromises()
  expect(button(w, '登记实际付款').attributes('disabled')).toBeDefined()
  await button(w, '重试原未确认请求').trigger('click'); await flushPromises()
  const { request_id: ignored, ...body } = pending
  expect(api.act).toHaveBeenCalledWith(true, body, 'finance-actor:1', expect.any(AbortSignal)); w.unmount()
})
it('supports explicit zero opening and a credit direction without guessing historical dates', async () => {
  vi.mocked(api.workspace).mockResolvedValue({ ...payableWorkspace(), opening: null })
  const w = mount(Component, { props }); await flushPromises(); await button(w, '提出期初余额').trigger('click'); await fillMoney(w, '0.00'); await w.get('[aria-label="应付业务日期"]').setValue('2026-09-01'); await w.get('[aria-label="应付金额方向"]').setValue('CREDIT'); await w.get('[aria-label="确认历史未明来源依据"]').setValue(true)
  await w.get('form').trigger('submit'); await flushPromises()
  expect(api.act).toHaveBeenCalledWith(true, expect.objectContaining({ action: 'PROPOSE_OPENING', cutoff_date: '2026-09-01', amount: '0.00', direction: 'CREDIT', acknowledge_unknown_sources: true }), props.viewerKey, expect.any(AbortSignal)); w.unmount()
})
it('keeps effective and proposed amounts apart and gives supplier only its exact-version review actions', async () => {
  const row = { ...payableEntry(), id: 'OPEN1', kind: 'OPENING' as const, document_no: 'OPEN-SEP', active: payableVersion(), proposal: { ...payableVersion(), event_id: 'P2', version: 2, amount: '150.00', signed_amount: '150.00', status: 'PENDING_SUPPLIER' }, allowed_actions: ['REVIEW_OPENING', 'CONFIRM_OPENING'] }
  vi.mocked(api.workspace).mockResolvedValue({ ...payableWorkspace(), opening: row, records: { items: [row], total: 1, limit: 25, offset: 0 } }); vi.mocked(api.detail).mockResolvedValue({ ...row, account_revision: 7, source_fingerprint: 'f'.repeat(64) })
  const w = mount(Component, { props: { internal: false, factories: [{ factory_id: 'huaxing' }], viewerKey: 'supplier:1' } }); await flushPromises(); await button(w, '期初、费用与资金凭证').trigger('click')
  expect(w.text()).toContain('旧有效 100.00 暂计；新提议 150.00 待双方确认')
  await w.get('[aria-label="查看往来凭证 OPEN-SEP"]').trigger('click'); await flushPromises()
  expect(button(w, '内部确认期初')).toBeUndefined(); await w.get('[aria-label="应付处理原因"]').setValue('核对期初差异凭证'); await w.get('[aria-label="往来核对结果"]').setValue('DISPUTED'); await w.get('form').trigger('submit'); await flushPromises()
  expect(api.act).toHaveBeenCalledWith(false, expect.objectContaining({ action: 'REVIEW_OPENING', target_id: 'OPEN1', decision: 'DISPUTED', expected_revision: 7 }), 'supplier:1', expect.any(AbortSignal)); w.unmount()
})
it('allows supplier advance-return declaration only against server-provided parent capacity, independently of receipt and material returns', async () => {
  const w = mount(Component, { props: { internal: false, factories: [{ factory_id: 'huaxing' }], viewerKey: 'supplier:1' } }); await flushPromises(); await button(w, '声明预付款实际退回').trigger('click'); await fillMoney(w, '18.00')
  expect(w.get('[aria-label="预付款退回原付款"]').text()).toContain('BANK-OUT1 · 可退回 180.00 CNY')
  await w.get('[aria-label="预付款退回原付款"]').setValue('PAY1'); await w.get('[aria-label="往来资金凭证"]').setValue('BANK-IN1'); await w.get('form').trigger('submit'); await flushPromises()
  expect(api.act).toHaveBeenCalledWith(false, expect.objectContaining({ action: 'DECLARE_PAYMENT_RETURN', parent_payment_id: 'PAY1', return_date: '2026-10-15', amount: '18.00', bank_reference: 'BANK-IN1' }), 'supplier:1', expect.any(AbortSignal)); w.unmount()
})
it('uses exact credit/target identities, server capacities and integer-cent allocation previews', async () => {
  const w = mount(Component, { props }); await flushPromises(); await button(w, '登记核销分配').trigger('click')
  expect(w.get('[aria-label="核销来源"]').text()).not.toContain('BANK-OUT1')
  await w.get('[aria-label="核销来源"]').setValue('FEE:CONFIRM-CREDIT1')
  await w.get('[aria-label="选择核销目标 OPEN-SEP"]').setValue(true); await w.get('[aria-label="本次核销 OPEN-SEP"]').setValue('0.10')
  await w.get('[aria-label="选择核销目标 BILL-SEP"]').setValue(true); await w.get('[aria-label="本次核销 BILL-SEP"]').setValue('0.20')
  expect(w.get('[aria-label="本次核销金额合计"]').text()).toContain('0.30 CNY'); expect(w.text()).toContain('未核销 500.00 CNY')
  await w.get('[aria-label="应付处理原因"]').setValue('按双方凭证逐项抵扣'); await w.get('form').trigger('submit'); await flushPromises()
  expect(api.act).toHaveBeenCalledWith(true, expect.objectContaining({ action: 'ALLOCATE', source_kind: 'CREDIT', source_id: 'FEE:CONFIRM-CREDIT1', targets: [{ target_kind: 'OPENING', target_id: 'OPENING:CONFIRM-OPEN1', amount: '0.10' }, { target_kind: 'SETTLEMENT', target_id: 'SETTLEMENT:BILL1', amount: '0.20' }] }), props.viewerKey, expect.any(AbortSignal)); w.unmount()
})
it('releases only selected allocations using frozen business documents while preserving cash facts', async () => {
  const w = mount(Component, { props }); await flushPromises(); await button(w, '核销与解除记录').trigger('click')
  expect(w.text()).toContain('BANK-OLD → 货款月结 BILL-OLD · 2026-09 · 版本 3'); expect(w.text()).not.toContain('HISTORICAL-LONG-SOURCE-ID')
  await button(w, '解除原核销分配').trigger('click'); await w.get('[aria-label="解除核销 A1"]').setValue(true); await w.get('[aria-label="应付处理原因"]').setValue('原单重核先解除分配'); await w.get('form').trigger('submit'); await flushPromises()
  expect(api.act).toHaveBeenCalledWith(true, expect.objectContaining({ action: 'DEALLOCATE', allocation_ids: ['A1'] }), props.viewerKey, expect.any(AbortSignal)); w.unmount()
})
it('requires an explicit correction reference and never labels a void as a real bank refund', async () => {
  const w = mount(Component, { props }); await flushPromises(); await openPayment(w); await button(w, '申请更正错误资金记录').trigger('click'); await w.get('[aria-label="应付处理原因"]').setValue('原付款凭证重复录入'); await w.get('form').trigger('submit'); expect(api.act).not.toHaveBeenCalled()
  expect(w.text()).toContain('原资金事实在双方更正完成前继续计账'); await w.get('[aria-label="错误资金更正凭证"]').setValue('ERR-CORRECTION1'); await w.get('form').trigger('submit'); await flushPromises()
  expect(api.act).toHaveBeenCalledWith(true, expect.objectContaining({ action: 'REQUEST_VOID', target_id: 'PAY1', correction_reference: 'ERR-CORRECTION1' }), props.viewerKey, expect.any(AbortSignal)); w.unmount()
})
it('blocks a record action when its account revision is newer than the displayed workspace', async () => {
  vi.mocked(api.detail).mockResolvedValue({ ...payableEntry(), account_revision: 8, source_fingerprint: 'new-context' })
  const w = mount(Component, { props }); await flushPromises(); await openPayment(w)
  expect(button(w, '申请更正错误资金记录').attributes('disabled')).toBeDefined(); expect(w.text()).toContain('依据或账户版本变化'); expect(api.act).not.toHaveBeenCalled(); w.unmount()
})
it('records independent deductible fees against the exact related bill without rewriting goods monthly amounts', async () => {
  const w = mount(Component, { props }); await flushPromises(); await button(w, '提出独立费用').trigger('click'); await fillMoney(w, '0.50')
  await w.get('[aria-label="应付金额方向"]').setValue('DEDUCT_PAYABLE'); await w.get('[aria-label="独立费用类别"]').setValue('ROUNDING'); await w.get('[aria-label="费用关联月结"]').setValue('BILL1')
  expect(w.text()).toContain('已确认货款净额 500.00'); await w.get('form').trigger('submit'); await flushPromises()
  expect(api.act).toHaveBeenCalledWith(true, expect.objectContaining({ action: 'PROPOSE_FEE', amount: '0.50', fee_date: '2026-10-15', direction: 'DEDUCT_PAYABLE', category: 'ROUNDING', related_settlement_id: 'BILL1' }), props.viewerKey, expect.any(AbortSignal))
  expect(vi.mocked(api.act).mock.calls[0]![1]).not.toHaveProperty('lines'); w.unmount()
})
it('requires internal bank confirmation of an actual advance return and retains the original payment document in history', async () => {
  const row = { ...payableEntry(), id: 'RET1', kind: 'PAYMENT_RETURN' as const, status: 'DECLARED', document_no: 'ADVANCE-BACK1', amount: '18.00', parent_payment_id: 'PAY1', parent_payment_document_no: 'BANK-ORIGINAL', allowed_actions: ['CONFIRM_PAYMENT_RETURN'] }
  vi.mocked(api.workspace).mockResolvedValue({ ...payableWorkspace(), records: { items: [row], total: 1, limit: 25, offset: 0 } }); vi.mocked(api.detail).mockResolvedValue({ ...row, account_revision: 7, source_fingerprint: 'f'.repeat(64) })
  const w = mount(Component, { props }); await flushPromises(); await button(w, '期初、费用与资金凭证').trigger('click'); await w.get('[aria-label="查看往来凭证 ADVANCE-BACK1"]').trigger('click'); await flushPromises()
  expect(w.text()).toContain('原付款 BANK-ORIGINAL；该退回不属于物料退货现金')
  await w.get('[aria-label="应付处理原因"]').setValue('核实预付款退回银行入账'); await w.get('form').trigger('submit'); expect(api.act).not.toHaveBeenCalled()
  await w.get('[aria-label="预付款退回核实凭证"]').setValue('ACTUAL-IN1'); await w.get('form').trigger('submit'); await flushPromises()
  expect(api.act).toHaveBeenCalledWith(true, expect.objectContaining({ action: 'CONFIRM_PAYMENT_RETURN', target_id: 'RET1', confirmation_reference: 'ACTUAL-IN1' }), props.viewerKey, expect.any(AbortSignal)); w.unmount()
})
it('keeps a read-only account readable without inventing financial write authority', async () => {
  const row = { ...payableEntry(), allowed_actions: [] }
  vi.mocked(api.workspace).mockResolvedValue({ ...payableWorkspace(), allowed_actions: [], records: { items: [row], total: 1, limit: 25, offset: 0 } }); vi.mocked(api.detail).mockResolvedValue({ ...row, account_revision: 7, source_fingerprint: 'f'.repeat(64) })
  const w = mount(Component, { props }); await flushPromises(); await openPayment(w)
  expect(w.text()).toContain('真实付款流水'); expect(button(w, '登记实际付款')).toBeUndefined(); expect(button(w, '申请更正错误资金记录')).toBeUndefined(); expect(api.act).not.toHaveBeenCalled(); w.unmount()
})
it.each(['factory', 'viewer'])('does not restore an old completed money response after changing %s', async boundary => {
  const w = mount(Component, { props }); await flushPromises(); await button(w, '登记实际付款').trigger('click'); await fillMoney(w); await w.get('[aria-label="往来资金凭证"]').setValue('BANK-REAL1')
  let resolve!: (value: ReturnType<typeof payableWorkspace>) => void
  vi.mocked(api.act).mockImplementationOnce(() => new Promise(done => { resolve = done })); await w.get('form').trigger('submit'); await flushPromises()
  const signal = vi.mocked(api.act).mock.calls[0]![3]!
  vi.mocked(api.workspace).mockResolvedValue({ ...payableWorkspace(), supplier_name: '当前范围供方', opening: null, records: { items: [], total: 0, limit: 25, offset: 0 } })
  if (boundary === 'factory') await w.setProps({ factoryId: 'huadeng' }); else await w.setProps({ viewerKey: 'new-actor:2' })
  await flushPromises(); resolve(payableWorkspace()); await flushPromises()
  expect(signal.aborted).toBe(true); expect(w.text()).toContain('当前范围供方'); expect(w.text()).not.toContain('登记实际付款已保存'); expect(w.find('form').exists()).toBe(false); w.unmount()
})
it('prevents changing the currency while a money submission is in flight', async () => {
  const w = mount(Component, { props }); await flushPromises(); await button(w, '登记实际付款').trigger('click'); await fillMoney(w); await w.get('[aria-label="往来资金凭证"]').setValue('BANK-REAL1')
  let resolve!: (value: ReturnType<typeof payableWorkspace>) => void
  vi.mocked(api.act).mockImplementationOnce(() => new Promise(done => { resolve = done })); await w.get('form').trigger('submit'); await flushPromises()
  expect(w.get('[aria-label="应付币种"]').attributes('disabled')).toBeDefined()
  resolve(payableWorkspace()); await flushPromises(); expect(w.get('[role="status"]').text()).toContain('登记实际付款已保存'); w.unmount()
})
it.each(['factory', 'viewer', 'currency'])('discards old %s read results and does not restore their financial records', async boundary => {
  let resolve!: (value: ReturnType<typeof payableWorkspace>) => void
  vi.mocked(api.workspace).mockImplementationOnce(() => new Promise(done => { resolve = done }))
  const w = mount(Component, { props }); await flushPromises(); const signal = vi.mocked(api.workspace).mock.calls[0]![2]!
  vi.mocked(api.workspace).mockResolvedValue({ ...payableWorkspace(), supplier_name: '当前范围供方', opening: null, records: { items: [], total: 0, limit: 25, offset: 0 } })
  if (boundary === 'factory') await w.setProps({ factoryId: 'huadeng' }); else if (boundary === 'viewer') await w.setProps({ viewerKey: 'new-actor:2' }); else await w.get('[aria-label="应付币种"]').setValue('HKD')
  await flushPromises(); resolve(payableWorkspace()); await flushPromises()
  expect(signal.aborted).toBe(true); expect(w.text()).toContain('当前范围供方'); expect(w.text()).not.toContain('410.00 CNY'); w.unmount()
})
