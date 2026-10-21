import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import Component from '../CartonSupplierReturns.vue'
import { cartonSupplierReturnsApi as api, type SupplierReturn, type ReturnWorkspace } from '@/api/cartonSupplierReturns'

vi.mock('@/lib/http', () => ({ http: {}, getApiErrorMessage: (cause: Error) => cause.message }))
vi.mock('@/api/cartonSupplierReturns', () => ({ cartonSupplierReturnsApi: { list: vi.fn(), detail: vi.fn(), act: vi.fn() } }))
import { row } from './cartonReturnFixture'
const workspace = (items: SupplierReturn[], total = items.length): ReturnWorkspace => ({ items, total, pending_count: items.filter(item => item.pending).length, legacy_count: items.filter(item => item.legacy).length, limit: 20, offset: 0 })
const props = { factoryId: 'huaxing', viewerKey: 'vendor-v1' }
const button = (w: ReturnType<typeof mount>, text: string) => w.findAll('button').find(item => item.text() === text)!
beforeEach(() => {
  vi.resetAllMocks(); vi.useFakeTimers({ toFake: ['Date', 'setTimeout', 'clearTimeout'] }); vi.setSystemTime(new Date('2026-10-20T12:00:00Z'))
  vi.mocked(api.list).mockResolvedValue(workspace([row()]))
  vi.mocked(api.detail).mockResolvedValue(row()); vi.mocked(api.act).mockResolvedValue({ ...row(), revision: 3 })
})
afterEach(() => vi.useRealTimers())
it('uses server pending scope, distinguishes real quantities and verified cash, and exposes no stock cost or location fields', async () => {
  const w = mount(Component, { props }); await flushPromises()
  expect(api.list).toHaveBeenCalledWith('huaxing', false, { limit: 20, offset: 0, status: 'PENDING' }, expect.any(AbortSignal))
  expect(w.text()).toContain('已签收 4 · 异议 1'); expect(w.text()).toContain('待签收 5 张')
  expect(w.text()).toContain('已核实现金 0.00'); expect(w.text()).toContain('贷项 待核实 CNY')
  expect(w.text()).toContain('此退货累计净抵扣（跨月合计）')
  expect(w.text()).not.toMatch(/平均成本|仓位|库存估值/)
  await button(w, '查看与处理').trigger('click'); await flushPromises()
  expect(w.text()).toContain('SIGN-1'); expect(w.findAll('[aria-label="退货处理动作"] option').map(item => item.text())).toEqual(['选择处理事项', '登记本次签收', '登记本次异议'])
  w.unmount()
})
it('posts exact partial receipt evidence and retains one idempotency key after an uncertain response, including HTTP without randomUUID', async () => {
  const original = Object.getOwnPropertyDescriptor(globalThis.crypto, 'randomUUID')
  Object.defineProperty(globalThis.crypto, 'randomUUID', { configurable: true, value: undefined })
  vi.mocked(api.act).mockRejectedValueOnce(new Error('网络中断，状态待核实'))
  const w = mount(Component, { props }); await flushPromises()
  try {
    await button(w, '查看与处理').trigger('click'); await flushPromises()
    await w.get('[aria-label="退货处理动作"]').setValue('RECEIVE')
    await w.get('[aria-label="本次签收或异议数量"]').setValue('2.5000')
    await w.get('[aria-label="签收或异议日期"]').setValue('2026-10-03')
    await w.get('[aria-label="退货处理凭证单号"]').setValue('SIGN-2')
    await w.get('[aria-label="退货处理原因"]').setValue('核对本次送回纸品')
    await w.get('form').trigger('submit'); await flushPromises()
    expect(w.get('[role="alert"]').text()).toContain('网络中断')
    const first = vi.mocked(api.act).mock.calls[0]![2]
    expect(first).toMatchObject({ factory_id: 'huaxing', expected_revision: 2, source_fingerprint: 'f'.repeat(64), action: 'RECEIVE', quantity: '2.5000', receipt_date: '2026-10-03', document_no: 'SIGN-2', reason: '核对本次送回纸品' })
    expect(first.request_id).toMatch(/^[0-9a-f-]{36}$/i)
    await w.get('form').trigger('submit'); await flushPromises()
    expect(vi.mocked(api.act).mock.calls[1]![2]).toEqual(first)
    expect(w.get('[role="status"]').text()).toContain('回执已保存')
  } finally { w.unmount(); if (original) Object.defineProperty(globalThis.crypto, 'randomUUID', original); else delete (globalThis.crypto as Partial<Crypto>).randomUUID }
})
it('requires an exact refund target and internal reference without treating a supplier cash declaration as verified money', async () => {
  const detail = { ...row(), allowed_actions: ['CONFIRM_REFUND'], credit: { id: 'CREDIT1', unit_price: '2', amount: '20.00', document_no: 'CREDIT1', credit_date: '2026-10-03', status: 'CONFIRMED' }, refunds: [{ id: 'CASH1', kind: 'CASH' as const, amount: '6.00', refund_date: '2026-10-04', document_no: 'BANK1', status: 'PROPOSED' as const, reason: '银行退款申报', actor_name: '供方财务', created_at: '2026-10-04T08:00:00Z', credit_event_id: 'CREDIT1' }] }
  vi.mocked(api.list).mockResolvedValue(workspace([detail])); vi.mocked(api.detail).mockResolvedValue(detail)
  const w = mount(Component, { props: { ...props, internal: true } }); await flushPromises()
  expect(w.text()).toContain('已核实现金 0.00')
  await button(w, '查看与处理').trigger('click'); await flushPromises()
  expect(w.text()).toContain('现金退款 · 2026-10-04 · BANK1 · 6.00 CNY · 待内部核实')
  await w.get('[aria-label="退货处理动作"]').setValue('CONFIRM_REFUND')
  await w.get('[aria-label="退货处理原因"]').setValue('财务核对银行流水')
  await w.get('form').trigger('submit'); expect(api.act).not.toHaveBeenCalled()
  await w.get('[aria-label="内部到账或抵扣核实凭证"]').setValue('BANK-VERIFIED-1')
  await w.get('form').trigger('submit'); await flushPromises()
  expect(api.act).toHaveBeenCalledWith('M1', true, expect.objectContaining({ action: 'CONFIRM_REFUND', target_event_id: 'CASH1', confirmation_reference: 'BANK-VERIFIED-1' }), expect.any(AbortSignal))
  w.unmount()
})
it('loads history explicitly, labels unenrolled legacy returns, and never fabricates a new pending task', async () => {
  vi.mocked(api.list).mockResolvedValueOnce(workspace([])).mockResolvedValue(workspace([{ ...row(), enabled: false, legacy: true, pending: false, allowed_actions: ['ENROLL'] }]))
  const w = mount(Component, { props: { ...props, internal: true } }); await flushPromises()
  expect(w.text()).toContain('当前没有退货待办')
  await w.get('[aria-label="显示全部退货历史"]').setValue(true); await vi.advanceTimersByTimeAsync(250); await flushPromises()
  expect(vi.mocked(api.list).mock.calls.at(-1)![2]).toEqual({ limit: 20, offset: 0 })
  expect(w.text()).toContain('未接入协同'); expect(w.text()).toContain('全部历史 · 1 笔')
  w.unmount()
})
it('discards late factory/viewer results and removes draft evidence after an authority change', async () => {
  let resolve!: (value: ReturnWorkspace) => void
  vi.mocked(api.list).mockImplementationOnce(() => new Promise(done => { resolve = done }))
  const w = mount(Component, { props }); await flushPromises()
  const signal = vi.mocked(api.list).mock.calls[0]![3]!
  vi.mocked(api.list).mockResolvedValue(workspace([]))
  await w.setProps({ factoryId: 'huakang-a', viewerKey: 'vendor-v2' }); await flushPromises()
  expect(signal.aborted).toBe(true)
  resolve(workspace([row()])); await flushPromises()
  expect(w.text()).not.toContain('RETURN-1'); expect(w.text()).not.toContain('客户A')
  expect(w.find('form').exists()).toBe(false)
  w.unmount()
})
it('uses server search/pagination and makes successful write plus failed refresh distinguishable', async () => {
  vi.mocked(api.list).mockResolvedValue(workspace([row()], 21))
  const w = mount(Component, { props: { ...props, search: '' } }); await flushPromises()
  await button(w, '下一页').trigger('click'); await flushPromises()
  expect(vi.mocked(api.list).mock.calls.at(-1)![2].offset).toBe(20)
  await w.setProps({ search: '合同A' }); await vi.advanceTimersByTimeAsync(250); await flushPromises()
  expect(vi.mocked(api.list).mock.calls.at(-1)![2]).toEqual({ limit: 20, offset: 0, status: 'PENDING', keyword: '合同A' })
  vi.mocked(api.detail).mockResolvedValue({ ...row(), allowed_actions: ['RECONFIRM_DATE'] })
  await button(w, '查看与处理').trigger('click'); await flushPromises()
  await w.get('[aria-label="退货处理动作"]').setValue('RECONFIRM_DATE')
  await w.get('[aria-label="退货处理原因"]').setValue('已核对新实际退货日')
  vi.mocked(api.list).mockRejectedValueOnce(new Error('列表暂不可用'))
  await w.get('form').trigger('submit'); await flushPromises()
  expect(w.get('[role="alert"]').text()).toContain('回执已保存，列表刷新失败')
  expect(w.find('form').exists()).toBe(false)
  w.unmount()
})

it.each(['CASH', 'OFFSET'] as const)('sends %s declaration as evidence without inventing a verified receipt or recomputing money', async kind => {
  const detail = { ...row(), allowed_actions: ['DECLARE_REFUND'] }
  vi.mocked(api.detail).mockResolvedValue(detail)
  const w = mount(Component, { props }); await flushPromises()
  await button(w, '查看与处理').trigger('click'); await flushPromises()
  await w.get('[aria-label="退货处理动作"]').setValue('DECLARE_REFUND')
  await w.get('[aria-label="退款或抵扣方式"]').setValue(kind)
  await w.get('[aria-label="本次退款或抵扣金额"]').setValue('0.10')
  await w.get('[aria-label="退款或抵扣日期"]').setValue('2026-10-04')
  await w.get('[aria-label="退货处理凭证单号"]').setValue('REFUND-PAPER-1')
  await w.get('[aria-label="退货处理原因"]').setValue('按原凭证登记本次处理')
  expect(w.text()).toContain('未核实申报不自动计到账')
  await w.get('form').trigger('submit'); await flushPromises()
  expect(api.act).toHaveBeenCalledWith('M1', false, expect.objectContaining({ action: 'DECLARE_REFUND', kind, amount: '0.10', refund_date: '2026-10-04', document_no: 'REFUND-PAPER-1' }), expect.any(AbortSignal))
  expect(detail.cash_confirmed_amount).toBe('0.00'); w.unmount()
})
it('requires exact server-projected void targets and separate internal evidence for an erroneous confirmed cash receipt', async () => {
  const detail: SupplierReturn = { ...row(), allowed_actions: ['VOID'], voidable_event_ids: ['CASH1'], void_confirmation_required_event_ids: ['CASH1'], refunds: [{ id: 'CASH1', kind: 'CASH', amount: '6.00', refund_date: '2026-10-04', document_no: 'BANK1', status: 'CONFIRMED', reason: '供应商退款申报', actor_name: '供方财务', created_at: '2026-10-04T08:00:00Z', credit_event_id: 'CREDIT1', confirmation_id: 'INTERNAL-CONFIRM-1' }] }
  vi.mocked(api.detail).mockResolvedValue(detail)
  const w = mount(Component, { props: { ...props, internal: true } }); await flushPromises()
  await button(w, '查看与处理').trigger('click'); await flushPromises()
  await w.get('[aria-label="退货处理动作"]').setValue('VOID')
  const targetOptions = w.findAll('[aria-label="对应退货凭证"] option')
  expect(targetOptions.map(item => item.attributes('value'))).toEqual(['', 'CASH1'])
  expect(targetOptions.map(item => item.text()).join('')).not.toContain('SIGN-1')
  await w.get('[aria-label="退货处理原因"]').setValue('原银行回执重复登记需更正')
  await w.get('form').trigger('submit'); expect(api.act).not.toHaveBeenCalled()
  await w.get('[aria-label="内部到账或抵扣核实凭证"]').setValue('CORRECT-BANK-1')
  await w.get('form').trigger('submit'); await flushPromises()
  expect(api.act).toHaveBeenCalledWith('M1', true, expect.objectContaining({ action: 'VOID', target_event_id: 'CASH1', confirmation_reference: 'CORRECT-BANK-1' }), expect.any(AbortSignal))
  w.unmount()
})
it('shows prior credit/date evidence and keeps dates needing reconfirmation separate from cash facts', async () => {
  const detail: SupplierReturn = { ...row(), allowed_actions: ['RECONFIRM_DATE'], date_reconfirmation_required: true, cash_confirmed_amount: '6.00',
    credits: [{ id: 'C1', unit_price: '2', amount: '20.00', document_no: 'CR-OLD', credit_date: '2026-10-02', status: 'SUPERSEDED' }, { id: 'C2', unit_price: '2.5', amount: '25.00', document_no: 'CR-NEW', credit_date: '2026-10-03', status: 'CONFIRMED' }],
    date_history: [{ id: 'D1', event_type: 'RETURN_DATE_CORRECTED', actor_name: '主管', created_at: '2026-10-20', before_date: '2026-10-01', return_date: '2026-09-30', revision: 2, reason: '原交接日期核实更正' }] }
  vi.mocked(api.detail).mockResolvedValue(detail)
  const w = mount(Component, { props }); await flushPromises()
  await button(w, '查看与处理').trigger('click'); await flushPromises()
  expect(w.text()).toContain('原签收和真实到账记录保留'); expect(w.text()).toContain('CR-OLD'); expect(w.text()).toContain('CR-NEW')
  expect(w.text()).toContain('2026-10-01 → 2026-09-30'); expect(w.text()).toContain('已被新版本替代')
  expect(w.findAll('[aria-label="退货处理动作"] option').map(item => item.attributes('value'))).toEqual(['', 'RECONFIRM_DATE'])
  w.unmount()
})
